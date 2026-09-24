from fastapi import APIRouter, HTTPException, Query

from app.services.stacks_api import StacksAPIError, stacks_client

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/stocks")
async def list_stocks():
    try:
        return await stacks_client.list_stocks()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}")
async def get_stock(symbol: str):
    try:
        return await stacks_client.get_stock(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/history")
async def get_history(symbol: str, range: str | None = Query(default=None)):
    try:
        params = {"range": range} if range else {}
        return await stacks_client.get_history(symbol.upper(), **params)
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/financials")
async def get_financials(symbol: str):
    try:
        return await stacks_client.get_financials(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/directors")
async def get_directors(symbol: str):
    try:
        return await stacks_client.get_directors(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/documents")
async def get_documents(symbol: str):
    try:
        return await stacks_client.get_documents(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/trades")
async def get_trades(symbol: str):
    try:
        return await stacks_client.get_trades(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/stock/{symbol}/orderbook")
async def get_orderbook(symbol: str):
    try:
        return await stacks_client.get_orderbook(symbol.upper())
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/pe-ratios")
async def get_pe_ratios():
    try:
        return await stacks_client.get_pe_ratios()
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/dividends")
async def get_dividends(symbol: str | None = None):
    try:
        return await stacks_client.get_dividends(symbol.upper() if symbol else None)
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/search")
async def search(q: str = Query(min_length=1)):
    try:
        return await stacks_client.search(q)
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")


@router.get("/quote")
async def quote(name: str = Query(min_length=1)):
    try:
        return await stacks_client.quote(name)
    except StacksAPIError:
        raise HTTPException(503, "STACKS market data is temporarily unavailable. Please try again.")
