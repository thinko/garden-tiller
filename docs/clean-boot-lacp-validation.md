# Garden-Tiller Clean Boot LACP Validation

This comprehensive LACP validation system tests all permutations of network interface bonding configurations in clean boot scenarios to validate LACP/802.3ad negotiation with switches.

## Overview

The Clean Boot LACP Validation system consists of several integrated components:

### Components

1. **LACP Validation Test Script** (`scripts/lacp_validation_test.py`)
   - Tests all bonding mode permutations (802.3ad, active-backup, etc.)
   - Performs clean boot network interface testing
   - Uses circuit breaker pattern for resilient operations
   - Structured logging with JSON output

2. **Clean Boot Orchestrator** (`scripts/clean_boot_lacp_orchestrator.py`)
   - Orchestrates comprehensive testing across multiple hosts
   - Manages parallel execution and result aggregation
   - Integrates with Ansible inventory for host discovery
   - Generates comprehensive reports and recommendations

3. **Integration Script** (`scripts/run_clean_boot_lacp.sh`)
   - Bash wrapper that integrates with Garden-Tiller workflow
   - Handles prerequisites and environment preparation
   - Provides clean integration with existing check-lab.sh

4. **Ansible Playbook** (`playbooks/06-clean-boot-network-validation.yaml`)
   - Ansible integration for the clean boot LACP testing
   - Orchestrates testing workflow across infrastructure
   - Collects and consolidates results

## Features

### Comprehensive Testing
- **All Bonding Modes**: Tests 802.3ad (LACP), active-backup, balance-alb, balance-rr, balance-tlb, balance-xor, broadcast
- **Interface Combinations**: Tests 2, 3, 4+ interface bonding configurations
- **LACP Rate Testing**: Tests both slow (30s) and fast (1s) LACP packet rates
- **MII Monitoring**: Tests different monitoring frequencies (disabled, 50ms, 100ms)

### Switch Compatibility Analysis
- **Negotiation Tracking**: Records negotiation times and success rates
- **Partner Detection**: Validates LACP partner system detection
- **Aggregator Analysis**: Tracks aggregator ID assignment
- **Performance Metrics**: Measures negotiation speed and stability

### Resilient Operations
- **Circuit Breaker Pattern**: Uses PyBreaker for fault tolerance
- **Graceful Cleanup**: Restores network state after testing
- **Error Recovery**: Handles partial failures and timeouts
- **Parallel Execution**: Tests multiple hosts concurrently

### Structured Logging
- **JSON Output**: Machine-readable structured logs
- **Performance Tracking**: Detailed timing and metrics
- **Error Diagnostics**: Comprehensive error information
- **Switch Integration**: Placeholder for switch-side log collection

## Installation

### Prerequisites

1. **Root Access**: Required for network interface manipulation
2. **Python Dependencies**:
   ```bash
   pip3 install structlog pybreaker pyyaml
   ```
3. **Ansible**: Required for orchestration
4. **Network Tools**: `ethtool`, `ip`, `ping` (usually pre-installed)

### Setup

1. Ensure all scripts are executable:
   ```bash
   chmod +x scripts/clean_boot_lacp_orchestrator.py
   chmod +x scripts/lacp_validation_test.py
   chmod +x scripts/run_clean_boot_lacp.sh
   ```

2. Validate setup:
   ```bash
   ./scripts/test_clean_boot_lacp.sh
   ```

## Usage

### Standalone Execution

Run comprehensive clean boot LACP testing:
```bash
sudo ./scripts/run_clean_boot_lacp.sh
```

### Advanced Options

```bash
# Skip clean boot preparation (faster)
sudo ./scripts/run_clean_boot_lacp.sh --no-clean-boot

# Skip testing all permutations (faster)
sudo ./scripts/run_clean_boot_lacp.sh --no-permutations

# Custom parallel execution
sudo ./scripts/run_clean_boot_lacp.sh --parallel-hosts 5

# Custom inventory
sudo ./scripts/run_clean_boot_lacp.sh --inventory custom/hosts.yaml
```

### Ansible Integration

Run as part of Garden-Tiller suite:
```bash
# Full suite including clean boot testing
ansible-playbook -i inventories/hosts.yaml playbooks/site.yaml

# Only clean boot network validation
ansible-playbook -i inventories/hosts.yaml playbooks/06-clean-boot-network-validation.yaml

# Clean boot testing with specific tags
ansible-playbook -i inventories/hosts.yaml playbooks/site.yaml --tags clean-boot,lacp
```

### Python Script Direct Usage

```bash
# Basic usage
sudo python3 scripts/clean_boot_lacp_orchestrator.py

# With options
sudo python3 scripts/clean_boot_lacp_orchestrator.py \
    --inventory inventories/hosts.yaml \
    --results-dir reports \
    --parallel-hosts 3 \
    --verbose
```

## Configuration

### Environment Variables

- `NO_CLEAN_BOOT`: Set to 'true' to skip clean boot preparation
- `NO_PERMUTATIONS`: Set to 'true' to skip permutation testing
- `PARALLEL_HOSTS`: Number of hosts to test in parallel

### Inventory Requirements

The system requires a properly configured Ansible inventory with a `baremetal` group:

```yaml
all:
  children:
    baremetal:
      hosts:
        host1:
          bmc_address: 192.168.1.100
          switch_ip: 192.168.1.200
        host2:
          bmc_address: 192.168.1.101
          switch_ip: 192.168.1.201
```

## Results and Reports

### Output Files

Results are saved to the `reports/` directory:

- `clean_boot_lacp_results_TIMESTAMP.json`: Comprehensive test results
- `clean_boot_lacp_integration_TIMESTAMP.html`: Integration report
- `clean_boot_lacp_summary.md`: Execution summary
- `lacp_results_HOST_TIMESTAMP.json`: Per-host detailed results

### Result Structure

```json
{
  "test_session": {
    "session_id": "lacp_test_1234567890",
    "start_time": "2024-01-01T12:00:00",
    "hosts": ["host1", "host2"]
  },
  "summary": {
    "total_hosts": 2,
    "total_configurations_tested": 48,
    "total_successful_configurations": 32,
    "overall_success_rate": 66.7
  },
  "host_results": {
    "host1": {
      "interfaces_discovered": 4,
      "configurations_tested": 24,
      "successful_configs": 16,
      "best_config": {
        "mode": "LACP_802_3AD",
        "interfaces": ["eno1", "eno2"],
        "negotiation_time": 3.2
      }
    }
  },
  "compatibility_analysis": {
    "most_compatible_modes": [
      ["LACP_802_3AD", 2],
      ["ACTIVE_BACKUP", 2]
    ],
    "universal_configurations": [...],
    "performance_recommendations": [...]
  }
}
```

## Integration with Garden-Tiller

### Workflow Integration

The clean boot LACP validation integrates seamlessly with the Garden-Tiller validation suite:

1. **Pre-validation**: Basic network discovery and connectivity checks
2. **Clean Boot Preparation**: Network state cleanup and baseline establishment
3. **Comprehensive Testing**: All bonding mode permutations across all hosts
4. **Result Analysis**: Switch compatibility and performance analysis
5. **Cleanup and Restore**: Network state restoration
6. **Report Generation**: Comprehensive results and recommendations

### Check-lab.sh Integration

Add to your `check-lab.sh` workflow:

```bash
# Add clean boot LACP validation
echo "Running clean boot LACP validation..."
if sudo ./scripts/run_clean_boot_lacp.sh; then
    echo "✓ Clean boot LACP validation completed successfully"
else
    echo "✗ Clean boot LACP validation failed"
fi
```

## Performance Considerations

### Execution Time

- **Full permutation testing**: 30-45 minutes per host (depends on interface count)
- **Basic testing**: 10-15 minutes per host
- **Parallel execution**: Scales with number of parallel hosts

### Resource Requirements

- **CPU**: Minimal impact during testing
- **Memory**: Low memory footprint
- **Network**: Temporary interface state changes
- **Disk**: JSON result files (typically <10MB per host)

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   # Solution: Run with sudo
   sudo ./scripts/run_clean_boot_lacp.sh
   ```

2. **Missing Dependencies**
   ```bash
   # Solution: Install Python packages
   pip3 install structlog pybreaker pyyaml
   ```

3. **Ansible Inventory Issues**
   ```bash
   # Solution: Validate inventory structure
   ansible-inventory -i inventories/hosts.yaml --list
   ```

4. **Network Interface Access**
   ```bash
   # Solution: Ensure interfaces are not in use
   # Check for existing bonds: ls /sys/class/net/bond*
   ```

### Debug Mode

Enable verbose logging:
```bash
sudo ./scripts/run_clean_boot_lacp.sh --verbose
```

Check detailed logs:
```bash
tail -f logs/clean-boot-lacp-*.log
```

## Advanced Configuration

### Custom Test Parameters

Modify `scripts/clean_boot_lacp_orchestrator.py` for custom test scenarios:

```python
# Custom bonding modes to test
CUSTOM_MODES = [BondMode.LACP_802_3AD, BondMode.ACTIVE_BACKUP]

# Custom interface combinations
INTERFACE_COMBINATIONS = [2, 4]  # Only test 2 and 4 interface bonds
```

### Switch Integration

For switch-side logging integration, implement the `_get_switch_negotiation_logs()` method:

```python
def _get_switch_negotiation_logs(self, config: BondConfiguration) -> List[str]:
    # SSH to switch and collect LACP logs
    # SNMP queries for port statistics
    # Parse switch-specific LACP negotiation data
    pass
```

## Contributing

When contributing to the clean boot LACP validation:

1. Follow the existing code style and patterns
2. Add comprehensive error handling and logging
3. Update tests and documentation
4. Validate with `./scripts/test_clean_boot_lacp.sh`

## Related Documentation

- [Garden-Tiller Main README](../README.md)
- [Network Validation Documentation](05-network-validation.md)
- [LACP Best Practices](docs/lacp-best-practices.md)
- [Switch Configuration Guide](docs/switch-configuration.md)
