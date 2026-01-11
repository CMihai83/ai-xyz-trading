# ✅ Working System Endpoints

## 🟢 Currently Active Services

### For Windows Browser Access (from WSL2):

#### 1. **InfluxDB Dashboard** ✅
- **URL**: http://localhost:8086
- **Username**: `admin`
- **Password**: `adminpassword`
- **Data Explorer**: http://localhost:8086/orgs/a146866f8a408762/data-explorer?fluxScriptEditor
- **Organization**: trading-org
- **Bucket**: trading-data

#### 2. **AI Decision Engine** ✅
- **URL**: http://localhost:8002
- **Status**: Operational
- **Features**: 5-gate decision system active
- **Test**: `curl http://localhost:8002`

#### 3. **Position Management** ✅
- **URL**: http://localhost:8003
- **Status**: Operational
- **Features**: Zone-based position management
- **Test**: `curl http://localhost:8003`

#### 4. **Monitoring Service** ✅
- **URL**: http://localhost:8006
- **Status**: Operational
- **Features**: System health monitoring
- **Test**: `curl http://localhost:8006`

#### 5. **Risk Engine** ✅
- **URL**: http://localhost:8009
- **Status**: Operational
- **Features**: Real-time risk management
- **Test**: `curl http://localhost:8009`

#### 6. **Redis Cache** ✅
- **Port**: 6379
- **Status**: Running
- **Test**: `redis-cli ping`

## 🔴 Services Not Responding
- API Gateway (8000) - Import errors
- Market Scanner (8001) - Import errors
- Backtesting Engine (8004) - Import errors
- ML Framework (8005) - Import errors
- Notification Service (8007) - Import errors
- Data Pipeline (8008) - Import errors

## 📊 Test Commands (Run in WSL Terminal)

```bash
# Test AI Decision Engine
curl http://localhost:8002

# Test Position Management
curl http://localhost:8003

# Check active positions
curl http://localhost:8003/api/v1/positions

# Test Monitoring Service
curl http://localhost:8006/system/overview

# Test Risk Engine
curl http://localhost:8009/api/v1/risk/status

# Check Redis
redis-cli ping
```

## 🌐 Access from Windows Browser

Since you're using WSL2, you can access these URLs directly from your Windows browser:

1. **InfluxDB UI**: Open Chrome/Firefox and go to http://localhost:8086
2. **Login with**: 
   - Username: `admin`
   - Password: `adminpassword`
3. **View Trading Data**: Use the data explorer link above

## 📈 InfluxDB Data Explorer

To view trading metrics in InfluxDB:
1. Go to http://localhost:8086
2. Login with credentials above
3. Navigate to Data Explorer
4. Select bucket: `trading-data`
5. Query available metrics

## 🔧 Quick Fixes for Non-Working Services

The services that aren't working likely have import errors. To fix:

```bash
# Install missing dependencies
pip install structlog yfinance scikit-learn joblib psutil python-dotenv pydantic-settings

# Restart the system
pkill -f uvicorn
python3 /home/misu/live/ai-trading-system/run_system.py
```

## 💡 Current System Capabilities

With the working services, you can:
- Monitor system health (port 8006)
- Make AI-driven trading decisions (port 8002)
- Manage positions with zone strategies (port 8003)
- Apply risk management rules (port 8009)
- View real-time metrics in InfluxDB
- Cache data with Redis

The core trading engine components are operational!