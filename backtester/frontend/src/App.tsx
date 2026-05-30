import { useState } from 'react';
import Sidebar         from './components/Sidebar';
import MetricsGrid     from './components/MetricsGrid';
import ChartsPanel     from './components/ChartsPanel';
import TradeLog        from './components/TradeLog';
import StressPage      from './components/StressPage';
import { FormState, BacktestResponse } from './types';
import { runBacktest, isIndianSource } from './api';

type Page   = 'backtest' | 'stress';
type Status = 'idle' | 'loading' | 'success' | 'error';
type Tab    = 'charts' | 'trades' | 'report' | 'validation';

const today = new Date();
const fmt   = (d: Date) => d.toISOString().split('T')[0];
const yr1   = fmt(new Date(today.getTime() - 365 * 86_400_000));

const DEFAULT_FORM: FormState = {
  symbol: 'BTC/USDT', customSymbol: 'BTC/USDT', source: 'binance',
  startDate: yr1, endDate: fmt(today), datePreset: '1Y', interval: '1d',
  capital: 10_000, feePct: 0.10, slippagePct: 0.05, strategy: 'DCA',
  lowerBound: 20_000, upperBound: 70_000, numLevels: 5, gridSpacing: 'linear',
  gridInvestPerLevel: 500, buyIntervalHours: 24, dcaInvestPerBuy: 200,
  holdDays: 30, dcaExitType: 'time', profitTargetPct: 10,
  fastEma: 12, slowEma: 26, plaExitType: 'crossover',
  takeProfitPct: 5, stopLossPct: 3,
  plaLvl2Pct: -1, plaLvl3Pct: -2.5, plaLvl4Pct: -4, plaInvestPerLevel: 300,
  marketType: 'equity_delivery', brokerageModel: 'flat',
  brokerageFlat: 20, brokeragePct: 0.5,
  validationMode: 'none', trainRatio: 0.7, wfWindow: 252, wfStep: 63,
};

export default function App() {
  const [page,     setPage]     = useState<Page>('backtest');
  const [form,     setForm]     = useState<FormState>(DEFAULT_FORM);
  const [status,   setStatus]   = useState<Status>('idle');
  const [result,   setResult]   = useState<BacktestResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [tab,      setTab]      = useState<Tab>('charts');

  const updateForm = (updates: Partial<FormState>) =>
    setForm(prev => ({ ...prev, ...updates }));

  const handleRun = async () => {
    if (form.startDate >= form.endDate) {
      setErrorMsg('Start date must be before end date.'); setStatus('error'); return;
    }
    setStatus('loading'); setErrorMsg('');
    try {
      const data = await runBacktest(form);
      setResult(data); setStatus('success'); setTab('charts');
    } catch (err: any) {
      setErrorMsg(err.message || 'Unknown error'); setStatus('error');
    }
  };

  const symbol   = form.symbol === '__custom__' ? form.customSymbol : form.symbol;
  const currency = result?.currency ?? (isIndianSource(form.source) ? '₹' : '$');
  const locale   = isIndianSource(form.source) ? 'en-IN' : 'en-US';

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--tv-bg)] font-sans flex-col">

      {/* Nav */}
      <div className="flex-shrink-0 bg-[var(--tv-bg)]/95 backdrop-blur-md z-20 px-6 py-3 flex items-center justify-between border-b border-[var(--tv-border)]">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg font-black text-sm text-white" style={{ background: 'var(--tv-accent)' }}>TV</div>
          <div className="flex items-baseline gap-0.5">
            <span className="text-xl font-bold tracking-tight text-[var(--tv-text)]">Trade</span>
            <span className="text-xl font-bold tracking-tight text-[var(--tv-accent)]">Ved</span>
          </div>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-full p-1">
          {([{ key: 'backtest', label: '📈 Backtest' }, { key: 'stress', label: '🧪 Stress Test' }] as { key: Page; label: string }[]).map(p => (
            <button key={p.key} onClick={() => setPage(p.key)}
              className={`px-5 py-1.5 rounded-full text-sm font-semibold transition-all ${
                page === p.key ? 'bg-white text-[var(--tv-accent)] shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}>{p.label}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button className="w-9 h-9 flex items-center justify-center bg-[var(--tv-accent)] rounded-full text-white font-bold text-sm">HK</button>
        </div>
      </div>

      {/* Page content */}
      {page === 'stress' ? (
        <div className="flex-1 overflow-hidden"><StressPage /></div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <aside className="w-80 flex-shrink-0 overflow-y-auto bg-[var(--tv-s1)] shadow-sm z-10 border-r border-gray-100">
            <Sidebar form={form} onChange={updateForm} onRun={handleRun} loading={status === 'loading'} />
          </aside>
          <main className="flex-1 overflow-y-auto">
            <div className="p-8 max-w-[1400px] mx-auto">
              <div className="mb-6">
                <h1 className="text-3xl font-bold text-[var(--tv-text)] mb-1">Backtester</h1>
                <p className="text-sm text-[var(--tv-muted)]">
                  {symbol} · {form.strategy} · {form.startDate} → {form.endDate} · {currency}{form.capital.toLocaleString(locale)}
                  {isIndianSource(form.source) && <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-orange-100 text-orange-600">🇮🇳 NSE</span>}
                </p>
              </div>
              {status === 'loading' && (
                <div className="flex flex-col items-center justify-center py-20 bg-white rounded-3xl tv-soft-shadow">
                  <div className="animate-spin rounded-full h-10 w-10 border-4 border-gray-100 border-t-[var(--tv-accent)] mb-4" />
                  <p className="text-lg font-medium">Running backtest for {symbol}…</p>
                </div>
              )}
              {status === 'error' && (
                <div className="p-5 rounded-2xl mb-6 bg-red-50 border border-red-100 flex items-start gap-3">
                  <span className="text-xl">❌</span>
                  <div><p className="font-semibold text-red-700">{errorMsg}</p></div>
                </div>
              )}
              {status === 'idle' && (
                <div className="flex flex-col items-center justify-center py-24 bg-white rounded-3xl tv-soft-shadow">
                  <p className="text-xl font-bold mb-2">Ready to Backtest</p>
                  <p className="text-sm text-[var(--tv-muted)]">Configure your strategy in the sidebar and click Run.</p>
                </div>
              )}
              {status === 'success' && result && (
                <div className="space-y-8 fade-in">
                  <MetricsGrid results={result.results} currency={currency} />
                  <div className="flex gap-2 p-1 bg-white rounded-full tv-soft-shadow w-max">
                    {(['charts', 'trades', 'report'] as Tab[]).map(t => (
                      <button key={t} onClick={() => setTab(t)}
                        className={`px-6 py-2 rounded-full text-sm font-semibold transition-all ${
                          tab === t ? 'bg-[var(--tv-accent)] text-white shadow-sm' : 'text-gray-500 hover:bg-gray-50'
                        }`}>
                        {t === 'charts' ? '📈 Charts' : t === 'trades' ? '\ud83d��� Trade Log' : '📄 Summary'}
                      </button>
                    ))}
                  </div>
                  <div className="bg-white rounded-3xl p-6 tv-soft-shadow">
                    {tab === 'charts' && <ChartsPanel series={result.series} initialCapital={result.results.initial_capital ?? form.capital} currency={currency} validation={result.validation} />}
                    {tab === 'trades' && <TradeLog trades={result.series.trades} currency={currency} />}
                    {tab === 'report' && (
                      <pre className="text-sm text-gray-700 font-mono whitespace-pre-wrap bg-gray-50 rounded-2xl p-6">
                        {JSON.stringify({ backtest_id: result.backtest_id, symbol, strategy: form.strategy, total_return: `${result.results.total_return_pct.toFixed(2)}%`, sharpe: result.results.sharpe_ratio.toFixed(4), max_dd: `${result.results.max_drawdown_pct.toFixed(2)}%`, trades: result.results.num_trades, win_rate: `${result.results.win_rate.toFixed(1)}%` }, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      )}
    </div>
  );
}
