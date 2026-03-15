"""
Token Usage Tracker
Tracks token usage across LLM calls for cost monitoring.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from agents.config.settings import project_root

# Pricing per 1M tokens (approximate, check OpenRouter for current rates)
# AnythingLLM uses OpenRouter/Grok-4 underneath, so same pricing applies
PRICING = {
    "x-ai/grok-4": {"input": 3.00, "output": 15.00},  # $3/1M input, $15/1M output
    "anythingllm": {"input": 3.00, "output": 15.00},  # Uses Grok-4 via OpenRouter
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

    def estimate_cost(self) -> Dict[str, float]:
        """Token-based cost estimate (used as fallback when actual cost unavailable)."""
        costs = {}
        total = 0.0

        for provider, data in self.usage.items():
            model = data.get("model", provider)
            pricing = PRICING.get(model, {"input": 0, "output": 0})

            input_cost = (data["input_tokens"] / 1_000_000) * pricing["input"]
            output_cost = (data["output_tokens"] / 1_000_000) * pricing["output"]
            provider_cost = input_cost + output_cost

            costs[provider] = {
                "input_cost":       round(input_cost, 4),
                "output_cost":      round(output_cost, 4),
                "total_cost":       round(provider_cost, 4),
                "actual_cost_usd":  round(data.get("actual_cost_usd", 0.0), 6),
            }
            total += provider_cost

        costs["total"] = round(total, 4)
        return costs

    def get_summary(self) -> Dict:
        """Get full usage summary."""
        return {
            "usage": self.usage,
            "costs": self.estimate_cost(),
            "call_count": len(self.call_log),
            "calls": self.call_log
        }

    def save(self, init_time: datetime):
        """Save token usage to results folder."""
        from agents.config.settings import TESTER_NAME

        results_dir = project_root / "results"
        safe_time = str(init_time).replace(":", "-")
        filename = f"token_usage_{TESTER_NAME}_{safe_time}.json"
        filepath = results_dir / filename

        summary = self.get_summary()
        summary["run_timestamp"] = str(init_time)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4)

        print(f"\n[TOKENS] Usage saved to: {filename}")
        print(f"[TOKENS] Total estimated cost: ${summary['costs']['total']:.4f}")

        return filepath


# Global tracker instance
token_tracker = TokenTracker()
