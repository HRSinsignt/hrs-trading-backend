from __future__ import annotations

import statistics
from typing import Any

from app.services.stacks_api import stacks_client


async def compute_health_score(
    symbol: str | None = None,
    stock: dict[str, Any] | None = None,
    financials: Any = None,
    dividends: Any = None,
    history: list[dict[str, Any]] | None = None,
    peer_pe_values: list[float] | None = None,
) -> dict[str, Any]:
    """Return a numeric health score from already-fetched stock data.

    The function is intentionally resilient: it accepts both the legacy
    symbol-only calling pattern and the richer bundle-based pattern used by
    the analysis endpoints.
    """

    if stock is None and symbol:
        try:
            stock_data = await stacks_client.get_stock(symbol)
            stock = (stock_data or {}).get("stock") or {}
        except Exception:
            stock = {}

    if not stock and not symbol:
        return {"score": 0, "overall_score": 0, "rating": "Poor", "factors": {}, "error": "No stock data"}

    stock = stock or {}
    symbol_name = stock.get("symbol") or symbol

    pe_ratio = stock.get("pe_ratio")
    if pe_ratio is None and isinstance(stock.get("raw"), dict):
        pe_ratio = stock["raw"].get("pe_ratio") or stock["raw"].get("peRatio")

    try:
        pe_value = float(pe_ratio)
    except (TypeError, ValueError):
        pe_value = None

    peer_values = [float(v) for v in (peer_pe_values or []) if isinstance(v, (int, float)) and v > 0]
    peer_median = statistics.median(peer_values) if peer_values else None

    if peer_median and pe_value is not None and pe_value > 0:
        ratio_gap = abs(pe_value - peer_median) / peer_median
        valuation_score = max(0.0, min(100.0, 100.0 * (1 - min(ratio_gap, 1.5))))
    elif pe_value is not None and pe_value > 0:
        valuation_score = max(0.0, min(100.0, 100.0 - max(pe_value - 15, 0) * 4.0))
    else:
        valuation_score = 0.0

    ytd = stock.get("ytd_percent")
    try:
        ytd_value = float(ytd)
    except (TypeError, ValueError):
        ytd_value = 0.0
    momentum_score = max(0.0, min(100.0, 50.0 + ytd_value))

    volume = stock.get("volume")
    try:
        volume_value = float(volume)
    except (TypeError, ValueError):
        volume_value = 0.0
    volume_score = max(0.0, min(100.0, volume_value / 1000.0))

    wk_52 = stock.get("week_52_percent")
    try:
        wk_value = float(wk_52)
    except (TypeError, ValueError):
        wk_value = 0.0
    trend_score = max(0.0, min(100.0, 50.0 + wk_value))

    change = stock.get("change_percent")
    try:
        change_value = float(change)
    except (TypeError, ValueError):
        change_value = 0.0
    stability_score = max(0.0, 100.0 - abs(change_value) * 5.0)

    dividend_support = 0.0
    if dividends:
        if isinstance(dividends, list):
            dividend_support = 100.0 if len(dividends) > 0 else 0.0
        elif isinstance(dividends, dict):
            dividend_yield = dividends.get("yield") or dividends.get("dividend_yield")
            try:
                dividend_support = max(0.0, min(100.0, float(dividend_yield) * 10.0))
            except (TypeError, ValueError):
                dividend_support = 100.0 if dividends.get("has_dividend") else 0.0
    elif stock.get("has_dividend"):
        dividend_support = 100.0

    financials_score = 50.0
    if isinstance(financials, dict):
        revenue = financials.get("revenue") or financials.get("total_revenue")
        net_income = financials.get("net_income") or financials.get("profit") or financials.get("earnings")
        if revenue is not None and net_income is not None:
            try:
                revenue_val = float(revenue)
                net_val = float(net_income)
                financials_score = max(0.0, min(100.0, 50.0 + (net_val / max(revenue_val, 1.0)) * 100.0))
            except (TypeError, ValueError):
                financials_score = 50.0
        elif financials.get("has_data"):
            financials_score = 75.0

    factors = {
        "valuation": round(valuation_score, 1),
        "financial_strength": round(financials_score, 1),
        "dividend_support": round(dividend_support, 1),
        "momentum": round(momentum_score, 1),
        "liquidity": round(volume_score, 1),
        "stability": round(stability_score, 1),
    }

    score = round(sum(factors.values()) / len(factors), 1)
    rating = "Excellent" if score >= 80 else "Good" if score >= 60 else "Fair" if score >= 40 else "Poor"

    return {
        "score": score,
        "overall_score": score,
        "rating": rating,
        "factors": factors,
        "symbol": symbol_name,
    }