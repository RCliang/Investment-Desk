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
