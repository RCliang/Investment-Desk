/**
 * 市场冷热全景面板 (market board heat dashboard).
 *
 * Layout:
 *   1. 主线榜单 — lifecycle-tagged boards (主线/启动/退潮) as cards with
 *      triple sparklines (heat EMA / 20d excess return / cumulative main
 *      inflow); clicking drills into the detail modal.
 *   2. 冷热全景热力矩阵 — boards × trade dates, cell color = heat [0,100].
 *      持续性在这个图上是横向长红纹（主线），一日游是竖列斑点。
 *   3. 题材风向 — THS strong-stock theme counts over time + 业绩线.
 *   4. 下钻弹窗 — one board: cumulative excess vs HS300, daily main
 *      inflow bars, heat curve, recent leaders.
 *
 * Data: GET /api/quant/boards/{overview,heatmap,themes}/{bk}/detail,
 * refreshed nightly at 17:45 (admin can POST /boards/refresh).
 */
import { useMemo, useState } from 'react';
import SketchPanel from './components/SketchPanel';
import { useBoardsOverview, useBoardsHeatmap, useBoardDetail } from './hooks/useBoards';
import { triggerBoardsRefresh } from '../services/api';
import type { BoardOverviewItem, BoardTag, BoardDetailResponse } from '../types/boards';
import { TAG_LABELS } from '../types/boards';

const TAG_ORDER: Record<BoardTag, number> = { mainline: 0, starting: 1, fading: 2, cool: 3 };
const TAG_COLOR: Record<BoardTag, string> = {
  mainline: 'var(--marker-red)',
  starting: 'var(--hi-orange)',
  fading: 'var(--marker-blue)',
  cool: 'var(--pencil)',
};

function TagBadge({ tag }: { tag: BoardTag | null }) {
  if (!tag) return null;
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '1px 7px', borderRadius: 4,
      border: `1.5px solid ${TAG_COLOR[tag]}`, color: TAG_COLOR[tag],
      flexShrink: 0, letterSpacing: 1,
    }}>
      {TAG_LABELS[tag]}
    </span>
  );
}

/** heat [0,100] → cold blue → hot red (A股红涨约定). */
function heatColor(v: number | null | undefined): string {
  if (v == null) return 'transparent';
  const c = Math.max(0, Math.min(100, v)) / 100;
  if (c >= 0.5) return `rgba(171,59,59,${(0.14 + (c - 0.5) * 2 * 0.76).toFixed(3)})`;
  return `rgba(58,106,138,${(0.14 + (0.5 - c) * 2 * 0.5).toFixed(3)})`;
}

/** Generic SVG sparkline; nulls skipped, optional zero baseline. */
function Spark({ values, color, width = 108, height = 26, zero = false }: {
  values: (number | null)[]; color: string; width?: number; height?: number; zero?: boolean;
}) {
  const pts = values.filter((v): v is number => v != null);
  if (pts.length < 2) return <svg width={width} height={height} />;
  let min = Math.min(...pts), max = Math.max(...pts);
  if (zero) { min = Math.min(min, 0); max = Math.max(max, 0); }
  const pad = (max - min) * 0.08 || 0.5;
  min -= pad; max += pad;
  const range = max - min || 1;
  let vi = 0;
  const path = values.map((v) => {
    if (v == null) return null;
    const x = (vi / (pts.length - 1)) * (width - 2) + 1;
    vi += 1;
    const y = height - 2 - ((v - min) / range) * (height - 4);
    return `${vi === 1 ? '' : ' '}${x.toFixed(1)},${y.toFixed(1)}`;
  }).filter(Boolean).join('');
  const zeroY = height - 2 - ((0 - min) / range) * (height - 4);
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {zero && zeroY >= 0 && zeroY <= height && (
        <line x1={0} y1={zeroY} x2={width} y2={zeroY} stroke="var(--pencil)"
          strokeWidth={0.7} strokeDasharray="3 3" />
      )}
      <polyline points={path} fill="none" stroke={color} strokeWidth={1.6}
        strokeLinejoin="round" />
    </svg>
  );
}

function fmtSigned(v: number | null | undefined, digits = 1, suffix = ''): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}${suffix}`;
}

/** Leaderboard card: tag badge + triple sparkline + key numbers. */
function BoardCard({ b, onDrill }: { b: BoardOverviewItem; onDrill: (bk: string) => void }) {
  const spark = b.spark;
  return (
    <div className="board-card" onClick={() => onDrill(b.bk_code)} role="button" tabIndex={0}
         onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onDrill(b.bk_code)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <TagBadge tag={b.tag} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', flex: 1,
                       overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {b.name}
        </span>
        <span style={{ fontSize: 10, color: 'var(--paper)', background: 'var(--ink-soft)',
                       borderRadius: 3, padding: '1px 5px', flexShrink: 0 }}>
          {b.bk_type === 'industry' ? '行业' : '概念'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 10, marginTop: 6, alignItems: 'flex-end' }}>
        <div style={{ width: 108 }}>
          <div className="board-card-cap">热度 {(b.heat_ema ?? 0).toFixed(0)}</div>
          <Spark values={spark?.heat ?? []} color="var(--marker-red)" />
        </div>
        <div style={{ width: 108 }}>
          <div className="board-card-cap">20日超额 {fmtSigned(b.mom_excess_20d, 1, '%')}</div>
          <Spark values={spark?.excess ?? []} color="var(--ink)" zero />
        </div>
        <div style={{ width: 108 }}>
          <div className="board-card-cap">
            资金 {fmtSigned(spark?.flow_cum?.[spark.flow_cum.length - 1] ?? null, 1, '亿')}
          </div>
          <Spark values={spark?.flow_cum ?? []} color="#3a6a8a" zero />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10, marginTop: 5, fontSize: 11,
                    color: 'var(--pencil)', fontVariantNumeric: 'tabular-nums' }}>
        <span>#{b.heat_rank ?? '—'}</span>
        <span>广度 {b.breadth_20d != null ? `${(b.breadth_20d * 100).toFixed(0)}%` : '—'}</span>
        <span>主力/成交 {b.flow_ratio_20d != null
          ? `${(b.flow_ratio_20d * 100).toFixed(1)}%` : '—'}</span>
        <span>题材股 {b.theme_cnt}只</span>
        {b.leader?.name && (
          <span style={{ marginLeft: 'auto', color: 'var(--ink)' }}>
            领涨 {b.leader.name}
            {b.leader.change != null && ` +${b.leader.change.toFixed(1)}%`}
          </span>
        )}
      </div>
    </div>
  );
}

/** Drill-down modal: excess curve + main inflow bars + heat curve. */
function BoardDetailModal({ detail, onClose }: {
  detail: BoardDetailResponse; onClose: () => void;
}) {
  const W = 700, H = 190, pad = 10;
  const excess = detail.excess;
  let min = Math.min(0, ...excess), max = Math.max(0, ...excess);
  const yPad = (max - min) * 0.08 || 1;
  min -= yPad; max += yPad;
  const range = max - min || 1;
  const xAt = (i: number) => pad + (i / Math.max(1, excess.length - 1)) * (W - pad * 2);
  const yAt = (v: number) => H - pad - ((v - min) / range) * (H - pad * 2);
  const path = excess.map((v, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ');

  const flows = detail.main_net.filter((v): v is number => v != null);
  const flowMax = Math.max(1e8, ...flows.map((v) => Math.abs(v)));
  const heatVals = detail.heat.map((h) => h.heat_ema).filter((v): v is number => v != null);

  return (
    <div className="board-modal-overlay" onClick={onClose}>
      <div className="board-modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <TagBadge tag={detail.latest?.tag ?? null} />
          <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {detail.name}
          </span>
          <span style={{ fontSize: 11, color: 'var(--pencil)' }}>
            {detail.bk_code} · {detail.bk_type === 'industry' ? '行业' : detail.bk_type === 'concept' ? '概念' : detail.bk_type}
            {detail.member_hint != null && ` · ${detail.member_hint}只成分`}
          </span>
          {detail.latest && (
            <span style={{ marginLeft: 'auto', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
              热度 <b style={{ color: 'var(--marker-red)' }}>{detail.latest.heat_ema.toFixed(0)}</b>
              {detail.latest.heat_rank != null && ` · 全市场第${detail.latest.heat_rank}`}
            </span>
          )}
          <button className="mini-btn" onClick={onClose} style={{ marginLeft: 12 }}>关闭</button>
        </div>

        <div className="board-modal-chart">
          <div className="board-modal-cap">累计超额收益 vs 沪深300（%）</div>
          <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
            <line x1={pad} y1={yAt(0)} x2={W - pad} y2={yAt(0)} stroke="var(--pencil)"
              strokeWidth={1} strokeDasharray="5 4" />
            <path d={path} fill="none" stroke="var(--marker-red)" strokeWidth={2} />
          </svg>
          <div style={{ fontSize: 10, color: 'var(--pencil)' }}>
            {detail.dates[0]} → {detail.dates[detail.dates.length - 1]} ·
            窗口超额 {fmtSigned(excess[excess.length - 1], 1, '%')}
          </div>
        </div>

        <div className="board-modal-chart">
          <div className="board-modal-cap">日度主力净流入（亿元）</div>
          <div className="board-flow-bars">
            {detail.main_net.map((v, i) => (
              <div key={i} title={`${detail.dates[i]}: ${v != null ? (v / 1e8).toFixed(2) : '—'}亿`}
                   style={{
                flex: 1, height: '100%', position: 'relative',
                minWidth: 2, maxWidth: 8,
              }}>
                {v != null && (
                  <div style={{
                    position: 'absolute', left: '15%', width: '70%',
                    top: v >= 0 ? `${50 - Math.abs(v) / flowMax * 50}%` : '50%',
                    height: `${Math.max(0.8, Math.abs(v) / flowMax * 50)}%`,
                    background: v >= 0 ? 'var(--marker-red)' : 'var(--marker-green)',
                    opacity: 0.75, borderRadius: 1,
                  }} />
                )}
              </div>
            ))}
            <div className="board-flow-zero" />
          </div>
        </div>

        <div className="board-modal-chart">
          <div className="board-modal-cap">热度（0-100，5日EMA 平滑）</div>
          <Spark values={heatVals} color="var(--ink)" width={660} height={54} />
        </div>

        {detail.leaders.length > 0 && (
          <div className="board-modal-chart">
            <div className="board-modal-cap">近期领涨股</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 12 }}>
              {detail.leaders.map((l, i) => (
                <span key={i} style={{ color: 'var(--ink)' }}>
                  <span style={{ color: 'var(--pencil)', fontSize: 10 }}>{l.date.slice(5)}</span>{' '}
                  {l.name}{l.change != null && (
                    <b style={{ color: l.change >= 0 ? 'var(--marker-red)' : 'var(--marker-green)' }}>
                      {' '}{fmtSigned(l.change, 1, '%')}
                    </b>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function BoardsPanel() {
  const [sparkDays, setSparkDays] = useState(20);
  const [heatDays, setHeatDays] = useState(30);
  const [typeFilter, setTypeFilter] = useState<'all' | 'industry' | 'concept'>('all');
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);
  const [drillBk, setDrillBk] = useState<string | null>(null);

  const overview = useBoardsOverview(sparkDays, refreshKey);
  const heatmap = useBoardsHeatmap(heatDays, refreshKey);
  const detail = useBoardDetail(drillBk);

  const refreshNow = async () => {
    setRefreshing(true); setRefreshErr(null);
    try {
      await triggerBoardsRefresh();
      setRefreshKey((k) => k + 1);
    } catch (e: unknown) {
      setRefreshErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  /** Leaderboard: lifecycle-tagged first, then by heat EMA. */
  const leaders = useMemo(() => {
    const all = [...(overview.data?.industries ?? []), ...(overview.data?.concepts ?? [])];
    return all
      .sort((a, b) => (TAG_ORDER[a.tag ?? 'cool'] - TAG_ORDER[b.tag ?? 'cool'])
        || (b.heat_ema ?? 0) - (a.heat_ema ?? 0))
      .slice(0, 12);
  }, [overview.data]);

  const heatRows = useMemo(() => {
    const rows = heatmap.data?.rows ?? [];
    return typeFilter === 'all' ? rows : rows.filter((r) => r.bk_type === typeFilter);
  }, [heatmap.data, typeFilter]);

  const industries = heatRows.filter((r) => r.bk_type === 'industry');
  const concepts = heatRows.filter((r) => r.bk_type === 'concept');
  const dates = heatmap.data?.dates ?? [];

  const themes = overview.themes.data;

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {/* 1. 主线榜单 */}
      <SketchPanel title="主线榜单" mono={`BOARDS · ${overview.data?.date ?? '—'}`}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10,
                      flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: 'var(--pencil)' }}>
            热度 = 35%超额动量 + 30%主力资金 + 20%广度 + 15%同花顺题材（横截面百分位）·
            主线 = 近15日≥8天热度前25% 且 20日主力净流入为正
          </span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ display: 'flex', gap: 4 }}>
              {[10, 20, 40].map((d) => (
                <button key={d} className={`mini-btn ${sparkDays === d ? 'active' : ''}`}
                        onClick={() => setSparkDays(d)}>
                  {d}日线
                </button>
              ))}
            </span>
            <button className="mini-btn" onClick={refreshNow} disabled={refreshing}>
              {refreshing ? '刷新中…' : '立即刷新'}
            </button>
          </span>
        </div>
        {refreshErr && (
          <div style={{ color: 'var(--marker-red)', fontSize: 12, marginBottom: 8 }}>
            {refreshErr}
          </div>
        )}
        {overview.error && <div style={{ color: 'var(--marker-red)' }}>{overview.error}</div>}
        {overview.loading && <div style={{ color: 'var(--pencil)' }}>加载中…</div>}
        {!overview.loading && leaders.length === 0 && (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>
            暂无板块热度数据 — 等待每日 17:45 刷新，或由管理员点「立即刷新」。
          </div>
        )}
        <div className="board-card-grid">
          {leaders.map((b) => (
            <BoardCard key={b.bk_code} b={b} onDrill={setDrillBk} />
          ))}
        </div>
      </SketchPanel>

      {/* 2. 冷热全景热力矩阵 */}
      <SketchPanel title="冷热全景 · 热力矩阵" mono="HEATMAP">
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 8,
                      flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {(['all', 'industry', 'concept'] as const).map((t) => (
              <button key={t} className={`mini-btn ${typeFilter === t ? 'active' : ''}`}
                      onClick={() => setTypeFilter(t)}>
                {t === 'all' ? '全部' : t === 'industry' ? '行业' : '概念'}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {[20, 30, 60].map((d) => (
              <button key={d} className={`mini-btn ${heatDays === d ? 'active' : ''}`}
                      onClick={() => setHeatDays(d)}>
                {d}日
              </button>
            ))}
          </div>
          <span style={{ fontSize: 11, color: 'var(--pencil)' }}>
            行=板块（按当前热度排序）· 列=交易日 · 横向长红纹 = 有持续性的主线，竖列斑点 = 一日游 · 点击行名下钻
          </span>
        </div>
        {dates.length === 0 && (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>
            暂无热力数据（需要 ≥5 个交易日的历史积累；历史回填运行中或待运行 backfill_em_boards.py）。
          </div>
        )}
        {dates.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            {([
              ['行业', industries],
              ['概念', concepts],
            ] as const).map(([label, rows]) => rows.length > 0 && (
              <div key={label} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '4px 0',
                              letterSpacing: 2 }}>{label} · {rows.length}</div>
                <table className="table-sketch board-heat-table">
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.bk_code}>
                        <td className="board-heat-name row-clickable"
                            onClick={() => setDrillBk(r.bk_code)}
                            title="点击下钻">
                          <TagBadge tag={r.tag} />
                          <span style={{ maxWidth: 96, overflow: 'hidden',
                                         textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {r.name}
                          </span>
                        </td>
                        {r.values.map((v, i) => (
                          <td key={i} className="board-heat-cell"
                              title={`${dates[i]} · ${r.name}: ${v != null ? v.toFixed(0) : '无数据'}`}
                              style={{ background: heatColor(v) }} />
                        ))}
                        <td className="num" style={{ fontSize: 10, color: 'var(--pencil)',
                                                      whiteSpace: 'nowrap' }}>
                          {(r.heat_ema ?? 0).toFixed(0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </SketchPanel>

      {/* 3. 题材风向 */}
      <SketchPanel title="题材风向 · 同花顺强势股" mono={`THEMES · ${themes?.date ?? '—'}`}>
        {!themes || Object.keys(themes.themes).length === 0 ? (
          <div style={{ color: 'var(--pencil)', padding: '8px 0' }}>暂无题材数据。</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginBottom: 4, letterSpacing: 2 }}>题材线</div>
              <table className="table-sketch" style={{ fontSize: 12 }}>
                <thead><tr><th>题材</th><th>今日</th><th>趋势</th></tr></thead>
                <tbody>
                  {Object.entries(themes.themes).map(([tag, cnts]) => {
                    const max = Math.max(1, ...cnts);
                    const now = cnts[cnts.length - 1];
                    return (
                      <tr key={tag}>
                        <td>{tag}</td>
                        <td className="num" style={{
                          color: now >= 3 ? 'var(--marker-red)' : 'var(--ink)',
                          fontWeight: now >= 3 ? 700 : 400 }}>{now}只</td>
                        <td style={{ width: 120 }}>
                          <Spark values={cnts} color="var(--marker-red)" width={116} height={20} />
                          <span style={{ fontSize: 9, color: 'var(--pencil)' }}>峰{max}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginBottom: 4, letterSpacing: 2 }}>业绩线</div>
              <table className="table-sketch" style={{ fontSize: 12 }}>
                <thead><tr><th>标签</th><th>今日</th><th>趋势</th></tr></thead>
                <tbody>
                  {Object.entries(themes.perf).map(([tag, cnts]) => (
                    <tr key={tag}>
                      <td>{tag}</td>
                      <td className="num">{cnts[cnts.length - 1]}只</td>
                      <td style={{ width: 120 }}>
                        <Spark values={cnts} color="var(--pencil)" width={116} height={20} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--pencil)', marginTop: 6 }}>
          同花顺当日强势股的题材标签计数（零鉴权源）· 业绩线（中报增长/扭亏等）不参与板块热度匹配，单独展示。
        </div>
      </SketchPanel>

      {/* 4. Drill-down modal */}
      {drillBk && detail.data && (
        <BoardDetailModal detail={detail.data} onClose={() => setDrillBk(null)} />
      )}
      {drillBk && detail.loading && (
        <div className="board-modal-overlay" onClick={() => setDrillBk(null)}>
          <div className="board-modal" onClick={(e) => e.stopPropagation()}>
            <div style={{ color: 'var(--pencil)' }}>加载板块详情…</div>
          </div>
        </div>
      )}
    </div>
  );
}
