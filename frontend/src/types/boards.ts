/** Types for the market board heat dashboard (backend /api/quant/boards/*). */

/** Lifecycle tag of a board on a given date. */
export type BoardTag = 'mainline' | 'starting' | 'fading' | 'cool';

export const TAG_LABELS: Record<BoardTag, string> = {
  mainline: '主线',
  starting: '启动',
  fading: '退潮',
  cool: '冷却',
};

/** Per-board sparkline series for the leaderboard cards. */
export interface BoardSpark {
  dates: string[];
  heat: (number | null)[];      // heat_ema per date
  excess: (number | null)[];    // 20d cumulative excess return %
  flow_cum: number[];           // cumulative main inflow within window (亿)
}

/** One board in the overview leaderboard. */
export interface BoardOverviewItem {
  bk_code: string;
  name: string;
  bk_type: 'industry' | 'concept';
  heat: number;                  // [0, 100]
  heat_ema: number;
  tag: BoardTag | null;
  heat_rank: number | null;
  mom_excess_20d: number | null; // 20日累计超额收益%
  flow_ratio_20d: number | null; // 20日主力净流入/成交额
  breadth_20d: number | null;    // 20日均上涨家数占比 [0,1]
  theme_cnt: number;             // THS 强势股题材匹配数
  turnover_avg_20d: number | null; // 20日均成交额(亿)
  member_hint: number | null;
  leader: { name: string | null; code: string | null; change: number | null } | null;
  spark: BoardSpark | null;
}

export interface BoardsOverviewResponse {
  date: string | null;
  industries: BoardOverviewItem[];
  concepts: BoardOverviewItem[];
  weights: Record<string, number>;
  zombie_filter: { min_members: number; min_turnover_yi: number };
}

/** One row of the heat matrix. */
export interface BoardHeatmapRow {
  bk_code: string;
  name: string;
  bk_type: 'industry' | 'concept';
  tag: BoardTag | null;
  heat_ema: number;
  values: (number | null)[];     // aligned to response dates
}

export interface BoardsHeatmapResponse {
  date: string | null;
  dates: string[];
  rows: BoardHeatmapRow[];
}

/** Drill-down detail for one board. */
export interface BoardDetailResponse {
  bk_code: string;
  name: string;
  bk_type: string;
  member_hint: number | null;
  dates: string[];
  change_pct: (number | null)[];
  excess: number[];              // cumulative excess vs HS300 within window (%)
  main_net: (number | null)[];   // 元
  heat: { heat: number | null; heat_ema: number | null; tag: BoardTag | null }[];
  leaders: { date: string; name: string | null; code: string | null; change: number | null }[];
  latest: {
    tag: BoardTag | null; heat: number; heat_ema: number;
    heat_rank: number | null; theme_cnt: number | null;
  } | null;
}

/** THS theme strong-count evolution. */
export interface ThemeTrendsResponse {
  date: string | null;
  dates: string[];
  themes: Record<string, number[]>;  // tag → strong count per date
  perf: Record<string, number[]>;    // 业绩线 tags
}

/** Nightly refresh summary (admin POST /refresh). */
export interface BoardsRefreshResult {
  date: string;
  boards: number;
  classified: Record<string, number>;
  benchmark_pct: number;
  theme_tags: number;
  theme_strong: number;
  heat: { dates: number; boards: number; rows: number };
  elapsed_s: number;
}
