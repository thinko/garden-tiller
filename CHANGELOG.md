# Changelog

All notable changes to the Garden-Tiller project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure
- Core validation framework
- Network validation playbook
- DNS validation playbook
- Report generation capabilities
- Containerization with Podman/OpenShift support
- Docker support for RHEL 10 bootc containers
- Garden Shed integration module (`library/garden_shed.py`)
- New Garden Shed integrated playbooks:
  - Data collection playbook (`00-data-collection-garden-shed.yaml`)
  - HPE OOBM validation with Garden Shed (`01c-validate-hpe-oobm-garden-shed.yaml`)
  - IPMI enumeration with Garden Shed (`02-enumerate-ipmi-garden-shed.yaml`)
  - Firmware update with Garden Shed (`03-firmware-update-garden-shed.yaml`)
  - Network validation with Garden Shed (`05-network-validation-garden-shed.yaml`)
- Comprehensive documentation:
  - Ansible dict2items fixes documentation
  - Garden Shed integration analysis
  - Modernization summary
  - Report consolidation summary
- Test framework with unit tests for core modules
- Garden Shed wrapper script (`scripts/garden_shed_wrapper.py`)

### Changed
- Updated `.gitignore` for better exclusion patterns
- Enhanced `check-lab.sh` script
- Modified existing validation playbooks for improved functionality
- Updated iLO utilities (`library/ilo_utils.py`)
- Enhanced process iLO results module (`library/process_ilo_results.py`)
- Improved MAC address validation playbook
- Updated DNS validation playbook
- Enhanced report generation playbook
- Updated detailed baseline collection playbook
- Improved site playbook configuration
- Enhanced HTML report templates:
  - Firmware report template
  - Main validation report template
  - Network configuration report template
- Updated main validation report script template
- Moved legacy playbooks to `playbooks/legacy/` directory:
  - Legacy IPMI enumeration
  - Legacy firmware update
  - Legacy network validation
- **BREAKING**: Migrated Garden Shed module to external submodule:
  - Added `garden-shed` as git submodule at `external/garden-shed/`
  - Removed local `library/garden_shed.py` in favor of submodule version
  - Updated import paths in test files and wrapper scripts

### Fixed
- Ansible dict2items compatibility issues (comprehensive fixes completed)
- Various modernization improvements for better maintainability

## [0.1.0] - 2025-05-08

### Added
- Initial project creation
- Basic directory structure
- Main validation script framework
- Documentation structure
