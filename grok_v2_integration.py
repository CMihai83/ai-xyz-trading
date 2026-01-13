#!/usr/bin/env python3
"""
Grok V2 Integration Module
Integrates all 14 Grok recommendations into the AI-XYZ trading system.

This module provides a unified interface to all enhanced components.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

# Import all Grok V2 modules
from trade_results_tracker import get_trade_tracker, TradeResultsTracker
from grok_v2_bayesian_correction import get_bayesian_model, BayesianCorrectionModel
from grok_v2_volatility_regime_hmm import get_volatility_hmm, VolatilityRegimeHMM, VolatilityRegime
from grok_v2_redis_pool import get_redis_pool, RedisPool
from grok_v2_var_integration import get_var_calculator, get_var_limiter, VaRCalculator, VaRPositionLimiter
from grok_v2_websocket_events import get_websocket_client, BitgetWebSocketClient
from grok_v2_stress_testing import get_stress_tester, StressTester
from grok_v2_ensemble_exit import get_exit_ensemble, ExitEnsemble, ExitSignal
from grok_v2_online_cssi_learning import get_online_cssi_learner, OnlineCSSILearner
from grok_v2_anomaly_detection import get_anomaly_detector, get_trading_anomaly_monitor, AnomalyDetector
from grok_v2_graceful_degradation import get_graceful_degradation, GracefulDegradation, DegradationLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GrokV2Config:
    """Configuration for Grok V2 modules"""
    # Module enable flags
    enable_bayesian: bool = True
    enable_hmm: bool = True
    enable_redis_pool: bool = True
    enable_var: bool = True
    enable_websocket: bool = False  # Disabled by default (requires setup)
    enable_stress_testing: bool = True
    enable_ensemble_exit: bool = True
    enable_online_learning: bool = True
    enable_anomaly_detection: bool = True
    enable_graceful_degradation: bool = True

    # Bayesian model settings
    bayesian_min_observations: int = 10

    # HMM settings
    hmm_volatility_window: int = 20

    # VaR settings
    var_confidence: float = 0.95
    max_portfolio_var_pct: float = 0.10
    max_position_var_pct: float = 0.05

    # Ensemble settings
    ensemble_exit_threshold: float = 0.65

    # Anomaly detection settings
    anomaly_z_threshold: float = 3.0

    # Degradation settings
    component_failure_threshold: int = 5


class GrokV2Integration:
    """
    Main integration class for all Grok V2 enhancements.

    Provides a unified interface to:
    1. Trade result tracking
    2. Bayesian correction probability
    3. Volatility regime detection (HMM)
    4. Redis connection pooling
    5. VaR position limits
    6. WebSocket events (optional)
    7. Stress testing
    8. Ensemble exit model
    9. Online CSSI learning
    10. Anomaly detection
    11. Graceful degradation
    """

    VERSION = "2.0.0"

    def __init__(self, config: GrokV2Config = None):
        self.config = config or GrokV2Config()
        self.initialized = False

        # Module instances (lazy loaded)
        self._trade_tracker: Optional[TradeResultsTracker] = None
        self._bayesian: Optional[BayesianCorrectionModel] = None
        self._hmm: Optional[VolatilityRegimeHMM] = None
        self._redis: Optional[RedisPool] = None
        self._var_calculator: Optional[VaRCalculator] = None
        self._var_limiter: Optional[VaRPositionLimiter] = None
        self._websocket: Optional[BitgetWebSocketClient] = None
        self._stress_tester: Optional[StressTester] = None
        self._ensemble: Optional[ExitEnsemble] = None
        self._cssi_learner: Optional[OnlineCSSILearner] = None
        self._anomaly_detector: Optional[AnomalyDetector] = None
        self._degradation: Optional[GracefulDegradation] = None

        # Auto-initialize all modules
        self.initialize()

    def initialize(self):
        """Initialize all enabled modules"""
        logger.info(f"Initializing Grok V2 Integration v{self.VERSION}")

        # Initialize graceful degradation first
        if self.config.enable_graceful_degradation:
            self._degradation = get_graceful_degradation()
            self._degradation.register_component('bayesian_model')
            self._degradation.register_component('hmm_model')
            self._degradation.register_component('redis')
            self._degradation.register_component('var_calculator')
            self._degradation.register_component('ensemble_exit')
            self._degradation.register_component('cssi_learner')
            logger.info("✅ Graceful degradation initialized")

        # Trade tracker (always enabled)
        self._trade_tracker = get_trade_tracker()
        logger.info("✅ Trade result tracker initialized")

        # Initialize other modules
        if self.config.enable_bayesian:
            self._bayesian = get_bayesian_model()
            logger.info("✅ Bayesian correction model initialized")

        if self.config.enable_hmm:
            self._hmm = get_volatility_hmm()
            logger.info("✅ Volatility regime HMM initialized")

        if self.config.enable_redis_pool:
            self._redis = get_redis_pool()
            logger.info(f"✅ Redis pool initialized (connected: {self._redis.is_connected()})")

        if self.config.enable_var:
            self._var_calculator = get_var_calculator()
            self._var_limiter = get_var_limiter()
            logger.info("✅ VaR integration initialized")

        if self.config.enable_stress_testing:
            self._stress_tester = get_stress_tester()
            logger.info("✅ Stress testing module initialized")

        if self.config.enable_ensemble_exit:
            self._ensemble = get_exit_ensemble()
            logger.info("✅ Ensemble exit model initialized")

        if self.config.enable_online_learning:
            self._cssi_learner = get_online_cssi_learner()
            logger.info("✅ Online CSSI learner initialized")

        if self.config.enable_anomaly_detection:
            self._anomaly_detector = get_anomaly_detector()
            logger.info("✅ Anomaly detection initialized")

        self.initialized = True
        logger.info(f"Grok V2 Integration initialized successfully")

    # ==================== Trade Tracking ====================

    def record_trade_result(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        entry_time: str,
        contracts: float,
        leverage: float,
        margin_used: float,
        realized_pnl: float,
        exit_reason: str,
        averaging_steps: int = 0,
        peak_upnl: float = 0.0
    ):
        """Record a completed trade result"""
        return self._trade_tracker.record_trade(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            contracts=contracts,
            leverage=leverage,
            margin_used=margin_used,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason,
            averaging_steps=averaging_steps,
            peak_upnl=peak_upnl
        )

    def get_profit_factor_metrics(self) -> Dict:
        """Get profit factor and related metrics"""
        return self._trade_tracker.get_summary()

    # ==================== Bayesian Correction ====================

    def get_correction_probability(self, symbol: str, drawdown_pct: float) -> Dict:
        """Get Bayesian correction probability"""
        if not self.config.enable_bayesian:
            return {'probability': 0.5, 'confidence': 0.0, 'source': 'disabled'}

        try:
            prob, confidence = self._bayesian.get_correction_probability(symbol, drawdown_pct)
            return {
                'probability': prob,
                'confidence': confidence,
                'source': 'bayesian'
            }
        except Exception as e:
            logger.error(f"Bayesian model error: {e}")
            return {'probability': 0.5, 'confidence': 0.0, 'source': 'fallback'}

    def record_correction_outcome(
        self,
        symbol: str,
        drawdown_pct: float,
        did_correct: bool,
        correction_time_hours: float = 0
    ):
        """Record correction outcome for learning"""
        if self.config.enable_bayesian:
            self._bayesian.record_correction_event(
                symbol, drawdown_pct, did_correct, correction_time_hours
            )

        if self.config.enable_online_learning:
            self._cssi_learner.update({
                'drawdown_pct': drawdown_pct,
                'symbol': symbol
            }, did_correct, correction_time_hours)

    # ==================== Volatility Regime ====================

    def get_volatility_regime(self, volatility: float = None, symbol: str = None) -> Dict:
        """Get current volatility regime"""
        if not self.config.enable_hmm:
            return {'regime': 'NORMAL_VOL', 'factors': {}}

        try:
            if volatility is not None:
                state = self._hmm.update(volatility, symbol)
            else:
                state = self._hmm.get_regime(symbol)

            factors = self._hmm.get_regime_factor(symbol)

            return {
                'regime': state.regime.value,
                'probability': state.probability,
                'duration': state.regime_duration,
                'factors': factors
            }
        except Exception as e:
            logger.error(f"HMM error: {e}")
            return {'regime': 'NORMAL_VOL', 'factors': {}}

    # ==================== VaR Position Limits ====================

    def check_var_position_limit(
        self,
        symbol: str,
        position_size: float,
        portfolio_value: float
    ) -> Dict:
        """Check if position is within VaR limits"""
        if not self.config.enable_var:
            return {'allowed': True, 'reason': 'VaR disabled'}

        try:
            allowed, reason = self._var_limiter.check_position_allowed(
                symbol, position_size, portfolio_value
            )
            max_size = self._var_limiter.get_max_position_size(symbol, portfolio_value)

            return {
                'allowed': allowed,
                'reason': reason,
                'max_position_size': max_size,
                'requested_size': position_size
            }
        except Exception as e:
            logger.error(f"VaR check error: {e}")
            return {'allowed': True, 'reason': 'VaR check failed, allowing'}

    # ==================== Ensemble Exit Decision ====================

    def get_exit_recommendation(self, features: Dict) -> Dict:
        """Get ensemble exit recommendation"""
        if not self.config.enable_ensemble_exit:
            return {'signal': 'HOLD', 'confidence': 0.0}

        try:
            prediction = self._ensemble.predict(features)

            return {
                'signal': prediction.signal.value,
                'confidence': prediction.confidence,
                'exit_probability': prediction.exit_probability,
                'model_votes': prediction.model_votes,
                'reasons': prediction.reasons,
                'should_exit': prediction.exit_probability > self.config.ensemble_exit_threshold
            }
        except Exception as e:
            logger.error(f"Ensemble exit error: {e}")
            return {'signal': 'HOLD', 'confidence': 0.0, 'should_exit': False}

    # ==================== Stress Testing ====================

    def run_stress_test(
        self,
        positions: List[Dict],
        portfolio_value: float,
        scenario: str = 'flash_crash_2021'
    ) -> Dict:
        """Run stress test on portfolio"""
        if not self.config.enable_stress_testing:
            return {'error': 'Stress testing disabled'}

        try:
            result = self._stress_tester.run_stress_test(
                positions, portfolio_value, scenario
            )
            return {
                'scenario': result.scenario_name,
                'max_drawdown_pct': result.max_drawdown_pct,
                'positions_liquidated': result.positions_liquidated,
                'margin_call': result.margin_call_triggered,
                'risk_score': result.risk_score
            }
        except Exception as e:
            logger.error(f"Stress test error: {e}")
            return {'error': str(e)}

    # ==================== Anomaly Detection ====================

    def check_anomaly(self, metric_name: str, value: float) -> Optional[Dict]:
        """Check for anomaly in metric"""
        if not self.config.enable_anomaly_detection or not self._anomaly_detector:
            return None

        try:
            anomaly = self._anomaly_detector.check(metric_name, value)
            if anomaly:
                return {
                    'metric': anomaly.metric_name,
                    'value': anomaly.value,
                    'z_score': anomaly.z_score,
                    'severity': anomaly.severity,
                    'description': anomaly.description
                }
            return None
        except Exception as e:
            logger.error(f"Anomaly detection error: {e}")
            return None

    # ==================== Feature Availability ====================

    def is_feature_available(self, feature: str) -> bool:
        """Check if feature is available at current degradation level"""
        if not self.config.enable_graceful_degradation:
            return True

        return self._degradation.is_feature_available(feature)

    def get_system_health(self) -> Dict:
        """Get overall system health status"""
        if not self.config.enable_graceful_degradation:
            return {'level': 'normal', 'healthy': True}

        return self._degradation.get_status()

    # ==================== Unified Dashboard ====================

    def get_dashboard(self) -> Dict:
        """Get unified dashboard of all modules"""
        dashboard = {
            'version': self.VERSION,
            'timestamp': datetime.now().isoformat(),
            'modules': {}
        }

        # Trade metrics
        dashboard['modules']['trade_tracker'] = {
            'enabled': True,
            'metrics': self._trade_tracker.get_summary() if self._trade_tracker else {}
        }

        # Bayesian model
        if self.config.enable_bayesian and self._bayesian:
            dashboard['modules']['bayesian'] = {
                'enabled': True,
                'global_coefficients': self._bayesian.global_coeffs.tolist()
            }

        # HMM
        if self.config.enable_hmm and self._hmm:
            regime = self._hmm.get_regime()
            dashboard['modules']['hmm'] = {
                'enabled': True,
                'current_regime': regime.regime.value,
                'probability': regime.probability
            }

        # VaR
        if self.config.enable_var:
            dashboard['modules']['var'] = {
                'enabled': True,
                'max_portfolio_var': self.config.max_portfolio_var_pct,
                'max_position_var': self.config.max_position_var_pct
            }

        # Ensemble
        if self.config.enable_ensemble_exit and self._ensemble:
            dashboard['modules']['ensemble_exit'] = {
                'enabled': True,
                'accuracy': self._ensemble.get_accuracy(),
                'weights': self._ensemble.weights
            }

        # CSSI learner
        if self.config.enable_online_learning and self._cssi_learner:
            dashboard['modules']['cssi_learner'] = {
                'enabled': True,
                'updates': self._cssi_learner.update_count,
                'accuracy': self._cssi_learner.get_accuracy()
            }

        # Anomaly detection
        if self.config.enable_anomaly_detection and self._anomaly_detector:
            summary = self._anomaly_detector.get_anomaly_summary()
            dashboard['modules']['anomaly_detection'] = {
                'enabled': True,
                'total_anomalies': summary.get('total', 0)
            }

        # Degradation
        if self.config.enable_graceful_degradation and self._degradation:
            status = self._degradation.get_status()
            dashboard['modules']['graceful_degradation'] = {
                'enabled': True,
                'level': status['degradation_level'],
                'health_pct': status['health_percentage']
            }

        return dashboard

    def print_dashboard(self):
        """Print unified dashboard"""
        dashboard = self.get_dashboard()

        print("\n" + "=" * 70)
        print(f"🚀 GROK V2 INTEGRATION DASHBOARD v{self.VERSION}")
        print("=" * 70)

        # Trade metrics
        metrics = dashboard['modules'].get('trade_tracker', {}).get('metrics', {})
        print(f"\n📊 TRADING PERFORMANCE")
        print(f"   Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"   Profit Factor: {metrics.get('profit_factor', 0):.3f}")
        print(f"   Total Trades: {metrics.get('total_trades', 0)}")
        print(f"   Net P&L: ${metrics.get('net_pnl', 0):.2f}")

        # Module status
        print(f"\n📦 MODULE STATUS")
        for module, info in dashboard['modules'].items():
            status = "✅" if info.get('enabled') else "❌"
            extra = ""

            if module == 'hmm' and 'current_regime' in info:
                extra = f" ({info['current_regime']})"
            elif module == 'ensemble_exit' and 'accuracy' in info:
                extra = f" (acc: {info['accuracy']:.1%})"
            elif module == 'graceful_degradation':
                extra = f" ({info['level']})"

            print(f"   {status} {module}{extra}")

        print("\n" + "=" * 70)


# Singleton
_integration: Optional[GrokV2Integration] = None

def get_grok_v2_integration(config: GrokV2Config = None) -> GrokV2Integration:
    """Get singleton Grok V2 integration"""
    global _integration
    if _integration is None:
        _integration = GrokV2Integration(config)
        _integration.initialize()
    return _integration


if __name__ == "__main__":
    # Demo
    print("=" * 70)
    print("GROK V2 INTEGRATION TEST")
    print("=" * 70)

    # Create with custom config
    config = GrokV2Config(
        enable_websocket=False,  # Skip WebSocket for demo
    )

    integration = GrokV2Integration(config)
    integration.initialize()

    # Test trade recording
    print("\n📝 Recording test trade...")
    integration.record_trade_result(
        symbol="BTC/USDT:USDT",
        side="buy",
        entry_price=42000,
        exit_price=43000,
        entry_time="2026-01-11T10:00:00",
        contracts=0.1,
        leverage=10,
        margin_used=420,
        realized_pnl=100.0,
        exit_reason="profit_taking",
        averaging_steps=0,
        peak_upnl=120.0
    )

    # Test correction probability
    print("\n📈 Testing Bayesian correction probability...")
    corr_prob = integration.get_correction_probability("BTC/USDT:USDT", -25.0)
    print(f"   P(correction | -25% drawdown) = {corr_prob['probability']:.1%}")

    # Test volatility regime
    print("\n📊 Testing volatility regime...")
    regime = integration.get_volatility_regime(volatility=45.0)
    print(f"   Current regime: {regime['regime']}")

    # Test exit recommendation
    print("\n🎯 Testing exit recommendation...")
    exit_rec = integration.get_exit_recommendation({
        'symbol': 'BTC/USDT:USDT',
        'pnl_pct': 8.0,
        'holding_hours': 12,
        'volatility': 35,
        'momentum': 0.01,
        'current_price': 43000,
        'entry_price': 42000,
        'zone': 'PROFIT_TAKING',
        'peak_distance_pct': 5
    })
    print(f"   Signal: {exit_rec['signal']}")
    print(f"   Should Exit: {exit_rec.get('should_exit', False)}")

    # Test VaR check
    print("\n💰 Testing VaR position limit...")
    var_check = integration.check_var_position_limit(
        "BTC/USDT:USDT",
        position_size=5000,
        portfolio_value=50000
    )
    print(f"   Allowed: {var_check['allowed']}")
    print(f"   Max Size: ${var_check.get('max_position_size', 'N/A')}")

    # Test anomaly detection
    print("\n🔍 Testing anomaly detection...")
    anomaly = integration.check_anomaly("api_latency", 2500)
    if anomaly:
        print(f"   Anomaly detected: {anomaly['description']}")
    else:
        print("   No anomaly detected")

    # Print dashboard
    integration.print_dashboard()
