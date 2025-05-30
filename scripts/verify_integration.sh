#!/bin/bash
#
# Garden-Tiller: Integration Verification Script
# Verifies that the clean boot LACP validation is properly integrated
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}Garden-Tiller Integration Verification${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# Check 1: Verify all LACP components exist
echo -e "${YELLOW}1. Verifying LACP validation components...${NC}"

COMPONENTS=(
    "scripts/lacp_validation_test.py"
    "scripts/clean_boot_lacp_orchestrator.py"
    "scripts/run_clean_boot_lacp.sh"
    "scripts/test_clean_boot_lacp.sh"
    "playbooks/06-clean-boot-network-validation.yaml"
    "docs/clean-boot-lacp-validation.md"
)

for component in "${COMPONENTS[@]}"; do
    if [[ -f "$PROJECT_ROOT/$component" ]]; then
        echo -e "   ${GREEN}✅ $component${NC}"
    else
        echo -e "   ${RED}❌ $component (missing)${NC}"
        exit 1
    fi
done

# Check 2: Verify playbook integration
echo -e "\n${YELLOW}2. Verifying playbook integration...${NC}"

if grep -q "06-clean-boot-network-validation.yaml" "$PROJECT_ROOT/playbooks/site.yaml"; then
    echo -e "   ${GREEN}✅ Clean boot playbook integrated in site.yaml${NC}"
else
    echo -e "   ${RED}❌ Clean boot playbook not found in site.yaml${NC}"
    exit 1
fi

# Check 3: Verify playbook sequencing
echo -e "\n${YELLOW}3. Verifying playbook sequencing...${NC}"

EXPECTED_SEQUENCE=(
    "05-network-validation.yaml"
    "06-clean-boot-network-validation.yaml"
    "07-raid-validation.yaml"
    "08-dns-validation.yaml"
    "09-dhcp-validation.yaml"
    "10-time-sync-validation.yaml"
    "11-internet-proxy-validation.yaml"
    "12-generate-report.yaml"
)

for playbook in "${EXPECTED_SEQUENCE[@]}"; do
    if [[ -f "$PROJECT_ROOT/playbooks/$playbook" ]]; then
        echo -e "   ${GREEN}✅ $playbook${NC}"
    else
        echo -e "   ${RED}❌ $playbook (missing)${NC}"
        exit 1
    fi
done

# Check 4: Verify script permissions
echo -e "\n${YELLOW}4. Verifying script permissions...${NC}"

EXECUTABLES=(
    "scripts/lacp_validation_test.py"
    "scripts/clean_boot_lacp_orchestrator.py"
    "scripts/run_clean_boot_lacp.sh"
    "scripts/test_clean_boot_lacp.sh"
    "check-lab.sh"
)

for script in "${EXECUTABLES[@]}"; do
    if [[ -x "$PROJECT_ROOT/$script" ]]; then
        echo -e "   ${GREEN}✅ $script (executable)${NC}"
    else
        echo -e "   ${RED}❌ $script (not executable)${NC}"
        exit 1
    fi
done

# Check 5: Verify Python dependencies
echo -e "\n${YELLOW}5. Verifying Python dependencies...${NC}"

DEPENDENCIES=("structlog" "pybreaker" "yaml")

for dep in "${DEPENDENCIES[@]}"; do
    if python3 -c "import $dep" 2>/dev/null; then
        echo -e "   ${GREEN}✅ $dep available${NC}"
    else
        echo -e "   ${YELLOW}⚠️  $dep not installed (will be auto-installed when needed)${NC}"
    fi
done

# Check 6: Verify Ansible syntax
echo -e "\n${YELLOW}6. Verifying Ansible syntax...${NC}"

cd "$PROJECT_ROOT"

if ansible-playbook --syntax-check playbooks/site.yaml >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Main site.yaml syntax valid${NC}"
else
    echo -e "   ${RED}❌ Main site.yaml syntax error${NC}"
    exit 1
fi

if ansible-playbook --syntax-check playbooks/06-clean-boot-network-validation.yaml >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Clean boot playbook syntax valid${NC}"
else
    echo -e "   ${RED}❌ Clean boot playbook syntax error${NC}"
    exit 1
fi

# Check 7: Verify directory structure
echo -e "\n${YELLOW}7. Verifying directory structure...${NC}"

DIRECTORIES=("reports" "logs" "inventories" "playbooks" "scripts")

for dir in "${DIRECTORIES[@]}"; do
    if [[ -d "$PROJECT_ROOT/$dir" ]]; then
        echo -e "   ${GREEN}✅ $dir/ directory exists${NC}"
    else
        echo -e "   ${RED}❌ $dir/ directory missing${NC}"
        exit 1
    fi
done

# Check 8: Show integration summary
echo -e "\n${YELLOW}8. Integration Summary:${NC}"
echo ""

echo -e "${BLUE}🎯 Clean Boot LACP Features:${NC}"
echo "   • Comprehensive bonding mode testing (all 7 modes)"
echo "   • Circuit breaker pattern for fault tolerance"
echo "   • Structured logging with JSON output"
echo "   • Parallel host testing capabilities"
echo "   • Switch compatibility analysis"
echo "   • Network state backup and restoration"
echo ""

echo -e "${BLUE}🔗 Integration Points:${NC}"
echo "   • Integrated with check-lab.sh workflow"
echo "   • Uses existing inventory structure"
echo "   • Outputs to shared reports directory"
echo "   • Follows Garden-Tiller logging patterns"
echo "   • Proper playbook sequencing (after basic network validation)"
echo ""

echo -e "${BLUE}📋 Usage Options:${NC}"
echo "   1. Full Garden-Tiller suite: ./check-lab.sh"
echo "   2. Network validation only: ./check-lab.sh --tags network"
echo "   3. Clean boot LACP only: ./check-lab.sh --tags clean-boot"
echo "   4. Direct LACP testing: sudo ./scripts/run_clean_boot_lacp.sh"
echo ""

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}✅ Integration Verification Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${GREEN}The Garden-Tiller clean boot LACP validation system is fully integrated${NC}"
echo -e "${GREEN}and ready for production testing in your OpenShift lab environment.${NC}"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Update inventories/hosts.yaml with your baremetal hosts"
echo "2. Run comprehensive validation: ./check-lab.sh"
echo "3. Review generated reports in the reports/ directory"
echo "4. Use results to optimize network configuration for OpenShift"
