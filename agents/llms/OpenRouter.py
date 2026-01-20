from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agents.config.constants import OPENROUTER_MODEL_NAME
from agents.config.settings import llm_settings

class OpenRouterLLM:
    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=llm_settings.OPENROUTER_API_KEY,
            base_url=llm_settings.OPENROUTER_BASE_URL,
            model=OPENROUTER_MODEL_NAME,
            max_tokens=1000
        )

    def _create_agent(self, tools, response_format):
        return create_agent(
            model=self.llm,
            tools=tools,
            response_format=response_format
        )