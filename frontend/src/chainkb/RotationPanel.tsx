/**
 * 板块轮动策略面板 (sector-rotation mid-term trend strategy).
 *
 * Layout:
 *   1. Sector strength — 8 sectors, dual-dim (主力/技术) stacked bars;
 *      Top-K sectors flagged for today's rotation portfolio.
 *   2. Strength evolution — last ~30 days heatmap (sector × date).
 *   3. Recommended holdings — Top-K sectors × Top-N stocks with factor
 *      scores, entry confirmation, divergence warning, stop levels.
 *   4. In-sector rankings — full pool ranking, grouped by sector.
 *   5. Backtest — run (with/without fund-flow factors), strategy vs
 *      pool equal-weight benchmark curves, sector PnL, factor IC table.
 */
import { useCallback, useEffect, useState } from 'react';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import {
  getRotationSectors,
  getRotationSectorHistory,
  getRotationPortfolio,
  getRotationRankings,
  runRotationBacktest,
  getBacktest,
} from '../services/api';
import type {
  SectorScoresResponse,
  SectorHistoryResponse,
  RotationPortfolioResponse,
  RotationRankingsResponse,
  RotationBacktestSummary,
} from '../types/rotation';
import type { BacktestDetail } from '../types/signal';

const FLOW_COLOR = '#3a6a8a';   // 主力维
const TECH_COLOR = 'var(--marker-green)'; // 技术维

const FACTOR_LABELS: Record<string, string> = {
  price_momentum_20: '动量20',
  price_momentum_60: '动量60',
  trend_slope: '斜率',
  multi_ma_align: '均线排',
  breakout_strength: '突破位',
  volume_momentum: '量价',
  trend_consistency: '一致性',
  main_inflow_momentum_20: '主力吸筹',
  main_inflow_persistence: '主力持续',
  main_inflow_acceleration: '主力加速',
};

/** Dual-dim stacked horizontal bar: flow + tech ranks sum to strength. */
function StrengthBar({ flow, tech, strength }: {
  flow: number | null; tech: number | null; strength: number;
}) {
  const f = flow ?? 0;
  const t = tech ?? 0;
  return (
    <div className="detail-track" title={`主力维 ${(f * 100).toFixed(0)} / 技术维 ${(t * 100).toFixed(0)}`}>
      <div
        style={{ width: `${f * 50}%`, background: FLOW_COLOR, height: '10px',
                 borderRadius: '3px 0 0 3px', opacity: 0.85 }}
      />
      <div
        style={{ width: `${t * 50}%`, background: TECH_COLOR, height: '10px',
                 borderRadius: '0 3px 3px 0', opacity: 0.85 }}
      />
      <span style={{ marginLeft: 8, fontVariantNumeric: 'tabular-nums',
                    color: 'var(--ink)', fontSize: 12 }}>
        {(strength * 100).toFixed(0)}
      </span>
    </div>
  );
}

/** Sector × date heatmap cell color: blue→white→green by strength. */
function heatColor(v: number): string {
  const clamped = Math.max(0, Math.min(1, v));
  if (clamped >= 0.5) {
    const k = (clamped - 0.5) * 2; // 0..1 toward green
    return `rgba(58,138,110,${0.15 + k * 0.75})`;
  }
  const k = clamped * 2; // 0..1 toward blue
  return `rgba(58,106,138,${0.15 + (1 - k) * 0.5})`;
}

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

export default function RotationPanel() {
  const [sectors, setSectors] = useState<FetchState<SectorScoresResponse>>(initial());
  const [history, setHistory] = useState<FetchState<SectorHistoryResponse>>(initial());
  const [portfolio, setPortfolio] = useState<FetchState<RotationPortfolioResponse>>(initial());
  const [rankings, setRankings] = useState<FetchState<RotationRankingsResponse>>(initial());
  const [expandedSector, setExpandedSector] = useState<string | null>(null);

  const [btSummary, setBtSummary] = useState<RotationBacktestSummary | null>(null);
  const [btDetail, setBtDetail] = useState<BacktestDetail | null>(null);
  const [btRunning, setBtRunning] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);
  const [useFlowFactors, setUseFlowFactors] = useState(true);

  const loadAll = useCallback(() => {
    setSectors((s) => ({ ...s, loading: true }));
    getRotationSectors()
      .then((d) => setSectors({ data: d, loading: false, error: null }))
      .catch((e: unknown) => setSectors({
        data: null, loading: false,
        error: e instanceof Error ? e.message : String(e) }));
    getRotationSectorHistory(30)
      .then((d) => setHistory({ data: d, loading: false, error: null }))
      .catch(() => setHistory({ data: null, loading: false, error: null }));
    getRotationPortfolio()
      .then((d) => setPortfolio({ data: d, loading: false, error: null }))
      .catch(() => setPortfolio({ data: null, loading: false, error: null }));
    getRotationRankings()
      .then((d) => setRankings({ data: d, loading: false, error: null }))
      .catch(() => setRankings({ data: null, loading: false, error: null }));
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const runBacktestNow = useCallback(async () => {
    setBtRunning(true); setBtError(null);
    try {
      const summary = await runRotationBacktest({ use_fund_flow_factors: useFlowFactors });
      setBtSummary(summary);
      const detail = await getBacktest(summary.run_id);
      setBtDetail(detail);
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : String(e));
    } finally {
      setBtRunning(false);
    }
  }, [useFlowFactors]);

  const emptyHint = !sectors.loading && !sectors.data?.sectors?.length;

  const benchmarkCurve = (() => {
    const params = btDetail?.params as
      { benchmark_curve?: { date: string; equity: number }[] } | undefined;
    return params?.benchmark_curve ?? [];
  })();

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {/* 1. Sector strength */}
      <SketchPanel title="板块强度" mono="ROTATION · LAYER 1">
        {sectors.error && <div style={{ color: 'var(--marker-red)' }}>{sectors.error}</div>}
        {emptyHint && (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>
            暂无板块信号 — 等待每日 17:40 扫描，或由管理员触发 POST /api/quant/rotation/scan。
          </div>
        )}
        {sectors.data?.sectors?.map((s) => (
          <div key={s.sector}
               onClick={() => setExpandedSector(expandedSector === s.sector ? null : s.sector)}
               style={{ display: 'flex', alignItems: 'center', gap: 10,
                        padding: '5px 0', cursor: 'pointer' }}>
            <span style={{ width: 92, fontSize: 13, color: 'var(--ink)',
                           textAlign: 'right', flexShrink: 0 }}>
              {s.sector}
            </span>
            <StrengthBar flow={s.flow_dim} tech={s.tech_dim} strength={s.strength} />
            {s.is_selected && (
              <span style={{ fontSize: 11, color: 'var(--marker-green)',
                             border: '1.5px solid var(--marker-green)',
                             borderRadius: 4, padding: '1px 5px', flexShrink: 0 }}>
                持仓
              </span>
            )}
            {s.detail.momentum_20d != null && (
              <span style={{ fontSize: 11, fontVariantNumeric: 'tabular-nums',
                             color: s.detail.momentum_20d >= 0
                               ? 'var(--marker-green)' : 'var(--marker-red)',
                             width: 52, flexShrink: 0 }}>
                {(s.detail.momentum_20d * 100).toFixed(1)}%
              </span>
            )}
          </div>
        ))}
        <div style={{ fontSize: 11, color: 'var(--pencil)', marginTop: 6 }}>
          蓝色 = 主力维（净流入占比 20 日平滑，截面 rank）· 绿色 = 技术维（多头排列占比 + 板块动量）·
          强度 = 两维各 50% · 点击展开板块内排名
        </div>
      </SketchPanel>

      {/* 2. Strength evolution heatmap */}
      {history.data?.dates?.length ? (
        <SketchPanel title="强度演变 · 近 30 日" mono="HEATMAP">
          <div style={{ overflowX: 'auto' }}>
            <table className="table-sketch" style={{ fontSize: 11 }}>
              <tbody>
                {Object.entries(history.data.series).map(([sector, values]) => (
                  <tr key={sector}>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap', padding: '1px 6px' }}>
                      {sector}
                    </td>
                    {values.map((v, i) => (
                      <td key={i} title={`${history.data!.dates[i]}: ${(v * 100).toFixed(0)}`}
                          style={{ background: heatColor(v), padding: 0,
                                   width: 14, height: 14, border: 'none' }} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SketchPanel>
      ) : null}

      {/* 3. Recommended holdings */}
      <SketchPanel title="推荐持仓" mono={`ROTATION · ${portfolio.data?.date ?? '—'}`}>
        {portfolio.data?.holdings?.length ? (
          <table className="table-sketch">
            <thead>
              <tr>
                <th>代码</th><th>名称</th><th>板块</th><th>权重</th><th>综合分</th>
                <th>入场确认</th><th>背离</th><th>止损参考</th><th>主力因子</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.data.holdings.map((h) => (
                <tr key={h.ticker}>
                  <td className="num-left">{h.ticker}</td>
                  <td>{h.name}</td>
                  <td>{h.sector}</td>
                  <td className="num">{(h.weight * 100).toFixed(1)}%</td>
                  <td className="num">{h.composite_score.toFixed(3)}</td>
                  <td style={{ color: h.entry_ok ? 'var(--marker-green)' : 'var(--marker-red)' }}>
                    {h.entry_ok ? '多头排列 ✓' : '未确认'}
                  </td>
                  <td style={{ color: h.divergence_flag ? 'var(--marker-red)' : 'var(--pencil)' }}>
                    {h.divergence_flag ? '⚠ 价量背离' : '—'}
                  </td>
                  <td className="num">{h.stop_loss_price?.toFixed(2) ?? '—'}</td>
                  <td title={Object.entries(h.factor_scores)
                    .filter(([k]) => k.startsWith('main_'))
                    .map(([k, v]) => `${FACTOR_LABELS[k] ?? k}: ${v}`).join('\n')}>
                    {['main_inflow_momentum_20', 'main_inflow_persistence',
                      'main_inflow_acceleration']
                      .map((k) => h.factor_scores[k])
                      .filter((v) => v != null)
                      .map((v) => v.toFixed(2)).join(' / ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>暂无推荐持仓。</div>
        )}
        <div style={{ fontSize: 11, color: 'var(--pencil)', marginTop: 6 }}>
          月度调仓（Top-3 板块 × 板块内 Top-2）；持有期间每日检查破位卖出 / 硬止损 10% / 移动止盈（+20% 激活，回撤 8% 跟踪）。
        </div>
      </SketchPanel>

      {/* 4. In-sector rankings (expandable) */}
      {expandedSector && rankings.data?.stocks?.length ? (
        <SketchPanel title={`板块内排名 · ${expandedSector}`} mono="RANKING">
          <table className="table-sketch">
            <thead>
              <tr><th>#</th><th>代码</th><th>名称</th><th>综合分</th>
                  <th>多头排列</th><th>背离</th><th>入选</th></tr>
            </thead>
            <tbody>
              {rankings.data.stocks
                .filter((s) => s.sector === expandedSector)
                .map((s) => (
                  <tr key={s.ticker} className={s.is_selected ? 'row-clickable' : ''}>
                    <td className="num">{s.rank_in_sector ?? '—'}</td>
                    <td className="num-left">{s.ticker}</td>
                    <td>{s.name}</td>
                    <td className="num">{s.composite_score.toFixed(3)}</td>
                    <td>{s.entry_ok ? '✓' : ''}</td>
                    <td>{s.divergence_flag ? '⚠' : ''}</td>
                    <td>{s.is_selected ? `● ${(s.weight * 100).toFixed(0)}%` : ''}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </SketchPanel>
      ) : null}

      {/* 5. Backtest */}
      <SketchPanel title="策略回测" mono="BACKTEST">
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={useFlowFactors}
                   onChange={(e) => setUseFlowFactors(e.target.checked)} />
            含主力资金流因子（关闭 = 纯技术面长历史骨架）
          </label>
          <button className="btn" onClick={runBacktestNow} disabled={btRunning}>
            {btRunning ? '回测中…' : '运行回测'}
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
                delta={btSummary.excess_return_pct >= 0 ? '跑赢池内等权' : '跑输池内等权'} />
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
                  红线 = 轮动策略 · 虚线 = 池内等权基准（无成本）·
                  区间 {btSummary.start_date} → {btSummary.end_date}
                </div>
              </div>
            )}

            {Object.keys(btSummary.sector_pnl).length > 0 && (
              <div style={{ marginTop: 12, fontSize: 12 }}>
                <strong>分板块盈亏（元）：</strong>
                {Object.entries(btSummary.sector_pnl).map(([sec, pnl]) => (
                  <span key={sec} style={{
                    marginRight: 12,
                    color: pnl >= 0 ? 'var(--marker-green)' : 'var(--marker-red)',
                  }}>
                    {sec} {pnl >= 0 ? '+' : ''}{(pnl / 1e4).toFixed(1)}万
                  </span>
                ))}
              </div>
            )}

            {Object.keys(btSummary.ic_summary).length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: 'pointer', fontSize: 12 }}>因子 IC 详情</summary>
                <table className="table-sketch" style={{ marginTop: 6 }}>
                  <thead><tr><th>因子</th><th>IC均值</th><th>ICIR</th><th>IC正率</th></tr></thead>
                  <tbody>
                    {Object.entries(btSummary.ic_summary).map(([name, s]) => (
                      <tr key={name}>
                        <td>{FACTOR_LABELS[name] ?? name}</td>
                        <td className="num">{s.ic_mean.toFixed(3)}</td>
                        <td className="num">{s.icir.toFixed(2)}</td>
                        <td className="num">{(s.ic_pct_positive * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </>
        )}
      </SketchPanel>
    </div>
  );
}
