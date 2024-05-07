import base64
import hmac
import time
from typing import Any, Dict, List
from urllib.parse import urlencode

from hummingbot.connector.exchange.bitget import bitget_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class BitgetAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, passphrase: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        path = request.url.split(CONSTANTS.DEFAULT_DOMAIN)[1]

        params_str = (
            "?" + urlencode(dict(sorted(request.params.items(), key=lambda kv: (kv[0], kv[1]))), safe=",")
            if request.params is not None
            else request.params
        )

        if request.method == RESTMethod.GET:
            headers = self.add_auth_to_headers(method=request.method, path=path, params_str=params_str)
        else:
            headers = self.add_auth_to_headers(method=request.method, path=path, body_str=request.data)

        if request.headers is not None:
            headers.update(request.headers)
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. XT does not use this
        functionality
        """
        return request  # pass-through

    def get_ws_auth_payload(self) -> List[Dict[str, Any]]:
        """
        Generates a dictionary with all required information for the authentication process
        :return: a dictionary of authentication info including the request signature
        """
        timestamp = str(int(self.time_provider.time()))
        signature = self._generate_signature(self._pre_hash(timestamp, "GET", CONSTANTS.PRIVATE_WS_LOGIN_PATH))
        auth_info = [{"apiKey": self.api_key, "passphrase": self.passphrase, "timestamp": timestamp, "sign": signature}]
        return auth_info

    def add_auth_to_headers(self, method: RESTMethod, path: str, params_str: str = None, body_str: str = None):
        headers = {}

        timestamp = str(int(time.time() * 1000))

        pre_hash = self._pre_hash(timestamp, method.value, path, params_str, body_str)

        signature = self._generate_signature(pre_hash)

        headers["ACCESS-SIGN"] = signature
        headers["ACCESS-KEY"] = self.api_key
        headers["ACCESS-PASSPHRASE"] = self.passphrase
        headers["ACCESS-TIMESTAMP"] = timestamp

        headers["Content-Type"] = (
            CONSTANTS.XT_VALIDATE_CONTENTTYPE_URLENCODE
            if method == RESTMethod.GET
            else CONSTANTS.XT_VALIDATE_CONTENTTYPE_JSON
        )

        return headers

    def _generate_signature(self, message: str) -> str:
        mac = hmac.new(bytes(self.secret_key, encoding="utf8"), bytes(message, encoding="utf-8"), digestmod="sha256")
        d = mac.digest()
        return base64.b64encode(d).decode().strip()

    def _pre_hash(self, timestamp: str, method: str, path: str, params_str: str = None, body_str: str = None) -> str:
        pre_hash = "{}{}{}".format(timestamp, method, path)
        if params_str is not None:
            pre_hash = f"{pre_hash}{params_str}"
        if body_str is not None:
            pre_hash = f"{pre_hash}{body_str}"
        return pre_hash
