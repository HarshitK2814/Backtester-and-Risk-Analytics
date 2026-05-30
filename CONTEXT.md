# TradeVed Backtester — CONTEXT.md

Living progress document. Last updated: 2026-05-30 (session 4)

---

## Current Status

**Two pages fully working:**
1. **Backtest page** — full-featured (stable)
2. **Stress Test page** — SSE live loading, canvas MC chart, all 13 scenarios

Backend on `:8000` with `reload=False`. Frontend on `:5173`.

---

## Session 4 Fixes (2026-05-30)

- Stress GRID 0 trades — auto-bounds added to both stress endpoints
- SSE "Failed to fetch" — `timeout: 0, proxyTimeout: 0` in vite.config.ts
- `UnboundLocalError: n_runs` — moved assignment to top of `_generate()`
- MC counter "0/0" — pre-populate `total: form.mcRuns`; backend sends `"total"` in baseline
- `mcRuns: 1` default — changed to 100; MC pills: [50, 100, 250, 500]
- Source switch capital mismatch — `handleSourceChange` auto-Smart-Fills for new source

## Cleanup (session 4)
- Deleted reports/ (145 HTML), ppt_assets/ (27 files), app.py (old Streamlit)
- Deleted personal intern docs
- Rewrote README.md to cover full platform

## Audit (session 4): 45/48 API tests PASS
- DCA/GRID/PLA x BTC/NIFTY50/BANKNIFTY/SPY/RELIANCE x all 13 stress scenarios
- 3 non-failures: NIFTY50 Futures lot-size 422 (correct), walk-forward key name (correct), cost preview field name (correct)

---

## Features

### A — Timeframe-Aware Regime Detection (DONE)
- engine/regimes.py — MA windows sized in real trading days

### B — Stress Tester (DONE)
- 13 scenarios, SSE streaming, canvas MC chart
- Per-run severity: `severity x uniform(0.75, 1.25)`
- persist=True for crash scenarios
- mcRuns default: 100

### C — Walk-Forward Validation (DONE)
- engine/validation.py — run_holdout(), run_walk_forward()
- Returns `validation` key with per-window train/test metrics

---

## Test Suite

| Suite | Tests | Status |
|-------|-------|--------|
| pytest test_all.py | 37 | All pass |
| stress_validation.py | 207 | All pass |

---

## Known Backlog

| Priority | Item |
|----------|------|
| Medium | Pin shock to specific date |
| Low | Stress + walk-forward combined |
| Low | Volume-based regime detection |
| Low | Options greeks / non-linear payoff |
