#!/usr/bin/env python3
"""
Futures Risk Engine with Dynamic Margin Management
Handles risk calculation, margin allocation, and liquidation protection for futures trading.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiohttp
import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import numpy as np

# Import futures configuration
import sys
sys.path.append('/home/ubuntu/ai-trading-system-futures')
from futures_symbols_config import get_symbol_config, calculate_margin_required

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Futures Risk Engine", version="2.0.0")

class FuturesRiskEngine:
    """Advanced risk management for futures trading with dynamic margin allocation."""
    
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=1)
        self.risk_limits = {
            'max_margin_usage': 0.8,  # 80% max margin usage
            'liquidation_buffer': 0.15,  # 15% buffer from liquidation
            'max_leverage_per_symbol': 50,
            'max_positions_per_symbol': 2,  # Long and short
            'max_total_positions': 10,
            'max_correlation_exposure': 0.6,  # 60% max correlated exposure
            'daily_loss_limit': 0.1,  # 10% daily loss limit
            'drawdown_limit': 0.2  # 20% max drawdown
        }
        
        # Symbol correlations (simplified - in production, calculate dynamically)
        self.symbol_correlations = {
            'BTCUSDT': {'ETHUSDT': 0.8, 'BNBUSDT': 0.6, 'ADAUSDT': 0.7},
            'ETHUSDT': {'BTCUSDT': 0.8, 'BNBUSDT': 0.7, 'LINKUSDT': 0.6},
            'BNBUSDT': {'BTCUSDT': 0.6, 'ETHUSDT': 0.7, 'ADAUSDT': 0.5}
        }
        
    async def calculate_portfolio_risk(self, positions: List[Dict], account_balance: float) -> Dict:
        """Calculate comprehensive portfolio risk metrics."""
        if not positions:
            return {
                'total_margin_used': 0,
                'margin_usage_percent': 0,
                'liquidation_risk': 'low',
                'correlation_risk': 0,
                'var_1d': 0,
                'max_drawdown_risk': 0,
                'risk_score': 0
            }
        
        total_margin_used = 0
        total_notional = 0
        position_values = {}
        
        # Calculate basic metrics
        for position in positions:
            if float(position.get('total', 0)) != 0:  # Only active positions
                symbol = position['symbol']
                size = abs(float(position['total']))
                mark_price = float(position['markPrice'])
                leverage = float(position.get('leverage', 1))
                
                notional_value = size * mark_price
                margin_used = notional_value / leverage
                
                total_margin_used += margin_used
                total_notional += notional_value
                position_values[symbol] = {
                    'notional': notional_value,
                    'margin': margin_used,
                    'leverage': leverage,
                    'side': position.get('holdSide', 'long')
                }
        
        # Calculate margin usage
        margin_usage_percent = total_margin_used / account_balance if account_balance > 0 else 0
        
        # Calculate liquidation risk
        liquidation_risk = self._calculate_liquidation_risk(positions, account_balance)
        
        # Calculate correlation risk
        correlation_risk = self._calculate_correlation_risk(position_values)
        
        # Calculate VaR (simplified)
        var_1d = self._calculate_var(position_values)
        
        # Calculate max drawdown risk
        max_drawdown_risk = self._calculate_drawdown_risk(account_balance)
        
        # Overall risk score (0-100)
        risk_score = self._calculate_risk_score(
            margin_usage_percent, liquidation_risk, correlation_risk, var_1d
        )
        
        return {
            'total_margin_used': total_margin_used,
            'total_notional': total_notional,
            'margin_usage_percent': margin_usage_percent,
            'liquidation_risk': liquidation_risk,
            'correlation_risk': correlation_risk,
            'var_1d': var_1d,
            'max_drawdown_risk': max_drawdown_risk,
            'risk_score': risk_score,
            'risk_level': self._get_risk_level(risk_score),
            'recommendations': self._generate_risk_recommendations(risk_score, margin_usage_percent)
        }
    
    def _calculate_liquidation_risk(self, positions: List[Dict], account_balance: float) -> str:
        """Calculate liquidation risk level."""
        if not positions:
            return 'low'
        
        min_margin_ratio = float('inf')
        
        for position in positions:
            if float(position.get('total', 0)) != 0:
                unrealized_pnl = float(position.get('unrealizedPL', 0))
                margin_used = float(position.get('margin', 0))
                
                if margin_used > 0:
                    current_margin_ratio = (margin_used + unrealized_pnl) / margin_used
                    min_margin_ratio = min(min_margin_ratio, current_margin_ratio)
        
        if min_margin_ratio == float('inf'):
            return 'low'
        elif min_margin_ratio > 0.5:
            return 'low'
        elif min_margin_ratio > 0.2:
            return 'medium'
        else:
            return 'high'
    
    def _calculate_correlation_risk(self, position_values: Dict) -> float:
        """Calculate portfolio correlation risk."""
        if len(position_values) < 2:
            return 0.0
        
        total_correlation_exposure = 0.0
        total_notional = sum(pos['notional'] for pos in position_values.values())
        
        symbols = list(position_values.keys())
        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                correlation = self.symbol_correlations.get(symbol1, {}).get(symbol2, 0.0)
                if correlation > 0.5:  # High correlation
                    exposure1 = position_values[symbol1]['notional'] / total_notional
                    exposure2 = position_values[symbol2]['notional'] / total_notional
                    total_correlation_exposure += correlation * exposure1 * exposure2
        
        return min(total_correlation_exposure, 1.0)
    
    def _calculate_var(self, position_values: Dict, confidence_level: float = 0.95) -> float:
        """Calculate 1-day Value at Risk (simplified)."""
        if not position_values:
            return 0.0
        
        # Simplified VaR calculation using historical volatility estimates
        symbol_volatilities = {
            'BTCUSDT': 0.04,  # 4% daily volatility
            'ETHUSDT': 0.05,  # 5% daily volatility
            'BNBUSDT': 0.06,  # 6% daily volatility
            'ADAUSDT': 0.08,  # 8% daily volatility
            'SOLUSDT': 0.10,  # 10% daily volatility
        }
        
        total_var = 0.0
        for symbol, position in position_values.items():
            volatility = symbol_volatilities.get(symbol, 0.06)  # Default 6%
            position_var = position['notional'] * volatility * 1.645  # 95% confidence
            total_var += position_var ** 2
        
        return np.sqrt(total_var)
    
    def _calculate_drawdown_risk(self, account_balance: float) -> float:
        """Calculate maximum drawdown risk."""
        # Get historical balance data (simplified)
        historical_balances = self._get_historical_balances()
        
        if len(historical_balances) < 2:
            return 0.0
        
        peak = historical_balances[0]
        max_drawdown = 0.0
        
        for balance in historical_balances:
            if balance > peak:
                peak = balance
            drawdown = (peak - balance) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def _get_historical_balances(self) -> List[float]:
        """Get historical account balances (simplified)."""
        # In production, this would fetch from database
        return [10000, 10200, 9800, 10500, 10100, 9900, 10300]
    
    def _calculate_risk_score(self, margin_usage: float, liquidation_risk: str, 
                            correlation_risk: float, var: float) -> float:
        """Calculate overall risk score (0-100)."""
        score = 0.0
        
        # Margin usage component (0-40 points)
        score += min(margin_usage * 50, 40)
        
        # Liquidation risk component (0-30 points)
        liquidation_scores = {'low': 5, 'medium': 15, 'high': 30}
        score += liquidation_scores.get(liquidation_risk, 15)
        
        # Correlation risk component (0-20 points)
        score += correlation_risk * 20
        
        # VaR component (0-10 points)
        score += min(var / 1000, 1.0) * 10  # Normalize VaR
        
        return min(score, 100)
    
    def _get_risk_level(self, risk_score: float) -> str:
        """Get risk level based on risk score."""
        if risk_score < 30:
            return 'low'
        elif risk_score < 60:
            return 'medium'
        elif risk_score < 80:
            return 'high'
        else:
            return 'critical'
    
    def _generate_risk_recommendations(self, risk_score: float, margin_usage: float) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []
        
        if margin_usage > 0.8:
            recommendations.append("Reduce margin usage below 80%")
        
        if risk_score > 70:
            recommendations.append("Consider closing some positions to reduce risk")
        
        if margin_usage > 0.6:
            recommendations.append("Consider reducing leverage on existing positions")
        
        if risk_score > 50:
            recommendations.append("Monitor positions closely for liquidation risk")
        
        if not recommendations:
            recommendations.append("Risk levels are within acceptable limits")
        
        return recommendations
    
    async def validate_new_position(self, symbol: str, side: str, quantity: float, 
                                  leverage: int, current_positions: List[Dict], 
                                  account_balance: float) -> Dict:
        """Validate if a new position can be opened safely."""
        config = get_symbol_config(symbol)
        if not config:
            return {'allowed': False, 'reason': 'Symbol configuration not found'}
        
        # Check leverage limits
        if leverage > config['max_leverage']:
            return {'allowed': False, 'reason': f'Leverage {leverage} exceeds maximum {config["max_leverage"]}'}
        
        # Calculate margin required for new position
        current_price = 50000.0  # This should come from real market data
        margin_info = calculate_margin_required(symbol, quantity, current_price, leverage)
        
        # Calculate current portfolio risk
        current_risk = await self.calculate_portfolio_risk(current_positions, account_balance)
        
        # Check if new position would exceed margin limits
        new_margin_usage = (current_risk['total_margin_used'] + margin_info['initial_margin']) / account_balance
        
        if new_margin_usage > self.risk_limits['max_margin_usage']:
            return {
                'allowed': False, 
                'reason': f'New position would exceed margin limit ({new_margin_usage:.1%} > {self.risk_limits["max_margin_usage"]:.1%})'
            }
        
        # Check position limits
        symbol_positions = [p for p in current_positions if p['symbol'] == symbol and float(p.get('total', 0)) != 0]
        if len(symbol_positions) >= self.risk_limits['max_positions_per_symbol']:
            return {'allowed': False, 'reason': f'Maximum positions per symbol ({self.risk_limits["max_positions_per_symbol"]}) reached'}
        
        total_positions = len([p for p in current_positions if float(p.get('total', 0)) != 0])
        if total_positions >= self.risk_limits['max_total_positions']:
            return {'allowed': False, 'reason': f'Maximum total positions ({self.risk_limits["max_total_positions"]}) reached'}
        
        # Calculate risk score with new position
        simulated_positions = current_positions + [{
            'symbol': symbol,
            'total': str(quantity),
            'markPrice': str(current_price),
            'leverage': str(leverage),
            'holdSide': side,
            'margin': str(margin_info['initial_margin']),
            'unrealizedPL': '0'
        }]
        
        new_risk = await self.calculate_portfolio_risk(simulated_positions, account_balance)
        
        if new_risk['risk_score'] > 80:
            return {'allowed': False, 'reason': f'New position would create critical risk level ({new_risk["risk_score"]:.1f})'}
        
        return {
            'allowed': True,
            'margin_required': margin_info['initial_margin'],
            'new_margin_usage': new_margin_usage,
            'new_risk_score': new_risk['risk_score'],
            'recommendations': new_risk['recommendations']
        }
    
    async def calculate_optimal_leverage(self, symbol: str, signal_strength: float, 
                                       current_positions: List[Dict], account_balance: float) -> int:
        """Calculate optimal leverage based on risk management."""
        config = get_symbol_config(symbol)
        if not config:
            return 1
        
        # Base leverage from configuration
        base_leverage = config['default_leverage']
        max_leverage = config['max_leverage']
        
        # Calculate current portfolio risk
        current_risk = await self.calculate_portfolio_risk(current_positions, account_balance)
        
        # Adjust leverage based on current risk
        risk_adjustment = 1.0
        if current_risk['risk_score'] > 60:
            risk_adjustment = 0.5  # Reduce leverage if high risk
        elif current_risk['risk_score'] < 30:
            risk_adjustment = 1.2  # Increase leverage if low risk
        
        # Adjust based on signal strength
        signal_adjustment = 0.5 + (signal_strength * 0.5)  # 0.5 to 1.0 multiplier
        
        # Calculate optimal leverage
        optimal_leverage = int(base_leverage * risk_adjustment * signal_adjustment)
        
        # Ensure within limits
        optimal_leverage = max(1, min(optimal_leverage, max_leverage))
        
        return optimal_leverage
    
    async def monitor_liquidation_risk(self) -> Dict:
        """Monitor positions for liquidation risk and suggest actions."""
        # This would be called periodically to monitor all positions
        # For now, return a placeholder
        return {
            'status': 'monitoring',
            'high_risk_positions': [],
            'actions_taken': [],
            'timestamp': datetime.now().isoformat()
        }

# Initialize risk engine
risk_engine = FuturesRiskEngine()

# API Models
class PositionValidationRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    leverage: int
    current_positions: List[Dict]
    account_balance: float

class LeverageOptimizationRequest(BaseModel):
    symbol: str
    signal_strength: float
    current_positions: List[Dict]
    account_balance: float

# API Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "futures-risk-engine", "version": "2.0.0"}

@app.post("/risk/portfolio")
async def calculate_portfolio_risk_endpoint(positions: List[Dict], account_balance: float):
    """Calculate comprehensive portfolio risk metrics."""
    return await risk_engine.calculate_portfolio_risk(positions, account_balance)

@app.post("/risk/validate-position")
async def validate_position(request: PositionValidationRequest):
    """Validate if a new position can be opened safely."""
    return await risk_engine.validate_new_position(
        request.symbol,
        request.side,
        request.quantity,
        request.leverage,
        request.current_positions,
        request.account_balance
    )

@app.post("/risk/optimal-leverage")
async def calculate_optimal_leverage_endpoint(request: LeverageOptimizationRequest):
    """Calculate optimal leverage for a position."""
    optimal_leverage = await risk_engine.calculate_optimal_leverage(
        request.symbol,
        request.signal_strength,
        request.current_positions,
        request.account_balance
    )
    return {"optimal_leverage": optimal_leverage}

@app.get("/risk/limits")
async def get_risk_limits():
    """Get current risk management limits."""
    return risk_engine.risk_limits

@app.post("/risk/limits")
async def update_risk_limits(new_limits: Dict):
    """Update risk management limits."""
    risk_engine.risk_limits.update(new_limits)
    return {"status": "updated", "limits": risk_engine.risk_limits}

@app.get("/risk/monitor")
async def monitor_liquidation_risk():
    """Monitor positions for liquidation risk."""
    return await risk_engine.monitor_liquidation_risk()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
