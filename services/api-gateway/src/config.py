"""
Configuration settings for the AI Trading System.
"""

import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Bitget API Configuration
    BITGET_API_KEY: str = "bg_f483546274ffb2bfa567328e98dba6c0"
    BITGET_API_SECRET: str = "387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0"
    BITGET_API_PASSPHRASE: str = "2609Luiza"
    BITGET_SANDBOX: bool = False
    
    # Service URLs (Updated ports)
    MARKET_SCANNER_URL: str = "http://localhost:9001"
    AI_DECISION_ENGINE_URL: str = "http://localhost:9002"
    POSITION_MANAGEMENT_URL: str = "http://localhost:9003"
    BACKTESTING_ENGINE_URL: str = "http://localhost:9004"
    ML_FRAMEWORK_URL: str = "http://localhost:9005"
    MONITORING_SERVICE_URL: str = "http://localhost:9006"
    NOTIFICATION_SERVICE_URL: str = "http://localhost:9007"
    DATA_PIPELINE_URL: str = "http://localhost:9008"
    RISK_ENGINE_URL: str = "http://localhost:9009"
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://trading_user:trading_pass@postgres:5432/trading_db"
    REDIS_URL: str = "redis://redis:6379"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Trading Configuration
    MAX_POSITION_SIZE: float = 0.1  # 10% of portfolio per position
    MAX_PORTFOLIO_RISK: float = 0.15  # 15% total portfolio risk
    DEFAULT_STOP_LOSS: float = 0.15  # 15% stop loss
    DEFAULT_TAKE_PROFIT: float = 0.3  # 30% take profit
    
    # System Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields from .env

settings = Settings()
