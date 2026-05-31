import pandas as pd, warnings, sys
warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

csv_file = sys.argv[1] if len(sys.argv) > 1 else sorted(
    __import__('pathlib').Path('optimizer_results').glob('results_*.csv'))[-1]

df = pd.read_csv(csv_file)
valid = df[(df['num_trades'] > 0) & (df['error'].isna())]

cols = ['symbol','strategy','composite_score','total_return_pct',
        'annualised_return_pct','sharpe_ratio','sortino_ratio',
        'calmar_ratio','max_drawdown_pct','win_rate','profit_factor',
        'num_trades','params_summary']

W = 120
SEP = '=' * W

print(SEP)
print(f"  DATASET   Total: {len(df)}  |  Valid: {len(valid)}  |  Zero-trade: {(df['num_trades']==0).sum()}  |  Errors: {df['error'].notna().sum()}")
print(SEP)

# ── TOP 10 OVERALL ─────────────────────────────────────────────────────────────
print("\n TOP 10 OVERALL (composite score)")
print('-' * W)
top10 = valid.sort_values('composite_score', ascending=False).head(10)[cols]
print(top10.to_string(index=False, float_format=lambda x: f'{x:9.3f}'))

# ── PER STRATEGY ──────────────────────────────────────────────────────────────
for strat in ['GRID', 'DCA', 'PLA']:
    sub  = valid[valid['strategy'] == strat]
    best = sub.sort_values('composite_score', ascending=False).head(5)[cols]
    print(f"\n TOP 5  {strat}")
    print('-' * W)
    print(best.to_string(index=False, float_format=lambda x: f'{x:9.3f}'))

# ── PER SYMBOL ────────────────────────────────────────────────────────────────
for sym in ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']:
    sub  = valid[valid['symbol'] == sym]
    best = sub.sort_values('composite_score', ascending=False).head(3)[cols]
    print(f"\n TOP 3  {sym}")
    print('-' * W)
    print(best.to_string(index=False, float_format=lambda x: f'{x:9.3f}'))

# ── STRATEGY MEDIAN SUMMARY ───────────────────────────────────────────────────
print(f"\n STRATEGY SUMMARY (medians over all valid runs per strategy)")
print('-' * W)
summary = valid.groupby('strategy').agg(
    valid_runs=('composite_score', 'count'),
    med_return=('total_return_pct', 'median'),
    med_sharpe=('sharpe_ratio', 'median'),
    med_sortino=('sortino_ratio', 'median'),
    med_mdd=('max_drawdown_pct', 'median'),
    med_winrate=('win_rate', 'median'),
    best_return=('total_return_pct', 'max'),
    best_sharpe=('sharpe_ratio', 'max'),
).reset_index()
print(summary.to_string(index=False, float_format=lambda x: f'{x:9.2f}'))

# ── SYMBOL SUMMARY ────────────────────────────────────────────────────────────
print(f"\n SYMBOL SUMMARY (best score, return, sharpe across all strategies)")
print('-' * W)
sym_sum = valid.groupby('symbol').agg(
    valid_runs=('composite_score', 'count'),
    best_score=('composite_score', 'max'),
    best_return=('total_return_pct', 'max'),
    best_sharpe=('sharpe_ratio', 'max'),
    med_return=('total_return_pct', 'median'),
    med_mdd=('max_drawdown_pct', 'median'),
).reset_index()
print(sym_sum.to_string(index=False, float_format=lambda x: f'{x:9.2f}'))

print(f"\n{SEP}")
print("  VERDICT")
print(SEP)
best_row = valid.sort_values('composite_score', ascending=False).iloc[0]
print(f"  #1 Overall  : {best_row['symbol']} | {best_row['strategy']} | {best_row['params_summary']}")
print(f"                Score={best_row['composite_score']:.4f}  Return={best_row['total_return_pct']:.2f}%  Sharpe={best_row['sharpe_ratio']:.3f}  Sortino={best_row['sortino_ratio']:.3f}  MDD={best_row['max_drawdown_pct']:.2f}%")

for strat in ['GRID','DCA','PLA']:
    r = valid[valid['strategy']==strat].sort_values('composite_score',ascending=False).iloc[0]
    print(f"  Best {strat:<5}   : {r['symbol']} | {r['params_summary']}")
    print(f"                Score={r['composite_score']:.4f}  Return={r['total_return_pct']:.2f}%  Sharpe={r['sharpe_ratio']:.3f}  Sortino={r['sortino_ratio']:.3f}  MDD={r['max_drawdown_pct']:.2f}%  Trades={r['num_trades']}")
print(SEP)
