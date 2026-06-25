import { useEffect, useMemo, useState } from 'react';
import type { Layer, SubIndustry, CompanyWithMarket } from '../types/chainkb';
import { useTree, useSubIndustry } from './hooks/useChainKb';
import SketchPanel from './components/SketchPanel';
import StickyNote from './components/StickyNote';
import SubIndustryCard from './components/SubIndustryCard';

interface LayerScreenProps {
  initialGroupId: string | null;
  onSelectTicker: (ticker: string) => void;
  onResetGroupId: () => void;
}

/** Split group_id like "II-U-1" → "U". Single-segment IDs (e.g. "V-1") → "M". */
function umdSuffix(sub: SubIndustry): 'U' | 'M' | 'D' {
  const parts = sub.group_id.split('-');
  if (parts.length >= 3) {
    const seg = parts[parts.length - 2];
    if (seg === 'U' || seg === 'M' || seg === 'D') return seg;
  }
  return 'M';
}

function fmtNum(v: number | null | undefined, suffix = ''): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(0) + suffix;
  if (Math.abs(v) >= 10) return v.toFixed(1) + suffix;
  return v.toFixed(2) + suffix;
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(digits) + '%';
}

function MarketBadge({ market }: { market: string }) {
  return <span className="search-result-market">{market}</span>;
}

/** Companies table for a sub-industry. */
function CompaniesTable({
  companies,
  onSelectTicker,
}: {
  companies: CompanyWithMarket[];
  onSelectTicker: (t: string) => void;
}) {
  if (companies.length === 0) {
    return <div className="empty-pad">该子行业暂无挂载公司（或仅含海外参考标的）。</div>;
  }
  return (
    <table className="table-sketch">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>公司</th>
          <th>市场</th>
          <th style={{ textAlign: 'right' }}>现价</th>
          <th style={{ textAlign: 'right' }}>PE_TTM</th>
          <th style={{ textAlign: 'right' }}>PB</th>
          <th style={{ textAlign: 'right' }}>市值(亿)</th>
          <th style={{ textAlign: 'right' }}>EPS</th>
          <th style={{ textAlign: 'right' }}>ROE</th>
          <th style={{ textAlign: 'right' }}>毛利率</th>
        </tr>
      </thead>
      <tbody>
        {companies.map((c) => (
          <tr
            key={`${c.market}:${c.ticker}`}
            className="row-clickable"
            onClick={() => onSelectTicker(c.ticker)}
          >
            <td className="num-left">{c.ticker}</td>
            <td>
              <strong>{c.name_zh}</strong>
              {c.is_reference && (
                <span style={{ marginLeft: 6, fontSize: 10, color: '#5a6a85' }}>(参考)</span>
              )}
            </td>
            <td>
              <MarketBadge market={c.market} />
            </td>
            <td className="num">{fmtNum(c.quote?.price)}</td>
            <td className="num">{fmtNum(c.quote?.pe_ttm)}</td>
            <td className="num">{fmtNum(c.quote?.pb)}</td>
            <td className="num">{fmtNum(c.quote?.mcap_yi)}</td>
            <td className="num">{fmtNum(c.finance?.eps)}</td>
            <td className="num">{pct(c.finance?.roe_pct)}</td>
            <td className="num">{pct(c.finance?.gross_margin_pct)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function LayerScreen({
  initialGroupId,
  onSelectTicker,
  onResetGroupId,
}: LayerScreenProps) {
  const { data, loading, error } = useTree();
  const [activeLayerCode, setActiveLayerCode] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(initialGroupId);

  // When parent passes a new initialGroupId (from overview click), sync local state.
  useEffect(() => {
    if (initialGroupId) {
      setSelectedGroupId(initialGroupId);
      const layerCode = initialGroupId.split('-')[0];
      setActiveLayerCode(layerCode);
      onResetGroupId();
    }
  }, [initialGroupId, onResetGroupId]);

  const activeLayer: Layer | null = useMemo(() => {
    if (!data || !activeLayerCode) return data?.layers[0] ?? null;
    return data.layers.find((l) => l.code === activeLayerCode) ?? data.layers[0] ?? null;
  }, [data, activeLayerCode]);

  const { upstream, midstream, downstream } = useMemo(() => {
    const u: SubIndustry[] = [];
    const m: SubIndustry[] = [];
    const d: SubIndustry[] = [];
    if (activeLayer) {
      for (const sub of activeLayer.sub_industries) {
        const seg = umdSuffix(sub);
        if (seg === 'U') u.push(sub);
        else if (seg === 'D') d.push(sub);
        else m.push(sub);
      }
    }
    return { upstream: u, midstream: m, downstream: d };
  }, [activeLayer]);

  const subDetail = useSubIndustry(selectedGroupId);

  if (loading) return <div className="loading-pad">载入层级数据…</div>;
  if (error) return <div className="loading-pad">载入失败：{error}</div>;
  if (!data || !activeLayer) return <div className="empty-pad">暂无数据</div>;

  return (
    <div>
      {/* Layer tabs */}
      <div className="layer-tabs">
        {data.layers.map((layer) => (
          <div
            key={layer.code}
            className={`layer-tab ${layer.code === activeLayer.code ? 'active' : ''}`}
            onClick={() => {
              setActiveLayerCode(layer.code);
              setSelectedGroupId(null);
            }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setActiveLayerCode(layer.code);
                setSelectedGroupId(null);
              }
            }}
          >
            <span className="layer-tab-code">{layer.code}</span>
            <span>{layer.name_zh}</span>
          </div>
        ))}
      </div>

      {/* 3-column sub-industry split */}
      <SketchPanel
        title={`${activeLayer.code} · ${activeLayer.name_zh} 三段拆解`}
        mono={`${activeLayer.name_en.toUpperCase()} · UPSTREAM → MID → DOWNSTREAM`}
      >
        <div style={{ position: 'relative', minHeight: 240 }}>
          <div className="chain-flow">
            <div className="chain-col" style={{ transform: 'rotate(-0.5deg)' }}>
              <div className="chain-col-title">上游 · U</div>
              <div className="chain-col-sub">UPSTREAM</div>
              {upstream.length === 0 && (
                <div style={{ fontFamily: "'Patrick Hand', cursive", color: '#5a6a85', fontSize: 13 }}>
                  （无）
                </div>
              )}
              {upstream.map((sub) => (
                <SubIndustryCard
                  key={sub.id}
                  sub={sub}
                  onClick={(gid) => setSelectedGroupId(gid)}
                />
              ))}
            </div>
            <div className="chain-col" style={{ transform: 'rotate(0.4deg)' }}>
              <div className="chain-col-title">中游 · M</div>
              <div className="chain-col-sub">MIDSTREAM</div>
              {midstream.length === 0 && (
                <div style={{ fontFamily: "'Patrick Hand', cursive", color: '#5a6a85', fontSize: 13 }}>
                  （无）
                </div>
              )}
              {midstream.map((sub) => (
                <SubIndustryCard
                  key={sub.id}
                  sub={sub}
                  onClick={(gid) => setSelectedGroupId(gid)}
                />
              ))}
            </div>
            <div
              className="chain-col"
              style={{
                transform: 'rotate(-0.3deg)',
                borderColor: '#e85a4f',
                borderWidth: 3,
              }}
            >
              <div className="chain-col-title" style={{ color: '#e85a4f' }}>
                下游 · D
              </div>
              <div className="chain-col-sub">DOWNSTREAM ★</div>
              {downstream.length === 0 && (
                <div style={{ fontFamily: "'Patrick Hand', cursive", color: '#5a6a85', fontSize: 13 }}>
                  （无）
                </div>
              )}
              {downstream.map((sub) => (
                <SubIndustryCard
                  key={sub.id}
                  sub={sub}
                  onClick={(gid) => setSelectedGroupId(gid)}
                />
              ))}
            </div>
          </div>
        </div>
      </SketchPanel>

      {/* Selected sub-industry companies */}
      <div className="section" style={{ marginTop: 20 }}>
        <SketchPanel
          title={
            selectedGroupId
              ? `子行业公司列表`
              : '选择一个子行业'
          }
          mono={
            selectedGroupId
              ? `${selectedGroupId} · ${subDetail.data?.sub_industry.name_zh ?? ''}`
              : 'CLICK A CARD ABOVE'
          }
        >
          {!selectedGroupId && (
            <div className="empty-pad">
              点击上方任一子行业卡片，查看其挂载的公司明细 →
            </div>
          )}
          {selectedGroupId && subDetail.loading && (
            <div className="loading-pad">载入子行业公司…</div>
          )}
          {selectedGroupId && subDetail.error && (
            <div className="loading-pad">载入失败：{subDetail.error}</div>
          )}
          {selectedGroupId && subDetail.data && (
            <CompaniesTable
              companies={subDetail.data.companies}
              onSelectTicker={onSelectTicker}
            />
          )}
          {selectedGroupId && subDetail.data && subDetail.data.companies.length > 0 && (
            <StickyNote tone="green" inline style={{ marginTop: 14 }}>
              <span className="sticky-title">提示</span>
              点击表格任一行 → 进入该公司财务拆解视图（tab 03）
            </StickyNote>
          )}
        </SketchPanel>
      </div>
    </div>
  );
}
