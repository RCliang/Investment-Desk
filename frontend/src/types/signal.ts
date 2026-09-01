/** Types for the quant signal + backtest pipeline (backend /api/quant/*). */

/** One strategy in a scorecard. */
export interface StrategyDef {
  name: string;           // trend_ma | trend_breakout | breakout_donchian | ...
  category: 'trend' | 'momentum' | 'volume' | 'risk';
  weight: number;         // within-category weight
  normalized_weight?: number;  // weight × category_weight (v1_default only)
}

/** One strategy set (e.g. v1_default, trend_follow). */
export interface StrategySet {
  strategy_set: string;
  category_weights: Record<string, number>;
  buy_threshold: number;
  sell_threshold: number;
  strategies: StrategyDef[];
}

/** Strategy catalog response: a list of available strategy sets. */
export interface StrategiesResponse {
  strategy_sets: StrategySet[];
}

/** Per-strategy score breakdown for a single day. */
export interface SignalDetail {
  trend_ma: number;
  breakout_donchian: number;
  momentum_macd: number;
  momentum_rsi: number;
  volume_price: number;
  risk_atr: number;
  [key: string]: number;
}

/** A chain membership (sub_industry within a layer). */
export interface SignalChain {
  sub_industry_id: string;
  sub_industry_name: string;
  layer_code: string;
  layer_name: string;
}

/** One row in the signals list. */
export interface SignalItem {
  ticker: string;
  name: string;
  market: string | null;
  date: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  composite_score: number;   // [-1, +1]
  position_pct: number;      // [0, 1]
  stop_loss_price: number | null;
  target_price: number | null;
  chains: SignalChain[];
  detail: SignalDetail;
}

export interface SignalListResponse {
  total: number;
  date: string | null;
  strategy_set: string;
  items: SignalItem[];
}

/** Full detail for one ticker's latest signal. */
export interface SignalDetailResponse {
  ticker: string;
  strategy_set?: string;
  name: string;
  market: string | null;
  date: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  composite_score: number;
  position_pct: number;
  stop_loss_price: number | null;
  target_price: number | null;
  detail: SignalDetail;
  chains: SignalChain[];
}

/** Backtest run summary (returned by POST /backtest). */
export interface BacktestSummary {
  run_id: number;
  ticker: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  annual_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  win_rate_pct: number;
  trade_count: number;
  avg_hold_days: number;
  params: {
    commission_rate: number;
    commission_min: number;
    stamp_duty_rate: number;
    slippage_rate: number;
    lot_size: number;
    limit_band: number;
  };
}

export interface EquityPoint {
  date: string;
  equity: number;
}

export interface BacktestTrade {
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  shares: number;
  pnl: number;
  pnl_pct: number;
  hold_days: number;
  exit_reason: 'signal' | 'stop_loss' | 'trailing_stop' | 'end';
}

/** Full backtest detail (returned by GET /backtest/:id). */
export interface BacktestDetail extends BacktestSummary {
  strategy_set: string;
  equity_curve: EquityPoint[];
  trades: BacktestTrade[];
  created_at: string;
}

/** Scan trigger result. */
export interface ScanResult {
  scanned: number;
  date: string;
  strategy_set: string;
  BUY: number;
  SELL: number;
  HOLD: number;
  skipped: number;
  elapsed_s: number;
}
