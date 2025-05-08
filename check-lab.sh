#!/bin/bash
# This script starts ansible playbooks to check if the lab environment is set up correctly.
# Baremetal Validations:
#  1. Validate the provided OOBM IPs/ranges and credentials
#  2. IPMI (Redfish API) is accessible, get hardware info, serial numbers, power/OS status, etc.
#  3. Update firmware of ILO/iDRAC/BMC, BIOS, NICs, RAID Controller, etc.
#  4. MAC address validation for each interface
#  5. Switch/Network validation -- either through Switch CLI/API, or alternately a 'manual' (automated) validation of the network config from the lab hosts
#    a. Bonding/LACP/VPC
#    b. Access/Trunking/VLANs/Tagging
#    c. Port/Link Errors
#    d. MTU
#    e. Routing - gateway access, route validation
#  6. RAID validation (may be extend to disk prep/formatting), get disk serial numbers
#  7. DNS enumeration/validation
#  8. DHCP/BOOTP
#  9. NTP/PTP/Time Sync
# 10. Internet/proxy access

#  Reporting/Topology:
#  1. Health report and diagram of the lab environment topology
#  2. Identification and remediation steps for any issues found

