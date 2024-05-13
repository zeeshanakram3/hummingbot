import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.bitget import (
    bitget_constants as CONSTANTS,
    bitget_utils,
    bitget_web_utils as web_utils,
)
from hummingbot.connector.exchange.bitget.bitget_api_order_book_data_source import BitgetAPIOrderBookDataSource
from hummingbot.connector.exchange.bitget.bitget_api_user_stream_data_source import BitgetAPIUserStreamDataSource
from hummingbot.connector.exchange.bitget.bitget_auth import BitgetAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class BitgetExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        bitget_api_key: str,
        bitget_api_secret: str,
        bitget_passphrase: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.api_key = bitget_api_key
        self.secret_key = bitget_api_secret
        self.passphrase = bitget_passphrase
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_bitget_timestamp = 1.0
        super().__init__(client_config_map)

    @staticmethod
    def bitget_order_type(order_type: OrderType) -> str:
        return order_type.name.lower()

    @staticmethod
    def to_hb_order_type(bitget_type: str) -> OrderType:
        return OrderType[bitget_type]

    @property
    def authenticator(self):
        return BitgetAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase,
            time_provider=self._time_synchronizer,
        )

    @property
    def name(self) -> str:
        if self._domain == "com":
            return "bitget"
        else:
            return f"bitget_{self._domain}"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.SERVER_TIME_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        pairs_prices = await self._api_get(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)
        return pairs_prices

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        is_time_synchronizer_related = (
            "40004" in error_description
            or "40005" in error_description
            or "40008" in error_description
            or "40902" in error_description
            or "40911" in error_description
        )
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        error_description = str(status_update_exception)
        return (
            "40109" in error_description
            or "40768" in error_description
            or "40819" in error_description
            or "43001" in error_description
        )

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        error_description = str(cancelation_exception)
        return (
            "40733" in error_description
            or "40743" in error_description
            or "40768" in error_description
            or "40777" in error_description
            or "40817" in error_description
            or "40818" in error_description
            or "40819" in error_description
            or "40859" in error_description
            or "43001" in error_description
            or "43004" in error_description
            or "45024" in error_description
        )

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler, time_synchronizer=self._time_synchronizer, domain=self._domain, auth=self._auth
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return BitgetAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BitgetAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_NaN,
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        is_maker = order_type is OrderType.LIMIT
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> Tuple[str, float]:
        order_result = None
        amount_str = (
            f"{amount*price:f}" if order_type is OrderType.MARKET and trade_type is TradeType.BUY else f"{amount:f}"
        )
        type_str = BitgetExchange.bitget_order_type(order_type)
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        api_params = {
            "symbol": symbol,
            "side": side_str.lower(),
            "size": amount_str,
            "orderType": type_str,
            "clientOid": order_id,
        }
        if order_type is OrderType.LIMIT:
            price_str = f"{price:f}"
            api_params["price"] = price_str
            api_params["force"] = CONSTANTS.TIME_IN_FORCE_GTC

        try:
            order_result = await self._api_post(
                path_url=CONSTANTS.PLACE_ORDER_PATH_URL, data=api_params, is_auth_required=True
            )
            o_id = order_result["data"]["orderId"]
            transact_time = self.current_timestamp
        except IOError as e:
            error_description = str(e)
            is_server_overloaded = (
                "status is 503" in error_description
                and "Unknown error, please check your request or try again later." in error_description
            )
            if is_server_overloaded:
                o_id = "UNKNOWN"
                transact_time = self._time_synchronizer.time()
            else:
                raise
        return o_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=tracked_order.trading_pair)
        api_params = {
            "symbol": symbol,
            "clientOid": order_id,
        }
        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL, data=api_params, is_auth_required=True
        )

        if cancel_result["msg"] == "success":
            return True
        return False

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Example:
        {
            "code": "00000",
            "msg": "success",
            "requestTime": 1695808949356,
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "minTradeAmount": "0.0001",
                    "maxTradeAmount": "10000",
                    "takerFeeRate": "0.001",
                    "makerFeeRate": "0.001",
                    "pricePrecision": "4",
                    "quantityPrecision": "8",
                    "quotePrecision":"4",
                    "minTradeUSDT": "5",
                    "status": "online",
                    "buyLimitPriceRatio": "0.05",
                    "sellLimitPriceRatio": "0.05"
                }
            ]
        }
        """
        trading_pair_rules = exchange_info_dict.get("data", [])
        retval = []
        for rule in filter(bitget_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("symbol"))

                min_order_size = Decimal(rule.get("minTradeAmount"))
                min_price_increment = Decimal(f"1e-{rule['pricePrecision']}")
                min_amount_increment = Decimal(f"1e-{rule['quantityPrecision']}")
                min_notional_size = Decimal(rule["minTradeUSDT"])
                # TODO: this will only be correct for USDT/USDC pairs, for example ETH-BTC will be wrong
                # (
                #     rule["minTradeUSDT"]
                #     if rule["quoteCoin"] == "USDT" or rule["quoteCoin"] == "USDC"
                #     else Decimal(rule["minTradeUSDT"])
                #     / await self._get_last_traded_price(rule["baseCoin"] + rule["quoteCoin"])
                # )

                retval.append(
                    TradingRule(
                        trading_pair,
                        min_order_size=min_order_size,
                        min_price_increment=min_price_increment,
                        min_base_amount_increment=min_amount_increment,
                        min_notional_size=min_notional_size,
                    )
                )

            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        pass

    async def _user_stream_event_listener(self):
        """
        Listens to messages from _user_stream_tracker.user_stream queue.
        Traders, Orders, and Balance updates from the WS.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                if "code" in event_message or "data" not in event_message:
                    self.logger().error(f"Unexpected message in user stream: {event_message}.", exc_info=True)
                    continue

                channel: str = event_message["arg"]["channel"]
                results: Dict[str, Any] = event_message.get("data")

                if channel == CONSTANTS.WS_SUBSCRIPTION_TRADE_CHANNEL_NAME:
                    self._process_trade_message(results)
                elif channel == CONSTANTS.WS_SUBSCRIPTION_ORDERS_CHANNEL_NAME:
                    self._process_order_message(results)
                elif channel == CONSTANTS.WS_SUBSCRIPTION_ACCOUNT_CHANNEL_NAME:
                    self._process_balance_message_ws(results)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    def _process_trade_message(self, trades: Dict[str, Any]):
        for trade_data in trades:
            order_id = trade_data["orderId"]
            tracked_order = self._order_tracker.all_fillable_orders_by_exchange_order_id.get(order_id)
            if tracked_order is None:
                self.logger().debug(f"Ignoring trade message with order id {order_id}: not in in_flight_orders.")
            else:
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=tracked_order.trade_type,
                    percent_token=trade_data["feeDetail"][0]["feeCoin"],
                    flat_fees=[
                        TokenAmount(
                            amount=Decimal(trade_data["feeDetail"][0]["totalFee"]),
                            token=trade_data["feeDetail"][0]["feeCoin"],
                        )
                    ],
                )
                trade_update = TradeUpdate(
                    trade_id=(trade_data["tradeId"]),
                    client_order_id=tracked_order.client_order_id,
                    exchange_order_id=tracked_order.exchange_order_id,
                    trading_pair=tracked_order.trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade_data["size"]),
                    fill_quote_amount=Decimal(trade_data["amount"]),
                    fill_price=Decimal(trade_data["trade_data"]),
                    fill_timestamp=float(trade_data["uTime"]) * 1e-3,
                )
                self._order_tracker.process_trade_update(trade_update)

    def _process_order_message(self, orders: Dict[str, Any]):
        for order_data in orders:
            client_order_id = order_data["clientOid"]
            tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
            if not tracked_order:
                self.logger().debug(f"Ignoring order message with id {client_order_id}: not in in_flight_orders.")
                return

            update_timestamp = order_data["uTime"] if order_data["uTime"] is not None else order_data["cTime"]

            order_update = OrderUpdate(
                trading_pair=tracked_order.trading_pair,
                update_timestamp=int(update_timestamp) * 1e-3,
                new_state=CONSTANTS.ORDER_STATE[order_data["status"]],
                client_order_id=client_order_id,
                exchange_order_id=order_data["orderId"],
            )
            self._order_tracker.process_order_update(order_update=order_update)

    def _process_balance_message_ws(self, accounts: List[Dict[str, Any]]):
        for account_data in accounts:
            asset_name = account_data["coin"].upper()
            free_balance = Decimal(account_data["available"])
            total_balance = Decimal(account_data["available"]) + Decimal(account_data["frozen"])
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            exchange_order_id = order.exchange_order_id
            trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=order.trading_pair)
            response = await self._api_get(
                path_url=CONSTANTS.MY_TRADES_PATH_URL,
                params={
                    "orderId": exchange_order_id,
                    "symbol": trading_pair,
                },
                is_auth_required=True,
            )

            all_fills_response = response["data"]

            for trade in all_fills_response:
                exchange_order_id = trade["orderId"]
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token=trade["feeDetail"]["feeCoin"],
                    flat_fees=[
                        TokenAmount(amount=Decimal(trade["feeDetail"]["totalFee"]), token=trade["feeDetail"]["feeCoin"])
                    ],
                )
                trade_update = TradeUpdate(
                    trade_id=trade["tradeId"],
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=order.trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade["size"]),
                    fill_quote_amount=Decimal(trade["amount"]),
                    fill_price=Decimal(trade["priceAvg"]),
                    fill_timestamp=float(trade["uTime"]) * 1e-3,
                )
                trade_updates.append(trade_update)

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        client_order_id = tracked_order.client_order_id
        exchange_order_id = await tracked_order.get_exchange_order_id()
        response = await self._api_get(
            path_url=CONSTANTS.GET_ORDER_PATH_URL,
            params={
                "clientOid": client_order_id,
                "orderId": exchange_order_id,
            },
            is_auth_required=True,
        )

        updated_order_data = response["data"][0]

        new_state = CONSTANTS.ORDER_STATE[updated_order_data["status"]]

        update_timestamp = (
            updated_order_data["uTime"] if updated_order_data["uTime"] is not None else updated_order_data["cTime"]
        )

        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(updated_order_data["orderId"]),
            trading_pair=tracked_order.trading_pair,
            update_timestamp=float(update_timestamp) * 1e-3,
            new_state=new_state,
        )

        return order_update

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        account_info = await self._api_get(path_url=CONSTANTS.ACCOUNTS_PATH_URL, is_auth_required=True)

        balances = account_info["data"]
        for balance_entry in balances:
            asset_name = balance_entry["coin"].upper()
            free_balance = Decimal(balance_entry["available"])
            total_balance = Decimal(balance_entry["available"]) + Decimal(balance_entry["frozen"])
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(bitget_utils.is_exchange_information_valid, exchange_info["data"]):
            mapping[symbol_data["symbol"]] = combine_to_hb_trading_pair(
                base=symbol_data["baseCoin"], quote=symbol_data["quoteCoin"]
            )
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        params = {"symbol": symbol}

        resp_json = await self._api_request(
            method=RESTMethod.GET, path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL, params=params
        )

        for single_ticker in resp_json["data"]:
            if single_ticker["symbol"] == symbol:
                return float(single_ticker["lastPr"])
