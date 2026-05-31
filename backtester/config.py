"""
Configuration settings for the TradeVed Backtester system.
All paths, constants, and environment-based settings live here.
"""
import os
import logging
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent
DATA_STORAGE_DIR = BASE_DIR / "data_storage"
REPORTS_DIR      = BASE_DIR / "reports"
CHARTS_DIR       = BASE_DIR / "charts"
LOGS_DIR         = BASE_DIR / "logs"

# Ensure all runtime directories exist
for _d in [DATA_STORAGE_DIR, REPORTS_DIR, CHARTS_DIR, LOGS_DIR]:
    _d.mkdir(exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL = f"sqlite:///{BASE_DIR / 'backtester.db'}"

# ── API Settings ─────────────────────────────────────────────────────────────
API_TITLE       = "TradeVed Backtester API"
API_DESCRIPTION = "Production-grade cryptocurrency backtesting system with Grid, DCA & PLA strategies"
API_VERSION     = "1.0.0"
API_PREFIX      = "/api"

# ── External Data Sources ────────────────────────────────────────────────────
BINANCE_BASE_URL   = "https://api.binance.com"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Binance optional API credentials (not required for public OHLCV data)
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# ── Trading Defaults ──────────────────────────────────────────────────────────
DEFAULT_FEE_PERCENT      = 0.001   # 0.1 % Binance taker fee
DEFAULT_SLIPPAGE_PERCENT = 0.001   # 0.1 % market-impact slippage
DEFAULT_CAPITAL          = 10_000.0

# ── Rate Limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = 100

# ── Caching ───────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 3_600   # 1 hour

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

import sys as _sys
_stream_handler = logging.StreamHandler(_sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
# Reconfigure stdout to UTF-8 so ₹ and other non-ASCII characters don't crash on Windows
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass  # not available in older Python versions

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        _stream_handler,
        logging.FileHandler(LOGS_DIR / "backtester.log", encoding="utf-8"),
    ],
)

# ── CoinGecko symbol → coin-id mapping (extend as needed) ────────────────────
COINGECKO_ID_MAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "ADA": "cardano",
    "XRP": "ripple",
    "DOT": "polkadot",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "ATOM": "cosmos",
}
