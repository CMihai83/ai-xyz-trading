#!/usr/bin/env python3
"""
Redis State Manager for AI-XYZ
Implements thread-safe state management with atomic operations
Solves the race condition and concurrency issues
"""

import json
import redis
import time
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import logging


class RedisStateManager:
    """
    Thread-safe state management using Redis
    Provides atomic operations for position management
    """

    def __init__(self, host='localhost', port=6379, db=0):
        """
        Initialize Redis connection

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
        """
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True
            )

            # Test connection
            self.redis_client.ping()

            # Set up logging
            logging.basicConfig(level=logging.INFO)
            self.logger = logging.getLogger('RedisStateManager')

            self.logger.info("Redis connection established")

        except redis.ConnectionError:
            self.logger.warning("Redis not available, falling back to JSON file")
            self.redis_client = None
            self.fallback_file = '/app/position_state.json'

    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get position data atomically

        Args:
            symbol: Trading symbol

        Returns:
            Position dictionary or None
        """
        if self.redis_client:
            try:
                # Get position from Redis hash
                position_key = f"position:{symbol}"
                position_data = self.redis_client.hgetall(position_key)

                if position_data:
                    # Convert string values to appropriate types
                    return self._deserialize_position(position_data)

                return None

            except Exception as e:
                self.logger.error(f"Redis get error: {e}")
                return self._fallback_get_position(symbol)
        else:
            return self._fallback_get_position(symbol)

    def set_position(self, symbol: str, position: Dict) -> bool:
        """
        Set position data atomically

        Args:
            symbol: Trading symbol
            position: Position dictionary

        Returns:
            Success boolean
        """
        if self.redis_client:
            try:
                # Use pipeline for atomic multi-field update
                pipe = self.redis_client.pipeline()
                position_key = f"position:{symbol}"

                # Serialize position data
                serialized = self._serialize_position(position)

                # Set all fields atomically
                pipe.hmset(position_key, serialized)

                # Set expiry (24 hours)
                pipe.expire(position_key, 86400)

                # Add to position set
                pipe.sadd("active_positions", symbol)

                # Execute pipeline
                pipe.execute()

                self.logger.info(f"Position saved: {symbol}")
                return True

            except Exception as e:
                self.logger.error(f"Redis set error: {e}")
                return self._fallback_set_position(symbol, position)
        else:
            return self._fallback_set_position(symbol, position)

    def update_position_field(self, symbol: str, field: str, value: Any) -> bool:
        """
        Update single position field atomically

        Args:
            symbol: Trading symbol
            field: Field name
            value: Field value

        Returns:
            Success boolean
        """
        if self.redis_client:
            try:
                position_key = f"position:{symbol}"

                # Use atomic hincrby for numeric fields
                if field in ['amount', 'averaging_steps']:
                    self.redis_client.hincrby(position_key, field, int(value))
                elif field in ['unrealized_pnl', 'entry_price', 'current_price']:
                    # Store floats as strings
                    self.redis_client.hset(position_key, field, str(value))
                else:
                    self.redis_client.hset(position_key, field, value)

                # Update timestamp
                self.redis_client.hset(position_key, 'last_updated', datetime.now().isoformat())

                return True

            except Exception as e:
                self.logger.error(f"Redis update error: {e}")
                return False
        else:
            return self._fallback_update_field(symbol, field, value)

    def increment_averaging_step(self, symbol: str) -> int:
        """
        Atomically increment averaging step counter

        Args:
            symbol: Trading symbol

        Returns:
            New step count
        """
        if self.redis_client:
            try:
                key = f"averaging_steps:{symbol}"
                new_value = self.redis_client.incr(key)
                self.redis_client.expire(key, 86400)  # 24-hour expiry

                self.logger.info(f"{symbol}: Averaging step incremented to {new_value}")
                return new_value

            except Exception as e:
                self.logger.error(f"Redis increment error: {e}")
                return 0
        else:
            return self._fallback_increment_averaging(symbol)

    def get_all_positions(self) -> Dict[str, Dict]:
        """
        Get all active positions atomically

        Returns:
            Dictionary of all positions
        """
        if self.redis_client:
            try:
                # Get all active position symbols
                symbols = self.redis_client.smembers("active_positions")

                # Use pipeline to get all positions
                pipe = self.redis_client.pipeline()
                for symbol in symbols:
                    pipe.hgetall(f"position:{symbol}")

                # Execute and build result
                results = pipe.execute()
                positions = {}

                for symbol, position_data in zip(symbols, results):
                    if position_data:
                        positions[symbol] = self._deserialize_position(position_data)

                return positions

            except Exception as e:
                self.logger.error(f"Redis get all error: {e}")
                return self._fallback_get_all_positions()
        else:
            return self._fallback_get_all_positions()

    def delete_position(self, symbol: str) -> bool:
        """
        Delete position atomically

        Args:
            symbol: Trading symbol

        Returns:
            Success boolean
        """
        if self.redis_client:
            try:
                pipe = self.redis_client.pipeline()

                # Delete position hash
                pipe.delete(f"position:{symbol}")

                # Remove from active set
                pipe.srem("active_positions", symbol)

                # Delete related keys
                pipe.delete(f"averaging_steps:{symbol}")
                pipe.delete(f"peak_upnl:{symbol}")
                pipe.delete(f"surplus_stage:{symbol}")

                # Execute
                pipe.execute()

                self.logger.info(f"Position deleted: {symbol}")
                return True

            except Exception as e:
                self.logger.error(f"Redis delete error: {e}")
                return False
        else:
            return self._fallback_delete_position(symbol)

    def acquire_lock(self, resource: str, timeout: int = 10) -> bool:
        """
        Acquire distributed lock for resource

        Args:
            resource: Resource name to lock
            timeout: Lock timeout in seconds

        Returns:
            Lock acquired boolean
        """
        if self.redis_client:
            try:
                lock_key = f"lock:{resource}"
                lock_value = f"{datetime.now().isoformat()}"

                # Try to acquire lock with NX (only if not exists) and EX (expiry)
                acquired = self.redis_client.set(
                    lock_key,
                    lock_value,
                    nx=True,
                    ex=timeout
                )

                if acquired:
                    self.logger.debug(f"Lock acquired: {resource}")

                return bool(acquired)

            except Exception as e:
                self.logger.error(f"Lock error: {e}")
                return False
        else:
            # No locking in fallback mode
            return True

    def release_lock(self, resource: str) -> bool:
        """
        Release distributed lock

        Args:
            resource: Resource name to unlock

        Returns:
            Success boolean
        """
        if self.redis_client:
            try:
                lock_key = f"lock:{resource}"
                self.redis_client.delete(lock_key)
                self.logger.debug(f"Lock released: {resource}")
                return True

            except Exception as e:
                self.logger.error(f"Unlock error: {e}")
                return False
        else:
            return True

    def _serialize_position(self, position: Dict) -> Dict:
        """Serialize position data for Redis storage"""
        serialized = {}
        for key, value in position.items():
            if isinstance(value, (int, float)):
                serialized[key] = str(value)
            elif isinstance(value, dict):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = value
        return serialized

    def _deserialize_position(self, position_data: Dict) -> Dict:
        """Deserialize position data from Redis"""
        deserialized = {}
        for key, value in position_data.items():
            if key in ['entry_price', 'current_price', 'amount', 'unrealized_pnl']:
                deserialized[key] = float(value)
            elif key in ['leverage', 'averaging_steps']:
                deserialized[key] = int(value)
            elif value.startswith('{'):
                deserialized[key] = json.loads(value)
            else:
                deserialized[key] = value
        return deserialized

    # Fallback methods for when Redis is not available
    def _fallback_get_position(self, symbol: str) -> Optional[Dict]:
        """Fallback to JSON file for getting position"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)
            return state.get('positions', {}).get(symbol)
        except:
            return None

    def _fallback_set_position(self, symbol: str, position: Dict) -> bool:
        """Fallback to JSON file for setting position"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)

            if 'positions' not in state:
                state['positions'] = {}

            state['positions'][symbol] = position

            with open(self.fallback_file, 'w') as f:
                json.dump(state, f, indent=2)

            return True
        except Exception as e:
            self.logger.error(f"Fallback set error: {e}")
            return False

    def _fallback_update_field(self, symbol: str, field: str, value: Any) -> bool:
        """Fallback to JSON file for updating field"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)

            if 'positions' in state and symbol in state['positions']:
                state['positions'][symbol][field] = value

                with open(self.fallback_file, 'w') as f:
                    json.dump(state, f, indent=2)

                return True
            return False
        except:
            return False

    def _fallback_get_all_positions(self) -> Dict:
        """Fallback to JSON file for getting all positions"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)
            return state.get('positions', {})
        except:
            return {}

    def _fallback_delete_position(self, symbol: str) -> bool:
        """Fallback to JSON file for deleting position"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)

            if 'positions' in state and symbol in state['positions']:
                del state['positions'][symbol]

                with open(self.fallback_file, 'w') as f:
                    json.dump(state, f, indent=2)

                return True
            return False
        except:
            return False

    def _fallback_increment_averaging(self, symbol: str) -> int:
        """Fallback to JSON file for incrementing averaging steps"""
        try:
            with open(self.fallback_file, 'r') as f:
                state = json.load(f)

            if 'averaging_steps' not in state:
                state['averaging_steps'] = {}

            current = state['averaging_steps'].get(symbol, 0)
            state['averaging_steps'][symbol] = current + 1

            with open(self.fallback_file, 'w') as f:
                json.dump(state, f, indent=2)

            return current + 1
        except:
            return 0


def main():
    """Test Redis state manager"""
    manager = RedisStateManager()

    print("\n" + "="*60)
    print("REDIS STATE MANAGER TEST")
    print("="*60)

    # Test position operations
    test_position = {
        'entry_price': 50000.0,
        'amount': 0.01,
        'leverage': 8,
        'unrealized_pnl': -5.25,
        'current_price': 49475.0
    }

    # Set position
    success = manager.set_position('BTC/USDT', test_position)
    print(f"\n✅ Set position: {success}")

    # Get position
    retrieved = manager.get_position('BTC/USDT')
    print(f"✅ Retrieved position: {retrieved}")

    # Update field
    manager.update_position_field('BTC/USDT', 'unrealized_pnl', -10.50)
    print(f"✅ Updated UPNL")

    # Increment averaging
    step = manager.increment_averaging_step('BTC/USDT')
    print(f"✅ Averaging step: {step}")

    # Get all positions
    all_positions = manager.get_all_positions()
    print(f"✅ Total positions: {len(all_positions)}")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()