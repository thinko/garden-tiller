#!/usr/bin/env python3
"""
Process iLO collection results into structured format for reporting.
"""

import json
import sys
import argparse
from datetime import datetime, timezone


def process_ilo_results(results_data, hostvars_data):
    """Process raw iLO collection results into structured format."""
    processed_results = {}
    
    for result in results_data:
        hostname = result.get('item', 'unknown')
        stdout = result.get('stdout', '')
        stderr = result.get('stderr', '')
        rc = result.get('rc', -1)
        failed = result.get('failed', False)
        
        # Parse JSON output
        connection_success = False
        parsed_data = {}
        
        if stdout:
            try:
                parsed_data = json.loads(stdout)
                connection_success = 'error' not in parsed_data
            except json.JSONDecodeError:
                parsed_data = {'error': 'json_parse_failed', 'raw_stdout': stdout[:200]}
        else:
            parsed_data = {'error': 'no_stdout', 'stderr': stderr[:200]}
        
        # Extract host variables
        host_vars = hostvars_data.get(hostname, {})
        
        # Build structured result
        host_result = {
            'connection_status': 'success' if connection_success else 'failed',
            'raw_data': parsed_data,
            'server_details': {},
            'health_status': {},
            'boot_settings': {},
            'network_adapters': [],
            'network_summary': {'adapter_count': 0, 'adapters_with_mac': 0},
            'collection_timestamp': datetime.now(timezone.utc).isoformat(),
            'bmc_address': host_vars.get('bmc_address', 'Unknown'),
            'bmc_type': host_vars.get('bmc_type', 'ilo'),
            'hostname': hostname,
            'error_details': {}
        }
        
        if connection_success:
            # Extract server details - handle new comprehensive format
            server_info = parsed_data.get('server_info', {})
            hardware_summary = parsed_data.get('hardware_summary', {})
            
            host_result['server_details'] = {
                'product_name': server_info.get('model', parsed_data.get('product_name', 'Unknown')),
                'host_uuid': parsed_data.get('host_uuid', 'Unknown'),
                'power_status': parsed_data.get('power_status', 'Unknown'),
                'firmware_version': parsed_data.get('firmware_version', 'Unknown'),
                'manufacturer': server_info.get('manufacturer', 'Unknown'),
                'serial_number': server_info.get('serial_number', 'Unknown')
            }
            
            # Extract health status - handle new format
            health_data = parsed_data.get('health_status', {})
            host_result['health_status'] = {
                'system_health': health_data.get('system_health', 'Unknown'),
                'processor': health_data.get('processor', 'Not Available'),
                'memory': health_data.get('memory', 'Not Available'),
                'storage': health_data.get('storage', 'Not Available')
            }
            
            # Extract boot settings - handle new format
            boot_data = parsed_data.get('boot_settings', {})
            host_result['boot_settings'] = {
                'one_time_boot': boot_data.get('one_time_boot', 'Unknown'),
                'persistent_boot': boot_data.get('persistent_boot', 'Unknown')
            }
            
            # Extract network adapters - handle both old and new formats
            network_adapters = []
            if 'network_adapters' in parsed_data:
                # New comprehensive format
                if isinstance(parsed_data['network_adapters'], dict):
                    network_adapters = parsed_data['network_adapters'].get('adapters', [])
                else:
                    # Legacy format - direct list
                    network_adapters = parsed_data['network_adapters']
            
            host_result['network_adapters'] = network_adapters
            host_result['network_summary'] = {
                'adapter_count': len(network_adapters),
                'adapters_with_mac': len([a for a in network_adapters if a.get('mac_address') and a.get('mac_address') != 'Unknown'])
            }
        else:
            # Fill with failure values
            host_result['server_details'] = {
                'product_name': 'Connection Failed',
                'host_uuid': 'Connection Failed',
                'power_status': 'Connection Failed',
                'firmware_version': 'Connection Failed'
            }
            
            host_result['health_status'] = {
                'system_health': 'Connection Failed',
                'processor': 'Connection Failed',
                'memory': 'Connection Failed',
                'storage': 'Connection Failed'
            }
            
            host_result['boot_settings'] = {
                'one_time_boot': 'Connection Failed',
                'persistent_boot': 'Connection Failed'
            }
            
            host_result['error_details'] = {
                'message': stderr or 'Unknown error',
                'exit_code': rc,
                'stdout_preview': stdout[:200] if stdout else '',
                'stderr_preview': stderr[:200] if stderr else '',
                'parsed_error': parsed_data.get('error', '') if isinstance(parsed_data, dict) else ''
            }
        
        processed_results[hostname] = host_result
    
    return processed_results


def main():
    """Main entry point - supports both command line and file input."""
    parser = argparse.ArgumentParser(description='Process iLO collection results')
    parser.add_argument('--ilo-results-file', help='Path to JSON file containing iLO results')
    parser.add_argument('--hostvars-file', help='Path to JSON file containing hostvars')
    parser.add_argument('ilo_results_json', nargs='?', help='JSON string of iLO results (legacy)')
    parser.add_argument('hostvars_json', nargs='?', help='JSON string of hostvars (legacy)')
    
    args = parser.parse_args()
    
    try:
        # Determine input method - file-based or command-line
        if args.ilo_results_file and args.hostvars_file:
            # File-based input (preferred)
            with open(args.ilo_results_file, 'r') as f:
                results_data = json.load(f)
            with open(args.hostvars_file, 'r') as f:
                hostvars_data = json.load(f)
        elif args.ilo_results_json and args.hostvars_json:
            # Legacy command-line input
            results_data = json.loads(args.ilo_results_json)
            hostvars_data = json.loads(args.hostvars_json)
        elif len(sys.argv) >= 3 and not sys.argv[1].startswith('--'):
            # Legacy positional arguments support
            results_data = json.loads(sys.argv[1])
            hostvars_data = json.loads(sys.argv[2])
        else:
            parser.print_help()
            sys.exit(1)
        
        processed = process_ilo_results(results_data, hostvars_data)
        print(json.dumps(processed, indent=2))
        
    except FileNotFoundError as e:
        error_result = {
            'error': 'file_not_found',
            'message': f'Could not read input file: {str(e)}',
            'results': {}
        }
        print(json.dumps(error_result))
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_result = {
            'error': 'json_parse_failed',
            'message': f'Failed to parse JSON input: {str(e)}',
            'results': {}
        }
        print(json.dumps(error_result))
        sys.exit(1)
    except Exception as e:
        error_result = {
            'error': 'processing_failed',
            'message': str(e),
            'results': {}
        }
        print(json.dumps(error_result))
        sys.exit(1)


if __name__ == '__main__':
    main()
