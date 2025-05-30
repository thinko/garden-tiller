#!/usr/bin/env python3
"""
Garden-Tiller BMC Support Test Script
Tests both HPE iLO and Dell iDRAC utilities to verify they're working correctly
"""

import os
import sys
import structlog
import importlib.util
import json
import argparse

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger("bmc-test")


def check_library_installed(library_name):
    """Check if a Python library is installed"""
    try:
        importlib.import_module(library_name)
        return True
    except ImportError:
        return False


def test_idrac_utility(idrac_ip, username, password, verify_ssl=False):
    """Test the Dell iDRAC utility"""
    logger.info("Testing Dell iDRAC utility", ip=idrac_ip)
    
    # Import the module dynamically
    try:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from library.idrac_utils import get_idrac_info
        
        # Test the iDRAC connection
        result = get_idrac_info(idrac_ip, username, password)
        
        if result and "error" not in result:
            logger.info("Dell iDRAC test successful", ip=idrac_ip)
            print(json.dumps(result, indent=2))
            return True
        else:
            logger.error("Dell iDRAC test failed", ip=idrac_ip, result=result)
            return False
    except Exception as e:
        logger.error("Dell iDRAC utility error", error=str(e))
        return False


def test_ilo_utility(ilo_ip, username, password, verify_ssl=False, use_redfish=True):
    """Test the HPE iLO utility"""
    logger.info("Testing HPE iLO utility", ip=ilo_ip, use_redfish=use_redfish)
    
    # Import the module dynamically
    try:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from library.ilo_utils import get_ilo_info
        
        # Test the iLO connection
        result = get_ilo_info(ilo_ip, username, password, use_redfish=use_redfish, verify_ssl=verify_ssl)
        
        if result and "error" not in result:
            logger.info("HPE iLO test successful", ip=ilo_ip)
            print(json.dumps(result, indent=2))
            return True
        else:
            logger.error("HPE iLO test failed", ip=ilo_ip, result=result)
            return False
    except Exception as e:
        logger.error("HPE iLO utility error", error=str(e))
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test BMC connectivity utilities')
    parser.add_argument('--type', choices=['idrac', 'ilo'], required=True, help='BMC type to test')
    parser.add_argument('--ip', required=True, help='BMC IP address')
    parser.add_argument('--username', required=True, help='BMC username')
    parser.add_argument('--password', required=True, help='BMC password')
    parser.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificates')
    parser.add_argument('--ribcl', action='store_true', help='Use RIBCL instead of Redfish for HPE iLO')
    
    args = parser.parse_args()
    
    # Check library dependencies
    logger.info("Checking dependencies")
    
    # Common dependencies
    if not check_library_installed("structlog"):
        logger.error("structlog is not installed")
        sys.exit(1)
    
    if not check_library_installed("pybreaker"):
        logger.error("pybreaker is not installed")
        sys.exit(1)
    
    # Test the specified BMC type
    if args.type == "idrac":
        # Check Dell-specific dependencies
        if not check_library_installed("requests"):
            logger.error("requests is not installed (required for Dell iDRAC)")
            sys.exit(1)
        
        success = test_idrac_utility(args.ip, args.username, args.password, args.verify_ssl)
    else:  # args.type == "ilo"
        # Check HPE-specific dependencies
        if not check_library_installed("proliantutils"):
            logger.error("proliantutils is not installed (required for HPE iLO)")
            sys.exit(1)
        
        success = test_ilo_utility(args.ip, args.username, args.password, args.verify_ssl, not args.ribcl)
    
    if success:
        logger.info("BMC test completed successfully")
        sys.exit(0)
    else:
        logger.error("BMC test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
