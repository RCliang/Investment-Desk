# InvestLens 小程序版 v1 — 产业链知识库移植

**日期**: 2026-07-08
**作者**: Dong Liang + Claude
**状态**: Approved → 待写实施计划

## 背景

仓库已有两份代码:

- `frontend/` — React 18 + TypeScript + Vite 的 Web 版投资研究工作台, 包含「产业链知识库」和「公司深度分析」两大模块, 纸墨手绘设计风格
- `investlens-miniprogram/` — Taro 3.5.7 + React 18 + TypeScript 脚手架, 仅有一个简陋的产业链页面骨架, 仍在使用 axios (未改造为 `Taro.request`), 无认证 / 无图表 / 无自定义字体 / 无深度分析

本次目标: **把 Web 端的「产业链知识库」模块完整移植到小程序**, 让用户能在微信里随时浏览 5 层产业链、子行业下的公司列表、单公司的时序数据与最新 AI 分析。

## 非目标 (v1 明确不做)

| 不做项 | 原因 |
|-------|------|
| 深度分析 4 步流水线 (研报搜索 / OSS 下载 / MinerU 解析 / AI 分析) | 涉及 PDF 下载 / SSE / MinerU 轮询, 小程序环境复杂, 使用场景少 |
| SSE 流式 | 小程序不原生支持 fetch ReadableStream, 改 WebSocket 成本高, v1 暂不需要 |
| 管理员认证 (`AdminAuthContext` / `AdminLoginModal`) | chainkb 全公开, 无需 token; AI 分析在小程序里只展示最新一条, 不新建 |
| 手写字体加载 (Caveat / Patrick Hand) | 字体文件 1-3MB, 包体积成本高, 用系统默认字体代替 |
| SVG 拓扑图 | 小程序不支持 SVG, 改用层级卡片列表传达同样信息 |
| ECharts 时序图表 | 表格已能承载时序数据, 减少依赖 |
| 历史分析列表 | 只展示最新一条 AI 分析, 简化交互 |
| Markdown 渲染器 (复刻 `MarkdownRenderer`) | 没有深度分析就不需要渲染流式 LLM 输出 |
| 跨标签页同步 (前端 `storage` 事件) | 小程序不适用 |

## 关键决策

### 1. 功能范围: 只做 ChainKb

| 选项 | 取舍 |
|------|------|
| 只做产业链知识库 (本设计采纳) | 价值最高, 工作量可控, 避开 SSE / 管理员 / PDF 等小程序痛点 |
| ChainKb + 只读深度分析 (查看历史) | 多一层管理员登录流程, v1 暂不需要 |
| 全功能对等 | SSE 在小程序里需要降级为轮询 / WebSocket, 工作量最大 |

### 2. 视觉设计: 保留纸墨视觉, 简化字体

| 选项 | 取舍 |
|------|------|
| 保留视觉 + 简化字体 (本设计采纳) | 米黄背景 / 虚线边 / 黄色高亮 / 便利贴等视觉语言保留; 手写字体用系统默认代替 |
| 完全复刻 (含 Caveat / Patrick Hand) | 字体文件 1-3MB, 包体积 / 性能成本高 |
| 原生 WeUI 设计 | 与前端差异大, 失去产品辨识度 |

设计 token (SCSS 变量, 复刻前端 CSS 变量值):

```scss
$paper:        #fbf9f4;
$ink:          #1a2b4a;
$pencil:       #5a6a85;
$hi-yellow:    #fff3a8;
$marker-red:   #e85a4f;
$marker-green: #3a8a5a;
$sticky-yellow:#ffe97a;

// 字体: 系统默认 (不加载手写字体)
$font-base: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
$font-mono: "SF Mono", "JetBrains Mono", Consolas, monospace;
```

视觉技巧:
- 虚线边框: `border: 2rpx dashed rgba($ink, 0.4)`
- Tape 装饰: 伪元素 + `background: rgba($sticky-yellow, 0.6)` + `transform: rotate(-3deg)`
- 黄色高亮: `linear-gradient(transparent 60%, rgba($hi-yellow, 0.7) 60%)`
- 便利贴: 纯色背景 + `box-shadow` + 微小 `transform: rotate`

### 3. 后端访问: 部署 + 域名白名单

| 选项 | 取舍 |
|------|------|
| 部署后端 + 配置合法域名 (本设计采纳) | 真机可用, 生产级方案, 需 HTTPS + 在小程序后台配置 request 合法域名 |
| 仅开发者工具本地调试 | 真机不可用, 只适合早期实验 |
| 先 H5 调试后期适配 weapp | 不受域名限制, 但目标平台不明朗 |

`config/index.js` 通过 env 区分 dev / prod:
- dev: `http://localhost:8000` (微信开发者工具勾选"不校验合法域名")
- prod: `https://<configured-domain>` (在小程序后台 request 合法域名里配置)

### 4. 导航结构: 多页下钻 + 底部 tabBar

| 选项 | 取舍 |
|------|------|
| 多页下钻 + 底部 tabBar (本设计采纳) | 每页职责单一, 加载快, 符合小程序习惯 |
| 页内 3-Tab 横向切换 | Tab 切换含义尴尬 (没下钻时显示入口说明) |
| Tab 同屏 (复刻前端) | 单页太重, 首屏白屏时间长 |

底部 tabBar 3 项: `总览` / `搜索` / `我的`; 层级页和公司页通过 `Taro.navigateTo` 进入, 不在 tabBar 里。

## 架构

### 目录结构

```
investlens-miniprogram/src/
├── app.config.ts              # tabBar + pages 注册
├── app.ts                     # 全局入口
├── app.scss                   # 全局样式 + 设计 token 引入
├── pages/
│   ├── overview/              # 总览 tab (默认页)
│   ├── search/                # 搜索 tab
│   ├── profile/               # 我的 tab
│   ├── layers/                # 子行业下钻页 (navigateTo)
│   └── finance/               # 公司详情页 (navigateTo)
├── components/
│   ├── SketchPanel/           # 纸张式容器
│   ├── SketchKpi/             # KPI 卡片
│   ├── SubIndustryCard/       # 子行业入口卡
│   ├── MarketBadge/           # SH/SZ/BJ/HK/US 标识
│   ├── DataFreshness/         # 数据刷新时间
│   ├── LatestAnalysis/        # AI 分析包装 (拉数据 + 空态)
│   ├── BucketTabs/            # AI 分析 6 类横向切换
│   ├── BucketFieldCard/       # 字段卡 (含证据等级)
│   └── TimeseriesTable/       # 自定义时序表格
├── services/
│   ├── request.ts             # Taro.request 封装 (baseURL + 错误处理)
│   └── chainkb.ts             # 7 个 chainkb API 函数
├── hooks/
│   └── useChainKb.ts          # 6 个数据获取 hook
├── utils/
│   └── format.ts              # fmtNum / pct / marketOf 等纯函数 (从前端复制)
├── types/
│   └── chainkb.ts             # 已有, 保留 (必要时按后端响应校准)
└── styles/
    └── tokens.scss            # 纸墨调色板变量
```

清理: 删除现有 `src/pages/chain/` 和 `src/pages/index/`, 删除 `src/services/api.ts` (axios 版), 用新的 `services/request.ts` + `services/chainkb.ts` 替换。`types/chainkb.ts` 保留。

### API 服务层

`services/request.ts` — `Taro.request` 封装:

- baseURL 来自 `config/index.js` env 注入
- 统一错误处理: 网络错误 / 非 2xx → 抛 `Error` 含 message
- 超时 15s, 默认 GET
- v1 **不加 auth 头** (chainkb 全公开), 但封装结构保留, 后续可插

`services/chainkb.ts` — 7 个函数 (路径以 `backend/app/routers/chainkb.py` 实际定义为准, 实施阶段需先对齐):

| 函数 | HTTP | 用途 |
|------|------|------|
| `getTree()` | GET `/chainkb/tree` | 5 层全树 |
| `getSubIndustry(groupId)` | GET `/chainkb/sub-industry/{id}` | 子行业 + 公司列表 |
| `getCompany(ticker)` | GET `/chainkb/company/{ticker}` | 公司 profile + quote + finance |
| `getTimeseries(ticker, opts)` | GET `/chainkb/timeseries/{ticker}` | 解禁 / 股东 / 融资融券 / 研报 |
| `search(q, limit)` | GET `/chainkb/search` | 子行业 + 公司搜索 |
| `getFreshness()` | GET `/chainkb/freshness` | 数据时间戳 |
| `getLatestAnalysis(ticker)` | GET `/chainkb/latest-analysis/{ticker}` | 最新 AI 分析 (只读) |

### Hooks (`hooks/useChainKb.ts`)

复刻前端 `frontend/src/chainkb/hooks/useChainKb.ts` 的 6 个 hook:

| Hook | 行为 |
|------|------|
| `useTree()` | 一次性拉取, 缓存到内存 / storage |
| `useSubIndustry(groupId)` | groupId 变化时拉取 |
| `useCompany(ticker)` | ticker 变化时拉取 |
| `useTimeseries(ticker)` | ticker 变化时拉 (4 类一次返回) |
| `useSearch(q, limit, delay)` | 300ms debounce, 空字符串不触发 |
| `useFreshness()` | 60s 轮询 |

每个 hook 返回 `{ data, loading, error }` 三态。

## 页面规格

### 1. 总览页 (`pages/overview/`)

- 顶部: `InvestLens` 品牌 + `DataFreshness` 组件 (market / finance 最近更新时间)
- KPI 区 (横向滚动 3 张 `SketchKpi`): 公司总数 / 子行业总数 / 覆盖层数
- 5 个 `SketchPanel`, 每个 = 一层产业链:
  - 标题行: 层 code (`00`/`01`/...) + 层中文名 + 该层公司数
  - 内部: `SubIndustryCard` 网格 (每行 2 列), 显示子行业中文名 + 公司数
  - 点卡片 → `Taro.navigateTo({ url: '/pages/layers/index?groupId=xxx' })`
- **不做 SVG 拓扑图** (用层级卡片列表传达同样信息)

### 2. 搜索页 (`pages/search/`)

- 顶部搜索框 (Taro `Input` + `confirm-type="search"`)
- 防抖 300ms, 空字符串不触发
- 结果按类型分组显示: 子行业 / 公司
- 点子行业 → layers 页; 点公司 → finance 页
- 历史搜索 (可选, v1 可省略)

### 3. 我的页 (`pages/profile/`)

- `DataFreshness` 完整卡片 (market / finance 两个时间戳)
- "关于 InvestLens" 区块 (简介 + 后端版本号)
- 预留: 设置 / 反馈入口 (v1 占位不实现)

### 4. 层级页 (`pages/layers/index?groupId=xxx`)

- 顶部: 子行业中文名 + 所属层 + 公司数
- 公司列表 (自定义 `View` + `flex`, 非原生 table):
  - 每行: `MarketBadge` + 代码 + 简称 + 现价 + 涨跌幅% + PE + 市值
  - 涨跌幅正负用 `marker-red/green` 区分
  - 行高压缩, 信息密度优先
- 顶部搜索过滤 (按代码 / 简称)
- 点行 → `Taro.navigateTo({ url: '/pages/finance/index?ticker=xxx' })`

### 5. 公司详情页 (`pages/finance/index?ticker=xxx`)

- 顶部公司卡: `MarketBadge` + 代码 + 简称 + 所属行业 + 实时价 + 涨跌
- 基本面 KPI 行 (6 个 `SketchKpi` 横向滚动): PE_TTM / PB / 市值 / EPS / ROE / 毛利率
- **4 个时序子 Tab** (顶部 segment): 解禁 / 股东户数 / 融资融券 / 研报
  - 切换不发新请求, 数据一次性拉 (`getChainKbTimeseries` 返回 4 类)
  - 每个 Tab 用 `TimeseriesTable` 渲染, 空数据有占位
- **最新 AI 分析区块** (`LatestAnalysis` 组件):
  - 调 `getLatestAnalysis(ticker)`
  - 无数据: 显示 "暂无 AI 分析 (需要管理员在 Web 端生成)"
  - 有数据: `BucketTabs` (6 类) + `BucketFieldCard` 列表

## 组件清单

| 组件 | 职责 | 关键 props |
|------|------|-----------|
| `SketchPanel` | 纸张式容器 (米黄底 + 虚线边 + tape 角) | `title`, `children` |
| `SketchKpi` | KPI 卡 | `label`, `value`, `unit?` |
| `SubIndustryCard` | 子行业入口卡 | `sub: SubIndustry`, `onClick` |
| `MarketBadge` | 市场标识 | `market: 'SH'\|'SZ'\|'BJ'\|'HK'\|'US'` |
| `DataFreshness` | 数据时间指示 | `market`, `finance` 时间戳 |
| `LatestAnalysis` | AI 分析包装 (拉数据 + 空态) | `ticker` |
| `BucketTabs` | 6 类横向切换 | `buckets`, `active`, `onChange` |
| `BucketFieldCard` | 字段卡 (名称 + 值 + 证据等级) | `field: FieldValue` |
| `TimeseriesTable` | 自定义表格 (表头 + 行 + 横滚) | `columns`, `rows` |

每个组件目录包含 `index.tsx` + `index.scss` (+ 必要时 `index.config.ts`)。

格式化纯函数 (fmtNum / pct / marketOf 等) 从 `frontend/src/...` 复制到 `src/utils/format.ts`。

## app.config.ts 配置

```ts
export default defineAppConfig({
  pages: [
    'pages/overview/index',   // tabBar 项必须最先
    'pages/search/index',
    'pages/profile/index',
    'pages/layers/index',
    'pages/finance/index',
  ],
  tabBar: {
    color: '#5a6a85',
    selectedColor: '#1a2b4a',
    backgroundColor: '#fbf9f4',
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
  },
});
```

tabBar 图标 v1 可先省略 (微信允许无图标 tabBar); 后续若需要, 准备 6 张 81x81 PNG (3 tab × 普通/选中) 放入 `src/assets/tabbar/`。

## 风险与开放问题

| 风险 | 缓解 |
|------|------|
| 后端 chainkb 路由实际路径可能与本设计假设的 `/chainkb/...` 不一致 | 实施第 3 步前先读 `backend/app/routers/chainkb.py` 对齐 |
| Taro 3.5.7 在某些场景有 `ENABLE_INNER_HTML is not defined` 编译警告 (见 miniprogram README) | 业务逻辑先完成, 编译警告若不影响功能可后置; 必要时考虑 Taro 3.x 内补丁 |
| 真机环境 HTTPS 域名 / ICP 备案要求 | 部署阶段处理, 不在 v1 代码范围 |
| `getChainKbTimeseries` 响应体较大 (4 类数据) | 一次性拉取后切换 Tab 不重发; 必要时按 Tab 懒加载 (前端未做, v1 保持一致) |
| 6 个 hook 在小程序里无 React Query, 需要手写状态机 | 直接复刻前端的 `useEffect + useState` 三态模式, 不引入新依赖 |

## 实施顺序

10 步建议:

1. 设计 token + 全局样式 (`styles/tokens.scss` + `app.scss`)
2. 清理旧骨架 + 配 `app.config.ts` (3 tab + 2 隐藏页)
3. `services/request.ts` + `services/chainkb.ts` (先读后端 router 对齐路径) + `utils/format.ts`
4. `hooks/useChainKb.ts` (6 个 hook)
5. 基础容器组件 (`SketchPanel` / `SketchKpi` / `MarketBadge` / `DataFreshness`)
6. 总览页 (overview)
7. 层级页 (layers) + `SubIndustryCard`
8. 公司页 (finance) + 子组件 (`TimeseriesTable` / `LatestAnalysis` / `BucketTabs` / `BucketFieldCard`)
9. 搜索页 (search)
10. 我的页 (profile) + 真机调试 + 体验优化

## 范围对照表

| 改 | 不改 |
|---|---|
| 新建 `investlens-miniprogram/src/pages/{overview,search,profile,layers,finance}/` | `frontend/` 任何文件 |
| 新建 `investlens-miniprogram/src/components/{SketchPanel,SketchKpi,SubIndustryCard,MarketBadge,DataFreshness,LatestAnalysis,BucketTabs,BucketFieldCard,TimeseriesTable}/` | `backend/` 任何文件 (chainkb 路由已存在, 只读取对齐) |
| 新建 `investlens-miniprogram/src/services/{request,chainkb}.ts` | 后端 chainkb 业务逻辑 |
| 新建 `investlens-miniprogram/src/hooks/useChainKb.ts` | 后端路由 / 数据模型 |
| 新建 `investlens-miniprogram/src/utils/format.ts` | |
| 新建 `investlens-miniprogram/src/styles/tokens.scss` | |
| 重写 `investlens-miniprogram/src/app.config.ts` | Taro / React / TS 版本 |
| 重写 `investlens-miniprogram/src/app.scss` | |
| 删除 `investlens-miniprogram/src/pages/{chain,index}/` | `investlens-miniprogram/src/types/chainkb.ts` (保留, 必要时校准) |
| 删除 `investlens-miniprogram/src/services/api.ts` (axios 版) | |
