import axios from 'axios';

// 生产环境使用相对路径（通过nginx代理），开发环境使用localhost:8000
const isDev = import.meta.env.DEV;
const api = axios.create({
  baseURL: isDev ? 'http://localhost:8000' : '/api'
});

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
  const { data } = await api.get<TreeResponse>('/chainkb/tree');
  return data;
}

export async function getChainKbSubIndustry(groupId: string): Promise<SubIndustryDetail> {
  const { data } = await api.get<SubIndustryDetail>(`/chainkb/sub_industries/${groupId}`);
  return data;
}

export async function getChainKbCompany(ticker: string): Promise<CompanyProfile> {
  const { data } = await api.get<CompanyProfile>(`/chainkb/companies/${ticker}`);
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
    `/chainkb/companies/${ticker}/timeseries`,
    { params },
  );
  return data;
}

export async function searchChainKb(q: string, limit = 20): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/chainkb/search', {
    params: { q, limit },
  });
  return data;
}

// --- Freshness (data update timestamps) ---
import type { FreshnessResponse } from '../types/chainkb';

export async function getFreshness(): Promise<FreshnessResponse> {
  const { data } = await api.get<FreshnessResponse>('/chainkb/freshness');
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

/** SSE 流式分析的回调接口 */
export interface AnalyzeStreamCallbacks {
  onChunk: (content: string) => void;
  onCached?: (payload: { analysis_text: string; created_at: string; model_name: string }) => void;
  onDone?: (info: { cache_hit: boolean; length?: number }) => void;
  onError?: (err: string) => void;
}

/**
 * SSE 流式调用 AI 分析。
 * 用 fetch + ReadableStream（非 EventSource）以便传 query params 且 GET。
 *
 * dev 环境需绕过 axios baseURL，直接走 vite proxy 的 /api 前缀。
 */
export async function streamAnalyze(
  code: string,
  ossKeys: string[],
  callbacks: AnalyzeStreamCallbacks,
  options: { forceRefresh?: boolean } = {},
): Promise<void> {
  const isDev = import.meta.env.DEV;
  const base = isDev ? 'http://localhost:8000' : '';
  const params = new URLSearchParams({
    code,
    oss_keys: ossKeys.join(','),
  });
  if (options.forceRefresh) params.append('force_refresh', 'true');

  const resp = await fetch(
    `${base}/api/deep-analysis/analyze?${params.toString()}`,
    { headers: { Accept: 'text/event-stream' } },
  );
  if (!resp.ok || !resp.body) {
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
          if (currentEvent === 'chunk') callbacks.onChunk(parsed.content || '');
          else if (currentEvent === 'cached' && callbacks.onCached) callbacks.onCached(parsed);
          else if (currentEvent === 'done' && callbacks.onDone) callbacks.onDone(parsed);
          else if (currentEvent === 'error' && callbacks.onError) callbacks.onError(parsed.error || 'unknown');
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
