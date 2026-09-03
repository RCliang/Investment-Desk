/** Types for the ETF dual-momentum rotation strategy
 *  (backend /api/quant/etf-rotation/*). */

/** One ETF in the daily dual-momentum snapshot. */
export interface EtfScoreItem {
  ticker: string;
  name: string;
  asset_class: string;        // 宽基 / 行业 / 防守 / 货币
  momentum_raw: number | null;   // 复合动量 (未除波动率)
  momentum_score: number | null; // 动量 / 年化波动率
  momentum_rank: number | null;  // 截面排名 (1=最强, 货币ETF=null)
  abs_momentum_pass: boolean;    // 180日收益 ≥ 货币ETF(TOP1方案门槛窗)
  is_selected: boolean;
  weight: number;
  stop_price: number | null;
  detail: {
    r20?: number | null;    // 旧窗口方案遗留
    r60?: number | null;    // ≈3月
    r120?: number | null;   // ≈6月
    r180?: number | null;   // 绝对动量门槛窗
    r250?: number | null;   // ≈12月
  };
}

export interface EtfScoresResponse {
  date: string | null;
  etfs: EtfScoreItem[];
}

/** One holding in the target ETF portfolio (risk ETFs + cash parking). */
export interface EtfHolding {
  ticker: string;
  name: string;
  asset_class: string;
  momentum_score: number | null;
  momentum_rank: number | null;
  weight: number;
  stop_price: number | null;
}

export interface EtfPortfolioResponse {
  date: string | null;
  holdings: EtfHolding[];
}

/** Summary of an ETF backtest run (POST /etf-rotation/backtest). */
export interface EtfBacktestSummary {
  run_id: number;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  annual_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  rebalance_count: number;
  avg_turnover_pct: number;
  trade_count: number;
  win_rate_pct: number;
  benchmark_total_return_pct: number;
  excess_return_pct: number;
  sector_pnl: Record<string, number>;   // asset_class → PnL (元)
  ic_summary: Record<string, never>;    // placeholder (rule-based strategy)
  config: Record<string, unknown>;
}

export interface EtfBacktestRequest {
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  top_n?: number;
  buffer_rank?: number;
  holding_period?: number;
  use_abs_gate?: boolean;   // false = 纯相对动量 (消融 A1)
  use_buffer?: boolean;     // false = 关闭排名缓冲带
  use_market_gate?: boolean;      // 大盘MA择时: 510300 跌破 MA 屏蔽宽基+行业
  market_ma_window?: number;      // 择时均线窗口 (交易日)
  rebalance_mode?: 'fixed' | 'dynamic';  // dynamic = 每日检查、持仓变化才交易
  rebalance_anchor?: 'calendar' | 'grid'; // calendar(默认) = 每月首个交易日调仓
  weight_mode?: 'equal' | 'risk_parity'; // risk_parity = 逆波动率加权
  use_target_vol?: boolean;       // 目标波动率降仓, 释放份额停货币ETF
  target_vol?: number;            // 目标年化波动率 (0.10 = 10%)
  exit_replacement?: boolean;     // true(默认) = 退出后当日防守类补位(国债/黄金/红利)
}

/** Scan summary (admin-triggered POST /etf-rotation/scan). */
export interface EtfScanResult {
  date: string;
  scanned: number;
  selected: number;
  cash_weight: number;
  holdings: { ticker: string; name: string; weight: number }[];
  elapsed_s: number;
}
