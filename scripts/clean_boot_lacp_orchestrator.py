#!/usr/bin/env python3
"""
Garden-Tiller: Clean Boot LACP Orchestrator
Orchestrates comprehensive LACP validation testing in clean boot scenarios.

This script feeds the network validation playbook to perform exhaustive
LACP testing, tracking all bonding mode permutations and what works with switches.

Uses Structlog for logging and PyBreaker for fault tolerance as per coding standards.
"""

import json
import subprocess
import time
import yaml
import sys
import os
import signal
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import structlog
from pybreaker import CircuitBreaker

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Circuit breakers for resilient operations
ansible_breaker = CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    exclude=[KeyboardInterrupt]
)

network_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    exclude=[KeyboardInterrupt]
)

@dataclass
class TestSession:
    """Represents a complete test session"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    inventory_file: str
    clean_boot: bool
    test_permutations: bool
    hosts: List[str]
    results: Dict[str, Any]
    errors: List[str]

@dataclass
class HostTestResult:
    """Results for a specific host's LACP testing"""
    hostname: str
    interfaces_discovered: int
    configurations_tested: int
    successful_configs: int
    best_config: Optional[Dict[str, Any]]
    switch_compatibility: Dict[str, Any]
    performance_metrics: Dict[str, float]

class CleanBootLacpOrchestrator:
    """Main orchestrator class for clean boot LACP validation"""
    
    def __init__(self, 
                 inventory_file: str = "inventories/hosts.yaml",
                 playbook_dir: str = "playbooks",
                 results_dir: str = "reports"):
        self.inventory_file = Path(inventory_file)
        self.playbook_dir = Path(playbook_dir)
        self.results_dir = Path(results_dir)
        self.lacp_script = Path("scripts/lacp_validation_test.py")
        
        # Test configuration
        self.test_session: Optional[TestSession] = None
        self.shutdown_requested = False
        
        # Results tracking
        self.host_results: Dict[str, HostTestResult] = {}
        self.global_results: Dict[str, Any] = {}
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Ensure directories exist
        self.results_dir.mkdir(exist_ok=True)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info("Shutdown signal received", signal=signum)
        self.shutdown_requested = True
        
        if self.test_session:
            self.test_session.end_time = datetime.now()
            self._save_session_results()

    @ansible_breaker
    def validate_prerequisites(self) -> bool:
        """Validate that all prerequisites are met"""
        logger.info("Validating prerequisites")
        
        errors = []
        
        # Check if running as root
        if os.geteuid() != 0:
            errors.append("Script must be run as root for network interface manipulation")
        
        # Check inventory file
        if not self.inventory_file.exists():
            errors.append(f"Inventory file not found: {self.inventory_file}")
        
        # Check playbook directory
        if not self.playbook_dir.exists():
            errors.append(f"Playbook directory not found: {self.playbook_dir}")
        
        # Check LACP validation script
        if not self.lacp_script.exists():
            errors.append(f"LACP validation script not found: {self.lacp_script}")
        
        # Check Ansible installation
        try:
            result = subprocess.run(["ansible-playbook", "--version"], 
                                  capture_output=True, text=True, check=True)
            logger.info("Ansible version detected", version=result.stdout.split('\n')[0])
        except subprocess.CalledProcessError:
            errors.append("Ansible not found or not working")
        
        # Check Python dependencies
        try:
            import structlog, pybreaker, yaml
        except ImportError as e:
            errors.append(f"Missing Python dependency: {e}")
        
        # Validate inventory structure
        try:
            with open(self.inventory_file, 'r') as f:
                inventory = yaml.safe_load(f)
            
            if 'baremetal' not in inventory.get('all', {}).get('children', {}):
                errors.append("Inventory file missing 'baremetal' group")
            
        except Exception as e:
            errors.append(f"Invalid inventory file: {e}")
        
        if errors:
            for error in errors:
                logger.error("Prerequisite check failed", error=error)
            return False
        
        logger.info("All prerequisites validated successfully")
        return True

    @network_breaker
    def discover_baremetal_hosts(self) -> List[str]:
        """Discover baremetal hosts from inventory"""
        logger.info("Discovering baremetal hosts")
        
        try:
            result = subprocess.run([
                "ansible-inventory", "-i", str(self.inventory_file), 
                "--list", "--yaml"
            ], capture_output=True, text=True, check=True)
            
            inventory = yaml.safe_load(result.stdout)
            hosts = []
            
            # Extract baremetal hosts
            if 'baremetal' in inventory.get('all', {}).get('children', {}):
                baremetal_group = inventory['all']['children']['baremetal']
                if 'hosts' in baremetal_group:
                    hosts = list(baremetal_group['hosts'].keys())
            
            logger.info("Discovered baremetal hosts", count=len(hosts), hosts=hosts)
            return hosts
            
        except subprocess.CalledProcessError as e:
            logger.error("Failed to discover hosts", error=str(e))
            return []

    @ansible_breaker
    def prepare_clean_boot_environment(self) -> bool:
        """Prepare environment for clean boot testing"""
        logger.info("Preparing clean boot environment")
        
        try:
            # Run preliminary network validation to get baseline
            result = subprocess.run([
                "ansible-playbook", 
                "-i", str(self.inventory_file),
                str(self.playbook_dir / "05-network-validation.yaml"),
                "--tags", "discovery",
                "-v"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.warning("Baseline network validation had issues", 
                             stderr=result.stderr, stdout=result.stdout)
            
            # Clean up any existing bonds on all hosts
            cleanup_result = subprocess.run([
                "ansible", "baremetal", 
                "-i", str(self.inventory_file),
                "-m", "shell",
                "-a", "for bond in $(ls /sys/class/net/ | grep bond); do ip link del $bond 2>/dev/null || true; done",
                "--become"
            ], capture_output=True, text=True)
            
            logger.info("Clean boot environment prepared")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout preparing clean boot environment")
            return False
        except Exception as e:
            logger.error("Failed to prepare clean boot environment", error=str(e))
            return False

    @network_breaker
    def run_host_lacp_tests(self, hostname: str) -> HostTestResult:
        """Run comprehensive LACP tests for a specific host"""
        logger.info("Running LACP tests for host", hostname=hostname)
        
        start_time = time.time()
        
        try:
            # Create host-specific results directory
            host_results_dir = self.results_dir / f"lacp_results_{hostname}"
            host_results_dir.mkdir(exist_ok=True)
            
            # Run the LACP validation script on the target host
            output_file = host_results_dir / f"lacp_results_{hostname}_{int(time.time())}.json"
            
            result = subprocess.run([
                "ansible", hostname,
                "-i", str(self.inventory_file),
                "-m", "script",
                "-a", f"{self.lacp_script} --output {output_file} --verbose",
                "--become"
            ], capture_output=True, text=True, timeout=1800)  # 30 minute timeout
            
            # Parse results
            if result.returncode == 0:
                try:
                    # Try to retrieve the results file from the remote host
                    fetch_result = subprocess.run([
                        "ansible", hostname,
                        "-i", str(self.inventory_file),
                        "-m", "fetch",
                        "-a", f"src={output_file} dest={host_results_dir}/ flat=yes",
                    ], capture_output=True, text=True)
                    
                    # Load the results
                    local_results_file = host_results_dir / f"lacp_results_{hostname}_{int(time.time())}.json"
                    if local_results_file.exists():
                        with open(local_results_file, 'r') as f:
                            test_results = json.load(f)
                    else:
                        # Fallback: parse from stdout if file retrieval failed
                        test_results = self._parse_stdout_results(result.stdout)
                    
                except Exception as e:
                    logger.warning("Failed to parse results file", hostname=hostname, error=str(e))
                    test_results = self._parse_stdout_results(result.stdout)
            else:
                logger.error("LACP test failed for host", 
                           hostname=hostname, stderr=result.stderr)
                test_results = {"error": result.stderr}
            
            # Analyze results and create summary
            host_result = self._analyze_host_results(hostname, test_results)
            
            # Calculate performance metrics
            host_result.performance_metrics = {
                "total_test_time": time.time() - start_time,
                "avg_negotiation_time": self._calculate_avg_negotiation_time(test_results),
                "success_rate": (host_result.successful_configs / host_result.configurations_tested * 100) 
                              if host_result.configurations_tested > 0 else 0
            }
            
            logger.info("Host LACP tests completed", 
                       hostname=hostname,
                       successful=host_result.successful_configs,
                       total=host_result.configurations_tested)
            
            return host_result
            
        except subprocess.TimeoutExpired:
            logger.error("LACP tests timed out for host", hostname=hostname)
            return HostTestResult(
                hostname=hostname,
                interfaces_discovered=0,
                configurations_tested=0,
                successful_configs=0,
                best_config=None,
                switch_compatibility={},
                performance_metrics={"total_test_time": time.time() - start_time, "error": "timeout"}
            )
        except Exception as e:
            logger.error("LACP tests failed for host", hostname=hostname, error=str(e))
            return HostTestResult(
                hostname=hostname,
                interfaces_discovered=0,
                configurations_tested=0,
                successful_configs=0,
                best_config=None,
                switch_compatibility={},
                performance_metrics={"total_test_time": time.time() - start_time, "error": str(e)}
            )

    def _parse_stdout_results(self, stdout: str) -> Dict[str, Any]:
        """Parse results from stdout if JSON file isn't available"""
        try:
            # Look for JSON output in stdout
            lines = stdout.split('\n')
            json_start = -1
            json_end = -1
            
            for i, line in enumerate(lines):
                if line.strip().startswith('{'):
                    json_start = i
                if line.strip().endswith('}') and json_start != -1:
                    json_end = i
                    break
            
            if json_start != -1 and json_end != -1:
                json_text = '\n'.join(lines[json_start:json_end+1])
                return json.loads(json_text)
            
        except Exception as e:
            logger.warning("Failed to parse stdout results", error=str(e))
        
        return {"error": "Could not parse results", "stdout": stdout}

    def _analyze_host_results(self, hostname: str, test_results: Dict[str, Any]) -> HostTestResult:
        """Analyze test results for a host and create summary"""
        
        if "error" in test_results:
            return HostTestResult(
                hostname=hostname,
                interfaces_discovered=0,
                configurations_tested=0,
                successful_configs=0,
                best_config=None,
                switch_compatibility={"error": test_results["error"]},
                performance_metrics={}
            )
        
        # Extract key metrics
        interfaces_discovered = len(test_results.get('network_interfaces', []))
        
        successful_configs = test_results.get('test_summary', {}).get('successful_tests', 0)
        total_configs = test_results.get('test_summary', {}).get('total_tests', 0)
        
        # Find best configuration (fastest negotiation time with most interfaces)
        best_config = None
        best_score = 0
        
        for config in test_results.get('successful_configurations', []):
            # Score based on interface count and negotiation speed
            score = len(config.get('interfaces', [])) * 10 - config.get('negotiation_time', 60)
            if score > best_score:
                best_score = score
                best_config = config
        
        # Analyze switch compatibility
        switch_compatibility = self._analyze_switch_compatibility(test_results)
        
        return HostTestResult(
            hostname=hostname,
            interfaces_discovered=interfaces_discovered,
            configurations_tested=total_configs,
            successful_configs=successful_configs,
            best_config=best_config,
            switch_compatibility=switch_compatibility,
            performance_metrics={}
        )

    def _analyze_switch_compatibility(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze switch compatibility from test results"""
        compatibility = {
            "lacp_modes_working": [],
            "non_lacp_modes_working": [],
            "interface_combinations": {},
            "lacp_rate_preferences": {},
            "negotiation_times": {}
        }
        
        # Analyze by bonding mode
        for config in test_results.get('successful_configurations', []):
            mode = config.get('mode', 'unknown')
            iface_count = len(config.get('interfaces', []))
            
            if '802_3AD' in mode or 'LACP' in mode:
                if mode not in compatibility["lacp_modes_working"]:
                    compatibility["lacp_modes_working"].append(mode)
            else:
                if mode not in compatibility["non_lacp_modes_working"]:
                    compatibility["non_lacp_modes_working"].append(mode)
            
            # Track interface combinations
            if iface_count not in compatibility["interface_combinations"]:
                compatibility["interface_combinations"][iface_count] = []
            compatibility["interface_combinations"][iface_count].append(mode)
            
            # Track negotiation times by mode
            neg_time = config.get('negotiation_time', 0)
            if mode not in compatibility["negotiation_times"]:
                compatibility["negotiation_times"][mode] = []
            compatibility["negotiation_times"][mode].append(neg_time)
        
        return compatibility

    def _calculate_avg_negotiation_time(self, test_results: Dict[str, Any]) -> float:
        """Calculate average negotiation time across all successful tests"""
        times = []
        for config in test_results.get('successful_configurations', []):
            times.append(config.get('negotiation_time', 0))
        
        return sum(times) / len(times) if times else 0

    def run_parallel_tests(self, hosts: List[str], max_workers: int = 3) -> Dict[str, HostTestResult]:
        """Run LACP tests on multiple hosts in parallel"""
        logger.info("Running parallel LACP tests", hosts=hosts, max_workers=max_workers)
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all host tests
            future_to_host = {
                executor.submit(self.run_host_lacp_tests, host): host 
                for host in hosts
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_host):
                if self.shutdown_requested:
                    logger.info("Shutdown requested, cancelling remaining tests")
                    break
                
                host = future_to_host[future]
                try:
                    result = future.result(timeout=2400)  # 40 minute timeout per host
                    results[host] = result
                    logger.info("Host test completed", host=host)
                except Exception as e:
                    logger.error("Host test failed", host=host, error=str(e))
                    results[host] = HostTestResult(
                        hostname=host,
                        interfaces_discovered=0,
                        configurations_tested=0,
                        successful_configs=0,
                        best_config=None,
                        switch_compatibility={"error": str(e)},
                        performance_metrics={}
                    )
        
        return results

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate a comprehensive test report"""
        logger.info("Generating comprehensive test report")
        
        # Aggregate results across all hosts
        total_interfaces = sum(r.interfaces_discovered for r in self.host_results.values())
        total_configs_tested = sum(r.configurations_tested for r in self.host_results.values())
        total_successful = sum(r.successful_configs for r in self.host_results.values())
        
        # Find most compatible configurations
        mode_compatibility = {}
        for host_result in self.host_results.values():
            for mode in host_result.switch_compatibility.get("lacp_modes_working", []):
                if mode not in mode_compatibility:
                    mode_compatibility[mode] = 0
                mode_compatibility[mode] += 1
        
        # Create comprehensive report
        report = {
            "test_session": asdict(self.test_session) if self.test_session else {},
            "summary": {
                "total_hosts": len(self.host_results),
                "total_interfaces_discovered": total_interfaces,
                "total_configurations_tested": total_configs_tested,
                "total_successful_configurations": total_successful,
                "overall_success_rate": (total_successful / total_configs_tested * 100) 
                                      if total_configs_tested > 0 else 0
            },
            "host_results": {host: asdict(result) for host, result in self.host_results.items()},
            "compatibility_analysis": {
                "most_compatible_modes": sorted(mode_compatibility.items(), 
                                              key=lambda x: x[1], reverse=True),
                "universal_configurations": self._find_universal_configurations(),
                "performance_recommendations": self._generate_performance_recommendations()
            },
            "recommendations": self._generate_recommendations(),
            "timestamp": datetime.now().isoformat()
        }
        
        return report

    def _find_universal_configurations(self) -> List[Dict[str, Any]]:
        """Find configurations that work across all hosts"""
        universal_configs = []
        
        # Find configurations present in all hosts' successful configs
        if not self.host_results:
            return universal_configs
        
        # Get first host's successful configs as baseline
        first_host = list(self.host_results.values())[0]
        if not first_host.best_config:
            return universal_configs
        
        # This is a simplified approach - in a real implementation,
        # you'd do more sophisticated analysis
        baseline_mode = first_host.best_config.get('mode')
        
        # Check if this mode works on all hosts
        works_on_all = True
        for host_result in self.host_results.values():
            host_modes = host_result.switch_compatibility.get("lacp_modes_working", [])
            if baseline_mode not in host_modes:
                works_on_all = False
                break
        
        if works_on_all:
            universal_configs.append({
                "mode": baseline_mode,
                "description": f"Mode {baseline_mode} works across all tested hosts"
            })
        
        return universal_configs

    def _generate_performance_recommendations(self) -> List[str]:
        """Generate performance-based recommendations"""
        recommendations = []
        
        # Analyze negotiation times
        fast_modes = []
        for host_result in self.host_results.values():
            for mode, times in host_result.switch_compatibility.get("negotiation_times", {}).items():
                avg_time = sum(times) / len(times) if times else 0
                if avg_time < 5.0:  # Less than 5 seconds
                    fast_modes.append(mode)
        
        if fast_modes:
            recommendations.append(f"Fast negotiating modes: {', '.join(set(fast_modes))}")
        
        # Interface count recommendations
        max_interfaces = max((r.interfaces_discovered for r in self.host_results.values()), default=0)
        if max_interfaces >= 4:
            recommendations.append("Consider 4+ interface bonding for maximum throughput")
        
        return recommendations

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on test results"""
        recommendations = []
        
        # Success rate analysis
        total_configs = sum(r.configurations_tested for r in self.host_results.values())
        total_successful = sum(r.successful_configs for r in self.host_results.values())
        success_rate = (total_successful / total_configs * 100) if total_configs > 0 else 0
        
        if success_rate < 50:
            recommendations.append("Low success rate detected - check switch LACP configuration")
        elif success_rate > 80:
            recommendations.append("High success rate - network infrastructure appears well configured")
        
        # LACP specific recommendations
        lacp_working = any(
            result.switch_compatibility.get("lacp_modes_working")
            for result in self.host_results.values()
        )
        
        if lacp_working:
            recommendations.append("LACP negotiation successful - recommend 802.3ad mode for production")
        else:
            recommendations.append("LACP negotiation failed - consider active-backup mode")
        
        return recommendations

    def _save_session_results(self):
        """Save current session results"""
        if not self.test_session:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = self.results_dir / f"clean_boot_lacp_results_{timestamp}.json"
        
        report = self.generate_comprehensive_report()
        
        with open(results_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info("Session results saved", file=str(results_file))

    def run_comprehensive_test_suite(self, 
                                   clean_boot: bool = True,
                                   test_all_permutations: bool = True,
                                   parallel_hosts: int = 3) -> bool:
        """Run the comprehensive LACP test suite"""
        logger.info("Starting comprehensive LACP test suite")
        
        # Validate prerequisites
        if not self.validate_prerequisites():
            return False
        
        # Discover hosts
        hosts = self.discover_baremetal_hosts()
        if not hosts:
            logger.error("No baremetal hosts found")
            return False
        
        # Create test session
        self.test_session = TestSession(
            session_id=f"lacp_test_{int(time.time())}",
            start_time=datetime.now(),
            end_time=None,
            inventory_file=str(self.inventory_file),
            clean_boot=clean_boot,
            test_permutations=test_all_permutations,
            hosts=hosts,
            results={},
            errors=[]
        )
        
        try:
            # Prepare clean boot environment
            if clean_boot:
                if not self.prepare_clean_boot_environment():
                    self.test_session.errors.append("Failed to prepare clean boot environment")
                    return False
            
            # Run tests on all hosts
            self.host_results = self.run_parallel_tests(hosts, parallel_hosts)
            
            # Generate and save final report
            self.test_session.end_time = datetime.now()
            self._save_session_results()
            
            # Print summary
            self._print_summary()
            
            logger.info("Comprehensive LACP test suite completed successfully")
            return True
            
        except Exception as e:
            logger.error("Test suite failed", error=str(e))
            self.test_session.errors.append(str(e))
            self.test_session.end_time = datetime.now()
            self._save_session_results()
            return False

    def _print_summary(self):
        """Print a summary to console"""
        print("\n" + "="*80)
        print("CLEAN BOOT LACP VALIDATION SUMMARY")
        print("="*80)
        
        if self.test_session:
            print(f"Session ID: {self.test_session.session_id}")
            print(f"Duration: {self.test_session.end_time - self.test_session.start_time}")
            print(f"Hosts tested: {len(self.host_results)}")
        
        total_configs = sum(r.configurations_tested for r in self.host_results.values())
        total_successful = sum(r.successful_configs for r in self.host_results.values())
        
        print(f"Total configurations tested: {total_configs}")
        print(f"Successful configurations: {total_successful}")
        print(f"Success rate: {(total_successful/total_configs*100):.1f}%" if total_configs > 0 else "N/A")
        
        print("\nPer-Host Results:")
        for host, result in self.host_results.items():
            print(f"  {host}: {result.successful_configs}/{result.configurations_tested} successful")
            if result.best_config:
                print(f"    Best config: {result.best_config.get('mode', 'unknown')} "
                      f"({len(result.best_config.get('interfaces', []))} interfaces)")
        
        print(f"\nDetailed results saved to: {self.results_dir}")
        print("="*80)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean Boot LACP Orchestrator")
    parser.add_argument("--inventory", "-i", default="inventories/hosts.yaml",
                       help="Ansible inventory file")
    parser.add_argument("--playbook-dir", default="playbooks",
                       help="Playbook directory")
    parser.add_argument("--results-dir", default="reports",
                       help="Results output directory")
    parser.add_argument("--no-clean-boot", action="store_true",
                       help="Skip clean boot preparation")
    parser.add_argument("--no-permutations", action="store_true",
                       help="Skip testing all permutations")
    parser.add_argument("--parallel-hosts", type=int, default=3,
                       help="Number of hosts to test in parallel")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    # Check if running as root
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root for network interface manipulation")
        sys.exit(1)
    
    # Create orchestrator and run tests
    orchestrator = CleanBootLacpOrchestrator(
        inventory_file=args.inventory,
        playbook_dir=args.playbook_dir,
        results_dir=args.results_dir
    )
    
    try:
        success = orchestrator.run_comprehensive_test_suite(
            clean_boot=not args.no_clean_boot,
            test_all_permutations=not args.no_permutations,
            parallel_hosts=args.parallel_hosts
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Test suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Test suite failed", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
