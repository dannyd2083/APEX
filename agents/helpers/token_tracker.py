"""
Token Usage Tracker
Tracks token usage across LLM calls for cost monitoring.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from agents.config.settings import project_root

# Pricing per 1M tokens (approximate, check OpenRouter for current rates)
# AnythingLLM uses OpenRouter/Grok-4 underneath, so same pricing applies
PRICING = {
    "x-ai/grok-4":                      {"input": 3.00,  "output": 15.00},
    "anythingllm":                      {"input": 3.00,  "output": 15.00},
    "google/gemini-2.0-flash-exp:free":          {"input": 0.0, "output": 0.0},
    "qwen/qwen2.5-72b-instruct:free":            {"input": 0.0, "output": 0.0},
    "openai/gpt-oss-120b:free":                  {"input": 0.0,   "output": 0.0},
    "anthropic/claude-opus-4-5":                 {"input": 15.00, "output": 75.00},
    "anthropic/claude-3.5-haiku":                {"input": 0.80,  "output": 4.00},
    "meta-llama/llama-3.3-70b-instruct:free": {"input": 0.0, "output": 0.0},
    "deepseek/deepseek-r1:free":        {"input": 0.0,   "output": 0.0},
}


class TokenTracker:
    """Tracks token usage across a test run."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all counters for a new run."""
        self.usage = {
            "openrouter": {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "model": "x-ai/grok-4"
            },
            "anythingllm": {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "model": "unknown"
            }
        }
        self.call_log = []

    def log_call(self, provider: str, phase: str, input_tokens: int = 0,
                 output_tokens: int = 0, model: str = None,
                 actual_cost_usd: float = None):
        """Log a single LLM call. Pass actual_cost_usd when known (from OpenRouter API)."""
        if provider not in self.usage:
            self.usage[provider] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "actual_cost_usd": 0.0,
                "model": model or "unknown"
            }

        self.usage[provider]["input_tokens"]   += input_tokens
        self.usage[provider]["output_tokens"]  += output_tokens
        self.usage[provider]["calls"]          += 1
        self.usage[provider].setdefault("actual_cost_usd", 0.0)
        if actual_cost_usd is not None:
            self.usage[provider]["actual_cost_usd"] += actual_cost_usd
        if model:
            self.usage[provider]["model"] = model

        self.call_log.append({
            "timestamp":       datetime.now().isoformat(),
            "provider":        provider,
            "phase":           phase,
            "input_tokens":    input_tokens,
            "output_tokens":   output_tokens,
            "model":           model,
            "actual_cost_usd": actual_cost_usd,
        })

    def total_actual_cost(self) -> float:
        """Sum costs per call: use actual USD where reported, token estimate otherwise."""
        total = 0.0
        for call in self.call_log:
            if call.get("actual_cost_usd") is not None:
                total += call["actual_cost_usd"]
            else:
                model = call.get("model", "unknown")
                pricing = PRICING.get(model, {"input": 0, "output": 0})
                total += (call.get("input_tokens", 0) / 1_000_000) * pricing["input"]
                total += (call.get("output_tokens", 0) / 1_000_000) * pricing["output"]
        return round(total, 6)



# Global tracker instance
token_tracker = TokenTracker()
