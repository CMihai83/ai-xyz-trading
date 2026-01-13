#!/usr/bin/env python3
"""
Bitget Onchain Service - Tokenized Stock Trading
=================================================
Trades tokenized stocks (xStocks) via Bitget Onchain/Wallet API on Solana.

xStocks Available:
- TSLAx (Tesla), NVDAx (NVIDIA), AAPLx (Apple), AMZNx (Amazon)
- SPYx (S&P 500 ETF), QQQx (Nasdaq ETF), MSTRx (MicroStrategy)
- GOOGLx (Google), METAx (Meta), MSFTx (Microsoft), COINx (Coinbase)

API Endpoints:
- Market Data: /bgw-pro/market/v3/coin/getKline, getTxInfo
- Swap Quote: /bgw-pro/swapx/pro/quote
- Swap Execute: /bgw-pro/swapx/pro/swap
- Send Transaction: /bgw-pro/swapx/pro/send

Requirements:
- Bitget Wallet with SOL + USDC
- Partner-Code (contact Bitget for approval)
- Solana wallet private key for signing transactions

Based on Grok research and Bitget Web3 API documentation.
"""

import asyncio
import aiohttp
import json
import os
import time
import hmac
import hashlib
import base64
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger(__name__)


# =============================================================================
# PUBLIC API ENDPOINTS (No auth required)
# =============================================================================

# Jupiter API for Solana token prices (public)
JUPITER_PRICE_API = 'https://price.jup.ag/v6/price'
JUPITER_QUOTE_API = 'https://quote-api.jup.ag/v6/quote'
JUPITER_SWAP_API = 'https://quote-api.jup.ag/v6/swap'

# DexScreener API (public, reliable)
DEXSCREENER_API = 'https://api.dexscreener.com/latest/dex/tokens'

# Birdeye API for Solana token data (public with limits)
BIRDEYE_API = 'https://public-api.birdeye.so'


# =============================================================================
# XSTOCKS TOKEN ADDRESSES (Solana SPL Tokens)
# =============================================================================

XSTOCK_TOKENS = {
    # =========================================================================
    # VERIFIED XSTOCK TOKEN ADDRESSES (Solana SPL)
    # Source: DexScreener API, verified on-chain
    # =========================================================================

    # Tech Giants
    'TSLAx': {
        'name': 'Tesla xStock',
        'mint': 'XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB',
        'decimals': 9,
        'sector': 'auto_ev',
    },
    'NVDAx': {
        'name': 'NVIDIA xStock',
        'mint': 'Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh',
        'decimals': 9,
        'sector': 'semiconductors',
    },
    'AAPLx': {
        'name': 'Apple xStock',
        'mint': 'XsbEhLAtcf6HdfpFZ5xEMdqW8nfAvcsP5bdudRLJzJp',
        'decimals': 9,
        'sector': 'tech',
    },
    'AMZNx': {
        'name': 'Amazon xStock',
        'mint': 'Xs3eBt7uRfJX8QUs4suhyU8p2M6DoUDrJyWBa8LLZsg',
        'decimals': 9,
        'sector': 'ecommerce',
    },
    'GOOGLx': {
        'name': 'Alphabet/Google xStock',
        'mint': 'XsCPL9dNWBMvFtTmwcCA5v3xWPSMEBCszbQdiLLq6aN',
        'decimals': 9,
        'sector': 'tech',
    },
    # ETFs
    'SPYx': {
        'name': 'S&P 500 ETF xStock',
        'mint': 'XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W',
        'decimals': 9,
        'sector': 'etf_index',
    },
    # Bitcoin Proxy
    'MSTRx': {
        'name': 'MicroStrategy xStock',
        'mint': 'XsP7xzNPvEHS1m6qfanPUGjNmdnmsLKEoNAnHjdxxyZ',
        'decimals': 9,
        'sector': 'btc_proxy',
    },
}

# USDC on Solana (quote currency)
USDC_SOL = {
    'symbol': 'USDC',
    'mint': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'decimals': 6,
}


@dataclass
class StockQuote:
    """Quote for a tokenized stock"""
    symbol: str
    price_usd: float
    change_24h: float
    change_7d: float
    volume_24h: float
    market_cap: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SwapQuote:
    """Quote for a swap transaction"""
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    price: float
    slippage: float
    market: str
    gas_estimate: float
    expires_at: datetime


@dataclass
class Position:
    """Position in a tokenized stock"""
    symbol: str
    amount: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class BitgetOnchainService:
    """
    Service for trading tokenized stocks on Bitget Onchain (Solana)

    Features:
    - Fetch xStock prices and market data
    - Get swap quotes (USDC <-> xStocks)
    - Execute swaps via Bitget Wallet API
    - Portfolio tracking and management
    """

    def __init__(self, partner_code: str = None):
        # API Configuration
        self.base_url = 'https://api.bitget.com'
        self.web3_url = 'https://web3.bitget.com'
        self.partner_code = partner_code or os.getenv('BITGET_PARTNER_CODE', '')

        # Wallet Configuration (for signing transactions)
        self.wallet_address = os.getenv('SOLANA_WALLET_ADDRESS', '')
        self.private_key = os.getenv('SOLANA_PRIVATE_KEY', '')

        # Bitget API credentials
        self.api_key = os.getenv('BITGET_API_KEY', '')
        self.api_secret = os.getenv('BITGET_API_SECRET', '')
        self.api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

        # Session management
        self.session: Optional[aiohttp.ClientSession] = None

        # State
        self.prices: Dict[str, StockQuote] = {}
        self.positions: Dict[str, Position] = {}
        self.state_file = os.getenv('ONCHAIN_STATE_FILE', '/app/onchain_state.json')

        # Trading config
        self.default_slippage = 1.0  # 1%
        self.min_trade_usd = 5.0
        self.max_trade_usd = 1000.0

        logger.info("BitgetOnchainService initialized",
                   partner_code_set=bool(self.partner_code),
                   wallet_set=bool(self.wallet_address))

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Initialize HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            )
        self._load_state()
        logger.info("Service initialized")

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    def _get_headers(self) -> Dict:
        """Get request headers"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if self.partner_code:
            headers['Partner-Code'] = self.partner_code
        return headers

    def _sign_request(self, timestamp: str, method: str, path: str, body: str = '') -> str:
        """Generate request signature for authenticated endpoints"""
        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _get_auth_headers(self, method: str, path: str, body: str = '') -> Dict:
        """Get authenticated request headers"""
        timestamp = str(int(time.time() * 1000))
        headers = self._get_headers()
        headers.update({
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': self._sign_request(timestamp, method, path, body),
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.api_passphrase,
        })
        return headers

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    async def get_klines(
        self,
        symbol: str,
        period: str = '1h',
        limit: int = 100
    ) -> List[Dict]:
        """
        Get K-line/candlestick data for a tokenized stock

        Args:
            symbol: xStock symbol (e.g., 'TSLAx')
            period: Timeframe (1s, 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
            limit: Number of candles (max 1440)
        """
        token = XSTOCK_TOKENS.get(symbol)
        if not token:
            logger.error(f"Unknown symbol: {symbol}")
            return []

        payload = {
            'chain': 'sol',
            'contract': token['mint'],
            'period': period,
            'size': min(limit, 1440)
        }

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/market/v3/coin/getKline',
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        return data.get('data', [])
                    logger.warning(f"API error: {data.get('msg')}")
                else:
                    logger.warning(f"HTTP {resp.status} fetching klines for {symbol}")
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")

        return []

    async def get_token_info(self, symbol: str) -> Optional[Dict]:
        """
        Get transaction/market info for a tokenized stock

        Returns volume, buy/sell amounts, trader counts across timeframes
        """
        token = XSTOCK_TOKENS.get(symbol)
        if not token:
            return None

        payload = {
            'chain': 'sol',
            'contract': token['mint']
        }

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/market/v3/coin/getTxInfo',
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        return data.get('data')
        except Exception as e:
            logger.error(f"Error fetching token info: {e}")

        return None

    async def get_batch_token_info(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get market info for multiple tokens at once"""
        tokens = []
        for symbol in symbols:
            token = XSTOCK_TOKENS.get(symbol)
            if token:
                tokens.append({
                    'chain': 'sol',
                    'contract': token['mint']
                })

        if not tokens:
            return {}

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/market/v3/coin/batchGetTxInfo',
                json={'tokens': tokens}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        result = {}
                        for i, info in enumerate(data.get('data', [])):
                            if i < len(symbols):
                                result[symbols[i]] = info
                        return result
        except Exception as e:
            logger.error(f"Error fetching batch token info: {e}")

        return {}

    async def get_price(self, symbol: str) -> Optional[float]:
        """Get current price of a tokenized stock in USD"""
        # Try DexScreener first (most reliable)
        dex_data = await self.get_dexscreener_price(symbol)
        if dex_data and dex_data.get('price', 0) > 0:
            return dex_data['price']

        # Fallback to Bitget (requires partner code)
        klines = await self.get_klines(symbol, '1m', 1)
        if klines:
            return float(klines[-1].get('close', 0))

        # Last resort: Jupiter
        price = await self.get_jupiter_price(symbol)
        if price:
            return price

        return None

    # =========================================================================
    # JUPITER PUBLIC API (Fallback - No auth required)
    # =========================================================================

    async def get_jupiter_price(self, symbol: str) -> Optional[float]:
        """
        Get token price from Jupiter (public API, no auth needed)
        """
        token = XSTOCK_TOKENS.get(symbol)
        if not token:
            return None

        try:
            # Jupiter price API - returns USD price
            url = f"{JUPITER_PRICE_API}?ids={token['mint']}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price_data = data.get('data', {}).get(token['mint'])
                    if price_data:
                        return float(price_data.get('price', 0))
        except Exception as e:
            logger.debug(f"Jupiter price fetch failed for {symbol}: {e}")

        return None

    async def get_dexscreener_price(self, symbol: str) -> Optional[Dict]:
        """
        Get token price and data from DexScreener (public API, very reliable)
        Returns dict with price, volume, change data
        """
        token = XSTOCK_TOKENS.get(symbol)
        if not token:
            return None

        try:
            url = f"{DEXSCREENER_API}/{token['mint']}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get('pairs', [])
                    if pairs:
                        # Find the best USDC pair (highest liquidity)
                        usdc_pairs = [p for p in pairs if p.get('quoteToken', {}).get('symbol') == 'USDC']
                        if usdc_pairs:
                            best = max(usdc_pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0)))
                        else:
                            best = max(pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0)))

                        return {
                            'price': float(best.get('priceUsd', 0)),
                            'price_native': float(best.get('priceNative', 0)),
                            'volume_24h': float(best.get('volume', {}).get('h24', 0)),
                            'change_24h': float(best.get('priceChange', {}).get('h24', 0)),
                            'change_1h': float(best.get('priceChange', {}).get('h1', 0)),
                            'liquidity': float(best.get('liquidity', {}).get('usd', 0)),
                            'dex': best.get('dexId', 'unknown'),
                            'pair': best.get('pairAddress', ''),
                        }
        except Exception as e:
            logger.debug(f"DexScreener price fetch failed for {symbol}: {e}")

        return None

    async def get_dexscreener_prices_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get prices for multiple tokens from DexScreener
        Note: DexScreener doesn't have a batch endpoint, so we fetch individually
        """
        results = {}
        for symbol in symbols:
            data = await self.get_dexscreener_price(symbol)
            if data:
                results[symbol] = data
            await asyncio.sleep(0.1)  # Rate limiting
        return results

    async def get_jupiter_prices_batch(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get prices for multiple tokens from Jupiter
        """
        mints = []
        mint_to_symbol = {}
        for symbol in symbols:
            token = XSTOCK_TOKENS.get(symbol)
            if token:
                mints.append(token['mint'])
                mint_to_symbol[token['mint']] = symbol

        if not mints:
            return {}

        try:
            url = f"{JUPITER_PRICE_API}?ids={','.join(mints)}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prices = {}
                    for mint, price_data in data.get('data', {}).items():
                        symbol = mint_to_symbol.get(mint)
                        if symbol and price_data:
                            prices[symbol] = float(price_data.get('price', 0))
                    return prices
        except Exception as e:
            logger.debug(f"Jupiter batch price fetch failed: {e}")

        return {}

    async def get_jupiter_quote(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        slippage_bps: int = 100  # 1% = 100 basis points
    ) -> Optional[Dict]:
        """
        Get swap quote from Jupiter (public API)

        Args:
            from_token: 'USDC' or xStock symbol
            to_token: 'USDC' or xStock symbol
            amount: Amount of from_token
            slippage_bps: Slippage in basis points (100 = 1%)
        """
        # Resolve addresses
        if from_token == 'USDC':
            input_mint = USDC_SOL['mint']
            input_decimals = USDC_SOL['decimals']
        else:
            token = XSTOCK_TOKENS.get(from_token)
            if not token:
                return None
            input_mint = token['mint']
            input_decimals = token['decimals']

        if to_token == 'USDC':
            output_mint = USDC_SOL['mint']
        else:
            token = XSTOCK_TOKENS.get(to_token)
            if not token:
                return None
            output_mint = token['mint']

        # Convert to smallest unit
        amount_raw = int(amount * (10 ** input_decimals))

        try:
            url = (f"{JUPITER_QUOTE_API}"
                   f"?inputMint={input_mint}"
                   f"&outputMint={output_mint}"
                   f"&amount={amount_raw}"
                   f"&slippageBps={slippage_bps}")

            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('outAmount'):
                        return {
                            'inputMint': input_mint,
                            'outputMint': output_mint,
                            'inAmount': amount_raw,
                            'outAmount': int(data['outAmount']),
                            'priceImpactPct': float(data.get('priceImpactPct', 0)),
                            'routePlan': data.get('routePlan', []),
                            'slippageBps': slippage_bps,
                        }
                else:
                    logger.warning(f"Jupiter quote failed: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Jupiter quote error: {e}")

        return None

    async def refresh_all_prices(self) -> Dict[str, StockQuote]:
        """Refresh prices for all tracked xStocks using DexScreener public API"""
        symbols = list(XSTOCK_TOKENS.keys())

        # Use DexScreener API (most reliable)
        logger.info("Fetching prices from DexScreener...")
        dex_prices = await self.get_dexscreener_prices_batch(symbols)

        if dex_prices:
            logger.info(f"Got {len(dex_prices)} prices from DexScreener")
            for symbol, data in dex_prices.items():
                if data.get('price', 0) > 0:
                    self.prices[symbol] = StockQuote(
                        symbol=symbol,
                        price_usd=data['price'],
                        change_24h=data.get('change_24h', 0.0),
                        change_7d=0.0,
                        volume_24h=data.get('volume_24h', 0.0),
                        market_cap=0.0,
                        timestamp=datetime.now()
                    )
        else:
            # Fallback to Jupiter
            logger.info("DexScreener failed, trying Jupiter...")
            jupiter_prices = await self.get_jupiter_prices_batch(symbols)
            for symbol, price in jupiter_prices.items():
                if price > 0:
                    self.prices[symbol] = StockQuote(
                        symbol=symbol,
                        price_usd=price,
                        change_24h=0.0,
                        change_7d=0.0,
                        volume_24h=0.0,
                        market_cap=0.0,
                        timestamp=datetime.now()
                    )

        logger.info(f"Refreshed prices for {len(self.prices)} stocks")
        return self.prices

    # =========================================================================
    # SWAP / TRADING
    # =========================================================================

    async def get_swap_quote(
        self,
        from_token: str,  # 'USDC' or xStock symbol
        to_token: str,    # 'USDC' or xStock symbol
        amount: float,
        slippage: float = None
    ) -> Optional[SwapQuote]:
        """
        Get a quote for swapping tokens

        Args:
            from_token: Source token ('USDC' or xStock symbol like 'TSLAx')
            to_token: Target token ('USDC' or xStock symbol)
            amount: Amount of from_token to swap
            slippage: Max slippage percentage (default 1%)
        """
        slippage = slippage or self.default_slippage

        # Resolve token addresses
        if from_token == 'USDC':
            from_contract = USDC_SOL['mint']
            from_decimals = USDC_SOL['decimals']
        else:
            token = XSTOCK_TOKENS.get(from_token)
            if not token:
                logger.error(f"Unknown from_token: {from_token}")
                return None
            from_contract = token['mint']
            from_decimals = token['decimals']

        if to_token == 'USDC':
            to_contract = USDC_SOL['mint']
        else:
            token = XSTOCK_TOKENS.get(to_token)
            if not token:
                logger.error(f"Unknown to_token: {to_token}")
                return None
            to_contract = token['mint']

        # Convert amount to smallest unit
        from_amount = int(amount * (10 ** from_decimals))

        payload = {
            'fromChain': 'sol',
            'toChain': 'sol',
            'fromContract': from_contract,
            'toContract': to_contract,
            'fromAmount': str(from_amount),
            'estimateGas': True,
            'solMaxAccounts': 64
        }

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/swapx/pro/quote',
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        quote_data = data.get('data', {})

                        # Parse to_amount based on decimals
                        to_decimals = USDC_SOL['decimals'] if to_token == 'USDC' else 9
                        to_amount = float(quote_data.get('toAmount', 0)) / (10 ** to_decimals)

                        return SwapQuote(
                            from_token=from_token,
                            to_token=to_token,
                            from_amount=amount,
                            to_amount=to_amount,
                            price=to_amount / amount if amount > 0 else 0,
                            slippage=float(quote_data.get('slippage', slippage)),
                            market=quote_data.get('market', 'unknown'),
                            gas_estimate=float(quote_data.get('gasLimit', 0)),
                            expires_at=datetime.now() + timedelta(seconds=60)
                        )
                    else:
                        logger.warning(f"Quote error: {data.get('msg')}")
                elif resp.status == 403:
                    logger.error("Forbidden - Partner code required or not whitelisted")
                elif resp.status == 429:
                    logger.warning("Rate limited - too many requests")
                else:
                    logger.warning(f"HTTP {resp.status} getting quote")
        except Exception as e:
            logger.error(f"Error getting swap quote: {e}")

        return None

    async def get_swap_calldata(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        slippage: float = None,
        recipient: str = None
    ) -> Optional[Dict]:
        """
        Get calldata for executing a swap

        Returns transaction data ready for signing and submission
        """
        if not self.wallet_address:
            logger.error("Wallet address not configured")
            return None

        slippage = slippage or self.default_slippage
        recipient = recipient or self.wallet_address

        # First get a quote
        quote = await self.get_swap_quote(from_token, to_token, amount, slippage)
        if not quote:
            return None

        # Resolve addresses
        if from_token == 'USDC':
            from_contract = USDC_SOL['mint']
            from_decimals = USDC_SOL['decimals']
        else:
            token = XSTOCK_TOKENS.get(from_token)
            from_contract = token['mint']
            from_decimals = token['decimals']

        if to_token == 'USDC':
            to_contract = USDC_SOL['mint']
        else:
            token = XSTOCK_TOKENS.get(to_token)
            to_contract = token['mint']

        from_amount = int(amount * (10 ** from_decimals))

        payload = {
            'fromChain': 'sol',
            'toChain': 'sol',
            'fromContract': from_contract,
            'toContract': to_contract,
            'fromAmount': str(from_amount),
            'fromAddress': self.wallet_address,
            'toAddress': recipient,
            'market': quote.market,
            'slippage': str(slippage),
            'deadline': 600,  # 10 minutes
        }

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/swapx/pro/swap',
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        return data.get('data')
                    logger.warning(f"Swap error: {data.get('msg')}")
                else:
                    logger.warning(f"HTTP {resp.status} getting swap calldata")
        except Exception as e:
            logger.error(f"Error getting swap calldata: {e}")

        return None

    async def send_transaction(self, signed_tx: str, order_id: str) -> Optional[str]:
        """
        Submit a signed transaction to the network

        Args:
            signed_tx: Base64 encoded signed transaction
            order_id: Order ID from get_swap_calldata

        Returns:
            Transaction hash if successful
        """
        payload = {
            'chain': 'sol',
            'txs': [{
                'id': order_id,
                'rawTx': signed_tx,
                'from': self.wallet_address,
            }]
        }

        try:
            async with self.session.post(
                f'{self.base_url}/bgw-pro/swapx/pro/send',
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '00000':
                        results = data.get('data', [])
                        if results and results[0].get('txHash'):
                            return results[0]['txHash']
                        logger.warning(f"Send failed: {results}")
                else:
                    logger.warning(f"HTTP {resp.status} sending transaction")
        except Exception as e:
            logger.error(f"Error sending transaction: {e}")

        return None

    # =========================================================================
    # PORTFOLIO MANAGEMENT
    # =========================================================================

    async def buy_stock(
        self,
        symbol: str,
        usd_amount: float,
        slippage: float = None
    ) -> Optional[Dict]:
        """
        Buy a tokenized stock with USDC

        Args:
            symbol: xStock symbol (e.g., 'TSLAx')
            usd_amount: Amount of USDC to spend
            slippage: Max slippage percentage
        """
        if usd_amount < self.min_trade_usd:
            logger.warning(f"Amount ${usd_amount} below minimum ${self.min_trade_usd}")
            return None

        if usd_amount > self.max_trade_usd:
            logger.warning(f"Amount ${usd_amount} above maximum ${self.max_trade_usd}")
            return None

        logger.info(f"Buying {symbol} with ${usd_amount} USDC")

        # Get quote first
        quote = await self.get_swap_quote('USDC', symbol, usd_amount, slippage)
        if not quote:
            logger.error("Failed to get quote")
            return None

        logger.info(f"Quote: {usd_amount} USDC -> {quote.to_amount:.6f} {symbol} @ ${quote.price:.4f}")

        # Get calldata
        calldata = await self.get_swap_calldata('USDC', symbol, usd_amount, slippage)
        if not calldata:
            logger.error("Failed to get swap calldata")
            return None

        # Note: Transaction signing requires solana-py or similar
        # This would be implemented with actual wallet integration
        logger.info(f"Swap calldata received, order_id: {calldata.get('id')}")

        return {
            'action': 'buy',
            'symbol': symbol,
            'usd_amount': usd_amount,
            'expected_amount': quote.to_amount,
            'price': quote.price,
            'market': quote.market,
            'order_id': calldata.get('id'),
            'status': 'pending_signature'
        }

    async def sell_stock(
        self,
        symbol: str,
        amount: float,
        slippage: float = None
    ) -> Optional[Dict]:
        """
        Sell a tokenized stock for USDC

        Args:
            symbol: xStock symbol
            amount: Amount of stock tokens to sell
            slippage: Max slippage percentage
        """
        logger.info(f"Selling {amount} {symbol} for USDC")

        quote = await self.get_swap_quote(symbol, 'USDC', amount, slippage)
        if not quote:
            return None

        logger.info(f"Quote: {amount} {symbol} -> ${quote.to_amount:.2f} USDC @ ${quote.price:.4f}")

        calldata = await self.get_swap_calldata(symbol, 'USDC', amount, slippage)
        if not calldata:
            return None

        return {
            'action': 'sell',
            'symbol': symbol,
            'amount': amount,
            'expected_usd': quote.to_amount,
            'price': quote.price,
            'market': quote.market,
            'order_id': calldata.get('id'),
            'status': 'pending_signature'
        }

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def _load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    # Load positions
                    for symbol, pos in data.get('positions', {}).items():
                        self.positions[symbol] = Position(**pos)
                    logger.info(f"Loaded {len(self.positions)} positions from state")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        """Save state to file"""
        try:
            data = {
                'positions': {
                    symbol: {
                        'symbol': pos.symbol,
                        'amount': pos.amount,
                        'avg_price': pos.avg_price,
                        'current_price': pos.current_price,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'unrealized_pnl_pct': pos.unrealized_pnl_pct,
                    }
                    for symbol, pos in self.positions.items()
                },
                'updated_at': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state: {e}")

    # =========================================================================
    # SCANNING / ANALYSIS
    # =========================================================================

    async def scan_opportunities(self, min_volume: float = 10000) -> List[Dict]:
        """
        Scan xStocks for trading opportunities

        Returns top stocks by momentum/volume
        """
        opportunities = []

        await self.refresh_all_prices()

        for symbol, quote in self.prices.items():
            if quote.volume_24h < min_volume:
                continue

            # Simple momentum score
            momentum = quote.change_24h

            opportunities.append({
                'symbol': symbol,
                'price': quote.price_usd,
                'change_24h': quote.change_24h,
                'volume_24h': quote.volume_24h,
                'momentum': momentum,
                'sector': XSTOCK_TOKENS.get(symbol, {}).get('sector', 'unknown'),
                'signal': 'buy' if momentum > 2 else ('sell' if momentum < -2 else 'hold')
            })

        # Sort by momentum
        opportunities.sort(key=lambda x: x['momentum'], reverse=True)

        return opportunities


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Bitget Onchain Stock Trading Service')
    parser.add_argument('--prices', action='store_true', help='Fetch all xStock prices')
    parser.add_argument('--quote', nargs=3, metavar=('FROM', 'TO', 'AMOUNT'),
                       help='Get swap quote (e.g., USDC TSLAx 100)')
    parser.add_argument('--scan', action='store_true', help='Scan for opportunities')
    parser.add_argument('--klines', nargs=2, metavar=('SYMBOL', 'PERIOD'),
                       help='Get klines (e.g., TSLAx 1h)')

    args = parser.parse_args()

    async with BitgetOnchainService() as service:
        if args.prices:
            print("\n" + "="*60)
            print("xSTOCKS PRICES (Bitget Onchain / Solana)")
            print("="*60)

            prices = await service.refresh_all_prices()
            for symbol, quote in sorted(prices.items()):
                print(f"  {symbol:8} ${quote.price_usd:>10.2f}  "
                      f"24h: {quote.change_24h:>+6.2f}%  "
                      f"Vol: ${quote.volume_24h:>12,.0f}")

        elif args.quote:
            from_token, to_token, amount = args.quote
            amount = float(amount)

            print(f"\nGetting quote: {amount} {from_token} -> {to_token}")
            quote = await service.get_swap_quote(from_token, to_token, amount)

            if quote:
                print(f"\n  Input:  {quote.from_amount:.6f} {quote.from_token}")
                print(f"  Output: {quote.to_amount:.6f} {quote.to_token}")
                print(f"  Price:  ${quote.price:.4f}")
                print(f"  Market: {quote.market}")
                print(f"  Slippage: {quote.slippage}%")
            else:
                print("  Failed to get quote (partner code may be required)")

        elif args.scan:
            print("\n" + "="*60)
            print("xSTOCKS OPPORTUNITIES SCAN")
            print("="*60)

            opportunities = await service.scan_opportunities()
            for opp in opportunities[:10]:
                signal_icon = {'buy': '+', 'sell': '-', 'hold': '='}[opp['signal']]
                print(f"  {signal_icon} {opp['symbol']:8} ${opp['price']:>8.2f}  "
                      f"24h: {opp['change_24h']:>+6.2f}%  "
                      f"[{opp['sector']}]")

        elif args.klines:
            symbol, period = args.klines
            print(f"\nFetching {period} klines for {symbol}...")

            klines = await service.get_klines(symbol, period, 20)
            if klines:
                print(f"\nLast {len(klines)} candles:")
                for k in klines[-10:]:
                    print(f"  {k.get('timestamp', 'N/A')} | "
                          f"O: {k.get('open', 0):>8.2f} | "
                          f"H: {k.get('high', 0):>8.2f} | "
                          f"L: {k.get('low', 0):>8.2f} | "
                          f"C: {k.get('close', 0):>8.2f}")
            else:
                print("  No data returned")

        else:
            print("\n" + "="*60)
            print("BITGET ONCHAIN SERVICE - Tokenized Stock Trading")
            print("="*60)
            print("\nAvailable xStocks:")
            for symbol, info in XSTOCK_TOKENS.items():
                print(f"  {symbol:8} - {info['name']} [{info['sector']}]")
            print("\nUsage:")
            print("  --prices        Fetch all xStock prices")
            print("  --quote USDC TSLAx 100   Get swap quote")
            print("  --scan          Scan for opportunities")
            print("  --klines TSLAx 1h        Get candlestick data")


if __name__ == "__main__":
    asyncio.run(main())
