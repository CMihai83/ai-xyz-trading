"""
Configuration module for API Gateway service.

This module handles all configuration settings using Pydantic Settings
for type validation and environment variable management.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Optional
import os

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application Settings
    APP_NAME: str = "AI Trading System API Gateway"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Server Settings
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    WORKERS: int = Field(default=1, env="WORKERS")
    
    # Security Settings
    SECRET_KEY: str = Field(env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # CORS Settings
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        env="CORS_ORIGINS"
    )
    ALLOWED_HOSTS: List[str] = Field(
        default=["localhost", "127.0.0.1"],
        env="ALLOWED_HOSTS"
    )
    
    # Database Settings
    DATABASE_URL: str = Field(env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis Settings
    REDIS_URL: str = Field(env="REDIS_URL")
    REDIS_POOL_SIZE: int = Field(default=10, env="REDIS_POOL_SIZE")
    
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = Field(env="KAFKA_BOOTSTRAP_SERVERS")
    KAFKA_GROUP_ID: str = Field(default="api-gateway", env="KAFKA_GROUP_ID")
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW: int = Field(default=60, env="RATE_LIMIT_WINDOW")
    
    # Monitoring Settings
    PROMETHEUS_PORT: int = Field(default=8001, env="PROMETHEUS_PORT")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # External Service URLs
    MARKET_SCANNER_URL: str = Field(
        default="http://market-scanner:8001",
        env="MARKET_SCANNER_URL"
    )
    AI_DECISION_ENGINE_URL: str = Field(
        default="http://ai-decision-engine:8002",
        env="AI_DECISION_ENGINE_URL"
    )
    POSITION_MANAGEMENT_URL: str = Field(
        default="http://position-management:8003",
        env="POSITION_MANAGEMENT_URL"
    )
    BACKTESTING_ENGINE_URL: str = Field(
        default="http://backtesting-engine:8004",
        env="BACKTESTING_ENGINE_URL"
    )
    ML_FRAMEWORK_URL: str = Field(
        default="http://ml-framework:8005",
        env="ML_FRAMEWORK_URL"
    )
    MONITORING_SERVICE_URL: str = Field(
        default="http://monitoring-service:8006",
        env="MONITORING_SERVICE_URL"
    )
    NOTIFICATION_SERVICE_URL: str = Field(
        default="http://notification-service:8007",
        env="NOTIFICATION_SERVICE_URL"
    )
    DATA_PIPELINE_URL: str = Field(
        default="http://data-pipeline:8008",
        env="DATA_PIPELINE_URL"
    )
    RISK_ENGINE_URL: str = Field(
        default="http://risk-engine:8009",
        env="RISK_ENGINE_URL"
    )
    
    # API Keys and External Services
    ALPHA_VANTAGE_API_KEY: Optional[str] = Field(default=None, env="ALPHA_VANTAGE_API_KEY")
    POLYGON_API_KEY: Optional[str] = Field(default=None, env="POLYGON_API_KEY")
    FINNHUB_API_KEY: Optional[str] = Field(default=None, env="FINNHUB_API_KEY")
    
    # Email Settings
    SMTP_HOST: Optional[str] = Field(default=None, env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(default=None, env="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    
    # Notification Settings
    SLACK_WEBHOOK_URL: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None, env="DISCORD_WEBHOOK_URL")
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("ALLOWED_HOSTS", pre=True)
    def parse_allowed_hosts(cls, v):
        """Parse allowed hosts from string or list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed_environments = ["development", "staging", "production"]
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of: {allowed_environments}")
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level setting."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {allowed_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Create global settings instance
settings = Settings()

# Service configuration mapping
SERVICE_CONFIG = {
    "market_scanner": {
        "url": settings.MARKET_SCANNER_URL,
        "timeout": 30,
        "retries": 3
    },
    "ai_decision_engine": {
        "url": settings.AI_DECISION_ENGINE_URL,
        "timeout": 60,
        "retries": 2
    },
    "position_management": {
        "url": settings.POSITION_MANAGEMENT_URL,
        "timeout": 30,
        "retries": 3
    },
    "backtesting_engine": {
        "url": settings.BACKTESTING_ENGINE_URL,
        "timeout": 300,
        "retries": 1
    },
    "ml_framework": {
        "url": settings.ML_FRAMEWORK_URL,
        "timeout": 120,
        "retries": 2
    },
    "monitoring_service": {
        "url": settings.MONITORING_SERVICE_URL,
        "timeout": 30,
        "retries": 3
    },
    "notification_service": {
        "url": settings.NOTIFICATION_SERVICE_URL,
        "timeout": 15,
        "retries": 3
    },
    "data_pipeline": {
        "url": settings.DATA_PIPELINE_URL,
        "timeout": 60,
        "retries": 2
    },
    "risk_engine": {
        "url": settings.RISK_ENGINE_URL,
        "timeout": 30,
        "retries": 3
    }
}

# API endpoint mappings
API_ROUTES = {
    # Market Data Routes
    "/market/symbols": "market_scanner",
    "/market/quotes": "market_scanner",
    "/market/historical": "market_scanner",
    "/market/signals": "market_scanner",
    
    # Trading Routes
    "/trading/orders": "position_management",
    "/trading/positions": "position_management",
    "/trading/executions": "position_management",
    
    # Portfolio Routes
    "/portfolio/performance": "position_management",
    "/portfolio/risk": "risk_engine",
    "/portfolio/allocation": "position_management",
    
    # Analytics Routes
    "/analytics/backtest": "backtesting_engine",
    "/analytics/performance": "backtesting_engine",
    "/analytics/optimization": "backtesting_engine",
    
    # ML Routes
    "/ml/models": "ml_framework",
    "/ml/predictions": "ml_framework",
    "/ml/training": "ml_framework",
    
    # Decision Routes
    "/decisions/signals": "ai_decision_engine",
    "/decisions/recommendations": "ai_decision_engine",
    "/decisions/analysis": "ai_decision_engine",
    
    # Monitoring Routes
    "/monitoring/health": "monitoring_service",
    "/monitoring/metrics": "monitoring_service",
    "/monitoring/alerts": "monitoring_service",
    
    # Data Routes
    "/data/feeds": "data_pipeline",
    "/data/quality": "data_pipeline",
    "/data/processing": "data_pipeline"
}

