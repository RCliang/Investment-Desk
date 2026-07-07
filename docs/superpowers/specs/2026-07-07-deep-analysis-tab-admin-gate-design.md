# 公司深度分析 Tab — 重命名 + 管理员鉴权

**日期**: 2026-07-07
**作者**: Dong Liang + Claude
**状态**: Approved → 待写实施计划

## 背景

当前「个股深度分析」tab(`frontend/src/App.tsx:10` 菜单项)对所有人开放,研报下载、MinerU 解析、LLM 分析都会消耗 OSS / MinerU / DeepSeek 额度。仓库已有 `ADMIN_REFRESH_TOKEN` 共享密钥机制(用于 `/api/chainkb/refresh/*`),但仅覆盖刷新端点,深度分析 pipeline 的 8 个端点全部裸奔。

本次改造达成两件事:

1. **重命名**: 全站把 `个股深度分析` 改成 `公司深度分析`(5 处文案,见「文件改造清单」)
2. **管理员鉴权**: 把深度分析 tab 锁起来,只有持有 `ADMIN_REFRESH_TOKEN` 的管理员能用。普通访客看得到 tab 但带锁图标,点击弹登录框

非目标:

- 不引入完整用户系统/账号(JWT、OAuth、数据库 user 表等)。继续用单一共享密钥
- 不锁 ChainKb tab 03 的 `/latest` 端点。ChainKb 的「AI 公司拆解」section 继续对所有人公开,展示管理员生成好的最新分析结果(创建者管理员 / 查看者所有人)
- 不改历史 spec 文档中已写死的 `个股深度分析` 字样(历史记录)

## 范围

| 改 | 不改 |
|---|---|
| 新建 `backend/app/auth.py`,抽离 `verify_admin_token` | `ADMIN_REFRESH_TOKEN` 环境变量的生成方式 / config 读取逻辑 |
| `backend/app/routers/refresh.py` 改为 import 共享依赖 | refresh 端点的行为 / 既有 8 个刷新类型 |
| `backend/app/routers/research.py` 3 个端点加 admin 依赖 | research_service.py 业务逻辑 |
| `backend/app/routers/deep_analysis.py` 5 个端点加 admin 依赖(保留 `/latest` 公开) | `deep_analysis_service.py` / orchestrate / runner / storage |
| 新建 `frontend/src/auth/AdminAuthContext.tsx` | 现有 React 组件结构 / Vite 配置 |
| 新建 `frontend/src/auth/AdminLoginModal.tsx` + `admin.css` | Ant Design 主题 / 全局 token.css |
| `frontend/src/services/api.ts` 加 axios 拦截器(请求注 token / 401 清 token) | 其他既有 API 函数签名 |
| `frontend/src/App.tsx` tab label 改名 + 锁图标 + 点击拦截 | 路由结构 / 其他 tab |
| `frontend/src/pages/DeepAnalysisPage.tsx` H1 改名 + 退出按钮 | 4 步向导业务逻辑 |
| `frontend/src/chainkb/components/LatestAnalysisSection.tsx` 空态文案改名 | ChainKb 其他部分 |

## 关键决策

### 1. 复用 `ADMIN_REFRESH_TOKEN` 而非引入新 token

| 选项 | 缺点 |
|---|---|
| 新增 `DEEP_ANALYSIS_ADMIN_TOKEN` 环境变量 | 用户要管两个 token,容易混 |
| 复用 `ADMIN_REFRESH_TOKEN` | 一处失败全局失败(单点),但简单一致 |

**复用**。一个管理员 token 保护所有管理员端点(refresh + research + deep-analysis)。`backend/app/auth.py` 共享模块读同一个 `ADMIN_REFRESH_TOKEN`。

### 2. 前端登录 UX:点 tab 弹 modal

| 选项 | 缺点 |
|---|---|
| 点 tab 弹 modal 输 token | 弹框打断流 |
| 顶部菜单独立「管理员登录」入口 | 入口隐蔽,新用户发现不了 |
| 隐藏 tab,靠 URL 访问 | 安全性差(浏览器历史/书签泄漏) |

**点 tab 弹 modal**。tab 始终可见(`🔒 公司深度分析`),点击未登录时阻止路由跳转改为开 modal。最符合「这个功能存在但需要权限」的语义。

### 3. 后端保护范围:8 个端点全锁,/latest 公开

| 端点 | 所属 pipeline 步骤 | 锁? |
|---|---|---|
| `GET /api/research/reports` | Step 1 研报搜索(按 code) | 锁 |
| `GET /api/research/search` | Step 1 研报搜索(关键词) | 锁 |
| `POST /api/research/download` | Step 2 下载 PDF 到 OSS(耗 OSS / MinerU) | 锁 |
| `POST /api/deep-analysis/parse` | Step 3 MinerU 解析(耗 MinerU 额度) | 锁 |
| `GET /api/deep-analysis/parse-status` | Step 3 轮询 | 锁 |
| `GET /api/deep-analysis/analyze` | Step 4 LLM SSE 流(耗 DeepSeek 额度) | 锁 |
| `GET /api/deep-analysis/history` | 侧边栏历史列表 | 锁 |
| `GET /api/deep-analysis/records/{id}` | 历史详情查看 | 锁 |
| `GET /api/deep-analysis/latest` | ChainKb tab 03 公开展示 | **不锁** |

理由:如果只锁耗线的(下载/解析/分析)而留 search 公开,普通用户能看到 Step 1 列表但点下载就 401,UX 怪。整条 pipeline 锁起来,ChainKb 公开 view 是另一回事。

### 4. Token 持久化策略 + 「记住我」

- modal 内含「☑ 记住我」复选框,默认勾选
- 勾选 → `localStorage.setItem('adminToken', token)`(永久,跨浏览器重启)
- 不勾 → `sessionStorage.setItem('adminToken', token)`(关浏览器即失效)
- 不提供「不存」选项 —— 现代浏览器 token 短时效场景应该走 OTP,这里场景是个人工作台,接受 localStorage 风险

### 5. 不加 `/api/auth/verify` 端点

| 选项 | 缺点 |
|---|---|
| 加 verify 端点,登录时先校验 | 多一个端点,多一次往返 |
| 不加,直接存,后端首次 401 时清 token + 重弹 modal | 用户输错 token 时 modal 关了又开,UX 略抖 |

**不加**。modal 关闭 → 进入 tab → 首次 API 调用 → 后端 401 → axios 响应拦截器清 token + 触发 modal 重开 + 显示「token 无效」。一次额外往返不值。

### 6. 退出管理员入口:tab 顶部按钮

进入 DeepAnalysisPage 后,在 H1 旁边右侧放一个不显眼的「退出管理员」文字按钮(配 `LogoutOutlined` 图标),点击后 `logout()` + 跳回首页 + tab 恢复 🔒 状态。

### 7. Login modal 视觉风格:纸质手绘

不引入 Ant Design `<Modal>` 默认样式,自造纸感 modal 复用项目 CSS tokens:

- 半透明遮罩 `rgba(26, 43, 74, 0.45)`
- modal 卡片 `var(--paper)` 背景 + 2.5px `var(--ink)` 边框 + 6px 圆角 + `transform: rotate(-0.3deg)`(轻微倾斜,与 `.da-root .panel` 一致)
- 字体:`'Patrick Hand', 'Caveat', cursive`
- 输入框:`.input` 样式(已在 `deep-analysis.css:138` 定义)
- 按钮:`.btn` 主按钮样式(黄底黑边)
- 「记住我」:Ant Design `<Checkbox>` 加 className 覆盖成纸质风格

新 CSS 文件 `frontend/src/auth/admin.css`(独立于 deep-analysis.css,因为 modal 在 App 层渲染不在 `.da-root` 内)。

### 8. tab 图标:Ant Design Icons

App.tsx 顶层菜单用 Ant Design,tab label 前加 `<LockOutlined />`(未登录) / `<UnlockOutlined />`(已登录)图标。视觉上与 Ant Design nav 一致。

## 文件改造清单

### 后端

#### 新建 `backend/app/auth.py`

```python
"""Shared admin auth dependency.

Used by routers that protect privileged endpoints (refresh, research,
deep-analysis) with a single shared X-Admin-Token header compared
against ADMIN_REFRESH_TOKEN from config.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import ADMIN_REFRESH_TOKEN


def verify_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency: enforce X-Admin-Token header.

    - 503 if ADMIN_REFRESH_TOKEN unset (defensive: prevents accidental
      open access when misconfigured).
    - 401 if header missing or mismatched.
    """
    if not ADMIN_REFRESH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_REFRESH_TOKEN not configured; admin endpoints disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")
```

#### 改 `backend/app/routers/refresh.py`

- 删 line 23 `from app.config import ADMIN_REFRESH_TOKEN` import(已无直接使用)
- 删 line 63-75 `verify_admin_token` 函数定义
- 加 `from app.auth import verify_admin_token`
- 其他不变,既有 `dependencies=[Depends(verify_admin_token)]` 仍然有效

纯重构,无行为变化。

#### 改 `backend/app/routers/research.py`

3 个端点加依赖:

```python
from app.auth import verify_admin_token  # 顶部新增 import

@router.get("/reports", dependencies=[Depends(verify_admin_token)])
@router.get("/search", dependencies=[Depends(verify_admin_token)])
@router.post("/download", dependencies=[Depends(verify_admin_token)])
```

#### 改 `backend/app/routers/deep_analysis.py`

5 个端点加依赖,**`/latest` 不加**:

```python
from app.auth import verify_admin_token  # 顶部新增 import

@router.post("/parse", dependencies=[Depends(verify_admin_token)])
@router.get("/parse-status", dependencies=[Depends(verify_admin_token)])
@router.get("/analyze", dependencies=[Depends(verify_admin_token)])
@router.get("/history", dependencies=[Depends(verify_admin_token)])
@router.get("/records/{analysis_id}", dependencies=[Depends(verify_admin_token)])
# /latest 不加依赖,ChainKb tab 03 公开访问
```

同时把 line 2 docstring 里 `个股深度分析` 改为 `公司深度分析`。

### 前端

#### 新建 `frontend/src/auth/AdminAuthContext.tsx`

```typescript
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

const STORAGE_KEY = 'adminToken';

type StorageKind = 'localStorage' | 'sessionStorage';

interface AdminAuthState {
  token: string | null;
  isAdmin: boolean;
  login: (token: string, remember: boolean) => void;
  logout: () => void;
}

const AdminAuthContext = createContext<AdminAuthState>(/* ... */);

function readToken(): string | null {
  // 优先读 localStorage,其次 sessionStorage
  return localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
}

function clearToken() {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readToken());

  // 跨 tab 同步:监听 storage 事件(localStorage 在其他 tab 改动时触发)
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setToken(readToken());
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  // 监听全局 401 事件(由 axios 响应拦截器派发)
  useEffect(() => {
    const handler = () => {
      clearToken();
      setToken(null);
    };
    window.addEventListener('admin:unauthorized', handler);
    return () => window.removeEventListener('admin:unauthorized', handler);
  }, []);

  const login = (tok: string, remember: boolean) => {
    const storage: Storage = remember ? localStorage : sessionStorage;
    storage.setItem(STORAGE_KEY, tok);
    setToken(tok);
  };

  const logout = () => {
    clearToken();
    setToken(null);
  };

  return (
    <AdminAuthContext.Provider value={{ token, isAdmin: !!token, login, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export const useAdminAuth = () => useContext(AdminAuthContext);
```

#### 新建 `frontend/src/auth/AdminLoginModal.tsx`

```typescript
import { useState } from 'react';
import { Modal, Input, Checkbox } from 'antd';  // 仅取 Checkbox,Modal 自造
import { LockOutlined } from '@ant-design/icons';
import { useAdminAuth } from './AdminAuthContext';
import './admin.css';

interface Props {
  open: boolean;
  onClose: () => void;
  errorMsg?: string;  // 由父组件传入(首次 401 后显示「token 无效」)
}

export default function AdminLoginModal({ open, onClose, errorMsg }: Props) {
  const { login } = useAdminAuth();
  const [token, setToken] = useState('');
  const [remember, setRemember] = useState(true);

  const handleSubmit = () => {
    if (!token.trim()) return;
    login(token.trim(), remember);
    setToken('');
    onClose();
  };

  if (!open) return null;

  return (
    <div className="alm-overlay" onClick={onClose}>
      <div className="alm-card" onClick={(e) => e.stopPropagation()}>
        <div className="alm-header">
          <LockOutlined className="alm-icon" />
          <span className="alm-title">管理员验证</span>
        </div>
        <p className="alm-subtitle">
          「公司深度分析」需要管理员权限。请输入 admin token 继续。
        </p>
        <input
          className="alm-input"
          type="password"
          placeholder="X-Admin-Token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          autoFocus
        />
        {errorMsg && <div className="alm-error">{errorMsg}</div>}
        <label className="alm-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          <span>记住我(永久保留在此浏览器)</span>
        </label>
        <div className="alm-actions">
          <button className="alm-btn alm-btn-ghost" onClick={onClose}>取消</button>
          <button className="alm-btn" onClick={handleSubmit} disabled={!token.trim()}>
            进入
          </button>
        </div>
      </div>
    </div>
  );
}
```

#### 新建 `frontend/src/auth/admin.css`

纸质风格,复用全局 CSS tokens (`var(--paper)`, `var(--ink)`, `var(--hi-yellow)`, `var(--marker-red)` 等,定义在 `styles/tokens.css`):

```css
.alm-overlay {
  position: fixed; inset: 0;
  background: rgba(26, 43, 74, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  font-family: 'Patrick Hand', 'Caveat', cursive;
}
.alm-card {
  background: var(--paper);
  border: 2.5px solid var(--ink);
  border-radius: 6px;
  padding: 22px 26px 20px;
  width: 360px;
  max-width: calc(100vw - 32px);
  box-shadow: 4px 6px 0 rgba(26, 43, 74, 0.18);
  transform: rotate(-0.3deg);
  position: relative;
}
.alm-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}
.alm-icon { font-size: 18px; color: var(--ink); }
.alm-title {
  font-family: 'Caveat', cursive;
  font-weight: 700;
  font-size: 26px;
  color: var(--ink);
  line-height: 1;
}
.alm-subtitle {
  font-size: 13px;
  color: var(--ink-soft);
  margin: 6px 0 14px;
  line-height: 1.4;
}
.alm-input {
  width: 100%;
  background: var(--paper);
  border: 2px solid var(--ink);
  border-radius: 4px;
  padding: 8px 12px;
  font-family: 'Patrick Hand', cursive;
  font-size: 15px;
  color: var(--ink);
  outline: none;
}
.alm-input:focus { border-color: var(--marker-red); }
.alm-error {
  color: var(--marker-red);
  font-size: 13px;
  margin-top: 8px;
}
.alm-remember {
  display: flex; align-items: center; gap: 6px;
  margin: 14px 0 18px;
  font-size: 13px;
  color: var(--ink-soft);
  cursor: pointer;
}
.alm-actions {
  display: flex; justify-content: flex-end; gap: 8px;
}
.alm-btn {
  background: var(--hi-yellow);
  color: var(--ink);
  border: 2px solid var(--ink);
  padding: 6px 16px;
  border-radius: 4px;
  font-family: 'Patrick Hand', cursive;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 2px 2px 0 rgba(26, 43, 74, 0.12);
}
.alm-btn:disabled { opacity: 0.4; cursor: not-allowed; box-shadow: none; }
.alm-btn-ghost {
  background: transparent;
  color: var(--ink-soft);
  border: 2px dashed var(--pencil);
  box-shadow: none;
}
```

#### 改 `frontend/src/services/api.ts`

加请求/响应拦截器:

```typescript
// 顶部既有 import axios from 'axios';

// 请求拦截器:每次自动注入 X-Admin-Token 头
api.interceptors.request.use((config) => {
  const token =
    localStorage.getItem('adminToken') ?? sessionStorage.getItem('adminToken');
  if (token) {
    config.headers['X-Admin-Token'] = token;
  }
  return config;
});

// 响应拦截器:401 → 清 token + 派发全局事件,让 AdminAuthContext 重置 + 让 App 弹 modal
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('adminToken');
      sessionStorage.removeItem('adminToken');
      window.dispatchEvent(new Event('admin:unauthorized'));
    }
    return Promise.reject(error);
  }
);
```

#### 改 `frontend/src/App.tsx`

```tsx
import { useState } from 'react';
import { LockOutlined, UnlockOutlined } from '@ant-design/icons';
import { AdminAuthProvider, useAdminAuth } from './auth/AdminAuthContext';
import AdminLoginModal from './auth/AdminLoginModal';
import './auth/admin.css';

// tab 列表(line 10 附近):
const items = [
  // ...
  { key: 'deep', label: '公司深度分析' },  // 改名
  // ...
];

// menu onClick 处理:
const handleMenuClick = ({ key }) => {
  if (key === 'deep' && !isAdmin) {
    setLoginModalOpen(true);  // 阻止路由跳转,改为开 modal
    return;
  }
  navigate(`/${key}`);
};

// 顶部包装 Provider:
export default function App() {
  return (
    <AdminAuthProvider>
      <AppInner />
    </AdminAuthProvider>
  );
}

function AppInner() {
  const { isAdmin } = useAdminAuth();
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  // ... 既有路由 + menu 逻辑
  // tab label 动态加图标:
  //   !isAdmin → <LockOutlined /> 公司深度分析
  //   isAdmin  → <UnlockOutlined /> 公司深度分析
}
```

#### 改 `frontend/src/pages/DeepAnalysisPage.tsx`

- Line 24 docstring 改 `公司深度分析`
- Line 84 H1 改 `公司深度分析`
- H1 右侧加退出按钮:

```tsx
import { LogoutOutlined } from '@ant-design/icons';
import { useAdminAuth } from '../auth/AdminAuthContext';
import { useNavigate } from 'react-router-dom';

// 在 H1 行:
<div className="row-between">
  <h1>公司深度分析</h1>
  {isAdmin && (
    <button
      className="btn btn-ghost"
      onClick={() => { logout(); navigate('/'); }}
      style={{ fontSize: 13 }}
    >
      <LogoutOutlined /> 退出管理员
    </button>
  )}
</div>
```

#### 改 `frontend/src/chainkb/components/LatestAnalysisSection.tsx`

Line 51 空态文案:

```tsx
前往「公司深度分析」页 → 选择企业类型 → 上传研报 → 一键生成
```

### 后端 docstring 同步

`backend/app/routers/deep_analysis.py:2` 改成:

```python
"""Deep analysis router — 公司深度分析 pipeline 的 HTTP 端点。"""
```

## 错误处理与边界

| 场景 | 行为 |
|---|---|
| 未登录用户点 tab | 弹 login modal;取消则停留在当前页,不跳路由 |
| 未登录用户直接在地址栏输 `/deep-analysis` URL | 路由匹配,页面加载,但首次 API 调用 401 → axios 拦截器清 token + 派发事件 → App 监听到事件弹 modal |
| Token 输错 | modal 关闭 → tab 跳转 → API 401 → modal 重弹 + 显示「token 无效」 |
| Token 输对 | modal 关闭 → 跳路由 → API 200 → 正常使用 |
| 后端 `ADMIN_REFRESH_TOKEN` 没配(env 为空) | API 503 → 前端显示「服务端未配置 admin token,请联系部署者」 |
| 已登录用户点「退出管理员」 | `logout()` 清 storage + 跳回首页 + tab 恢复 🔒 |
| 跨 tab 页签同步 | 在 tab A 退出 → `storage` 事件触发 → tab B 的 `isAdmin` 自动重算为 false |
| 「记住我」勾选 → localStorage | 关闭浏览器再开仍保持登录 |
| 「记住我」不勾 → sessionStorage | 关闭浏览器即失效,下次需要重输 |
| ChainKb tab 03 访客访问 `/latest` | 200 正常返回,无感知,继续显示 AI 公司拆解结果 |
| ChainKb tab 03 显示空态(无 v2 分析) | 文案引导「前往公司深度分析页…」(改名后) |
| 已登录管理员在 ChainKb 看到 tab 03 | 行为不变(`/latest` 是公开端点) |

## 验证

### 静态检查

```bash
# 后端
cd backend
pytest tests/ -v
# 预期:既有测试全绿(加 dependencies 不影响逻辑,测试不带 header 会失败的需要补)

# 前端
cd frontend
npm run build
# 预期: tsc -b + vite build 通过
```

### 后端单元测试新增

`backend/tests/test_admin_auth.py`(新文件,5 个测试):

```python
def test_verify_admin_token_unset_config_returns_503()
def test_verify_admin_token_missing_header_returns_401()
def test_verify_admin_token_wrong_token_returns_401()
def test_verify_admin_token_correct_token_passes()
def test_protected_endpoints_list()  # 检查 8 个端点都注册了 Depends(verify_admin_token)
```

### 端到端手动 smoke

```bash
# 后端(配 ADMIN_REFRESH_TOKEN=test123)
cd backend && ADMIN_REFRESH_TOKEN=test123 uvicorn app.main:app --reload --port 8000

# 1. 不带 header 调 8 个被保护端点 → 全部 401
for ep in "/api/research/reports?code=688256" \
          "/api/research/search?keyword=cambricon" \
          "/api/deep-analysis/parse" \
          "/api/deep-analysis/parse-status?code=688256" \
          "/api/deep-analysis/analyze?code=688256" \
          "/api/deep-analysis/history?code=688256" \
          "/api/deep-analysis/records/1"; do
  curl -s -o /dev/null -w "%{http_code} $ep\n" "http://localhost:8000$ep"
done
# 预期: 全部 401 (POST 端点要换 -X POST)

# 2. /latest 不带 header → 200
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/deep-analysis/latest?code=688256"
# 预期: 200 或 404(取决于是否有 v2 记录,但不会 401)

# 3. 带 header 调被保护端点 → 200
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Admin-Token: test123" \
  "http://localhost:8000/api/research/reports?code=688256"
# 预期: 200

# 4. ADMIN_REFRESH_TOKEN 为空时调保护端点 → 503
ADMIN_REFRESH_TOKEN= uvicorn app.main:app --port 8001 &
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/api/research/reports?code=688256"
# 预期: 503
```

### 前端浏览器手动 smoke

```bash
cd frontend && npm run dev
```

| 场景 | 期望 |
|---|---|
| 打开 http://localhost:5173 | 顶部菜单显示「🔒 公司深度分析」(未登录态) |
| 点 tab | 弹 login modal,纸质风格 |
| 输错 token 点「进入」 | modal 关,短暂跳页,API 401 → modal 重弹 + 红字「token 无效」 |
| 输对 token 点「进入」 | modal 关,正常进 tab,菜单图标变 🔓 |
| 勾「记住我」+ 输对 + 关闭浏览器 + 重开 | 仍是登录态 |
| 不勾「记住我」+ 输对 + 关闭浏览器 + 重开 | 退出登录态 |
| 在 DeepAnalysisPage 点「退出管理员」 | 跳首页 + tab 恢复 🔒 |
| 切到 ChainKb tab 03 | 「AI 公司拆解」section 正常显示(对所有人公开) |

## 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| localStorage token 被 XSS 读取 | 中 | 个人工作台,无第三方 JS;后续如接入分析脚本需 review |
| Token 在浏览器 DevTools 可见 | 低 | 用户自己机器,可接受;生产部署不暴露他人 |
| Modal 文案「admin token」对普通用户太技术 | 低 | 副文用「请联系部署者获取」;实际不会有真普通用户(个人工作台) |
| `secrets.compare_digest` 在某些 Python 版本对 str vs bytes 行为不一 | 极低 | 两边都是 str,已验证 |
| axios 响应拦截器 401 误清 token(比如其他 API 也用 401) | 中 | 拦截器只在路径以 `/api/research/` 或 `/api/deep-analysis/`(除 `/latest`)开头时清;或检查请求头是否带了 X-Admin-Token |
| 跨 tab storage 事件不触发 sessionStorage | 极低 | sessionStorage 本就不跨 tab,符合预期 |
| 现有 pytest 测试不带 header 调保护端点全 401 | 中 | 在 conftest.py 加一个 autouse fixture 自动注入正确 header(只在 test mode) |
| ChainKb tab 03 依赖 `/latest` 公开,被误锁 | 中 | spec 明确 `/latest` 不加 Depends;CI 测试覆盖 |
| 历史文档引用「个股深度分析」造成搜索混乱 | 低 | 历史文档是历史记录,不改;未来文档用新名 |

## 关键文件路径

| 文件 | 改动类型 |
|---|---|
| `backend/app/auth.py` | **新建** `verify_admin_token` 共享依赖 |
| `backend/app/routers/refresh.py` | 删本地 `verify_admin_token`,改 import |
| `backend/app/routers/research.py` | 3 端点加 `Depends(verify_admin_token)` |
| `backend/app/routers/deep_analysis.py` | 5 端点加依赖(保留 `/latest`);docstring 改名 |
| `backend/tests/conftest.py` | 加 autouse fixture 注入测试用 X-Admin-Token 头 |
| `backend/tests/test_admin_auth.py` | **新建** 5 个单元测试 |
| `frontend/src/auth/AdminAuthContext.tsx` | **新建** Context + Provider + useAdminAuth hook |
| `frontend/src/auth/AdminLoginModal.tsx` | **新建** 纸质风格 login modal |
| `frontend/src/auth/admin.css` | **新建** modal 样式 |
| `frontend/src/services/api.ts` | 加 axios 请求/响应拦截器 |
| `frontend/src/App.tsx` | tab label 改名 + 图标 + 点击拦截 + 顶层包 Provider |
| `frontend/src/pages/DeepAnalysisPage.tsx` | H1 改名 + 退出管理员按钮 |
| `frontend/src/chainkb/components/LatestAnalysisSection.tsx` | 空态文案改名 |
| `docs/data-refresh-guide.md` | (可选)加一节「深度分析 pipeline 也用同一 token」|

## 提交数量: 1 commit

`feat(auth): gate 公司深度分析 tab behind admin token + rename from 个股深度分析`

## 实施顺序

1. 后端: 新建 `app/auth.py` → 改 `refresh.py` import(纯重构)
2. 后端: 给 `research.py` + `deep_analysis.py` 8 个端点加 `Depends`
3. 后端: 改 `conftest.py` 加测试用 token fixture
4. 后端: 新建 `test_admin_auth.py`
5. 后端验证: `pytest` 全绿 + 手动 curl 401/200/503
6. 前端: 新建 `AdminAuthContext.tsx`
7. 前端: 新建 `admin.css` + `AdminLoginModal.tsx`
8. 前端: 改 `services/api.ts` 加拦截器
9. 前端: 改 `App.tsx` tab 改名 + 图标 + 点击拦截 + Provider
10. 前端: 改 `DeepAnalysisPage.tsx` H1 改名 + 退出按钮
11. 前端: 改 `LatestAnalysisSection.tsx` 空态文案
12. 前端验证: `npm run build` 通过 + 浏览器手动 smoke
13. docstring 同步 + commit
