"""
AI Decision Engine - The Cortex
Hierarchical AI decision-making system with multiple gates and validation layers.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import redis
import structlog
from enum import Enum
import uuid

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="AI Decision Engine - The Cortex",
    description="Hierarchical AI decision-making system for trading",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)

class DecisionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"

class GateLevel(str, Enum):
    SIGNAL_VALIDATION = "signal_validation"
    RISK_ASSESSMENT = "risk_assessment"
    PORTFOLIO_IMPACT = "portfolio_impact"
    MARKET_CONDITIONS = "market_conditions"
    FINAL_APPROVAL = "final_approval"

class DecisionRequest(BaseModel):
    symbol: str
    signal_type: DecisionType
    signal_strength: float
    price: float
    quantity: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class DecisionResponse(BaseModel):
    decision_id: str
    symbol: str
    decision: DecisionType
    confidence: float
    reasoning: List[str]
    gate_results: Dict[str, Dict[str, Any]]
    timestamp: datetime
    execution_priority: int

class HierarchicalGateSystem:
    """The Cortex - Hierarchical decision-making system."""
    
    def __init__(self):
        self.gates = {
            GateLevel.SIGNAL_VALIDATION: self.signal_validation_gate,
            GateLevel.RISK_ASSESSMENT: self.risk_assessment_gate,
            GateLevel.PORTFOLIO_IMPACT: self.portfolio_impact_gate,
            GateLevel.MARKET_CONDITIONS: self.market_conditions_gate,
            GateLevel.FINAL_APPROVAL: self.final_approval_gate
        }
    
    async def process_decision(self, request: DecisionRequest) -> DecisionResponse:
        """Process decision through all hierarchical gates."""
        decision_id = str(uuid.uuid4())
        gate_results = {}
        reasoning = []
        
        logger.info(f"Processing decision {decision_id} for {request.symbol}")
        
        # Process through each gate in sequence
        for gate_level, gate_function in self.gates.items():
            try:
                gate_result = await gate_function(request, gate_results)
                gate_results[gate_level.value] = gate_result
                
                if not gate_result['approved']:
                    # Gate rejected the decision
                    reasoning.append(f"Rejected at {gate_level.value}: {gate_result['reason']}")
                    return DecisionResponse(
                        decision_id=decision_id,
                        symbol=request.symbol,
                        decision=DecisionType.HOLD,
                        confidence=0.0,
                        reasoning=reasoning,
                        gate_results=gate_results,
                        timestamp=datetime.now(),
                        execution_priority=0
                    )
                else:
                    reasoning.append(f"Passed {gate_level.value}: {gate_result['reason']}")
                    
            except Exception as e:
                logger.error(f"Error in gate {gate_level.value}: {str(e)}")
                gate_results[gate_level.value] = {
                    'approved': False,
                    'reason': f"Gate error: {str(e)}",
                    'confidence': 0.0
                }
                reasoning.append(f"Error in {gate_level.value}: {str(e)}")
                return DecisionResponse(
                    decision_id=decision_id,
                    symbol=request.symbol,
                    decision=DecisionType.HOLD,
                    confidence=0.0,
                    reasoning=reasoning,
                    gate_results=gate_results,
                    timestamp=datetime.now(),
                    execution_priority=0
                )
        
        # All gates passed - calculate final decision
        final_confidence = self.calculate_final_confidence(gate_results)
        execution_priority = self.calculate_execution_priority(request, final_confidence)
        
        return DecisionResponse(
            decision_id=decision_id,
            symbol=request.symbol,
            decision=request.signal_type,
            confidence=final_confidence,
            reasoning=reasoning,
            gate_results=gate_results,
            timestamp=datetime.now(),
            execution_priority=execution_priority
        )
    
    async def signal_validation_gate(self, request: DecisionRequest, previous_gates: Dict) -> Dict:
        """Gate 1: Validate the incoming signal quality and consistency."""
        
        # Check signal strength
        if request.signal_strength < 0.3:
            return {
                'approved': False,
                'reason': f'Signal strength too low: {request.signal_strength}',
                'confidence': 0.0,
                'metrics': {'signal_strength': request.signal_strength}
            }
        
        # Check for conflicting signals (simulate)
        conflicting_signals = await self.check_conflicting_signals(request.symbol)
        if conflicting_signals > 2:
            return {
                'approved': False,
                'reason': f'Too many conflicting signals: {conflicting_signals}',
                'confidence': 0.0,
                'metrics': {'conflicting_signals': conflicting_signals}
            }
        
        # Signal validation passed
        confidence = min(request.signal_strength * 1.2, 1.0)
        return {
            'approved': True,
            'reason': 'Signal validation passed',
            'confidence': confidence,
            'metrics': {
                'signal_strength': request.signal_strength,
                'conflicting_signals': conflicting_signals
            }
        }
    
    async def risk_assessment_gate(self, request: DecisionRequest, previous_gates: Dict) -> Dict:
        """Gate 2: Assess risk parameters and position sizing."""
        
        # Get current portfolio risk
        portfolio_risk = await self.get_portfolio_risk()
        
        # Check if adding this position would exceed risk limits
        position_risk = self.calculate_position_risk(request)
        total_risk = portfolio_risk + position_risk
        
        if total_risk > 0.15:  # 15% max portfolio risk
            return {
                'approved': False,
                'reason': f'Risk limit exceeded: {total_risk:.2%}',
                'confidence': 0.0,
                'metrics': {
                    'portfolio_risk': portfolio_risk,
                    'position_risk': position_risk,
                    'total_risk': total_risk
                }
            }
        
        # Check volatility
        volatility = await self.get_symbol_volatility(request.symbol)
        if volatility > 0.5:  # 50% annualized volatility limit
            return {
                'approved': False,
                'reason': f'Volatility too high: {volatility:.2%}',
                'confidence': 0.0,
                'metrics': {'volatility': volatility}
            }
        
        # Risk assessment passed
        risk_confidence = 1.0 - (total_risk / 0.15)  # Higher confidence with lower risk
        return {
            'approved': True,
            'reason': 'Risk assessment passed',
            'confidence': risk_confidence,
            'metrics': {
                'portfolio_risk': portfolio_risk,
                'position_risk': position_risk,
                'total_risk': total_risk,
                'volatility': volatility
            }
        }
    
    async def portfolio_impact_gate(self, request: DecisionRequest, previous_gates: Dict) -> Dict:
        """Gate 3: Analyze impact on overall portfolio composition."""
        
        # Get current portfolio allocation
        portfolio_allocation = await self.get_portfolio_allocation()
        
        # Check sector concentration
        symbol_sector = await self.get_symbol_sector(request.symbol)
        current_sector_allocation = portfolio_allocation.get(symbol_sector, 0.0)
        
        if current_sector_allocation > 0.3:  # 30% max sector allocation
            return {
                'approved': False,
                'reason': f'Sector concentration too high: {current_sector_allocation:.2%}',
                'confidence': 0.0,
                'metrics': {
                    'sector': symbol_sector,
                    'sector_allocation': current_sector_allocation
                }
            }
        
        # Check correlation with existing positions
        correlation_risk = await self.calculate_correlation_risk(request.symbol)
        if correlation_risk > 0.8:
            return {
                'approved': False,
                'reason': f'High correlation with existing positions: {correlation_risk:.2f}',
                'confidence': 0.0,
                'metrics': {'correlation_risk': correlation_risk}
            }
        
        # Portfolio impact assessment passed
        diversification_benefit = 1.0 - correlation_risk
        return {
            'approved': True,
            'reason': 'Portfolio impact assessment passed',
            'confidence': diversification_benefit,
            'metrics': {
                'sector': symbol_sector,
                'sector_allocation': current_sector_allocation,
                'correlation_risk': correlation_risk,
                'diversification_benefit': diversification_benefit
            }
        }
    
    async def market_conditions_gate(self, request: DecisionRequest, previous_gates: Dict) -> Dict:
        """Gate 4: Analyze current market conditions and regime."""
        
        # Get market regime indicators
        market_regime = await self.get_market_regime()
        vix_level = await self.get_vix_level()
        
        # Check if market conditions are favorable for the signal type
        if request.signal_type in [DecisionType.BUY] and market_regime == 'bear_market':
            if vix_level > 30:  # High volatility in bear market
                return {
                    'approved': False,
                    'reason': f'Unfavorable market conditions: {market_regime}, VIX: {vix_level}',
                    'confidence': 0.0,
                    'metrics': {
                        'market_regime': market_regime,
                        'vix_level': vix_level
                    }
                }
        
        # Check market liquidity
        market_liquidity = await self.get_market_liquidity()
        if market_liquidity < 0.5:
            return {
                'approved': False,
                'reason': f'Low market liquidity: {market_liquidity}',
                'confidence': 0.0,
                'metrics': {'market_liquidity': market_liquidity}
            }
        
        # Market conditions assessment passed
        market_confidence = self.calculate_market_confidence(market_regime, vix_level, market_liquidity)
        return {
            'approved': True,
            'reason': 'Market conditions favorable',
            'confidence': market_confidence,
            'metrics': {
                'market_regime': market_regime,
                'vix_level': vix_level,
                'market_liquidity': market_liquidity
            }
        }
    
    async def final_approval_gate(self, request: DecisionRequest, previous_gates: Dict) -> Dict:
        """Gate 5: Final approval with executive override capability."""
        
        # Calculate aggregate confidence from all previous gates
        gate_confidences = [
            gate_result['confidence'] 
            for gate_result in previous_gates.values()
        ]
        
        avg_confidence = np.mean(gate_confidences)
        min_confidence = np.min(gate_confidences)
        
        # Require minimum confidence threshold
        if avg_confidence < 0.6 or min_confidence < 0.3:
            return {
                'approved': False,
                'reason': f'Insufficient confidence: avg={avg_confidence:.2f}, min={min_confidence:.2f}',
                'confidence': 0.0,
                'metrics': {
                    'avg_confidence': avg_confidence,
                    'min_confidence': min_confidence,
                    'gate_confidences': gate_confidences
                }
            }
        
        # Check for executive overrides or special conditions
        executive_override = await self.check_executive_override(request)
        
        # Final approval granted
        final_confidence = (avg_confidence + min_confidence) / 2
        return {
            'approved': True,
            'reason': 'Final approval granted',
            'confidence': final_confidence,
            'metrics': {
                'avg_confidence': avg_confidence,
                'min_confidence': min_confidence,
                'executive_override': executive_override,
                'final_confidence': final_confidence
            }
        }
    
    # Helper methods (simplified implementations for demo)
    async def check_conflicting_signals(self, symbol: str) -> int:
        """Check for conflicting signals."""
        return np.random.randint(0, 4)  # Simulate 0-3 conflicting signals
    
    async def get_portfolio_risk(self) -> float:
        """Get current portfolio risk."""
        return np.random.uniform(0.05, 0.12)  # Simulate 5-12% portfolio risk
    
    def calculate_position_risk(self, request: DecisionRequest) -> float:
        """Calculate risk of the proposed position."""
        return np.random.uniform(0.01, 0.05)  # Simulate 1-5% position risk
    
    async def get_symbol_volatility(self, symbol: str) -> float:
        """Get symbol volatility."""
        return np.random.uniform(0.15, 0.45)  # Simulate 15-45% volatility
    
    async def get_portfolio_allocation(self) -> Dict[str, float]:
        """Get current portfolio sector allocation."""
        return {
            'Technology': 0.25,
            'Healthcare': 0.15,
            'Finance': 0.20,
            'Consumer': 0.18,
            'Energy': 0.12,
            'Other': 0.10
        }
    
    async def get_symbol_sector(self, symbol: str) -> str:
        """Get symbol sector."""
        sector_map = {
            'AAPL': 'Technology', 'GOOGL': 'Technology', 'MSFT': 'Technology',
            'JNJ': 'Healthcare', 'PFE': 'Healthcare',
            'JPM': 'Finance', 'BAC': 'Finance',
            'XOM': 'Energy', 'CVX': 'Energy'
        }
        return sector_map.get(symbol, 'Other')
    
    async def calculate_correlation_risk(self, symbol: str) -> float:
        """Calculate correlation risk with existing positions."""
        return np.random.uniform(0.2, 0.9)  # Simulate correlation
    
    async def get_market_regime(self) -> str:
        """Get current market regime."""
        regimes = ['bull_market', 'bear_market', 'sideways', 'volatile']
        return np.random.choice(regimes)
    
    async def get_vix_level(self) -> float:
        """Get VIX level."""
        return np.random.uniform(12, 35)  # Simulate VIX 12-35
    
    async def get_market_liquidity(self) -> float:
        """Get market liquidity indicator."""
        return np.random.uniform(0.3, 1.0)  # Simulate liquidity
    
    def calculate_market_confidence(self, regime: str, vix: float, liquidity: float) -> float:
        """Calculate market confidence score."""
        base_confidence = 0.7
        
        if regime == 'bull_market':
            base_confidence += 0.2
        elif regime == 'bear_market':
            base_confidence -= 0.2
        
        if vix < 20:
            base_confidence += 0.1
        elif vix > 30:
            base_confidence -= 0.1
        
        base_confidence += (liquidity - 0.5) * 0.2
        
        return max(0.0, min(1.0, base_confidence))
    
    async def check_executive_override(self, request: DecisionRequest) -> bool:
        """Check for executive override conditions."""
        return False  # No overrides in demo
    
    def calculate_final_confidence(self, gate_results: Dict) -> float:
        """Calculate final confidence score."""
        confidences = [result['confidence'] for result in gate_results.values()]
        return np.mean(confidences)
    
    def calculate_execution_priority(self, request: DecisionRequest, confidence: float) -> int:
        """Calculate execution priority (1-10, 10 being highest)."""
        base_priority = int(confidence * 10)
        
        # Adjust based on signal strength
        if request.signal_strength > 0.8:
            base_priority += 1
        
        # Adjust based on signal type
        if request.signal_type in [DecisionType.SELL, DecisionType.CLOSE]:
            base_priority += 1  # Risk management has higher priority
        
        return min(10, max(1, base_priority))

# Initialize the decision engine
decision_engine = HierarchicalGateSystem()

@app.get("/")
async def root():
    return {
        "service": "ai-decision-engine",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "gates_active": len(decision_engine.gates)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ai-decision-engine",
        "timestamp": datetime.now().isoformat(),
        "redis_connected": redis_client.ping()
    }

@app.post("/analyze", response_model=DecisionResponse)
async def analyze_decision(request: DecisionRequest):
    """Analyze a trading decision through the hierarchical gate system."""
    try:
        decision = await decision_engine.process_decision(request)
        
        # Store decision in cache for audit trail
        redis_client.setex(
            f"decision:{decision.decision_id}",
            3600,  # 1 hour
            decision.json()
        )
        
        return decision
        
    except Exception as e:
        logger.error(f"Error analyzing decision: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing decision: {str(e)}")

@app.get("/decision/{decision_id}")
async def get_decision(decision_id: str):
    """Retrieve a previous decision by ID."""
    try:
        decision_data = redis_client.get(f"decision:{decision_id}")
        if not decision_data:
            raise HTTPException(status_code=404, detail="Decision not found")
        
        return json.loads(decision_data)
        
    except Exception as e:
        logger.error(f"Error retrieving decision: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving decision: {str(e)}")

@app.get("/gates/status")
async def get_gates_status():
    """Get status of all decision gates."""
    return {
        "gates": [
            {
                "level": gate_level.value,
                "name": gate_level.value.replace('_', ' ').title(),
                "status": "active",
                "description": f"Gate {i+1}: {gate_level.value.replace('_', ' ').title()}"
            }
            for i, gate_level in enumerate(decision_engine.gates.keys())
        ],
        "total_gates": len(decision_engine.gates),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
