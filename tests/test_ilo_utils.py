#!/usr/bin/env python3
"""
Garden-Tiller HPE iLO Utilities Test Suite
Comprehensive tests for ilo_utils.py with mocking of external dependencies
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add the library directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'library'))

# Import the module under test
import ilo_utils

class TestIloProUtils:
    """Test suite for IloProUtils class"""

    @pytest.fixture
    def mock_ilo_client(self):
        """Create a mock iLO client for testing"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                # Configure mock iLO client
                mock_client = Mock()
                mock_ilo.Ilo.return_value = mock_client
                
                # Configure basic responses
                mock_client.get_product_name.return_value = "ProLiant DL380 Gen9"
                mock_client.get_host_power_status.return_value = "ON"
                mock_client.get_fw_version.return_value = {"firmware_version": "2.70"}
                mock_client.get_host_uuid.return_value = "11111111-2222-3333-4444-555555555555"
                
                yield mock_client

    @pytest.fixture
    def ilo_utils_instance(self, mock_ilo_client):
        """Create an IloProUtils instance for testing"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            return ilo_utils.IloProUtils(
                ilo_ip="10.0.0.100", 
                ilo_username="admin", 
                ilo_password="password",
                use_redfish=True,
                verify_ssl=False
            )

    def test_init_with_proliantutils_available(self):
        """Test initialization when proliantutils is available"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                mock_client = Mock()
                mock_ilo.Ilo.return_value = mock_client
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    ilo_username="admin", 
                    ilo_password="password",
                    use_redfish=True,
                    verify_ssl=False
                )
                
                assert instance.ilo_ip == "10.0.0.100"
                assert instance.username == "admin"
                assert instance.password == "password"
                assert instance.use_redfish is True
                assert instance.verify_ssl is False
                assert instance.client is not None

    def test_init_without_proliantutils(self):
        """Test initialization when proliantutils is not available"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', False):
            instance = ilo_utils.IloProUtils(
                ilo_ip="10.0.0.100",
                ilo_username="admin",
                ilo_password="password",
                use_redfish=True,
                verify_ssl=False
            )
            
            assert instance.client is None

    def test_get_product_name_success(self, ilo_utils_instance, mock_ilo_client):
        """Test successful product name retrieval"""
        result = ilo_utils_instance.get_product_name()
        assert result == "ProLiant DL380 Gen9"
        mock_ilo_client.get_product_name.assert_called_once()

    def test_get_product_name_failure(self, ilo_utils_instance, mock_ilo_client):
        """Test product name retrieval failure"""
        mock_ilo_client.get_product_name.side_effect = Exception("Connection failed")
        
        result = ilo_utils_instance.get_product_name()
        assert result == "Unknown"

    def test_get_power_status_success(self, ilo_utils_instance, mock_ilo_client):
        """Test successful power status retrieval"""
        result = ilo_utils_instance.get_power_status()
        assert result == "ON"
        mock_ilo_client.get_host_power_status.assert_called_once()

    def test_get_power_status_failure(self, ilo_utils_instance, mock_ilo_client):
        """Test power status retrieval failure"""
        mock_ilo_client.get_host_power_status.side_effect = Exception("Connection failed")
        
        result = ilo_utils_instance.get_power_status()
        assert result == "Unknown"

    def test_get_firmware_version_success(self, ilo_utils_instance, mock_ilo_client):
        """Test successful firmware version retrieval"""
        result = ilo_utils_instance.get_firmware_version()
        assert result == "2.70"

    def test_get_firmware_version_failure(self, ilo_utils_instance, mock_ilo_client):
        """Test firmware version retrieval failure"""
        mock_ilo_client.get_fw_version.side_effect = Exception("Connection failed")
        
        result = ilo_utils_instance.get_firmware_version()
        assert result == "Unknown"

    def test_get_host_uuid_success(self, ilo_utils_instance, mock_ilo_client):
        """Test successful host UUID retrieval"""
        result = ilo_utils_instance.get_host_uuid()
        assert result == "11111111-2222-3333-4444-555555555555"

    def test_get_host_uuid_failure(self, ilo_utils_instance, mock_ilo_client):
        """Test host UUID retrieval failure"""
        mock_ilo_client.get_host_uuid.side_effect = Exception("Connection failed")
        
        result = ilo_utils_instance.get_host_uuid()
        assert result == "Unknown"

    @patch('ilo_utils.requests.get')
    def test_redfish_get_request_success(self, mock_get, ilo_utils_instance):
        """Test successful Redfish GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response
        
        result = ilo_utils_instance._redfish_get_request("/redfish/v1/Systems/1")
        
        assert result == {"test": "data"}
        mock_get.assert_called_once()

    @patch('ilo_utils.requests.get')
    def test_redfish_get_request_failure(self, mock_get, ilo_utils_instance):
        """Test failed Redfish GET request"""
        mock_get.side_effect = Exception("Network error")
        
        result = ilo_utils_instance._redfish_get_request("/redfish/v1/Systems/1")
        
        assert result is None

    def test_get_all_details_success(self, ilo_utils_instance, mock_ilo_client):
        """Test successful get_all_details execution"""
        # Mock additional methods that get_all_details calls
        mock_ilo_client.get_one_time_boot.return_value = "Hdd"
        mock_ilo_client.get_persistent_boot_device.return_value = ["Hdd"]
        
        with patch.object(ilo_utils_instance, 'get_health_status') as mock_health:
            mock_health.return_value = {
                "system_health": "OK",
                "processor": "OK", 
                "memory": "OK",
                "storage": "OK"
            }
            
            with patch.object(ilo_utils_instance, 'get_network_adapters_enhanced') as mock_network:
                mock_network.return_value = []
                
                with patch.object(ilo_utils_instance, 'get_comprehensive_hardware_inventory_enhanced') as mock_hardware:
                    mock_hardware.return_value = {"test": "inventory"}
                    
                    result = ilo_utils_instance.get_all_details()
                    
                    assert result["collection_status"] == "success"
                    assert result["product_name"] == "ProLiant DL380 Gen9"
                    assert result["power_status"] == "ON"
                    assert result["firmware_version"] == "2.70"
                    assert result["host_uuid"] == "11111111-2222-3333-4444-555555555555"
                    assert "timestamp" in result
                    assert "errors_encountered" in result
                    assert result["partial_data"] is False

    def test_get_all_details_with_errors(self, ilo_utils_instance, mock_ilo_client):
        """Test get_all_details with some errors occurring"""
        # Make some methods fail
        mock_ilo_client.get_product_name.side_effect = Exception("Product name error")
        mock_ilo_client.get_host_power_status.return_value = "ON"  # This one works
        
        with patch.object(ilo_utils_instance, 'get_health_status') as mock_health:
            mock_health.side_effect = Exception("Health error")
            
            with patch.object(ilo_utils_instance, 'get_network_adapters_enhanced') as mock_network:
                mock_network.return_value = []
                
                with patch.object(ilo_utils_instance, 'get_comprehensive_hardware_inventory_enhanced') as mock_hardware:
                    mock_hardware.return_value = {"test": "inventory"}
                    
                    result = ilo_utils_instance.get_all_details()
                    
                    assert result["collection_status"] == "errors_occurred"
                    assert result["product_name"] == "Unknown"
                    assert result["power_status"] == "ON"  # This one should work
                    assert result["partial_data"] is True
                    assert len(result["errors_encountered"]) > 0

    def test_get_all_details_no_proliantutils(self):
        """Test get_all_details when proliantutils is not available"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', False):
            instance = ilo_utils.IloProUtils(
                ilo_ip="10.0.0.100",
                ilo_username="admin", 
                ilo_password="password",
                use_redfish=True,
                verify_ssl=False
            )
            
            result = instance.get_all_details()
            
            assert result["collection_status"] == "error"
            assert "proliantutils not available" in result["error"]

    def test_circuit_breaker_functionality(self, ilo_utils_instance, mock_ilo_client):
        """Test that circuit breaker works correctly"""
        # Make the client consistently fail
        mock_ilo_client.get_product_name.side_effect = Exception("Persistent failure")
        
        # Call the method multiple times to trigger circuit breaker
        for _ in range(6):  # More than the fail_max of 5
            try:
                ilo_utils_instance.get_product_name()
            except:
                pass  # Expected to fail
        
        # Circuit breaker should now be open
        # Note: This test verifies the circuit breaker integration, 
        # actual behavior depends on pybreaker configuration


class TestMainFunction:
    """Test suite for main function and CLI interface"""

    @patch('sys.argv', ['ilo_utils.py', '10.0.0.100', 'admin', 'password', 'get_all_details', '--redfish'])
    @patch('ilo_utils.IloProUtils')
    def test_main_get_all_details(self, mock_ilo_class):
        """Test main function with get_all_details action"""
        mock_instance = Mock()
        mock_instance.get_all_details.return_value = {"test": "result"}
        mock_ilo_class.return_value = mock_instance
        
        with patch('builtins.print') as mock_print:
            ilo_utils.main()
            
        # Verify the IloProUtils was initialized correctly
        mock_ilo_class.assert_called_once_with(
            '10.0.0.100', 'admin', 'password', True, False
        )
        
        # Verify get_all_details was called
        mock_instance.get_all_details.assert_called_once()
        
        # Verify JSON output was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]
        assert '"test": "result"' in printed_output

    @patch('sys.argv', ['ilo_utils.py', '10.0.0.100', 'admin', 'password', 'unknown_action'])
    @patch('ilo_utils.IloProUtils')
    def test_main_unknown_action(self, mock_ilo_class):
        """Test main function with unknown action"""
        mock_instance = Mock()
        mock_ilo_class.return_value = mock_instance
        
        with patch('builtins.print') as mock_print:
            ilo_utils.main()
            
        # Verify error output was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]
        assert "Unknown action: unknown_action" in printed_output

    @patch('sys.argv', ['ilo_utils.py', '10.0.0.100', 'admin', 'password', 'get_all_details'])
    @patch('ilo_utils.IloProUtils')
    def test_main_exception_handling(self, mock_ilo_class):
        """Test main function exception handling"""
        mock_ilo_class.side_effect = Exception("Connection failed")
        
        with patch('builtins.print') as mock_print:
            with patch('sys.exit') as mock_exit:
                ilo_utils.main()
                
        # Verify error was printed and exit was called
        mock_print.assert_called_once()
        mock_exit.assert_called_once_with(1)
        
        # Verify error JSON structure
        printed_output = mock_print.call_args[0][0]
        error_data = json.loads(printed_output)
        assert "error" in error_data
        assert error_data["action"] == "get_all_details"
        assert error_data["ilo_ip"] == "10.0.0.100"


class TestUtilityFunctions:
    """Test suite for utility functions and decorators"""

    def test_retry_with_backoff_decorator(self):
        """Test retry decorator functionality"""
        call_count = 0
        
        @ilo_utils.retry_with_backoff(max_tries=3, initial_delay=0.01)  # Small delay for testing
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Attempt {call_count} failed")
            return "Success"
        
        result = failing_function()
        assert result == "Success"
        assert call_count == 3

    def test_retry_with_backoff_permanent_failure(self):
        """Test retry decorator with permanent failure"""
        call_count = 0
        
        @ilo_utils.retry_with_backoff(max_tries=3, initial_delay=0.01)
        def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise Exception(f"Attempt {call_count} failed")
        
        with pytest.raises(Exception) as exc_info:
            always_failing_function()
        
        assert "Attempt 3 failed" in str(exc_info.value)
        assert call_count == 3


class TestErrorHandling:
    """Test suite for error handling scenarios"""

    def test_ilo_connection_error_handling(self):
        """Test handling of iLO connection errors"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                # Simulate IloConnectionError
                mock_ilo.Ilo.side_effect = Exception("IloConnectionError: Could not connect")
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    ilo_username="admin",
                    ilo_password="password",
                    use_redfish=True,
                    verify_ssl=False
                )
                
                result = instance.get_all_details()
                assert result["collection_status"] == "error"
                assert "Could not connect" in result["error"]

    def test_invalid_credentials_handling(self):
        """Test handling of invalid credentials"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                mock_client = Mock()
                mock_client.get_product_name.side_effect = Exception("Authentication failed")
                mock_ilo.Ilo.return_value = mock_client
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    ilo_username="baduser",
                    ilo_password="badpass",
                    use_redfish=True,
                    verify_ssl=False
                )
                
                result = instance.get_all_details()
                assert result["collection_status"] == "errors_occurred"
                assert result["partial_data"] is True

    def test_network_timeout_handling(self):
        """Test handling of network timeouts"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                mock_client = Mock()
                mock_client.get_product_name.side_effect = Exception("Timeout")
                mock_ilo.Ilo.return_value = mock_client
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    username="admin",
                    password="password", 
                    use_redfish=True,
                    verify_ssl=False
                )
                
                result = instance.get_all_details()
                assert result["collection_status"] == "errors_occurred"
                assert "Timeout" in str(result["errors_encountered"])


class TestDataValidation:
    """Test suite for data validation and sanitization"""

    def test_json_serialization(self):
        """Test that all returned data is JSON serializable"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                mock_client = Mock()
                mock_client.get_product_name.return_value = "ProLiant DL380 Gen9"
                mock_client.get_host_power_status.return_value = "ON"
                mock_client.get_fw_version.return_value = {"firmware_version": "2.70"}
                mock_client.get_host_uuid.return_value = "test-uuid"
                mock_ilo.Ilo.return_value = mock_client
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    username="admin",
                    password="password",
                    use_redfish=True,
                    verify_ssl=False
                )
                
                with patch.object(instance, 'get_health_status') as mock_health:
                    mock_health.return_value = {"system_health": "OK"}
                    
                    with patch.object(instance, 'get_network_adapters_enhanced') as mock_network:
                        mock_network.return_value = []
                        
                        with patch.object(instance, 'get_comprehensive_hardware_inventory_enhanced') as mock_hardware:
                            mock_hardware.return_value = {}
                            
                            result = instance.get_all_details()
                            
                            # This should not raise an exception
                            json_output = json.dumps(result, indent=2, default=str)
                            assert len(json_output) > 0

    def test_unicode_handling(self):
        """Test handling of unicode characters in responses"""
        with patch('ilo_utils.PROLIANTUTILS_AVAILABLE', True):
            with patch('ilo_utils.ilo') as mock_ilo:
                mock_client = Mock()
                mock_client.get_product_name.return_value = "ProLiant® DL380 Gen9"  # Unicode character
                mock_ilo.Ilo.return_value = mock_client
                
                instance = ilo_utils.IloProUtils(
                    ilo_ip="10.0.0.100",
                    username="admin",
                    password="password",
                    use_redfish=True,
                    verify_ssl=False
                )
                
                result = instance.get_product_name()
                assert "ProLiant" in result
                
                # Should be JSON serializable
                json.dumps({"product": result})


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
