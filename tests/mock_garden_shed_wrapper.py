#!/usr/bin/env python3
import json
import sys

# Mock data simulating Garden Shed output
result = {
    'collection_status': 'success',
    'timestamp': '2023-10-27T10:00:00',
    'garden_shed_data': {
        'system_info': {
            'NetworkAdapters': [
                {
                    'PhysicalPorts': [
                        {'MacAddress': 'AA:BB:CC:DD:EE:FF', 'Name': 'Port 1', 'Status': 'Up'}
                    ],
                    'Name': 'Adapter 1'
                }
            ],
            'FirmwareInventory': {
                'BiosVersion': '1.0.0',
                'SystemBMC': [{'Version': '2.0.0'}]
            },
            'Processor': {'count': 1},
            'Memory': {'TotalSystemMemoryGB': 32}
        }
    }
}
print(json.dumps(result))
