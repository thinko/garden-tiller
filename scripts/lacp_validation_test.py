#!/usr/bin/env python3
"""
Garden-Tiller: LACP Network Validation Test Script
Tests all permutations of network interface bonding configurations
to validate LACP/802.3ad negotiation with switches in clean boot scenarios.

Uses Structlog for logging and PyBreaker for fault tolerance as per coding standards.
"""

import json
import subprocess
import time
import itertools
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import structlog
from pybreaker import CircuitBreaker

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Circuit breaker for resilient operations
network_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    exclude=[KeyboardInterrupt]
)

class BondMode(Enum):
    """Network bonding modes for testing"""
    BALANCE_RR = "0"           # Round-robin
    ACTIVE_BACKUP = "1"        # Active-backup
    BALANCE_XOR = "2"          # XOR
    BROADCAST = "3"            # Broadcast
    LACP_802_3AD = "4"         # 802.3ad (LACP)
    BALANCE_TLB = "5"          # Adaptive transmit load balancing
    BALANCE_ALB = "6"          # Adaptive load balancing

class LacpRate(Enum):
    """LACP packet transmission rates"""
    SLOW = "slow"    # 30 seconds
    FAST = "fast"    # 1 second

class MiiMon(Enum):
    """MII monitoring frequencies"""
    DISABLED = "0"
    NORMAL = "100"     # 100ms
    FREQUENT = "50"    # 50ms

@dataclass
class NetworkInterface:
    """Represents a network interface"""
    name: str
    mac_address: str
    driver: str
    speed: str
    duplex: str
    link_detected: bool
    pci_slot: str

@dataclass
class BondConfiguration:
    """Represents a bonding configuration"""
    bond_name: str
    mode: BondMode
    interfaces: List[str]
    lacp_rate: LacpRate
    miimon: MiiMon
    primary: Optional[str] = None
    xmit_hash_policy: str = "layer2"

@dataclass
class TestResult:
    """Represents the result of a bonding test"""
    config: BondConfiguration
    success: bool
    negotiation_time: float
    lacp_partner_detected: bool
    aggregator_id: Optional[str]
    active_slave_count: int
    error_message: Optional[str]
    switch_negotiation_logs: List[str]

class LacpValidator:
    """Main class for LACP validation testing"""
    
    def __init__(self, inventory_file: str = "inventories/hosts.yaml"):
        self.inventory_file = inventory_file
        self.results: List[TestResult] = []
        self.original_network_config = {}
        self.test_interfaces: List[NetworkInterface] = []
        
    @network_breaker
    def discover_network_interfaces(self) -> List[NetworkInterface]:
        """Discover available network interfaces on the system"""
        logger.info("Discovering network interfaces")
        
        try:
            # Get interface list
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            
            interfaces = []
            for line in result.stdout.split('\n'):
                if ': ' in line and not line.strip().startswith(' '):
                    parts = line.split(': ')
                    if len(parts) >= 2:
                        iface_name = parts[1].split('@')[0]
                        
                        # Skip loopback, virtual, and management interfaces
                        if (iface_name.startswith(('lo', 'docker', 'br-', 'virbr', 'veth')) or
                            'bond' in iface_name or 'team' in iface_name):
                            continue
                            
                        # Get detailed interface information
                        iface_info = self._get_interface_details(iface_name)
                        if iface_info:
                            interfaces.append(iface_info)
            
            logger.info("Discovered network interfaces", count=len(interfaces))
            return interfaces
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to discover network interfaces", error=str(e))
            raise

    def _get_interface_details(self, interface: str) -> Optional[NetworkInterface]:
        """Get detailed information about a specific interface"""
        try:
            # Get MAC address
            mac_result = subprocess.run(
                ["cat", f"/sys/class/net/{interface}/address"],
                capture_output=True,
                text=True,
                check=True
            )
            mac_address = mac_result.stdout.strip()
            
            # Get driver information
            driver_result = subprocess.run(
                ["ethtool", "-i", interface],
                capture_output=True,
                text=True
            )
            driver = "unknown"
            if driver_result.returncode == 0:
                for line in driver_result.stdout.split('\n'):
                    if line.startswith('driver:'):
                        driver = line.split(':')[1].strip()
                        break
            
            # Get link information
            link_result = subprocess.run(
                ["ethtool", interface],
                capture_output=True,
                text=True
            )
            
            speed = "unknown"
            duplex = "unknown"
            link_detected = False
            
            if link_result.returncode == 0:
                for line in link_result.stdout.split('\n'):
                    if 'Speed:' in line:
                        speed = line.split(':')[1].strip()
                    elif 'Duplex:' in line:
                        duplex = line.split(':')[1].strip()
                    elif 'Link detected:' in line:
                        link_detected = 'yes' in line.lower()
            
            # Get PCI slot information
            pci_slot = "unknown"
            try:
                pci_result = subprocess.run(
                    ["ethtool", "-i", interface],
                    capture_output=True,
                    text=True
                )
                if pci_result.returncode == 0:
                    for line in pci_result.stdout.split('\n'):
                        if line.startswith('bus-info:'):
                            pci_slot = line.split(':')[1].strip()
                            break
            except:
                pass
            
            return NetworkInterface(
                name=interface,
                mac_address=mac_address,
                driver=driver,
                speed=speed,
                duplex=duplex,
                link_detected=link_detected,
                pci_slot=pci_slot
            )
            
        except subprocess.CalledProcessError:
            logger.warning("Failed to get details for interface", interface=interface)
            return None

    def generate_bond_configurations(self) -> List[BondConfiguration]:
        """Generate all permutations of bonding configurations to test"""
        logger.info("Generating bond configurations")
        
        # Filter interfaces that have link detected
        active_interfaces = [iface for iface in self.test_interfaces if iface.link_detected]
        
        if len(active_interfaces) < 2:
            logger.error("Need at least 2 active interfaces for bonding tests")
            return []
        
        configurations = []
        
        # Test different interface combinations (2, 3, 4+ interfaces)
        for combo_size in range(2, min(len(active_interfaces) + 1, 5)):
            for iface_combo in itertools.combinations(active_interfaces, combo_size):
                interface_names = [iface.name for iface in iface_combo]
                
                # Test different bonding modes
                for mode in BondMode:
                    # Test different LACP rates (only relevant for 802.3ad)
                    lacp_rates = [LacpRate.SLOW, LacpRate.FAST] if mode == BondMode.LACP_802_3AD else [LacpRate.SLOW]
                    
                    for lacp_rate in lacp_rates:
                        # Test different MII monitoring settings
                        for miimon in MiiMon:
                            bond_name = f"bond-test-{len(configurations)}"
                            
                            config = BondConfiguration(
                                bond_name=bond_name,
                                mode=mode,
                                interfaces=interface_names,
                                lacp_rate=lacp_rate,
                                miimon=miimon,
                                primary=interface_names[0] if mode == BondMode.ACTIVE_BACKUP else None
                            )
                            configurations.append(config)
        
        logger.info("Generated bond configurations", count=len(configurations))
        return configurations

    @network_breaker
    def backup_network_configuration(self):
        """Backup current network configuration"""
        logger.info("Backing up network configuration")
        
        try:
            # Save current interface configurations
            result = subprocess.run(
                ["ip", "addr", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            self.original_network_config['ip_addr'] = result.stdout
            
            # Save routing table
            result = subprocess.run(
                ["ip", "route", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            self.original_network_config['ip_route'] = result.stdout
            
            logger.info("Network configuration backed up successfully")
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to backup network configuration", error=str(e))
            raise

    @network_breaker
    def create_bond_interface(self, config: BondConfiguration) -> bool:
        """Create a bonding interface with the specified configuration"""
        logger.info("Creating bond interface", config=config.bond_name, mode=config.mode.value)
        
        try:
            # Load bonding module if not already loaded
            subprocess.run(["modprobe", "bonding"], check=False)
            
            # Create bond interface
            subprocess.run([
                "ip", "link", "add", config.bond_name, "type", "bond"
            ], check=True)
            
            # Configure bonding mode
            with open(f"/sys/class/net/{config.bond_name}/bonding/mode", "w") as f:
                f.write(config.mode.value)
            
            # Configure MII monitoring
            with open(f"/sys/class/net/{config.bond_name}/bonding/miimon", "w") as f:
                f.write(config.miimon.value)
            
            # Configure LACP rate for 802.3ad mode
            if config.mode == BondMode.LACP_802_3AD:
                with open(f"/sys/class/net/{config.bond_name}/bonding/lacp_rate", "w") as f:
                    f.write(config.lacp_rate.value)
                
                # Configure transmit hash policy
                with open(f"/sys/class/net/{config.bond_name}/bonding/xmit_hash_policy", "w") as f:
                    f.write(config.xmit_hash_policy)
            
            # Set primary slave for active-backup mode
            if config.primary:
                with open(f"/sys/class/net/{config.bond_name}/bonding/primary", "w") as f:
                    f.write(config.primary)
            
            # Bring up the bond interface
            subprocess.run(["ip", "link", "set", config.bond_name, "up"], check=True)
            
            # Add slave interfaces
            for interface in config.interfaces:
                # Bring down the interface first
                subprocess.run(["ip", "link", "set", interface, "down"], check=True)
                
                # Add to bond
                with open(f"/sys/class/net/{config.bond_name}/bonding/slaves", "w") as f:
                    f.write(f"+{interface}")
                
                # Bring up the interface
                subprocess.run(["ip", "link", "set", interface, "up"], check=True)
            
            logger.info("Bond interface created successfully", bond=config.bond_name)
            return True
            
        except Exception as e:
            logger.error("Failed to create bond interface", bond=config.bond_name, error=str(e))
            return False

    @network_breaker
    def test_lacp_negotiation(self, config: BondConfiguration) -> TestResult:
        """Test LACP negotiation for a specific configuration"""
        logger.info("Testing LACP negotiation", config=config.bond_name)
        
        start_time = time.time()
        
        try:
            # Create the bond interface
            if not self.create_bond_interface(config):
                return TestResult(
                    config=config,
                    success=False,
                    negotiation_time=0.0,
                    lacp_partner_detected=False,
                    aggregator_id=None,
                    active_slave_count=0,
                    error_message="Failed to create bond interface",
                    switch_negotiation_logs=[]
                )
            
            # Wait for negotiation (up to 60 seconds)
            negotiation_timeout = 60
            negotiation_success = False
            lacp_partner_detected = False
            aggregator_id = None
            active_slave_count = 0
            
            for attempt in range(negotiation_timeout):
                time.sleep(1)
                
                # Check bond status
                try:
                    with open(f"/proc/net/bonding/{config.bond_name}", "r") as f:
                        bond_status = f.read()
                    
                    # Parse bond status for LACP information
                    if config.mode == BondMode.LACP_802_3AD:
                        if "Aggregator ID:" in bond_status:
                            aggregator_id = self._extract_aggregator_id(bond_status)
                        
                        if "Partner System:" in bond_status and "00:00:00:00:00:00" not in bond_status:
                            lacp_partner_detected = True
                        
                        # Count active slaves
                        active_slave_count = bond_status.count("MII Status: up")
                        
                        # Check if all interfaces are up and negotiated
                        if (active_slave_count == len(config.interfaces) and 
                            lacp_partner_detected and aggregator_id):
                            negotiation_success = True
                            break
                    else:
                        # For non-LACP modes, just check if interfaces are up
                        active_slave_count = bond_status.count("MII Status: up")
                        if active_slave_count == len(config.interfaces):
                            negotiation_success = True
                            break
                            
                except Exception as e:
                    logger.warning("Error reading bond status", error=str(e))
            
            negotiation_time = time.time() - start_time
            
            # Get switch negotiation logs if available
            switch_logs = self._get_switch_negotiation_logs(config)
            
            result = TestResult(
                config=config,
                success=negotiation_success,
                negotiation_time=negotiation_time,
                lacp_partner_detected=lacp_partner_detected,
                aggregator_id=aggregator_id,
                active_slave_count=active_slave_count,
                error_message=None if negotiation_success else "Negotiation timeout or partial failure",
                switch_negotiation_logs=switch_logs
            )
            
            logger.info("LACP negotiation test completed", 
                       bond=config.bond_name, 
                       success=negotiation_success,
                       time=negotiation_time)
            
            return result
            
        except Exception as e:
            error_msg = f"Test failed with exception: {str(e)}"
            logger.error("LACP negotiation test failed", bond=config.bond_name, error=error_msg)
            
            return TestResult(
                config=config,
                success=False,
                negotiation_time=time.time() - start_time,
                lacp_partner_detected=False,
                aggregator_id=None,
                active_slave_count=0,
                error_message=error_msg,
                switch_negotiation_logs=[]
            )
        
        finally:
            # Clean up the bond interface
            self.cleanup_bond_interface(config.bond_name)

    def _extract_aggregator_id(self, bond_status: str) -> Optional[str]:
        """Extract aggregator ID from bond status"""
        for line in bond_status.split('\n'):
            if "Aggregator ID:" in line:
                return line.split(':')[1].strip()
        return None

    def _get_switch_negotiation_logs(self, config: BondConfiguration) -> List[str]:
        """Attempt to get switch-side negotiation logs"""
        # This is a placeholder - in a real implementation, you would
        # connect to the switch via SSH/SNMP to get LACP negotiation logs
        logs = []
        
        # Example placeholder logs
        logs.append(f"Switch port negotiation started for bond {config.bond_name}")
        logs.append(f"LACP PDUs received from {config.interfaces}")
        
        return logs

    @network_breaker
    def cleanup_bond_interface(self, bond_name: str):
        """Clean up a bond interface"""
        logger.info("Cleaning up bond interface", bond=bond_name)
        
        try:
            # Remove bond interface if it exists
            result = subprocess.run(
                ["ip", "link", "show", bond_name],
                capture_output=True,
                stderr=subprocess.DEVNULL
            )
            
            if result.returncode == 0:
                # Bring down the bond
                subprocess.run(["ip", "link", "set", bond_name, "down"], check=False)
                
                # Remove the bond
                subprocess.run(["ip", "link", "delete", bond_name], check=False)
            
        except Exception as e:
            logger.warning("Error during bond cleanup", bond=bond_name, error=str(e))

    def restore_network_configuration(self):
        """Restore original network configuration"""
        logger.info("Restoring network configuration")
        
        try:
            # Clean up any remaining test bonds
            result = subprocess.run(
                ["ip", "link", "show", "type", "bond"],
                capture_output=True,
                text=True
            )
            
            for line in result.stdout.split('\n'):
                if 'bond-test-' in line:
                    bond_name = line.split(':')[1].strip().split('@')[0]
                    self.cleanup_bond_interface(bond_name)
            
            # Restore interface states
            for interface in self.test_interfaces:
                subprocess.run(["ip", "link", "set", interface.name, "up"], check=False)
            
            logger.info("Network configuration restored")
            
        except Exception as e:
            logger.error("Failed to restore network configuration", error=str(e))

    def run_validation_tests(self) -> Dict[str, Any]:
        """Run all LACP validation tests"""
        logger.info("Starting LACP validation tests")
        
        try:
            # Discover network interfaces
            self.test_interfaces = self.discover_network_interfaces()
            
            if len(self.test_interfaces) < 2:
                logger.error("Insufficient network interfaces for testing")
                return {"error": "Need at least 2 network interfaces"}
            
            # Backup current configuration
            self.backup_network_configuration()
            
            # Generate test configurations
            configurations = self.generate_bond_configurations()
            
            if not configurations:
                logger.error("No valid configurations generated")
                return {"error": "No valid bond configurations could be generated"}
            
            # Run tests
            total_tests = len(configurations)
            logger.info("Running validation tests", total=total_tests)
            
            for i, config in enumerate(configurations):
                logger.info("Running test", current=i+1, total=total_tests, config=config.bond_name)
                
                try:
                    result = self.test_lacp_negotiation(config)
                    self.results.append(result)
                    
                    # Brief pause between tests
                    time.sleep(2)
                    
                except KeyboardInterrupt:
                    logger.info("Tests interrupted by user")
                    break
                except Exception as e:
                    logger.error("Test failed", config=config.bond_name, error=str(e))
                    
                    # Add failed result
                    self.results.append(TestResult(
                        config=config,
                        success=False,
                        negotiation_time=0.0,
                        lacp_partner_detected=False,
                        aggregator_id=None,
                        active_slave_count=0,
                        error_message=str(e),
                        switch_negotiation_logs=[]
                    ))
            
            # Generate summary
            summary = self.generate_test_summary()
            
            logger.info("LACP validation tests completed", 
                       total=len(self.results),
                       successful=summary['successful_tests'],
                       failed=summary['failed_tests'])
            
            return summary
            
        except Exception as e:
            logger.error("Validation tests failed", error=str(e))
            return {"error": str(e)}
        
        finally:
            # Always restore network configuration
            self.restore_network_configuration()

    def generate_test_summary(self) -> Dict[str, Any]:
        """Generate a comprehensive test summary"""
        successful_tests = [r for r in self.results if r.success]
        failed_tests = [r for r in self.results if not r.success]
        
        # Group results by configuration parameters
        by_mode = {}
        by_interface_count = {}
        by_lacp_rate = {}
        
        for result in self.results:
            mode = result.config.mode.name
            if mode not in by_mode:
                by_mode[mode] = {'success': 0, 'failed': 0}
            by_mode[mode]['success' if result.success else 'failed'] += 1
            
            iface_count = len(result.config.interfaces)
            if iface_count not in by_interface_count:
                by_interface_count[iface_count] = {'success': 0, 'failed': 0}
            by_interface_count[iface_count]['success' if result.success else 'failed'] += 1
            
            if result.config.mode == BondMode.LACP_802_3AD:
                rate = result.config.lacp_rate.name
                if rate not in by_lacp_rate:
                    by_lacp_rate[rate] = {'success': 0, 'failed': 0}
                by_lacp_rate[rate]['success' if result.success else 'failed'] += 1
        
        summary = {
            'test_summary': {
                'total_tests': len(self.results),
                'successful_tests': len(successful_tests),
                'failed_tests': len(failed_tests),
                'success_rate': len(successful_tests) / len(self.results) * 100 if self.results else 0
            },
            'results_by_mode': by_mode,
            'results_by_interface_count': by_interface_count,
            'results_by_lacp_rate': by_lacp_rate,
            'successful_configurations': [
                {
                    'bond_name': r.config.bond_name,
                    'mode': r.config.mode.name,
                    'interfaces': r.config.interfaces,
                    'negotiation_time': r.negotiation_time,
                    'lacp_partner_detected': r.lacp_partner_detected,
                    'aggregator_id': r.aggregator_id,
                    'active_slave_count': r.active_slave_count
                }
                for r in successful_tests
            ],
            'failed_configurations': [
                {
                    'bond_name': r.config.bond_name,
                    'mode': r.config.mode.name,
                    'interfaces': r.config.interfaces,
                    'error_message': r.error_message
                }
                for r in failed_tests
            ],
            'network_interfaces': [asdict(iface) for iface in self.test_interfaces],
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return summary

    def save_results(self, output_file: str = "lacp_validation_results.json"):
        """Save test results to a JSON file"""
        summary = self.generate_test_summary()
        
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info("Results saved", file=output_file)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LACP Network Validation Test Script")
    parser.add_argument("--inventory", "-i", default="inventories/hosts.yaml",
                       help="Ansible inventory file")
    parser.add_argument("--output", "-o", default="lacp_validation_results.json",
                       help="Output file for results")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    # Check if running as root
    if os.geteuid() != 0:
        logger.error("This script must be run as root to modify network interfaces")
        sys.exit(1)
    
    # Run validation tests
    validator = LacpValidator(args.inventory)
    
    try:
        results = validator.run_validation_tests()
        
        if "error" in results:
            logger.error("Validation failed", error=results["error"])
            sys.exit(1)
        
        # Save results
        validator.save_results(args.output)
        
        # Print summary
        print(f"\nLACP Validation Test Summary:")
        print(f"Total tests: {results['test_summary']['total_tests']}")
        print(f"Successful: {results['test_summary']['successful_tests']}")
        print(f"Failed: {results['test_summary']['failed_tests']}")
        print(f"Success rate: {results['test_summary']['success_rate']:.1f}%")
        print(f"\nResults saved to: {args.output}")
        
    except KeyboardInterrupt:
        logger.info("Validation tests interrupted by user")
        validator.restore_network_configuration()
        sys.exit(1)
    except Exception as e:
        logger.error("Validation tests failed", error=str(e))
        validator.restore_network_configuration()
        sys.exit(1)

if __name__ == "__main__":
    main()
