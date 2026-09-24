"""
Stock screener: applies structured filters to the live STACKS stock list.

Natural-language queries are parsed with plain regex into the SAME filter
object the structured form uses — deliberately not handed to the AI to
"interpret" freely, since a screener is a numeric filter operation and
regex is both cheaper and more predictable than an LLM for it. Anything the
parser can't confidently extract is just left as an unset filter rather than
guessed.
"""
from __future__ import annotations

import re

FilterDict = dict


def parse_natural_language(query: str) -> FilterDict:
    q = query.lower()
    filters: FilterDict = {}

    m = re.search(r"under\s*\$?(\d+(?:\.\d+)?)", q) or re.search(r"below\s*\$?(\d+(?:\.\d+)?)\s*(?:in\s*)?price", q)
    if m:
        filters["max_price"] = float(m.group(1))
    m = re.search(r"(?:over|above)\s*\$?(\d+(?:\.\d+)?)\s*(?:in\s*)?price", q)
    if m:
        filters["min_price"] = float(m.group(1))

    m = re.search(r"p/?e\s*(?:below|under|less than)\s*(\d+(?:\.\d+)?)", q)
    if m:
        filters["max_pe"] = float(m.group(1))
    m = re.search(r"p/?e\s*(?:above|over|greater than)\s*(\d+(?:\.\d+)?)", q)
    if m:
        filters["min_pe"] = float(m.group(1))

    m = re.search(r"volume\s*(?:above|over|greater than)\s*(\d+(?:,\d{3})*)", q)
    if m:
        filters["min_volume"] = float(m.group(1).replace(",", ""))
    m = re.search(r"volume\s*(?:below|under|less than)\s*(\d+(?:,\d{3})*)", q)
    if m:
        filters["max_volume"] = float(m.group(1).replace(",", ""))

    m = re.search(r"(?:up|gained?|gaining)\s*(?:more than|over|by)?\s*(\d+(?:\.\d+)?)\s*%", q)
    if m:
        filters["min_change_pct"] = float(m.group(1))
    m = re.search(r"(?:down|lost|losing|declined?)\s*(?:more than|over|by)?\s*(\d+(?:\.\d+)?)\s*%", q)
    if m:
        filters["max_change_pct"] = -float(m.group(1))

    if "undervalued" in q:
        # heuristic proxy: low P/E among stocks that have one — refined further
        # downstream by comparing against peer P/E, not invented here.
        filters.setdefault("max_pe", 12.0)

    if "dividend" in q and ("pay" in q or "paying" in q or "yield" in q):
        filters["has_dividend"] = True

    if "health score" in q or "healthy" in q:
        m2 = re.search(r"(?:above|over|at least)\s*(\d+)", q)
        if m2:
            filters["min_health_score"] = float(m2.group(1))

    return filters


def _passes(stock: dict, f: FilterDict) -> bool:
    def num(key):
        v = stock.get(key)
        return v if isinstance(v, (int, float)) else None

    checks = [
        (f.get("max_price"), num("price"), lambda v, t: v is not None and v <= t),
        (f.get("min_price"), num("price"), lambda v, t: v is not None and v >= t),
        (f.get("max_pe"), num("pe_ratio"), lambda v, t: v is not None and 0 < v <= t),
        (f.get("min_pe"), num("pe_ratio"), lambda v, t: v is not None and v >= t),
        (f.get("max_volume"), num("volume"), lambda v, t: v is not None and v <= t),
        (f.get("min_volume"), num("volume"), lambda v, t: v is not None and v >= t),
        (f.get("min_change_pct"), num("change_percent"), lambda v, t: v is not None and v >= t),
        (f.get("max_change_pct"), num("change_percent"), lambda v, t: v is not None and v <= t),
        (f.get("min_health_score"), num("health_score"), lambda v, t: v is not None and v >= t),
    ]
    for threshold, value, cmp in checks:
        if threshold is None:
            continue
        if not cmp(value, threshold):
            return False
    if f.get("has_dividend") and not stock.get("has_dividend"):
        return False
    return True


def apply_filters(stocks: list[dict], filters: FilterDict) -> list[dict]:
    return [s for s in stocks if _passes(s, filters)]
