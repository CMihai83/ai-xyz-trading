"""
Florin Trading System - Central Configuration
Ensures complete isolation from ai_xyz system
"""
import os
import redis
from typing import Optional

# Redis Configuration
REDIS_DB = int(os.getenv('REDIS_DB', '2'))  # Default to DB 2 for Florin
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

# Log Configuration
LOG_DIR = os.getenv('LOG_DIR', '/var/log/florin_trading')
DATA_DIR = os.getenv('DATA_DIR', '/app/data')

# PID file location
PID_DIR = os.getenv('PID_DIR', '/app/pids')

# State file locations
STATE_DIR = os.getenv('STATE_DIR', '/app')
POSITION_STATE_FILE = os.path.join(STATE_DIR, 'position_state.json')
AVERAGING_STATE_FILE = os.path.join(STATE_DIR, 'averaging_state.json')
CONTINUOUS_TRADING_STATE_FILE = os.path.join(STATE_DIR, 'continuous_trading_state.json')
PERFORMANCE_HISTORY_FILE = os.path.join(STATE_DIR, 'performance_history.json')

# API Configuration (use Florin-specific environment variables)
BITGET_API_KEY = os.getenv('FLORIN_BITGET_API_KEY') or os.getenv('BITGET_API_KEY')
BITGET_API_SECRET = os.getenv('FLORIN_BITGET_API_SECRET') or os.getenv('BITGET_API_SECRET')
BITGET_API_PASSPHRASE = os.getenv('FLORIN_BITGET_API_PASSPHRASE') or os.getenv('BITGET_API_PASSPHRASE')


def get_redis_connection(db: Optional[int] = None) -> redis.Redis:
    """
    Get a Redis connection with the configured database.
    
    Args:
        db: Optional database number. If not provided, uses REDIS_DB from environment.
        
    Returns:
        Redis connection instance
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db if db is not None else REDIS_DB,
        decode_responses=True,
        socket_keepalive=True,
        socket_connect_timeout=5,
        retry_on_timeout=True
    )


def get_log_file_path(log_name: str) -> str:
    """
    Get full path for a log file.
    
    Args:
        log_name: Name of the log file (e.g., 'florin_trading.log')
        
    Returns:
        Full path to the log file
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, log_name)


def get_pid_file_path(pid_name: str) -> str:
    """
    Get full path for a PID file.
    
    Args:
        pid_name: Name of the PID file (e.g., 'florin_trading.pid')
        
    Returns:
        Full path to the PID file
    """
    os.makedirs(PID_DIR, exist_ok=True)
    return os.path.join(PID_DIR, pid_name)


def get_data_file_path(data_name: str) -> str:
    """
    Get full path for a data file.
    
    Args:
        data_name: Name of the data file
        
    Returns:
        Full path to the data file
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, data_name)


# Export configuration summary
def print_config_summary():
    """Print configuration summary for debugging"""
    print("=" * 60)
    print("FLORIN TRADING SYSTEM - CONFIGURATION")
    print("=" * 60)
    print(f"Redis Host: {REDIS_HOST}:{REDIS_PORT}")
    print(f"Redis DB: {REDIS_DB} (ISOLATED FROM AI_XYZ)")
    print(f"Log Directory: {LOG_DIR}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"PID Directory: {PID_DIR}")
    print(f"State Directory: {STATE_DIR}")
    print(f"API Key Configured: {'Yes' if BITGET_API_KEY else 'No'}")
    print("=" * 60)


if __name__ == "__main__":
    print_config_summary()
    
    # Test Redis connection
    try:
        r = get_redis_connection()
        r.ping()
        print(f"\nRedis connection successful (DB {REDIS_DB})")
        
        # Set a test key
        test_key = f"florin_trading:test:{os.getpid()}"
        r.setex(test_key, 60, "Florin Trading System - Isolated Instance")
        print(f"Test key set: {test_key}")
        
        # Verify isolation
        print(f"\nVerifying isolation from ai_xyz (DB 1)...")
        r_aixy = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1, decode_responses=True)
        ai_xyz_keys = r_aixy.keys("*")
        florin_keys = r.keys("*")
        
        print(f"AI_XYZ keys (DB 1): {len(ai_xyz_keys)}")
        print(f"Florin keys (DB {REDIS_DB}): {len(florin_keys)}")
        print("\nIsolation verified! Databases are separate.")
        
    except Exception as e:
        print(f"\nRedis connection failed: {e}")
        print("Make sure Redis is running and accessible.")
