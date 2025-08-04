#!/bin/bash
# Garden-Tiller: OpenShift Lab Environment Validation Suite
# This script orchestrates ansible playbooks to verify if a lab environment is ready for OpenShift deployment
#
# Baremetal Validations:
#  1. Validate the provided OOBM IPs/ranges and credentials
#  2. IPMI (Redfish API) is accessible, get hardware info, device inventory, serial numbers, power/OS status, current boot settings, etc.
#  3. Document and prepare to update the firmware of ILO/iDRAC/BMC, BIOS, NICs, RAID Controller, etc.
#  4. MAC address discovery/interface inventory
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
#
#  Reporting/Topology:
#  1. Health report and diagram of the lab environment topology
#  2. Identification and remediation steps for any issues found

# Initialize logging with Structlog
LOG_DIR="./logs"
LOG_FILE="${LOG_DIR}/check-lab-$(date +%Y%m%d-%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Color definitions for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -i, --inventory INVENTORY  Specify the inventory file to use"
    echo "  -t, --tags TAGS           Run only specific validation tags (comma separated)"
    echo "  -s, --skip-tags TAGS      Skip specific validation tags (comma separated)"
    echo "  -v, --verbose             Increase verbosity"
    echo "  -p, --podman              Run validations in a Podman container"
    echo "  -c, --check               Run in check mode (dry run)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Available validation tags:"
    echo "  oobm, ipmi, firmware, mac, network, raid, dns, dhcp, timesync, internet, all"
    echo ""
    echo "Example:"
    echo "  $0 --inventory ./inventories/my-lab/hosts.yaml --tags network,dns,dhcp"
    exit 1
}

# Default values
INVENTORY="./inventories/sample/hosts.sample.yaml"
TAGS="all"
SKIP_TAGS=""
VERBOSE=0
USE_PODMAN=0
CHECK_MODE=0

# Process command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -i|--inventory)
            INVENTORY="$2"
            shift 2
            ;;
        -t|--tags)
            TAGS="$2"
            shift 2
            ;;
        -s|--skip-tags)
            SKIP_TAGS="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -p|--podman)
            USE_PODMAN=1
            shift
            ;;
        -c|--check)
            CHECK_MODE=1
            shift
            ;;
        -h|--help)
            show_usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            show_usage
            ;;
    esac
done

# Check if inventory file exists
if [ ! -f "$INVENTORY" ]; then
    echo -e "${RED}Error: Inventory file '$INVENTORY' not found${NC}"
    exit 1
fi

# Display banner
echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}     Garden-Tiller Lab Validation Suite         ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "${GREEN}Starting validation with inventory: ${INVENTORY}${NC}"
echo -e "${GREEN}Log file: ${LOG_FILE}${NC}"
echo ""

# Set up ansible command with proper options
ANSIBLE_CMD="ansible-playbook"
ANSIBLE_OPTS="-i ${INVENTORY}"

if [ $VERBOSE -eq 1 ]; then
    ANSIBLE_OPTS="${ANSIBLE_OPTS} -v"
fi

if [ $CHECK_MODE -eq 1 ]; then
    ANSIBLE_OPTS="${ANSIBLE_OPTS} --check"
    echo -e "${YELLOW}Running in check mode (dry run)${NC}"
fi

if [ -n "$TAGS" ] && [ "$TAGS" != "all" ]; then
    ANSIBLE_OPTS="${ANSIBLE_OPTS} --tags ${TAGS}"
    echo -e "${GREEN}Running only tags: ${TAGS}${NC}"
fi

if [ -n "$SKIP_TAGS" ]; then
    ANSIBLE_OPTS="${ANSIBLE_OPTS} --skip-tags ${SKIP_TAGS}"
    echo -e "${YELLOW}Skipping tags: ${SKIP_TAGS}${NC}"
fi

# Run the validations
if [ $USE_PODMAN -eq 1 ]; then
    echo -e "${BLUE}Running validations in Podman container...${NC}"
    podman run --rm -it \
        -v "$(pwd):/app:Z" \
        -v "${INVENTORY}:/app/inventory:Z" \
        --network host \
        localhost/garden-tiller:latest \
        ${ANSIBLE_OPTS} playbooks/site.yaml 2>&1 | tee -a "${LOG_FILE}"
    # Get exit code from podman (first command in pipeline)
    EXIT_CODE=${PIPESTATUS[0]}
else
    echo -e "${BLUE}Running validations...${NC}"
    ${ANSIBLE_CMD} ${ANSIBLE_OPTS} playbooks/site.yaml 2>&1 | tee -a "${LOG_FILE}"
    # Get exit code from ansible-playbook (first command in pipeline)  
    EXIT_CODE=${PIPESTATUS[0]}
fi

# Check exit status and look for actual report files
REPORT_DIR="./reports"


if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Validation completed successfully!${NC}"
    
    # Find the most recent report file
    if [ -d "$REPORT_DIR" ]; then
        LATEST_REPORT=$(find "$REPORT_DIR" -name "lab-report-*.html" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
        if [ -n "$LATEST_REPORT" ] && [ -f "$LATEST_REPORT" ]; then
            echo -e "${GREEN}Check the report at ${LATEST_REPORT}${NC}"
        else
            echo -e "${YELLOW}No report file found in ${REPORT_DIR}. This may indicate an issue with report generation.${NC}"
        fi
    else
        echo -e "${YELLOW}Reports directory not found. Report generation may have failed.${NC}"
    fi
else
    echo -e "${RED}Validation failed with exit code ${EXIT_CODE}${NC}"
    echo -e "${RED}Please check the log file for details: ${LOG_FILE}${NC}"
    
    # Check if partial results were generated
    if [ -d "$REPORT_DIR" ]; then
        LATEST_REPORT=$(find "$REPORT_DIR" -name "lab-report-*.html" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
        if [ -n "$LATEST_REPORT" ] && [ -f "$LATEST_REPORT" ]; then
            echo -e "${YELLOW}A partial report may be available at ${LATEST_REPORT}${NC}"
        fi
    fi
fi

exit $EXIT_CODE

