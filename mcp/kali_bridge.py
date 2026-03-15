#!/usr/bin/env python3

# This script connect the MCP AI agent to Kali Linux terminal and API Server.

# some of the code here was inspired from https://github.com/whit3rabbit0/project_astro , be sure to check them out

import sys
import os
import argparse
import logging
from typing import Dict, Any, Optional
import requests

from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_KALI_SERVER = "http://localhost:5000" # change to your linux IP
DEFAULT_REQUEST_TIMEOUT = 600  # 10 minutes default timeout for API requests

class KaliToolsClient:
    """Client for communicating with the Kali Linux Tools API Server"""
    
    def __init__(self, server_url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        """
        Initialize the Kali Tools Client
        
        Args:
            server_url: URL of the Kali Tools API Server
            timeout: Request timeout in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        logger.info(f"Initialized Kali Tools Client connecting to {server_url}")
        
    def safe_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform a GET request with optional query parameters.
        
        Args:
            endpoint: API endpoint path (without leading slash)
            params: Optional query parameters
            
        Returns:
            Response data as dictionary
        """
        if params is None:
            params = {}

        url = f"{self.server_url}/{endpoint}"

        try:
            logger.debug(f"GET {url} with params: {params}")
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}", "success": False}

    def safe_post(self, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a POST request with JSON data.
        
        Args:
            endpoint: API endpoint path (without leading slash)
            json_data: JSON data to send
            
        Returns:
            Response data as dictionary
        """
        url = f"{self.server_url}/{endpoint}"
        
        try:
            logger.debug(f"POST {url} with data: {json_data}")
            response = requests.post(url, json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}", "success": False}

    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute a generic command on the Kali server
        
        Args:
            command: Command to execute
            
        Returns:
            Command execution results
        """
        return self.safe_post("api/command", {"command": command})
    
    def check_health(self) -> Dict[str, Any]:
        """
        Check the health of the Kali Tools API Server
        
        Returns:
            Health status information
        """
        return self.safe_get("health")

def setup_mcp_server(kali_client: KaliToolsClient) -> FastMCP:
    """
    Set up the MCP server with all tool functions
    
    Args:
        kali_client: Initialized KaliToolsClient
        
    Returns:
        Configured FastMCP instance
    """
    mcp = FastMCP("kali-mcp")
    
    @mcp.tool()
    def nmap_scan(target: str, scan_type: str = "-sV", ports: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute an Nmap scan against a target.

        Args:
            target: The IP address or hostname to scan
            scan_type: Scan type (e.g., -sV for version detection)
            ports: Specific port or range to scan (e.g. "80", "80,443", "1-1000").
                   If empty, scans --top-ports 1000.
            additional_args: Additional Nmap arguments

        Returns:
            Scan results
        """
        port_arg = f"-p {ports}" if ports else "--top-ports 1000"
        scripts  = "--script vuln,http-enum,http-title,http-auth-finder,http-headers"
        cmd = f"nmap {scan_type} {port_arg} {scripts} {target}"
        if additional_args:
            cmd += f" {additional_args}"
        return kali_client.execute_command(cmd)

    @mcp.tool()
    def gobuster_scan(url: str, mode: str = "dir", wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Gobuster to find directories, DNS subdomains, or virtual hosts.

        Args:
            url: The target URL
            mode: Scan mode (dir, dns, fuzz, vhost)
            wordlist: Path to wordlist file
            additional_args: Additional Gobuster arguments

        Returns:
            Scan results
        """
        cmd = f"timeout 300 gobuster {mode} -u {url} -w {wordlist} -t 100 -q"
        if additional_args:
            cmd += f" {additional_args}"
        return kali_client.execute_command(cmd)

    @mcp.tool()
    def dirb_scan(url: str, wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Dirb web content scanner.
        
        Args:
            url: The target URL
            wordlist: Path to wordlist file
            additional_args: Additional Dirb arguments
            
        Returns:
            Scan results
        """
        data = {
            "url": url,
            "wordlist": wordlist,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/dirb", data)

    @mcp.tool()
    def nikto_scan(target: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Nikto web server scanner.
        
        Args:
            target: The target URL or IP
            additional_args: Additional Nikto arguments
            
        Returns:
            Scan results
        """
        data = {
            "target": target,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/nikto", data)

    @mcp.tool()
    def sqlmap_scan(url: str, data: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Run sqlmap SQL injection scanner (auto-detects GET and POST).

        Args:
            url:  Target URL — for GET params use http://host/page?id=1,
                  for POST pass the URL and provide data separately
            data: POST body string (e.g. "user=foo&pass=bar"); if empty,
                  sqlmap crawls the page for forms automatically
            additional_args: Extra sqlmap flags (e.g. "--dbs", "--dump", "-p username")

        Returns:
            Scan results including injection points and extracted data
        """
        base = f"sqlmap -u '{url}' --batch --forms --crawl=2 --level=2 --risk=1 --threads=4"
        if data:
            base += f" --data='{data}'"
        if additional_args:
            base += f" {additional_args}"
        cmd = f"timeout 300 {base}"
        return kali_client.execute_command(cmd)

    @mcp.tool()
    def autorecon_scan(target: str) -> Dict[str, Any]:
        """
        Run autorecon against a target — automatically chains nmap, gobuster,
        nikto, and service-specific scanners then returns parsed results.

        Args:
            target: IP address or hostname (not a full URL)

        Returns:
            Combined output from all sub-scans
        """
        safe = target.replace(".", "_").replace("/", "_").replace(":", "_")
        out  = f"/tmp/autorecon_{safe}"
        log  = f"/tmp/ar_{safe}.txt"
        # Run autorecon directly — modern autorecon handles non-TTY environments.
        # Strip ANSI colour codes from the log before showing it.
        cmd  = (
            f"rm -rf {out} {log} ; "
            f"unbuffer sudo timeout 120 autorecon {target} --output {out} --only-scans-dir --exclude-tags long "
            f"  > {log} 2>&1 ; "
            f"echo '=== AUTORECON LIVE (last 20 lines) ==='; "
            f"tail -60 {log} 2>/dev/null | sed 's/\\x1b\\[[0-9;]*[mGKHJF]//g' ; "
            f"echo '=== AUTORECON RESULTS ==='; "
            f"find {out} -name '*.txt' 2>/dev/null | sort | while read f; do "
            f"  echo \"--- $f ---\"; head -80 \"$f\"; echo; "
            f"done | head -600"
        )
        return kali_client.execute_command(cmd)

    @mcp.tool()
    def metasploit_run(module: str, options: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Execute a Metasploit module.
        
        Args:
            module: The Metasploit module path
            options: Dictionary of module options
            
        Returns:
            Module execution results
        """
        data = {
            "module": module,
            "options": options
        }
        return kali_client.safe_post("api/tools/metasploit", data)

    @mcp.tool()
    def hydra_attack(
        target: str, 
        service: str, 
        username: str = "", 
        username_file: str = "", 
        password: str = "", 
        password_file: str = "", 
        additional_args: str = ""
    ) -> Dict[str, Any]:
        """
        Execute Hydra password cracking tool.
        
        Args:
            target: Target IP or hostname
            service: Service to attack (ssh, ftp, http-post-form, etc.)
            username: Single username to try
            username_file: Path to username file
            password: Single password to try
            password_file: Path to password file
            additional_args: Additional Hydra arguments
            
        Returns:
            Attack results
        """
        data = {
            "target": target,
            "service": service,
            "username": username,
            "username_file": username_file,
            "password": password,
            "password_file": password_file,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/hydra", data)

    @mcp.tool()
    def john_crack(
        hash_file: str, 
        wordlist: str = "/usr/share/wordlists/rockyou.txt", 
        format_type: str = "", 
        additional_args: str = ""
    ) -> Dict[str, Any]:
        """
        Execute John the Ripper password cracker.
        
        Args:
            hash_file: Path to file containing hashes
            wordlist: Path to wordlist file
            format_type: Hash format type
            additional_args: Additional John arguments
            
        Returns:
            Cracking results
        """
        data = {
            "hash_file": hash_file,
            "wordlist": wordlist,
            "format": format_type,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/john", data)

    @mcp.tool()
    def wpscan_analyze(url: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute WPScan WordPress vulnerability scanner.
        
        Args:
            url: The target WordPress URL
            additional_args: Additional WPScan arguments
            
        Returns:
            Scan results
        """
        data = {
            "url": url,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/wpscan", data)

    @mcp.tool()
    def enum4linux_scan(target: str, additional_args: str = "-a") -> Dict[str, Any]:
        """
        Execute Enum4linux Windows/Samba enumeration tool.
        
        Args:
            target: The target IP or hostname
            additional_args: Additional enum4linux arguments
            
        Returns:
            Enumeration results
        """
        data = {
            "target": target,
            "additional_args": additional_args
        }
        return kali_client.safe_post("api/tools/enum4linux", data)

    @mcp.tool()
    def server_health() -> Dict[str, Any]:
        """
        Check the health status of the Kali API server.
        
        Returns:
            Server health information
        """
        return kali_client.check_health()
    
    @mcp.tool()
    def zap_scan(url: str = "", mode: str = "spider", port: int = 8080) -> Dict[str, Any]:
        """
        Run OWASP ZAP via zap-cli for spidering or active scanning.
        Uses the full path to zap-cli to avoid PATH issues.
        Starts the ZAP daemon automatically if it is not already running.

        Args:
            url:  Target URL to scan (not required for mode="alerts")
            mode: "spider" to crawl links, "active" for active vuln scan
                  (uses all scanners), "alerts" to retrieve current ZAP alerts as JSON
            port: ZAP proxy port (default 8080)

        Returns:
            Scan results or alert list
        """
        ZAP_CLI = "/home/kali/.local/bin/zap-cli"
        daemon_check = (
            f"if ! pgrep -f zaproxy > /dev/null 2>&1; then "
            f"zaproxy -daemon -port {port} -host 127.0.0.1 -config api.disablekey=true "
            f"> /dev/null 2>&1 & sleep 40; fi"
        )
        if mode == "spider":
            zap_api = f"http://127.0.0.1:{port}/JSON/spider/view/results/?apikey="
            py_script = 'import sys,json; d=json.load(sys.stdin); [print(u) for u in d.get("results",[])]'
            cmd = (
                f"{daemon_check} && {ZAP_CLI} -p {port} spider {url} && "
                f"curl -s '{zap_api}' | python3 -c '{py_script}'"
            )
        elif mode == "active":
            cmd = (
                f"{daemon_check} && {ZAP_CLI} -p {port} active-scan --scanners all {url} && "
                f"echo '[ZAP ALERTS]' && {ZAP_CLI} -p {port} alerts --output-format json"
            )
        elif mode == "alerts":
            cmd = f"{daemon_check} && {ZAP_CLI} -p {port} alerts --output-format json"
        else:
            return {"error": f"Unknown mode '{mode}'. Use: spider, active, alerts"}
        return kali_client.execute_command(cmd)

    @mcp.tool()
    def execute_command(command: str) -> Dict[str, Any]:
        """
        Execute an arbitrary command on the Kali server.

        Args:
            command: The command to execute

        Returns:
            Command execution results
        """
        return kali_client.execute_command(command)

    return mcp

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run the Kali MCP Client")
    parser.add_argument("--server", type=str, default=DEFAULT_KALI_SERVER, 
                      help=f"Kali API server URL (default: {DEFAULT_KALI_SERVER})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT,
                      help=f"Request timeout in seconds (default: {DEFAULT_REQUEST_TIMEOUT})")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()

def main():
    """Main entry point for the MCP server."""
    args = parse_args()

    # # Check if running in stdio mode
    # is_stdio = sys.stdin.isatty() is False and sys.stdout.isatty() is False
    
    # Configure logging based on debug flag
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Initialize the Kali Tools client
    kali_client = KaliToolsClient(args.server, args.timeout)
    
    # Check server health and log the result
    health = kali_client.check_health()
    if "error" in health:
        logger.warning(f"Unable to connect to Kali API server at {args.server}: {health['error']}")
        logger.warning("MCP server will start, but tool execution may fail")
    else:
        logger.info(f"Successfully connected to Kali API server at {args.server}")
        logger.info(f"Server health status: {health['status']}")
        if not health.get("all_essential_tools_available", False):
            logger.warning("Not all essential tools are available on the Kali server")
            missing_tools = [tool for tool, available in health.get("tools_status", {}).items() if not available]
            if missing_tools:
                logger.warning(f"Missing tools: {', '.join(missing_tools)}")
    
    # Set up and run the MCP server
    mcp = setup_mcp_server(kali_client)
    logger.info("Starting Kali MCP server")
    mcp.run()

if __name__ == "__main__":
    main()
