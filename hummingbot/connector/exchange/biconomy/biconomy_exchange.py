from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.biconomy import (
    biconomy_constants as CONSTANTS,
    biconomy_utils,
    biconomy_web_utils as web_utils,
)
from hummingbot.connector.exchange.biconomy.biconomy_api_order_book_data_source import BiconomyAPIOrderBookDataSource
from hummingbot.connector.exchange.biconomy.biconomy_api_user_stream_data_source import BiconomyAPIUserStreamDataSource
from hummingbot.connector.exchange.biconomy.biconomy_auth import BiconomyAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class BiconomyExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        biconomy_api_key: str,
        biconomy_api_secret: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.api_key = biconomy_api_key
        self.secret_key = biconomy_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_biconomy_timestamp = 1.0
        super().__init__(client_config_map)

    @staticmethod
    def to_hb_order_type(biconomy_type: str) -> OrderType:
        return OrderType[biconomy_type]

    @property
    def authenticator(self):
        return BiconomyAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            time_provider=self._time_synchronizer,
        )

    @property
    def name(self) -> str:
        if self._domain == "com":
            return "biconomy"
        else:
            return f"biconomy_{self._domain}"

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
        return

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        error_description = str(status_update_exception)
        return "10005" in error_description

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        error_description = str(cancelation_exception)
        return "10005" in error_description

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler, time_synchronizer=self._time_synchronizer, domain=self._domain, auth=self._auth
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return BiconomyAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BiconomyAPIUserStreamDataSource(
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
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        api_params = {
            "market": symbol,
            "side": side_str,
            "amount": amount_str,
        }

        order_result = None

        try:
            if order_type is OrderType.LIMIT:
                api_params["price"] = f"{price:f}"
                order_result = await self._api_post(
                    path_url=CONSTANTS.PLACE_LIMIT_ORDER_PATH_URL, data=api_params, is_auth_required=True
                )
            else:
                order_result = await self._api_post(
                    path_url=CONSTANTS.PLACE_MARKET_ORDER_PATH_URL, data=api_params, is_auth_required=True
                )

            if order_result["result"] is not None:
                o_id = order_result["result"]["id"]
                transact_time = self.current_timestamp
            else:
                raise ValueError(order_result)

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
            "market": symbol,
            "order_id": tracked_order.exchange_order_id,
        }
        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL, data=api_params, is_auth_required=True
        )

        if cancel_result["code"] == 0:
            return True
        return False

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Example:
        [
            {
                "baseAsset": "ETH",
                "baseAssetPrecision": 4,
                "quoteAsset": "USDT",
                "quoteAssetPrecision": 2,
                "status": "trading",
                "symbol": "ETH_USDT"
            },
            {
                "baseAsset": "BTC",
                "baseAssetPrecision": 5,
                "quoteAsset": "USDT",
                "quoteAssetPrecision": 2,
                "status": "trading",
                "symbol": "BTC_USDT"
            }
        ]
        """
        trading_pair_rules = exchange_info_dict
        retval = []
        for rule in filter(biconomy_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("symbol"))

                min_base_amount_increment = Decimal(f"1e-{rule['baseAssetPrecision']}")
                min_quote_amount_increment = Decimal(f"1e-{rule['quoteAssetPrecision']}")
                min_price_increment = Decimal(f"1e-{rule['quoteAssetPrecision']}")

                retval.append(
                    TradingRule(
                        trading_pair,
                        min_price_increment=min_price_increment,
                        min_base_amount_increment=min_base_amount_increment,
                        min_quote_amount_increment=min_quote_amount_increment,
                    )
                )

            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _status_polling_loop_fetch_updates(self):
        await self._update_order_fills_from_trades()
        await super()._status_polling_loop_fetch_updates()

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
        # async for event_message in self._iter_user_event_queue():
        #     try:
        #         if "code" in event_message or "data" not in event_message:
        #             self.logger().error(f"Unexpected message in user stream: {event_message}.", exc_info=True)
        #             continue

        #         channel: str = event_message["arg"]["channel"]
        #         results: Dict[str, Any] = event_message.get("data")

        #         if channel == CONSTANTS.WS_SUBSCRIPTION_TRADE_CHANNEL_NAME:
        #             self._process_trade_message(results)
        #         elif channel == CONSTANTS.WS_SUBSCRIPTION_ORDERS_CHANNEL_NAME:
        #             self._process_order_message(results)
        #         elif channel == CONSTANTS.WS_SUBSCRIPTION_ACCOUNT_CHANNEL_NAME:
        #             self._process_balance_message_ws(results)

        #     except asyncio.CancelledError:
        #         raise
        #     except Exception:
        #         self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
        #         await self._sleep(5.0)

    async def _update_order_fills_from_trades(self):
        """
        This is intended to be a backup measure to get filled events with trade ID for orders,
        in case Binance's user stream events are not working.
        NOTE: It is not required to copy this functionality in other connectors.
        This is separated from _update_order_status which only updates the order status without producing filled
        events, since Binance's get order endpoint does not return trade IDs.
        The minimum poll interval for order status is 1 seconds.
        """
        small_interval_last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        small_interval_current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        long_interval_last_tick = self._last_poll_timestamp / self.LONG_POLL_INTERVAL
        long_interval_current_tick = self.current_timestamp / self.LONG_POLL_INTERVAL

        if long_interval_current_tick > long_interval_last_tick or (
            self.in_flight_orders and small_interval_current_tick > small_interval_last_tick
        ):
            query_time = int(self._last_trades_poll_biconomy_timestamp * 1e3)
            self._last_trades_poll_biconomy_timestamp = self._time_synchronizer.time()
            order_by_exchange_id_map: dict[str, InFlightOrder] = {}
            for order in self._order_tracker.all_fillable_orders.values():
                order_by_exchange_id_map[order.exchange_order_id] = order

            tasks = []
            trading_pairs = self.trading_pairs
            for trading_pair in trading_pairs:
                api_params = {
                    "market": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
                    "offset": 0,
                    "limit": 100,
                }
                if self._last_poll_timestamp > 0:
                    api_params["start_time"] = query_time
                tasks.append(
                    self._api_post(path_url=CONSTANTS.COMPLETED_ORDERS_PATH_URL, data=api_params, is_auth_required=True)
                )

            self.logger().debug(f"Polling for order fills of {len(tasks)} trading pairs.")
            results = await safe_gather(*tasks, return_exceptions=True)

            for completed_orders, trading_pair in zip(results, trading_pairs):

                if isinstance(completed_orders, Exception):
                    self.logger().network(
                        f"Error fetching trades update for the order {trading_pair}: {completed_orders}.",
                        app_warning_msg=f"Failed to fetch trade update for {trading_pair}.",
                    )
                    continue
                for completed_order in completed_orders["result"]["records"]:
                    exchange_order_id = str(completed_order["id"])

                    # Even canceled orders are treated as completed and returned in the completed orders endpoint,
                    # so we need to filter them out, i.e. if the 'completed_order.deal_money' is 0 then the order
                    # was canceled and not filled
                    if completed_order["deal_money"] == "0" and completed_order["deal_stock"] == "0":
                        continue

                    deal = await self._get_trade_from_order_id(exchange_order_id)
                    trade_id = str(deal["id"])

                    if exchange_order_id in order_by_exchange_id_map:
                        # This is a fill for a tracked order
                        tracked_order = order_by_exchange_id_map[exchange_order_id]
                        fee = TradeFeeBase.new_spot_fee(
                            fee_schema=self.trade_fee_schema(),
                            trade_type=tracked_order.trade_type,
                            flat_fees=[TokenAmount(amount=Decimal(deal["fee"]), token=tracked_order.quote_asset)],
                        )
                        trade_update = TradeUpdate(
                            trade_id=trade_id,
                            client_order_id=tracked_order.client_order_id,
                            exchange_order_id=exchange_order_id,
                            trading_pair=trading_pair,
                            fee=fee,
                            fill_base_amount=Decimal(deal["amount"]),
                            fill_quote_amount=Decimal(deal["deal"]),
                            fill_price=Decimal(deal["price"]),
                            fill_timestamp=deal["time"] * 1e-3,
                        )
                        self._order_tracker.process_trade_update(trade_update)
                    elif self.is_confirmed_new_order_filled_event(trade_id, exchange_order_id, trading_pair):
                        # This is a fill of an order registered in the DB but not tracked any more
                        self._current_trade_fills.add(
                            TradeFillOrderDetails(
                                market=self.display_name, exchange_trade_id=trade_id, symbol=trading_pair
                            )
                        )
                        self.trigger_event(
                            MarketEvent.OrderFilled,
                            OrderFilledEvent(
                                timestamp=float(deal["time"]) * 1e-3,
                                order_id=self._exchange_order_ids.get(completed_order["order_id"], None),
                                trading_pair=trading_pair,
                                trade_type=(
                                    TradeType.BUY if completed_order["side"] is CONSTANTS.SIDE_BUY else TradeType.SELL
                                ),
                                order_type=OrderType.LIMIT_MAKER if deal["role"] == 1 else OrderType.LIMIT,
                                price=Decimal(deal["price"]),
                                amount=Decimal(deal["amount"]),
                                exchange_trade_id=trade_id,
                            ),
                        )
                        self.logger().info(f"Recreating missing trade in TradeFill: {completed_order}")

    async def _get_trade_from_order_id(self, exchange_order_id: str) -> Optional[Any]:
        api_params = {
            "order_id": exchange_order_id,
            "offset": 0,
            "limit": 100,
        }
        response = await self._api_post(path_url=CONSTANTS.MY_TRADES_PATH_URL, data=api_params, is_auth_required=True)

        trades = response["result"]["records"] if "records" in response["result"] else []

        return trades[0] if len(trades) > 0 else None

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            exchange_order_id = order.exchange_order_id
            api_params = {
                "order_id": exchange_order_id,
                "offset": 0,
                "limit": 100,
            }
            response = await self._api_post(
                path_url=CONSTANTS.MY_TRADES_PATH_URL, data=api_params, is_auth_required=True
            )

            trades = response["result"]["records"] if "records" in response["result"] else []

            for trade in trades:
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    flat_fees=[TokenAmount(amount=Decimal(trade["fee"]), token=order.quote_asset)],
                )
                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=order.trading_pair,
                    fill_base_amount=Decimal(trade["amount"]),
                    fill_quote_amount=Decimal(trade["deal"]),
                    fill_price=Decimal(trade["price"]),
                    fill_timestamp=float(trade["time"]) * 1e-3,
                    fee=fee,
                )
                trade_updates.append(trade_update)

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        exchange_order_id = await tracked_order.get_exchange_order_id()
        trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=tracked_order.trading_pair)
        response = await self._api_post(
            path_url=CONSTANTS.GET_ORDER_PATH_URL,
            data={"order_id": exchange_order_id, "market": trading_pair},
            is_auth_required=True,
        )

        updated_order_data = response["result"]
        if updated_order_data is not None:
            order_update = OrderUpdate(
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=str(updated_order_data["id"]),
                trading_pair=tracked_order.trading_pair,
                update_timestamp=tracked_order.last_update_timestamp,
                new_state=tracked_order.current_state,
            )
        else:
            response = await self._api_post(
                path_url=CONSTANTS.COMPLETED_ORDER_DETAIL_PATH_URL,
                data={"order_id": exchange_order_id},
                is_auth_required=True,
            )
            updated_order_data = response["result"]
            order_update = OrderUpdate(
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=str(updated_order_data["id"]),
                trading_pair=tracked_order.trading_pair,
                update_timestamp=updated_order_data["ftime"] * 1e-3,
                new_state=OrderState.FILLED,
            )

        return order_update

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()
        account_info = await self._api_post(path_url=CONSTANTS.ACCOUNTS_PATH_URL, is_auth_required=True)
        balances = account_info["result"]
        for asset_name, balance_info in balances.items():
            if asset_name != "user_id":
                free_balance = Decimal(balance_info["available"])
                total_balance = free_balance + Decimal(balance_info["freeze"])
                self._account_available_balances[asset_name] = free_balance
                self._account_balances[asset_name] = total_balance
                remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(biconomy_utils.is_exchange_information_valid, exchange_info):
            mapping[symbol_data["symbol"]] = combine_to_hb_trading_pair(
                base=symbol_data["baseAsset"], quote=symbol_data["quoteAsset"]
            )
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)

        resp_json = await self._api_request(method=RESTMethod.GET, path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)

        for single_ticker in resp_json["ticker"]:
            if single_ticker["symbol"] == symbol:
                return float(single_ticker["last"])
