import { ValidationData, ValidationMetrics, WalkForwardWindow } from '../types';

const GREEN  = 'var(--tv-green)';
const RED    = 'var(--tv-red)';
const ORANGE = 'var(--tv-amber)';
const AMBER  = 'var(--tv-amber)';
const TEXT   = 'var(--tv-text)';
const GREY   = 'var(--tv-muted)';
const DIM    = 'var(--tv-dim)';

interface Props {
  validation: ValidationData;
  currency?:  string;
}

export default function ValidationPanel({ validation: v, currency = '$' }: Props) {
  const locale = currency === '₹' ? 'en-IN' : 'en-US';

  if (v.mode === 'holdout')      return <HoldoutView v={v} currency={currency} locale={locale} />;
  if (v.mode === 'walk_forward') return <WalkForwardView v={v} currency={currency} locale={locale} />;
  return null;
}

function HoldoutView({ v, currency, locale }: { v: ValidationData; currency: string; locale: string }) {
  const ins = v.in_sample;
  const oos = v.out_of_sample;
  if (!ins || !oos) return null;

  const oosTrades     = oos.num_trades ?? 0;
  const lowTradeCount = oosTrades < 5;
  const verdict       = lowTradeCount ? 'insufficient_data' : (v.verdict ?? 'stable');
  const verdictCfg = {
    stable:            { color: GREEN,  icon: '[OK]', msg: 'Out-of-sample results are consistent with in-sample. Strategy appears robust.' },
    degraded:          { color: ORANGE, icon: '[!]',  msg: 'Out-of-sample Sharpe dropped >50% vs in-sample. Results may reflect in-sample bias.' },
    failed:            { color: RED,    icon: '[X]',  msg: 'Strategy lost money out-of-sample. The in-sample return may not generalize.' },
    insufficient_data: { color: ORANGE, icon: '[!]',  msg: `Only ${oosTrades} OOS trade${oosTrades !== 1 ? 's' : ''} — extend the date range.` },
  }[verdict] ?? { color: DIM, icon: '', msg: '' };

  const fmtPct  = (n: number | undefined) => `${((n ?? 0) >= 0 ? '+' : '')}${(n ?? 0).toFixed(2)}%`;
  const fmtNum  = (n: number | undefined) => (n ?? 0).toFixed(2);
  const retCol  = (n: number | undefined) => ((n ?? 0) >= 0 ? GREEN : RED);
  const shrCol  = (n: number | undefined) => ((n ?? 0) >= 1 ? GREEN : (n ?? 0) >= 0 ? ORANGE : RED);
  const delta   = (a: number | undefined, b: number | undefined) => {
    const d = (b ?? 0) - (a ?? 0);
    return { val: d, str: `${d >= 0 ? '+' : ''}${d.toFixed(2)}`, col: d >= 0 ? GREEN : RED };
  };

  const rows = [
    { label: 'Total Return',   ins_str: fmtPct(ins.total_return_pct),      oos_str: fmtPct(oos.total_return_pct),      ins_col: retCol(ins.total_return_pct),      oos_col: retCol(oos.total_return_pct),      delta: delta(ins.total_return_pct, oos.total_return_pct) },
    { label: 'Ann. Return',    ins_str: fmtPct(ins.annualised_return_pct), oos_str: fmtPct(oos.annualised_return_pct), ins_col: retCol(ins.annualised_return_pct), oos_col: retCol(oos.annualised_return_pct), delta: delta(ins.annualised_return_pct, oos.annualised_return_pct) },
    { label: 'Sharpe Ratio',   ins_str: fmtNum(ins.sharpe_ratio),          oos_str: fmtNum(oos.sharpe_ratio),          ins_col: shrCol(ins.sharpe_ratio),          oos_col: lowTradeCount ? GREY : shrCol(oos.sharpe_ratio), delta: delta(ins.sharpe_ratio, oos.sharpe_ratio) },
    { label: 'Sortino Ratio',  ins_str: fmtNum(ins.sortino_ratio),         oos_str: fmtNum(oos.sortino_ratio),         ins_col: shrCol(ins.sortino_ratio),         oos_col: lowTradeCount ? GREY : shrCol(oos.sortino_ratio), delta: delta(ins.sortino_ratio, oos.sortino_ratio) },
    { label: 'Max Drawdown',   ins_str: `${(ins.max_drawdown_pct ?? 0).toFixed(2)}%`, oos_str: `${(oos.max_drawdown_pct ?? 0).toFixed(2)}%`, ins_col: (ins.max_drawdown_pct ?? 0) < -10 ? RED : ORANGE, oos_col: (oos.max_drawdown_pct ?? 0) < -10 ? RED : ORANGE, delta: delta(ins.max_drawdown_pct, oos.max_drawdown_pct) },
    { label: 'Win Rate',       ins_str: `${(ins.win_rate ?? 0).toFixed(1)}%`, oos_str: `${(oos.win_rate ?? 0).toFixed(1)}%`, ins_col: (ins.win_rate ?? 0) >= 50 ? GREEN : RED, oos_col: (oos.win_rate ?? 0) >= 50 ? GREEN : RED, delta: delta(ins.win_rate, oos.win_rate) },
    { label: 'Trades',         ins_str: String(ins.num_trades ?? 0),        oos_str: String(oos.num_trades ?? 0),        ins_col: TEXT, oos_col: TEXT, delta: delta(ins.num_trades, oos.num_trades) },
  ];

  return (
    <div className="space-y-4 fade-in">
      <div>
        <h3 className="text-sm font-bold tracking-wide mb-1" style={{ color: TEXT }}>Holdout Validation</h3>
        <p className="text-xs" style={{ color: GREY }}>
          Training on {((v.train_ratio ?? 0.7) * 100).toFixed(0)}% of data up to <strong style={{ color: TEXT }}>{v.split_date}</strong>,
          tested on the remaining {((1 - (v.train_ratio ?? 0.7)) * 100).toFixed(0)}% unseen data.
        </p>
      </div>

      <div className="px-4 py-3 rounded-xl flex items-start gap-3"
        style={{ background: `${verdictCfg.color}18`, border: `1px solid ${verdictCfg.color}55` }}>
        <span className="text-lg">{verdictCfg.icon}</span>
        <div>
          <p className="text-sm font-semibold" style={{ color: verdictCfg.color }}>
            {verdict.replace('_', ' ').replace(/^\w/, c => c.toUpperCase())}
          </p>
          <p className="text-xs mt-0.5" style={{ color: GREY }}>{verdictCfg.msg}</p>
        </div>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #23233A' }}>
        <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--tv-s1)' }}>
              <th className="text-left px-4 py-3 text-xs font-semibold" style={{ color: GREY, borderBottom: '1px solid #23233A', width: '28%' }}>Metric</th>
              <th className="text-center px-4 py-3 text-xs font-bold" style={{ color: GREEN, borderBottom: '1px solid #23233A' }}>
                In-Sample <div className="text-[10px] font-normal mt-0.5" style={{ color: DIM }}>{ins.num_candles} candles</div>
              </th>
              <th className="text-center px-4 py-3 text-xs font-bold" style={{ color: AMBER, borderBottom: '1px solid #23233A' }}>
                Out-of-Sample <div className="text-[10px] font-normal mt-0.5" style={{ color: DIM }}>{oos.num_candles} candles</div>
              </th>
              <th className="text-center px-4 py-3 text-xs font-bold" style={{ color: GREY, borderBottom: '1px solid #23233A' }}>Delta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.label}>
                <td className="px-4 py-2.5 text-xs font-medium" style={{ color: GREY }}>{row.label}</td>
                <td className="px-4 py-2.5 text-center text-sm font-bold" style={{ color: row.ins_col }}>{row.ins_str}</td>
                <td className="px-4 py-2.5 text-center text-sm font-bold" style={{ color: row.oos_col }}>{row.oos_str}</td>
                <td className="px-4 py-2.5 text-center text-xs font-semibold" style={{ color: row.delta.col }}>{row.delta.str}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function WalkForwardView({ v, currency, locale }: { v: ValidationData; currency: string; locale: string }) {
  const agg  = v.out_of_sample;
  const wins = v.windows ?? [];
  const fmtPct = (n: number | undefined) => `${((n ?? 0) >= 0 ? '+' : '')}${(n ?? 0).toFixed(2)}%`;
  const fmtNum = (n: number | undefined) => (n ?? 0).toFixed(2);
  const retCol = (n: number | undefined) => ((n ?? 0) >= 0 ? GREEN : RED);
  const shrCol = (n: number | undefined) => ((n ?? 0) >= 1 ? GREEN : (n ?? 0) >= 0 ? ORANGE : RED);
  const oosTrades = agg?.num_trades ?? 0;
  const lowTradeCount = oosTrades < 5;

  return (
    <div className="space-y-4 fade-in">
      <div>
        <h3 className="text-sm font-bold tracking-wide mb-1" style={{ color: TEXT }}>Walk-Forward Validation</h3>
        <p className="text-xs" style={{ color: GREY }}>
          {v.num_windows} windows — trained on {v.window} candles, tested on {v.step} unseen candles each.
        </p>
      </div>

      {agg && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'OOS Total Return', val: fmtPct(agg.total_return_pct), col: retCol(agg.total_return_pct) },
            { label: 'OOS Sharpe',       val: fmtNum(agg.sharpe_ratio),     col: lowTradeCount ? GREY : shrCol(agg.sharpe_ratio) },
            { label: 'OOS Max DD',       val: `${(agg.max_drawdown_pct ?? 0).toFixed(2)}%`, col: (agg.max_drawdown_pct ?? 0) < -10 ? RED : ORANGE },
            { label: 'OOS Trades',       val: String(oosTrades),            col: lowTradeCount ? RED : TEXT },
          ].map(m => (
            <div key={m.label} className="rounded-xl p-3" style={{ background: 'var(--tv-bg)', border: '1px solid #23233A' }}>
              <span className="text-xs font-medium" style={{ color: GREY }}>{m.label}</span>
              <div className="text-base font-bold" style={{ color: m.col }}>{m.val}</div>
            </div>
          ))}
        </div>
      )}

      {wins.length > 0 && (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #23233A' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={{ borderCollapse: 'collapse', minWidth: '600px' }}>
              <thead>
                <tr style={{ background: 'var(--tv-s1)' }}>
                  {['#', 'Train Period', 'Test Period', 'Best Params', 'Train Sharpe', 'OOS Return', 'OOS Sharpe', 'Max DD', 'Trades'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold" style={{ color: GREY, borderBottom: '1px solid #23233A' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {wins.map((w: WalkForwardWindow, i: number) => (
                  <tr key={i}>
                    <td className="px-3 py-2" style={{ color: DIM }}>{w.window_num}</td>
                    <td className="px-3 py-2" style={{ color: DIM }}>{w.train_period}</td>
                    <td className="px-3 py-2" style={{ color: TEXT }}>{w.test_period}</td>
                    <td className="px-3 py-2 font-mono" style={{ color: DIM, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.best_params}</td>
                    <td className="px-3 py-2 text-right" style={{ color: shrCol(w.train_sharpe) }}>{(w.train_sharpe ?? 0).toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-bold" style={{ color: retCol(w.return_pct) }}>{fmtPct(w.return_pct)}</td>
                    <td className="px-3 py-2 text-right" style={{ color: shrCol(w.sharpe) }}>{(w.sharpe ?? 0).toFixed(2)}</td>
                    <td className="px-3 py-2 text-right" style={{ color: (w.max_dd_pct ?? 0) < -10 ? RED : ORANGE }}>{(w.max_dd_pct ?? 0).toFixed(2)}%</td>
                    <td className="px-3 py-2 text-right" style={{ color: TEXT }}>{w.num_trades ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
