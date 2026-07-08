import { useEffect, useRef, useState } from 'react';
import {
  getTree,
  getSubIndustry,
  getCompany,
  getTimeseries,
  search,
  getFreshness,
} from '../services/chainkb';
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
  FreshnessResponse,
} from '../types/chainkb';

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const initialState: FetchState<unknown> = {
  data: null,
  loading: true,
  error: null,
};

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/** 一次性拉取全树 */
export function useTree(): FetchState<TreeResponse> {
  const [state, setState] = useState<FetchState<TreeResponse>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getTree()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) });
      });
    return () => { cancelled = true; };
  }, []);

  return state;
}

/** 按 groupId 拉子行业; groupId 为 null 时不发请求 */
export function useSubIndustry(groupId: string | null): FetchState<SubIndustryDetail> {
  const [state, setState] = useState<FetchState<SubIndustryDetail>>(initialState as FetchState<SubIndustryDetail>);

  useEffect(() => {
    if (!groupId) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getSubIndustry(groupId)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [groupId]);

  return state;
}

/** 按 ticker 拉公司 profile */
export function useCompany(ticker: string | null): FetchState<CompanyProfile> {
  const [state, setState] = useState<FetchState<CompanyProfile>>(initialState as FetchState<CompanyProfile>);

  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getCompany(ticker)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [ticker]);

  return state;
}

/** 按 ticker 拉时序数据 (默认 4 类一次返回, limit=30) */
export function useTimeseries(ticker: string | null, limit = 30): FetchState<TimeSeriesResponse> {
  const [state, setState] = useState<FetchState<TimeSeriesResponse>>(initialState as FetchState<TimeSeriesResponse>);

  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getTimeseries(ticker, { limit })
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [ticker, limit]);

  return state;
}

/** 防抖搜索; 空字符串不发请求, 立即清空 */
export function useSearch(q: string, limit = 20, delay = 280): FetchState<SearchResponse> {
  const [state, setState] = useState<FetchState<SearchResponse>>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (!q) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setState({ data: null, loading: true, error: null });
      search(q, limit)
        .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
        .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    }, delay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q, limit, delay]);

  return state;
}

/** 60s 轮询 freshness; 失败时保留上次数据 */
export function useFreshness(): FreshnessResponse | null {
  const [data, setData] = useState<FreshnessResponse | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getFreshness()
        .then((d) => { if (!cancelled) setData(d); })
        .catch(() => { /* 静默, 保留上次数据 */ });
    };
    tick(); // 立即跑一次
    timerRef.current = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return data;
}
