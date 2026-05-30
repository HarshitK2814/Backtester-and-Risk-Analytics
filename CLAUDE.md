# TradeVed Backtester — CLAUDE.md

Auto-loaded by Claude Code every session. Keep it accurate; update when architecture changes.

---

## Project Overview

**TradeVed Backtester** — a full-stack quantitative backtesting platform for crypto, US stocks, and Indian markets (NSE/BSE). Includes a full **Stress Tester** with 13 scenario presets, SSE-streamed Monte Carlo simulation, canvas-based live spaghetti chart, and delta-view toggle.

- **Backend:** FastAPI + SQLite + Python 3.11+
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS
- **Working directory:** `backtester/` (all `python` commands run from here)

---

## How to Run

```powershell
# Kill old backend process if port 8000 is in use
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force

# Terminal 1 — Backend (FastAPI on :8000)
cd "C:\Users\Harshit Kumar\Downloads\TradeVed Backtester\backtester"
python main.py

# Terminal 2 — Frontend (Vite on :5173)
cd "C:\Users\Harshit Kumar\Downloads\TradeVed Backtester\backtester\frontend"
npm run dev -- --port 5173
```

API docs: http://localhost:8000/docs
UI: http://localhost:5173

---

## Key Architecture Decisions

### Cost Models
- **SimpleCostModel:** flat % fee per leg (crypto / US stocks)
- **IndianCostModel:** itemised STT + NSE exchange charges + SEBI + GST (Budget 2024 rates)
- `track=False` for provisional estimates, `track=True` for final recorded calls — prevents double-counting

### Simulator
- **WACB** (Weighted-Average Cost Basis): `new_avg = (old_qty*old_avg + new_qty*price) / total_qty`
- **Lot-size enforcement:** `math.floor(qty / lot_size) * lot_size` — only when `lot_size > 1`
- **Partial fills:** if cash < required, back-solve for affordable qty

### Indian Market
- Auto-detection: `req.source in ("nse","bse") or is_indian(req.symbol)` => `use_indian_costs=True`
- Lot sizes from `data/indian_assets.py:FO_LOT_SIZES` — applied only for `market_type in ("futures","options")`
- 422 raised when lot_sz > 1, 0 trades, and BUY signals existed (with guidance message)

### Strategies
**GRID** — buys at price levels; leave bounds at 0 for auto-detection (+-10% pad from price history).
**DCA** — buys at fixed time intervals.
**PLA** — EMA crossover entry + cascading average-down. Use Daily candles, not Weekly.

### Metrics
- `win_rate` returned as **0-100 range**. Do not multiply by 100.
- Annualisation: `TRADING_DAYS_PER_YEAR = 252`

### Stress Tester
- 13 scenario presets in `SCENARIO_PRESETS`
- Per-run severity jitter: `severity x uniform(0.75, 1.25)` — both timing AND magnitude vary
- `persist=True` for permanent crash scenarios — no snap-back
- SSE endpoint: `POST /api/stress/stream` — async generator, `asyncio.to_thread` for blocking calls
- GRID auto-bounds applied in ALL three endpoints (backtest/run, stress/run, stress/stream)

---

## Common Bugs / Gotchas

| Issue | Root cause | Fix applied |
|-------|-----------|-------------|
| GRID 0 trades in stress | Auto-bounds missing from stress endpoints | Added to both /api/stress/run and /api/stress/stream |
| SSE "Failed to fetch" | Vite proxy ~60s timeout killed SSE | `timeout: 0, proxyTimeout: 0` in vite.config.ts |
| `UnboundLocalError: n_runs` | Variable assigned after first use in generator | Moved n_runs to top of _generate() |
| Stress shows nothing for non-BTC | mcRuns default was 1; source switch didn't reset capital | mcRuns default = 100; source switch auto-Smart-Fills |
| All MC paths identical | Fixed severity per run | Per-run `severity x uniform(0.75, 1.25)` |
| Stress crashes profitable | _apply_drift snapped back after shock | persist=True parameter |
| $ everywhere on Indian backtests | Hardcoded $ throughout frontend | currency variable + en-IN locale |
| Port 8000 in use | Old process running | Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force |

---

## Do NOT

- Do not set `reload=True` in `uvicorn.run()` — log written every request causes watchfiles deadlock
- Do not hardcode `$` in frontend — always use `currency` variable
- Do not call `_calculate_cost(..., track=True)` twice for the same trade leg
- Do not use `en-US` locale for Indian amounts — use `en-IN`
- Do not multiply `win_rate` by 100 in frontend — already 0-100
- Do not fix per-run severity to constant — `uniform(0.75, 1.25)` jitter is intentional
- Do not call `_apply_drift` with `persist=False` for crash scenarios
- Do not add new stress scenarios without updating StressSidebar.tsx + types.ts
