#!/usr/bin/env python3
"""
Grok Recommendation #5: WebSocket Event-Driven Architecture
Replaces polling with WebSocket event streams for real-time updates.
"""
import asyncio
import json
import websockets
import hmac
import hashlib
import base64
import time
import os
from typing import Dict, Callable, Optional, List, Any
from dataclasses import dataclass
from enum import Enum
import logging
import threading
from queue import Queue
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventType(Enum):
    """WebSocket event types"""
    POSITION_UPDATE = "position.update"
    ORDER_UPDATE = "order.update"
    BALANCE_UPDATE = "balance.update"
    TICKER = "ticker"
    TRADE = "trade"
    KLINE = "kline"
    MARK_PRICE = "mark_price"
    FUNDING_RATE = "funding_rate"


@dataclass
class PositionEvent:
    """Position update event"""
    symbol: str
    side: str
    contracts: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    liquidation_price: float
    margin: float
    timestamp: int


@dataclass
class OrderEvent:
    """Order update event"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    amount: float
    filled: float
    status: str
    timestamp: int


class BitgetWebSocketClient:
    """
    WebSocket client for Bitget exchange.

    Supports both public and private channels.
    """

    PUBLIC_WS_URL = "wss://ws.bitget.com/v2/ws/public"
    PRIVATE_WS_URL = "wss://ws.bitget.com/v2/ws/private"

    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        passphrase: str = None
    ):
        self.api_key = api_key or os.getenv('BITGET_API_KEY')
        self.api_secret = api_secret or os.getenv('BITGET_API_SECRET')
        self.passphrase = passphrase or os.getenv('BITGET_API_PASSPHRASE')

        self._public_ws = None
        self._private_ws = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

        # Event handlers
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

        # Event queue for sync consumers
        self.event_queue: Queue = Queue(maxsize=1000)

        # Subscribed channels
        self._subscriptions: List[Dict] = []

    def _generate_signature(self, timestamp: str) -> str:
        """Generate authentication signature"""
        message = f"{timestamp}GET/user/verify"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()

    async def _authenticate(self, ws):
        """Authenticate private WebSocket connection"""
        timestamp = str(int(time.time()))
        signature = self._generate_signature(timestamp)

        auth_message = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": signature
            }]
        }

        await ws.send(json.dumps(auth_message))
        response = await ws.recv()
        data = json.loads(response)

        if data.get('event') == 'login' and data.get('code') == '0':
            logger.info("WebSocket authenticated successfully")
            return True
        else:
            logger.error(f"WebSocket authentication failed: {data}")
            return False

    async def _subscribe(self, ws, channels: List[Dict]):
        """Subscribe to channels"""
        subscribe_message = {
            "op": "subscribe",
            "args": channels
        }
        await ws.send(json.dumps(subscribe_message))
        self._subscriptions.extend(channels)
        logger.info(f"Subscribed to {len(channels)} channels")

    def on(self, event_type: str, handler: Callable):
        """Register event handler"""
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable = None):
        """Remove event handler"""
        if handler:
            self._handlers[event_type].remove(handler)
        else:
            self._handlers[event_type] = []

    async def _process_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Handle ping/pong
            if data.get('event') == 'ping':
                return

            # Handle subscription confirmations
            if data.get('event') == 'subscribe':
                logger.debug(f"Subscription confirmed: {data}")
                return

            # Handle data updates
            if 'data' in data:
                channel = data.get('arg', {}).get('channel', '')
                inst_type = data.get('arg', {}).get('instType', '')

                event_type = self._map_channel_to_event(channel)
                event_data = data['data']

                # Process and dispatch event
                for item in event_data if isinstance(event_data, list) else [event_data]:
                    processed = self._process_event_data(event_type, item, inst_type)

                    # Call registered handlers
                    for handler in self._handlers.get(event_type, []):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(processed)
                            else:
                                handler(processed)
                        except Exception as e:
                            logger.error(f"Handler error: {e}")

                    # Add to queue for sync consumers
                    if not self.event_queue.full():
                        self.event_queue.put_nowait({
                            'type': event_type,
                            'data': processed,
                            'timestamp': time.time()
                        })

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")

    def _map_channel_to_event(self, channel: str) -> str:
        """Map Bitget channel to event type"""
        mapping = {
            'positions': EventType.POSITION_UPDATE.value,
            'orders': EventType.ORDER_UPDATE.value,
            'account': EventType.BALANCE_UPDATE.value,
            'ticker': EventType.TICKER.value,
            'trade': EventType.TRADE.value,
            'candle': EventType.KLINE.value,
            'mark-price': EventType.MARK_PRICE.value,
            'funding-rate': EventType.FUNDING_RATE.value,
        }

        for key, value in mapping.items():
            if key in channel.lower():
                return value

        return channel

    def _process_event_data(self, event_type: str, data: Dict, inst_type: str) -> Any:
        """Process raw event data into typed objects"""
        if event_type == EventType.POSITION_UPDATE.value:
            return PositionEvent(
                symbol=data.get('instId', ''),
                side=data.get('posSide', ''),
                contracts=float(data.get('pos', 0)),
                entry_price=float(data.get('avgPx', 0)),
                mark_price=float(data.get('markPx', 0)),
                unrealized_pnl=float(data.get('upl', 0)),
                leverage=int(float(data.get('lever', 1))),
                liquidation_price=float(data.get('liqPx', 0)),
                margin=float(data.get('margin', 0)),
                timestamp=int(data.get('uTime', time.time() * 1000))
            )

        elif event_type == EventType.ORDER_UPDATE.value:
            return OrderEvent(
                order_id=data.get('ordId', ''),
                symbol=data.get('instId', ''),
                side=data.get('side', ''),
                order_type=data.get('ordType', ''),
                price=float(data.get('px', 0)),
                amount=float(data.get('sz', 0)),
                filled=float(data.get('fillSz', 0)),
                status=data.get('state', ''),
                timestamp=int(data.get('uTime', time.time() * 1000))
            )

        return data

    async def _connection_loop(self, ws_url: str, is_private: bool = False):
        """Main connection loop with reconnection"""
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    self._reconnect_attempts = 0

                    # Authenticate if private
                    if is_private:
                        if not await self._authenticate(ws):
                            await asyncio.sleep(5)
                            continue

                        # Subscribe to private channels
                        await self._subscribe(ws, [
                            {"instType": "USDT-FUTURES", "channel": "positions", "instId": "default"},
                            {"instType": "USDT-FUTURES", "channel": "orders", "instId": "default"},
                            {"instType": "USDT-FUTURES", "channel": "account", "coin": "USDT"}
                        ])

                    if is_private:
                        self._private_ws = ws
                    else:
                        self._public_ws = ws

                    logger.info(f"{'Private' if is_private else 'Public'} WebSocket connected")

                    # Ping loop
                    async def ping_loop():
                        while self._running:
                            try:
                                await ws.send('ping')
                                await asyncio.sleep(20)
                            except:
                                break

                    asyncio.create_task(ping_loop())

                    # Message loop
                    async for message in ws:
                        if message == 'pong':
                            continue
                        await self._process_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            # Reconnection logic
            if self._running:
                self._reconnect_attempts += 1
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached")
                    break

                wait_time = min(30, 2 ** self._reconnect_attempts)
                logger.info(f"Reconnecting in {wait_time}s (attempt {self._reconnect_attempts})")
                await asyncio.sleep(wait_time)

    async def start(self):
        """Start WebSocket connections"""
        self._running = True

        # Start both public and private connections
        await asyncio.gather(
            self._connection_loop(self.PRIVATE_WS_URL, is_private=True),
            # self._connection_loop(self.PUBLIC_WS_URL, is_private=False)
        )

    def start_background(self):
        """Start WebSocket in background thread"""
        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        logger.info("WebSocket started in background")

    async def stop(self):
        """Stop WebSocket connections"""
        self._running = False

        if self._private_ws:
            await self._private_ws.close()
        if self._public_ws:
            await self._public_ws.close()

        logger.info("WebSocket connections closed")

    def get_next_event(self, timeout: float = 1.0) -> Optional[Dict]:
        """Get next event from queue (sync interface)"""
        try:
            return self.event_queue.get(timeout=timeout)
        except:
            return None


class EventDrivenPositionMonitor:
    """
    Event-driven position monitor using WebSocket.

    Replaces polling-based monitoring with real-time events.
    """

    def __init__(self, ws_client: BitgetWebSocketClient):
        self.ws_client = ws_client
        self.positions: Dict[str, PositionEvent] = {}
        self.zone_handlers: Dict[str, Callable] = {}

        # Register position update handler
        self.ws_client.on(EventType.POSITION_UPDATE.value, self._on_position_update)

    def _on_position_update(self, event: PositionEvent):
        """Handle position update event"""
        symbol = event.symbol

        # Store latest position
        self.positions[symbol] = event

        # Calculate zone
        if event.contracts > 0:
            upnl_pct = (event.unrealized_pnl / event.margin * 100) if event.margin > 0 else 0

            zone = self._determine_zone(upnl_pct, event.unrealized_pnl)

            logger.info(f"📊 {symbol}: UPNL=${event.unrealized_pnl:.4f} ({upnl_pct:.1f}%) | Zone: {zone}")

            # Call zone handler if registered
            if zone in self.zone_handlers:
                self.zone_handlers[zone](symbol, event, upnl_pct)

    def _determine_zone(self, upnl_pct: float, upnl_usd: float) -> str:
        """Determine position zone"""
        if upnl_usd > 0.15:
            if upnl_pct > 5:
                return 'PROFIT_TAKING'
            return 'NEUTRAL'
        elif upnl_usd < -0.15:
            if upnl_pct < -25:
                return 'AVERAGING'
            if upnl_pct < -90:
                return 'STOP_LOSS'
            return 'NEUTRAL'
        return 'NEUTRAL'

    def on_zone(self, zone: str, handler: Callable):
        """Register zone transition handler"""
        self.zone_handlers[zone] = handler

    def get_position(self, symbol: str) -> Optional[PositionEvent]:
        """Get current position"""
        return self.positions.get(symbol)


# Singleton
_ws_client: Optional[BitgetWebSocketClient] = None

def get_websocket_client() -> BitgetWebSocketClient:
    """Get singleton WebSocket client"""
    global _ws_client
    if _ws_client is None:
        _ws_client = BitgetWebSocketClient()
    return _ws_client


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("WEBSOCKET EVENT-DRIVEN DEMO")
    print("=" * 60)

    # Note: Real WebSocket requires valid API credentials
    # This is a demonstration of the architecture

    async def position_handler(event: PositionEvent):
        print(f"Position Update: {event.symbol}")
        print(f"  Contracts: {event.contracts}")
        print(f"  UPNL: ${event.unrealized_pnl}")

    async def order_handler(event: OrderEvent):
        print(f"Order Update: {event.order_id}")
        print(f"  Status: {event.status}")

    # Create client
    client = BitgetWebSocketClient()

    # Register handlers
    client.on(EventType.POSITION_UPDATE.value, position_handler)
    client.on(EventType.ORDER_UPDATE.value, order_handler)

    print("\nWebSocket client configured with handlers:")
    print(f"  - Position updates: {len(client._handlers.get(EventType.POSITION_UPDATE.value, []))} handlers")
    print(f"  - Order updates: {len(client._handlers.get(EventType.ORDER_UPDATE.value, []))} handlers")

    # In production, you would call:
    # client.start_background()  # or await client.start()

    print("\nTo start WebSocket in production:")
    print("  client.start_background()")
    print("  # or")
    print("  await client.start()")
