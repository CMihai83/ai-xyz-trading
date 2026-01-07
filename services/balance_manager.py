#!/usr/bin/env python3
"""
Balance Manager Service - Automatically moves excess funds from futures to spot
Maintains $400 in futures account, moving excess in $15 increments to spot
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
import ccxt
from dotenv import load_dotenv

# Setup paths
sys.path.append('/app')
load_dotenv('/app/.env')

# Setup logging
log_dir = Path('/app/logs')
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'balance_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('BalanceManager')

class BalanceManager:
    def __init__(self):
        """Initialize the balance manager with exchange connection"""
        self.TARGET_BALANCE = 400.0  # Target futures balance in USDT
        self.TRANSFER_INCREMENT = 15.0  # Transfer in $15 increments
        self.MIN_TRANSFER = 15.0  # Minimum transfer amount
        
        # Initialize exchange
        self.exchange = self._init_exchange()
        
        # Track transfer history
        self.transfer_history_file = Path('/app/logs/transfer_history.json')
        self.transfer_history = self._load_transfer_history()
        
    def _init_exchange(self):
        """Initialize Bitget exchange connection"""
        try:
            exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'broker': 'partner#3xr6yhzc'
                }
            })
            
            # Test connection
            exchange.fetch_balance()
            logger.info("✅ Connected to Bitget exchange")
            return exchange
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to exchange: {e}")
            raise
    
    def _load_transfer_history(self):
        """Load transfer history from file"""
        if self.transfer_history_file.exists():
            try:
                with open(self.transfer_history_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_transfer_history(self):
        """Save transfer history to file"""
        with open(self.transfer_history_file, 'w') as f:
            json.dump(self.transfer_history[-100:], f, indent=2)  # Keep last 100 transfers
    
    def get_futures_balance(self):
        """Get current futures account USDT balance"""
        try:
            balance = self.exchange.fetch_balance()
            
            # Get USDT balance (free + used)
            usdt_free = balance.get('USDT', {}).get('free', 0)
            usdt_used = balance.get('USDT', {}).get('used', 0)
            usdt_total = usdt_free + usdt_used
            
            logger.info(f"📊 Futures Balance - Total: ${usdt_total:.2f} (Free: ${usdt_free:.2f}, Used: ${usdt_used:.2f})")
            
            return {
                'total': usdt_total,
                'free': usdt_free,
                'used': usdt_used
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch balance: {e}")
            return None
    
    def transfer_to_spot(self, amount):
        """Transfer USDT from futures to spot account"""
        try:
            # Round to 2 decimal places
            amount = round(amount, 2)
            
            # Bitget transfer params
            params = {
                'coin': 'USDT',
                'amount': str(amount),
                'from': 'swap',  # futures account
                'to': 'spot',    # spot account
            }
            
            logger.info(f"💸 Transferring ${amount} from futures to spot...")
            
            # Execute transfer
            result = self.exchange.transfer('USDT', amount, 'swap', 'spot')
            
            # Record transfer
            transfer_record = {
                'timestamp': datetime.now().isoformat(),
                'amount': amount,
                'direction': 'futures_to_spot',
                'result': result,
                'success': True
            }
            self.transfer_history.append(transfer_record)
            self._save_transfer_history()
            
            logger.info(f"✅ Successfully transferred ${amount} to spot account")
            return True
            
        except Exception as e:
            logger.error(f"❌ Transfer failed: {e}")
            
            # Record failed transfer
            transfer_record = {
                'timestamp': datetime.now().isoformat(),
                'amount': amount,
                'direction': 'futures_to_spot',
                'error': str(e),
                'success': False
            }
            self.transfer_history.append(transfer_record)
            self._save_transfer_history()
            
            return False
    
    def check_and_transfer(self):
        """Check balance and transfer excess to spot in $5 increments"""
        try:
            # Get current balance
            balance_info = self.get_futures_balance()
            if not balance_info:
                return
            
            total_balance = balance_info['total']
            free_balance = balance_info['free']
            
            # Calculate excess (what's above $50)
            excess = total_balance - self.TARGET_BALANCE
            
            if excess >= self.MIN_TRANSFER:
                # Calculate how many $5 increments to transfer
                num_increments = int(excess / self.TRANSFER_INCREMENT)
                transfer_amount = num_increments * self.TRANSFER_INCREMENT
                
                # Make sure we're not transferring more than free balance
                transfer_amount = min(transfer_amount, free_balance)
                
                if transfer_amount >= self.MIN_TRANSFER:
                    logger.info(f"📈 Excess detected: ${excess:.2f}")
                    logger.info(f"🔄 Will transfer: ${transfer_amount:.2f} ({num_increments} x $15 increments)")
                    
                    # Execute transfer
                    success = self.transfer_to_spot(transfer_amount)
                    
                    if success:
                        # Verify new balance
                        time.sleep(2)
                        new_balance = self.get_futures_balance()
                        if new_balance:
                            logger.info(f"📊 New futures balance: ${new_balance['total']:.2f}")
                else:
                    logger.info(f"⏸️ Free balance (${free_balance:.2f}) insufficient for transfer")
            else:
                logger.info(f"✓ Balance (${total_balance:.2f}) within target. No transfer needed.")
                
        except Exception as e:
            logger.error(f"❌ Error in check_and_transfer: {e}")
    
    def get_transfer_summary(self):
        """Get summary of recent transfers"""
        if not self.transfer_history:
            return "No transfers yet"
        
        successful = [t for t in self.transfer_history if t['success']]
        failed = [t for t in self.transfer_history if not t['success']]
        
        total_transferred = sum(t['amount'] for t in successful)
        
        summary = f"""
📊 Transfer Summary:
• Total Transfers: {len(self.transfer_history)}
• Successful: {len(successful)}
• Failed: {len(failed)}
• Total Moved: ${total_transferred:.2f}
• Last Transfer: {self.transfer_history[-1]['timestamp']}
"""
        return summary
    
    def run_continuous(self, check_interval_seconds=3600):
        """Run continuous balance checking (default: every hour)"""
        logger.info("🚀 Starting Balance Manager Service")
        logger.info(f"⚙️ Settings: Target=${self.TARGET_BALANCE}, Increment=${self.TRANSFER_INCREMENT}, Check every {check_interval_seconds}s")
        
        while True:
            try:
                logger.info("\n" + "="*50)
                logger.info(f"🔍 Checking balance at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Check and transfer if needed
                self.check_and_transfer()
                
                # Print summary every 10 checks
                if len(self.transfer_history) % 10 == 0 and self.transfer_history:
                    logger.info(self.get_transfer_summary())
                
                # Wait for next check
                logger.info(f"⏰ Next check in {check_interval_seconds} seconds...")
                time.sleep(check_interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("\n👋 Balance Manager stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                logger.info(f"🔄 Retrying in {check_interval_seconds} seconds...")
                time.sleep(check_interval_seconds)

def main():
    """Main entry point"""
    manager = BalanceManager()
    
    # Run continuous monitoring (checks every hour)
    manager.run_continuous(check_interval_seconds=3600)

if __name__ == "__main__":
    main()