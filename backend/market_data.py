"""Market data: prices + company profile + news (Yahoo Finance via yfinance) and
financial statements (SEC EDGAR XBRL "company facts"). Both are free and keyless.

Every fetch goes through `load()`:
  1. fresh disk cache (data/cache, 6 hours)  -> source "cache"
  2. live fetch (unless DATA_MODE=sample)      -> source "live"
  3. bundled snapshot (data/sample/<T>.json)   -> source "sample"
so the app still works when Yahoo rate-limits or there is no internet.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable

import httpx

from . import config

CACHE_TTL_SECONDS = 6 * 3600
TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")
KINDS = ("history", "profile", "news", "financials")


class DataUnavailable(Exception):
    pass


def normalize_ticker(raw: str) -> str:
    t = (raw or "").strip().upper().lstrip("$")
    if not TICKER_RE.match(t):
        raise DataUnavailable(f"'{raw}' is not a valid US stock ticker.")
    return t


# ---------------------------------------------------------------- cache layer

def _cache_path(kind: str, ticker: str):
    return config.CACHE_DIR / f"{ticker}_{kind}.json"


def _sample(kind: str, ticker: str) -> Any | None:
    path = config.SAMPLE_DIR / f"{ticker}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get(kind)


def sample_tickers() -> list[str]:
    return sorted(p.stem for p in config.SAMPLE_DIR.glob("*.json") if p.stem.isupper())


def load(kind: str, ticker: str) -> tuple[Any, str]:
    """Return (data, source) for one kind of data about one ticker."""
    ticker = normalize_ticker(ticker)
    path = _cache_path(kind, ticker)
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
        return json.loads(path.read_text(encoding="utf-8")), "cache"

    error = None
    if config.DATA_MODE != "sample":
        try:
            data = FETCHERS[kind](ticker)
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            return data, "live"
        except Exception as exc:  # network down, rate limit, unknown ticker...
            error = exc

    data = _sample(kind, ticker)
    if data is not None:
        return data, "sample"
    if error is not None:
        raise DataUnavailable(f"Could not get {kind} for {ticker}: {error}")
    raise DataUnavailable(f"No offline data for {ticker}. Offline tickers: {', '.join(sample_tickers())}")


# ---------------------------------------------------------------- Yahoo (yfinance)

def _fetch_history(ticker: str) -> dict:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="5y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        raise DataUnavailable(f"No price history for {ticker} (unknown or delisted ticker?)")
    closes = hist["Close"].dropna()
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in closes.index],
        "closes": [round(float(c), 4) for c in closes.values],
    }


PROFILE_FIELDS = {
    "longName": "name",
    "sector": "sector",
    "industry": "industry",
    "country": "country",
    "marketCap": "market_cap",
    "trailingPE": "pe_trailing",
    "forwardPE": "pe_forward",
    "priceToSalesTrailing12Months": "price_to_sales",
    "beta": "beta",
    "dividendYield": "dividend_yield_pct",
    "shortPercentOfFloat": "short_pct_of_float",
    "fiftyTwoWeekHigh": "high_52w",
    "fiftyTwoWeekLow": "low_52w",
    "targetMeanPrice": "analyst_target_mean",
    "recommendationKey": "analyst_consensus",
    "numberOfAnalystOpinions": "analyst_count",
    "fullTimeEmployees": "employees",
    "longBusinessSummary": "business_summary",
    "quoteType": "quote_type",
    "exchange": "exchange",
}


def _fetch_profile(ticker: str) -> dict:
    import yfinance as yf

    info = yf.Ticker(ticker).info or {}
    out = {new: info.get(old) for old, new in PROFILE_FIELDS.items()}
    if not out.get("name") and not out.get("market_cap"):
        raise DataUnavailable(f"No company profile for {ticker}")
    if isinstance(out.get("short_pct_of_float"), (int, float)):
        out["short_pct_of_float"] = round(out["short_pct_of_float"] * 100, 2)
    for k, v in out.items():
        if isinstance(v, float):
            out[k] = round(v, 2)
    if out.get("business_summary"):
        out["business_summary"] = out["business_summary"][:600]
    return out


def _fetch_news(ticker: str) -> list[dict]:
    import yfinance as yf

    items = []
    for raw in (yf.Ticker(ticker).news or [])[:10]:
        c = raw.get("content", raw)
        provider = c.get("provider") or {}
        items.append({
            "title": c.get("title", ""),
            "publisher": provider.get("displayName") if isinstance(provider, dict) else c.get("publisher", ""),
            "published": (c.get("pubDate") or c.get("providerPublishTime") or ""),
            "summary": (c.get("summary") or "")[:300],
        })
    return items


# ---------------------------------------------------------------- SEC EDGAR

SEC_CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "stockholders_equity": ["StockholdersEquity"],
}
FLOW_ITEMS = {"revenue", "net_income", "operating_cash_flow"}


def _sec_get(url: str) -> Any:
    resp = httpx.get(url, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _cik_for(ticker: str) -> int:
    path = config.SAMPLE_DIR / "sec_company_tickers.json"
    table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if table is None:
        table = _sec_get("https://www.sec.gov/files/company_tickers.json")
        config.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(table), encoding="utf-8")
    want = ticker.replace(".", "-")
    for row in table.values():
        if row["ticker"].upper() == want:
            return int(row["cik_str"])
    raise DataUnavailable(f"{ticker} is not in the SEC company list (foreign or not SEC-registered?)")


def _annual_series(facts: dict, names: list[str], flow: bool) -> list[dict]:
    """Last 4 fiscal-year values from 10-K filings for the first concept that has data."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best: list[dict] = []
    for name in names:
        units = gaap.get(name, {}).get("units", {}).get("USD", [])
        by_end: dict[str, dict] = {}
        for f in units:
            if f.get("form") not in ("10-K", "10-K/A", "20-F", "40-F"):
                continue
            if flow:
                if not f.get("start"):
                    continue
                days = (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days
                if not 330 <= days <= 400:
                    continue
            prev = by_end.get(f["end"])
            if prev is None or f.get("filed", "") > prev.get("filed", ""):
                by_end[f["end"]] = f
        series = [{"period_end": e, "value": by_end[e]["val"]} for e in sorted(by_end)][-4:]
        if series and (not best or series[-1]["period_end"] > best[-1]["period_end"]):
            best = series
    return best


def _fetch_financials(ticker: str) -> dict:
    cik = _cik_for(ticker)
    facts = _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    out: dict[str, Any] = {"source": "SEC EDGAR 10-K filings", "entity": facts.get("entityName"), "annual": {}}
    for item, names in SEC_CONCEPTS.items():
        out["annual"][item] = _annual_series(facts, names, flow=item in FLOW_ITEMS)
    if not any(out["annual"].values()):
        raise DataUnavailable(f"SEC filings for {ticker} have no standard financial data")
    return out


FETCHERS: dict[str, Callable[[str], Any]] = {
    "history": _fetch_history,
    "profile": _fetch_profile,
    "news": _fetch_news,
    "financials": _fetch_financials,
}


# ---------------------------------------------------------------- derived numbers

PERIOD_DAYS = {"1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "3y": 756, "5y": 1260}


def _clean(x: float | None, nd: int = 2) -> float | None:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(x, nd)


def price_stats(history: dict, period: str) -> dict:
    n = PERIOD_DAYS[period]
    closes = history["closes"][-(n + 1):]
    dates = history["dates"][-(n + 1):]
    if len(closes) < 2:
        raise DataUnavailable("Not enough price history")
    peak, max_dd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        max_dd = min(max_dd, c / peak - 1)
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)) * math.sqrt(252)
    return {
        "period": period,
        "start_date": dates[0],
        "end_date": dates[-1],
        "start_price": _clean(closes[0]),
        "last_price": _clean(closes[-1]),
        "return_pct": _clean((closes[-1] / closes[0] - 1) * 100, 1),
        "high": _clean(max(closes)),
        "low": _clean(min(closes)),
        "max_drawdown_pct": _clean(max_dd * 100, 1),
        "annualized_volatility_pct": _clean(vol * 100, 1),
    }


def growth_pct(series: list[dict]) -> float | None:
    if len(series) < 2 or not series[-2]["value"]:
        return None
    return _clean((series[-1]["value"] / abs(series[-2]["value"]) - 1) * 100, 1)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
