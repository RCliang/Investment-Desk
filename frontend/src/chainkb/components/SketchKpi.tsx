interface SketchKpiProps {
  label: string;
  value: string | number;
  stamp?: string;
  delta?: string;
  deltaTone?: 'up' | 'down' | 'neutral';
}

/**
 * Single KPI tile. Stamp (A/B/C/D...) renders in the top-right corner;
 * delta renders below the value with color-coded tone.
 */
export default function SketchKpi({ label, value, stamp, delta, deltaTone = 'neutral' }: SketchKpiProps) {
  return (
    <div className="kpi">
      {stamp && <span className="kpi-stamp">{stamp}</span>}
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {delta && <div className={`kpi-delta ${deltaTone}`}>{delta}</div>}
    </div>
  );
}
