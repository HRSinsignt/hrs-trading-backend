from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import analysis, market, status, stocks

app = FastAPI(
    title="HRS Trading Analysis API",
    description="Backend for HRS Trading Analysis, a Jamaica Stock Exchange AI research app. "
    "All market data is sourced live from the STACKS API — nothing here is "
    "mock or hard-coded.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hrs-trading-frontend.vercel.app",
        "https://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(analysis.router)
app.include_router(market.router)
app.include_router(status.router)


@app.get("/")
async def root():
    return {"service": "hrs-trading-analysis-backend", "status": "running"}
