#!/usr/bin/env python3
"""
Garden-Tiller Dell iDRAC Utilities
Provides functions for interacting with Dell iDRAC using Redfish API
Uses Structlog for logging and PyBreaker for resilience
"""

import os
import sys
import json
import time
import requests
import urllib3
import functools
import pybreaker
import structlog
import argparse
from datetime import datetime

# Suppress insecure HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize logger
logger = structlog.get_logger("idrac-utils")

# Configure circuit breaker
breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    exclude=[
        KeyError,
        ValueError,
        FileNotFoundError
    ]
)

# Define retry decorator with exponential backoff
def retry_with_backoff(max_tries=3, initial_delay=1):
    """Retry a function with exponential backoff"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            backoff = initial_delay
            
            while attempts < max_tries:
                try:
                    return func(*args, **kwargs)
                except pybreaker.CircuitBreakerError:
                    # Don't retry if the circuit is open
                    raise
                except Exception as e:
                    attempts += 1
                    if attempts == max_tries:
                        raise
                    # Exponential backoff
                    time.sleep(backoff)
                    backoff *= 2
            return func(*args, **kwargs)
        return wrapper
    return decorator

class IdracRedfishAPI:
    """Class for interacting with Dell iDRAC using Redfish API"""
    
    def __init__(self, idrac_ip, idrac_username, idrac_password, verify_ssl=False):
        """Initialize the IdracRedfishAPI with iDRAC credentials"""
        self.idrac_ip = idrac_ip
        self.idrac_username = idrac_username
        self.idrac_password = idrac_password
        self.base_url = f"https://{idrac_ip}"
        self.redfish_uri = "/redfish/v1"
        self.session = requests.Session()
        self.session.auth = (idrac_username, idrac_password)
        self.session.verify = verify_ssl
        self.session.headers.update({'Content-Type': 'application/json'})

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_request(self, uri):
        """Send GET request to iDRAC"""
        logger.debug("Sending GET request", url=f"{self.base_url}{uri}")
        response = self.session.get(f"{self.base_url}{uri}")
        response.raise_for_status()
        return response.json()

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_system_attributes(self):
        """Get LC system attributes"""
        logger.info("Getting LC system attributes", idrac_ip=self.idrac_ip)
        
        # Get Systems collection
        response = self.get_request(f"{self.redfish_uri}/Systems")
        
        if 'Members' not in response or len(response['Members']) == 0:
            logger.error("No systems found", idrac_ip=self.idrac_ip)
            return None
        
        # Get first system in the collection
        system_uri = response['Members'][0]['@odata.id']
        system_response = self.get_request(system_uri)
        
        # Get LC system attributes URI
        attributes_uri = f"{system_uri}/Oem/Dell/DellLC/LCAttributes"
        
        try:
            attributes_response = self.get_request(attributes_uri)
            return attributes_response.get('Attributes', {})
        except Exception as e:
            logger.error("Failed to get LC system attributes", idrac_ip=self.idrac_ip, error=str(e))
            return None

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_idrac_uptime(self):
        """Get iDRAC uptime"""
        logger.info("Getting iDRAC uptime", idrac_ip=self.idrac_ip)
        
        # Get Managers collection
        response = self.get_request(f"{self.redfish_uri}/Managers")
        
        if 'Members' not in response or len(response['Members']) == 0:
            logger.error("No managers found", idrac_ip=self.idrac_ip)
            return None
        
        # Get first manager in the collection (iDRAC)
        manager_uri = response['Members'][0]['@odata.id']
        manager_response = self.get_request(manager_uri)
        
        if 'Status' not in manager_response:
            logger.error("No status information found", idrac_ip=self.idrac_ip)
            return None
            
        # Get the last reset time and calculate uptime
        if 'LastResetTime' in manager_response:
            last_reset_time = manager_response['LastResetTime']
            try:
                # Format: YYYY-MM-DDThh:mm:ss+TZD
                reset_time = datetime.strptime(last_reset_time.split('+')[0], "%Y-%m-%dT%H:%M:%S")
                current_time = datetime.now()
                uptime_seconds = (current_time - reset_time).total_seconds()
                
                # Convert to days, hours, minutes, seconds
                days, remainder = divmod(uptime_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                uptime = {
                    'last_reset': last_reset_time,
                    'uptime_seconds': uptime_seconds,
                    'uptime_human': f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
                }
                return uptime
            except Exception as e:
                logger.error("Failed to parse uptime", idrac_ip=self.idrac_ip, error=str(e))
                return None
        
        logger.error("No LastResetTime found", idrac_ip=self.idrac_ip)
        return None

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_network_devices(self):
        """Get network devices information"""
        logger.info("Getting network devices information", idrac_ip=self.idrac_ip)
        
        # Get Systems collection
        response = self.get_request(f"{self.redfish_uri}/Systems")
        
        if 'Members' not in response or len(response['Members']) == 0:
            logger.error("No systems found", idrac_ip=self.idrac_ip)
            return None
        
        # Get first system in the collection
        system_uri = response['Members'][0]['@odata.id']
        
        # Get network interfaces
        networks_uri = f"{system_uri}/NetworkInterfaces"
        
        try:
            networks_response = self.get_request(networks_uri)
            
            if 'Members' not in networks_response or len(networks_response['Members']) == 0:
                logger.error("No network interfaces found", idrac_ip=self.idrac_ip)
                return None
                
            network_devices = []
            
            for member in networks_response['Members']:
                nic_uri = member['@odata.id']
                nic_response = self.get_request(nic_uri)
                
                # Get network ports for this interface
                if 'NetworkPorts' in nic_response:
                    ports_uri = nic_response['NetworkPorts']['@odata.id']
                    ports_response = self.get_request(ports_uri)
                    
                    if 'Members' in ports_response:
                        for port in ports_response['Members']:
                            port_uri = port['@odata.id']
                            port_response = self.get_request(port_uri)
                            
                            # Extract relevant information
                            port_info = {
                                'id': port_response.get('Id', 'Unknown'),
                                'name': port_response.get('Name', 'Unknown'),
                                'description': port_response.get('Description', ''),
                                'link_status': port_response.get('LinkStatus', 'Unknown'),
                                'mac_address': port_response.get('AssociatedNetworkAddresses', ['Unknown'])[0] if 'AssociatedNetworkAddresses' in port_response else 'Unknown',
                                'speed_mbps': port_response.get('CurrentLinkSpeedMbps', 0),
                                'full_duplex': port_response.get('LinkConfiguration', [{}])[0].get('FullDuplex', False) if 'LinkConfiguration' in port_response else False
                            }
                            network_devices.append(port_info)
            
            return network_devices
        except Exception as e:
            logger.error("Failed to get network devices", idrac_ip=self.idrac_ip, error=str(e))
            return None

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_ntp_settings(self):
        """Get NTP settings"""
        logger.info("Getting NTP settings", idrac_ip=self.idrac_ip)
        
        # Get Managers collection (iDRAC)
        response = self.get_request(f"{self.redfish_uri}/Managers")
        
        if 'Members' not in response or len(response['Members']) == 0:
            logger.error("No managers found", idrac_ip=self.idrac_ip)
            return None
        
        # Get first manager in the collection (iDRAC)
        manager_uri = response['Members'][0]['@odata.id']
        
        # Get network protocol settings
        network_protocol_uri = f"{manager_uri}/NetworkProtocol"
        
        try:
            protocol_response = self.get_request(network_protocol_uri)
            
            if 'NTP' not in protocol_response:
                logger.error("No NTP information found", idrac_ip=self.idrac_ip)
                return None
                
            ntp_info = {
                'enabled': protocol_response['NTP'].get('ProtocolEnabled', False),
                'ntp_servers': protocol_response['NTP'].get('NTPServers', []),
                'port': protocol_response['NTP'].get('Port', 0)
            }
            
            return ntp_info
        except Exception as e:
            logger.error("Failed to get NTP settings", idrac_ip=self.idrac_ip, error=str(e))
            return None

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_dns_settings(self):
        """Get DNS settings from LC attributes"""
        logger.info("Getting DNS settings", idrac_ip=self.idrac_ip)
        
        try:
            attributes = self.get_system_attributes()
            
            if not attributes:
                logger.error("No LC attributes found", idrac_ip=self.idrac_ip)
                return None
                
            dns_settings = {
                'dns_from_dhcp': attributes.get('IPv4.1.DNSFromDHCP', 'Unknown'),
                'dns1': attributes.get('IPv4.1.DNS1', 'Unknown'),
                'dns2': attributes.get('IPv4.1.DNS2', 'Unknown'),
                'hostname': attributes.get('HostName', 'Unknown'),
                'domain_name': attributes.get('DomainName', 'Unknown')
            }
            
            return dns_settings
        except Exception as e:
            logger.error("Failed to get DNS settings", idrac_ip=self.idrac_ip, error=str(e))
            return None


def get_idrac_info(idrac_ip, username, password, verify_ssl=False):
    """
    Main function to get all iDRAC information
    Returns a dict with all collected information
    
    Args:
        idrac_ip: The IP address of the iDRAC interface
        username: The username to authenticate with
        password: The password to authenticate with
        verify_ssl: Whether to verify SSL certificates (default: False)
    """
    logger.info("Collecting iDRAC information", idrac_ip=idrac_ip)
    
    try:
        api = IdracRedfishAPI(idrac_ip, username, password, verify_ssl)
        
        # Collect all information
        system_attrs = api.get_system_attributes()
        uptime = api.get_idrac_uptime()
        network_devices = api.get_network_devices()
        ntp_settings = api.get_ntp_settings()
        dns_settings = api.get_dns_settings()
        
        # Combine into a single dict
        idrac_info = {
            'system_attributes': system_attrs,
            'uptime': uptime,
            'network_devices': network_devices,
            'ntp_settings': ntp_settings,
            'dns_settings': dns_settings
        }
        
        logger.info("Successfully collected iDRAC information", idrac_ip=idrac_ip)
        return idrac_info
        
    except Exception as e:
        logger.error("Failed to collect iDRAC information", idrac_ip=idrac_ip, error=str(e))
        return None


# Example usage if run directly
if __name__ == "__main__":
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True)
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    
    parser = argparse.ArgumentParser(description='Dell iDRAC Utility')
    parser.add_argument('idrac_ip', help='iDRAC IP address')
    parser.add_argument('username', help='iDRAC username')
    parser.add_argument('password', help='iDRAC password')
    parser.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificates')
    
    if len(sys.argv) < 4:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    
    info = get_idrac_info(args.idrac_ip, args.username, args.password, args.verify_ssl)
    if info:
        print(json.dumps(info, indent=2))
