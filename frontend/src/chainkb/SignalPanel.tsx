import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import { useSignals, useSignalDetail, useQuantActions, useStrategies } from './hooks/useSignal';
import type { SignalItem, BacktestDetail, BacktestTrade } from '../types/signal';
import type { SignalFilter } from '../services/api';

type ActionFilter = 'BUY' | 'SELL' | 'HOLD' | 'ALL';
const LAYERS = ['', 'I', 'II', 'III', 'IV', 'V'] as const;
const LAYER_LABELS: Record<string, string> = {
  '': '全部层级',
  I: 'I · 能源与电力',
  II: 'II · 芯片系统',
  III: 'III · AI基础设施',
  IV: 'IV · AI基础模型',
  V: 'V · AI应用',
};

const STRATEGY_LABELS: Record<string, string> = {
  trend_ma: '趋势·均线',
  breakout_donchian: '趋势·突破',
  momentum_macd: '动量·MACD',
  momentum_rsi: '动量·RSI',
  volume_price: '量价',
  risk_atr: '风控·ATR',
};

function actionColor(action: string): string {
  return action === 'BUY' ? 'var(--marker-green)'
    : action === 'SELL' ? 'var(--marker-red)'
    : 'var(--pencil)';
}

function scoreTone(score: number): 'up' | 'down' | 'neutral' {
  if (score >= 0.3) return 'up';
  if (score <= -0.3) return 'down';
  return 'neutral';
}

/** Inline horizontal bar showing the strategy detail breakdown. */
function DetailBar({ detail }: { detail: SignalItem['detail'] }) {
  const entries = Object.entries(detail).filter(([k]) => STRATEGY_LABELS[k]);
  return (
    <div className="signal-detail-bar">
      {entries.map(([k, v]) => {
        const pct = Math.abs(v) * 50; // ±50% of half-bar
        const positive = v >= 0;
        return (
          <div key={k} className="detail-row" title={`${STRATEGY_LABELS[k]}: ${v.toFixed(2)}`}>
            <span className="detail-label">{STRATEGY_LABELS[k]}</span>
            <div className="detail-track">
              <div className="detail-midline" />
              <div
                className="detail-fill"
                style={{
                  width: `${pct}%`,
                  marginLeft: positive ? '50%' : `${50 - pct}%`,
                  background: positive ? 'var(--marker-green)' : 'var(--marker-red)',
                }}
              />
            </div>
            <span className="detail-val">{v.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Equity-curve sparkline drawn as inline SVG (sketch style), with buy/sell
 * markers overlaid at each trade's entry/exit date.
 *
 * Markers:
 *   ▲ green  = BUY (entry)
 *   ▼ red    = SELL via signal
 *   ▼ orange = SELL via stop_loss (hard 10%)
 *   ▼ blue   = SELL via trailing_stop (profit lock)
 *   ▼ gray   = SELL via end (backtest close, forced)
 *
 * Same-day exit+re-entry: markers nudge ±6px vertically to avoid overlap.
 */
type MarkerKind = 'buy' | 'sell-signal' | 'sell-stop' | 'sell-trail' | 'sell-end';
interface Marker { x: number; y: number; kind: MarkerKind; date: string; price?: number }

const MARKER_COLOR: Record<MarkerKind, string> = {
  'buy': 'var(--marker-green)',
  'sell-signal': 'var(--marker-red)',
  'sell-stop': '#e8a04a',
  'sell-trail': '#3a6a8a',
  'sell-end': 'var(--pencil)',
};

/** Compute all geometry (points/markers/baseline) for an equity curve.
 * Pure function — same inputs → same SVG-ready values. Used by both the
 * inline sparkline and the zoomable modal so they stay in sync. */
function computeEquityGeometry(
  curve: { date: string; equity: number }[],
  trades: BacktestTrade[] | undefined,
  width: number,
  height: number,
) {
  const equities = curve.map((p) => p.equity);
  // For-loop min/max (spread blows the stack on 1000+ point curves).
  let min = equities[0];
  let max = equities[0];
  for (let i = 1; i < equities.length; i++) {
    const v = equities[i];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const yPad = (max - min) * 0.08 || 1;
  min -= yPad;
  max += yPad;
  const range = max - min || 1;
  const pad = 10;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const dateToIdx = new Map<string, number>();
  curve.forEach((p, i) => dateToIdx.set(p.date, i));
  const xForIdx = (i: number) => pad + (i / (curve.length - 1)) * w;
  const yForEquity = (eq: number) => pad + h - ((eq - min) / range) * h;

  const points = curve.map((p, i) =>
    `${xForIdx(i).toFixed(1)},${yForEquity(p.equity).toFixed(1)}`,
  );
  const baselineY = yForEquity(curve[0].equity);

  const markers: Marker[] = [];
  if (trades) {
    for (const t of trades) {
      const entryIdx = dateToIdx.get(t.entry_date);
      if (entryIdx !== undefined) {
        markers.push({
          x: xForIdx(entryIdx),
          y: yForEquity(curve[entryIdx].equity),
          kind: 'buy',
          date: t.entry_date,
          price: t.entry_price,
        });
      }
      if (t.exit_date) {
        const exitIdx = dateToIdx.get(t.exit_date);
        if (exitIdx !== undefined) {
          const kind: MarkerKind =
            t.exit_reason === 'signal' ? 'sell-signal' :
            t.exit_reason === 'stop_loss' ? 'sell-stop' :
            t.exit_reason === 'trailing_stop' ? 'sell-trail' :
            'sell-end';
          markers.push({
            x: xForIdx(exitIdx),
            y: yForEquity(curve[exitIdx].equity),
            kind,
            date: t.exit_date,
            price: t.exit_price ?? undefined,
          });
        }
      }
    }
  }
  // Nudge vertically when markers share an x (same-day stop + new buy).
  const byX = new Map<number, Marker[]>();
  for (const m of markers) {
    const key = Math.round(m.x);
    if (!byX.has(key)) byX.set(key, []);
    byX.get(key)!.push(m);
  }
  for (const [, group] of byX) {
    if (group.length > 1) {
      group.forEach((m, i) => { m.y += (i - (group.length - 1) / 2) * 8; });
    }
  }
  return { points, baselineY, markers, pad, width, height };
}

/** Pure SVG renderer. `markerScale` enlarges markers in the modal so they
 * stay visible when the curve is zoomed. */
function EquityChart({
  geom, markerScale = 1, strokeWidth = 2,
}: {
  geom: ReturnType<typeof computeEquityGeometry>;
  markerScale?: number;
  strokeWidth?: number;
}) {
  const { points, baselineY, markers, pad, width, height } = geom;
  return (
    <svg width={width} height={height} className="equity-svg">
      <line
        x1={pad} y1={baselineY} x2={width - pad} y2={baselineY}
        stroke="var(--graph-major)" strokeWidth={1} strokeDasharray="4 4"
      />
      <polyline
        points={points.join(' ')}
        fill="none" stroke="var(--ink)" strokeWidth={strokeWidth}
        strokeLinejoin="round" strokeLinecap="round"
      />
      {markers.map((m, i) => {
        const color = MARKER_COLOR[m.kind];
        const isBuy = m.kind === 'buy';
        const sz = 5 * markerScale;
        const dy = isBuy ? -sz : sz;
        const tri = `${m.x},${m.y + dy} ${m.x - sz},${m.y} ${m.x + sz},${m.y}`;
        const label = `${m.date} · ${m.kind}${m.price ? ' @' + m.price.toFixed(2) : ''}`;
        return (
          <g key={i}>
            <polygon points={tri} fill={color} stroke="var(--paper)" strokeWidth={1} />
            <title>{label}</title>
          </g>
        );
      })}
    </svg>
  );
}

/** Inline sparkline. Click opens the zoomable modal. */
function EquitySparkline({ curve, trades, onOpen }: {
  curve: { date: string; equity: number }[];
  trades?: BacktestTrade[];
  onOpen: () => void;
}) {
  if (curve.length < 2) return <div className="empty-pad">曲线数据不足</div>;
  const geom = useMemo(
    () => computeEquityGeometry(curve, trades, 760, 200),
    [curve, trades],
  );
  return (
    <div className="equity-spark-wrap" onClick={onOpen} role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
    >
      <EquityChart geom={geom} />
      <div className="equity-zoom-hint">🔍 点击放大 · 滚轮缩放 · 拖拽平移</div>
    </div>
  );
}

/** Full-screen zoomable modal. Wheel = zoom toward cursor, drag = pan,
 * double-click = reset, Esc / backdrop-click = close. */
function EquityModal({ curve, trades, onClose }: {
  curve: { date: string; equity: number }[];
  trades: BacktestTrade[];
  onClose: () => void;
}) {
  // Large base canvas; CSS transform scales/translates it inside the viewport.
  const BASE_W = 2400;
  const BASE_H = 700;
  const geom = useMemo(
    () => computeEquityGeometry(curve, trades, BASE_W, BASE_H),
    [curve, trades],
  );

  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset transform when curve changes (new backtest).
  useEffect(() => { setScale(1); setTx(0); setTy(0); }, [curve]);

  // Esc to close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const onWheel = useCallback((e: React.WheelEvent) => {
    // Zoom toward cursor: adjust translate so the point under the cursor
    // stays fixed. factor>1 zoom in, <1 zoom out. Clamp 0.3–6.
    e.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const px = e.clientX - rect.left;   // cursor in viewport coords
    const py = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setScale((prev) => {
      const next = Math.min(6, Math.max(0.3, prev * factor));
      const realFactor = next / prev;
      // Keep cursor point fixed: new_tx = px - (px - tx) * realFactor
      setTx((prevTx) => px - (px - prevTx) * realFactor);
      setTy((prevTy) => py - (py - prevTy) * realFactor);
      return next;
    });
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Only drag with primary button; ignore clicks on markers (they have
    // their own <title> tooltips and shouldn't initiate pan).
    if (e.button !== 0) return;
    dragRef.current = { x: e.clientX, y: e.clientY, tx, ty };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }, [tx, ty]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    setTx(dragRef.current.tx + dx);
    setTy(dragRef.current.ty + dy);
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    dragRef.current = null;
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  }, []);

  const reset = useCallback(() => { setScale(1); setTx(0); setTy(0); }, []);

  return (
    <div className="equity-modal-backdrop" onClick={onClose}>
      {/* stopPropagation on the panel so clicks inside don't close */}
      <div className="equity-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="equity-modal-header">
          <span className="equity-modal-title">回测净值曲线 · 可缩放</span>
          <div className="equity-modal-controls">
            <button className="mini-btn" onClick={() => setScale((s) => Math.min(6, s * 1.25))}>＋ 放大</button>
            <button className="mini-btn" onClick={() => setScale((s) => Math.max(0.3, s / 1.25))}>－ 缩小</button>
            <button className="mini-btn" onClick={reset}>↺ 重置</button>
            <span className="equity-zoom-pct">{Math.round(scale * 100)}%</span>
            <button className="mini-btn equity-close" onClick={onClose}>✕ 关闭</button>
          </div>
        </div>
        <div
          className="equity-modal-canvas"
          ref={containerRef}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          onDoubleClick={reset}
        >
          <div
            className="equity-modal-transform"
            style={{
              transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
              transformOrigin: '0 0',
              width: BASE_W,
              height: BASE_H,
            }}
          >
            <EquityChart geom={geom} markerScale={1.6} strokeWidth={3} />
          </div>
        </div>
        <div className="marker-legend">
          <span><span className="legend-mark" style={{ background: 'var(--marker-green)' }} />▲ 买入</span>
          <span><span className="legend-mark" style={{ background: 'var(--marker-red)' }} />▼ 信号卖出</span>
          <span><span className="legend-mark" style={{ background: '#e8a04a' }} />▼ 止损</span>
          <span><span className="legend-mark" style={{ background: '#3a6a8a' }} />▼ 移动止盈</span>
          <span className="equity-modal-tip">滚轮缩放 · 拖拽平移 · 双击重置 · Esc 关闭</span>
        </div>
      </div>
    </div>
  );
}

export default function SignalPanel() {
  const [action, setAction] = useState<ActionFilter>('BUY');
  const [layer, setLayer] = useState<string>('');
  const [strategySet, setStrategySet] = useState<string>('trend_follow');
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestDetail | null>(null);
  const [chartZoom, setChartZoom] = useState(false);

  const filter: SignalFilter = useMemo(() => ({
    action: action === 'ALL' ? undefined : action,
    layer: layer || undefined,
    strategy_set: strategySet,
    limit: 100,
  }), [action, layer, strategySet]);

  const { data: signals, loading, error } = useSignals(filter);
  const { data: strategiesData } = useStrategies();
  const { data: detail } = useSignalDetail(selectedTicker);
  const actions = useQuantActions();

  const handleRunBacktest = async (ticker: string) => {
    setBacktestResult(null);
    const summary = await actions.backtest(ticker, { strategySet });
    if (summary) {
      const full = await actions.fetchBacktest(summary.run_id);
      setBacktestResult(full);
    }
  };

  const counts = signals?.items.reduce(
    (acc, it) => { acc[it.action] += 1; return acc; },
    { BUY: 0, SELL: 0, HOLD: 0 } as Record<string, number>,
  ) ?? { BUY: 0, SELL: 0, HOLD: 0 };

  return (
    <div className="signal-panel">
      {/* ── Filter bar ────────────────────────────────────────── */}
      <SketchPanel title="信号筛选" mono="QUANT/v1" rotate="none">
        <div className="signal-filter-row">
          <div className="filter-group">
            <span className="filter-label">动作</span>
            {(['BUY', 'SELL', 'HOLD', 'ALL'] as ActionFilter[]).map((a) => (
              <button
                key={a}
                className={`filter-chip ${action === a ? 'active' : ''}`}
                style={action === a ? { borderColor: actionColor(a === 'ALL' ? 'HOLD' : a) } : {}}
                onClick={() => setAction(a)}
              >
                {a === 'ALL' ? '全部' : a}
              </button>
            ))}
          </div>
          <div className="filter-group">
            <span className="filter-label">策略集</span>
            <select value={strategySet} onChange={(e) => setStrategySet(e.target.value)}>
              {(strategiesData?.strategy_sets ?? []).map((ss) => (
                <option key={ss.strategy_set} value={ss.strategy_set}>
                  {ss.strategy_set === 'trend_follow' ? '趋势跟踪 · 破位卖出'
                    : ss.strategy_set === 'v1_default' ? '多因子打分卡'
                    : ss.strategy_set}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">产业链层</span>
            <select value={layer} onChange={(e) => setLayer(e.target.value)}>
              {LAYERS.map((l) => <option key={l} value={l}>{LAYER_LABELS[l]}</option>)}
            </select>
          </div>
          <div className="filter-meta">
            {signals?.date && <span>数据日期 {signals.date}</span>}
            <span>共 {signals?.total ?? 0} 条</span>
          </div>
        </div>
        {/* Distribution KPIs */}
        <div className="kpi-row">
          <SketchKpi label="BUY 信号" value={counts.BUY} deltaTone="up" delta="看多" />
          <SketchKpi label="SELL 信号" value={counts.SELL} deltaTone="down" delta="看空" />
          <SketchKpi label="HOLD" value={counts.HOLD} delta="观望" />
        </div>
      </SketchPanel>

      {/* ── Signal table ──────────────────────────────────────── */}
      <SketchPanel title={`信号列表 · ${action === 'ALL' ? '全部' : action}`} mono={`${signals?.total ?? 0} 条`}>
        {loading && <div className="empty-pad">扫描中…</div>}
        {error && <div className="empty-pad error">加载失败: {error}</div>}
        {!loading && !error && signals && signals.items.length === 0 && (
          <div className="empty-pad">该筛选条件下暂无信号</div>
        )}
        {signals && signals.items.length > 0 && (
          <table className="table-sketch signal-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>动作</th>
                <th style={{ textAlign: 'right' }}>综合分</th>
                <th style={{ textAlign: 'right' }}>仓位</th>
                <th style={{ textAlign: 'right' }}>止损</th>
                <th style={{ textAlign: 'right' }}>目标</th>
                <th>所属子行业</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {signals.items.map((it) => (
                <tr
                  key={it.ticker}
                  className={selectedTicker === it.ticker ? 'row-selected' : ''}
                  onClick={() => setSelectedTicker(it.ticker)}
                >
                  <td className="mono">{it.ticker}</td>
                  <td>{it.name}</td>
                  <td>
                    <span className="action-badge" style={{ color: actionColor(it.action), borderColor: actionColor(it.action) }}>
                      {it.action}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }} className={`score-${scoreTone(it.composite_score)}`}>
                    {it.composite_score > 0 ? '+' : ''}{it.composite_score.toFixed(3)}
                  </td>
                  <td style={{ textAlign: 'right' }}>{(it.position_pct * 100).toFixed(0)}%</td>
                  <td style={{ textAlign: 'right' }}>{it.stop_loss_price?.toFixed(2) ?? '—'}</td>
                  <td style={{ textAlign: 'right' }}>{it.target_price?.toFixed(2) ?? '—'}</td>
                  <td className="chain-cell">
                    {it.chains.slice(0, 2).map((c) => (
                      <span key={c.sub_industry_id} className="chain-tag">
                        {c.layer_code}·{c.sub_industry_name}
                      </span>
                    ))}
                  </td>
                  <td>
                    <button
                      className="mini-btn"
                      onClick={(e) => { e.stopPropagation(); handleRunBacktest(it.ticker); }}
                    >
                      回测
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SketchPanel>

      {/* ── Detail + backtest drawer ──────────────────────────── */}
      {(detail || backtestResult || actions.backtesting) && (
        <SketchPanel title={detail ? `${detail.name} (${detail.ticker}) 信号详情` : '信号详情'} mono="DETAIL">
          {detail && (
            <>
              <div className="kpi-row">
                <SketchKpi label="动作" value={detail.action} deltaTone={scoreTone(detail.composite_score)} />
                <SketchKpi label="综合分" value={detail.composite_score.toFixed(3)} delta={detail.action} deltaTone={scoreTone(detail.composite_score)} />
                <SketchKpi label="建议仓位" value={`${(detail.position_pct * 100).toFixed(0)}%`} />
                <SketchKpi label="止损价" value={detail.stop_loss_price?.toFixed(2) ?? '—'} />
                <SketchKpi label="目标价" value={detail.target_price?.toFixed(2) ?? '—'} />
              </div>
              <h4 className="section-subhead">子策略分解</h4>
              <DetailBar detail={detail.detail} />
              {detail.chains.length > 0 && (
                <>
                  <h4 className="section-subhead">产业链归属</h4>
                  <div className="chain-list">
                    {detail.chains.map((c) => (
                      <span key={c.sub_industry_id} className="chain-tag">
                        {c.layer_code} · {c.layer_name} → {c.sub_industry_name}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
          {actions.backtesting && <div className="empty-pad">回测进行中…</div>}
          {actions.backtestError && <div className="empty-pad error">回测失败: {actions.backtestError}</div>}
          {backtestResult && (
            <>
              <h4 className="section-subhead">
                回测 · {backtestResult.start_date} → {backtestResult.end_date}
              </h4>
              <div className="kpi-row">
                <SketchKpi
                  label="总收益" value={`${backtestResult.total_return_pct > 0 ? '+' : ''}${backtestResult.total_return_pct}%`}
                  deltaTone={backtestResult.total_return_pct >= 0 ? 'up' : 'down'}
                />
                <SketchKpi label="年化" value={`${backtestResult.annual_return_pct > 0 ? '+' : ''}${backtestResult.annual_return_pct}%`} deltaTone={backtestResult.annual_return_pct >= 0 ? 'up' : 'down'} />
                <SketchKpi label="最大回撤" value={`${backtestResult.max_drawdown_pct}%`} deltaTone="down" />
                <SketchKpi label="夏普" value={backtestResult.sharpe_ratio.toFixed(2)} />
                <SketchKpi label="胜率" value={`${backtestResult.win_rate_pct}%`} />
                <SketchKpi label="交易次数" value={backtestResult.trade_count} />
              </div>
              <EquitySparkline
                curve={backtestResult.equity_curve}
                trades={backtestResult.trades}
                onOpen={() => setChartZoom(true)}
              />
              {/* Legend for the markers */}
              <div className="marker-legend">
                <span><span className="legend-mark" style={{ background: 'var(--marker-green)' }} />▲ 买入</span>
                <span><span className="legend-mark" style={{ background: 'var(--marker-red)' }} />▼ 信号卖出</span>
                <span><span className="legend-mark" style={{ background: '#e8a04a' }} />▼ 止损</span>
                <span><span className="legend-mark" style={{ background: '#3a6a8a' }} />▼ 移动止盈</span>
              </div>
              <div className="backtest-meta">
                初始资金 ¥{backtestResult.initial_capital.toLocaleString()} →
                终值 ¥{backtestResult.final_equity.toLocaleString()} ·
                平均持仓 {backtestResult.avg_hold_days} 天 ·
                含佣金 {backtestResult.params.commission_rate * 100}% + 印花税 {backtestResult.params.stamp_duty_rate * 100}% + 滑点 {backtestResult.params.slippage_rate * 100}%
              </div>
            </>
          )}
        </SketchPanel>
      )}

      {/* Zoomable equity-chart modal */}
      {chartZoom && backtestResult && (
        <EquityModal
          curve={backtestResult.equity_curve}
          trades={backtestResult.trades}
          onClose={() => setChartZoom(false)}
        />
      )}
    </div>
  );
}
