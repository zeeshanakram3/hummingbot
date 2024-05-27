from unittest import TestCase

from hummingbot.connector.exchange.xt.xt_order_book import XtOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class XtOrderBookTests(TestCase):

    def test_snapshot_message_from_exchange(self):
        snapshot_message = XtOrderBook.snapshot_message_from_exchange(
            msg={"lastUpdateId": 1, "bids": [["4.00000000", "431.00000000"]], "asks": [["4.00000200", "12.00000000"]]},
            timestamp=1640000000.0,
            metadata={"trading_pair": "BTC-USDT"},
        )

        self.assertEqual("BTC-USDT", snapshot_message.trading_pair)
        self.assertEqual(OrderBookMessageType.SNAPSHOT, snapshot_message.type)
        self.assertEqual(1640000000.0, snapshot_message.timestamp)
        self.assertEqual(1, snapshot_message.update_id)
        self.assertEqual(-1, snapshot_message.trade_id)
        self.assertEqual(1, len(snapshot_message.bids))
        self.assertEqual(4.0, snapshot_message.bids[0].price)
        self.assertEqual(431.0, snapshot_message.bids[0].amount)
        self.assertEqual(1, snapshot_message.bids[0].update_id)
        self.assertEqual(1, len(snapshot_message.asks))
        self.assertEqual(4.000002, snapshot_message.asks[0].price)
        self.assertEqual(12.0, snapshot_message.asks[0].amount)
        self.assertEqual(1, snapshot_message.asks[0].update_id)

    def test_diff_message_from_exchange(self):
        diff_msg = XtOrderBook.diff_message_from_exchange(
            msg={
                "topic": "depth_update",
                "fi": 120,
                "i": 123,
                "s": "btc_usdt",
                "b": [["0.0024", "10"]],
                "a": [["0.0026", "100"]],
            },
            timestamp=1640000000.0,
            metadata={"trading_pair": "BTC-USDT"},
        )

        self.assertEqual("BTC-USDT", diff_msg.trading_pair)
        self.assertEqual(OrderBookMessageType.DIFF, diff_msg.type)
        self.assertEqual(1640000000.0, diff_msg.timestamp)
        self.assertEqual(123, diff_msg.update_id)
        self.assertEqual(120, diff_msg.first_update_id)
        self.assertEqual(-1, diff_msg.trade_id)
        self.assertEqual(1, len(diff_msg.bids))
        self.assertEqual(0.0024, diff_msg.bids[0].price)
        self.assertEqual(10.0, diff_msg.bids[0].amount)
        self.assertEqual(123, diff_msg.bids[0].update_id)
        self.assertEqual(1, len(diff_msg.asks))
        self.assertEqual(0.0026, diff_msg.asks[0].price)
        self.assertEqual(100.0, diff_msg.asks[0].amount)
        self.assertEqual(123, diff_msg.asks[0].update_id)

    def test_trade_message_from_exchange(self):
        trade_update = {
            "topic": "trade",
            "s": "btc_usdt",
            "i": 6316559590087222000,
            "t": 1655992403617,
            "p": "43000",
            "q": "0.21",
            "b": True,
        }

        trade_message = XtOrderBook.trade_message_from_exchange(msg=trade_update, metadata={"trading_pair": "BTC-USDT"})

        self.assertEqual("BTC-USDT", trade_message.trading_pair)
        self.assertEqual(OrderBookMessageType.TRADE, trade_message.type)
        self.assertEqual(1655992403.617, trade_message.timestamp)
        self.assertEqual(-1, trade_message.update_id)
        self.assertEqual(-1, trade_message.first_update_id)
        self.assertEqual(6316559590087222000, trade_message.trade_id)
