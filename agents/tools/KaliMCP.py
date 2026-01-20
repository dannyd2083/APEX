import sys
from langchain.agents.structured_output import ToolStrategy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
# from pathlib import Path
from pydantic import BaseModel
from agents.config.settings import project_root, ip_settings

class KaliMCPResponse(BaseModel):
    output: str

class KaliMCP:
    def __init__(self):
        self.config = self._params()
        self.response_format = ToolStrategy(KaliMCPResponse)

    def _params(self) -> dict:
        return StdioServerParameters(
            command = sys.executable,
            args = [
                f"{project_root}/mcp/mcp_server.py",
                "--server",
                f"http://{ip_settings.KALI_IP}:5000"
            ],
        )

    async def _call(self, llm, question):
        async with stdio_client(self.config) as (read, write):
            async with ClientSession(read, write) as kali_session:
                await kali_session.initialize() 
                tools = await load_mcp_tools(kali_session)
                agent = llm._create_agent(tools, self.response_format)

                result = await agent.ainvoke({
                    "messages": question
                })
        return result
