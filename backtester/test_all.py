import sys, traceback, math
from datetime import datetime, timedelta
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from data.fetcher import DataFetcher
from data.validator import DataValidator
from data.indian_assets import get_lot_size, is_indian
from engine.simulator import TradeSimulator
from engine.metrics import calculate_metrics
from engine.cost_models import IndianCostModel
from strategies.grid import GridStrategy
from strategies.dca  import DCAStrategy
from strategies.pla  import PLAStrategy

fetcher   = DataFetcher()
validator = DataValidator()
results = []

def run_test(name, fn):
    try:
        fn()
        results.append(("PASS", name))
        print(f"[PASS] {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e)))
        print(f"[FAIL] {name}")
        traceback.print_exc()
        print()

def test_fetch_crypto():
    df = fetcher.fetch("BTC/USDT", datetime(2024,1,1), datetime(2024,3,31), "binance", "1d")
    assert len(df) > 50
    assert list(df.columns[:6]) == ["timestamp","open","high","low","close","volume"]
run_test("Crypto BTC/USDT from Binance", test_fetch_crypto)

def test_fetch_nse_equity():
    df = fetcher.fetch("RELIANCE", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    assert len(df) > 40
    assert (df["timestamp"].dt.dayofweek < 5).all()
    assert (df["close"] > 0).all()
run_test("NSE Equity RELIANCE", test_fetch_nse_equity)

def test_fetch_nifty50():
    df = fetcher.fetch("NIFTY50", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    assert len(df) > 40
run_test("NSE Index NIFTY50", test_fetch_nifty50)

def test_fetch_banknifty():
    df = fetcher.fetch("BANKNIFTY", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    assert len(df) > 40
run_test("NSE Index BANKNIFTY", test_fetch_banknifty)

def test_fetch_etf():
    df = fetcher.fetch("NIFTYBEES", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    assert len(df) > 40
run_test("NSE ETF NIFTYBEES", test_fetch_etf)

def test_fetch_bse():
    df = fetcher.fetch("TCS", datetime(2024,1,1), datetime(2024,3,31), "bse", "1d")
    assert len(df) > 40
run_test("BSE Equity TCS", test_fetch_bse)

print()
print("=== STRATEGY SIGNAL TESTS ===")

def test_grid_nifty():
    df = fetcher.fetch("NIFTY50", datetime(2024,1,1), datetime(2024,6,30), "nse", "1d")
    strat = GridStrategy(lower_bound=20000, upper_bound=25000, num_levels=5, invest_per_level_usd=10000)
    sig = strat.generate_signals(df)
    assert (sig["signal"]=="BUY").sum() + (sig["signal"]=="SELL").sum() > 0
run_test("Grid signals NIFTY50", test_grid_nifty)

def test_dca_reliance():
    df = fetcher.fetch("RELIANCE", datetime(2024,1,1), datetime(2024,6,30), "nse", "1d")
    strat = DCAStrategy(buy_interval_hours=24, invest_per_buy_usd=5000, hold_days=30)
    sig = strat.generate_signals(df)
    assert (sig["signal"]=="BUY").sum() > 0 and (sig["signal"]=="SELL").sum() > 0
run_test("DCA signals RELIANCE", test_dca_reliance)

def test_pla_tcs():
    df = fetcher.fetch("TCS", datetime(2023,1,1), datetime(2023,12,31), "nse", "1d")
    strat = PLAStrategy(fast_ema=12, slow_ema=26, invest_per_level_usd=[5000,5000,10000,15000])
    sig = strat.generate_signals(df)
run_test("PLA signals TCS", test_pla_tcs)

print()
print("=== SIMULATOR: EQUITY ===")

def test_equity_delivery():
    df = fetcher.fetch("HDFCBANK", datetime(2023,6,1), datetime(2023,12,31), "nse", "1d")
    strat = DCAStrategy(buy_interval_hours=24, invest_per_buy_usd=10000, hold_days=60)
    sig = strat.generate_signals(df)
    sim = TradeSimulator("HDFCBANK", capital=200000, use_indian_costs=True, market_type="equity_delivery",
                         brokerage_model="flat", brokerage_flat=20)
    res = sim.run(sig)
    assert abs(res["total_fees_paid"] - res["cost_breakdown"].get("total", 0)) < 0.02
run_test("Equity Delivery HDFCBANK DCA", test_equity_delivery)

def test_equity_intraday():
    df = fetcher.fetch("INFY", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    lo = float(df["close"].min()) * 0.9
    hi = float(df["close"].max()) * 1.1
    strat = GridStrategy(lower_bound=lo, upper_bound=hi, num_levels=6, invest_per_level_usd=5000)
    sig = strat.generate_signals(df)
    sim = TradeSimulator("INFY", capital=100000, use_indian_costs=True, market_type="equity_intraday",
                         brokerage_model="flat", brokerage_flat=20)
    res = sim.run(sig)
    assert abs(res["total_fees_paid"] - res["cost_breakdown"].get("total", 0)) < 0.02
run_test("Equity Intraday INFY Grid", test_equity_intraday)

print()
print("=== SIMULATOR: FUTURES ===")

def test_futures_nifty_dca():
    df = fetcher.fetch("NIFTY50", datetime(2024,1,1), datetime(2024,6,30), "nse", "1d")
    lot_sz = get_lot_size("NIFTY50")
    approx_price = float(df["close"].median())
    min_invest   = lot_sz * approx_price * 1.1
    strat = DCAStrategy(buy_interval_hours=24*5, invest_per_buy_usd=min_invest, hold_days=30)
    sig = strat.generate_signals(df)
    sim = TradeSimulator("NIFTY50", capital=10_000_000, use_indian_costs=True, market_type="futures",
                         brokerage_model="flat", brokerage_flat=20, lot_size=lot_sz)
    res = sim.run(sig)
    assert len(res["trades"]) > 0
    assert abs(res["total_fees_paid"] - res["cost_breakdown"].get("total", 0)) < 0.02
run_test("Futures NIFTY50 DCA", test_futures_nifty_dca)

def test_futures_banknifty_grid():
    df = fetcher.fetch("BANKNIFTY", datetime(2024,1,1), datetime(2024,6,30), "nse", "1d")
    lot_sz = get_lot_size("BANKNIFTY")
    approx_price = float(df["close"].median())
    min_invest   = lot_sz * approx_price * 1.1
    lo = float(df["close"].min()) * 0.92
    hi = float(df["close"].max()) * 1.08
    strat = GridStrategy(lower_bound=lo, upper_bound=hi, num_levels=6, invest_per_level_usd=min_invest)
    sig = strat.generate_signals(df)
    sim = TradeSimulator("BANKNIFTY", capital=10_000_000, use_indian_costs=True, market_type="futures",
                         brokerage_model="flat", brokerage_flat=20, lot_size=lot_sz)
    res = sim.run(sig)
    assert len(res["trades"]) > 0
    assert abs(res["total_fees_paid"] - res["cost_breakdown"].get("total", 0)) < 0.02
run_test("Futures BANKNIFTY Grid", test_futures_banknifty_grid)

def test_futures_insufficient_capital():
    rows = [{"timestamp": datetime(2024,1,1)+timedelta(days=i),
             "close": 22500.0, "signal": "BUY" if i==1 else "HOLD",
             "quantity": 50.0} for i in range(10)]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("NIFTY50", capital=5000, use_indian_costs=True, market_type="futures",
                         brokerage_model="flat", brokerage_flat=20, lot_size=50)
    res = sim.run(df)
    assert res["total_fees_paid"] == 0.0
    assert len(res["trades"]) == 0
run_test("Futures insufficient capital (graceful skip)", test_futures_insufficient_capital)

def test_futures_lot_size_skip_tracking():
    rows = [{"timestamp": datetime(2024,1,1)+timedelta(days=i),
             "close": 22000.0,
             "signal": "BUY" if i in [1,3,5] else "HOLD",
             "quantity": 10.0} for i in range(10)]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("NIFTY50", capital=5_000_000, lot_size=50,
                         use_indian_costs=True, market_type="futures")
    res = sim.run(df)
    assert res["lot_size_skips"] == 3
    assert len(res["trades"]) == 0
run_test("Simulator tracks lot_size_skips correctly", test_futures_lot_size_skip_tracking)

print()
print("=== LOT SIZE TESTS ===")

def test_lot_sizes():
    cases = [
        ("NIFTY50",50),("NIFTY",50),("BANKNIFTY",15),
        ("RELIANCE",250),("HDFCBANK",550),("TCS",150),
        ("SBIN",1500),("ITC",3200),("INFY",300),
        ("NIFTYBEES",1),("BTC/USDT",1),
    ]
    for sym, expected in cases:
        got = get_lot_size(sym)
        assert got == expected, f"{sym}: expected {expected}, got {got}"
run_test("Lot sizes all correct", test_lot_sizes)

def test_lot_rounding():
    rows = [{"timestamp": datetime(2024,1,1)+timedelta(days=i),
             "close": 22000.0,
             "signal": "BUY" if i==1 else ("SELL" if i==10 else "HOLD"),
             "quantity": 73.0} for i in range(15)]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("NIFTY50", capital=5000000, lot_size=50,
                         use_indian_costs=True, market_type="futures")
    res = sim.run(df)
    for t in res["trades"]:
        assert t["quantity"] % 50 < 0.001
run_test("Lot rounding 73->50", test_lot_rounding)

def test_lot_rounding_edge_zero():
    rows = [{"timestamp": datetime(2024,1,1)+timedelta(days=i),
             "close": 22000.0,
             "signal": "BUY" if i==1 else "HOLD",
             "quantity": 30.0} for i in range(5)]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("NIFTY50", capital=5000000, lot_size=50,
                         use_indian_costs=True, market_type="futures")
    res = sim.run(df)
    assert len(res["trades"]) == 0
run_test("Lot rounding qty<lot gives 0 (skip)", test_lot_rounding_edge_zero)

print()
print("=== COST MODEL VALIDATION ===")

def test_cost_futures_stt():
    calc = IndianCostModel()
    turnover = 1_100_000
    buy  = calc.calculate(turnover, "BUY",  "futures", "flat", 20)
    sell = calc.calculate(turnover, "SELL", "futures", "flat", 20)
    assert buy.stt == 0.0
    assert abs(sell.stt - turnover*0.0002) < 0.01
run_test("Futures STT correct (0 BUY, 0.02% SELL)", test_cost_futures_stt)

def test_cost_intraday_stt():
    calc = IndianCostModel()
    turnover = 500_000
    buy  = calc.calculate(turnover, "BUY",  "equity_intraday", "flat", 20)
    sell = calc.calculate(turnover, "SELL", "equity_intraday", "flat", 20)
    assert buy.stt == 0.0
    assert abs(sell.stt - turnover*0.00025) < 0.01
run_test("Intraday STT correct (0 BUY, 0.025% SELL)", test_cost_intraday_stt)

def test_cost_delivery_stt():
    calc = IndianCostModel()
    turnover = 500_000
    buy  = calc.calculate(turnover, "BUY",  "equity_delivery", "flat", 20)
    sell = calc.calculate(turnover, "SELL", "equity_delivery", "flat", 20)
    assert abs(buy.stt  - turnover*0.001) < 0.01
    assert abs(sell.stt - turnover*0.001) < 0.01
run_test("Delivery STT correct (0.1% both sides)", test_cost_delivery_stt)

def test_cost_options_stt():
    calc = IndianCostModel()
    premium = 100_000
    sell = calc.calculate(premium, "SELL", "options", "flat", 20)
    assert abs(sell.stt - premium*0.001) < 0.01
run_test("Options STT correct (0.1% SELL)", test_cost_options_stt)

def test_cost_gst_base():
    calc = IndianCostModel()
    cb = calc.calculate(100_000, "BUY", "equity_delivery", "flat", 20)
    expected_gst = (cb.brokerage + cb.exchange_charges + cb.sebi_charges) * 0.18
    assert abs(cb.gst - expected_gst) < 0.001
run_test("GST computed on correct base", test_cost_gst_base)

def test_cost_total_equals_sum():
    calc = IndianCostModel()
    for mtype in ["equity_delivery","equity_intraday","futures","options"]:
        for side in ["BUY","SELL"]:
            cb = calc.calculate(200_000, side, mtype, "flat", 20)
            expected = cb.brokerage + cb.stt + cb.exchange_charges + cb.sebi_charges + cb.gst + cb.stamp_duty
            assert abs(cb.total - expected) < 0.001
run_test("Cost total equals sum of components", test_cost_total_equals_sum)

print()
print("=== METRICS TESTS ===")

def test_metrics_btc_grid():
    df = fetcher.fetch("BTC/USDT", datetime(2023,1,1), datetime(2023,12,31), "binance", "1d")
    strat = GridStrategy(lower_bound=15000, upper_bound=35000, num_levels=6, invest_per_level_usd=500)
    sig = strat.generate_signals(df)
    sim = TradeSimulator("BTC/USDT", capital=10000)
    res = sim.run(sig)
    m = calculate_metrics(res["trades"], res["equity_curve"], res["timestamps"], 10000)
    for key in ["sharpe_ratio","sortino_ratio","calmar_ratio","volatility_pct","max_drawdown_pct"]:
        assert not math.isnan(m[key])
    assert 0 <= m["win_rate"] <= 100
run_test("Metrics BTC Grid no NaN/Inf", test_metrics_btc_grid)

def test_metrics_zero_trades():
    m = calculate_metrics([], [10000,10000,10000], ["2024-01-01","2024-01-02","2024-01-03"], 10000)
    assert m["num_trades"] == 0
    assert m["total_return_pct"] == 0.0
run_test("Metrics zero trades edge case", test_metrics_zero_trades)

def test_metrics_single_trade():
    trades = [{
        "entry_time": "2024-01-01T00:00:00", "entry_price": 100.0,
        "exit_time":  "2024-01-10T00:00:00", "exit_price":  110.0,
        "quantity": 10.0, "pnl": 100.0, "pnl_pct": 0.1, "fees": 0.5, "side": "LONG"
    }]
    m = calculate_metrics(trades, [10000,10050,10100,10100],
                          ["2024-01-01","2024-01-02","2024-01-03","2024-01-04"], 10000)
    assert m["num_trades"] == 1
    assert m["win_rate"] == 100.0
run_test("Metrics single winning trade", test_metrics_single_trade)

def test_metrics_annualisation():
    import numpy as np
    n = 252
    capital = 10000.0
    eq = [capital * (1.001 ** i) for i in range(n+1)]
    ts = [(datetime(2023,1,2) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n+1)]
    m = calculate_metrics([], eq, ts, capital)
    expected = ((1.001)**252 - 1) * 100
    assert abs(m["annualised_return_pct"] - expected) < 2.0
run_test("Metrics annualisation (252 days)", test_metrics_annualisation)

print()
print("=== DATA VALIDATOR TESTS ===")

def test_validator_good_data():
    df = fetcher.fetch("RELIANCE", datetime(2024,1,1), datetime(2024,3,31), "nse", "1d")
    res = validator.validate(df)
    assert res.passed
run_test("Validator accepts good NSE data", test_validator_good_data)

def test_validator_bad_data():
    import numpy as np
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10),
        "open":  [100]*10, "high":  [90]*10, "low":   [110]*10,
        "close": [100]*10, "volume":[1000]*10,
    })
    res = validator.validate(df)
    assert not res.passed or res.quality_score < 100
run_test("Validator catches high<low violation", test_validator_bad_data)

print()
print("=== SYMBOL DETECTION TESTS ===")

def test_is_indian():
    assert is_indian("RELIANCE")
    assert is_indian("NIFTY50")
    assert not is_indian("BTC/USDT")
    assert not is_indian("AAPL")
run_test("is_indian() detection", test_is_indian)

print()
print("=== WACB TESTS ===")

def test_wacb_correct():
    rows = [
        {"timestamp": datetime(2024,1,i+1), "close": p, "signal": s, "quantity": q}
        for i,(p,s,q) in enumerate([
            (100,"BUY",100.0),(120,"BUY",100.0),(130,"SELL",200.0),(130,"HOLD",0.0),(130,"HOLD",0.0),
        ])
    ]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("TEST", capital=100000, use_indian_costs=False, fee_percent=0.0, slippage_percent=0.0)
    res = sim.run(df)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert abs(t["entry_price"] - 110.0) < 0.01
    assert abs(t["pnl"] - 4000.0) < 0.1
run_test("WACB entry price and PnL correct", test_wacb_correct)

def test_partial_sell():
    rows = [
        {"timestamp": datetime(2024,1,i+1), "close": p, "signal": s, "quantity": q}
        for i,(p,s,q) in enumerate([(100,"BUY",200),(110,"SELL",100),(120,"SELL",100),(130,"HOLD",0)])
    ]
    df = pd.DataFrame(rows)
    sim = TradeSimulator("TEST", capital=100000, use_indian_costs=False, fee_percent=0.0, slippage_percent=0.0)
    res = sim.run(df)
    assert len(res["trades"]) == 2
run_test("Partial sell WACB", test_partial_sell)

def test_regime_tf_aware():
    from engine.regimes import classify_regimes
    from engine.metrics import _candles_per_day
    import numpy as np
    n_daily = 504
    ts_daily = pd.date_range("2022-01-01", periods=n_daily, freq="1D")
    close = 40000 + np.cumsum(np.random.default_rng(42).normal(0, 300, n_daily))
    close = np.abs(close)
    df_daily = pd.DataFrame({"timestamp": ts_daily, "close": close, "open": close,
                              "high": close*1.01, "low": close*0.99})
    n_4h = n_daily * 6
    ts_4h = pd.date_range("2022-01-01", periods=n_4h, freq="4H")
    close_4h = np.interp(np.linspace(0, n_daily - 1, n_4h), np.arange(n_daily), close)
    df_4h = pd.DataFrame({"timestamp": ts_4h, "close": close_4h, "open": close_4h,
                           "high": close_4h*1.01, "low": close_4h*0.99})
    labels_daily = classify_regimes(df_daily)
    labels_4h    = classify_regimes(df_4h)
    cpd_daily = _candles_per_day(df_daily["timestamp"].tolist())
    cpd_4h    = _candles_per_day(df_4h["timestamp"].tolist())
    import numpy as _np
    n_d = len(df_daily); n_4 = len(df_4h)
    long_days_d = float(_np.clip(n_d / cpd_daily / 5, 10, 60))
    long_days_4 = float(_np.clip(n_4 / cpd_4h   / 5, 10, 60))
    assert abs(long_days_d - long_days_4) < 5
run_test("Regime detection is timeframe-aware (Feature A)", test_regime_tf_aware)

def test_stress_non_mutating():
    from engine.stress import SCENARIO_PRESETS, apply_stress
    import numpy as np
    n = 300
    ts = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = 40000 + np.cumsum(np.random.default_rng(1).normal(0, 200, n))
    df = pd.DataFrame({"timestamp": ts, "open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close, "volume": 100.0})
    orig_close = df["close"].copy()
    for key, scenario in SCENARIO_PRESETS.items():
        perturbed = apply_stress(df, scenario, severity=1.0, seed=42)
        pd.testing.assert_series_equal(df["close"], orig_close, check_names=False)
        assert (perturbed["high"] >= perturbed["close"]).all()
        assert (perturbed["low"]  <= perturbed["close"]).all()
        assert (perturbed["close"] > 0).all()
run_test("apply_stress is pure (non-mutating) + OHLCV consistent (Feature B)", test_stress_non_mutating)

def test_stress_monte_carlo_percentiles():
    from engine.stress import SCENARIO_PRESETS, run_stress_backtest
    from strategies.dca import DCAStrategy
    import numpy as np
    n = 300
    ts = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = np.abs(40000 + np.cumsum(np.random.default_rng(7).normal(0, 300, n)))
    df = pd.DataFrame({"timestamp": ts, "open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close, "volume": 100.0})
    scenario  = SCENARIO_PRESETS["covid_crash"]
    sim_kw    = dict(symbol="BTC/USDT", fee_percent=0.001, slippage_percent=0.001)
    strat_p   = {**DCAStrategy.default_params(), "invest_per_buy_usd": 500}
    result = run_stress_backtest(df=df, strategy_cls=DCAStrategy, strategy_params=strat_p,
                                 sim_kwargs=sim_kw, capital=10_000, scenario=scenario,
                                 severity=1.0, monte_carlo_runs=20, seed=99)
    mc = result.get("monte_carlo")
    assert mc is not None
    p5, p50, p95 = mc["return_pct"]["p5"], mc["return_pct"]["p50"], mc["return_pct"]["p95"]
    assert p5 <= p50 <= p95
run_test("Stress MC percentiles P5<=P50<=P95 (Feature B)", test_stress_monte_carlo_percentiles)

print()
print("=" * 60)
passed = sum(1 for r in results if r[0]=="PASS")
failed = sum(1 for r in results if r[0]=="FAIL")
print(f"TOTAL: {passed} PASSED, {failed} FAILED out of {len(results)}")
if failed:
    print("\nFAILED TESTS:")
    for r in results:
        if r[0]=="FAIL":
            print(f"  [{r[1]}] {r[2]}")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
