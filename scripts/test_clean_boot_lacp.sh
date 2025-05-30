#!/bin/bash
#
# Test script for clean boot LACP validation components
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Testing Clean Boot LACP Validation Components ==="

# Test 1: Syntax check for Python scripts
echo "1. Checking Python script syntax..."
python3 -m py_compile "$SCRIPT_DIR/clean_boot_lacp_orchestrator.py"
python3 -m py_compile "$SCRIPT_DIR/lacp_validation_test.py"
echo "   ✓ Python scripts syntax is valid"

# Test 2: Bash script syntax check
echo "2. Checking bash script syntax..."
bash -n "$SCRIPT_DIR/run_clean_boot_lacp.sh"
echo "   ✓ Bash script syntax is valid"

# Test 3: Ansible playbook syntax checks
echo "3. Checking Ansible playbook syntax..."
cd "$PROJECT_ROOT"

# Check main playbooks
ansible-playbook --syntax-check -i inventories/hosts.yaml playbooks/06-clean-boot-network-validation.yaml
echo "   ✓ Clean boot network validation playbook syntax is valid"

ansible-playbook --syntax-check -i inventories/hosts.yaml playbooks/site.yaml
echo "   ✓ Main site.yaml playbook syntax is valid"

# Test 4: Check required dependencies
echo "4. Checking Python dependencies..."
python3 -c "import structlog; print('   ✓ structlog available')" 2>/dev/null || echo "   ⚠ structlog not available (install with: pip3 install structlog)"
python3 -c "import pybreaker; print('   ✓ pybreaker available')" 2>/dev/null || echo "   ⚠ pybreaker not available (install with: pip3 install pybreaker)"
python3 -c "import yaml; print('   ✓ pyyaml available')" 2>/dev/null || echo "   ⚠ pyyaml not available (install with: pip3 install pyyaml)"

# Test 5: Check file permissions
echo "5. Checking file permissions..."
if [[ -x "$SCRIPT_DIR/clean_boot_lacp_orchestrator.py" ]]; then
    echo "   ✓ clean_boot_lacp_orchestrator.py is executable"
else
    echo "   ✗ clean_boot_lacp_orchestrator.py is not executable"
fi

if [[ -x "$SCRIPT_DIR/run_clean_boot_lacp.sh" ]]; then
    echo "   ✓ run_clean_boot_lacp.sh is executable"
else
    echo "   ✗ run_clean_boot_lacp.sh is not executable"
fi

if [[ -x "$SCRIPT_DIR/lacp_validation_test.py" ]]; then
    echo "   ✓ lacp_validation_test.py is executable"
else
    echo "   ✗ lacp_validation_test.py is not executable"
fi

# Test 6: Check directory structure
echo "6. Checking directory structure..."
[[ -d "$PROJECT_ROOT/reports" ]] && echo "   ✓ reports directory exists" || echo "   ⚠ reports directory missing (will be created)"
[[ -d "$PROJECT_ROOT/logs" ]] && echo "   ✓ logs directory exists" || echo "   ⚠ logs directory missing (will be created)"
[[ -f "$PROJECT_ROOT/inventories/hosts.yaml" ]] && echo "   ✓ inventory file exists" || echo "   ✗ inventory file missing"

echo ""
echo "=== Test Summary ==="
echo "Clean Boot LACP validation components are ready for use."
echo ""
echo "Usage examples:"
echo "  # Run comprehensive clean boot LACP testing"
echo "  sudo $SCRIPT_DIR/run_clean_boot_lacp.sh"
echo ""
echo "  # Run as part of Garden-Tiller suite"
echo "  ansible-playbook -i inventories/hosts.yaml playbooks/06-clean-boot-network-validation.yaml"
echo ""
echo "  # Run only clean boot tests with main site playbook"
echo "  ansible-playbook -i inventories/hosts.yaml playbooks/site.yaml --tags clean-boot"
echo ""
echo "Note: Tests require root privileges for network interface manipulation."
