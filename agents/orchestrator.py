import argparse
import asyncio
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ==============================================================================
# 1. PATH CONFIGURATION
# ==============================================================================
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
sys.path.append(str(project_root))

# ==============================================================================
# 2. MODULE IMPORTS
# ==============================================================================
from agents.config.constants import OPENROUTER_MODEL_NAME, TARGET_OS, TARGET_VERSION
from agents.config.settings import llm_settings, ip_settings, project_root
from agents.helpers.save_json import save_result, extract_json_from_llm_response
from agents.llms.AnythingLLM import AnythingLLMLLM
from agents.llms.OpenRouter import OpenRouterLLM
from agents.logger import DatabaseLogger
from agents.tools.KaliMCP import KaliMCP
from agents.tools.SSHKaliTool import SSHKaliTool
from agents.classifier import classify_failures
from agents.helpers.token_tracker import token_tracker

# ==============================================================================
# 3. GLOBAL SETTINGS
# ==============================================================================
# FRESH_SCAN: If True, ignores DB cache and forces a new Nmap scan.
# Set to False to reuse cached recon from Supabase (saves API costs!)
FRESH_SCAN = False
MAX_ROUNDS = 3  # Max feedback loop iterations

# ==============================================================================
# 4. HELPER FUNCTIONS
# ==============================================================================
def parse_cli_args():
    parser = argparse.ArgumentParser(description='PLANTE - Automated Pentesting')
    parser.add_argument('--target-ip', help='Target IP address')
    parser.add_argument('--target-os', help='Target OS (Linux, Windows, FreeBSD)', default=None)
    parser.add_argument('--target-name', help='Target name for result files (e.g., Lame, Blue)', default=None)
    parser.add_argument('--fresh-scan', action='store_true', help='Force fresh nmap scan instead of using cached recon')
    return parser.parse_args()


# Privilege indicators by OS for success validation
PRIVILEGE_INDICATORS = {
    "linux": ["uid=0(root)"],
    "windows": ["nt authority\\system", "nt authority\\\\system", "administrator"],
    "freebsd": ["uid=0(root)", "root@"],
    "metasploitable": ["uid=0(root)"],
}


def check_root_access(output, target_os="linux"):
    """Check if output indicates root/admin access for the given OS."""
    output_lower = output.lower()
    os_key = target_os.lower()
    indicators = PRIVILEGE_INDICATORS.get(os_key, PRIVILEGE_INDICATORS["linux"])
    return any(indicator.lower() in output_lower for indicator in indicators)


def load_prompt(name: str) -> str:
    """Read a prompt template file from the agents/prompts directory."""
    prompts_dir = project_root / "agents" / "prompts"
    prompt_path = prompts_dir / name
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_module_from_chain(chain):
    """Extract the MSF module path from a chain's commands (e.g., 'exploit/windows/smb/ms17_010_eternalblue')."""
    for stage in chain.get('stages', []):
        for cmd_obj in stage.get('commands', []):
            cmd_str = cmd_obj.get('command', '') if isinstance(cmd_obj, dict) else str(cmd_obj)
            if cmd_str.strip().lower().startswith('use '):
                module_path = cmd_str.strip()[4:].strip()
                if '/' in module_path:  # Looks like a real module path
                    return module_path
    return None


async def investigate_failure(ssh, target_ip: str, port: int, service_name: str, module_path: str = None, chain_output: str = None) -> dict:
    """
    Run diagnostic commands to gather evidence before classifying a failure.

    Checks:
    1. Is the port open? (nc -zv, cross-referenced with exploit output)
    2. What version is running? (nmap -sV)
    3. Does a Metasploit module exist? (msfconsole search)

    Args:
        ssh: SSHKaliTool instance
        target_ip: Target IP address
        port: Port number to check
        service_name: Service name (e.g., 'vsftpd', 'samba')
        module_path: MSF module path from chain commands (e.g., 'exploit/windows/smb/ms17_010_eternalblue')
        chain_output: Raw output from the chain's execution (used to check if exploit connected)

    Returns:
        dict with: port_open, actual_version, module_exists
    """
    evidence = {
        'port_open': False,
        'actual_version': 'unknown',
        'module_exists': False,
    }

    print(f"\n[INVESTIGATE] Checking {service_name} on port {port}...")

    try:
        # Check 1: Is port open?
        # First check the exploit's own output — if the exploit connected to the target,
        # the port was open when it mattered. A post-exploit nc check can give false negatives
        # if the exploit crashed the target service (e.g., MS08-067 buffer overflow crashes svchost).
        exploit_connected = False
        if chain_output:
            output_lower = chain_output.lower()
            connection_markers = [
                "attempting to trigger",
                "binding to",
                "connection established",
                "connecting to target",
                "connected to target",
                "calling dcom",
                "calling rpc",
                "sending exploit",
                "sending stage",
                "started reverse tcp handler",
                "trying target",
            ]
            exploit_connected = any(marker in output_lower for marker in connection_markers)

        if exploit_connected:
            evidence['port_open'] = True
            print(f"  Port open: True (exploit output confirms connection)")
        else:
            result = await ssh.run_command(f"nc -zv {target_ip} {port} 2>&1")
            output = result.get('stdout', '') + result.get('stderr', '')
            evidence['port_open'] = "open" in output.lower() or "succeeded" in output.lower()
            print(f"  Port open: {evidence['port_open']} (nc check)")

        # Check 2: What version is running?
        result = await ssh.run_command(f"nmap -sV -p {port} {target_ip}")
        evidence['actual_version'] = result.get('stdout', '')
        print(f"  Version check done")

        # Check 3: Does Metasploit module exist?
        # Use the actual module name from the chain if available, otherwise fall back to service name.
        # Nmap service names (e.g., "microsoft-ds") don't match MSF module names (e.g., "ms17_010_eternalblue").
        if module_path:
            search_term = module_path.split('/')[-1]  # e.g., "ms17_010_eternalblue"
            print(f"  Searching MSF for module: {search_term} (from chain)")
        else:
            search_term = service_name
            print(f"  Searching MSF for service: {search_term} (fallback)")

        result = await ssh.run_command(
            f"msfconsole -q -x 'search name:{search_term}; exit' 2>/dev/null"
        )
        output = result.get('stdout', '')
        evidence['module_exists'] = "exploit/" in output.lower() or "auxiliary/" in output.lower()
        print(f"  Module exists: {evidence['module_exists']}")

    except Exception as e:
        print(f"  [INVESTIGATE] Error: {e}")

    return evidence

def has_any_success(exec_results):
    """Check if any chain achieved at least initial access."""
    return bool(
        exec_results.get('initial_chains') or
        exec_results.get('privilege_chains') or
        exec_results.get('persistence_chains')
    )


def collect_round_context(exec_results, fix_results, classification_result, original_chains):
    """Collect context from this round for feeding into next round's chain generation."""
    context = {"chains_attempted": [], "discoveries": []}

    all_results = exec_results.get('attack_chains', {})

    # Build classification lookup
    classifications = {}
    if classification_result:
        for c in classification_result.get('classifications', []):
            classifications[c['chain_name']] = c.get('classification', 'UNKNOWN')

    for chain_name, chain_data in all_results.items():
        entry = {
            "name": chain_name,
            "result": chain_data.get('overall_status', 'unknown'),
            "stage_reached": chain_data.get('furthest_stage'),
            "classification": classifications.get(chain_name),
        }

        # Extract error from failed commands
        errors = []
        for stage_name, commands in chain_data.items():
            if not isinstance(commands, list):
                continue
            for cmd in commands:
                if isinstance(cmd, dict) and cmd.get('status') == 'error':
                    reason = cmd.get('failure_reason') or 'unknown error'
                    errors.append(reason)
        entry["errors"] = errors

        # Extract useful output from successful enumeration commands
        for stage_name, commands in chain_data.items():
            if not isinstance(commands, list):
                continue
            for cmd in commands:
                if isinstance(cmd, dict) and cmd.get('status') == 'success':
                    output = cmd.get('raw_output', '')
                    # Capture outputs that contain scan/enum results (>100 chars)
                    if len(output) > 100:
                        context["discoveries"].append({
                            "source": chain_name,
                            "command": cmd.get('command', ''),
                            "output": output[:2000]
                        })

        context["chains_attempted"].append(entry)

    # Include remediation results if any
    if fix_results:
        fix_chains = fix_results.get('attack_chains', {})
        for chain_name, chain_data in fix_chains.items():
            for existing in context["chains_attempted"]:
                if existing["name"] == chain_name:
                    existing["remediation_attempted"] = True
                    existing["remediation_result"] = chain_data.get('overall_status', 'unknown')

    return context


def format_previous_rounds(accumulated_context):
    """Format previous round results as text for the attack chain prompt."""
    if not accumulated_context:
        return ""

    lines = []
    lines.append("=" * 60)
    lines.append("PREVIOUS ATTEMPTS (DO NOT REPEAT THESE)")
    lines.append("=" * 60)

    for round_idx, ctx in enumerate(accumulated_context, 1):
        lines.append(f"\n--- Round {round_idx} ---")

        for chain in ctx["chains_attempted"]:
            name = chain["name"]
            result = chain["result"]
            errors = chain.get("errors", [])
            classification = chain.get("classification", "N/A")
            remediated = chain.get("remediation_attempted", False)
            remed_result = chain.get("remediation_result", "N/A")

            lines.append(f"\nChain: {name}")
            lines.append(f"  Result: {result}")
            if errors:
                lines.append(f"  Errors: {'; '.join(errors[:3])}")
            lines.append(f"  Classification: {classification}")
            if remediated:
                lines.append(f"  Remediation attempted: {remed_result}")

        if ctx.get("discoveries"):
            lines.append(f"\nDISCOVERIES FROM ROUND {round_idx}:")
            lines.append("Use these findings to create NEW attack chains.")
            for disc in ctx["discoveries"]:
                lines.append(f"\n  Command: {disc['command']}")
                lines.append(f"  Output:\n{disc['output']}")

    lines.append("\n" + "=" * 60)
    lines.append("RULES FOR THIS ROUND:")
    lines.append("1. Do NOT reuse any exploit MODULE from previous rounds. Remediation")
    lines.append("   already tried fixing parameters on those modules and it still failed.")
    lines.append("   Choose a completely different vulnerability, service, or technique.")
    lines.append("2. USE the discoveries above (command outputs, found directories, etc.)")
    lines.append("   as starting points for new attack vectors.")
    lines.append("3. Consider non-Metasploit approaches: curl, wget, manual HTTP requests,")
    lines.append("   web shells, file upload, default credentials, etc.")
    lines.append("=" * 60)

    return "\n".join(lines)


# ==============================================================================
# 5. EXECUTION LOGIC (SSH)
# ==============================================================================
async def execute_attack_chain_via_ssh(attack_chain_json, db, target_os="linux"):
    """
    Executes the provided attack chains on the Kali VM via SSH.
    Handles both persistent Metasploit sessions and standalone shell commands.
    """
    results = {
        "target": attack_chain_json.get("target", "unknown"),
        "attack_chains": {},
        "failed_chains": [],
        "initial_chains": [],
        "privilege_chains": [],
        "persistence_chains": []
    }

    chains = attack_chain_json.get("attack_chains", [])
    if not chains:
        print(f"\n[EXEC] No attack chains to execute. Skipping.")
        return results

    print(f"\n[EXEC] Connecting to Kali VM at {ip_settings.KALI_IP}...")

    async with SSHKaliTool(
        host=ip_settings.KALI_IP,
        username="kali",
        password="kali",
        timeout=120
    ) as ssh:

        total_chains = len(chains)
        print(f"[EXEC] Processing {total_chains} attack chains...\n")

        for chain_idx, chain in enumerate(chains, 1):
            try:
                # --- Chain Setup ---
                chain_name = chain["name"]
                use_persistent = chain.get("use_persistent_session", False)
                session_name = chain.get("session_name", None)
                
                print(f"\n{'='*60}")
                print(f"[CHAIN {chain_idx}/{total_chains}] Executing: {chain_name}")
                if use_persistent:
                    print(f"[CHAIN] Using persistent session: {session_name}")
                print(f"{'='*60}")
                
                chain_output = {}
                chain_success_stage = None

                # --- Stage Execution Loop ---
                for stage in chain["stages"]:
                    stage_name = stage["stage"]
                    commands = stage.get("commands", [])
                    
                    print(f"\n[STAGE] {stage_name}")
                    print(f"Description: {stage['description']}")

                    stage_results = []

                    # Run commands within the stage
                    for idx, cmd_obj in enumerate(commands, 1):
                        # Force session alignment: Ensure commands use the Chain's declared session
                        if use_persistent and session_name:
                            target_session = session_name
                        else:
                            if isinstance(cmd_obj, dict):
                                target_session = cmd_obj.get("session_name")
                            else:
                                target_session = None

                        # Parse command object (supports legacy string format)
                        if isinstance(cmd_obj, str):
                            cmd_type = "regular"
                            cmd = cmd_obj
                            wait_time = 3
                        else:
                            cmd_type = cmd_obj.get("type", "regular")
                            cmd = cmd_obj.get("command", "")
                            wait_time = cmd_obj.get("wait", 3)
                        
                        print(f"\n  [CMD {idx}/{len(commands)}] Type: {cmd_type} | Wait: {wait_time}s")
                        if cmd:
                            print(f"  Command: {cmd[:80]}{'...' if len(cmd) > 80 else ''}")
                        
                        # --- Command Execution ---
                        if cmd_type == "start_session":
                            result = await ssh.start_persistent_session(target_session, cmd)
                            output = result.get("message", "")
                            cmd_success = result.get("success", False)
                            
                        elif cmd_type == "session_command":
                            result = await ssh.run_in_persistent_session(target_session, cmd, wait_time)
                            output = result["stdout"] + result["stderr"]
                            cmd_success = result["success"]
                            
                        elif cmd_type == "close_session":
                            result = await ssh.close_persistent_session(target_session)
                            output = result.get("message", "")
                            cmd_success = result.get("success", False)
                            
                        else:  # Regular command
                            result = await ssh.run_command(cmd)
                            output = result["stdout"] + result["stderr"]
                            cmd_success = result["success"]
                        
                        # --- Output Analysis & Validation ---
                        output_lower = output.lower()
                        failure_reason = None
                        
                        # Metasploit Session Checks
                        if cmd_type in ["session_command", "start_session"]:
                            # Success Markers
                            if "command shell session" in output_lower and "opened" in output_lower:
                                cmd_success = True
                            elif "session" in output_lower and "opened" in output_lower:
                                cmd_success = True
                            elif check_root_access(output, target_os):
                                cmd_success = True
                            elif "accepted the first client connection" in output_lower:
                                cmd_success = True
                            
                            # Failure Markers
                            elif "invalid session identifier" in output_lower:
                                cmd_success = False
                                failure_reason = "Session does not exist"
                            elif "exploit failed" in output_lower or "died" in output_lower:
                                cmd_success = False
                                failure_reason = "Exploit failed"
                            elif "uid=1000(kali)" in output_lower:
                                cmd_success = False
                                failure_reason = "Commands executed on Kali, not target"
                            elif "error in expression" in output_lower or "unknown command" in output_lower:
                                cmd_success = False
                                failure_reason = "Metasploit command error"
                            elif "exploit completed, but no session was created" in output_lower:
                                if not cmd_success: 
                                    cmd_success = False
                                    failure_reason = "Exploit ran but failed to open a session"
                            
                            # Configuration Confirmation (set/use commands)
                            elif cmd.strip().lower().startswith(("set ", "use ")):
                                if "=>" in output or "no payload configured" in output_lower:
                                    cmd_success = True
                                elif "msf exploit" in output_lower or "msf auxiliary" in output_lower:
                                    cmd_success = True
                                elif "msf" in output_lower and "exploit(" in output_lower and "error" not in output_lower:
                                    cmd_success = True
                        
                        # Regular Command Checks
                        elif cmd_type == "regular":
                            if "ssh" in cmd and "@" in cmd:
                                if result.get("return_code") == 0 and "permission denied" not in output_lower:
                                    cmd_success = True
                                else:
                                    cmd_success = False
                                    failure_reason = "SSH connection failed"
                            
                            elif "python" in cmd:
                                if "success" in output_lower:
                                    cmd_success = True
                                elif check_root_access(output, target_os):
                                    cmd_success = True
                                elif "root" in output_lower and len(output) > 10:
                                    cmd_success = True
                                elif "failed" in output_lower or "error" in output_lower:
                                    cmd_success = False
                                    failure_reason = "Python script reported failure"
                                elif len(output.strip()) == 0:
                                    cmd_success = False
                                    failure_reason = "Python script produced no output (timeout/silent fail)"
                                else:
                                    cmd_success = result.get("return_code", 0) == 0
                            
                            elif "cat >" in cmd or "echo" in cmd:
                                cmd_success = result.get("return_code", 0) == 0
                        
                        # Log Result
                        if cmd_success:
                            analysis = f"Type: {cmd_type}. SUCCESS"
                        else:
                            analysis = f"Type: {cmd_type}. FAILED"
                            if failure_reason:
                                analysis += f" - {failure_reason}"
                        
                        stage_results.append({
                            "description": stage["description"],
                            "command": cmd if cmd else f"<{cmd_type} operation>",
                            "command_type": cmd_type,
                            "raw_output": output,
                            "analysis": analysis,
                            "status": "success" if cmd_success else "error",
                            "return_code": result.get("return_code", 0),
                            "failure_reason": failure_reason
                        })
                        
                        print(f"    Status: {'SUCCESS' if cmd_success else 'FAILED'}")
                        if failure_reason:
                            print(f"    Reason: {failure_reason}")
                        
                        if output and len(output) > 0:
                            lines = [l for l in output.split('\n') if l.strip()]
                            if lines:
                                for line in lines[-3:]:
                                    if any(kw in line.lower() for kw in ['session', 'uid=', 'error', 'success', 'opened']):
                                        print(f"    Output: {line[:100]}")

                    chain_output[stage_name] = stage_results

                    # --- Stage Success Determination ---
                    # Filter out non-critical commands (file creation, echo) for success check
                    meaningful_results = [
                        r for r in stage_results 
                        if r["command_type"] not in ["close_session"] 
                        and not any(skip in r["command"] for skip in ["cat >", "echo 'N/A"])
                    ]
                    
                    if meaningful_results:
                        stage_success = any(r["status"] == "success" for r in meaningful_results)
                    else:
                        stage_success = any(r["status"] == "success" for r in stage_results)
                    
                    # Strict Validation for Exploitation Stages
                    full_stage_output = "\n".join([r.get("raw_output", "").lower() for r in stage_results])

                    if stage_name == "initial_access":
                        session_opened = "session" in full_stage_output and "opened" in full_stage_output
                        if not session_opened and use_persistent and session_name:
                            # Exploit may still be running in background — retry sessions check.
                            # Backgrounded exploits (-j) print "no session was created" immediately
                            # but the actual exploitation continues asynchronously.
                            has_terminal_failure = any(marker in full_stage_output for marker in [
                                "exploit failed", "died", "invalid session"
                            ])
                            if not has_terminal_failure:
                                print(f"  [VALIDATION] No session yet — exploit may still be running. Retrying in 20s...")
                                await asyncio.sleep(20)
                                retry_result = await ssh.run_in_persistent_session(session_name, "sessions -l", wait_time=5)
                                retry_output = (retry_result["stdout"] + retry_result["stderr"]).lower()
                                full_stage_output = full_stage_output + "\n" + retry_output
                                session_opened = "session" in full_stage_output and "opened" in full_stage_output
                                if not session_opened and "no active sessions" not in retry_output and "meterpreter" in retry_output:
                                    session_opened = True
                                if session_opened:
                                    print(f"  [VALIDATION] Session found on retry!")
                                    stage_results.append({
                                        "description": "Auto-retry: session check after additional wait",
                                        "command": "sessions -l",
                                        "command_type": "session_command",
                                        "raw_output": retry_result["stdout"] + retry_result["stderr"],
                                        "analysis": "Type: session_command. SUCCESS (retry)",
                                        "status": "success",
                                        "return_code": 0,
                                        "failure_reason": None
                                    })
                        if not session_opened:
                            print(f"  [VALIDATION] Stage 'initial_access' failed: No session opened.")
                            stage_success = False

                    elif stage_name == "privilege_escalation":
                        got_root = check_root_access(full_stage_output, target_os)
                        if not got_root:
                            print(f"  [VALIDATION] Stage 'privilege_escalation' failed: No root/admin access detected.")
                            stage_success = False

                    # Final Stage Decision
                    if stage_success:
                        chain_success_stage = stage_name
                        print(f"  [STAGE] {stage_name} - PASSED")
                    else:
                        print(f"  [STAGE] {stage_name} - FAILED")
                        break # Stop chain execution immediately on failure

                # --- Chain Classification ---
                # Only exploitation stages count toward success.
                # Non-exploitation stages (reconnaissance, enumeration, scanning) are
                # informational — they don't mean we achieved access to the target.
                EXPLOITATION_STAGES = {"initial_access", "privilege_escalation", "persistence"}

                if chain_success_stage is None:
                    results["failed_chains"].append(chain_name)
                    overall = "failed"
                    print(f"\n[CHAIN] Result: FAILED - No stages succeeded")
                elif chain_success_stage not in EXPLOITATION_STAGES:
                    # Chain completed but only reached non-exploitation stages (e.g., recon)
                    overall = "completed"
                    print(f"\n[CHAIN] Result: COMPLETED ({chain_success_stage}) - Non-exploitation, not counted as access")
                elif chain_success_stage == "initial_access":
                    results["initial_chains"].append(chain_name)
                    overall = "partial"
                    print(f"\n[CHAIN] Result: PARTIAL - Got initial access")
                elif chain_success_stage == "privilege_escalation":
                    results["privilege_chains"].append(chain_name)
                    overall = "partial"
                    print(f"\n[CHAIN] Result: PARTIAL - Escalated privileges")
                elif chain_success_stage == "persistence":
                    results["persistence_chains"].append(chain_name)
                    overall = "completed"
                    print(f"\n[CHAIN] Result: COMPLETED - Full chain successful")

                chain_output["overall_status"] = overall
                chain_output["furthest_stage"] = chain_success_stage
                chain_output["notes"] = []

                results["attack_chains"][chain_name] = chain_output
                
            except Exception as e:
                print(f"\n[ERROR] Chain '{chain_name}' failed with exception: {e}")
                error_trace = traceback.format_exc()
                print(error_trace)
                
                results["attack_chains"][chain_name] = {
                    "overall_status": "error",
                    "furthest_stage": None,
                    "error": str(e),
                    "traceback": error_trace,
                    "notes": ["Chain execution failed with exception"]
                }
                results["failed_chains"].append(chain_name)
                print(f"[INFO] Continuing to next chain despite error...\n")

    print(f"\n{'='*60}")
    print("[EXEC] All chains processed")
    print(f"{'='*60}")
    print(f"Completed (Persistence): {results['persistence_chains']}")
    print(f"Partial (Privileges): {results['privilege_chains']}")
    print(f"Partial (Initial): {results['initial_chains']}")
    print(f"Failed (No stages reached): {results['failed_chains']}")
    
    return results

# ==============================================================================
# 6. MAIN ORCHESTRATION LOOP
# ==============================================================================
async def main(args):
    test_init_time = datetime.now()
    db = DatabaseLogger()

    # Apply CLI overrides
    global FRESH_SCAN
    target_os = args.target_os or TARGET_OS
    target_name = args.target_name or "metasploitable"
    if args.target_ip:
        ip_settings.TARGET_IP = args.target_ip
    if args.fresh_scan:
        FRESH_SCAN = True

    # Auto-detect Kali's best IP for reverse shells (LHOST)
    # KALI_IP = host-only IP for SSH (never changes)
    # kali_lhost = tun0 IP if VPN running, otherwise same as KALI_IP
    kali_lhost = ip_settings.KALI_IP
    print("[CONFIG] Detecting Kali LHOST for reverse shells...")
    try:
        async with SSHKaliTool(
            host=ip_settings.KALI_IP, username="kali", password="kali", timeout=10
        ) as ssh:
            result = await ssh.run_command(
                "ip -4 addr show tun0 2>/dev/null | grep -oP 'inet \\K[\\d.]+'"
            )
            tun0_ip = result.get('stdout', '').strip()
            if tun0_ip:
                kali_lhost = tun0_ip
                print(f"[CONFIG] VPN detected — LHOST: {kali_lhost}")
            else:
                print(f"[CONFIG] No VPN — LHOST: {kali_lhost}")
    except Exception as e:
        print(f"[WARN] Could not detect tun0: {e}. LHOST: {kali_lhost}")

    print(f"[CONFIG] Target: {target_name} ({ip_settings.TARGET_IP}) | OS: {target_os}")
    print(f"[CONFIG] Kali SSH: {ip_settings.KALI_IP} | Kali LHOST: {kali_lhost} | Fresh scan: {FRESH_SCAN}")
    save_result.set_target_name(target_name)

    # Initialize accumulators OUTSIDE try block so they're always available in finally
    ac_rounds = []
    exec_rounds = []
    classification_rounds = []
    reval_rounds = []
    exec_fix_rounds = []
    final_success = False
    round_num = 0

    try:
        # --- Initialization ---
        orchestrator_agent_id = db.register_agent('Orchestrator', 'coordinator', 'localhost')
        openrouter_llm = OpenRouterLLM()
        llm = AnythingLLMLLM(
            base_url=llm_settings.ANYTHINGLLM_API_URL,
            api_key=llm_settings.ANYTHINGLLM_API_KEY,
            workspace_slug=llm_settings.ANYTHINGLLM_WORKSPACE_SLUG,
        )
        kali_mcp = KaliMCP()

        # --- Phase 1: Reconnaissance ---
        goto_attack_chain = False
        structured_json_string = None
        structured = None
        result = None
        recon_id = None

        db.start_run(ip_settings.TARGET_IP, f"{target_os} ({target_name})",
                     description=f"Automated penetration test: {target_name}")
        
        # Check for Cached Recon Results
        if not FRESH_SCAN:
            print(f"\n[MODE] FRESH_SCAN = False — checking for existing recon results for {ip_settings.TARGET_IP}...")
            db.log_raw('orchestrator', 'INFO', 'Checking for cached recon results', {'target': ip_settings.TARGET_IP})

            try:
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT recon_id, result_json
                    FROM recon_results
                    WHERE target_ip = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (ip_settings.TARGET_IP,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()

                if row:
                    recon_id, result_json = row
                    print(f"[REUSE] Found recon record recon_id={recon_id}. Skipping fresh scan.")
                    db.log_raw('orchestrator', 'INFO', 'Using cached recon results', {'recon_id': recon_id})
                    structured_json_string = json.dumps(result_json, indent=2)
                    goto_attack_chain = True
                else:
                    print("[REUSE] No valid recon record found. Running fresh scan.")
                    db.log_raw('orchestrator', 'INFO', 'No cached recon found, running fresh scan')
                    goto_attack_chain = False

            except Exception as e:
                print(f"[ERROR] DB recon lookup failed: {e}")
                db.log_raw('orchestrator', 'ERROR', f'Failed to check cached recon: {str(e)}')
                goto_attack_chain = False

        # Execute Recon if Needed
        if goto_attack_chain:
            print("\n[INFO] Using stored recon JSON for attack chain.\n")
        else:
            print("\n[SCAN] Running fresh recon scan...")
            db.log_raw('orchestrator', 'INFO', 'Starting recon phase', 
                        {'target': ip_settings.TARGET_IP, 'model': OPENROUTER_MODEL_NAME})
            
            recon_template = load_prompt("recon_prompt.txt")
            recon_question = recon_template.replace("__TARGET_IP__", ip_settings.TARGET_IP)
            recon_start_time = time.time()

            db.log_llm_decision(
                    llm_model=OPENROUTER_MODEL_NAME,
                    prompt=recon_question[:2000],
                    response=recon_question[:10000],
                    reasoning="recon_phase_start"
            )

            result = await kali_mcp._call(openrouter_llm, recon_question)
            
            recon_duration = time.time() - recon_start_time
            db.log_raw('orchestrator', 'INFO', 'Recon phase completed', 
                        {'duration': recon_duration, 'result_type': str(type(result))})
            print("\nRecon result received.")
            
            # Recon Result Parsing
            if isinstance(result, dict):
                structured = result.get("structured_response")
                raw_output = json.dumps(result, indent=2, default=str)
                messages = result.get("messages", [])

                # Log tool calls
                tool_call_count = 0
                for msg in messages:
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            tool_name = tool_call.get('name', 'unknown')
                            tool_args = tool_call.get('args', {})
                            cmd_id = db.log_command(
                                tool_name=tool_name,
                                command_text=str(tool_args),
                                target_ip=ip_settings.TARGET_IP,
                                agent_id=orchestrator_agent_id
                            )
                            tool_call_count += 1
                            if hasattr(msg, 'content'):
                                db.update_command_result(
                                    command_id=cmd_id,
                                    success=True,
                                    raw_output=str(msg.content)[:10000]
                                )
                
                if tool_call_count > 0:
                    db.log_raw('orchestrator', 'INFO', f'Logged {tool_call_count} tool calls', 
                                {'tool_calls': tool_call_count})

                if structured is not None:
                    print("\nStructured response:\n", structured)
                    structured_dict = structured.model_dump() if hasattr(structured, 'model_dump') else (
                            structured.dict() if hasattr(structured, 'dict') else structured
                        )

                    # Unwrap KaliMCPResponse: {"output": "..."} → parse the inner JSON
                    recon_data = structured_dict
                    if isinstance(structured_dict, dict) and 'output' in structured_dict and len(structured_dict) == 1:
                        inner = structured_dict['output']
                        if isinstance(inner, dict):
                            recon_data = inner
                        elif isinstance(inner, str):
                            try:
                                recon_data = json.loads(inner)
                            except Exception:
                                recon_data = structured_dict

                    recon_id = db.log_recon(
                        tool_used='kali_mcp_agent',
                        raw_output=raw_output,
                        result_json=recon_data,
                        target_ip=ip_settings.TARGET_IP,
                        agent_id=orchestrator_agent_id
                    )

                    # Log vulnerabilities
                    vuln_count = 0
                    if isinstance(recon_data, dict) and 'open_ports' in recon_data:
                        for port_info in recon_data.get('open_ports', []):
                            if 'cve_candidates' in port_info and port_info['cve_candidates']:
                                for cve in port_info['cve_candidates']:
                                    severity = 'high' if port_info.get('risk') == 'high' else 'medium'
                                    db.log_vulnerability(
                                        target_ip=ip_settings.TARGET_IP,
                                        port=port_info.get('port'),
                                        service_name=port_info.get('service'),
                                        service_version=port_info.get('version'),
                                        vulnerability_type='potential_cve',
                                        severity=severity,
                                        cve_id=cve,
                                        description=f"Potential {cve} vulnerability on {port_info.get('service')}",
                                        recon_id=recon_id
                                    )
                                    vuln_count += 1
                    
                    if vuln_count > 0:
                        db.log_raw('orchestrator', 'INFO', f'Logged {vuln_count} vulnerabilities', 
                                    {'vulnerability_count': vuln_count})
                    
                    db.log_llm_decision(
                        llm_model=OPENROUTER_MODEL_NAME,
                        prompt=recon_question[:2000],
                        response=raw_output[:10000],
                        reasoning="recon_phase_complete"
                    )
                    print("Recon results logged successfully")

                else:
                    print("\nNo structured response, logging raw result...")
                    recon_id = db.log_recon(
                            tool_used='kali_mcp_agent',
                            raw_output=raw_output,
                            result_json={"status": "partial", "raw": str(result)[:5000]},
                            target_ip=ip_settings.TARGET_IP,
                            agent_id=orchestrator_agent_id
                        )
            else:
                print("\nResult was not a dict; raw repr:\n", repr(result))
                db.log_raw('orchestrator', 'WARN', 'Unexpected result type', {'type': str(type(result))})
                recon_id = db.log_recon(
                    tool_used='kali_mcp_agent',
                    raw_output=str(result),
                    result_json={"status": "error", "type": str(type(result))},
                    target_ip=ip_settings.TARGET_IP,
                    agent_id=orchestrator_agent_id
                )

        # --- Prepare recon data for attack chain generation ---
        if structured is None and not goto_attack_chain:
            structured_json_string = json.dumps({"error": "no_structured_response", "raw_result": str(result)}, indent=2)
        elif structured is not None:
            # Unwrap KaliMCPResponse Pydantic model — extract the .output field
            raw_data = structured
            if hasattr(structured, 'output'):
                raw_data = structured.output
            elif hasattr(structured, 'model_dump'):
                dumped = structured.model_dump()
                raw_data = dumped.get('output', dumped)

            if isinstance(raw_data, dict):
                structured_json_string = json.dumps(raw_data, indent=2, ensure_ascii=False)
            elif isinstance(raw_data, str):
                try:
                    parsed = json.loads(raw_data)
                    structured_json_string = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception:
                    structured_json_string = json.dumps({"raw_structured_response": raw_data}, indent=2, ensure_ascii=False)
            else:
                try:
                    parsed = json.loads(str(raw_data))
                    structured_json_string = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception:
                    structured_json_string = json.dumps({"raw_structured_response": str(raw_data)}, indent=2, ensure_ascii=False)

        # Load prompt templates (once, outside loop)
        ac_prompt_template = load_prompt("attack_chain_prompt.txt")
        exec_prompt_template = load_prompt("execution_prompt.txt")
        remediation_template = load_prompt("remediation_prompt.txt")

        # ==============================================================
        # FEEDBACK LOOP — Phases 2-4 repeat up to MAX_ROUNDS times
        # ==============================================================
        accumulated_context = []

        for round_num in range(1, MAX_ROUNDS + 1):
            print(f"\n{'#'*60}")
            print(f"  ROUND {round_num}/{MAX_ROUNDS}")
            print(f"{'#'*60}")

            # Reset per-round variables
            clean_fix_exec = None
            classification_result = None
            correctable_chains = []

            # --- Phase 2: Attack Chain Generation ---
            db.log_raw('orchestrator', 'INFO', f'Starting attack chain analysis (round {round_num})',
                        {'target': ip_settings.TARGET_IP, 'model': 'anythingllm', 'round': round_num})

            attack_chain_start_time = time.time()

            # Build previous rounds context (empty on round 1)
            previous_rounds_text = format_previous_rounds(accumulated_context)

            ac_question = (
                ac_prompt_template
                .replace("__TARGET_OS__", target_os)
                .replace("__TARGET_VER__", target_name)
                .replace("__TARGET_IP__", ip_settings.TARGET_IP)
                .replace("__KALI_IP__", kali_lhost)
                .replace("__FULL_SCAN_JSON__", structured_json_string)
                .replace("__PREVIOUS_ROUNDS__", previous_rounds_text)
            )

            db.log_llm_decision(
                llm_model='anythingllm',
                prompt=ac_question[:2000],
                response=f"Initiating attack chain analysis (round {round_num})...",
                reasoning=f"attack_chain_phase_start_round_{round_num}"
            )

            print("\nAsking AnythingLLM for attack chain...")
            ac_response = llm._call(ac_question, phase="attack_chain_generation")
            attack_chain_duration = time.time() - attack_chain_start_time
            db.log_raw('orchestrator', 'INFO', f'Attack chain analysis completed (round {round_num})',
                        {'duration': attack_chain_duration, 'round': round_num})
            print("\nResponse received from LLM")

            # Parse and Validate Attack Chains
            try:
                ac_json = extract_json_from_llm_response(ac_response)

                required_fields = ["target", "summary", "attack_chains"]
                missing_fields = [field for field in required_fields if field not in ac_json]

                if missing_fields:
                    print(f"WARNING: Attack chain response missing fields: {missing_fields}")
                    db.log_raw('orchestrator', 'WARN', 'Attack chain response incomplete',
                                {'missing_fields': missing_fields})

                # Display generated chains
                if "attack_chains" in ac_json and isinstance(ac_json["attack_chains"], list):
                    print(f"\nGenerated {len(ac_json['attack_chains'])} attack chains:")
                    for idx, chain in enumerate(ac_json["attack_chains"], 1):
                        chain_name = chain.get("name", f"Unnamed Chain {idx}")
                        use_persistent = chain.get("use_persistent_session", False)
                        session_name = chain.get("session_name", "N/A")
                        num_stages = len(chain.get("stages", []))

                        print(f"  {idx}. {chain_name}")
                        print(f"     - Persistent Session: {use_persistent}")
                        if use_persistent:
                            print(f"     - Session Name: {session_name}")
                        print(f"     - Stages: {num_stages}")
                else:
                    print("WARNING: No valid attack_chains found in response")
                    db.log_raw('orchestrator', 'WARN', 'No attack chains in response')

                # Log to DB
                attack_surface = "\n".join(ac_json.get('summary', ['Attack surface analysis']))
                proposed_chains = ac_json.get('attack_chains', [])

                chain_id = db.log_attack_chain(
                    attack_surface=attack_surface,
                    proposed_stages=proposed_chains,
                    chain_json=ac_json,
                    recon_id=recon_id if recon_id else None
                )

                db.log_raw('orchestrator', 'INFO', 'Attack chain logged successfully',
                            {'chain_id': chain_id, 'num_chains': len(proposed_chains)})

            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to parse attack chain JSON: {e}")
                db.log_raw('orchestrator', 'ERROR', 'Attack chain JSON parse error',
                            {'error': str(e), 'response_preview': ac_response[:500]})
                ac_json = {
                    "target": ip_settings.TARGET_IP,
                    "summary": ["Failed to parse LLM response"],
                    "attack_chains": [],
                    "followup_requests": []
                }

            except Exception as e:
                print(f"ERROR: Unexpected error processing attack chain: {e}")
                db.log_raw('orchestrator', 'ERROR', 'Attack chain processing error', {'error': str(e)})
                traceback.print_exc()
                ac_json = {
                    "target": ip_settings.TARGET_IP,
                    "summary": ["Processing error"],
                    "attack_chains": [],
                    "followup_requests": []
                }

            db.log_llm_decision(
                llm_model='anythingllm',
                prompt=ac_question[:2000],
                response=ac_response[:10000],
                reasoning=f"attack_chain_phase_complete_round_{round_num}"
            )

            clean_ac = extract_json_from_llm_response(ac_response)
            ac_rounds.append({"round": round_num, **clean_ac})

            print("\nAttack chain generation complete")
            print(f"Chains to execute: {len(ac_json.get('attack_chains', []))}")

            # --- Phase 3: Execution ---
            db.log_raw('orchestrator', 'INFO', f'Starting execution phase (round {round_num})',
                        {'target': ip_settings.TARGET_IP, 'round': round_num})

            exec_start_time = time.time()

            exec_question = (
                exec_prompt_template
                .replace("__TARGET_IP__", ip_settings.TARGET_IP)
                .replace("__TARGET_OS__", target_os)
                .replace("__TARGET_VER__", target_name)
                .replace("__ATTACK_CHAIN_JSON__", ac_response)
            )

            db.log_llm_decision(
                llm_model=OPENROUTER_MODEL_NAME,
                prompt=exec_question[:2000],
                response=f"Initiating execution phase (round {round_num})...",
                reasoning=f"execution_phase_start_round_{round_num}"
            )

            print(f"\n[EXECUTION] Executing attack chains via SSH (round {round_num})...\n")

            exec_response = await execute_attack_chain_via_ssh(clean_ac, db, target_os)

            exec_duration = time.time() - exec_start_time
            db.log_raw('orchestrator', 'INFO', f'Execution phase completed (round {round_num})',
                        {'duration': exec_duration, 'round': round_num})

            clean_exec = extract_json_from_llm_response(exec_response)
            exec_rounds.append({"round": round_num, **clean_exec})

            # Check for success after execution
            if has_any_success(clean_exec):
                print(f"\n[ROUND {round_num}] SUCCESS — chain(s) reached access!")
                final_success = True
                # Still run remediation for partial chains if needed, but mark success
                break

            # --- Phase 4: Evaluation & Remediation ---

            # Check if any chains were actually executed
            if not clean_exec.get('attack_chains'):
                print(f"\n[ROUND {round_num}] No chains were executed (LLM returned empty/invalid response). Continuing...")
                if round_num < MAX_ROUNDS:
                    continue
                else:
                    break

            # Identify Failures
            failed_chain_names = (
                clean_exec.get('failed_chains', []) +
                clean_exec.get('initial_chains', []) +
                clean_exec.get('privilege_chains', [])
            )

            if not failed_chain_names:
                if has_any_success(clean_exec):
                    print(f"\n[ROUND {round_num}] No failed chains detected. Orchestration complete.")
                    final_success = True
                    break
                else:
                    # All chains were recon-only (no exploitation attempted) — not a real success
                    print(f"\n[ROUND {round_num}] No exploitation chains executed (recon-only round). Collecting context and continuing...")
                    round_ctx = collect_round_context(clean_exec, None, None, clean_ac)
                    accumulated_context.append(round_ctx)
                    if round_num < MAX_ROUNDS:
                        continue
                    else:
                        break

            print(f"\n[REVAL] Found {len(failed_chain_names)} failed/partial chains. Starting remediation...")

            # Prepare context for remediation
            failed_chain_context = []
            all_chain_results = clean_exec.get('attack_chains', {})

            for name in failed_chain_names:
                if name in all_chain_results:
                    chain_data = all_chain_results[name]
                    failed_chain_context.append({
                        "chain_name": name,
                        "status": chain_data.get('overall_status'),
                        "furthest_stage": chain_data.get('furthest_stage'),
                        "execution_logs": chain_data
                    })

            # --- INVESTIGATION PHASE ---
            chain_service_lookup = {}
            for chain in clean_ac.get('attack_chains', []):
                cname = chain.get('name')
                target_service = chain.get('target_service', 'unknown')
                target_port = chain.get('target_port', 0)
                module_path = extract_module_from_chain(chain)
                chain_service_lookup[cname] = (target_service, target_port, module_path)

            print("\n[INVESTIGATE] Running diagnostic commands on failed chains...")
            investigation_evidence = {}

            async with SSHKaliTool(
                host=ip_settings.KALI_IP,
                username="kali",
                password="kali",
                timeout=120
            ) as ssh:
                for chain_ctx in failed_chain_context:
                    cname = chain_ctx['chain_name']
                    service, port, module_path = chain_service_lookup.get(cname, ('unknown', 0, None))

                    # Collect raw output from the chain's execution for connection evidence
                    chain_raw_output = ""
                    exec_logs = chain_ctx.get('execution_logs', {})
                    for stage_name, commands in exec_logs.items():
                        if not isinstance(commands, list):
                            continue
                        for cmd in commands:
                            if isinstance(cmd, dict):
                                chain_raw_output += cmd.get('raw_output', '') + "\n"

                    if service != 'unknown' and port != 0:
                        evidence = await investigate_failure(
                            ssh,
                            ip_settings.TARGET_IP,
                            port,
                            service,
                            module_path=module_path,
                            chain_output=chain_raw_output
                        )
                        investigation_evidence[cname] = evidence
                    else:
                        print(f"  [INVESTIGATE] Skipping {cname}: missing service/port info")
                        investigation_evidence[cname] = {
                            'port_open': 'unknown',
                            'actual_version': 'unknown',
                            'module_exists': 'unknown',
                            'note': 'Chain missing target_service/target_port fields'
                        }

            # --- FAILURE CLASSIFIER ---
            print("\n[CLASSIFIER] Classifying failed chains...")
            classifier_start_time = time.time()

            correctable_chains, fundamental_chains, classification_result = classify_failures(
                failed_chain_context,
                ip_settings.TARGET_IP,
                llm,
                evidence=investigation_evidence
            )

            print(f"[CLASSIFIER] Classification completed ({time.time() - classifier_start_time:.2f}s)")

            classification_rounds.append({"round": round_num, **classification_result})

            if fundamental_chains:
                print(f"\n[CLASSIFIER] Skipping {len(fundamental_chains)} FUNDAMENTAL chains:")
                for chain in fundamental_chains:
                    print(f"  - {chain['chain_name']}: {chain.get('classification_reasoning', 'N/A')}")

            # Remediate correctable chains
            if correctable_chains:
                print(f"\n[CLASSIFIER] Proceeding with {len(correctable_chains)} CORRECTABLE chains")

                remediation_task = (
                    remediation_template
                    .replace("__FAILURE_REPORT__", json.dumps(correctable_chains, indent=2))
                    .replace("__KALI_IP__", kali_lhost)
                    .replace("__TARGET_IP__", ip_settings.TARGET_IP)
                    .replace("__TARGET_OS__", target_os)
                )

                print("\n[REVAL] Asking LLM to fix the correctable chains...")
                reval_start_time = time.time()
                reval_response = llm._call(remediation_task, phase="remediation")
                print(f"[REVAL] Remediation plan received ({time.time() - reval_start_time:.2f}s)")

                clean_reval = extract_json_from_llm_response(reval_response)
                reval_rounds.append({"round": round_num, **clean_reval})

                # Execute Remediation
                if "attack_chains" in clean_reval and len(clean_reval["attack_chains"]) > 0:
                    print(f"\n[EXEC_FIX] Executing {len(clean_reval['attack_chains'])} remediated chains via SSH...\n")

                    fix_exec_start_time = time.time()
                    fix_exec_response = await execute_attack_chain_via_ssh(clean_reval, db, target_os)

                    fix_exec_duration = time.time() - fix_exec_start_time
                    print(f"[EXEC_FIX] Remediation execution completed in {fix_exec_duration:.2f}s")

                    clean_fix_exec = extract_json_from_llm_response(fix_exec_response)
                    exec_fix_rounds.append({"round": round_num, **clean_fix_exec})

                    total_success = len(clean_fix_exec.get('persistence_chains', []))
                    print(f"\n[EXEC_FIX] Remediated Chains Success: {total_success}/{len(clean_reval['attack_chains'])}")

                    # Check for success after remediation
                    if has_any_success(clean_fix_exec):
                        print(f"\n[ROUND {round_num}] SUCCESS after remediation!")
                        final_success = True
                        break
                else:
                    print("\n[EXEC_FIX] No valid attack chains in remediation response. Skipping execution.")
            else:
                print("\n[CLASSIFIER] No correctable chains found. Skipping remediation phase.")

            # --- Collect context for next round ---
            round_ctx = collect_round_context(
                clean_exec,
                clean_fix_exec,
                classification_result,
                clean_ac
            )
            accumulated_context.append(round_ctx)

            if round_num < MAX_ROUNDS:
                print(f"\n[ROUND {round_num}] All chains failed. Pivoting to round {round_num + 1}...")
            else:
                print(f"\n[ROUND {round_num}] Max rounds reached. Stopping.")

        print(f"\n{'='*60}")
        print(f"ORCHESTRATION COMPLETE — {'SUCCESS' if final_success else 'FAILED'}")
        print(f"Rounds used: {round_num}/{MAX_ROUNDS}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\n ERROR: {e}")
        import traceback
        traceback.print_exc()
        db.log_raw('orchestrator', 'ERROR', f'Fatal error: {str(e)}',
                  {'traceback': traceback.format_exc()})

    finally:
        # Save all collected round data — runs even after crashes so partial data is preserved
        try:
            def _wrap_rounds(rounds_list):
                return {
                    "target": ip_settings.TARGET_IP,
                    "total_rounds": round_num,
                    "final_result": "SUCCESS" if final_success else "FAILED",
                    "rounds": rounds_list,
                }

            if ac_rounds:
                save_result.save_json_results('ac', test_init_time, _wrap_rounds(ac_rounds))
            if exec_rounds:
                save_result.save_json_results('exec', test_init_time, _wrap_rounds(exec_rounds))
            if classification_rounds:
                save_result.save_json_results('classification', test_init_time, _wrap_rounds(classification_rounds))
            if reval_rounds:
                save_result.save_json_results('reval', test_init_time, _wrap_rounds(reval_rounds))
            if exec_fix_rounds:
                save_result.save_json_results('exec_fix', test_init_time, _wrap_rounds(exec_fix_rounds))
        except Exception as save_err:
            print(f"\n[WARN] Failed to save result files: {save_err}")

        # Save token usage
        token_tracker.save(test_init_time)

        if db.current_run_id:
            db.end_run(status='completed')
            print("Run ended successfully")

if __name__ == "__main__":
    args = parse_cli_args()
    asyncio.run(main(args))