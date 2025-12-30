# 🎯 AI Trading System - Operations Guide

## 📊 System Overview
The AI Trading System is a sophisticated automated trading platform that uses machine learning and advanced algorithms to make trading decisions on the Bitget exchange.

## 🚀 How to Operate the System

### 1. System Status Check
```bash
# Check all running services
curl http://localhost:8000/api/v1/health

# Monitor specific services
- API Gateway: http://localhost:8000
- Market Scanner: http://localhost:8001  
- AI Decision Engine: http://localhost:8002
- Position Management: http://localhost:8003
- Risk Engine: http://localhost:8009
```

### 2. Trading Operations

#### A. Start Automated Trading
1. **Enable Trading Mode**
   ```bash
   # Via API
   curl -X POST http://localhost:8000/api/v1/trading/start \
     -H "Content-Type: application/json" \
     -d '{"mode": "live", "initial_capital": 10000}'
   ```

2. **Configure Trading Parameters**
   - Risk per trade: 1-2% of capital
   - Max positions: 5-10 concurrent
   - Stop loss: 2-5%
   - Take profit: 5-15%

#### B. Manual Trading Controls
```bash
# Place manual order
curl -X POST http://localhost:8000/api/v1/orders/create \
  -d '{"symbol": "BTC/USDT", "side": "buy", "amount": 0.001}'

# Check positions
curl http://localhost:8000/api/v1/positions

# Close position
curl -X POST http://localhost:8000/api/v1/positions/{id}/close
```

### 3. Monitoring & Analytics

#### A. Real-Time Monitoring
- **InfluxDB Dashboard**: http://localhost:8086
  - Username: admin
  - Password: adminpassword
  - View metrics: trading-data bucket

#### B. Performance Metrics
```bash
# Get performance stats
curl http://localhost:8000/api/v1/analytics/performance

# Get daily P&L
curl http://localhost:8000/api/v1/analytics/pnl/daily
```

### 4. AI Decision Engine Control

#### Configure AI Parameters
```bash
# Adjust risk tolerance
curl -X PUT http://localhost:8002/api/v1/config \
  -d '{"risk_tolerance": "conservative"}'

# Set market regime
curl -X PUT http://localhost:8002/api/v1/market-regime \
  -d '{"regime": "volatile"}'
```

#### Decision Gates (5-Level System)
1. **Signal Gate**: Technical indicators alignment
2. **Risk Gate**: Position size and exposure check  
3. **Portfolio Gate**: Diversification requirements
4. **Market Gate**: Overall market conditions
5. **Executive Gate**: Final approval/veto

### 5. Risk Management

#### Set Risk Limits
```bash
# Configure risk parameters
curl -X PUT http://localhost:8009/api/v1/risk/limits \
  -d '{
    "max_drawdown": 0.20,
    "max_position_size": 0.10,
    "max_leverage": 2.0,
    "daily_loss_limit": 0.05
  }'
```

### 6. Strategy Management

#### A. Active Strategies
- **Mean Reversion**: RSI-based oversold/overbought
- **Momentum**: Trend following with MA crossovers
- **Zone Trading**: Accumulation/distribution zones
- **Volatility**: Bollinger Bands breakouts

#### B. Strategy Control
```bash
# Enable/disable strategies
curl -X POST http://localhost:8000/api/v1/strategies/momentum/enable
curl -X POST http://localhost:8000/api/v1/strategies/mean-reversion/disable

# Adjust strategy parameters
curl -X PUT http://localhost:8000/api/v1/strategies/zone-trading/config \
  -d '{"accumulation_threshold": 0.95, "distribution_threshold": 1.05}'
```

### 7. Emergency Controls

#### Stop All Trading
```bash
# Emergency stop
curl -X POST http://localhost:8000/api/v1/emergency/stop

# Close all positions
curl -X POST http://localhost:8000/api/v1/positions/close-all

# Disable automated trading
curl -X POST http://localhost:8000/api/v1/trading/disable
```

### 8. Data & Backtesting

#### Run Backtest
```bash
# Test strategy on historical data
curl -X POST http://localhost:8004/api/v1/backtest/run \
  -d '{
    "strategy": "momentum",
    "symbol": "BTC/USDT",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 10000
  }'
```

### 9. System Maintenance

#### Health Checks
```bash
# Check all services health
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  echo "Service on port $port:"
  curl -s http://localhost:$port/health || echo "Not responding"
done
```

#### Restart Services
```bash
# Restart specific service
docker-compose restart api-gateway

# Restart all services
docker-compose restart

# View logs
docker-compose logs -f api-gateway
```

## 📈 Trading Workflow

### Automated Trading Flow:
1. **Market Scanner** → Continuously scans markets for opportunities
2. **Signal Generation** → Creates buy/sell signals based on indicators
3. **AI Decision Engine** → Validates signals through 5-gate system
4. **Risk Engine** → Checks risk limits and position sizing
5. **Position Management** → Executes trades and manages positions
6. **Monitoring** → Tracks performance and adjusts parameters

### Manual Intervention Points:
- Override AI decisions
- Adjust risk parameters
- Close positions manually
- Enable/disable strategies
- Set trading limits

## 🔐 Security & Safety

### API Authentication
All API calls should include authentication:
```bash
# Get JWT token
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -d '{"username": "admin", "password": "your_password"}' | jq -r '.token')

# Use token in requests
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/positions
```

### Bitget Integration
The system is configured with your Bitget API credentials:
- API Key: bg_f483546274ffb2bfa567328e98dba6c0
- Configured for live trading
- Rate limiting enabled

## 🎯 Best Practices

1. **Start Small**: Begin with paper trading or minimal capital
2. **Monitor Actively**: Check system regularly during initial operation
3. **Set Limits**: Always configure stop-loss and risk limits
4. **Review Performance**: Analyze daily P&L and adjust strategies
5. **Backup Data**: Regular backups of trading data and configurations
6. **Test Changes**: Use backtesting before applying strategy changes

## 📞 Support & Troubleshooting

### Common Issues:
1. **Service not responding**: Check Docker containers status
2. **No trades executing**: Verify AI decision gates and risk limits
3. **Connection errors**: Check network and API credentials
4. **High CPU usage**: Adjust market scanner frequency

### Logs Location:
- Application logs: `docker-compose logs [service-name]`
- Trading logs: InfluxDB → trading-data bucket
- Error logs: Check individual service logs

## 🚨 Important Notes

- This system trades with REAL MONEY on Bitget
- Always set appropriate risk limits
- Monitor system during market volatility
- Keep API credentials secure
- Regular system updates recommended

---

For detailed API documentation, visit: http://localhost:8000/docs