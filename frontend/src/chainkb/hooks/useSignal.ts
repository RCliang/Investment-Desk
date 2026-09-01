import { useCallback, useEffect, useState } from 'react';
import {
  getStrategies,
  getSignals,
  getSignalDetail,
  getBacktest,
  runBacktest,
  triggerScan,
  type SignalFilter,
} from '../../services/api';
import type {
  StrategiesResponse,
  SignalListResponse,
  SignalDetailResponse,
  BacktestDetail,
  BacktestSummary,
  ScanResult,
} from '../../types/signal';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}
const initial = <T,>(): FetchState<T> => ({ data: null, loading: false, error: null });

/** One-shot fetch of the strategy catalog. */
export function useStrategies() {
  const [state, setState] = useState<FetchState<StrategiesResponse>>(initial());
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getStrategies()
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    return () => { cancelled = true; };
  }, []);
  return state;
}

/** Filtered signal list. Refetches whenever the filter object reference
 * changes, or when `refreshKey` is bumped (e.g. after a manual rescan). */
export function useSignals(filter: SignalFilter, refreshKey?: number) {
  const [state, setState] = useState<FetchState<SignalListResponse>>(initial());
  // Stable string key so identical filter values don't refetch.
  const key = JSON.stringify([filter, refreshKey]);
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getSignals(filter)
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

/** Detail for one ticker (null skip when ticker is null). Refetches when
 * the strategy set changes so the drawer matches the list the user sees. */
export function useSignalDetail(ticker: string | null, strategySet?: string) {
  const [state, setState] = useState<FetchState<SignalDetailResponse>>(initial());
  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getSignalDetail(ticker, strategySet)
      .then((d) => !cancelled && setState({ data: d, loading: false, error: null }))
      .catch((e: unknown) => !cancelled && setState({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    return () => { cancelled = true; };
  }, [ticker, strategySet]);
  return state;
}

/** Imperative actions (not hooks) — used by button handlers. */
export function useQuantActions() {
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const scan = useCallback(async (strategySet?: string): Promise<ScanResult | null> => {
    setScanning(true);
    setScanError(null);
    try {
      const r = await triggerScan(strategySet);
      return r;
    } catch (e: unknown) {
      setScanError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setScanning(false);
    }
  }, []);

  const backtest = useCallback(async (
    ticker: string,
    opts?: { startDate?: string; endDate?: string; strategySet?: string },
  ): Promise<BacktestSummary | null> => {
    setBacktesting(true);
    setBacktestError(null);
    try {
      const r = await runBacktest({
        ticker,
        start_date: opts?.startDate,
        end_date: opts?.endDate,
        strategy_set: opts?.strategySet,
      });
      return r;
    } catch (e: unknown) {
      setBacktestError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBacktesting(false);
    }
  }, []);

  const fetchBacktest = useCallback(async (runId: number): Promise<BacktestDetail | null> => {
    return getBacktest(runId);
  }, []);

  return { scan, scanning, scanError, backtest, backtesting, backtestError, fetchBacktest };
}
