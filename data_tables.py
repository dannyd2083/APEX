"""
Database Viewer Script
======================
View all data in the AI Battle Bots database without Supabase dashboard.

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    python view_database.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import json
from datetime import datetime

# Load environment variables
load_dotenv()

def get_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
        sslmode=os.getenv("DB_SSLMODE", "prefer")
    )

def print_header(title):
    """Print formatted header"""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def view_attack_runs(conn, limit=10):
    """View recent attack runs"""
    print_header("ATTACK RUNS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT run_id, target_ip, target_os, status, 
               started_at, ended_at, description
        FROM attack_runs 
        ORDER BY started_at DESC 
        LIMIT %s
    """, (limit,))
    
    runs = cursor.fetchall()
    
    if not runs:
        print("No attack runs found.")
        return
    
    for run in runs:
        print(f"\n[Run #{run['run_id']}]")
        print(f"  Target: {run['target_ip']} ({run['target_os']})")
        print(f"  Status: {run['status']}")
        print(f"  Started: {run['started_at']}")
        print(f"  Ended: {run['ended_at'] if run['ended_at'] else 'Still running'}")
        if run['description']:
            print(f"  Description: {run['description']}")
    
    cursor.close()

def view_recon_results(conn, run_id=None, limit=5):
    """View reconnaissance results"""
    print_header("RECON RESULTS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if run_id:
        cursor.execute("""
            SELECT recon_id, run_id, tool_used, target_ip, 
                   result_json, created_at
            FROM recon_results 
            WHERE run_id = %s
            ORDER BY created_at DESC
        """, (run_id,))
    else:
        cursor.execute("""
            SELECT recon_id, run_id, tool_used, target_ip, 
                   result_json, created_at
            FROM recon_results 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
    
    results = cursor.fetchall()
    
    if not results:
        print("No recon results found.")
        return
    
    for result in results:
        print(f"\n[Recon #{result['recon_id']}] Run #{result['run_id']}")
        print(f"  Tool: {result['tool_used']}")
        print(f"  Target: {result['target_ip']}")
        print(f"  Date: {result['created_at']}")
        
        if result['result_json']:
            try:
                data = result['result_json']
                if isinstance(data, dict):
                    if 'open_ports' in data:
                        print(f"  Open Ports: {len(data['open_ports'])}")
                        for i, port in enumerate(data['open_ports'][:3], 1):
                            service = port.get('service', 'unknown')
                            port_num = port.get('port', '?')
                            print(f"    {i}. Port {port_num}: {service}")
                        if len(data['open_ports']) > 3:
                            print(f"    ... and {len(data['open_ports']) - 3} more")
            except Exception as e:
                print(f"  (Could not parse result_json: {e})")
    
    cursor.close()

def view_vulnerabilities(conn, run_id=None, limit=10):
    """View discovered vulnerabilities"""
    print_header("VULNERABILITIES")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if run_id:
        cursor.execute("""
            SELECT vuln_id, target_ip, port, service_name, 
                   service_version, vulnerability_type, severity, 
                   cve_id, description, discovered_at
            FROM vulnerabilities 
            WHERE run_id = %s
            ORDER BY severity DESC, discovered_at DESC
        """, (run_id,))
    else:
        cursor.execute("""
            SELECT vuln_id, target_ip, port, service_name, 
                   service_version, vulnerability_type, severity, 
                   cve_id, description, discovered_at
            FROM vulnerabilities 
            ORDER BY severity DESC, discovered_at DESC 
            LIMIT %s
        """, (limit,))
    
    vulns = cursor.fetchall()
    
    if not vulns:
        print("No vulnerabilities found.")
        return
    
    severity_colors = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'low': '🟢'
    }
    
    for vuln in vulns:
        severity_icon = severity_colors.get(vuln['severity'], '⚪')
        print(f"\n{severity_icon} [Vuln #{vuln['vuln_id']}] {vuln['severity'].upper()}")
        print(f"  Target: {vuln['target_ip']}:{vuln['port']}")
        print(f"  Service: {vuln['service_name']} {vuln['service_version'] or ''}")
        print(f"  Type: {vuln['vulnerability_type']}")
        if vuln['cve_id']:
            print(f"  CVE: {vuln['cve_id']}")
        if vuln['description']:
            print(f"  Description: {vuln['description']}")
        print(f"  Discovered: {vuln['discovered_at']}")
    
    cursor.close()

def view_attack_chains(conn, run_id=None, limit=5):
    """View attack chain recommendations"""
    print_header("ATTACK CHAINS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if run_id:
        cursor.execute("""
            SELECT chain_id, run_id, attack_surface, 
                   proposed_stages, chain_json, created_at
            FROM attack_chains 
            WHERE run_id = %s
            ORDER BY created_at DESC
        """, (run_id,))
    else:
        cursor.execute("""
            SELECT chain_id, run_id, attack_surface, 
                   proposed_stages, chain_json, created_at
            FROM attack_chains 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
    
    chains = cursor.fetchall()
    
    if not chains:
        print("No attack chains found.")
        return
    
    for chain in chains:
        print(f"\n[Chain #{chain['chain_id']}] Run #{chain['run_id']}")
        print(f"  Date: {chain['created_at']}")
        print(f"  Attack Surface: {chain['attack_surface'][:100]}...")
        
        if chain['proposed_stages']:
            stages = chain['proposed_stages']
            if isinstance(stages, dict):
                print("\n  Proposed Attack Stages:")
                for stage_name, stage_data in stages.items():
                    print(f"    • {stage_name.replace('_', ' ').title()}")
                    if isinstance(stage_data, dict) and 'description' in stage_data:
                        desc = stage_data['description'][:80]
                        print(f"      {desc}...")
    
    cursor.close()

def view_llm_decisions(conn, run_id=None, limit=5):
    """View LLM decisions and prompts"""
    print_header("LLM DECISIONS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if run_id:
        cursor.execute("""
            SELECT decision_id, llm_model, reasoning,
                   LEFT(prompt, 100) as prompt_preview,
                   LEFT(response, 100) as response_preview,
                   created_at
            FROM llm_decisions 
            WHERE run_id = %s
            ORDER BY created_at DESC
        """, (run_id,))
    else:
        cursor.execute("""
            SELECT decision_id, llm_model, reasoning,
                   LEFT(prompt, 100) as prompt_preview,
                   LEFT(response, 100) as response_preview,
                   created_at
            FROM llm_decisions 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
    
    decisions = cursor.fetchall()
    
    if not decisions:
        print("No LLM decisions found.")
        return
    
    for decision in decisions:
        print(f"\n[Decision #{decision['decision_id']}]")
        print(f"  Model: {decision['llm_model']}")
        print(f"  Reasoning: {decision['reasoning']}")
        print(f"  Date: {decision['created_at']}")
        print(f"  Prompt: {decision['prompt_preview']}...")
        print(f"  Response: {decision['response_preview']}...")
    
    cursor.close()

def view_commands(conn, run_id=None, limit=10, show_full=False):
    """View executed commands"""
    print_header("COMMANDS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if show_full:
        select_fields = "command_id, tool_name, target_ip, command_text, raw_output, success, started_at, ended_at, error_message"
    else:
        select_fields = """command_id, tool_name, target_ip, 
                   success, started_at, ended_at,
                   LEFT(command_text, 80) as command_preview"""
    
    if run_id:
        cursor.execute(f"""
            SELECT {select_fields}
            FROM commands 
            WHERE run_id = %s
            ORDER BY started_at DESC
        """, (run_id,))
    else:
        cursor.execute(f"""
            SELECT {select_fields}
            FROM commands 
            ORDER BY started_at DESC 
            LIMIT %s
        """, (limit,))
    
    commands = cursor.fetchall()
    
    if not commands:
        print("No commands found.")
        return
    
    for cmd in commands:
        status = "✓" if cmd['success'] else "✗"
        print(f"\n{status} [Command #{cmd['command_id']}]")
        print(f"  Tool: {cmd['tool_name']}")
        print(f"  Target: {cmd['target_ip']}")
        
        if show_full:
            print(f"  Command: {cmd['command_text']}")
        else:
            print(f"  Command: {cmd['command_preview']}...")
        
        print(f"  Started: {cmd['started_at']}")
        if cmd['ended_at']:
            duration = (cmd['ended_at'] - cmd['started_at']).total_seconds()
            print(f"  Duration: {duration:.2f}s")
        
        if show_full:
            if cmd['error_message']:
                print(f"  Error: {cmd['error_message']}")
            if cmd['raw_output']:
                print(f"\n  Raw Output:")
                print("  " + "-"*60)
                output_lines = cmd['raw_output'].split('\n')
                for line in output_lines[:20]:  # Show first 20 lines
                    print(f"  {line}")
                if len(output_lines) > 20:
                    print(f"  ... ({len(output_lines) - 20} more lines)")
                print("  " + "-"*60)
    
    cursor.close()

def view_raw_logs(conn, run_id=None, limit=20, log_level=None):
    """View raw debug logs"""
    print_header("RAW LOGS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT log_id, run_id, source, log_level, message, 
               metadata, created_at
        FROM raw_logs 
        WHERE 1=1
    """
    params = []
    
    if run_id:
        query += " AND run_id = %s"
        params.append(run_id)
    
    if log_level:
        query += " AND log_level = %s"
        params.append(log_level.upper())
    
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, params)
    logs = cursor.fetchall()
    
    if not logs:
        print("No logs found.")
        return
    
    level_icons = {
        'INFO': '📘',
        'WARN': '⚠️',
        'ERROR': '❌',
        'DEBUG': '🔍'
    }
    
    for log in logs:
        icon = level_icons.get(log['log_level'], '📝')
        print(f"\n{icon} [Log #{log['log_id']}] {log['log_level']}")
        print(f"  Source: {log['source']}")
        print(f"  Run: #{log['run_id']}")
        print(f"  Time: {log['created_at']}")
        print(f"  Message: {log['message']}")
        
        if log['metadata']:
            print(f"  Metadata:")
            metadata = log['metadata']
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    print(f"    {key}: {value}")
    
    cursor.close()

def view_agents(conn):
    """View registered agents"""
    print_header("REGISTERED AGENTS")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT agent_id, name, type, ip_address, status, last_seen
        FROM agents 
        ORDER BY last_seen DESC
    """)
    
    agents = cursor.fetchall()
    
    if not agents:
        print("No agents found.")
        return
    
    for agent in agents:
        print(f"\n[Agent #{agent['agent_id']}] {agent['name']}")
        print(f"  Type: {agent['type']}")
        print(f"  IP: {agent['ip_address']}")
        print(f"  Status: {agent['status']}")
        print(f"  Last Seen: {agent['last_seen']}")
    
    cursor.close()

def view_full_recon_output(conn, recon_id):
    """View complete recon output including structured and raw"""
    print_header(f"FULL RECON OUTPUT - Recon #{recon_id}")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT recon_id, run_id, tool_used, target_ip, 
               result_json, raw_output, created_at
        FROM recon_results 
        WHERE recon_id = %s
    """, (recon_id,))
    
    result = cursor.fetchone()
    
    if not result:
        print(f"Recon #{recon_id} not found.")
        cursor.close()
        return
    
    print(f"\n[Recon #{result['recon_id']}]")
    print(f"  Run: #{result['run_id']}")
    print(f"  Tool: {result['tool_used']}")
    print(f"  Target: {result['target_ip']}")
    print(f"  Date: {result['created_at']}")
    
    print("\n" + "="*80)
    print("STRUCTURED OUTPUT (JSON):")
    print("="*80)
    if result['result_json']:
        print(json.dumps(result['result_json'], indent=2))
    else:
        print("(No structured output)")
    
    print("\n" + "="*80)
    print("RAW OUTPUT:")
    print("="*80)
    if result['raw_output']:
        print(result['raw_output'])
    else:
        print("(No raw output)")
    
    cursor.close()

def view_full_attack_chain(conn, chain_id):
    """View complete attack chain with all details"""
    print_header(f"FULL ATTACK CHAIN - Chain #{chain_id}")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT chain_id, run_id, recon_id, attack_surface, 
               proposed_stages, chain_json, mitre_attack_ids, created_at
        FROM attack_chains 
        WHERE chain_id = %s
    """, (chain_id,))
    
    chain = cursor.fetchone()
    
    if not chain:
        print(f"Attack chain #{chain_id} not found.")
        cursor.close()
        return
    
    print(f"\n[Chain #{chain['chain_id']}]")
    print(f"  Run: #{chain['run_id']}")
    print(f"  Recon: #{chain['recon_id']}")
    print(f"  Date: {chain['created_at']}")
    
    print("\n" + "="*80)
    print("ATTACK SURFACE:")
    print("="*80)
    print(chain['attack_surface'])
    
    print("\n" + "="*80)
    print("PROPOSED STAGES:")
    print("="*80)
    if chain['proposed_stages']:
        print(json.dumps(chain['proposed_stages'], indent=2))
    else:
        print("(No proposed stages)")
    
    print("\n" + "="*80)
    print("COMPLETE CHAIN JSON:")
    print("="*80)
    if chain['chain_json']:
        print(json.dumps(chain['chain_json'], indent=2))
    else:
        print("(No chain JSON)")
    
    if chain['mitre_attack_ids']:
        print("\n" + "="*80)
        print("MITRE ATT&CK IDs:")
        print("="*80)
        for mitre_id in chain['mitre_attack_ids']:
            print(f"  • {mitre_id}")
    
    cursor.close()

def view_full_llm_decision(conn, decision_id):
    """View complete LLM decision with full prompt and response"""
    print_header(f"FULL LLM DECISION - Decision #{decision_id}")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT decision_id, run_id, command_id, llm_model, 
               prompt, response, reasoning, tokens_used, created_at
        FROM llm_decisions 
        WHERE decision_id = %s
    """, (decision_id,))
    
    decision = cursor.fetchone()
    
    if not decision:
        print(f"LLM decision #{decision_id} not found.")
        cursor.close()
        return
    
    print(f"\n[Decision #{decision['decision_id']}]")
    print(f"  Run: #{decision['run_id']}")
    print(f"  Model: {decision['llm_model']}")
    print(f"  Reasoning: {decision['reasoning']}")
    print(f"  Date: {decision['created_at']}")
    if decision['tokens_used']:
        print(f"  Tokens: {decision['tokens_used']}")
    
    print("\n" + "="*80)
    print("FULL PROMPT:")
    print("="*80)
    print(decision['prompt'])
    
    print("\n" + "="*80)
    print("FULL RESPONSE:")
    print("="*80)
    print(decision['response'])
    
    cursor.close()

def view_summary(conn):
    """View database summary statistics"""
    print_header("DATABASE SUMMARY")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Count records in each table
    tables = [
        'attack_runs', 'agents', 'commands', 'recon_results',
        'attack_chains', 'llm_decisions', 'vulnerabilities', 'raw_logs'
    ]
    
    print("\nRecord Counts:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        count = cursor.fetchone()['count']
        print(f"  {table:20s}: {count:>6d} records")
    
    # Latest attack run
    cursor.execute("""
        SELECT run_id, target_ip, status, started_at 
        FROM attack_runs 
        ORDER BY started_at DESC 
        LIMIT 1
    """)
    latest = cursor.fetchone()
    
    if latest:
        print(f"\nLatest Attack Run:")
        print(f"  Run #{latest['run_id']}: {latest['target_ip']} ({latest['status']})")
        print(f"  Started: {latest['started_at']}")
    
    cursor.close()

def main():
    """Main function with interactive menu"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║          AI BATTLE BOTS - Database Viewer                      ║
    ║                                                                 ║
    ║  View all penetration testing data without Supabase dashboard  ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        conn = get_connection()
        print("✓ Connected to database successfully!\n")
        
        while True:
            print("\n" + "-"*60)
            print("MENU:")
            print("  1. View Summary")
            print("  2. View Attack Runs")
            print("  3. View Recon Results")
            print("  4. View Vulnerabilities")
            print("  5. View Attack Chains")
            print("  6. View LLM Decisions")
            print("  7. View Commands")
            print("  8. View Raw Logs")
            print("  9. View Agents")
            print(" 10. View Specific Run (by ID)")
            print(" 11. View Full Recon Output (by ID)")
            print(" 12. View Full Attack Chain (by ID)")
            print(" 13. View Full LLM Decision (by ID)")
            print(" 14. View Commands with Full Output")
            print("  0. Exit")
            print("-"*60)
            
            choice = input("\nEnter choice: ").strip()
            
            if choice == '0':
                print("\nGoodbye!")
                break
            elif choice == '1':
                view_summary(conn)
            elif choice == '2':
                limit = input("How many runs? (default 10): ").strip()
                limit = int(limit) if limit else 10
                view_attack_runs(conn, limit)
            elif choice == '3':
                limit = input("How many results? (default 5): ").strip()
                limit = int(limit) if limit else 5
                view_recon_results(conn, limit=limit)
            elif choice == '4':
                limit = input("How many vulnerabilities? (default 10): ").strip()
                limit = int(limit) if limit else 10
                view_vulnerabilities(conn, limit=limit)
            elif choice == '5':
                limit = input("How many chains? (default 5): ").strip()
                limit = int(limit) if limit else 5
                view_attack_chains(conn, limit=limit)
            elif choice == '6':
                limit = input("How many decisions? (default 5): ").strip()
                limit = int(limit) if limit else 5
                view_llm_decisions(conn, limit=limit)
            elif choice == '7':
                limit = input("How many commands? (default 10): ").strip()
                limit = int(limit) if limit else 10
                view_commands(conn, limit=limit)
            elif choice == '8':
                limit = input("How many logs? (default 20): ").strip()
                limit = int(limit) if limit else 20
                level = input("Filter by level? (INFO/WARN/ERROR or leave blank): ").strip().upper()
                view_raw_logs(conn, limit=limit, log_level=level if level else None)
            elif choice == '9':
                view_agents(conn)
            elif choice == '10':
                run_id = input("Enter Run ID: ").strip()
                if run_id.isdigit():
                    run_id = int(run_id)
                    print(f"\n📊 Viewing all data for Run #{run_id}")
                    view_attack_runs(conn, limit=1)
                    view_recon_results(conn, run_id=run_id)
                    view_vulnerabilities(conn, run_id=run_id)
                    view_attack_chains(conn, run_id=run_id)
                    view_llm_decisions(conn, run_id=run_id)
                    view_commands(conn, run_id=run_id)
                    view_raw_logs(conn, run_id=run_id, limit=20)
                else:
                    print("Invalid Run ID")
            elif choice == '11':
                recon_id = input("Enter Recon ID: ").strip()
                if recon_id.isdigit():
                    view_full_recon_output(conn, int(recon_id))
                else:
                    print("Invalid Recon ID")
            elif choice == '12':
                chain_id = input("Enter Chain ID: ").strip()
                if chain_id.isdigit():
                    view_full_attack_chain(conn, int(chain_id))
                else:
                    print("Invalid Chain ID")
            elif choice == '13':
                decision_id = input("Enter Decision ID: ").strip()
                if decision_id.isdigit():
                    view_full_llm_decision(conn, int(decision_id))
                else:
                    print("Invalid Decision ID")
            elif choice == '14':
                limit = input("How many commands? (default 5): ").strip()
                limit = int(limit) if limit else 5
                view_commands(conn, limit=limit, show_full=True)
            else:
                print("Invalid choice. Try again.")
        
        conn.close()
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()