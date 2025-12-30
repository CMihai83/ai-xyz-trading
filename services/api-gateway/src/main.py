"""
API Gateway - Main entry point for the AI Trading System.
Orchestrates all services and provides unified API.
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import asyncio
import time
from datetime import datetime
import structlog
import uvicorn

from config import settings
from futures_trading_engine import futures_trading_engine
from bitget_futures_client import BitgetFuturesClient, test_bitget_futures_connection
from live_positions_registry import LivePositionsRegistry
from exchange_reconciliation import ExchangeReconciliationService
from position_zone_manager import PositionZoneManager

logger = structlog.get_logger(__name__)

# Initialize new components
positions_registry = None
reconciliation_service = None
zone_manager = None

app = FastAPI(
    title="AI Trading System - API Gateway",
    description="Unified API for the complete AI-powered trading system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins including moondox.eu
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

security = HTTPBearer()

# Pydantic models
class TradingSignalRequest(BaseModel):
    symbol: str
    signal_type: str
    signal_strength: float
    price: float
    metadata: Optional[Dict[str, Any]] = None

class SystemStatus(BaseModel):
    status: str
    timestamp: datetime
    services: Dict[str, str]
    trading_engine: Dict[str, Any]
    bitget_connection: bool

@app.on_event("startup")
async def startup_event():
    """Initialize the trading system on startup."""
    global positions_registry, reconciliation_service, zone_manager
    
    logger.info("Starting AI Futures Trading System...")
    
    # Test Bitget Futures connection
    bitget_connected = test_bitget_futures_connection(
        settings.BITGET_API_KEY,
        settings.BITGET_API_SECRET,
        settings.BITGET_API_PASSPHRASE
    )
    
    if bitget_connected:
        logger.info("Bitget Futures connection successful")
        
        # Initialize live positions registry
        positions_registry = LivePositionsRegistry()
        await positions_registry.connect()
        logger.info("Live Positions Registry initialized")
        
        # Initialize reconciliation service
        reconciliation_service = ExchangeReconciliationService(
            registry=positions_registry,
            bitget_client=futures_trading_engine.futures_client,
            interval=5
        )
        await reconciliation_service.start()
        logger.info("Exchange Reconciliation Service started")
        
        # Initialize zone manager
        zone_manager = PositionZoneManager(
            registry=positions_registry,
            bitget_client=futures_trading_engine.futures_client,
            check_interval=3
        )
        await zone_manager.start()
        logger.info("Position Zone Manager started")
        
        # Start futures trading engine
        await futures_trading_engine.start()
        
        # Link zone manager to trading engine for new position notifications
        futures_trading_engine.zone_manager = zone_manager
        futures_trading_engine.registry = positions_registry
        
    else:
        logger.error("Failed to connect to Bitget Futures - trading engine not started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down AI Futures Trading System...")
    
    # Stop all services
    await futures_trading_engine.stop()
    
    if zone_manager:
        await zone_manager.stop()
        
    if reconciliation_service:
        await reconciliation_service.stop()
        
    if positions_registry:
        await positions_registry.disconnect()

@app.get("/")
async def root():
    """Root endpoint with system information."""
    # Test Bitget Futures connection on each request
    bitget_status = "testing"
    try:
        bitget_connected = test_bitget_futures_connection(
            settings.BITGET_API_KEY,
            settings.BITGET_API_SECRET,
            settings.BITGET_API_PASSPHRASE
        )
        bitget_status = "connected" if bitget_connected else "disconnected"
    except:
        bitget_status = "error"
    
    return {
        "service": "ai-trading-system",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "description": "Complete AI-powered futures trading system with Bitget integration",
        "trading_mode": "futures",
        "bitget_configured": True,
        "bitget_status": bitget_status
    }

@app.get("/api/v1/bitget/status")
async def bitget_status():
    """Check Bitget Futures connection status."""
    try:
        connected = test_bitget_futures_connection(
            settings.BITGET_API_KEY,
            settings.BITGET_API_SECRET,
            settings.BITGET_API_PASSPHRASE
        )
        
        return {
            "connected": connected,
            "trading_mode": "futures",
            "api_key": settings.BITGET_API_KEY[:10] + "..." if settings.BITGET_API_KEY else None,
            "timestamp": datetime.now().isoformat(),
            "message": "Bitget Futures connection successful" if connected else "Failed to connect to Bitget Futures"
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    import httpx
    
    # Check all services
    services_status = {}
    service_ports = {
        "api_gateway": 9000,
        "market_scanner": 9001,
        "ai_decision_engine": 9002,
        "position_management": 9003,
        "backtesting_engine": 9004,
        "ml_framework": 9005,
        "monitoring_service": 9006,
        "notification_service": 9007,
        "data_pipeline": 9008,
        "risk_engine": 9009
    }
    
    async with httpx.AsyncClient(timeout=1.0) as client:
        for service, port in service_ports.items():
            try:
                response = await client.get(f"http://localhost:{port}/")
                services_status[service] = "healthy" if response.status_code == 200 else "unhealthy"
            except:
                services_status[service] = "offline"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": services_status,
        "futures_trading_engine": "running" if futures_trading_engine.running else "stopped",
        "bitget_futures_connection": "connected"
    }

@app.get("/system/status", response_model=SystemStatus)
async def get_system_status():
    """Get comprehensive system status."""
    trading_status = await futures_trading_engine.get_futures_trading_status()
    
    return SystemStatus(
        status="operational",
        timestamp=datetime.now(),
        services={
            "market_scanner": "healthy",
            "ai_decision_engine": "healthy",
            "position_management": "healthy",
            "trading_engine": "running" if futures_trading_engine.running else "stopped"
        },
        trading_engine=trading_status,
        bitget_connection=True
    )

# Trading Operations
@app.post("/trading/start")
async def start_trading():
    """Start the futures trading engine."""
    try:
        success = await futures_trading_engine.start()
        if success:
            return {"message": "Futures trading engine started successfully", "status": "running", "mode": "futures"}
        else:
            raise HTTPException(status_code=500, detail="Failed to start futures trading engine")
    except Exception as e:
        logger.error(f"Error starting futures trading engine: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error starting futures trading engine: {str(e)}")

@app.post("/trading/stop")
async def stop_trading():
    """Stop the futures trading engine."""
    try:
        await futures_trading_engine.stop()
        return {"message": "Futures trading engine stopped successfully", "status": "stopped", "mode": "futures"}
    except Exception as e:
        logger.error(f"Error stopping futures trading engine: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error stopping futures trading engine: {str(e)}")

@app.get("/trading/status")
async def get_trading_status():
    """Get futures trading engine status."""
    try:
        status = await futures_trading_engine.get_futures_trading_status()
        return status
    except Exception as e:
        logger.error(f"Error getting trading status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting trading status: {str(e)}")

# Account Information
@app.get("/account/balance")
async def get_account_balance():
    """Get futures account balance from Bitget."""
    try:
        balance = futures_trading_engine.futures_client.get_futures_account("umcbl")
        return {
            "balance": balance,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting account balance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting account balance: {str(e)}")

@app.get("/account/info")
async def get_account_info():
    """Get futures account information from Bitget."""
    try:
        account_info = futures_trading_engine.futures_client.get_futures_account("umcbl")
        return {
            "account_info": account_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting account info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting account info: {str(e)}")

# Market Data Endpoints
@app.get("/market/ticker/{symbol}")
async def get_ticker(symbol: str):
    """Get futures ticker information for a symbol."""
    try:
        ticker = futures_trading_engine.futures_client.get_futures_ticker(f"{symbol}USDT")
        return ticker
    except Exception as e:
        logger.error(f"Error getting ticker for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting ticker: {str(e)}")

@app.get("/market/scan")
async def scan_market():
    """Get futures market scan results."""
    try:
        scan_results = await futures_trading_engine.get_futures_market_scan()
        return scan_results
    except Exception as e:
        logger.error(f"Error scanning market: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error scanning market: {str(e)}")

@app.get("/api/market/symbols")
async def get_market_symbols():
    """Get all available futures trading symbols."""
    try:
        all_tickers = futures_trading_engine.futures_client.get_all_futures_tickers("umcbl")
        symbols = [ticker.get('symbol', '') for ticker in all_tickers if ticker.get('symbol', '').endswith('USDT')]
        return {
            "symbols": symbols[:50],  # Return top 50 symbols
            "total": len(symbols),
            "mode": "futures",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting market symbols: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting market symbols: {str(e)}")

# Position Management
@app.get("/positions")
async def get_positions():
    """Get all active futures positions."""
    try:
        return {
            "positions": list(futures_trading_engine.active_positions.values()),
            "count": len(futures_trading_engine.active_positions),
            "mode": "futures",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting positions: {str(e)}")

@app.get("/api/positions")
async def get_api_positions():
    """Get all active futures positions (API endpoint)."""
    try:
        # Get actual positions from Bitget
        bitget_positions = futures_trading_engine.futures_client.get_all_positions()
        
        # Filter and format positions that have actual size
        active_positions = []
        for pos in bitget_positions:
            if float(pos.get('total', 0)) > 0:
                active_positions.append({
                    'symbol': pos.get('symbol', '').replace('_UMCBL', ''),
                    'side': pos.get('holdSide'),
                    'size': float(pos.get('total', 0)),
                    'entry_price': float(pos.get('averageOpenPrice', 0)),
                    'current_price': float(pos.get('marketPrice', 0)),
                    'unrealized_pnl': float(pos.get('unrealizedPL', 0)),
                    'margin': float(pos.get('margin', 0)),
                    'leverage': int(pos.get('leverage', 1)),
                    'margin_mode': pos.get('marginMode', 'fixed')
                })
        
        return {
            "positions": active_positions,
            "count": len(active_positions),
            "mode": "futures",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting positions: {str(e)}")

@app.get("/positions/{position_id}")
async def get_position(position_id: str):
    """Get specific futures position details."""
    try:
        if position_id not in futures_trading_engine.active_positions:
            raise HTTPException(status_code=404, detail="Position not found")
        
        return futures_trading_engine.active_positions[position_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position {position_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting position: {str(e)}")

# Manual Trading Operations
@app.post("/trading/long")
async def open_long_position(symbol: str, quantity: float, leverage: int = 10, price: Optional[float] = None):
    """Manually open a long futures position."""
    try:
        order_type = "market" if price is None else "limit"
        
        # Set leverage
        futures_trading_engine.futures_client.set_leverage(
            f"{symbol}USDT",
            "USDT",
            leverage
        )
        
        order_result = futures_trading_engine.futures_client.place_futures_order(
            symbol=f"{symbol}USDT",
            margin_coin="USDT",
            side="open_long",
            order_type=order_type,
            size=str(quantity),
            price=str(price) if price else None
        )
        
        return {
            "message": "Long position opened successfully",
            "order": order_result,
            "leverage": leverage,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error placing buy order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error placing buy order: {str(e)}")

@app.post("/trading/short")
async def open_short_position(symbol: str, quantity: float, leverage: int = 10, price: Optional[float] = None):
    """Manually open a short futures position."""
    try:
        order_type = "market" if price is None else "limit"
        
        # Set leverage
        futures_trading_engine.futures_client.set_leverage(
            f"{symbol}USDT",
            "USDT",
            leverage
        )
        
        order_result = futures_trading_engine.futures_client.place_futures_order(
            symbol=f"{symbol}USDT",
            margin_coin="USDT",
            side="open_short",
            order_type=order_type,
            size=str(quantity),
            price=str(price) if price else None
        )
        
        return {
            "message": "Short position opened successfully",
            "order": order_result,
            "leverage": leverage,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error placing sell order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error placing sell order: {str(e)}")

# Futures Position Closure
@app.post("/trading/close")
async def close_position(symbol: str, side: str):
    """Close a futures position."""
    try:
        # Get current position
        position = futures_trading_engine.futures_client.get_single_position(f"{symbol}USDT", "USDT")
        
        if not position or len(position) == 0:
            raise HTTPException(status_code=404, detail="No position found for this symbol")
        
        # Find the position with the matching side
        target_position = None
        for pos in position:
            if (side == "long" and pos.get('holdSide') == 'long') or \
               (side == "short" and pos.get('holdSide') == 'short'):
                target_position = pos
                break
        
        if not target_position:
            raise HTTPException(status_code=404, detail=f"No {side} position found")
        
        # Close the position
        close_side = "close_long" if side == "long" else "close_short"
        size = target_position.get('total', 0)
        
        order_result = futures_trading_engine.futures_client.place_futures_order(
            symbol=f"{symbol}USDT",
            margin_coin="USDT",
            side=close_side,
            order_type="market",
            size=str(size)
        )
        
        return {
            "message": f"{side.capitalize()} position closed successfully",
            "order": order_result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing position: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}")

# Order Management
@app.get("/orders/open")
async def get_open_orders():
    """Get all open futures orders."""
    try:
        orders = futures_trading_engine.futures_client.get_futures_open_orders()
        return {
            "orders": orders,
            "count": len(orders),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting open orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting open orders: {str(e)}")

@app.get("/orders/history")
async def get_order_history(symbol: Optional[str] = None, limit: int = 100):
    """Get futures order history."""
    try:
        if symbol:
            orders = futures_trading_engine.futures_client.get_futures_order_history(f"{symbol}USDT", limit=limit)
        else:
            # Get history for all major pairs
            orders = []
        return {
            "orders": orders,
            "count": len(orders),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting order history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting order history: {str(e)}")

@app.delete("/orders/{order_id}")
async def cancel_order(order_id: str, symbol: str):
    """Cancel a futures order."""
    try:
        result = futures_trading_engine.futures_client.cancel_futures_order(
            f"{symbol}USDT",
            "USDT",
            order_id=order_id
        )
        return {
            "message": "Order cancelled successfully",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error cancelling order: {str(e)}")

# Futures-specific endpoints
@app.post("/futures/leverage")
async def set_leverage(symbol: str, leverage: int):
    """Set leverage for a futures symbol."""
    try:
        result = futures_trading_engine.futures_client.set_leverage(
            f"{symbol}USDT",
            "USDT",
            leverage
        )
        return {
            "message": f"Leverage set to {leverage}x for {symbol}",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error setting leverage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting leverage: {str(e)}")

@app.get("/futures/positions")
async def get_futures_positions():
    """Get all futures positions from exchange."""
    try:
        positions = futures_trading_engine.futures_client.get_all_positions("USDT-FUTURES")
        return {
            "positions": positions,
            "count": len(positions),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting futures positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting futures positions: {str(e)}")

# System Control
@app.post("/system/restart")
async def restart_system():
    """Restart the futures trading system."""
    try:
        await futures_trading_engine.stop()
        await asyncio.sleep(2)
        success = await futures_trading_engine.start()
        
        if success:
            return {"message": "System restarted successfully", "status": "running"}
        else:
            raise HTTPException(status_code=500, detail="Failed to restart system")
    except Exception as e:
        logger.error(f"Error restarting system: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error restarting system: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
