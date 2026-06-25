/**
 * TypeScript interfaces for the v1 chain knowledge base API.
 *
 * Mirrors the response shapes returned by /api/chainkb/* (see backend
 * app/services/chainkb_service.py). All numeric fields are nullable
 * because HK/US reference companies have no quote/finance data, and
 * some CN fields may be missing for newly listed tickers.
 */

// ── Structural (tree) ────────────────────────────────────────────────────

export interface SubIndustry {
  id: number;
  group_id: string;       // e.g. "II-M-1"
  name_zh: string;
  name_en: string;
  company_count: number;  // non-reference companies only
}

export interface Layer {
  code: string;           // "I" | "II" | "III" | "IV" | "V"
  name_zh: string;
  name_en: string;
  layer_order: number;    // 1..5
  sub_industries: SubIndustry[];
}

export interface TreeResponse {
  layers: Layer[];
}

// ── Company brief (used in lists + search results) ───────────────────────

export interface CompanyBrief {
  id: number;
  ticker: string;
  name_zh: string;
  name_en: string;
  market: string;          // SH | SZ | BJ | HK | US | ...
  is_reference: boolean;
  lifecycle: string;       // canonical | generated | deprecated
}

// ── Market + financial snapshots ─────────────────────────────────────────

export interface Quote {
  price: number | null;
  last_close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  change_amt: number | null;
  change_pct: number | null;
  amount_wan: number | null;
  turnover_pct: number | null;
  pe_ttm: number | null;
  pe_static: number | null;
  pb: number | null;
  mcap_yi: number | null;
  float_mcap_yi: number | null;
  limit_up: number | null;
  limit_down: number | null;
  vol_ratio: number | null;
  amplitude_pct: number | null;
  fetched_at: string | null;
  source: string;
}

export interface FinanceSnapshot {
  eps: number | null;
  bvps: number | null;
  roe_pct: number | null;
  net_margin_pct: number | null;
  gross_margin_pct: number | null;
  revenue_yi: number | null;
  net_profit_yi: number | null;
  debt_ratio_pct: number | null;
  float_shares: number | null;
  total_shares: number | null;
  fetched_at: string | null;
  source: string;
}

// ── Sub-industry detail (companies + market data) ────────────────────────

export interface CompanyWithMarket extends CompanyBrief {
  quote: Quote | null;
  finance: FinanceSnapshot | null;
}

export interface SubIndustryBrief {
  id: number;
  group_id: string;
  name_zh: string;
  name_en: string;
  layer_code: string | null;
  layer_name_zh: string | null;
}

export interface SubIndustryDetail {
  sub_industry: SubIndustryBrief;
  companies: CompanyWithMarket[];
}

// ── Company profile (single-company deep view) ───────────────────────────

export interface Concept {
  name: string;
  tag_type: string;        // industry | concept | region | index
}

export interface CompanySubIndustry {
  id: number;
  group_id: string;
  name_zh: string;
  name_en: string;
  layer_code: string | null;
  layer_name_zh: string | null;
}

export interface CompanyProfile {
  company: CompanyBrief & { description: string };
  quote: Quote | null;
  finance: FinanceSnapshot | null;
  concepts: Concept[];
  sub_industries: CompanySubIndustry[];
}

// ── Time-series ──────────────────────────────────────────────────────────

export interface LockupEvent {
  date: string | null;
  type: string;
  shares_wan: number | null;
  ratio_pct: number | null;
  mcap_wan: number | null;
  total_shares_ratio_pct: number | null;
  is_upcoming: boolean;
}

export interface HolderPeriod {
  end_date: string | null;
  notice_date: string | null;
  holder_num: number | null;
  change_num: number | null;
  change_ratio_pct: number | null;
  avg_free_shares: number | null;
  avg_hold_amt_yi: number | null;
  close_price: number | null;
}

export interface MarginDaily {
  date: string | null;
  rzye_yi: number | null;          // 融资余额 (亿)
  rqye_yi: number | null;          // 融券余额 (亿)
  rzrqye_yi: number | null;        // 合计 (亿)
  rzmre_yi: number | null;
  rzche_yi: number | null;
  rzjme_yi: number | null;         // 融资净买额 (亿)
  rqmcl_wan: number | null;
  rqchl_wan: number | null;
  rqjmg_wan: number | null;
  rzyezb_pct: number | null;
  close_price: number | null;
  change_pct: number | null;
}

export interface ResearchReport {
  publish_date: string | null;
  broker: string;
  title: string;
  rating: string;
  industry: string;
  info_code: string;
  predict_this_year_eps: number | null;
  predict_next_year_eps: number | null;
  predict_next_two_year_eps: number | null;
}

export interface TimeSeriesResponse {
  ticker: string;
  lockup?: LockupEvent[];
  holders?: HolderPeriod[];
  margin?: MarginDaily[];
  reports?: ResearchReport[];
}

// ── Search ───────────────────────────────────────────────────────────────

export interface SearchResult extends CompanyBrief {
  sub_industries: { group_id: string; name_zh: string }[];
}

export interface SearchResponse {
  q: string;
  results: SearchResult[];
}
