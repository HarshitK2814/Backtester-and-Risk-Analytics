"""
Data Fetcher — pulls OHLCV candles from multiple sources:
  1. Binance REST API  (no auth needed for public klines)
  2. CoinGecko API     (free tier, 10 000+ coins)
  3. yfinance          (stocks / forex / crypto / Indian markets)
  4. NSE (India)       — yfinance with .NS suffix + Indian symbol resolution
  5. BSE (India)       — yfinance with .BO suffix + Indian symbol resolution

All methods return a pandas DataFrame with columns:
  timestamp | open | high | low | close | volume

Indian symbol auto-resolution examples:
  "RELIANCE"  + source="nse"  →  yfinance ticker "RELIANCE.NS"
  "TCS"       + source="bse"  →  yfinance ticker "TCS.BO"
  "NIFTY50"   + source="nse"  →  yfinance ticker "^NSEI"
  "GOLDBEES"  + source="nse"  →  yfinance ticker "GOLDBEES.NS"
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Literal, Optional

import pandas as pd
import requests

from data.indian_assets import to_yf_symbol as _indian_to_yf

logger = logging.getLogger(__name__)

# ── Interval helpers ──────────────────────────────────────────────────────────
BINANCE_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _to_ms(dt: datetime) -> int:
    """Convert datetime → millisecond UNIX timestamp."""
    return int(dt.timestamp() * 1000)

def _normalize_symbol_binance(symbol: str) -> str:
    """'BTC/USDT' → 'BTCUSDT'"""
    return symbol.replace("/", "").replace("-", "").upper()

def _base_currency(symbol: str) -> str:
    """'BTC/USDT' → 'BTC'"""
    return symbol.split("/")[0].upper()


# ─────────────────────────────────────────────────────────────────────────────
# Binance Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class BinanceFetcher:
    BASE_URL = "https://api.binance.com"
    MAX_CANDLES_PER_REQUEST = 1000

    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV klines from Binance public REST API.
        Automatically paginates if the date range spans >1000 candles.
        """
        binance_sym = _normalize_symbol_binance(symbol)
        binance_interval = BINANCE_INTERVAL_MAP.get(interval, "1d")

        url = f"{self.BASE_URL}/api/v3/klines"
        all_records: list[list] = []

        current_start = start_date
        while current_start < end_date:
            params = {
                "symbol":    binance_sym,
                "interval":  binance_interval,
                "startTime": _to_ms(current_start),
                "endTime":   _to_ms(end_date),
                "limit":     self.MAX_CANDLES_PER_REQUEST,
            }
            try:
                resp = requests.get(url, params=params, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error("Binance request failed: %s", exc)
                break

            data = resp.json()
            if not data:
                break

            all_records.extend(data)

            # Advance start to the last candle's close time + 1 ms
            last_open_ms = data[-1][0]
            current_start = datetime.utcfromtimestamp(last_open_ms / 1000) + timedelta(milliseconds=1)

            if len(data) < self.MAX_CANDLES_PER_REQUEST:
                break  # no more pages

            time.sleep(0.05)   # respect rate limits

        if not all_records:
            raise ValueError(f"No data returned from Binance for {symbol} [{start_date} – {end_date}]")

        df = pd.DataFrame(all_records, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        df.sort_values("timestamp", inplace=True)
        df.drop_duplicates("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        logger.info("Binance: fetched %d candles for %s", len(df), symbol)
        return df


# ─────────────────────────────────────────────────────────────────────────────
# CoinGecko Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class CoinGeckoFetcher:
    BASE_URL = "https://api.coingecko.com/api/v3"

    # Partial symbol → CoinGecko coin-id map
    SYMBOL_TO_ID: dict[str, str] = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
        "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
        "DOT": "polkadot", "DOGE": "dogecoin", "AVAX": "avalanche-2",
        "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
        "LTC": "litecoin", "BCH": "bitcoin-cash", "ATOM": "cosmos",
        "NEAR": "near", "FTM": "fantom", "ALGO": "algorand",
        "VET": "vechain", "ICP": "internet-computer",
    }

    def _get_coin_id(self, symbol: str) -> str:
        base = _base_currency(symbol)
        coin_id = self.SYMBOL_TO_ID.get(base)
        if not coin_id:
            raise ValueError(f"No CoinGecko ID for symbol '{symbol}'. Add it to SYMBOL_TO_ID.")
        return coin_id

    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV from CoinGecko market_chart endpoint.
        Note: CoinGecko returns daily granularity for ranges >90 days.
        """
        coin_id = self._get_coin_id(symbol)
        days = (end_date - start_date).days + 1

        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days":        str(days),
            "interval":    "daily",
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"CoinGecko request failed: {exc}") from exc

        raw = resp.json()
        prices  = raw.get("prices", [])
        volumes = raw.get("total_volumes", [])

        if not prices:
            raise ValueError(f"No CoinGecko data for {symbol}")

        price_df  = pd.DataFrame(prices,  columns=["timestamp", "close"])
        volume_df = pd.DataFrame(volumes, columns=["timestamp", "volume"])

        df = price_df.merge(volume_df, on="timestamp")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        df["open"]  = df["close"].shift(1).fillna(df["close"])
        df["high"]  = df["close"] * 1.002   # approximate (daily OHLC not provided)
        df["low"]   = df["close"] * 0.998
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        # Filter to requested date range
        df = df[(df["timestamp"] >= pd.Timestamp(start_date)) & (df["timestamp"] <= pd.Timestamp(end_date))]
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        logger.info("CoinGecko: fetched %d candles for %s", len(df), symbol)
        return df


# ─────────────────────────────────────────────────────────────────────────────
# yfinance Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class YFinanceFetcher:
    """Fetches OHLCV data using yfinance (stocks, ETFs, BTC-USD, etc.)."""

    INTERVAL_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "1h",  # yfinance doesn't support 4h natively
        "1d": "1d", "1w": "1wk",
    }

    def _to_yf_symbol(self, symbol: str, exchange: str = "") -> str:
        """
        Convert a symbol to yfinance ticker format.

        Handles:
          'BTC/USDT'         → 'BTC-USD'
          'AAPL'             → 'AAPL'        (US stocks — pass-through)
          'RELIANCE.NS'      → 'RELIANCE.NS' (already yfinance format)
          '^NSEI'            → '^NSEI'       (indices — pass-through)
        """
        s = symbol.strip()
        # Already in yfinance format
        if s.endswith(".NS") or s.endswith(".BO") or s.startswith("^"):
            return s
        # Crypto pairs: 'BTC/USDT' → 'BTC-USD'
        if "/" in s:
            base, quote = s.split("/")
            quote = "USD" if quote.upper() == "USDT" else quote
            return f"{base}-{quote}"
        return s

    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("Install yfinance: pip install yfinance") from exc

        yf_sym    = self._to_yf_symbol(symbol)
        yf_interval = self.INTERVAL_MAP.get(interval, "1d")

        ticker = yf.Ticker(yf_sym)
        raw = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval=yf_interval,
            auto_adjust=True,
        )

        if raw.empty:
            raise ValueError(f"yfinance returned no data for {symbol}")

        df = raw.reset_index()
        ts_col = "Datetime" if "Datetime" in df.columns else "Date"
        df.rename(columns={
            ts_col:  "timestamp",
            "Open":  "open",
            "High":  "high",
            "Low":   "low",
            "Close": "close",
            "Volume":"volume",
        }, inplace=True)

        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        logger.info("yfinance: fetched %d candles for %s", len(df), symbol)
        return df


# ─────────────────────────────────────────────────────────────────────────────
# Unified DataFetcher
# ─────────────────────────────────────────────────────────────────────────────

Source = Literal["binance", "coingecko", "yfinance", "nse", "bse", "auto"]


class IndianMarketFetcher:
    """
    Fetches OHLCV data for Indian NSE/BSE assets via yfinance.

    Automatically resolves Indian symbols to yfinance tickers:
      "RELIANCE" + exchange="NSE"  →  "RELIANCE.NS"
      "TCS"      + exchange="BSE"  →  "TCS.BO"
      "NIFTY50"  + any             →  "^NSEI"
      "GOLDBEES" + exchange="NSE"  →  "GOLDBEES.NS"

    Data is adjusted for splits and dividends (auto_adjust=True).
    Returns only trading days — weekends and Indian holidays have no rows (as expected).
    """

    _YF = YFinanceFetcher()

    def fetch(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d",
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        yf_sym = _indian_to_yf(symbol, exchange)
        logger.info("Indian market: %s → yfinance %s", symbol, yf_sym)
        df = self._YF.fetch(yf_sym, start_date, end_date, interval)

        # Post-process: remove any weekend rows that might slip through
        if interval == "1d":
            df = df[df["timestamp"].dt.dayofweek < 5].copy()

        # Validate OHLC sanity
        bad = (df["high"] < df["low"]).sum()
        if bad:
            logger.warning("Indian data quality: %d rows with high < low — dropping", bad)
            df = df[df["high"] >= df["low"]].copy()

        # Forward-fill any isolated NaN close prices (rare corporate-action artifacts)
        df["close"] = df["close"].ffill()
        df = df.dropna(subset=["close", "open", "high", "low"])
        df.reset_index(drop=True, inplace=True)

        logger.info("IndianFetcher: %d candles for %s (%s)", len(df), symbol, exchange)
        return df


class DataFetcher:
    """
    Unified interface that routes to the right data source.

    source options:
        'binance'   — Binance REST API (best for crypto)
        'coingecko' — CoinGecko (10k+ coins, daily)
        'yfinance'  — yfinance (US stocks, ETFs, forex, crypto)
        'nse'       — NSE India (via yfinance with .NS suffix)
        'bse'       — BSE India (via yfinance with .BO suffix)
        'auto'      — tries Binance → CoinGecko → yfinance

    Indian market examples:
        fetch("RELIANCE", ..., source="nse")
        fetch("TCS",      ..., source="bse")
        fetch("NIFTY50",  ..., source="nse")
        fetch("NIFTYBEES",..., source="nse")
    """

    def __init__(self):
        self._binance    = BinanceFetcher()
        self._coingecko  = CoinGeckoFetcher()
        self._yfinance   = YFinanceFetcher()
        self._indian     = IndianMarketFetcher()

    def fetch(
        self,
        symbol:     str,
        start_date: datetime,
        end_date:   datetime,
        source:     Source = "binance",
        interval:   str    = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for any asset from any supported source.

        Returns pd.DataFrame with columns:
            timestamp | open | high | low | close | volume | source
        """
        # ── Indian markets ────────────────────────────────────────────────────
        if source == "nse":
            df = self._indian.fetch(symbol, start_date, end_date, interval, exchange="NSE")
            df["source"] = "nse"
            return df

        if source == "bse":
            df = self._indian.fetch(symbol, start_date, end_date, interval, exchange="BSE")
            df["source"] = "bse"
            return df

        # ── Crypto / US markets / auto fallback ───────────────────────────────
        fetchers: dict[str, any] = {
            "binance":   self._binance.fetch,
            "coingecko": self._coingecko.fetch,
            "yfinance":  self._yfinance.fetch,
        }

        order = ["binance", "coingecko", "yfinance"] if source == "auto" else [source]

        last_exc: Optional[Exception] = None
        for src in order:
            fn = fetchers.get(src)
            if fn is None:
                continue
            try:
                logger.info("Fetching %s from %s (%s → %s)…",
                            symbol, src, start_date.date(), end_date.date())
                df = fn(symbol, start_date, end_date, interval)
                if not df.empty:
                    df["source"] = src
                    return df
            except Exception as exc:
                logger.warning("Source '%s' failed for %s: %s", src, symbol, exc)
                last_exc = exc

        raise ValueError(
            f"All data sources failed for '{symbol}'. Last error: {last_exc}"
        )
