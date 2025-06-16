#!/bin/bash
#
# Garden-Tiller IPMI Command Wrapper
# Executes ipmitool commands while filtering benign stderr messages
#

# Function to filter stderr output
filter_stderr() {
    local stderr_content="$1"
    # Remove the benign cipher suite error
    echo "$stderr_content" | grep -v "Unable to Get Channel Cipher Suites" | grep -v "Get Channel Cipher Suites command failed"
}

# Function to execute ipmitool command with filtered stderr
execute_ipmi_command() {
    local bmc_address="$1"
    local username="$2"
    local password="$3"
    local command="$4"
    local fallback_msg="${5:-COMMAND_FAILED}"
    
    # Execute the command and capture stdout and stderr separately
    local temp_stdout=$(mktemp)
    local temp_stderr=$(mktemp)
    
    # Run the ipmitool command
    ipmitool -I lanplus -H "$bmc_address" -U "$username" -P "$password" $command \
        1>"$temp_stdout" 2>"$temp_stderr"
    local exit_code=$?
    
    # Read the outputs
    local stdout_content=$(<"$temp_stdout")
    local stderr_content=$(<"$temp_stderr")
    
    # Clean up temp files
    rm -f "$temp_stdout" "$temp_stderr"
    
    # Filter the stderr
    local filtered_stderr
    filtered_stderr=$(filter_stderr "$stderr_content")
    
    # Output stdout (this is what Ansible will capture)
    if [ $exit_code -eq 0 ] && [ -n "$stdout_content" ]; then
        echo "$stdout_content"
    else
        echo "$fallback_msg"
    fi
    
    # Output filtered stderr to stderr if there are real errors
    if [ -n "$filtered_stderr" ]; then
        echo "$filtered_stderr" >&2
    fi
    
    # Return the original exit code only if there are real errors
    if [ -n "$filtered_stderr" ]; then
        exit $exit_code
    else
        exit 0
    fi
}

# Main execution
if [ $# -lt 4 ]; then
    echo "Usage: $0 <bmc_address> <username> <password> <command> [fallback_message]" >&2
    echo "Example: $0 10.9.1.51 admin password 'fru print' 'FRU_COLLECTION_FAILED'" >&2
    exit 1
fi

execute_ipmi_command "$@"
