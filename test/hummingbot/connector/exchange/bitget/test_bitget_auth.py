import asyncio
from unittest import TestCase
from unittest.mock import MagicMock

from typing_extensions import Awaitable

import hummingbot.connector.exchange.bitget.bitget_constants as CONSTANTS
from hummingbot.connector.exchange.bitget import bitget_web_utils as web_utils
from hummingbot.connector.exchange.bitget.bitget_auth import BitgetAuth
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest


class BitgetAuthTests(TestCase):

    def setUp(self) -> None:
        self._api_key = "testApiKey"
        self._secret = "testSecret"
        self._passphrase = "testPassphrase"

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def test_rest_authenticate(self):
        now = 1234567890.000
        mock_time_provider = MagicMock()
        mock_time_provider.time.return_value = now

        params = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "orderType": "limit",
            "force": "gtc",
            "price": "23222.5",
            "size": "1",
            "clientOid": "121211212122",
        }

        auth = BitgetAuth(
            api_key=self._api_key,
            secret_key=self._secret,
            passphrase=self._passphrase,
            time_provider=mock_time_provider,
        )
        url = web_utils.private_rest_url(CONSTANTS.PLACE_ORDER_PATH_URL, CONSTANTS.DEFAULT_DOMAIN)
        request = RESTRequest(method=RESTMethod.POST, url=url, data=params, is_auth_required=True)
        configured_request = self.async_run_with_timeout(auth.rest_authenticate(request))

        print(configured_request)

        self.assertEqual(configured_request.params, None)
        self.assertEqual(self._api_key, configured_request.headers["ACCESS-KEY"])
        self.assertEqual(self._api_key, configured_request.headers["ACCESS-KEY"])
