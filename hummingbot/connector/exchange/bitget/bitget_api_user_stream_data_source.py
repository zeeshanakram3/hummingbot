import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.bitget import bitget_constants as CONSTANTS
from hummingbot.connector.exchange.bitget.bitget_auth import BitgetAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest, WSPlainTextRequest, WSResponse
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.bitget.bitget_exchange import BitgetExchange


class BitgetAPIUserStreamDataSource(UserStreamTrackerDataSource):

    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 3600  # (1 hour) Recommended to Ping/Update listen key to keep connection alive

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: BitgetAuth,
        trading_pairs: List[str],
        connector: "BitgetExchange",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__()
        self._auth: BitgetAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._api_factory = api_factory
        self._connector = connector
        self._trading_pairs: List[str] = trading_pairs

        self._pong_response_event: Optional[asyncio.Event] = None

    async def _authenticate(self, ws: WSAssistant):
        """
        Authenticates user to websocket
        """
        auth_payload: List[str] = self._auth.get_ws_auth_payload()
        payload = {"op": "login", "args": auth_payload}
        login_request: WSJSONRequest = WSJSONRequest(payload=payload)
        await ws.send(login_request)
        response: WSResponse = await ws.receive()
        message = response.data

        if message["event"] != "login" and message["code"] != "0":
            self.logger().error("Error authenticating the private websocket connection")
            raise IOError("Private websocket connection authentication failed")

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates an instance of WSAssistant connected to the exchange
        """

        ws: WSAssistant = await self._get_ws_assistant()
        url = f"{CONSTANTS.WSS_URL_PRIVATE.format(self._domain)}"
        await ws.connect(ws_url=url, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        await self._authenticate(ws)
        self.logger().info("Connected to Bitget Private WebSocket")
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        try:
            payloads = []

            # Subscribe to order channel
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                payloads.append(
                    {
                        "instType": "SPOT",
                        "channel": CONSTANTS.WS_SUBSCRIPTION_ORDERS_CHANNEL_NAME,
                        "instId": symbol,
                    }
                )

            # Subscribe to account channel
            payloads.append(
                {"instType": "SPOT", "channel": CONSTANTS.WS_SUBSCRIPTION_ACCOUNT_CHANNEL_NAME, "coin": "default"}
            )

            # Subscribe to trade channel
            payloads.append(
                {"instType": "SPOT", "channel": CONSTANTS.WS_SUBSCRIPTION_TRADE_CHANNEL_NAME, "instId": "default"}
            )

            payload = {"op": "subscribe", "args": payloads}
            subscription_request = WSJSONRequest(payload)
            await websocket_assistant.send(subscription_request)

            self.logger().info("Subscribed to private account, trade and orders channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error occurred subscribing to account, position and orders channels...")
            raise

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant, queue: asyncio.Queue):
        while True:
            try:
                await asyncio.wait_for(
                    super()._process_websocket_messages(websocket_assistant=websocket_assistant, queue=queue),
                    timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL,
                )
            except asyncio.TimeoutError:
                if self._pong_response_event and not self._pong_response_event.is_set():
                    # The PONG response for the previous PING request was never received
                    raise IOError("The user stream channel is unresponsive (pong response not received)")
                self._pong_response_event = asyncio.Event()
                await self._send_ping(websocket_assistant=websocket_assistant)

    async def _process_event_message(self, event_message: Dict[str, Any], queue: asyncio.Queue):
        if event_message == CONSTANTS.WS_PONG_RESPONSE:
            if self._pong_response_event:
                self._pong_response_event.set()
        elif "event" in event_message:
            if event_message["event"] == "error":
                raise IOError(f"Private channel subscription failed ({event_message})")
        else:
            await super()._process_event_message(event_message=event_message, queue=queue)

    async def _get_ws_assistant(self) -> WSAssistant:
        if self._ws_assistant is None:
            self._ws_assistant = await self._api_factory.get_ws_assistant()
        return self._ws_assistant

    async def _send_ping(self, websocket_assistant: WSAssistant):
        ping_request = WSPlainTextRequest(payload=CONSTANTS.WS_PING_REQUEST)
        await websocket_assistant.send(ping_request)
