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

usage() {
  echo "Usage: $0 [all|dns_check <hostname>|ntp_check|internet_check]"
  exit 1
}

check_dns_resolution() {
  local hostname=$1
  local ip_address

  if command -v getent &> /dev/null; then
    ip_address=$(getent hosts "$hostname" | awk '{print $1}')
  elif command -v nslookup &> /dev/null; then
    # Extract IP address, handling potential multiple Address lines from nslookup
    ip_address=$(nslookup "$hostname" | awk '/^Address: / {print $2}' | head -n 1)
  else
    echo "FAILURE: Neither getent nor nslookup is available."
    return 1
  fi

  if [ -n "$ip_address" ]; then
    echo "SUCCESS: $hostname resolved to $ip_address"
  else
    echo "FAILURE: $hostname could not be resolved."
  fi
}

check_ntp_synchronization() {
  # Check with timedatectl
  if command -v timedatectl &> /dev/null; then
    if timedatectl status | grep -q "System clock synchronized: yes" && \
       timedatectl status | grep -q "NTP service: active"; then
      echo "SUCCESS: NTP synchronized. (Source: timedatectl)"
      return 0
    fi
  fi

  # Check with ntpstat
  if command -v ntpstat &> /dev/null; then
    if ntpstat &> /dev/null; then # ntpstat exits 0 if synchronized
      echo "SUCCESS: NTP synchronized. (Source: ntpstat)"
      return 0
    fi
  fi

  # Check with chronyc
  if command -v chronyc &> /dev/null; then
    if chronyc sources | grep -q "^\^\*"; then
      local sync_source
      sync_source=$(chronyc sources | grep "^\^\*" | awk '{print $2}')
      echo "SUCCESS: NTP synchronized. Source: $sync_source (chronyc)"
      return 0
    fi
  fi

  echo "FAILURE: NTP not synchronized or status undetermined."
  return 1
}

check_internet_access() {
  local target_url="https://www.google.com"
  # Using -s for silent, -S to show error, -L to follow redirects, 
  # --max-time for timeout, -I to fetch headers only (faster), and -o /dev/null to discard body
  if command -v curl &> /dev/null; then
    if curl -sSL --max-time 10 -I "$target_url" -o /dev/null; then
      echo "SUCCESS: Internet access confirmed via $target_url"
      return 0
    else
      echo "FAILURE: Could not connect to $target_url. Check internet connectivity and proxy settings."
      return 1
    fi
  else
    echo "FAILURE: curl command not found. Cannot check internet access."
    return 1
  fi
}

main() {
  if [ $# -eq 0 ] || [ "$1" = "all" ]; then
    echo "Running all checks..."
    check_dns_resolution "google.com"
    check_ntp_synchronization
    check_internet_access
  elif [ "$1" = "dns_check" ]; then
    if [ -z "$2" ]; then
      echo "Error: Missing hostname for dns_check."
      usage
    fi
    check_dns_resolution "$2"
  elif [ "$1" = "ntp_check" ]; then
    check_ntp_synchronization
  elif [ "$1" = "internet_check" ]; then
    check_internet_access
  else
    echo "Error: Unknown command '$1'."
    usage
  fi
}

# Call main with all script arguments
main "$@"
