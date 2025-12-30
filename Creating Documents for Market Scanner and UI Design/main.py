"""
API Gateway - Main Application Entry Point

This is the central API gateway that routes requests to appropriate microservices
and handles authentication, rate limiting, and request/response transformation.
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
import time
from typing import Dict, Any

from .config import settings
from .middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    AuthenticationMiddleware,
    MetricsMiddleware
)
from .routers import (
    auth,
    market_data,
    trading,
    portfolio,
    analytics,
    admin,
    health
)
from .database import init_db
from .cache import init_cache
from .monitoring import init_monitoring

# Configure structured logging
logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting API Gateway...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Initialize cache
    await init_cache()
    logger.info("Cache initialized")
    
    # Initialize monitoring
    await init_monitoring()
    logger.info("Monitoring initialized")
    
    logger.info("API Gateway started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Gateway...")
    logger.info("API Gateway shutdown complete")

# Create FastAPI application
app = FastAPI(
    title="AI Trading System API Gateway",
    description="Central API gateway for the AI-powered trading system",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan
)

# Add security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthenticationMiddleware)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(market_data.router, prefix="/market", tags=["market-data"])
app.include_router(trading.router, prefix="/trading", tags=["trading"])
app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Global HTTP exception handler."""
    logger.error(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "timestamp": time.time(),
                "path": str(request.url.path)
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    logger.error(
        "Unhandled exception occurred",
        exception=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "timestamp": time.time(),
                "path": str(request.url.path)
            }
        }
    )

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AI Trading System API Gateway",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": time.time(),
        "environment": settings.ENVIRONMENT
    }

@app.get("/info")
async def info():
    """API information endpoint."""
    return {
        "api": {
            "name": "AI Trading System API Gateway",
            "version": "1.0.0",
            "description": "Central API gateway for the AI-powered trading system"
        },
        "services": {
            "market_scanner": "Market scanning and signal generation",
            "ai_decision_engine": "AI-powered decision making",
            "position_management": "Position and risk management",
            "backtesting_engine": "Strategy backtesting and validation",
            "ml_framework": "Machine learning pipeline",
            "monitoring_service": "System monitoring and health"
        },
        "features": [
            "Real-time market data processing",
            "AI-powered trading decisions",
            "Advanced risk management",
            "Comprehensive backtesting",
            "Machine learning integration",
            "Real-time monitoring and alerts"
        ],
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development"
    )

