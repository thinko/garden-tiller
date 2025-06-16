#!/usr/bin/env python3
"""
Garden-Tiller IPMI Filter Plugins
Provides custom Ansible filters for processing IPMI command results
"""

import re
from ansible.errors import AnsibleFilterError


def clean_ipmi_stderr(stderr_content):
    """
    Filter to clean stderr output from IPMI commands by removing benign errors.
    
    Removes known benign error messages that don't affect command functionality:
    - "Unable to Get Channel Cipher Suites"
    
    Args:
        stderr_content (str): The stderr content from an IPMI command
        
    Returns:
        str: Cleaned stderr content with benign errors removed
    """
    if not isinstance(stderr_content, str):
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


def ipmi_has_real_errors(stderr_content):
    """
    Check if IPMI stderr contains real errors (not just benign cipher suite errors).
    
    Args:
        stderr_content (str): The stderr content from an IPMI command
        
    Returns:
        bool: True if there are real errors, False if only benign errors or no errors
    """
    if not isinstance(stderr_content, str):
        return False
    
    # Clean the stderr first
    cleaned_stderr = clean_ipmi_stderr(stderr_content)
    
    # If there's still content after cleaning, it's likely a real error
    return bool(cleaned_stderr.strip())


def ipmi_extract_useful_info(command_result):
    """
    Extract useful information from an IPMI command result, handling stderr appropriately.
    
    Args:
        command_result (dict): The result dictionary from an Ansible shell/command task
        
    Returns:
        dict: Processed result with cleaned stderr and error flags
    """
    if not isinstance(command_result, dict):
        raise AnsibleFilterError("Input must be a dictionary containing command results")
    
    result = command_result.copy()
    
    # Clean stderr if present
    if 'stderr' in result:
        result['stderr_cleaned'] = clean_ipmi_stderr(result['stderr'])
        result['has_real_errors'] = ipmi_has_real_errors(result['stderr'])
    
    # Clean stderr_lines if present
    if 'stderr_lines' in result:
        stderr_text = '\n'.join(result['stderr_lines'])
        cleaned_stderr = clean_ipmi_stderr(stderr_text)
        result['stderr_lines_cleaned'] = cleaned_stderr.split('\n') if cleaned_stderr else []
    
    return result


class FilterModule(object):
    """Ansible filter plugin class"""
    
    def filters(self):
        return {
            'clean_ipmi_stderr': clean_ipmi_stderr,
            'ipmi_has_real_errors': ipmi_has_real_errors,
            'ipmi_extract_useful_info': ipmi_extract_useful_info,
        }
