# Tushare Macro Economic Data API Reference

## shibor - SHIBOR利率

获取上海银行间同业拆放利率（SHIBOR）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date | str | No | 日期（格式：YYYYMMDD） |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| date | 日期 |
| overnight | 隔夜利率 |
| 1w | 1周利率 |
| 2w | 2周利率 |
| 1m | 1个月利率 |
| 3m | 3个月利率 |
| 6m | 6个月利率 |
| 9m | 9个月利率 |
| 1y | 1年利率 |

### Example
```python
# 获取SHIBOR数据
df = pro.shibor(
    start_date='20240101',
    end_date='20240201'
)

# 获取单日SHIBOR
df = pro.shibor(date='20240201')
```

---

## shibor_quote - SHIBOR报价

获取SHIBOR报价数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date | str | No | 日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |
| bank_type | str | No | 银行类型 |

### Return Fields
| Field | Description |
|-------|-------------|
| date | 日期 |
| bank_type | 银行类型 |
| overnight | 隔夜利率 |
| 1w | 1周利率 |
| 2w | 2周利率 |
| 1m | 1个月利率 |
| 3m | 3个月利率 |
| 6m | 6个月利率 |
| 9m | 9个月利率 |
| 1y | 1年利率 |

### Example
```python
df = pro.shibor_quote(
    start_date='20240101',
    end_date='20240201'
)
```

---

## lpr - 贷款市场报价利率

获取贷款市场报价利率（LPR）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date | str | No | 日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| date | 日期 |
| 1y | 1年期LPR |
| 5y | 5年期以上LPR |

### Example
```python
df = pro.lpr(
    start_date='20230101',
    end_date='20240201'
)
```

---

## gdp - 国内生产总值

获取GDP（国内生产总值）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| quarter | str | No | 季度（格式：YYYYQ1/Q2/Q3/Q4） |
| start_q | str | No | 开始季度 |
| end_q | str | No | 结束季度 |

### Return Fields
| Field | Description |
|-------|-------------|
| quarter | 季度 |
| gdp | 国内生产总值（亿元） |
| gdp_pc | 人均国内生产总值（元） |
| pri_ind_gdp | 第一产业GDP（亿元） |
| sec_ind_gdp | 第二产业GDP（亿元） |
| ter_ind_gdp | 第三产业GDP（亿元） |

### Example
```python
# 获取GDP数据
df = pro.gdp(
    start_q='2023Q1',
    end_q='2023Q4'
)
```

---

## cpi - 居民消费价格指数

获取CPI（居民消费价格指数）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | TS代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | TS代码 |
| date | 日期 |
| cpi | 全国居民消费价格指数 |
| cpi_yoy | CPI同比 |
| cpi_mom | CPI环比 |
| food_cpi_yoy | 食品CPI同比 |
| nonfood_cpi_yoy | 非食品CPI同比 |

### Example
```python
df = pro.cpi(
    start_date='20230101',
    end_date='20240201'
)
```

---

## ppi - 工业品出厂价格指数

获取PPI（工业品出厂价格指数）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | TS代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | TS代码 |
| date | 日期 |
| ppi | 工业品出厂价格指数 |
| ppi_yoy | PPI同比 |
| ppi_mom | PPI环比 |
| ppi_prod_yoy | 生产资料PPI同比 |
| ppi_life_yoy | 生活资料PPI同比 |

### Example
```python
df = pro.ppi(
    start_date='20230101',
    end_date='20240201'
)
```

---

## pmi - 采购经理指数

获取PMI（采购经理指数）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | TS代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | TS代码 |
| date | 日期 |
| pmi | 制造业PMI |
| pmi_new_orders | 新订单指数 |
| pmi_output | 生产指数 |
| pmi_emp | 从业人员指数 |
| pmi_supplier_deliver | 供应商配送时间指数 |
| pmi_raw_inventory | 原材料库存指数 |
| pmi_order_inventory | 产成品库存指数 |
| pmi_purchase | 采购量指数 |
| pmi_import | 进口指数 |
| pmi_export | 新出口订单指数 |
| pmi_purchase_price | 主要原材料购进价格指数 |

### Example
```python
df = pro.pmi(
    start_date='20230101',
    end_date='20240201'
)
```

---

## m2 - 货币供应量

获取M2（广义货币供应量）数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | TS代码 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |
| period | str | No | 报告期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | TS代码 |
| date | 日期 |
| m2 | 广义货币供应量（亿元） |
| m2_yoy | M2同比 |
| m2_mom | M2环比 |
| m1 | 狭义货币供应量（亿元） |
| m1_yoy | M1同比 |
| m1_mom | M1环比 |
| m0 | 流通中现金（亿元） |
| m0_yoy | M0同比 |
| m0_mom | M0环比 |

### Example
```python
df = pro.m2(
    start_date='20230101',
    end_date='20240201'
)
```

---

## 其他宏观经济指标

### 工业增加值

```python
# 工业增加值数据
df = pro.iai_ind(
    start_date='20230101',
    end_date='20240201'
)
```

### 社会消费品零售总额

```python
# 社会消费品零售总额
df = pro.retail_sale(
    start_date='20230101',
    end_date='20240201'
)
```

### 固定资产投资

```python
# 固定资产投资
df = pro.fai(
    start_date='20230101',
    end_date='20240201'
)
```

### 进出口数据

```python
# 进出口数据
df = pro.trade(
    start_date='20230101',
    end_date='20240201'
)
```

---

## 宏观数据使用建议

### 经济周期分析

```python
# 分析经济周期指标
def analyze_economic_cycle(start_date, end_date):
    # 获取PMI数据
    pmi_df = pro.pmi(start_date=start_date, end_date=end_date)

    # 获取CPI数据
    cpi_df = pro.cpi(start_date=start_date, end_date=end_date)

    # 获取PPI数据
    ppi_df = pro.ppi(start_date=start_date, end_date=end_date)

    # 判断经济周期
    latest_pmi = pmi_df.iloc[-1]['pmi']
    latest_cpi = cpi_df.iloc[-1]['cpi_yoy']
    latest_ppi = ppi_df.iloc[-1]['ppi_yoy']

    if latest_pmi > 50 and latest_cpi > 2:
        cycle = '扩张期'
    elif latest_pmi < 50 and latest_cpi < 2:
        cycle = '衰退期'
    elif latest_pmi > 50 and latest_cpi < 2:
        cycle = '复苏期'
    else:
        cycle = '滞胀期'

    return {
        'cycle': cycle,
        'pmi': latest_pmi,
        'cpi': latest_cpi,
        'ppi': latest_ppi
    }
```

### 货币政策分析

```python
# 分析货币政策松紧
def analyze_monetary_policy(start_date, end_date):
    # 获取M2数据
    m2_df = pro.m2(start_date=start_date, end_date=end_date)

    # 获取SHIBOR数据
    shibor_df = pro.shibor(start_date=start_date, end_date=end_date)

    # 获取LPR数据
    lpr_df = pro.lpr(start_date=start_date, end_date=end_date)

    # 判断货币政策
    latest_m2_yoy = m2_df.iloc[-1]['m2_yoy']
    latest_shibor_1w = shibor_df.iloc[-1]['1w']
    latest_lpr_1y = lpr_df.iloc[-1]['1y']

    if latest_m2_yoy > 10 and latest_shibor_1w < 2:
        policy = '宽松'
    elif latest_m2_yoy < 8 and latest_shibor_1w > 3:
        policy = '紧缩'
    else:
        policy = '中性'

    return {
        'policy': policy,
        'm2_growth': latest_m2_yoy,
        'shibor_1w': latest_shibor_1w,
        'lpr_1y': latest_lpr_1y
    }
```

### 宏观因子构建

```python
# 构建宏观因子
def build_macro_factors(start_date, end_date):
    factors = {}

    # 增长因子：PMI
    pmi_df = pro.pmi(start_date=start_date, end_date=end_date)
    factors['growth'] = pmi_df.set_index('date')['pmi']

    # 通胀因子：CPI
    cpi_df = pro.cpi(start_date=start_date, end_date=end_date)
    factors['inflation'] = cpi_df.set_index('date')['cpi_yoy']

    # 利率因子：SHIBOR
    shibor_df = pro.shibor(start_date=start_date, end_date=end_date)
    factors['interest_rate'] = shibor_df.set_index('date')['1w']

    # 货币因子：M2
    m2_df = pro.m2(start_date=start_date, end_date=end_date)
    factors['monetary'] = m2_df.set_index('date')['m2_yoy']

    return pd.DataFrame(factors)
```

### 行业轮动策略

```python
# 基于宏观因子的行业轮动
def sector_rotation_by_macro(macro_date):
    # 获取宏观指标
    pmi = pro.pmi(start_date=macro_date, end_date=macro_date).iloc[-1]['pmi']
    cpi = pro.cpi(start_date=macro_date, end_date=macro_date).iloc[-1]['cpi_yoy']

    # 根据宏观环境选择行业
    if pmi > 50 and cpi < 2:
        # 经济复苏期：配置周期股
        sectors = ['801020.SI', '801040.SI', '801880.SI']  # 采掘、钢铁、汽车
    elif pmi > 50 and cpi > 3:
        # 经济过热期：配置能源、原材料
        sectors = ['801020.SI', '801050.SI', '801010.SI']  # 采掘、有色、农林牧渔
    elif pmi < 50 and cpi > 3:
        # 滞胀期：配置防御性行业
        sectors = ['801120.SI', '801150.SI', '801170.SI']  # 食品饮料、医药、公用事业
    else:
        # 衰退期：配置成长股
        sectors = ['801750.SI', '801730.SI', '801780.SI']  # 计算机、电气设备、通信

    return sectors
```

---

## 宏观指标阈值参考

| 指标 | 阈值 | 含义 |
|------|------|------|
| PMI | 50 | >50 扩张，<50 收缩 |
| CPI | 3% | >3% 通胀压力 |
| CPI | 2% | 目标通胀率 |
| CPI | 1% | <1% 通缩压力 |
| PPI | 0 | 正增长企业盈利改善 |
| M2同比 | 8-10% | 适度增长 |
| M2同比 | >10% | 货币宽松 |
| SHIBOR隔夜 | 2% | 适度利率水平 |
| LPR 1年期 | 3.5% | 参考利率 |
| GDP增速 | 6% | 潜在增长率 |
