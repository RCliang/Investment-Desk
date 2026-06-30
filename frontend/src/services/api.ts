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
