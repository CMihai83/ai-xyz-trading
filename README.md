# 🤖 AI-XYZ Trading System v2.0

## Production-Ready Automated Cryptocurrency Trading Platform

### 🚀 Quick Start

```bash
# Start the complete system
./restart_aixyz_system.sh

# Check system status
./status.sh

# Monitor live trading
tail -f /tmp/aixyz_main.log
```

### 📊 System Overview

**AI-XYZ** is a sophisticated automated trading system for Bitget exchange featuring:
- **Zone-based position management** with 5 states (Neutral, Averaging, Surplus, Profit, StopLoss)
- **Fibonacci-based averaging** with adaptive thresholds
- **Surplus dump mechanism** for optimized profit-taking
- **Multi-timeframe analysis** across 6 timeframes (1m to 1d)
- **Dynamic position sizing** ($5 per position, max 10 concurrent)

### 🏗️ Current Architecture (Actual Running System)

```mermaid
graph TB
    BITGET[Bitget Exchange] <--> CONNECTOR[exchange_connector.py<br/>PID: 3421373]
    CONNECTOR --> JSON[(exchange_data.json)]
    
    MAIN[aixyz_continuous_profit_system.py<br/>PID: 3421331] --> SCANNER[Market Scanner]
    SCANNER --> MAIN
    
    MAIN --> ZONES[Zone State Machine]
    ZONES --> FIBONACCI[Fibonacci Service]
    
    ZONES --> SURPLUS[automatic_surplus_executor.py<br/>PID: 3421365]
    
    MAIN --> LOGS[/tmp/aixyz_main.log]
    SURPLUS --> LOGS2[/var/log/surplus_executor.log]
```

### 📁 Active System Structure

```
/root/ai_xyz/
├── 🟢 Active Core (3 services, 17 total files)
│   ├── aixyz_continuous_profit_system.py    # Main trading engine
│   ├── automatic_surplus_executor.py        # Surplus dump service  
│   ├── exchange_connector.py                # Exchange sync service
│   ├── position_sizing_config.py            # Position calculations
│   ├── enhanced_market_scanner.py           # Market analysis
│   ├── simple_vsa_scanner.py               # Volume spread analysis
│   └── core/
│       ├── adaptive_fibonacci_system.py     # Averaging logic
│       ├── zone_state_machine.py           # State transitions
│       └── [4 more active modules]
│
└── 🔴 Inactive (201 unused files - 93% of codebase)
    ├── test_*.py (66 test files)
    ├── services/* (40 microservice files - not running)
    └── [95 other unused files]
```

### ⚙️ System Configuration

#### Capital Management
| Parameter | Value | Description |
|-----------|-------|-------------|
| Position Size | $5 | Per position allocation |
| Max Positions | 10 | Global cap (even with >$50) |
| Min Notional | $6.50 | After leverage |
| Capital Split | 70/30 | Trading/Reserve |

#### Zone Configuration
| Zone | UPNL Range | Action |
|------|------------|--------|
| Stop Loss | ≤ -90% | Emergency close |
| Averaging | ≤ -25% | Execute DCA |
| Neutral | -25% to +5% | Monitor only |
| Surplus/Profit | ≥ +5% | Take profits |

### 📈 Current Performance

```
System Status: ✅ RUNNING
Active Positions: 5-7
Balance: ~$28-30 USDT
Active Processes: 3
Active Files: 17/216 (7.9%)
CPU Usage: 2-5%
Memory: ~500MB
```

### 🛠️ System Commands

```bash
# Core Operations
./restart_aixyz_system.sh    # Full restart
./status.sh                   # Check status
./stop_aixyz_system.sh        # Stop all

# Monitoring
tail -f /tmp/aixyz_main.log                    # Main logs
tail -f /var/log/surplus_executor.log          # Surplus logs
tail -f /var/log/exchange_connector.log        # Exchange sync

# Debugging
ps aux | grep aixyz           # Check processes
cat exchange_data.json        # View positions
```

### 📊 Key Features

#### Fibonacci Averaging System
- Dynamically calculates safe averaging levels
- Uses historical delta analysis
- Adapts to market volatility
- Maximum 5-8 averaging steps

#### Surplus Dump Mechanism
- Triggers when averaged positions recover
- Dumps 50% of surplus at profit
- Minimum threshold: $0.10
- Automatic execution every 30 seconds

#### Position Lifecycle
1. **Market Scanner** finds opportunity (score > 0.3)
2. **Position Opening** with Fibonacci parameters
3. **Zone Monitoring** every 5 seconds
4. **Averaging** if UPNL ≤ -25%
5. **Surplus Dump** if recovered with averaging steps
6. **Profit Taking** or Stop Loss

### 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| System not starting | `pkill -f aixyz && rm *.pid && ./restart_aixyz_system.sh` |
| Positions not syncing | Check `/var/log/exchange_connector.log` |
| Averaging not executing | Verify UPNL ≤ -25% and margin available |
| High CPU usage | Restart with `./restart_aixyz_system.sh` |

### 📝 Documentation

- **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)** - Complete technical details
- **[UNUSED_FILES_LIST.md](UNUSED_FILES_LIST.md)** - 201 unused files list
- **[CARDINAL_RULES_TRADING_SYSTEM.md](CARDINAL_RULES_TRADING_SYSTEM.md)** - Core trading rules

### 🚨 Safety Features

- **Stop Loss**: Auto-close at -90% UPNL
- **Position Cap**: Maximum 10 positions enforced
- **Reserve Capital**: 30% always kept safe
- **Exchange Sync**: Updates every 10 seconds
- **Error Recovery**: Automatic retry with exponential backoff

### 📊 System Metrics

| Metric | Value |
|--------|-------|
| Total Python Files | 216 |
| Active Files | 17 (7.9%) |
| Unused Files | 201 (93.1%) |
| Running Services | 3 |
| Update Frequency | 5-30 seconds |
| Log Rotation | Daily |

### 🔮 Roadmap

- [ ] Clean up 201 unused files
- [ ] Implement ML market regime detection
- [ ] Add multi-exchange support
- [ ] Build real-time web dashboard
- [ ] Add Telegram bot notifications
- [ ] Create comprehensive backtesting

---

**Version**: 2.0.0  
**Updated**: 2025-09-17 20:22 UTC  
**Status**: 🟢 PRODUCTION ACTIVE

### Frontend Application
- **React Dashboard** (Port 3000) - Real-time trading interface

## 🔑 Bitget Integration

The system is pre-configured with Bitget API credentials for live trading:

```
BITGET_API_KEY=bg_f483546274ffb2bfa567328e98dba6c0
BITGET_API_SECRET=387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0
BITGET_API_PASSPHRASE=2609Luiza
```

### Live Trading Features
- ✅ Real-time position monitoring
- ✅ Automated trade execution
- ✅ Risk management and stop-losses
- ✅ Portfolio rebalancing
- ✅ Performance tracking

## 📊 Key Features

### AI Decision Engine - The Cortex
- **5-Gate Hierarchical System**: Signal validation, risk assessment, portfolio impact, market regime, executive override
- **Market Regime Detection**: Bull/bear/sideways/volatile market identification
- **Confidence Scoring**: Every decision includes confidence metrics
- **Audit Trail**: Complete decision history and reasoning

### Market Scanner - The Observatory
- **Real-time Analysis**: 15+ technical indicators (RSI, MACD, Bollinger Bands, etc.)
- **Signal Generation**: Buy/sell signals with confidence scoring
- **Multi-timeframe**: 1m, 5m, 15m, 1h, 4h, 1d analysis
- **Custom Indicators**: Plugin architecture for custom indicators

### Position Management - Zone-Based Strategy
- **Accumulation Zones**: Strategic position building
- **Distribution Zones**: Profit-taking strategies
- **Dynamic Stop-Losses**: Trailing and zone-based stops
- **Portfolio Balancing**: Automatic rebalancing
- **Adaptive Fibonacci Averaging**: Automatic K coefficient calculation for safe averaging
- **Surplus Dump Logic**: Intelligent profit-taking at 85% and 50% of peak UPNL
- **Zone State Machine**: Neutral, Averaging, Surplus Dump, Profit Taking, Stop Loss zones
- **Liquidation Safety**: All averaging steps maintain >10% distance from liquidation

### Backtesting Engine - The Chronosphere
- **Multiple Strategies**: RSI mean reversion, MA crossover, Bollinger Bands, momentum
- **Walk-Forward Analysis**: Robust strategy validation
- **Performance Metrics**: Sharpe ratio, max drawdown, win rate, profit factor
- **Monte Carlo Simulation**: Risk assessment

### ML Framework - Model Marketplace
- **Multiple Algorithms**: Random Forest, Gradient Boosting, SVM, Logistic Regression
- **Feature Engineering**: 8+ technical features with automatic generation
- **Model Validation**: Cross-validation and performance tracking
- **Prediction API**: Real-time ML predictions

### Risk Engine - Real-time Risk Management
- **Portfolio VaR**: Value at Risk calculation
- **Position Sizing**: Dynamic position sizing based on risk
- **Correlation Analysis**: Portfolio correlation monitoring
- **Liquidity Risk**: Real-time liquidity assessment

### Monitoring Service - The Vital Signs
- **System Metrics**: CPU, memory, disk, network monitoring
- **Service Health**: Real-time health checks for all services
- **Alert Rules**: Configurable alerting system
- **Performance Tracking**: Response times and error rates

## 🔧 Configuration

### Environment Variables
```bash
# Bitget API Configuration
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_api_secret
BITGET_API_PASSPHRASE=your_passphrase

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Database Configuration
DATABASE_URL=postgresql://user:pass@localhost/trading_db
```

### Risk Limits
```python
risk_limits = {
    'max_portfolio_var': 0.05,      # 5% daily VaR
    'max_position_size': 0.1,       # 10% of portfolio
    'max_sector_concentration': 0.3, # 30% per sector
    'max_correlation': 0.8,         # 80% correlation limit
    'min_liquidity_score': 0.5      # Minimum liquidity score
}
```

## 📈 Trading Strategies

### Built-in Strategies
1. **RSI Mean Reversion** - Buy oversold, sell overbought
2. **Moving Average Crossover** - Golden/death cross signals
3. **Bollinger Bands** - Band touch and mean reversion
4. **Momentum** - Trend following strategy

### Custom Strategy Development
```python
async def custom_strategy(data, parameters, initial_capital):
    # Your strategy logic here
    return {
        'final_portfolio_value': portfolio_value,
        'trades': trades,
        'performance_data': performance_data
    }
```

## 🚀 Deployment

### Local Development
```bash
python start_system.py
```

### Docker Deployment
```bash
docker-compose up -d
```

### Kubernetes Deployment
```bash
kubectl apply -f infrastructure/kubernetes/
```

### Cloud Deployment
```bash
# AWS
terraform apply -var-file="aws.tfvars"

# Azure
terraform apply -var-file="azure.tfvars"

# GCP
terraform apply -var-file="gcp.tfvars"
```

## 📊 Performance Specifications

- **Latency**: <50ms for ML inference, <100ms for trading decisions
- **Throughput**: 1000+ market data updates/second
- **Scalability**: Supports 100+ concurrent users
- **Availability**: 99.9% uptime with auto-recovery
- **Data**: Multi-year historical backtesting capability

## 🔍 Monitoring & Observability

### Health Checks
```bash
# Check all services
curl http://localhost:8000/health

# Individual service health
curl http://localhost:8001/health  # Market Scanner
curl http://localhost:8002/health  # AI Decision Engine
```

### Metrics
- System metrics (CPU, memory, disk)
- Trading metrics (P&L, positions, trades)
- Performance metrics (latency, throughput)
- Business metrics (win rate, Sharpe ratio)

### Alerts
- System alerts (high CPU, memory)
- Trading alerts (large losses, risk limits)
- Performance alerts (high latency, errors)

## 🧪 Testing

### Unit Tests
```bash
pytest services/*/tests/
```

### Integration Tests
```bash
pytest tests/integration/
```

### Load Tests
```bash
python tests/load_test.py
```

## 📚 API Documentation

### API Gateway
- **Base URL**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **OpenAPI Spec**: http://localhost:8000/openapi.json

### Key Endpoints
```
GET  /health                    # System health
GET  /positions                 # Current positions
POST /orders                    # Place order
GET  /signals                   # Trading signals
GET  /backtest                  # Run backtest
POST /ml/predict               # ML prediction
GET  /risk/portfolio           # Portfolio risk
```

## 🔐 Security

- JWT authentication
- API rate limiting
- Input validation
- Secure credential storage
- Audit logging
- Network security

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests
4. Submit pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

- **Documentation**: See `/docs` folder
- **Issues**: GitHub Issues
- **Discord**: Trading System Community
- **Email**: support@trading-system.com

---

**⚠️ Risk Disclaimer**: This software is for educational and research purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results. Use at your own risk.
