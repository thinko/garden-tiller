#!/usr/bin/env python3
"""
Process iLO collection results into structured format for reporting.
"""

import json
import sys
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
            # Extract server details
            host_result['server_details'] = {
                'product_name': parsed_data.get('product_name', 'Unknown'),
                'host_uuid': parsed_data.get('host_uuid', 'Unknown'),
                'power_status': parsed_data.get('power_status', 'Unknown'),
                'firmware_version': parsed_data.get('firmware_version', 'Unknown')
            }
            
            # Extract health status
            health_data = parsed_data.get('health_status', {})
            host_result['health_status'] = {
                'system_health': health_data.get('system_health', 'Unknown'),
                'processor': health_data.get('processor', 'Not Available'),
                'memory': health_data.get('memory', 'Not Available'),
                'storage': health_data.get('storage', 'Not Available')
            }
            
            # Extract boot settings
            boot_data = parsed_data.get('boot_settings', {})
            host_result['boot_settings'] = {
                'one_time_boot': boot_data.get('one_time_boot', 'Unknown'),
                'persistent_boot': boot_data.get('persistent_boot', 'Unknown')
            }
            
            # Extract network adapters
            network_adapters = parsed_data.get('network_adapters', [])
            host_result['network_adapters'] = network_adapters
            host_result['network_summary'] = {
                'adapter_count': len(network_adapters),
                'adapters_with_mac': len([a for a in network_adapters if 'mac_address' in a])
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
    """Main function for command line usage."""
    if len(sys.argv) != 3:
        print("Usage: process_ilo_results.py <results_json> <hostvars_json>")
        sys.exit(1)
    
    try:
        results_data = json.loads(sys.argv[1])
        hostvars_data = json.loads(sys.argv[2])
        
        processed = process_ilo_results(results_data, hostvars_data)
        print(json.dumps(processed, indent=2))
        
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
