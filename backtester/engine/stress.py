"""
Stress Testing Engine — scenario-based OHLCV perturbation + Monte Carlo.

Each scenario perturbs a copy of the raw OHLCV data *before* the strategy
runs, so the strategy reacts to the shock naturally rather than seeing
post-hoc equity adjustments.

Public API
----------
SCENARIO_PRESETS  : dict[str, StressScenario]  — 13 named presets
apply_stress()    : pure function, returns a perturbed DataFrame copy
run_stress_backtest() : runs baseline + N perturbed backtests, aggregates results
"""
from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from engine.metrics import calculate_metrics, _candles_per_day
from engine.simulator import TradeSimulator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StressScenario:
    name:                str
    display_name:        str
    shock_depth_pct:     float          # primary shock magnitude %
    shock_duration_days: int            # duration of main shock in trading days
    vol_multiplier:      float          # widen candle H/L range
    slip_multiplier:     float = 1.0    # multiply slippage_percent for stressed run
    spread_multiplier:   float = 1.0    # widen spread (separate from vol)
    direction:           str   = "down" # "down" | "up" | "both"
    outlier_count:       int   = 0      # random shock candles
    outlier_min_pct:     float = 20.0
    outlier_max_pct:     float = 30.0
    gap_min_pct:         float = 0.0    # open-gap magnitude
    gap_max_pct:         float = 0.0
    gap_count:           int   = 0
    pump_pct:            float = 0.0    # pre-shock pump (pump_dump) or V-recovery
    pump_duration_days:  int   = 0
    bounce_count:        int   = 0      # relief rallies (GFC)
    bounce_pct:          float = 0.0
    mean_revert:         bool  = False  # whipsaw / range-bound chop mode
    seed:                Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# 13 Scenario presets
# ─────────────────────────────────────────────────────────────────────────────

SCENARIO_PRESETS: dict[str, StressScenario] = {
    "gfc_2008": StressScenario(
        name="gfc_2008", display_name="2008 GFC Replay",
        shock_depth_pct=37.0, shock_duration_days=252, vol_multiplier=1.5,
        direction="down", bounce_count=2, bounce_pct=15.0,
    ),
    "covid_crash": StressScenario(
        name="covid_crash", display_name="2020 COVID Flash Crash",
        shock_depth_pct=34.0, shock_duration_days=30, vol_multiplier=2.5,
        direction="down", pump_pct=60.0, pump_duration_days=45,
    ),
    "flash_crash_2010": StressScenario(
        name="flash_crash_2010", display_name="2010 Flash Crash",
        shock_depth_pct=9.0, shock_duration_days=1, vol_multiplier=3.0,
        direction="down", outlier_count=1, outlier_min_pct=9.0, outlier_max_pct=20.0,
    ),
    "luna_collapse": StressScenario(
        name="luna_collapse", display_name="LUNA-style Collapse",
        shock_depth_pct=95.0, shock_duration_days=7, vol_multiplier=4.0,
        direction="down",
    ),
    "liquidity_drought": StressScenario(
        name="liquidity_drought", display_name="Liquidity Drought",
        shock_depth_pct=0.0, shock_duration_days=10, vol_multiplier=1.2,
        slip_multiplier=5.0, spread_multiplier=3.0, direction="both",
    ),
    "pump_dump": StressScenario(
        name="pump_dump", display_name="Pump & Dump",
        shock_depth_pct=60.0, shock_duration_days=3, vol_multiplier=2.0,
        direction="down", pump_pct=50.0, pump_duration_days=5,
    ),
    "whipsaw_chop": StressScenario(
        name="whipsaw_chop", display_name="Whipsaw Chop",
        shock_depth_pct=5.0, shock_duration_days=60, vol_multiplier=2.5,
        direction="both", mean_revert=True,
    ),
    "slow_bleed": StressScenario(
        name="slow_bleed", display_name="Slow Bleed Bear",
        shock_depth_pct=40.0, shock_duration_days=180, vol_multiplier=1.0,
        direction="down",
    ),
    "vol_spike": StressScenario(
        name="vol_spike", display_name="Vol Spike (VIX-style)",
        shock_depth_pct=0.0, shock_duration_days=30, vol_multiplier=3.0,
        direction="both",
    ),
    "gap_risk": StressScenario(
        name="gap_risk", display_name="Gap Risk",
        shock_depth_pct=0.0, shock_duration_days=0, vol_multiplier=1.0,
        gap_min_pct=3.0, gap_max_pct=8.0, gap_count=10, direction="both",
    ),
    "range_bound": StressScenario(
        name="range_bound", display_name="Range-bound Consolidation",
        shock_depth_pct=2.0, shock_duration_days=90, vol_multiplier=1.0,
        direction="both", mean_revert=True,
    ),
    "trend_reversal": StressScenario(
        name="trend_reversal", display_name="Trend Exhaustion + Reversal",
        shock_depth_pct=25.0, shock_duration_days=20, vol_multiplier=1.5,
        direction="down", pump_pct=30.0, pump_duration_days=60,
    ),
    "outlier_injection": StressScenario(
        name="outlier_injection", display_name="20-30% Outlier Injection",
        shock_depth_pct=0.0, shock_duration_days=0, vol_multiplier=1.0,
        outlier_count=5, outlier_min_pct=20.0, outlier_max_pct=30.0, direction="down",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Low-level OHLCV perturbation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_drift(df: pd.DataFrame, start: int, end: int,
                 total_pct: float, direction: str = "down",
                 persist: bool = False) -> None:
    """
    Geometric drift: prices in [start, end) converge to ±total_pct% by end.
    If persist=True, all prices from end onwards are also scaled by the final
    multiplier so the shock level is maintained (no snap-back to original).
    """
    end = min(end, len(df))
    n   = end - start
    if n <= 0 or total_pct <= 0:
        return
    target = (1.0 - total_pct / 100) if direction == "down" else (1.0 + total_pct / 100)
    steps  = np.arange(1, n + 1, dtype=float)
    mults  = target ** (steps / n)          # geometric interpolation 1→target
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            continue
        col_i = df.columns.get_loc(col)
        df.iloc[start:end, col_i] = df.iloc[start:end, col_i].values * mults
        if persist and end < len(df):
            # Apply the final factor to all remaining candles so there's no snap-back
            df.iloc[end:, col_i] = df.iloc[end:, col_i].values * target


def _apply_vol_scale(df: pd.DataFrame, start: int, end: int,
                     multiplier: float) -> None:
    """Widen high/low wicks around close by multiplier."""
    end = min(end, len(df))
    if multiplier <= 1.0 or start >= end:
        return
    close_col = df.columns.get_loc("close")
    high_col  = df.columns.get_loc("high")
    low_col   = df.columns.get_loc("low")
    for i in range(start, end):
        c  = df.iat[i, close_col]
        h  = df.iat[i, high_col]
        lo = df.iat[i, low_col]
        df.iat[i, high_col] = c + max(0.0, h  - c) * multiplier
        df.iat[i, low_col]  = c - max(0.0, c  - lo) * multiplier


def _inject_outliers(df: pd.DataFrame, indices: list[int],
                     shock_pcts: list[float], direction: str,
                     rng: np.random.Generator) -> None:
    """Apply single-candle shock to each index."""
    close_col = df.columns.get_loc("close")
    open_col  = df.columns.get_loc("open")  if "open"  in df.columns else -1
    high_col  = df.columns.get_loc("high")  if "high"  in df.columns else -1
    low_col   = df.columns.get_loc("low")   if "low"   in df.columns else -1
    for idx, spct in zip(indices, shock_pcts):
        if idx >= len(df):
            continue
        sign = -1.0 if direction == "down" else (1.0 if direction == "up" else float(rng.choice([-1, 1])))
        factor = max(0.001, 1.0 + sign * spct / 100)
        df.iat[idx, close_col] *= factor
        if open_col  >= 0: df.iat[idx, open_col]  *= factor
        if high_col  >= 0: df.iat[idx, high_col]  *= factor
        if low_col   >= 0: df.iat[idx, low_col]   *= factor


def _apply_gaps(df: pd.DataFrame, indices: list[int],
                gap_pcts: list[float], direction: str,
                rng: np.random.Generator) -> None:
    """Modify open prices relative to the previous candle's close."""
    if "open" not in df.columns or "close" not in df.columns:
        return
    close_col = df.columns.get_loc("close")
    open_col  = df.columns.get_loc("open")
    high_col  = df.columns.get_loc("high") if "high" in df.columns else -1
    low_col   = df.columns.get_loc("low")  if "low"  in df.columns else -1
    for idx, gpct in zip(indices, gap_pcts):
        if idx == 0 or idx >= len(df):
            continue
        prev_close = df.iat[idx - 1, close_col]
        sign = -1.0 if direction == "down" else (1.0 if direction == "up" else float(rng.choice([-1, 1])))
        new_open = max(1e-6, prev_close * (1.0 + sign * gpct / 100))
        old_open = df.iat[idx, open_col]
        ratio = new_open / old_open if old_open > 0 else 1.0
        df.iat[idx, open_col] = new_open
        # Shift high/low by same ratio to maintain candle structure
        if high_col >= 0: df.iat[idx, high_col] = max(new_open, df.iat[idx, high_col] * ratio)
        if low_col  >= 0: df.iat[idx, low_col]  = min(new_open, df.iat[idx, low_col]  * ratio)


def _apply_chop(df: pd.DataFrame, start: int, end: int,
                noise_pct: float, rng: np.random.Generator,
                mean_revert: bool = False) -> None:
    """Random per-candle returns with optional mean-reversion (AR-1)."""
    end = min(end, len(df))
    n   = end - start
    if n <= 0 or noise_pct <= 0:
        return
    returns = rng.normal(0, noise_pct / 100, size=n)
    if mean_revert:
        for i in range(1, n):
            returns[i] -= 0.5 * returns[i - 1]
    factors = np.exp(returns)
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            continue
        col_i = df.columns.get_loc(col)
        df.iloc[start:end, col_i] = df.iloc[start:end, col_i].values * factors


def _fix_ohlcv(df: pd.DataFrame) -> None:
    """Clamp negatives and restore high >= max(O,C) / low <= min(O,C)."""
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col].clip(lower=1e-6)
    if "high" in df.columns and "open" in df.columns and "close" in df.columns:
        df["high"] = df[["open", "high", "close"]].max(axis=1)
    if "low" in df.columns and "open" in df.columns and "close" in df.columns:
        df["low"] = df[["open", "low", "close"]].min(axis=1)


# ─────────────────────────────────────────────────────────────────────────────
# Public: apply_stress
# ─────────────────────────────────────────────────────────────────────────────

def apply_stress(
    df:       pd.DataFrame,
    scenario: StressScenario,
    severity: float = 1.0,
    seed:     Optional[int] = None,
) -> pd.DataFrame:
    """
    Return a new DataFrame with OHLCV perturbed according to *scenario*.

    Pure function — input df is never mutated.
    severity  : 0.5 = mild, 1.0 = moderate, 1.5 = severe
    seed      : controls start position and stochastic draws for reproducibility
    """
    out = df.copy(deep=True)
    rng = np.random.default_rng(seed if seed is not None else 42)
    n   = len(out)
    if n < 2:
        return out

    cpd   = _candles_per_day(df["timestamp"].tolist()) if "timestamp" in df.columns else 1.0
    shock = scenario.shock_depth_pct * severity
    vmult = 1.0 + (scenario.vol_multiplier - 1.0) * severity
    dur_c = max(1, round(scenario.shock_duration_days * cpd))

    # Random start in the first 60% of the dataset so the strategy has room to react
    lo_start = max(0, int(n * 0.05))
    hi_start = max(lo_start + 1, int(n * 0.60))
    start    = int(rng.integers(lo_start, hi_start))
    end      = min(start + dur_c, n)

    sname = scenario.name

    if sname == "gfc_2008":
        # Persistent bleed: prices stay down after 12-month grind; 2 relief rallies mid-crash
        _apply_drift(out, start, end, shock, "down", persist=True)
        if scenario.bounce_count > 0:
            bounce_dur = max(1, dur_c // max(1, scenario.bounce_count * 4))
            for i in range(scenario.bounce_count):
                b_start = start + dur_c * (i + 1) // (scenario.bounce_count + 1)
                b_end   = min(b_start + bounce_dur, end)
                _apply_drift(out, b_start, b_end, scenario.bounce_pct * severity, "up")
        _apply_vol_scale(out, start, end, vmult)

    elif sname == "covid_crash":
        # Crash persists until the V-recovery pump brings it back; pump does NOT persist
        _apply_drift(out, start, end, shock, "down", persist=True)
        if scenario.pump_pct > 0:
            pump_dur = max(1, round(scenario.pump_duration_days * cpd))
            pump_end = min(end + pump_dur, n)
            # Recovery partially reverses the crash — persist the recovered level
            _apply_drift(out, end, pump_end, scenario.pump_pct * severity, "up", persist=True)
        _apply_vol_scale(out, start, end, vmult)

    elif sname == "flash_crash_2010":
        # Single-candle outlier spike — prices recover same day, no persistence needed
        shock_idx = start
        _inject_outliers(out, [shock_idx], [shock], "down", rng)
        _apply_vol_scale(out, shock_idx, min(shock_idx + 3, n), vmult)

    elif sname == "luna_collapse":
        # Asymptotic collapse with no recovery — must persist
        _apply_drift(out, start, end, min(shock, 99.0), "down", persist=True)
        _apply_vol_scale(out, start, end, vmult)

    elif sname == "liquidity_drought":
        smult = max(1.0, scenario.spread_multiplier * severity)
        _apply_vol_scale(out, start, end, smult)

    elif sname == "pump_dump":
        # Pump then dump back below start — dump persists
        pump_dur = max(1, round(scenario.pump_duration_days * cpd))
        pump_end = min(start + pump_dur, n)
        _apply_drift(out, start, pump_end, scenario.pump_pct * severity, "up")
        dump_end = min(pump_end + dur_c, n)
        _apply_drift(out, pump_end, dump_end, shock, "down", persist=True)

    elif sname in ("whipsaw_chop", "range_bound"):
        _apply_chop(out, start, end, shock, rng, mean_revert=scenario.mean_revert)
        _apply_vol_scale(out, start, end, vmult)

    elif sname == "slow_bleed":
        # Gradual bleed persists — no snap-back
        _apply_drift(out, start, end, shock, "down", persist=True)

    elif sname == "vol_spike":
        _apply_vol_scale(out, start, end, vmult)

    elif sname == "gap_risk":
        gc = max(1, round(scenario.gap_count * severity))
        g_indices = sorted(rng.choice(max(1, n - 1), size=min(gc, max(1, n - 1)), replace=False).tolist())
        g_pcts    = rng.uniform(scenario.gap_min_pct, scenario.gap_max_pct, size=len(g_indices)).tolist()
        _apply_gaps(out, g_indices, g_pcts, scenario.direction, rng)

    elif sname == "trend_reversal":
        # Pump then reversal — reversal persists below the original start price
        pump_dur = max(1, round(scenario.pump_duration_days * cpd))
        pump_end = min(start + pump_dur, n)
        _apply_drift(out, start, pump_end, scenario.pump_pct * severity, "up")
        rev_end  = min(pump_end + dur_c, n)
        _apply_drift(out, pump_end, rev_end, shock, "down", persist=True)
        _apply_vol_scale(out, start, rev_end, vmult)

    elif sname == "outlier_injection":
        pass  # handled below

    # Outlier injection — standalone or layered on any scenario
    if scenario.outlier_count > 0:
        oc       = max(1, round(scenario.outlier_count * severity))
        indices  = sorted(rng.choice(n, size=min(oc, n), replace=False).tolist())
        opcts    = rng.uniform(scenario.outlier_min_pct, scenario.outlier_max_pct, size=len(indices)).tolist()
        _inject_outliers(out, indices, opcts, scenario.direction, rng)

    _fix_ohlcv(out)
    logger.debug("apply_stress(%s, sev=%.1f, seed=%s): n=%d  start=%d  end=%d",
                 sname, severity, seed, n, start, end)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Internal: single backtest run
# ─────────────────────────────────────────────────────────────────────────────

def _single_backtest(
    df:              pd.DataFrame,
    strategy_cls,
    strategy_params: dict,
    sim_kwargs:      dict,
    capital:         float,
) -> dict:
    """Run one backtest; return metrics dict. Absorbs exceptions as zeroed metrics."""
    try:
        inst    = strategy_cls(**strategy_params)
        sigs    = inst.generate_signals(df.copy())
        sim     = TradeSimulator(capital=capital, **sim_kwargs)
        out     = sim.run(sigs)
        return calculate_metrics(
            trades          = out["trades"],
            equity_curve    = out["equity_curve"],
            timestamps      = out["timestamps"],
            initial_capital = capital,
        )
    except Exception as exc:
        logger.warning("Stress _single_backtest failed: %s", exc)
        return {
            "total_return_pct": 0.0, "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0, "max_drawdown_pct": 0.0,
            "win_rate": 0.0, "num_trades": 0,
            "equity_curve": [capital],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_stress_backtest
# ─────────────────────────────────────────────────────────────────────────────

def run_stress_backtest(
    df:                  pd.DataFrame,
    strategy_cls,
    strategy_params:     dict,
    sim_kwargs:          dict,          # TradeSimulator kwargs (without capital)
    capital:             float,
    scenario:            StressScenario,
    severity:            float = 1.0,
    monte_carlo_runs:    int   = 1,
    extra_outlier_count: int   = 0,
    seed:                Optional[int] = None,
) -> dict:
    """
    Run baseline + N stressed backtests; return aggregated results dict.

    sim_kwargs keys: symbol, fee_percent, slippage_percent, use_indian_costs,
                     market_type, brokerage_model, brokerage_flat, brokerage_pct,
                     lot_size  (all optional — TradeSimulator defaults apply)
    """
    master_rng = np.random.default_rng(seed)

    # ── Baseline (no perturbation) ──────────────────────────────────────────
    baseline = _single_backtest(df, strategy_cls, strategy_params, sim_kwargs, capital)

    # ── Build effective scenario (add extra outliers if requested) ──────────
    eff_scenario = deepcopy(scenario)
    if extra_outlier_count > 0:
        eff_scenario.outlier_count += extra_outlier_count

    # Stressed sim_kwargs: apply slip_multiplier
    stressed_sim_kw = {**sim_kwargs}
    if eff_scenario.slip_multiplier > 1.0:
        base_slip = stressed_sim_kw.get("slippage_percent", 0.001)
        stressed_sim_kw["slippage_percent"] = base_slip * eff_scenario.slip_multiplier * severity

    # ── Monte Carlo / deterministic runs ───────────────────────────────────
    per_run: list[dict] = []
    equity_curves:   list[list[float]] = []
    price_curves:    list[list[float]] = []

    n_runs = max(1, monte_carlo_runs)
    for _ in range(n_runs):
        run_seed = int(master_rng.integers(0, 2 ** 31))
        # Vary shock magnitude ±25% per run so paths fan out realistically.
        # Without this, all runs share the same severity and only differ in
        # *when* the shock starts — producing near-identical paths.
        run_severity = (severity * float(master_rng.uniform(0.75, 1.25))
                        if n_runs > 1 else severity)
        perturbed_df = apply_stress(df, eff_scenario, severity=run_severity, seed=run_seed)
        m = _single_backtest(perturbed_df, strategy_cls, strategy_params,
                             stressed_sim_kw, capital)
        per_run.append({
            "return_pct":        m.get("total_return_pct",     0.0),
            "sharpe":            m.get("sharpe_ratio",         0.0),
            "sortino":           m.get("sortino_ratio",        0.0),
            "calmar":            m.get("calmar_ratio",         0.0),
            "max_dd_pct":        m.get("max_drawdown_pct",     0.0),
            "win_rate":          m.get("win_rate",              0.0),
            "num_trades":        m.get("num_trades",             0),
            "final_equity":      m.get("final_equity",         capital),
            "annualized_return": m.get("annualised_return_pct", 0.0),
        })
        equity_curves.append(m.get("equity_curve", [capital]))
        price_curves.append(perturbed_df["close"].tolist())

    # ── Representative (median-return) run for charting ─────────────────────
    returns  = np.array([r["return_pct"] for r in per_run])
    p50_val  = float(np.median(returns))
    rep_idx  = int(np.argmin(np.abs(returns - p50_val)))

    # ── Monte Carlo percentile aggregation ───────────────────────────────────
    mc_result: Optional[dict] = None
    if n_runs > 1:
        def _pcts(arr: np.ndarray, include_best: bool = True) -> dict:
            d = {
                "p5":   round(float(np.percentile(arr,  5)), 4),
                "p50":  round(float(np.percentile(arr, 50)), 4),
                "p95":  round(float(np.percentile(arr, 95)), 4),
                "worst": round(float(arr.min()), 4),
            }
            if include_best:
                d["best"] = round(float(arr.max()), 4)
            return d

        mc_result = {
            "runs":             n_runs,
            "return_pct":       _pcts(returns),
            "max_drawdown_pct": _pcts(np.array([r["max_dd_pct"] for r in per_run]), include_best=False),
            "sharpe":           _pcts(np.array([r["sharpe"]     for r in per_run]), include_best=False),
            "sortino":          _pcts(np.array([r["sortino"]    for r in per_run]), include_best=False),
            "win_rate":         _pcts(np.array([r["win_rate"]   for r in per_run]), include_best=False),
            "per_run":          per_run,
        }

    # ── Build equity fan (P5/P50/P95 per timestamp) for charting ────────────
    equity_fan: Optional[dict] = None
    if n_runs > 1 and equity_curves:
        min_len = min(len(ec) for ec in equity_curves)
        mat     = np.array([ec[:min_len] for ec in equity_curves])
        equity_fan = {
            "p5":  [round(v, 4) for v in np.percentile(mat, 5,  axis=0).tolist()],
            "p50": [round(v, 4) for v in np.percentile(mat, 50, axis=0).tolist()],
            "p95": [round(v, 4) for v in np.percentile(mat, 95, axis=0).tolist()],
        }

    # ── Spaghetti curves for individual-path MC visualization ────────────────
    # Return up to 100 equity paths, each subsampled to ≤200 points
    spaghetti_data: Optional[dict] = None
    if n_runs > 1 and equity_curves:
        max_lines = min(100, n_runs)
        if n_runs > max_lines:
            sample_idx = np.round(np.linspace(0, n_runs - 1, max_lines)).astype(int).tolist()
        else:
            sample_idx = list(range(n_runs))

        ref_len = min(len(ec) for ec in equity_curves)
        n_ts    = min(ref_len, 200)
        ts_idx  = np.round(np.linspace(0, ref_len - 1, n_ts)).astype(int).tolist()

        spaghetti_runs = []
        for ri in sample_idx:
            ec = equity_curves[ri]
            spaghetti_runs.append({
                "run_idx":   ri,
                "return_pct": round(float(per_run[ri]["return_pct"]), 4),
                "max_dd_pct": round(float(per_run[ri]["max_dd_pct"]), 4),
                "sharpe":     round(float(per_run[ri]["sharpe"]),     4),
                "win_rate":   round(float(per_run[ri]["win_rate"]),   4),
                "equity": [round(float(ec[i]) if i < len(ec) else float(ec[-1]), 2) for i in ts_idx],
            })
        spaghetti_data = {"ts_indices": ts_idx, "runs": spaghetti_runs}

    timestamps     = [str(t) for t in df["timestamp"].tolist()] if "timestamp" in df.columns else []
    baseline_eq    = baseline.get("equity_curve", [capital])
    stressed_eq    = equity_curves[rep_idx] if equity_curves else [capital]
    stressed_price = price_curves[rep_idx]  if price_curves  else df["close"].tolist()

    return {
        "scenario": {
            "name":         scenario.name,
            "display_name": getattr(scenario, "display_name", scenario.name),
            "severity":     severity,
            "params": {
                "shock_depth_pct":     scenario.shock_depth_pct,
                "shock_duration_days": scenario.shock_duration_days,
                "vol_multiplier":      scenario.vol_multiplier,
                "slip_multiplier":     scenario.slip_multiplier,
            },
        },
        "baseline": {
            k: v for k, v in baseline.items()
            if k not in ("equity_curve", "drawdowns", "timestamps", "trades")
        },
        "stressed": {
            **per_run[rep_idx],
            "equity_curve":  stressed_eq,
        } if per_run else {
            "return_pct": 0, "sharpe": 0, "max_dd_pct": 0,
            "win_rate": 0, "num_trades": 0, "equity_curve": [capital],
        },
        "monte_carlo": mc_result,
        "series": {
            "timestamps":      timestamps,
            "baseline_equity": baseline_eq,
            "stressed_equity": stressed_eq,
            "stressed_price":  stressed_price,
            "baseline_price":  df["close"].tolist(),
            "equity_fan":      equity_fan,
            "spaghetti":       spaghetti_data,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: aggregate_stress_results  (used by SSE streaming endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_stress_results(
    baseline:      dict,
    per_run:       list[dict],
    equity_curves: list[list[float]],
    price_curves:  list[list[float]],
    df:            pd.DataFrame,
    capital:       float,
    scenario:      StressScenario,
    severity:      float,
) -> dict:
    """
    Aggregate collected per-run data into the same response structure that
    run_stress_backtest() returns.  Used by the SSE streaming endpoint after
    collecting all runs one-by-one.
    """
    n_runs = len(per_run)
    if n_runs == 0:
        return {}

    returns = np.array([r["return_pct"] for r in per_run])
    p50_val = float(np.median(returns))
    rep_idx = int(np.argmin(np.abs(returns - p50_val)))

    def _pcts(arr: np.ndarray, include_best: bool = True) -> dict:
        d = {
            "p5":    round(float(np.percentile(arr,  5)), 4),
            "p50":   round(float(np.percentile(arr, 50)), 4),
            "p95":   round(float(np.percentile(arr, 95)), 4),
            "worst": round(float(arr.min()), 4),
        }
        if include_best:
            d["best"] = round(float(arr.max()), 4)
        return d

    mc_result: Optional[dict] = None
    if n_runs > 1:
        mc_result = {
            "runs":             n_runs,
            "return_pct":       _pcts(returns),
            "max_drawdown_pct": _pcts(np.array([r["max_dd_pct"] for r in per_run]), include_best=False),
            "sharpe":           _pcts(np.array([r["sharpe"]     for r in per_run]), include_best=False),
            "sortino":          _pcts(np.array([r.get("sortino", 0) for r in per_run]), include_best=False),
            "win_rate":         _pcts(np.array([r["win_rate"]   for r in per_run]), include_best=False),
            "per_run":          per_run,
        }

    equity_fan: Optional[dict] = None
    if n_runs > 1 and equity_curves:
        min_len = min(len(ec) for ec in equity_curves)
        mat     = np.array([ec[:min_len] for ec in equity_curves])
        equity_fan = {
            "p5":  [round(v, 4) for v in np.percentile(mat,  5, axis=0).tolist()],
            "p50": [round(v, 4) for v in np.percentile(mat, 50, axis=0).tolist()],
            "p95": [round(v, 4) for v in np.percentile(mat, 95, axis=0).tolist()],
        }

    spaghetti_data: Optional[dict] = None
    if n_runs > 1 and equity_curves:
        max_lines  = min(100, n_runs)
        sample_idx = (np.round(np.linspace(0, n_runs - 1, max_lines)).astype(int).tolist()
                      if n_runs > max_lines else list(range(n_runs)))
        ref_len = min(len(ec) for ec in equity_curves)
        n_ts    = min(ref_len, 200)
        ts_idx  = np.round(np.linspace(0, ref_len - 1, n_ts)).astype(int).tolist()
        spaghetti_runs = []
        for ri in sample_idx:
            ec = equity_curves[ri]
            spaghetti_runs.append({
                "run_idx":    ri,
                "return_pct": round(float(per_run[ri]["return_pct"]), 4),
                "max_dd_pct": round(float(per_run[ri]["max_dd_pct"]), 4),
                "sharpe":     round(float(per_run[ri]["sharpe"]),     4),
                "win_rate":   round(float(per_run[ri]["win_rate"]),   4),
                "equity": [round(float(ec[i]) if i < len(ec) else float(ec[-1]), 2) for i in ts_idx],
            })
        spaghetti_data = {"ts_indices": ts_idx, "runs": spaghetti_runs}

    timestamps     = [str(t) for t in df["timestamp"].tolist()] if "timestamp" in df.columns else []
    baseline_eq    = baseline.get("equity_curve", [capital])
    stressed_eq    = equity_curves[rep_idx] if equity_curves else [capital]
    stressed_price = price_curves[rep_idx]  if price_curves  else df["close"].tolist()

    return {
        "scenario": {
            "name":         scenario.name,
            "display_name": getattr(scenario, "display_name", scenario.name),
            "severity":     severity,
            "params": {
                "shock_depth_pct":     scenario.shock_depth_pct,
                "shock_duration_days": scenario.shock_duration_days,
                "vol_multiplier":      scenario.vol_multiplier,
                "slip_multiplier":     scenario.slip_multiplier,
            },
        },
        "baseline": {k: v for k, v in baseline.items()
                     if k not in ("equity_curve", "drawdowns", "timestamps", "trades")},
        "stressed": {
            **per_run[rep_idx],
            "equity_curve": stressed_eq,
        } if per_run else {
            "return_pct": 0, "sharpe": 0, "max_dd_pct": 0,
            "win_rate": 0, "num_trades": 0, "equity_curve": [capital],
        },
        "monte_carlo": mc_result,
        "series": {
            "timestamps":      timestamps,
            "baseline_equity": baseline_eq,
            "stressed_equity": stressed_eq,
            "stressed_price":  stressed_price,
            "baseline_price":  df["close"].tolist(),
            "equity_fan":      equity_fan,
            "spaghetti":       spaghetti_data,
        },
    }


# Expose internal helper so the SSE endpoint can call it directly
run_single_backtest = _single_backtest
