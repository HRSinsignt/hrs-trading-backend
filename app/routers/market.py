from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import market_analytics, screener
from app.services.stacks_api import StacksAPIError, stacks_client

router = APIRouter(prefix="/api/market", tags=["market"])


class ScreenRequest(BaseModel):
    query: str | None = None
    max_price: float | None = None
    min_price: float | None = None
    max_pe: float | None = None
    min_pe: float | None = None
    max_volume: float | None = None
    min_volume: float | None = None
    min_change_pct: float | None = None
    max_change_pct: float | None = None
    has_dividend: bool | None = None


async def _live_stocks():
    try:
        data = await stacks_client.list_stocks()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")
    return data


@router.get("/summary")
async def summary():
    data = await _live_stocks()
    stocks = data.get("stocks", [])
    return {
        "summary": market_analytics.market_summary(stocks),
        "retrieved_at": data.get("retrieved_at"),
    }


@router.get("/movers")
async def movers(limit: int = 10):
    data = await _live_stocks()
    stocks = data.get("stocks", [])
    return {
        "movers": market_analytics.market_movers(stocks, limit=limit),
        "retrieved_at": data.get("retrieved_at"),
    }


@router.get("/pe-rankings")
async def pe_rankings(limit: int = 15):
    data = await _live_stocks()
    stocks = data.get("stocks", [])
    return {
        "rankings": market_analytics.pe_rankings(stocks, limit=limit),
        "retrieved_at": data.get("retrieved_at"),
    }


@router.post("/screen")
async def screen(req: ScreenRequest):
    data = await _live_stocks()
    stocks = data.get("stocks", [])

    filters = {}
    if req.query:
        filters.update(screener.parse_natural_language(req.query))
    # structured filters always take precedence over natural-language guesses
    structured = req.model_dump(exclude={"query"}, exclude_none=True)
    filters.update(structured)

    results = screener.apply_filters(stocks, filters)
    return {
        "filters_applied": filters,
        "results": results,
        "result_count": len(results),
        "retrieved_at": data.get("retrieved_at"),
    }
