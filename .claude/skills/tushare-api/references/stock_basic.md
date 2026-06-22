# Tushare Stock Basic Data API Reference

## stock_basic - 股票列表

获取股票基础信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码（支持多选） |
| list_status | str | No | 上市状态：L上市D退市P暂停上市 |
| exchange | str | No | 交易所SSE上交所SZSE深交所 |
| is_hs | str | No | 是否沪深港通标的N否S沪H深 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| symbol | 股票简称 |
| name | 股票名称 |
| area | 所在地域 |
| industry | 所属行业 |
| market | 市场类型（主板/创业板/科创板） |
| list_date | 上市日期 |

### Example
```python
df = pro.stock_basic(
    exchange='',
    list_status='L',
    fields='ts_code,symbol,name,area,industry,list_date'
)
```

---

## daily_basic - 每日指标

获取每日股票指标（PE、PB、市值等）

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
| close | 收盘价 |
| turnover_rate | 换手率 |
| volume_ratio | 量比 |
| pe | 市盈率 |
| pe_ttm | 市盈率TTM |
| pb | 市净率 |
| ps | 市销率 |
| ps_ttm | 市销率TTM |
| dv_ratio | 股息率 |
| dv_ttm | 股息率TTM |
| total_share | 总股本（万股） |
| float_share | 流通股本（万股） |
| free_share | 自由流通股本（万股） |
| total_mv | 总市值（万元） |
| circ_mv | 流通市值（万元） |

### Example
```python
df = pro.daily_basic(
    ts_code='600000.SH',
    start_date='20240101',
    end_date='20240201'
)
```

---

## trade_calendar - 交易日历

获取交易日历信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| exchange | str | No | 交易所SSE上交所SZSE深交所 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| exchange | 交易所代码 |
| cal_date | 日历日期 |
| is_open | 是否开市（1开市0休市） |

### Example
```python
df = pro.trade_calendar(
    exchange='SSE',
    start_date='20240101',
    end_date='20240201'
)
```

---

## namechange - 历史名称变更

获取股票历史名称变更记录

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
| name | 股票名称 |
| start_date | 变更开始日期 |
| end_date | 变更结束日期 |
| change_reason | 变更原因 |

### Example
```python
df = pro.namechange(ts_code='600000.SH')
```

---

## new_share - IPO新股

获取新股上市信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| sub_code | 申购代码 |
| name | 股票名称 |
| ipo_date | 上市日期 |
| issue_date | 发行日期 |
| issue_price | 发行价格 |
| amount | 发行数量（万股） |
| market_amount | 网上发行数量（万股） |
| pe | 发行市盈率 |

### Example
```python
df = pro.new_share(
    start_date='20240101',
    end_date='20240201'
)
```

---

## stk_managers - 高管信息

获取上市公司高管信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| name | 姓名 |
| gender | 性别 |
| lev | 高管级别 |
| title | 职务 |
| edu | 教育背景 |
| birth_date | 出生年份 |
| begin_date | 开始任职日期 |
| end_date | 结束任职日期 |

### Example
```python
df = pro.stk_managers(ts_code='600000.SH')
```

---

## stk_rewards - 分红送股

获取上市公司分红送股信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| record_date | str | No | 股权登记日 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| div_proc | 实施进度 |
| stk_div | 每股送转比例 |
| stk_bo_rate | 每股转增比例 |
| stk_co_rate | 每股送股比例 |
| cash_div | 每股分红（税后） |
| cash_div_tax | 每股分红（税前） |
| record_date | 股权登记日 |
| ex_date | 除权除息日 |
| pay_date | 派息日 |

### Example
```python
df = pro.stk_rewards(
    ts_code='600000.SH',
    start_date='20230101'
)
```
