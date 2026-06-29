import type { FreshnessResponse, FreshnessEntry } from '../../types/chainkb';

const TYPE_LABELS: { key: keyof FreshnessResponse; label: string }[] = [
  { key: 'quotes',   label: '现价' },
  { key: 'finance',  label: '财务' },
  { key: 'reports', label: '研报' },
  { key: 'concepts', label: '概念' },
  { key: 'lockup',   label: '解禁' },
  { key: 'holders', label: '股东' },
  { key: 'margin',   label: '融资融券' },
];

function formatAgo(minutes: number | null): string {
  if (minutes == null) return '从未';
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
  return `${Math.floor(minutes / 1440)}天前`;
}

function entryDisplay(
  entry: FreshnessEntry,
  isRunning: boolean,
  failedAt: string | undefined,
): { text: string; className: string; title?: string } {
  if (isRunning) {
    return { text: '更新中…', className: 'fresh-running', title: '后台正在更新此数据' };
  }
  if (failedAt) {
    return {
      text: '失败',
      className: 'fresh-failed',
      title: `最近失败: ${failedAt}`,
    };
  }
  return {
    text: formatAgo(entry.minutes_ago),
    className: 'fresh-ok',
  };
}

interface DataFreshnessProps {
  freshness: FreshnessResponse | null;
}

export default function DataFreshness({ freshness }: DataFreshnessProps) {
  if (!freshness) {
    return <div className="freshness-strip freshness-loading">数据更新时间载入中…</div>;
  }

  const runningSet = new Set(freshness.running);

  return (
    <div className="freshness-strip">
      {TYPE_LABELS.map(({ key, label }) => {
        const entry = freshness[key] as FreshnessEntry;
        const failedAt = freshness.failed_recent[key as string];
        const { text, className, title } = entryDisplay(
          entry,
          runningSet.has(key as string),
          failedAt,
        );
        return (
          <span key={key as string} className={`fresh-item ${className}`} title={title}>
            <span className="fresh-label">{label}</span>
            <span className="fresh-value">{text}</span>
          </span>
        );
      })}
    </div>
  );
}
