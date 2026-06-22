# Tushare Index Data API Reference

## index_basic - 指数基本信息

获取指数基础信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 指数代码 |
| name | str | No | 指数名称 |
| market | str | No | 市场代码（SSE上交所SZSE深交所） |
| type | str | No | 指数类型 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 指数代码 |
| name | 指数名称 |
| market | 市场代码（SSE上交所SZSE深交所） |
| publisher | 发布方 |
| index_type | 指数类型 |
| category | 指数类别 |
| base_date | 基期 |
| base_point | 基点 |
| list_date | 发布日期 |
| weight_rule | 加权规则 |
| desc | 指数描述 |
| exp_date | 到期日期 |

### Example
```python
# 获取所有指数
df = pro.index_basic()

# 获取上证指数
df = pro.index_basic(ts_code='000001.SH')

# 获取深交所指数
df = pro.index_basic(market='SZSE')
```

---

## index_daily - 指数日线行情

获取指数日线行情数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 指数代码（支持多选） |
| trade_date | str | No | 交易日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 指数代码 |
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| pre_close | 昨收价 |
| change | 涨跌额 |
| pct_chg | 涨跌幅(%) |
| vol | 成交量（手） |
| amount | 成交额（千元） |

### Example
```python
# 上证指数日线
df = pro.index_daily(
    ts_code='000001.SH',
    start_date='20240101',
    end_date='20240201'
)

# 沪深300指数
df = pro.index_daily(
    ts_code='000300.SH',
    start_date='20240101',
    end_date='20240201'
)

# 多个指数
df = pro.index_daily(
    ts_code='000001.SH,399001.SZ,000300.SH',
    start_date='20240101'
)
```

---

## index_classify - 行业分类

获取行业分类信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| level | str | Yes | 行业级别（L1一级L2二级） |
| src | str | Yes | 数据来源（SW申万L1申万L2中信CITIC） |

### Return Fields
| Field | Description |
|-------|-------------|
| index_code | 指数代码 |
| industry_name | 行业名称 |
| level | 行业级别 |
| parent_code | 父级代码 |
| is_pub | 是否公开 |

### Example
```python
# 申万一级行业
df = pro.index_classify(level='L1', src='SW')

# 申万二级行业
df = pro.index_classify(level='L2', src='SW')

# 中信行业分类
df = pro.index_classify(level='L1', src='CITIC')
```

---

## index_weight - 指数成分股权重

获取指数成分股权重信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| index_code | str | Yes | 指数代码 |
| con_date | str | No | 截止日期 |
| into_date | str | No | 纳入日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| index_code | 指数代码 |
| con_code | 成分股代码 |
| con_name | 成分股名称 |
| weight | 权重 |
| con_date | 截止日期 |
| into_date | 纳入日期 |
| note | 备注 |

### Example
```python
# 沪深300成分股权重
df = pro.index_weight(
    index_code='000300.SH',
    con_date='20240101'
)

# 上证50成分股权重
df = pro.index_weight(
    index_code='000016.SH',
    con_date='20240101'
)
```

---

## index_member - 指数成分股

获取指数成分股列表

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | Yes | 指数代码 |
| index_code | str | No | 同ts_code |
| in_date | str | No | 纳入日期 |
| out_date | str | No | 剔除日期 |
| is_new | str | No | 是否最新（1是0否） |

### Return Fields
| Field | Description |
|-------|-------------|
| index_code | 指数代码 |
| con_code | 成分股代码 |
| con_name | 成分股名称 |
| in_date | 纳入日期 |
| out_date | 剔除日期 |
| is_new | 是否最新 |

### Example
```python
# 沪深300成分股
df = pro.index_member(
    ts_code='000300.SH',
    is_new='1'
)

# 中证500成分股
df = pro.index_member(
    ts_code='000905.SH',
    is_new='1'
)
```

---

## index_dailywx - 指数日线(不含未停牌)

获取指数日线行情（不含未停牌股票）

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 指数代码 |
| trade_date | str | No | 交易日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
与`index_daily`相同

### Example
```python
df = pro.index_dailywx(
    ts_code='000300.SH',
    start_date='20240101'
)
```

---

## 指数数据使用建议

### 常用指数代码

```python
# 主要市场指数
major_indices = {
    '000001.SH': '上证指数',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000300.SH': '沪深300',
    '000016.SH': '上证50',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
}

# 行业指数
industry_indices = {
    '801010.SI': '申万农林牧渔',
    '801020.SI': '申万采掘',
    '801030.SI': '申万化工',
    '801040.SI': '申万钢铁',
    '801050.SI': '申万有色金属',
    '801080.SI': '申万电子',
    '801110.SI': '申万家用电器',
    '801120.SI': '申万食品饮料',
    '801140.SI': '申万纺织服装',
    '801150.SI': '申万轻工制造',
    '801160.SI': '申万医药生物',
    '801170.SI': '申万公用事业',
    '801180.SI': '申万交通运输',
    '801200.SI': '申万房地产',
    '801210.SI': '申万金融服务',
    '801230.SI': '申万商业贸易',
    '801710.SI': '申万建筑材料',
    '801720.SI': '申万建筑装饰',
    '801730.SI': '申万电气设备',
    '801740.SI': '申万国防军工',
    '801750.SI': '申万计算机',
    '801760.SI': '申万传媒',
    '801770.SI': '申万通信',
    '801780.SI': '申万银行',
    '801790.SI': '申万非银金融',
    '801880.SI': '申万汽车',
    '801890.SI': '申万机械设备',
}
```

### 指数成分股分析

```python
# 获取指数成分股权重
def get_index_weights(index_code, date):
    df = pro.index_weight(index_code=index_code, con_date=date)
    return df.sort_values('weight', ascending=False)

# 获取指数前十大权重股
def get_top_weights(index_code, date, top_n=10):
    df = get_index_weights(index_code, date)
    return df.head(top_n)

# 获取指数成分股
def get_index_members(index_code, is_new='1'):
    df = pro.index_member(ts_code=index_code, is_new=is_new)
    return df
```

### 行业轮动分析

```python
# 获取申万一级行业指数表现
def analyze_sector_performance(start_date, end_date):
    sectors = pro.index_classify(level='L1', src='SW')
    sector_codes = sectors['index_code'].tolist()

    # 获取所有行业指数行情
    dfs = []
    for code in sector_codes:
        df = pro.index_daily(
            ts_code=code,
            start_date=start_date,
            end_date=end_date
        )
        dfs.append(df)

    # 合并数据并计算涨跌幅
    all_data = pd.concat(dfs)
    performance = all_data.groupby('ts_code')['pct_chg'].sum()
    return performance.sort_values(ascending=False)
```

### 指数估值分析

```python
# 获取指数估值数据
def get_index_valuation(index_code, trade_date):
    df = pro.index_basic(ts_code=index_code)
    # 结合daily_basic数据获取PE、PB等指标
    basic_df = pro.daily_basic(
        ts_code=index_code,
        trade_date=trade_date
    )
    return basic_df
```
