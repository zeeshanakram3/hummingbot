import asyncio
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.biconomy import biconomy_constants as CONSTANTS, biconomy_web_utils as web_utils
from hummingbot.connector.exchange.biconomy.biconomy_order_book import BiconomyOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.biconomy.biconomy_exchange import BiconomyExchange


class BiconomyAPIOrderBookDataSource(OrderBookTrackerDataSource):
    ONE_HOUR = 60 * 60

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "BiconomyExchange",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._trade_messages_queue_key = CONSTANTS.WS_SUBSCRIPTION_TRADES_CHANNEL_NAME
        self._diff_messages_queue_key = CONSTANTS.WS_SUBSCRIPTION_DIFF_CHANNEL_NAME
        self._domain = domain
        self._api_factory = api_factory
        self._ping_task: Optional[asyncio.Task] = None

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved

        :return: the response from the exchange (JSON dictionary)
        """
        params = {
            "symbol": await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
            "limit": "100",
        }

        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.SNAPSHOT_PATH_URL,
            headers={"Content-Type": "application/json"},
        )

        return data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        :param ws: the websocket assistant used to connect to the exchange
        """
        try:
            trade_params = []
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                trade_params.append(symbol)

                payload = {"method": "depth.subscribe", "params": [symbol, 100, "0"], "id": CONSTANTS.DIFF_STREAM_ID}
                subscribe_orderbook_request: WSJSONRequest = WSJSONRequest(payload=payload)
                await ws.send(subscribe_orderbook_request)

            payload = {"method": "deals.subscribe", "params": trade_params, "id": CONSTANTS.TRADE_STREAM_ID}
            subscribe_trade_request: WSJSONRequest = WSJSONRequest(payload=payload)

            await ws.send(subscribe_trade_request)

            self.logger().info("Subscribed to public order book and trades channels...")

            # Start a task to periodically send ping messages
            self._ping_task = asyncio.create_task(self._send_ping_periodically(ws))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...", exc_info=True
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(
            ws_url=CONSTANTS.WSS_URL_PUBLIC.format(self._domain), ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL
        )
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = BiconomyOrderBook.snapshot_message_from_exchange(
            snapshot, snapshot_timestamp, metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        if "method" in raw_message and raw_message["method"] == CONSTANTS.WS_SUBSCRIPTION_TRADES_CHANNEL_NAME:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(
                symbol=raw_message["params"][0]
            )
            diff_timestamp: float = time.time()
            for single_msg in raw_message["params"][1]:
                trade_message = BiconomyOrderBook.trade_message_from_exchange(
                    single_msg, timestamp=diff_timestamp, metadata={"trading_pair": trading_pair}
                )
                message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        if "method" in raw_message and raw_message["method"] == CONSTANTS.WS_SUBSCRIPTION_DIFF_CHANNEL_NAME:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(
                symbol=raw_message["params"][2]
            )

            diff_msg = raw_message["params"][1]
            diff_timestamp: float = time.time()
            order_book_message: OrderBookMessage = BiconomyOrderBook.diff_message_from_exchange(
                diff_msg, diff_timestamp, {"trading_pair": trading_pair}
            )
            message_queue.put_nowait(order_book_message)

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        channel = ""
        if "method" in event_message:
            event_type = event_message["method"]
            channel = (
                self._diff_messages_queue_key
                if CONSTANTS.WS_SUBSCRIPTION_DIFF_CHANNEL_NAME in event_type
                else self._trade_messages_queue_key
            )
        return channel

    async def _send_ping_periodically(self, ws: WSAssistant):
        while True:
            try:
                await asyncio.sleep(5)
                await self._send_ping(ws)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger().warning("Error sending ping message.", exc_info=True)

    async def _send_ping(self, websocket_assistant: WSAssistant):
        payload = {"method": "server.ping", "params": [], "id": 5160}
        ping_request: WSJSONRequest = WSJSONRequest(payload=payload)
        await websocket_assistant.send(ping_request)

    async def _on_order_stream_interruption(self, websocket_assistant: Optional[WSAssistant] = None):
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()

        await super()._on_order_stream_interruption(websocket_assistant=websocket_assistant)
