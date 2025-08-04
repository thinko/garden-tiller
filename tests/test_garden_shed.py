#!/usr/bin/env python3
import json
import sys
import os
import traceback

# Add the parent directory to Python path to resolve garden_shed import from submodule
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'external', 'garden-shed'))

from garden_shed import GardenShed
import requests # For handling potential request exceptions

def main():
    servers = [
        "10.9.1.51",
#        "10.9.1.52",
#        "10.9.1.53",
    ]
    username = "Administrator"
    password = "password1"

    for server_ip in servers:
        print(f"\n--- Attempting to gather details from server: {server_ip} ---")
        try:
            shed = GardenShed(
                host=server_ip,
                username=username,
                password=password,
                verify_ssl=False,  # SSL validation turned off as requested
                timeout=30 # Optional: pass a specific timeout
            )
            system_info = shed.get_system_info()
            print(json.dumps(system_info, indent=2))
            print(f"--- Successfully gathered details from {server_ip} ---")

        except requests.exceptions.ConnectionError as e:
            print(f"Error connecting to {server_ip}:")
            print(f"  Request: {e.request}")
            print(f"  Response: {e.response}")
            print(f"  Error: {e}")
            print("  Traceback:")
            traceback.print_exc()

        except requests.exceptions.HTTPError as e:
            print(f"HTTP error for {server_ip}: {e}")
            if e.response is not None:
                print(f"Response content: {e.response.text}")
        except Exception as e:
            print(f"An unexpected error occurred for server {server_ip}: {e}")
            traceback.print_exc()
        print("-" * 60)

if __name__ == "__main__":
    main()