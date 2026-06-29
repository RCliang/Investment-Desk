# InvestLens 云端部署指南（APScheduler 方案）

## 1. 前置准备

### 1.1 生成管理员 Token

在**本地或服务器**上运行：

```bash
python3 -c "import secrets; print(secrets.token_hex(16))"
# 输出类似: 7a3b9f8c2e1d4a5b6c7d8e9f0a1b2c3d
```

复制这个值，后面要用。

### 1.2 创建 `.env` 文件

在项目根目录（与 `docker-compose.yml` 同级）创建 `.env`：

```ini
DEEPSEEK_API_KEY=your_deepseek_api_key_here
MODEL_NAME=deepseek-chat
TUSHARE_TOKEN=your_tushare_token_here
ADMIN_REFRESH_TOKEN=上面生成的32字符hex值
```

**安全提醒**：
- `.env` 已加入 `.gitignore`，不会提交到 Git
- 生产环境建议设置文件权限 `chmod 600 .env`

---

## 2. 部署到云端服务器

### 2.1 上传代码

```bash
# 方法一：Git clone（推荐）
ssh user@your-server
git clone https://github.com/RCliang/Investment-Desk.git
cd Investment-Desk

# 方法二：SCP 上传
scp -r . user@your-server:/opt/investlens/
ssh user@your-server
cd /opt/investlens
```

### 2.2 配置环境变量

```bash
# 在服务器上创建 .env
nano .env

# 粘贴上面的内容，保存退出（Ctrl+X, Y, Enter）
```

### 2.3 启动服务

```bash
# 构建并启动
docker-compose up -d --build

# 查看容器状态
docker ps

# 应该看到两个容器：
# investment-desk-backend-1   (port 8000)
# investment-desk-frontend-1  (port 3000)
```

### 2.4 验证调度器启动

```bash
# 查看后端日志，确认调度器已启动
docker logs investment-desk-backend-1 | grep scheduler

# 应该看到：
# INFO app.services.scheduler: scheduler started with 8 jobs
```

如果没看到，检查完整日志：

```bash
docker logs investment-desk-backend-1
```

---

## 3. 首次数据初始化

部署后手动跑一次全量刷新：

```bash
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli all
```

这会按顺序执行 7 种刷新类型（快 → 慢），耗时约 10–30 分钟（取决于数据量）。

查看进度：

```bash
# 新开一个终端，实时查看日志
docker logs -f investment-desk-backend-1
```

---

## 4. 自动调度时间表

APScheduler 会在容器启动时自动注册以下任务（时区 **Asia/Shanghai**）：

| 类型 | Cron 表达式 | 触发时间 |
|------|------------|---------|
| `quotes_0` | `mon-fri 9-14 */5` | 交易日 9:00–14:59，每 5 分钟 |
| `quotes_1` | `mon-fri 15 0-30` | 交易日 15:00–15:30，每 5 分钟 |
| `margin` | `mon-fri 15:30` | 交易日 15:30 |
| `finance` | `sun 03:00` | 每周日 03:00 |
| `reports` | `sun 04:00` | 每周日 04:00 |
| `lockup` | `sun 05:00` | 每周日 05:00 |
| `holders` | `1st 03:00` | 每月 1 号 03:00 |
| `concepts` | `1st 04:00` | 每月 1 号 04:00 |

**重要**：
- 周末/节假日 `quotes` 和 `margin` 也会触发，但 backfill 脚本内部会跳过非交易日
- 容器重启后，调度器会重新计算下次触发时间（错过的执行不会补跑）
- `misfire_grace_time=600s`：如果停机超过 10 分钟，该次 cron 会被丢弃

---

## 5. 监控与维护

### 5.1 查看调度任务列表

```bash
docker exec -it investment-desk-backend-1 python -c "
from app.services.scheduler import get_scheduler
s = get_scheduler()
for job in s.get_jobs():
    print(f'{job.id}: next_run={job.next_run_time}, trigger={job.trigger}')
"
```

### 5.2 查看最近刷新记录

```bash
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli --list
```

输出示例：

```
  id  type        status      started                rows  by
  42  quotes      succeeded   2026-06-29 14:30:12     234  scheduler
  41  margin      succeeded   2026-06-28 15:30:00    5000  scheduler
  40  reports     failed      2026-06-23 04:00:12    null  scheduler
```

### 5.3 查看失败详情

```bash
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli --status 40
```

### 5.4 数据库直查

```bash
docker exec -it investment-desk-backend-1 sqlite3 /app/data/investlens.db <<EOF
SELECT id, refresh_type, status, started_at, finished_at, rows_affected, triggered_by
FROM chain_refresh_log
ORDER BY started_at DESC
LIMIT 20;
EOF
```

### 5.5 前端新鲜度条

打开 `http://your-server-ip:3000/chain`，页面顶部右侧会显示各数据类型的新鲜度：

```
现价 3分钟前 · 财务 2天前 · 研报 更新中… · 概念 5天前
```

---

## 6. 常见问题排查

### 6.1 调度器没启动

**症状**：`docker logs` 看不到 `scheduler started`

**原因**：
1. APScheduler 依赖未安装
2. FastAPI startup 事件报错

**解决**：

```bash
# 1. 进入容器检查依赖
docker exec -it investment-desk-backend-1 pip list | grep apscheduler

# 2. 查看完整启动日志
docker logs investment-desk-backend-1 | head -50

# 3. 如果缺少依赖，重建镜像
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 6.2 刷新一直失败

**症状**：`--list` 看到大量 `failed` 状态

**排查步骤**：

```bash
# 1. 手动跑失败的类型看错误
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli reports

# 2. 直接跑 backfill 脚本看子进程输出
docker exec -it investment-desk-backend-1 python scripts/backfill_em_reports.py

# 3. 常见根因：
#    - 网络不通（EM/Tencent 接口需公网访问）
#    - 数据源限流（脚本内部有 sleep，但偶发升级会失败）
#    - JSON 文件未生成（检查 /app/data/ 目录）
```

### 6.3 容器重启后错过执行

**症状**：周日凌晨 3 点容器重启，`finance` 没跑

**原因**：`misfire_grace_time=600s`，停机超过 10 分钟会丢弃

**解决**：

```bash
# 手动补跑
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli finance

# 或者等下周日的 cron 触发
```

**预防**：确保服务器稳定运行，或用 systemd/pm2 托管 Docker Compose：

```ini
# /etc/systemd/system/investlens.service
[Unit]
Description=InvestLens Docker Compose
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/investlens
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

### 6.4 时区不对

**症状**：cron 触发时间与预期不符

**检查**：

```bash
docker exec -it investment-desk-backend-1 date
# 应该输出 CST (China Standard Time)

docker exec -it investment-desk-backend-1 cat /etc/timezone
# 应该输出 Asia/Shanghai
```

如果不正确，重新构建镜像（Dockerfile 已配置时区）。

---

## 7. 更新与重启

### 7.1 代码更新

```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动
docker-compose up -d --build

# 验证调度器重启
docker logs investment-desk-backend-1 | grep scheduler
```

### 7.2 仅重启后端

```bash
docker-compose restart backend
```

### 7.3 完全停止

```bash
docker-compose down

# 如果需要删除数据卷（危险！）
docker-compose down -v
```

---

## 8. 性能优化建议

### 8.1 单 Worker 限制

当前配置 `--workers 1` 是**必须的**，因为 APScheduler 运行在进程内。多 worker 会导致重复触发。

如果未来需要水平扩展，考虑：
- 方案 A：外部 cron + `docker exec`（本方案的反面）
- 方案 B：分布式锁（Redis/ZooKeeper）+ 多 worker
- 方案 C：Kubernetes CronJob

### 8.2 内存监控

```bash
docker stats investment-desk-backend-1
```

APScheduler 本身占用很小（<50MB），主要内存消耗在 backfill 脚本运行时。

### 8.3 日志轮转

防止日志无限增长：

```yaml
# docker-compose.yml 添加
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 9. 速查表

```bash
# 启动
docker-compose up -d --build

# 查看日志
docker logs -f investment-desk-backend-1

# 手动刷新
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli quotes

# 查看调度任务
docker exec -it investment-desk-backend-1 python -c "from app.services.scheduler import get_scheduler; s=get_scheduler(); [print(j.id, j.next_run_time) for j in s.get_jobs()]"

# 查看刷新历史
docker exec -it investment-desk-backend-1 python -m app.services.refresh_cli --list

# 重启后端
docker-compose restart backend

# 停止所有
docker-compose down
```

---

## 10. 下一步

- [ ] 配置 HTTPS（nginx 反代 + Let's Encrypt）
- [ ] 设置告警（基于 `/api/chainkb/freshness` 的 `failed_recent` 字段）
- [ ] 备份 SQLite 数据库（定时 `cp data/investlens.db backups/`）
- [ ] 监控服务器资源（Prometheus + Grafana）
