import unittest

from hummingbot.connector.exchange.bitget import bitget_utils as utils


class BotgetUtilTestCases(unittest.TestCase):

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
            "status": "offline",
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_1))

        invalid_info_2 = {
            "status": "grey",
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_2))

        valid_info_3 = {
            "status": "online",
        }

        self.assertTrue(utils.is_exchange_information_valid(valid_info_3))
