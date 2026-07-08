// 数字格式化, 对齐 frontend/src/chainkb/FinanceScreen.tsx:27-47

/** 通用数字: 大数缩写 (k), 小数保留 1-2 位 */
export function fmtNum(v: number | null | undefined, suffix = ''): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (Math.abs(v) >= 1000) return (v / 1000).toFixed(1) + 'k' + suffix;
  if (Math.abs(v) >= 100) return v.toFixed(0) + suffix;
  if (Math.abs(v) >= 10) return v.toFixed(1) + suffix;
  return v.toFixed(2) + suffix;
}

/** 股价: 永远 2 位小数, 不缩写 */
export function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(2);
}

/** 百分比: 默认 2 位小数 */
export function pct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(digits) + '%';
}

/** 带正负号的百分比 (涨跌幅用) */
export function signedPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—';
  const s = v > 0 ? '+' : '';
  return s + v.toFixed(digits) + '%';
}

/** 整数千分位 (1,284) */
export function fmtCount(n: number): string {
  return n.toLocaleString('en-US');
}

/** 把分钟数转为"刚刚/N分钟前/N小时前/N天前" */
export function formatAgo(minutes: number | null): string {
  if (minutes == null) return '从未';
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
  return `${Math.floor(minutes / 1440)}天前`;
}
