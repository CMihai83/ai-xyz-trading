#!/usr/bin/env python3
"""
Trade Audit Logger for AI-XYZ System
====================================

Comprehensive debugging system that logs every step of trade decision making
to enable full audit trail and logic verification.
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import structlog

class TradeAuditLogger:
    """Comprehensive trade audit logger for debugging trade logic"""
    
    def __init__(self, log_file: str = None):
        # Use environment variable or fallback to /app/logs for container
        if log_file is None:
            import os
            base_path = os.environ.get('AIXYZ_LOG_PATH', '/app/logs')
            if not os.path.exists(base_path):
                base_path = '/root/ai_xyz'
            if not os.path.exists(base_path):
                base_path = '.'
            log_file = os.path.join(base_path, 'trade_audit.log')
        self.log_file = log_file
        self.logger = structlog.get_logger(__name__)
        self.current_trade_id = None
        self.trade_data = {}
        
    def start_trade_audit(self, symbol: str, action: str) -> str:
        """Start a new trade audit session"""
        self.current_trade_id = f"{symbol}_{action}_{int(time.time())}"
        self.trade_data = {
            'trade_id': self.current_trade_id,
            'symbol': symbol,
            'action': action,
            'timestamp': datetime.now().isoformat(),
            'steps': []
        }
        
        self.log_step("TRADE_START", {
            'trade_id': self.current_trade_id,
            'symbol': symbol,
            'action': action
        })
        
        return self.current_trade_id
    
    def log_step(self, step_name: str, data: Dict[str, Any]):
        """Log a single step in the trade decision process"""
        if not self.current_trade_id:
            self.current_trade_id = f"unknown_{int(time.time())}"
            
        step_data = {
            'step': step_name,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        # Add to current trade data
        if 'steps' not in self.trade_data:
            self.trade_data['steps'] = []
        self.trade_data['steps'].append(step_data)
        
        # Log to console with formatting
        self.logger.info(f"🔍 AUDIT [{step_name}]", **data)
        
        # Log to file
        with open(self.log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} | {self.current_trade_id} | {step_name} | {json.dumps(data, default=str)}\n")
    
    def log_market_data(self, symbol: str, data: Dict[str, Any]):
        """Log market data analysis"""
        self.log_step("MARKET_DATA", {
            'symbol': symbol,
            'current_price': data.get('current_price'),
            'volume': data.get('volume'),
            'volatility': data.get('volatility'),
            'trend': data.get('trend')
        })
    
    def log_delta_calculation(self, symbol: str, timeframe_deltas: Dict[str, float], final_delta: Dict[str, float]):
        """Log delta calculation process"""
        self.log_step("DELTA_CALCULATION", {
            'symbol': symbol,
            'timeframe_deltas': {tf: f"{delta*100:.1f}%" for tf, delta in timeframe_deltas.items()},
            'final_delta_pct': f"{final_delta['percentage']*100:.1f}%",
            'final_delta_abs': f"${final_delta['absolute']:.4f}",
            'selected_timeframe': final_delta.get('best_timeframe', 'unknown')
        })
    
    def log_fibonacci_parameters(self, params: Dict[str, Any]):
        """Log Fibonacci parameter calculation"""
        self.log_step("FIBONACCI_PARAMS", {
            'leverage': params.get('leverage'),
            'max_steps': params.get('max_averaging_steps'),
            'safe_to_trade': params.get('safe_to_trade'),
            'total_margin': params.get('total_capital_needed'),
            'initial_position_size': params.get('initial_position_size')
        })
    
    def log_averaging_thresholds(self, thresholds: List[float], delta_used: float):
        """Log averaging threshold calculation"""
        self.log_step("AVERAGING_THRESHOLDS", {
            'delta_used_pct': f"{delta_used*100:.1f}%",
            'threshold_count': len(thresholds),
            'thresholds_pct': [f"{t*100:.1f}%" for t in thresholds],
            'first_step_trigger': f"{thresholds[0]*100:.1f}%" if thresholds else "N/A"
        })
    
    def log_position_decision(self, decision: str, reason: str, data: Dict[str, Any]):
        """Log final position decision"""
        self.log_step("POSITION_DECISION", {
            'decision': decision,
            'reason': reason,
            'position_data': data
        })
    
    def log_averaging_trigger(self, current_upnl: float, threshold: float, step_number: int, 
                            entry_price: float, current_price: float):
        """Log averaging step trigger"""
        self.log_step("AVERAGING_TRIGGER", {
            'step_number': step_number,
            'current_upnl_pct': f"{(current_upnl/100)*100:.2f}%",
            'threshold_pct': f"{threshold*100:.2f}%",
            'entry_price': f"${entry_price:.4f}",
            'current_price': f"${current_price:.4f}",
            'price_change_pct': f"{((current_price-entry_price)/entry_price)*100:.2f}%",
            'should_trigger': current_upnl <= threshold
        })
    
    def log_risk_check(self, risk_data: Dict[str, Any]):
        """Log risk management checks"""
        self.log_step("RISK_CHECK", risk_data)
    
    def log_order_execution(self, order_data: Dict[str, Any]):
        """Log order execution details"""
        self.log_step("ORDER_EXECUTION", order_data)
    
    def finalize_trade_audit(self, final_result: str, summary: Dict[str, Any]):
        """Finalize and save complete trade audit"""
        self.log_step("TRADE_COMPLETE", {
            'final_result': final_result,
            'summary': summary
        })
        
        # Save complete audit to separate file
        audit_file = f"/app/audits/{self.current_trade_id}_complete.json"
        try:
            import os
            os.makedirs("/app/audits", exist_ok=True)
            with open(audit_file, 'w') as f:
                json.dump(self.trade_data, f, indent=2, default=str)
            self.logger.info(f"📁 Complete audit saved: {audit_file}")
        except Exception as e:
            self.logger.error(f"Failed to save audit: {e}")
        
        # Reset for next trade
        self.current_trade_id = None
        self.trade_data = {}

# Global audit logger instance
audit_logger = TradeAuditLogger()