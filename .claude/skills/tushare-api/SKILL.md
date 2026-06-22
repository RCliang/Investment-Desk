---
name: tushare-api
description: Tushare Pro API documentation and reference for quantitative trading system development. Use when building data query modules, accessing financial market data, or implementing trading strategies that require Chinese stock/futures/market data. Provides quick reference for API parameters, return fields, and usage examples.
---

# Tushare API Reference

Tushare Pro is a Python financial data interface providing fast access to Chinese financial markets including stocks, futures, indices, and macroeconomic data.

## Quick Start

```python
import tushare as ts

# Initialize with your token
ts.set_token('YOUR_TOKEN')
pro = ts.pro_api()

# Query stock basic information
df = pro.stock_basic(exchange='', list_status='L')
```

## API Categories

### Stock Basic Data (基础数据)
- `stock_basic` - Stock list information
- `daily_basic` - Daily basic indicators (PE, PB, market cap)
- `trade_calendar` - Trading calendar
- `namechange` - Historical stock name changes
- `new_share` - IPO new stock information
- `stk_managers` - Listed company management
- `stk_rewards` - Dividend and stock split data

### Market Data (行情数据)
- `daily` - Historical daily K-line (OHLCV)
- `daily_std` - Real-time daily quotes
- `weekly` - Weekly K-line
- `monthly` - Monthly K-line
- `stk_mins` - Minute-level K-line data
- `adj_factor` - Price adjustment factors
- `stk_limit` - Limit up/down list
- `stk_sus` - Suspend/Resume trading

### Financial Data (财务数据)
- `income` - Income statement
- `balancesheet` - Balance sheet
- `cashflow` - Cash flow statement
- `fina_indicator` - Financial indicators
- `fina_audit` - Financial audit opinions
- `forecast` - Performance forecast
- `express` - Performance express reports

### Index Data (指数数据)
- `index_basic` - Index basic information
- `index_daily` - Index daily K-line
- `index_classify` - Industry classification (Shenwan/CITIC)
- `index_weight` - Index constituent weights

### Futures Data (期货数据)
- `fut_basic` - Futures contract information
- `fut_daily` - Futures daily K-line
- `fut_mins` - Futures minute data
- `fut_pos` - Futures position ranking

### Macro Economy (宏观经济)
- `shibor` - SHIBOR interest rate
- `shibor_quote` - SHIBOR quote data
- `lpr` - LPR (Loan Prime Rate)
- `gdp` - Gross Domestic Product
- `cpi` - Consumer Price Index
- `ppi` - Producer Price Index
- `pmi` - Purchasing Managers Index

## Stock Code Format

- Shanghai SSE: `.SH` (e.g., `600000.SH` for stocks, `000001.SH` for indices)
- Shenzhen SZSE: `.SZ` (e.g., `000001.SZ` for stocks, `399005.SZ` for indices)
- Beijing BSE: `.BJ` (stocks starting with 9)
- Hong Kong HKEX: `.HK` (e.g., `00001.HK`)

## Common Query Patterns

### Get Daily K-line Data
```python
# Query daily data for multiple stocks
df = pro.daily(
    ts_code='600000.SH,000001.SZ',
    start_date='20240101',
    end_date='20240201'
)
```

### Get Stock List
```python
# Get all listed stocks
df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,area,industry,list_date')
```

### Get Financial Indicators
```python
# Get latest financial indicators
df = pro.fina_indicator(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20231231'
)
```

## Detailed API Reference

For detailed API parameters, return fields, and usage examples, see:
- [Stock Basic Data Reference](references/stock_basic.md)
- [Market Data Reference](references/market_data.md)
- [Financial Data Reference](references/financial_data.md)
- [Index Data Reference](references/index_data.md)
- [Futures Data Reference](references/futures_data.md)
- [Macro Data Reference](references/macro_data.md)

## Resources

- Official Documentation: https://tushare.pro/document/2
- GitHub Repository: https://github.com/waditu
- WeChat Public: waditu

## Error Handling

```python
# Handle rate limits and errors
try:
    df = pro.daily(ts_code='600000.SH', start_date='20240101')
except ts.errors.TushareException as e:
    print(f"Tushare API Error: {e}")
```
