import { useEffect, useState } from 'react';
import {
  getBoardsOverview,
  getBoardsHeatmap,
  getBoardDetail,
  getThemeTrends,
} from '../../services/api';
import type {
  BoardsOverviewResponse,
  BoardsHeatmapResponse,
  BoardDetailResponse,
  ThemeTrendsResponse,
} from '../../types/boards';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}
const initial = <T,>(): FetchState<T> => ({ data: null, loading: false, error: null });

/** Leaderboard + theme trends, refetching when the window or refresh key
 * changes (refresh key bumps after a manual POST /boards/refresh). */
export function useBoardsOverview(days: number, refreshKey: number) {
  const [state, setState] = useState<FetchState<BoardsOverviewResponse>>(initial());
  const [themes, setThemes] = useState<FetchState<ThemeTrendsResponse>>(initial());
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getBoardsOverview(days)
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    getThemeTrends(20)
      .then((d) => !cancelled && setThemes({ data: d, loading: false, error: null }))
      .catch(() => !cancelled && setThemes({ data: null, loading: false, error: null }));
    return () => { cancelled = true; };
  }, [days, refreshKey]);
  return { ...state, themes };
}

/** Heat matrix, refetching when the column window changes. */
export function useBoardsHeatmap(days: number, refreshKey: number) {
  const [state, setState] = useState<FetchState<BoardsHeatmapResponse>>(initial());
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getBoardsHeatmap(days)
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    return () => { cancelled = true; };
  }, [days, refreshKey]);
  return state;
}

/** Drill-down detail for one board (null bkCode = idle). */
export function useBoardDetail(bkCode: string | null, days = 100) {
  const [state, setState] = useState<FetchState<BoardDetailResponse>>(initial());
  useEffect(() => {
    if (!bkCode) {
      setState(initial());
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getBoardDetail(bkCode, days)
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    return () => { cancelled = true; };
  }, [bkCode, days]);
  return state;
}
