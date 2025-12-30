"""
Risk Engine - Real-time risk management and calculation.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import asyncio
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Risk Engine",
    description="Real-time risk management and calculation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RiskMetrics(BaseModel):
    portfolio_var: float
    portfolio_cvar: float
    sharpe_ratio: float
    max_drawdown: float
    beta: float
    correlation_risk: float
    concentration_risk: float
    liquidity_risk: float

class PositionRisk(BaseModel):
    symbol: str
    position_size: float
    var_1d: float
    var_5d: float
    beta: float
    volatility: float
    correlation_with_portfolio: float

class RiskEngine:
    """Real-time risk management engine."""
    
    def __init__(self):
        self.risk_limits = {
            'max_portfolio_var': 0.05,  # 5% daily VaR
            'max_position_size': 0.1,   # 10% of portfolio
            'max_sector_concentration': 0.3,  # 30% per sector
            'max_correlation': 0.8,     # 80% correlation limit
            'min_liquidity_score': 0.5  # Minimum liquidity score
        }
        self.portfolio_data = {}
        self.market_data = {}
    
    async def calculate_portfolio_risk(self, positions: List[Dict]) -> RiskMetrics:
        """Calculate comprehensive portfolio risk metrics."""
        if not positions:
            return RiskMetrics(
                portfolio_var=0.0,
                portfolio_cvar=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                beta=0.0,
                correlation_risk=0.0,
                concentration_risk=0.0,
                liquidity_risk=0.0
            )
        
        # Calculate portfolio weights
        total_value = sum(pos['quantity'] * pos['current_price'] for pos in positions)
        weights = np.array([pos['quantity'] * pos['current_price'] / total_value for pos in positions])
        
        # Get historical returns for each position
        returns_matrix = await self.get_returns_matrix([pos['symbol'] for pos in positions])
        
        if returns_matrix is None or returns_matrix.empty:
            # Return default metrics if no data
            return RiskMetrics(
                portfolio_var=0.02,
                portfolio_cvar=0.03,
                sharpe_ratio=0.5,
                max_drawdown=0.1,
                beta=1.0,
                correlation_risk=0.3,
                concentration_risk=self.calculate_concentration_risk(weights),
                liquidity_risk=0.2
            )
        
        # Calculate portfolio returns
        portfolio_returns = (returns_matrix * weights).sum(axis=1)
        
        # Value at Risk (VaR) - 95% confidence
        portfolio_var = np.percentile(portfolio_returns, 5)
        
        # Conditional Value at Risk (CVaR)
        portfolio_cvar = portfolio_returns[portfolio_returns <= portfolio_var].mean()
        
        # Sharpe ratio
        sharpe_ratio = portfolio_returns.mean() / portfolio_returns.std() * np.sqrt(252)
        
        # Maximum drawdown
        cumulative_returns = (1 + portfolio_returns).cumprod()
        running_max = cumulative_returns.cummax()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Portfolio beta (vs market)
        market_returns = await self.get_market_returns()
        if market_returns is not None and len(market_returns) == len(portfolio_returns):
            covariance = np.cov(portfolio_returns, market_returns)[0, 1]
            market_variance = np.var(market_returns)
            beta = covariance / market_variance if market_variance > 0 else 1.0
        else:
            beta = 1.0
        
        # Correlation risk
        correlation_matrix = returns_matrix.corr()
        avg_correlation = correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, k=1)].mean()
        correlation_risk = max(0, avg_correlation)
        
        # Concentration risk
        concentration_risk = self.calculate_concentration_risk(weights)
        
        # Liquidity risk
        liquidity_risk = await self.calculate_liquidity_risk([pos['symbol'] for pos in positions])
        
        return RiskMetrics(
            portfolio_var=abs(portfolio_var),
            portfolio_cvar=abs(portfolio_cvar),
            sharpe_ratio=sharpe_ratio,
            max_drawdown=abs(max_drawdown),
            beta=beta,
            correlation_risk=correlation_risk,
            concentration_risk=concentration_risk,
            liquidity_risk=liquidity_risk
        )
    
    async def calculate_position_risk(self, symbol: str, position_size: float, 
                                    portfolio_positions: List[Dict]) -> PositionRisk:
        """Calculate risk metrics for a specific position."""
        # Get historical returns
        returns = await self.get_symbol_returns(symbol)
        
        if returns is None or len(returns) < 30:
            # Default values if no data
            return PositionRisk(
                symbol=symbol,
                position_size=position_size,
                var_1d=0.02,
                var_5d=0.05,
                beta=1.0,
                volatility=0.2,
                correlation_with_portfolio=0.3
            )
        
        # 1-day VaR (95% confidence)
        var_1d = abs(np.percentile(returns, 5))
        
        # 5-day VaR (assuming independence)
        var_5d = var_1d * np.sqrt(5)
        
        # Volatility (annualized)
        volatility = returns.std() * np.sqrt(252)
        
        # Beta vs market
        market_returns = await self.get_market_returns()
        if market_returns is not None and len(market_returns) == len(returns):
            covariance = np.cov(returns, market_returns)[0, 1]
            market_variance = np.var(market_returns)
            beta = covariance / market_variance if market_variance > 0 else 1.0
        else:
            beta = 1.0
        
        # Correlation with portfolio
        portfolio_returns = await self.get_portfolio_returns(portfolio_positions)
        if portfolio_returns is not None and len(portfolio_returns) == len(returns):
            correlation = np.corrcoef(returns, portfolio_returns)[0, 1]
        else:
            correlation = 0.3
        
        return PositionRisk(
            symbol=symbol,
            position_size=position_size,
            var_1d=var_1d,
            var_5d=var_5d,
            beta=beta,
            volatility=volatility,
            correlation_with_portfolio=correlation
        )
    
    def calculate_concentration_risk(self, weights: np.ndarray) -> float:
        """Calculate concentration risk using Herfindahl index."""
        return np.sum(weights ** 2)
    
    async def calculate_liquidity_risk(self, symbols: List[str]) -> float:
        """Calculate portfolio liquidity risk."""
        # Simplified liquidity risk calculation
        # In practice, this would use actual volume and bid-ask spread data
        liquidity_scores = []
        
        for symbol in symbols:
            # Simulate liquidity score based on symbol characteristics
            if symbol in ['AAPL', 'GOOGL', 'MSFT', 'AMZN']:
                score = 0.9  # High liquidity
            elif symbol in ['SPY', 'QQQ', 'IWM']:
                score = 0.95  # Very high liquidity
            else:
                score = 0.6  # Medium liquidity
            
            liquidity_scores.append(score)
        
        # Return average liquidity risk (1 - liquidity score)
        avg_liquidity = np.mean(liquidity_scores)
        return 1 - avg_liquidity
    
    async def get_returns_matrix(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """Get historical returns matrix for symbols."""
        # Simulate returns data
        # In practice, this would fetch real historical data
        np.random.seed(42)
        
        returns_data = {}
        for symbol in symbols:
            # Generate correlated returns
            returns = np.random.normal(0.001, 0.02, 252)  # Daily returns for 1 year
            returns_data[symbol] = returns
        
        return pd.DataFrame(returns_data)
    
    async def get_symbol_returns(self, symbol: str) -> Optional[np.ndarray]:
        """Get historical returns for a symbol."""
        # Simulate returns
        np.random.seed(hash(symbol) % 1000)
        return np.random.normal(0.001, 0.02, 252)
    
    async def get_market_returns(self) -> Optional[np.ndarray]:
        """Get market returns (e.g., S&P 500)."""
        # Simulate market returns
        np.random.seed(123)
        return np.random.normal(0.0008, 0.015, 252)
    
    async def get_portfolio_returns(self, positions: List[Dict]) -> Optional[np.ndarray]:
        """Calculate portfolio returns from positions."""
        if not positions:
            return None
        
        # Get returns for each position
        all_returns = []
        weights = []
        
        total_value = sum(pos['quantity'] * pos['current_price'] for pos in positions)
        
        for pos in positions:
            returns = await self.get_symbol_returns(pos['symbol'])
            if returns is not None:
                weight = pos['quantity'] * pos['current_price'] / total_value
                all_returns.append(returns)
                weights.append(weight)
        
        if not all_returns:
            return None
        
        # Calculate weighted portfolio returns
        returns_matrix = np.array(all_returns).T
        weights_array = np.array(weights)
        portfolio_returns = (returns_matrix * weights_array).sum(axis=1)
        
        return portfolio_returns
    
    async def check_risk_limits(self, risk_metrics: RiskMetrics) -> Dict[str, Any]:
        """Check if risk metrics exceed defined limits."""
        violations = []
        
        if risk_metrics.portfolio_var > self.risk_limits['max_portfolio_var']:
            violations.append({
                'type': 'portfolio_var',
                'current': risk_metrics.portfolio_var,
                'limit': self.risk_limits['max_portfolio_var'],
                'severity': 'high'
            })
        
        if risk_metrics.concentration_risk > self.risk_limits['max_sector_concentration']:
            violations.append({
                'type': 'concentration_risk',
                'current': risk_metrics.concentration_risk,
                'limit': self.risk_limits['max_sector_concentration'],
                'severity': 'medium'
            })
        
        if risk_metrics.correlation_risk > self.risk_limits['max_correlation']:
            violations.append({
                'type': 'correlation_risk',
                'current': risk_metrics.correlation_risk,
                'limit': self.risk_limits['max_correlation'],
                'severity': 'medium'
            })
        
        return {
            'violations': violations,
            'total_violations': len(violations),
            'risk_status': 'high' if any(v['severity'] == 'high' for v in violations) else 'normal',
            'timestamp': datetime.now().isoformat()
        }
    
    def update_risk_limits(self, new_limits: Dict[str, float]):
        """Update risk limits."""
        self.risk_limits.update(new_limits)

# Initialize risk engine
risk_engine = RiskEngine()

@app.get("/")
async def root():
    return {
        "service": "risk-engine",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "risk_limits": risk_engine.risk_limits
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "risk-engine",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/portfolio/risk", response_model=RiskMetrics)
async def calculate_portfolio_risk(positions: List[Dict]):
    """Calculate portfolio risk metrics."""
    try:
        risk_metrics = await risk_engine.calculate_portfolio_risk(positions)
        return risk_metrics
    except Exception as e:
        logger.error(f"Error calculating portfolio risk: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio risk: {str(e)}")

@app.post("/position/risk", response_model=PositionRisk)
async def calculate_position_risk(symbol: str, position_size: float, portfolio_positions: List[Dict]):
    """Calculate position risk metrics."""
    try:
        position_risk = await risk_engine.calculate_position_risk(symbol, position_size, portfolio_positions)
        return position_risk
    except Exception as e:
        logger.error(f"Error calculating position risk: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating position risk: {str(e)}")

@app.post("/risk/check")
async def check_risk_limits(risk_metrics: RiskMetrics):
    """Check risk metrics against limits."""
    try:
        violations = await risk_engine.check_risk_limits(risk_metrics)
        return violations
    except Exception as e:
        logger.error(f"Error checking risk limits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error checking risk limits: {str(e)}")

@app.get("/risk/limits")
async def get_risk_limits():
    """Get current risk limits."""
    return {
        "limits": risk_engine.risk_limits,
        "timestamp": datetime.now().isoformat()
    }

@app.put("/risk/limits")
async def update_risk_limits(new_limits: Dict[str, float]):
    """Update risk limits."""
    try:
        risk_engine.update_risk_limits(new_limits)
        return {
            "message": "Risk limits updated successfully",
            "new_limits": risk_engine.risk_limits,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error updating risk limits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating risk limits: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
