import type { ReactNode } from 'react';

interface SketchPanelProps {
  title: string;
  mono?: string;
  rotate?: 'left' | 'right' | 'none';
  className?: string;
  style?: React.CSSProperties;
  children: ReactNode;
}

/**
 * Sketch-styled panel: paper background, 2.5px ink border, soft drop shadow.
 * Optional mono label appears top-right (small caps JetBrains Mono).
 */
export default function SketchPanel({
  title,
  mono,
  rotate = 'none',
  className = '',
  style,
  children,
}: SketchPanelProps) {
  const rotateClass =
    rotate === 'left' ? 'panel-rotate-l' : rotate === 'right' ? 'panel-rotate-r' : '';
  return (
    <div className={`chart-box ${rotateClass} ${className}`.trim()} style={style}>
      <div className="panel-title">
        {title}
        {mono && <span className="panel-title-mono">{mono}</span>}
      </div>
      {children}
    </div>
  );
}
