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
import requests
import base64
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
        """Get comprehensive server details with robust error handling"""
        logger.info("Getting all server details", ilo_ip=self.ilo_ip)
        
        all_details = {
            "collection_status": "in_progress",
            "errors_encountered": [],
            "partial_data": False
        }
        
        # Try to get product name
        try:
            all_details["product_name"] = self.get_product_name()
            logger.debug("Successfully retrieved product name", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Failed to get product name", ilo_ip=self.ilo_ip, error=str(e))
            all_details["product_name"] = "Unknown"
            all_details["errors_encountered"].append(f"product_name: {str(e)}")
            all_details["partial_data"] = True
        
        # Try to get power status - Direct Redfish HTTP as primary method
        try:
            logger.info("Attempting power status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
            all_details["power_status"] = self.get_power_status_via_redfish_http()
            logger.debug("Successfully retrieved power status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Direct Redfish HTTP power status failed, trying proliantutils fallback", 
                          ilo_ip=self.ilo_ip, error=str(e))
            try:
                all_details["power_status"] = self.get_host_power_status()
                logger.debug("Successfully retrieved power status via proliantutils fallback", ilo_ip=self.ilo_ip)
            except Exception as e2:
                logger.warning("Failed to get power status", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["power_status"] = "Unknown"
                all_details["errors_encountered"].append(f"power_status: Direct Redfish HTTP failed ({str(e)}), proliantutils failed ({str(e2)})")
                all_details["partial_data"] = True
        
        # Try to get firmware version - Direct Redfish HTTP as primary method
        try:
            logger.info("Attempting firmware version via direct Redfish HTTP", ilo_ip=self.ilo_ip)
            all_details["firmware_version"] = self.get_firmware_version_via_redfish_http()
            logger.debug("Successfully retrieved firmware version via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Direct Redfish HTTP firmware version failed, trying proliantutils fallback", 
                          ilo_ip=self.ilo_ip, error=str(e))
            try:
                all_details["firmware_version"] = self.get_firmware_version()
                logger.debug("Successfully retrieved firmware version via proliantutils fallback", ilo_ip=self.ilo_ip)
            except Exception as e2:
                logger.warning("Failed to get firmware version", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["firmware_version"] = "Unknown"
                all_details["errors_encountered"].append(f"firmware_version: Direct Redfish HTTP failed ({str(e)}), proliantutils failed ({str(e2)})")
                all_details["partial_data"] = True
        
        # Try to get host UUID
        try:
            all_details["host_uuid"] = self.get_host_uuid()
            logger.debug("Successfully retrieved host UUID", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Failed to get host UUID", ilo_ip=self.ilo_ip, error=str(e))
            all_details["host_uuid"] = "Unknown"
            all_details["errors_encountered"].append(f"host_uuid: {str(e)}")
            all_details["partial_data"] = True
        
        # Try to get boot settings - Direct Redfish HTTP as primary method
        try:
            logger.info("Attempting boot settings via direct Redfish HTTP", ilo_ip=self.ilo_ip)
            boot_settings_direct = self.get_boot_settings_via_redfish_http()
            all_details["boot_settings"] = boot_settings_direct
            logger.debug("Successfully retrieved boot settings via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Direct Redfish HTTP boot settings failed, trying proliantutils fallback", 
                          ilo_ip=self.ilo_ip, error=str(e))
            try:
                one_time_boot = self.get_one_time_boot()
                persistent_boot = self.get_persistent_boot_device()
                all_details["boot_settings"] = {
                    "one_time_boot": one_time_boot,
                    "persistent_boot": persistent_boot
                }
                logger.debug("Successfully retrieved boot settings via proliantutils fallback", ilo_ip=self.ilo_ip)
            except Exception as e2:
                logger.warning("Failed to get boot settings", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["boot_settings"] = {
                    "one_time_boot": "Unknown",
                    "persistent_boot": "Unknown"
                }
                all_details["errors_encountered"].append(f"boot_settings: Direct Redfish HTTP failed ({str(e)}), proliantutils failed ({str(e2)})")
                all_details["partial_data"] = True
        
        # Try to get health status - Direct Redfish HTTP as primary method  
        try:
            logger.info("Attempting health status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
            health_status_direct = self.get_health_status_via_redfish_http()
            all_details["health_status"] = {"system_health": health_status_direct}
            logger.debug("Successfully retrieved health status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Direct Redfish HTTP health status failed, trying proliantutils fallback", 
                          ilo_ip=self.ilo_ip, error=str(e))
            try:
                all_details["health_status"] = self.get_host_health_status()
                logger.debug("Successfully retrieved health status via proliantutils fallback", ilo_ip=self.ilo_ip)
            except Exception as e2:
                logger.warning("Failed to get health status", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["health_status"] = {"system_health": "Unknown"}
                all_details["errors_encountered"].append(f"health_status: Direct Redfish HTTP failed ({str(e)}), proliantutils failed ({str(e2)})")
                all_details["partial_data"] = True
        
        # Try to get network adapters with enhanced details
        try:
            adapters = self.get_network_adapter_details()
            all_details["network_adapters"] = adapters
            all_details["network_adapter_count"] = len(adapters) if adapters else 0
            logger.debug("Successfully retrieved enhanced network adapters", 
                        ilo_ip=self.ilo_ip, 
                        adapter_count=all_details["network_adapter_count"])
        except Exception as e:
            logger.warning("Failed to get enhanced network adapters, trying basic method", 
                          ilo_ip=self.ilo_ip, error=str(e))
            try:
                # Fallback to basic network adapter method
                adapters = self.get_network_adapters()
                all_details["network_adapters"] = adapters
                all_details["network_adapter_count"] = len(adapters) if adapters else 0
            except Exception as e2:
                logger.warning("Failed to get network adapters", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["network_adapters"] = []
                all_details["network_adapter_count"] = 0
                all_details["errors_encountered"].append(f"network_adapters: {str(e2)}")
                all_details["partial_data"] = True

        # Try to get comprehensive hardware inventory via BMC APIs with enhanced details
        try:
            hardware_inventory = self.get_comprehensive_hardware_inventory_enhanced()
            all_details["hardware_inventory"] = hardware_inventory
            
            # Extract key information for compatibility with existing report templates
            if "server_info" in hardware_inventory and not isinstance(hardware_inventory["server_info"], dict) or "error" not in hardware_inventory.get("server_info", {}):
                all_details["server_info"] = hardware_inventory["server_info"]
                # Update collection metadata with server details
                if "collection_metadata" not in all_details:
                    all_details["collection_metadata"] = {}
                all_details["collection_metadata"].update(hardware_inventory["server_info"])
            
            logger.debug("Successfully retrieved comprehensive hardware inventory", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Failed to get comprehensive hardware inventory, using fallback methods", ilo_ip=self.ilo_ip, error=str(e))
            all_details["hardware_inventory"] = {"error": str(e)}
            all_details["errors_encountered"].append(f"hardware_inventory: {str(e)}")
            all_details["partial_data"] = True
            
            # Fallback to basic system details method
            try:
                system_details = self.get_system_details()
                all_details["system_hardware"] = system_details
                logger.debug("Successfully retrieved basic system hardware details", ilo_ip=self.ilo_ip)
            except Exception as e2:
                logger.warning("Failed to get basic system hardware details", ilo_ip=self.ilo_ip, error=str(e2))
                all_details["system_hardware"] = {"error": str(e2)}
                all_details["errors_encountered"].append(f"system_hardware: {str(e2)}")
                all_details["partial_data"] = True

            # Fallback to basic server info method
            try:
                server_info = self.get_server_serial_model()
                all_details["server_info"] = server_info
                # Update collection metadata with server details
                if "collection_metadata" not in all_details:
                    all_details["collection_metadata"] = {}
                all_details["collection_metadata"].update(server_info)
                logger.debug("Successfully retrieved basic server information", ilo_ip=self.ilo_ip)
            except Exception as e3:
                logger.warning("Failed to get basic server information", ilo_ip=self.ilo_ip, error=str(e3))
                all_details["server_info"] = {"error": str(e3)}
                all_details["errors_encountered"].append(f"server_info: {str(e3)}")
                all_details["partial_data"] = True
        
        # Update collection status
        if all_details["errors_encountered"]:
            all_details["collection_status"] = "partial_success" if not all_details["partial_data"] else "errors_occurred"
        else:
            all_details["collection_status"] = "complete_success"
        
        logger.info("Completed server details collection", 
                    ilo_ip=self.ilo_ip, 
                    status=all_details["collection_status"],
                    errors_count=len(all_details["errors_encountered"]))
        return all_details

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_system_details(self):
        """Get comprehensive system hardware details"""
        logger.info("Getting system hardware details", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                # Use Redfish to get system details
                system_details = {}
                
                # Get BIOS information
                try:
                    bios_data = self.client.get_current_bios_settings()
                    system_details['bios'] = bios_data
                except Exception as e:
                    logger.warning("Failed to get BIOS details", ilo_ip=self.ilo_ip, error=str(e))
                    system_details['bios'] = "Not available"
                
                # Get processor information
                try:
                    processor_data = self.client.get_processor_details()
                    system_details['processors'] = processor_data
                except Exception as e:
                    logger.warning("Failed to get processor details", ilo_ip=self.ilo_ip, error=str(e))
                    system_details['processors'] = "Not available"
                
                # Get memory information
                try:
                    memory_data = self.client.get_memory_details()
                    system_details['memory'] = memory_data
                except Exception as e:
                    logger.warning("Failed to get memory details", ilo_ip=self.ilo_ip, error=str(e))
                    system_details['memory'] = "Not available"
                
                # Get storage information
                try:
                    storage_data = self.client.get_storage_details()
                    system_details['storage'] = storage_data
                except Exception as e:
                    logger.warning("Failed to get storage details", ilo_ip=self.ilo_ip, error=str(e))
                    system_details['storage'] = "Not available"
                
                logger.info("Retrieved system hardware details", ilo_ip=self.ilo_ip)
                return system_details
            else:
                logger.warning("System details not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "System details require Redfish API"}
                
        except Exception as e:
            logger.error("Failed to get system hardware details", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_network_adapter_details(self):
        """Get detailed network adapter information with enhanced Redfish HTTP support
        
        Uses direct Redfish HTTP requests as the primary method for maximum compatibility
        and reliability, with proliantutils and XML as fallback methods.
        """
        logger.info("Getting detailed network adapter information", ilo_ip=self.ilo_ip)
        
        # Primary method: Direct Redfish HTTP requests
        try:
            logger.info("Attempting direct Redfish HTTP method for network adapters", ilo_ip=self.ilo_ip)
            redfish_result = self.get_network_adapters_via_redfish_http()
            
            if redfish_result and (redfish_result.get('adapters') or redfish_result.get('host_mac_addresses')):
                # Convert the direct Redfish result to the expected format
                enhanced_adapters = []
                host_mac_addresses = redfish_result.get('host_mac_addresses', [])
                
                # Process detailed adapter information if available
                detailed_adapters = redfish_result.get('adapters', [])
                
                if detailed_adapters:
                    # We have detailed adapter info - merge with MAC addresses from HostCorrelation
                    for i, adapter in enumerate(detailed_adapters):
                        # Get MAC address from HostCorrelation if available and adapter MAC is unknown
                        mac_from_host_correlation = host_mac_addresses[i] if i < len(host_mac_addresses) else 'Unknown'
                        adapter_mac = adapter.get('mac_address', 'Unknown')
                        permanent_mac = adapter.get('permanent_mac_address', 'Unknown')
                        
                        # Use HostCorrelation MAC if adapter MAC is unknown or null
                        if adapter_mac in ['Unknown', None, ''] and mac_from_host_correlation != 'Unknown':
                            adapter_mac = mac_from_host_correlation
                        if permanent_mac in ['Unknown', None, ''] and mac_from_host_correlation != 'Unknown':
                            permanent_mac = mac_from_host_correlation
                        
                        enhanced_adapter = {
                            'name': adapter.get('name', f'Network Adapter {i+1}'),
                            'mac_address': adapter_mac,
                            'permanent_mac_address': permanent_mac,
                            'speed': adapter.get('speed_mbps', 'Unknown'),
                            'status': adapter.get('status', 'Unknown'),
                            'link_status': adapter.get('link_status', 'Unknown'),
                            'full_duplex': adapter.get('full_duplex', 'Unknown'),
                            'mtu_size': adapter.get('mtu_size', 'Unknown'),
                            'auto_neg': adapter.get('auto_neg', 'Unknown'),
                            'collection_method': 'direct_redfish_http_merged'
                        }
                        enhanced_adapters.append(enhanced_adapter)
                    
                    # If we have more MAC addresses than detailed adapters, add the extras
                    if len(host_mac_addresses) > len(detailed_adapters):
                        for i in range(len(detailed_adapters), len(host_mac_addresses)):
                            mac = host_mac_addresses[i]
                            enhanced_adapter = {
                                'name': f'Network Adapter {i+1}',
                                'mac_address': mac,
                                'permanent_mac_address': mac,
                                'speed': 'Unknown',
                                'status': 'Unknown',
                                'link_status': 'Unknown',
                                'collection_method': 'direct_redfish_http_host_correlation'
                            }
                            enhanced_adapters.append(enhanced_adapter)
                
                else:
                    # No detailed adapters, but we have MAC addresses from HostCorrelation
                    for i, mac in enumerate(host_mac_addresses):
                        enhanced_adapter = {
                            'name': f'Network Adapter {i+1}',
                            'mac_address': mac,
                            'permanent_mac_address': mac,
                            'speed': 'Unknown',
                            'status': 'Unknown',
                            'link_status': 'Unknown',
                            'collection_method': 'direct_redfish_http_host_correlation'
                        }
                        enhanced_adapters.append(enhanced_adapter)
                
                logger.info("Successfully retrieved network adapters via direct Redfish HTTP", 
                           ilo_ip=self.ilo_ip, 
                           adapter_count=len(enhanced_adapters),
                           mac_count=len(redfish_result.get('host_mac_addresses', [])))
                return enhanced_adapters
            else:
                logger.warning("Direct Redfish HTTP method returned no useful data", ilo_ip=self.ilo_ip)
                
        except Exception as e:
            logger.warning("Direct Redfish HTTP method failed, trying proliantutils fallback", 
                          ilo_ip=self.ilo_ip, error=str(e))
        
        # Fallback method: proliantutils (original method)
        try:
            if self.use_redfish:
                # Check if this method exists on the client (iLO4 compatibility issue)
                if hasattr(self.client, 'get_nic_inventory'):
                    logger.info("Trying proliantutils get_nic_inventory method", ilo_ip=self.ilo_ip)
                    # Get NIC inventory with more details
                    adapters = self.client.get_nic_inventory()
                    
                    # Enhanced adapter information
                    enhanced_adapters = []
                    for adapter in adapters:
                        if isinstance(adapter, dict):
                            enhanced_adapter = {
                                'name': adapter.get('Name', 'Unknown'),
                                'mac_address': adapter.get('MACAddress', 'Unknown'),
                                'speed': adapter.get('SpeedMbps', 'Unknown'),
                                'status': adapter.get('Status', {}).get('Health', 'Unknown'),
                                'manufacturer': adapter.get('Manufacturer', 'Unknown'),
                                'model': adapter.get('Model', 'Unknown'),
                                'firmware_version': adapter.get('FirmwareVersion', 'Unknown'),
                                'link_status': adapter.get('LinkStatus', 'Unknown'),
                                'collection_method': 'proliantutils_redfish'
                            }
                            enhanced_adapters.append(enhanced_adapter)
                    
                    logger.info("Retrieved detailed network adapter information via proliantutils Redfish", 
                               ilo_ip=self.ilo_ip, 
                               adapter_count=len(enhanced_adapters))
                    return enhanced_adapters
                else:
                    logger.warning("get_nic_inventory method not available on this iLO version, falling back to XML", 
                                  ilo_ip=self.ilo_ip)
                    # Fallback to XML endpoint for network adapters
                    xml_data = self.get_xml_endpoint_data()
                    if xml_data.get("status") == "success":
                        parsed_data = self.parse_xml_hardware_data(xml_data["xml_data"])
                        if parsed_data and "network_adapters" in parsed_data:
                            adapters = parsed_data["network_adapters"].get("adapters", [])
                            # Add collection method to each adapter
                            for adapter in adapters:
                                adapter['collection_method'] = 'xml_endpoint'
                            return adapters
                    return []
            else:
                # RIBCL fallback - try XML endpoint if available
                logger.info("RIBCL mode - attempting XML endpoint for network adapter details", ilo_ip=self.ilo_ip)
                xml_data = self.get_xml_endpoint_data()
                if xml_data.get("status") == "success":
                    parsed_data = self.parse_xml_hardware_data(xml_data["xml_data"])
                    if parsed_data and "network_adapters" in parsed_data:
                        adapters = parsed_data["network_adapters"].get("adapters", [])
                        # Add collection method to each adapter
                        for adapter in adapters:
                            adapter['collection_method'] = 'ribcl_xml'
                        return adapters
                return []
                
        except Exception as e:
            logger.error("Failed to get detailed network adapter information via proliantutils", 
                        ilo_ip=self.ilo_ip, error=str(e))
            # Try XML endpoint as final fallback
            try:
                logger.info("Attempting XML endpoint fallback for network adapters", ilo_ip=self.ilo_ip)
                xml_data = self.get_xml_endpoint_data()
                if xml_data.get("status") == "success":
                    parsed_data = self.parse_xml_hardware_data(xml_data["xml_data"])
                    if parsed_data and "network_adapters" in parsed_data:
                        adapters = parsed_data["network_adapters"].get("adapters", [])
                        # Add collection method to each adapter
                        for adapter in adapters:
                            adapter['collection_method'] = 'xml_fallback'
                        return adapters
            except Exception as xml_e:
                logger.warning("XML endpoint fallback also failed", ilo_ip=self.ilo_ip, error=str(xml_e))
            return []

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_server_serial_model(self):
        """Get server serial number and model information"""
        logger.info("Getting server serial and model information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                # Get system information
                system_info = {}
                
                try:
                    # Try to get system details
                    system_data = self.client.get_system_info()
                    system_info.update(system_data)
                except Exception:
                    # Fallback methods
                    pass
                
                # Extract key information
                server_info = {
                    'manufacturer': system_info.get('Manufacturer', 'Unknown'),
                    'model': system_info.get('Model', 'Unknown'),
                    'serial_number': system_info.get('SerialNumber', 'Unknown'),
                    'part_number': system_info.get('PartNumber', 'Unknown'),
                    'asset_tag': system_info.get('AssetTag', 'Unknown'),
                    'sku': system_info.get('SKU', 'Unknown')
                }
                
                logger.info("Retrieved server serial and model information", ilo_ip=self.ilo_ip)
                return server_info
            else:
                logger.warning("Server details not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Server details require Redfish API"}
                
        except Exception as e:
            logger.error("Failed to get server serial and model information", 
                        ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_bios_information(self):
        """Get comprehensive BIOS information with iLO4 compatibility"""
        logger.info("Getting BIOS information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                bios_info = {}
                
                # Check for iLO4 compatibility issues
                try:
                    # Get BIOS settings with compatibility check
                    if hasattr(self.client, 'get_current_bios_settings'):
                        bios_settings = self.client.get_current_bios_settings()
                        if bios_settings and not isinstance(bios_settings, str):
                            bios_info['settings'] = bios_settings
                        else:
                            logger.warning("BIOS settings returned empty or invalid data", ilo_ip=self.ilo_ip)
                            bios_info['settings'] = {}
                    else:
                        logger.warning("get_current_bios_settings method not available", ilo_ip=self.ilo_ip)
                        bios_info['settings'] = {}
                except Exception as e:
                    logger.warning("Failed to get BIOS settings", ilo_ip=self.ilo_ip, error=str(e))
                    bios_info['settings'] = {}
                
                try:
                    # Get system ROM information if available
                    if hasattr(self.client, 'get_system_rom_info'):
                        rom_info = self.client.get_system_rom_info()
                        bios_info['rom_info'] = rom_info if rom_info else {}
                    else:
                        bios_info['rom_info'] = {}
                except Exception as e:
                    logger.debug("System ROM info not available", ilo_ip=self.ilo_ip, error=str(e))
                    bios_info['rom_info'] = {}
                
                # If BMC API fails, try to get basic BIOS info from XML endpoint
                if not bios_info.get('settings') and not bios_info.get('rom_info'):
                    logger.info("BMC API BIOS info insufficient, attempting XML fallback", ilo_ip=self.ilo_ip)
                    try:
                        xml_data = self.get_xml_endpoint_data()
                        if xml_data.get("status") == "success":
                            parsed_data = self.parse_xml_hardware_data(xml_data["xml_data"])
                            if parsed_data and "ilo_info" in parsed_data:
                                ilo_info = parsed_data["ilo_info"]
                                bios_info['ilo_firmware'] = ilo_info.get('firmware_version', 'Unknown')
                                bios_info['ilo_product'] = ilo_info.get('product_name', 'Unknown')
                                bios_info['xml_source'] = True
                    except Exception as xml_e:
                        logger.warning("XML fallback for BIOS info also failed", ilo_ip=self.ilo_ip, error=str(xml_e))
                
                # Extract key BIOS information
                bios_summary = {
                    'version': bios_info.get('rom_info', {}).get('version', 
                              bios_info.get('ilo_firmware', 'Unknown (XML source)') if bios_info.get('xml_source') else 'Unknown'),
                    'date': bios_info.get('rom_info', {}).get('date', 'Unknown'),
                    'family': bios_info.get('rom_info', {}).get('family', 'Unknown'),
                    'boot_mode': bios_info.get('settings', {}).get('BootMode', 'Unknown'),
                    'secure_boot': bios_info.get('settings', {}).get('SecureBootStatus', 'Unknown'),
                    'settings_count': len(bios_info.get('settings', {})),
                    'ilo_firmware': bios_info.get('ilo_firmware', 'Unknown'),
                    'ilo_product': bios_info.get('ilo_product', 'Unknown'),
                    'raw_data': bios_info
                }
                
                logger.info("Retrieved BIOS information", ilo_ip=self.ilo_ip)
                return bios_summary
            else:
                # RIBCL mode - try XML endpoint for iLO info
                logger.info("RIBCL mode - attempting XML endpoint for iLO information", ilo_ip=self.ilo_ip)
                try:
                    xml_data = self.get_xml_endpoint_data()
                    if xml_data.get("status") == "success":
                        parsed_data = self.parse_xml_hardware_data(xml_data["xml_data"])
                        if parsed_data and "ilo_info" in parsed_data:
                            ilo_info = parsed_data["ilo_info"]
                            return {
                                'version': 'Unknown (RIBCL mode)',
                                'ilo_firmware': ilo_info.get('firmware_version', 'Unknown'),
                                'ilo_product': ilo_info.get('product_name', 'Unknown'),
                                'source': 'XML endpoint',
                                'raw_data': ilo_info
                            }
                except Exception as xml_e:
                    logger.warning("XML endpoint not available in RIBCL mode", ilo_ip=self.ilo_ip, error=str(xml_e))
                
                return {"error": "BIOS information requires Redfish API or XML endpoint"}
        except Exception as e:
            logger.error("Failed to get BIOS information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_processor_information(self):
        """Get comprehensive processor information"""
        logger.info("Getting processor information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                processors = []
                try:
                    # Get processor details - try different methods based on proliantutils version
                    if hasattr(self.client, 'get_processor_details'):
                        proc_data = self.client.get_processor_details()
                    elif hasattr(self.client, 'get_system_health'):
                        # Fallback: extract processor info from system health
                        health_data = self.client.get_system_health()
                        proc_data = health_data.get('processors', []) if isinstance(health_data, dict) else []
                    else:
                        proc_data = []
                    
                    # Process the data
                    if isinstance(proc_data, list):
                        for proc in proc_data:
                            if isinstance(proc, dict):
                                processor = {
                                    'name': proc.get('Name', 'Unknown'),
                                    'model': proc.get('Model', 'Unknown'),
                                    'manufacturer': proc.get('Manufacturer', 'Unknown'),
                                    'cores': proc.get('TotalCores', 'Unknown'),
                                    'threads': proc.get('TotalThreads', 'Unknown'),
                                    'speed_mhz': proc.get('MaxSpeedMHz', 'Unknown'),
                                    'socket': proc.get('Socket', 'Unknown'),
                                    'status': proc.get('Status', {}).get('Health', 'Unknown'),
                                    'architecture': proc.get('InstructionSet', 'Unknown')
                                }
                                processors.append(processor)
                    
                    logger.info("Retrieved processor information", 
                               ilo_ip=self.ilo_ip, 
                               processor_count=len(processors))
                    return {
                        'processors': processors,
                        'processor_count': len(processors),
                        'total_cores': sum(proc.get('cores', 0) for proc in processors if isinstance(proc.get('cores'), int)),
                        'total_threads': sum(proc.get('threads', 0) for proc in processors if isinstance(proc.get('threads'), int))
                    }
                except Exception as e:
                    logger.warning("Failed to get detailed processor info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "processors": []}
            else:
                logger.warning("Processor information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Processor information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get processor information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_memory_information(self):
        """Get comprehensive memory information"""
        logger.info("Getting memory information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                memory_modules = []
                try:
                    # Get memory details
                    if hasattr(self.client, 'get_memory_details'):
                        mem_data = self.client.get_memory_details()
                    elif hasattr(self.client, 'get_system_health'):
                        # Fallback: extract memory info from system health
                        health_data = self.client.get_system_health()
                        mem_data = health_data.get('memory', []) if isinstance(health_data, dict) else []
                    else:
                        mem_data = []
                    
                    total_memory_gb = 0
                    
                    # Process memory modules
                    if isinstance(mem_data, list):
                        for mem in mem_data:
                            if isinstance(mem, dict):
                                size_mb = mem.get('CapacityMB', 0)
                                size_gb = round(size_mb / 1024, 2) if size_mb else 0
                                total_memory_gb += size_gb
                                
                                memory_module = {
                                    'name': mem.get('Name', 'Unknown'),
                                    'size_mb': size_mb,
                                    'size_gb': size_gb,
                                    'speed_mhz': mem.get('OperatingSpeedMhz', 'Unknown'),
                                    'type': mem.get('MemoryDeviceType', 'Unknown'),
                                    'manufacturer': mem.get('Manufacturer', 'Unknown'),
                                    'part_number': mem.get('PartNumber', 'Unknown'),
                                    'location': mem.get('DeviceLocator', 'Unknown'),
                                    'status': mem.get('Status', {}).get('Health', 'Unknown')
                                }
                                memory_modules.append(memory_module)
                    
                    logger.info("Retrieved memory information", 
                               ilo_ip=self.ilo_ip, 
                               module_count=len(memory_modules),
                               total_memory_gb=total_memory_gb)
                    return {
                        'memory_modules': memory_modules,
                        'module_count': len(memory_modules),
                        'total_memory_gb': total_memory_gb,
                        'populated_slots': len([m for m in memory_modules if m.get('size_gb', 0) > 0])
                    }
                except Exception as e:
                    logger.warning("Failed to get detailed memory info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "memory_modules": []}
            else:
                logger.warning("Memory information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Memory information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get memory information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_storage_information(self):
        """Get comprehensive storage information"""
        logger.info("Getting storage information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                storage_devices = []
                try:
                    # Get storage details
                    if hasattr(self.client, 'get_storage_details'):
                        storage_data = self.client.get_storage_details()
                    elif hasattr(self.client, 'get_smart_storage_config'):
                        # Try Smart Storage configuration
                        storage_data = self.client.get_smart_storage_config()
                    else:
                        storage_data = []
                    
                    total_capacity_gb = 0
                    
                    # Process storage devices
                    if isinstance(storage_data, list):
                        for storage in storage_data:
                            if isinstance(storage, dict):
                                capacity_gb = storage.get('CapacityGB', 0)
                                total_capacity_gb += capacity_gb if capacity_gb else 0
                                
                                storage_device = {
                                    'name': storage.get('Name', 'Unknown'),
                                    'model': storage.get('Model', 'Unknown'),
                                    'manufacturer': storage.get('Manufacturer', 'Unknown'),
                                    'capacity_gb': capacity_gb,
                                    'interface_type': storage.get('InterfaceType', 'Unknown'),
                                    'media_type': storage.get('MediaType', 'Unknown'),
                                    'location': storage.get('Location', 'Unknown'),
                                    'serial_number': storage.get('SerialNumber', 'Unknown'),
                                    'status': storage.get('Status', {}).get('Health', 'Unknown'),
                                    'firmware_version': storage.get('FirmwareVersion', 'Unknown')
                                }
                                storage_devices.append(storage_device)
                    
                    logger.info("Retrieved storage information", 
                               ilo_ip=self.ilo_ip, 
                               device_count=len(storage_devices),
                               total_capacity_gb=total_capacity_gb)
                    return {
                        'storage_devices': storage_devices,
                        'device_count': len(storage_devices),
                        'total_capacity_gb': total_capacity_gb
                    }
                except Exception as e:
                    logger.warning("Failed to get detailed storage info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "storage_devices": []}
            else:
                logger.warning("Storage information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Storage information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get storage information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_power_thermal_information(self):
        """Get power and thermal information"""
        logger.info("Getting power and thermal information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                power_thermal = {}
                try:
                    # Get power information
                    if hasattr(self.client, 'get_power_reading'):
                        power_data = self.client.get_power_reading()
                        power_thermal['power'] = power_data
                    
                    # Get thermal information
                    if hasattr(self.client, 'get_thermal_config'):
                        thermal_data = self.client.get_thermal_config()
                        power_thermal['thermal'] = thermal_data
                    elif hasattr(self.client, 'get_system_health'):
                        # Try to get temperature from system health
                        health_data = self.client.get_system_health()
                        if isinstance(health_data, dict):
                            power_thermal['thermal'] = health_data.get('temperature', {})
                    
                    logger.info("Retrieved power and thermal information", ilo_ip=self.ilo_ip)
                    return power_thermal
                except Exception as e:
                    logger.warning("Failed to get power/thermal info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e)}
            else:
                logger.warning("Power/thermal information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Power/thermal information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get power and thermal information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_comprehensive_hardware_inventory(self):
        """Get complete hardware inventory using BMC APIs"""
        logger.info("Getting comprehensive hardware inventory", ilo_ip=self.ilo_ip)
        
        inventory = {
            "collection_method": "BMC_API",
            "collection_timestamp": datetime.now().isoformat(),
            "ilo_ip": self.ilo_ip,
            "api_type": "Redfish" if self.use_redfish else "RIBCL",
            "errors": []
        }
        
        # Get server basic information
        try:
            server_info = self.get_server_serial_model()
            inventory["server_info"] = server_info
        except Exception as e:
            inventory["errors"].append(f"server_info: {str(e)}")
            inventory["server_info"] = {"error": str(e)}
        
        # Get BIOS information
        try:
            bios_info = self.get_bios_information()
            inventory["bios"] = bios_info
        except Exception as e:
            inventory["errors"].append(f"bios: {str(e)}")
            inventory["bios"] = {"error": str(e)}
        
        # Get processor information
        try:
            processor_info = self.get_processor_information()
            inventory["processors"] = processor_info
        except Exception as e:
            inventory["errors"].append(f"processors: {str(e)}")
            inventory["processors"] = {"error": str(e)}
        
        # Get memory information
        try:
            memory_info = self.get_memory_information()
            inventory["memory"] = memory_info
        except Exception as e:
            inventory["errors"].append(f"memory: {str(e)}")
            inventory["memory"] = {"error": str(e)}
        
        # Get storage information
        try:
            storage_info = self.get_storage_information()
            inventory["storage"] = storage_info
        except Exception as e:
            inventory["errors"].append(f"storage: {str(e)}")
            inventory["storage"] = {"error": str(e)}
        
        # Get network adapter information
        try:
            network_info = self.get_network_adapter_details()
            inventory["network_adapters"] = {
                "adapters": network_info,
                "adapter_count": len(network_info) if network_info else 0
            }
        except Exception as e:
            inventory["errors"].append(f"network_adapters: {str(e)}")
            inventory["network_adapters"] = {"error": str(e), "adapters": []}
        
        # Get power and thermal information
        try:
            power_thermal_info = self.get_power_thermal_information()
            inventory["power_thermal"] = power_thermal_info
        except Exception as e:
            inventory["errors"].append(f"power_thermal: {str(e)}")
            inventory["power_thermal"] = {"error": str(e)}
        
        # Calculate collection success rate
        total_categories = 7  # server_info, bios, processors, memory, storage, network, power_thermal
        successful_categories = total_categories - len(inventory["errors"])
        inventory["collection_success_rate"] = f"{successful_categories}/{total_categories}"
        inventory["collection_status"] = "complete" if len(inventory["errors"]) == 0 else "partial"
        
        logger.info("Completed comprehensive hardware inventory", 
                   ilo_ip=self.ilo_ip,
                   success_rate=inventory["collection_success_rate"],
                   status=inventory["collection_status"])
        
        return inventory

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_smartarray_information(self):
        """Get comprehensive SmartArray controller and RAID configuration information"""
        logger.info("Getting SmartArray information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                smartarray_info = {
                    "controllers": [],
                    "logical_drives": [],
                    "physical_drives": []
                }
                
                try:
                    # Get Smart Storage configuration
                    if hasattr(self.client, 'get_smart_storage_config'):
                        storage_config = self.client.get_smart_storage_config()
                        if isinstance(storage_config, dict):
                            # Parse controllers
                            controllers = storage_config.get('Controllers', [])
                            for controller in controllers:
                                if isinstance(controller, dict):
                                    controller_info = {
                                        'name': controller.get('Name', 'Unknown'),
                                        'model': controller.get('Model', 'Unknown'),
                                        'firmware_version': controller.get('FirmwareVersion', 'Unknown'),
                                        'serial_number': controller.get('SerialNumber', 'Unknown'),
                                        'cache_size_mb': controller.get('CacheSizeInMB', 'Unknown'),
                                        'status': controller.get('Status', {}).get('Health', 'Unknown'),
                                        'location': controller.get('Location', 'Unknown'),
                                        'encryption_enabled': controller.get('EncryptionEnabled', False)
                                    }
                                    smartarray_info['controllers'].append(controller_info)
                                    
                                    # Parse logical drives for this controller
                                    logical_drives = controller.get('LogicalDrives', [])
                                    for logical_drive in logical_drives:
                                        if isinstance(logical_drive, dict):
                                            ld_info = {
                                                'controller': controller_info['name'],
                                                'name': logical_drive.get('Name', 'Unknown'),
                                                'raid_level': logical_drive.get('RAIDLevel', 'Unknown'),
                                                'capacity_gb': logical_drive.get('CapacityGB', 'Unknown'),
                                                'status': logical_drive.get('Status', {}).get('Health', 'Unknown'),
                                                'strip_size_kb': logical_drive.get('StripSizeKB', 'Unknown'),
                                                'accelerator': logical_drive.get('Accelerator', 'Unknown')
                                            }
                                            smartarray_info['logical_drives'].append(ld_info)
                                    
                                    # Parse physical drives for this controller
                                    physical_drives = controller.get('PhysicalDrives', [])
                                    for physical_drive in physical_drives:
                                        if isinstance(physical_drive, dict):
                                            pd_info = {
                                                'controller': controller_info['name'],
                                                'name': physical_drive.get('Name', 'Unknown'),
                                                'model': physical_drive.get('Model', 'Unknown'),
                                                'serial_number': physical_drive.get('SerialNumber', 'Unknown'),
                                                'capacity_gb': physical_drive.get('CapacityGB', 'Unknown'),
                                                'interface_type': physical_drive.get('InterfaceType', 'Unknown'),
                                                'media_type': physical_drive.get('MediaType', 'Unknown'),
                                                'location': physical_drive.get('Location', 'Unknown'),
                                                'status': physical_drive.get('Status', {}).get('Health', 'Unknown'),
                                                'firmware_version': physical_drive.get('FirmwareVersion', 'Unknown'),
                                                'temperature_celsius': physical_drive.get('TemperatureCelsius', 'Unknown')
                                            }
                                            smartarray_info['physical_drives'].append(pd_info)
                    
                    # Calculate summary statistics
                    smartarray_info['summary'] = {
                        'total_controllers': len(smartarray_info['controllers']),
                        'total_logical_drives': len(smartarray_info['logical_drives']),
                        'total_physical_drives': len(smartarray_info['physical_drives']),
                        'total_capacity_gb': sum(pd.get('capacity_gb', 0) for pd in smartarray_info['physical_drives'] if isinstance(pd.get('capacity_gb'), (int, float))),
                        'raid_levels': list(set(ld.get('raid_level') for ld in smartarray_info['logical_drives'] if ld.get('raid_level', 'Unknown') != 'Unknown'))
                    }
                    
                    logger.info("Retrieved SmartArray information", 
                               ilo_ip=self.ilo_ip,
                               controller_count=smartarray_info['summary']['total_controllers'])
                    return smartarray_info
                    
                except Exception as e:
                    logger.warning("Failed to get detailed SmartArray info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "controllers": [], "logical_drives": [], "physical_drives": []}
            else:
                logger.warning("SmartArray information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "SmartArray information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get SmartArray information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_hba_information(self):
        """Get Host Bus Adapter (HBA) information"""
        logger.info("Getting HBA information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                hba_info = {"adapters": []}
                
                try:
                    # Try to get HBA information from network adapters or PCIe devices
                    if hasattr(self.client, 'get_pcie_device_inventory'):
                        pcie_devices = self.client.get_pcie_device_inventory()
                        
                        for device in pcie_devices:
                            if isinstance(device, dict):
                                # Look for HBA-like devices (Fibre Channel, InfiniBand, etc.)
                                device_type = device.get('DeviceType', '').lower()
                                device_name = device.get('Name', '').lower()
                                
                                if any(hba_type in device_type or hba_type in device_name 
                                       for hba_type in ['fibre', 'fc', 'hba', 'infiniband', 'ib']):
                                    hba_adapter = {
                                        'name': device.get('Name', 'Unknown'),
                                        'model': device.get('Model', 'Unknown'),
                                        'manufacturer': device.get('Manufacturer', 'Unknown'),
                                        'device_type': device.get('DeviceType', 'Unknown'),
                                        'firmware_version': device.get('FirmwareVersion', 'Unknown'),
                                        'driver_version': device.get('DriverVersion', 'Unknown'),
                                        'location': device.get('Location', 'Unknown'),
                                        'status': device.get('Status', {}).get('Health', 'Unknown'),
                                        'pci_device_id': device.get('DeviceID', 'Unknown'),
                                        'pci_vendor_id': device.get('VendorID', 'Unknown')
                                    }
                                    hba_info['adapters'].append(hba_adapter)
                    
                    # Also check network adapters for HBA functionality
                    network_adapters = self.get_network_adapter_details()
                    for adapter in network_adapters:
                        if isinstance(adapter, dict):
                            adapter_name = adapter.get('name', '').lower()
                            if any(hba_type in adapter_name for hba_type in ['fibre', 'fc', 'infiniband', 'ib']):
                                hba_adapter = {
                                    'name': adapter.get('name', 'Unknown'),
                                    'model': adapter.get('model', 'Unknown'),
                                    'manufacturer': adapter.get('manufacturer', 'Unknown'),
                                    'device_type': 'Network HBA',
                                    'firmware_version': adapter.get('firmware_version', 'Unknown'),
                                    'mac_address': adapter.get('mac_address', 'Unknown'),
                                    'status': adapter.get('status', 'Unknown'),
                                    'speed': adapter.get('speed', 'Unknown')
                                }
                                hba_info['adapters'].append(hba_adapter)
                    
                    hba_info['adapter_count'] = len(hba_info['adapters'])
                    
                    logger.info("Retrieved HBA information", 
                               ilo_ip=self.ilo_ip,
                               adapter_count=hba_info['adapter_count'])
                    return hba_info
                    
                except Exception as e:
                    logger.warning("Failed to get detailed HBA info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "adapters": [], "adapter_count": 0}
            else:
                logger.warning("HBA information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "HBA information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get HBA information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_usb_information(self):
        """Get USB port and device information"""
        logger.info("Getting USB information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                usb_info = {"ports": [], "devices": []}
                
                try:
                    # Try to get USB information from system or chassis
                    if hasattr(self.client, 'get_usb_config'):
                        usb_config = self.client.get_usb_config()
                        if isinstance(usb_config, dict):
                            # Parse USB ports
                            ports = usb_config.get('Ports', [])
                            for port in ports:
                                if isinstance(port, dict):
                                    port_info = {
                                        'name': port.get('Name', 'Unknown'),
                                        'location': port.get('Location', 'Unknown'),
                                        'usb_version': port.get('USBVersion', 'Unknown'),
                                        'status': port.get('Status', {}).get('Health', 'Unknown'),
                                        'enabled': port.get('Enabled', 'Unknown'),
                                        'connected_device': port.get('ConnectedDevice', 'None')
                                    }
                                    usb_info['ports'].append(port_info)
                    
                    # Try alternative method via chassis or system information
                    elif hasattr(self.client, 'get_system_health'):
                        health_data = self.client.get_system_health()
                        if isinstance(health_data, dict) and 'usb' in health_data:
                            usb_data = health_data['usb']
                            if isinstance(usb_data, list):
                                for usb_item in usb_data:
                                    port_info = {
                                        'name': usb_item.get('Name', 'Unknown'),
                                        'status': usb_item.get('Status', 'Unknown'),
                                        'location': usb_item.get('Location', 'Unknown')
                                    }
                                    usb_info['ports'].append(port_info)
                    
                    usb_info['port_count'] = len(usb_info['ports'])
                    usb_info['device_count'] = len(usb_info['devices'])
                    
                    logger.info("Retrieved USB information", 
                               ilo_ip=self.ilo_ip,
                               port_count=usb_info['port_count'])
                    return usb_info
                    
                except Exception as e:
                    logger.warning("Failed to get detailed USB info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "ports": [], "devices": [], "port_count": 0, "device_count": 0}
            else:
                logger.warning("USB information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "USB information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get USB information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_power_supply_information(self):
        """Get power supply information"""
        logger.info("Getting power supply information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                power_supply_info = {"power_supplies": []}
                
                try:
                    # Get power supply information
                    if hasattr(self.client, 'get_power_details'):
                        power_data = self.client.get_power_details()
                        if isinstance(power_data, dict):
                            power_supplies = power_data.get('PowerSupplies', [])
                            for ps in power_supplies:
                                if isinstance(ps, dict):
                                    ps_info = {
                                        'name': ps.get('Name', 'Unknown'),
                                        'model': ps.get('Model', 'Unknown'),
                                        'manufacturer': ps.get('Manufacturer', 'Unknown'),
                                        'serial_number': ps.get('SerialNumber', 'Unknown'),
                                        'part_number': ps.get('PartNumber', 'Unknown'),
                                        'power_capacity_watts': ps.get('PowerCapacityWatts', 'Unknown'),
                                        'power_output_watts': ps.get('PowerOutputWatts', 'Unknown'),
                                        'efficiency_percent': ps.get('EfficiencyPercent', 'Unknown'),
                                        'status': ps.get('Status', {}).get('Health', 'Unknown'),
                                        'power_input_type': ps.get('PowerInputType', 'Unknown'),
                                        'firmware_version': ps.get('FirmwareVersion', 'Unknown'),
                                        'location': ps.get('Location', 'Unknown')
                                    }
                                    power_supply_info['power_supplies'].append(ps_info)
                    
                    # Try alternative method if first doesn't work
                    elif hasattr(self.client, 'get_system_health'):
                        health_data = self.client.get_system_health()
                        if isinstance(health_data, dict) and 'power_supplies' in health_data:
                            ps_data = health_data['power_supplies']
                            if isinstance(ps_data, list):
                                for ps in ps_data:
                                    ps_info = {
                                        'name': ps.get('Name', 'Unknown'),
                                        'status': ps.get('Status', 'Unknown'),
                                        'power_capacity_watts': ps.get('PowerCapacityWatts', 'Unknown')
                                    }
                                    power_supply_info['power_supplies'].append(ps_info)
                    
                    # Calculate summary
                    power_supply_info['summary'] = {
                        'total_power_supplies': len(power_supply_info['power_supplies']),
                        'total_capacity_watts': sum(ps.get('power_capacity_watts', 0) 
                                                  for ps in power_supply_info['power_supplies'] 
                                                  if isinstance(ps.get('power_capacity_watts'), (int, float))),
                        'healthy_count': len([ps for ps in power_supply_info['power_supplies'] 
                                            if ps.get('status', '').lower() in ['ok', 'good', 'healthy']])
                    }
                    
                    logger.info("Retrieved power supply information", 
                               ilo_ip=self.ilo_ip,
                               ps_count=power_supply_info['summary']['total_power_supplies'])
                    return power_supply_info
                    
                except Exception as e:
                    logger.warning("Failed to get detailed power supply info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "power_supplies": []}
            else:
                logger.warning("Power supply information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Power supply information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get power supply information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_fan_information(self):
        """Get fan information"""
        logger.info("Getting fan information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                fan_info = {"fans": []}
                
                try:
                    # Get fan information
                    if hasattr(self.client, 'get_thermal_config'):
                        thermal_data = self.client.get_thermal_config()
                        if isinstance(thermal_data, dict):
                            fans = thermal_data.get('Fans', [])
                            for fan in fans:
                                if isinstance(fan, dict):
                                    fan_detail = {
                                        'name': fan.get('Name', 'Unknown'),
                                        'location': fan.get('Location', 'Unknown'),
                                        'current_reading': fan.get('Reading', 'Unknown'),
                                        'reading_units': fan.get('ReadingUnits', 'Unknown'),
                                        'lower_threshold': fan.get('LowerThresholdNonCritical', 'Unknown'),
                                        'upper_threshold': fan.get('UpperThresholdNonCritical', 'Unknown'),
                                        'status': fan.get('Status', {}).get('Health', 'Unknown'),
                                        'manufacturer': fan.get('Manufacturer', 'Unknown'),
                                        'model': fan.get('Model', 'Unknown'),
                                        'part_number': fan.get('PartNumber', 'Unknown'),
                                        'redundancy': fan.get('Redundancy', 'Unknown')
                                    }
                                    fan_info['fans'].append(fan_detail)
                    
                    # Try alternative method if first doesn't work
                    elif hasattr(self.client, 'get_system_health'):
                        health_data = self.client.get_system_health()
                        if isinstance(health_data, dict) and 'fans' in health_data:
                            fan_data = health_data['fans']
                            if isinstance(fan_data, list):
                                for fan in fan_data:
                                    fan_detail = {
                                        'name': fan.get('Name', 'Unknown'),
                                        'status': fan.get('Status', 'Unknown'),
                                        'current_reading': fan.get('Reading', 'Unknown'),
                                        'location': fan.get('Location', 'Unknown')
                                    }
                                    fan_info['fans'].append(fan_detail)
                    
                    # Calculate summary
                    fan_info['summary'] = {
                        'total_fans': len(fan_info['fans']),
                        'healthy_count': len([fan for fan in fan_info['fans'] 
                                            if fan.get('status', '').lower() in ['ok', 'good', 'healthy']]),
                        'average_reading': None
                    }
                    
                    # Calculate average reading if available
                    readings = [fan.get('current_reading') for fan in fan_info['fans'] 
                              if isinstance(fan.get('current_reading'), (int, float))]
                    if readings:
                        fan_info['summary']['average_reading'] = sum(readings) / len(readings)
                    
                    logger.info("Retrieved fan information", 
                               ilo_ip=self.ilo_ip,
                               fan_count=fan_info['summary']['total_fans'])
                    return fan_info
                    
                except Exception as e:
                    logger.warning("Failed to get detailed fan info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e), "fans": []}
            else:
                logger.warning("Fan information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Fan information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get fan information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_enhanced_ilo_information(self):
        """Get enhanced iLO information including network settings, licenses, and security"""
        logger.info("Getting enhanced iLO information", ilo_ip=self.ilo_ip)
        try:
            if self.use_redfish:
                ilo_enhanced_info = {}
                
                try:
                    # Get Manager information (iLO details)
                    if hasattr(self.client, 'get_manager_info'):
                        manager_info = self.client.get_manager_info()
                        if isinstance(manager_info, dict):
                            ilo_enhanced_info['manager'] = {
                                'name': manager_info.get('Name', 'Unknown'),
                                'model': manager_info.get('Model', 'Unknown'),
                                'firmware_version': manager_info.get('FirmwareVersion', 'Unknown'),
                                'datetime': manager_info.get('DateTime', 'Unknown'),
                                'date_time_local_offset': manager_info.get('DateTimeLocalOffset', 'Unknown'),
                                'status': manager_info.get('Status', {}).get('Health', 'Unknown'),
                                'power_state': manager_info.get('PowerState', 'Unknown'),
                                'uuid': manager_info.get('UUID', 'Unknown')
                            }
                    
                    # Get iLO network configuration
                    if hasattr(self.client, 'get_manager_ethernet_interface'):
                        network_config = self.client.get_manager_ethernet_interface()
                        if isinstance(network_config, dict):
                            ilo_enhanced_info['network'] = {
                                'hostname': network_config.get('HostName', 'Unknown'),
                                'fqdn': network_config.get('FQDN', 'Unknown'),
                                'mac_address': network_config.get('MACAddress', 'Unknown'),
                                'interface_enabled': network_config.get('InterfaceEnabled', 'Unknown'),
                                'link_status': network_config.get('LinkStatus', 'Unknown'),
                                'speed_mbps': network_config.get('SpeedMbps', 'Unknown'),
                                'full_duplex': network_config.get('FullDuplex', 'Unknown'),
                                'ipv4_addresses': network_config.get('IPv4Addresses', []),
                                'ipv6_addresses': network_config.get('IPv6Addresses', []),
                                'name_servers': network_config.get('NameServers', [])
                            }
                    
                    # Get iLO license information
                    if hasattr(self.client, 'get_license_info'):
                        license_info = self.client.get_license_info()
                        if isinstance(license_info, dict):
                            ilo_enhanced_info['licensing'] = {
                                'license_key': license_info.get('LicenseKey', 'Unknown'),
                                'license_type': license_info.get('LicenseType', 'Unknown'),
                                'license_string': license_info.get('LicenseString', 'Unknown'),
                                'expiry_date': license_info.get('ExpiryDate', 'Unknown'),
                                'features': license_info.get('Features', [])
                            }
                    
                    # Get security settings
                    if hasattr(self.client, 'get_security_params'):
                        security_params = self.client.get_security_params()
                        if isinstance(security_params, dict):
                            ilo_enhanced_info['security'] = {
                                'encryption_settings': security_params.get('EncryptionSettings', {}),
                                'authentication_settings': security_params.get('AuthenticationSettings', {}),
                                'session_timeout': security_params.get('SessionTimeout', 'Unknown'),
                                'ssl_settings': security_params.get('SSLSettings', {})
                            }
                    
                    logger.info("Retrieved enhanced iLO information", ilo_ip=self.ilo_ip)
                    return ilo_enhanced_info
                    
                except Exception as e:
                    logger.warning("Failed to get enhanced iLO info", ilo_ip=self.ilo_ip, error=str(e))
                    return {"error": str(e)}
            else:
                logger.warning("Enhanced iLO information not available via RIBCL", ilo_ip=self.ilo_ip)
                return {"error": "Enhanced iLO information requires Redfish API"}
        except Exception as e:
            logger.error("Failed to get enhanced iLO information", ilo_ip=self.ilo_ip, error=str(e))
            return {"error": str(e)}

    # Update the comprehensive hardware inventory method to include all new components
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_comprehensive_hardware_inventory_enhanced(self):
        """Get complete enhanced hardware inventory including all system components"""
        logger.info("Getting comprehensive enhanced hardware inventory", ilo_ip=self.ilo_ip)
        
        inventory = {
            "collection_method": "BMC_API_Enhanced",
            "collection_timestamp": datetime.now().isoformat(),
            "ilo_ip": self.ilo_ip,
            "api_type": "Redfish" if self.use_redfish else "RIBCL",
            "errors": []
        }
        
        # Get basic hardware info (existing methods)
        for component, method in [
            ("server_info", self.get_server_serial_model),
            ("bios", self.get_bios_information),
            ("processors", self.get_processor_information),
            ("memory", self.get_memory_information),
            ("storage", self.get_storage_information),
            ("network_adapters", self.get_network_adapter_details),
            ("power_thermal", self.get_power_thermal_information),
        ]:
            try:
                if component == "network_adapters":
                    # Handle network adapters specially to maintain compatibility
                    network_info = method()
                    inventory[component] = {
                        "adapters": network_info,
                        "adapter_count": len(network_info) if network_info else 0
                    }
                else:
                    inventory[component] = method()
            except Exception as e:
                inventory["errors"].append(f"{component}: {str(e)}")
                inventory[component] = {"error": str(e)}
        
        # Get enhanced hardware components
        for component, method in [
            ("smartarray", self.get_smartarray_information),
            ("hba_adapters", self.get_hba_information),
            ("usb_devices", self.get_usb_information),
            ("power_supplies", self.get_power_supply_information),
            ("fans", self.get_fan_information),
            ("ilo_enhanced", self.get_enhanced_ilo_information),
        ]:
            try:
                inventory[component] = method()
            except Exception as e:
                inventory["errors"].append(f"{component}: {str(e)}")
                inventory[component] = {"error": str(e)}
        
        # Calculate enhanced collection success rate
        total_categories = 13  # Updated count including new components
        successful_categories = total_categories - len(inventory["errors"])
        inventory["collection_success_rate"] = f"{successful_categories}/{total_categories}"
        inventory["collection_status"] = "complete" if len(inventory["errors"]) == 0 else "partial"
        
        # Add comprehensive summary
        inventory["hardware_summary"] = {
            "server_manufacturer": inventory.get("server_info", {}).get("manufacturer", "Unknown"),
            "server_model": inventory.get("server_info", {}).get("model", "Unknown"),
            "total_processors": inventory.get("processors", {}).get("processor_count", 0),
            "total_memory_gb": inventory.get("memory", {}).get("total_memory_gb", 0),
            "total_storage_devices": inventory.get("storage", {}).get("device_count", 0),
            "total_network_adapters": inventory.get("network_adapters", {}).get("adapter_count", 0),
            "smartarray_controllers": inventory.get("smartarray", {}).get("summary", {}).get("total_controllers", 0),
            "power_supplies": inventory.get("power_supplies", {}).get("summary", {}).get("total_power_supplies", 0),
            "fans": inventory.get("fans", {}).get("summary", {}).get("total_fans", 0),
            "hba_adapters": inventory.get("hba_adapters", {}).get("adapter_count", 0),
            "usb_ports": inventory.get("usb_devices", {}).get("port_count", 0)
        }
        
        logger.info("Completed comprehensive enhanced hardware inventory", 
                   ilo_ip=self.ilo_ip,
                   success_rate=inventory["collection_success_rate"],
                   status=inventory["collection_status"])
        
        return inventory

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_comprehensive_hardware_inventory_with_fallback(self):
        """Get comprehensive hardware inventory with enhanced fallback support for iLO4"""
        logger.info("Getting comprehensive hardware inventory with enhanced fallback support", ilo_ip=self.ilo_ip)
        
        # First try the comprehensive enhanced BMC API method
        try:
            inventory = self.get_comprehensive_hardware_inventory_enhanced()
            
            # Check if we got meaningful data (not all "Unknown")
            server_info = inventory.get("server_info", {})
            bios_info = inventory.get("bios", {})
            network_info = inventory.get("network_adapters", {})
            
            has_meaningful_data = (
                (server_info.get("manufacturer") not in ["Unknown", None] and server_info.get("manufacturer") != "") or
                (server_info.get("model") not in ["Unknown", None] and server_info.get("model") != "") or
                (server_info.get("serial_number") not in ["Unknown", None] and server_info.get("serial_number") != "") or
                (bios_info.get("version") not in ["Unknown", None] and bios_info.get("version") != "") or
                (network_info.get("adapter_count", 0) > 0 and len(network_info.get("adapters", [])) > 0)
            )
            
            if has_meaningful_data:
                # BMC API worked well enough
                inventory["fallback_used"] = False
                logger.info("Enhanced BMC API provided sufficient data", ilo_ip=self.ilo_ip)
                return inventory
            else:
                logger.info("Enhanced BMC API returned mostly unknown values, trying fallback methods", ilo_ip=self.ilo_ip)
        except Exception as e:
            logger.warning("Enhanced BMC API collection failed, trying fallback methods", ilo_ip=self.ilo_ip, error=str(e))
        
        # If enhanced BMC API failed or had too many errors, try XML endpoint fallback first
        logger.info("Attempting XML endpoint fallback", ilo_ip=self.ilo_ip)
        xml_data = self.get_xml_endpoint_data()
        
        if xml_data.get("status") == "success":
            # Parse XML data
            parsed_xml = self.parse_xml_hardware_data(xml_data["xml_data"])
            
            if parsed_xml.get("parsing_successful"):
                # Convert XML data to comprehensive inventory format
                fallback_inventory = {
                    "collection_method": "XML_endpoint_primary",
                    "collection_timestamp": datetime.now().isoformat(),
                   
                   
                    "ilo_ip": self.ilo_ip,
                    "api_type": "XML",
                    "fallback_used": True,
                    "bmc_api_failed": True,
                    "errors": ["Enhanced BMC API insufficient, using XML endpoint as primary source"]
                }
                
                # Map XML data to inventory structure
                if "server_info" in parsed_xml:
                    fallback_inventory["server_info"] = parsed_xml["server_info"]
                
                if "ilo_info" in parsed_xml:
                    fallback_inventory["bios"] = {
                        "version": "Unknown (XML source)",
                        "ilo_firmware": parsed_xml["ilo_info"].get("firmware_version", "Unknown"),
                        "ilo_product": parsed_xml["ilo_info"].get("product_name", "Unknown"),
                        "raw_data": parsed_xml["ilo_info"]
                    }
                    fallback_inventory["ilo_enhanced"] = {
                        "manager": {
                            "firmware_version": parsed_xml["ilo_info"].get("firmware_version", "Unknown"),
                            "name": parsed_xml["ilo_info"].get("product_name", "Unknown")
                        }
                    }
                
                if "network_adapters" in parsed_xml:
                    fallback_inventory["network_adapters"] = parsed_xml["network_adapters"]
                
                if "health_status" in parsed_xml:
                    fallback_inventory["health_status"] = parsed_xml["health_status"]
                
                # Default empty sections for enhanced components (not available via XML)
                fallback_inventory.update({
                    "processors": {"error": "Not available via XML endpoint", "processor_count": 0},
                    "memory": {"error": "Not available via XML endpoint", "module_count": 0},
                    "storage": {"error": "Not available via XML endpoint", "device_count": 0},
                    "power_thermal": {"error": "Not available via XML endpoint"},
                    "smartarray": {"error": "Not available via XML endpoint", "controllers": [], "logical_drives": [], "physical_drives": []},
                    "hba_adapters": {"error": "Not available via XML endpoint", "adapters": [], "adapter_count": 0},
                    "usb_devices": {"error": "Not available via XML endpoint", "ports": [], "devices": [], "port_count": 0, "device_count": 0},
                    "power_supplies": {"error": "Not available via XML endpoint", "power_supplies": []},
                    "fans": {"error": "Not available via XML endpoint", "fans": []},
                    "collection_success_rate": "4/13",  # server_info, bios, network, health out of 13 total
                    "collection_status": "partial_via_xml",
                    "xml_parsed_data": parsed_xml,
                    "hardware_summary": {
                        "server_manufacturer": fallback_inventory.get("server_info", {}).get("manufacturer", "Unknown"),
                        "server_model": fallback_inventory.get("server_info", {}).get("model", "Unknown"),
                        "total_processors": 0,
                        "total_memory_gb": 0,
                        "total_storage_devices": 0,
                        "total_network_adapters": fallback_inventory.get("network_adapters", {}).get("adapter_count", 0),
                        "smartarray_controllers": 0,
                        "power_supplies": 0,
                        "fans": 0,
                        "hba_adapters": 0,
                        "usb_ports": 0
                    }
                })
                
                logger.info("Successfully collected hardware data via XML fallback", 
                           ilo_ip=self.ilo_ip,
                           server_model=fallback_inventory.get("server_info", {}).get("model", "Unknown"))
                
                return fallback_inventory
            else:
                logger.warning("XML parsing failed, trying alternative methods", ilo_ip=self.ilo_ip)
        
        # If XML endpoint also failed, use minimal fallback
        logger.info("Using minimal fallback inventory structure", ilo_ip=self.ilo_ip)
        alt_inventory = {
            "collection_method": "minimal_fallback",
            "collection_timestamp": datetime.now().isoformat(),
            "ilo_ip": self.ilo_ip,
            "api_type": "Fallback",
            "fallback_used": True,
            "bmc_api_failed": True,
            "xml_endpoint_failed": xml_data.get("status") != "success",
            "collection_status": "minimal_data_only",
            "errors": ["BMC API failed", "XML endpoint failed"],
            "server_info": {"error": "Not available"},
            "network_adapters": {"adapters": [], "adapter_count": 0},
            "health_status": {"system_health": "Unknown"},
            "processors": {"error": "Not available", "processor_count": 0},
            "memory": {"error": "Not available", "module_count": 0},
            "storage": {"error": "Not available", "device_count": 0},
            "power_thermal": {"error": "Not available"},
            "bios": {"version": "Unknown", "error": "Not available"},
            "smartarray": {"error": "Not available", "controllers": [], "logical_drives": [], "physical_drives": []},
            "hba_adapters": {"error": "Not available", "adapters": [], "adapter_count": 0},
            "usb_devices": {"error": "Not available", "ports": [], "devices": [], "port_count": 0, "device_count": 0},
            "power_supplies": {"error": "Not available", "power_supplies": []},
            "fans": {"error": "Not available", "fans": []},
            "ilo_enhanced": {"error": "Not available"},
            "collection_success_rate": "0/13",
            "hardware_summary": {
                "server_manufacturer": "Unknown",
                "server_model": "Unknown",
                "total_processors": 0,
                "total_memory_gb": 0,
                "total_storage_devices": 0,
                "total_network_adapters": 0,
                "smartarray_controllers": 0,
                "power_supplies": 0,
                "fans": 0,
                "hba_adapters": 0,
                "usb_ports": 0
            }
        }
        
        return alt_inventory
    
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_power_status_via_redfish_http(self):
        """Get power status using direct Redfish HTTP requests"""
        logger.info("Getting power status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        
        try:
            # Prepare authentication header
            auth_string = f"{self.ilo_username}:{self.ilo_password}"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {auth_bytes}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get system information
            system_url = f"https://{self.ilo_ip}/redfish/v1/Systems/1/"
            
            logger.debug("Making Redfish request for power status", 
                        url=system_url, ilo_ip=self.ilo_ip)
            
            response = requests.get(
                system_url, 
                headers=headers, 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            response.raise_for_status()
            system_data = response.json()
            
            power_state = system_data.get('PowerState', 'Unknown')
            
            logger.info("Successfully retrieved power status via direct Redfish HTTP", 
                       ilo_ip=self.ilo_ip, 
                       power_state=power_state)
            
            return power_state
            
        except Exception as e:
            logger.error("Failed to get power status via direct Redfish HTTP", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_firmware_version_via_redfish_http(self):
        """Get firmware version using direct Redfish HTTP requests"""
        logger.info("Getting firmware version via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        
        try:
            # Prepare authentication header
            auth_string = f"{self.ilo_username}:{self.ilo_password}"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {auth_bytes}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get manager information (iLO firmware)
            manager_url = f"https://{self.ilo_ip}/redfish/v1/Managers/1/"
            
            logger.debug("Making Redfish request for firmware version", 
                        url=manager_url, ilo_ip=self.ilo_ip)
            
            response = requests.get(
                manager_url, 
                headers=headers, 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            response.raise_for_status()
            manager_data = response.json()
            
            firmware_version = manager_data.get('FirmwareVersion', 'Unknown')
            
            logger.info("Successfully retrieved firmware version via direct Redfish HTTP", 
                       ilo_ip=self.ilo_ip, 
                       firmware_version=firmware_version)
            
            return firmware_version
            
        except Exception as e:
            logger.error("Failed to get firmware version via direct Redfish HTTP", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_health_status_via_redfish_http(self):
        """Get health status using direct Redfish HTTP requests"""
        logger.info("Getting health status via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        
        try:
            # Prepare authentication header
            auth_string = f"{self.ilo_username}:{self.ilo_password}"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {auth_bytes}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get system information for health status
            system_url = f"https://{self.ilo_ip}/redfish/v1/Systems/1/"
            
            logger.debug("Making Redfish request for health status", 
                        url=system_url, ilo_ip=self.ilo_ip)
            
            response = requests.get(
                system_url, 
                headers=headers, 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            response.raise_for_status()
            system_data = response.json()
            
            # Extract health information from Status object
            status_info = system_data.get('Status', {})
            health_status = status_info.get('Health', 'Unknown')
            state = status_info.get('State', 'Unknown')
            
            # Combine health and state for more comprehensive status
            if health_status != 'Unknown' and state != 'Unknown':
                full_health_status = f"{health_status} ({state})"
            elif health_status != 'Unknown':
                full_health_status = health_status
            elif state != 'Unknown':
                full_health_status = state
            else:
                full_health_status = 'Unknown'
            
            logger.info("Successfully retrieved health status via direct Redfish HTTP", 
                       ilo_ip=self.ilo_ip, 
                       health_status=full_health_status)
            
            return full_health_status
            
        except Exception as e:
            logger.error("Failed to get health status via direct Redfish HTTP", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise

    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_boot_settings_via_redfish_http(self):
        """Get boot settings using direct Redfish HTTP requests"""
        logger.info("Getting boot settings via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        
        try:
            # Prepare authentication header
            auth_string = f"{self.ilo_username}:{self.ilo_password}"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {auth_bytes}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get system information for boot settings
            system_url = f"https://{self.ilo_ip}/redfish/v1/Systems/1/"
            
            logger.debug("Making Redfish request for boot settings", 
                        url=system_url, ilo_ip=self.ilo_ip)
            
            response = requests.get(
                system_url, 
                headers=headers, 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            response.raise_for_status()
            system_data = response.json()
            
            # Extract boot information
            boot_info = system_data.get('Boot', {})
            boot_settings = {
                'boot_source_override_enabled': boot_info.get('BootSourceOverrideEnabled', 'Unknown'),
                'boot_source_override_target': boot_info.get('BootSourceOverrideTarget', 'Unknown'),
                'boot_source_override_mode': boot_info.get('BootSourceOverrideMode', 'Unknown'),
                'uefi_target_boot_source_override': boot_info.get('UefiTargetBootSourceOverride', 'Unknown')
            }
            
            # Also try to get boot order information
            boot_order = boot_info.get('BootOrder', [])
            if boot_order:
                boot_settings['boot_order'] = boot_order
            
            logger.info("Successfully retrieved boot settings via direct Redfish HTTP", 
                       ilo_ip=self.ilo_ip, 
                       boot_settings=boot_settings)
            
            return boot_settings
            
        except Exception as e:
            logger.error("Failed to get boot settings via direct Redfish HTTP", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise
        
        # If all methods failed
        logger.error("All collection methods failed", ilo_ip=self.ilo_ip)
        return {
            "collection_method": "all_failed",
            "collection_timestamp": datetime.now().isoformat(),
            "ilo_ip": self.ilo_ip,
            "api_type": "N/A",
            "fallback_used": True,
            "bmc_api_failed": True,
            "xml_endpoint_failed": True,
            "alternative_methods_failed": True,
            "collection_status": "failed",
            "errors": ["All collection methods failed"],
            "server_info": {"error": "All collection methods failed"},
            "network_adapters": {"adapters": [], "adapter_count": 0, "error": "All collection methods failed"},
            "health_status": {"system_health": "Unknown", "error": "All collection methods failed"},
            "processors": {"error": "All collection methods failed", "processor_count": 0},
            "memory": {"error": "All collection methods failed", "module_count": 0},
            "storage": {"error": "All collection methods failed", "device_count": 0},
            "power_thermal": {"error": "All collection methods failed"},
            "bios": {"error": "All collection methods failed"},
            "smartarray": {"error": "All collection methods failed", "controllers": [], "logical_drives": [], "physical_drives": []},
            "hba_adapters": {"error": "All collection methods failed", "adapters": [], "adapter_count": 0},
            "usb_devices": {"error": "All collection methods failed", "ports": [], "devices": [], "port_count": 0, "device_count": 0},
            "power_supplies": {"error": "All collection methods failed", "power_supplies": []},
            "fans": {"error": "All collection methods failed", "fans": []},
            "ilo_enhanced": {"error": "All collection methods failed"},
            "collection_success_rate": "0/13",
            "hardware_summary": {
                "server_manufacturer": "Unknown",
                "server_model": "Unknown",
                "total_processors": 0,
                "total_memory_gb": 0,
                "total_storage_devices": 0,
                "total_network_adapters": 0,
                "smartarray_controllers": 0,
                "power_supplies": 0,
                "fans": 0,
                "hba_adapters": 0,
                "usb_ports": 0
            }
        }
    
    @retry_with_backoff(max_tries=3, initial_delay=1)
    @breaker
    def get_network_adapters_via_redfish_http(self):
        """Get network adapter information using direct Redfish HTTP requests
        
        This method bypasses proliantutils issues by making direct HTTPS requests
        to the Redfish API endpoints, which provides more reliable MAC address collection.
        """
        logger.info("Getting network adapters via direct Redfish HTTP", ilo_ip=self.ilo_ip)
        
        try:
            # Prepare authentication header
            auth_string = f"{self.ilo_username}:{self.ilo_password}"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {auth_bytes}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # First, get the main system information
            system_url = f"https://{self.ilo_ip}/redfish/v1/Systems/1/"
            
            logger.debug("Making Redfish request to Systems endpoint", 
                        url=system_url, ilo_ip=self.ilo_ip)
            
            response = requests.get(
                system_url, 
                headers=headers, 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            response.raise_for_status()
            system_data = response.json()
            
            # Extract MAC addresses from HostCorrelation if available
            mac_addresses = []
            if 'HostCorrelation' in system_data and 'HostMACAddress' in system_data['HostCorrelation']:
                mac_addresses = system_data['HostCorrelation']['HostMACAddress']
                logger.info("Found MAC addresses in HostCorrelation", 
                           ilo_ip=self.ilo_ip, 
                           mac_count=len(mac_addresses),
                           mac_addresses=mac_addresses)
            
            # Try to get additional network adapter details from EthernetInterfaces
            adapters = []
            try:
                ethernet_url = f"https://{self.ilo_ip}/redfish/v1/Systems/1/EthernetInterfaces/"
                logger.debug("Making Redfish request to EthernetInterfaces", 
                            url=ethernet_url, ilo_ip=self.ilo_ip)
                
                eth_response = requests.get(
                    ethernet_url, 
                    headers=headers, 
                    verify=self.verify_ssl, 
                    timeout=30
                )
                
                if eth_response.status_code == 200:
                    eth_data = eth_response.json()
                    if 'Members' in eth_data:
                        for member in eth_data['Members']:
                            if '@odata.id' in member:
                                # Get detailed info for each adapter
                                adapter_url = f"https://{self.ilo_ip}{member['@odata.id']}"
                                try:
                                    adapter_response = requests.get(
                                        adapter_url, 
                                        headers=headers, 
                                        verify=self.verify_ssl, 
                                        timeout=30
                                    )
                                    if adapter_response.status_code == 200:
                                        adapter_info = adapter_response.json()
                                        adapter_details = {
                                            'name': adapter_info.get('Name', 'Unknown'),
                                            'description': adapter_info.get('Description', 'Unknown'),
                                            'mac_address': adapter_info.get('MACAddress', 'Unknown'),
                                            'permanent_mac_address': adapter_info.get('PermanentMACAddress', 'Unknown'),
                                            'speed_mbps': adapter_info.get('SpeedMbps', 'Unknown'),
                                            'full_duplex': adapter_info.get('FullDuplex', 'Unknown'),
                                            'mtu_size': adapter_info.get('MTUSize', 'Unknown'),
                                            'auto_neg': adapter_info.get('AutoNeg', 'Unknown'),
                                            'link_status': adapter_info.get('LinkStatus', 'Unknown'),
                                            'status': adapter_info.get('Status', {}).get('Health', 'Unknown'),
                                            'firmware_version': adapter_info.get('UefiDevicePath', 'Unknown')
                                        }
                                        adapters.append(adapter_details)
                                        logger.debug("Retrieved adapter details", 
                                                    adapter_name=adapter_details['name'],
                                                    mac_address=adapter_details['mac_address'])
                                except Exception as e:
                                    logger.warning("Failed to get details for adapter", 
                                                  adapter_url=adapter_url, error=str(e))
                                    continue
                    
                    logger.info("Retrieved ethernet interface details", 
                               ilo_ip=self.ilo_ip, 
                               adapter_count=len(adapters))
                else:
                    logger.warning("EthernetInterfaces endpoint returned non-200 status", 
                                  status_code=eth_response.status_code)
            
            except Exception as e:
                logger.warning("Failed to get EthernetInterfaces details", 
                              ilo_ip=self.ilo_ip, error=str(e))
            
            # Combine results with preference for detailed adapter info
            result = {
                'adapters': adapters,
                'host_mac_addresses': mac_addresses,
                'system_info': {
                    'manufacturer': system_data.get('Manufacturer', 'Unknown'),
                    'model': system_data.get('Model', 'Unknown'),
                    'serial_number': system_data.get('SerialNumber', 'Unknown'),
                    'uuid': system_data.get('UUID', 'Unknown'),
                    'power_state': system_data.get('PowerState', 'Unknown')
                },
                'collection_method': 'direct_redfish_http',
                'total_mac_addresses': len(mac_addresses),
                'detailed_adapters': len(adapters)
            }
            
            logger.info("Successfully retrieved network information via direct Redfish HTTP", 
                       ilo_ip=self.ilo_ip,
                       total_macs=len(mac_addresses),
                       detailed_adapters=len(adapters))
            
            return result
            
        except requests.exceptions.SSLError as e:
            logger.error("SSL certificate error with Redfish HTTP request", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise Exception(f"SSL certificate verification failed. Try setting verify_ssl=False. Error: {str(e)}")
        
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error with Redfish HTTP request", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise Exception(f"Failed to connect to iLO. Check IP address and network connectivity. Error: {str(e)}")
        
        except requests.exceptions.Timeout as e:
            logger.error("Timeout error with Redfish HTTP request", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise Exception(f"Request timed out. iLO may be slow or unresponsive. Error: {str(e)}")
        
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error with Redfish HTTP request", 
                        ilo_ip=self.ilo_ip, 
                        status_code=e.response.status_code if e.response else 'Unknown',
                        error=str(e))
            if e.response and e.response.status_code == 401:
                raise Exception(f"Authentication failed. Check username and password. Error: {str(e)}")
            else:
                raise Exception(f"HTTP error occurred. Status: {e.response.status_code if e.response else 'Unknown'}. Error: {str(e)}")
        
        except json.JSONDecodeError as e:
            logger.error("JSON decode error with Redfish HTTP response", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise Exception(f"Failed to parse JSON response from iLO. Error: {str(e)}")
        
        except Exception as e:
            logger.error("Unexpected error with Redfish HTTP request", 
                        ilo_ip=self.ilo_ip, error=str(e))
            raise Exception(f"Unexpected error occurred: {str(e)}")
    

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
        
        # Enhance server details with additional metadata
        server_details.update({
            "collection_metadata": {
                "method": "Redfish" if use_redfish else "RIBCL",
                "timestamp": datetime.now().isoformat(),
                "verify_ssl": verify_ssl,
                "ilo_ip": ilo_ip
            }
        })
        
        logger.info("Successfully collected iLO information", ilo_ip=ilo_ip)
        return server_details
        
    except Exception as e:
        logger.error("Failed to collect iLO information", 
                     ilo_ip=ilo_ip, 
                     error=str(e))
        # Return partial data structure even on error
        return {
            "error": str(e),
            "collection_metadata": {
                "method": "Redfish" if use_redfish else "RIBCL",
                "timestamp": datetime.now().isoformat(),
                "verify_ssl": verify_ssl,
                "ilo_ip": ilo_ip,
                "error_occurred": True
            },
            "product_name": "Collection Failed",
            "power_status": "Unknown",
            "firmware_version": "Unknown",
            "host_uuid": "Unknown",
            "boot_settings": {
                "one_time_boot": "Unknown",
                "persistent_boot": "Unknown"
            },
            "health_status": {
                "system_health": "Unknown"
            },
            "network_adapters": []
        }


# Example usage if run directly
def main():
    """Command-line interface for iLO utilities"""
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
    
    parser = argparse.ArgumentParser(description='HPE iLO Hardware Inventory Tool')
    parser.add_argument('ilo_ip', help='iLO IP address')
    parser.add_argument('username', help='iLO username')
    parser.add_argument('password', help='iLO password')
    parser.add_argument('action', nargs='?', default='get_comprehensive_hardware_inventory_with_fallback',
                        help='Action to perform', 
                        choices=['get_all_details', 'get_comprehensive_hardware_inventory',
                                'get_comprehensive_hardware_inventory_enhanced',
                                'get_comprehensive_hardware_inventory_with_fallback',
                                'get_bios_information', 'get_processor_information',
                                'get_memory_information', 'get_storage_information',
                                'get_network_adapter_details', 'get_power_thermal_information',
                                'get_smartarray_information', 'get_hba_information',
                                'get_usb_information', 'get_power_supply_information',
                                'get_fan_information', 'get_enhanced_ilo_information'])
    parser.add_argument('--use-ribcl', action='store_true', help='Use RIBCL instead of Redfish')
    parser.add_argument('--redfish', action='store_true', help='Use Redfish API (default)')
    parser.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificates')
    
    args = parser.parse_args()
    
    try:
        # Determine whether to use Redfish or RIBCL
        use_redfish = not args.use_ribcl  # Default to Redfish unless --use-ribcl is specified
        
        # Initialize iLO client
        ilo_client = IloProUtils(args.ilo_ip, args.username, args.password, 
                                use_redfish, args.verify_ssl)
        
        # Execute the requested action
        if args.action == 'get_all_details':
            result = ilo_client.get_all_details()
        elif args.action == 'get_comprehensive_hardware_inventory':
            result = ilo_client.get_comprehensive_hardware_inventory()
        elif args.action == 'get_comprehensive_hardware_inventory_enhanced':
            result = ilo_client.get_comprehensive_hardware_inventory_enhanced()
        elif args.action == 'get_comprehensive_hardware_inventory_with_fallback':
            result = ilo_client.get_comprehensive_hardware_inventory_with_fallback()
        elif args.action == 'get_bios_information':
            result = ilo_client.get_bios_information()
        elif args.action == 'get_processor_information':
            result = ilo_client.get_processor_information()
        elif args.action == 'get_memory_information':
            result = ilo_client.get_memory_information()
        elif args.action == 'get_storage_information':
            result = ilo_client.get_storage_information()
        elif args.action == 'get_network_adapter_details':
            result = ilo_client.get_network_adapter_details()
        elif args.action == 'get_power_thermal_information':
            result = ilo_client.get_power_thermal_information()
        elif args.action == 'get_smartarray_information':
            result = ilo_client.get_smartarray_information()
        elif args.action == 'get_hba_information':
            result = ilo_client.get_hba_information()
        elif args.action == 'get_usb_information':
            result = ilo_client.get_usb_information()
        elif args.action == 'get_power_supply_information':
            result = ilo_client.get_power_supply_information()
        elif args.action == 'get_fan_information':
            result = ilo_client.get_fan_information()
        elif args.action == 'get_enhanced_ilo_information':
            result = ilo_client.get_enhanced_ilo_information()
        elif args.action == 'get_power_thermal_information':
            result = ilo_client.get_power_thermal_information()
        else:
            result = {"error": f"Unknown action: {args.action}"}
        
        # Output JSON result
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        error_result = {
            "error": str(e),
            "action": args.action,
            "ilo_ip": args.ilo_ip,
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(error_result, indent=2, default=str))
        sys.exit(1)


if __name__ == "__main__":
    main()
