# Garden-Tiller

A highly portable and comprehensive lab validation suite for OpenShift deployments. This toolkit verifies that remote lab environments meet all prerequisites for successful OpenShift cluster deployments.

## Overview

Garden-Tiller uses Ansible, Python, and Shell scripts to validate:
- Bare metal hardware configuration
- Network connectivity and configuration
- Storage subsystems
- Required infrastructure services (DNS, DHCP, NTP)
- Internet/proxy access

## Features

- **Comprehensive Validations**: Covers all aspects of infrastructure required for OpenShift
- **Portable**: Designed to run on RHEL 8/9 with minimal dependencies
- **Containerized**: Can run in Podman containers for development or OpenShift for production
- **Resilient**: Uses PyBreaker library for circuit breaking and fault handling
- **Detailed Reporting**: Generates HTML reports with diagrams showing lab topology
- **Remediation**: Suggests fixes for identified issues
- **Vendor Specific Tools**: Enhanced functionality for Dell iDRAC and other vendor BMCs

## Prerequisites

- RHEL 8 or RHEL 9 (or compatible Linux distribution)
- Ansible Core 2.12 or higher
- Python 3.9 or higher
- Standard Linux utilities
- Podman (optional, for containerized execution)

## Quick Start

1. Clone this repository:
   ```bash
   git clone https://github.com/thinko/garden-tiller.git
   cd garden-tiller
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create your inventory file or modify the sample:
   ```bash
   cp -r inventories/sample inventories/my-lab
   # Edit inventories/my-lab/hosts.yaml with your lab details
   ```

4. Run the validation suite:
   ```bash
   ./check-lab.sh --inventory inventories/my-lab/hosts.yaml
   ```

## Usage

```bash
./check-lab.sh [OPTIONS]

Options:
  -i, --inventory INVENTORY  Specify the inventory file to use
  -t, --tags TAGS           Run only specific validation tags (comma separated)
  -s, --skip-tags TAGS      Skip specific validation tags (comma separated)
  -v, --verbose             Increase verbosity
  -p, --podman              Run validations in a Podman container
  -c, --check               Run in check mode (dry run)
  -h, --help                Show this help message

Available validation tags:
  oobm, ipmi, dell, idrac, hpe, ilo, firmware, mac, network, raid, dns, dhcp, timesync, internet, all

Example:
  ./check-lab.sh --inventory ./inventories/my-lab/hosts.yaml --tags network,dns,dhcp
```

## Dell iDRAC Integration

Garden-Tiller includes specialized support for Dell servers equipped with iDRAC management controllers, providing enhanced validation capabilities:

### Dell iDRAC Features

- **Advanced Hardware Inspection**: Deep hardware validation using Dell's Redfish API
- **Firmware Compliance**: Validation of firmware versions against requirements
- **Network Configuration**: Verification of NIC bonding, VLAN configurations, and link states
- **iDRAC Settings**: Validation of NTP, DNS, and other critical iDRAC settings
- **Service Tag Collection**: Automated collection of Dell service tags and warranty information

### Using Dell iDRAC Features

To leverage these capabilities, specify the BMC type as `idrac` in your inventory:

```yaml
all:
  hosts:
    dell-server-01:
      bmc_address: 192.168.1.101
      bmc_username: root
      bmc_password: calvin
      bmc_type: idrac   # Enables Dell-specific functionality
```

Run Dell-specific validations with:

```bash
./check-lab.sh --inventory inventories/my-lab/hosts.yaml --tags dell,idrac
```

## HPE iLO Integration

Garden-Tiller provides specialized support for HPE ProLiant servers equipped with Integrated Lights-Out (iLO) management controllers:

### HPE iLO Features

- **Comprehensive Hardware Inspection**: Deep hardware validation using proliantutils
- **Firmware Compliance**: Validation of firmware versions against minimum requirements
- **Power Management**: Verification of server power status and configuration
- **Health Status**: Monitoring of server health and component status
- **Boot Configuration**: Validation of boot settings for proper PXE or disk booting

### Using HPE iLO Features

To leverage these capabilities, specify the BMC type as `ilo` in your inventory:

```yaml
all:
  hosts:
    hpe-server-01:
      bmc_address: 192.168.1.102
      bmc_username: Administrator
      bmc_password: password
      bmc_type: ilo   # Enables HPE-specific functionality
      min_ilo_firmware: "2.61"  # Optional: specify minimum firmware version
```

Run HPE-specific validations with:

```bash
./check-lab.sh --inventory inventories/my-lab/hosts.yaml --tags hpe,ilo
```

## Testing BMC Connectivity

You can use the included test script to verify connectivity to Dell iDRAC or HPE iLO directly:

```bash
# Test Dell iDRAC connection
./scripts/test_bmc_utils.py --type idrac --ip 192.168.10.101 --username root --password calvin

# Test HPE iLO connection
./scripts/test_bmc_utils.py --type ilo --ip 192.168.10.102 --username Administrator --password password
```

This can help debug connectivity issues before running the full validation suite.

## Containerized Execution

To build and run the containerized version:

```bash
# Build the container
podman build -t garden-tiller:latest -f docker/Dockerfile .

# Run validations in container
./check-lab.sh --inventory inventories/my-lab/hosts.yaml --podman
```

## Directory Structure

```
.
├── check-lab.sh                # Main entry script
├── inventories/                # Ansible inventories
│   └── sample/                 # Sample inventory structure
├── playbooks/                  # Ansible playbooks for each validation
├── roles/                      # Ansible roles
├── library/                    # Custom Ansible modules
├── filter_plugins/             # Custom Ansible filters
├── scripts/                    # Utility scripts
├── docker/                     # Containerization files
└── reports/                    # Generated reports (HTML/PDF)
```

## License

BSD 3-Clause License. See `LICENSE` for details.
