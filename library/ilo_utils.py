#!/usr/bin/env python3
"""
Garden-Tiller HPE iLO Utilities
Provides functions for interacting with HPE iLO using proliantutils
Uses Structlog for logging and PyBreaker for resilience
"""

import os
import sys
import json
import time
import functools
import pybreaker
import structlog
import argparse
from datetime import datetime
import urllib3

# Optional imports - HPE dependencies
try:
    from proliantutils import ilo
    from proliantutils.ilo import ribcl
    from proliantutils.exception import IloError, IloConnectionError
    from proliantutils.redfish import redfish
    PROLIANTUTILS_AVAILABLE = True
except ImportError:
    PROLIANTUTILS_AVAILABLE = False

# Suppress insecure HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize logger
logger = structlog.get_logger("ilo-utils")

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

class IloProUtils:
    """Class for interacting with HPE iLO using proliantutils"""
    
    def __init__(self, ilo_ip, ilo_username, ilo_password, use_redfish=True, verify_ssl=False):
        """Initialize the IloProUtils with iLO credentials"""
        if not PROLIANTUTILS_AVAILABLE:
            raise ImportError("proliantutils package is not installed")
            
        self.ilo_ip = ilo_ip
        self.ilo_username = ilo_username
        self.ilo_password = ilo_password
        self.use_redfish = use_redfish
        self.verify_ssl = verify_ssl
        
        # Initialize iLO client based on preference (Redfish or RIBCL)
        if use_redfish:
            logger.info("Initializing iLO with Redfish API", 
                       ilo_ip=ilo_ip, 
                       verify_ssl=verify_ssl)
            try:
                # Try with correct parameter name (may vary based on proliantutils version)
                self.client = redfish.RedfishOperations(
                    ilo_ip, ilo_username, ilo_password, 
                    verify=verify_ssl  # Standard parameter name for SSL verification
                )
            except TypeError:
                try:
                    # Alternate parameter name seen in some versions
                    self.client = redfish.RedfishOperations(
                        ilo_ip, ilo_username, ilo_password, 
                        verify_cert=verify_ssl  # Alternative parameter name
                    )
                except TypeError:
                    # Fallback to no SSL verification parameter
                    logger.warning("Falling back to default SSL verification - certificate validation may occur", ilo_ip=ilo_ip)
                    self.client = redfish.RedfishOperations(
                        ilo_ip, ilo_username, ilo_password
                    )
        else:
            logger.info("Initializing iLO with RIBCL", ilo_ip=ilo_ip)
            self.client = ribcl.RIBCLOperations(
                ilo_ip, ilo_username, ilo_password
            )

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_product_name(self):
        """Get the product name of the server"""
        logger.info("Getting product name", ilo_ip=self.ilo_ip)
        try:
            product_name = self.client.get_product_name()
            logger.info("Retrieved product name", 
                        ilo_ip=self.ilo_ip, 
                        product_name=product_name)
            return product_name
        except Exception as e:
            logger.error("Failed to get product name", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_host_power_status(self):
        """Get the current power status of the server"""
        logger.info("Getting power status", ilo_ip=self.ilo_ip)
        try:
            power_status = self.client.get_host_power_status()
            logger.info("Retrieved power status", 
                        ilo_ip=self.ilo_ip, 
                        power_status=power_status)
            return power_status
        except Exception as e:
            logger.error("Failed to get power status", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_server_health(self):
        """Get server health status"""
        logger.info("Getting server health", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                # Redfish method
                health_status = self.client.get_current_bios_settings().get(
                    'ServerHealth', 'Unknown')
            else:
                # RIBCL fallback
                health_status = 'Unknown' 
                # RIBCL doesn't have a direct method; this is handled in get_all_details
            
            logger.info("Retrieved server health", 
                        ilo_ip=self.ilo_ip, 
                        health_status=health_status)
            return health_status
        except Exception as e:
            logger.error("Failed to get server health", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            return "Unknown"

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_firmware_version(self):
        """Get the iLO firmware version"""
        logger.info("Getting firmware version", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                fw_version = self.client.get_fw_version()
            else:
                # RIBCL method - use get_product_name as fallback
                fw_version = "Unknown (RIBCL mode)"
                try:
                    # Try to get information that might contain firmware info
                    fw_version = self.client.get_product_name() + " (RIBCL mode)"
                except Exception:
                    pass
                    
            logger.info("Retrieved firmware version", 
                        ilo_ip=self.ilo_ip, 
                        firmware_version=fw_version)
            return fw_version
        except Exception as e:
            logger.error("Failed to get firmware version", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_one_time_boot(self):
        """Get the one time boot setting"""
        logger.info("Getting one-time boot setting", ilo_ip=self.ilo_ip)
        try:
            one_time_boot = self.client.get_one_time_boot()
            logger.info("Retrieved one-time boot setting", 
                        ilo_ip=self.ilo_ip, 
                        one_time_boot=one_time_boot)
            return one_time_boot
        except Exception as e:
            logger.error("Failed to get one-time boot setting", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_persistent_boot_device(self):
        """Get the persistent boot device setting"""
        logger.info("Getting persistent boot device", ilo_ip=self.ilo_ip)
        try:
            persistent_boot = self.client.get_persistent_boot_device()
            logger.info("Retrieved persistent boot device", 
                        ilo_ip=self.ilo_ip, 
                        persistent_boot=persistent_boot)
            return persistent_boot
        except Exception as e:
            logger.error("Failed to get persistent boot device", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_network_adapters(self):
        """Get information about network adapters"""
        logger.info("Getting network adapters", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                # Redfish method
                adapters = self.client.get_nic_inventory()
            else:
                # RIBCL doesn't have a direct method for detailed NIC info
                adapters = []
                
            logger.info("Retrieved network adapters", 
                        ilo_ip=self.ilo_ip, 
                        adapter_count=len(adapters))
            return adapters
        except Exception as e:
            logger.error("Failed to get network adapters", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            return []

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_host_uuid(self):
        """Get the host system UUID"""
        logger.info("Getting host UUID", ilo_ip=self.ilo_ip)
        try:
            host_uuid = self.client.get_host_uuid()
            logger.info("Retrieved host UUID", 
                        ilo_ip=self.ilo_ip, 
                        uuid=host_uuid)
            return host_uuid
        except Exception as e:
            logger.error("Failed to get host UUID", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_host_health_status(self):
        """Get the health status of the host"""
        logger.info("Getting host health status", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                # Using Redfish
                health_data = {}
                # System health
                health_data['system_health'] = self.get_server_health()
                
                # Storage health (if available)
                try:
                    storage_data = self.client.get_storage_details()
                    health_data['storage'] = storage_data
                except Exception:
                    health_data['storage'] = "Not available"
                
                # Memory health
                try:
                    memory_data = self.client.get_memory_details()
                    health_data['memory'] = memory_data
                except Exception:
                    health_data['memory'] = "Not available"
                    
                # Processor health
                try:
                    processor_data = self.client.get_processor_details()
                    health_data['processor'] = processor_data
                except Exception:
                    health_data['processor'] = "Not available"
                    
                logger.info("Retrieved host health details", 
                            ilo_ip=self.ilo_ip)
                return health_data
            else:
                # RIBCL has limited health status info
                return {"system_health": "Not available via RIBCL"}
        except Exception as e:
            logger.error("Failed to get host health status", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_all_details(self):
        """Get comprehensive server details"""
        logger.info("Getting all server details", ilo_ip=self.ilo_ip)
        try:
            all_details = {}
            
            # Try to get product name
            try:
                all_details["product_name"] = self.get_product_name()
            except Exception as e:
                logger.error("Failed to get product name in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["product_name"] = "Unknown"
            
            # Try to get power status
            try:
                all_details["power_status"] = self.get_host_power_status()
            except Exception as e:
                logger.error("Failed to get power status in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["power_status"] = "Unknown"
            
            # Try to get firmware version
            try:
                all_details["firmware_version"] = self.get_firmware_version()
            except Exception as e:
                logger.error("Failed to get firmware version in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["firmware_version"] = "Unknown"
            
            # Try to get host UUID
            try:
                all_details["host_uuid"] = self.get_host_uuid()
            except Exception as e:
                logger.error("Failed to get host UUID in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["host_uuid"] = "Unknown"
            
            # Try to get boot settings
            try:
                all_details["boot_settings"] = {
                    "one_time_boot": self.get_one_time_boot(),
                    "persistent_boot": self.get_persistent_boot_device()
                }
            except Exception as e:
                logger.error("Failed to get boot settings in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["boot_settings"] = {
                    "one_time_boot": "Unknown",
                    "persistent_boot": "Unknown"
                }
            
            # Try to get health status
            try:
                all_details["health_status"] = self.get_host_health_status()
            except Exception as e:
                logger.error("Failed to get health status in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["health_status"] = {"system_health": "Unknown"}
            
            # Try to get network adapters
            try:
                all_details["network_adapters"] = self.get_network_adapters()
            except Exception as e:
                logger.error("Failed to get network adapters in get_all_details", 
                             ilo_ip=self.ilo_ip, 
                             error=str(e))
                all_details["network_adapters"] = []
            
            logger.info("Successfully retrieved all server details", 
                        ilo_ip=self.ilo_ip)
            return all_details
        except Exception as e:
            logger.error("Failed to get all server details", 
                         ilo_ip=self.ilo_ip, 
                         error=str(e))
            return {"error": str(e)}


def get_ilo_info(ilo_ip, username, password, use_redfish=True, verify_ssl=False):
    """
    Main function to get all iLO information
    Returns a dict with all collected information
    
    Args:
        ilo_ip: The IP address of the iLO interface
        username: The username to authenticate with
        password: The password to authenticate with
        use_redfish: Whether to use the Redfish API (True) or RIBCL (False)
        verify_ssl: Whether to verify SSL certificates (default: False)
    """
    logger.info("Collecting iLO information", ilo_ip=ilo_ip)
    
    try:
        # Check if proliantutils is available
        if not PROLIANTUTILS_AVAILABLE:
            logger.error("proliantutils package is not installed")
            return {"error": "proliantutils package is not installed"}
            
        ilo_client = IloProUtils(ilo_ip, username, password, use_redfish, verify_ssl)
        server_details = ilo_client.get_all_details()
        
        logger.info("Successfully collected iLO information", ilo_ip=ilo_ip)
        return server_details
        
    except Exception as e:
        logger.error("Failed to collect iLO information", 
                     ilo_ip=ilo_ip, 
                     error=str(e))
        return {"error": str(e)}


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
    
    parser = argparse.ArgumentParser(description='HPE iLO Utility')
    parser.add_argument('ilo_ip', help='iLO IP address')
    parser.add_argument('username', help='iLO username')
    parser.add_argument('password', help='iLO password')
    parser.add_argument('--redfish', action='store_true', default=True, help='Use Redfish API (default)')
    parser.add_argument('--ribcl', action='store_true', help='Use RIBCL instead of Redfish')
    parser.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificates')
    
    if len(sys.argv) < 4:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    
    # Set defaults based on arguments
    use_redfish = not args.ribcl  # Use Redfish by default unless RIBCL flag is specified
    
    info = get_ilo_info(args.ilo_ip, args.username, args.password, use_redfish, args.verify_ssl)
    if info:
        print(json.dumps(info, indent=2))
