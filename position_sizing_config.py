#!/usr/bin/env python3
"""
Position Sizing Configuration
Default: $6.5 after leverage
Higher size only when confidence > 0.7
"""

class PositionSizingConfig:
    # Total capital available for allocation - FLORIN'S ACCOUNT ($5 per position)
    TOTAL_CAPITAL = 5.0  # $5 total capital per position

    # Capital allocation strategy
    SAFETY_MARGIN_PERCENT = 0.30  # 30% reserved as safety margin ($1.50)
    TRADING_CAPITAL_PERCENT = 0.70  # 70% for initial + averaging ($3.50)

    # Base position margin - $0.70 initial margin (before leverage)
    BASE_MARGIN_SIZE = 0.70  # $0.70 initial margin (FIXED)

    # Base position value after leverage (10x average leverage)
    BASE_POSITION_VALUE = 7.00  # $7.00 position value after leverage ($0.70 margin * 10x leverage)
    
    # Capital breakdown
    SAFETY_MARGIN = TOTAL_CAPITAL * SAFETY_MARGIN_PERCENT  # $1.50 safety margin
    TRADING_CAPITAL = TOTAL_CAPITAL * TRADING_CAPITAL_PERCENT  # $3.50 for initial + averaging
    AVERAGING_CAPITAL = TRADING_CAPITAL - BASE_MARGIN_SIZE  # $2.80 for averaging steps
    
    # Safety margin usage
    NORMAL_MARGIN_USAGE = 0.70  # Use 70% of averaging capital normally
    EMERGENCY_MARGIN_USAGE = 0.30  # Reserve 30% for emergency final step
    
    # Confidence threshold for larger positions
    HIGH_CONFIDENCE_THRESHOLD = 0.7
    
    # Maximum position size multiplier when high confidence
    MAX_SIZE_MULTIPLIER = 2.0  # Can go up to 2x base size
    
    @staticmethod
    def calculate_position_size(leverage: float, confidence: float = 0.5) -> dict:
        """
        Calculate position size based on confidence level
        
        Args:
            leverage: Leverage to use (7x-10x)
            confidence: Signal confidence (0-1)
            
        Returns:
            dict with margin_size and position_value
        """
        # Default position value after leverage
        position_value = PositionSizingConfig.BASE_MARGIN_SIZE * leverage
        
        # Only increase size if confidence > 0.7
        if confidence > PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD:
            # Scale size based on confidence above threshold
            # confidence 0.7 = 1x, confidence 0.85 = 2x, confidence 1.0 = 3x
            confidence_factor = (confidence - PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD) / 0.3
            size_multiplier = 1.0 + (confidence_factor * (PositionSizingConfig.MAX_SIZE_MULTIPLIER - 1.0))
            base_position_value = PositionSizingConfig.BASE_MARGIN_SIZE * leverage
            position_value = base_position_value * size_multiplier
        
        # Calculate margin required
        margin_size = position_value / leverage
        
        return {
            'margin_size': margin_size,
            'position_value': position_value,
            'confidence': confidence,
            'size_multiplier': position_value / (PositionSizingConfig.BASE_MARGIN_SIZE * leverage)
        }
    
    @staticmethod
    def get_position_size_for_signal(signal: dict) -> dict:
        """
        Get position size for a trading signal
        
        Args:
            signal: Trading signal with confidence and leverage
            
        Returns:
            dict with sizing information
        """
        confidence = signal.get('confidence', 0.5)
        leverage = signal.get('leverage', 7)
        
        sizing = PositionSizingConfig.calculate_position_size(leverage, confidence)
        
        # Add explanation
        if confidence > PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD:
            sizing['reason'] = f"High confidence ({confidence:.2f}) - using {sizing['size_multiplier']:.1f}x base size"
        else:
            sizing['reason'] = f"Standard confidence ({confidence:.2f}) - using base size $7.00"
        
        return sizing

# Example usage
if __name__ == "__main__":
    print("="*60)
    print("POSITION SIZING CONFIGURATION")
    print("="*60)
    print(f"Base Position Value: ${PositionSizingConfig.BASE_POSITION_VALUE} (after leverage)")
    print(f"High Confidence Threshold: {PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD}")
    print(f"Max Size Multiplier: {PositionSizingConfig.MAX_SIZE_MULTIPLIER}x")
    
    print("\n" + "="*60)
    print("SIZING EXAMPLES")
    print("="*60)
    
    test_cases = [
        {'confidence': 0.3, 'leverage': 7},
        {'confidence': 0.5, 'leverage': 8},
        {'confidence': 0.69, 'leverage': 9},
        {'confidence': 0.7, 'leverage': 10},
        {'confidence': 0.75, 'leverage': 8},
        {'confidence': 0.85, 'leverage': 9},
        {'confidence': 1.0, 'leverage': 10}
    ]
    
    for test in test_cases:
        result = PositionSizingConfig.calculate_position_size(test['leverage'], test['confidence'])
        print(f"\nConfidence: {test['confidence']:.2f}, Leverage: {test['leverage']}x")
        print(f"  Position Value: ${result['position_value']:.2f}")
        print(f"  Margin Required: ${result['margin_size']:.2f}")
        print(f"  Size Multiplier: {result['size_multiplier']:.1f}x")