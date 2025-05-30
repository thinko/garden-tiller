#!/usr/bin/python

# Copyright: (c) 2023, Your Name <your.email@example.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: resilient_command

short_description: Execute a command with resilience patterns

version_added: "1.0.0"

description:
    - This module wraps command execution with resilience patterns
    - It uses the PyBreaker library for circuit breaking and standard retry mechanisms
    - Provides better error handling and logging than standard command module

options:
    command:
        description: The command to run
        required: true
        type: str
    retry_count:
        description: Number of retries if the command fails
        required: false
        type: int
        default: 3
    retry_delay:
        description: Delay between retries in seconds
        required: false
        type: int
        default: 2
    circuit_threshold:
        description: Number of failures before opening the circuit
        required: false
        type: int
        default: 5
    timeout:
        description: Command execution timeout in seconds
        required: false
        type: int
        default: 30

author:
    - Your Name (@yourgithub)
'''

EXAMPLES = r'''
# Execute a command with default resilience settings
- name: Test network connectivity
  resilient_command:
    command: ping -c 3 www.example.com

# Execute with custom retry and circuit settings
- name: Test firmware update operation
  resilient_command:
    command: update_firmware.sh -d /dev/sda
    retry_count: 5
    retry_delay: 10
    circuit_threshold: 3
    timeout: 120
'''

RETURN = r'''
stdout:
    description: The command standard output
    type: str
    returned: always
stderr:
    description: The command standard error
    type: str
    returned: always
rc:
    description: The command return code
    type: int
    returned: always
circuit_state:
    description: The state of the circuit breaker after execution
    type: str
    returned: always
'''

import os
import time
import subprocess
import shlex
import signal
from ansible.module_utils.basic import AnsibleModule

try:
    # Requires: pip install pybreaker
    import pybreaker
    HAS_PYBREAKER = True
except ImportError:
    HAS_PYBREAKER = False


def run_with_timeout(command, timeout):
    """Run a command with a timeout."""
    process = subprocess.Popen(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Wait for the process to finish or timeout
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        # Kill the process if it times out
        process.kill()
        stdout, stderr = process.communicate()
        return 124, stdout, stderr  # Using 124 as a standard timeout exit code


def main():
    # Define module arguments
    module_args = dict(
        command=dict(type='str', required=True),
        retry_count=dict(type='int', default=3),
        retry_delay=dict(type='int', default=2),
        circuit_threshold=dict(type='int', default=5),
        timeout=dict(type='int', default=30)
    )

    # Create module instance
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # Check if pybreaker is installed
    if not HAS_PYBREAKER:
        module.fail_json(
            msg="The Python pybreaker library is required for this module"
        )

    # Get module parameters
    command = module.params['command']
    retry_count = module.params['retry_count']
    retry_delay = module.params['retry_delay']
    circuit_threshold = module.params['circuit_threshold']
    timeout = module.params['timeout']

    if module.check_mode:
        module.exit_json(
            changed=True,
            command=command,
            msg="Would have run command with resilience patterns"
        )

    # Create circuit breaker
    breaker = pybreaker.CircuitBreaker(
        fail_max=circuit_threshold,
        reset_timeout=60,
        exclude=[subprocess.TimeoutExpired]  # Don't trip the breaker on timeouts
    )

    # Execute command with resilience patterns
    attempts = 0
    result = {
        'stdout': '',
        'stderr': '',
        'rc': -1,
        'circuit_state': 'closed',
        'attempts': 0,
        'changed': True
    }

    # Update circuit state
    if breaker.current_state == pybreaker.STATE_OPEN:
        result['circuit_state'] = 'open'
        result['failed'] = True
        result['msg'] = "Circuit is open due to too many failures"
        module.fail_json(**result)
    
    max_retries = retry_count + 1  # Original try + retries
    while attempts < max_retries:
        attempts += 1
        result['attempts'] = attempts
        
        try:
            # Execute command with timeout using the circuit breaker
            @breaker
            def execute_command():
                return run_with_timeout(command, timeout)
                
            rc, stdout, stderr = execute_command()
            
            result['stdout'] = stdout
            result['stderr'] = stderr
            result['rc'] = rc
            
            # Update circuit state in the result
            if breaker.current_state == pybreaker.STATE_OPEN:
                result['circuit_state'] = 'open'
            elif breaker.current_state == pybreaker.STATE_HALF_OPEN:
                result['circuit_state'] = 'half-open'
            else:
                result['circuit_state'] = 'closed'
            
            # Success - no need to retry
            if rc == 0:
                module.exit_json(**result)
                
            # Command failed, but we've reached max retries
            if attempts >= max_retries:
                result['failed'] = True
                result['msg'] = f"Command failed after {attempts} attempts"
                module.fail_json(**result)
                
            # Calculate exponential backoff
            wait_time = retry_delay * (2 ** (attempts - 1))
            time.sleep(wait_time)
                
        except pybreaker.CircuitBreakerError as e:
            result['circuit_state'] = 'open'
            result['failed'] = True
            result['msg'] = f"Circuit breaker is open: {str(e)}"
            module.fail_json(**result)
            
        except Exception as e:
            if attempts >= max_retries:
                result['failed'] = True
                result['msg'] = f"Command failed with exception: {str(e)}"
                module.fail_json(**result)
                
            # Calculate exponential backoff
            wait_time = retry_delay * (2 ** (attempts - 1))
            time.sleep(wait_time)
    
    # Should never reach here, but just in case
    result['failed'] = True
    result['msg'] = f"Command failed after {attempts} attempts"
    module.fail_json(**result)


if __name__ == '__main__':
    main()
