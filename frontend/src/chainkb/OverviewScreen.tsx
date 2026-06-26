import type { TreeResponse, Layer } from '../types/chainkb';
import { useTree } from './hooks/useChainKb';
import SketchPanel from './components/SketchPanel';
import SketchKpi from './components/SketchKpi';
import StickyNote from './components/StickyNote';
import SubIndustryCard from './components/SubIndustryCard';

interface OverviewScreenProps {
  onSelectSubIndustry: (groupId: string) => void;
}

/** Format company counts: 128 → "128", 1284 → "1,284" */
function fmt(n: number): string {
  return n.toLocaleString('en-US');
}

/** Stats derived from the tree. */
function deriveStats(tree: TreeResponse) {
  let totalCompanies = 0;
  let subIndustryCount = 0;
  const perLayer: { code: string; name_zh: string; count: number }[] = [];
  for (const layer of tree.layers) {
    let layerCount = 0;
    for (const sub of layer.sub_industries) {
      layerCount += sub.company_count;
      subIndustryCount += 1;
    }
    totalCompanies += layerCount;
    perLayer.push({ code: layer.code, name_zh: layer.name_zh, count: layerCount });
  }
  return { totalCompanies, subIndustryCount, layerCount: tree.layers.length, perLayer };
}

/** Inline SVG: 5 layer bubbles connected by arrows. */
function TopologySvg({ layers }: { layers: { code: string; name_zh: string; count: number }[] }) {
  if (layers.length === 0) return null;
  const max = Math.max(...layers.map((l) => l.count), 1);
  const width = 860;
  const height = 220;
  const pad = 80;
  const gap = (width - pad * 2) / (layers.length - 1 || 1);
  return (
    <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
      {layers.map((layer, i) => {
        const x = pad + gap * i;
        const y = height / 2;
        const radius = 44 + (layer.count / max) * 20;
        const isLast = i === layers.length - 1;
        return (
          <g key={layer.code}>
            {/* arrow to next */}
            {!isLast && (
              <>
                <path
                  d={`M ${x + radius + 6} ${y} L ${x + gap - radius - 6} ${y}`}
                  stroke="#1a2b4a"
                  strokeWidth="1.6"
                  strokeDasharray="4,3"
                  fill="none"
                />
                <path
                  d={`M ${x + gap - radius - 12} ${y - 5} L ${x + gap - radius - 6} ${y} L ${x + gap - radius - 12} ${y + 5}`}
                  stroke="#1a2b4a"
                  strokeWidth="1.6"
                  fill="none"
                />
              </>
            )}
            {/* bubble */}
            <ellipse
              cx={x}
              cy={y}
              rx={radius}
              ry={radius * 0.72}
              fill={isLast ? 'rgba(232,90,79,0.08)' : 'rgba(26,43,74,0.04)'}
              stroke={isLast ? '#e85a4f' : '#1a2b4a'}
              strokeWidth="2.2"
              strokeDasharray={isLast ? '4,3' : 'none'}
              transform={`rotate(${i % 2 === 0 ? -1 : 1.5} ${x} ${y})`}
            />
            <text
              x={x}
              y={y - 6}
              textAnchor="middle"
              fontFamily="JetBrains Mono, monospace"
              fontSize="11"
              fill={isLast ? '#e85a4f' : '#1a2b4a'}
              fontWeight="500"
            >
              {layer.code}
            </text>
            <text
              x={x}
              y={y + 10}
              textAnchor="middle"
              fontFamily="Patrick Hand, cursive"
              fontSize="13"
              fill="#1a2b4a"
            >
              {layer.name_zh}
            </text>
            <text
              x={x}
              y={y + 26}
              textAnchor="middle"
              fontFamily="JetBrains Mono, monospace"
              fontSize="10"
              fill="#5a6a85"
            >
              {layer.count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Inline SVG: 5 vertical bars with hatched fills. */
function DistributionBars({ layers }: { layers: { code: string; name_zh: string; count: number }[] }) {
  if (layers.length === 0) return null;
  const max = Math.max(...layers.map((l) => l.count), 1);
  const hatches = ['hatch-cross', 'hatch-light', 'hatch-cross', 'hatch-light', 'hatch-cross'];
  return (
    <div className="bar-row" style={{ height: 220 }}>
      {layers.map((layer, i) => {
        const heightPx = 24 + (layer.count / max) * 160;
        return (
          <div key={layer.code} className="bar-col">
            <div
              className={hatches[i % hatches.length]}
              style={{
                width: '100%',
                height: heightPx,
                border: '2px solid #1a2b4a',
                borderRadius: '2px 2px 0 0',
                boxSizing: 'border-box',
              }}
            />
            <span className="bar-value">{layer.count}</span>
            <span className="bar-label">
              {layer.code} · {layer.name_zh}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function OverviewScreen({ onSelectSubIndustry }: OverviewScreenProps) {
  const { data, loading, error } = useTree();

  if (loading) {
    return <div className="loading-pad">载入产业链数据…</div>;
  }
  if (error) {
    return (
      <div className="loading-pad">
        <strong>载入失败</strong>
        <br />
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#e85a4f' }}>
          {error}
        </span>
      </div>
    );
  }
  if (!data) return null;

  const stats = deriveStats(data);

  return (
    <div>
      {/* KPI Row */}
      <div className="kpi-row">
        <SketchKpi
          stamp="A"
          label="跟踪公司数"
          value={fmt(stats.totalCompanies)}
          delta="CN · HK · US"
          deltaTone="up"
        />
        <SketchKpi
          stamp="B"
          label="子行业数"
          value={stats.subIndustryCount}
          delta={`${stats.layerCount} 层级`}
          deltaTone="neutral"
        />
        <SketchKpi
          stamp="C"
          label="产业链层级"
          value={stats.layerCount}
          delta="I → II → III → IV → V"
          deltaTone="neutral"
        />
        <SketchKpi
          stamp="D"
          label="覆盖市场"
          value="5"
          delta="SH · SZ · BJ · HK · US"
          deltaTone="up"
        />
      </div>

      {/* Topology + Distribution */}
      <div className="content-grid">
        <SketchPanel
          title="产业链拓扑"
          mono="TOPOLOGY · 5 LAYERS"
          rotate="left"
        >
          <div className="chart-canvas" style={{ height: 220 }}>
            <TopologySvg layers={stats.perLayer} />
          </div>
          <div className="chart-caption">— 红色虚线 = 终端应用层 —</div>
        </SketchPanel>

        <SketchPanel
          title="层级分布"
          mono="BAR · COMPANY COUNT"
          rotate="right"
        >
          <div style={{ position: 'relative', minHeight: 220 }}>
            <DistributionBars layers={stats.perLayer} />
            <StickyNote tone="yellow" style={{ top: -24, right: -16 }}>
              <span className="sticky-title">→ 下一步</span>
              点击下方任一子行业卡片，
              查看环节内的公司列表
              <span className="sticky-arrow">↘ 详见 01</span>
            </StickyNote>
          </div>
          <div className="chart-caption">公司数 · 按产业链层级</div>
        </SketchPanel>
      </div>

      {/* Sub-Industry Grid (grouped by layer) */}
      {data.layers.map((layer: Layer, idx: number) => (
        <div className="section" key={layer.code}>
          <SketchPanel
            title={`${layer.code} · ${layer.name_zh}`}
            mono={`LAYER ${idx + 1} · ${layer.name_en.toUpperCase()} · ${layer.sub_industries.length} SEGMENTS`}
          >
            <div className="sub-grid">
              {layer.sub_industries.map((sub) => (
                <SubIndustryCard key={sub.id} sub={sub} onClick={onSelectSubIndustry} />
              ))}
            </div>
          </SketchPanel>
        </div>
      ))}

      <div className="footer-note">
        InvestLens · 产业链知识库 v1 · 数据来源：东方财富 / Tushare / 通达信
      </div>
    </div>
  );
}
