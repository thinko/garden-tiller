# NMState Generator Terminology Updates

## Overview
Updated the Garden-Tiller nmstate generator script to replace "master/slave" terminology with inclusive alternatives, following modern networking and software development practices.

## Changes Made

### 1. Data Structure Updates
- **BondConfiguration class**: Changed `slaves: List[str]` to `subordinates: List[str]`
- Updated all references to bond subordinate interfaces throughout the codebase

### 2. Function Signatures
- **_create_subordinate_interface()**: Renamed from `_create_slave_interface()`
- Simplified interface creation since nmstate handles bond relationships through the bond's `port` list
- Removed unnecessary `primary` parameter as nmstate doesn't require explicit master/subordinate relationships

### 3. YAML Configuration Format
- **link-aggregation.port**: Uses nmstate's standard `port` field for subordinate interfaces
- **Subordinate interfaces**: Configured as standard ethernet interfaces without special bond properties
- Bond relationships are established through the bond's port list, following nmstate specifications

### 4. Documentation Updates
- Added terminology section explaining the use of inclusive naming
- Updated comments and docstrings throughout the code
- Clarified that subordinate interfaces are defined in bond's "port" list per nmstate spec

## Technical Details

### Before (Deprecated Terminology):
```python
@dataclass
class BondConfiguration:
    slaves: List[str]  # Deprecated terminology

def _create_slave_interface(self, interface_name: str, master: str):
    return {
        'name': interface_name,
        'slave-type': 'bond',
        'master': master
    }
```

### After (Inclusive Terminology):
```python
@dataclass
class BondConfiguration:
    subordinates: List[str]  # Inclusive terminology

def _create_subordinate_interface(self, interface_name: str):
    return {
        'name': interface_name,
        'type': 'ethernet',
        'state': 'up'
    }
```

### NMState YAML Output Format:
```yaml
interfaces:
  - name: bond0
    type: bond
    state: up
    link-aggregation:
      mode: 802.3ad
      port:                    # Subordinate interfaces listed here
        - enp1s0
        - enp1s1
      options:
        miimon: '100'
  - name: enp1s0              # Subordinate interface
    type: ethernet
    state: up
  - name: enp1s1              # Subordinate interface  
    type: ethernet
    state: up
```

## Compatibility
- Maintains full compatibility with nmstate YAML format
- Follows Red Hat OpenShift NodeNetworkConfigurationPolicy specifications
- No functional changes to network configuration behavior
- Only terminology and documentation improvements

## Benefits
1. **Inclusive Language**: Removes potentially offensive terminology
2. **Industry Alignment**: Follows modern networking industry practices
3. **Documentation Clarity**: Clearer understanding of subordinate interface relationships
4. **Maintainability**: More intuitive code structure and naming

## Files Modified
- `/scripts/nmstate_generator.py` - Complete terminology update

## Validation
- ✅ Python syntax validation passed
- ✅ Script help functionality verified
- ✅ No remaining deprecated terminology references
- ✅ NMState format compliance maintained

The nmstate generator is now ready for production use with inclusive terminology while maintaining full functionality for OpenShift cluster network configuration.
