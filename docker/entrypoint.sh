#!/bin/bash
# Garden-Tiller container entrypoint script

set -e

# Create logs directory
mkdir -p /app/logs

# Print banner
echo "====================================="
echo " Garden-Tiller Lab Validation Suite "
echo "====================================="
echo "Running in container mode"
echo "Current date: $(date)"

# If a custom command is provided, run it
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    # Default: Run the main playbook
    exec ansible-playbook playbooks/site.yaml
fi
