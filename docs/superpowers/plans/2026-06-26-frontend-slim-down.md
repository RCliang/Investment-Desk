# Frontend Slim-Down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the frontend to a single-page app rendering `ChainKbPage` as the landing experience; remove the dark Ant Design theme, SPA router, and three deprecated feature pages.

**Architecture:** `index.html → main.tsx → <App /> → <ChainPage /> → <ChainKbPage />`. No router, no `ConfigProvider`, no `<Layout>` chrome. The sketch-styled `.chainkb-root` paper background owns the full viewport.

**Tech Stack:** React 18 + TypeScript 5.6 (strict) + Vite 5.4 + axios. Removing: `antd`, `@ant-design/icons`, `react-router-dom`. Keeping: `react-markdown` (MarkdownRenderer spare part).

## Global Constraints

- Working directory: `E:\2026projects\Investment-Desk`
- Frontend root: `frontend/`
- TypeScript strict mode + `noUnusedLocals` + `noUnusedParameters` (`tsconfig.app.json`)
- Build must stay green after every task: `cd frontend && npm run build` exits 0
- Lint must stay green after every task: `cd frontend && npm run lint` exits 0
- Backend completely untouched (no `routers/`, `services/`, or `main.py` edits)
- `frontend/src/chainkb/**` completely untouched
- `frontend/src/components/MarkdownRenderer.tsx` preserved → `react-markdown` must stay in `package.json`
- `frontend/src/pages/ChainPage.tsx` preserved as thin wrapper (future router revival point)
- Spec: `docs/superpowers/specs/2026-06-26-frontend-slim-down-design.md`

---

### Task 1: Rewrite App.tsx to drop router + antd providers

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `App` default-exports a function returning `<ChainPage />` (no props).

- [ ] **Step 1: Verify current build is green (baseline)**

Run: `cd frontend && npm run build`
Expected: exits 0; produces `dist/`. This confirms the starting point is clean.

- [ ] **Step 2: Rewrite App.tsx**

Replace the entire contents of `frontend/src/App.tsx` with:

```tsx
import ChainPage from './pages/ChainPage';

/**
 * Single-page entry. The dark Ant Design ConfigProvider and BrowserRouter
 * have been removed; ChainKbPage owns the full viewport with its own
 * `.chainkb-root` paper theme.
 *
 * To revive routing: reinstall react-router-dom, wrap this return value
 * in <BrowserRouter><Routes>...</Routes></BrowserRouter>, and add routes.
 * ChainPage is preserved at src/pages/ChainPage.tsx as the /chain target.
 */
export default function App() {
  return <ChainPage />;
}
```

- [ ] **Step 3: Verify build passes**

Run: `cd frontend && npm run build`
Expected: exits 0. (DataPage/ReportPage/PlanPage/Layout still exist as orphan files and still compile because antd/react-router are still installed.)

- [ ] **Step 4: Verify lint passes**

Run: `cd frontend && npm run lint`
Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/App.tsx
git commit -m "refactor(frontend): App.tsx 直接渲染 ChainPage，移除 router 与 antd 主题包裹"
```

---

### Task 2: Delete the 4 orphaned files

**Files:**
- Delete: `frontend/src/pages/DataPage.tsx`
- Delete: `frontend/src/pages/ReportPage.tsx`
- Delete: `frontend/src/pages/PlanPage.tsx`
- Delete: `frontend/src/components/Layout.tsx`

**Interfaces:**
- Consumes: Task 1 (these files are no longer referenced from `App.tsx`).
- Produces: `frontend/src/pages/` contains only `ChainPage.tsx`; `frontend/src/components/` contains only `MarkdownRenderer.tsx`.

- [ ] **Step 1: Confirm no live imports remain**

Run: `cd frontend && grep -rE "from '.*(/|-)(DataPage|ReportPage|PlanPage|Layout)'" src/`
Expected: empty output. (Task 1 removed the only importer — `App.tsx`. If anything matches, fix the caller before deleting.)

- [ ] **Step 2: Delete the files**

```bash
cd "E:/2026projects/Investment-Desk/frontend/src"
rm pages/DataPage.tsx pages/ReportPage.tsx pages/PlanPage.tsx components/Layout.tsx
```

- [ ] **Step 3: Verify build passes**

Run: `cd frontend && npm run build`
Expected: exits 0.

- [ ] **Step 4: Verify lint passes**

Run: `cd frontend && npm run lint`
Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add -A frontend/src/pages frontend/src/components
git commit -m "refactor(frontend): 删除 DataPage/ReportPage/PlanPage/Layout"
```

---

### Task 3: Trim services/api.ts to 5 chainkb functions

**Files:**
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: `../types/chainkb` type definitions (untouched).
- Produces: `services/api.ts` exports only `getChainKbTree`, `getChainKbSubIndustry`, `getChainKbCompany`, `getChainKbTimeseries`, `searchChainKb`, plus type re-exports of `TreeResponse`, `SubIndustryDetail`, `CompanyProfile`, `TimeSeriesResponse`, `SearchResponse`.

- [ ] **Step 1: Verify chainkb is the only consumer of api.ts**

Run: `cd frontend && grep -rE "from ['\"](\.\./)+services/api['\"]|from ['\"]\./services/api['\"]" src/`
Expected: only `src/chainkb/hooks/useChainKb.ts` matches. If anything else matches, it's a legacy caller that will break — fix or delete it first.

- [ ] **Step 2: Rewrite api.ts**

Replace the entire contents of `frontend/src/services/api.ts` with:

```typescript
import axios from 'axios';

const api = axios.create({ baseURL: 'http://localhost:8000' });

// --- Chain Knowledge Base (v1) ---
import type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
} from '../types/chainkb';
export type {
  TreeResponse,
  SubIndustryDetail,
  CompanyProfile,
  TimeSeriesResponse,
  SearchResponse,
};

export async function getChainKbTree(): Promise<TreeResponse> {
  const { data } = await api.get<TreeResponse>('/api/chainkb/tree');
  return data;
}

export async function getChainKbSubIndustry(groupId: string): Promise<SubIndustryDetail> {
  const { data } = await api.get<SubIndustryDetail>(`/api/chainkb/sub_industries/${groupId}`);
  return data;
}

export async function getChainKbCompany(ticker: string): Promise<CompanyProfile> {
  const { data } = await api.get<CompanyProfile>(`/api/chainkb/companies/${ticker}`);
  return data;
}

export async function getChainKbTimeseries(
  ticker: string,
  opts: { types?: string[]; limit?: number } = {},
): Promise<TimeSeriesResponse> {
  const params: Record<string, string> = {};
  if (opts.types && opts.types.length) params.types = opts.types.join(',');
  if (opts.limit != null) params.limit = String(opts.limit);
  const { data } = await api.get<TimeSeriesResponse>(
    `/api/chainkb/companies/${ticker}/timeseries`,
    { params },
  );
  return data;
}

export async function searchChainKb(q: string, limit = 20): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/api/chainkb/search', {
    params: { q, limit },
  });
  return data;
}
```

- [ ] **Step 3: Verify build passes**

Run: `cd frontend && npm run build`
Expected: exits 0.

- [ ] **Step 4: Verify no legacy function references remain**

Run: `cd frontend && grep -rE "analyzeChain|getChainHistory|queryData|getStockQuote|getStockHist|getStockFinancial|getStockReports|getStockBlocks|getStockFundFlow|generateReport|listReports|getReport|createPlan|listPlans|updatePlan|deletePlan" src/`
Expected: empty output.

- [ ] **Step 5: Verify lint passes**

Run: `cd frontend && npm run lint`
Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/services/api.ts
git commit -m "refactor(frontend): 精简 services/api.ts，仅保留 5 个 chainkb 函数"
```

---

### Task 4: Uninstall antd / @ant-design/icons / react-router-dom

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: Tasks 1–3 (no source file imports the packages being removed).
- Produces: `package.json` `dependencies` lists only `axios`, `react`, `react-dom`, `react-markdown`.

- [ ] **Step 1: Confirm no source imports the packages**

Run: `cd frontend && grep -rE "from ['\"]antd['\"]|from ['\"]@ant-design/icons['\"]|from ['\"]react-router-dom['\"]|from ['\"]react-router['\"]" src/`
Expected: empty. If anything matches, stop and reconcile before uninstalling.

- [ ] **Step 2: Uninstall**

Run: `cd frontend && npm uninstall antd @ant-design/icons react-router-dom`
Expected: exits 0; `package.json` and `package-lock.json` updated.

- [ ] **Step 3: Verify react-markdown is still installed**

Run: `cd frontend && grep "\"react-markdown\"" package.json`
Expected: one match line, e.g. `"react-markdown": "^10.1.0",`. (MarkdownRenderer.tsx depends on it.)

- [ ] **Step 4: Verify build passes**

Run: `cd frontend && npm run build`
Expected: exits 0; bundle main JS chunk meaningfully smaller than the Task 1 baseline.

- [ ] **Step 5: Verify lint passes**

Run: `cd frontend && npm run lint`
Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/package.json frontend/package-lock.json
git commit -m "refactor(frontend): 卸载 antd / @ant-design/icons / react-router-dom"
```

---

### Task 5: Clean dark-theme residue from index.css

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: `index.css` contains no dark-theme hardcoded colors. The sketch dashboard's `.chainkb-root` rule (in `chainkb.css`) sets the real background.

- [ ] **Step 1: Verify current contents**

Run: read `frontend/src/index.css`.

Expected current contents (this is the baseline — must match before editing):

```css
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background: #0d1117;
}
```

If the file has drifted from this baseline, re-read it and adapt Step 2's edit to the current state.

- [ ] **Step 2: Remove the dark background declaration**

In `frontend/src/index.css`, delete the line `  background: #0d1117;` so the file becomes:

```css
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
}
```

Leave `margin: 0`, `min-width`, and `min-height` alone — they're generic resets that don't conflict with the sketch theme. The sketch dashboard's `.chainkb-root` selector supplies the actual paper background.

- [ ] **Step 3: Verify build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: both exit 0.

- [ ] **Step 4: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/index.css
git commit -m "refactor(frontend): 清理 index.css 中的 dark-theme 背景色"
```

---

### Task 6: End-to-end smoke test

**Files:**
- None (verification only; no commits).

- [ ] **Step 1: Start backend**

Run (terminal A, foreground):
```bash
cd backend
uvicorn app.main:app --port 8000
```
Expected: `Uvicorn running on http://127.0.0.1:8000`; application startup completes without error.

- [ ] **Step 2: Start frontend dev server**

Run (terminal B, foreground):
```bash
cd frontend
npm run dev
```
Expected: Vite ready on http://localhost:5173; no module-resolution errors in output.

- [ ] **Step 3: Open http://localhost:5173 and verify overall shape**

Expected:
- Browser loads directly into the sketch dashboard (no router redirect flash, no `/chain` navigation).
- Paper-textured background and hand-drawn fonts render.
- No dark Ant Design chrome anywhere; no header bar, no sider menu.

- [ ] **Step 4: Verify tab 00 总览**

- 4 KPI tiles render with real numbers (~339 companies, ~48 sub-industries, 5 layers, 5 markets).
- Topology SVG shows 5 layer bubbles connected by dashed arrows.
- Distribution chart shows 5 bars with hatched fills.
- Sub-industry grid shows ~48 cards grouped by layer.
- Click any sub-industry card → switches to tab 01 with that group pre-selected.

- [ ] **Step 5: Verify tab 01 产业链层级**

- 5 layer tabs at top; default first layer selected.
- 3 columns (上游 U / 中游 M / 下游 D) populated based on `group_id` suffix.
- Click any sub-industry card → companies table below populates with real tickers.
- Click any company row → switches to tab 03 with that ticker pre-loaded.

- [ ] **Step 6: Verify tab 03 财务拆解**

- Default ticker `688256` (寒武纪) loads automatically.
- KPI row shows price / PE_TTM / PB / mcap / EPS / ROE / revenue.
- 4 time-series tabs (解禁 / 股东 / 融资融券 / 研报) render row counts matching the backend response.
- Concepts cloud shows tags.
- Search bar: type `寒武` → dropdown shows 寒武纪; click → KPI row updates.

- [ ] **Step 7: Final residual-import sweep**

Run: `cd frontend && grep -rE "antd|@ant-design|react-router" src/`
Expected: empty output.

Run: `cd frontend && grep -rE "react-markdown" src/`
Expected: only `src/components/MarkdownRenderer.tsx` matches.

- [ ] **Step 8: Inspect bundle size**

Run: `cd frontend && npm run build`
Expected: main JS chunk < 400 KB minified (down from ~1.2 MB at Task 1 baseline). The Vite `>500 kB` warning may still appear if `react-markdown`'s deps push it over; acceptable per spec.

(No commit — verification only.)

---

## Self-Review Notes

- **Spec coverage**: every item in the spec's "File Changes" / "Verification" sections maps to a task step.
- **Ordering safety**: Task 1 rewrites `App.tsx` *before* Task 2 deletes the orphaned pages, so the build stays green at every commit. Task 4 (uninstall) runs *after* Task 2 (delete) and Task 3 (trim), guaranteeing no live imports remain when the packages leave.
- **No placeholders**: every code block is complete; every grep has an exact expected output.
- **Type/name consistency**: `getChainKbTree` / `getChainKbSubIndustry` / `getChainKbCompany` / `getChainKbTimeseries` / `searchChainKb` are the names used in both `useChainKb.ts` (consumer) and the rewritten `api.ts` (producer).
- **Conditional tasks**: none. `index.css` was inspected up-front and confirmed to contain exactly the `#0d1117` line that Task 5 removes.
