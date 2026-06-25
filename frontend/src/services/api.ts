import axios from 'axios';

const api = axios.create({ baseURL: 'http://localhost:8000' });

// --- Chain ---
export async function analyzeChain(industry: string) {
  const { data } = await api.post('/api/chain/analyze', { industry });
  return data;
}

export async function getChainHistory() {
  const { data } = await api.get('/api/chain/history');
  return data;
}

// --- Data ---
export async function queryData(source: string, action: string, params: Record<string, unknown> = {}) {
  const { data } = await api.post('/api/data/query', { source, action, params });
  return data;
}

export async function getStockQuote(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}`);
  return data;
}

export async function getStockHist(code: string, period = 'daily') {
  const { data } = await api.get(`/api/data/stock/${code}/hist`, { params: { period } });
  return data;
}

export async function getStockFinancial(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/financial`);
  return data;
}

export async function getStockReports(code: string, page = 1) {
  const { data } = await api.get(`/api/data/stock/${code}/reports`, { params: { page } });
  return data;
}

export async function getStockBlocks(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/blocks`);
  return data;
}

export async function getStockFundFlow(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/fund-flow`);
  return data;
}

// --- Report ---
export async function generateReport(industry: string, onChunk: (text: string) => void) {
  const resp = await fetch(`http://localhost:8000/api/report/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ industry }),
  });
  const reader = resp.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        onChunk(line.slice(6));
      }
    }
  }
}

export async function listReports() {
  const { data } = await api.get('/api/report/list');
  return data;
}

export async function getReport(id: number) {
  const { data } = await api.get(`/api/report/${id}`);
  return data;
}

// --- Plan ---
export async function createPlan(plan: {
  stock_code: string; stock_name: string; direction: string;
  position_ratio: number; target_price?: number; stop_loss_price?: number; reason?: string;
}) {
  const { data } = await api.post('/api/plan/create', plan);
  return data;
}

export async function listPlans() {
  const { data } = await api.get('/api/plan/list');
  return data;
}

export async function updatePlan(id: number, updates: Record<string, unknown>) {
  const { data } = await api.put(`/api/plan/${id}`, updates);
  return data;
}

export async function deletePlan(id: number) {
  const { data } = await api.delete(`/api/plan/${id}`);
  return data;
}

// --- Chain Knowledge Base (v1) ---
// Types are re-exported from ../types/chainkb for consumer convenience.
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
    `/api/chainkb/companies/${ticker}/timeseries`, { params },
  );
  return data;
}

export async function searchChainKb(q: string, limit = 20): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/api/chainkb/search', {
    params: { q, limit },
  });
  return data;
}

