// 临时验证 format.ts 的纯函数行为, 不进生产构建。
// 运行: node scripts/verify-format.mjs
import { fmtNum, fmtPrice, pct, signedPct, fmtCount, formatAgo } from '../src/utils/format.ts';

const asserts = [
  ['fmtNum(1234)', fmtNum(1234), '1.2k'],
  ['fmtNum(1234, "亿")', fmtNum(1234, '亿'), '1.2k亿'],
  ['fmtNum(12.345)', fmtNum(12.345), '12.3'],
  ['fmtNum(null)', fmtNum(null), '—'],
  ['fmtPrice(12.345)', fmtPrice(12.345), '12.35'],
  ['pct(12.345)', pct(12.345), '12.35%'],
  ['signedPct(1.5)', signedPct(1.5), '+1.50%'],
  ['signedPct(-1.5)', signedPct(-1.5), '-1.50%'],
  ['fmtCount(1284)', fmtCount(1284), '1,284'],
  ['formatAgo(null)', formatAgo(null), '从未'],
  ['formatAgo(0)', formatAgo(0), '刚刚'],
  ['formatAgo(30)', formatAgo(30), '30分钟前'],
  ['formatAgo(120)', formatAgo(120), '2小时前'],
  ['formatAgo(1500)', formatAgo(1500), '1天前'],
];

let failed = 0;
for (const [name, actual, expected] of asserts) {
  if (actual !== expected) {
    console.error(`FAIL ${name}: expected ${expected}, got ${actual}`);
    failed++;
  } else {
    console.log(`PASS ${name}`);
  }
}
if (failed > 0) {
  console.error(`\n${failed} assertion(s) failed`);
  process.exit(1);
} else {
  console.log(`\nAll ${asserts.length} assertions passed`);
}
