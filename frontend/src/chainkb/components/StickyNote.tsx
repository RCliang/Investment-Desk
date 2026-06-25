import type { ReactNode } from 'react';

interface StickyNoteProps {
  title?: string;
  tone?: 'yellow' | 'pink' | 'green';
  inline?: boolean;
  style?: React.CSSProperties;
  children: ReactNode;
}

/**
 * Sticky note annotation. Absolutely-positioned by default (parent must be
 * `position: relative`). Pass `inline` to render as a flow element.
 */
export default function StickyNote({
  title,
  tone = 'yellow',
  inline = false,
  style,
  children,
}: StickyNoteProps) {
  const toneClass = `sticky-${tone}`;
  const inlineClass = inline ? 'sticky-inline' : '';
  return (
    <div
      className={`sticky ${toneClass} ${inlineClass}`.trim()}
      style={style}
    >
      {title && <span className="sticky-title">{title}</span>}
      {children}
    </div>
  );
}
