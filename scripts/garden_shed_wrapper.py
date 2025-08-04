#!/usr/bin/env python3
"""
Garden Shed Wrapper Script for Ansible Integration
Provides a clean interface between Ansible and the garden_shed library
"""

import sys
import json
import argparse
from datetime import datetime

# Add the garden-shed submodule directory to Python path
sys.path.insert(0, '/home/thinko/projects/garden-tiller/external/garden-shed')

try:
    from garden_shed import GardenShed
except ImportError as e:
    print(json.dumps({
        'collection_status': 'error',
        'error': f'Failed to import garden_shed: {str(e)}',
        'timestamp': datetime.now().isoformat(),
        'garden_shed_data': None
    }, indent=2))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Garden Shed iLO Data Collection Wrapper')
    parser.add_argument('host', help='iLO IP address or hostname')
    parser.add_argument('username', help='iLO username')
    parser.add_argument('password', help='iLO password')
    parser.add_argument('--port', type=int, default=443, help='HTTPS port (default: 443)')
    parser.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificates')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    try:
        # Create GardenShed instance
        shed = GardenShed(
            host=args.host,
            username=args.username,
            password=args.password,
            port=args.port,
            verify_ssl=args.verify_ssl,
            timeout=args.timeout
        )
        
        # Get system information
        system_info = shed.get_system_info()
        
        # Return successful result
        result = {
            'collection_status': 'success',
            'timestamp': datetime.now().isoformat(),
            'garden_shed_data': system_info
        }
        
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        # Return error result
        error_result = {
            'collection_status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
            'garden_shed_data': None
        }
        
        print(json.dumps(error_result, indent=2, default=str))
        sys.exit(1)


if __name__ == '__main__':
    main()
