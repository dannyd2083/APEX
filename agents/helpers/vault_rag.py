from __future__ import annotations

import json
import requests
from mcp import ClientSession
from mcp.client.sse import sse_client

VAULT_URL = "http://localhost:3000"


class VaultRAG:
    """
    RAG over the redstack-vault knowledge base via its running SSE MCP server.

    Requires the vault server to be running (start_server.bat in redstack-vault).
    If it's not running, query() returns "" and the coordinator proceeds without it.
    """

    def _is_running(self) -> bool:
        try:
            r = requests.get(f"{VAULT_URL}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    async def query(self, topic: str, max_chains: int = 3, max_procs: int = 3) -> str:
        """
        Query the vault for attack patterns relevant to a topic.

        Returns a formatted text block ready for __RAG_CONTEXT__, or "" if
        the vault server isn't running or nothing relevant is found.
        """
        if not self._is_running():
            print("[VaultRAG] Vault server not running at localhost:3000 — skipping")
            return ""

        try:
            async with sse_client(f"{VAULT_URL}/sse") as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    chains_result = await session.call_tool(
                        "search_attack_chains",
                        {"query": topic}
                    )
                    chains = json.loads(chains_result.content[0].text)[:max_chains]

                    procs_result = await session.call_tool(
                        "text_search_procedures",
                        {"query": topic, "limit": max_procs}
                    )
                    procs = json.loads(procs_result.content[0].text)[:max_procs]

                    return self._format(chains, procs)

        except Exception as e:
            print(f"[VaultRAG] Query failed: {e}")
            return ""

    def _format(self, chains: list, procs: list) -> str:
        if not chains and not procs:
            return ""

        lines = ["=== Vault Intelligence ==="]

        for c in chains:
            lines.append(f"\nATTACK CHAIN: {c.get('name', '')}")
            desc = (c.get("description") or "")[:150]
            if desc:
                lines.append(f"  Description: {desc}")
            steps = c.get("steps") or []
            if steps:
                step_names = [s["name"] for s in steps if s.get("name")]
                lines.append(f"  Steps: {' → '.join(step_names[:5])}")
            tags = c.get("tags") or []
            if tags:
                lines.append(f"  Tags: {', '.join(tags[:6])}")

        for p in procs:
            lines.append(f"\nPROCEDURE: {p.get('name', '')}")
            desc = (p.get("description") or "")[:120]
            if desc:
                lines.append(f"  Description: {desc}")
            cmds = p.get("commands") or []
            if cmds:
                lines.append("  Commands:")
                for cmd in cmds[:3]:
                    lines.append(f"    {cmd.strip()[:120]}")

        return "\n".join(lines)
