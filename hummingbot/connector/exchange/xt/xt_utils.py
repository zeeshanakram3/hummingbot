from decimal import Decimal
from typing import Any, Dict

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "BTC-USDT"

DEFAULT_FEES = TradeFeeSchema(maker_percent_fee_decimal=Decimal("0.002"), taker_percent_fee_decimal=Decimal("0.002"))


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("state", None) == "ONLINE" and exchange_info.get("tradingEnabled", False)


class XtConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="xt", const=True, client_data=None)
    xt_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your XT API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    xt_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your XT API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )

    class Config:
        title = "xt"


KEYS = XtConfigMap.construct()
