from __future__ import annotations
import logging, time
from datetime import datetime, timedelta
from typing import Literal, Optional
import pandas as pd
import requests
from data.indian_assets import to_yf_symbol as _indian_to_yf

logger = logging.getLogger(__name__)
BINANCE_INTERVAL_MAP = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"1h","4h":"4h","1d":"1d","1w":"1w"}

def _to_ms(dt): return int(dt.timestamp() * 1000)
def _normalize_symbol_binance(s): return s.replace("/","").replace("-","").upper()
def _base_currency(s): return s.split("/")[0].upper()


class BinanceFetcher:
    BASE_URL = "https://api.binance.com"
    MAX_CANDLES_PER_REQUEST = 1000

    def fetch(self, symbol, start_date, end_date, interval="1d"):
        sym = _normalize_symbol_binance(symbol)
        url = f"{self.BASE_URL}/api/v3/klines"
        all_records = []
        current_start = start_date
        while current_start < end_date:
            params = {"symbol": sym, "interval": BINANCE_INTERVAL_MAP.get(interval, "1d"),
                      "startTime": _to_ms(current_start), "endTime": _to_ms(end_date),
                      "limit": self.MAX_CANDLES_PER_REQUEST}
            try:
                resp = requests.get(url, params=params, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error("Binance request failed: %s", exc); break
            data = resp.json()
            if not data: break
            all_records.extend(data)
            last_open_ms = data[-1][0]
            current_start = datetime.utcfromtimestamp(last_open_ms / 1000) + timedelta(milliseconds=1)
            if len(data) < self.MAX_CANDLES_PER_REQUEST: break
            time.sleep(0.05)
        if not all_records:
            raise ValueError(f"No data from Binance for {symbol}")
        df = pd.DataFrame(all_records, columns=["timestamp","open","high","low","close","volume",
                          "close_time","quote_volume","num_trades","taker_buy_base","taker_buy_quote","ignore"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        for col in ["open","high","low","close","volume"]: df[col] = df[col].astype(float)
        df = df[["timestamp","open","high","low","close","volume"]].copy()
        df.sort_values("timestamp", inplace=True); df.drop_duplicates("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        logger.info("Binance: fetched %d candles for %s", len(df), symbol)
        return df


class CoinGeckoFetcher:
    BASE_URL = "https://api.coingecko.com/api/v3"
    SYMBOL_TO_ID = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "SOL": "solana",
        "ADA": "cardano", "XRP": "ripple", "DOT": "polkadot", "DOGE": "dogecoin",
        "AVAX": "avalanche-2", "MATIC": "matic-network", "LINK": "chainlink",
        "UNI": "uniswap", "LTC": "litecoin", "BCH": "bitcoin-cash", "ATOM": "cosmos",
    }
    def _get_coin_id(self, symbol):
        base = _base_currency(symbol)
        coin_id = self.SYMBOL_TO_ID.get(base)
        if not coin_id: raise ValueError(f"No CoinGecko ID for '{symbol}'")
        return coin_id

    def fetch(self, symbol, start_date, end_date, interval="1d"):
        coin_id = self._get_coin_id(symbol)
        days = (end_date - start_date).days + 1
        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        try:
            resp = requests.get(url, params={"vs_currency":"usd","days":str(days),"interval":"daily"}, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"CoinGecko failed: {exc}") from exc
        raw = resp.json()
        prices  = raw.get("prices", []); volumes = raw.get("total_volumes", [])
        if not prices: raise ValueError(f"No CoinGecko data for {symbol}")
        df = pd.DataFrame(prices, columns=["timestamp","close"]).merge(
             pd.DataFrame(volumes, columns=["timestamp","volume"]), on="timestamp")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        df["open"] = df["close"].shift(1).fillna(df["close"])
        df["high"] = df["close"] * 1.002; df["low"] = df["close"] * 0.998
        df = df[["timestamp","open","high","low","close","volume"]]
        df = df[(df["timestamp"] >= pd.Timestamp(start_date)) & (df["timestamp"] <= pd.Timestamp(end_date))]
        df.sort_values("timestamp", inplace=True); df.reset_index(drop=True, inplace=True)
        logger.info("CoinGecko: fetched %d candles for %s", len(df), symbol)
        return df


class YFinanceFetcher:
    INTERVAL_MAP = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"1h","4h":"1h","1d":"1d","1w":"1wk"}

    def _to_yf_symbol(self, symbol):
        s = symbol.strip()
        if s.endswith(".NS") or s.endswith(".BO") or s.startswith("^"):
            return s
        if "/" in s:
            base, quote = s.split("/")
            return f"{base}-{('USD' if quote.upper()=='USDT' else quote)}"
        return s

    def fetch(self, symbol, start_date, end_date, interval="1d"):
        import yfinance as yf
        yf_sym = self._to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_sym)
        raw = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                             end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                             interval=self.INTERVAL_MAP.get(interval, "1d"), auto_adjust=True)
        if raw.empty: raise ValueError(f"yfinance returned no data for {symbol}")
        df = raw.reset_index()
        ts_col = "Datetime" if "Datetime" in df.columns else "Date"
        df.rename(columns={ts_col:"timestamp","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df = df[["timestamp","open","high","low","close","volume"]]
        df.sort_values("timestamp", inplace=True); df.reset_index(drop=True, inplace=True)
        logger.info("yfinance: fetched %d candles for %s", len(df), symbol)
        return df


class IndianMarketFetcher:
    _YF = YFinanceFetcher()

    def fetch(self, symbol, start_date, end_date, interval="1d", exchange="NSE"):
        yf_sym = _indian_to_yf(symbol, exchange)
        logger.info("Indian market: %s -> yfinance %s", symbol, yf_sym)
        df = self._YF.fetch(yf_sym, start_date, end_date, interval)
        if interval == "1d":
            df = df[df["timestamp"].dt.dayofweek < 5].copy()
        bad = (df["high"] < df["low"]).sum()
        if bad: df = df[df["high"] >= df["low"]].copy()
        df["close"] = df["close"].ffill()
        df = df.dropna(subset=["close","open","high","low"])
        df.reset_index(drop=True, inplace=True)
        logger.info("IndianFetcher: %d candles for %s (%s)", len(df), symbol, exchange)
        return df


Source = Literal["binance", "coingecko", "yfinance", "nse", "bse", "auto"]


class DataFetcher:
    def __init__(self):
        self._binance   = BinanceFetcher()
        self._coingecko = CoinGeckoFetcher()
        self._yfinance  = YFinanceFetcher()
        self._indian    = IndianMarketFetcher()

    def fetch(self, symbol, start_date, end_date, source: Source = "binance", interval="1d"):
        if source == "nse":
            df = self._indian.fetch(symbol, start_date, end_date, interval, exchange="NSE")
            df["source"] = "nse"; return df
        if source == "bse":
            df = self._indian.fetch(symbol, start_date, end_date, interval, exchange="BSE")
            df["source"] = "bse"; return df
        fetchers = {"binance": self._binance.fetch, "coingecko": self._coingecko.fetch, "yfinance": self._yfinance.fetch}
        order = ["binance","coingecko","yfinance"] if source == "auto" else [source]
        last_exc = None
        for src in order:
            fn = fetchers.get(src)
            if fn is None: continue
            try:
                logger.info("Fetching %s from %s...", symbol, src)
                df = fn(symbol, start_date, end_date, interval)
                if not df.empty:
                    df["source"] = src; return df
            except Exception as exc:
                logger.warning("Source '%s' failed for %s: %s", src, symbol, exc)
                last_exc = exc
        raise ValueError(f"All sources failed for '{symbol}'. Last: {last_exc}")
