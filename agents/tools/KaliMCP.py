import sys
from langchain.agents.structured_output import ToolStrategy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel
from agents.config.settings import project_root, ip_settings
from agents.helpers.token_tracker import token_tracker

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

                # Track token usage from agent loop messages
                messages = result.get("messages", [])
                total_input = 0
                total_output = 0
                call_count = 0
                for msg in messages:
                    if hasattr(msg, 'response_metadata'):
                        usage = msg.response_metadata.get('token_usage', {})
                        if usage:
                            total_input += usage.get('prompt_tokens', 0)
                            total_output += usage.get('completion_tokens', 0)
                            call_count += 1
                if call_count > 0:
                    token_tracker.log_call(
                        provider="openrouter",
                        phase="recon",
                        input_tokens=total_input,
                        output_tokens=total_output,
                        model="x-ai/grok-4"
                    )
                    print(f"[TOKENS] Recon: {call_count} LLM calls, {total_input} input + {total_output} output tokens")

        return result
