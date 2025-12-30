"""Market data router for API Gateway."""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import httpx
from ..config import settings

router = APIRouter()

@router.get("/symbols")
async def get_symbols():
    """Get available trading symbols."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.MARKET_SCANNER_URL}/symbols")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail="Market scanner service unavailable")

@router.get("/quotes/{symbol}")
async def get_quote(symbol: str):
    """Get real-time quote for a symbol."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.MARKET_SCANNER_URL}/quotes/{symbol}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail="Market scanner service unavailable")

@router.get("/historical/{symbol}")
async def get_historical_data(
    symbol: str,
    period: str = Query("1d", description="Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)"),
    interval: str = Query("1m", description="Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)")
):
    """Get historical market data."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.MARKET_SCANNER_URL}/historical/{symbol}",
                params={"period": period, "interval": interval}
            )
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail="Market scanner service unavailable")

@router.get("/signals/{symbol}")
async def get_trading_signals(symbol: str):
    """Get trading signals for a symbol."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{settings.MARKET_SCANNER_URL}/signals/{symbol}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail="Market scanner service unavailable")
