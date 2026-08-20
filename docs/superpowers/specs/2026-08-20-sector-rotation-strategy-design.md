# 板块轮动中期趋势策略 — 设计文档

日期: 2026-08-20 · 状态: 已实现 v1 · 分支: feat/quant-trend-follow-strategy

## 目标

在 8 板块自选池（CPO / HBM / 先进封装 / 半导体设备 / CMP / 机器人执行器 / 测试设备 / 半导体材料，71 只 A 股，硬约束宇宙）上，用「主力资金动向 + 技术面」做月度调仓的中期趋势策略，并接入现有量化基建（数据管道、回测、调度、前端）。

## 三层架构

```
16:30 mootdx 日线增量（现有）  16:40 主力资金流增量（新增，EM→Sina 兜底）
17:00 单票信号（现有）  17:30 多因子扫描（现有）  17:40 板块轮动扫描（新增）

板块层  8 板块强度分 = 主力维 50% + 技术维 50% → Top-3 板块
选股层  入选板块内 多因子综合分排名 → 每板块 Top-2（多头排列门控，顺延 ≤2 名）
个股层  每日检查退出：MA 破位 / 硬止损 10% / 移动止盈（+20% 激活 / -8% 跟踪）
```

### 板块强度分（sector_rotation.compute_sector_strength）

- 主力维：个股日度 `main_net / amount`（净流入占成交额比，天然去规模）→ 板块等权均值 → 20 日平滑 → 8 板块截面 rank
- 技术维：①板块内多头排列（MA5>MA20>MA60）占比 20 日均值 ②板块等权指数 20 日动量 → 各自 rank 后平均
- 资金流缺失的日期自动退化为纯技术维（长历史骨架模式）

### 个股因子（接入现有 MultiFactorEngine，ICIR 自适应加权）

7 个现有趋势因子 + 3 个新增主力因子（`factors/fund_flow_factors.py`）：

| 因子 | 定义 |
|---|---|
| main_inflow_momentum_20 | 20 日累计主力净流入 / 20 日累计成交额（吸筹强度） |
| main_inflow_persistence | 20 日净流入为正天数占比（持续性） |
| main_inflow_acceleration | 5 日均值(占比) − 20 日均值（加速性） |

### 组合构建

- 月度（20 交易日）调仓：Top-3 板块 × 板块内 Top-2 = ≤6 只
- 权重：`min(1/n, 20%)`，不归一化——持仓不足 5 只时上限生效、剩余留现金
- 入场确认：非多头排列顺延（最多 2 名，否则现金）；非调仓日退出的仓位持币到下个调仓日

## 数据管道

- `chain_fund_flow_daily` 表：(ticker, date) PK + main/super/large/mid/small_net（元）+ source
- `scripts/backfill_em_fund_flow.py`：EM push2his 优先（120 日），失败自动切新浪 MoneyFlow（200 日，主力=r0_net+r1_net），连续 3 只 EM 失败后熔断直走新浪；1.5s 限流；`--incremental` 每日增量（lmt=5）
- 实测（本机网络）：push2his 被 IP 连接级封锁（HTTP 000 瞬断），datacenter 正常；新浪兜底 71/71 成功，14200 行，141 秒
- mootdx 日线：`backfill_mootdx_klines.py --pool`（新增开关）补齐池内 44 只缺票，1600 根/只

## 引擎改造（复用并修正现有基建）

1. `factor_model.compute_composite` NaN 鲁棒化：逐股 masked weighted mean——某因子对该股缺失（如资金流史前时期）时从权重分母剔除而非污染整行；无缺失时与旧实现一致（有测试锁定）
2. IC 权重滞后：IC 统计按 `holding_period` 行 shift 后再取权重，消除「调仓日权重用了未来 forward returns」的前视偏差（此修正同样作用于现有多因子引擎，历史回测数字会变化——更诚实）
3. `load_seed_to_db._upsert_many`：按 999 host 参数预算内部切块（本机 SQLite 上限 999，旧代码 5000 行/批必然超限）

## API（backend/app/routers/quant.py）

- `GET /api/quant/rotation/sectors` — 8 板块强度快照（两维分解 + Top-K 标记）
- `GET /api/quant/rotation/sector-history?days=30` — 强度演变（热力图数据）
- `GET /api/quant/rotation/portfolio` — 当日推荐持仓（因子明细/入场确认/背离预警/止损参考）
- `GET /api/quant/rotation/rankings?sector=` — 板块内全排名
- `POST /api/quant/rotation/backtest` — 回测（`use_fund_flow_factors=false` 为纯技术骨架）
- `POST /api/quant/rotation/scan` — 手动触发扫描（admin）

## 前端（ChainKbPage 新 tab「05 · 板块轮动」）

板块强度双色条（蓝=主力维/绿=技术维，点击展开板块内排名）+ 30 日强度热力图 + 推荐持仓表（主力因子分/背离预警/止损位）+ 回测面板（KPI、策略 vs 池内等权双曲线、分板块盈亏、因子 IC 表）。

## 验证结果（2026-08-20，如实记录）

**基础设施**：单测 20 个新增全过、全量 135 过无回归；真实数据端到端跑通（扫描 17 秒：71 只、8 板块、当日选出 3 只）。

**策略经济学（v1 未达标，验收标准为跑赢池内等权）**：

| 配置 | 总收益 | 基准(池内等权) | 夏普 | 基准夏普 | 最大回撤 | 基准回撤 |
|---|---|---|---|---|---|---|
| 3板块×2只（骨架） | +105.7% | +294.5% | 0.668 | 0.928 | 36.7% | 44.4% |
| 3板块×2只（含主力因子） | +64.6% | +294.5% | 0.517 | 0.928 | 36.7% | 44.4% |
| 8板块×3只（骨架，对照） | +49.9% | +294.5% | 0.466 | — | 49.0% | 44.4% |

区间 2021-08 → 2026-08。结论：回撤控制有效（36.7% vs 44.4%），但绝对与风险调整收益均跑输。退出原因盈亏分解（8×3 对照）：移动止盈 +184 万、调仓 +36 万、**硬止损 -125 万（176 次）、破位退出 -44 万（255 次）**，平均持仓 11.5 天——半导体高波动下固定 10% 止损 + MA 破位造成严重鞭打；主力因子近端 IC 为负（该池近期呈动量反转特征，ICIR 已自动降权，机制按设计工作）。

**v2 迭代方向**（按预期收益排序）：
1. 止损改 ATR 自适应（高波动板块放宽），或止损幅度按板块波动率分层
2. 破位退出加缓冲带（close < MA20×0.97 才触发），降低 255 次小额亏损退出
3. 退出后冷却期 + 趋势重立才回补（避免高位砍、更高位接回）
4. 主力因子在 200 日窗口持续累积后重估 IC；当前负 IC 或为反转期特征，可测试 direction=-1
5. 调仓日保留仍在趋势中的旧持仓（降低 78% 月换手）

## 文件清单

- backend/data/sector_pool.json · app/services/quant/sector_pool.py
- app/models/chain_models.py（FundFlowDaily/SectorScore/RotationSignal）
- scripts/backfill_em_fund_flow.py · backfill_mootdx_klines.py（--pool）· load_seed_to_db.py（load_fund_flow + upsert 修复）
- app/services/quant/factors/fund_flow_factors.py · factor_model.py（NaN 鲁棒 + IC 滞后）
- app/services/quant/sector_rotation.py · rotation_backtest.py · rotation_service.py
- app/routers/quant.py · app/services/scheduler.py · refresh_service.py
- frontend/src/types/rotation.ts · services/api.ts · chainkb/RotationPanel.tsx · ChainKbPage.tsx
- backend/tests/test_rotation.py（20 用例：因子公式/无前视/NaN 鲁棒/IC 滞后/板块聚合/选股门控/回测冒烟/解析/DB 集成）
