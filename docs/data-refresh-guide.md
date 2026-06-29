# 数据刷新功能使用说明（生产部署）

本文档说明 InvestLens 数据刷新功能（data refresh）在生产环境的部署与使用方法。涵盖配置、启动、三种触发方式、监控以及常见问题排查。

> 对应设计文档：`docs/superpowers/specs/2026-06-26-data-freshness-design.md`
> 实施计划：`docs/superpowers/plans/2026-06-26-data-freshness.md`

---

## 1. 功能概览

数据刷新系统由四个组件构成：

| 组件 | 文件 | 作用 |
|------|------|------|
| **Orchestrator** | `backend/app/services/refresh_service.py` | 调度 backfill 脚本 + 入库；统一日志、超时、并发控制 |
| **HTTP Router** | `backend/app/routers/refresh.py` |对外接口：`POST /refresh/{type}`、`GET /refresh/status/{id}`、`GET /freshness`|
| **APScheduler** | `backend/app/services/scheduler.py` |进程内自动调度，按 cron 触发各类型刷新 |
| **CLI** | `backend/app/services/refresh_cli.py` |本地命令行触发，免 token |

所有触发路径（HTTP / Scheduler / CLI）最终汇聚到 `refresh_service.dispatch()`，因此日志、错误处理、并发检查完全一致。每次运行在 `chain_refresh_log` 表中留下一行审计记录（`running` → `succeeded` 或 `failed`）。

支持 7 种刷新类型 + 1 个聚合：

| type | 数据来源脚本 | 入库 loader | 默认调度 |
|------|-------------|-----------|---------|
| `quotes` | `backfill_tencent_quotes.py` | `load_quotes` | 周一至五 9:00–14:59 每 5 分钟 + 15:00–15:30 每 5 分钟 |
| `finance` | `backfill_mootdx_finance.py` | `load_finance` | 周日 03:00 |
| `reports` | `backfill_em_reports.py` | `load_reports` | 周日 04:00 |
| `concepts` | `backfill_em_concept_blocks.py` | `load_concept_blocks` | 每月 1 号 04:00 |
| `lockup` | `backfill_em_lockup_expiry.py` | `load_lockup` | 周日 05:00 |
| `holders` | `backfill_em_holder_num.py` | `load_holder_num` | 每月 1 号 03:00 |
| `margin` | `backfill_em_margin_trading.py` | `load_margin` | 周一至五 15:30 |
| `all` | （顺序执行以上 7 种） | — | 无（仅手动） |

`all` 执行顺序：`quotes → margin → lockup → holders → reports → concepts → finance`（快 → 慢），单类失败不会中断后续。

---

## 2. 依赖

`backend/requirements.txt` 已包含：

```
apscheduler>=3.10
```

首次部署：

```bash
cd backend
pip install -r requirements.txt
```

---

## 3. 配置 `.env`

### 3.1 必填项：`ADMIN_REFRESH_TOKEN`

HTTP 接口（`POST /api/chainkb/refresh/*` 和 `GET /api/chainkb/refresh/status/*`）通过 `X-Admin-Token` 请求头鉴权。Token 从 `ADMIN_REFRESH_TOKEN` 环境变量读取。

生成一个强随机 token：

```bash
python -c "import secrets; print(secrets.token_hex(16))"
# 输出类似: 7a3b9f8c2e1d4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b
```

写入 `backend/.env`：

```ini
ADMIN_REFRESH_TOKEN=7a3b9f8c2e1d4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b
```

> **警告**：如果留空，所有 `/refresh/*` 接口会返回 **503 Service Unavailable**，拒绝裸奔。这是有意为之的保护机制。
>
> `GET /api/chainkb/freshness` 是公开接口（前端需要轮询），不需要 token。

### 3.2 完整 `.env` 模板

参考 `backend/.env.example`。除 `ADMIN_REFRESH_TOKEN` 外，其他视数据源需求填写：

```ini
# 必填（不填则刷新接口返回 503）
ADMIN_REFRESH_TOKEN=<上面生成的 32 字符 hex>

# 选填：DeepSeek（产业链分析与报告生成）
DEEPSEEK_API_KEY=
MODEL_NAME=deepseek-chat

# 选填：Tushare（专业财务指标）
TUSHARE_TOKEN=

# 选填：iWencai（研报搜索）
IWENCAI_API_KEY=
```

---

## 4. 启动后端（调度器自动启动）

### 4.1 直接 uvicorn 启动

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`app/main.py` 注册了两个 FastAPI 生命周期事件：

```python
@app.on_event("startup")
async def startup_scheduler():
    from app.services.scheduler import start_scheduler
    start_scheduler()

@app.on_event("shutdown")
async def shutdown_scheduler():
    from app.services.scheduler import shutdown_scheduler
    shutdown_scheduler()
```

启动日志里会看到：

```
INFO apscheduler.scheduler: Scheduler started
INFO app.services.scheduler: scheduler started with 8 jobs
```

8 个 job 分别是：`quotes_0`、`quotes_1`（同一类型两条 cron）、`margin`、`finance`、`reports`、`lockup`、`holders`、`concepts`。

### 4.2 生产部署建议

用进程管理器托管 uvicorn，使其崩溃后自动拉起：

**systemd（Linux）**：

```ini
# /etc/systemd/system/investlens.service
[Unit]
Description=InvestLens Backend
After=network.target

[Service]
Type=simple
User=investlens
WorkingDirectory=/opt/investlens/backend
EnvironmentFile=/opt/investlens/backend/.env
ExecStart=/opt/investlens/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

> 注意：`EnvironmentFile` 直接把 `.env` 作为 systemd 环境文件加载，无需 `python-dotenv`。但 `app/config.py` 仍会调用 `load_dotenv()`，本地与生产行为一致。

**pm2 / supervisor**：同理，确保 `cwd=backend/`、`.env` 可读、重启策略为 `always`。

### 4.3 重要提醒：进程内调度器

APScheduler 运行在 uvicorn 同一进程内。**每次 uvicorn 重启，已注册的 job 会重新基于当前时间计算下次触发——错过的执行不会补跑**（`misfire_grace_time=600`，超过 10 分钟的 misfire 会被丢弃）。

多 worker 部署（`uvicorn --workers 4`）会启动 4 个独立调度器，触发 4 次重复刷新。生产环境请使用 **单 worker**（默认），或多进程 + 外部锁（v1 未实现）。

---

## 5. 三种触发刷新的方式

### 5.1 方式一：CLI（推荐本地使用，免 token）

适用场景：本地手动跑一次、初始化数据、运维排查。

```bash
cd backend

# 触发单个类型（同步阻塞至完成）
python -m app.services.refresh_cli quotes          # ~2s
python -m app.services.refresh_cli reports         # 较慢，~1–5min
python -m app.services.refresh_cli finance         # 最慢，~5–10min

# 触发全部 7 种（按 快→慢 顺序，单类失败不中断）
python -m app.services.refresh_cli all

# 查看最近 20 次执行记录
python -m app.services.refresh_cli --list

# 查看某次 job 的详细状态
python -m app.services.refresh_cli --status 42
```

`--list` 输出示例：

```
  id  type        status      started                rows  by
  42  quotes      succeeded   2026-06-29 14:30:12     234  scheduler
  41  margin      succeeded   2026-06-28 15:30:00    5000  scheduler
  40  reports     failed      2026-06-23 04:00:12    null  scheduler
```

CLI 直接调用 `refresh_service.dispatch(...)`，不经过 HTTP，因此**不需要 token**。`triggered_by` 字段记为 `cli`。

### 5.2 方式二：HTTP API（远程触发，需 token）

适用场景：从另一台机器触发、定时脚本调用、运维平台集成。

#### 5.2.1 触发刷新

```bash
# quotes 是同步类型：阻塞 ~2s，返回最终结果
curl -X POST http://your-host:8000/api/chainkb/refresh/quotes \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# HTTP 200，body：
# {
#   "job_id": 42, "refresh_type": "quotes", "status": "succeeded",
#   "started_at": "...", "finished_at": "...", "rows_affected": 234,
#   "triggered_by": "manual"
# }


# 其他类型是异步：立即返回 job_id，后台执行
curl -X POST http://your-host:8000/api/chainkb/refresh/reports \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# HTTP 202，body：
# {
#   "job_id": 43, "refresh_type": "reports", "status": "running",
#   "started_at": "...", "status_url": "/api/chainkb/refresh/status/43"
# }
```

**同步 vs 异步的规则**（`SYNC_TYPES = {"quotes"}`）：
- `quotes`：HTTP 线程内同步执行（~2s），返回 200 + 最终结果
- 其他所有类型（含 `all`）：丢入 `ThreadPoolExecutor(max_workers=1)`，立即返回 202 + `job_id`

#### 5.2.2 查询 job 状态

```bash
curl http://your-host:8000/api/chainkb/refresh/status/43 \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"
```

返回该 job 的完整字段（status / started_at / finished_at / rows_affected / error / triggered_by）。

#### 5.2.3 公开的新鲜度接口

```bash
# 无需 token，前端每 60s 轮询一次
curl http://your-host:8000/api/chainkb/freshness
```

返回示例：

```json
{
  "quotes":   { "last_success_at": "2026-06-29T06:30:00Z", "status": "succeeded", "minutes_ago": 3 },
  "finance":  { "last_success_at": "2026-06-23T19:00:00Z", "status": "succeeded", "minutes_ago": 7200 },
  "reports":  { "last_success_at": null, "status": "never", "minutes_ago": null },
  "concepts": { "...": "..." },
  "lockup":   { "...": "..." },
  "holders":  { "...": "..." },
  "margin":   { "...": "..." },
  "running": ["reports"],
  "failed_recent": {
    "finance": "2026-06-20T19:00:00Z"
  }
}
```

### 5.3 方式三：自动调度器（零干预）

启动后端即自动启用，无需手动配置。

调度时间表（时区 `Asia/Shanghai`）：

| 类型 | Cron | 说明 |
|------|------|------|
| `quotes_0` | `mon-fri 9-14,*/5 min` | 交易日开盘后到 14:59，每 5 分钟 |
| `quotes_1` | `mon-fri 15,0-30 min` | 交易日 15:00–15:30，每 5 分钟 |
| `margin` | `mon-fri 15:30` | 收盘后跑一次当日融资融券 |
| `finance` | `sun 03:00` | 周日凌晨 |
| `reports` | `sun 04:00` | 周日凌晨 |
| `lockup` | `sun 05:00` | 周日凌晨 |
| `holders` | `1st 03:00` | 每月 1 号凌晨 |
| `concepts` | `1st 04:00` | 每月 1 号凌晨 |

`triggered_by` 字段记为 `scheduler`。

> 周末/节假日 `quotes` 和 `margin` 也会触发，但 backfill 脚本内部对非交易日数据会跳过；不影响数据正确性。

---

## 6. 监控数据新鲜度

### 6.1 前端新鲜度条

打开 `http://localhost:5173/chain`，页面顶部右侧有一条形新鲜度指示器（`DataFreshness.tsx`），每 60 秒自动轮询 `/api/chainkb/freshness`：

```
现价 3分钟前 · 财务 2天前 · 研报 更新中… · 概念 5天前 · 解禁 1天前 · 股东 12天前 · 融资融券 5小时前
```

状态颜色：
- **正常**（`fresh-ok`，灰色）：显示 "X分钟前 / X小时前 / X天前"
- **更新中**（`fresh-running`，高亮）：显示 "更新中…"，鼠标悬停看 tooltip
- **失败**（`fresh-failed`，红色）：显示 "失败"，鼠标悬停看最近失败时间
- **从未成功**：显示 "从未"

### 6.2 数据库直查

```bash
cd backend
sqlite3 data/investlens.db

# 最近 20 次刷新
SELECT id, refresh_type, status, started_at, finished_at, rows_affected, triggered_by
FROM chain_refresh_log
ORDER BY started_at DESC
LIMIT 20;

# 当前正在跑的
SELECT * FROM chain_refresh_log WHERE status='running';

# 最近 7 天失败
SELECT refresh_type, started_at, error
FROM chain_refresh_log
WHERE status='failed' AND finished_at > datetime('now', '-7 days')
ORDER BY started_at DESC;
```

### 6.3 日志

后端日志（uvicorn stdout/stderr）会打印每次刷新的关键节点：

```
INFO app.services.refresh_service: refresh 'quotes': running backfill_tencent_quotes.py ...
INFO app.services.refresh_service: refresh 'quotes': backfill done, loading into DB ...
INFO app.services.refresh_service: refresh 'quotes': succeeded rows=234
ERROR app.services.refresh_service: refresh 'reports': failed — RuntimeError: backfill em_reports exited 1: ...
```

systemd 部署用 `journalctl -u investlens -f` 实时查看。

---

## 7. 并发与冲突

### 7.1 单类型互斥

同一 `refresh_type` 不能并发执行。开始执行前，`refresh_service.is_running()` 会查询是否存在 `status='running'` 的同名记录；存在则：

- **HTTP**：返回 `409 Conflict`，body `{"detail": "refresh 'X' already running"}`
- **CLI**：打印 `→ skipped: X already running`，退出码 1
- **Scheduler**：静默跳过（APScheduler 的 `max_instances=1` + `coalesce=True` 本身就保证不重叠）

### 7.2 全局工作线程

HTTP 异步刷新共用一个 `ThreadPoolExecutor(max_workers=1)`，因此多个慢类型刷新会**排队串行执行**，不会同时跑两个。`quotes`（同步）走 HTTP 请求线程，不进这个池子。

### 7.3 `all` 与子类型冲突

`POST /refresh/all` 启动前会检查 7 个子类型都未在运行，否则返回 409。`refresh_service.refresh_all()` 内部则用 `try/except RefreshConflictError: continue` 跳过已在跑的子类型。

### 7.4 卡死自愈

`is_running()` 调用时会顺带执行 `_sweep_stale()`：把超过 `2 * timeout` 仍未结束的 `running` 行标记为 `failed`，避免 backfill 进程被 kill 后该类型永久卡死。各类型 timeout 见 `refresh_service._TIMEOUTS`：

| type | timeout | 说明 |
|------|---------|------|
| `quotes` | 60s | 实时数据，很快 |
| `finance` | 600s | mootdx 拉取大量股票 |
| 其他 | 900s | EM 系列脚本，含 rate-limit sleep |

---

## 8. 失败处理

### 8.1 错误记录

每次失败都会在 `chain_refresh_log.error` 字段写入：

```
RuntimeError: backfill_em_reports.py exited 1: Traceback (most recent call last):
  File "...", line 42, in <module>
    ...
```

最多 1000 字符（`str(e)[:1000]`）。

### 8.2 backfill 子进程的 stdout/stderr

`subprocess.run(..., capture_output=True)` 会捕获子进程输出。失败时把 stderr（或 stdout）末尾 500 字符拼进错误消息。完整子进程日志不会保留——如需排查 backfill 脚本本身的问题，手动跑一遍：

```bash
cd backend
python scripts/backfill_em_reports.py 2>&1 | tee /tmp/reports.log
```

### 8.3 重试策略

v1 **不自动重试**。失败的类型等下一次 cron 触发，或手动重跑。

手动重跑失败类型：

```bash
# CLI
python -m app.services.refresh_cli reports

# 或 HTTP
curl -X POST http://host:8000/api/chainkb/refresh/reports \
  -H "X-Admin-Token: $TOKEN"
```

---

## 9. Docker 部署

### 9.1 当前 `docker-compose.yml` 的注意点

仓库内的 `docker-compose.yml` **目前没有**透传 `ADMIN_REFRESH_TOKEN`：

```yaml
environment:
  - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
  - MODEL_NAME=${MODEL_NAME:-deepseek-chat}
  - TUSHARE_TOKEN=${TUSHARE_TOKEN}
  # ← 缺少 ADMIN_REFRESH_TOKEN
```

如果要通过 Docker 部署并使用 HTTP 刷新接口，**必须手动加一行**：

```yaml
environment:
  - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
  - MODEL_NAME=${MODEL_NAME:-deepseek-chat}
  - TUSHARE_TOKEN=${TUSHARE_TOKEN}
  - ADMIN_REFRESH_TOKEN=${ADMIN_REFRESH_TOKEN}   # 新增
```

然后在宿主机 `.env`（与 docker-compose 同级）或导出环境变量后执行：

```bash
export ADMIN_REFRESH_TOKEN=$(python -c "import secrets; print(secrets.token_hex(16))")
docker-compose up -d --build
```

### 9.2 调度器在容器内的行为

容器内 uvicorn 单进程，APScheduler 正常工作。**前提是容器不重启**——重启会丢失内存中的调度状态（但 `chain_refresh_log` 数据在卷 `backend-data` 里持久化）。

如需重启后立即追上最新数据，进入容器手动跑一次：

```bash
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli quotes
```

---

## 10. 常见问题排查

### 10.1 `503 Service Unavailable`

```
{"detail": "ADMIN_REFRESH_TOKEN not configured; refresh endpoints disabled."}
```

原因：`ADMIN_REFRESH_TOKEN` 环境变量为空。处理：生成 token，写入 `.env`，重启后端。

### 10.2 `401 Unauthorized`

```
{"detail": "invalid or missing X-Admin-Token"}
```

原因：请求未带 `X-Admin-Token` 头，或值与配置不一致。处理：

```bash
# 验证当前后端加载的 token（在 backend 目录下）
python -c "from app.config import ADMIN_REFRESH_TOKEN; print(ADMIN_REFRESH_TOKEN)"
```

注意 token 比对用 `secrets.compare_digest`，**大小写敏感**，且不允许空字符串绕过。

### 10.3 `409 Conflict`

```
{"detail": "refresh 'X' already running"}
```

原因：同类型已在跑。处理：等当前 job 结束，或用 `--status <id>` 查询进度。若确信是僵尸 `running` 行（backfill 进程被 kill），等 `2 * timeout` 秒后 `_sweep_stale` 会自动清理；或手动 SQL：

```sql
UPDATE chain_refresh_log SET status='failed', error='manual cleanup'
WHERE status='running' AND refresh_type='X';
```

### 10.4 刷新一直失败

1. 用 CLI 直跑看完整错误：
   ```bash
   python -m app.services.refresh_cli <type>
   ```
2. 直接跑 backfill 脚本看子进程输出：
   ```bash
   python scripts/backfill_<type>.py
   ```
3. 常见根因：
   - 网络不通（EM/Tencent 接口需公网访问）
   - 数据源限流（脚本内部有 sleep，但偶发升级会失败）
   - backfill 脚本依赖的 JSON 未生成（看 `backend/data/` 目录）

### 10.5 前端新鲜度条不更新

- 检查浏览器 Network：`GET /api/chainkb/freshness` 是否 200
- 后端启动了？调度器日志有 `scheduler started with 8 jobs`？
- `chain_refresh_log` 表里有 `status='succeeded'` 的行？没有就显示 "从未"。

### 10.6 调度器没触发

- 服务器时区是不是 `Asia/Shanghai`？`scheduler.py` 写死了这个时区，主机时区不影响 cron 解释，但日志时间会乱。
- `misfire_grace_time=600`：如果 uvicorn 在 cron 触发时刻停机超过 10 分钟，重启后该次执行会被丢弃。
- 多 worker 模式（`--workers N`）会启动 N 个调度器，触发 N 次重复。**必须单 worker**。

---

## 11. 生产环境部署清单

部署前逐项确认：

- [ ] `ADMIN_REFRESH_TOKEN` 已生成（≥32 字符）并写入 `.env`
- [ ] `.env` 文件权限 `600`，仅服务账号可读
- [ ] `.env` 已加入 `.gitignore`（仓库已配置）
- [ ] 进程管理器（systemd / pm2 / supervisor）配置 `Restart=always`
- [ ] uvicorn 单 worker 启动（不加 `--workers N`）
- [ ] `backend/data/` 目录可写（SQLite + backfill JSON 落盘）
- [ ] 服务器时区 `Asia/Shanghai`（与 cron 解释一致）
- [ ] 防火墙放行 8000 端口（或反代 80/443）
- [ ] 反向代理（nginx）超时 ≥ 600s（finance 同步路径不适用，但 reports 异步返回很快，不涉及）
- [ ] 首次部署：手动跑 `python -m app.services.refresh_cli all` 初始化全部数据
- [ ] 日志收集：`journalctl -u investlens` 或 docker logs 持久化
- [ ] 监控告警：基于 `chain_refresh_log.status='failed'` 配置告警规则（v1 未内置，需外部监控读取 `/api/chainkb/freshness` 的 `failed_recent`）

---

## 12. 速查表

```bash
# 生成 token
python -c "import secrets; print(secrets.token_hex(16))"

# 启动
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 本地手动刷新（免 token）
python -m app.services.refresh_cli quotes
python -m app.services.refresh_cli all
python -m app.services.refresh_cli --list
python -m app.services.refresh_cli --status 42

# 远程触发（需 token）
curl -X POST http://host:8000/api/chainkb/refresh/quotes \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

curl http://host:8000/api/chainkb/refresh/status/42 \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# 公开新鲜度接口
curl http://host:8000/api/chainkb/freshness

# DB 直查
sqlite3 backend/data/investlens.db \
  "SELECT id,refresh_type,status,started_at,rows_affected,triggered_by FROM chain_refresh_log ORDER BY started_at DESC LIMIT 20;"
```
