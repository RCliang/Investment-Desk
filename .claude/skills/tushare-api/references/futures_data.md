# Tushare Futures Data API Reference

## fut_basic - 期货合约信息

获取期货合约基础信息

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 合约代码 |
| exchange | str | No | 交易所代码 |
| fut_type | str | No | 合约类型 |
| trade_date | str | No | 交易日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| symbol | 合约简称 |
| name | 合约名称 |
| fut_type | 合约类型 |
| multiplier | 合约乘数 |
| trade_unit | 交易单位 |
| per_unit_mark | 每 tick 最小变动价位 |
| quote_unit | 报价单位 |
| quote_unit_desc | 报价单位描述 |
| d_mode_desc | 交割方式描述 |
| list_date | 上市日期 |
| delist_date | 最后交易日期 |
| trade_time_desc | 交易时间段描述 |

### Example
```python
# 获取所有期货合约
df = pro.fut_basic()

# 获取特定交易所合约
df = pro.fut_basic(exchange='CFFEX')

# 获取特定合约
df = pro.fut_basic(ts_code='IF2401')
```

---

## fut_daily - 期货行情

获取期货日线行情数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 合约代码（支持多选） |
| trade_date | str | No | 交易日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |
| exchange | str | No | 交易所代码 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| trade_date | 交易日期 |
| pre_close | 昨收盘 |
| pre_settle | 昨结算价 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| settle | 结算价 |
| change1 | 涨跌1（收盘价-昨结算价） |
| change2 | 涨跌2（结算价-昨结算价） |
| vol | 成交量（手） |
| amount | 成交额（万元） |
| oi | 持仓量（手） |
| oi_chg | 持仓量变化 |

### Example
```python
# 获取股指期货日线
df = pro.fut_daily(
    ts_code='IF2401',
    start_date='20240101',
    end_date='20240201'
)

# 获取商品期货日线
df = pro.fut_daily(
    ts_code='AU2406',
    start_date='20240101'
)

# 获取交易所所有合约
df = pro.fut_daily(
    exchange='CFFEX',
    start_date='20240101'
)
```

---

## fut_mins - 期货分钟行情

获取期货分钟级K线数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | Yes | 合约代码 |
| trade_date | str | Yes | 交易日期 |
| freq | str | No | K线频率：1min/5min/15min/30min/60min |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| trade_time | 交易时间 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量（手） |
| amount | 成交额（万元） |
| oi | 持仓量（手） |

### Example
```python
# 1分钟线
df = pro.fut_mins(
    ts_code='IF2401',
    trade_date='20240201',
    freq='1min'
)

# 5分钟线
df = pro.fut_mins(
    ts_code='IF2401',
    trade_date='20240201',
    freq='5min'
)
```

---

## fut_pos - 期货持仓排名

获取期货持仓排名数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | Yes | 合约代码 |
| trade_date | str | Yes | 交易日期 |
| broker_type | str | No | 经纪商类型 |
| data_type | str | No | 数据类型 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| trade_date | 交易日期 |
| broker | 期货公司名称 |
| vol_type | 持仓类型（成交量/持买单量/持卖单量） |
| ranking | 排名 |
| vol | 成交量/持仓量 |
| vol_chg | 变化量 |

### Example
```python
df = pro.fut_pos(
    ts_code='IF2401',
    trade_date='20240201'
)
```

---

## fut_settle - 期货结算

获取期货结算数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 合约代码 |
| trade_date | str | No | 交易日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| trade_date | 交易日期 |
| pre_settle | 上期结算价 |
| settle | 当期结算价 |
| settle_chg | 结算价变化 |
| volume | 成交量 |
| amount | 成交额 |
| open_interest | 持仓量 |
| oi_chg | 持仓量变化 |

### Example
```python
df = pro.fut_settle(
    ts_code='IF2401',
    trade_date='20240201'
)
```

---

## fut_openinterest - 期货持仓量

获取期货持仓量数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 合约代码 |
| trade_date | str | No | 交易日期 |
| start_date | str | No | 开始日期 |
| end_date | str | No | 结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 合约代码 |
| trade_date | 交易日期 |
| open_interest | 持仓量（手） |
| oi_chg | 持仓量变化 |

### Example
```python
df = pro.fut_openinterest(
    ts_code='IF2401',
    start_date='20240101',
    end_date='20240201'
)
```

---

## 期货交易所代码

```python
exchanges = {
    'CFFEX': '中国金融期货交易所',  # 股指期货、国债期货
    'SHFE': '上海期货交易所',      # 有色金属、黄金、钢材
    'DCE': '大连商品交易所',       # 农产品、化工品
    'CZCE': '郑州商品交易所',      # 农产品、化工品
    'INE': '上海国际能源交易中心',  # 原油、20号胶
}
```

---

## 常用期货合约代码

```python
# 股指期货（CFFEX）
stock_index_futures = {
    'IF': '沪深300股指期货',
    'IH': '上证50股指期货',
    'IC': '中证500股指期货',
    'IM': '中证1000股指期货',
}

# 国债期货（CFFEX）
bond_futures = {
    'T': '10年期国债期货',
    'TF': '5年期国债期货',
    'TS': '2年期国债期货',
}

# 商品期货（SHFE）
metal_futures = {
    'CU': '铜',
    'AL': '铝',
    'ZN': '锌',
    'PB': '铅',
    'NI': '镍',
    'SN': '锡',
    'AU': '黄金',
    'AG': '白银',
}

# 能化期货（SHFE/INE/INE）
energy_futures = {
    'RB': '螺纹钢',
    'HC': '热轧卷板',
    'SC': '原油',
    'NR': '20号胶',
}

# 农产品期货（DCE/CZCE）
agri_futures = {
    'M': '豆粕',
    'Y': '豆油',
    'A': '豆一',
    'C': '玉米',
    'CS': '玉米淀粉',
    'JD': '鸡蛋',
    'L': '聚乙烯',
    'PP': '聚丙烯',
    'V': '聚氯乙烯',
    'SR': '白糖',
    'CF': '棉花',
    'RM': '菜籽粕',
    'OI': '菜籽油',
}
```

---

## 期货数据使用建议

### 期现套利分析

```python
# 获取期货和现货数据
def analyze_basis(fut_code, start_date, end_date):
    # 获取期货数据
    fut_df = pro.fut_daily(
        ts_code=fut_code,
        start_date=start_date,
        end_date=end_date
    )

    # 获取对应的现货指数数据
    index_code = fut_code[:2] + '000.SH'  # IF -> IF000.SH
    index_df = pro.index_daily(
        ts_code=index_code,
        start_date=start_date,
        end_date=end_date
    )

    # 合并数据计算基差
    df = pd.merge(
        fut_df[['trade_date', 'settle']],
        index_df[['trade_date', 'close']],
        on='trade_date'
    )
    df['basis'] = df['settle'] - df['close']
    df['basis_rate'] = df['basis'] / df['close'] * 100

    return df
```

### 跨期套利分析

```python
# 获取不同到期日的期货合约价差
def analyze_calendar_spread(code1, code2, start_date, end_date):
    df1 = pro.fut_daily(
        ts_code=code1,
        start_date=start_date,
        end_date=end_date
    )

    df2 = pro.fut_daily(
        ts_code=code2,
        start_date=start_date,
        end_date=end_date
    )

    # 计算价差
    df = pd.merge(
        df1[['trade_date', 'settle']],
        df2[['trade_date', 'settle']],
        on='trade_date',
        suffixes=('_1', '_2')
    )
    df['spread'] = df['settle_1'] - df['settle_2']

    return df
```

### 持仓量分析

```python
# 分析持仓量变化趋势
def analyze_open_interest(ts_code, start_date, end_date):
    df = pro.fut_daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date
    )

    # 计算持仓量变化
    df['oi_ma5'] = df['oi'].rolling(5).mean()
    df['oi_change'] = df['oi'].diff()

    return df
```

### 主力合约识别

```python
# 识别主力合约（持仓量最大的合约）
def get_main_contract(symbol, trade_date):
    # 获取该品种所有合约
    df = pro.fut_basic(exchange=symbol[:4])

    # 获取各合约持仓量
    oi_list = []
    for code in df['ts_code']:
        try:
            oi_df = pro.fut_openinterest(
                ts_code=code,
                trade_date=trade_date
            )
            if not oi_df.empty:
                oi_list.append({
                    'ts_code': code,
                    'oi': oi_df.iloc[0]['open_interest']
                })
        except:
            continue

    # 找出持仓量最大的合约
    if oi_list:
        oi_df = pd.DataFrame(oi_list)
        main_contract = oi_df.loc[oi_df['oi'].idxmax(), 'ts_code']
        return main_contract

    return None
```
