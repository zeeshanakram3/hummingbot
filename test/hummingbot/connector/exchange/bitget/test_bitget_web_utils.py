import unittest
from urllib.parse import urljoin

import hummingbot.connector.exchange.bitget.bitget_constants as CONSTANTS
from hummingbot.connector.exchange.bitget import bitget_web_utils as web_utils


class BinanceUtilTestCases(unittest.TestCase):

    def test_public_rest_url(self):
        path_url = "/api/v2/public/time"
        domain = "com"
        expected_url = urljoin(CONSTANTS.REST_URL.format(domain), path_url)
        self.assertEqual(expected_url, web_utils.public_rest_url(path_url, domain))

    def test_private_rest_url(self):
        path_url = "/api/v2/spot/account/assets"
        domain = "com"
        expected_url = urljoin(CONSTANTS.REST_URL.format(domain), path_url)
        self.assertEqual(expected_url, web_utils.private_rest_url(path_url, domain))
