import unittest

import hummingbot.connector.exchange.xt.xt_constants as CONSTANTS
from hummingbot.connector.exchange.xt import xt_web_utils as web_utils


class XtUtilTestCases(unittest.TestCase):

    def test_public_rest_url(self):
        path_url = CONSTANTS.SERVER_TIME_PATH_URL
        domain = "com"
        expected_url = CONSTANTS.REST_URL.format(domain) + CONSTANTS.PUBLIC_API_VERSION + path_url
        self.assertEqual(expected_url, web_utils.public_rest_url(path_url, domain))

    def test_private_rest_url(self):
        path_url = CONSTANTS.PUBLIC_API_VERSION
        domain = "com"
        expected_url = CONSTANTS.REST_URL.format(domain) + CONSTANTS.PRIVATE_API_VERSION + path_url
        self.assertEqual(expected_url, web_utils.private_rest_url(path_url, domain))
