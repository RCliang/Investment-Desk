/**
 * Deep analysis pipeline 类型定义。
 * 与后端 backend/app/routers/deep_analysis.py + research.py 对齐。
 */

// ── 研报搜索（/api/research/*） ────────────────────────────────────

/** 东财按股票代码搜出的研报条目 */
export interface ResearchReport {
  title: string;
  publish_date: string;  // YYYY-MM-DD
  org_name: string;
  rating?: string;
  industry?: string;
  info_code: string;
  pdf_url: string;
}

/** iwencai 关键词搜出的研报条目（无 info_code） */
export interface SearchReport {
  title: string;
  publish_date: string;
  org_name: string;
  stock_codes: string[];
  source: string;
}

// ── 下载（/api/research/download） ────────────────────────────────

export interface DownloadRequestItem {
  info_code: string;
  publish_date: string;
  org_name: string;
  title: string;
}

export interface DownloadResult {
  info_code: string;
  filename: string;
  oss_url: string;
  status: 'ok' | 'exists' | 'failed';
  error?: string;
}

// ── 解析（/api/deep-analysis/parse） ──────────────────────────────

export interface ParseResponse {
  total: number;
  cached: number;
  submitted: number;
  failed: number;
  results: ParseResultItem[];
  mineru_mode: 'live' | 'mock';
}

export interface ParseResultItem {
  oss_key: string;
  status: 'cached' | 'submitted' | 'failed';
  task_id?: string;
  error?: string;
}

// ── 解析状态（/api/deep-analysis/parse-status） ───────────────────

export interface ParseStatusResponse {
  code: string;
  total: number;
  done: number;
  pending: number;
  failed: number;
  details: ParseStatusItem[];
}

export interface ParseStatusItem {
  oss_key: string;
  status: 'done' | 'parsing' | 'failed';
  token_count?: number;
  error?: string;
}

// ── 历史（/api/deep-analysis/history） ────────────────────────────

export interface HistoryResponse {
  code: string;
  analyses: HistoryItem[];
}

export interface HistoryItem {
  id: number;
  created_at: string;
  model_name: string;
  report_count: number;
  preview: string;
}

export interface AnalysisRecord {
  id: number;
  stock_code: string;
  oss_keys: string[];
  analysis_text: string;
  created_at: string;
  model_name: string;
}

// ── 结构化分析(v2) ─────────────────────────────────────────────

export type CompanyType = 'equipment' | 'material' | 'packaging' | 'ip' | 'general';

export type BucketId = 'industry_chain' | 'equipment' | 'material' | 'financial' | 'risk' | 'catalyst';

export type Evidence = 'strong' | 'medium' | 'weak' | 'unknown';

export interface FieldValue {
  value: string | number | string[] | null;
  evidence: Evidence;
  quote: string | null;
}

export interface BucketResult {
  bucket_id: BucketId;
  fields: Record<string, FieldValue>;
}

export interface AnalysisStats {
  ok: number;
  error: number;
  total: number;
}

export interface AnalysisDoc {
  version: 'v2';
  company_type: CompanyType;
  stock_code: string;
  buckets: BucketResult[];
  analyzed_at: string;
  model_name: string;
  stats: AnalysisStats;
}

export const COMPANY_TYPE_LABELS: Record<CompanyType, string> = {
  equipment: '设备',
  material:  '材料',
  packaging: '封测',
  ip:        'IP',
  general:   '综合',
};

export const BUCKET_DISPLAY_NAMES: Record<BucketId, string> = {
  industry_chain: '产业链与竞争格局',
  equipment:      '设备层指标',
  material:       '材料层指标',
  financial:      '分业务财务',
  risk:           '风险与反证',
  catalyst:       '催化剂与监控',
};
