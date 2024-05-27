import hashlib
import hmac
import json
from urllib.parse import urlencode

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class BiconomyAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """

        request.data = json.loads(request.data) if request.data else {}
        request.data["api_key"] = self.api_key

        data_str = (
            urlencode(dict(sorted(request.data.items(), key=lambda kv: (kv[0], kv[1]))), safe=",")
            if request.data is not None
            else request.data
        )

        pre_hash = f"{data_str}&secret_key={self.secret_key}"
        signature = self._generate_signature(pre_hash)

        request.data["sign"] = signature
        request.headers = {"Content-Type": "application/x-www-form-urlencoded"}

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. XT does not use this
        functionality
        """
        return request  # pass-through

    def _generate_signature(self, message: str) -> str:
        digest = hmac.new(self.secret_key.encode("utf8"), message.encode("utf8"), hashlib.sha256).hexdigest()
        return digest.upper()
