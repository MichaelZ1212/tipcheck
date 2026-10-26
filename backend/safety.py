"""Defenses that run in plain code (not in the model), so a prompt can't talk its way past them.

1. Injection scanner: flags text that tries to give orders to an AI.
2. Fencing: untrusted text (the tip, news headlines) is wrapped in tags the agents are told never to obey.
3. Number grounding: every number an agent writes must appear in the evidence it cites.
4. Advice filter: the app explains a tip; it never tells anyone to buy or sell.
5. Rate limit per visitor.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from typing import Any

INJECTION_PATTERNS = [
    (r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)", "ignore-previous-instructions"),
    (r"disregard (all |your |the )?(instructions|rules|guidelines|system prompt)", "disregard-instructions"),
    (r"\b(system|developer) (prompt|message|instructions?)\b", "mentions-system-prompt"),
    (r"you are now|act as (a|an)? ?(different|new|unfiltered)|pretend (to be|you are)", "role-override"),
    (r"(rate|mark|label|classify|call) (this|it|the stock|the tip) (as )?(a )?(strong buy|buy|safe|legit|checks? out|supported)", "forces-verdict"),
    (r"(reveal|print|show|repeat|leak) (your|the) (instructions|prompt|system|api key|keys?|secrets?)", "prompt-or-key-leak"),
    (r"\b(api[_ -]?key|portkey|openai_api_key)\b", "asks-about-keys"),
    (r"</?\s*(untrusted|system|instructions?|evidence)[^>]*>", "fake-tags"),
    (r"(note|message|instruction)s? (to|for) (the )?(ai|assistant|model|llm|agent|chatgpt|gpt)", "addresses-the-ai"),
    (r"do not (mention|report|flag) (any )?(risks?|red flags?|warnings?)", "suppress-warnings"),
    (r"(^|\n)\s*(system|assistant|developer)\s*:", "fake-role-message"),
    (r"\bset (the )?(verdict|risk[_ ]?level|rating|red[_ ]?flags)\b", "forces-verdict"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in INJECTION_PATTERNS]


def scan_for_injection(text: str) -> list[str]:
    return sorted({name for rx, name in _COMPILED if rx.search(text or "")})


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​-‏‪-‮⁦-⁩]")


def clean_text(text: str, limit: int) -> str:
    """Drop invisible/control characters (used to hide instructions) and cap length."""
    text = _CTRL.sub("", text or "")
    return text[:limit]


def quarantine(text: str) -> str:
    """Cut out the parts of a tip that give orders to an AI (bracketed notes, lines, or sentences), keep the rest."""
    marker = "[removed by TipCheck: instructions aimed at AI]"
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", lambda m: marker if scan_for_injection(m.group(0)) else m.group(0), text)
    lines = []
    for line in text.splitlines():
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [marker if scan_for_injection(p) else p for p in parts]
        lines.append(" ".join(kept))
    out = "\n".join(lines)
    return re.sub(r"(\[removed by TipCheck: instructions aimed at AI\]\s*)+", marker + " ", out).strip()


def fence(text: str, label: str) -> str:
    """Wrap untrusted text so agents treat it as data. Any tag-like text inside is defused."""
    body = re.sub(r"<\s*/?\s*untrusted", "‹untrusted", text, flags=re.IGNORECASE)
    return f"<untrusted_{label}>\n{body}\n</untrusted_{label}>"


# ---------------------------------------------------------------- number grounding

_NUM = re.compile(
    r"(?P<neg>[-−])?\$?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|x\b|trillion\b|billion\b|million\b|thousand\b|tn\b|bn\b|[TBMK]\b)?",
    re.IGNORECASE,
)
_SCALE = {"t": 1e12, "tn": 1e12, "trillion": 1e12, "b": 1e9, "bn": 1e9, "billion": 1e9,
          "m": 1e6, "million": 1e6, "k": 1e3, "thousand": 1e3}


# Names that contain digits but aren't quantities: "S&P 500", "52-week high", "200-day average", "10-K", "401(k)".
_NOT_QUANTITIES = re.compile(
    r"S&(amp;)?P\s*500|\b\d+[- ](week|day|month|year|quarter)s?\b|\b10-[KQ]\b|\b20-F\b|\b8-K\b|\b401\s?\(k\)",
    re.IGNORECASE)


def numbers_in_text(text: str) -> list[tuple[str, float]]:
    """Numbers worth checking in agent prose: (as written, value in base units)."""
    out = []
    text = _NOT_QUANTITIES.sub(" ", text or "")
    for m in _NUM.finditer(text):
        raw = m.group(0).strip()
        value = float(m.group("num").replace(",", ""))
        unit = (m.group("unit") or "").lower()
        has_marker = "$" in raw or unit
        # Skip years, claim/evidence ids (C1, E3), and small bare counts ("2 quarters").
        start = m.start()
        if start > 0 and text[start - 1].isalpha():
            continue
        if not has_marker and (value <= 12 or (1990 <= value <= 2100 and value == int(value))):
            continue
        value *= _SCALE.get(unit, 1)
        if m.group("neg"):
            value = -value
        out.append((raw, value))
    return out


def _numbers_in_evidence(obj: Any, acc: list[float]) -> list[float]:
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in_evidence(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in_evidence(v, acc)
    elif isinstance(obj, str):
        acc.extend(v for _, v in numbers_in_text(obj))
    return acc


def _close(x: float, v: float) -> bool:
    if v == 0:
        return abs(x) < 0.05
    if abs(x - v) <= max(0.051, 0.02 * abs(v)):
        return True
    # Allow sign to be written in words ("fell 12%" vs -12.0), and percent written as a fraction.
    return abs(abs(x) - abs(v)) <= max(0.051, 0.02 * abs(v)) or abs(x - v * 100) <= max(0.051, 0.02 * abs(v * 100))


_PRICE_KEYS = {"start_price", "last_price", "high", "low", "high_52w", "low_52w", "analyst_target_mean", "from", "to"}


def _derived(evidence_items: list[Any], tip_text: str) -> list[float]:
    """The few numbers an analyst may honestly compute: gaps between percentages (stock vs S&P 500), percent moves
    between prices (incl. the tip's own price targets), and year-over-year changes within one financial series."""
    pcts, prices, out = [], [v for _, v in numbers_in_text(tip_text) if v > 0], []

    def walk(obj: Any, key: str = "") -> None:
        if isinstance(obj, dict):
            if "value" in obj and isinstance(obj["value"], (int, float)):
                return
            for k, v in obj.items():
                walk(v, k)
        elif isinstance(obj, list):
            series = [x["value"] for x in obj if isinstance(x, dict) and isinstance(x.get("value"), (int, float))]
            for a, b in zip(series, series[1:]):
                out.append(b - a)
                if a:
                    out.append((b / abs(a) - 1) * 100)
            for x in obj:
                walk(x, key)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            if "_pct" in key:
                pcts.append(float(obj))
            if key in _PRICE_KEYS and obj > 0:
                prices.append(float(obj))

    for item in evidence_items:
        walk(item)
    out += [a - b for a in pcts for b in pcts if a is not b]
    out += [(b / a - 1) * 100 for a in prices for b in prices if a is not b]
    return out


def _rounds_to(raw: str, x: float, v: float) -> bool:
    """True if x, as written in raw (e.g. '75%' or '566.7%'), is a correct rounding of v (sign may be in words)."""
    digits = re.search(r"\d+(?:\.(\d+))?", raw.replace(",", ""))
    places = len(digits.group(1)) if digits and digits.group(1) else 0
    half = 0.5 * 10 ** -places + 1e-9
    return abs(abs(x) - abs(v)) <= half


def ungrounded_numbers(text: str, evidence_ids: list[str], evidence: dict[str, Any]) -> list[str]:
    """Numbers in `text` that match nothing in the evidence. Cited items are checked first; a number found in
    another evidence item still counts (agents sometimes cite the wrong id), but a number found nowhere is made up.
    Simple honest math on cited evidence (see _derived) is allowed if it is rounded correctly."""
    cited = [evidence[e] for e in evidence_ids if e in evidence and e != "TIP"]
    rest = [v for k, v in evidence.items() if k not in evidence_ids and k != "TIP"]
    tip = str(evidence.get("TIP", ""))
    values = _numbers_in_evidence(cited + rest + [tip], [])
    derived: list[float] | None = None
    bad = []
    for raw, x in numbers_in_text(text):
        if any(_close(x, v) for v in values):
            continue
        if derived is None:  # only build the computed values when needed
            derived = _derived(cited or rest, tip)
        if not any(_rounds_to(raw, x, d) for d in derived):
            bad.append(raw)
    return bad


# ---------------------------------------------------------------- advice filter

_ADVICE = re.compile(
    r"\b(you should|i recommend|we recommend|go ahead and|definitely|must)\s+(buy|sell|short|invest|put)\b"
    r"|\b(strong buy|strong sell|buy now|sell now)\b",
    re.IGNORECASE,
)


def strip_advice(text: str) -> tuple[str, bool]:
    """Remove sentences that tell the reader to trade. Returns (text, was_changed)."""
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    kept = [s for s in sentences if not _ADVICE.search(s)]
    return " ".join(kept), len(kept) != len(sentences)


# ---------------------------------------------------------------- rate limit

class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True
