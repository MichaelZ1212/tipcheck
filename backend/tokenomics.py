"""Token counts -> dollars, per-run budget, and a daily spending cap that survives restarts."""

from __future__ import annotations

import json
import threading
from datetime import date
from typing import Any

from . import config

# OpenAI Standard short-context prices, USD per 1M tokens (course pricing table, lecture 11).
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50},
    "gpt-6-astra": {"input": 10.00, "cached": 1.00, "cache_write": 12.50, "output": 50.00},
}
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"


class BudgetExceeded(Exception):
    pass


def usage_dict(usage: Any) -> dict:
    return {
        "requests": getattr(usage, "requests", 0) or 0,
        "tool_calls": getattr(usage, "tool_calls", 0) or 0,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_write_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "reasoning_tokens": getattr(usage, "output_reasoning_tokens", 0) or 0,
    }


def cost_usd(usage: dict, model: str = config.MODEL_NAME) -> float:
    """input_tokens includes cached and cache-write tokens; bill the rest at the normal input rate."""
    p = PRICES.get(model, PRICES["gpt-6-luna"])
    cached = usage.get("cache_read_tokens", 0)
    written = usage.get("cache_write_tokens", 0)
    uncached = max(0, usage.get("input_tokens", 0) - cached - written)
    dollars = (uncached * p["input"] + cached * p["cached"] + written * p["cache_write"]
               + usage.get("output_tokens", 0) * p["output"]) / 1_000_000
    return round(dollars, 7)


def add_usage(a: dict, b: dict) -> dict:
    keys = set(a) | set(b)
    return {k: (a.get(k, 0) or 0) + (b.get(k, 0) or 0) for k in keys if k not in ("cost_usd", "seconds")}


class RunLedger:
    """Spend for one tip check, per agent, with a hard stop."""

    def __init__(self, budget_usd: float, model: str = config.MODEL_NAME):
        self.budget_usd = budget_usd
        self.model = model
        self.agents: dict[str, dict] = {}

    def record(self, agent: str, usage: dict) -> None:
        row = add_usage(self.agents.get(agent, {}), usage)
        row["cost_usd"] = cost_usd(row, self.model)
        self.agents[agent] = row

    @property
    def total(self) -> dict:
        tot: dict = {}
        for row in self.agents.values():
            tot = add_usage(tot, row)
        tot["cost_usd"] = cost_usd(tot, self.model)
        return tot

    def check(self) -> None:
        spent = self.total["cost_usd"]
        if spent >= self.budget_usd:
            raise BudgetExceeded(f"Run budget hit: ${spent:.4f} spent, limit ${self.budget_usd:.4f}")


class DailySpend:
    """App-wide daily cap (protects the API key from a bug or an abusive visitor)."""

    def __init__(self, limit_usd: float):
        self.limit_usd = limit_usd
        self.path = config.DATA_DIR / "spend.json"
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        today = date.today().isoformat()
        return data if data.get("date") == today else {"date": today, "usd": 0.0, "runs": 0}

    def spent_today(self) -> float:
        return self._read()["usd"]

    def can_start(self) -> bool:
        return self.spent_today() < self.limit_usd

    def add(self, usd: float) -> None:
        with self._lock:
            data = self._read()
            data["usd"] = round(data["usd"] + usd, 6)
            data["runs"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data), encoding="utf-8")
