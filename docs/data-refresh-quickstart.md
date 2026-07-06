# 数据刷新快速部署(5 分钟版)

> 完整文档:`docs/data-refresh-guide.md`(578 行,含 HTTP API / 故障排查 / 并发模型)
> 设计原理:`docs/superpowers/specs/2026-06-26-data-freshness-design.md`

---

## TL;DR

**不需要 cron。** 后端内置 APScheduler,启动 uvicorn 即按预定时间表自动刷新所有数据。

部署的核心 5 步:

```bash
# 1. 拉代码 + 装依赖
git clone <repo> /opt/investlens && cd /opt/investlens/backend
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt

# 2. 配 .env(必填 ADMIN_REFRESH_TOKEN,否则刷新接口 503)
echo "ADMIN_REFRESH_TOKEN=$(python -c 'import secrets; print(secrets.token_hex(16))')" > .env

# 3. 设时区(调度时间表按 Asia/Shanghai 解释)
sudo timedatectl set-timezone Asia/Shanghai

# 4. 首次灌数据(用 CLI,免 token)
../.venv/bin/python -m app.services.refresh_cli all

# 5. 用 systemd 托管 uvicorn,崩溃自动拉起(配置见下文)
sudo cp /tmp/investlens.service /etc/systemd/system/ && sudo systemctl enable --now investlens
```

---

## 内置调度时间表(自动跑,无需配置)

`backend/app/services/scheduler.py:39-54` 定义了 8 条 cron。uvicorn 启动后自动加载,日志可见:

```
INFO apscheduler.scheduler: Scheduler started
INFO app.services.scheduler: scheduler started with 8 jobs
```

| 类型 | Cron | 说明 |
|---|---|---|
| `quotes_0` | `mon-fri 09-14, */5min` | 开盘期 5 分钟一次 |
| `quotes_1` | `mon-fri 15:00-15:30, */5min` | 收盘期 5 分钟一次 |
| `margin` | `mon-fri 15:30` | 收盘后当日融资融券 |
| `finance` | `sun 03:00` | 周日凌晨 |
| `reports` | `sun 04:00` | 周日凌晨 |
| `lockup` | `sun 05:00` | 周日凌晨 |
| `holders` | `1st 03:00` | 每月 1 号 |
| `concepts` | `1st 04:00` | 每月 1 号 |

> 周末/节假日 quotes/margin 也会触发,backfill 脚本内部会跳过非交易日,数据正确性不受影响。

---

## 三种触发方式(按场景选)

### 1. 自动(默认,零干预)

启动 uvicorn 即生效。**不要配 cron**,会和进程内调度器冲突触发重复刷新。

### 2. CLI(本地手动,免 token)

适用场景:首次灌数据、运维排查、补跑失败 job。

```bash
cd backend

# 单个类型(同步阻塞至完成)
python -m app.services.refresh_cli quotes          # ~2s
python -m app.services.refresh_cli reports         # ~1-5min
python -m app.services.refresh_cli finance         # ~5-10min

# 全部 7 种(快→慢顺序,单类失败不中断)
python -m app.services.refresh_cli all

# 查最近 20 次执行
python -m app.services.refresh_cli --list

# 查某次 job 详情
python -m app.services.refresh_cli --status 42
```

### 3. HTTP API(远程触发,需 token)

适用场景:从运维平台、外部 cron、CI 触发。

```bash
# 触发(quotes 同步,其他异步返回 job_id)
curl -X POST http://host:8000/api/chainkb/refresh/reports \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# 查状态
curl http://host:8000/api/chainkb/refresh/status/43 \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# 公开的新鲜度接口(无需 token,前端轮询)
curl http://host:8000/api/chainkb/freshness
```

> HTTP 接口必填 `X-Admin-Token`,值来自 `.env` 的 `ADMIN_REFRESH_TOKEN`。留空 → 所有 `/refresh/*` 接口 503。

---

## systemd 配置(生产推荐)

`/etc/systemd/system/investlens.service`:

```ini
[Unit]
Description=InvestLens Backend
After=network.target

[Service]
Type=simple
User=investlens
WorkingDirectory=/opt/investlens/backend
EnvironmentFile=/opt/investlens/backend/.env
ExecStart=/opt/investlens/.venv/bin/uvicorn app.main:app \
          --host 0.0.0.0 --port 8000 --no-access-log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用:

```bash
sudo useradd -r -s /usr/sbin/nologin -d /opt/investlens investlens
sudo chown -R investlens:investlens /opt/investlens
sudo systemctl daemon-reload
sudo systemctl enable --now investlens
sudo systemctl status investlens     # active (running) 即可
journalctl -u investlens -f           # 实时看日志
```

---

## 验证部署成功

```bash
# 1. 进程在跑
sudo systemctl status investlens | grep "active (running)"

# 2. 调度器已加载 8 个 job
journalctl -u investlens | grep "scheduler started with 8 jobs"

# 3. 前端新鲜度条有数据
# 浏览器打开 https://your-host/chain,右上角应显示:
# "现价 3分钟前 · 财务 2天前 · 研报 ..."

# 4. 数据库有审计记录
sqlite3 /opt/investlens/backend/data/investlens.db \
  "SELECT id,refresh_type,status,started_at,rows_affected,triggered_by \
   FROM chain_refresh_log ORDER BY started_at DESC LIMIT 10;"
```

---

## 5 个关键陷阱(踩过都麻烦)

| 陷阱 | 症状 | 解决 |
|---|---|---|
| **多 worker** | 同一时刻触发 N 次重复刷新 | uvicorn 默认单 worker,**不要加** `--workers N` |
| **token 留空** | `POST /refresh/*` 返回 503 | `.env` 必填 `ADMIN_REFRESH_TOKEN` |
| **时区错** | 凌晨被唤醒跑数据 | `sudo timedatectl set-timezone Asia/Shanghai` |
| **进程重启** | 错过的执行不补跑 | `misfire_grace_time=600`,超 10 分钟的 misfire 丢弃 |
| **同类型并发** | HTTP 返回 409 Conflict | 同类型必须等前一次结束。僵尸行等 `2*timeout` 自动清,或手动 SQL `UPDATE chain_refresh_log SET status='failed' WHERE status='running'` |

---

## 失败排查路径(从快到慢)

```bash
# 1. 看后端日志最近失败
journalctl -u investlens -n 200 | grep -i "refresh.*failed"

# 2. 查 DB 失败详情(error 字段含 backfill stderr)
sqlite3 backend/data/investlens.db \
  "SELECT refresh_type, started_at, error FROM chain_refresh_log \
   WHERE status='failed' ORDER BY started_at DESC LIMIT 5;"

# 3. CLI 复跑某类型看完整错误
python -m app.services.refresh_cli reports

# 4. 直接跑 backfill 子脚本看原始输出
python scripts/backfill_em_reports.py 2>&1 | tee /tmp/r.log
```

常见根因:网络不通(EM/Tencent 接口)、EM 限流(脚本有 sleep 但偶发升级)、`backend/data/` 无写权限。

---

## 部署清单(打印核对)

- [ ] `python3 -m venv .venv && pip install -r requirements.txt`
- [ ] `.env` 含 `ADMIN_REFRESH_TOKEN=$(secrets.token_hex(16))`
- [ ] `.env` 权限 `chmod 600`
- [ ] `timedatectl` 显示 `Asia/Shanghai`
- [ ] systemd unit 文件已安装,`Restart=always`
- [ ] uvicorn **单 worker** 启动(不加 `--workers`)
- [ ] `backend/data/` investlens 用户可写
- [ ] 首次 `python -m app.services.refresh_cli all` 跑通
- [ ] 启动日志含 `scheduler started with 8 jobs`
- [ ] 前端新鲜度条显示真实数据
- [ ] `chain_refresh_log` 表有 `succeeded` 行

---

## 何时不用这套方案

- **离线刷新**(后端不开):直接跑 `python scripts/backfill_*.py`,然后 `python scripts/load_seed_to_db.py`。不走 dispatch,没有审计,没有并发控制。
- **测试环境**:`DEEPSEEK_API_KEY` 不设即可,LLM 走 mock,但 backfill 脚本仍需联网拉行情。

详细架构、HTTP API 字段、并发模型见 **`docs/data-refresh-guide.md`**。
