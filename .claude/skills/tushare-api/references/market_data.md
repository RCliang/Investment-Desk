# Tushare Market Data API Reference

## daily - 日线行情

获取股票日线行情数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码（支持多选，逗号分隔） |
| trade_date | str | No | 交易日期（YYYYMMDD格式） |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| pre_close | 昨收价 |
| change | 涨跌额 |
| pct_chg | 涨跌幅（%） |
| vol | 成交量（手） |
| amount | 成交额（千元） |

### Example
```python
# 单只股票
df = pro.daily(
    ts_code='600000.SH',
    start_date='20240101',
    end_date='20240201'
)

# 多只股票
df = pro.daily(
    ts_code='600000.SH,000001.SZ,600036.SH',
    start_date='20240101',
    end_date='20240201'
)
```

---

## daily_std - 实时行情

获取实时行情数据（需更高积分权限）

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| trade_date | str | No | 交易日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量（手） |
| amount | 成交额（千元） |
| turnover_rate | 换手率 |

### Example
```python
df = pro.daily_std(ts_code='600000.SH', trade_date='20240201')
```

---

## weekly - 周线行情

获取股票周线行情数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量（手） |
| amount | 成交额（千元） |

### Example
```python
df = pro.weekly(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20240201'
)
```

---

## monthly - 月线行情

获取股票月线行情数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量（手） |
| amount | 成交额（千元） |

### Example
```python
df = pro.monthly(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20240201'
)
```

---

## stk_mins - 分钟行情

获取分钟级K线数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | Yes | 股票代码 |
| trade_date | str | Yes | 交易日期 |
| freq | str | No | K线频率：1min/5min/15min/30min/60min |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_time | 交易时间 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量（手） |
| amount | 成交额（千元） |

### Example
```python
# 1分钟线
df = pro.stk_mins(
    ts_code='600000.SH',
    trade_date='20240201',
    freq='1min'
)

# 5分钟线
df = pro.stk_mins(
    ts_code='600000.SH',
    trade_date='20240201',
    freq='5min'
)
```

---

## adj_factor - 复权因子

获取股票复权因子

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| trade_date | str | No | 交易日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| trade_date | 交易日期 |
| adj_factor | 复权因子 |

### Example
```python
df = pro.adj_factor(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20240201'
)

# 计算后复权价格
price_adj = price * adj_factor
```

---

## stk_limit - 涨跌停

获取每日涨跌停股票列表

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| trade_date | str | No | 交易日期 |
| ts_code | str | No | 股票代码 |
| limit_type | str | No | 类型：U涨停D跌停 |

### Return Fields
| Field | Description |
|-------|-------------|
| trade_date | 交易日期 |
| ts_code | 股票代码 |
| name | 股票名称 |
| close | 收盘价 |
| pct_chg | 涨跌幅 |
| amp | 振幅 |
| limit_type | 涨跌停类型（U涨D跌） |
| up_stat | 涨停统计（首次/多次） |
| limit_times | 封涨停次数 |

### Example
```python
# 涨停股票
df = pro.stk_limit(
    trade_date='20240201',
    limit_type='U'
)
```

---

## stk_sus - 停牌股票

获取停牌股票信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| suspend_date | str | No | 停牌日期 |
| resump_date | str | No | 复牌日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| name | 股票名称 |
| suspend_type | 停牌类型 |
| suspend_date | 停牌日期 |
| resump_date | 复牌日期 |
| suspend_reason | 停牌原因 |
| ann_date | 公告日期 |

### Example
```python
df = pro.stk_sus(suspend_date='20240201')
```

---

## 使用建议

### K线数据获取最佳实践

1. **日线数据：** 使用`daily`接口，支持批量获取
2. **分钟数据：** 使用`stk_mins`接口，需要指定日期和频率
3. **复权处理：** 使用`adj_factor`接口获取复权因子
4. **实时行情：** `daily_std`接口需要更高积分权限

### 数据频率选择

```python
# 根据策略选择合适的K线周期
freq_map = {
    'intraday': '1min',      # 日内交易
    'short_term': '5min',    # 短线
    'swing': 'daily',        # 波段
    'trend': 'weekly',       # 趋势
    'long_term': 'monthly'   # 长线
}
```

### 复权价格计算

```python
# 后复权价格
df = pro.daily(ts_code='600000.SH', start_date='20230101')
adj = pro.adj_factor(ts_code='600000.SH', start_date='20230101')

df = df.merge(adj, on=['ts_code', 'trade_date'])
df['close_adj'] = df['close'] * df['adj_factor']
```
