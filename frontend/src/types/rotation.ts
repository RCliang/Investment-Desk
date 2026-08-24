/** Types for the sector-rotation strategy (backend /api/quant/rotation/*). */

/** One sector in the daily strength snapshot. */
export interface SectorScoreItem {
  sector: string;
  strength: number;          // [0, 1] composite
  flow_dim: number | null;   // 主力维 rank [0, 1]
  tech_dim: number | null;   // 技术维 rank [0, 1]
  member_count: number;
  is_selected: boolean;      // in today's Top-K
  detail: {
    flow_mean_20d?: number | null;   // 板块主力净流入占比 20 日均值
    align_share_20d?: number | null; // 多头排列占比 20 日均值
    momentum_20d?: number | null;    // 板块等权指数 20 日动量
  };
}

export interface SectorScoresResponse {
  date: string | null;
  sectors: SectorScoreItem[];
}

export interface SectorHistoryResponse {
  dates: string[];
  series: Record<string, number[]>;  // sector → strength per date
}

/** One holding in the recommended rotation portfolio. */
export interface RotationHolding {
  ticker: string;
  name: string;
  sector: string;
  rank_in_sector: number | null;
  weight: number;
  composite_score: number;   // [0, 1]
  entry_ok: boolean;         // 多头排列确认
  divergence_flag: boolean;  // 价创新高但主力净流出
  stop_loss_price: number | null;
  factor_scores: Record<string, number>;
}

export interface RotationPortfolioResponse {
  date: string | null;
  holdings: RotationHolding[];
}

/** One stock row in the full in-sector ranking table. */
export interface RotationRankItem {
  ticker: string;
  name: string;
  sector: string;
  rank_in_sector: number | null;
  composite_score: number;
  is_selected: boolean;
  weight: number;
  entry_ok: boolean;
  divergence_flag: boolean;
  stop_loss_price: number | null;
}

export interface RotationRankingsResponse {
  date: string | null;
  stocks: RotationRankItem[];
}

/** Summary of a rotation backtest run (POST /rotation/backtest). */
export interface RotationBacktestSummary {
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
  sector_pnl: Record<string, number>;
  ic_summary: Record<string, { ic_mean: number; icir: number; ic_pct_positive: number }>;
  config: Record<string, unknown>;
}

export interface RotationBacktestRequest {
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  holding_period?: number;
  top_k?: number;
  top_n_per_sector?: number;
  max_weight?: number;
  use_fund_flow_factors?: boolean;
  fund_flow_direction?: 1 | -1;
  stop_mode?: 'fixed' | 'atr';
  atr_mult?: number;
  breakdown_buffer?: number;
  keep_in_trend?: boolean;
  reentry_enabled?: boolean;
  reentry_cooldown?: number;
}

/** Scan summary (admin-triggered POST /rotation/scan). */
export interface RotationScanResult {
  date: string;
  sector_count: number;
  scanned: number;
  selected: number;
  top_sectors: {
    sector: string;
    strength: number;
    chosen: string[];
    skipped_non_bullish: string[];
  }[];
  holdings: { ticker: string; name: string; weight: number }[];
  elapsed_s: number;
}
