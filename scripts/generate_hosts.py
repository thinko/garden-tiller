#!/usr/bin/env python3
"""
Script to generate a hosts.yaml file for Garden-Tiller based on BMC credentials and IP addresses/IP range.
"""

import argparse
import ipaddress
import yaml


def generate_hosts_file(output_file, bmc_username, bmc_password, ip_range):
    """Generate a hosts.yaml file based on the provided inputs."""
    inventory = {
        "baremetal": {
            "hosts": {}
        },
        "all": {
            "vars": {
                "ansible_user": "root",
                "ansible_ssh_private_key_file": "~/.ssh/id_rsa",
                "validate_firmware": True,
                "validate_network": True,
                "validate_services": True,
                "proxy_url": "http://proxy.example.com:3128",
                "no_proxy": "localhost,127.0.0.1,192.168.1.0/24",
                "ntp_servers": [
                    "0.rhel.pool.ntp.org",
                    "1.rhel.pool.ntp.org"
                ],
                "dns_servers": [
                    "8.8.8.8",
                    "1.1.1.1"
                ],
                "expected_mtu": 9000,
                "expected_bond_mode": "802.3ad",
                "report_output": "html"
            }
        }
    }

    # Parse the IP range and add hosts
    try:
        for ip in ipaddress.IPv4Network(ip_range, strict=False):
            host_key = f"node-{ip.exploded.replace('.', '-')}"
            inventory["baremetal"]["hosts"][host_key] = {
                "ansible_host": ip.exploded,
                "bmc_address": ip.exploded,  # Assuming BMC is on the same IP for simplicity
                "bmc_username": bmc_username,
                "bmc_password": bmc_password,
                "bmc_type": "idrac",  # Default to idrac; can be customized later
                "mac_addresses": [
                    {"interface": "eno1", "expected_mac": "00:00:00:00:00:00"},
                    {"interface": "eno2", "expected_mac": "00:00:00:00:00:00"}
                ],
                "raid": {
                    "controller": "Unknown",
                    "configuration": "RAID1"
                }
            }
    except ValueError as e:
        print(f"Error parsing IP range: {e}")
        return

    # Write to the output file
    with open(output_file, "w") as f:
        yaml.dump(inventory, f, default_flow_style=False)

    print(f"Hosts file generated: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate a hosts.yaml file for Garden-Tiller.")
    parser.add_argument("--output", "-o", default="hosts.yaml", help="Output file name (default: hosts.yaml)")
    parser.add_argument("--bmc-username", "-u", required=True, help="BMC/ILO/iDRAC username")
    parser.add_argument("--bmc-password", "-p", required=True, help="BMC/ILO/iDRAC password")
    parser.add_argument("--ip-range", "-r", required=True, help="IP range or CIDR block (e.g., 192.168.1.0/24)")

    args = parser.parse_args()

    generate_hosts_file(args.output, args.bmc_username, args.bmc_password, args.ip_range)


if __name__ == "__main__":
    main()
