#!/usr/bin/env python3
"""
Garden-Tiller Resilient IPMI Command Module
Provides resilient execution of IPMI commands with error filtering and retry logic
Uses Structlog for logging and PyBreaker for resilience as per coding standards
"""

import os
import subprocess
import time
import re
import structlog
import pybreaker
from ansible.module_utils.basic import AnsibleModule

# Configure structured logging
logger = structlog.get_logger("resilient-ipmi")

# Configure circuit breaker for IPMI commands
ipmi_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=60,
    exclude=[
        subprocess.TimeoutExpired,
        KeyboardInterrupt,
    ]
)


def clean_ipmi_stderr(stderr_content):
    """
    Clean stderr output from IPMI commands by removing benign errors.
    
    Args:
        stderr_content (str): The stderr content from an IPMI command
        
    Returns:
        str: Cleaned stderr content with benign errors removed
    """
    if not stderr_content:
        return stderr_content
    
    # Define patterns for benign errors to remove
    benign_patterns = [
        r'Unable to Get Channel Cipher Suites\s*',
        r'Get Channel Cipher Suites command failed.*?\n?',
    ]
    
    cleaned_stderr = stderr_content
    for pattern in benign_patterns:
        cleaned_stderr = re.sub(pattern, '', cleaned_stderr, flags=re.IGNORECASE | re.MULTILINE)
    
    # Clean up any resulting empty lines
    cleaned_stderr = re.sub(r'\n\s*\n', '\n', cleaned_stderr)
    cleaned_stderr = cleaned_stderr.strip()
    
    return cleaned_stderr


def has_real_errors(stderr_content):
    """
    Check if IPMI stderr contains real errors (not just benign cipher suite errors).
    
    Args:
        stderr_content (str): The stderr content from an IPMI command
        
    Returns:
        bool: True if there are real errors, False if only benign errors or no errors
    """
    cleaned_stderr = clean_ipmi_stderr(stderr_content)
    return bool(cleaned_stderr.strip())


@ipmi_breaker
def execute_ipmi_command(bmc_address, username, password, command, timeout=30):
    """
    Execute an IPMI command with circuit breaker protection.
    
    Args:
        bmc_address (str): BMC IP address
        username (str): BMC username
        password (str): BMC password
        command (str): IPMI command to execute (without ipmitool prefix)
        timeout (int): Command timeout in seconds
        
    Returns:
        dict: Command execution result
    """
    full_command = [
        'ipmitool', '-I', 'lanplus',
        '-H', bmc_address,
        '-U', username,
        '-P', password
    ] + command.split()
    
    logger.info("Executing IPMI command", 
                bmc_address=bmc_address, 
                command=command)
    
    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # Don't raise on non-zero return codes
        )
        
        # Clean stderr output
        cleaned_stderr = clean_ipmi_stderr(result.stderr)
        has_errors = has_real_errors(result.stderr)
        
        execution_result = {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'stderr_cleaned': cleaned_stderr,
            'has_real_errors': has_errors,
            'command': ' '.join(full_command),
            'success': result.returncode == 0 and not has_errors
        }
        
        if execution_result['success']:
            logger.info("IPMI command completed successfully", 
                       bmc_address=bmc_address,
                       command=command)
        else:
            logger.warning("IPMI command completed with issues",
                          bmc_address=bmc_address,
                          command=command,
                          returncode=result.returncode,
                          has_real_errors=has_errors)
        
        return execution_result
        
    except subprocess.TimeoutExpired:
        logger.error("IPMI command timed out",
                    bmc_address=bmc_address,
                    command=command,
                    timeout=timeout)
        raise
    except Exception as e:
        logger.error("IPMI command execution failed",
                    bmc_address=bmc_address,
                    command=command,
                    error=str(e))
        raise


def run_module():
    """Main module execution function"""
    
    # Define module arguments
    module_args = dict(
        bmc_address=dict(type='str', required=True),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        command=dict(type='str', required=True),
        timeout=dict(type='int', default=30),
        retry_count=dict(type='int', default=3),
        retry_delay=dict(type='int', default=2),
        fail_on_stderr=dict(type='bool', default=False),
        fallback_message=dict(type='str', default='COMMAND_FAILED')
    )
    
    # Initialize module
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )
    
    # Get parameters
    bmc_address = str(module.params['bmc_address'])
    username = str(module.params['username'])
    password = str(module.params['password'])
    command = str(module.params['command'])
    timeout = int(module.params['timeout'])
    retry_count = int(module.params['retry_count'])
    retry_delay = int(module.params['retry_delay'])
    fail_on_stderr = bool(module.params['fail_on_stderr'])
    fallback_message = str(module.params['fallback_message'])
    
    # Initialize result
    result = {
        'changed': False,
        'attempts': 0,
        'circuit_state': 'unknown'
    }
    
    # Attempt command execution with retries
    for attempt in range(1, retry_count + 1):
        result['attempts'] = attempt
        
        try:
            execution_result = execute_ipmi_command(
                bmc_address, username, password, command, timeout
            )
            
            # Update result with execution details
            result.update(execution_result)
            result['circuit_state'] = 'closed'
            
            # Determine if this should be treated as a failure
            if execution_result['returncode'] != 0:
                # If return code is non-zero, use fallback message
                result['stdout'] = fallback_message
                result['failed'] = False  # Don't fail the task, let playbook logic handle it
            elif fail_on_stderr and execution_result['has_real_errors']:
                result['failed'] = True
                result['msg'] = "Command completed but stderr contains real errors"
                module.fail_json(**result)
            else:
                # Success case
                result['failed'] = False
                module.exit_json(**result)
                
        except pybreaker.CircuitBreakerError as e:
            result['circuit_state'] = 'open'
            if attempt >= retry_count:
                result['failed'] = True
                result['msg'] = f"Circuit breaker is open after {attempt} attempts: {str(e)}"
                result['stdout'] = fallback_message
                module.fail_json(**result)
                
        except Exception as e:
            if attempt >= retry_count:
                result['failed'] = True
                result['msg'] = f"Command failed after {attempt} attempts: {str(e)}"
                result['stdout'] = fallback_message
                module.fail_json(**result)
                
            # Wait before retry
            if attempt < retry_count:
                time.sleep(retry_delay * attempt)  # Exponential backoff
    
    # If we get here, all retries were exhausted
    result['failed'] = False  # Don't fail, let playbook handle via fallback message
    result['stdout'] = fallback_message
    module.exit_json(**result)


def main():
    """Module entry point"""
    run_module()


if __name__ == '__main__':
    main()
