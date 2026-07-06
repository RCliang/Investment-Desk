import { useEffect, useState } from 'react';
import type {
  LockupEvent,
  HolderPeriod,
  MarginDaily,
  ResearchReport,
} from '../types/chainkb';
import { useCompany, useTimeseries, useSearch } from './hooks/useChainKb';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import StickyNote from './components/StickyNote';
import LatestAnalysisSection from './components/LatestAnalysisSection';

interface FinanceScreenProps {
  initialTicker: string | null;
  onResetTicker: () => void;
}

type TsTabKey = 'lockup' | 'holders' | 'margin' | 'reports';
const TS_TABS: { key: TsTabKey; label: string }[] = [
  { key: 'lockup', label: '解禁' },
  { key: 'holders', label: '股东户数' },
  { key: 'margin', label: '融资融券' },
  { key: 'reports', label: '研报' },
];

function fmtNum(v: number | null | undefined, suffix = ''): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (Math.abs(v) >= 1000) return (v / 1000).toFixed(1) + 'k' + suffix;
  if (Math.abs(v) >= 100) return v.toFixed(0) + suffix;
  if (Math.abs(v) >= 10) return v.toFixed(1) + suffix;
  return v.toFixed(2) + suffix;
}
/** Stock prices never abbreviate — show full precision (e.g., 茅台 1700.00, not 1.7k). */
function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(2);
}
function pct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(digits) + '%';
}
function signedPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  const s = v > 0 ? '+' : '';
  return s + v.toFixed(digits) + '%';
}

function LockupTable({ rows }: { rows: LockupEvent[] }) {
  if (rows.length === 0) return <div className="empty-pad">该股票暂无解禁记录</div>;
  return (
    <table className="table-sketch">
      <thead>
        <tr>
          <th>日期</th>
          <th>类型</th>
          <th style={{ textAlign: 'right' }}>解禁股(万)</th>
          <th style={{ textAlign: 'right' }}>占比</th>
          <th style={{ textAlign: 'right' }}>市值(万)</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.date ?? '—'}</td>
            <td>{r.type}</td>
            <td className="num">{fmtNum(r.shares_wan)}</td>
            <td className="num">{pct(r.ratio_pct)}</td>
            <td className="num">{fmtNum(r.mcap_wan)}</td>
            <td>
              {r.is_upcoming ? (
                <span style={{ color: '#e85a4f', fontWeight: 'bold' }}>即将解禁</span>
              ) : (
                <span style={{ color: '#5a6a85' }}>已过</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HoldersTable({ rows }: { rows: HolderPeriod[] }) {
  if (rows.length === 0) return <div className="empty-pad">该股票暂无股东户数记录</div>;
  return (
    <table className="table-sketch">
      <thead>
        <tr>
          <th>期末日期</th>
          <th>公告日期</th>
          <th style={{ textAlign: 'right' }}>户数</th>
          <th style={{ textAlign: 'right' }}>环比变化</th>
          <th style={{ textAlign: 'right' }}>户均持股</th>
          <th style={{ textAlign: 'right' }}>户均市值(万)</th>
          <th style={{ textAlign: 'right' }}>收盘价</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.end_date ?? '—'}</td>
            <td>{r.notice_date ?? '—'}</td>
            <td className="num">{fmtNum(r.holder_num)}</td>
            <td className="num">{signedPct(r.change_ratio_pct)}</td>
            <td className="num">{fmtNum(r.avg_free_shares)}</td>
            <td className="num">{fmtNum(r.avg_hold_amt_yi, '亿')}</td>
            <td className="num">{fmtPrice(r.close_price)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MarginTable({ rows }: { rows: MarginDaily[] }) {
  if (rows.length === 0) return <div className="empty-pad">该股票暂无融资融券记录</div>;
  return (
    <table className="table-sketch">
      <thead>
        <tr>
          <th>日期</th>
          <th style={{ textAlign: 'right' }}>融资余额(亿)</th>
          <th style={{ textAlign: 'right' }}>融券余额(亿)</th>
          <th style={{ textAlign: 'right' }}>合计(亿)</th>
          <th style={{ textAlign: 'right' }}>净买额(亿)</th>
          <th style={{ textAlign: 'right' }}>收盘价</th>
          <th style={{ textAlign: 'right' }}>涨跌幅</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.date ?? '—'}</td>
            <td className="num">{fmtNum(r.rzye_yi)}</td>
            <td className="num">{fmtNum(r.rqye_yi)}</td>
            <td className="num">{fmtNum(r.rzrqye_yi)}</td>
            <td className="num" style={{ color: (r.rzjme_yi ?? 0) >= 0 ? '#3a8a5a' : '#e85a4f' }}>
              {signedPct(r.rzjme_yi, 2)}
            </td>
            <td className="num">{fmtPrice(r.close_price)}</td>
            <td className="num" style={{ color: (r.change_pct ?? 0) >= 0 ? '#3a8a5a' : '#e85a4f' }}>
              {signedPct(r.change_pct)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReportsTable({ rows }: { rows: ResearchReport[] }) {
  if (rows.length === 0) return <div className="empty-pad">该股票暂无机构研报</div>;
  return (
    <table className="table-sketch">
      <thead>
        <tr>
          <th>日期</th>
          <th>券商</th>
          <th>评级</th>
          <th>标题</th>
          <th style={{ textAlign: 'right' }}>EPS(今)</th>
          <th style={{ textAlign: 'right' }}>EPS(明)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.publish_date ?? '—'}</td>
            <td>{r.broker}</td>
            <td>
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  border: '1px solid #5a6a85',
                  padding: '1px 5px',
                  borderRadius: 2,
                }}
              >
                {r.rating || '—'}
              </span>
            </td>
            <td style={{ maxWidth: 360 }}>{r.title}</td>
            <td className="num">{fmtNum(r.predict_this_year_eps)}</td>
            <td className="num">{fmtNum(r.predict_next_year_eps)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function FinanceScreen({ initialTicker, onResetTicker }: FinanceScreenProps) {
  const [ticker, setTicker] = useState<string>(initialTicker ?? '688256');
  const [query, setQuery] = useState('');
  const [activeTsTab, setActiveTsTab] = useState<TsTabKey>('lockup');

  // Sync from parent (LayerScreen drill-down).
  useEffect(() => {
    if (initialTicker) {
      setTicker(initialTicker);
      onResetTicker();
    }
  }, [initialTicker, onResetTicker]);

  const company = useCompany(ticker);
  const ts = useTimeseries(ticker, 30);
  const search = useSearch(query, 8);

  const pickTicker = (t: string) => {
    setTicker(t);
    setQuery('');
    setActiveTsTab('lockup');
  };

  const tsCounts = {
    lockup: ts.data?.lockup?.length ?? 0,
    holders: ts.data?.holders?.length ?? 0,
    margin: ts.data?.margin?.length ?? 0,
    reports: ts.data?.reports?.length ?? 0,
  };

  return (
    <div>
      {/* Search */}
      <div className="search-wrap">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索公司名或代码 (如：寒武纪 / 688256 / AI)"
          style={{
            flex: 1,
            padding: '10px 14px',
            fontFamily: "'Patrick Hand', cursive",
            fontSize: 15,
            color: '#1a2b4a',
            background: '#fbf9f4',
            border: '2.5px solid #1a2b4a',
            borderRadius: 5,
            outline: 'none',
            boxShadow: '2px 2px 0 rgba(26,43,74,0.1)',
          }}
        />
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            color: '#5a6a85',
            padding: '0 8px',
          }}
        >
          {search.loading ? '搜索中…' : query.trim() && search.data ? `${search.data.results.length} 条` : ''}
        </span>
      </div>

      {query.trim() && search.data && search.data.results.length > 0 && (
        <div className="search-results">
          {search.data.results.map((r) => (
            <div
              key={`${r.market}:${r.ticker}`}
              className="search-result-row"
              onClick={() => pickTicker(r.ticker)}
            >
              <span className="search-result-ticker">{r.ticker}</span>
              <span className="search-result-name">
                {r.name_zh} {r.name_en && `· ${r.name_en}`}
              </span>
              {r.sub_industries[0] && (
                <span style={{ fontFamily: "'Patrick Hand', cursive", fontSize: 12, color: '#5a6a85' }}>
                  {r.sub_industries[0].name_zh}
                </span>
              )}
              <span className="search-result-market">{r.market}</span>
            </div>
          ))}
        </div>
      )}

      {query.trim() && search.data && search.data.results.length === 0 && !search.loading && (
        <div className="empty-pad">未找到匹配「{query.trim()}」的公司</div>
      )}

      {/* Company header */}
      {company.loading && <div className="loading-pad">载入公司档案…</div>}
      {company.error && <div className="loading-pad">载入失败：{company.error}</div>}
      {company.data && (
        <>
          <div className="company-header">
            <span className="company-name">{company.data.company.name_zh}</span>
            <span className="company-ticker">{ticker}</span>
            <span className="company-pill">{company.data.company.market}</span>
            <span className="company-pill">{company.data.company.lifecycle}</span>
            {company.data.company.is_reference && (
              <span className="company-pill" style={{ borderColor: '#e85a4f', color: '#e85a4f' }}>
                海外参考
              </span>
            )}
            {company.data.sub_industries.map((si) => (
              <span key={si.id} className="company-pill">
                {si.group_id} · {si.name_zh}
              </span>
            ))}
          </div>

          {company.data.company.description && (
            <div
              style={{
                fontFamily: "'Patrick Hand', cursive",
                fontSize: 14,
                color: '#3d4f6e',
                lineHeight: 1.6,
                marginBottom: 16,
                padding: '8px 12px',
                borderLeft: '3px solid #5a6a85',
                background: 'rgba(26,43,74,0.03)',
              }}
            >
              {company.data.company.description}
            </div>
          )}

          {/* KPI Row */}
          <div className="kpi-row kpi-row-7">
            <SketchKpi
              stamp="01"
              label="现价"
              value={fmtPrice(company.data.quote?.price)}
              delta={signedPct(company.data.quote?.change_pct)}
              deltaTone={
                (company.data.quote?.change_pct ?? 0) >= 0 ? 'up' : 'down'
              }
            />
            <SketchKpi
              stamp="02"
              label="PE_TTM"
              value={fmtNum(company.data.quote?.pe_ttm)}
              delta={`静态 ${fmtNum(company.data.quote?.pe_static)}`}
              deltaTone="neutral"
            />
            <SketchKpi
              stamp="03"
              label="PB"
              value={fmtNum(company.data.quote?.pb)}
              delta="—"
              deltaTone="neutral"
            />
            <SketchKpi
              stamp="04"
              label="市值(亿)"
              value={fmtNum(company.data.quote?.mcap_yi)}
              delta={`流通 ${fmtNum(company.data.quote?.float_mcap_yi)}`}
              deltaTone="neutral"
            />
            <SketchKpi
              stamp="05"
              label="EPS"
              value={fmtNum(company.data.finance?.eps)}
              delta={`BVPS ${fmtNum(company.data.finance?.bvps)}`}
              deltaTone="neutral"
            />
            <SketchKpi
              stamp="06"
              label="ROE"
              value={pct(company.data.finance?.roe_pct)}
              delta={`净利率 ${pct(company.data.finance?.net_margin_pct)}`}
              deltaTone="neutral"
            />
            <SketchKpi
              stamp="07"
              label="营收(亿)"
              value={fmtNum(company.data.finance?.revenue_yi)}
              delta={`净利 ${fmtNum(company.data.finance?.net_profit_yi)}`}
              deltaTone="neutral"
            />
          </div>

          {/* AI 公司拆解(LatestAnalysisSection) */}
          <LatestAnalysisSection ticker={ticker} />

          {/* Time-series */}
          <SketchPanel
            title="时序明细"
            mono={`TIMESERIES · ${ticker} · LATEST 30`}
            rotate="left"
          >
            <div className="ts-tabs">
              {TS_TABS.map((tab) => (
                <div
                  key={tab.key}
                  className={`ts-tab ${activeTsTab === tab.key ? 'active' : ''}`}
                  onClick={() => setActiveTsTab(tab.key)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setActiveTsTab(tab.key);
                    }
                  }}
                >
                  {tab.label}
                  <span className="ts-tab-count">{tsCounts[tab.key]}</span>
                </div>
              ))}
            </div>

            {ts.loading && <div className="loading-pad">载入时序数据…</div>}
            {ts.error && <div className="loading-pad">载入失败：{ts.error}</div>}
            {!ts.loading && !ts.error && ts.data && (
              <>
                {activeTsTab === 'lockup' && <LockupTable rows={ts.data.lockup ?? []} />}
                {activeTsTab === 'holders' && <HoldersTable rows={ts.data.holders ?? []} />}
                {activeTsTab === 'margin' && <MarginTable rows={ts.data.margin ?? []} />}
                {activeTsTab === 'reports' && <ReportsTable rows={ts.data.reports ?? []} />}
              </>
            )}
          </SketchPanel>

          {/* Concepts cloud */}
          {company.data.concepts.length > 0 && (
            <div className="section" style={{ marginTop: 20 }}>
              <SketchPanel
                title="概念标签云"
                mono={`CONCEPTS · ${company.data.concepts.length}`}
                rotate="right"
              >
                <div className="concepts-cloud">
                  {company.data.concepts.map((c, i) => (
                    <span key={`${c.name}-${i}`} className={`concept-tag ${c.tag_type}`}>
                      {c.name}
                    </span>
                  ))}
                </div>
              </SketchPanel>
            </div>
          )}

          {/* Sticky hint */}
          <StickyNote tone="pink" inline style={{ marginTop: 16 }}>
            <span className="sticky-title">提示</span>
            切换上方 4 个时序 tab 可查看：解禁 / 股东户数 / 融资融券 / 研报，
            每类最多展示最近 30 条。点击表格行不会跳转，可在「公司对比」(下期) 添加到对比篮。
          </StickyNote>
        </>
      )}
    </div>
  );
}
