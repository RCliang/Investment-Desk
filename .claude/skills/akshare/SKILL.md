---
name: akshare
description: Comprehensive AkShare data integration for Chinese financial markets. Use when fetching: (1) Stock data - K-line, real-time quotes, stock pools (screening, limit-up, ST stocks, new stocks, IPO), (2) Financial data - statements, indicators, analysis, (3) Market data - indices, sectors (industry/concept), dragon-tiger list, fund flow, (4) Valuation - PE/PB ratios, market indicators, (5) Shareholder data - institutional holdings, insider trading, (6) News & events - company announcements, market news, (7) Macro economy - GDP, CPI, PMI, interest rates, money supply, (8) Derivatives - futures, bonds, convertible bonds, funds (ETF/LOF). Essential for quant-trading-alerts system integration with 100+ documented API functions.
---

# AkShare Data Integration

## Quick Start

### Installation

```bash
pip install akshare
```

### Basic Usage

```python
import akshare as ak

# Get stock historical data
df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20240101", end_date="20240131")

# Get stock real-time data
df = ak.stock_zh_a_spot_em()
```

## Data Categories

### 1. Stock Market Data (股票行情)
- **Historical K-line**: `stock_zh_a_hist()` - Daily/weekly/monthly data
- **Intraday data**: `stock_zh_a_hist_min_em()` - Minute-level K-line
- **Real-time quotes**: `stock_zh_a_spot_em()` - All A-shares with 20+ fields

### 2. Stock Pool Screening (股票池筛选)
- **Stock lists**: `stock_zh_a_spot_em()`, `stock_info_a_code_name()` - Complete A-share list
- **Strong stocks**: `stock_zt_pool_em()`, `stock_zt_pool_strong_em()` - Limit-up pools
- **Weak stocks**: `stock_dt_pool_em()` - Limit-down pools
- **New stocks**: `stock_new_sh()`, `stock_new_sz()`, `stock_ipo_list()` - IPO data
- **ST stocks**: `stock_zh_a_st_em()` - Filter high-risk stocks
- **Suspended**: `stock_paused_list()` - Trading suspension

### 3. Financial Data (财务数据)
- **Financial statements**: `stock_balance_sheet_by_report_em()`, `stock_profit_sheet_by_report_em()`, `stock_cash_flow_sheet_by_report_em()`
- **Financial indicators**: `stock_financial_analysis_indicator()` - ROE, margins, growth rates
- **Financial abstract**: `stock_financial_abstract()` - Key metrics summary

### 4. Index & Sector Data (指数与板块)
- **Index data**: `stock_zh_index_spot()`, `stock_zh_index_daily()` - Major indices (上证, 深证, 创业板, 科创50, 沪深300, 中证500/1000)
- **Index constituents**: `index_stock_cons()`, `index_cons_weight_bb()` - Stock lists from indices
- **Industry sectors**: `stock_board_industry_name_em()`, `stock_board_industry_cons_em()` - 银行, 证券, 医药, etc.
- **Concept sectors**: `stock_board_concept_name_em()`, `stock_board_concept_cons_em()` - ChatGPT, 机器人, 新能源, etc.

### 5. Dragon-Tiger List (龙虎榜)
- **Daily list**: `stock_lhb_em()`, `stock_lhb_detail_daily()` - Unusual trading activity
- **Institutional**: `stock_lhb_jgzj_detail()` - Institutional buys/sells
- **Brokerage**: `stock_lhb_yyb_detail()` - Top-performing departments

### 6. Fund Flow (资金流向)
- **Individual stock**: `stock_individual_fund_flow_rank()`, `stock_individual_fund_flow()` - Net inflow, main force, large orders
- **Stock popularity**: `stock_hot_rank_em()` - **Eastmoney popularity ranking (人气榜)** - Market attention, visits, discussions
- **Sector flow**: `stock_fund_flow_concept()`, `stock_fund_flow_industry()` - Concept/industry fund flow
- **Market-wide**: `stock_fund_flow_statistics()` - Overall market distribution
- **Northbound**: `stock_hsgt_fund_flow_summary()` - Stock connect capital flow

### 7. Valuation Indicators (估值指标)
- **Market valuation**: `stock_a_lg_indicator()`, `stock_zh_a_pe()`, `stock_zh_a_pb()` - PE, PB, PS, dividend yield
- **Index valuation**: `stock_index_pe()` - Index-level valuation metrics

### 8. Shareholder Data (股东数据)
- **Top shareholders**: `stock_zh_a_gdhs()`, `stock_zh_a_gdjc()` - Top 10 shareholders
- **Shareholder changes**: `stock_zh_a_shareholder_change()` - Increase/decrease data
- **Institutional**: `stock_fund_hold_composition()`, `stock_institutional_follow()` - Fund holdings, coverage

### 9. News & Events (新闻与事件)
- **Stock news**: `stock_news_em()` - Individual stock news
- **Announcements**: `stock_announcement()` - Company announcements
- **Market news**: `stock_news_global()` - Market-wide news

### 10. Macro Economy (宏观经济)
- **GDP**: `macro_china_gdp()` - Economic growth
- **CPI**: `macro_china_cpi_yearly()`, `macro_china_cpi_monthly()` - Inflation
- **PMI**: `macro_china_pmi_yearly()`, `macro_china_pmi_business()` - Economic activity
- **Interest rates**: `macro_china_shibor_rate()`, `macro_china_lpr_rate()` - Monetary policy
- **Money supply**: `macro_china_m2()` - M2 data
- **Forex reserves**: `macro_china_fx_reserves()` - Foreign reserves

### 11. Margin Trading (融资融券)
- **Margin details**: `stock_margin_detail_sz()`, `stock_margin_detail_sh()` - Margin buying, short selling

### 12. Futures Data (期货数据)
- **Commodity futures**: `futures_zh_spot()` - Real-time commodity quotes
- **Financial futures**: `futures_main_sina()` - Index futures (CSI300, SSE50, CSI500)

### 13. Bond Data (债券数据)
- **Convertible bonds**: `bond_cov_jsl()` - All convertible bonds with premium ratio
- **Treasury bonds**: `bond_china_yield()` - Yield curve

### 14. Fund Data (基金数据)
- **ETF**: `fund_etf_spot_em()`, `fund_etf_hist_em()` - ETF quotes and history
- **Open-end funds**: `fund_open_fund_info_em()`, `fund_open_fund_daily_em()` - Mutual fund data
- **Fund holdings**: `fund_portfolio_hold()` - Top stock holdings

## Integration with quant-trading-alerts

When integrating akshare into the system:

1. Check existing `data/api/financial_data.py` for current implementation
2. Consider creating a separate `AkShareDataAPI` class to avoid conflicts with Tushare
3. Follow the same data format as existing `FinancialDataAPI` for consistency
4. Use Tushare code format (e.g., '000001.SZ') internally

## Common Patterns

### Data Format Conversion

```python
# AkShare uses simple symbol format: '000001'
# Tushare uses exchange suffix: '000001.SZ'

def akshare_to_tushare_code(symbol: str) -> str:
    """Convert AkShare format to Tushare format"""
    if symbol.startswith('6'):
        return f"{symbol}.SH"
    elif symbol.startswith(('0', '3')):
        return f"{symbol}.SZ"
    return symbol

def tushare_to_akshare_code(ts_code: str) -> str:
    """Convert Tushare format to AkShare format"""
    return ts_code.split('.')[0]
```

### Error Handling

```python
import akshare as ak
import pandas as pd

def safe_akshare_call(func, *args, **kwargs):
    """Wrapper with error handling for akshare calls"""
    try:
        df = func(*args, **kwargs)
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        print(f"AkShare API error: {e}")
        return pd.DataFrame()
```

## Reference Documentation

For detailed API documentation with 100+ functions and examples:

- **[API Reference](references/api_reference.md)** - Complete catalog with:
  - Stock Market Data (K-line, real-time, intraday)
  - Stock Pool Screening (lists, limit-up, ST, IPO)
  - Financial Data (statements, indicators, analysis)
  - Index & Sector Data (indices, constituents, industry/concept boards)
  - Dragon-Tiger List (daily, institutional, brokerage)
  - Fund Flow (individual, sector, market-wide, northbound)
  - Valuation Indicators (PE, PB, market metrics)
  - Shareholder Data (top shareholders, institutional holdings)
  - News & Events (stock news, announcements)
  - Macro Economy (GDP, CPI, PMI, rates, money supply)
  - Futures Data (commodity, financial futures)
  - Bond Data (convertible bonds, treasury yields)
  - Fund Data (ETF, open-end, holdings)

- **[Integration Guide](references/integration_guide.md)** - Integration patterns for quant-trading-alerts

- **[Data Mapping](references/data_mapping.md)** - Field mappings between AkShare and system format

**Quick Navigation by Use Case:**

| Need | Primary Functions | Reference Section |
|------|-------------------|-------------------|
| Stock universe | `stock_zh_a_spot_em()` | Stock Pool Screening |
| Strong stocks | `stock_zt_pool_em()` | Stock Pool Screening |
| K-line data | `stock_zh_a_hist()` | Stock Market Data |
| Financials | `stock_financial_analysis_indicator()` | Financial Data |
| Index data | `stock_zh_index_spot()`, `index_stock_cons()` | Index & Sector Data |
| Sectors | `stock_board_industry_cons_em()` | Index & Sector Data |
| Dragon-tiger | `stock_lhb_em()` | Dragon-Tiger List |
| Fund flow | `stock_individual_fund_flow_rank()` | Fund Flow |
| Valuation | `stock_a_lg_indicator()` | Valuation Indicators |
| Macro | `macro_china_gdp()`, `macro_china_cpi_yearly()` | Macro Economy |

## Official Documentation

https://akshare.akfamily.xyz/
