import os
import logging
from pathlib import Path

BASE_DIR         = Path(__file__).parent
DATA_STORAGE_DIR = BASE_DIR / "data_storage"
REPORTS_DIR      = BASE_DIR / "reports"
CHARTS_DIR       = BASE_DIR / "charts"
LOGS_DIR         = BASE_DIR / "logs"

for _d in [DATA_STORAGE_DIR, REPORTS_DIR, CHARTS_DIR, LOGS_DIR]:
    _d.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{BASE_DIR / 'backtester.db'}"

API_TITLE       = "TradeVed Backtester API"
API_DESCRIPTION = "Production-grade backtesting system with Grid, DCA & PLA strategies"
API_VERSION     = "1.0.0"
API_PREFIX      = "/api"

BINANCE_BASE_URL   = "https://api.binance.com"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

DEFAULT_FEE_PERCENT      = 0.001
DEFAULT_SLIPPAGE_PERCENT = 0.001
DEFAULT_CAPITAL          = 10_000.0

RATE_LIMIT_PER_MINUTE = 100
CACHE_TTL_SECONDS     = 3_600

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

import sys as _sys
_stream_handler = logging.StreamHandler(_sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        _stream_handler,
        logging.FileHandler(LOGS_DIR / "backtester.log", encoding="utf-8"),
    ],
)

COINGECKO_ID_MAP: dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
    "DOT": "polkadot", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "ATOM": "cosmos",
}
