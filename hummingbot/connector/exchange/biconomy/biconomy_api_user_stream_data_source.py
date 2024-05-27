import asyncio
from typing import TYPE_CHECKING, List, Optional

from hummingbot.connector.exchange.biconomy import biconomy_constants as CONSTANTS
from hummingbot.connector.exchange.biconomy.biconomy_auth import BiconomyAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.biconomy.biconomy_exchange import BiconomyExchange


class BiconomyAPIUserStreamDataSource(UserStreamTrackerDataSource):

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: BiconomyAuth,
        trading_pairs: List[str],
        connector: "BiconomyExchange",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__()
        self._auth: BiconomyAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._api_factory = api_factory
        self._connector = connector
        self._trading_pairs: List[str] = trading_pairs

        self._pong_response_event: Optional[asyncio.Event] = None

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates an instance of WSAssistant connected to the exchange
        """

        ws = await self._get_ws_assistant()
        await ws.connect(
            ws_url=CONSTANTS.WSS_URL_PUBLIC.format(self._domain), ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL
        )
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.

        Biconomy does not require any channel subscription.
        """
        pass

    async def _get_ws_assistant(self) -> WSAssistant:
        if self._ws_assistant is None:
            self._ws_assistant = await self._api_factory.get_ws_assistant()
        return self._ws_assistant
