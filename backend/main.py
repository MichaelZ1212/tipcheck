"""FastAPI server: serves the web page and streams a tip check live (Server-Sent Events)."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, market_data, safety
from .agents import check_tip
from .tokenomics import PRICE_SOURCE, PRICES, DailySpend

app = FastAPI(title="TipCheck")
limiter = safety.RateLimiter(config.CHECKS_PER_MINUTE_PER_IP)
daily = DailySpend(config.DAILY_BUDGET_USD)


class CheckRequest(BaseModel):
    tip: str = Field(min_length=10, max_length=config.MAX_TIP_CHARS)
    ticker: str | None = Field(default=None, max_length=8)
    effort: Literal["quick", "standard"] = "quick"
    budget_usd: float | None = Field(default=None, gt=0, le=1.0)


@app.get("/api/health")
def health():
    return {"ok": True, "model": config.MODEL_NAME, "key": config.key_source() or "missing",
            "data_mode": config.DATA_MODE, "offline_tickers": market_data.sample_tickers(),
            "spent_today_usd": round(daily.spent_today(), 4), "daily_budget_usd": config.DAILY_BUDGET_USD,
            "run_budget_usd": config.RUN_BUDGET_USD}


@app.get("/api/pricing")
def pricing():
    return {"model": config.MODEL_NAME, "prices_per_million": PRICES, "source": PRICE_SOURCE}


@app.post("/api/check")
async def check(req: CheckRequest, request: Request):
    if not config.key_source():
        raise HTTPException(500, "No API key. Put PORTKEY_API_KEY in a .env file in this folder or the one above it.")
    if not limiter.allow(request.client.host if request.client else "local"):
        raise HTTPException(429, "Too many checks in a minute. Wait a moment and try again.")
    if not daily.can_start():
        raise HTTPException(429, f"TipCheck hit its daily spending cap (${config.DAILY_BUDGET_USD:.2f}). Try again tomorrow.")

    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def worker():
        try:
            record = await check_tip(req.tip, emit, ticker_hint=req.ticker or None, effort=req.effort,
                                     budget_usd=min(req.budget_usd or config.RUN_BUDGET_USD, config.RUN_BUDGET_USD * 4))
            daily.add(record["usage"]["total"].get("cost_usd", 0.0))
        except Exception as exc:
            await queue.put({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def stream():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()  # browser closed the tab: stop spending

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs")
def runs():
    out = []
    for path in sorted(config.RUNS_DIR.glob("*.json"), reverse=True)[:50]:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"id": r["id"], "created": r.get("created"), "ticker": r.get("ticker"), "status": r.get("status"),
                    "verdict": (r.get("report") or {}).get("verdict"), "tip": r.get("tip", "")[:120],
                    "cost_usd": r.get("usage", {}).get("total", {}).get("cost_usd")})
    return out


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    if not all(c.isalnum() or c == "-" for c in run_id):
        raise HTTPException(400, "bad id")
    path = config.RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(404, "not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
