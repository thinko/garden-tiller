#!/usr/bin/env python3
"""
Test file for the report_generator module
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path

# Add the parent directory to the path so we can import our module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.report_generator import setup_logging, ReportGenerator

class TestReportGenerator:
    """Tests for the ReportGenerator class"""
    
    @pytest.fixture
    def sample_results(self):
        """Fixture providing sample validation results"""
        return {
            "network": {
                "bond": {
                    "status": True,
                    "mode": "802.3ad",
                    "passed": True
                },
                "vlan": {
                    "status": True,
                    "details": ["VLAN100", "VLAN200"]
                },
                "mtu": {
                    "expected": 9000,
                    "results": {"eth0": True, "eth1": True},
                    "passed": True
                },
                "errors": {
                    "interfaces_with_errors": [],
                    "passed": True
                },
                "routing": {
                    "has_default_route": True,
                    "gateway_reachable": True,
                    "internet_reachable": True,
                    "dns_resolution": True
                },
                "total_checks": 5,
                "passed_checks": 5,
                "failed_checks": 0
            }
        }
    
    @pytest.fixture
    def logger(self):
        """Fixture providing a logger instance"""
        return setup_logging()
    
    def test_init(self, logger):
        """Test ReportGenerator initialization"""
        with tempfile.NamedTemporaryFile(suffix=".json") as results_file:
            with tempfile.NamedTemporaryFile(suffix=".html") as output_file:
                generator = ReportGenerator(results_file.name, output_file.name, logger)
                assert generator.results_file == results_file.name
                assert generator.output_file == output_file.name
                assert generator.results is None
    
    def test_load_results(self, sample_results, logger):
        """Test loading results from a file"""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+") as results_file:
            # Write sample results to the file
            json.dump(sample_results, results_file)
            results_file.flush()
            
            with tempfile.NamedTemporaryFile(suffix=".html") as output_file:
                generator = ReportGenerator(results_file.name, output_file.name, logger)
                
                # Test fails with invalid JSON
                with pytest.raises(Exception):
                    with open(results_file.name, "w") as f:
                        f.write("This is not valid JSON")
                    generator.load_results()
                
                # Test succeeds with valid JSON
                with open(results_file.name, "w") as f:
                    json.dump(sample_results, f)
                assert generator.load_results() is True
                assert generator.results == sample_results
                
    def test_structlog_setup(self):
        """Test that Structlog setup works correctly"""
        logger = setup_logging(level="DEBUG")
        assert logger is not None
        
        # Test structured logging with contextual information
        logger.debug("Debug message", test_param="value")
        logger.info("Info message", count=42, success=True)
        logger.warning("Warning message", component="network", host="test-server")
        logger.error("Error message", error_code=500, error_msg="Internal Server Error")
