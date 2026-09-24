"""
Centralized client for the STACKS Jamaica Stock Exchange public API.

IMPORTANT — this file is the ONLY place that should talk to STACKS directly.
Everything else in the backend (routers, AI layer) goes through this service.

WHAT THIS FILE DOES NOT DO:
- It never invents stock data. If STACKS returns nothing usable, methods
  return None / an empty list / a `DataUnavailable` marker, and callers are
  expected to surface that honestly instead of filling in a placeholder
  number.

VERIFYING THE REAL RESPONSE SHAPE:
This client was built without the ability to reach stacksja.com directly, so
the field names in `_normalize_stock` are best-guess based on the endpoint
names you described (symbol/name/price/change/volume, etc.), with a raw
passthrough for anything unrecognized. Before you rely on this in production:

  1. Set STACKS_API_BASE / STACKS_API_KEY in your .env
  2. Hit GET /api/status and GET /api/stocks from the diagnostics page, or run:
        curl -s $STACKS_API_BASE/stocks | python -m json.tool | head -50
  3. Compare the real field names against `_normalize_stock` below and adjust
     the key lookups there. The raw response is always kept under `raw` on
     each returned object, so nothing is lost while you do this.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.cache import cache

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_RETRIES = 2


class StacksAPIError(Exception):
    """Raised when STACKS cannot be reached or returns an error response."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class StacksAPIClient:
    def __init__(self) -> None:
        self._last_success: Optional[dict] = None
        self._last_error: Optional[dict] = None

    # ------------------------------------------------------------------
    # Low-level request handling: retries, timeouts, error normalization
    # ------------------------------------------------------------------
    async def _request(self, path: str, params: dict | None = None) -> Any:
        url = f"{settings.stacks_api_base.rstrip('/')}/{path.lstrip('/')}"
        headers = {}
        if settings.stacks_api_key:
            headers["x-api-key"] = settings.stacks_api_key

        last_exc: Optional[Exception] = None
        started = time.time()

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    resp = await client.get(url, params=params, headers=headers)
                    elapsed_ms = round((time.time() - started) * 1000, 1)

                    if resp.status_code >= 500 and attempt < MAX_RETRIES:
                        # transient server error - retry with light backoff
                        time.sleep(0.3 * (attempt + 1))
                        continue

                    if resp.status_code >= 400:
                        self._last_error = {
                            "endpoint": path,
                            "status_code": resp.status_code,
                            "message": resp.text[:500],
                            "at": time.time(),
                        }
                        raise StacksAPIError(
                            f"STACKS returned HTTP {resp.status_code} for {path}",
                            status_code=resp.status_code,
                        )

                    try:
                        data = resp.json()
                    except ValueError as e:
                        self._last_error = {
                            "endpoint": path,
                            "status_code": resp.status_code,
                            "message": f"Non-JSON response: {e}",
                            "at": time.time(),
                        }
                        raise StacksAPIError(
                            f"STACKS returned a non-JSON response for {path}"
                        ) from e

                    self._last_success = {
                        "endpoint": path,
                        "status_code": resp.status_code,
                        "response_time_ms": elapsed_ms,
                        "at": time.time(),
                    }
                    return data

                except httpx.RequestError as e:
                    last_exc = e
                    if attempt < MAX_RETRIES:
                        time.sleep(0.3 * (attempt + 1))
                        continue

        self._last_error = {
            "endpoint": path,
            "status_code": None,
            "message": str(last_exc) if last_exc else "Unknown network error",
            "at": time.time(),
        }
        raise StacksAPIError(
            f"Could not reach STACKS API for {path}: {last_exc}"
        )

    async def _cached_request(
        self, cache_key: str, path: str, ttl: int, params: dict | None = None
    ) -> Any:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit.value, hit.retrieved_at_iso, True

        data = await self._request(path, params=params)
        entry = cache.set(cache_key, data, ttl)
        return data, entry.retrieved_at_iso, False

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    async def check_status(self) -> dict:
        """Used by the /api/status diagnostic endpoint."""
        started = time.time()
        try:
            data = await self._request("stocks")
            elapsed_ms = round((time.time() - started) * 1000, 1)
            count = len(data) if isinstance(data, list) else len(
                data.get("data", data.get("stocks", []))
                if isinstance(data, dict)
                else []
            )
            return {
                "connected": True,
                "endpoint_tested": "/stocks",
                "response_time_ms": elapsed_ms,
                "stocks_retrieved": count,
                "last_success": self._last_success,
                "last_error": self._last_error,
            }
        except StacksAPIError as e:
            return {
                "connected": False,
                "endpoint_tested": "/stocks",
                "response_time_ms": round((time.time() - started) * 1000, 1),
                "stocks_retrieved": 0,
                "error": str(e),
                "last_success": self._last_success,
                "last_error": self._last_error,
            }

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _first(d: dict, *keys: str, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    @classmethod
    def _normalize_stock(self, raw_data: dict) -> dict:
        def clean_num(val):
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return val
            try:
                return float(str(val).replace(",", ""))
            except (ValueError, TypeError):
                return None

        return {
            "symbol": raw_data.get("symbol"),
            "company_name": raw_data.get("company_name"),
            "market": raw_data.get("market"),
            "security_type": raw_data.get("security_type"),
            "price": clean_num(raw_data.get("last_traded_price") or raw_data.get("closing_price")),
            "closing_price": clean_num(raw_data.get("closing_price")),
            "change": clean_num(raw_data.get("price_change")),
            "change_percent": clean_num(raw_data.get("change_percent")),
            "volume": clean_num(raw_data.get("volume")),
            "turnover_value": clean_num(raw_data.get("turnover_value")),
            "vwap": clean_num(raw_data.get("vwap")),
            "closing_bid": clean_num(raw_data.get("closing_bid")),
            "closing_ask": clean_num(raw_data.get("closing_ask")),
            "week_range_52": raw_data.get("week_range_52"),
            "ytd_percent": clean_num(raw_data.get("ytd_percent")),
            "qtd_percent": clean_num(raw_data.get("qtd_percent")),
            "prev_quarter_percent": clean_num(raw_data.get("prev_quarter_percent")),
            "week_52_percent": clean_num(raw_data.get("week_52_percent")),
            "close_year_end": clean_num(raw_data.get("close_year_end")),
            "close_prev_quarter_end": clean_num(raw_data.get("close_prev_quarter_end")),
            "close_quarter_before_that": clean_num(raw_data.get("close_quarter_before_that")),
            "trade_date": raw_data.get("trade_date"),
            "raw": raw_data,
        }

    @staticmethod
    def _extract_list(data: Any) -> list[dict]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "stocks", "results", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    # ------------------------------------------------------------------
    # Public endpoints — mirrors the STACKS surface you described
    # ------------------------------------------------------------------
    async def list_stocks(self) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            "stocks", "stocks", settings.live_cache_ttl
        )
        stocks = [self._normalize_stock(s) for s in self._extract_list(data)]
        return {"stocks": stocks, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_stock(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"stock:{symbol}", f"stock/{symbol}", settings.live_cache_ttl
        )
        payload = data.get("data", data) if isinstance(data, dict) else data
        return {
            "stock": self._normalize_stock(payload) if isinstance(payload, dict) else None,
            "retrieved_at": retrieved_at,
            "from_cache": from_cache,
        }

    async def get_history(self, symbol: str, **params) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"history:{symbol}:{params}",
            f"stock/{symbol}/history",
            settings.static_cache_ttl,
            params=params,
        )
        return {"history": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_financials(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"financials:{symbol}", f"stock/{symbol}/financials", settings.static_cache_ttl
        )
        return {"financials": data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_directors(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"directors:{symbol}", f"stock/{symbol}/directors", settings.static_cache_ttl
        )
        return {"directors": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_documents(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"documents:{symbol}", f"stock/{symbol}/documents", settings.static_cache_ttl
        )
        return {"documents": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_trades(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"trades:{symbol}", f"stock/{symbol}/trades", settings.live_cache_ttl
        )
        return {"trades": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_orderbook(self, symbol: str) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            f"orderbook:{symbol}", f"stock/{symbol}/orderbook", settings.live_cache_ttl
        )
        return {"orderbook": data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_pe_ratios(self) -> dict:
        data, retrieved_at, from_cache = await self._cached_request(
            "pe-ratios", "pe-ratios", settings.live_cache_ttl
        )
        return {"pe_ratios": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def get_dividends(self, symbol: Optional[str] = None) -> dict:
        path = f"stock/{symbol}/dividends" if symbol else "dividends"
        key = f"dividends:{symbol or 'all'}"
        data, retrieved_at, from_cache = await self._cached_request(
            key, path, settings.static_cache_ttl
        )
        return {"dividends": self._extract_list(data) or data, "retrieved_at": retrieved_at, "from_cache": from_cache}

    async def search(self, query: str) -> dict:
        data = await self._request("search", params={"q": query})
        return {"results": [self._normalize_stock(s) for s in self._extract_list(data)]}

    async def quote(self, name: str) -> dict:
        data = await self._request("quote", params={"name": name})
        payload = data.get("data", data) if isinstance(data, dict) else data
        return {"quote": self._normalize_stock(payload) if isinstance(payload, dict) else payload}


stacks_client = StacksAPIClient()
