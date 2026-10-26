"""Download a small offline snapshot of market data into data/sample/ (needs internet, no API key).

    python scripts/build_sample.py            # default tickers
    python scripts/build_sample.py AAPL MSFT  # your own list

The app falls back to this snapshot whenever live data is unavailable, and uses only it when DATA_MODE=sample.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import config, market_data  # noqa: E402

DEFAULT = ["SOUN", "GME", "COST", "TSLA", "NVDA", "PLTR", "AAPL", "AMC", "SPY"]

config.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
for ticker in sys.argv[1:] or DEFAULT:
    snap = {"snapshot_utc": market_data.utc_now()}
    kinds = ["history"] if ticker == "SPY" else list(market_data.KINDS)
    for kind in kinds:
        try:
            snap[kind] = market_data.FETCHERS[kind](ticker)
            print(f"  {ticker:5} {kind:10} ok")
        except Exception as exc:
            print(f"  {ticker:5} {kind:10} FAILED: {exc}")
    if "history" in snap:
        (config.SAMPLE_DIR / f"{ticker}.json").write_text(json.dumps(snap), encoding="utf-8")
print(f"Saved to {config.SAMPLE_DIR}")
