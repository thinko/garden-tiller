#!/usr/bin/env python3
"""
Garden-Tiller: Network Discovery Orchestrator
Orchestrates network discovery tasks to generate a JSON inventory for Garden-Tiller.
"""

import argparse
import subprocess
import sys
import os
import time
import re # Added for arp-scan output parsing
import shutil # Added for copying nmap_xml_input
import json # Added for writing error JSON in _convert_nmap_xml_to_json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

import structlog
# import pybreaker # Will add later when implementing circuit breakers

# Configure structured logging (basic configuration, can be enhanced like clean_boot_lacp_orchestrator.py)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),  # Human-readable output for now
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Define default values
DEFAULT_OUTPUT_DIR = Path("reports/discovery_output")
DEFAULT_TCPDUMP_DURATION = 120  # seconds
DEFAULT_INTERFACE = "eth0" # This might need to be discovered or error if not present

class NetworkDiscoveryOrchestrator:
    def __init__(self,
                 interface: str,
                 output_dir: Path,
                 tcpdump_duration: int,
                 nmap_list_scan_targets: Optional[str] = None, # New argument
                 skip_pcap: bool = False,
                 skip_arp: bool = False,
                 skip_nmap_list_scan: bool = False, # New argument
                 skip_nmap_ping_scan: bool = False, # New argument
                 nmap_xml_input: Optional[Path] = None):
        self.interface = interface
        self.output_dir = output_dir
        self.tcpdump_duration = tcpdump_duration
        self.nmap_list_scan_targets = nmap_list_scan_targets
        self.skip_pcap = skip_pcap
        self.skip_arp = skip_arp
        self.skip_nmap_list_scan = skip_nmap_list_scan
        self.skip_nmap_ping_scan = skip_nmap_ping_scan
        self.skip_ansible_trigger = False # Will be set by arg
        self.cleanup_temp_files = False # Will be set by arg
        self.nmap_xml_input = nmap_xml_input

        self.host_list_file = self.output_dir / "local-hosts.txt"
        self.nmap_full_scan_xml = self.output_dir / "nmap-full-scan.xml"
        self.final_inventory_json = self.output_dir / "inventory.json"

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Output directory", path=str(self.output_dir))

    def validate_prerequisites(self) -> bool:
        """Validate that all necessary command-line tools are available."""
        logger.info("Validating prerequisites...")
        tools = {
            "tcpdump": "Required for passive traffic capture.",
            "tshark": "Required for processing PCAP files.",
            "arp-scan": "Required for local network host discovery.",
            "nmap": "Required for active scanning and service enumeration.",
            "ansible-playbook": "Required for triggering Ansible playbooks."
        }
        all_tools_found = True

        for tool, desc in tools.items():
            tool_found_custom = False
            try:
                if tool == "arp-scan":
                    # arp-scan doesn't have a reliable --version that exits 0
                    # Check presence by running `arp-scan --help` and looking for usage string
                    result = subprocess.run([tool, "--help"], capture_output=True, text=True, timeout=5)
                    if "Usage: arp-scan" in result.stdout or "Usage: arp-scan" in result.stderr:
                        logger.info(f"Tool '{tool}' found (via --help).", description=desc)
                        tool_found_custom = True
                    else:
                        raise FileNotFoundError # Or some other error to indicate not found as expected
                elif tool == "tcpdump":
                    # tcpdump --version exits 0
                    subprocess.run([tool, "--version"], capture_output=True, text=True, check=True, timeout=5)
                    logger.info(f"Tool '{tool}' found (via --version).", description=desc)
                    tool_found_custom = True
                else: # tshark, nmap, ansible-playbook
                    subprocess.run([tool, "--version"], capture_output=True, text=True, check=True, timeout=5)
                    logger.info(f"Tool '{tool}' found (via --version).", description=desc)
                    tool_found_custom = True

            except FileNotFoundError:
                logger.error(f"Tool '{tool}' not found. {desc}", tool=tool)
                all_tools_found = False
            except subprocess.CalledProcessError as e:
                logger.error(f"Tool '{tool}' found, but version/help check command failed.",
                             tool=tool, error=str(e.stderr), description=desc)
                all_tools_found = False # Treat as missing if version check fails this way
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout checking for tool '{tool}'. {desc}", tool=tool)
                all_tools_found = False
            except Exception as e: # Catch any other unexpected errors
                logger.error(f"An unexpected error occurred while checking for tool '{tool}'. {desc}",
                             tool=tool, error=str(e))
                all_tools_found = False

            if not tool_found_custom and not all_tools_found and tool in tools: # Ensure we mark as false if custom check didn't pass
                 # This condition might be redundant if all_tools_found is set correctly in each except block
                 pass


        if not all_tools_found:
            logger.critical("One or more required tools are missing or failed verification. Please install/fix them to proceed.")
            return False

        logger.info("All essential prerequisites validated.")
        return True

    def run_pipeline(self):
        """Execute the full network discovery pipeline."""
        logger.info("Starting network discovery pipeline...")

        if not self.validate_prerequisites():
            sys.exit(1)

        # Placeholder for pipeline steps
        logger.info("Pipeline steps would run here.")
        # Step 1: Passive Recon (tcpdump, tshark)
        # Step 2: Active Discovery Local (arp-scan)
        # Step 3: Nmap Scans (list, ping, full)
        # Step 4: (Covered by Nmap scripts and JSON parsing)
        # Step 1: Passive Recon (tcpdump, tshark)
        self.passive_recon_results: Set[str] = set() # Store unique IPs from PCAP

        if not self.skip_pcap:
            pcap_file = self._run_tcpdump()
            if pcap_file:
                self.passive_recon_results = self._process_pcap(pcap_file)
        else:
            logger.info("Skipping PCAP capture and analysis phase.")

        # Step 2: Active Discovery Local (arp-scan)
        self.arp_scan_hosts: Set[str] = set()
        if not self.skip_arp:
            self.arp_scan_hosts = self._run_arp_scan_and_extract_ips()
            # Write these hosts to local-hosts.txt, which will be the primary input for Nmap
            try:
                with open(self.host_list_file, 'w') as f:
                    for ip in sorted(list(self.arp_scan_hosts)): # Sort for consistent output
                        f.write(f"{ip}\n")
                if self.arp_scan_hosts:
                    logger.info(f"ARP scan results written to {self.host_list_file}", count=len(self.arp_scan_hosts))
                else:
                    logger.info(f"ARP scan found no hosts. {self.host_list_file} is empty or not updated from this step.")
            except IOError as e:
                logger.error(f"Failed to write ARP scan results to {self.host_list_file}", error=str(e))
        else:
            logger.info("Skipping ARP scan phase.")
            # If ARP is skipped, local-hosts.txt might not be created or might be from a previous run.
            # Nmap steps should handle an empty or missing local-hosts.txt.


        # Step 3: Nmap Scans (list, ping, full)
        if not self.nmap_xml_input or not self.nmap_xml_input.exists(): # Only run Nmap scans if not using a pre-existing XML
            self._run_nmap_list_scan()
            self._run_nmap_ping_scan()
            self._run_nmap_full_scan()
            # Ensure nmap_full_scan_xml is correctly set even if using provided input
        elif self.nmap_xml_input and self.nmap_xml_input.exists():
            logger.info(f"Using provided Nmap XML input: {self.nmap_xml_input}. Skipping live Nmap scans.")
            # Ensure the main XML path is correctly pointing to the user's file or a copy
            if self.nmap_xml_input != self.nmap_full_scan_xml:
                try:
                    import shutil
                    shutil.copy(str(self.nmap_xml_input), str(self.nmap_full_scan_xml))
                    logger.info(f"Copied provided Nmap XML to expected location: {self.nmap_full_scan_xml}")
                except Exception as e:
                    logger.error(f"Failed to copy provided Nmap XML from {self.nmap_xml_input} to {self.nmap_full_scan_xml}.", error=str(e))
                    # This could be critical, subsequent steps might fail.
            else:
                # nmap_xml_input is already the target nmap_full_scan_xml
                pass


        # Step 4: (Covered by Nmap scripts and JSON parsing during Step 5)

        # Step 5: Data Transformation (convert_nmap_to_json.py)
        self._convert_nmap_xml_to_json()

        # Step 6: Ansible Integration
        if not self.skip_ansible_trigger:
            if self.final_inventory_json.exists() and self.final_inventory_json.stat().st_size > 0 :
                self._trigger_ansible_playbook()
            else:
                logger.warning(f"Ansible trigger skipped: Final inventory JSON '{self.final_inventory_json}' is missing or empty.")
        else:
            logger.info("Skipping Ansible playbook trigger step as per --skip-ansible-trigger.")

        if self.cleanup_temp_files:
            self._cleanup_temporary_files()

        logger.info("Network discovery pipeline finished.")


    def _cleanup_temporary_files(self) -> None:
        """Remove intermediate files created during the discovery process."""
        logger.info("Cleaning up temporary files...")
        files_to_remove = [
            self.output_dir / "initial_capture.pcap",
            self.host_list_file, # local-hosts.txt
            self.output_dir / "nmap_list_scan_output.txt",
            self.output_dir / "nmap_ping_scan_output.gnmap",
        ]
        # Note: nmap-full-scan.xml and inventory.json are considered primary outputs and are NOT removed.

        for file_path in files_to_remove:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Removed temporary file: {file_path}")
                else:
                    logger.debug(f"Temporary file not found for cleanup (already removed or never created): {file_path}")
            except OSError as e:
                logger.warning(f"Failed to remove temporary file {file_path}", error=str(e))
        logger.info("Temporary file cleanup complete.")


    def _trigger_ansible_playbook(self) -> None:
        """Trigger the main Ansible playbook (site.yaml) with discovery data."""
        logger.info("Attempting to trigger Ansible playbook 'playbooks/site.yaml'.")

        # Determine the project root directory to correctly locate playbooks and inventory
        # Assuming this script is in project_root/scripts/
        project_root = Path(__file__).parent.parent
        playbook_path = project_root / "playbooks" / "site.yaml"

        # Using a dummy inventory or a standard one if required by site.yaml structure for localhost tasks
        # The actual hosts will be added dynamically by 00-process-discovery.yaml
        # For simplicity, let's assume 'inventories/hosts.yaml' exists and can be used,
        # or that site.yaml's initial plays run on localhost.
        inventory_path = project_root / "inventories" / "hosts.yaml" # Default inventory

        if not playbook_path.exists():
            logger.error(f"Ansible playbook site.yaml not found at expected location: {playbook_path}")
            return

        if not inventory_path.exists():
            logger.warning(f"Default Ansible inventory not found at {inventory_path}. "
                           "Playbook execution might fail if it requires it for initial connection/localhost tasks.")
            # Proceeding anyway, as dynamic inventory is the key for discovered hosts.

        cmd = [
            "ansible-playbook",
            str(playbook_path),
            "-i", str(inventory_path), # Provide a base inventory
            "--extra-vars", f"discovery_json_file={str(self.final_inventory_json.resolve())}"
            # Pass absolute path to the JSON
        ]

        try:
            logger.info(f"Executing Ansible playbook: {' '.join(cmd)}")
            # Set a long timeout as Ansible playbooks can take a while
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600) # 1 hour timeout

            logger.info("Ansible playbook executed successfully.")
            if result.stdout:
                logger.debug("Ansible playbook stdout:", playbook_stdout=result.stdout)
            if result.stderr: # Ansible often uses stderr for verbose info too
                logger.debug("Ansible playbook stderr:", playbook_stderr=result.stderr)

        except FileNotFoundError:
            logger.error("ansible-playbook command not found. Please ensure Ansible is installed and in PATH.")
        except subprocess.CalledProcessError as e:
            logger.error("Ansible playbook execution failed.",
                         cmd=' '.join(e.cmd),
                         return_code=e.returncode,
                         stdout=e.stdout, # Full stdout/stderr can be very verbose, consider summarizing
                         stderr=e.stderr)
        except subprocess.TimeoutExpired:
            logger.error("Ansible playbook execution timed out.")
        except Exception as e:
            logger.error("An unexpected error occurred while triggering Ansible playbook.",
                         error=str(e), exc_info=True)


    def _run_nmap_list_scan(self) -> None:
        """Run Nmap list scan (-sL) if target is provided."""
        if self.skip_nmap_list_scan or not self.nmap_list_scan_targets:
            logger.info("Skipping Nmap list scan phase or no targets specified.")
            return

        logger.info(f"Starting Nmap list scan for targets: {self.nmap_list_scan_targets}")
        output_file = self.output_dir / "nmap_list_scan_output.txt"
        cmd = ["nmap", "-sL", self.nmap_list_scan_targets, "-oN", str(output_file)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180) # 3 min timeout
            logger.info("Nmap list scan completed.", output_file=str(output_file), stdout=result.stdout[:200])
        except FileNotFoundError:
            logger.error("nmap command not found. Please ensure it's installed.")
        except subprocess.CalledProcessError as e:
            logger.error("Nmap list scan failed.", error=e.stderr, stdout=e.stdout)
        except subprocess.TimeoutExpired:
            logger.error(f"Nmap list scan timed out for targets: {self.nmap_list_scan_targets}")
        except Exception as e:
            logger.error("An unexpected error occurred during Nmap list scan.", error=str(e), exc_info=True)


    def _run_nmap_ping_scan(self) -> None:
        """Run Nmap ping scan (-sn) on hosts from local-hosts.txt and update the file with live hosts."""
        if self.skip_nmap_ping_scan:
            logger.info("Skipping Nmap ping scan phase.")
            return

        if not self.host_list_file.exists() or self.host_list_file.stat().st_size == 0:
            logger.warning(f"Host list file '{self.host_list_file}' is empty or does not exist. Skipping Nmap ping scan.")
            return

        logger.info(f"Starting Nmap ping scan (-sn) using host list: {self.host_list_file}")
        grepable_output_file = self.output_dir / "nmap_ping_scan_output.gnmap"

        cmd = ["nmap", "-sn", "-iL", str(self.host_list_file), "-oG", str(grepable_output_file), "--stats-every", "30s"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600) # 10 min timeout
            logger.info("Nmap ping scan completed.", gnmap_file=str(grepable_output_file))

            # Parse grepable output to find live hosts
            live_hosts = set()
            if grepable_output_file.exists():
                with open(grepable_output_file, 'r') as f:
                    for line in f:
                        # Example line for a live host: Host: 192.168.1.1 () Status: Up
                        if "Status: Up" in line:
                            parts = line.split()
                            if len(parts) > 1 and parts[0] == "Host:":
                                ip = parts[1]
                                live_hosts.add(ip)

            if live_hosts:
                logger.info(f"Nmap ping scan identified {len(live_hosts)} live hosts. Updating {self.host_list_file}.")
                try:
                    with open(self.host_list_file, 'w') as f:
                        for ip in sorted(list(live_hosts)):
                            f.write(f"{ip}\n")
                    logger.info(f"Successfully updated {self.host_list_file} with live hosts from ping scan.")
                except IOError as e:
                    logger.error(f"Failed to write updated live host list to {self.host_list_file}", error=str(e))
            else:
                logger.warning(f"Nmap ping scan did not identify any live hosts from {self.host_list_file}. "
                               f"The file will not be updated by this step, or will be empty if it was created by arp-scan with no results.")
                # Decide if local-hosts.txt should be emptied if no hosts are up
                # Current behavior: if no live_hosts, it does not modify local-hosts.txt unless it was empty before.
                # If arp-scan found hosts, but ping-scan says none are up, local-hosts.txt will still contain arp-scan hosts.
                # This might be desired if ping scan is blocked but deep scan should still try.
                # For now, let's overwrite with empty if ping scan confirms none are up from the list.
                if self.host_list_file.exists(): # Ensure it exists before trying to overwrite
                    logger.info(f"Overwriting {self.host_list_file} as empty since ping scan found no live hosts from the list.")
                    try:
                        with open(self.host_list_file, 'w') as f:
                            pass # Write empty file
                    except IOError as e:
                         logger.error(f"Failed to overwrite {self.host_list_file} as empty.", error=str(e))


        except FileNotFoundError:
            logger.error("nmap command not found. Please ensure it's installed.")
        except subprocess.CalledProcessError as e:
            # Nmap -sn can return non-zero if all hosts are down. This might not be a script error.
            if "0 hosts up" in e.stdout or "0 hosts up" in e.stderr:
                 logger.info("Nmap ping scan completed: 0 hosts found up.", gnmap_file=str(grepable_output_file))
                 if self.host_list_file.exists(): # Ensure it exists before trying to overwrite
                    logger.info(f"Overwriting {self.host_list_file} as empty since ping scan found no live hosts.")
                    try:
                        with open(self.host_list_file, 'w') as f:
                            pass # Write empty file
                    except IOError as e:
                         logger.error(f"Failed to overwrite {self.host_list_file} as empty.", error=str(e))
            else:
                logger.error("Nmap ping scan failed.", error=e.stderr, stdout=e.stdout)
        except subprocess.TimeoutExpired:
            logger.error(f"Nmap ping scan timed out using host list: {self.host_list_file}")
        except Exception as e:
            logger.error("An unexpected error occurred during Nmap ping scan.", error=str(e), exc_info=True)

    def _run_nmap_full_scan(self) -> None:
        """Run Nmap full scan (-Pn -A -p-) on hosts from local-hosts.txt."""
        if self.nmap_xml_input and self.nmap_xml_input.exists():
            logger.info(f"Skipping Nmap full scan, using provided XML input: {self.nmap_xml_input}")
            # Copy the provided XML to the expected output location if it's different
            if self.nmap_xml_input != self.nmap_full_scan_xml:
                try:
                    shutil.copy(str(self.nmap_xml_input), str(self.nmap_full_scan_xml))
                    logger.info(f"Copied provided Nmap XML to {self.nmap_full_scan_xml}")
                except Exception as e:
                    logger.error(f"Failed to copy provided Nmap XML.", source=self.nmap_xml_input, dest=self.nmap_full_scan_xml, error=str(e))
                    # Indicate that the primary XML file might be missing for subsequent steps
                    return # Do not proceed with scan if copy fails and was intended
            return

        if not self.host_list_file.exists() or self.host_list_file.stat().st_size == 0:
            logger.warning(f"Host list file '{self.host_list_file}' is empty or does not exist. Skipping Nmap full scan.")
            return

        logger.info(f"Starting Nmap full scan (-Pn -A -p-) using host list: {self.host_list_file}. Output XML: {self.nmap_full_scan_xml}")

        if os.geteuid() != 0:
            logger.warning("Nmap full scan with OS detection (-A) often requires root privileges for best results. Attempting with sudo.")

        cmd = [
            "sudo", "nmap", "-Pn", "-A", "-p-",
            "-iL", str(self.host_list_file),
            "-oX", str(self.nmap_full_scan_xml),
            "--stats-every", "60s" # Provide updates for long scans
        ]

        try:
            # This can be a very long process
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=7200) # 2 hour timeout
            logger.info("Nmap full scan completed.", xml_file=str(self.nmap_full_scan_xml), summary=result.stdout.split("Nmap done:")[-1])
        except FileNotFoundError:
            logger.error("nmap command not found. Please ensure it's installed.")
        except subprocess.CalledProcessError as e:
            logger.error("Nmap full scan failed.", error=e.stderr, stdout=e.stdout)
        except subprocess.TimeoutExpired:
            logger.error(f"Nmap full scan timed out using host list: {self.host_list_file}. "
                         f"Partial results might be in {self.nmap_full_scan_xml}")
        except Exception as e:
            logger.error("An unexpected error occurred during Nmap full scan.", error=str(e), exc_info=True)


    def _convert_nmap_xml_to_json(self) -> None:
        """Convert the Nmap XML output to a structured JSON file."""
        logger.info(f"Attempting to convert Nmap XML {self.nmap_full_scan_xml} to JSON {self.final_inventory_json}.")

        if not self.nmap_full_scan_xml.exists():
            logger.error(f"Nmap XML file '{self.nmap_full_scan_xml}' does not exist. Cannot convert to JSON.")
            # Create an empty/error JSON to prevent downstream failures
            error_payload = {
                "scan_metadata": {"error": f"Source Nmap XML file not found: {self.nmap_full_scan_xml}"},
                "hosts": []
            }
            try:
                with open(self.final_inventory_json, 'w') as f:
                    json.dump(error_payload, f, indent=4)
                logger.info(f"Created error JSON file at {self.final_inventory_json}.")
            except Exception as e:
                logger.error(f"Failed to write error JSON file {self.final_inventory_json}.", error=str(e))
            return

        conversion_script_path = Path(sys.path[0]) / "convert_nmap_to_json.py"
        if not conversion_script_path.exists():
            # Fallback if sys.path[0] is not reliable (e.g. when installed as a package)
            # This assumes the script is in the same directory as the orchestrator
            conversion_script_path = Path(__file__).parent / "convert_nmap_to_json.py"

        if not conversion_script_path.exists():
            logger.error(f"Nmap to JSON conversion script not found at {conversion_script_path}. Cannot proceed.")
            return

        cmd = [
            sys.executable, # Use the same Python interpreter that's running this script
            str(conversion_script_path),
            str(self.nmap_full_scan_xml),
            str(self.final_inventory_json)
        ]

        try:
            logger.info(f"Executing Nmap to JSON conversion script: {' '.join(cmd)}")
            # Increased timeout as parsing large XML can take time
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300) # 5 min timeout

            # The conversion script itself logs success/failure to its stderr/stdout
            if result.stdout:
                logger.info("Conversion script stdout:", script_stdout=result.stdout.strip())
            if result.stderr: # The script uses stderr for its own info/error logging
                # Filter out "INFO:" messages from stderr to only log actual errors from the script
                script_errors = "\n".join([line for line in result.stderr.strip().split('\n') if "ERROR:" in line])
                script_infos = "\n".join([line for line in result.stderr.strip().split('\n') if "INFO:" in line])
                if script_infos:
                     logger.info("Conversion script internal logs (INFO):", script_stderr_info=script_infos)
                if script_errors:
                    logger.error("Conversion script reported errors:", script_stderr_errors=script_errors)
                elif not script_infos and not script_errors and result.stderr.strip(): # Non-categorized stderr
                    logger.warning("Conversion script stderr (uncategorized):", script_stderr_uncat=result.stderr.strip())


            if self.final_inventory_json.exists():
                logger.info(f"Nmap XML successfully converted to JSON: {self.final_inventory_json}")
            else:
                # This case should ideally be caught by check=True or error logs from script
                logger.error(f"Conversion script ran, but output JSON file {self.final_inventory_json} was not created.")

        except subprocess.CalledProcessError as e:
            logger.error("Nmap to JSON conversion script failed.",
                         cmd=' '.join(e.cmd),
                         return_code=e.returncode,
                         stdout=e.stdout.strip(),
                         stderr=e.stderr.strip())
        except subprocess.TimeoutExpired:
            logger.error(f"Nmap to JSON conversion script timed out after 300 seconds.",
                         xml_file=str(self.nmap_full_scan_xml))
        except Exception as e:
            logger.error("An unexpected error occurred while running the Nmap to JSON conversion script.",
                         error=str(e), exc_info=True)


    def _run_tcpdump(self) -> Optional[Path]:
        """Run tcpdump to capture network traffic."""
        pcap_file = self.output_dir / "initial_capture.pcap"
        # Check if user has privileges for tcpdump (typically root)
        if os.geteuid() != 0:
            logger.warning("tcpdump usually requires root privileges. Attempting to run anyway.")
            # Consider asking for sudo password or erroring out if not root,
            # but for now, let it try and fail if permissions are insufficient.

        cmd = [
            "sudo", "tcpdump", "-i", self.interface,
            "-w", str(pcap_file),
            "-U"  # Write packets to file immediately (useful for live capture)
        ]

        logger.info(f"Starting tcpdump capture on {self.interface} for {self.tcpdump_duration} seconds. Output: {pcap_file}")

        try:
            # Run tcpdump in the background
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info(f"tcpdump process started with PID: {process.pid}")

            # Let other tasks run while tcpdump is capturing
            # For now, we'll just sleep here to simulate parallel work before waiting.
            # In a more complex scenario, this would be managed by async operations or threads.
            # For this linear script, we will wait for it after a conceptual "parallel" window.

            # Wait for tcpdump to finish (or timeout)
            # A more robust way for long captures would be to truly background it
            # and check on it later, or use a timer to send SIGINT.
            # For this script's purpose, Popen.wait with a timeout is okay.
            try:
                process.wait(timeout=self.tcpdump_duration + 5) # Give a little extra time for tcpdump to stop
            except subprocess.TimeoutExpired:
                logger.info(f"tcpdump capture duration of {self.tcpdump_duration}s reached. Stopping tcpdump...")
                # process.terminate() # Send SIGTERM
                # For tcpdump, SIGINT is usually preferred for graceful shutdown and flushing buffers
                subprocess.run(["sudo", "kill", "-INT", str(process.pid)])
                process.wait(timeout=10) # Wait for it to terminate

            stdout, stderr = process.communicate() # Get final output after termination

            if process.returncode is not None and process.returncode != 0 and not (process.returncode == -2 and "packets captured" in stderr.decode(errors='ignore')): # SIGINT often results in -2
                # tcpdump with SIGINT often exits with -2. stderr might contain "packets captured".
                # If it's not SIGINT or there's no "packets captured" message, it might be an actual error.
                # Example error: "tcpdump: eth0: You don't have permission to capture on that device"
                if "You don't have permission" in stderr.decode(errors='ignore'):
                     logger.error("tcpdump failed due to permission issues. Try running with sudo.",
                                  stderr=stderr.decode(errors='ignore'))
                elif "No such device" in stderr.decode(errors='ignore'):
                    logger.error(f"tcpdump failed: Interface '{self.interface}' not found or no permission.",
                                 stderr=stderr.decode(errors='ignore'))
                elif "packets captured" not in stderr.decode(errors='ignore'): # If SIGINT but no packets, still log
                    logger.warning(f"tcpdump exited with code {process.returncode} but might be okay (e.g. due to SIGINT).",
                                 stdout=stdout.decode(errors='ignore'),
                                 stderr=stderr.decode(errors='ignore'))

            if pcap_file.exists() and pcap_file.stat().st_size > 0:
                logger.info("tcpdump capture completed.", file=str(pcap_file), size=pcap_file.stat().st_size)
                return pcap_file
            elif pcap_file.exists():
                logger.warning("tcpdump completed, but PCAP file is empty.", file=str(pcap_file))
                return None # Or pcap_file if downstream can handle empty
            else:
                logger.error("tcpdump did not create the PCAP file.", file=str(pcap_file))
                return None

        except FileNotFoundError:
            logger.error("tcpdump command not found. Please ensure it's installed and in PATH.")
            return None
        except Exception as e:
            logger.error("An error occurred while running tcpdump.", error=str(e), exc_info=True)
            return None

    def _process_pcap(self, pcap_file: Path) -> set[str]:
        """Process PCAP file with tshark to extract unique IP addresses."""
        logger.info(f"Processing PCAP file: {pcap_file} with tshark.")
        unique_ips = set()

        cmd = [
            "tshark", "-r", str(pcap_file),
            "-T", "fields", "-e", "ip.src", "-e", "ip.dst",
            "-E", "separator=," # Use comma as separator for fields
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            output_lines = result.stdout.strip().split('\n')

            for line in output_lines:
                if not line.strip():
                    continue
                # Each line could have "ip_src,ip_dst" or just one if the other is not present (e.g. non-IP packet somehow)
                # Or if a packet is purely layer 2, it might be empty.
                parts = line.split(',')
                for part in parts:
                    ip = part.strip()
                    if ip: # Ensure it's not an empty string
                        # Basic validation for an IP address format (not exhaustive)
                        if '.' in ip and all(sub.isdigit() for sub in ip.split('.')):
                             unique_ips.add(ip)
                        elif ':' in ip: # Basic IPv6 check
                             unique_ips.add(ip)


            logger.info(f"Extracted {len(unique_ips)} unique IP addresses from PCAP.", ips=list(unique_ips)[:20]) # Log a sample
            return unique_ips

        except FileNotFoundError:
            logger.error("tshark command not found. Please ensure it's installed and in PATH. Cannot process PCAP.")
            return unique_ips # Return empty set
        except subprocess.CalledProcessError as e:
            logger.error("tshark processing failed.", error=str(e.stderr), stdout=e.stdout)
            return unique_ips
        except subprocess.TimeoutExpired:
            logger.error("tshark processing timed out.", pcap_file=str(pcap_file))
            return unique_ips
        except Exception as e:
            logger.error("An error occurred during PCAP processing with tshark.", error=str(e), exc_info=True)
            return unique_ips

    def _run_arp_scan_and_extract_ips(self) -> set[str]:
        """Run arp-scan to discover local hosts and extract their IP addresses."""
        logger.info(f"Starting arp-scan on interface {self.interface}.")
        discovered_ips = set()

        if os.geteuid() != 0:
            logger.warning("arp-scan usually requires root privileges. Attempting to run with sudo.")

        cmd = [
            "sudo", "arp-scan", "-I", self.interface,
            "--localnet", "--quiet", "--ignoredups", # --quiet to simplify output, --ignoredups for cleaner list
            "--parse", # Easier to parse output
        ]
        # Example output of arp-scan --localnet --parse:
        # 192.168.1.1\t00:11:22:33:44:55\tVendor Name
        # 192.168.1.10\tc0:ff:ee:c0:ff:ee\tAnother Vendor
        # ... (may include MAC and Vendor, or just IP if --quiet is very aggressive)
        # Using --parse should give structured output.
        # If --parse is not available on some versions, regex on default output is needed.
        # For now, assuming --parse is available. If not, will need to adjust.
        # The command `sudo arp-scan -I eth0 --localnet | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}'` was in the prompt.
        # This implies we might not need MAC/Vendor here, just IPs.
        # Let's stick to extracting IPs using a simpler arp-scan output or grep if necessary.
        # The prompt used: `sudo arp-scan -I eth0 --localnet | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}'`
        # This avoids parsing issues and directly gets IPs.

        # Alternative simpler command if only IPs are needed:
        # cmd_arp_scan_only_ips = f"sudo arp-scan -I {self.interface} --localnet | grep -oE '([0-9]{{1,3}}\\.){{3}}[0-9]{{1,3}}'"
        # Using shell=True for pipes is generally discouraged, so let's try to get IPs from structured output if possible,
        # or run two commands if not. The --parse flag is ideal.

        # Rechecking arp-scan capabilities: --parse is not a standard option for basic arp-scan.
        # The output format is typically: <IP address>\t<MAC address>\t<Vendor details>
        # So, we can split by tabs and take the first element.

        cmd_arp_scan = ["sudo", "arp-scan", "-I", self.interface, "--localnet", "--ignoredups"]


        try:
            # Using text=True for Python 3.7+
            result = subprocess.run(cmd_arp_scan, capture_output=True, text=True, check=True, timeout=60)
            output_lines = result.stdout.strip().split('\n')

            # Output example:
            # Interface: eth0, type: EN10MB, MAC: 00:0c:29:1c:bf:5e, IPv4: 192.168.1.100
            # Starting arp-scan 1.9.7 with 256 hosts (https://github.com/royhills/arp-scan)
            # 192.168.1.1   00:aa:bb:cc:dd:ee       Router Vendor Inc.
            # 192.168.1.10  00:11:22:33:44:55       Some Device Ltd.
            # ...
            # Ended arp-scan 1.9.7: 256 hosts scanned in 1.872 seconds (136.75 hosts/sec). 2 responded

            ip_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}") # Matches IP at the start of a line

            for line in output_lines:
                line = line.strip()
                match = ip_pattern.match(line)
                if match:
                    ip = match.group(0)
                    discovered_ips.add(ip)

            if discovered_ips:
                logger.info(f"arp-scan discovered {len(discovered_ips)} local hosts.", sample_ips=list(discovered_ips)[:10])
            else:
                logger.info("arp-scan did not discover any local hosts on this segment.")
            return discovered_ips

        except FileNotFoundError:
            logger.error("arp-scan command not found. Please ensure it's installed and in PATH.")
            return discovered_ips
        except subprocess.CalledProcessError as e:
            # arp-scan can exit with non-zero if no hosts are found on some versions/setups,
            # or if there are warnings, even if it partially succeeds.
            # Check stderr for common non-fatal messages.
            stderr_lower = e.stderr.lower()
            if "0 responded" in e.stdout or "0 responded" in stderr_lower:
                logger.info("arp-scan completed but found 0 responsive hosts.", stdout=e.stdout, stderr=e.stderr)
            elif "ioctl(SIOCSIFFLAGS)" in stderr_lower and "cannot assign requested address" in stderr_lower:
                 logger.error(f"arp-scan failed: Problem with interface '{self.interface}'. May not have an IP or is down.", stderr=e.stderr)
            elif "libnet_init() failed" in stderr_lower:
                 logger.error(f"arp-scan failed: libnet initialization error. Often a permissions issue or network interface problem.", stderr=e.stderr)
            else:
                logger.error("arp-scan execution failed.",
                             error=str(e), stdout=e.stdout, stderr=e.stderr)
            return discovered_ips # Return whatever might have been collected if any, or empty set
        except subprocess.TimeoutExpired:
            logger.error("arp-scan timed out.", interface=self.interface)
            return discovered_ips
        except Exception as e:
            logger.error("An error occurred during arp-scan.", error=str(e), exc_info=True)
            return discovered_ips


def main():
    parser = argparse.ArgumentParser(description="Network Discovery Orchestrator for Garden-Tiller")
    parser.add_argument("--interface", "-i", type=str, default=DEFAULT_INTERFACE,
                        help=f"Network interface for scanning (default: {DEFAULT_INTERFACE})")
    parser.add_argument("--output-dir", "-o", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Directory for output files (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--tcpdump-duration", "-d", type=int, default=DEFAULT_TCPDUMP_DURATION,
                        help=f"Duration for tcpdump capture in seconds (default: {DEFAULT_TCPDUMP_DURATION})")

    parser.add_argument("--skip-pcap", action="store_true",
                        help="Skip PCAP capture and analysis phase.")
    parser.add_argument("--skip-arp", action="store_true",
                        help="Skip ARP scan phase.")
    parser.add_argument("--nmap-list-scan-targets", type=str, default=None,
                        help="Target subnet range for Nmap list scan (e.g., '192.168.1.0/24'). Optional.")
    parser.add_argument("--skip-nmap-list-scan", action="store_true",
                        help="Skip Nmap list scan phase (-sL).")
    parser.add_argument("--skip-nmap-ping-scan", action="store_true",
                        help="Skip Nmap ping scan phase (-sn).")

    parser.add_argument("--nmap-xml-input", type=Path, default=None,
                        help="Path to an existing Nmap XML file to use instead of live scanning (for testing).")
    parser.add_argument("--skip-ansible-trigger", action="store_true",
                        help="Skip the final step of triggering the Ansible playbook.")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove temporary files created during discovery (e.g., pcap, intermediate nmap outputs). "
                             "Keeps main outputs: inventory.json and nmap-full-scan.xml.")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging (DEBUG level).")

    args = parser.parse_args()

    if args.verbose:
        # More verbose logging setup if desired, for now structlog's default is quite informative
        logger.info("Verbose logging enabled.") # structlog does not have levels in the same way as logging

    # Check if running as root if certain operations require it
    # if os.geteuid() != 0:
    #     logger.critical("This script may need to be run as root for tcpdump and arp-scan.")
    #     # sys.exit(1) # Decide if this is a hard exit or warning

    orchestrator = NetworkDiscoveryOrchestrator(
        interface=args.interface,
        output_dir=args.output_dir,
        tcpdump_duration=args.tcpdump_duration,
        nmap_list_scan_targets=args.nmap_list_scan_targets,
        skip_pcap=args.skip_pcap,
        skip_arp=args.skip_arp,
        skip_nmap_list_scan=args.skip_nmap_list_scan,
        skip_nmap_ping_scan=args.skip_nmap_ping_scan,
        skip_ansible_trigger=args.skip_ansible_trigger,
        cleanup_temp_files=args.cleanup,
        nmap_xml_input=args.nmap_xml_input
    )

    try:
        orchestrator.run_pipeline()
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error("Unhandled exception in pipeline", error=str(e), exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
