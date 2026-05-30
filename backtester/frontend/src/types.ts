export type Strategy       = 'GRID' | 'DCA' | 'PLA';
export type DataSource     = 'binance' | 'coingecko' | 'yfinance' | 'nse' | 'bse';
export type Interval       = '1d' | '4h' | '1h' | '15m' | '1w';
export type MarketType     = 'equity_delivery' | 'equity_intraday' | 'futures' | 'options' | 'crypto';
export type BrokerageModel = 'flat' | 'percentage' | 'zero';

export interface Trade {
  entry_time:  string;
  entry_price: number;
  exit_time?:  string;
  exit_price?: number;
  quantity:    number;
  pnl:         number;
  pnl_pct:     number;
  fees:        number;
  side:        string;
}

export interface CostBreakdown {
  brokerage: number; stt: number; exchange_charges: number;
  sebi_charges: number; gst: number; stamp_duty: number; total: number;
}

export interface RegimeStat {
  total_return_pct: number; sharpe_ratio: number; sortino_ratio: number;
  volatility_pct: number; max_drawdown_pct: number; num_candles: number;
  pct_of_period: number; num_trades: number; win_rate: number;
  profit_factor: number; avg_trade_pnl: number; best_trade: number;
  worst_trade: number; gross_profit: number; gross_loss: number;
  avg_trade_duration: number;
}

export interface RegimeBreakdownData {
  method: string;
  regime_counts: { bull: number; bear: number; sideways: number };
  bull: RegimeStat; bear: RegimeStat; sideways: RegimeStat;
}

export interface ValidationMetrics {
  num_trades: number; sharpe_ratio: number; sortino_ratio: number;
  total_return_pct: number; annualised_return_pct: number;
  max_drawdown_pct: number; win_rate: number;
  volatility_pct?: number; calmar_ratio?: number;
  final_equity?: number; num_candles?: number;
}

export interface WalkForwardWindow {
  window_num: number; train_period: string; test_period: string;
  best_params: string; train_sharpe: number; return_pct: number;
  sharpe: number; max_dd_pct: number; num_trades: number; win_rate: number;
}

export interface ValidationData {
  mode: 'holdout' | 'walk_forward';
  train_ratio?: number; split_date?: string;
  in_sample?: ValidationMetrics; out_of_sample?: ValidationMetrics;
  verdict?: 'stable' | 'degraded' | 'failed' | 'insufficient_data';
  window?: number; step?: number; num_windows?: number;
  windows?: WalkForwardWindow[];
  validation_equity_curve?: number[];
  validation_timestamps?: string[];
  validation_drawdowns?: number[];
}

export interface MetricsResults {
  total_return_pct: number; total_return_usd: number;
  annualised_return: number; annualised_return_pct: number;
  sharpe_ratio: number; sortino_ratio: number; calmar_ratio: number;
  max_drawdown_pct: number; volatility_pct: number;
  win_rate: number; profit_factor: number; num_trades: number;
  best_trade: number; worst_trade: number; final_equity: number;
  initial_capital: number; avg_trade_pnl: number;
  avg_trade_duration: number; gross_profit: number; gross_loss: number;
  total_fees_paid: number; data_quality_score: number;
  cost_breakdown?: CostBreakdown; regimes?: RegimeBreakdownData;
}

export interface SeriesData {
  equity_curve: number[]; drawdowns: number[]; timestamps: string[];
  trades: Trade[]; close_prices: number[]; regime_labels?: string[];
}

export interface BacktestResponse {
  backtest_id: string; status: string; report_url: string;
  currency: string; market_type: string;
  results: MetricsResults; series: SeriesData; validation?: ValidationData;
}

export type StressScenarioKey =
  | 'gfc_2008' | 'covid_crash' | 'flash_crash_2010' | 'luna_collapse'
  | 'liquidity_drought' | 'pump_dump' | 'whipsaw_chop' | 'slow_bleed'
  | 'vol_spike' | 'gap_risk' | 'range_bound' | 'trend_reversal'
  | 'outlier_injection';

export type StressSeverity = 'mild' | 'moderate' | 'severe' | 'custom';

export interface MonteCarloStats { p5: number; p50: number; p95: number; worst: number; best?: number; }

export interface StressRunMetrics {
  return_pct: number; sharpe: number; sortino?: number; calmar?: number;
  max_dd_pct: number; win_rate: number; num_trades: number;
  final_equity?: number; annualized_return?: number;
}

export interface StressMonteCarloResult {
  runs: number; return_pct: MonteCarloStats; max_drawdown_pct: MonteCarloStats;
  sharpe: MonteCarloStats; sortino?: MonteCarloStats; win_rate: MonteCarloStats;
  per_run: StressRunMetrics[];
}

export interface SpaghettiRun {
  run_idx: number; return_pct: number; max_dd_pct: number; sharpe: number; win_rate: number; equity: number[];
}

export interface StressSeries {
  timestamps: string[]; baseline_equity: number[]; stressed_equity: number[];
  stressed_price: number[]; baseline_price: number[];
  equity_fan?: { p5: number[]; p50: number[]; p95: number[] };
  spaghetti?: { ts_indices: number[]; runs: SpaghettiRun[] };
}

export interface StressResponse {
  backtest_id: string; symbol: string; strategy: string;
  scenario: { name: string; display_name: string; severity: number; params: Record<string, number> };
  baseline: Partial<MetricsResults>;
  stressed: StressRunMetrics & { equity_curve: number[] };
  monte_carlo?: StressMonteCarloResult;
  series: StressSeries;
}

export interface StressFormState {
  symbol: string; customSymbol: string; source: DataSource;
  startDate: string; endDate: string; datePreset: string; interval: Interval;
  capital: number; feePct: number; slippagePct: number;
  strategy: Strategy;
  lowerBound: number; upperBound: number; numLevels: number;
  gridSpacing: 'linear' | 'exponential'; gridInvestPerLevel: number;
  buyIntervalHours: number; dcaInvestPerBuy: number; holdDays: number;
  dcaExitType: 'time' | 'profit'; profitTargetPct: number;
  fastEma: number; slowEma: number;
  plaExitType: 'crossover' | 'take_profit' | 'stop_loss';
  takeProfitPct: number; stopLossPct: number;
  plaLvl2Pct: number; plaLvl3Pct: number; plaLvl4Pct: number;
  plaInvestPerLevel: number;
  marketType: MarketType; brokerageModel: BrokerageModel;
  brokerageFlat: number; brokeragePct: number;
  scenarioKey: StressScenarioKey; severity: StressSeverity;
  shockDepthPct?: number; shockDurationDays?: number; volMultiplier?: number;
  outlierCount: number; mcRuns: number; seed?: number;
}

export interface FormState {
  symbol: string; customSymbol: string; source: DataSource;
  startDate: string; endDate: string; datePreset: string; interval: Interval;
  capital: number; feePct: number; slippagePct: number;
  strategy: Strategy;
  lowerBound: number; upperBound: number; numLevels: number;
  gridSpacing: 'linear' | 'exponential'; gridInvestPerLevel: number;
  buyIntervalHours: number; dcaInvestPerBuy: number; holdDays: number;
  dcaExitType: 'time' | 'profit'; profitTargetPct: number;
  fastEma: number; slowEma: number;
  plaExitType: 'crossover' | 'take_profit' | 'stop_loss';
  takeProfitPct: number; stopLossPct: number;
  plaLvl2Pct: number; plaLvl3Pct: number; plaLvl4Pct: number;
  plaInvestPerLevel: number;
  marketType: MarketType; brokerageModel: BrokerageModel;
  brokerageFlat: number; brokeragePct: number;
  validationMode: 'none' | 'holdout' | 'walk_forward';
  trainRatio: number; wfWindow: number; wfStep: number;
}
