import unittest

from hummingbot.connector.exchange.xt import xt_utils as utils


class XtUtilTestCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.base_asset = "COINALPHA"
        cls.quote_asset = "HBOT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.hb_trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = f"{cls.base_asset}{cls.quote_asset}"

    def test_is_exchange_information_valid(self):
        invalid_info_1 = {
            "state": "ONLINE",
            "tradingEnabled": False,
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_1))

        invalid_info_2 = {
            "state": "OFFLINE",
            "tradingEnabled": True,
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_2))

        invalid_info_3 = {
            "state": "OFFLINE",
            "tradingEnabled": False,
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_3))

        invalid_info_4 = {
            "state": "ONLINE",
            "tradingEnabled": True,
        }

        self.assertTrue(utils.is_exchange_information_valid(invalid_info_4))
