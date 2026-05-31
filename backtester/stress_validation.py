"""
Stress Test Validation Script
==============================
Tests all 13 scenarios x 3 strategies (GRID/DCA/PLA) x 3 assets
= 117 base tests, plus severity variations (mild/moderate/severe) for
the top 5 most dangerous scenarios = additional combinations.

Usage: python stress_validation.py
"""

import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

import requests

BASE_URL = "http://localhost:8000"
STRESS_URL = f"{BASE_URL}/api/stress/run"
MAX_WORKERS = 4

# ── Scenario definitions (13 total) ────────────────────────────────────────────
ALL_SCENARIOS = [
    "gfc_2008",
    "covid_crash",
    "flash_crash_2010",
    "luna_collapse",
    "liquidity_drought",
    "pump_dump",
    "whipsaw_chop",
    "slow_bleed",
    "vol_spike",
    "gap_risk",
    "range_bound",
    "trend_reversal",
    "outlier_injection",
]
assert len(ALL_SCENARIOS) == 13, f"Expected 13 scenarios, got {len(ALL_SCENARIOS)}"

# Top 5 "most dangerous" scenarios — add severity variants
TOP_5_SCENARIOS = ["luna_collapse", "slow_bleed", "gfc_2008", "covid_crash", "pump_dump"]
SEVERITY_VARIANTS = [0.5, 1.0, 1.5]  # mild, moderate, severe

# ── Asset / strategy combinations ──────────────────────────────────────────────
# Each entry: (symbol, source, capital, strategy, strategy_params, extra_sim_kwargs)

ASSET_STRATEGY_CONFIGS = []

# ── BTC/USDT (Binance) ─────────────────────────────────────────────────────────
BTC_COMMON = dict(
    symbol="BTC/USDT", source="binance", interval="1d",
    start_date="2021-01-01", end_date="2023-12-31",
    capital=10000.0,
    use_indian_costs=False, market_type="equity_delivery",
)

ASSET_STRATEGY_CONFIGS.append({
    **BTC_COMMON, "strategy": "GRID",
    "params": {
        "lower_bound": 20000.0, "upper_bound": 60000.0,
        "num_levels": 5, "spacing": "linear",
        "invest_per_level_usd": 500.0,
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **BTC_COMMON, "strategy": "DCA",
    "params": {
        "buy_interval_hours": 24, "invest_per_buy_usd": 200.0,
        "hold_days": 30, "exit_type": "profit", "profit_target_pct": 10.0,
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **BTC_COMMON, "strategy": "PLA",
    "params": {
        "fast_ema": 9, "slow_ema": 21,
        "entry_levels": [0.0, -1.0, -2.5, -4.0],
        "invest_per_level_usd": [300.0, 300.0, 600.0, 900.0],
        "exit_type": "take_profit", "take_profit_pct": 5.0,
    },
})

# ── AAPL (yfinance) ─────────────────────────────────────────────────────────────
AAPL_COMMON = dict(
    symbol="AAPL", source="yfinance", interval="1d",
    start_date="2021-01-01", end_date="2023-12-31",
    capital=10000.0,
    use_indian_costs=False, market_type="equity_delivery",
)

ASSET_STRATEGY_CONFIGS.append({
    **AAPL_COMMON, "strategy": "GRID",
    "params": {
        "lower_bound": 150.0, "upper_bound": 220.0,
        "num_levels": 5, "spacing": "linear",
        "invest_per_level_usd": 300.0,
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **AAPL_COMMON, "strategy": "DCA",
    "params": {
        "buy_interval_hours": 24, "invest_per_buy_usd": 200.0,
        "hold_days": 30, "exit_type": "time",
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **AAPL_COMMON, "strategy": "PLA",
    "params": {
        "fast_ema": 12, "slow_ema": 26,
        "entry_levels": [0.0, -1.0, -2.5, -4.0],
        "invest_per_level_usd": [300.0, 300.0, 600.0, 900.0],
        "exit_type": "crossover",
    },
})

# ── NIFTY50 (NSE) ─────────────────────────────────────────────────────────────
NIFTY_COMMON = dict(
    symbol="NIFTY50", source="nse", interval="1d",
    start_date="2021-01-01", end_date="2023-12-31",
    capital=500000.0,
    use_indian_costs=True, market_type="equity_delivery",
)

ASSET_STRATEGY_CONFIGS.append({
    **NIFTY_COMMON, "strategy": "GRID",
    "params": {
        "lower_bound": 14000.0, "upper_bound": 20000.0,
        "num_levels": 5, "spacing": "linear",
        "invest_per_level_usd": 20000.0,
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **NIFTY_COMMON, "strategy": "DCA",
    "params": {
        "buy_interval_hours": 24, "invest_per_buy_usd": 5000.0,
        "hold_days": 30, "exit_type": "time",
    },
})
ASSET_STRATEGY_CONFIGS.append({
    **NIFTY_COMMON, "strategy": "PLA",
    "params": {
        "fast_ema": 9, "slow_ema": 21,
        "entry_levels": [0.0, -1.0, -2.5, -4.0],
        "invest_per_level_usd": [25000.0, 25000.0, 50000.0, 75000.0],
        "exit_type": "take_profit", "take_profit_pct": 5.0,
    },
})

assert len(ASSET_STRATEGY_CONFIGS) == 9, f"Expected 9 asset/strategy configs, got {len(ASSET_STRATEGY_CONFIGS)}"


# ── Build test matrix ──────────────────────────────────────────────────────────

def build_test_cases():
    """Build 117+ test case dicts."""
    cases = []

    # 13 scenarios x 9 asset/strategy combos = 117 tests (severity=1.0)
    for cfg in ASSET_STRATEGY_CONFIGS:
        for scenario in ALL_SCENARIOS:
            cases.append({
                **cfg,
                "scenario_key": scenario,
                "severity": 1.0,
                "monte_carlo_runs": 5,  # small MC for ordering check
                "seed": 42,
                "_label": f"{cfg['symbol']}|{cfg['strategy']}|{scenario}|sev=1.0",
                "_asset": cfg["symbol"],
                "_strategy": cfg["strategy"],
                "_scenario": scenario,
                "_severity": 1.0,
            })

    # Top-5 scenarios x 3 severities x 9 combos (but severity=1.0 already counted)
    # Only add mild (0.5) and severe (1.5) to avoid duplicates
    for cfg in ASSET_STRATEGY_CONFIGS:
        for scenario in TOP_5_SCENARIOS:
            for sev in [0.5, 1.5]:
                cases.append({
                    **cfg,
                    "scenario_key": scenario,
                    "severity": sev,
                    "monte_carlo_runs": 5,
                    "seed": 42,
                    "_label": f"{cfg['symbol']}|{cfg['strategy']}|{scenario}|sev={sev}",
                    "_asset": cfg["symbol"],
                    "_strategy": cfg["strategy"],
                    "_scenario": scenario,
                    "_severity": sev,
                })

    return cases


# ── Single test runner ─────────────────────────────────────────────────────────

def _is_finite(val):
    """Return True if val is a finite float (not NaN, not Inf)."""
    if val is None:
        return False
    try:
        return math.isfinite(float(val))
    except (TypeError, ValueError):
        return False


def _has_nan_or_inf(curve):
    """Return True if the equity curve list contains any NaN or Inf."""
    for v in curve:
        if v is None:
            return True
        try:
            if not math.isfinite(float(v)):
                return True
        except (TypeError, ValueError):
            return True
    return False


def run_single_test(case: dict) -> dict:
    """POST one stress test and validate the response. Returns result dict."""
    label = case["_label"]
    # Build request payload (strip private _keys)
    payload = {k: v for k, v in case.items() if not k.startswith("_")}
    # Convert date strings to proper format
    payload["start_date"] = str(payload["start_date"])
    payload["end_date"] = str(payload["end_date"])

    result = {
        "label": label,
        "asset": case["_asset"],
        "strategy": case["_strategy"],
        "scenario": case["_scenario"],
        "severity": case["_severity"],
        "status": "UNKNOWN",
        "errors": [],
        "http_status": None,
        "baseline_return": None,
        "stressed_return": None,
        "return_delta": None,
        "verdict": None,
        "mc_ok": None,
    }

    try:
        t0 = time.time()
        resp = requests.post(STRESS_URL, json=payload, timeout=120)
        elapsed = round(time.time() - t0, 1)
        result["elapsed_s"] = elapsed
        result["http_status"] = resp.status_code

        if resp.status_code != 200:
            result["status"] = "FAILED"
            result["errors"].append(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return result

        data = resp.json()
        errors = []

        # ── Extract key fields ──────────────────────────────────────────────
        baseline = data.get("baseline", {})
        stressed = data.get("stressed", {})
        series   = data.get("series", {})
        mc       = data.get("monte_carlo")

        baseline_return = baseline.get("total_return_pct")
        stressed_return = stressed.get("return_pct")
        result["baseline_return"] = baseline_return
        result["stressed_return"] = stressed_return

        if baseline_return is not None and stressed_return is not None:
            try:
                result["return_delta"] = round(float(stressed_return) - float(baseline_return), 4)
            except (TypeError, ValueError):
                pass

        # ── Check 1: stressed.return_pct is finite ──────────────────────────
        if not _is_finite(stressed_return):
            errors.append(f"stressed.return_pct is not finite: {stressed_return!r}")

        # ── Check 2: win_rate in 0–100 range ───────────────────────────────
        win_rate = stressed.get("win_rate")
        if win_rate is not None:
            try:
                wr = float(win_rate)
                if wr < 0 or wr > 100:
                    errors.append(f"win_rate out of [0,100]: {wr}")
            except (TypeError, ValueError):
                errors.append(f"win_rate not numeric: {win_rate!r}")

        # ── Check 3: series length consistency ─────────────────────────────
        ts_len = len(series.get("timestamps", []))
        be_len = len(series.get("baseline_equity", []))
        se_len = len(series.get("stressed_equity", []))

        if ts_len > 0 and be_len > 0 and se_len > 0:
            # Equity curves can differ from timestamps (1 extra for final equity)
            # but baseline_equity and stressed_equity should be same length
            if be_len != se_len:
                errors.append(
                    f"Series length mismatch: baseline_equity={be_len}, stressed_equity={se_len}"
                )
        elif ts_len == 0 or be_len == 0:
            errors.append(f"Empty series: timestamps={ts_len}, baseline_equity={be_len}")

        # ── Check 4: No NaN/Inf in equity curves ───────────────────────────
        for curve_name in ("baseline_equity", "stressed_equity"):
            curve = series.get(curve_name, [])
            if curve and _has_nan_or_inf(curve):
                errors.append(f"{curve_name} contains NaN or Inf")

        # ── Check 5: MC p5 ≤ p50 ≤ p95 ordering ───────────────────────────
        mc_ok = True
        if mc and "return_pct" in mc:
            rp = mc["return_pct"]
            p5  = rp.get("p5")
            p50 = rp.get("p50")
            p95 = rp.get("p95")
            if p5 is not None and p50 is not None and p95 is not None:
                if not (p5 <= p50 <= p95):
                    errors.append(
                        f"MC return_pct ordering violated: p5={p5}, p50={p50}, p95={p95}"
                    )
                    mc_ok = False
        result["mc_ok"] = mc_ok

        # ── Verdict: DEGRADED or IMPROVED or NEUTRAL ───────────────────────
        if result["return_delta"] is not None:
            delta = result["return_delta"]
            if delta < -2.0:
                result["verdict"] = "DEGRADED"
            elif delta > 2.0:
                result["verdict"] = "IMPROVED"
            else:
                result["verdict"] = "NEUTRAL"
        else:
            result["verdict"] = "UNKNOWN"

        result["status"] = "FAILED" if errors else "PASSED"
        result["errors"] = errors

    except requests.exceptions.Timeout:
        result["status"] = "FAILED"
        result["errors"].append("Request timed out (>120s)")
    except Exception as exc:
        result["status"] = "FAILED"
        result["errors"].append(f"Exception: {exc}")

    return result


# ── Main runner ────────────────────────────────────────────────────────────────

def main():
    # Quick health check
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"[ERROR] Backend health check failed: HTTP {r.status_code}")
            sys.exit(1)
        print(f"[OK] Backend is up at {BASE_URL}")
    except Exception as exc:
        print(f"[ERROR] Cannot reach backend at {BASE_URL}: {exc}")
        sys.exit(1)

    test_cases = build_test_cases()
    total = len(test_cases)
    # Count base tests
    base_count = sum(1 for c in test_cases if c["_severity"] == 1.0)
    sev_count  = total - base_count
    print(f"\nTest matrix: {base_count} base tests (13×9) + {sev_count} severity variants = {total} total")
    print(f"Running with {MAX_WORKERS} parallel workers...\n")

    results = []
    done = 0
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_case = {executor.submit(run_single_test, c): c for c in test_cases}
        for future in as_completed(future_to_case):
            res = future.result()
            results.append(res)
            done += 1
            status_icon = "PASS" if res["status"] == "PASSED" else "FAIL"
            delta_str = (f"Δ={res['return_delta']:+.1f}%" if res["return_delta"] is not None else "Δ=N/A")
            print(
                f"  [{done:3d}/{total}] {status_icon} {res['label']:<65} "
                f"{delta_str:>10}  {res['verdict'] or '':>8}"
                + (f"  [{', '.join(res['errors'][:1])}]" if res["errors"] else "")
            )

    elapsed_total = round(time.time() - t_start, 1)

    # ── Stats ──────────────────────────────────────────────────────────────────
    passed  = [r for r in results if r["status"] == "PASSED"]
    failed  = [r for r in results if r["status"] == "FAILED"]
    degraded = [r for r in results if r["verdict"] == "DEGRADED"]

    print("\n" + "=" * 90)
    print("SUMMARY TABLE — grouped by scenario (severity=1.0 only)")
    print("=" * 90)

    base_results = [r for r in results if r["severity"] == 1.0]

    # Collect per-scenario stats
    scenario_stats = {}
    for scen in ALL_SCENARIOS:
        sc_results = [r for r in base_results if r["scenario"] == scen]
        if not sc_results:
            continue

        deltas = [r["return_delta"] for r in sc_results if r["return_delta"] is not None]
        median_delta = sorted(deltas)[len(deltas) // 2] if deltas else None
        n_degraded = sum(1 for r in sc_results if r["verdict"] == "DEGRADED")
        n_failed   = sum(1 for r in sc_results if r["status"] == "FAILED")
        n_passed   = sum(1 for r in sc_results if r["status"] == "PASSED")

        # Semantic sense check: scenarios with shock_depth >= 25% "should" mostly degrade
        should_degrade = scen in ("luna_collapse", "slow_bleed", "gfc_2008",
                                  "covid_crash", "pump_dump", "trend_reversal")
        semantic_ok = True
        semantic_note = ""
        if should_degrade:
            if median_delta is not None and median_delta > 5.0:
                semantic_ok = False
                semantic_note = "UNEXPECTED IMPROVEMENT"
            else:
                semantic_note = "expected"
        else:
            semantic_note = "neutral/mixed ok"

        scenario_stats[scen] = {
            "median_delta":  median_delta,
            "n_degraded":    n_degraded,
            "n_failed":      n_failed,
            "n_passed":      n_passed,
            "semantic_ok":   semantic_ok,
            "semantic_note": semantic_note,
        }

    # Print table header
    print(f"\n{'Scenario':<25} {'Median Δ%':>10} {'DEGRADED':>9} {'FAILED':>7} {'PASSED':>7}  Semantic")
    print("-" * 80)
    for scen in ALL_SCENARIOS:
        s = scenario_stats.get(scen)
        if not s:
            continue
        delta_str  = f"{s['median_delta']:+.2f}%" if s['median_delta'] is not None else "  N/A"
        sem_marker = ("  [!WARN]" if not s["semantic_ok"] else "")
        print(
            f"  {scen:<23} {delta_str:>10}  {s['n_degraded']:>7}  {s['n_failed']:>6}  "
            f"{s['n_passed']:>6}   {s['semantic_note']}{sem_marker}"
        )

    # ── Severity comparison (top-5 scenarios) ─────────────────────────────────
    print("\n" + "=" * 90)
    print("SEVERITY COMPARISON — Top-5 scenarios (median Δ% by severity)")
    print("=" * 90)
    print(f"\n{'Scenario':<25} {'Mild(0.5)':>12} {'Mod(1.0)':>12} {'Severe(1.5)':>12}")
    print("-" * 65)
    for scen in TOP_5_SCENARIOS:
        row = []
        for sev in [0.5, 1.0, 1.5]:
            sc_results = [r for r in results if r["scenario"] == scen and r["severity"] == sev]
            deltas = [r["return_delta"] for r in sc_results if r["return_delta"] is not None]
            if deltas:
                med = sorted(deltas)[len(deltas) // 2]
                row.append(f"{med:+.2f}%")
            else:
                row.append("  N/A")
        print(f"  {scen:<23} {row[0]:>12} {row[1]:>12} {row[2]:>12}")

    # ── Per-failure detail ─────────────────────────────────────────────────────
    if failed:
        print(f"\n{'=' * 90}")
        print(f"FAILURES ({len(failed)} total)")
        print("=" * 90)
        for r in failed:
            print(f"\n  {r['label']}")
            print(f"    HTTP: {r['http_status']}  elapsed: {r.get('elapsed_s', '?')}s")
            for e in r["errors"]:
                print(f"    ERROR: {e}")

    # ── MC ordering failures ────────────────────────────────────────────────────
    mc_fails = [r for r in results if r["mc_ok"] is False]
    if mc_fails:
        print(f"\n{'=' * 90}")
        print(f"MC PERCENTILE ORDERING VIOLATIONS ({len(mc_fails)} total)")
        print("=" * 90)
        for r in mc_fails:
            print(f"  {r['label']}")

    # ── Most dangerous scenario ────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("OVERALL STATISTICS")
    print("=" * 90)
    print(f"  Total tests:        {total}")
    print(f"  Passed:             {len(passed)}")
    print(f"  Failed:             {len(failed)}")
    print(f"  Pass rate:          {100*len(passed)/total:.1f}%")
    print(f"  Total elapsed:      {elapsed_total}s")

    # Most dangerous = scenario with worst (most negative) median delta
    worst_scen = None
    worst_delta = float("inf")
    for scen, s in scenario_stats.items():
        if s["median_delta"] is not None and s["median_delta"] < worst_delta:
            worst_delta = s["median_delta"]
            worst_scen  = scen

    if worst_scen:
        print(f"\n  Most dangerous scenario: {worst_scen} (median Δ = {worst_delta:+.2f}%)")

    # Asset breakdown
    print("\n  Asset breakdown:")
    for asset in ["BTC/USDT", "AAPL", "NIFTY50"]:
        ar = [r for r in results if r["asset"] == asset]
        ap = sum(1 for r in ar if r["status"] == "PASSED")
        print(f"    {asset:<12}  {ap}/{len(ar)} passed")

    # Strategy breakdown
    print("\n  Strategy breakdown:")
    for strat in ["GRID", "DCA", "PLA"]:
        sr = [r for r in results if r["strategy"] == strat]
        sp = sum(1 for r in sr if r["status"] == "PASSED")
        print(f"    {strat:<8}  {sp}/{len(sr)} passed")

    print()
    if len(failed) > 0:
        print(f"[RESULT] VALIDATION INCOMPLETE — {len(failed)} test(s) failed.")
    else:
        print("[RESULT] ALL TESTS PASSED.")


if __name__ == "__main__":
    main()
