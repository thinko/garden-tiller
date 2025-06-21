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

## Automated Network Discovery

Garden-Tiller includes a Python-based Network Discovery Orchestrator to automate the initial phases of network reconnaissance and inventory generation. This script performs a series of passive and active scans to identify live hosts, open ports, services, operating systems, and potential Out-of-Band Management (OOBM) interfaces like Dell iDRACs and HP iLOs.

The output is a structured `inventory.json` file, which can then be automatically ingested by the main `site.yaml` playbook to populate Ansible's in-memory inventory for subsequent validation tasks.

### Features

- **Phased Discovery:** Progresses from passive listening (`tcpdump`, `tshark`) to local active probing (`arp-scan`), and finally to comprehensive network-wide scanning (`nmap`).
- **OOBM Identification:** Specifically attempts to identify Dell iDRAC and HP iLO interfaces based on Nmap scan results.
- **JSON Output:** Generates a detailed `inventory.json` file tailored for consumption by Garden-Tiller's Ansible playbooks.
- **Configurable:** Allows specification of network interface, scan durations, target subnets for list scans, and options to skip specific phases or use existing Nmap XML data.

### Usage

The script `scripts/network_discovery_orchestrator.py` can be run directly. It typically requires root privileges for some scanning operations (like `tcpdump` and `arp-scan`, and Nmap's OS detection).

**Basic execution:**

```bash
sudo python3 scripts/network_discovery_orchestrator.py --interface eth0
```

This will run the full pipeline using `eth0`, with default settings, and produce output files (including `inventory.json`) in `reports/discovery_output/`.

**Command-line Options:**

```
usage: network_discovery_orchestrator.py [-h] [--interface INTERFACE] [--output-dir OUTPUT_DIR] [--tcpdump-duration TCPDUMP_DURATION]
                                         [--skip-pcap] [--skip-arp] [--nmap-list-scan-targets NMAP_LIST_SCAN_TARGETS]
                                         [--skip-nmap-list-scan] [--skip-nmap-ping-scan]
                                         [--nmap-xml-input NMAP_XML_INPUT] [--skip-ansible-trigger] [-v]

Network Discovery Orchestrator for Garden-Tiller

options:
  -h, --help            show this help message and exit
  --interface INTERFACE, -i INTERFACE
                        Network interface for scanning (default: eth0)
  --output-dir OUTPUT_DIR, -o OUTPUT_DIR
                        Directory for output files (default: reports/discovery_output)
  --tcpdump-duration TCPDUMP_DURATION, -d TCPDUMP_DURATION
                        Duration for tcpdump capture in seconds (default: 120)
  --skip-pcap           Skip PCAP capture and analysis phase.
  --skip-arp            Skip ARP scan phase.
  --nmap-list-scan-targets NMAP_LIST_SCAN_TARGETS
                        Target subnet range for Nmap list scan (e.g., '192.168.1.0/24'). Optional.
  --skip-nmap-list-scan
                        Skip Nmap list scan phase (-sL).
  --skip-nmap-ping-scan
                        Skip Nmap ping scan phase (-sn).
  --nmap-xml-input NMAP_XML_INPUT
                        Path to an existing Nmap XML file to use instead of live scanning (for testing).
  --skip-ansible-trigger
                        Skip the final step of triggering the Ansible playbook.
  -v, --verbose         Enable verbose logging (DEBUG level).
```

**Integration with Main Playbook:**

When the orchestrator completes and generates `inventory.json`, it can automatically trigger the main `playbooks/site.yaml`. The `00-process-discovery.yaml` playbook (imported by `site.yaml`) will then load this JSON file to dynamically add discovered hosts to Ansible's inventory for the current run.

This automated discovery process is particularly useful for bootstrapping inventory in new or unknown lab environments.

## Testing BMC Connectivity

BMC connectivity can be tested using the standard playbooks:

```bash
# Test OOBM connectivity for all hosts
ansible-playbook -i inventories/hosts.yaml playbooks/01-validate-oobm.yaml
```

This validates BMC connectivity before running the full validation suite.

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
