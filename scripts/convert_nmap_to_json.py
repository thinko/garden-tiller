import xmltodict
import json
import sys
from pathlib import Path

# Basic logger, can be enhanced if needed
def log_info(message):
    print(f"INFO: {message}", file=sys.stderr)

def log_error(message):
    print(f"ERROR: {message}", file=sys.stderr)

def extract_script_output(port_or_host, script_id):
    """Helper to extract specific NSE script output."""
    if not isinstance(port_or_host.get('script'), list):
        scripts = [port_or_host.get('script')] if port_or_host.get('script') else []
    else:
        scripts = port_or_host.get('script', [])

    for script in scripts:
        if script and script.get('@id') == script_id:
            return script
    return None

def parse_host_data(nmap_host_dict):
    """Parses data for a single host from the Nmap XML dict."""
    host_data = {}

    # IP Address
    ip_address = None
    for addr in nmap_host_dict.get('address', []):
        if addr.get('@addrtype') == 'ipv4':
            ip_address = addr.get('@addr')
            break
        elif addr.get('@addrtype') == 'ipv6' and not ip_address: # Fallback to ipv6 if no ipv4
            ip_address = addr.get('@addr')
    if not ip_address: # Should always find one if it's a host entry
        return None
    host_data['ip_address'] = ip_address

    # Status
    status_elem = nmap_host_dict.get('status')
    host_data['status'] = status_elem.get('@state') if status_elem else 'unknown'
    host_data['status_reason'] = status_elem.get('@reason') if status_elem else 'unknown'

    # MAC Address and Vendor
    mac_address = None
    vendor = None
    for addr in nmap_host_dict.get('address', []):
        if addr.get('@addrtype') == 'mac':
            mac_address = addr.get('@addr')
            vendor = addr.get('@vendor')
            break
    host_data['mac_address'] = mac_address
    host_data['vendor'] = vendor

    # Hostnames
    hostnames_list = []
    hostnames_elem = nmap_host_dict.get('hostnames')
    if hostnames_elem:
        # Can be a list of 'hostname' dicts or a single 'hostname' dict
        current_hostnames = hostnames_elem.get('hostname', [])
        if not isinstance(current_hostnames, list):
            current_hostnames = [current_hostnames] if current_hostnames else []
        for h_elem in current_hostnames:
            if h_elem and h_elem.get('@name'):
                hostnames_list.append({
                    'name': h_elem.get('@name'),
                    'type': h_elem.get('@type')
                })
    host_data['hostnames'] = hostnames_list

    # OS Match
    os_info = {}
    os_elem = nmap_host_dict.get('os')
    if os_elem:
        os_matches = []
        # osmatch can be a list or a single dict
        osmatch_entries = os_elem.get('osmatch', [])
        if not isinstance(osmatch_entries, list):
            osmatch_entries = [osmatch_entries] if osmatch_entries else []

        for match in osmatch_entries:
            if match: # Ensure match is not None
                os_matches.append({
                    'name': match.get('@name'),
                    'accuracy': match.get('@accuracy'),
                    'line': match.get('@line')
                })
        if os_matches:
            os_info['os_matches'] = sorted(os_matches, key=lambda x: int(x['accuracy']), reverse=True) # Best guess first

        # OS Fingerprint (if available)
        os_fingerprint_elem = os_elem.get('osfingerprint')
        if os_fingerprint_elem and os_fingerprint_elem.get('@fingerprint'):
            os_info['os_fingerprint'] = os_fingerprint_elem.get('@fingerprint')
    host_data['os_info'] = os_info if os_info else None


    # Ports and Services
    ports_list = []
    ports_elem = nmap_host_dict.get('ports')
    if ports_elem:
        # 'port' can be a list of dicts or a single dict
        port_entries = ports_elem.get('port', [])
        if not isinstance(port_entries, list):
            port_entries = [port_entries] if port_entries else []

        for p_elem in port_entries:
            if not p_elem: continue
            port_data = {
                'protocol': p_elem.get('@protocol'),
                'port_id': int(p_elem.get('@portid')),
                'state': p_elem.get('state', {}).get('@state'),
                'reason': p_elem.get('state', {}).get('@reason'),
                'service': None,
                'nse_scripts': []
            }
            service_elem = p_elem.get('service')
            if service_elem:
                port_data['service'] = {
                    'name': service_elem.get('@name'),
                    'product': service_elem.get('@product'),
                    'version': service_elem.get('@version'),
                    'extrainfo': service_elem.get('@extrainfo'),
                    'method': service_elem.get('@method'),
                    'conf': service_elem.get('@conf'),
                    'cpe': service_elem.get('cpe') # Can be list or string
                }
                # Ensure CPE is always a list
                if port_data['service']['cpe'] and not isinstance(port_data['service']['cpe'], list):
                    port_data['service']['cpe'] = [port_data['service']['cpe']]


            # NSE Script output for the port
            current_scripts = p_elem.get('script', [])
            if not isinstance(current_scripts, list):
                current_scripts = [current_scripts] if current_scripts else []
            for script_out in current_scripts:
                if script_out:
                    port_data['nse_scripts'].append({
                        'id': script_out.get('@id'),
                        'output': script_out.get('@output')
                        # TODO: Parse table elements if needed more structured
                    })
            ports_list.append(port_data)
    host_data['ports'] = sorted(ports_list, key=lambda x: x['port_id'])


    # Host-level NSE Scripts (e.g. smb-os-discovery)
    host_scripts_elem = nmap_host_dict.get('hostscript')
    if host_scripts_elem:
        host_data['host_nse_scripts'] = []
        current_scripts = host_scripts_elem.get('script', [])
        if not isinstance(current_scripts, list):
            current_scripts = [current_scripts] if current_scripts else []
        for script_out in current_scripts:
            if script_out:
                 host_data['host_nse_scripts'].append({
                    'id': script_out.get('@id'),
                    'output': script_out.get('@output')
                })

    # iDRAC and iLO identification
    host_data['is_idrac'] = False # Default
    host_data['idrac_confidence_factors'] = {}
    host_data['ilo_info'] = None # Default

    # iDRAC check:
    # 1. MAC Vendor "Dell Inc."
    if vendor and "Dell" in vendor:
        host_data['idrac_confidence_factors']['mac_vendor_dell'] = True

    # 2. Port 443 open
    port_443_open = any(p['port_id'] == 443 and p['state'] == 'open' for p in host_data.get('ports', []))
    if port_443_open:
        host_data['idrac_confidence_factors']['port_443_open'] = True

    # 3. HTTP Title contains "iDRAC" (from http-title script on port 443)
    # 4. Redfish API endpoint /redfish/v1/ returns 200 (harder to check directly from typical Nmap XML,
    #    but http-title or http-headers on / might give clues if it's a Dell server page)
    for port_info in host_data.get('ports', []):
        if port_info['port_id'] == 443 and port_info['state'] == 'open':
            for script in port_info.get('nse_scripts', []):
                if script['id'] == 'http-title' and script['output'] and "iDRAC" in script['output']:
                    host_data['idrac_confidence_factors']['http_title_idrac'] = True
                # Check for Redfish might involve looking at http-robots.txt or specific known paths if scanned by NSE.
                # The `http-redfish-info` script would be ideal if run.
                if script['id'] == 'http-redfish-info' and script['output']: # Assuming this script was run
                     host_data['idrac_confidence_factors']['redfish_detected'] = True
                     # Could parse script['output'] for more details here.

    # High-confidence iDRAC signature
    if (host_data['idrac_confidence_factors'].get('mac_vendor_dell') and
        host_data['idrac_confidence_factors'].get('port_443_open') and
        host_data['idrac_confidence_factors'].get('http_title_idrac')):
        # Redfish is a strong indicator but might not always be available/scanned
        host_data['is_idrac'] = True


    # HP iLO check (from http-hp-ilo-info NSE script)
    # This script usually runs on common HTTP ports (80, 443) or specific iLO port 17988
    ilo_script_data = None
    for port_info in host_data.get('ports', []):
        for script in port_info.get('nse_scripts', []):
            if script['id'] == 'http-hp-ilo-info':
                ilo_script_data = script['output']
                break
        if ilo_script_data: break

    if ilo_script_data:
        # Parse the key-value output of http-hp-ilo-info
        # Example: \n  ServerType: ProLiant DL380 Gen9\n  ProductID: ...
        parsed_ilo_info = {}
        for line in ilo_script_data.strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                parsed_ilo_info[key.strip().replace(' ', '')] = val.strip() # Normalize key
        host_data['ilo_info'] = parsed_ilo_info
        if "Hewlett Packard" not in (host_data['vendor'] or "") and "HP" not in (host_data['vendor'] or "") :
             log_info(f"Host {ip_address} has iLO info but vendor is {host_data['vendor']}. Setting vendor to HP.")
             host_data['vendor'] = "Hewlett Packard" # Correct vendor if iLO is found

    return host_data


def convert_nmap_xml_to_json(xml_file_path, json_file_path):
    try:
        log_info(f"Attempting to read Nmap XML file: {xml_file_path}")
        with open(xml_file_path, 'r') as xml_file:
            xml_content = xml_file.read()

        if not xml_content.strip():
            log_error(f"Error: The XML file {xml_file_path} is empty.")
            # Create an empty JSON structure
            data_dict_transformed = {"scan_metadata": {"error": "Input XML file was empty"}, "hosts": []}
        else:
            nmap_dict = xmltodict.parse(xml_content)
            log_info("Nmap XML parsed successfully by xmltodict.")

            # Transform into desired JSON structure
            data_dict_transformed = {
                "scan_metadata": {},
                "hosts": []
            }

            nmaprun_info = nmap_dict.get('nmaprun', {})

            # Scan Metadata
            scan_metadata = data_dict_transformed["scan_metadata"]
            scan_metadata['nmap_version'] = nmaprun_info.get('@version')
            scan_metadata['args'] = nmaprun_info.get('@args')
            scan_metadata['start_time_str'] = nmaprun_info.get('@startstr')
            scan_metadata['start_time_unix'] = nmaprun_info.get('@start')

            scaninfo = nmaprun_info.get('scaninfo', {})
            if isinstance(scaninfo, list): # Take the first if multiple scaninfo blocks (unlikely for single run)
                scaninfo = scaninfo[0] if scaninfo else {}

            scan_metadata['scan_type'] = scaninfo.get('@type')
            scan_metadata['protocol'] = scaninfo.get('@protocol')
            scan_metadata['num_services'] = scaninfo.get('@numservices')

            runstats = nmaprun_info.get('runstats', {})
            if runstats:
                scan_metadata['finish_time_str'] = runstats.get('finished', {}).get('@timestr')
                scan_metadata['finish_time_unix'] = runstats.get('finished', {}).get('@time')
                scan_metadata['elapsed_seconds'] = runstats.get('finished', {}).get('@elapsed')
                scan_metadata['hosts_up'] = runstats.get('hosts', {}).get('@up')
                scan_metadata['hosts_down'] = runstats.get('hosts', {}).get('@down')
                scan_metadata['hosts_total'] = runstats.get('hosts', {}).get('@total')

            # Hosts data
            # nmaprun_info.get('host') can be a list of hosts or a single host dict
            nmap_hosts = nmaprun_info.get('host', [])
            if not isinstance(nmap_hosts, list):
                nmap_hosts = [nmap_hosts] if nmap_hosts else []

            for nmap_host_dict in nmap_hosts:
                if not nmap_host_dict: continue # Skip if empty host entry

                host_detail = parse_host_data(nmap_host_dict)
                if host_detail:
                    data_dict_transformed["hosts"].append(host_detail)

            log_info(f"Processed {len(data_dict_transformed['hosts'])} hosts.")

        # Write JSON output
        log_info(f"Writing JSON output to: {json_file_path}")
        with open(json_file_path, 'w') as json_file:
            json.dump(data_dict_transformed, json_file, indent=4)
        log_info(f"Successfully converted {xml_file_path} to {json_file_path}")

    except FileNotFoundError:
        log_error(f"Error: The file {xml_file_path} was not found.")
        # Create an empty JSON file or structure to avoid breaking pipeline
        empty_json = {"scan_metadata": {"error": f"Input XML file {xml_file_path} not found"}, "hosts": []}
        try:
            with open(json_file_path, 'w') as json_file:
                json.dump(empty_json, json_file, indent=4)
            log_info(f"Created empty JSON file at {json_file_path} due to missing input XML.")
        except Exception as dump_e:
            log_error(f"Could not even write empty JSON: {dump_e}")

    except Exception as e:
        log_error(f"An error occurred during XML to JSON conversion: {e}")
        # Also attempt to write an error JSON
        error_json = {"scan_metadata": {"error": f"Conversion failed: {e}"}, "hosts": []}
        try:
            with open(json_file_path, 'w') as json_file:
                json.dump(error_json, json_file, indent=4)
            log_info(f"Wrote error JSON to {json_file_path} due to conversion error.")
        except Exception as dump_e:
            log_error(f"Could not write error JSON: {dump_e}")
        sys.exit(1) # Exit with error if conversion fails catastrophically

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_nmap_to_json.py <input_nmap.xml> <output.json>", file=sys.stderr)
        sys.exit(1)

    input_xml_path = Path(sys.argv[1])
    output_json_path = Path(sys.argv[2])

    # Ensure output directory exists
    output_json_path.parent.mkdir(parents=True, exist_ok=True)

    convert_nmap_xml_to_json(input_xml_path, output_json_path)
