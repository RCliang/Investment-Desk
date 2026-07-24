import { useMemo, useState } from 'react';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import { useSignals, useSignalDetail, useQuantActions } from './hooks/useSignal';
import type { SignalItem, BacktestDetail } from '../types/signal';
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

/** Equity-curve sparkline drawn as inline SVG (sketch style). */
function EquitySparkline({ curve, width = 520, height = 140 }: {
  curve: { date: string; equity: number }[];
  width?: number;
  height?: number;
}) {
  if (curve.length < 2) return <div className="empty-pad">曲线数据不足</div>;
  const equities = curve.map((p) => p.equity);
  const min = Math.min(...equities);
  const max = Math.max(...equities);
  const range = max - min || 1;
  const pad = 8;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const points = curve.map((p, i) => {
    const x = pad + (i / (curve.length - 1)) * w;
    const y = pad + h - ((p.equity - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const baselineY = pad + h - ((curve[0].equity - min) / range) * h;
  return (
    <svg width={width} height={height} className="equity-svg">
      {/* starting-capital baseline */}
      <line
        x1={pad} y1={baselineY} x2={width - pad} y2={baselineY}
        stroke="var(--graph-major)" strokeWidth={1} strokeDasharray="4 4"
      />
      <polyline
        points={points.join(' ')}
        fill="none" stroke="var(--ink)" strokeWidth={2}
        strokeLinejoin="round" strokeLinecap="round"
      />
      {/* end dot */}
      <circle
        cx={pad + w} cy={pad + h - ((equities[equities.length - 1] - min) / range) * h}
        r={3} fill="var(--hi-orange-edge)"
      />
    </svg>
  );
}

export default function SignalPanel() {
  const [action, setAction] = useState<ActionFilter>('BUY');
  const [layer, setLayer] = useState<string>('');
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestDetail | null>(null);

  const filter: SignalFilter = useMemo(() => ({
    action: action === 'ALL' ? undefined : action,
    layer: layer || undefined,
    limit: 100,
  }), [action, layer]);

  const { data: signals, loading, error } = useSignals(filter);
  const { data: detail } = useSignalDetail(selectedTicker);
  const actions = useQuantActions();

  const handleRunBacktest = async (ticker: string) => {
    setBacktestResult(null);
    const summary = await actions.backtest(ticker);
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
              <EquitySparkline curve={backtestResult.equity_curve} />
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
    </div>
  );
}
