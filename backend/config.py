"""Settings, API keys, and the model.

The .env file is looked up in this project folder first, then the folder above it
(where the teaching staff keep theirs). The nearest file wins.
"""

from __future__ import annotations

import os
import warnings
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
warnings.filterwarnings("ignore", module=r"yfinance.*")  # noisy pandas deprecation warnings inside yfinance

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for folder in (PROJECT_ROOT, PROJECT_ROOT.parent):
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=False)

DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"
PROMPTS_DIR = PROJECT_ROOT / "backend" / "prompts"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-6-luna")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")

# "auto": live market data, falling back to the bundled sample snapshot.
# "sample": never touch the network for market data (offline demo / grading).
DATA_MODE = os.getenv("DATA_MODE", "auto").strip().lower()

DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "2.00"))
RUN_BUDGET_USD = float(os.getenv("RUN_BUDGET_USD", "0.05"))
MAX_TIP_CHARS = 2500
CHECKS_PER_MINUTE_PER_IP = 6

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "TipCheck student project tipcheck-app@example.com")


def key_source() -> str:
    """Which key the app will use: 'portkey', 'openai', or '' if neither is set."""
    if os.getenv("PORTKEY_API_KEY", "").strip():
        return "portkey"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return ""


@lru_cache(maxsize=1)
def build_model():
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    source = key_source()
    if source == "portkey":
        client = AsyncOpenAI(
            api_key=os.environ["PORTKEY_API_KEY"].strip(),
            base_url=PORTKEY_BASE_URL,
            # Bypass Portkey's response cache: every check is a real model call, so token counts are real.
            default_headers={"x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"},
        )
    elif source == "openai":
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())
    else:
        raise RuntimeError(
            "No API key found. Put PORTKEY_API_KEY (or OPENAI_API_KEY) in a .env file "
            "in this folder or the folder above it."
        )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
