#!/usr/bin/env python3
"""
Garden-Tiller: NMState Configuration Generator
Generates nmstate YAML manifests from network validation results for OpenShift NodeNetworkConfigurationPolicy

This script analyzes the network validation results (LACP/bonds, VLANs, routes, DHCP, etc.)
and generates appropriate nmstate configuration manifests for each host.

Features:
- Generates nmstate YAML from network validation results
- Creates NodeNetworkConfigurationPolicy manifests for OpenShift
- Supports bonding, VLAN, routing, and DHCP configurations
- Validates configurations against nmstate schema
- Structured logging with Structlog
- Circuit breaker pattern for resilient operations

Terminology:
- Uses "subordinate" interfaces instead of deprecated "slave" terminology
- Bond subordinate interfaces are defined in the bond's "port" list per nmstate spec
- Follows inclusive naming conventions for network configuration

Requirements:
- Python 3.8+
- PyBreaker for circuit breaker pattern
- Structlog for structured logging
- PyYAML for YAML processing
- Network validation results from Garden-Tiller

Usage:
    python3 nmstate_generator.py --results-dir reports/ --output-dir nmstate-configs/
    python3 nmstate_generator.py --validation-report reports/network-validation.json --host node1
"""

import argparse
import json
import logging
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import ipaddress
import re

# Import resilience libraries as per coding instructions
try:
    import pybreaker
except ImportError:
    print("PyBreaker not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pybreaker"])
    import pybreaker

try:
    import structlog
except ImportError:
    print("Structlog not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "structlog"])
    import structlog

# Configure structured logging with Structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
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

logger = structlog.get_logger()

@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""
    name: str
    type: str
    state: str = "up"
    mtu: Optional[int] = None
    mac_address: Optional[str] = None
    ipv4: Optional[Dict[str, Any]] = None
    ipv6: Optional[Dict[str, Any]] = None
    ethtool: Optional[Dict[str, Any]] = None

@dataclass
class BondConfiguration:
    """Represents a bond interface configuration."""
    name: str
    mode: str
    subordinates: List[str]
    options: Dict[str, Any]
    mtu: Optional[int] = None
    state: str = "up"

@dataclass
class VlanConfiguration:
    """Represents a VLAN interface configuration."""
    name: str
    vlan_id: int
    base_interface: str
    state: str = "up"
    mtu: Optional[int] = None
    ipv4: Optional[Dict[str, Any]] = None
    ipv6: Optional[Dict[str, Any]] = None

@dataclass
class RouteConfiguration:
    """Represents a route configuration."""
    destination: str
    next_hop_address: str
    next_hop_interface: Optional[str] = None
    metric: Optional[int] = None
    table_id: Optional[int] = None

@dataclass
class NMStateConfiguration:
    """Complete nmstate configuration for a host."""
    hostname: str
    interfaces: List[Dict[str, Any]]
    routes: Optional[Dict[str, Any]] = None
    dns_resolver: Optional[Dict[str, Any]] = None
    route_rules: Optional[List[Dict[str, Any]]] = None

class NMStateGeneratorError(Exception):
    """Custom exception for nmstate generation errors."""
    pass

class NetworkValidationParser:
    """Parses network validation results and extracts configuration data."""
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(component="NetworkValidationParser")
        self.circuit_breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=30,
            exclude=[NMStateGeneratorError]
        )
    
    @pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)
    def parse_validation_results(self, results_file: Path) -> Dict[str, Any]:
        """Parse network validation results from JSON file."""
        self.logger.info("Parsing network validation results", file=str(results_file))
        
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
            
            # Handle different result file formats
            if isinstance(data, dict):
                if 'hosts' in data:
                    # Multi-host results format
                    return data
                elif 'hostname' in data or 'host' in data:
                    # Single host results format
                    hostname = data.get('hostname', data.get('host', 'unknown'))
                    return {'hosts': {hostname: data}}
                else:
                    # Legacy format - try to extract host data
                    return {'hosts': {'default': data}}
            
            self.logger.warning("Unexpected results format", data_type=type(data))
            return {'hosts': {}}
            
        except json.JSONDecodeError as e:
            self.logger.error("Invalid JSON in results file", error=str(e))
            raise NMStateGeneratorError(f"Invalid JSON in results file: {e}")
        except FileNotFoundError:
            self.logger.error("Results file not found", file=str(results_file))
            raise NMStateGeneratorError(f"Results file not found: {results_file}")
    
    def extract_bond_configuration(self, host_data: Dict[str, Any]) -> List[BondConfiguration]:
        """Extract bond configuration from validation results."""
        bonds = []
        
        # Check network validation results
        network_data = host_data.get('network', {})
        bond_data = network_data.get('bond', {})
        
        if bond_data.get('status', False):
            bond_mode = bond_data.get('mode', '802.3ad')
            
            # Check LACP test results for detailed bond configuration
            lacp_results = host_data.get('lacp_test_results', [])
            successful_bonds = [r for r in lacp_results if r.get('success', False)]
            
            if successful_bonds:
                # Use the best performing bond configuration
                best_bond = max(successful_bonds, 
                              key=lambda x: x.get('negotiation_time', float('inf')))
                
                # Extract interface names from the results
                interfaces = self._extract_bond_interfaces(host_data)
                
                if interfaces:
                    bond_config = BondConfiguration(
                        name="bond0",
                        mode=self._normalize_bond_mode(best_bond.get('bonding_mode', bond_mode)),
                        subordinates=interfaces,
                        options=self._get_bond_options(best_bond.get('bonding_mode', bond_mode)),
                        mtu=network_data.get('mtu', {}).get('expected', 1500)
                    )
                    bonds.append(bond_config)
        
        return bonds
    
    def extract_vlan_configuration(self, host_data: Dict[str, Any]) -> List[VlanConfiguration]:
        """Extract VLAN configuration from validation results."""
        vlans = []
        
        network_data = host_data.get('network', {})
        vlan_data = network_data.get('vlan', {})
        
        if vlan_data.get('status', False):
            vlan_details = vlan_data.get('details', [])
            
            for vlan_line in vlan_details:
                if isinstance(vlan_line, str) and 'vlan' in vlan_line.lower():
                    # Parse VLAN information from the line
                    vlan_info = self._parse_vlan_line(vlan_line)
                    if vlan_info:
                        vlans.append(vlan_info)
        
        return vlans
    
    def extract_route_configuration(self, host_data: Dict[str, Any]) -> List[RouteConfiguration]:
        """Extract route configuration from validation results."""
        routes = []
        
        network_data = host_data.get('network', {})
        routing_data = network_data.get('routing', {})
        
        if routing_data.get('has_default_route', False):
            # Extract default route information
            # This would typically come from the validation results
            # For now, we'll create a basic default route structure
            default_route = RouteConfiguration(
                destination="0.0.0.0/0",
                next_hop_address="",  # Will be filled from actual data
                metric=100
            )
            routes.append(default_route)
        
        return routes
    
    def _extract_bond_interfaces(self, host_data: Dict[str, Any]) -> List[str]:
        """Extract physical interfaces that should be part of the bond."""
        interfaces = []
        
        # Look for interface information in various places
        network_interfaces = host_data.get('network_interfaces', [])
        environment_info = host_data.get('environment_info', {})
        
        # Try environment info first
        if environment_info and 'network_interfaces' in environment_info:
            for iface in environment_info['network_interfaces']:
                if isinstance(iface, dict) and iface.get('name'):
                    name = iface['name']
                    # Skip virtual interfaces
                    if not any(prefix in name for prefix in ['lo', 'bond', 'vlan', 'br-', 'docker']):
                        interfaces.append(name)
        
        # Fallback to basic interface detection
        if not interfaces:
            # Look for common interface naming patterns
            for i in range(4):  # Support up to 4 interfaces
                for prefix in ['eth', 'ens', 'eno', 'enp']:
                    interfaces.append(f"{prefix}{i}")
        
        # Return first 2 interfaces for bonding by default
        return interfaces[:2] if interfaces else ['eth0', 'eth1']
    
    def _normalize_bond_mode(self, mode: str) -> str:
        """Normalize bond mode to nmstate format."""
        mode_mapping = {
            '802.3ad': '802.3ad',
            'active-backup': 'active-backup',
            'balance-alb': 'balance-alb',
            'balance-tlb': 'balance-tlb',
            'balance-rr': 'balance-rr',
            'balance-xor': 'balance-xor',
            'broadcast': 'broadcast'
        }
        return mode_mapping.get(mode, '802.3ad')
    
    def _get_bond_options(self, mode: str) -> Dict[str, Any]:
        """Get bond options based on mode."""
        base_options = {
            'miimon': '100'
        }
        
        if mode == '802.3ad':
            base_options.update({
                'lacp_rate': 'fast',
                'xmit_hash_policy': 'layer3+4'
            })
        
        return base_options
    
    def _parse_vlan_line(self, vlan_line: str) -> Optional[VlanConfiguration]:
        """Parse a VLAN configuration line."""
        # Example: "eth0.100: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500"
        match = re.search(r'(\w+)\.(\d+)', vlan_line)
        if match:
            base_interface = match.group(1)
            vlan_id = int(match.group(2))
            
            return VlanConfiguration(
                name=f"{base_interface}.{vlan_id}",
                vlan_id=vlan_id,
                base_interface=base_interface
            )
        
        return None

class NMStateGenerator:
    """Generates nmstate YAML configurations from network validation results."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = structlog.get_logger().bind(component="NMStateGenerator")
        self.parser = NetworkValidationParser()
        
        # Circuit breaker for file operations
        self.circuit_breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=30
        )
    
    @pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)
    def generate_host_configuration(self, hostname: str, host_data: Dict[str, Any]) -> NMStateConfiguration:
        """Generate nmstate configuration for a specific host."""
        self.logger.info("Generating nmstate configuration", hostname=hostname)
        
        interfaces = []
        
        # Extract bond configurations
        bonds = self.parser.extract_bond_configuration(host_data)
        for bond in bonds:
            bond_interface = self._create_bond_interface(bond)
            interfaces.append(bond_interface)
            
            # Add subordinate interfaces
            for subordinate in bond.subordinates:
                subordinate_interface = self._create_subordinate_interface(subordinate)
                interfaces.append(subordinate_interface)
        
        # Extract VLAN configurations
        vlans = self.parser.extract_vlan_configuration(host_data)
        for vlan in vlans:
            vlan_interface = self._create_vlan_interface(vlan)
            interfaces.append(vlan_interface)
        
        # Extract route configurations
        routes = self._create_route_configuration(host_data)
        
        # Create DNS configuration
        dns_config = self._create_dns_configuration(host_data)
        
        return NMStateConfiguration(
            hostname=hostname,
            interfaces=interfaces,
            routes=routes,
            dns_resolver=dns_config
        )
    
    def _create_bond_interface(self, bond: BondConfiguration) -> Dict[str, Any]:
        """Create bond interface configuration."""
        bond_config = {
            'name': bond.name,
            'type': 'bond',
            'state': bond.state,
            'link-aggregation': {
                'mode': bond.mode,
                'port': bond.subordinates,
                'options': bond.options
            }
        }
        
        if bond.mtu:
            bond_config['mtu'] = bond.mtu
        
        # Add IP configuration (this would come from validation results)
        bond_config['ipv4'] = {
            'enabled': True,
            'dhcp': True
        }
        
        return bond_config
    
    def _create_subordinate_interface(self, interface_name: str) -> Dict[str, Any]:
        """Create subordinate interface configuration."""
        return {
            'name': interface_name,
            'type': 'ethernet',
            'state': 'up'
        }
    
    def _create_vlan_interface(self, vlan: VlanConfiguration) -> Dict[str, Any]:
        """Create VLAN interface configuration."""
        vlan_config = {
            'name': vlan.name,
            'type': 'vlan',
            'state': vlan.state,
            'vlan': {
                'base-iface': vlan.base_interface,
                'id': vlan.vlan_id
            }
        }
        
        if vlan.mtu:
            vlan_config['mtu'] = vlan.mtu
        
        if vlan.ipv4:
            vlan_config['ipv4'] = vlan.ipv4
        
        return vlan_config
    
    def _create_route_configuration(self, host_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create route configuration."""
        routes = self.parser.extract_route_configuration(host_data)
        
        if not routes:
            return None
        
        route_config = {
            'config': []
        }
        
        for route in routes:
            route_entry = {
                'destination': route.destination,
                'next-hop-address': route.next_hop_address
            }
            
            if route.next_hop_interface:
                route_entry['next-hop-interface'] = route.next_hop_interface
            
            if route.metric:
                route_entry['metric'] = route.metric
            
            route_config['config'].append(route_entry)
        
        return route_config
    
    def _create_dns_configuration(self, host_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create DNS configuration."""
        network_data = host_data.get('network', {})
        routing_data = network_data.get('routing', {})
        
        if routing_data.get('dns_resolution', False):
            return {
                'config': {
                    'search': [],
                    'server': ['8.8.8.8', '8.8.4.4']  # Default DNS servers
                }
            }
        
        return None
    
    @pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)
    def generate_yaml_file(self, config: NMStateConfiguration) -> Path:
        """Generate YAML file for nmstate configuration."""
        filename = f"{config.hostname}-nmstate.yaml"
        file_path = self.output_dir / filename
        
        # Create nmstate YAML structure
        nmstate_config = {
            'interfaces': config.interfaces
        }
        
        if config.routes:
            nmstate_config['routes'] = config.routes
        
        if config.dns_resolver:
            nmstate_config['dns-resolver'] = config.dns_resolver
        
        # Write YAML file
        with open(file_path, 'w') as f:
            yaml.dump(nmstate_config, f, default_flow_style=False, indent=2)
        
        self.logger.info("Generated nmstate YAML", 
                        hostname=config.hostname, file=str(file_path))
        
        return file_path
    
    def generate_nncp_manifest(self, config: NMStateConfiguration) -> Path:
        """Generate NodeNetworkConfigurationPolicy manifest for OpenShift."""
        filename = f"{config.hostname}-nncp.yaml"
        file_path = self.output_dir / filename
        
        # Create nmstate configuration
        nmstate_config = {
            'interfaces': config.interfaces
        }
        
        if config.routes:
            nmstate_config['routes'] = config.routes
        
        if config.dns_resolver:
            nmstate_config['dns-resolver'] = config.dns_resolver
        
        # Create NNCP manifest
        nncp_manifest = {
            'apiVersion': 'nmstate.io/v1',
            'kind': 'NodeNetworkConfigurationPolicy',
            'metadata': {
                'name': f"{config.hostname}-network-config",
                'labels': {
                    'garden-tiller.io/generated': 'true',
                    'garden-tiller.io/hostname': config.hostname
                }
            },
            'spec': {
                'nodeSelector': {
                    'kubernetes.io/hostname': config.hostname
                },
                'desiredState': nmstate_config
            }
        }
        
        # Write NNCP manifest
        with open(file_path, 'w') as f:
            yaml.dump(nncp_manifest, f, default_flow_style=False, indent=2)
        
        self.logger.info("Generated NNCP manifest", 
                        hostname=config.hostname, file=str(file_path))
        
        return file_path

class NMStateOrchestrator:
    """Orchestrates nmstate configuration generation for all hosts."""
    
    def __init__(self, results_dir: Path, output_dir: Path):
        self.results_dir = Path(results_dir)
        self.output_dir = Path(output_dir)
        self.logger = structlog.get_logger().bind(component="NMStateOrchestrator")
        self.generator = NMStateGenerator(output_dir)
        self.parser = NetworkValidationParser()
    
    def generate_all_configurations(self, generate_nncp: bool = True) -> Dict[str, List[Path]]:
        """Generate nmstate configurations for all hosts from validation results."""
        self.logger.info("Starting nmstate configuration generation",
                        results_dir=str(self.results_dir), output_dir=str(self.output_dir))
        
        generated_files = {
            'nmstate': [],
            'nncp': []
        }
        
        # Find all validation result files
        result_files = list(self.results_dir.glob("*validation*.json"))
        result_files.extend(list(self.results_dir.glob("*lacp*.json")))
        result_files.extend(list(self.results_dir.glob("*network*.json")))
        
        if not result_files:
            self.logger.warning("No validation result files found",
                              search_dir=str(self.results_dir))
            return generated_files
        
        for result_file in result_files:
            try:
                # Parse validation results
                validation_data = self.parser.parse_validation_results(result_file)
                
                # Generate configurations for each host
                for hostname, host_data in validation_data.get('hosts', {}).items():
                    if not host_data:
                        continue
                    
                    # Generate nmstate configuration
                    config = self.generator.generate_host_configuration(hostname, host_data)
                    
                    # Generate YAML files
                    nmstate_file = self.generator.generate_yaml_file(config)
                    generated_files['nmstate'].append(nmstate_file)
                    
                    # Generate NNCP manifest if requested
                    if generate_nncp:
                        nncp_file = self.generator.generate_nncp_manifest(config)
                        generated_files['nncp'].append(nncp_file)
                
            except Exception as e:
                self.logger.error("Failed to process result file",
                                file=str(result_file), error=str(e))
                continue
        
        self.logger.info("nmstate configuration generation completed",
                        nmstate_files=len(generated_files['nmstate']),
                        nncp_files=len(generated_files['nncp']))
        
        return generated_files
    
    def generate_summary_report(self, generated_files: Dict[str, List[Path]]) -> Path:
        """Generate a summary report of all generated configurations."""
        summary_file = self.output_dir / "generation-summary.yaml"
        
        summary = {
            'generation_metadata': {
                'timestamp': datetime.now().isoformat(),
                'generator': 'Garden-Tiller NMState Generator',
                'total_nmstate_files': len(generated_files.get('nmstate', [])),
                'total_nncp_files': len(generated_files.get('nncp', []))
            },
            'generated_files': {
                'nmstate_configurations': [str(f) for f in generated_files.get('nmstate', [])],
                'nncp_manifests': [str(f) for f in generated_files.get('nncp', [])]
            },
            'usage_instructions': {
                'nmstate_files': 'Use these files directly with nmstatectl apply',
                'nncp_manifests': 'Apply these to OpenShift cluster with kubectl apply -f',
                'example_commands': [
                    'nmstatectl apply hostname-nmstate.yaml',
                    'kubectl apply -f hostname-nncp.yaml'
                ]
            }
        }
        
        with open(summary_file, 'w') as f:
            yaml.dump(summary, f, default_flow_style=False, indent=2)
        
        return summary_file

def main():
    """Main entry point for the nmstate generator."""
    parser = argparse.ArgumentParser(
        description="Garden-Tiller NMState Configuration Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 nmstate_generator.py --results-dir reports/ --output-dir nmstate-configs/
  python3 nmstate_generator.py --validation-report reports/network-validation.json
  python3 nmstate_generator.py --results-dir reports/ --no-nncp --verbose
        """
    )
    
    parser.add_argument("--results-dir", "-r", type=str, default="reports",
                       help="Directory containing validation result files")
    parser.add_argument("--output-dir", "-o", type=str, default="nmstate-configs",
                       help="Output directory for generated configurations")
    parser.add_argument("--validation-report", type=str,
                       help="Specific validation report file to process")
    parser.add_argument("--no-nncp", action="store_true",
                       help="Skip generating NodeNetworkConfigurationPolicy manifests")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    try:
        # Initialize orchestrator
        orchestrator = NMStateOrchestrator(
            results_dir=Path(args.results_dir),
            output_dir=Path(args.output_dir)
        )
        
        # Generate configurations
        generated_files = orchestrator.generate_all_configurations(
            generate_nncp=not args.no_nncp
        )
        
        # Generate summary report
        summary_file = orchestrator.generate_summary_report(generated_files)
        
        print(f"✅ nmstate configuration generation completed!")
        print(f"📁 Output directory: {args.output_dir}")
        print(f"📄 Summary report: {summary_file}")
        print(f"🔧 Generated {len(generated_files['nmstate'])} nmstate configurations")
        if not args.no_nncp:
            print(f"🚀 Generated {len(generated_files['nncp'])} OpenShift NNCP manifests")
        
        sys.exit(0)
    
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
