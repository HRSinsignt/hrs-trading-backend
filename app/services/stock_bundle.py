"""
Shared helper for assembling a full per-stock data bundle (quote, history,
financials, dividends, health score) — used by the single-stock analysis,
comparison, and agent-research endpoints so the gathering logic lives in one
place instead of being copy-pasted across routers.
"""
from __future__ import annotations

from app.services.health_score import compute_health_score
from app.services.stacks_api import StacksAPIError, stacks_client


async def get_stock_bundle(symbol: str, peer_pe_values: list[float] | None = None) -> dict:
    symbol = symbol.upper()
    bundle: dict = {"symbol": symbol}
    errors = []

    async def safe(label, coro):
        try:
            bundle[label] = await coro
        except StacksAPIError as e:
            bundle[label] = None
            errors.append(f"{label}: {e}")

    await safe("quote", stacks_client.get_stock(symbol))
    await safe("history", stacks_client.get_history(symbol))
    await safe("financials", stacks_client.get_financials(symbol))
    await safe("dividends", stacks_client.get_dividends(symbol))

    stock_obj = (bundle.get("quote") or {}).get("stock") or {}
    history_list = (bundle.get("history") or {}).get("history")
    financials_obj = (bundle.get("financials") or {}).get("financials")
    dividends_list = (bundle.get("dividends") or {}).get("dividends")

    bundle["calculated_health_score"] = await compute_health_score(
        symbol=symbol,
        stock=stock_obj,
        financials=financials_obj,
        dividends=dividends_list,
        history=history_list if isinstance(history_list, list) else None,
        peer_pe_values=peer_pe_values or [],
    )
    if errors:
        bundle["data_gaps"] = errors

    return bundle
