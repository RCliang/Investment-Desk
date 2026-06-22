# AkShare API Reference

Complete catalog of akshare API functions for Chinese financial market data.

## Table of Contents

1. [Stock Market Data](#stock-market-data-股票行情) - K-line, real-time quotes, intraday data
2. [Stock Pool Screening](#stock-pool-screening-股票池筛选) - Stock lists, filtering, classification
3. [Financial Data](#financial-data-财务数据) - Statements, indicators, analysis
4. [Index & Sector Data](#index--sector-data-指数与板块数据) - Indices, concept boards, industry sectors
5. [Dragon-Tiger List](#dragon-tiger-list-龙虎榜) - Trading anomalies, institutional activity
6. [Fund Flow](#fund-flow-资金流向) - Money flow, institutional trading
7. [Margin Trading](#margin-trading-融资融券) - Margin buying, short selling
8. [Limit-up Stocks](#limit-up-stocks-涨停板) - Limit-up pool, strength analysis
9. [Valuation Indicators](#valuation-indicators-估值指标) - PE, PB, market sentiment
10. [Shareholder Data](#shareholder-data-股东数据) - Institutional holdings, insider trading
11. [News & Events](#news--events-新闻与事件) - Company news, announcements
12. [Macro Economy](#macro-economy-宏观经济) - GDP, CPI, PMI, economic indicators
13. [Futures Data](#futures-data-期货数据) - Commodity futures, financial futures
14. [Bond Data](#bond-data-债券数据) - Bonds, convertible bonds
15. [Fund Data](#fund-data-基金数据) - ETF, LOF, mutual funds

---

## Stock Market Data (股票行情)

### Historical K-line Data (历史行情)

#### stock_zh_a_hist()
A-share historical K-line data (individual stock)

```python
import akshare as ak

df = ak.stock_zh_a_hist(
    symbol="000001",        # Stock code (AkShare format: 6 digits)
    period="daily",         # daily, weekly, monthly
    start_date="20240101",  # YYYYMMDD
    end_date="20240131",    # YYYYMMDD
    adjust="qfq"           # "" (no adjust), "qfq" (forward), "hfq" (backward)
)

# Returns columns:
# - 日期: Date
# - 开盘: Open
# - 收盘: Close
# - 最高: High
# - 最低: Low
# - 成交量: Volume
# - 成交额: Turnover
# - 振幅: Amplitude
# - 涨跌幅: Change %
# - 涨跌额: Change
# - 换手率: Turnover rate
```

#### stock_zh_a_hist_min_em()
A-share minute K-line data (Eastmoney source)

```python
df = ak.stock_zh_a_hist_min_em(
    symbol="000001",
    period="1",            # 1, 5, 15, 30, 60 minutes
    adjust="qfq",
    start_date="2024-01-01 09:30:00",
    end_date="2024-01-31 15:00:00"
)
```

#### stock_zh_a_spot_em()
A-share real-time quotes (Eastmoney source)

```python
df = ak.stock_zh_a_spot_em()

# Returns columns:
# - 代码: Code
# - 名称: Name
# - 最新价: Latest price
# - 涨跌幅: Change %
# - 涨跌额: Change
# - 成交量: Volume
# - 成交额: Turnover
# - 振幅: Amplitude
# - 最高: High
# - 最低: Low
# - 今开: Open
# - 昨收: Previous close
# - 量比: Volume ratio
# - 换手率: Turnover rate
# - 市盈率-动态: PE (dynamic)
# - 市净率: PB
```

### Index Data (指数数据)

#### stock_zh_index_spot()
Index real-time quotes

```python
df = ak.stock_zh_index_spot()

# Major indices included:
# - 上证指数: sh000001
# - 深证成指: sz399001
# - 创业板指: sz399006
```

#### stock_zh_index_daily()
Index historical daily data

```python
df = ak.stock_zh_index_daily(
    symbol="sh000001",     # Index symbol
    start_date="20240101",
    end_date="20240131"
)
```

## Financial Data (财务数据)

### Financial Statements (财务报表)

#### stock_financial_abstract()
Financial statement abstract (THS data source)

```python
df = ak.stock_financial_abstract(
    symbol="000001"
)

# Returns financial metrics including:
# - ROE
# - Revenue
# - Net profit
# - Debt ratio
# - etc.
```

#### stock_financial_analysis_indicator()
Financial analysis indicators (Eastmoney source)

```python
df = ak.stock_financial_analysis_indicator(
    symbol="000001"
)

# Comprehensive financial indicators including:
# - Profitability
# - Growth
# - Operational efficiency
# - Debt ratios
```

### Balance Sheet/Income Statement/Cash Flow

#### stock_balance_sheet_by_report_em()
Balance sheet by report date

```python
df = ak.stock_balance_sheet_by_report_em(
    symbol="000001"
)
```

#### stock_profit_sheet_by_report_em()
Income statement by report date

```python
df = ak.stock_profit_sheet_by_report_em(
    symbol="000001"
)
```

#### stock_cash_flow_sheet_by_report_em()
Cash flow statement by report date

```python
df = ak.stock_cash_flow_sheet_by_report_em(
    symbol="000001"
)
```

## Macro Economy Data (宏观经济)

### GDP (国内生产总值)

#### macro_china_gdp()
China GDP data

```python
df = ak.macro_china_gdp()

# Returns:
# - 季度: Quarter
# - 国内生产总值-绝对值: GDP absolute value
# - 国内生产总值-同比增长: GDP YoY growth
```

### CPI (居民消费价格指数)

#### macro_china_cpi_yearly()
China CPI yearly data

```python
df = ak.macro_china_cpi_yearly()

# Returns:
# - 月份: Month
# - 全国当月: National CPI
# - 全国同比增长: YoY change
```

### PMI (采购经理指数)

#### macro_china_pmi_yearly()
China PMI yearly data

```python
df = ak.macro_china_pmi_yearly()

# Returns:
# - 月份: Month
# - 制造业-指数: Manufacturing PMI
# - 非制造业-指数: Non-manufacturing PMI
```

## Concept & Sector Data (概念板块)

### Concept Boards (概念板块)

#### stock_board_concept_name_em()
Concept board list (Eastmoney)东方财富的概念板块信息

```python
df = ak.stock_board_concept_name_em()

# Returns all concept boards with:
# 名称	类型	描述
# 排名	int64	-
# 板块名称	object	-
# 板块代码	object	-
# 最新价	float64	-
# 涨跌额	float64	-
# 涨跌幅	float64	注意单位：%
# 总市值	int64	-
# 换手率	float64	注意单位：%
# 上涨家数	int64	-
# 下跌家数	int64	-
# 领涨股票	object	-
# 领涨股票-涨跌幅	float64	注意单位：%
```

#### stock_board_concept_cons_em()
Stocks in specific concept board

```python
df = ak.stock_board_concept_cons_em(
    symbol="ChatGPT"  # Concept board name
)

# Returns all stocks in the concept board
```

### Industry Boards (行业板块)

#### stock_board_industry_name_em()
Industry board list (Eastmoney)

```python
df = ak.stock_board_industry_name_em()

# Returns all industry boards
```

#### stock_board_industry_cons_em()
Stocks in specific industry board

```python
df = ak.stock_board_industry_cons_em(
    symbol="银行"  # Industry name
)
```

## Margin Trading (融资融券)

#### stock_margin_detail_sz()
Shenzhen margin trading details

```python
df = ak.stock_margin_detail_sz(
    symbol="000001",
    start_date="20240101",
    end_date="20240131"
)

# Returns:
# - 交易日期: Trading date
# - 融资余额: Margin balance
# - 融资买入额: Margin buying
# - 融券余额: Short balance
# - 融券卖出量: Short selling
```

#### stock_margin_detail_sh()
Shanghai margin trading details

```python
df = ak.stock_margin_detail_sh(
    symbol="600000",
    start_date="20240101",
    end_date="20240131"
)
```

## Limit-up Stocks (涨停板)

#### stock_zt_pool_em()
Limit-up stock pool (Eastmoney)

```python
df = ak.stock_zt_pool_em(
    date="20240131"  # YYYYMMDD format
)

# Returns:
# - 代码: Code
# - 名称: Name
# - 最新价: Price
# - 涨跌幅: Change %
# - 成交额: Turnover
# - 换手率: Turnover rate
# - 封单金额: Limit-up order amount
```

## Stock Heat/Flow (股票热度/资金流向)

### Stock Popularity Ranking (股票人气排名)

#### stock_hot_rank_em()
**Eastmoney Stock Popularity Ranking (人气榜)** - **Most Important Heat Indicator**

```python
df = ak.stock_hot_rank_em()

# Source: http://guba.eastmoney.com/rank/
# Returns real-time stock popularity ranking from Eastmoney Guba

# Return fields:
# - 代码: Stock code
# - 名称: Stock name
# - 最新价: Latest price
# - 涨跌幅: Change %
# - 总市值: Total market cap
# - 成交额: Trading turnover
# - 换手率: Turnover rate
# - 量比: Volume ratio
# - 人气排名: Popularity ranking
# - 人气值: Popularity score
# - 访问量: Visit count
# - 讨论量: Discussion count

# Use cases:
# 1. Discover stocks with highest market attention
# 2. Combine with fund flow to assess sustainability of hot stocks
# 3. Screen potential strong stocks
# 4. Track social sentiment trends

# Note: Real-time data, updates during market hours (9:30-15:00)
```

### Individual Stock Fund Flow (个股资金流向)

#### stock_individual_fund_flow_rank()
Individual stock fund flow ranking

```python
df = ak.stock_individual_fund_flow_rank(
    symbol="000001",
    indicator="今日"  # 今日, 3日, 5日, 10日
)

# Returns fund flow data including:
# - 净流入: Net inflow
# - 主力: Main force (institutional) flow
# - 超大单: Large orders (>100 lots)
# - 大单: Medium-large orders (50-100 lots)
# - 中单: Medium orders (10-50 lots)
# - 小单: Small orders (<10 lots)

# Use cases: Measure individual stock money flow heat
```

#### stock_individual_fund_flow()
Historical fund flow for a stock

```python
df = ak.stock_individual_fund_flow(
    stock="000001",
    market="sh"  # sh or sz
)

# Daily fund flow history
```

### Sector Fund Flow (板块资金流)

#### stock_fund_flow_concept()
Concept sector fund flow

```python
df = ak.stock_fund_flow_concept(
    symbol="ChatGPT"
)

# Returns fund flow for concept board
```

#### stock_fund_flow_industry()
Industry sector fund flow

```python
df = ak.stock_fund_flow_industry(
    symbol="银行"
)

# Returns fund flow for industry sector
```

## Stock Pool Screening (股票池筛选)

### Stock List (股票列表)

#### stock_zh_a_spot_em()
Get all A-share stocks with real-time quotes (most comprehensive)

```python
df = ak.stock_zh_a_spot_em()

# Returns ALL A-share stocks with comprehensive fields:
# - 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额
# - 振幅, 最高, 最低, 今开, 昨收, 量比, 换手率
# - 市盈率-动态, 市净率, 总市值, 流通市值
# Use for: Building stock universes, filtering stocks
```

#### stock_info_a_code_name()
Get A-share stock code and name list

```python
df = ak.stock_info_a_code_name()

# Simple list: code, name
# Use for: Quick stock reference, building code lists
```

#### stock_info_sz_name_code()
Shenzhen stock list

```python
df = ak.stock_info_sz_name_code(sector="主板")  # 主板, 创业板
```

#### stock_sh_a_spot_em()
Shanghai A-share real-time quotes

```python
df = ak.stock_sh_a_spot_em()
```

### Stock Classification (股票分类)

#### stock_zh_a_broadcasts()
Get stock classifications by industry, concept, area

```python
# Industry classification
df = ak.stock_board_industry_name_em()

# Concept classification
df = ak.stock_board_concept_name_em()

# Area classification
df = ak.stock_board_area_name_em()
```

### Strong/Weak Stocks (强势股/弱势股)

#### stock_zt_pool_em()
Limit-up stock pool (strong stocks)

```python
df = ak.stock_zt_pool_em(date="20240131")

# Fields: 代码, 名称, 最新价, 涨跌幅, 成交额, 换手率, 封单金额
# Use for: Finding strong momentum stocks
```

#### stock_dt_pool_em()
Limit-down stock pool (weak stocks)

```python
df = ak.stock_dt_pool_em(date="20240131")
```

#### stock_zt_pool_strong_em()
Strong limit-up stocks with high seal amount

```python
df = ak.stock_zt_pool_strong_em(date="20240131")
```

### New Stocks (新股)

#### stock_new_sh()
Shanghai new stocks

```python
df = ak.stock_new_sh()
```

#### stock_new_sz()
Shenzhen new stocks

```python
df = ak.stock_new_sz()
```

#### stock_ipo_list()
IPO list

```python
df = ak.stock_ipo_list()
```

### ST & Special Treatment Stocks (特别处理股票)

#### stock_zh_a_st_em()
ST stocks list

```python
df = ak.stock_zh_a_st_em()

# Use for: Filtering out high-risk stocks
```

### Suspended/Resumed Stocks (停复牌)

#### stock_paused_list()
Suspended stocks list

```python
df = ak.stock_paused_list()
```

---

## Index & Sector Data (指数与板块数据)

### Index Data (指数数据)

#### stock_zh_index_spot()
All real-time index quotes

```python
df = ak.stock_zh_index_spot()

# Major indices:
# - 上证指数: sh000001
# - 深证成指: sz399001
# - 创业板指: sz399006
# - 科创50: sh000688
# - 沪深300: sh000300
# - 中证500: sh000905
# - 中证1000: sh000852
```

#### stock_zh_index_daily()
Index historical daily data

```python
df = ak.stock_zh_index_daily(
    symbol="sh000001",
    start_date="20240101",
    end_date="20240131"
)
```

#### stock_index_pe()
Index PE ratio

```python
df = ak.stock_index_pe(symbol="sh000001")

# Returns PE, PB, PS, dividend yield for index
```

### Index Constituents (指数成份股)

#### index_stock_cons()
Index constituent stocks

```python
df = ak.index_stock_cons(
    symbol="000300",  # CSI 300
    date="20240131"
)

# Use for: Getting stock list from index
```

#### index_cons_weight_bb()
Index constituent weights (from Eastmoney)

```python
df = ak.index_cons_weight_bb(
    symbol="000300"
)
```

### Sector Data (板块数据)

#### stock_board_industry_name_em()
Industry sector list (Eastmoney)

```python
df = ak.stock_board_industry_name_em()

# Returns: 板块名称, 最新价, 涨跌幅, 总市值, 成交量, 换手率
# Industries include: 银行, 证券, 医药, 电子, etc.
```

#### stock_board_industry_cons_em()
Industry sector constituent stocks

```python
df = ak.stock_board_industry_cons_em(
    symbol="银行",  # Industry name
    field="价值指标"  # Optional: 价值指标, 涨跌幅
)
```

#### stock_board_concept_name_em()
Concept sector list (Eastmoney)

```python
df = ak.stock_board_concept_name_em()

# Hot concepts: ChatGPT, 机器人, 新能源, etc.
```

#### stock_board_concept_cons_em()
Concept sector constituent stocks

```python
df = ak.stock_board_concept_cons_em(
    symbol="ChatGPT"
)
```

### Sector Performance (板块表现)

#### stock_board_industry_spot_em()
Industry sectors real-time quotes

```python
df = ak.stock_board_industry_spot_em()
```

---

## Dragon-Tiger List (龙虎榜)

### Daily Dragon-Tiger List (每日龙虎榜)

#### stock_lhb_detail_daily()
Daily dragon-tiger list details

```python
df = ak.stock_lhb_detail_daily(
    start_date="20240101",
    end_date="20240131"
)

# Shows stocks with unusual trading activity, institutional buys/sells
# Fields: 代码, 名称, 交易日期, 营业部名称, 买入金额, 卖出金额
```

#### stock_lhb_em()
Dragon-tiger list (Eastmoney)

```python
df = ak.stock_lhb_em(date="20240131")

# Comprehensive dragon-tiger list data
```

### Institutional Trading (机构交易)

#### stock_lhb_jgzj_detail()
Institutional trading details

```python
df = ak.stock_lhb_jgzj_detail(
    start_date="20240101",
    end_date="20240131"
)

# Shows institutional buying/selling on dragon-tiger list
```

### Brokerage Performance (营业部表现)

#### stock_lhb_yyb_detail()
Brokerage department performance

```python
df = ak.stock_lhb_yyb_detail(
    start_date="20240101",
    end_date="20240131"
)

# Track top-performing brokerage departments
```

---

## Fund Flow (资金流向)

### Individual Stock Fund Flow (个股资金流)

#### stock_individual_fund_flow_rank()
Individual stock fund flow ranking

```python
df = ak.stock_individual_fund_flow_rank(
    symbol="000001",
    indicator="今日"  # 今日, 3日, 5日, 10日
)

# Fields: 净流入, 主力, 超大单, 大单, 中单, 小单
```

#### stock_individual_fund_flow()
Historical fund flow for a stock

```python
df = ak.stock_individual_fund_flow(
    stock="000001",
    market="sh"  # sh or sz
)

# Daily fund flow history
```

### Sector Fund Flow (板块资金流)

#### stock_fund_flow_concept()
Concept sector fund flow

```python
df = ak.stock_fund_flow_concept(
    symbol="ChatGPT",
    data_type="主力"  # 主力, 超大单, 大单, 中单, 小单
)
```

#### stock_fund_flow_industry()
Industry sector fund flow

```python
df = ak.stock_fund_flow_industry(
    symbol="银行"
)
```

### Market-wide Fund Flow (市场资金流)

#### stock_fund_flow_statistics()
Market fund flow statistics

```python
df = ak.stock_fund_flow_statistics(
    date="20240131"
)

# Overall market fund flow distribution
```

#### stock_hsgt_fund_flow_summary()
Stock connect fund flow summary

```python
df = ak.stock_hsgt_fund_flow_summary(
    indicator="沪股通"  # 沪股通, 深股通
)

# Northbound capital flow
```

---

## Valuation Indicators (估值指标)

### Market Valuation (市场估值)

#### stock_a_lg_indicator()
A-share valuation indicators

```python
df = ak.stock_a_lg_indicator(date="20240131")

# Market-wide PE, PB, PS, dividend yield
# Use for: Market timing, assessing market valuation level
```

#### stock_zh_a_pb()
A-share PB ratio

```python
df = ak.stock_zh_a_pb()
```

#### stock_zh_a_pe()
A-share PE ratio

```python
df = ak.stock_zh_a_pe()
```

### Individual Stock Valuation (个股估值)

#### stock_individual_info_em()
Individual stock detailed info (includes valuation)

```python
df = ak.stock_individual_info_em(
    symbol="000001",
    indicator="市盈率"
)

# PE, PB, PS, market cap indicators
```

---

## Shareholder Data (股东数据)

### Top Shareholders (主要股东)

#### stock_zh_a_gdhs()
Top 10 shareholders

```python
df = ak.stock_zh_a_gdhs(
    symbol="000001",
    quarter="20231231"
)

# Fields: 股东名称, 持股数量, 持股比例, 股东性质
```

#### stock_zh_a_gdjc()
Top 10 circulating shareholders

```python
df = ak.stock_zh_a_gdjc(
    symbol="000001",
    quarter="20231231"
)
```

### Shareholder Changes (股东变动)

#### stock_zh_a_shareholder_change()
Shareholder changes

```python
df = ak.stock_zh_a_shareholder_change(
    symbol="000001",
    quarter="20231231"
)

# Shareholder increase/decrease data
```

### Institutional Holdings (机构持股)

#### stock_fund_hold_composition()
Fund holdings composition

```python
df = ak.stock_fund_hold_composition(
    symbol="000001",
    quarter="20231231"
)

# Funds holding this stock
```

#### stock_institutional_follow()
Institutional research/coverage

```python
df = ak.stock_institutional_follow(
    symbol="000001"
)

# Institutions following this stock
```

---

## News & Events (新闻与事件)

### Stock News (个股新闻)

#### stock_news_em()
Stock news from Eastmoney

```python
df = ak.stock_news_em(
    symbol="000001"
)

# Recent news headlines and links
```

#### stock_information_global_ctrl()
Stock information and announcements

```python
df = ak.stock_information_global_ctrl(
    symbol="000001",
    indicator="公告"
)
```

### Market News (市场新闻)

#### stock_news_global()
Global stock market news

```python
df = ak.stock_news_global(
    symbol="A股"
)
```

### Company Announcements (公司公告)

#### stock_announcement()
Stock announcements

```python
df = ak.stock_announcement(
    symbol="000001",
    ann_type="重大事项"  # 公告类型
)
```

---

## Technical Indicators (技术指标计算)

### Indicator Calculation

```python
import akshare as ak

# AkShare provides indicator calculation functions
# Common technical indicators are often calculated from K-line data

# Example: Calculate MA (Moving Average)
def calculate_ma(df, period=5):
    """Calculate moving average"""
    return df['收盘'].rolling(window=period).mean()

# Example: Calculate MACD
def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD"""
    exp1 = df['收盘'].ewm(span=fast, adjust=False).mean()
    exp2 = df['收盘'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

# Example: Calculate RSI
def calculate_rsi(df, period=14):
    """Calculate RSI"""
    delta = df['收盘'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

---

## Macro Economy (宏观经济)

### GDP (国内生产总值)

#### macro_china_gdp()
China GDP data

```python
df = ak.macro_china_gdp()

# Fields: 季度, 国内生产总值-绝对值, 国内生产总值-同比增长
# Use for: Economic growth analysis, business cycle identification
```

### CPI (居民消费价格指数)

#### macro_china_cpi_yearly()
China CPI yearly data

```python
df = ak.macro_china_cpi_yearly()

# Fields: 月份, 全国当月, 全国同比增长, 全国环比增长
# Use for: Inflation analysis, monetary policy impact
```

#### macro_china_cpi_monthly()
China CPI monthly data

```python
df = ak.macro_china_cpi_monthly()
```

### PMI (采购经理指数)

#### macro_china_pmi_yearly()
China PMI yearly data

```python
df = ak.macro_china_pmi_yearly()

# Fields: 月份, 制造业-指数, 非制造业-指数
# Use for: Economic activity gauge, manufacturing health
```

#### macro_china_pmi_business()
Business PMI (Caixin)

```python
df = ak.macro_china_pmi_business()

# Caixin PMI (private sector survey)
```

### Interest Rates (利率)

#### macro_china_shibor_rate()
Shibor rate

```python
df = ak.macro_china_shibor_rate()

# Interbank offered rate
```

#### macro_china_lpr_rate()
LPR (Loan Prime Rate)

```python
df = ak.macro_china_lpr_rate()

# Benchmark lending rate
```

### Money Supply (货币供应量)

#### macro_china_m2()
M2 money supply

```python
df = ak.macro_china_m2()

# Broad money supply
```

### Foreign Exchange (外汇储备)

#### macro_china_fx_reserves()
Foreign exchange reserves

```python
df = ak.macro_china_fx_reserves()

# China's foreign reserves
```

---

## Futures Data (期货数据)

### Commodity Futures (商品期货)

#### futures_sina_sina_spot()
Futures real-time quotes (Sina)

```python
df = ak.futures_sina_sina_spot()

# Major commodity futures quotes
```

#### futures_zh_spot()
Futures real-time quotes (Eastmoney)

```python
df = ak.futures_zh_spot()
```

### Financial Futures (金融期货)

#### futures_main_sina()
Index futures (CSI 300, SSE 50, etc.)

```python
df = ak.futures_main_sina(
    symbol="IF0",  # IF: CSI300, IH: SSE50, IC: CSI500
    start_date="20240101",
    end_date="20240131"
)

# Stock index futures data
```

---

## Bond Data (债券数据)

### Convertible Bonds (可转债)

#### bond_cov_jsl()
Convertible bonds from Jisilu

```python
df = ak.bond_cov_jsl()

# All convertible bonds with premium ratio, conversion price
```

#### bond_cov_comparison()
Convertible bond comparison

```python
df = ak.bond_cov_comparison(
    symbol="113050"  # Convertible bond code
)
```

### Treasury Bonds (国债)

#### bond_china_yield()
Treasury bond yield curve

```python
df = ak.bond_china_yield()

# Treasury yields across maturities
```

---

## Fund Data (基金数据)

### ETF Funds

#### fund_etf_spot_em()
ETF real-time quotes (Eastmoney)

```python
df = ak.fund_etf_spot_em()

# All ETF funds with real-time quotes
```

#### fund_etf_hist_em()
ETF historical data

```python
df = ak.fund_etf_hist_em(
    symbol="510300",  # ETF code
    period="daily",
    start_date="20240101",
    end_date="20240131"
)
```

### Open-end Funds (开放式基金)

#### fund_open_fund_info_em()
Open-end fund information

```python
df = ak.fund_open_fund_info_em(
    fund="000001",
    indicator="单位净值走势"
)
```

#### fund_open_fund_daily_em()
Open-end fund daily data

```python
df = ak.fund_open_fund_daily_em(
    symbol="000001",
    start_date="20240101",
    end_date="20240131"
)
```

### Fund Holdings (基金持仓)

#### fund_portfolio_hold()
Fund stock holdings

```python
df = ak.fund_portfolio_hold(
    fund="000001",
    quarter="20231231"
)

# Top stock holdings
```

---

## Notes

### Symbol Format

- **AkShare**: Simple 6-digit format: `000001`, `600000`
- **Tushare**: 6 digits + exchange suffix: `000001.SZ`, `600000.SH`
- **Conversion**:
  ```python
  def akshare_to_tushare(symbol):
      if symbol.startswith('6'):
          return f"{symbol}.SH"
      elif symbol.startswith(('0', '3')):
          return f"{symbol}.SZ"
      return symbol
  ```

### Date Format

- **Most functions**: `YYYYMMDD` format: `20240101`
- **Some functions**: `YYYY-MM-DD` format: `2024-01-01`
- **Quarterly data**: `YYYYMMDD` for quarter end: `20240331`

### Rate Limits & Best Practices

1. **Rate Limits**:
   - Eastmoney sources (`_em` suffix) may have rate limits
   - Add 0.5-1 second delays between requests for batch operations

2. **Caching**:
   - Real-time data updates during market hours
   - Historical data may be cached by AkShare

3. **Error Handling**:
   ```python
   def safe_akshare_call(func, *args, **kwargs):
       try:
           df = func(*args, **kwargs)
           return df if not df.empty else pd.DataFrame()
       except Exception as e:
           print(f"AkShare error: {e}")
           return pd.DataFrame()
   ```

4. **Batch Processing**:
   ```python
   import time
   for symbol in symbols:
       df = safe_akshare_call(ak.stock_zh_a_hist, symbol=symbol)
       time.sleep(0.5)  # Rate limiting
   ```

### Data Source Suffixes

- `_em`: Eastmoney (东财) - Comprehensive, most reliable
- `_sina`: Sina Finance (新浪)
- `_th`: Tonghuashun (同花顺)
- No suffix: Aggregated or official source

### Priority for quant-trading-alerts System

**Essential (Priority 1)**:
- Stock screening: `stock_zh_a_spot_em()`, `stock_zt_pool_em()`
- K-line data: `stock_zh_a_hist()`, `stock_zh_a_hist_min_em()`
- Financial data: `stock_financial_analysis_indicator()`
- Index data: `stock_zh_index_spot()`, `index_stock_cons()`
- Dragon-tiger list: `stock_lhb_em()`
- Fund flow: `stock_individual_fund_flow_rank()`

**Useful (Priority 2)**:
- Valuation: `stock_a_lg_indicator()`, `stock_index_pe()`
- Macro: `macro_china_gdp()`, `macro_china_cpi_yearly()`, `macro_china_pmi_yearly()`
- Sectors: `stock_board_industry_cons_em()`, `stock_board_concept_cons_em()`

## Official Documentation

Complete API documentation: https://akshare.akfamily.xyz/data/index.html
