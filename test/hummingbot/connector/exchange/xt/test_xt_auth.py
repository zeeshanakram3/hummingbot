import asyncio
import hashlib
import hmac
import json
from copy import copy
from unittest import TestCase
from unittest.mock import MagicMock
from urllib.parse import urlencode

from typing_extensions import Awaitable

import hummingbot.connector.exchange.xt.xt_constants as CONSTANTS
from hummingbot.connector.exchange.xt import xt_web_utils as web_utils
from hummingbot.connector.exchange.xt.xt_auth import XtAuth
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest


class XtAuthTests(TestCase):

    def setUp(self) -> None:
        self._api_key = "testApiKey"
        self._secret = "testSecret"

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def test_rest_authenticate(self):
        now = 1234567890.000
        mock_time_provider = MagicMock()
        mock_time_provider.time.return_value = now

        params = {
            "symbol": "btc_usdt",
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": 1,
            "price": "0.1",
            "bizType": "SPOT",
        }
        full_params = copy(params)

        auth = XtAuth(api_key=self._api_key, secret_key=self._secret, time_provider=mock_time_provider)
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL, CONSTANTS.DEFAULT_DOMAIN)
        request = RESTRequest(method=RESTMethod.POST, url=url, data=json.dumps(params), is_auth_required=True)
        configured_request = self.async_run_with_timeout(auth.rest_authenticate(request))

        request_headers = auth.header_for_authentication()
        X = urlencode(dict(sorted(request_headers.items(), key=lambda kv: (kv[0], kv[1]))))
        Y = "#{}#{}#{}".format(RESTMethod.POST, "/v4/order", json.dumps(full_params))

        expected_signature = hmac.new(
            self._secret.encode("utf-8"), f"{X + Y}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        # self.assertEqual(now * 1e3, configured_request.headers["timestamp"])
        self.assertEqual(expected_signature, configured_request.headers["validate-signature"])
        self.assertEqual(self._api_key, configured_request.headers["validate-appkey"])
