from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai_analyst import ai_analyst
from app.services.health_score import compute_health_score
from app.services.market_analytics import market_movers, market_summary as compute_market_summary
from app.services.stacks_api import StacksAPIError, stacks_client
from app.services.stock_bundle import get_stock_bundle

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class CheapestPERequest(BaseModel):
    question: str = "What are the cheapest JSE stocks based on P/E?"
    limit: int = 10


class StockAnalysisRequest(BaseModel):
    symbol: str


class AskRequest(BaseModel):
    question: str
    symbol: str | None = None


class CompareRequest(BaseModel):
    symbols: list[str]
    question: str | None = None


class AgentResearchRequest(BaseModel):
    question: str
    limit: int = 5


async def _peer_pe_values() -> list[float]:
    try:
        data = await stacks_client.list_stocks()
    except StacksAPIError:
        return []
    return [
        s["pe_ratio"]
        for s in data.get("stocks", [])
        if isinstance(s.get("pe_ratio"), (int, float)) and s["pe_ratio"] > 0
    ]


@router.post("/cheapest-pe")
async def cheapest_pe(req: CheapestPERequest):
    """Implements the documented workflow:
    1. retrieve P/E data -> 2. validate -> 3. drop missing/invalid ->
    4. rank in Python -> 5. hand structured results to the AI -> 6. explain.
    """
    try:
        pe_data = await stacks_client.get_pe_ratios()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")

    raw = pe_data.get("pe_ratios")
    rows = raw if isinstance(raw, list) else []

    valid = []
    for row in rows:
        pe = row.get("pe_ratio") if isinstance(row, dict) else None
        if pe is None:
            pe = (row or {}).get("peRatio") if isinstance(row, dict) else None
        try:
            pe_val = float(pe)
        except (TypeError, ValueError):
            continue
        if pe_val <= 0:
            continue
        valid.append({**row, "pe_ratio": pe_val})

    ranked = sorted(valid, key=lambda r: r["pe_ratio"])[: req.limit]

    if not ranked:
        return {
            "ranked_results": [],
            "explanation": (
                "STACKS did not return any stocks with a valid, positive P/E "
                "ratio right now, so no ranking could be produced."
            ),
            "retrieved_at": pe_data.get("retrieved_at"),
        }

    explanation = await ai_analyst.rank_by_pe(ranked, req.question)
    return {
        "ranked_results": ranked,
        "explanation": explanation,
        "retrieved_at": pe_data.get("retrieved_at"),
    }


@router.post("/stock")
async def analyze_stock(req: StockAnalysisRequest):
    """Implements the documented "Analyze GK" workflow: gather quote,
    history, financials, dividends, compute a Health Score, then explain in
    the structured QUICK SUMMARY / VALUATION / ... format.
    """
    peer_pe = await _peer_pe_values()
    bundle = await get_stock_bundle(req.symbol, peer_pe_values=peer_pe)

    try:
        explanation = await ai_analyst.analyze_stock(bundle["symbol"], bundle)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    return {"symbol": bundle["symbol"], "data": bundle, "explanation": explanation}


@router.post("/compare")
async def compare_stocks(req: CompareRequest):
    """Company comparison across up to 4 symbols. Each bundle is gathered
    the same way as single-stock analysis (quote/history/financials/
    dividends/health score); the AI only compares, never re-fetches.
    """
    symbols = [s.upper() for s in req.symbols if s.strip()][:4]
    if len(symbols) < 2:
        raise HTTPException(400, "Provide at least 2 symbols to compare (max 4).")

    peer_pe = await _peer_pe_values()
    bundles = [await get_stock_bundle(sym, peer_pe_values=peer_pe) for sym in symbols]

    try:
        explanation = await ai_analyst.compare_stocks(bundles, req.question)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    return {"symbols": symbols, "companies": bundles, "explanation": explanation}


@router.post("/market-summary")
async def market_summary_endpoint():
    """AI-generated narrative market summary, built on top of the
    backend-computed market_summary + market_movers aggregates."""
    try:
        stocks_data = await stacks_client.list_stocks()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")

    stocks = stocks_data.get("stocks", [])
    summary = compute_market_summary(stocks)
    movers = market_movers(stocks, limit=5)

    bundle = {
        "retrieved_at": stocks_data.get("retrieved_at"),
        "summary": summary,
        "movers": movers,
    }

    try:
        narrative = await ai_analyst.market_summary(bundle)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    return {"data": bundle, "summary": narrative}


@router.post("/agent-research")
async def agent_research(req: AgentResearchRequest):
    """A simplified 'AI Agent' research workflow. All data gathering,
    filtering, and ranking happens in Python; the steps list is returned so
    the frontend can render research progress, and the AI only explains the
    final, backend-produced candidate list.
    """
    steps = []

    def step(label, ok=True):
        steps.append({"label": label, "done": ok})

    try:
        stocks_data = await stacks_client.list_stocks()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")
    step("Retrieve JSE stocks")

    stocks = stocks_data.get("stocks", [])
    peer_pe = [s["pe_ratio"] for s in stocks if isinstance(s.get("pe_ratio"), (int, float)) and s["pe_ratio"] > 0]
    step("Retrieve valuation information (P/E)")

    candidates = [s for s in stocks if isinstance(s.get("pe_ratio"), (int, float)) and s["pe_ratio"] > 0]
    candidates = sorted(candidates, key=lambda s: s["pe_ratio"])[: max(req.limit * 3, req.limit)]
    step("Check P/E and shortlist candidates")

    scored = []
    for s in candidates:
        try:
            fin = await stacks_client.get_financials(s["symbol"])
            div = await stacks_client.get_dividends(s["symbol"])
            hist = await stacks_client.get_history(s["symbol"])
        except StacksAPIError:
            fin, div, hist = None, None, None
        health = await compute_health_score(
            symbol=s.get("symbol"),
            stock=s,
            financials=(fin or {}).get("financials"),
            dividends=(div or {}).get("dividends"),
            history=(hist or {}).get("history") if isinstance((hist or {}).get("history"), list) else None,
            peer_pe_values=peer_pe,
        )
        scored.append({**s, "health_score": health.get("overall_score"), "health_score_detail": health})
    step("Retrieve financial and dividend information")
    step("Analyze available historical performance")
    step("Calculate Health Scores")

    ranked = sorted(
        [c for c in scored if c.get("health_score") is not None],
        key=lambda c: c["health_score"],
        reverse=True,
    )[: req.limit]
    step("Rank candidates")

    if not ranked:
        step("Generate explanation", ok=False)
        return {
            "steps": steps,
            "candidates": [],
            "explanation": (
                "None of the candidate stocks had enough data (valuation + "
                "financial/dividend/history metrics) to compute a Health Score, "
                "so no ranked shortlist could be produced."
            ),
        }

    try:
        explanation = await ai_analyst.agent_explain(req.question, {"candidates": ranked})
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    step("Generate explanation")

    return {"steps": steps, "candidates": ranked, "explanation": explanation}


@router.post("/ask")
async def ask(req: AskRequest):
    """General-purpose Q&A grounded in STACKS data for a given symbol, if any."""
    context: dict = {}
    if req.symbol:
        symbol = req.symbol.upper()
        try:
            context["quote"] = await stacks_client.get_stock(symbol)
        except StacksAPIError:
            context["quote"] = None
            context["note"] = "STACKS market data is temporarily unavailable for this symbol."

    try:
        answer = await ai_analyst.general_question(req.question, context)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    return {"answer": answer}
