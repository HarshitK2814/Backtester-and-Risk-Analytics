import React, { useMemo, useState } from 'react';
import {
  AreaChart, Area,
  LineChart, Line,
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  Brush, ReferenceLine,
} from 'recharts';
import { StressResponse } from '../types';
import MCPathsCanvas, { MCRun } from './MCPathsCanvas';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number | undefined, decimals = 2): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toFixed(decimals);
}
function sign(n: number, d = 2): string {
  return n >= 0 ? `+${n.toFixed(d)}` : n.toFixed(d);
}
function deltaColor(delta: number, invertBad = false): string {
  const bad = invertBad ? delta > 0 : delta < 0;
  return bad ? 'text-red-500' : 'text-green-600';
}
function makeBuckets(values: number[], bucketSize = 5) {
  if (!values.length) return [];
  const mn = Math.floor(Math.min(...values) / bucketSize) * bucketSize;
  const mx = Math.ceil(Math.max(...values)  / bucketSize) * bucketSize;
  const buckets: Record<number, number> = {};
  for (let b = mn; b <= mx; b += bucketSize) buckets[b] = 0;
  values.forEach(v => { const b = Math.floor(v / bucketSize) * bucketSize; buckets[b] = (buckets[b] ?? 0) + 1; });
  return Object.entries(buckets).map(([range, count]) => ({ range: `${range}%`, count: count as number }));
}

// ─── Shared UI pieces ─────────────────────────────────────────────────────────

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-2xl border border-gray-100 tv-soft-shadow p-4 ${className}`}>
      {children}
    </div>
  );
}
function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-3">
      <h4 className="text-sm font-bold text-[var(--tv-text)]">{children}</h4>
      {sub && <p className="text-xs text-[var(--tv-muted)] mt-0.5">{sub}</p>}
    </div>
  );
}

const TT_STYLE = { backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: 11, padding: '6px 10px' };

// ─── Compare card ─────────────────────────────────────────────────────────────

function CompareCard({ label, baseline, stressed, unit = '%', invertBad = false, decimals = 2 }: {
  label: string; baseline: number; stressed: number; unit?: string;
  invertBad?: boolean; decimals?: number;
}) {
  const delta   = stressed - baseline;
  const fmtV    = (v: number) => v.toFixed(decimals);
  const fmtD    = (v: number) => (v >= 0 ? `+${v.toFixed(decimals)}` : v.toFixed(decimals));
  return (
    <div className="bg-white rounded-2xl border border-gray-100 tv-soft-shadow p-3 hover:shadow-md transition-shadow">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--tv-muted)] mb-2">{label}</p>
      <div className="flex items-end gap-2 flex-wrap">
        <div>
          <p className="text-[10px] text-[var(--tv-muted)] mb-0.5">Baseline</p>
          <p className="text-lg font-bold text-[var(--tv-text)]">{fmtV(baseline)}{unit}</p>
        </div>
        <div className="text-gray-300 pb-0.5 text-lg">→</div>
        <div>
          <p className="text-[10px] text-[var(--tv-muted)] mb-0.5">Stressed</p>
          <p className="text-lg font-bold text-orange-500">{fmtV(stressed)}{unit}</p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-[10px] text-[var(--tv-muted)] mb-0.5">Δ</p>
          <p className={`text-sm font-bold ${deltaColor(delta, invertBad)}`}>{fmtD(delta)}{unit}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Stat chip ────────────────────────────────────────────────────────────────

function StatChip({ label, value, color = '' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center px-3 py-2 bg-gray-50 rounded-xl border border-gray-100 min-w-[80px]">
      <span className="text-[10px] text-[var(--tv-muted)]">{label}</span>
      <span className={`text-sm font-bold ${color || 'text-[var(--tv-text)]'}`}>{value}</span>
    </div>
  );
}

// ─── Verdict banner ───────────────────────────────────────────────────────────

function VerdictBanner({ baseRet, stressRet, baseDD, stressDD }: {
  baseRet: number; stressRet: number; baseDD: number; stressDD: number;
}) {
  const delta   = stressRet - baseRet;
  const ddDelta = stressDD  - baseDD;
  let verdict: 'survived' | 'degraded' | 'failed';
  if (delta > -10 && ddDelta > -10) verdict = 'survived';
  else if (delta > -30)              verdict = 'degraded';
  else                               verdict = 'failed';

  const cfg = {
    survived: { bg: 'bg-green-50 border-green-200',   icon: '✅', text: 'text-green-700',  label: 'Strategy Survived',       sub: 'Performance held up — returns and drawdown stayed within acceptable bounds.' },
    degraded:  { bg: 'bg-yellow-50 border-yellow-200', icon: '⚠️', text: 'text-yellow-700', label: 'Performance Degraded',     sub: 'Significant impact detected. Strategy is fragile but recoverable.' },
    failed:    { bg: 'bg-red-50 border-red-200',       icon: '❌', text: 'text-red-700',    label: 'Strategy Failed',          sub: 'Severe losses under this scenario. High risk of capital destruction.' },
  }[verdict];

  return (
    <div className={`flex items-start gap-3 p-4 rounded-2xl border ${cfg.bg}`}>
      <span className="text-2xl mt-0.5">{cfg.icon}</span>
      <div className="flex-1">
        <p className={`font-bold text-sm ${cfg.text}`}>{cfg.label}</p>
        <p className="text-xs text-[var(--tv-muted)] mt-0.5">{cfg.sub}</p>
        <p className={`text-xs mt-1.5 font-medium ${cfg.text}`}>
          Return Δ {sign(delta)}% &nbsp;·&nbsp; Drawdown Δ {sign(ddDelta)}% &nbsp;·&nbsp; {fmt(baseRet)}% → {fmt(stressRet)}%
        </p>
      </div>
    </div>
  );
}

// ─── MC Interpretation panel ──────────────────────────────────────────────────

function MCInterpretation({ runs, p5, p50, p95, worst, best }: {
  runs: number; p5: number; p50: number; p95: number; worst: number; best?: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between text-sm font-semibold text-blue-700">
        <span>🔍 How to interpret Monte Carlo results ({runs} simulations)</span>
        <span className="text-lg">{open ? '−' : '+'}</span>
      </button>

      {/* Always-visible summary */}
      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div className="bg-white rounded-xl p-2 border border-blue-100">
          <p className="text-[10px] text-red-500 font-semibold uppercase mb-1">P5 — Tail Risk</p>
          <p className="text-base font-bold text-red-500">{sign(p5)}%</p>
          <p className="text-[10px] text-[var(--tv-muted)] mt-1">In 5% of runs, returns were this bad or worse. This is your stress-tail.</p>
        </div>
        <div className="bg-white rounded-xl p-2 border border-blue-100">
          <p className="text-[10px] text-orange-500 font-semibold uppercase mb-1">P50 — Typical</p>
          <p className="text-base font-bold text-[var(--tv-text)]">{sign(p50)}%</p>
          <p className="text-[10px] text-[var(--tv-muted)] mt-1">Median outcome — half of runs were better, half worse.</p>
        </div>
        <div className="bg-white rounded-xl p-2 border border-blue-100">
          <p className="text-[10px] text-green-600 font-semibold uppercase mb-1">P95 — Best Case</p>
          <p className="text-base font-bold text-green-600">{sign(p95)}%</p>
          <p className="text-[10px] text-[var(--tv-muted)] mt-1">Top 5% of runs. Don't count on this.</p>
        </div>
        <div className="bg-white rounded-xl p-2 border border-blue-100">
          <p className="text-[10px] text-red-700 font-semibold uppercase mb-1">WORST RUN</p>
          <p className="text-base font-bold text-red-700">{sign(worst)}%</p>
          <p className="text-[10px] text-[var(--tv-muted)] mt-1">Absolute worst of all {runs} simulations.</p>
        </div>
      </div>

      {open && (
        <div className="mt-3 space-y-2 text-xs text-blue-800 border-t border-blue-200 pt-3">
          <p><strong>What is Monte Carlo?</strong> Each run applies the same stress scenario but with a different random seed — the shock starts at a random point in the data (within the first 60%) and stochastic elements (outlier positions, gap timing) vary. This simulates the uncertainty of <em>when</em> the shock hits relative to your strategy's position cycle.</p>
          <p><strong>Reading the spaghetti chart:</strong> Each line is one simulated equity path. Thin lines are all runs — green if profitable, red if loss. The thick orange line is the P50 (median representative run). The thick dashed blue line is your baseline (no stress).</p>
          <p><strong>The range matters more than the median:</strong> A tight cluster of lines means the scenario has predictable impact. A wide spread means timing matters a lot — bad luck can dramatically worsen outcomes.</p>
          <p><strong>Click any row</strong> in the Run Log below the chart to highlight that simulation path and see its exact metrics.</p>
        </div>
      )}
    </div>
  );
}

// ─── Static MC Paths view (post-completion) ───────────────────────────────────

function MCPathsCard({
  spaghetti, baselineEquity, timestamps, currency, locale, capital,
}: {
  spaghetti:      { ts_indices: number[]; runs: { run_idx: number; return_pct: number; max_dd_pct: number; sharpe: number; win_rate: number; equity: number[] }[] };
  baselineEquity: number[];
  timestamps:     string[];
  currency:       string;
  locale:         string;
  capital:        number;
}) {
  const [sortField, setSortField]           = useState<'return_pct' | 'max_dd_pct' | 'sharpe'>('return_pct');
  const [sortDir,   setSortDir]             = useState<'desc' | 'asc'>('desc');
  const [filterPos, setFilterPos]           = useState<boolean | null>(null);

  const { ts_indices, runs } = spaghetti;

  const mcRuns: MCRun[] = useMemo(() => runs.map(r => ({
    run_idx:    r.run_idx,
    return_pct: r.return_pct,
    max_dd_pct: r.max_dd_pct,
    sharpe:     r.sharpe,
    win_rate:   r.win_rate,
    equity:     r.equity,
  })), [runs]);

  // Subsample baseline to same length as equity paths
  const baselineSub = useMemo(() => {
    const n = mcRuns[0]?.equity.length ?? 0;
    if (!n || !baselineEquity.length) return [];
    return ts_indices.map(i => baselineEquity[i] ?? baselineEquity[baselineEquity.length - 1]);
  }, [mcRuns, baselineEquity, ts_indices]);

  const positiveCount = runs.filter(r => r.return_pct >= 0).length;
  const negativeCount = runs.length - positiveCount;

  const sortedRuns = useMemo(() => {
    let r = [...runs];
    if (filterPos === true)  r = r.filter(x => x.return_pct >= 0);
    if (filterPos === false) r = r.filter(x => x.return_pct < 0);
    r.sort((a, b) => sortDir === 'desc' ? b[sortField] - a[sortField] : a[sortField] - b[sortField]);
    return r;
  }, [runs, sortField, sortDir, filterPos]);

  const toggleSort = (f: typeof sortField) => {
    if (sortField === f) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortField(f); setSortDir('desc'); }
  };

  return (
    <Card>
      <SectionTitle
        sub={`${runs.length} simulated equity paths · hover to inspect · click to pin · colour: red=loss, teal=gain`}
      >
        {runs.length} Monte Carlo Equity Paths
      </SectionTitle>

      {/* Filter pills */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {[
          { label: `All (${runs.length})`,          v: null,  active: filterPos === null,  cls: 'bg-gray-700 text-white', inact: 'bg-gray-100 text-gray-500' },
          { label: `Profitable (${positiveCount})`, v: true,  active: filterPos === true,  cls: 'bg-green-500 text-white', inact: 'bg-green-50 text-green-600' },
          { label: `Loss (${negativeCount})`,       v: false, active: filterPos === false, cls: 'bg-red-500 text-white',   inact: 'bg-red-50 text-red-500' },
        ].map(({ label, v, active, cls, inact }) => (
          <button key={label}
            onClick={() => setFilterPos(v as boolean | null)}
            className={`px-3 py-1 rounded-full text-xs font-semibold transition ${active ? cls : inact}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Canvas chart */}
      <MCPathsCanvas
        runs={filterPos === null ? mcRuns : mcRuns.filter(r => filterPos ? r.return_pct >= 0 : r.return_pct < 0)}
        baselineEquity={baselineSub}
        timestamps={timestamps}
        tsIndices={ts_indices}
        capital={capital}
        currency={currency}
        locale={locale}
        height={400}
        isLive={false}
      />

      {/* Run log table */}
      <div className="mt-4">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--tv-muted)] mb-2">
          Run Log — click canvas paths or table rows
        </p>
        <div className="overflow-y-auto" style={{ maxHeight: 220 }}>
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-50 z-10">
              <tr>
                <th className="text-left py-1.5 px-2 text-[var(--tv-muted)] font-medium">#</th>
                {[
                  ['return_pct', 'Return'],
                  ['max_dd_pct', 'Max DD'],
                  ['sharpe',     'Sharpe'],
                ].map(([f, label]) => (
                  <th key={f} className="text-right py-1.5 px-2 text-[var(--tv-muted)] font-medium cursor-pointer hover:text-[var(--tv-accent)]"
                    onClick={() => toggleSort(f as typeof sortField)}>
                    {label} {sortField === f ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                  </th>
                ))}
                <th className="text-right py-1.5 px-2 text-[var(--tv-muted)] font-medium">Win %</th>
              </tr>
            </thead>
            <tbody>
              {sortedRuns.map(run => (
                <tr key={run.run_idx}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-default">
                  <td className="py-1.5 px-2">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: `hsl(${Math.round((Math.max(0, Math.min(1, (run.return_pct + 50) / 100))) * 160)},80%,45%)` }} />
                      <span className="text-[var(--tv-muted)]">#{run.run_idx}</span>
                    </div>
                  </td>
                  <td className={`text-right py-1.5 px-2 font-semibold ${run.return_pct >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    {run.return_pct >= 0 ? '+' : ''}{run.return_pct.toFixed(2)}%
                  </td>
                  <td className={`text-right py-1.5 px-2 ${run.max_dd_pct < -15 ? 'text-red-500' : 'text-[var(--tv-muted)]'}`}>
                    {run.max_dd_pct.toFixed(2)}%
                  </td>
                  <td className={`text-right py-1.5 px-2 ${run.sharpe >= 1 ? 'text-green-600' : 'text-[var(--tv-muted)]'}`}>
                    {run.sharpe.toFixed(3)}
                  </td>
                  <td className="text-right py-1.5 px-2 text-[var(--tv-muted)]">
                    {run.win_rate.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props { result: StressResponse; currency: string; locale: string; }

export default function StressResults({ result, currency, locale }: Props) {
  const { baseline, stressed, monte_carlo: mc, series, scenario } = result;

  const baseRet     = (baseline.total_return_pct   ?? 0) as number;
  const baseSharpe  = (baseline.sharpe_ratio        ?? 0) as number;
  const baseSortino = (baseline.sortino_ratio       ?? 0) as number;
  const baseCalmar  = (baseline.calmar_ratio        ?? 0) as number;
  const baseDD      = (baseline.max_drawdown_pct    ?? 0) as number;
  const baseWR      = (baseline.win_rate            ?? 0) as number;
  const baseTrades  = (baseline.num_trades          ?? 0) as number;
  const baseAnn     = (baseline.annualised_return_pct ?? (baseline as any).annualised_return ?? 0) as number;
  const baseEq      = (baseline.final_equity        ?? 0) as number;
  const capital     = (baseline as any).initial_capital ?? baseEq;

  const fmtMoney = (v: number) => `${currency}${v.toLocaleString(locale, { maximumFractionDigits: 0 })}`;

  // ── Equity overlay chart data ────────────────────────────────────────────
  const equityData = useMemo(() => {
    const len = Math.min(series.timestamps.length, series.baseline_equity.length, series.stressed_equity.length);
    return Array.from({ length: len }, (_, i) => ({
      ts:       series.timestamps[i].slice(0, 10),
      baseline: series.baseline_equity[i],
      stressed: series.stressed_equity[i],
      ...(series.equity_fan ? {
        p5:  series.equity_fan.p5[i],
        p95: series.equity_fan.p95[i],
      } : {}),
    }));
  }, [series]);

  // ── Price chart data ─────────────────────────────────────────────────────
  const priceData = useMemo(() => {
    const len = Math.min(series.timestamps.length, series.baseline_price.length, series.stressed_price.length);
    return Array.from({ length: len }, (_, i) => ({
      ts:       series.timestamps[i].slice(0, 10),
      original: series.baseline_price[i],
      perturbed: series.stressed_price[i],
    }));
  }, [series]);

  const returnHistData = useMemo(() => mc?.per_run ? makeBuckets(mc.per_run.map(r => r.return_pct)) : [], [mc]);
  const ddHistData     = useMemo(() => mc?.per_run ? makeBuckets(mc.per_run.map(r => r.max_dd_pct)) : [], [mc]);

  const sevLabel  = scenario.severity <= 0.6 ? 'Mild' : scenario.severity >= 1.4 ? 'Severe' : 'Moderate';
  const xInterval = Math.max(0, Math.floor(equityData.length / 6) - 1);
  const pxInterval = Math.max(0, Math.floor(priceData.length / 6) - 1);

  return (
    <div className="space-y-5">

      {/* Scenario header */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="px-3 py-1 bg-orange-50 border border-orange-200 rounded-full text-orange-600 font-semibold text-xs">
          {scenario.display_name}
        </span>
        <span className="text-xs text-[var(--tv-muted)]">{sevLabel} severity</span>
        {mc && <span className="text-xs text-[var(--tv-muted)]">· {mc.runs} MC runs</span>}
        <span className="text-xs text-[var(--tv-muted)]">
          · Shock {scenario.params?.shock_depth_pct ?? '—'}% / {scenario.params?.shock_duration_days ?? '—'} d / vol×{scenario.params?.vol_multiplier ?? 1}
        </span>
      </div>

      {/* Verdict */}
      <VerdictBanner baseRet={baseRet} stressRet={stressed.return_pct} baseDD={baseDD} stressDD={stressed.max_dd_pct} />

      {/* Baseline stats strip */}
      {baseEq > 0 && (
        <div className="flex flex-wrap gap-2">
          <StatChip label="Baseline Return"  value={`${sign(baseRet)}%`} color={baseRet >= 0 ? 'text-green-600' : 'text-red-500'} />
          <StatChip label="Ann. Return"      value={`${sign(baseAnn)}%`} />
          <StatChip label="Sharpe"           value={fmt(baseSharpe)} />
          <StatChip label="Sortino"          value={fmt(baseSortino)} />
          <StatChip label="Calmar"           value={fmt(baseCalmar)} />
          <StatChip label="Max Drawdown"     value={`${fmt(baseDD)}%`} />
          <StatChip label="Final Equity"     value={fmtMoney(baseEq)} color="text-[var(--tv-accent)]" />
        </div>
      )}

      {/* Primary compare cards */}
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--tv-muted)] mb-2">Baseline vs Stressed</p>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          <CompareCard label="Total Return"  baseline={baseRet}    stressed={stressed.return_pct} />
          <CompareCard label="Sharpe Ratio"  baseline={baseSharpe} stressed={stressed.sharpe}     unit="" />
          <CompareCard label="Max Drawdown"  baseline={baseDD}     stressed={stressed.max_dd_pct} invertBad />
          <CompareCard label="Win Rate"      baseline={baseWR}     stressed={stressed.win_rate} />
          <CompareCard label="# Trades"      baseline={baseTrades} stressed={stressed.num_trades} unit="" decimals={0} />
        </div>
        {(stressed.sortino != null || stressed.calmar != null || stressed.annualized_return != null) && (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
            {stressed.sortino != null && baseSortino !== 0 && (
              <CompareCard label="Sortino Ratio"  baseline={baseSortino} stressed={stressed.sortino}           unit="" />
            )}
            {stressed.calmar  != null && baseCalmar  !== 0 && (
              <CompareCard label="Calmar Ratio"   baseline={baseCalmar}  stressed={stressed.calmar}            unit="" />
            )}
            {stressed.annualized_return != null && (
              <CompareCard label="Ann. Return"    baseline={baseAnn}     stressed={stressed.annualized_return} />
            )}
          </div>
        )}
      </div>

      {/* Equity overlay with Brush */}
      <Card>
        <SectionTitle sub="Drag the scrubber below to zoom into any time window">
          Equity Curve — Baseline vs Stressed{mc && mc.runs > 1 ? ' (P50 representative run)' : ''}
        </SectionTitle>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={equityData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="ts" tick={{ fontSize: 10, fill: '#9CA3AF' }} interval={xInterval} />
            <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} tickFormatter={v => `${currency}${(v/1000).toFixed(0)}k`} width={52} />
            <Tooltip contentStyle={TT_STYLE}
              formatter={(v: number, n: string) => [fmtMoney(v), n]}
              labelStyle={{ color: '#6B7280', fontWeight: 600 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Brush dataKey="ts" height={20} stroke="#e5e7eb" travellerWidth={6} fill="#f9fafb" endIndex={equityData.length - 1} />
            <ReferenceLine y={capital || equityData[0]?.baseline} stroke="#9CA3AF" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="baseline" name="Baseline" stroke="#3B82F6" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="stressed" name="Stressed (P50)" stroke="#F97316" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Price chart with Brush */}
      <Card>
        <SectionTitle sub="Shows exactly where and how much the shock perturbed prices">
          Price Path — Original vs Perturbed
        </SectionTitle>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={priceData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="ts" tick={{ fontSize: 10, fill: '#9CA3AF' }} interval={pxInterval} />
            <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }}
              tickFormatter={v => `${currency}${v.toLocaleString(locale, { maximumFractionDigits: 0 })}`} width={60} />
            <Tooltip contentStyle={TT_STYLE}
              formatter={(v: number, n: string) => [`${currency}${v.toLocaleString(locale, { maximumFractionDigits: 2 })}`, n]}
              labelStyle={{ color: '#6B7280', fontWeight: 600 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Brush dataKey="ts" height={20} stroke="#e5e7eb" travellerWidth={6} fill="#f9fafb" endIndex={priceData.length - 1} />
            <Line type="monotone" dataKey="original"  name="Original"  stroke="#3B82F6" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="perturbed" name="Perturbed" stroke="#F97316" strokeWidth={2} dot={false} strokeDasharray="5 3" />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* ── Monte Carlo section ─────────────────────────────────────────── */}
      {mc && mc.runs > 1 && (
        <div className="space-y-4">

          {/* Interpretation */}
          <MCInterpretation
            runs={mc.runs}
            p5={mc.return_pct.p5}
            p50={mc.return_pct.p50}
            p95={mc.return_pct.p95}
            worst={mc.return_pct.worst}
            best={mc.return_pct.best}
          />

          {/* Canvas MC paths chart */}
          {series.spaghetti && series.spaghetti.runs.length > 0 && (
            <MCPathsCard
              spaghetti={series.spaghetti}
              baselineEquity={series.baseline_equity}
              timestamps={series.timestamps}
              currency={currency}
              locale={locale}
              capital={capital || series.baseline_equity[0] || 10000}
            />
          )}

          {/* Percentile table */}
          <Card>
            <SectionTitle sub="Across all simulations — P5 is your stress-tail, P50 is typical, P95 is the upside">
              Monte Carlo Percentiles ({mc.runs} runs)
            </SectionTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-[var(--tv-text)]">
                <thead>
                  <tr className="border-b border-gray-100">
                    {['Metric','P5 — Tail Risk','P50 — Median','P95 — Best 5%','Worst Run'].map(h => (
                      <th key={h} className={`py-2 text-[var(--tv-muted)] font-medium text-xs ${h === 'Metric' ? 'text-left pr-4' : 'text-right px-3'}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {([
                    { label: 'Return %',     s: mc.return_pct,       unit: '%' },
                    { label: 'Max Drawdown', s: mc.max_drawdown_pct, unit: '%' },
                    { label: 'Sharpe',       s: mc.sharpe,           unit: '' },
                    ...(mc.sortino ? [{ label: 'Sortino', s: mc.sortino, unit: '' as '' }] : []),
                    { label: 'Win Rate',     s: mc.win_rate,         unit: '%' },
                  ] as { label: string; s: { p5: number; p50: number; p95: number; worst: number }; unit: string }[]).map(({ label, s, unit }) => (
                    <tr key={label} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-2.5 pr-4 font-semibold">{label}</td>
                      <td className="text-right px-3 text-red-500 font-medium">{fmt(s.p5)}{unit}</td>
                      <td className="text-right px-3 font-bold text-[var(--tv-text)]">{fmt(s.p50)}{unit}</td>
                      <td className="text-right px-3 text-green-600 font-medium">{fmt(s.p95)}{unit}</td>
                      <td className="text-right px-3 text-red-700 font-bold">{fmt(s.worst)}{unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Histograms side by side */}
          {(returnHistData.length > 0 || ddHistData.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {returnHistData.length > 0 && (
                <Card>
                  <SectionTitle sub="How often each return bucket occurred across all runs">
                    Return Distribution
                  </SectionTitle>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={returnHistData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                      <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                      <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                      <Tooltip contentStyle={TT_STYLE} labelStyle={{ color: '#6B7280' }} formatter={(v: number) => [v, 'Runs']} />
                      <ReferenceLine x="0%" stroke="#9CA3AF" strokeDasharray="4 4" />
                      <Bar dataKey="count" name="Runs" radius={[4,4,0,0]}
                        fill="#F97316" opacity={0.85} />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              )}
              {ddHistData.length > 0 && (
                <Card>
                  <SectionTitle sub="Distribution of max drawdown experienced per simulation">
                    Drawdown Distribution
                  </SectionTitle>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={ddHistData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                      <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                      <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                      <Tooltip contentStyle={TT_STYLE} labelStyle={{ color: '#6B7280' }} formatter={(v: number) => [v, 'Runs']} />
                      <Bar dataKey="count" name="Runs" radius={[4,4,0,0]}
                        fill="#EF4444" opacity={0.85} />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              )}
            </div>
          )}

          {/* P5/P50/P95 band chart */}
          {series.equity_fan && (
            <Card>
              <SectionTitle sub="The shaded band shows the full spread of outcomes — from worst 5% to best 5%">
                Equity Fan — Outcome Band (P5 / P50 / P95 across {mc.runs} runs)
              </SectionTitle>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={equityData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                  <defs>
                    <linearGradient id="p95grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22C55E" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#22C55E" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="p5grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#FEE2E2" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#FEE2E2" stopOpacity={0.2} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis dataKey="ts" tick={{ fontSize: 10, fill: '#9CA3AF' }} interval={xInterval} />
                  <YAxis tick={{ fontSize: 10, fill: '#9CA3AF' }} tickFormatter={v => `${currency}${(v/1000).toFixed(0)}k`} width={52} />
                  <Tooltip contentStyle={TT_STYLE}
                    formatter={(v: number, n: string) => [fmtMoney(v), n]}
                    labelStyle={{ color: '#6B7280', fontWeight: 600 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Brush dataKey="ts" height={20} stroke="#e5e7eb" travellerWidth={6} fill="#f9fafb" endIndex={equityData.length - 1} />
                  <Area type="monotone" dataKey="p95"      name="P95 (Best 5%)"   stroke="#22C55E" fill="url(#p95grad)" strokeWidth={1.5} dot={false} />
                  <Area type="monotone" dataKey="stressed" name="P50 (Median)"    stroke="#F97316" fill="#F97316"       fillOpacity={0.08} strokeWidth={2} dot={false} />
                  <Area type="monotone" dataKey="p5"       name="P5 (Worst 5%)"   stroke="#EF4444" fill="url(#p5grad)"  strokeWidth={1.5} dot={false} />
                  <Line  type="monotone" dataKey="baseline" name="Baseline"        stroke="#3B82F6" strokeWidth={2} dot={false} strokeDasharray="6 3" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          )}

        </div>
      )}
    </div>
  );
}
