import psycopg2
from psycopg2.extras import Json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseLogger:
    def __init__(self):
        self.conn_params = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME")
        }
        self.current_run_id = None
    
    def get_connection(self):
        return psycopg2.connect(
            host=self.conn_params["host"],
            port=self.conn_params["port"],
            user=self.conn_params["user"],
            password=self.conn_params["password"],
            dbname=self.conn_params["database"],
            sslmode=os.getenv("DB_SSLMODE", "prefer")
        )
    
    def start_run(self, target_ip, target_os, description=None):
        """Create new attack run and return run_id"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO attack_runs (target_ip, target_os, status, description) 
                   VALUES (%s, %s, 'running', %s) RETURNING run_id""",
                (target_ip, target_os, description)
            )
            self.current_run_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Started new attack run: run_id={self.current_run_id}")
            self.log_raw('orchestrator', 'INFO', f'Started attack run against {target_ip}', 
                        {'target_os': target_os, 'run_id': self.current_run_id})
            return self.current_run_id
        except Exception as e:
            print(f"Failed to start run: {e}")
            return None
    
    def log_command(self, tool_name, command_text, target_ip, agent_id=None):
        """Log individual command execution - returns command_id"""
        if not self.current_run_id:
            return None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO commands 
                   (run_id, tool_name, command_text, target_ip, started_at, agent_id) 
                   VALUES (%s, %s, %s, %s, NOW(), %s) 
                   RETURNING command_id""",
                (self.current_run_id, tool_name, command_text, target_ip, agent_id)
            )
            command_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Logged command: {tool_name} (command_id={command_id})")
            return command_id
        except Exception as e:
            print(f"Failed to log command: {e}")
            return None
    
    def update_command_result(self, command_id, success, raw_output, exit_code=0, 
                             error_message=None, duration_seconds=None):
        """Update command with execution results"""
        if not command_id:
            return
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """UPDATE commands 
                   SET ended_at = NOW(), 
                       success = %s, 
                       raw_output = %s, 
                       exit_code = %s,
                       error_message = %s,
                       duration_seconds = %s
                   WHERE command_id = %s""",
                (success, raw_output, exit_code, error_message, duration_seconds, command_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Updated command {command_id} result (success={success})")
        except Exception as e:
            print(f"Failed to update command result: {e}")
    
    def log_recon(self, tool_used, raw_output, result_json, target_ip=None, command_id=None, agent_id=None):
        """Log reconnaissance results"""
        if not self.current_run_id:
            print("No active run_id, skipping recon log")
            return None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO recon_results 
                   (run_id, command_id, agent_id, target_ip, tool_used, result_json, raw_output) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING recon_id""",
                (self.current_run_id, command_id, agent_id, target_ip, tool_used, 
                 Json(result_json), str(raw_output))
            )
            recon_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Logged recon results (recon_id={recon_id})")
            return recon_id
        except Exception as e:
            print(f"Failed to log recon: {e}")
            return None
    
    def log_attack_chain(self, attack_surface, proposed_stages, chain_json, 
                        recon_id=None, mitre_attack_ids=None):
        """Log attack chain planning"""
        if not self.current_run_id:
            print("No active run_id, skipping attack chain log")
            return None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO attack_chains 
                   (run_id, recon_id, attack_surface, proposed_stages, chain_json, mitre_attack_ids) 
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING chain_id""",
                (self.current_run_id, recon_id, attack_surface, 
                 Json(proposed_stages), Json(chain_json), mitre_attack_ids)
            )
            chain_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Logged attack chain (chain_id={chain_id})")
            return chain_id
        except Exception as e:
            print(f"Failed to log attack chain: {e}")
            return None
    
    def log_llm_decision(self, llm_model, prompt, response, reasoning=None, 
                        command_id=None, tokens_used=None):
        """Log LLM decisions"""
        if not self.current_run_id:
            return None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO llm_decisions 
                   (run_id, command_id, llm_model, prompt, response, reasoning, 
                    tokens_used) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING decision_id""",
                (self.current_run_id, command_id, llm_model, prompt[:2000], 
                 response[:10000], reasoning, tokens_used)
            )
            decision_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Logged LLM decision (decision_id={decision_id}, model={llm_model})")
            return decision_id
        except Exception as e:
            print(f"Failed to log LLM decision: {e}")
            return None
    
    def log_vulnerability(self, target_ip, port, service_name, service_version, 
                         vulnerability_type, severity, cve_id=None, description=None, 
                         recon_id=None, mitre_attack_id=None):
        """Log discovered vulnerabilities"""
        if not self.current_run_id:
            return None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO vulnerabilities 
                   (run_id, recon_id, target_ip, port, service_name, service_version,
                    vulnerability_type, severity, cve_id, description, mitre_attack_id) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING vuln_id""",
                (self.current_run_id, recon_id, target_ip, port, service_name, 
                 service_version, vulnerability_type, severity, cve_id, description, 
                 mitre_attack_id)
            )
            vuln_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Logged vulnerability: {vulnerability_type} on port {port} (vuln_id={vuln_id})")
            return vuln_id
        except Exception as e:
            print(f"Failed to log vulnerability: {e}")
            return None
    
    def log_raw(self, source, log_level, message, metadata=None):
        """Log raw debug messages"""
        if not self.current_run_id:
            return
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO raw_logs 
                   (run_id, source, log_level, message, metadata) 
                   VALUES (%s, %s, %s, %s, %s)""",
                (self.current_run_id, source, log_level, message, 
                 Json(metadata) if metadata else None)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Failed to log raw: {e}")
    
    def register_agent(self, name, agent_type, ip_address=None, status='active'):
        """Register an agent"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO agents (name, type, ip_address, status, last_seen) 
                   VALUES (%s, %s, %s, %s, NOW()) 
                   RETURNING agent_id""",
                (name, agent_type, ip_address, status)
            )
            agent_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Registered agent: {name} (agent_id={agent_id})")
            return agent_id
        except Exception as e:
            print(f"Failed to register agent: {e}")
            return None
    
    def end_run(self, status='completed'):
        """Mark run as complete"""
        if not self.current_run_id:
            return
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """UPDATE attack_runs 
                   SET ended_at = NOW(), status = %s 
                   WHERE run_id = %s""",
                (status, self.current_run_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Ended attack run: {status}")
            self.log_raw('orchestrator', 'INFO', f'Ended attack run with status: {status}', 
                        {'run_id': self.current_run_id, 'final_status': status})
        except Exception as e:
            print(f"Failed to end run: {e}")