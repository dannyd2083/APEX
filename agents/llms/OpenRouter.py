import requests as _requests

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agents.config.constants import OPENROUTER_MODEL_NAME
from agents.config.settings import llm_settings
from agents.helpers.token_tracker import token_tracker


class OpenRouterLLM:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or OPENROUTER_MODEL_NAME
        self.llm = ChatOpenAI(
            api_key=llm_settings.OPENROUTER_API_KEY,
            base_url=llm_settings.OPENROUTER_BASE_URL,
            model=self.model_name,
            max_tokens=4096
        )

    def _fetch_generation_cost(self, gen_id: str) -> float | None:
        """Query OpenRouter /api/v1/generation for the exact cost of a call."""
        try:
            r = _requests.get(
                f"https://openrouter.ai/api/v1/generation?id={gen_id}",
                headers={"Authorization": f"Bearer {llm_settings.OPENROUTER_API_KEY}"},
                timeout=5,
            )
            if r.status_code == 200:
                return float(r.json().get("data", {}).get("total_cost", 0.0))
        except Exception:
            pass
        return None

    def _call(self, prompt: str, phase: str = "unknown", retries: int = 3,
              json_mode: bool = False) -> str:
        """Call the LLM and track exact cost via OpenRouter generation API."""
        import time
        input_tokens = len(prompt) // 4  # rough fallback estimate

        invoker = (
            self.llm.bind(response_format={"type": "json_object"})
            if json_mode else self.llm
        )

        last_err = None
        for attempt in range(1, retries + 1):
            try:
                response = invoker.invoke(prompt)
                break
            except Exception as e:
                last_err = e
                if attempt < retries:
                    wait = attempt * 5
                    print(f"[LLM] {phase} attempt {attempt} failed ({e}) — retrying in {wait}s")
                    time.sleep(wait)
        else:
            raise last_err

        output_text = response.content if hasattr(response, "content") else str(response)

        output_tokens = len(output_text) // 4
        actual_cost   = None

        if hasattr(response, "response_metadata"):
            meta  = response.response_metadata
            usage = meta.get("token_usage", {})
            input_tokens  = usage.get("prompt_tokens",     input_tokens)
            output_tokens = usage.get("completion_tokens", output_tokens)
            # OpenRouter includes exact cost directly in token_usage.cost
            if "cost" in usage:
                actual_cost = float(usage["cost"])
                print(f"[Cost] {phase}: ${actual_cost:.5f}")

        token_tracker.log_call(
            provider="openrouter",
            phase=phase,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_name,
            actual_cost_usd=actual_cost,
        )

        return output_text

    def _create_agent(self, tools, response_format):
        return create_agent(
            model=self.llm,
            tools=tools,
            response_format=response_format
        )
