import { useState } from 'react';
import { Trade } from '../types';

const GREEN = 'var(--tv-green)';
const RED   = 'var(--tv-red)';
const GREY  = 'var(--tv-muted)';
const TEXT  = 'var(--tv-text)';
const DIM   = 'var(--tv-dim)';
const CARD  = 'var(--tv-s1)';
const BORDER = 'var(--tv-border)';

export default function TradeLog({ trades, currency = '$' }: { trades: Trade[]; currency?: string }) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'entry_time', dir: 'asc' });
  const locale = currency === '₹' ? 'en-IN' : 'en-US';
  const fmtPrice = (n: number) => `${currency}${n.toLocaleString(locale, { maximumFractionDigits: 2 })}`;
  if (!trades.length) return (
    <div className="flex items-center justify-center h-40 rounded-xl" style={{ background: CARD, border: `1px solid ${BORDER}` }}>
      <p style={{ color: GREY }}>No completed trades in this backtest.</p>
    </div>
  );
  const rows = trades.map((t, i) => {
    let durH = 0;
    try { if (t.entry_time && t.exit_time) durH = (new Date(t.exit_time).getTime() - new Date(t.entry_time).getTime()) / 3_600_000; } catch {}
    return { ...t, _i: i + 1, duration: durH };
  });
  const sorted = [...rows].sort((a, b) => {
    const av = (a as any)[sort.key]; const bv = (b as any)[sort.key];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sort.dir === 'asc' ? cmp : -cmp;
  });
  const toggleSort = (key: string) => setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }));
  const winners = trades.filter(t => t.pnl > 0).length;
  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);
  return (
    <div className="fade-in">
      <div className="flex flex-wrap gap-4 mb-3 px-1 pb-3" style={{ borderBottom: `1px solid ${BORDER}` }}>
        {[['Total', trades.length.toString(), ''], ['Winners', winners.toString(), GREEN], ['Losers', (trades.length - winners).toString(), RED], ['Win Rate', `${(winners / trades.length * 100).toFixed(1)}%`, winners / trades.length >= 0.5 ? GREEN : RED], ['Gross P&L', `${totalPnl >= 0 ? '+' : ''}${fmtPrice(Math.abs(totalPnl))}`, totalPnl >= 0 ? GREEN : RED]].map(([l, v, c]) => (
          <div key={l} className="flex gap-1.5 items-baseline">
            <span className="text-xs" style={{ color: GREY }}>{l}:</span>
            <span className="text-sm font-bold" style={{ color: c || TEXT }}>{v}</span>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl" style={{ border: `1px solid ${BORDER}` }}>
        <table className="w-full text-xs" style={{ background: CARD }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
              {[['_i','#'],['entry_time','Entry'],['entry_price','Entry Price'],['exit_time','Exit'],['exit_price','Exit Price'],['quantity','Qty'],['pnl','P&L'],['pnl_pct','P&L %'],['fees','Fees'],['duration','Duration']].map(([k, l]) => (
                <th key={k} onClick={() => toggleSort(k)} className="px-3 py-2.5 text-left font-semibold cursor-pointer select-none whitespace-nowrap" style={{ color: sort.key === k ? GREEN : GREY }}>
                  {l}{sort.key === k && <span className="ml-1">{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((t, i) => {
              const pnlColor = t.pnl > 0 ? GREEN : t.pnl < 0 ? RED : GREY;
              const dur = t.duration < 48 ? `${t.duration.toFixed(1)}h` : `${(t.duration/24).toFixed(1)}d`;
              return (
                <tr key={i} style={{ borderBottom: `1px solid ${BORDER}` }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--tv-s3)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <td className="px-3 py-2" style={{ color: DIM }}>{t._i}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: TEXT }}>{t.entry_time?.replace('T',' ').slice(0,16)}</td>
                  <td className="px-3 py-2" style={{ color: TEXT }}>{fmtPrice(t.entry_price)}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: TEXT }}>{t.exit_time ? t.exit_time.replace('T',' ').slice(0,16) : '—'}</td>
                  <td className="px-3 py-2" style={{ color: TEXT }}>{t.exit_price ? fmtPrice(t.exit_price) : '—'}</td>
                  <td className="px-3 py-2" style={{ color: TEXT }}>{t.quantity.toFixed(6)}</td>
                  <td className="px-3 py-2 font-bold" style={{ color: pnlColor }}>{t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(4)}</td>
                  <td className="px-3 py-2 font-bold" style={{ color: pnlColor }}>{(t.pnl_pct * 100) >= 0 ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%</td>
                  <td className="px-3 py-2" style={{ color: DIM }}>{t.fees.toFixed(4)}</td>
                  <td className="px-3 py-2" style={{ color: DIM }}>{t.duration > 0 ? dur : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
