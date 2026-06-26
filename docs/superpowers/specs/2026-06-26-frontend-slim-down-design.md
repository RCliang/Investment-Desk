# Frontend Slim-Down: ChainKbPage as the Sole Landing Page

**Date**: 2026-06-26
**Status**: Approved (design phase)
**Supersedes**: prior 4-route dark-frontend layout (`ChainPage` LLM view + `DataPage` + `ReportPage` + `PlanPage`)

## Goal

Strip the frontend down to a single-page application that renders the
sketch-aesthetic `ChainKbPage` (already built, consuming `/api/chainkb/*`)
as the landing experience. Remove the dark Ant Design theme, the SPA
router, and the three deprecated feature pages.

The backend is explicitly **out of scope** — the four legacy routers
(`chain` / `data` / `report` / `plan`) stay mounted in `app/main.py`
even though no frontend code calls them anymore. They cost nothing to
keep and make future revival trivial.

## Final Shape

```
index.html → main.tsx → <App /> → <ChainPage /> → <ChainKbPage />
```

- No `BrowserRouter`, no route table.
- No `ConfigProvider`, no Ant Design theme.
- No `<Layout>` chrome (dark sider menu gone).
- `ChainKbPage` owns the full viewport; its `.chainkb-root` paper background
  is the entire visual surface.

Bundle expected to drop from ~1.2 MB → ~300 KB minified (75% reduction;
the ~100 KB ceiling vs. the previously projected ~200 KB comes from
keeping `react-markdown` so `MarkdownRenderer.tsx` still compiles).

## File Changes

### Delete (4 files)

| File | Reason |
|---|---|
| `src/pages/DataPage.tsx` | Legacy data-query UI; superseded. |
| `src/pages/ReportPage.tsx` | Legacy streaming-report UI; superseded. |
| `src/pages/PlanPage.tsx` | Legacy investment-plan UI; superseded. |
| `src/components/Layout.tsx` | Ant Design `<Layout>` + sider `<Menu>`; cannot compile after `antd` / `react-router-dom` are uninstalled (imports `Outlet`, `useNavigate`, `useLocation`, `Layout`, `Menu`, `Typography`, 4 icon components). |

### Keep as-is

| File | Notes |
|---|---|
| `src/pages/ChainPage.tsx` | Thin wrapper around `<ChainKbPage />`. Preserved so a future router revival can use it as the `/chain` route target without renaming. Currently has zero non-React imports — compiles cleanly with the slimmed dependency set. |
| `src/components/MarkdownRenderer.tsx` | Spare part for future use. **Requires keeping `react-markdown` in `package.json`** — otherwise the `import ReactMarkdown from 'react-markdown'` line fails TypeScript compilation. |
| `src/chainkb/**` | The entire sketch dashboard (host + 3 screens + hooks + components + scoped CSS). Untouched. |
| `src/types/chainkb.ts` | Untouched. |
| `src/main.tsx`, `index.html`, `vite.config.ts`, `tsconfig*.json`, `eslint.config.js`, `nginx.conf`, `Dockerfile` | All untouched. `nginx.conf`'s `try_files $uri $uri/ /index.html;` remains correct for the single-page shape (any unknown path still serves `index.html`). |

### Rewrite (3 files)

#### `src/App.tsx`

From:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import Layout from './components/Layout';
import ChainPage from './pages/ChainPage';
import DataPage from './pages/DataPage';
import ReportPage from './pages/ReportPage';
import PlanPage from './pages/PlanPage';

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: { ... } }}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Navigate to="/chain" replace />} />
            <Route path="/chain" element={<ChainPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/plan" element={<PlanPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
```

To:

```tsx
import ChainPage from './pages/ChainPage';

export default function App() {
  return <ChainPage />;
}
```

#### `src/services/api.ts`

Remove 16 legacy API functions and leave only the 5 chainkb ones.

**Remove**:
- `analyzeChain` (LLM chain analysis)
- `getChainHistory`
- `queryData`
- `getStockQuote`, `getStockHist`, `getStockFinancial`, `getStockReports`, `getStockBlocks`, `getStockFundFlow`
- `generateReport`, `listReports`, `getReport`
- `createPlan`, `listPlans`, `updatePlan`, `deletePlan`

(16 functions total: 2 chain + 1 data + 6 stock + 3 report + 4 plan.)

**Keep**:
- `getChainKbTree`, `getChainKbSubIndustry`, `getChainKbCompany`, `getChainKbTimeseries`, `searchChainKb`
- The `axios.create({ baseURL: 'http://localhost:8000' })` client
- The type re-exports from `../types/chainkb`

#### `package.json` + `package-lock.json`

```bash
npm uninstall antd @ant-design/icons react-router-dom
# react-markdown stays (MarkdownRenderer.tsx still imports it)
```

Final dependency list:

```json
{
  "dependencies": {
    "axios": "^1.18.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^10.1.0"
  }
}
```

### Inspect-but-probably-skip

- `src/index.css` — currently imported by `main.tsx`. Need to verify
  it doesn't contain Ant Design-specific resets (e.g., `body { background: #0d1117 }`
  or antd class overrides). If it does, remove those rules. If it's a
  generic reset, leave alone. Decision deferred to implementation phase.
- `dist/` — old production build. `npm run build` overwrites it; no
  manual cleanup needed.

## Verification

| Check | Command / Action | Pass Criterion |
|---|---|---|
| Lint | `npm run lint` | exit 0 |
| Type-check + build | `npm run build` | exit 0; produces `dist/` |
| Dev server | `npm run dev`, open http://localhost:5173 | Sketch dashboard renders directly at `/`; no flash of redirect; no console errors |
| No residual imports | `grep -rE "antd\|@ant-design\|react-router" src/` | Empty result |
| Backend integration | With backend on :8000, the 3 tabs load real data | Tree renders 5 layers / 48 sub-industries; sub-industry drill-down returns companies; finance tab loads 寒武纪 profile |
| Bundle size | Inspect `npm run build` output | Main JS chunk < 400 KB minified (down from ~1.2 MB) |

## Non-Goals

- Backend changes (no router removal, no service deletion, no DB schema changes).
- Any modification to `src/chainkb/**` code.
- Implementing the deferred 02 公司对比 / 04 风险标记 tabs.
- Adding new features, pages, or routes.
- URL-encoded state in ChainKbPage (tab state still lives in React useState).
- Docker production rebuild / deployment changes (`nginx.conf` already correct).

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `react-markdown` accidentally uninstalled → `MarkdownRenderer.tsx` compile failure | Medium (easy mistake) | Verification step includes `grep react-markdown package.json`; if missing, restore it before re-build. |
| Hidden import of `antd` / `react-router-dom` somewhere in `src/chainkb/**` | Low (ChainKbPage was deliberately built with raw HTML) | `grep -rE "antd\|@ant-design\|react-router" src/` in verification catches any stray import. |
| `index.css` has dark-theme residue causing visual artifacts | Medium | Inspect during implementation; remove antd-specific rules only. |
| Bundle chunk-size warning persists even after cleanup | Low (Ant Design v6 was the main contributor) | Acceptable; the warning threshold is 500 KB and we should land around 300 KB. |
| User later wants a second page back | Not a risk — ChainPage.tsx thin wrapper is preserved precisely as the re-attachment point. | Re-install `react-router-dom`, restore `App.tsx` router shell, add the second page. |

## Out-of-Scope Notes (Context for Future Work)

- The backend's `app/routers/chain.py`, `data.py`, `report.py`, `plan.py`
  become "dormant code" — mounted but uncalled. They continue to create
  their tables on startup (`Base.metadata.create_all`) and occupy a few
  hundred lines of Python. If a future cleanup pass wants to remove them,
  the steps are: (1) drop the `include_router` calls in `main.py`,
  (2) delete the four router + four service files, (3) leave the ORM
  models in `models/models.py` (the DB tables hold real user data).
- `MarkdownRenderer.tsx` uses inline dark-theme colors (`#e6edf3`,
  `#8b949e`, etc.). If it's revived for a real feature, those colors
  need reskinning to match whatever theme is active at that time.
