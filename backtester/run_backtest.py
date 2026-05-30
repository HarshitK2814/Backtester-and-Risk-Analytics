"""run_backtest.py — Standalone CLI script (no server required)."""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from data.fetcher    import DataFetcher
from data.validator  import DataValidator
from engine.simulator import TradeSimulator
from engine.metrics  import calculate_metrics
from frontend.report import generate_report
from strategies      import STRATEGY_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

DIVIDER = "─" * 70


def run_single(symbol, strategy, start, end, capital, source, interval, fee, slippage, extra_params):
    strategy = strategy.upper()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt   = datetime.strptime(end,   "%Y-%m-%d")

    print(f"\n{DIVIDER}")
    print(f"  {strategy} Backtest — {symbol}  [{start} → {end}]  Capital: {capital:,.0f}")
    print(DIVIDER)

    df  = DataFetcher().fetch(symbol, start_dt, end_dt, source, interval)
    val = DataValidator().validate(df)
    print(f"  Data: {len(df)} candles | quality {val.quality_score:.0f}/100")

    cls   = STRATEGY_REGISTRY[strategy]
    params = {**cls.default_params(), **extra_params}
    sigs  = cls(**params).generate_signals(df.copy())

    sim    = TradeSimulator(symbol, capital, fee, slippage)
    out    = sim.run(sigs)
    metrics = calculate_metrics(out["trades"], out["equity_curve"], out["timestamps"], capital)

    ret = metrics["total_return_pct"]
    print(f"  Return: {ret:+.2f}%  |  Sharpe: {metrics['sharpe_ratio']:.3f}  |  MaxDD: {metrics['max_drawdown_pct']:.2f}%")
    print(f"  Trades: {metrics['num_trades']}  |  WinRate: {metrics['win_rate']:.1f}%  |  Fees: {out['total_fees_paid']:.2f}")

    import uuid
    bid   = str(uuid.uuid4())[:8]
    rpath = generate_report(bid, symbol, strategy, params, metrics, df)
    print(f"  Report: {rpath}")
    return metrics, rpath


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",   default="BTC/USDT")
    p.add_argument("--strategy", default="GRID",    choices=["GRID", "DCA", "PLA"])
    p.add_argument("--start",    default="2023-01-01")
    p.add_argument("--end",      default="2023-12-31")
    p.add_argument("--capital",  default=10_000.0,   type=float)
    p.add_argument("--source",   default="binance",  choices=["binance", "coingecko", "yfinance", "nse", "bse"])
    p.add_argument("--interval", default="1d")
    p.add_argument("--fee",      default=0.001,       type=float)
    p.add_argument("--slippage", default=0.001,       type=float)
    p.add_argument("--open",     action="store_true")
    p.add_argument("--all",      action="store_true")
    args = p.parse_args()

    if args.all:
        for strat in ["GRID", "DCA", "PLA"]:
            try:
                run_single(args.symbol, strat, args.start, args.end,
                           args.capital, args.source, args.interval,
                           args.fee, args.slippage, {})
            except Exception as exc:
                logger.error("%s failed: %s", strat, exc)
        return

    metrics, rpath = run_single(
        args.symbol, args.strategy, args.start, args.end,
        args.capital, args.source, args.interval, args.fee, args.slippage, {},
    )
    if args.open:
        webbrowser.open(str(rpath))


if __name__ == "__main__":
    main()
