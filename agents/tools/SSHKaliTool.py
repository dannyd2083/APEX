import asyncio
import asyncssh
import re
from typing import List, Dict, Any, Optional


class SSHKaliTool:
    """
    Asynchronous SSH command executor for Kali Linux.
    Supports:
        - Async command execution
        - Timeout handling
        - Interactive command detection
        - tmux session wrapping for interactive tools (e.g., msfconsole)
        - Persistent interactive sessions across multiple commands
        - Command sanitization
        - Parallel execution (max 5 concurrent)
        - Context manager for connection lifecycle
    """

    def __init__(self, host, username, password=None, key_path=None, max_concurrent=5, timeout=60):
        self.host = host
        self.username = username
        self.password = password
        self.key_path = key_path
        self.timeout = timeout
        self.sem = asyncio.Semaphore(max_concurrent)
        self.conn = None
        self.persistent_sessions = {}  # Track persistent tmux sessions

    async def __aenter__(self):
        """Establish SSH connection when entering context"""
        try:
            self.conn = await asyncssh.connect(
                self.host,
                username=self.username,
                password=self.password,
                client_keys=[self.key_path] if self.key_path else None,
                known_hosts=None
            )
            print(f"[SSH] Connected to {self.host}")
            return self
        except Exception as e:
            print(f"[SSH] Connection failed: {e}")
            raise

    async def __aexit__(self, *exc):
        """Close SSH connection and cleanup persistent sessions"""
        # Cleanup all persistent sessions
        for session_name in list(self.persistent_sessions.keys()):
            await self.close_persistent_session(session_name)
        
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()
            print(f"[SSH] Disconnected from {self.host}")

    # ---------------------------
    # Persistent Session Management
    # ---------------------------
    async def start_persistent_session(self, session_name: str, initial_command: str = "bash") -> Dict[str, Any]:
        """
        Start a persistent tmux session that can be used for multiple commands.
        
        Args:
            session_name: Unique name for the session
            initial_command: Command to run in the session (default: bash)
        
        Returns:
            Dict with success status and session info
        """
        try:
            # Kill any existing session with same name
            await self.conn.run(f"tmux kill-session -t {session_name} 2>/dev/null || true")
            
            # Create new tmux session with initial command
            await self.conn.run(f"tmux new-session -d -s {session_name} {initial_command}")
            
            # Give it a moment to start
            await asyncio.sleep(2)
            
            # Store session info
            self.persistent_sessions[session_name] = {
                "name": session_name,
                "command": initial_command,
                "created_at": asyncio.get_event_loop().time()
            }
            
            print(f"[SSH] Started persistent session: {session_name}")
            
            return {
                "success": True,
                "session_name": session_name,
                "message": f"Persistent session '{session_name}' started"
            }
            
        except Exception as e:
            print(f"[SSH] Failed to start persistent session {session_name}: {e}")
            return {
                "success": False,
                "session_name": session_name,
                "error": str(e)
            }

    async def run_in_persistent_session(self, session_name: str, command: str, 
                                       wait_time: int = 3) -> Dict[str, Any]:
        """
        Execute a command in an existing persistent session.
        
        Args:
            session_name: Name of the persistent session
            command: Command to execute
            wait_time: Seconds to wait for command output
        
        Returns:
            Dict with command output and status
        """
        if session_name not in self.persistent_sessions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Session '{session_name}' does not exist",
                "return_code": -1
            }
        
        try:
            print(f"[SSH] Running in session {session_name}: {command[:80]}...")
            
            # Send command to the session
            escaped_cmd = command.replace("'", "'\\''")
            await self.conn.run(f"tmux send-keys -t {session_name} '{escaped_cmd}' ENTER")
            
            # Wait for command to execute
            await asyncio.sleep(wait_time)
            
            # Capture output
            result = await self.conn.run(f"tmux capture-pane -pt {session_name} -S -100")
            
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr if result.stderr else "",
                "return_code": 0
            }
            
        except Exception as e:
            print(f"[SSH] Error running command in session {session_name}: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1
            }

    async def close_persistent_session(self, session_name: str) -> Dict[str, Any]:
        """
        Close a persistent session.
        
        Args:
            session_name: Name of the session to close
        
        Returns:
            Dict with success status
        """
        try:
            await self.conn.run(f"tmux kill-session -t {session_name} 2>/dev/null || true")
            
            if session_name in self.persistent_sessions:
                del self.persistent_sessions[session_name]
            
            print(f"[SSH] Closed persistent session: {session_name}")
            
            return {
                "success": True,
                "message": f"Session '{session_name}' closed"
            }
            
        except Exception as e:
            print(f"[SSH] Error closing session {session_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def list_persistent_sessions(self) -> List[str]:
        """List all active persistent sessions."""
        return list(self.persistent_sessions.keys())

    # ---------------------------
    # Standard command execution
    # ---------------------------
    async def run_command(self, cmd: str) -> Dict[str, Any]:
        """Execute a command via SSH with proper error handling"""
        async with self.sem:
            print(f"[SSH] Executing: {cmd[:100]}...")
            
            try:
                # Detect interactive commands
                if self._is_interactive(cmd):
                    result = await asyncio.wait_for(
                        self._run_tmux_command(cmd), 
                        timeout=self.timeout
                    )
                else:
                    result = await asyncio.wait_for(
                        self._run_simple(cmd), 
                        timeout=self.timeout
                    )
                
                # Special handling for verification commands
                if result['success']:
                    print(f"[SSH] Command succeeded")
                else:
                    print(f"[SSH] Command failed (exit {result['return_code']})")
                
                return result

            except asyncio.TimeoutError:
                print(f"[SSH] Command timed out after {self.timeout}s")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Timeout after {self.timeout}s",
                    "return_code": -1,
                }
            except Exception as e:
                print(f"[SSH] Command error: {e}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": str(e),
                    "return_code": -1,
                }

    async def _run_simple(self, cmd: str):
        """Execute a simple command and return results"""
        try:
            result = await self.conn.run(cmd, check=False)
            return {
                "success": result.exit_status == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.exit_status,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "return_code": -1,
            }

    async def _run_tmux_command(self, cmd: str):
        """Execute interactive commands using tmux session wrapper"""
        session = f"auto_{abs(hash(cmd)) % 10000}"
        
        try:
            # Kill any existing session with same name
            await self.conn.run(f"tmux kill-session -t {session} 2>/dev/null || true")
            
            # Create new tmux session
            await self.conn.run(f"tmux new-session -d -s {session}")
            
            # Send command to session
            escaped_cmd = cmd.replace("'", "'\\''")
            await self.conn.run(f"tmux send-keys -t {session} '{escaped_cmd}' ENTER")
            
            # Wait for command to execute
            await asyncio.sleep(10)
            
            # Capture output from pane
            result = await self.conn.run(f"tmux capture-pane -pt {session} -S -100")
            
            # Kill session
            await self.conn.run(f"tmux kill-session -t {session}")
            
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr if result.stderr else "",
                "return_code": 0,
            }
            
        except Exception as e:
            # Cleanup on error
            try:
                await self.conn.run(f"tmux kill-session -t {session} 2>/dev/null || true")
            except:
                pass
            
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Tmux execution error: {str(e)}",
                "return_code": -1,
            }

    def _is_interactive(self, cmd):
        """Detect if a command is interactive and needs tmux wrapper"""
        interactive_patterns = [
            "msfconsole",
            "nc -l",
            "python -i",
            "bash -i",
            "sh -i",
            "mysql",
            "ftp"
        ]
        return any(pattern in cmd for pattern in interactive_patterns)
    
    async def run_command_with_analysis(self, cmd: str, success_indicators: list = None) -> Dict[str, Any]:
        """
        Execute command and analyze output for success indicators.
        Useful for Metasploit and other tools where exit code isn't reliable.
        """
        result = await self.run_command(cmd)
        
        # If success indicators provided, check output
        if success_indicators and result['stdout']:
            output_lower = result['stdout'].lower()
            for indicator in success_indicators:
                if indicator.lower() in output_lower:
                    result['success'] = True
                    result['matched_indicator'] = indicator
                    break
        
        return result