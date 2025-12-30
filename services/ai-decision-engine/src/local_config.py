
import os

# Service URLs - Override for local development
MARKET_SCANNER_URL = os.getenv("MARKET_SCANNER_URL", "http://localhost:8001")
AI_DECISION_ENGINE_URL = os.getenv("AI_DECISION_ENGINE_URL", "http://localhost:8002")
POSITION_MANAGEMENT_URL = os.getenv("POSITION_MANAGEMENT_URL", "http://localhost:8003")
BACKTESTING_ENGINE_URL = os.getenv("BACKTESTING_ENGINE_URL", "http://localhost:8004")
ML_FRAMEWORK_URL = os.getenv("ML_FRAMEWORK_URL", "http://localhost:8005")
MONITORING_SERVICE_URL = os.getenv("MONITORING_SERVICE_URL", "http://localhost:8006")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8007")
DATA_PIPELINE_URL = os.getenv("DATA_PIPELINE_URL", "http://localhost:8008")
RISK_ENGINE_URL = os.getenv("RISK_ENGINE_URL", "http://localhost:8009")

# Database connections
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

# Bitget Configuration
BITGET_API_KEY = "bg_f483546274ffb2bfa567328e98dba6c0"
BITGET_API_SECRET = "387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0"
BITGET_API_PASSPHRASE = "2609Luiza"
