import { request } from './request';
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
  FreshnessResponse,
} from '../types/chainkb';
import type { AnalysisDoc } from '../types/deepAnalysis';

export function getTree(): Promise<TreeResponse> {
  return request<TreeResponse>('/api/chainkb/tree');
}

export function getSubIndustry(groupId: string): Promise<SubIndustryDetail> {
  return request<SubIndustryDetail>(`/api/chainkb/sub_industries/${encodeURIComponent(groupId)}`);
}

export function getCompany(ticker: string): Promise<CompanyProfile> {
  return request<CompanyProfile>(`/api/chainkb/companies/${encodeURIComponent(ticker)}`);
}

export function getTimeseries(
  ticker: string,
  opts: { types?: string[]; limit?: number } = {},
): Promise<TimeSeriesResponse> {
  return request<TimeSeriesResponse>(
    `/api/chainkb/companies/${encodeURIComponent(ticker)}/timeseries`,
    {
      query: {
        types: opts.types?.join(','),
        limit: opts.limit,
      },
    },
  );
}

export function search(q: string, limit = 20): Promise<SearchResponse> {
  return request<SearchResponse>('/api/chainkb/search', { query: { q, limit } });
}

export function getFreshness(): Promise<FreshnessResponse> {
  return request<FreshnessResponse>('/api/chainkb/freshness');
}

/**
 * 获取最新 v2 结构化分析。
 * 后端无分析时返回 404, 本函数捕获后返回 null (与前端 api.ts 行为对齐)。
 */
export async function getLatestAnalysis(code: string): Promise<AnalysisDoc | null> {
  try {
    return await request<AnalysisDoc>('/api/deep-analysis/latest', { query: { code } });
  } catch (err) {
    if (err instanceof Error && 'statusCode' in err && (err as { statusCode: number }).statusCode === 404) {
      return null;
    }
    throw err;
  }
}
