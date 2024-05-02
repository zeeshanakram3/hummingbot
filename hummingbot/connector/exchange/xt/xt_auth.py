import hashlib
import hmac
import json
from collections import OrderedDict
from typing import Dict
from urllib.parse import urlencode

from hummingbot.connector.exchange.xt import xt_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class XtAuth(AuthBase):
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
        endpoint_url = request.url.split(CONSTANTS.PRIVATE_API_VERSION)[1]
        path = f"/{CONSTANTS.PRIVATE_API_VERSION}{endpoint_url}"

        params_str = (
            urlencode(dict(sorted(request.params.items(), key=lambda kv: (kv[0], kv[1]))), safe=",")
            if request.params is not None
            else request.params
        )

        if request.method == RESTMethod.GET or request.method == RESTMethod.DELETE:
            headers = self.add_auth_to_headers(method=request.method, path=path, params_str=params_str)
        else:
            headers = self.add_auth_to_headers(method=request.method, path=path, body_str=json.dumps(request.data))

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

    def add_auth_to_headers(self, method: RESTMethod, path: str, params_str: str = None, body_str: str = None):
        headers = self.header_for_authentication()
        X = urlencode(dict(sorted(headers.items(), key=lambda kv: (kv[0], kv[1]))))

        Y = "#{}#{}".format(method, path)
        if params_str is not None:
            Y = f"{Y}#{params_str}"
        if body_str is not None:
            Y = f"{Y}#{body_str}"

        signature = self._generate_signature(X + Y)
        headers["validate-signature"] = signature

        headers["Content-Type"] = (
            CONSTANTS.XT_VALIDATE_CONTENTTYPE_URLENCODE
            if method == RESTMethod.GET
            else CONSTANTS.XT_VALIDATE_CONTENTTYPE_JSON
        )

        return headers

    def header_for_authentication(self) -> Dict[str, str]:
        headers = OrderedDict()
        headers["validate-algorithms"] = CONSTANTS.XT_VALIDATE_ALGORITHMS
        headers["validate-appkey"] = self.api_key
        headers["validate-recvwindow"] = CONSTANTS.XT_VALIDATE_RECVWINDOW
        headers["validate-timestamp"] = str(int(self.time_provider.time() * 1e3))
        return headers

    def _generate_signature(self, encoded_params_str: str) -> str:
        digest = hmac.new(self.secret_key.encode("utf8"), encoded_params_str.encode("utf8"), hashlib.sha256).hexdigest()
        return digest
