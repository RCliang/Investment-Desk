# InvestLens 小程序 v1 — 产业链知识库移植 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Web 端「产业链知识库」模块 (5 层产业链 / 子行业公司列表 / 公司时序数据 / AI 分析) 完整移植到 Taro 微信小程序, 形成可真机使用的 v1。

**Architecture:** Taro 3.5.7 + React 18 + TypeScript. 多页下钻 + 底部 tabBar (总览/搜索/我的)。`Taro.request` 替代 axios, 系统默认字体替代手写字体, 用层级卡片列表代替 SVG 拓扑。纸墨视觉 (米黄 / 虚线 / 黄色高亮 / 便利贴) 通过 SCSS 变量 + 现代 CSS 技巧实现。

**Tech Stack:** Taro 3.5.7, React 18 (function components + hooks), TypeScript 5.1, Sass, `@tarojs/components` + `@tarojs/taro`。

## Global Constraints

来自 spec `docs/superpowers/specs/2026-07-08-investlens-miniprogram-chainkb-design.md` 的项目级约束 (每个任务隐式继承):

- **Taro 3.5.7** (不升级, 不降级), framework: 'react', compiler: webpack5 (见 `config/index.js`)
- **设计稿尺寸 750px** (`designWidth: 750`), 所有尺寸用 `px`, Taro 自动转 `rpx` (`pxtransform`)
- **设计 token** 复刻前端 CSS 变量值 (见各任务): `$paper: #fbf9f4`, `$ink: #1a2b4a`, `$pencil: #5a6a85`, `$hi-yellow: #fff3a8`, `$marker-red: #e85a4f`, `$marker-green: #3a8a5a`, `$sticky-yellow: #ffe97a`
- **字体**: 系统默认 `-apple-system, "PingFang SC", "Helvetica Neue", sans-serif`, **不加载手写字体**
- **API base URL**: dev = `http://localhost:8000` (微信开发者工具勾"不校验合法域名"), prod = `https://<部署域名>` (通过 `config/prod.js` 的 `defineConstants` 注入)
- **后端 API 路径** (已对齐 `backend/app/routers/`):
  - `GET /api/chainkb/tree`
  - `GET /api/chainkb/sub_industries/{group_id}` (注意是下划线 `sub_industries`)
  - `GET /api/chainkb/companies/{ticker}`
  - `GET /api/chainkb/companies/{ticker}/timeseries?types=&limit=`
  - `GET /api/chainkb/search?q=&limit=`
  - `GET /api/chainkb/freshness`
  - `GET /api/deep-analysis/latest?code=` (注意是 `/api/deep-analysis/`, 不是 `/api/chainkb/`)
- **范围**: v1 不做深度分析 pipeline / SSE / 管理员认证 / 手写字体 / SVG 拓扑 / ECharts
- **测试策略**: 项目无测试运行器 (package.json 只有 Taro CLI + TS)。每个任务的"验证"= TS 编译通过 + `npm run build:weapp` 成功 + 微信开发者工具手动 smoke test。纯函数 (format.ts) 额外写一个一次性 Node 脚本验证。
- **代码风格**: 函数组件 + hooks (不用 class component, 与前端一致)。每文件单一职责。
- **commit 风格**: `feat(miniprogram): ...`, `chore(miniprogram): ...`, `refactor(miniprogram): ...` (与现有提交历史一致)

---

## File Structure

任务覆盖的文件 (创建 / 修改 / 删除):

```
investlens-miniprogram/
├── config/
│   └── prod.js                                    # Modify: 注入 BASE_URL
├── src/
│   ├── app.config.ts                              # Modify: 5 pages + tabBar
│   ├── app.scss                                   # Modify: 全局纸墨背景
│   ├── styles/
│   │   └── tokens.scss                            # Create: 设计 token
│   ├── types/
│   │   ├── chainkb.ts                             # Keep (现有, 必要时校准)
│   │   └── deepAnalysis.ts                        # Create: AnalysisDoc/Bucket/Field
│   ├── services/
│   │   ├── request.ts                             # Create: Taro.request 封装
│   │   └── chainkb.ts                             # Create: 7 个 API 函数
│   │   (api.ts                                    # Delete: 旧 axios 版)
│   ├── utils/
│   │   └── format.ts                              # Create: 纯格式化函数
│   ├── hooks/
│   │   └── useChainKb.ts                          # Create: 6 个 hook
│   ├── components/
│   │   ├── SketchPanel/                           # Create
│   │   ├── SketchKpi/                             # Create
│   │   ├── MarketBadge/                           # Create
│   │   ├── DataFreshness/                         # Create
│   │   ├── SubIndustryCard/                       # Create
│   │   ├── TimeseriesTable/                       # Create
│   │   ├── LatestAnalysis/                        # Create
│   │   ├── BucketTabs/                            # Create
│   │   └── BucketFieldCard/                       # Create
│   ├── pages/
│   │   ├── overview/                              # Create
│   │   ├── search/                                # Create
│   │   ├── profile/                               # Create
│   │   ├── layers/                                # Create
│   │   ├── finance/                               # Create
│   │   (chain/                                    # Delete)
│   │   (index/                                    # Delete)
│   └── app.ts                                     # 现有 App 类保留不动
```

每个组件目录标准结构: `index.tsx` + `index.scss` (部分加 `index.config.ts` 用 `definePageConfig` 设置 navigation bar)。每个 page 目录标准结构: `index.tsx` + `index.scss` + `index.config.ts`。

---

## Task 1: 项目骨架重置 + 设计 token

清掉旧骨架, 配好 tabBar + 全局纸墨背景, 让 devtools 能跑起一个空白纸色页面。

**Files:**
- Create: `investlens-miniprogram/src/styles/tokens.scss`
- Modify: `investlens-miniprogram/src/app.config.ts`
- Modify: `investlens-miniprogram/src/app.scss`
- Delete: `investlens-miniprogram/src/pages/chain/` (整目录)
- Delete: `investlens-miniprogram/src/pages/index/` (整目录)
- Delete: `investlens-miniprogram/src/services/api.ts` (整文件)

**Interfaces:**
- Produces: `styles/tokens.scss` 暴露 SCSS 变量 `$paper/$ink/$pencil/$hi-yellow/$marker-red/$marker-green/$sticky-yellow/$font-base/$font-mono`, 后续所有 `.scss` 通过 `@import '@/styles/tokens.scss';` 使用

- [ ] **Step 1: 删除旧骨架文件**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
rm -rf src/pages/chain src/pages/index src/services/api.ts
```

- [ ] **Step 2: 创建设计 token 文件**

Create `src/styles/tokens.scss`:

```scss
// Paper-ink design tokens (复刻 frontend/src/styles/tokens.css 的 CSS 变量值)
$paper:         #fbf9f4;
$ink:           #1a2b4a;
$pencil:        #5a6a85;
$hi-yellow:     #fff3a8;
$marker-red:    #e85a4f;
$marker-green:  #3a8a5a;
$sticky-yellow: #ffe97a;

// 字体: 系统默认 (不加载 Caveat / Patrick Hand)
$font-base: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
$font-mono: "SF Mono", "JetBrains Mono", Consolas, monospace;
```

- [ ] **Step 3: 改写 app.config.ts**

Replace `src/app.config.ts` 内容:

```typescript
import { defineAppConfig } from '@tarojs/taro'

export default defineAppConfig({
  pages: [
    'pages/overview/index',
    'pages/search/index',
    'pages/profile/index',
    'pages/layers/index',
    'pages/finance/index',
  ],
  tabBar: {
    color: '#5a6a85',
    selectedColor: '#1a2b4a',
    backgroundColor: '#fbf9f4',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/overview/index', text: '总览' },
      { pagePath: 'pages/search/index',  text: '搜索' },
      { pagePath: 'pages/profile/index', text: '我的' },
    ],
  },
  window: {
    navigationBarTitleText: 'InvestLens',
    navigationBarBackgroundColor: '#fbf9f4',
    navigationBarTextStyle: 'black',
    backgroundColor: '#fbf9f4',
  },
  style: 'v2',
  lazyCodeLoading: 'requiredComponents',
  sitemapLocation: 'sitemap.json',
})
```

注意: 引用了 5 个 page 路径, 后续 Task 会逐一创建。本任务结束时, 因为 page 文件还不存在, `npm run build:weapp` 会报错 — 这是预期的, 用 devtools 看不到内容也属正常。下一任务开始补 page。

- [ ] **Step 4: 改写 app.scss 全局背景**

Replace `src/app.scss` 内容:

```scss
@import './styles/tokens.scss';

page {
  background-color: $paper;
  color: $ink;
  font-family: $font-base;
  font-size: 28px;
  line-height: 1.5;
}
```

- [ ] **Step 5: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/styles/tokens.scss \
        investlens-miniprogram/src/app.config.ts \
        investlens-miniprogram/src/app.scss \
        investlens-miniprogram/src/pages \
        investlens-miniprogram/src/services/api.ts
git status  # 确认变更范围
git commit -m "$(cat <<'EOF'
refactor(miniprogram): reset skeleton + add paper-ink design tokens

Drop the initial chain/index skeleton and axios-based api.ts. Register
the v1 page set (overview/search/profile + layers/finance) and the
3-item bottom tabBar. Add SCSS design tokens mirroring the frontend's
paper-ink CSS variables. Apply global paper background to page.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: API 服务层 + 类型 + 格式化工具

打基础: `Taro.request` 封装 + 7 个 chainkb API 函数 + 深度分析类型 (用于 LatestAnalysis) + 格式化纯函数。

**Files:**
- Create: `investlens-miniprogram/src/services/request.ts`
- Create: `investlens-miniprogram/src/services/chainkb.ts`
- Create: `investlens-miniprogram/src/utils/format.ts`
- Create: `investlens-miniprogram/src/types/deepAnalysis.ts`
- Verify: `investlens-miniprogram/src/types/chainkb.ts` (现有, 必要时补缺)

**Interfaces:**
- Produces (供后续任务使用):
  - `services/request.ts`: `request<T>(path: string, opts?: RequestOptions): Promise<T>`  其中 `RequestOptions = { method?: 'GET'|'POST'; query?: Record<string,string|number|undefined>; body?: unknown }`
  - `services/chainkb.ts`: `getTree()`, `getSubIndustry(groupId)`, `getCompany(ticker)`, `getTimeseries(ticker, opts?)`, `search(q, limit?)`, `getFreshness()`, `getLatestAnalysis(code)`
  - `utils/format.ts`: `fmtNum(v, suffix?)`, `fmtPrice(v)`, `pct(v, digits?)`, `signedPct(v, digits?)`, `fmtCount(n)`, `formatAgo(minutes)`
  - `types/deepAnalysis.ts`: `CompanyType`, `BucketId`, `Evidence`, `FieldValue`, `BucketResult`, `AnalysisStats`, `AnalysisDoc`, `COMPANY_TYPE_LABELS`, `BUCKET_DISPLAY_NAMES`, `FIELD_LABELS`, `fieldLabel(name)`
- Consumes: `types/chainkb.ts` (现有)

- [ ] **Step 1: 校验现有 chainkb.ts 类型完整性**

Read `src/types/chainkb.ts`, 确认含 spec 第 5 节列出的所有类型 (`TreeResponse`/`Layer`/`SubIndustry`/`CompanyBrief`/`Quote`/`FinanceSnapshot`/`CompanyWithMarket`/`SubIndustryBrief`/`SubIndustryDetail`/`Concept`/`CompanySubIndustry`/`CompanyProfile`/`LockupEvent`/`HolderPeriod`/`MarginDaily`/`ResearchReport`/`TimeSeriesResponse`/`SearchResult`/`SearchResponse`/`FreshnessEntry`/`FreshnessResponse`)。

若缺类型, 补齐。若与 spec 第 5 节不一致, 以 spec 为准修正。

- [ ] **Step 2: 创建 deepAnalysis.ts 类型**

Create `src/types/deepAnalysis.ts`:

```typescript
// 与 frontend/src/types/deepAnalysis.ts 对齐 (v1 只需要展示最新分析, 不需要 SSE/parse 相关)

export type CompanyType = 'equipment' | 'material' | 'packaging' | 'ip' | 'general';

export type BucketId =
  | 'industry_chain'
  | 'equipment'
  | 'material'
  | 'financial'
  | 'risk'
  | 'catalyst';

export type Evidence = 'strong' | 'medium' | 'weak' | 'unknown';

export interface FieldValue {
  value: string | number | string[] | null;
  evidence: Evidence;
  quote: string | null;
}

export interface BucketResult {
  bucket_id: BucketId;
  fields: Record<string, FieldValue>;
}

export interface AnalysisStats {
  ok: number;
  error: number;
  total: number;
}

export interface AnalysisDoc {
  version: 'v2';
  company_type: CompanyType;
  stock_code: string;
  buckets: BucketResult[];
  analyzed_at: string;
  model_name: string;
  stats: AnalysisStats;
}

export const COMPANY_TYPE_LABELS: Record<CompanyType, string> = {
  equipment: '设备',
  material:  '材料',
  packaging: '封测',
  ip:        'IP',
  general:   '综合',
};

export const BUCKET_DISPLAY_NAMES: Record<BucketId, string> = {
  industry_chain: '产业链与竞争格局',
  equipment:      '设备层指标',
  material:       '材料层指标',
  financial:      '分业务财务',
  risk:           '风险与反证',
  catalyst:       '催化剂与监控',
};

export const FIELD_LABELS: Record<string, string> = {
  domestic_share:        '国产化率',
  competitors:           '主要竞争对手',
  certification_stage:   '客户认证阶段',
  industry_position:     '行业地位',
  value_chain_link:      '产业链环节',
  keyEquipmentModels:    '核心设备型号',
  targetProcessNode:     '目标制程节点',
  throughput:            '设备产能/吞吐',
  yield_rate:            '良率',
  customer_validation:   '客户验证进度',
  key_materials:         '核心材料',
  purity_grade:          '纯度等级',
  domestic_suppliers:    '国产供应商',
  import_dependency:     '进口依赖度',
  certification_progress:'认证进度',
  revenue_forecast:      '营收预测',
  gross_margin:          '毛利率',
  net_profit_forecast:   '净利润预测',
  pe_band:               'PE 估值区间',
  growth_drivers:        '增长驱动',
  tech_risk:             '技术风险',
  market_risk:           '市场风险',
  policy_risk:           '政策/贸易战风险',
  supply_chain_risk:     '供应链风险',
  counter_evidence:      '反证(看空理由)',
  short_term_catalyst:   '短期催化剂',
  long_term_catalyst:    '长期催化剂',
  monitoring_metrics:    '监控指标',
  inflection_point:      '拐点信号',
};

export function fieldLabel(name: string): string {
  return FIELD_LABELS[name] ?? name;
}
```

- [ ] **Step 3: 创建 request.ts (Taro.request 封装)**

Create `src/services/request.ts`:

```typescript
import Taro from '@tarojs/taro';

// dev: localhost (微信开发者工具需勾"不校验合法域名")
// prod: 通过 config/prod.js defineConstants 注入 BASE_URL
const BASE_URL = typeof BASE_URL_ENV !== 'undefined'
  ? BASE_URL_ENV
  : 'http://localhost:8000';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  header?: Record<string, string>;
}

export class ApiError extends Error {
  statusCode: number;
  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
    this.name = 'ApiError';
  }
}

/**
 * 统一 Taro.request 封装。
 * path 形如 '/api/chainkb/tree' (含 /api 前缀)。
 * 非 2xx 状态码抛 ApiError。网络错误抛 Error。
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, header } = opts;
  const url = BASE_URL + path + buildQuery(query);

  const res = await Taro.request({
    url,
    method,
    data: body,
    header: { 'Content-Type': 'application/json', ...header },
    timeout: 15000,
  });

  if (res.statusCode < 200 || res.statusCode >= 300) {
    const msg = (res.data && (res.data as { detail?: string }).detail) || `HTTP ${res.statusCode}`;
    throw new ApiError(res.statusCode, msg);
  }
  return res.data as T;
}

function buildQuery(query?: RequestOptions['query']): string {
  if (!query) return '';
  const entries = Object.entries(query).filter(([, v]) => v !== undefined && v !== '');
  if (entries.length === 0) return '';
  const params = entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return '?' + params.join('&');
}
```

注意: `BASE_URL_ENV` 是 prod 构建时常量, 由 `config/prod.js` 注入 (见 Step 7)。dev 下未定义, 走 `http://localhost:8000` fallback。TS 会警告 `BASE_URL_ENV` 未声明, 在下一步 Step 4 添加全局声明解决。

- [ ] **Step 4: 添加全局常量声明**

Create `src/global.d.ts`:

```typescript
/// <reference types="@tarojs/taro" />

declare const BASE_URL_ENV: string;
```

- [ ] **Step 5: 创建 chainkb.ts (7 个 API 函数)**

Create `src/services/chainkb.ts`:

```typescript
import { request } from './request';
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
  FreshnessResponse,
} from '../types/chainkb';
import type { AnalysisDoc } from '../types/deepAnalysis';

export function getTree(): Promise<TreeResponse> {
  return request<TreeResponse>('/api/chainkb/tree');
}

export function getSubIndustry(groupId: string): Promise<SubIndustryDetail> {
  return request<SubIndustryDetail>(`/api/chainkb/sub_industries/${encodeURIComponent(groupId)}`);
}

export function getCompany(ticker: string): Promise<CompanyProfile> {
  return request<CompanyProfile>(`/api/chainkb/companies/${encodeURIComponent(ticker)}`);
}

export function getTimeseries(
  ticker: string,
  opts: { types?: string[]; limit?: number } = {},
): Promise<TimeSeriesResponse> {
  return request<TimeSeriesResponse>(
    `/api/chainkb/companies/${encodeURIComponent(ticker)}/timeseries`,
    {
      query: {
        types: opts.types?.join(','),
        limit: opts.limit,
      },
    },
  );
}

export function search(q: string, limit = 20): Promise<SearchResponse> {
  return request<SearchResponse>('/api/chainkb/search', { query: { q, limit } });
}

export function getFreshness(): Promise<FreshnessResponse> {
  return request<FreshnessResponse>('/api/chainkb/freshness');
}

/**
 * 获取最新 v2 结构化分析。
 * 后端无分析时返回 404, 本函数捕获后返回 null (与前端 api.ts 行为对齐)。
 */
export async function getLatestAnalysis(code: string): Promise<AnalysisDoc | null> {
  try {
    return await request<AnalysisDoc>('/api/deep-analysis/latest', { query: { code } });
  } catch (err) {
    if (err instanceof Error && 'statusCode' in err && (err as { statusCode: number }).statusCode === 404) {
      return null;
    }
    throw err;
  }
}
```

- [ ] **Step 6: 创建 format.ts (纯函数)**

Create `src/utils/format.ts`:

```typescript
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
```

- [ ] **Step 7: 改写 config/prod.js 注入 BASE_URL**

Replace `config/prod.js` 内容 (现有内容先用 Read 检查, 再替换):

```javascript
// 生产构建时把 BASE_URL_ENV 注入为字符串字面量。
// 真机部署前请把 https://api.investlens.example.com 改成实际域名
// (该域名需在小程序后台 request 合法域名列表里配置)。
module.exports = {
  env: {
    NODE_ENV: '"production"'
  },
  defineConstants: {
    BASE_URL_ENV: '"https://api.investlens.example.com"'
  },
  mini: {},
  h5: {}
}
```

- [ ] **Step 8: 创建一个一次性验证脚本 (可选, 验证 format.ts)**

Create `investlens-miniprogram/scripts/verify-format.mjs` (临时, 不在构建产物里):

```javascript
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
```

由于 `.ts` 直接被 Node 跑需要 ts-node / esbuild, 实际跑改为临时改后缀或用 npx:

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsx scripts/verify-format.mjs 2>nul || (
  echo tsx unavailable, falling back to manual review
  type src\utils\format.ts
)
```

如果 `tsx` 不可用且不便安装, 直接 review `format.ts` 与 frontend 原版 (路径见 spec) 是否逐字对齐即可。

- [ ] **Step 9: TS 编译检查**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit
```

预期: 无错误。若有, 修到无错误为止。

- [ ] **Step 10: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/services/request.ts \
        investlens-miniprogram/src/services/chainkb.ts \
        investlens-miniprogram/src/utils/format.ts \
        investlens-miniprogram/src/types/deepAnalysis.ts \
        investlens-miniprogram/src/types/chainkb.ts \
        investlens-miniprogram/src/global.d.ts \
        investlens-miniprogram/config/prod.js \
        investlens-miniprogram/scripts/verify-format.mjs
git commit -m "$(cat <<'EOF'
feat(miniprogram): add Taro.request wrapper, chainkb API, format utils

- services/request.ts: Taro.request 封装 (baseURL via defineConstants,
  15s timeout, ApiError on non-2xx)
- services/chainkb.ts: 7 个 API 函数 (tree/sub_industry/company/
  timeseries/search/freshness/latest-analysis), 路径对齐后端 router
- utils/format.ts: 数字/百分比/时间格式化纯函数 (对齐前端)
- types/deepAnalysis.ts: AnalysisDoc v2 类型 (LatestAnalysis 用)
- global.d.ts: BASE_URL_ENV 全局声明
- config/prod.js: 注入生产 baseURL (占位域名, 部署时改)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: useChainKb hooks

复刻前端 6 个数据获取 hook, 供页面使用。

**Files:**
- Create: `investlens-miniprogram/src/hooks/useChainKb.ts`

**Interfaces:**
- Consumes: `services/chainkb.ts` 的 7 个函数
- Produces:
  - `FetchState<T> = { data: T | null; loading: boolean; error: string | null }`
  - `useTree(): FetchState<TreeResponse>`
  - `useSubIndustry(groupId: string | null): FetchState<SubIndustryDetail>`
  - `useCompany(ticker: string | null): FetchState<CompanyProfile>`
  - `useTimeseries(ticker: string | null, limit?: number): FetchState<TimeSeriesResponse>`
  - `useSearch(q: string, limit?: number, delay?: number): FetchState<SearchResponse>`
  - `useFreshness(): FreshnessResponse | null` (60s 轮询, 静默失败)

- [ ] **Step 1: 创建 hooks 文件**

Create `src/hooks/useChainKb.ts`:

```typescript
import { useEffect, useRef, useState } from 'react';
import {
  getTree,
  getSubIndustry,
  getCompany,
  getTimeseries,
  search,
  getFreshness,
} from '../services/chainkb';
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
  FreshnessResponse,
} from '../types/chainkb';

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const initialState: FetchState<unknown> = {
  data: null,
  loading: true,
  error: null,
};

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/** 一次性拉取全树 */
export function useTree(): FetchState<TreeResponse> {
  const [state, setState] = useState<FetchState<TreeResponse>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getTree()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) });
      });
    return () => { cancelled = true; };
  }, []);

  return state;
}

/** 按 groupId 拉子行业; groupId 为 null 时不发请求 */
export function useSubIndustry(groupId: string | null): FetchState<SubIndustryDetail> {
  const [state, setState] = useState<FetchState<SubIndustryDetail>>(initialState as FetchState<SubIndustryDetail>);

  useEffect(() => {
    if (!groupId) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getSubIndustry(groupId)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [groupId]);

  return state;
}

/** 按 ticker 拉公司 profile */
export function useCompany(ticker: string | null): FetchState<CompanyProfile> {
  const [state, setState] = useState<FetchState<CompanyProfile>>(initialState as FetchState<CompanyProfile>);

  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getCompany(ticker)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [ticker]);

  return state;
}

/** 按 ticker 拉时序数据 (默认 4 类一次返回, limit=30) */
export function useTimeseries(ticker: string | null, limit = 30): FetchState<TimeSeriesResponse> {
  const [state, setState] = useState<FetchState<TimeSeriesResponse>>(initialState as FetchState<TimeSeriesResponse>);

  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    getTimeseries(ticker, { limit })
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    return () => { cancelled = true; };
  }, [ticker, limit]);

  return state;
}

/** 防抖搜索; 空字符串不发请求, 立即清空 */
export function useSearch(q: string, limit = 20, delay = 280): FetchState<SearchResponse> {
  const [state, setState] = useState<FetchState<SearchResponse>>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (!q) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setState({ data: null, loading: true, error: null });
      search(q, limit)
        .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
        .catch((err) => { if (!cancelled) setState({ data: null, loading: false, error: errorMessage(err) }); });
    }, delay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q, limit, delay]);

  return state;
}

/** 60s 轮询 freshness; 失败时保留上次数据 */
export function useFreshness(): FreshnessResponse | null {
  const [data, setData] = useState<FreshnessResponse | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getFreshness()
        .then((d) => { if (!cancelled) setData(d); })
        .catch(() => { /* 静默, 保留上次数据 */ });
    };
    tick(); // 立即跑一次
    timerRef.current = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return data;
}
```

注意:
- 用裸 `setTimeout` / `clearTimeout` / `setInterval` / `clearInterval` (无 `window.` 前缀)。这些在 H5 和 weapp 运行时都是全局可用的, 避免任何 `window is not defined` 风险。
- `ReturnType<typeof setInterval>` 在 H5 下解析为 `number`, 在 Node/weapp 下解析为 `NodeJS.Timeout`, 用 `useRef<ReturnType<typeof setInterval> | null>(null)` 是跨平台兼容写法。

- [ ] **Step 2: TS 编译检查**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit
```

预期: 无错误。

- [ ] **Step 3: weapp 构建检查**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npm run build:weapp 2>&1 | tail -20
```

预期: 构建成功 (可能有 Taro 3.5.7 的 `ENABLE_INNER_HTML` 警告, 见 README, 可忽略)。若失败, 修复后重新构建。

- [ ] **Step 4: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/hooks/useChainKb.ts
git commit -m "$(cat <<'EOF'
feat(miniprogram): add 6 chainkb data hooks (tree/sub/company/ts/search/freshness)

Mirror the frontend's useChainKb hook set with FetchState<T> shape:
useTree (one-shot), useSubIndustry/useCompany/useTimeseries (refetch on
arg change), useSearch (280ms debounce, skip empty), useFreshness
(60s polling, silent fail).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 基础容器组件 (SketchPanel / SketchKpi / MarketBadge / DataFreshness)

4 个最常用的展示组件, 后续页面都依赖。

**Files:**
- Create: `src/components/SketchPanel/index.tsx` + `index.scss`
- Create: `src/components/SketchKpi/index.tsx` + `index.scss`
- Create: `src/components/MarketBadge/index.tsx` + `index.scss`
- Create: `src/components/DataFreshness/index.tsx` + `index.scss`

**Interfaces:**
- Produces:
  - `<SketchPanel title?: string; children: ReactNode; className?: string>`
  - `<SketchKpi label: string; value: ReactNode; unit?: string>`
  - `<MarketBadge market: 'SH'|'SZ'|'BJ'|'HK'|'US'|string>`
  - `<DataFreshness market?: FreshnessEntry; finance?: FreshnessEntry; variant?: 'compact'|'full'>`

- [ ] **Step 1: SketchPanel 组件**

Create `src/components/SketchPanel/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

interface SketchPanelProps {
  title?: string;
  code?: string;
  children: ReactNode;
  className?: string;
}

export default function SketchPanel({ title, code, children, className = '' }: SketchPanelProps) {
  return (
    <View className={`sketch-panel ${className}`}>
      <View className='sketch-panel__tape' />
      {(title || code) && (
        <View className='sketch-panel__header'>
          {code && <Text className='sketch-panel__code'>{code}</Text>}
          {title && <Text className='sketch-panel__title'>{title}</Text>}
        </View>
      )}
      <View className='sketch-panel__body'>{children}</View>
    </View>
  );
}
```

Create `src/components/SketchPanel/index.scss`:

```scss
@import '@/styles/tokens.scss';

.sketch-panel {
  position: relative;
  background: #fff;
  border: 2px dashed rgba($ink, 0.35);
  border-radius: 8px;
  padding: 28px 24px;
  margin-bottom: 24px;
  box-shadow: 2px 2px 0 rgba($ink, 0.08);

  &__tape {
    position: absolute;
    top: -12px;
    left: 24px;
    width: 80px;
    height: 24px;
    background: rgba($sticky-yellow, 0.6);
    transform: rotate(-3deg);
    border-radius: 2px;
  }

  &__header {
    display: flex;
    align-items: baseline;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px dashed rgba($ink, 0.2);
  }

  &__code {
    font-family: $font-mono;
    font-size: 24px;
    color: $marker-red;
    margin-right: 16px;
    font-weight: bold;
  }

  &__title {
    font-size: 32px;
    font-weight: bold;
    color: $ink;
  }

  &__body {
    color: $ink;
  }
}
```

- [ ] **Step 2: SketchKpi 组件**

Create `src/components/SketchKpi/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

interface SketchKpiProps {
  label: string;
  value: ReactNode;
  unit?: string;
}

export default function SketchKpi({ label, value, unit }: SketchKpiProps) {
  return (
    <View className='sketch-kpi'>
      <Text className='sketch-kpi__label'>{label}</Text>
      <Text className='sketch-kpi__value'>
        {value}
        {unit && <Text className='sketch-kpi__unit'> {unit}</Text>}
      </Text>
    </View>
  );
}
```

Create `src/components/SketchKpi/index.scss`:

```scss
@import '@/styles/tokens.scss';

.sketch-kpi {
  display: inline-flex;
  flex-direction: column;
  padding: 16px 20px;
  background: rgba($hi-yellow, 0.4);
  border-left: 4px solid $marker-red;
  border-radius: 2px 6px 6px 2px;
  min-width: 140px;

  &__label {
    font-size: 22px;
    color: $pencil;
    margin-bottom: 6px;
  }

  &__value {
    font-family: $font-mono;
    font-size: 36px;
    font-weight: bold;
    color: $ink;
    line-height: 1.1;
  }

  &__unit {
    font-size: 22px;
    color: $pencil;
    font-weight: normal;
    margin-left: 4px;
  }
}
```

- [ ] **Step 3: MarketBadge 组件**

Create `src/components/MarketBadge/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import './index.scss';

interface MarketBadgeProps {
  market: string;
}

const COLORS: Record<string, string> = {
  SH: 'sh',
  SZ: 'sz',
  BJ: 'bj',
  HK: 'hk',
  US: 'us',
};

export default function MarketBadge({ market }: MarketBadgeProps) {
  const cls = COLORS[market] || 'other';
  return (
    <View className={`market-badge market-badge--${cls}`}>
      <Text className='market-badge__text'>{market}</Text>
    </View>
  );
}
```

Create `src/components/MarketBadge/index.scss`:

```scss
@import '@/styles/tokens.scss';

.market-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  border-radius: 4px;
  font-family: $font-mono;
  font-size: 20px;
  font-weight: bold;
  min-width: 36px;

  &--sh { background: rgba($marker-red, 0.15); color: $marker-red; }
  &--sz { background: rgba($marker-green, 0.15); color: $marker-green; }
  &--bj { background: rgba($ink, 0.1); color: $ink; }
  &--hk { background: rgba(#a020f0, 0.15); color: #a020f0; }
  &--us { background: rgba(#1e90ff, 0.15); color: #1e90ff; }
  &--other { background: rgba($pencil, 0.15); color: $pencil; }

  &__text {
    line-height: 1.4;
  }
}
```

- [ ] **Step 4: DataFreshness 组件**

Create `src/components/DataFreshness/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import type { FreshnessEntry } from '../../types/chainkb';
import { formatAgo } from '../../utils/format';
import './index.scss';

interface DataFreshnessProps {
  market?: FreshnessEntry | null;
  finance?: FreshnessEntry | null;
  variant?: 'compact' | 'full';
}

export default function DataFreshness({ market, finance, variant = 'compact' }: DataFreshnessProps) {
  if (variant === 'compact') {
    return (
      <View className='data-freshness data-freshness--compact'>
        <Text className='data-freshness__item'>
          行情 <Text className='data-freshness__time'>{formatAgo(market?.minutes_ago ?? null)}</Text>
        </Text>
        <Text className='data-freshness__sep'>·</Text>
        <Text className='data-freshness__item'>
          财务 <Text className='data-freshness__time'>{formatAgo(finance?.minutes_ago ?? null)}</Text>
        </Text>
      </View>
    );
  }

  return (
    <View className='data-freshness data-freshness--full'>
      <View className='data-freshness__row'>
        <Text className='data-freshness__label'>行情数据</Text>
        <Text className='data-freshness__value'>{formatAgo(market?.minutes_ago ?? null)}</Text>
      </View>
      <View className='data-freshness__row'>
        <Text className='data-freshness__label'>财务数据</Text>
        <Text className='data-freshness__value'>{formatAgo(finance?.minutes_ago ?? null)}</Text>
      </View>
    </View>
  );
}
```

Create `src/components/DataFreshness/index.scss`:

```scss
@import '@/styles/tokens.scss';

.data-freshness {
  &--compact {
    display: flex;
    align-items: center;
    font-size: 22px;
    color: $pencil;
  }

  &__item { color: $pencil; }
  &__time {
    color: $ink;
    font-family: $font-mono;
    margin-left: 4px;
  }
  &__sep { margin: 0 12px; color: rgba($pencil, 0.5); }

  &--full {
    background: rgba($hi-yellow, 0.3);
    border-radius: 8px;
    padding: 16px 20px;
  }

  &__row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 26px;
  }

  &__label { color: $pencil; }
  &__value {
    color: $ink;
    font-family: $font-mono;
  }
}
```

- [ ] **Step 5: TS 编译 + weapp 构建**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 两者均成功。若有错, 修到无错。

- [ ] **Step 6: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/components/SketchPanel \
        investlens-miniprogram/src/components/SketchKpi \
        investlens-miniprogram/src/components/MarketBadge \
        investlens-miniprogram/src/components/DataFreshness
git commit -m "$(cat <<'EOF'
feat(miniprogram): add SketchPanel/SketchKpi/MarketBadge/DataFreshness

Foundational display components for v1:
- SketchPanel: paper-style container with tape decoration, dashed border
- SketchKpi: highlighted KPI card with yellow background + red accent
- MarketBadge: SH/SZ/BJ/HK/US market tags with semantic colors
- DataFreshness: compact and full variants for showing data freshness

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: SubIndustryCard + 总览页

v1 默认 tab 页。展示 5 层产业链 + 子行业卡片, 点击进入层级页。

**Files:**
- Create: `src/components/SubIndustryCard/index.tsx` + `index.scss`
- Create: `src/pages/overview/index.tsx` + `index.scss` + `index.config.ts`

**Interfaces:**
- Consumes: `useTree`, `useFreshness` from `hooks/useChainKb`; `SketchPanel`, `SketchKpi`, `DataFreshness`; types `Layer`, `SubIndustry`
- Produces:
  - `<SubIndustryCard sub: SubIndustry; onClick: (groupId: string) => void>`
  - Page at route `pages/overview/index` (tabBar entry)

- [ ] **Step 1: SubIndustryCard 组件**

Create `src/components/SubIndustryCard/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import type { SubIndustry } from '../../types/chainkb';
import './index.scss';

interface SubIndustryCardProps {
  sub: SubIndustry;
  onClick: (groupId: string) => void;
}

export default function SubIndustryCard({ sub, onClick }: SubIndustryCardProps) {
  return (
    <View className='sub-card' onClick={() => onClick(sub.group_id)}>
      <Text className='sub-card__name'>{sub.name_zh}</Text>
      <View className='sub-card__meta'>
        <Text className='sub-card__group'>{sub.group_id}</Text>
        <Text className='sub-card__count'>{sub.company_count} 家</Text>
      </View>
    </View>
  );
}
```

Create `src/components/SubIndustryCard/index.scss`:

```scss
@import '@/styles/tokens.scss';

.sub-card {
  background: #fff;
  border: 1px solid rgba($ink, 0.15);
  border-left: 4px solid rgba($marker-red, 0.6);
  border-radius: 4px;
  padding: 18px 16px;
  transition: background 0.15s;

  &:active { background: rgba($hi-yellow, 0.3); }

  &__name {
    display: block;
    font-size: 26px;
    font-weight: bold;
    color: $ink;
    margin-bottom: 8px;
    line-height: 1.3;
  }

  &__meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  &__group {
    font-family: $font-mono;
    font-size: 20px;
    color: $pencil;
  }

  &__count {
    font-size: 22px;
    color: $marker-red;
    font-weight: bold;
  }
}
```

- [ ] **Step 2: overview page config**

Create `src/pages/overview/index.config.ts`:

```typescript
export default definePageConfig({
  navigationBarTitleText: 'InvestLens · 产业链',
  enablePullDownRefresh: false,
});
```

- [ ] **Step 3: overview page tsx**

Create `src/pages/overview/index.tsx`:

```tsx
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useTree, useFreshness } from '../../hooks/useChainKb';
import SketchPanel from '../../components/SketchPanel';
import SketchKpi from '../../components/SketchKpi';
import DataFreshness from '../../components/DataFreshness';
import SubIndustryCard from '../../components/SubIndustryCard';
import { fmtCount } from '../../utils/format';
import './index.scss';

export default function OverviewPage() {
  const { data: tree, loading, error } = useTree();
  const freshness = useFreshness();

  const handleSubClick = (groupId: string) => {
    Taro.navigateTo({ url: `/pages/layers/index?groupId=${encodeURIComponent(groupId)}` });
  };

  if (loading) {
    return (
      <View className='overview overview--center'>
        <Text className='overview__status'>加载中…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View className='overview overview--center'>
        <Text className='overview__status overview__status--err'>加载失败: {error}</Text>
      </View>
    );
  }

  if (!tree) return null;

  const totalCompanies = tree.layers.reduce(
    (sum, l) => sum + l.sub_industries.reduce((s, sub) => s + sub.company_count, 0),
    0,
  );
  const totalSubs = tree.layers.reduce((s, l) => s + l.sub_industries.length, 0);

  return (
    <ScrollView className='overview' scrollY>
      <View className='overview__brand'>
        <Text className='overview__brand-name'>InvestLens</Text>
        <Text className='overview__brand-sub'>投资研究 · 五层产业链拆解</Text>
        <DataFreshness market={freshness?.quotes} finance={freshness?.finance} />
      </View>

      <ScrollView className='overview__kpis' scrollX>
        <SketchKpi label='公司总数' value={fmtCount(totalCompanies)} unit='家' />
        <SketchKpi label='子行业' value={fmtCount(totalSubs)} unit='个' />
        <SketchKpi label='覆盖层' value={fmtCount(tree.layers.length)} unit='层' />
      </ScrollView>

      {tree.layers.map((layer) => {
        const layerCompanyCount = layer.sub_industries.reduce((s, sub) => s + sub.company_count, 0);
        return (
          <SketchPanel key={layer.code} code={layer.code} title={layer.name_zh}>
            <View className='overview__layer-meta'>
              <Text className='overview__layer-count'>{fmtCount(layerCompanyCount)} 家公司 · {layer.sub_industries.length} 个子行业</Text>
            </View>
            <View className='overview__sub-grid'>
              {layer.sub_industries.map((sub) => (
                <SubIndustryCard key={sub.id} sub={sub} onClick={handleSubClick} />
              ))}
            </View>
          </SketchPanel>
        );
      })}

      <View className='overview__footer'>
        <Text>InvestLens · 产业链知识库 v1</Text>
      </View>
    </ScrollView>
  );
}
```

- [ ] **Step 4: overview page scss**

Create `src/pages/overview/index.scss`:

```scss
@import '@/styles/tokens.scss';

.overview {
  height: 100vh;
  padding: 24px;

  &--center {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  &__status {
    font-size: 28px;
    color: $pencil;

    &--err { color: $marker-red; }
  }

  &__brand {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px dashed rgba($ink, 0.2);
  }

  &__brand-name {
    display: block;
    font-size: 52px;
    font-weight: bold;
    color: $ink;
    font-family: $font-mono;
    letter-spacing: -1px;
  }

  &__brand-sub {
    display: block;
    font-size: 22px;
    color: $pencil;
    margin-top: 4px;
    margin-bottom: 10px;
  }

  &__kpis {
    display: flex;
    white-space: nowrap;
    margin-bottom: 24px;

    .sketch-kpi {
      margin-right: 16px;
    }
  }

  &__layer-meta {
    margin-bottom: 14px;
  }

  &__layer-count {
    font-size: 22px;
    color: $pencil;
  }

  &__sub-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  &__footer {
    text-align: center;
    color: $pencil;
    font-size: 22px;
    padding: 24px 0;
  }
}
```

- [ ] **Step 5: TS 编译 + 构建 + devtools 验证**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。打开微信开发者工具, 加载 `investlens-miniprogram/dist`:
- 启动后默认在 "总览" tab, 看到米黄背景 + InvestLens 标题 + 3 张 KPI 卡 + 5 个 SketchPanel (每层一个)
- 每个 panel 内是 2 列子行业卡片网格, 显示中文名 + group_id + "N 家"
- 顶部"行情 N分钟前 · 财务 N分钟前" 时间正确显示
- (可选) 真机或开发者工具勾"不校验合法域名", 确认能拉到 localhost:8000 数据

- [ ] **Step 6: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/components/SubIndustryCard \
        investlens-miniprogram/src/pages/overview
git commit -m "$(cat <<'EOF'
feat(miniprogram): implement overview page (default tab)

- SubIndustryCard: 子行业入口卡 (中文名 + group_id + 公司数)
- pages/overview: 5 层 SketchPanel + 子行业 2 列网格, 顶部品牌 +
  数据新鲜度 + 3 张 KPI (公司总数/子行业数/覆盖层数), 点击卡片
  navigateTo layers?groupId=

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 层级页 (layers)

展示某子行业下所有公司, 点击进入公司详情页。

**Files:**
- Create: `src/pages/layers/index.tsx` + `index.scss` + `index.config.ts`

**Interfaces:**
- Consumes: `useSubIndustry` from hooks; `MarketBadge`; types `CompanyWithMarket`; query param `groupId`
- Produces: page at `pages/layers/index?groupId=<string>` (hidden, navigateTo only)

- [ ] **Step 1: layers page config**

Create `src/pages/layers/index.config.ts`:

```typescript
export default definePageConfig({
  navigationBarTitleText: '子行业',
});
```

- [ ] **Step 2: layers page tsx**

Create `src/pages/layers/index.tsx`:

```tsx
import { useState } from 'react';
import { View, Text, Input, ScrollView } from '@tarojs/components';
import Taro, { getCurrentInstance } from '@tarojs/taro';
import { useSubIndustry } from '../../hooks/useChainKb';
import MarketBadge from '../../components/MarketBadge';
import { fmtPrice, signedPct, fmtNum } from '../../utils/format';
import './index.scss';

export default function LayersPage() {
  const groupId = (getCurrentInstance().router?.params?.groupId) || '';
  const { data, loading, error } = useSubIndustry(groupId || null);
  const [filter, setFilter] = useState('');

  if (!groupId) {
    return <View className='layers layers--center'><Text>缺少 groupId 参数</Text></View>;
  }
  if (loading) {
    return <View className='layers layers--center'><Text>加载中…</Text></View>;
  }
  if (error) {
    return <View className='layers layers--center'><Text className='layers__err'>加载失败: {error}</Text></View>;
  }
  if (!data) return null;

  const { sub_industry: sub, companies } = data;
  const q = filter.trim().toLowerCase();
  const filtered = q
    ? companies.filter(
        (c) => c.ticker.toLowerCase().includes(q) || c.name_zh.toLowerCase().includes(q),
      )
    : companies;

  const handleRowClick = (ticker: string) => {
    Taro.navigateTo({ url: `/pages/finance/index?ticker=${encodeURIComponent(ticker)}` });
  };

  return (
    <ScrollView className='layers' scrollY>
      <View className='layers__header'>
        <Text className='layers__sub-name'>{sub.name_zh}</Text>
        <Text className='layers__sub-meta'>
          {sub.layer_code ?? ''} {sub.layer_name_zh ?? ''} · {companies.length} 家公司
        </Text>
      </View>

      <Input
        className='layers__filter'
        type='text'
        placeholder='按代码 / 简称过滤'
        value={filter}
        onInput={(e) => setFilter(e.detail.value)}
      />

      <View className='layers__table'>
        <View className='layers__row layers__row--head'>
          <Text className='layers__cell layers__cell--ticker'>代码</Text>
          <Text className='layers__cell layers__cell--name'>公司</Text>
          <Text className='layers__cell layers__cell--num'>现价</Text>
          <Text className='layers__cell layers__cell--num'>涨跌</Text>
          <Text className='layers__cell layers__cell--num'>PE</Text>
          <Text className='layers__cell layers__cell--num'>市值(亿)</Text>
        </View>

        {filtered.length === 0 && (
          <View className='layers__empty'><Text>无匹配公司</Text></View>
        )}

        {filtered.map((c) => {
          const pctVal = c.quote?.change_pct;
          const pctCls = pctVal == null ? '' : pctVal > 0 ? 'layers__cell--up' : pctVal < 0 ? 'layers__cell--down' : '';
          return (
            <View
              key={c.ticker}
              className='layers__row layers__row--data'
              onClick={() => handleRowClick(c.ticker)}
            >
              <View className='layers__cell layers__cell--ticker'>
                <MarketBadge market={c.market} />
                <Text className='layers__ticker'>{c.ticker}</Text>
              </View>
              <Text className='layers__cell layers__cell--name'>{c.name_zh}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtPrice(c.quote?.price)}</Text>
              <Text className={`layers__cell layers__cell--num ${pctCls}`}>{signedPct(pctVal)}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtNum(c.quote?.pe_ttm)}</Text>
              <Text className='layers__cell layers__cell--num'>{fmtNum(c.quote?.mcap_yi)}</Text>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}
```

- [ ] **Step 3: layers page scss**

Create `src/pages/layers/index.scss`:

```scss
@import '@/styles/tokens.scss';

.layers {
  height: 100vh;
  padding: 20px;
  background: $paper;

  &--center {
    display: flex;
    align-items: center;
    justify-content: center;
    color: $pencil;
  }

  &__err { color: $marker-red; }

  &__header {
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 2px dashed rgba($ink, 0.2);
  }

  &__sub-name {
    display: block;
    font-size: 40px;
    font-weight: bold;
    color: $ink;
  }

  &__sub-meta {
    display: block;
    font-size: 22px;
    color: $pencil;
    margin-top: 6px;
  }

  &__filter {
    background: #fff;
    border: 1px solid rgba($ink, 0.2);
    border-radius: 6px;
    padding: 14px 18px;
    font-size: 26px;
    margin-bottom: 16px;
  }

  &__table {
    background: #fff;
    border: 1px solid rgba($ink, 0.15);
    border-radius: 6px;
    overflow: hidden;
  }

  &__row {
    display: flex;
    align-items: center;
    padding: 14px 12px;
    border-bottom: 1px solid rgba($ink, 0.08);
    font-size: 24px;

    &--head {
      background: rgba($hi-yellow, 0.3);
      font-size: 20px;
      color: $pencil;
      font-weight: bold;
    }

    &--data {
      &:active { background: rgba($hi-yellow, 0.2); }
    }

    &:last-child { border-bottom: none; }
  }

  &__cell {
    flex: 1;
    padding: 0 4px;

    &--ticker {
      flex: 1.2;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    &--name {
      flex: 1.5;
      color: $ink;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    &--num {
      flex: 0.9;
      text-align: right;
      font-family: $font-mono;
      color: $ink;
    }
    &--up { color: $marker-red; }
    &--down { color: $marker-green; }
  }

  &__ticker {
    font-family: $font-mono;
    font-size: 22px;
    color: $pencil;
  }

  &__empty {
    text-align: center;
    color: $pencil;
    padding: 40px 0;
    font-size: 26px;
  }
}
```

- [ ] **Step 4: TS 编译 + 构建 + devtools 验证**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。在 devtools 里:
- 从总览页点任一子行业卡片 → 进入 layers 页
- 顶部显示子行业中文名 + 所属层 + 公司数
- 过滤框输入文字能即时筛选
- 公司列表显示代码/简称/现价/涨跌/PE/市值, 涨跌幅红绿色正确
- 点任一行 → 进入 finance 页 (下一任务才实现, 此时会报 page not found, 正常)

- [ ] **Step 5: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/pages/layers
git commit -m "$(cat <<'EOF'
feat(miniprogram): implement layers page (sub-industry company list)

Navigate-to page receiving ?groupId=. Renders sub-industry header +
ticker/name filter input + 6-column company list (market badge +
ticker + name + price + change% + PE + mcap) with red/green tinting
on change percent. Row tap navigates to finance page.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: TimeseriesTable 组件

可复用的时序数据表格, 供 finance 页的 4 个子 Tab 共用。

**Files:**
- Create: `src/components/TimeseriesTable/index.tsx` + `index.scss`

**Interfaces:**
- Produces:
  ```tsx
  interface Column {
    key: string;        // 行对象的字段名
    label: string;      // 表头显示
    width?: number;     // flex 权重 (默认 1)
    align?: 'left' | 'right';
    render?: (row: any) => ReactNode;  // 自定义渲染
  }
  interface TimeseriesTableProps {
    columns: Column[];
    rows: any[];
    emptyText?: string;
  }
  ```

- [ ] **Step 1: 创建 TimeseriesTable**

Create `src/components/TimeseriesTable/index.tsx`:

```tsx
import { View, Text, ScrollView } from '@tarojs/components';
import type { ReactNode } from 'react';
import './index.scss';

export interface Column {
  key: string;
  label: string;
  width?: number;
  align?: 'left' | 'right';
  render?: (row: Record<string, unknown>) => ReactNode;
}

interface TimeseriesTableProps {
  columns: Column[];
  rows: Record<string, unknown>[];
  emptyText?: string;
}

export default function TimeseriesTable({ columns, rows, emptyText = '暂无数据' }: TimeseriesTableProps) {
  return (
    <View className='ts-table'>
      <View className='ts-table__head'>
        {columns.map((col) => (
          <Text
            key={col.key}
            className='ts-table__head-cell'
            style={{ flex: col.width ?? 1, textAlign: col.align ?? 'left' }}
          >
            {col.label}
          </Text>
        ))}
      </View>

      {rows.length === 0 ? (
        <View className='ts-table__empty'><Text>{emptyText}</Text></View>
      ) : (
        <ScrollView scrollY className='ts-table__body'>
          {rows.map((row, i) => (
            <View key={i} className='ts-table__row'>
              {columns.map((col) => (
                <Text
                  key={col.key}
                  className='ts-table__cell'
                  style={{ flex: col.width ?? 1, textAlign: col.align ?? 'left' }}
                >
                  {col.render ? col.render(row) : formatDefault(row[col.key])}
                </Text>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

function formatDefault(v: unknown): string {
  if (v == null || v === '') return '—';
  if (typeof v === 'number') {
    if (Number.isNaN(v)) return '—';
    return String(v);
  }
  return String(v);
}
```

Create `src/components/TimeseriesTable/index.scss`:

```scss
@import '@/styles/tokens.scss';

.ts-table {
  background: #fff;
  border: 1px solid rgba($ink, 0.15);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: 800px;

  &__head {
    display: flex;
    background: rgba($hi-yellow, 0.3);
    padding: 12px 10px;
    border-bottom: 1px solid rgba($ink, 0.15);
  }

  &__head-cell {
    font-size: 20px;
    color: $pencil;
    font-weight: bold;
    padding: 0 6px;
  }

  &__body {
    flex: 1;
    overflow: auto;
  }

  &__row {
    display: flex;
    padding: 12px 10px;
    border-bottom: 1px solid rgba($ink, 0.06);
    font-size: 22px;

    &:last-child { border-bottom: none; }
  }

  &__cell {
    color: $ink;
    padding: 0 6px;
    font-family: $font-mono;
    word-break: break-all;
  }

  &__empty {
    padding: 40px 0;
    text-align: center;
    color: $pencil;
    font-size: 24px;
  }
}
```

- [ ] **Step 2: TS 编译 + 构建**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。

- [ ] **Step 3: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/components/TimeseriesTable
git commit -m "$(cat <<'EOF'
feat(miniprogram): add TimeseriesTable reusable component

Generic table with column config (key/label/width/align/render) and
default cell formatter that handles null/NaN. Sticky-style head, scroll
body, empty state. Used by finance page's 4 time-series sub-tabs.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: LatestAnalysis + BucketTabs + BucketFieldCard

3 个用于 AI 分析展示的组件。组合起来: `LatestAnalysis` 拉数据 → `BucketTabs` 选类 → `BucketFieldCard` 渲染字段。

**Files:**
- Create: `src/components/BucketFieldCard/index.tsx` + `index.scss`
- Create: `src/components/BucketTabs/index.tsx` + `index.scss`
- Create: `src/components/LatestAnalysis/index.tsx` + `index.scss`

**Interfaces:**
- Consumes: `getLatestAnalysis` from services; types `AnalysisDoc`, `BucketResult`, `FieldValue`, `BucketId`; constants `BUCKET_DISPLAY_NAMES`, `COMPANY_TYPE_LABELS`, `fieldLabel`
- Produces:
  - `<BucketFieldCard name: string; field: FieldValue>`
  - `<BucketTabs buckets: BucketResult[]; active: BucketId; onChange: (id: BucketId) => void>`
  - `<LatestAnalysis ticker: string>` (内部拉数据 + 空态 + 渲染 BucketTabs + BucketFieldCard)

- [ ] **Step 1: BucketFieldCard 组件**

Create `src/components/BucketFieldCard/index.tsx`:

```tsx
import { View, Text } from '@tarojs/components';
import type { FieldValue, Evidence } from '../../types/deepAnalysis';
import { fieldLabel } from '../../types/deepAnalysis';
import './index.scss';

interface BucketFieldCardProps {
  name: string;
  field: FieldValue;
}

const EVIDENCE_LABEL: Record<Evidence, string> = {
  strong:  '强证据',
  medium:  '中等证据',
  weak:    '弱证据',
  unknown: '未知',
};

const EVIDENCE_CLS: Record<Evidence, string> = {
  strong:  'bucket-field--strong',
  medium:  'bucket-field--medium',
  weak:    'bucket-field--weak',
  unknown: 'bucket-field--unknown',
};

function renderValue(v: FieldValue['value']): string {
  if (v == null) return '—';
  if (Array.isArray(v)) return v.length ? v.join('、') : '—';
  return String(v);
}

export default function BucketFieldCard({ name, field }: BucketFieldCardProps) {
  return (
    <View className={`bucket-field ${EVIDENCE_CLS[field.evidence]}`}>
      <View className='bucket-field__head'>
        <Text className='bucket-field__name'>{fieldLabel(name)}</Text>
        <Text className='bucket-field__evidence'>{EVIDENCE_LABEL[field.evidence]}</Text>
      </View>
      <Text className='bucket-field__value'>{renderValue(field.value)}</Text>
      {field.quote && (
        <Text className='bucket-field__quote'>「{field.quote}」</Text>
      )}
    </View>
  );
}
```

Create `src/components/BucketFieldCard/index.scss`:

```scss
@import '@/styles/tokens.scss';

.bucket-field {
  background: #fff;
  border: 1px solid rgba($ink, 0.1);
  border-left: 4px solid $pencil;
  border-radius: 4px;
  padding: 14px 16px;
  margin-bottom: 12px;

  &--strong  { border-left-color: $marker-green; }
  &--medium  { border-left-color: #f5a623; }
  &--weak    { border-left-color: $marker-red; }
  &--unknown { border-left-color: $pencil; opacity: 0.7; }

  &__head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 6px;
  }

  &__name {
    font-size: 22px;
    color: $pencil;
    font-weight: bold;
  }

  &__evidence {
    font-size: 18px;
    color: $pencil;
    background: rgba($ink, 0.05);
    padding: 2px 8px;
    border-radius: 8px;
  }

  &__value {
    display: block;
    font-size: 28px;
    color: $ink;
    line-height: 1.4;
    margin-bottom: 6px;
  }

  &__quote {
    display: block;
    font-size: 20px;
    color: $pencil;
    font-style: italic;
    background: rgba($hi-yellow, 0.3);
    padding: 6px 10px;
    border-radius: 4px;
  }
}
```

- [ ] **Step 2: BucketTabs 组件**

Create `src/components/BucketTabs/index.tsx`:

```tsx
import { View, Text, ScrollView } from '@tarojs/components';
import type { BucketId, BucketResult } from '../../types/deepAnalysis';
import { BUCKET_DISPLAY_NAMES } from '../../types/deepAnalysis';
import './index.scss';

interface BucketTabsProps {
  buckets: BucketResult[];
  active: BucketId;
  onChange: (id: BucketId) => void;
}

export default function BucketTabs({ buckets, active, onChange }: BucketTabsProps) {
  return (
    <ScrollView className='bucket-tabs' scrollX>
      {buckets.map((b) => {
        const isActive = b.bucket_id === active;
        return (
          <View
            key={b.bucket_id}
            className={`bucket-tabs__item ${isActive ? 'bucket-tabs__item--active' : ''}`}
            onClick={() => onChange(b.bucket_id)}
          >
            <Text className='bucket-tabs__label'>{BUCKET_DISPLAY_NAMES[b.bucket_id]}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}
```

Create `src/components/BucketTabs/index.scss`:

```scss
@import '@/styles/tokens.scss';

.bucket-tabs {
  display: flex;
  white-space: nowrap;
  background: #fff;
  border-bottom: 1px solid rgba($ink, 0.1);
  padding: 0 12px;
  margin-bottom: 16px;

  &__item {
    display: inline-flex;
    padding: 16px 18px;
    border-bottom: 3px solid transparent;
    &:active { opacity: 0.7; }

    &--active {
      border-bottom-color: $marker-red;
      .bucket-tabs__label { color: $ink; font-weight: bold; }
    }
  }

  &__label {
    font-size: 24px;
    color: $pencil;
  }
}
```

- [ ] **Step 3: LatestAnalysis 组件**

Create `src/components/LatestAnalysis/index.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { View, Text } from '@tarojs/components';
import { getLatestAnalysis } from '../../services/chainkb';
import type { AnalysisDoc, BucketId } from '../../types/deepAnalysis';
import { COMPANY_TYPE_LABELS } from '../../types/deepAnalysis';
import BucketTabs from '../BucketTabs';
import BucketFieldCard from '../BucketFieldCard';
import './index.scss';

interface LatestAnalysisProps {
  ticker: string;
}

export default function LatestAnalysis({ ticker }: LatestAnalysisProps) {
  const [doc, setDoc] = useState<AnalysisDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeBucket, setActiveBucket] = useState<BucketId | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getLatestAnalysis(ticker)
      .then((d) => {
        if (cancelled) return;
        setDoc(d);
        if (d && d.buckets.length > 0) setActiveBucket(d.buckets[0].bucket_id);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__status'>加载中…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__status latest-analysis__status--err'>加载失败: {error}</Text>
      </View>
    );
  }

  if (!doc) {
    return (
      <View className='latest-analysis'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__empty'>暂无 AI 分析 (需要管理员在 Web 端生成)</Text>
      </View>
    );
  }

  const activeBucketData = doc.buckets.find((b) => b.bucket_id === activeBucket);
  const fieldEntries = activeBucketData ? Object.entries(activeBucketData.fields) : [];

  return (
    <View className='latest-analysis'>
      <View className='latest-analysis__head'>
        <Text className='latest-analysis__title'>最新 AI 分析</Text>
        <Text className='latest-analysis__meta'>
          {COMPANY_TYPE_LABELS[doc.company_type]} · {doc.model_name} · {new Date(doc.analyzed_at).toLocaleDateString('zh-CN')}
        </Text>
      </View>

      <BucketTabs
        buckets={doc.buckets}
        active={activeBucket ?? doc.buckets[0].bucket_id}
        onChange={setActiveBucket}
      />

      <View className='latest-analysis__fields'>
        {fieldEntries.length === 0 ? (
          <Text className='latest-analysis__empty'>该类别暂无字段</Text>
        ) : (
          fieldEntries.map(([name, field]) => (
            <BucketFieldCard key={name} name={name} field={field} />
          ))
        )}
      </View>
    </View>
  );
}
```

Create `src/components/LatestAnalysis/index.scss`:

```scss
@import '@/styles/tokens.scss';

.latest-analysis {
  margin-top: 24px;
  padding: 20px;
  background: #fff;
  border: 2px dashed rgba($ink, 0.2);
  border-radius: 8px;

  &__head {
    margin-bottom: 12px;
  }

  &__title {
    display: block;
    font-size: 32px;
    font-weight: bold;
    color: $ink;
  }

  &__meta {
    display: block;
    font-size: 20px;
    color: $pencil;
    margin-top: 4px;
    font-family: $font-mono;
  }

  &__status {
    display: block;
    color: $pencil;
    font-size: 24px;
    margin-top: 12px;

    &--err { color: $marker-red; }
  }

  &__empty {
    display: block;
    color: $pencil;
    font-size: 22px;
    margin-top: 12px;
    font-style: italic;
  }

  &__fields {
    margin-top: 8px;
  }
}
```

- [ ] **Step 4: TS 编译 + 构建**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。

- [ ] **Step 5: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/components/BucketFieldCard \
        investlens-miniprogram/src/components/BucketTabs \
        investlens-miniprogram/src/components/LatestAnalysis
git commit -m "$(cat <<'EOF'
feat(miniprogram): add LatestAnalysis + BucketTabs + BucketFieldCard

- BucketFieldCard: 字段卡 (label + value + quote + 证据等级色条
  strong=green/medium=orange/weak=red/unknown=grey)
- BucketTabs: 6 类横向滚动切换, active 项红色下划线
- LatestAnalysis: 按 ticker 拉数据, 404→"暂无 AI 分析" 空态, 否则
  显示元信息 (类型/模型/日期) + BucketTabs + 字段卡列表

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 公司详情页 (finance)

v1 最复杂的页面: 公司卡 + 6 项 KPI + 4 子 Tab 时序数据 + 最新 AI 分析。

**Files:**
- Create: `src/pages/finance/index.tsx` + `index.scss` + `index.config.ts`

**Interfaces:**
- Consumes: `useCompany`, `useTimeseries` from hooks; `SketchKpi`, `MarketBadge`, `TimeseriesTable`, `LatestAnalysis`; types `CompanyProfile`, `TimeSeriesResponse`, `Column`; query param `ticker`

- [ ] **Step 1: finance page config**

Create `src/pages/finance/index.config.ts`:

```typescript
export default definePageConfig({
  navigationBarTitleText: '公司详情',
});
```

- [ ] **Step 2: finance page tsx**

Create `src/pages/finance/index.tsx`:

```tsx
import { useState, useMemo } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import { getCurrentInstance } from '@tarojs/taro';
import { useCompany, useTimeseries } from '../../hooks/useChainKb';
import SketchKpi from '../../components/SketchKpi';
import MarketBadge from '../../components/MarketBadge';
import TimeseriesTable, { type Column } from '../../components/TimeseriesTable';
import LatestAnalysis from '../../components/LatestAnalysis';
import { fmtPrice, signedPct, fmtNum, pct } from '../../utils/format';
import type { LockupEvent, HolderPeriod, MarginDaily, ResearchReport } from '../../types/chainkb';
import './index.scss';

type SubTab = 'lockup' | 'holders' | 'margin' | 'reports';
const SUB_TABS: { key: SubTab; label: string }[] = [
  { key: 'lockup',  label: '解禁' },
  { key: 'holders', label: '股东户数' },
  { key: 'margin',  label: '融资融券' },
  { key: 'reports', label: '研报' },
];

const LOCKUP_COLS: Column[] = [
  { key: 'date',                label: '日期',   width: 1.2 },
  { key: 'type',                label: '类型',   width: 0.8 },
  { key: 'shares_wan',          label: '股数(万)', align: 'right' },
  { key: 'ratio_pct',           label: '占比%',   align: 'right', render: (r) => pct(r.ratio_pct as number | null) },
  { key: 'mcap_wan',            label: '市值(万)', align: 'right', render: (r) => fmtNum(r.mcap_wan as number | null) },
];
const HOLDER_COLS: Column[] = [
  { key: 'end_date',           label: '截止日',  width: 1.2 },
  { key: 'holder_num',         label: '户数',    align: 'right', render: (r) => fmtNum(r.holder_num as number | null) },
  { key: 'change_ratio_pct',   label: '环比%',   align: 'right', render: (r) => signedPct(r.change_ratio_pct as number | null) },
  { key: 'avg_free_shares',    label: '人均流通', align: 'right', render: (r) => fmtNum(r.avg_free_shares as number | null) },
];
const MARGIN_COLS: Column[] = [
  { key: 'date',     label: '日期',   width: 1.2 },
  { key: 'rzye_yi',  label: '融资(亿)', align: 'right', render: (r) => fmtNum(r.rzye_yi as number | null) },
  { key: 'rqye_yi',  label: '融券(亿)', align: 'right', render: (r) => fmtNum(r.rqye_yi as number | null) },
  { key: 'rzjme_yi', label: '净买(亿)', align: 'right', render: (r) => fmtNum(r.rzjme_yi as number | null) },
];
const REPORT_COLS: Column[] = [
  { key: 'publish_date', label: '日期',   width: 1 },
  { key: 'broker',       label: '券商',   width: 1 },
  { key: 'rating',       label: '评级',   width: 0.7 },
  { key: 'title',        label: '标题',   width: 2.5 },
];

export default function FinancePage() {
  const ticker = (getCurrentInstance().router?.params?.ticker) || '';
  const { data: profile, loading, error } = useCompany(ticker || null);
  const { data: ts } = useTimeseries(ticker || null, 30);
  const [subTab, setSubTab] = useState<SubTab>('lockup');

  const subRows = useMemo<Record<string, unknown>[]>(() => {
    if (!ts) return [];
    switch (subTab) {
      case 'lockup':  return (ts.lockup  ?? []) as unknown as Record<string, unknown>[];
      case 'holders': return (ts.holders ?? []) as unknown as Record<string, unknown>[];
      case 'margin':  return (ts.margin  ?? []) as unknown as Record<string, unknown>[];
      case 'reports': return (ts.reports ?? []) as unknown as Record<string, unknown>[];
    }
  }, [ts, subTab]);

  const subCols = subTab === 'lockup' ? LOCKUP_COLS : subTab === 'holders' ? HOLDER_COLS : subTab === 'margin' ? MARGIN_COLS : REPORT_COLS;

  if (!ticker) {
    return <View className='finance finance--center'><Text>缺少 ticker 参数</Text></View>;
  }
  if (loading) {
    return <View className='finance finance--center'><Text>加载中…</Text></View>;
  }
  if (error) {
    return <View className='finance finance--center'><Text className='finance__err'>加载失败: {error}</Text></View>;
  }
  if (!profile) return null;

  const { company, quote, finance: fin, sub_industries: subs } = profile;
  const changePct = quote?.change_pct;
  const priceCls = changePct == null ? '' : changePct > 0 ? 'finance__price--up' : changePct < 0 ? 'finance__price--down' : '';

  return (
    <ScrollView className='finance' scrollY>
      <View className='finance__head'>
        <View className='finance__head-row'>
          <MarketBadge market={company.market} />
          <Text className='finance__ticker'>{company.ticker}</Text>
          <Text className='finance__name'>{company.name_zh}</Text>
        </View>
        <View className='finance__head-row'>
          <Text className={`finance__price ${priceCls}`}>{fmtPrice(quote?.price)}</Text>
          <Text className={`finance__change ${priceCls}`}>{signedPct(changePct)}</Text>
        </View>
        <Text className='finance__sub'>
          {subs.map((s) => s.name_zh).join(' / ') || '—'}
        </Text>
      </View>

      <ScrollView className='finance__kpis' scrollX>
        <SketchKpi label='PE(TTM)'  value={fmtNum(quote?.pe_ttm)} />
        <SketchKpi label='PB'       value={fmtNum(quote?.pb)} />
        <SketchKpi label='市值'     value={fmtNum(quote?.mcap_yi)} unit='亿' />
        <SketchKpi label='EPS'      value={fmtNum(fin?.eps)} />
        <SketchKpi label='ROE'      value={pct(fin?.roe_pct)} />
        <SketchKpi label='毛利率'   value={pct(fin?.gross_margin_pct)} />
      </ScrollView>

      <View className='finance__subtabs'>
        {SUB_TABS.map((t) => (
          <View
            key={t.key}
            className={`finance__subtab ${subTab === t.key ? 'finance__subtab--active' : ''}`}
            onClick={() => setSubTab(t.key)}
          >
            <Text>{t.label}</Text>
          </View>
        ))}
      </View>

      <TimeseriesTable columns={subCols} rows={subRows} emptyText={`暂无${SUB_TABS.find((t) => t.key === subTab)?.label}数据`} />

      <LatestAnalysis ticker={ticker} />

      <View className='finance__footer'>
        <Text>数据来源: 后端 chainkb / deep-analysis</Text>
      </View>
    </ScrollView>
  );
}
```

- [ ] **Step 3: finance page scss**

Create `src/pages/finance/index.scss`:

```scss
@import '@/styles/tokens.scss';

.finance {
  height: 100vh;
  padding: 20px;
  background: $paper;

  &--center {
    display: flex;
    align-items: center;
    justify-content: center;
    color: $pencil;
  }

  &__err { color: $marker-red; }

  &__head {
    background: #fff;
    padding: 20px;
    border: 2px dashed rgba($ink, 0.2);
    border-radius: 8px;
    margin-bottom: 20px;
  }

  &__head-row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 8px;

    &:last-child { margin-bottom: 0; }
  }

  &__ticker {
    font-family: $font-mono;
    font-size: 26px;
    color: $pencil;
  }

  &__name {
    font-size: 32px;
    font-weight: bold;
    color: $ink;
  }

  &__price {
    font-family: $font-mono;
    font-size: 48px;
    font-weight: bold;
    color: $ink;

    &--up { color: $marker-red; }
    &--down { color: $marker-green; }
  }

  &__change {
    font-family: $font-mono;
    font-size: 28px;
    &--up { color: $marker-red; }
    &--down { color: $marker-green; }
  }

  &__sub {
    display: block;
    font-size: 22px;
    color: $pencil;
    margin-top: 8px;
  }

  &__kpis {
    display: flex;
    white-space: nowrap;
    margin-bottom: 20px;

    .sketch-kpi { margin-right: 12px; }
  }

  &__subtabs {
    display: flex;
    background: #fff;
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 12px;
    border: 1px solid rgba($ink, 0.1);
  }

  &__subtab {
    flex: 1;
    text-align: center;
    padding: 14px 0;
    font-size: 24px;
    color: $pencil;
    border-bottom: 3px solid transparent;

    &--active {
      color: $ink;
      font-weight: bold;
      border-bottom-color: $marker-red;
      background: rgba($hi-yellow, 0.3);
    }
  }

  &__footer {
    text-align: center;
    color: $pencil;
    font-size: 20px;
    padding: 24px 0;
  }
}
```

- [ ] **Step 4: TS 编译 + 构建 + devtools 验证**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。devtools 验证:
- 从 layers 页点公司 → finance 页正常加载
- 公司卡: 市场 badge + 代码 + 简称 + 大字号现价 + 涨跌 (红/绿)
- KPI 横滚 6 项: PE/PB/市值/EPS/ROE/毛利率
- 4 子 Tab 切换不重发请求, 表格内容随 Tab 切换变化
- 空数据 Tab 显示"暂无XX数据"
- 底部 AI 分析区块: 若有数据, 显示元信息 + 6 类 tabs + 字段卡; 若无, 显示空态提示

- [ ] **Step 5: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/pages/finance
git commit -m "$(cat <<'EOF'
feat(miniprogram): implement finance page (company detail)

Navigate-to page receiving ?ticker=. Renders company header card (badge +
ticker + name + big price + change %) + 6-KPI horizontal scroll (PE/PB/
mcap/EPS/ROE/gross margin) + 4 sub-tabs (lockup/holders/margin/reports)
backed by TimeseriesTable with per-tab column config + LatestAnalysis
section at the bottom. Sub-tab switch uses already-fetched data (no
refetch).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 搜索页 + 我的页

完成最后两个 tabBar 页面。

**Files:**
- Create: `src/pages/search/index.tsx` + `index.scss` + `index.config.ts`
- Create: `src/pages/profile/index.tsx` + `index.scss` + `index.config.ts`

**Interfaces:**
- Consumes (search): `useSearch`; `MarketBadge`; types `SearchResult`
- Consumes (profile): `useFreshness`; `DataFreshness`

- [ ] **Step 1: search page config**

Create `src/pages/search/index.config.ts`:

```typescript
export default definePageConfig({
  navigationBarTitleText: '搜索',
});
```

- [ ] **Step 2: search page tsx**

Create `src/pages/search/index.tsx`:

```tsx
import { useState } from 'react';
import { View, Text, Input, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useSearch } from '../../hooks/useChainKb';
import MarketBadge from '../../components/MarketBadge';
import './index.scss';

export default function SearchPage() {
  const [q, setQ] = useState('');
  const { data, loading, error } = useSearch(q, 20, 280);

  const handleCompanyClick = (ticker: string) => {
    Taro.navigateTo({ url: `/pages/finance/index?ticker=${encodeURIComponent(ticker)}` });
  };
  const handleSubClick = (groupId: string) => {
    Taro.navigateTo({ url: `/pages/layers/index?groupId=${encodeURIComponent(groupId)}` });
  };

  const subResults = (data?.results ?? []).filter(
    (r) => r.sub_industries && r.sub_industries.length > 0,
  );
  const subSet = new Map<string, string>();
  subResults.forEach((r) => {
    r.sub_industries.forEach((s) => subSet.set(s.group_id, s.name_zh));
  });
  const subList = Array.from(subSet.entries()).slice(0, 10);

  return (
    <View className='search'>
      <Input
        className='search__input'
        type='text'
        placeholder='搜索公司代码 / 名称 / 子行业'
        confirmType='search'
        value={q}
        onInput={(e) => setQ(e.detail.value)}
        focus
      />

      <ScrollView className='search__body' scrollY>
        {!q && (
          <View className='search__hint'>
            <Text>输入关键字开始搜索</Text>
          </View>
        )}

        {loading && <View className='search__status'><Text>搜索中…</Text></View>}
        {error && <View className='search__status search__status--err'><Text>搜索失败: {error}</Text></View>}

        {data && !loading && (
          <>
            {subList.length > 0 && (
              <View className='search__group'>
                <Text className='search__group-title'>子行业 ({subList.length})</Text>
                {subList.map(([gid, name]) => (
                  <View key={gid} className='search__sub-row' onClick={() => handleSubClick(gid)}>
                    <Text className='search__sub-name'>{name}</Text>
                    <Text className='search__sub-gid'>{gid}</Text>
                  </View>
                ))}
              </View>
            )}

            <View className='search__group'>
              <Text className='search__group-title'>公司 ({data.results.length})</Text>
              {data.results.length === 0 && (
                <View className='search__empty'><Text>无匹配公司</Text></View>
              )}
              {data.results.map((r) => (
                <View
                  key={r.ticker}
                  className='search__company-row'
                  onClick={() => handleCompanyClick(r.ticker)}
                >
                  <MarketBadge market={r.market} />
                  <Text className='search__company-ticker'>{r.ticker}</Text>
                  <Text className='search__company-name'>{r.name_zh}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}
```

- [ ] **Step 3: search page scss**

Create `src/pages/search/index.scss`:

```scss
@import '@/styles/tokens.scss';

.search {
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 20px;
  background: $paper;

  &__input {
    background: #fff;
    border: 2px solid rgba($ink, 0.2);
    border-radius: 8px;
    padding: 16px 20px;
    font-size: 28px;
    margin-bottom: 16px;
  }

  &__body {
    flex: 1;
    overflow: auto;
  }

  &__hint, &__status, &__empty {
    text-align: center;
    color: $pencil;
    padding: 60px 0;
    font-size: 24px;
  }

  &__status--err { color: $marker-red; }

  &__group {
    margin-bottom: 24px;
  }

  &__group-title {
    display: block;
    font-size: 22px;
    color: $pencil;
    margin-bottom: 10px;
    border-bottom: 1px dashed rgba($ink, 0.2);
    padding-bottom: 6px;
  }

  &__sub-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #fff;
    padding: 14px 16px;
    border-radius: 4px;
    margin-bottom: 6px;
    border-left: 3px solid rgba($marker-red, 0.5);

    &:active { background: rgba($hi-yellow, 0.3); }
  }

  &__sub-name {
    font-size: 26px;
    color: $ink;
    font-weight: bold;
  }

  &__sub-gid {
    font-family: $font-mono;
    font-size: 22px;
    color: $pencil;
  }

  &__company-row {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #fff;
    padding: 14px 16px;
    border-radius: 4px;
    margin-bottom: 6px;
    border-left: 3px solid rgba($marker-green, 0.5);

    &:active { background: rgba($hi-yellow, 0.3); }
  }

  &__company-ticker {
    font-family: $font-mono;
    font-size: 24px;
    color: $pencil;
  }

  &__company-name {
    font-size: 26px;
    color: $ink;
  }
}
```

- [ ] **Step 4: profile page config + tsx + scss**

Create `src/pages/profile/index.config.ts`:

```typescript
export default definePageConfig({
  navigationBarTitleText: '我的',
});
```

Create `src/pages/profile/index.tsx`:

```tsx
import { View, Text, ScrollView } from '@tarojs/components';
import { useFreshness } from '../../hooks/useChainKb';
import SketchPanel from '../../components/SketchPanel';
import DataFreshness from '../../components/DataFreshness';
import './index.scss';

export default function ProfilePage() {
  const freshness = useFreshness();

  return (
    <ScrollView className='profile' scrollY>
      <View className='profile__brand'>
        <Text className='profile__brand-name'>InvestLens</Text>
        <Text className='profile__brand-sub'>投资研究工作台 · 小程序版 v1</Text>
      </View>

      <SketchPanel title='数据更新'>
        <DataFreshness
          variant='full'
          market={freshness?.quotes}
          finance={freshness?.finance}
        />
      </SketchPanel>

      <SketchPanel title='关于'>
        <Text className='profile__about'>
          InvestLens 是个人 A 股投资研究工作台, 提供五层产业链拆解、公司基本面与财务时序数据、AI 公司分析。小程序版 v1 聚焦产业链知识库浏览, 深度分析与数据刷新请前往 Web 端。
        </Text>
      </SketchPanel>

      <SketchPanel title='更多'>
        <View className='profile__row profile__row--disabled'>
          <Text>设置</Text><Text className='profile__row-meta'>敬请期待</Text>
        </View>
        <View className='profile__row profile__row--disabled'>
          <Text>反馈</Text><Text className='profile__row-meta'>敬请期待</Text>
        </View>
      </SketchPanel>

      <View className='profile__footer'>
        <Text>© 2026 InvestLens</Text>
      </View>
    </ScrollView>
  );
}
```

Create `src/pages/profile/index.scss`:

```scss
@import '@/styles/tokens.scss';

.profile {
  height: 100vh;
  padding: 24px;
  background: $paper;

  &__brand {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px dashed rgba($ink, 0.2);
  }

  &__brand-name {
    display: block;
    font-size: 52px;
    font-weight: bold;
    color: $ink;
    font-family: $font-mono;
    letter-spacing: -1px;
  }

  &__brand-sub {
    display: block;
    font-size: 22px;
    color: $pencil;
    margin-top: 6px;
  }

  &__about {
    display: block;
    font-size: 24px;
    color: $ink;
    line-height: 1.7;
  }

  &__row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 0;
    border-bottom: 1px solid rgba($ink, 0.06);
    font-size: 26px;
    color: $ink;

    &:last-child { border-bottom: none; }
    &--disabled { color: $pencil; }
  }

  &__row-meta {
    font-size: 22px;
    color: $pencil;
  }

  &__footer {
    text-align: center;
    color: $pencil;
    font-size: 20px;
    padding: 32px 0;
  }
}
```

- [ ] **Step 5: TS 编译 + 构建 + 全量 devtools 验证**

```bash
cd "E:\2026projects\Investment-Desk\investlens-miniprogram"
npx tsc --noEmit && npm run build:weapp 2>&1 | tail -10
```

预期: 成功。完整 smoke test (devtools):
- 总览 tab: 5 层 + 子行业卡片正常, 点击进入 layers
- layers: 公司列表渲染正常, 点公司进入 finance
- finance: 4 子 Tab 切换正常, AI 分析区块正确显示或空态
- 搜索 tab: 输入"半导"等关键字, 280ms 防抖后出结果, 分子行业/公司两组
- 我的 tab: 数据更新时间正确, 关于文字显示
- 3 个 tabBar 切换图标/文字高亮正常

- [ ] **Step 6: 提交**

```bash
cd "E:\2026projects\Investment-Desk"
git add investlens-miniprogram/src/pages/search investlens-miniprogram/src/pages/profile
git commit -m "$(cat <<'EOF'
feat(miniprogram): implement search + profile pages

- pages/search: top input + 280ms debounce, results split into
  子行业 / 公司 groups, tap navigates to layers/finance
- pages/profile: brand header + SketchPanels for data freshness
  (DataFreshness full variant), about text, placeholder rows for
  settings/feedback

Completes v1 page set per the chainkb port spec.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## 验收清单 (Definition of Done)

完成全部 10 个任务后, 验收:

- [ ] `npx tsc --noEmit` 无错误
- [ ] `npm run build:weapp` 成功 (Taro `ENABLE_INNER_HTML` 警告可忽略)
- [ ] 微信开发者工具加载 `dist/`, 5 个页面均可正常打开
- [ ] 总览 → layers → finance 下钻链路顺畅, 数据正确
- [ ] 搜索页输入有结果, 子行业/公司分类正确
- [ ] 我的页显示数据新鲜度
- [ ] 视觉与前端纸墨风格一致 (米黄背景 / 虚线边 / 黄色高亮 / 红绿涨跌色)
- [ ] 提交历史 10 个, 每个 commit 信息符合项目规范 (`feat(miniprogram): ...`)
- [ ] 后端无任何改动 (chainkb router 现成可用)

后续 (out of v1 scope): 部署后端 + 配置合法域名 + 真机预览 + 体验评分。
