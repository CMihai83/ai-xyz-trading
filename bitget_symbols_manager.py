#!/usr/bin/env python3
"""
Bitget Symbols Information Manager
Downloads and maintains all futures symbols info including decimal precision
"""
import ccxt
import json
import os
import time
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
import threading
import logging

load_dotenv('/app/.env')

class BitgetSymbolsManager:
    def __init__(self):
        self.symbols_file = '/app/bitget_symbols_info.json'
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        self.symbols_data = self.load_symbols_data()
        self.logger = self.setup_logger()
        
    def setup_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger('BitgetSymbolsManager')
        # Also log to file
        handler = logging.FileHandler('/app/logs/symbols_manager.log')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger
    
    def load_symbols_data(self) -> Dict[str, Any]:
        """Load existing symbols data from file"""
        if os.path.exists(self.symbols_file):
            try:
                with open(self.symbols_file, 'r') as f:
                    data = json.load(f)
                    print(f"Loaded {len(data.get('symbols', {}))} symbols from cache")
                    return data
            except Exception as e:
                print(f"Error loading symbols data: {e}")
        
        return {
            'last_full_update': None,
            'symbols': {},
            'update_history': []
        }
    
    def save_symbols_data(self):
        """Save symbols data to file"""
        try:
            with open(self.symbols_file, 'w') as f:
                json.dump(self.symbols_data, f, indent=2)
            self.logger.info(f"Saved {len(self.symbols_data['symbols'])} symbols to {self.symbols_file}")
        except Exception as e:
            self.logger.error(f"Error saving symbols data: {e}")
    
    def fetch_all_symbols(self) -> Dict[str, Any]:
        """Fetch all futures symbols from Bitget"""
        self.logger.info("Fetching all symbols from Bitget...")
        try:
            markets = self.exchange.load_markets(reload=True)
            futures_markets = {
                symbol: market for symbol, market in markets.items() 
                if market.get('type') == 'swap' and ':USDT' in symbol
            }
            
            self.logger.info(f"Found {len(futures_markets)} USDT futures symbols")
            return futures_markets
        except Exception as e:
            self.logger.error(f"Error fetching markets: {e}")
            return {}
    
    def extract_symbol_info(self, symbol: str, market_info: Dict) -> Dict:
        """Extract relevant information for a symbol"""
        return {
            'symbol': symbol,
            'base': market_info.get('base', ''),
            'quote': market_info.get('quote', ''),
            'contract_size': market_info.get('contractSize', 1),
            'min_amount': float(market_info.get('limits', {}).get('amount', {}).get('min', 1)) if market_info.get('limits', {}).get('amount', {}).get('min') else 1,
            'max_amount': float(market_info.get('limits', {}).get('amount', {}).get('max')) if market_info.get('limits', {}).get('amount', {}).get('max') else None,
            'min_cost': float(market_info.get('limits', {}).get('cost', {}).get('min', 5)) if market_info.get('limits', {}).get('cost', {}).get('min') else 5,
            'amount_precision': int(market_info.get('precision', {}).get('amount', 0)) if market_info.get('precision', {}).get('amount') is not None else 0,
            'price_precision': int(market_info.get('precision', {}).get('price', 4)) if market_info.get('precision', {}).get('price') is not None else 4,
            'tick_size': float(market_info.get('info', {}).get('priceStep', 0.0001)) if market_info.get('info', {}).get('priceStep') else 0.0001,
            'lot_size': float(market_info.get('info', {}).get('sizeMultiplier', 1)) if market_info.get('info', {}).get('sizeMultiplier') else 1,
            'is_active': market_info.get('active', True),
            'maker_fee': market_info.get('maker', 0.0002),
            'taker_fee': market_info.get('taker', 0.0006),
            'max_leverage': market_info.get('info', {}).get('maxLever', 20),
            'last_updated': datetime.now().isoformat(),
            'requires_whole_contracts': market_info.get('precision', {}).get('amount', 0) == 0
        }
    
    def update_all_symbols(self):
        """Update all symbols information"""
        self.logger.info("Starting full symbols update...")
        markets = self.fetch_all_symbols()
        
        if not markets:
            self.logger.warning("No markets fetched, skipping update")
            return
        
        updated_count = 0
        new_count = 0
        
        for symbol, market in markets.items():
            symbol_info = self.extract_symbol_info(symbol, market)
            
            if symbol in self.symbols_data['symbols']:
                # Update existing symbol
                old_info = self.symbols_data['symbols'][symbol]
                if symbol_info != old_info:
                    updated_count += 1
                    self.logger.info(f"Updated {symbol}")
            else:
                # New symbol
                new_count += 1
                self.logger.info(f"Added new symbol {symbol}")
            
            self.symbols_data['symbols'][symbol] = symbol_info
        
        # Update metadata
        self.symbols_data['last_full_update'] = datetime.now().isoformat()
        self.symbols_data['update_history'].append({
            'timestamp': datetime.now().isoformat(),
            'total_symbols': len(self.symbols_data['symbols']),
            'updated': updated_count,
            'new': new_count
        })
        
        # Keep only last 100 update records
        if len(self.symbols_data['update_history']) > 100:
            self.symbols_data['update_history'] = self.symbols_data['update_history'][-100:]
        
        self.save_symbols_data()
        self.logger.info(f"Update complete: {new_count} new, {updated_count} updated, {len(self.symbols_data['symbols'])} total")
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Get information for a specific symbol"""
        # Check cache first
        if symbol in self.symbols_data['symbols']:
            return self.symbols_data['symbols'][symbol]
        
        # Not in cache, fetch from exchange
        self.logger.info(f"Symbol {symbol} not in cache, fetching from exchange...")
        try:
            markets = self.exchange.load_markets(reload=True)
            if symbol in markets:
                symbol_info = self.extract_symbol_info(symbol, markets[symbol])
                self.symbols_data['symbols'][symbol] = symbol_info
                self.save_symbols_data()
                return symbol_info
            else:
                self.logger.warning(f"Symbol {symbol} not found on exchange")
                return None
        except Exception as e:
            self.logger.error(f"Error fetching symbol {symbol}: {e}")
            return None
    
    def get_amount_precision(self, symbol: str) -> int:
        """Get the amount precision (decimal places) for a symbol"""
        info = self.get_symbol_info(symbol)
        if info:
            return info.get('amount_precision', 0)
        return 0
    
    def round_amount(self, symbol: str, amount: float) -> float:
        """Round amount to the correct precision for a symbol"""
        info = self.get_symbol_info(symbol)
        if info:
            precision = info.get('amount_precision', 0)
            if precision == 0:
                # No decimals allowed, round to nearest integer
                return round(amount)
            else:
                # Round to specified decimal places
                return round(amount, precision)
        # Default to no decimals if symbol not found
        return round(amount)
    
    def requires_whole_contracts(self, symbol: str) -> bool:
        """Check if symbol requires whole number contracts"""
        info = self.get_symbol_info(symbol)
        if info:
            return info.get('requires_whole_contracts', True)
        return True  # Default to whole contracts for safety
    
    def get_minimum_order_size(self, symbol: str) -> Dict:
        """Get minimum order requirements for a symbol"""
        info = self.get_symbol_info(symbol)
        if info:
            return {
                'min_amount': info.get('min_amount', 1),
                'min_cost': info.get('min_cost', 5),
                'lot_size': info.get('lot_size', 1)
            }
        return {'min_amount': 1, 'min_cost': 5, 'lot_size': 1}
    
    def continuous_update_service(self, update_interval: int = 3600):
        """Run continuous update service (default: every hour)"""
        self.logger.info(f"Starting continuous update service (interval: {update_interval} seconds)")
        
        while True:
            try:
                self.update_all_symbols()
                time.sleep(update_interval)
            except Exception as e:
                self.logger.error(f"Error in continuous update: {e}")
                time.sleep(60)  # Wait 1 minute on error
    
    def start_background_service(self, update_interval: int = 3600):
        """Start the update service in a background thread"""
        thread = threading.Thread(
            target=self.continuous_update_service,
            args=(update_interval,),
            daemon=True
        )
        thread.start()
        self.logger.info("Background update service started")
        return thread

def main():
    """Main function for standalone execution"""
    manager = BitgetSymbolsManager()
    
    print("Bitget Symbols Manager")
    print("="*50)
    
    # Do initial full update
    print("Performing initial symbols update...")
    manager.update_all_symbols()
    
    # Show statistics
    print(f"\nTotal symbols loaded: {len(manager.symbols_data['symbols'])}")
    print(f"Last update: {manager.symbols_data['last_full_update']}")
    
    # Show some examples
    print("\nExample symbols requiring whole contracts:")
    count = 0
    for symbol, info in manager.symbols_data['symbols'].items():
        if info['requires_whole_contracts']:
            print(f"  {symbol}: precision={info['amount_precision']}, min={info['min_amount']}")
            count += 1
            if count >= 5:
                break
    
    # Start continuous update service
    print("\nStarting continuous update service (every hour)...")
    manager.start_background_service(3600)
    
    # Keep running
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    main()