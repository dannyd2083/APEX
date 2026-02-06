from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agents.config.constants import OPENROUTER_MODEL_NAME
from agents.config.settings import llm_settings
from agents.helpers.token_tracker import token_tracker


class OpenRouterLLM:
    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=llm_settings.OPENROUTER_API_KEY,
            base_url=llm_settings.OPENROUTER_BASE_URL,
            model=OPENROUTER_MODEL_NAME,
            max_tokens=1000
        )
        self.model_name = OPENROUTER_MODEL_NAME

    def _call(self, prompt: str, phase: str = "unknown") -> str:
        """Call the LLM and track token usage."""
        # Estimate input tokens (rough: 1 token ≈ 4 chars)
        input_tokens = len(prompt) // 4

        response = self.llm.invoke(prompt)
        output_text = response.content if hasattr(response, 'content') else str(response)

        # Get actual token usage if available
        if hasattr(response, 'response_metadata'):
            metadata = response.response_metadata
            if 'token_usage' in metadata:
                input_tokens = metadata['token_usage'].get('prompt_tokens', input_tokens)
                output_tokens = metadata['token_usage'].get('completion_tokens', len(output_text) // 4)
            else:
                output_tokens = len(output_text) // 4
        else:
            output_tokens = len(output_text) // 4

        # Log to tracker
        token_tracker.log_call(
            provider="openrouter",
            phase=phase,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_name
        )

        return output_text

    def _create_agent(self, tools, response_format):
        return create_agent(
            model=self.llm,
            tools=tools,
            response_format=response_format
        )
