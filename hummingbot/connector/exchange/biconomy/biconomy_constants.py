from hummingbot.core.api_throttler.data_types import RateLimit

DEFAULT_DOMAIN = "com"

HBOT_ORDER_ID_PREFIX = "bic"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL = "https://api.biconomy.{}/"
WSS_URL_PUBLIC = "wss://www.biconomy.{}/ws"

# Public REST API endpoints
TICKER_PRICE_CHANGE_PATH_URL = "/api/v1/tickers"
EXCHANGE_INFO_PATH_URL = "/api/v1/exchangeInfo"
SNAPSHOT_PATH_URL = "/api/v1/depth"
SERVER_TIME_PATH_URL = "/api/v1/exchangeInfo"

# Private REST API endpoints
ACCOUNTS_PATH_URL = "/api/v2/private/user"

PLACE_LIMIT_ORDER_PATH_URL = "/api/v2/private/trade/limit"
PLACE_MARKET_ORDER_PATH_URL = "/api/v2/private/trade/market"
CANCEL_ORDER_PATH_URL = "/api/v2/private/trade/cancel"

MY_TRADES_PATH_URL = "/api/v2/private/order/deals"
GET_ORDER_PATH_URL = "/api/v2/private/order/pending/detail"
COMPLETED_ORDERS_PATH_URL = "/api/v2/private/order/finished"
COMPLETED_ORDER_DETAIL_PATH_URL = "/api/v2/private/order/finished/detail"

WS_HEARTBEAT_TIME_INTERVAL = 150

# Trade sides
SIDE_BUY = 2
SIDE_SELL = 1

# Websocket public event types
WS_SUBSCRIPTION_DIFF_CHANNEL_NAME = "depth.update"
WS_SUBSCRIPTION_TRADES_CHANNEL_NAME = "deals.update"

# Websocket stream IDs (callback ID send by client)
TRADE_STREAM_ID = 1
DIFF_STREAM_ID = 2

# Rate Limit time intervals
ONE_SECOND = 1

RATE_LIMITS = [
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=PLACE_LIMIT_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=PLACE_MARKET_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=GET_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=COMPLETED_ORDER_DETAIL_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=COMPLETED_ORDERS_PATH_URL, limit=500, time_interval=ONE_SECOND),
]
