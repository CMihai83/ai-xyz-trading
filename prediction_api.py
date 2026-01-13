"""
AI-XYZ Prediction API
FastAPI endpoint for prediction service.

Endpoints:
- GET /predict/{symbol} - Get prediction for a symbol
- GET /predict/batch - Get predictions for multiple symbols
- GET /market/overview - Get market overview
- GET /stats - Get service statistics
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
import ccxt
import os
from dotenv import dotenv_values
from datetime import datetime

from prediction_service import PredictionService, get_prediction_service
from prediction_model_final import PredictionModelFinal

# Load environment
env = dotenv_values('/root/ai_xyz/.env')

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': env.get('BITGET_API_KEY'),
    'secret': env.get('BITGET_API_SECRET'),
    'password': env.get('BITGET_API_PASSPHRASE'),
    'options': {'defaultType': 'swap'}
})

# Initialize prediction service
prediction_service = get_prediction_service(exchange)

# Create FastAPI app
app = FastAPI(
    title="AI-XYZ Prediction API",
    description="Price prediction service for cryptocurrency trading",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response models
class PredictionResponse(BaseModel):
    symbol: str
    direction: str
    confidence: float
    strength: str
    entry_price: float
    target_15m: float
    target_30m: float
    target_60m: float
    stop_loss: float
    risk_reward: float
    signals: Dict
    timestamp: str
    expires_at: str
    is_valid: bool


class BatchPredictionResponse(BaseModel):
    count: int
    predictions: List[Dict]


class MarketOverviewResponse(BaseModel):
    timestamp: str
    total_analyzed: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    market_bias: str
    top_bullish: List[Dict]
    top_bearish: List[Dict]


class StatsResponse(BaseModel):
    prediction_count: int
    correct_predictions: int
    accuracy: float
    cache_size: int
    active_predictions: int


class EntrySignalRequest(BaseModel):
    symbol: str
    scanner_direction: str  # 'long' or 'short'


class ExitSignalRequest(BaseModel):
    symbol: str
    position_side: str  # 'long' or 'short'
    entry_price: float


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "service": "AI-XYZ Prediction API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "/predict/{symbol}",
            "/predict/batch",
            "/market/overview",
            "/entry/signal",
            "/exit/signal",
            "/stats"
        ]
    }


@app.get("/predict/{symbol}", response_model=PredictionResponse)
async def get_prediction(symbol: str, timeframe: str = "60m"):
    """
    Get prediction for a specific symbol.

    Args:
        symbol: Trading symbol (e.g., API3USDT or API3/USDT:USDT)
        timeframe: Prediction timeframe (5m, 15m, 30m, 60m)
    """
    # Normalize symbol format
    if '/' not in symbol:
        symbol = f"{symbol[:len(symbol)-4]}/{symbol[-4:]}:USDT"

    signal = prediction_service.predict(symbol)

    if signal is None:
        raise HTTPException(status_code=404, detail=f"Unable to generate prediction for {symbol}")

    return PredictionResponse(
        symbol=signal.symbol,
        direction=signal.direction,
        confidence=signal.confidence,
        strength=signal.strength.value,
        entry_price=signal.entry_price,
        target_15m=signal.target_15m,
        target_30m=signal.target_30m,
        target_60m=signal.target_60m,
        stop_loss=signal.stop_loss,
        risk_reward=signal.risk_reward,
        signals=signal.signals,
        timestamp=signal.timestamp.isoformat(),
        expires_at=signal.expires_at.isoformat(),
        is_valid=signal.is_valid()
    )


@app.get("/predict/batch", response_model=BatchPredictionResponse)
async def get_batch_predictions(
    symbols: str = Query(..., description="Comma-separated list of symbols")
):
    """
    Get predictions for multiple symbols.

    Args:
        symbols: Comma-separated list of symbols
    """
    symbol_list = [s.strip() for s in symbols.split(',')]

    # Normalize symbols
    normalized = []
    for s in symbol_list:
        if '/' not in s:
            s = f"{s[:len(s)-4]}/{s[-4:]}:USDT"
        normalized.append(s)

    predictions = prediction_service.predict_batch(normalized)

    results = []
    for symbol, signal in predictions.items():
        results.append(signal.to_dict())

    return BatchPredictionResponse(
        count=len(results),
        predictions=results
    )


@app.get("/market/overview", response_model=MarketOverviewResponse)
async def get_market_overview(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols (default: top 20 by volume)")
):
    """
    Get market overview with predictions.

    Args:
        symbols: Optional comma-separated list of symbols
    """
    if symbols:
        symbol_list = [s.strip() for s in symbols.split(',')]
        # Normalize
        normalized = []
        for s in symbol_list:
            if '/' not in s:
                s = f"{s[:len(s)-4]}/{s[-4:]}:USDT"
            normalized.append(s)
    else:
        # Get top 20 symbols by volume
        try:
            tickers = exchange.fetch_tickers()
            # Filter USDT perpetual futures
            usdt_futures = [(k, v) for k, v in tickers.items()
                          if k.endswith(':USDT') and v.get('quoteVolume', 0) > 0]
            # Sort by volume
            usdt_futures.sort(key=lambda x: x[1].get('quoteVolume', 0), reverse=True)
            normalized = [s[0] for s in usdt_futures[:20]]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching symbols: {e}")

    overview = prediction_service.get_market_overview(normalized)

    return MarketOverviewResponse(**overview)


@app.post("/entry/signal")
async def check_entry_signal(request: EntrySignalRequest):
    """
    Check if entry is approved based on prediction.

    Args:
        request: Entry signal request with symbol and scanner direction
    """
    symbol = request.symbol
    if '/' not in symbol:
        symbol = f"{symbol[:len(symbol)-4]}/{symbol[-4:]}:USDT"

    signal = prediction_service.get_entry_signal(
        symbol,
        min_confidence=70,
        min_rr=0.5
    )

    if signal:
        return {
            "approved": True,
            "signal": signal
        }
    else:
        # Get prediction anyway for context
        pred = prediction_service.predict(symbol)
        return {
            "approved": False,
            "reason": "Entry conditions not met",
            "prediction": pred.to_dict() if pred else None
        }


@app.post("/exit/signal")
async def check_exit_signal(request: ExitSignalRequest):
    """
    Check if position should be exited based on prediction.

    Args:
        request: Exit signal request with position details
    """
    symbol = request.symbol
    if '/' not in symbol:
        symbol = f"{symbol[:len(symbol)-4]}/{symbol[-4:]}:USDT"

    exit_signal = prediction_service.get_exit_signal(
        symbol,
        request.position_side,
        request.entry_price
    )

    return {
        "should_exit": exit_signal is not None,
        "signal": exit_signal
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get prediction service statistics"""
    stats = prediction_service.get_stats()
    return StatsResponse(**stats)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "prediction_service": "active",
        "exchange": "connected" if exchange else "disconnected"
    }


def run_api(host: str = "0.0.0.0", port: int = 8009):
    """Run the prediction API server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    print("Starting AI-XYZ Prediction API on port 8009...")
    run_api()
