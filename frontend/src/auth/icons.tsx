/**
 * Inline SVG icons for admin auth UI.
 *
 * Why inline: @ant-design/icons was removed in the 2026-06-26 frontend
 * slim-down. These three icons are everything the admin gate needs.
 * Stroke uses currentColor so CSS controls the visible color.
 *
 * Viewbox/stroke-width match Ant Design's Outlined style so the
 * aesthetic stays consistent if icons are ever restored.
 */
import type { CSSProperties } from 'react';

interface IconProps {
  className?: string;
  style?: CSSProperties;
}

const SVG_PROPS = {
  width: '1em',
  height: '1em',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export function LockIcon({ className, style }: IconProps) {
  return (
    <svg {...SVG_PROPS} className={className} style={style}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

export function UnlockIcon({ className, style }: IconProps) {
  return (
    <svg {...SVG_PROPS} className={className} style={style}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 7.5-2" />
    </svg>
  );
}

export function LogoutIcon({ className, style }: IconProps) {
  return (
    <svg {...SVG_PROPS} className={className} style={style}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  );
}
