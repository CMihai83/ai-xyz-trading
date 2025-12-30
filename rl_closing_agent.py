#!/usr/bin/env python3
"""
Reinforcement Learning Agent for Optimal Closing Strategies
Uses RL to learn the best times to close profitable positions based on market conditions
"""

import numpy as np
import pandas as pd
from collections import defaultdict
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json
import os
import pickle

class RLClosingAgent:
    """
    Reinforcement Learning agent that learns optimal position closing strategies
    Uses Q-learning to determine when to close positions based on market state
    """

    def __init__(self, learning_rate: float = 0.1, discount_factor: float = 0.95,
                 epsilon: float = 0.1, epsilon_decay: float = 0.995):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon  # Exploration rate
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = 0.01

        # Q-table: state -> action -> q_value
        self.q_table = defaultdict(lambda: defaultdict(float))

        # State discretization bins
        self.state_bins = {
            'pnl_pct': [-1, -0.5, -0.2, -0.1, 0, 0.1, 0.2, 0.5, 1, 2],  # P&L percentage bins
            'holding_time_hours': [0, 1, 2, 4, 8, 12, 24, 48, 72],  # Holding time bins
            'opportunity_cost': [0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5],  # Opportunity cost bins
            'market_volatility': [0, 0.02, 0.05, 0.1, 0.2, 0.5],  # Volatility bins
            'correlation': [-1, -0.5, -0.2, 0, 0.2, 0.5, 1]  # Correlation bins
        }

        # Actions: [HOLD_SHORT, HOLD_MEDIUM, HOLD_LONG, CLOSE_LOW, CLOSE_MEDIUM, CLOSE_HIGH]
        self.actions = ['HOLD_SHORT', 'HOLD_MEDIUM', 'HOLD_LONG', 'CLOSE_LOW', 'CLOSE_MEDIUM', 'CLOSE_HIGH']
        self.action_rewards = {
            'HOLD_SHORT': 0.1,   # Small reward for holding briefly
            'HOLD_MEDIUM': 0.2,  # Medium reward for holding longer
            'HOLD_LONG': 0.3,    # Large reward for holding long-term
            'CLOSE_LOW': -0.5,   # Penalty for closing too early
            'CLOSE_MEDIUM': 0,   # Neutral for reasonable closing
            'CLOSE_HIGH': 0.5    # Reward for closing at peak
        }

        # Training data and performance tracking
        self.training_episodes = []
        self.performance_history = []
        self.model_file = 'rl_closing_agent_model.pkl'

        # Load existing model if available
        self.load_model()

    def get_state(self, position_data: Dict, market_context: Dict) -> str:
        """
        Convert position and market data into discrete state representation

        Args:
            position_data: Current position metrics
            market_context: Market context data

        Returns:
            str: Discrete state string
        """
        # Extract key features
        pnl_pct = position_data.get('pnl', 0)
        holding_time = position_data.get('holding_time_hours', 0)
        opportunity_cost = market_context.get('current_opportunity_cost', 0)

        market_perf = market_context.get('market_performance', {}).get(
            position_data.get('symbol', ''), {}
        )
        volatility = market_perf.get('volatility', 0.05)
        correlation = market_perf.get('correlation', 0)

        # Discretize each feature
        pnl_bin = self._discretize_value(pnl_pct, self.state_bins['pnl_pct'])
        time_bin = self._discretize_value(holding_time, self.state_bins['holding_time_hours'])
        opp_cost_bin = self._discretize_value(opportunity_cost, self.state_bins['opportunity_cost'])
        vol_bin = self._discretize_value(volatility, self.state_bins['market_volatility'])
        corr_bin = self._discretize_value(correlation, self.state_bins['correlation'])

        # Create state string
        state = f"PNL{pnl_bin}_TIME{time_bin}_OPP{opp_cost_bin}_VOL{vol_bin}_CORR{corr_bin}"

        return state

    def _discretize_value(self, value: float, bins: List[float]) -> int:
        """Discretize a continuous value into bin index"""
        for i, bin_edge in enumerate(bins):
            if value <= bin_edge:
                return i
        return len(bins)  # Last bin for values above all edges

    def choose_action(self, state: str, training: bool = False) -> str:
        """
        Choose action using epsilon-greedy policy

        Args:
            state: Current state string
            training: Whether in training mode (allows exploration)

        Returns:
            str: Chosen action
        """
        if training and random.random() < self.epsilon:
            # Exploration: random action
            return random.choice(self.actions)
        else:
            # Exploitation: best action from Q-table
            q_values = self.q_table[state]
            if q_values:
                return max(q_values, key=q_values.get)
            else:
                # No experience with this state, choose reasonable default
                return self._get_default_action(state)

    def _get_default_action(self, state: str) -> str:
        """Get reasonable default action for unseen states"""
        # Parse state components
        parts = state.split('_')
        pnl_bin = int(parts[0].replace('PNL', ''))
        time_bin = int(parts[1].replace('TIME', ''))
        opp_bin = int(parts[2].replace('OPP', ''))

        # Default logic based on state
        if pnl_bin >= 4:  # Profitable (PNL >= 0)
            if opp_bin >= 3:  # High opportunity cost
                return 'CLOSE_MEDIUM'
            elif time_bin >= 4:  # Held long time
                return 'CLOSE_LOW'
            else:
                return 'HOLD_MEDIUM'
        else:  # Losing or break-even
            return 'CLOSE_LOW'

    def learn_from_experience(self, state: str, action: str, reward: float, next_state: str):
        """
        Update Q-table using Q-learning algorithm

        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state after action
        """
        # Current Q-value
        current_q = self.q_table[state][action]

        # Maximum Q-value for next state
        next_q_values = self.q_table[next_state]
        max_next_q = max(next_q_values.values()) if next_q_values else 0

        # Q-learning update
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )

        # Update Q-table
        self.q_table[state][action] = new_q

    def calculate_reward(self, action: str, position_outcome: Dict) -> float:
        """
        Calculate reward for an action based on position outcome

        Args:
            action: Action taken
            position_outcome: Final position outcome data

        Returns:
            float: Reward value
        """
        base_reward = self.action_rewards.get(action, 0)

        # Adjust based on actual outcome
        final_pnl = position_outcome.get('final_pnl_pct', 0)
        holding_time = position_outcome.get('total_holding_time_hours', 0)
        max_pnl = position_outcome.get('max_pnl_pct_achieved', 0)

        # Reward modifications
        reward_modifier = 0

        # Reward for profitability
        if final_pnl > 0:
            reward_modifier += min(final_pnl * 10, 2.0)  # Cap at +2.0

        # Penalty for missing potential profit
        if max_pnl > final_pnl + 0.1:  # Missed more than 10% potential profit
            missed_profit_penalty = (max_pnl - final_pnl) * 5
            reward_modifier -= min(missed_profit_penalty, 3.0)  # Cap penalty at -3.0

        # Holding time efficiency
        if action.startswith('HOLD'):
            # Reward longer holding if position became more profitable
            if final_pnl > 0.2:  # Good profit
                reward_modifier += 0.5
        elif action.startswith('CLOSE'):
            # Reward quick closing if avoiding losses
            if final_pnl < -0.1:  # Significant loss avoided
                reward_modifier += 0.3

        total_reward = base_reward + reward_modifier

        # Bound rewards
        return np.clip(total_reward, -5.0, 5.0)

    def train_on_historical_data(self, historical_positions: pd.DataFrame, episodes: int = 1000):
        """
        Train the RL agent on historical position data

        Args:
            historical_positions: DataFrame with historical position data
            episodes: Number of training episodes
        """
        print("🧠 Training RL Closing Agent...")

        successful_episodes = 0

        for episode in range(episodes):
            # Sample a random position sequence from historical data
            position_sequence = self._sample_position_sequence(historical_positions)

            if not position_sequence:
                continue

            total_reward = 0
            state_action_pairs = []

            # Simulate the position lifecycle
            for i, position_state in enumerate(position_sequence[:-1]):
                current_state = self.get_state(position_state['position_data'], position_state['market_context'])
                next_state = self.get_state(position_sequence[i+1]['position_data'], position_sequence[i+1]['market_context'])

                # Choose action (with exploration)
                action = self.choose_action(current_state, training=True)

                # Calculate reward based on what happened next
                reward = self.calculate_reward(action, position_sequence[i+1])

                # Learn from this experience
                self.learn_from_experience(current_state, action, reward, next_state)

                total_reward += reward
                state_action_pairs.append((current_state, action, reward))

            # Track episode performance
            if total_reward > 0:
                successful_episodes += 1

            # Decay exploration rate
            self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

            # Log progress
            if (episode + 1) % 100 == 0:
                print(f"Episode {episode + 1}/{episodes}: "
                      f"Avg Reward: {total_reward/len(position_sequence):.3f}, "
                      f"Epsilon: {self.epsilon:.3f}")

        # Save trained model
        self.save_model()

        print(f"✅ RL Training complete! Successful episodes: {successful_episodes}/{episodes}")
        print(f"📊 Q-table size: {len(self.q_table)} states")

    def _sample_position_sequence(self, historical_data: pd.DataFrame) -> List[Dict]:
        """Sample a sequence of position states from historical data"""
        # Group by position/trade ID
        if 'position_id' not in historical_data.columns:
            # Create synthetic position IDs based on symbol and time windows
            historical_data = historical_data.copy()
            historical_data['position_id'] = historical_data.groupby('symbol').ngroup()

        position_groups = historical_data.groupby('position_id')

        # Sample a random position
        sample_position_id = random.choice(list(position_groups.groups.keys()))
        position_data = position_groups.get_group(sample_position_id)

        if len(position_data) < 3:  # Need at least start, middle, end
            return []

        # Create sequence of states
        sequence = []
        timestamps = sorted(position_data['timestamp'].unique())

        for timestamp in timestamps[:10]:  # Limit sequence length
            time_slice = position_data[position_data['timestamp'] == timestamp]

            if len(time_slice) == 0:
                continue

            row = time_slice.iloc[0]

            # Reconstruct position and market state
            position_state = {
                'position_data': {
                    'symbol': row.get('symbol'),
                    'pnl': row.get('pnl_pct', 0),
                    'holding_time_hours': row.get('holding_time_hours', 0),
                    'unrealized_pl_usd': row.get('unrealized_pl_usd', 0)
                },
                'market_context': {
                    'current_opportunity_cost': row.get('opportunity_cost', 0),
                    'market_performance': {
                        row.get('symbol'): {
                            'return': row.get('market_return', 0),
                            'volatility': row.get('market_volatility', 0.05),
                            'correlation': row.get('correlation', 0)
                        }
                    }
                }
            }

            sequence.append(position_state)

        return sequence

    def get_closing_recommendation(self, position_data: Dict, market_context: Dict) -> Dict:
        """
        Get closing recommendation from trained RL agent

        Args:
            position_data: Current position data
            market_context: Current market context

        Returns:
            dict: Closing recommendation with confidence
        """
        state = self.get_state(position_data, market_context)
        action = self.choose_action(state, training=False)

        # Get confidence based on Q-value difference
        q_values = self.q_table[state]
        if len(q_values) > 1:
            sorted_actions = sorted(q_values.items(), key=lambda x: x[1], reverse=True)
            best_q = sorted_actions[0][1]
            second_best_q = sorted_actions[1][1]
            confidence = min((best_q - second_best_q) / abs(best_q + 0.001), 1.0)
        else:
            confidence = 0.5

        # Convert action to recommendation
        recommendation = self._action_to_recommendation(action, confidence)

        return {
            'action': action,
            'recommendation': recommendation,
            'confidence': confidence,
            'state': state,
            'q_values': dict(q_values) if q_values else {}
        }

    def _action_to_recommendation(self, action: str, confidence: float) -> str:
        """Convert RL action to human-readable recommendation"""
        if action.startswith('HOLD'):
            duration = {'SHORT': 'briefly', 'MEDIUM': 'longer', 'LONG': 'extended period'}[action.split('_')[1]]
            confidence_text = "high" if confidence > 0.7 else "moderate" if confidence > 0.4 else "low"
            return f"Hold position {duration} ({confidence_text} confidence in continued upside)"
        else:
            urgency = {'LOW': 'soon', 'MEDIUM': 'now', 'HIGH': 'immediately'}[action.split('_')[1]]
            confidence_text = "high" if confidence > 0.7 else "moderate" if confidence > 0.4 else "low"
            return f"Close position {urgency} ({confidence_text} confidence in optimal timing)"

    def save_model(self):
        """Save trained model to disk"""
        try:
            model_data = {
                'q_table': dict(self.q_table),
                'epsilon': self.epsilon,
                'performance_history': self.performance_history,
                'trained_at': datetime.now().isoformat()
            }

            with open(self.model_file, 'wb') as f:
                pickle.dump(model_data, f)

            print(f"💾 RL model saved to {self.model_file}")

        except Exception as e:
            print(f"❌ Failed to save RL model: {e}")

    def load_model(self):
        """Load trained model from disk"""
        try:
            if os.path.exists(self.model_file):
                with open(self.model_file, 'rb') as f:
                    model_data = pickle.load(f)

                self.q_table = defaultdict(lambda: defaultdict(float), model_data.get('q_table', {}))
                self.epsilon = model_data.get('epsilon', self.epsilon)
                self.performance_history = model_data.get('performance_history', [])

                print(f"📂 RL model loaded from {self.model_file}")
                print(f"📊 Loaded {len(self.q_table)} states from training")

        except Exception as e:
            print(f"⚠️ Could not load RL model: {e}")

    def get_training_stats(self) -> Dict:
        """Get training statistics and performance metrics"""
        return {
            'states_learned': len(self.q_table),
            'total_experiences': sum(len(actions) for actions in self.q_table.values()),
            'current_epsilon': self.epsilon,
            'performance_history': self.performance_history[-10:] if self.performance_history else []
        }

    def reset_learning(self):
        """Reset the agent for fresh learning"""
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.epsilon = 0.1
        self.performance_history = []

        if os.path.exists(self.model_file):
            os.remove(self.model_file)

        print("🔄 RL agent reset for fresh learning")