/**
 * ETF 动量轮动策略面板 (混合池双动量 · 网格TOP1方案).
 *
 * 运行配置 = 2026-09 网格搜索 TOP1（top2 · 月度调仓 · 3/6/12月窗口
 * lw0.7 · 快速波动率20日 · 目标波动12% · ATR 4×），后端扫描/回测默认值
 * 与本面板一致，详见 docs/etf-rotation-grid-search-plan.md。
 *
 * Layout:
 *   1. Momentum ranking — whole pool with blended/vol-adjusted momentum,
 *      per-window returns, absolute-momentum gate flag and target weight.
 *   2. Target portfolio — Top-N risk ETFs + cash parking, ATR stop refs.
 *   3. Backtest — runs the TOP1 defaults; toggles expose the ablation
 *      axes (A1 gate-off, market timing, rebalance mode, weighting).
 */
import { useCallback, useEffect, useState } from 'react';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import {
  getEtfScores,
  getEtfPortfolio,
  runEtfBacktest,
  getBacktest,
} from '../services/api';
import type {
  EtfScoresResponse,
  EtfPortfolioResponse,
  EtfBacktestSummary,
} from '../types/etf-rotation';
import type { BacktestDetail } from '../types/signal';

const CLASS_COLOR: Record<string, string> = {
  宽基: '#3a6a8a',
  行业: 'var(--marker-green)',
  防守: '#8a7a3a',
  货币: 'var(--pencil)',
};

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`;
}

/** The grid-search TOP1 scheme this panel runs on (backend defaults). */
const TOP1 = {
  badge: '方案 · 网格TOP1 + 防守补位',
  params: 'top2 · 月度调仓 · 窗口(60,120,250)×(0.15,0.15,0.70) · 波动率窗20日 · 绝对动量180日 · 缓冲带3 · 目标波动12% · ATR止损4×ATR14 · 破位缓冲3% · 退出后防守类当日补位(国债/黄金/红利)',
  ref: '网格回测参考（2021-09→2026-09，含成本，多相位平均）：总收益 ~62% · 回撤 ~12% · 夏普 ~1.13 · 验证期夏普 ~1.77',
};

function CurveChart({ strategy, benchmark }: {
  strategy: { date: string; equity: number }[];
  benchmark: { date: string; equity: number }[];
}) {
  const W = 640, H = 220, pad = 12;
  const all = [...strategy.map((p) => p.equity), ...benchmark.map((p) => p.equity)];
  let min = Math.min(...all), max = Math.max(...all);
  const yPad = (max - min) * 0.06 || 1;
  min -= yPad; max += yPad;
  const range = max - min || 1;
  const toPath = (curve: { equity: number }[]) => curve
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${(pad + (i / (curve.length - 1)) * (W - pad * 2)).toFixed(1)},`
      + `${(H - pad - ((p.equity - min) / range) * (H - pad * 2)).toFixed(1)}`)
    .join(' ');
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      <path d={toPath(benchmark)} fill="none" stroke="var(--pencil)" strokeWidth={1.4}
        strokeDasharray="5 4" />
      <path d={toPath(strategy)} fill="none" stroke="var(--marker-red)" strokeWidth={2} />
    </svg>
  );
}

interface FetchState<T> { data: T | null; loading: boolean; error: string | null }
const initial = <T,>(): FetchState<T> => ({ data: null, loading: false, error: null });

export default function EtfRotationPanel() {
  const [scores, setScores] = useState<FetchState<EtfScoresResponse>>(initial());
  const [portfolio, setPortfolio] = useState<FetchState<EtfPortfolioResponse>>(initial());

  const [btSummary, setBtSummary] = useState<EtfBacktestSummary | null>(null);
  const [btDetail, setBtDetail] = useState<BacktestDetail | null>(null);
  const [btRunning, setBtRunning] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);
  const [useAbsGate, setUseAbsGate] = useState(true);
  const [useMarketGate, setUseMarketGate] = useState(false);
  const [rebalanceMode, setRebalanceMode] = useState<'fixed' | 'dynamic'>('fixed');
  const [weightMode, setWeightMode] = useState<'equal' | 'risk_parity'>('equal');
  const [useTargetVol, setUseTargetVol] = useState(true);
  const [exitReplacement, setExitReplacement] = useState(true);

  const loadAll = useCallback(() => {
    setScores((s) => ({ ...s, loading: true }));
    getEtfScores()
      .then((d) => setScores({ data: d, loading: false, error: null }))
      .catch((e: unknown) => setScores({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e) }));
    getEtfPortfolio()
      .then((d) => setPortfolio({ data: d, loading: false, error: null }))
      .catch(() => setPortfolio({ data: null, loading: false, error: null }));
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const runBacktestNow = useCallback(async () => {
    setBtRunning(true); setBtError(null);
    try {
      const summary = await runEtfBacktest({
        use_abs_gate: useAbsGate,
        use_market_gate: useMarketGate,
        rebalance_mode: rebalanceMode,
        weight_mode: weightMode,
        use_target_vol: useTargetVol,
        exit_replacement: exitReplacement,
      });
      setBtSummary(summary);
      const detail = await getBacktest(summary.run_id);
      setBtDetail(detail);
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : String(e));
    } finally {
      setBtRunning(false);
    }
  }, [useAbsGate, useMarketGate, rebalanceMode, weightMode, useTargetVol, exitReplacement]);

  const emptyHint = !scores.loading && !scores.data?.etfs?.length;
  const ranked = scores.data?.etfs?.filter((e) => e.momentum_rank != null) ?? [];
  const cashRow = scores.data?.etfs?.find((e) => e.asset_class === '货币');
  const maxScore = Math.max(...ranked.map((e) => Math.abs(e.momentum_score ?? 0)), 1e-9);

  const benchmarkCurve = (() => {
    const params = btDetail?.params as
      { benchmark_curve?: { date: string; equity: number }[] } | undefined;
    return params?.benchmark_curve ?? [];
  })();

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {/* 0. Active scheme banner (grid-search TOP1) */}
      <div style={{
        display: 'grid', gap: 2, fontSize: 12, color: 'var(--pencil)',
        border: '1.5px solid var(--marker-red)', borderRadius: 6,
        padding: '8px 12px',
      }}>
        <div>
          <span style={{ color: 'var(--marker-red)', fontWeight: 600 }}>
            ★ {TOP1.badge}
          </span>
          <span style={{ marginLeft: 10 }}>{TOP1.params}</span>
        </div>
        <div>{TOP1.ref}</div>
      </div>

      {/* 1. Momentum ranking */}
      <SketchPanel title="动量排名" mono={`DUAL MOMENTUM · ${scores.data?.date ?? '—'}`}>
        {scores.error && <div style={{ color: 'var(--marker-red)' }}>{scores.error}</div>}
        {emptyHint && (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>
            暂无 ETF 信号 — 等待每日 17:50 扫描，或先运行数据回填（refresh 类型 etf_klines）。
          </div>
        )}
        {ranked.length > 0 && (
          <table className="table-sketch">
            <thead>
              <tr>
                <th>#</th><th>代码</th><th>名称</th><th>类别</th>
                <th>R60</th><th>R120</th><th>R250</th><th>得分</th>
                <th>绝对动量</th><th>权重</th><th>止损参考</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((e) => (
                <tr key={e.ticker} className={e.is_selected ? 'row-clickable' : ''}>
                  <td className="num">{e.momentum_rank}</td>
                  <td className="num-left">{e.ticker}</td>
                  <td>{e.name}</td>
                  <td>
                    <span style={{
                      color: CLASS_COLOR[e.asset_class] ?? 'var(--ink)',
                      fontSize: 11,
                    }}>
                      {e.asset_class}
                    </span>
                  </td>
                  <td className="num" style={{
                    color: (e.detail.r60 ?? 0) >= 0 ? 'var(--marker-green)' : 'var(--marker-red)',
                  }}>{pct(e.detail.r60)}</td>
                  <td className="num" style={{
                    color: (e.detail.r120 ?? 0) >= 0 ? 'var(--marker-green)' : 'var(--marker-red)',
                  }}>{pct(e.detail.r120)}</td>
                  <td className="num" style={{
                    color: (e.detail.r250 ?? 0) >= 0 ? 'var(--marker-green)' : 'var(--marker-red)',
                  }}>{pct(e.detail.r250)}</td>
                  <td className="num">
                    <span title={`复合动量 ${e.momentum_raw?.toFixed(3)}`}>
                      {e.momentum_score?.toFixed(2)}
                    </span>
                    <div className="detail-track" style={{ display: 'inline-flex', marginLeft: 6 }}>
                      <div style={{
                        width: `${Math.abs(e.momentum_score ?? 0) / maxScore * 60}px`,
                        background: (e.momentum_score ?? 0) >= 0
                          ? 'var(--marker-green)' : 'var(--marker-red)',
                        height: 8, borderRadius: 3, opacity: 0.7,
                      }} />
                    </div>
                  </td>
                  <td style={{ color: e.abs_momentum_pass ? 'var(--marker-green)' : 'var(--marker-red)' }}>
                    {e.abs_momentum_pass ? '✓ 过闸' : '✗ 弱于现金'}
                  </td>
                  <td className="num">{e.weight > 0 ? `${(e.weight * 100).toFixed(0)}%` : ''}</td>
                  <td className="num">{e.stop_price?.toFixed(3) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cashRow && cashRow.weight > 0 && (
          <div style={{ fontSize: 12, marginTop: 8, color: 'var(--pencil)' }}>
            空仓停泊：{cashRow.name}（{cashRow.ticker}）{(cashRow.weight * 100).toFixed(0)}%
            —— 绝对动量未过闸的槽位以货币 ETF 持有。
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--pencil)', marginTop: 6 }}>
          得分 = (0.15×R60 + 0.15×R120 + 0.70×R250) ÷ 年化波动率（20日窗，后复权价）·
          绝对动量 = R180 ≥ 货币ETF 同期 · 月度调仓 + 排名缓冲带（持仓保留至前 5 名）·
          目标波动率 12% 超限时降仓停泊货币ETF
        </div>
      </SketchPanel>

      {/* 2. Target portfolio */}
      <SketchPanel title="目标持仓" mono={`PORTFOLIO · ${portfolio.data?.date ?? '—'}`}>
        {portfolio.data?.holdings?.length ? (
          <table className="table-sketch">
            <thead>
              <tr><th>代码</th><th>名称</th><th>类别</th><th>权重</th><th>动量排名</th><th>止损参考</th></tr>
            </thead>
            <tbody>
              {portfolio.data.holdings.map((h) => (
                <tr key={h.ticker}>
                  <td className="num-left">{h.ticker}</td>
                  <td>{h.name}</td>
                  <td style={{ color: CLASS_COLOR[h.asset_class] ?? 'var(--ink)' }}>
                    {h.asset_class}
                  </td>
                  <td className="num">{(h.weight * 100).toFixed(1)}%</td>
                  <td className="num">{h.momentum_rank ?? '现金'}</td>
                  <td className="num">{h.stop_price?.toFixed(3) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>暂无推荐持仓。</div>
        )}
        <div style={{ fontSize: 11, color: 'var(--pencil)', marginTop: 6 }}>
          Top-2 每槽 1/2（未过闸槽位与波动超限释放的份额停泊货币ETF）·
          持有期每日检查 ATR 灾难止损（4×ATR14）与 MA20 破位（3% 缓冲带）。
        </div>
      </SketchPanel>

      {/* 3. Backtest */}
      <SketchPanel title="策略回测" mono="BACKTEST">
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={useAbsGate}
                   onChange={(e) => setUseAbsGate(e.target.checked)} />
            绝对动量门控（关闭 = 纯相对动量消融 A1）
          </label>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={useMarketGate}
                   onChange={(e) => setUseMarketGate(e.target.checked)} />
            大盘 MA200 择时（510300 跌破均线时屏蔽宽基+行业，防守类可继续持有）
          </label>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            调仓模式
            <select value={rebalanceMode}
                    onChange={(e) => setRebalanceMode(e.target.value as 'fixed' | 'dynamic')}>
              <option value="fixed">固定周期（默认每月）</option>
              <option value="dynamic">动态调仓（每日检查、变化才交易）</option>
            </select>
          </label>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            加权方式
            <select value={weightMode}
                    onChange={(e) => setWeightMode(e.target.value as 'equal' | 'risk_parity')}>
              <option value="equal">等权（每槽 1/N）</option>
              <option value="risk_parity">风险平价（逆波动率）</option>
            </select>
          </label>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={useTargetVol}
                   onChange={(e) => setUseTargetVol(e.target.checked)} />
            目标波动率 12%（组合波动超阈值时降仓，释放份额停货币ETF）
          </label>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={exitReplacement}
                   onChange={(e) => setExitReplacement(e.target.checked)} />
            退出后防守类当日补位（国债/黄金/红利择优，关闭 = 持币等月度调仓）
          </label>
          <button className="btn" onClick={runBacktestNow} disabled={btRunning}>
            {btRunning ? '回测中…' : '运行回测（TOP1 默认参数）'}
          </button>
          {btError && <span style={{ color: 'var(--marker-red)' }}>{btError}</span>}
        </div>

        {btSummary && (
          <>
            <div className="kpi-row" style={{ marginTop: 12 }}>
              <SketchKpi label="总收益" value={`${btSummary.total_return_pct.toFixed(1)}%`}
                delta={`基准 ${btSummary.benchmark_total_return_pct.toFixed(1)}%`}
                deltaTone={btSummary.excess_return_pct >= 0 ? 'up' : 'down'} />
              <SketchKpi label="超额" value={`${btSummary.excess_return_pct.toFixed(1)}%`}
                deltaTone={btSummary.excess_return_pct >= 0 ? 'up' : 'down'}
                delta={btSummary.excess_return_pct >= 0 ? '跑赢同池等权' : '跑输同池等权'} />
              <SketchKpi label="夏普" value={btSummary.sharpe_ratio.toFixed(2)} />
              <SketchKpi label="最大回撤" value={`${btSummary.max_drawdown_pct.toFixed(1)}%`}
                deltaTone="down" />
              <SketchKpi label="调仓次数" value={btSummary.rebalance_count}
                delta={`换手 ${btSummary.avg_turnover_pct.toFixed(1)}%`} />
              <SketchKpi label="胜率" value={`${btSummary.win_rate_pct.toFixed(0)}%`}
                delta={`${btSummary.trade_count} 笔`} />
            </div>

            {btDetail && benchmarkCurve.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <CurveChart strategy={btDetail.equity_curve} benchmark={benchmarkCurve} />
                <div style={{ fontSize: 11, color: 'var(--pencil)' }}>
                  红线 = 双动量策略 · 虚线 = 同池等权基准（含防守资产，无成本）·
                  区间 {btSummary.start_date} → {btSummary.end_date}
                </div>
              </div>
            )}

            {Object.keys(btSummary.sector_pnl).length > 0 && (
              <div style={{ marginTop: 12, fontSize: 12 }}>
                <strong>分类盈亏（元）：</strong>
                {Object.entries(btSummary.sector_pnl).map(([cls, pnl]) => (
                  <span key={cls} style={{
                    marginRight: 12,
                    color: pnl >= 0 ? 'var(--marker-green)' : 'var(--marker-red)',
                  }}>
                    {cls} {pnl >= 0 ? '+' : ''}{(pnl / 1e4).toFixed(1)}万
                  </span>
                ))}
              </div>
            )}
          </>
        )}
      </SketchPanel>
    </div>
  );
}
