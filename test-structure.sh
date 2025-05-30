#!/bin/bash
# Quick test script to verify basic functionality after directory structure flattening

# Print test banner
echo "====================================="
echo " Garden-Tiller Validation Test      "
echo "====================================="

# Check key files exist
echo "Checking key files..."
FILES_TO_CHECK=(
  "check-lab.sh"
  "playbooks/site.yaml"
  "scripts/report_generator.py"
  "library/resilient_command.py"
  "docker/Dockerfile"
  "scripts/templates/report_template.html"
)

for file in "${FILES_TO_CHECK[@]}"; do
  if [ -f "$file" ]; then
    echo "✓ Found $file"
  else
    echo "✗ Missing $file"
  fi
done

# Check directory structure
echo -e "\nChecking directory structure..."
DIRS_TO_CHECK=(
  "inventories"
  "playbooks"
  "roles"
  "library"
  "filter_plugins"
  "scripts"
  "docker"
  "reports"
)

for dir in "${DIRS_TO_CHECK[@]}"; do
  if [ -d "$dir" ]; then
    echo "✓ Found $dir/"
  else
    echo "✗ Missing $dir/"
  fi
done

# Try running the script with --help
echo -e "\nTesting check-lab.sh --help..."
./check-lab.sh --help

# Done
echo -e "\nTest completed. The above errors (if any) should be addressed."
