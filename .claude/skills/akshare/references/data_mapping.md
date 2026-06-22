# Data Mapping Between AkShare and quant-trading-alerts

Field name mappings and data format conversions between AkShare API and system format.

## K-line Data (K线数据)

### AkShare → System Format

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 日期 | date | datetime | Trading date |
| 代码 | symbol | str | Stock code (Tushare format) |
| 开盘 | open | float | Opening price |
| 收盘 | close | float | Closing price |
| 最高 | high | float | Highest price |
| 最低 | low | float | Lowest price |
| 成交量 | volume | int | Trading volume (shares) |
| 成交额 | turnover | float | Trading amount (RMB) |
| 振幅 | amplitude | float | Price amplitude (%) |
| 涨跌幅 | pct_chg | float | Price change percentage |
| 涨跌额 | change | float | Price change amount |
| 换手率 | turnover_rate | float | Turnover rate (%) |

### Conversion Example

```python
# AkShare raw data
{
    '日期': '2024-01-01',
    '代码': '000001',
    '开盘': 10.5,
    '收盘': 10.8,
    '最高': 10.9,
    '最低': 10.4,
    '成交量': 1000000,
    '成交额': 10800000.0,
    '振幅': 4.76,
    '涨跌幅': 2.86,
    '涨跌额': 0.3,
    '换手率': 1.2
}

# System format
{
    'date': pd.Timestamp('2024-01-01'),
    'symbol': '000001.SZ',
    'open': 10.5,
    'close': 10.8,
    'high': 10.9,
    'low': 10.4,
    'volume': 1000000,
    'turnover': 10800000.0,
    'amplitude': 4.76,
    'pct_chg': 2.86,
    'turnover_rate': 1.2
}
```

## Stock Basic Info (股票基本信息)

### Real-time Quotes Fields

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 代码 | ts_code/symbol | str | Stock code |
| 名称 | name | str | Stock name |
| 最新价 | close/price | float | Latest price |
| 今开 | open | float | Today's open |
| 昨收 | pre_close | float | Previous close |
| 最高 | high | float | Today's high |
| 最低 | low | float | Today's low |
| 成交量 | volume | int | Volume |
| 成交额 | turnover | float | Turnover |
| 振幅 | amplitude | float | Amplitude (%) |
| 涨跌幅 | pct_chg | float | Change % |
| 涨跌额 | change | float | Change amount |
| 换手率 | turnover_rate | float | Turnover rate (%) |
| 量比 | volume_ratio | float | Volume ratio |
| 市盈率-动态 | pe_ttm | float | PE ratio (TTM) |
| 市净率 | pb | float | PB ratio |
| 总市值 | total_mv | float | Total market cap |
| 流通市值 | circ_mv | float | Circulating market cap |

## Financial Data (财务数据)

### Financial Indicators

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| ROE-摊薄 | roe | float | Return on equity (%) |
| 营业总收入 | revenue | float | Total revenue |
| 营业收入同比增长 | or_rev_yoy | float | Revenue growth YoY (%) |
| 净利润 | net_profit | float | Net profit |
| 净利润同比增长 | np_yoy | float | Net profit growth YoY (%) |
| 销售净利率 | netprofit_margin | float | Net profit margin (%) |
| 销售毛利率 | gross_margin | float | Gross margin (%) |
| 资产负债率 | debt_to_assets | float | Debt to assets ratio (%) |
| 流动比率 | current_ratio | float | Current ratio |
| 速动比率 | quick_ratio | float | Quick ratio |
| 每股收益 | eps | float | Earnings per share |
| 每股净资产 | naps | float | Net assets per share |

### Date Field Handling

Financial data often uses report period (报告期) format:

```python
# AkShare format: '2024-03-31' or '2024一季'
# System format: '20240331'

def convert_report_period(period: str) -> str:
    """Convert report period to system format"""
    # Handle '2024-03-31' format
    if '-' in period:
        return period.replace('-', '')

    # Handle '2024一季' format
    import re
    match = re.match(r'(\d{4})(.*)', period)
    if match:
        year, quarter = match.groups()
        quarter_map = {'一季': '0331', '中报': '0630', '三季': '0930', '年报': '1231'}
        return year + quarter_map.get(quarter, '1231')

    return period
```

## Concept & Sector Data (概念板块数据)

### Concept Board Fields

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 板块名称 | board_name | str | Concept board name |
| 最新价 | board_price | float | Board index price |
| 涨跌幅 | board_pct_chg | float | Board change % |
| 总市值 | total_mv | float | Total market cap |
| 成交量 | volume | int | Volume |
| 换手率 | turnover_rate | float | Turnover rate (%) |
| 上涨家数 | up_count | int | Number of rising stocks |
| 下跌家数 | down_count | int | Number of falling stocks |
| 领涨股票 | leader_stock | str | Leading stock |

## Limit-up Data (涨停板数据)

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 代码 | ts_code/symbol | str | Stock code |
| 名称 | name | str | Stock name |
| 最新价 | close/price | float | Latest price |
| 涨跌幅 | pct_chg | float | Change % |
| 成交额 | turnover | float | Turnover |
| 换手率 | turnover_rate | float | Turnover rate (%) |
| 封单金额 | seal_amount | float | Limit-up seal amount |
| 首次封板时间 | first_seal_time | str | First seal time |
| 最后封板时间 | last_seal_time | str | Last seal time |
| 封板次数 | seal_count | int | Seal count |
| 打开次数 | open_count | int | Open count |

## Margin Trading Data (融资融券数据)

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 交易日期 | trade_date | str | Trading date (YYYYMMDD) |
| 融资余额 | margin_balance | float | Margin balance |
| 融资买入额 | margin_buy | float | Margin buying amount |
| 融券余额 | short_balance | float | Short balance |
| 融券卖出量 | short_sell | float | Short selling volume |
| 融资融券余额 | total_balance | float | Total balance |

## Macro Economy Data (宏观经济数据)

### GDP Data

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 季度 | quarter | str | Quarter (e.g., '2024Q1') |
| 国内生产总值-绝对值 | gdp_value | float | GDP value |
| 国内生产总值-同比增长 | gdp_yoy | float | GDP growth YoY (%) |
| 第一产业 | primary_industry | float | Primary industry |
| 第二产业 | secondary_industry | float | Secondary industry |
| 第三产业 | tertiary_industry | float | Tertiary industry |

### CPI Data

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 月份 | month | str | Month (e.g., '2024-01') |
| 全国当月 | cpi_current | float | Current CPI |
| 全国同比增长 | cpi_yoy | float | CPI YoY growth |
| 全国环比增长 | cpi_mom | float | CPI MoM growth |

### PMI Data

| AkShare Field | System Field | Data Type | Description |
|--------------|--------------|-----------|-------------|
| 月份 | month | str | Month (e.g., '2024-01') |
| 制造业-指数 | pmi_manufacturing | float | Manufacturing PMI |
| 非制造业-指数 | pmi_non_manufacturing | float | Non-manufacturing PMI |
| 综合PMI | pmi_composite | float | Composite PMI |

## Date Format Conversion

### Common Date Formats

```python
# AkShare uses various date formats:
# - '2024-01-01' (daily data)
# - '20240101' (some historical data)
# - '2024一季' (financial reports)

# System format (Tushare style):
# - '20240101' (always YYYYMMDD)

def normalize_date(date_str: str) -> str:
    """Convert various date formats to YYYYMMDD"""
    # Remove dashes if present
    date_str = date_str.replace('-', '')

    # Handle quarter format
    if '一季' in date_str:
        return date_str.replace('一季', '0331')
    elif '中报' in date_str or '二季' in date_str:
        return date_str.replace('中报', '0630').replace('二季', '0630')
    elif '三季' in date_str:
        return date_str.replace('三季', '0931')
    elif '年报' in date_str or '四季' in date_str:
        return date_str.replace('年报', '1231').replace('四季', '1231')

    return date_str
```

## Stock Code Conversion

### Format Comparison

| System | Format | Example |
|--------|--------|---------|
| AkShare | 6 digits | 000001, 600000 |
| Tushare | 6 digits + exchange suffix | 000001.SZ, 600000.SH |
| Futu | Exchange prefix + 6 digits | SZ.000001, SH.600000 |

### Conversion Logic

```python
def akshare_to_tushare(akshare_code: str) -> str:
    """Convert AkShare format to Tushare format"""
    if akshare_code.startswith('6'):
        return f"{akshare_code}.SH"  # Shanghai
    elif akshare_code.startswith(('0', '3')):
        return f"{akshare_code}.SZ"  # Shenzhen
    elif akshare_code.startswith('8') or akshare_code.startswith('4'):
        return f"{akshare_code}.BJ"  # Beijing
    return akshare_code

def tushare_to_akshare(tushare_code: str) -> str:
    """Convert Tushare format to AkShare format"""
    return tushare_code.split('.')[0]

def futu_to_akshare(futu_code: str) -> str:
    """Convert Futu format to AkShare format"""
    if '.' in futu_code:
        return futu_code.split('.')[1]
    return futu_code
```

## Data Quality Checks

```python
def validate_kline_data(df: pd.DataFrame) -> bool:
    """Validate K-line data quality"""
    required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']

    # Check required columns
    if not all(col in df.columns for col in required_columns):
        return False

    # Check for null values
    if df[required_columns].isnull().any().any():
        return False

    # Check price relationships
    if (df['high'] < df['low']).any():
        return False

    if (df['high'] < df['open']).any() or (df['high'] < df['close']).any():
        return False

    if (df['low'] > df['open']).any() or (df['low'] > df['close']).any():
        return False

    # Check positive volume
    if (df['volume'] < 0).any():
        return False

    return True
```

## Performance Considerations

### Batch Processing

When fetching large amounts of data:

1. **Use batch API calls** where available (e.g., `stock_zh_a_spot_em()`)
2. **Add rate limiting** between requests (0.5-1 second delay)
3. **Implement caching** for frequently accessed data
4. **Use parallel processing** for independent stock codes

```python
import time
from concurrent.futures import ThreadPoolExecutor

def fetch_with_rate_limit(func, *args, **kwargs):
    """Fetch data with rate limiting"""
    time.sleep(0.5)  # 0.5 second delay between requests
    return func(*args, **kwargs)

def batch_fetch_stocks(symbols: list, api):
    """Fetch data for multiple stocks in parallel"""
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(
            lambda s: api.get_kline_daily(s, '20240101', '20240131'),
            symbols
        ))
    return results
```
