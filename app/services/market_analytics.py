"""
Market-wide analytics computed purely from the already-normalized STACKS
stock list. Every aggregate here is arithmetic over real fields; anything
that can't be computed from available data is returned as None ("N/A" in
the UI), never guessed.
"""
from __future__ import annotations

from typing import Optional


def _is_num(v) -> bool:
    return isinstance(v, (int, float))


def market_summary(stocks: list[dict]) -> dict:
    total = len(stocks)
    advancers = sum(1 for s in stocks if _is_num(s.get("change_percent")) and s["change_percent"] > 0)
    decliners = sum(1 for s in stocks if _is_num(s.get("change_percent")) and s["change_percent"] < 0)
    unchanged = sum(1 for s in stocks if _is_num(s.get("change_percent")) and s["change_percent"] == 0)
    unknown = total - advancers - decliners - unchanged

    volumes = [s["volume"] for s in stocks if _is_num(s.get("volume"))]
    total_volume = sum(volumes) if volumes else None

    values = []
    for s in stocks:
        price, vol = s.get("price"), s.get("volume")
        if _is_num(price) and _is_num(vol):
            values.append(price * vol)
    total_value = sum(values) if values else None

    return {
        "stocks_tracked": total,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "no_change_data": unknown,
        "total_volume": total_volume,
        "total_value_traded": round(total_value, 2) if total_value is not None else None,
    }


def _sorted(stocks: list[dict], key: str, reverse: bool) -> list[dict]:
    usable = [s for s in stocks if _is_num(s.get(key))]
    return sorted(usable, key=lambda s: s[key], reverse=reverse)


def market_movers(stocks: list[dict], limit: int = 10) -> dict:
    with_value = []
    for s in stocks:
        price, vol = s.get("price"), s.get("volume")
        value = price * vol if _is_num(price) and _is_num(vol) else None
        with_value.append({**s, "value_traded": value})

    return {
        "top_gainers": _sorted(stocks, "change_percent", reverse=True)[:limit],
        "top_losers": _sorted(stocks, "change_percent", reverse=False)[:limit],
        "most_active": _sorted(stocks, "volume", reverse=True)[:limit],
        "highest_value_traded": sorted(
            [s for s in with_value if _is_num(s.get("value_traded"))],
            key=lambda s: s["value_traded"],
            reverse=True,
        )[:limit],
    }


def pe_rankings(stocks: list[dict], limit: int = 15) -> list[dict]:
    usable = [s for s in stocks if _is_num(s.get("pe_ratio")) and s["pe_ratio"] > 0]
    return sorted(usable, key=lambda s: s["pe_ratio"])[:limit]
