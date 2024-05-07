from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_DOMAIN = "com"

HBOT_ORDER_ID_PREFIX = "bitget"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL = "https://api.bitget.{}/"
WSS_URL_PUBLIC = "wss://ws.bitget.{}/v2/ws/public"
WSS_URL_PRIVATE = "wss://ws.bitget.{}/v2/ws/private"

PUBLIC_API_VERSION = "v2"
PRIVATE_API_VERSION = "v2"

# Public REST API endpoints
TICKER_PRICE_CHANGE_PATH_URL = "/api/v2/spot/market/tickers"
EXCHANGE_INFO_PATH_URL = "/api/v2/spot/public/symbols"
SNAPSHOT_PATH_URL = "/api/v2/spot/market/orderbook"
SERVER_TIME_PATH_URL = "/api/v2/public/time"

# Private REST API endpoints
ACCOUNTS_PATH_URL = " /api/v2/spot/account/assets"
MY_TRADES_PATH_URL = "/api/v2/spot/trade/fills"
PLACE_ORDER_PATH_URL = "/api/v2/spot/trade/place-order"
CANCEL_ORDER_PATH_URL = "/api/v2/spot/trade/cancel-order"
GET_ORDER_PATH_URL = "/api/v2/spot/trade/orderInfo"
OPEN_ORDER_PATH_URL = "/api/v2/spot/trade/unfilled-orders"


PRIVATE_WS_LOGIN_PATH = "/user/verify"

WS_HEARTBEAT_TIME_INTERVAL = 15

# WebSocket Public Endpoints
WS_PING_REQUEST = "ping"
WS_PONG_RESPONSE = "pong"

# Websocket public event types
WS_SUBSCRIPTION_DIFF_CHANNEL_NAME = "books"
WS_SUBSCRIPTION_TRADES_CHANNEL_NAME = "trade"


# Private Websocket event types
WS_SUBSCRIPTION_TRADE_CHANNEL_NAME = "fill"
WS_SUBSCRIPTION_ORDERS_CHANNEL_NAME = "orders"
WS_SUBSCRIPTION_ACCOUNT_CHANNEL_NAME = "account"

# Websocket stream IDs (callback ID send by client)
TRADE_STREAM_ID = 1
DIFF_STREAM_ID = 2
USER_STREAM_ID = 1

# XT params
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

TIME_IN_FORCE_GTC = "GTC"  # Good till cancelled
TIME_IN_FORCE_IOC = "IOC"  # Immediate or cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill or kill
TIME_IN_FORCE_POST_ONLY = "post_only"  # Post only


XT_VALIDATE_ALGORITHMS = "HmacSHA256"
XT_VALIDATE_RECVWINDOW = "5000"
XT_VALIDATE_CONTENTTYPE_URLENCODE = "application/x-www-form-urlencoded"
XT_VALIDATE_CONTENTTYPE_JSON = "application/json;charset=UTF-8"


# Order States
ORDER_STATE = {
    "init": OrderState.OPEN,
    "live": OrderState.OPEN,
    "new": OrderState.OPEN,
    "filled": OrderState.FILLED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "cancelled": OrderState.CANCELED,
}


# Rate Limit time intervals
ONE_SECOND = 1

RATE_LIMITS = [
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=PLACE_ORDER_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=GET_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=OPEN_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=PRIVATE_WS_LOGIN_PATH, limit=10, time_interval=ONE_SECOND),
]
