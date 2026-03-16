import sys
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agents.config.settings import project_root, ip_settings


class KaliMCP:
    def __init__(self):
        self.config = self._params()
        # Persistent session state (set by __aenter__)
        self._cm      = None
        self._sess_cm = None
        self._session = None

    def _params(self) -> StdioServerParameters:
        return StdioServerParameters(
            command=sys.executable,
            args=[
                f"{project_root}/mcp/kali_bridge.py",
                "--server",
                f"http://{ip_settings.KALI_IP}:5000",
            ],
        )

    # ------------------------------------------------------------------
    # Persistent connection context manager
    # ------------------------------------------------------------------

    async def __aenter__(self):
        """Open kali_bridge.py once and keep it alive for all calls."""
        self._cm      = stdio_client(self.config)
        read, write   = await self._cm.__aenter__()
        self._sess_cm = ClientSession(read, write)
        self._session = await self._sess_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *args):
        if self._sess_cm:
            await self._sess_cm.__aexit__(*args)
        if self._cm:
            await self._cm.__aexit__(*args)
        self._session = self._sess_cm = self._cm = None

    # ------------------------------------------------------------------
    # Internal call — reuses persistent session or opens a one-shot one
    # ------------------------------------------------------------------

    async def _call_mcp_tool(self, tool_name: str, args: dict) -> str:
        if self._session:
            return await self._call_with(self._session, tool_name, args)

        # Fallback: no persistent session — open a temporary one
        async with stdio_client(self.config) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await self._call_with(session, tool_name, args)

    async def _call_with(self, session: ClientSession,
                         tool_name: str, args: dict) -> str:
        result = await session.call_tool(tool_name, args)
        if not result.content:
            return "(no output)"
        block = result.content[0]
        text  = block.text if hasattr(block, "text") else str(block)
        return self._parse_result(text)

    def _parse_result(self, text: str) -> str:
        try:
            data   = json.loads(text)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            rc     = data.get("return_code", "?")
            parts  = [f"[exit code: {rc}]"]
            if stdout:
                parts.append(f"[stdout]\n{stdout}")
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            return "\n".join(parts)
        except Exception:
            return text

    # ------------------------------------------------------------------
    # Public tool methods
    # ------------------------------------------------------------------

    async def execute(self, command: str) -> str:
        return await self._call_mcp_tool("execute_command", {"command": command})

    async def nmap_scan(self, target: str, ports: str = "") -> str:
        return await self._call_mcp_tool("nmap_scan", {
            "target": target, "scan_type": "-sV",
            "ports": ports, "additional_args": "",
        })

    async def gobuster_scan(self, url: str) -> str:
        return await self._call_mcp_tool("gobuster_scan", {
            "url": url, "mode": "dir",
            "wordlist": "/usr/share/wordlists/dirb/big.txt",
            "additional_args": "",
        })

    async def zap_spider(self, url: str, port: int = 8080) -> str:
        return await self._call_mcp_tool("zap_scan", {
            "url": url, "mode": "spider", "port": port,
        })

    async def sqlmap(self, url: str, data: str = "", extra: str = "") -> str:
        return await self._call_mcp_tool("sqlmap_scan", {
            "url": url, "data": data, "additional_args": extra,
        })

    async def autorecon(self, target: str) -> str:
        return await self._call_mcp_tool("autorecon_scan", {"target": target})

    async def zap_active(self, url: str, port: int = 8080) -> str:
        scan_out   = await self._call_mcp_tool("zap_scan", {
            "url": url, "mode": "active", "port": port,
        })
        alerts_out = await self._call_mcp_tool("zap_scan", {
            "url": "", "mode": "alerts", "port": port,
        })
        return scan_out + "\n\n[ZAP ALERTS]\n" + alerts_out
