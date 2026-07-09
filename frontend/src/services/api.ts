import axios from 'axios';

// 生产环境使用相对路径（通过nginx代理），开发环境使用localhost:8000
const isDev = import.meta.env.DEV;
const api = axios.create({
  baseURL: isDev ? 'http://localhost:8000' : ''
});

// ── Admin auth helpers ─────────────────────────────────────────────
// Shared between the axios interceptors (below) and streamAnalyze's
// native fetch() call (which bypasses axios). Keep STORAGE_KEY in sync
// with frontend/src/auth/AdminAuthContext.tsx.
const ADMIN_TOKEN_KEY = 'adminToken';
const ADMIN_UNAUTHORIZED_EVENT = 'admin:unauthorized';

function readAdminToken(): string | null {
  return (
    localStorage.getItem(ADMIN_TOKEN_KEY) ??
    sessionStorage.getItem(ADMIN_TOKEN_KEY)
  );
}

function notifyAdminUnauthorized() {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  window.dispatchEvent(new Event(ADMIN_UNAUTHORIZED_EVENT));
}

// ── Admin auth interceptors (axios only) ───────────────────────────
// Request: attach X-Admin-Token if a token is stored.
// NOTE: streamAnalyze uses native fetch() and replicates this injection
// itself — the interceptor does not catch fetch() calls.
api.interceptors.request.use((config) => {
  const token = readAdminToken();
  if (token) {
    config.headers['X-Admin-Token'] = token;
  }
  return config;
});

// Response: on 401, clear any stored token and notify the auth context.
// AdminAuthContext listens for this event, resets its state, and the
// app reopens the login modal.
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      notifyAdminUnauthorized();
    }
    return Promise.reject(error);
  },
);

// --- Chain Knowledge Base (v1) ---
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
} from '../types/chainkb';
export type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
};

export async function getChainKbTree(): Promise<TreeResponse> {
  const { data } = await api.get<TreeResponse>('/api/chainkb/tree');
  return data;
}

export async function getChainKbSubIndustry(groupId: string): Promise<SubIndustryDetail> {
  const { data } = await api.get<SubIndustryDetail>(`/api/chainkb/sub_industries/${groupId}`);
  return data;
}

export async function getChainKbCompany(ticker: string): Promise<CompanyProfile> {
  const { data } = await api.get<CompanyProfile>(`/api/chainkb/companies/${ticker}`);
  return data;
}

export async function getChainKbTimeseries(
  ticker: string,
  opts: { types?: string[]; limit?: number } = {},
): Promise<TimeSeriesResponse> {
  const params: Record<string, string> = {};
  if (opts.types && opts.types.length) params.types = opts.types.join(',');
  if (opts.limit != null) params.limit = String(opts.limit);
  const { data } = await api.get<TimeSeriesResponse>(
    `/api/chainkb/companies/${ticker}/timeseries`,
    { params },
  );
  return data;
}

export async function searchChainKb(q: string, limit = 20): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/api/chainkb/search', {
    params: { q, limit },
  });
  return data;
}

// --- Freshness (data update timestamps) ---
import type { FreshnessResponse } from '../types/chainkb';

export async function getFreshness(): Promise<FreshnessResponse> {
  const { data } = await api.get<FreshnessResponse>('/api/chainkb/freshness');
  return data;
}

// --- Research report search + download ---
import type {
  ResearchReport,
  SearchReport,
  DownloadRequestItem,
  DownloadResult,
  ParseResponse,
  ParseStatusResponse,
  HistoryResponse,
  AnalysisRecord,
  CompanyType,
  BucketId,
  BucketResult,
  AnalysisDoc,
} from '../types/deepAnalysis';
export type {
  ResearchReport,
  SearchReport,
  DownloadRequestItem,
  DownloadResult,
  ParseResponse,
  ParseStatusResponse,
  HistoryResponse,
  AnalysisRecord,
  CompanyType,
  BucketId,
  BucketResult,
  AnalysisDoc,
};

/** 按股票代码搜索研报（东财） */
export async function searchReportsByCode(code: string): Promise<{ reports: ResearchReport[] }> {
  const { data } = await api.get('/api/research/reports', { params: { code } });
  return data;
}

/** 按关键词搜索研报（iwencai） */
export async function searchReportsByKeyword(keyword: string): Promise<{ reports: SearchReport[] }> {
  const { data } = await api.get('/api/research/search', { params: { keyword } });
  return data;
}

/** 批量下载研报 PDF → OSS */
export async function downloadReports(
  code: string,
  reports: DownloadRequestItem[],
): Promise<{ results: DownloadResult[] }> {
  const { data } = await api.post('/api/research/download', { code, reports });
  return data;
}

// --- Deep analysis pipeline ---

/** 提交 PDF 给 MinerU 解析 */
export async function parseReports(code: string, ossKeys: string[]): Promise<ParseResponse> {
  const { data } = await api.post<ParseResponse>('/api/deep-analysis/parse', {
    code,
    oss_keys: ossKeys,
  });
  return data;
}

/** 轮询解析进度 */
export async function getParseStatus(code: string): Promise<ParseStatusResponse> {
  const { data } = await api.get<ParseStatusResponse>('/api/deep-analysis/parse-status', {
    params: { code },
  });
  return data;
}

/** SSE 流式分析的回调接口(v2 结构化版本) */
export interface AnalyzeStreamCallbacks {
  onStart?: (payload: { version: 'v2'; company_type: CompanyType; buckets: BucketId[] }) => void;
  onBucketStart?: (bucketId: BucketId) => void;
  onBucketDone?: (bucketId: BucketId, result: BucketResult) => void;
  onBucketError?: (bucketId: BucketId, error: string) => void;
  onCached?: (doc: AnalysisDoc) => void;
  onDone?: (info: { version: 'v2'; analysis_id: number; ok_count: number; error_count: number; total: number }) => void;
  onError?: (err: string) => void;
}

export async function streamAnalyze(
  code: string,
  ossKeys: string[],
  companyType: CompanyType,
  callbacks: AnalyzeStreamCallbacks,
  options: { forceRefresh?: boolean } = {},
): Promise<void> {
  const isDev = import.meta.env.DEV;
  const base = isDev ? 'http://localhost:8000' : '';
  const params = new URLSearchParams({
    code,
    oss_keys: ossKeys.join(','),
    company_type: companyType,
  });
  if (options.forceRefresh) params.append('force_refresh', 'true');

  // Native fetch() bypasses the axios interceptors above, so we
  // replicate the admin-token injection here. On 401, mirror the
  // response interceptor's behavior so the modal reopens.
  const adminToken = readAdminToken();
  const resp = await fetch(
    `${base}/api/deep-analysis/analyze?${params.toString()}`,
    {
      headers: {
        Accept: 'text/event-stream',
        ...(adminToken ? { 'X-Admin-Token': adminToken } : {}),
      },
    },
  );
  if (!resp.ok || !resp.body) {
    if (resp.status === 401) {
      notifyAdminUnauthorized();
    }
    throw new Error(`HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let currentEvent = 'message';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.trim()) {
        currentEvent = 'message';
        continue;
      }
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const payload = line.slice(5).trim();
        try {
          const parsed = JSON.parse(payload);
          switch (currentEvent) {
            case 'start':         callbacks.onStart?.(parsed); break;
            case 'bucket_start':  callbacks.onBucketStart?.(parsed.bucket_id); break;
            case 'bucket_done':   callbacks.onBucketDone?.(parsed.bucket_id, parsed.result); break;
            case 'bucket_error':  callbacks.onBucketError?.(parsed.bucket_id, parsed.error); break;
            case 'cached':        callbacks.onCached?.(parsed); break;
            case 'done':          callbacks.onDone?.(parsed); break;
            case 'error':         callbacks.onError?.(parsed.error || parsed.reason || 'unknown'); break;
          }
        } catch {
          // 忽略解析失败的非 JSON 数据行
        }
        currentEvent = 'message';
      }
    }
  }
}

/** 历史分析列表 */
export async function getAnalysisHistory(code: string): Promise<HistoryResponse> {
  const { data } = await api.get<HistoryResponse>('/api/deep-analysis/history', {
    params: { code },
  });
  return data;
}

/** 按 id 拉取单条历史分析 */
export async function getAnalysisRecord(id: number): Promise<AnalysisRecord> {
  const { data } = await api.get<AnalysisRecord>(`/api/deep-analysis/records/${id}`);
  return data;
}

/**
 * 按 code 取最新一条 v2 结构化分析(ChainKb tab 03「公司拆解」用)。
 * 该股票没有任何 v2 分析时返回 null(404 视为正常路径,吞掉)。
 * 其他错误(500/网络)照样抛。
 */
export async function getLatestAnalysis(code: string): Promise<AnalysisDoc | null> {
  try {
    const { data } = await api.get<AnalysisDoc>('/api/deep-analysis/latest', {
      params: { code },
    });
    return data;
  } catch (err: unknown) {
    if (err instanceof axios.AxiosError && err.response?.status === 404) return null;
    throw err;
  }
}
