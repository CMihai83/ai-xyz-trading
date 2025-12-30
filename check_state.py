#!/usr/bin/env python3
import json
try:
    with open('position_state.json', 'r') as f:
        state = json.load(f)
    print('Position zones:')
    for symbol, zone in state.get('position_zones', {}).items():
        print(f'  {symbol}: {zone}')
    print('Averaging steps:')
    for symbol, steps in state.get('averaging_steps', {}).items():
        print(f'  {symbol}: {steps}')
    print('Fibonacci configs:')
    for symbol, config in state.get('fibonacci_configs', {}).items():
        print(f'  {symbol}: max_steps={config.get("max_averaging_steps", "N/A")}')
except Exception as e:
    print(f'Error: {e}')