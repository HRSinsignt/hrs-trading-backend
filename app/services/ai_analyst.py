"""
The AI layer. This module NEVER hits the market for numbers itself — it only
receives data that the rest of the backend already pulled from STACKS (or
calculated locally from STACKS data), and explains it in plain language.

Every prompt sent here should label its inputs as one of:
  - LIVE STACKS DATA        (verbatim from the API)
  - CALCULATED METRIC       (derived locally from STACKS data, e.g. a health score)
  - GENERAL FINANCIAL EDUCATION (background knowledge, not specific to this stock)

The model is instructed to keep those categories visible in its answer and to
say so explicitly if a figure it would need is missing, rather than filling
the gap with a plausible-sounding number.
"""
from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from app.config import settings

SYSTEM_PROMPT = """You are HRS AI, the market analyst assistant for HRS Trading Analysis, \
covering the JSE (Jamaica Stock Exchange).

Hard rules:
1. Only use the numbers given to you in the "DATA" block below. Never invent
   a price, ratio, percentage, or date.
2. If a field is missing, null, or "N/A", say so plainly ("STACKS did not
   return a P/E ratio for this stock") instead of estimating one.
3. Label your claims: prefix data-derived sentences with where the number
   came from, e.g. "According to the latest STACKS data..." or "Based on our
   calculation...". General background/education can be flagged as such
   ("As general context...").
4. This is not investment advice. Never say "buy this stock", "sell this
   stock", or promise a "guaranteed" outcome. Use phrasing like "based on the
   available data...", "potentially attractive based on these metrics...",
   or "investors may wish to investigate further...".
5. Be concise and specific — reference the actual figures you were given.
6. Every response about market data should end with a one-line reminder of
   when the underlying data was retrieved, using the retrieved_at/timestamp
   fields given to you — never claim data is "real-time" unless told so.
"""

DISCLAIMER = (
    "HRS Trading Analysis provides market information and analytical tools for "
    "informational and educational purposes only. It is not financial "
    "advice and does not guarantee investment outcomes."
)


class AIAnalyst:
    def __init__(self) -> None:
        self._client: AsyncAnthropic | None = None

    @property
    def client(self) -> AsyncAnthropic:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable "
                "AI analysis."
            )
        if self._client is None:
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def _run(self, user_prompt: str, data: dict[str, Any]) -> str:
        data_block = json.dumps(data, indent=2, default=str)
        message = await self.client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\nDATA:\n```json\n{data_block}\n```",
                }
            ],
        )
        return "".join(block.text for block in message.content if block.type == "text")

    async def analyze_stock(self, symbol: str, bundle: dict[str, Any]) -> str:
        prompt = (
            f"Analyze the JSE-listed stock {symbol} using only the data below. "
            "Structure your answer with these exact section headers, in this "
            "order, omitting content within a section if the data isn't "
            "available (say so rather than skipping the header silently):\n\n"
            "QUICK SUMMARY\nVALUATION\nFINANCIAL HEALTH\nPRICE PERFORMANCE\n"
            "DIVIDENDS\nSTRENGTHS\nRISKS\nWHAT TO WATCH\n\n"
            "Use the calculated_health_score object (if present) under "
            "FINANCIAL HEALTH and label it CALCULATED, not live data."
        )
        return await self._run(prompt, bundle)

    async def compare_stocks(self, bundles: list[dict[str, Any]], question: str | None = None) -> str:
        prompt = (
            (f'The user asked: "{question}". ' if question else "")
            + "Compare the JSE-listed stocks below using only the data given. "
            "Address, in order: which has stronger valuation metrics, which has "
            "stronger financial performance, which has better dividend "
            "characteristics, which has stronger momentum, and the major "
            "differences overall. If a metric is missing for one or more "
            "companies, say so instead of estimating it. Do not declare an "
            "overall 'winner' or give a guaranteed recommendation."
        )
        return await self._run(prompt, {"companies": bundles})

    async def market_summary(self, bundle: dict[str, Any]) -> str:
        prompt = (
            "Write a concise JSE market summary using only the data below. "
            "Structure it with these section headers: Market Overview, Biggest "
            "Movers, Most Active Stocks, Important Valuation Observations, "
            "Notable Activity, Things Investors May Want to Watch. State the "
            "data retrieval timestamp clearly."
        )
        return await self._run(prompt, bundle)

    async def agent_explain(self, question: str, findings: dict[str, Any]) -> str:
        prompt = (
            f'The user asked the HRS AI Research agent: "{question}". Below are '
            "the candidates the backend already retrieved, filtered, and ranked "
            "using STACKS data and locally-calculated metrics — do not "
            "re-rank or add candidates. Explain why these came out on top and "
            "what data was used, being explicit about any gaps."
        )
        return await self._run(prompt, findings)

    async def rank_by_pe(self, ranked: list[dict[str, Any]], question: str) -> str:
        prompt = (
            f'The user asked: "{question}". Below is a pre-computed ranking '
            "(already filtered for missing/invalid P/E values, already sorted "
            "in Python). Explain the ranking and highlight notable entries. "
            "Do not re-derive or re-sort the numbers yourself."
        )
        return await self._run(prompt, {"ranked_results": ranked})

    async def general_question(self, question: str, context: dict[str, Any]) -> str:
        prompt = (
            f'The user asked: "{question}". Use the STACKS data provided as '
            "context where relevant. If the question needs data not included "
            "here, say what additional endpoint/data would be needed instead "
            "of guessing."
        )
        return await self._run(prompt, context)


ai_analyst = AIAnalyst()
