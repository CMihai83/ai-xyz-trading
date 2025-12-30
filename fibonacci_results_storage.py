#!/usr/bin/env python3
"""
Fibonacci Results Storage and Reporting System
Stores Fibonacci averaging service results with position IDs
Provides detailed reports on position configurations
"""

import json
import redis
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

class FibonacciResultsStorage:
    """Stores and manages Fibonacci averaging service results for all positions"""
    
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.storage_key = "fibonacci_results"
        self.file_backup = Path("/app/fibonacci_results_backup.json")
        
    def store_results(self, position_id: str, symbol: str, fibonacci_results: Dict) -> bool:
        """
        Store Fibonacci service results for a position
        
        Args:
            position_id: Unique position identifier
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            fibonacci_results: Complete results from Fibonacci service
        """
        try:
            # Add metadata
            storage_data = {
                'position_id': position_id,
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'results': fibonacci_results
            }
            
            # Store in Redis
            key = f"{self.storage_key}:{position_id}"
            self.redis_client.set(key, json.dumps(storage_data))
            self.redis_client.expire(key, 86400 * 7)  # Keep for 7 days
            
            # Also store in file backup
            self._backup_to_file(position_id, storage_data)
            
            logger.info(f"Stored Fibonacci results for position {position_id} ({symbol})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store Fibonacci results: {e}")
            return False
    
    def get_results(self, position_id: str) -> Optional[Dict]:
        """Retrieve Fibonacci results for a specific position"""
        try:
            key = f"{self.storage_key}:{position_id}"
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            
            # Try file backup if not in Redis
            return self._load_from_file(position_id)
            
        except Exception as e:
            logger.error(f"Failed to retrieve Fibonacci results: {e}")
            return None
    
    def get_all_active_results(self) -> List[Dict]:
        """Get all stored Fibonacci results"""
        try:
            results = []
            pattern = f"{self.storage_key}:*"
            
            for key in self.redis_client.scan_iter(pattern):
                data = self.redis_client.get(key)
                if data:
                    results.append(json.loads(data))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get all results: {e}")
            return []
    
    def _backup_to_file(self, position_id: str, data: Dict):
        """Backup results to JSON file"""
        try:
            # Load existing backup
            if self.file_backup.exists():
                with open(self.file_backup, 'r') as f:
                    backup = json.load(f)
            else:
                backup = {}
            
            # Update with new data
            backup[position_id] = data
            
            # Save backup
            with open(self.file_backup, 'w') as f:
                json.dump(backup, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to backup to file: {e}")
    
    def _load_from_file(self, position_id: str) -> Optional[Dict]:
        """Load results from file backup"""
        try:
            if self.file_backup.exists():
                with open(self.file_backup, 'r') as f:
                    backup = json.load(f)
                    return backup.get(position_id)
        except Exception as e:
            logger.error(f"Failed to load from file: {e}")
        return None
    
    def generate_report(self, position_id: Optional[str] = None) -> str:
        """
        Generate detailed report of Fibonacci configurations
        
        Args:
            position_id: Specific position ID or None for all positions
        """
        report_lines = []
        report_lines.append("="*80)
        report_lines.append("FIBONACCI AVERAGING SERVICE RESULTS REPORT")
        report_lines.append("="*80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        if position_id:
            # Report for specific position
            data = self.get_results(position_id)
            if data:
                report_lines.extend(self._format_position_report(data))
            else:
                report_lines.append(f"No results found for position ID: {position_id}")
        else:
            # Report for all positions
            all_results = self.get_all_active_results()
            if all_results:
                report_lines.append(f"Total Positions with Fibonacci Config: {len(all_results)}")
                report_lines.append("")
                
                for data in all_results:
                    report_lines.extend(self._format_position_report(data))
                    report_lines.append("-"*80)
            else:
                report_lines.append("No Fibonacci results found in storage")
        
        return "\n".join(report_lines)
    
    def _format_position_report(self, data: Dict) -> List[str]:
        """Format a single position's Fibonacci report"""
        lines = []
        
        # Header
        lines.append(f"📊 Position ID: {data['position_id']}")
        lines.append(f"   Symbol: {data['symbol']}")
        lines.append(f"   Configured: {data['timestamp']}")
        lines.append("")
        
        results = data['results']
        
        # Basic parameters
        lines.append("📈 TRADING PARAMETERS:")
        lines.append(f"   Leverage: {results.get('leverage', 'N/A')}x")
        lines.append(f"   Initial Position Size: ${results.get('initial_position_size', 0):.2f}")
        lines.append(f"   Total Margin Required: ${results.get('total_margin_required', 0):.2f}")
        lines.append(f"   Liquidation Price: ${results.get('liquidation_price', 0):.2f}")
        lines.append(f"   Confidence Score: {results.get('confidence_score', 0):.2%}")
        lines.append("")
        
        # Backtesting results if available
        if 'backtest_results' in results:
            bt = results['backtest_results']
            lines.append("📊 BACKTESTING RESULTS:")
            lines.append(f"   Total Trades Simulated: {bt.get('total_trades', 0)}")
            lines.append(f"   Win Rate: {bt.get('win_rate', 0):.2%}")
            lines.append(f"   Total Return: {bt.get('total_return', 0):.2%}")
            lines.append(f"   Max Drawdown: {bt.get('max_drawdown', 0):.2%}")
            lines.append(f"   Sharpe Ratio: {bt.get('sharpe_ratio', 0):.2f}")
            lines.append(f"   Recovery Rate: {bt.get('recovery_rate', 0):.2%}")
            lines.append(f"   Averaging Effectiveness: {bt.get('averaging_effectiveness', 0):.2%}")
            lines.append(f"   Liquidation Events: {bt.get('liquidation_events', 0)}")
            lines.append("")
        
        # Candle data info
        if 'candles_used' in results:
            lines.append("📈 HISTORICAL DATA:")
            lines.append(f"   Candles Analyzed: {results['candles_used']}")
            if 'optimization_score' in results:
                lines.append(f"   Optimization Score: {results['optimization_score']:.2f}")
            lines.append("")
        
        # Averaging steps
        averaging_steps = results.get('averaging_steps', [])
        if averaging_steps:
            lines.append(f"📊 AVERAGING STEPS ({len(averaging_steps)} levels):")
            
            for step in averaging_steps:
                lines.append(f"   Step {step['step_number']}:")
                lines.append(f"      Trigger Price: ${step['price']:.4f}")
                lines.append(f"      Position Multiplier: {step['position_multiplier']:.2f}x")
                lines.append(f"      Margin Allocation: ${step['margin_allocation']:.2f}")
                lines.append(f"      Fibonacci Weight: {step['fibonacci_weight']}")
                
                if 'distance_from_entry' in step:
                    lines.append(f"      Distance from Entry: ${step['distance_from_entry']:.4f}")
                
                if 'liquidation_safety' in step:
                    safety = "✅ SAFE" if step['liquidation_safety'] else "⚠️ RISKY"
                    lines.append(f"      Liquidation Safety: {safety}")
                lines.append("")
        
        # Summary statistics
        if averaging_steps:
            total_margin = sum(s['margin_allocation'] for s in averaging_steps)
            max_multiplier = max(s['position_multiplier'] for s in averaging_steps)
            
            lines.append("📈 SUMMARY:")
            lines.append(f"   Total Averaging Margin: ${total_margin:.2f}")
            lines.append(f"   Maximum Position Multiplier: {max_multiplier:.2f}x")
            lines.append(f"   Average Step Size: ${total_margin/len(averaging_steps):.2f}")
            
            # Fibonacci sequence used
            fib_weights = [s['fibonacci_weight'] for s in averaging_steps]
            lines.append(f"   Fibonacci Sequence: {fib_weights}")
        
        return lines

def store_position_fibonacci_results(position_id: str, symbol: str, 
                                    entry_price: float, direction: str,
                                    fibonacci_service_response: Dict):
    """
    Convenience function to store Fibonacci results when opening a position
    
    Args:
        position_id: Unique position identifier
        symbol: Trading symbol
        entry_price: Entry price of the position
        direction: 'long' or 'short'
        fibonacci_service_response: Response from Fibonacci averaging service
    """
    storage = FibonacciResultsStorage()
    
    # Add position context to results
    enhanced_results = {
        **fibonacci_service_response,
        'entry_price': entry_price,
        'direction': direction
    }
    
    return storage.store_results(position_id, symbol, enhanced_results)

def get_position_fibonacci_report(position_id: Optional[str] = None) -> str:
    """
    Get formatted report of Fibonacci configurations
    
    Args:
        position_id: Specific position or None for all
        
    Returns:
        Formatted report string
    """
    storage = FibonacciResultsStorage()
    return storage.generate_report(position_id)

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path
    
    # Add services to path
    sys.path.append(str(Path(__file__).parent / 'services' / 'api-gateway' / 'src'))
    
    async def test_storage():
        """Test the storage system with sample data"""
        
        print("Testing Fibonacci Results Storage System")
        print("="*60)
        
        # Sample Fibonacci service response
        sample_response = {
            'success': True,
            'leverage': 8,
            'initial_position_size': 6.5,
            'averaging_steps': [
                {
                    'step_number': 1,
                    'price': 49800.00,
                    'margin_allocation': 12.50,
                    'position_multiplier': 1.0,
                    'fibonacci_weight': 21,
                    'distance_from_entry': 200.0,
                    'liquidation_safety': True
                },
                {
                    'step_number': 2,
                    'price': 49520.00,
                    'margin_allocation': 20.00,
                    'position_multiplier': 1.6,
                    'fibonacci_weight': 13,
                    'distance_from_entry': 480.0,
                    'liquidation_safety': True
                },
                {
                    'step_number': 3,
                    'price': 49300.00,
                    'margin_allocation': 32.50,
                    'position_multiplier': 2.6,
                    'fibonacci_weight': 8,
                    'distance_from_entry': 700.0,
                    'liquidation_safety': True
                }
            ],
            'total_margin_required': 65.0,
            'liquidation_price': 47500.0,
            'confidence_score': 0.75
        }
        
        # Store results for a test position
        position_id = "test_pos_001"
        symbol = "BTC/USDT:USDT"
        
        success = store_position_fibonacci_results(
            position_id=position_id,
            symbol=symbol,
            entry_price=50000.0,
            direction='long',
            fibonacci_service_response=sample_response
        )
        
        if success:
            print(f"✅ Successfully stored results for position {position_id}")
        else:
            print(f"❌ Failed to store results")
        
        # Generate report
        print("\nGenerating report...")
        print("")
        report = get_position_fibonacci_report(position_id)
        print(report)
        
        # Store another position
        position_id_2 = "test_pos_002"
        sample_response_2 = {
            **sample_response,
            'leverage': 10,
            'initial_position_size': 10.0,
            'averaging_steps': sample_response['averaging_steps'][:2]  # Only 2 steps
        }
        
        store_position_fibonacci_results(
            position_id=position_id_2,
            symbol="ETH/USDT:USDT",
            entry_price=3000.0,
            direction='short',
            fibonacci_service_response=sample_response_2
        )
        
        # Generate report for all positions
        print("\n" + "="*60)
        print("Report for ALL positions:")
        print("")
        report_all = get_position_fibonacci_report()
        print(report_all)
    
    asyncio.run(test_storage())