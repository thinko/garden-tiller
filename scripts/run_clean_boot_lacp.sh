#!/bin/bash
#
# Garden-Tiller: Clean Boot LACP Integration Script
# Integrates the clean boot LACP orchestrator with the existing check-lab.sh workflow
#

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LACP_ORCHESTRATOR="$SCRIPT_DIR/clean_boot_lacp_orchestrator.py"
INVENTORY_FILE="$PROJECT_ROOT/inventories/hosts.yaml"
RESULTS_DIR="$PROJECT_ROOT/reports"

# Logging configuration
LOG_FILE="$PROJECT_ROOT/logs/clean-boot-lacp-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$(dirname "$LOG_FILE")"

# Redirect all output to log file while also displaying on console
exec > >(tee -a "$LOG_FILE")
exec 2>&1

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $*" >&2
}

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites for clean boot LACP testing"
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root for network interface manipulation"
        exit 1
    fi
    
    # Check Python dependencies
    if ! python3 -c "import structlog, pybreaker, yaml" 2>/dev/null; then
        log_warning "Installing required Python dependencies"
        pip3 install structlog pybreaker pyyaml || {
            log_error "Failed to install Python dependencies"
            exit 1
        }
    fi
    
    # Check if orchestrator script exists
    if [[ ! -f "$LACP_ORCHESTRATOR" ]]; then
        log_error "LACP orchestrator script not found: $LACP_ORCHESTRATOR"
        exit 1
    fi
    
    # Check if inventory exists
    if [[ ! -f "$INVENTORY_FILE" ]]; then
        log_error "Inventory file not found: $INVENTORY_FILE"
        exit 1
    fi
    
    # Check Ansible installation
    if ! command -v ansible-playbook >/dev/null 2>&1; then
        log_error "Ansible not found. Please install Ansible."
        exit 1
    fi
    
    log_info "Prerequisites check completed successfully"
}

# Function to run pre-validation network checks
run_pre_validation() {
    log_info "Running pre-validation network checks"
    
    cd "$PROJECT_ROOT"
    
    # Run basic network discovery
    if ansible-playbook -i "$INVENTORY_FILE" playbooks/05-network-validation.yaml --tags discovery -v; then
        log_info "Pre-validation network checks completed successfully"
    else
        log_warning "Pre-validation checks had issues, but continuing with LACP tests"
    fi
}

# Function to run the main LACP orchestration
run_lacp_orchestration() {
    log_info "Starting clean boot LACP orchestration"
    
    cd "$PROJECT_ROOT"
    
    # Build command arguments
    local cmd_args=(
        "$LACP_ORCHESTRATOR"
        "--inventory" "$INVENTORY_FILE"
        "--results-dir" "$RESULTS_DIR"
        "--verbose"
    )
    
    # Add optional arguments based on environment variables
    if [[ "${NO_CLEAN_BOOT:-}" == "true" ]]; then
        cmd_args+=(--no-clean-boot)
    fi
    
    if [[ "${NO_PERMUTATIONS:-}" == "true" ]]; then
        cmd_args+=(--no-permutations)
    fi
    
    if [[ -n "${PARALLEL_HOSTS:-}" ]]; then
        cmd_args+=(--parallel-hosts "$PARALLEL_HOSTS")
    fi
    
    # Run the orchestrator
    log_info "Executing: python3 ${cmd_args[*]}"
    
    if python3 "${cmd_args[@]}"; then
        log_info "LACP orchestration completed successfully"
        return 0
    else
        log_error "LACP orchestration failed"
        return 1
    fi
}

# Function to generate integration report
generate_integration_report() {
    log_info "Generating integration report"
    
    local report_file="$RESULTS_DIR/clean_boot_lacp_integration_$(date +%Y%m%d_%H%M%S).html"
    
    cat > "$report_file" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Garden-Tiller Clean Boot LACP Integration Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #2E8B57; color: white; padding: 20px; }
        .summary { background-color: #f0f8f0; padding: 15px; margin: 20px 0; }
        .section { margin: 20px 0; }
        .success { color: #008000; }
        .error { color: #ff0000; }
        .warning { color: #ff8c00; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Garden-Tiller Clean Boot LACP Integration Report</h1>
        <p>Generated on: $(date)</p>
    </div>
    
    <div class="summary">
        <h2>Executive Summary</h2>
        <p>This report summarizes the results of comprehensive LACP validation testing performed in a clean boot scenario.</p>
    </div>
    
    <div class="section">
        <h2>Test Configuration</h2>
        <ul>
            <li><strong>Inventory File:</strong> $INVENTORY_FILE</li>
            <li><strong>Results Directory:</strong> $RESULTS_DIR</li>
            <li><strong>Clean Boot Mode:</strong> ${NO_CLEAN_BOOT:-false}</li>
            <li><strong>All Permutations:</strong> ${NO_PERMUTATIONS:-false}</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>Results Files</h2>
        <p>Detailed results can be found in the following files:</p>
        <ul>
EOF
    
    # List recent result files
    find "$RESULTS_DIR" -name "clean_boot_lacp_results_*.json" -mtime -1 | while read -r file; do
        echo "            <li><a href=\"$(basename "$file")\">$(basename "$file")</a></li>" >> "$report_file"
    done
    
    cat >> "$report_file" << 'EOF'
        </ul>
    </div>
    
    <div class="section">
        <h2>Integration with Garden-Tiller</h2>
        <p>This LACP validation integrates with the Garden-Tiller lab validation suite to provide comprehensive network testing.</p>
        <p>Use the following command to run this test as part of the overall lab validation:</p>
        <pre>sudo ./scripts/run_clean_boot_lacp.sh</pre>
    </div>
    
    <div class="section">
        <h2>Next Steps</h2>
        <ol>
            <li>Review the detailed JSON results files</li>
            <li>Implement recommended configurations on production systems</li>
            <li>Update switch configurations based on compatibility findings</li>
            <li>Integrate successful configurations into infrastructure automation</li>
        </ol>
    </div>
</body>
</html>
EOF
    
    log_info "Integration report generated: $report_file"
}

# Function to cleanup on exit
cleanup() {
    log_info "Cleaning up temporary resources"
    
    # Kill any background processes
    if [[ -n "${ORCHESTRATOR_PID:-}" ]]; then
        if kill -0 "$ORCHESTRATOR_PID" 2>/dev/null; then
            log_info "Terminating orchestrator process $ORCHESTRATOR_PID"
            kill -TERM "$ORCHESTRATOR_PID" 2>/dev/null || true
            sleep 5
            kill -KILL "$ORCHESTRATOR_PID" 2>/dev/null || true
        fi
    fi
    
    # Restore network state if needed
    cd "$PROJECT_ROOT"
    if command -v ansible >/dev/null 2>&1 && [[ -f "$INVENTORY_FILE" ]]; then
        log_info "Ensuring network state is clean"
        ansible all -i "$INVENTORY_FILE" -m shell \
            -a "for bond in \$(ls /sys/class/net/ 2>/dev/null | grep bond || true); do ip link del \$bond 2>/dev/null || true; done" \
            --become 2>/dev/null || true
    fi
}

# Set up signal handlers
trap cleanup EXIT
trap 'log_info "Interrupted by user"; exit 130' INT TERM

# Main execution function
main() {
    log_info "Starting Garden-Tiller Clean Boot LACP Integration"
    log_info "Log file: $LOG_FILE"
    
    # Check prerequisites
    check_prerequisites
    
    # Run pre-validation
    run_pre_validation
    
    # Run main LACP orchestration
    if run_lacp_orchestration; then
        log_info "LACP orchestration completed successfully"
        
        # Generate integration report
        generate_integration_report
        
        log_info "Clean Boot LACP Integration completed successfully"
        log_info "Check results in: $RESULTS_DIR"
        log_info "Full log available at: $LOG_FILE"
        
        return 0
    else
        log_error "LACP orchestration failed"
        log_error "Check log file for details: $LOG_FILE"
        return 1
    fi
}

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Garden-Tiller Clean Boot LACP Integration Script

This script orchestrates comprehensive LACP validation testing in clean boot scenarios.
It integrates with the existing Garden-Tiller workflow to test all bonding mode 
permutations and track what works with switches.

OPTIONS:
    -h, --help          Show this help message
    --no-clean-boot     Skip clean boot environment preparation
    --no-permutations   Skip testing all permutations (faster testing)
    --parallel-hosts N  Number of hosts to test in parallel (default: 3)
    --inventory FILE    Ansible inventory file (default: inventories/hosts.yaml)
    --verbose           Enable verbose output

ENVIRONMENT VARIABLES:
    NO_CLEAN_BOOT       Set to 'true' to skip clean boot preparation
    NO_PERMUTATIONS     Set to 'true' to skip permutation testing
    PARALLEL_HOSTS      Number of parallel host tests

EXAMPLES:
    # Run full comprehensive testing
    sudo $0
    
    # Run without clean boot preparation
    sudo NO_CLEAN_BOOT=true $0
    
    # Run faster testing (no permutations)
    sudo $0 --no-permutations
    
    # Test with custom parallelism
    sudo $0 --parallel-hosts 5

REQUIREMENTS:
    - Must run as root
    - Ansible installed and configured
    - Python 3 with structlog, pybreaker, pyyaml
    - Valid inventory file with baremetal hosts

RESULTS:
    Results are saved to: $RESULTS_DIR
    Logs are saved to: $PROJECT_ROOT/logs/

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        --no-clean-boot)
            export NO_CLEAN_BOOT=true
            shift
            ;;
        --no-permutations)
            export NO_PERMUTATIONS=true
            shift
            ;;
        --parallel-hosts)
            export PARALLEL_HOSTS="$2"
            shift 2
            ;;
        --inventory)
            INVENTORY_FILE="$2"
            shift 2
            ;;
        --verbose)
            set -x
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Run main function
main "$@"
