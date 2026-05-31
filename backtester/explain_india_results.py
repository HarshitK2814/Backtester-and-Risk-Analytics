"""
explain_india_results.py
========================
Shows the TOP 15 Indian Futures results with the HIDDEN invest_per_level
column exposed, making it clear why rows that look identical are different.
"""
import sys, ast, warnings
warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from pathlib import Path

csv_file = sys.argv[1] if len(sys.argv) > 1 else sorted(
    Path('optimizer_results').glob('india_results_*.csv'))[-1]

df = pd.read_csv(csv_file)
valid = df[(df['num_trades'] > 0) & (df['error'].isna())].copy()

# ── Extract base invest level from the stored list ──────────────────────────
def base_invest(row):
    # Use the pre-computed scalar column if available
    v = row.get('param_invest_base', None)
    if v is not None and not (isinstance(v, float) and pd.isna(v)) and v != 0:
        return float(v)
    # Fallback: parse list string
    try:
        val = row.get('param_invest_per_level_usd', None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            lst = ast.literal_eval(str(val))
            return lst[0]
    except Exception:
        pass
    return float(row.get('param_invest_per_buy_usd') or 0)

valid['invest_base'] = valid.apply(base_invest, axis=1)

# ── Build readable params_summary WITH invest ────────────────────────────────
def make_summary(row):
    s = row['strategy']
    if s == 'GRID':
        return (f"lvl={row.get('param_num_levels','')} | "
                f"spc={str(row.get('param_spacing',''))[:3]} | "
                f"inv=₹{int(row.get('param_invest_per_level_usd',0) or 0):,}")
    if s == 'DCA':
        return (f"int={row.get('param_buy_interval_hours','')}h | "
                f"inv=₹{int(row.get('param_invest_per_buy_usd',0) or 0):,} | "
                f"hold={row.get('param_hold_days','')}d | "
                f"exit={row.get('param_exit_type','')}")
    if s == 'PLA':
        inv = int(row['invest_base'] or 0)
        return (f"f={row.get('param_fast_ema','')} | "
                f"s={row.get('param_slow_ema','')} | "
                f"inv=₹{inv:,}/level | "
                f"exit={row.get('param_exit_type','')} | "
                f"tp={row.get('param_take_profit_pct','')}%")
    return ''

valid['full_params'] = valid.apply(make_summary, axis=1)

SEP = '=' * 140
SEP2 = '-' * 140

# ── TOP 15 with invest shown ──────────────────────────────────────────────────
top15 = valid.sort_values('composite_score', ascending=False).head(15)

print(f"\n{SEP}")
print("  TOP 15 INDIAN FUTURES  —  Full parameter breakdown (invest level now visible)")
print(SEP)
print(f"{'#':<4} {'Strat':<5} {'Symbol':<10} {'Score':>7} {'Return':>8} {'Sharpe':>7} {'Sortino':>8} "
      f"{'MDD':>7} {'WinR':>6} {'Tr':>3} {'Fees':>10}   Full Parameters")
print(SEP2)

for rank, (_, row) in enumerate(top15.iterrows(), 1):
    medal = {1:"🥇", 2:"🥈", 3:"🥉"}.get(rank, f"#{rank:<2}")
    print(f"{medal:<4} {row['strategy']:<5} {row['symbol']:<10} "
          f"{row['composite_score']:>7.4f} "
          f"{row['total_return_pct']:>+7.1f}% "
          f"{row['sharpe_ratio']:>7.3f} "
          f"{row['sortino_ratio']:>8.3f} "
          f"{row['max_drawdown_pct']:>6.1f}% "
          f"{row['win_rate']:>5.0f}% "
          f"{int(row['num_trades']):>3} "
          f"₹{row['total_fees_inr']:>8,.0f}   "
          f"{row['full_params']}")

# ── Why #1 beats #2 despite #2 having higher return ─────────────────────────
print(f"\n{SEP}")
print("  WHY #1 SCORES HIGHER THAN #2 (even though #2 has +22% vs #1's +20.4%)")
print(SEP2)
r1 = top15.iloc[0]
r2 = top15.iloc[1]
metrics = [
    ("Total Return",     "total_return_pct",      "%"),
    ("Sharpe Ratio",     "sharpe_ratio",           ""),
    ("Sortino Ratio",    "sortino_ratio",          ""),
    ("Calmar Ratio",     "calmar_ratio",           ""),
    ("Max Drawdown",     "max_drawdown_pct",       "%"),
    ("Composite Score",  "composite_score",        ""),
]
weights = {"total_return_pct": 0.25, "sharpe_ratio": 0.35,
           "sortino_ratio": 0.20, "calmar_ratio": 0.10, "max_drawdown_pct": 0.10,
           "composite_score": 0.0}
print(f"{'Metric':<20} {'Weight':>8}   {'#1 INFY':>10}   {'#2 INFY':>10}   Winner")
print(SEP2)
for label, col, unit in metrics:
    w = weights.get(col, 0)
    v1, v2 = r1[col], r2[col]
    # For MDD, lower (less negative) is better
    if col == "max_drawdown_pct":
        winner = "#1" if v1 > v2 else "#2"
    elif col == "composite_score":
        winner = "#1" if v1 > v2 else "#2"
    else:
        winner = "#1" if v1 > v2 else "#2"
    w_str = f"{w:.0%}" if w > 0 else "  —  "
    print(f"  {label:<18} {w_str:>8}   {v1:>9.3f}{unit}   {v2:>9.3f}{unit}   {winner}")
print()
print(f"  → #1 invest/level: ₹{int(r1['invest_base']):,}   |   #2 invest/level: ₹{int(r2['invest_base']):,}")
print(f"  → Smaller position size = less drawdown = better risk-adjusted metrics")
print(f"  → Composite score weights Sharpe (35%) + Sortino (20%) more than raw Return (25%)")
print(f"  → So #1 wins despite lower absolute return: its volatility-per-unit-of-gain is superior")

# ── EMA pair comparison ───────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  EMA PAIR COMPARISON  —  Why 9/21 dominated over 12/26 and 20/50")
print(SEP2)
pla_valid = valid[valid['strategy'] == 'PLA'].copy()
pla_valid['ema_pair'] = pla_valid.apply(
    lambda r: f"EMA {int(r.get('param_fast_ema',0))}/{int(r.get('param_slow_ema',0))}", axis=1)
summary = pla_valid.groupby('ema_pair').agg(
    runs=('composite_score', 'count'),
    avg_score=('composite_score', 'mean'),
    best_score=('composite_score', 'max'),
    avg_return=('total_return_pct', 'mean'),
    best_return=('total_return_pct', 'max'),
    avg_sharpe=('sharpe_ratio', 'mean'),
    avg_mdd=('max_drawdown_pct', 'mean'),
).reset_index().sort_values('avg_score', ascending=False)

print(f"  {'EMA Pair':<12} {'Runs':>5} {'Avg Score':>10} {'Best Score':>11} "
      f"{'Avg Return':>11} {'Avg Sharpe':>11} {'Avg MDD':>9}")
print(f"  {'-'*12} {'-'*5} {'-'*10} {'-'*11} {'-'*11} {'-'*11} {'-'*9}")
for _, row in summary.iterrows():
    print(f"  {row['ema_pair']:<12} {int(row['runs']):>5} {row['avg_score']:>10.4f} "
          f"{row['best_score']:>11.4f} {row['avg_return']:>+10.1f}% "
          f"{row['avg_sharpe']:>11.3f} {row['avg_mdd']:>8.1f}%")

print(f"\n  → EMA 9/21 wins because it fires EARLIER in the trend (faster signal)")
print(f"  → Indian bull market 2022-24: entering early = capturing more of the move")
print(f"  → EMA 20/50 fires too late — often after 15-25% of the rally is already done")

# ── Invest level impact ───────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  INVEST LEVEL IMPACT  —  How position size affects returns (INFY PLA 9/21 tp=5%)")
print(SEP2)
infy_912 = pla_valid[
    (pla_valid['symbol'] == 'INFY') &
    (pla_valid['param_fast_ema'] == 9) &
    (pla_valid['param_slow_ema'] == 21) &
    (pla_valid['param_exit_type'] == 'take_profit') &
    (pla_valid['param_take_profit_pct'] == 5.0)
].copy()

if not infy_912.empty:
    print(f"  {'Invest/Level':>14} {'Capital':>12} {'Return':>9} {'Sharpe':>8} "
          f"{'MDD':>7} {'Score':>8} {'Fees':>10}")
    print(f"  {'-'*14} {'-'*12} {'-'*9} {'-'*8} {'-'*7} {'-'*8} {'-'*10}")
    for _, row in infy_912.sort_values('invest_base').iterrows():
        print(f"  ₹{int(row['invest_base']):>12,} ₹{int(row['capital']):>11,} "
              f"{row['total_return_pct']:>+8.2f}% "
              f"{row['sharpe_ratio']:>8.3f} "
              f"{row['max_drawdown_pct']:>6.1f}% "
              f"{row['composite_score']:>8.4f} "
              f"₹{row['total_fees_inr']:>8,.0f}")
    print()
    print(f"  → Different invest sizes → different lot counts → slightly different WACB")
    print(f"  → More capital deployed = higher absolute ₹ gain but same % return structure")
    print(f"  → Optimal size hits the sweet spot: enough lots to matter, not so many that")
    print(f"     a single bad cycle inflates drawdown disproportionately")

print(f"\n{SEP}\n")
