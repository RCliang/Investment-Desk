import { useCallback, useEffect, useState } from 'react';
import {
  getChainKbTree,
  getChainKbSubIndustry,
  getChainKbCompany,
  getChainKbTimeseries,
  searchChainKb,
  getFreshness,
} from '../../services/api';
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
  FreshnessResponse,
} from '../../types/chainkb';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const initial = <T,>(): FetchState<T> => ({ data: null, loading: false, error: null });

/**
 * Fetch the full tree (5 layers × ~48 sub-industries + company counts).
 * Fires once on mount.
 */
export function useTree() {
  const [state, setState] = useState<FetchState<TreeResponse>>(initial());
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getChainKbTree()
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch(
        (err: unknown) =>
          !cancelled &&
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}

/**
 * Fetch a single sub-industry detail (companies + market snapshots).
 * Refetches when `groupId` changes; pass null to skip.
 */
export function useSubIndustry(groupId: string | null) {
  const [state, setState] = useState<FetchState<SubIndustryDetail>>(initial());
  useEffect(() => {
    if (!groupId) {
      setState(initial());
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getChainKbSubIndustry(groupId)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch(
        (err: unknown) =>
          !cancelled &&
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [groupId]);
  return state;
}

/**
 * Fetch a single company profile (quote + finance + concepts + sub_industries).
 * Refetches when `ticker` changes; pass null to skip.
 */
export function useCompany(ticker: string | null) {
  const [state, setState] = useState<FetchState<CompanyProfile>>(initial());
  useEffect(() => {
    if (!ticker) {
      setState(initial());
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getChainKbCompany(ticker)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch(
        (err: unknown) =>
          !cancelled &&
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [ticker]);
  return state;
}

/**
 * Fetch aggregated time-series (lockup / holders / margin / reports).
 * Refetches when `ticker` changes; `limit` defaults to 30 rows per type.
 */
export function useTimeseries(ticker: string | null, limit = 30) {
  const [state, setState] = useState<FetchState<TimeSeriesResponse>>(initial());
  useEffect(() => {
    if (!ticker) {
      setState(initial());
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getChainKbTimeseries(ticker, { limit })
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch(
        (err: unknown) =>
          !cancelled &&
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [ticker, limit]);
  return state;
}

/**
 * Debounced search hook. Fires when `q` (trimmed, length >= 1) settles for
 * `delay` ms. Empty query clears results immediately.
 */
export function useSearch(q: string, limit = 20, delay = 280) {
  const [state, setState] = useState<FetchState<SearchResponse>>(initial());

  const fire = useCallback(
    (term: string) => {
      let cancelled = false;
      setState({ data: null, loading: true, error: null });
      searchChainKb(term, limit)
        .then((data) => !cancelled && setState({ data, loading: false, error: null }))
        .catch(
          (err: unknown) =>
            !cancelled &&
            setState({
              data: null,
              loading: false,
              error: err instanceof Error ? err.message : String(err),
            }),
        );
      return () => {
        cancelled = true;
      };
    },
    [limit],
  );

  useEffect(() => {
    const trimmed = q.trim();
    if (!trimmed) {
      setState(initial());
      return;
    }
    const handle = window.setTimeout(() => {
      fire(trimmed);
    }, delay);
    return () => window.clearTimeout(handle);
  }, [q, delay, fire]);

  return state;
}

// ── Freshness: polls /api/chainkb/freshness every 60s ───────────────────────
export function useFreshness() {
  const [data, setData] = useState<FreshnessResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const f = await getFreshness();
        if (!cancelled) setData(f);
      } catch {
        // silent — backend may be down; UI shows last known state
      }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);
  return data;
}
