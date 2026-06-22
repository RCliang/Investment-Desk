# AkShare Integration Guide for quant-trading-alerts

Guide for integrating AkShare API into the quant-trading-alerts system.

## Current System Architecture

The existing system uses:
- **Tushare API** as primary data source (`data/api/financial_data.py`)
- **PostgreSQL** for data storage (`data/storage/db_manager.py`)
- **Tushare code format**: `000001.SZ`, `600000.SH` (6 digits + exchange suffix)

## Integration Strategy

### Option 1: Create Separate AkShareDataAPI Class

Create a new class that mirrors the existing `FinancialDataAPI` interface:

```python
# data/api/akshare_data.py

import akshare as ak
import pandas as pd
from typing import List, Optional


class AkShareDataAPI:
    """AkShare API wrapper for Chinese market data"""

    @staticmethod
    def _convert_to_tushare_format(symbol: str) -> str:
        """Convert AkShare format to Tushare format

        Args:
            symbol: AkShare format (e.g., '000001', '600000')

        Returns:
            Tushare format (e.g., '000001.SZ', '600000.SH')
        """
        if symbol.startswith('6'):
            return f"{symbol}.SH"
        elif symbol.startswith(('0', '3')):
            return f"{symbol}.SZ"
        return symbol

    @staticmethod
    def _convert_to_akshare_format(ts_code: str) -> str:
        """Convert Tushare format to AkShare format

        Args:
            ts_code: Tushare format (e.g., '000001.SZ')

        Returns:
            AkShare format (e.g., '000001')
        """
        return ts_code.split('.')[0]

    def get_kline_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Get daily K-line data

        Args:
            symbol: Stock code in Tushare format (e.g., '000001.SZ')
            start_date: Start date YYYYMMDD
            end_date: End date YYYYMMDD

        Returns:
            DataFrame with columns matching existing format
        """
        try:
            ak_symbol = self._convert_to_akshare_format(symbol)

            df = ak.stock_zh_a_hist(
                symbol=ak_symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

            if df.empty:
                return pd.DataFrame()

            # Rename columns to match existing format
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'turnover',
                '振幅': 'amplitude',
                '涨跌幅': 'pct_chg',
                '涨跌额': 'change',
                '换手率': 'turnover_rate'
            })

            # Add symbol column
            df['symbol'] = symbol

            # Convert date format
            df['date'] = pd.to_datetime(df['date'])

            # Select and order columns
            df = df[[
                'symbol', 'date', 'open', 'high', 'low', 'close',
                'volume', 'pct_chg', 'amplitude', 'turnover'
            ]]

            return df.sort_values('date')

        except Exception as e:
            print(f"AkShare获取K线数据失败: {e}")
            return pd.DataFrame()

    def get_stock_list(self) -> pd.DataFrame:
        """Get all A-share stock list

        Returns:
            DataFrame with stock basic info
        """
        try:
            df = ak.stock_zh_a_spot_em()

            if df.empty:
                return pd.DataFrame()

            # Convert to Tushare format
            df['ts_code'] = df['代码'].apply(self._convert_to_tushare_format)
            df['name'] = df['名称']
            df['industry'] = ''  # AkShare doesn't provide industry in spot data

            return df[['ts_code', '代码', 'name', 'industry']]

        except Exception as e:
            print(f"AkShare获取股票列表失败: {e}")
            return pd.DataFrame()

    def get_financial_indicator(self, symbol: str) -> pd.DataFrame:
        """Get financial indicators

        Args:
            symbol: Stock code in Tushare format

        Returns:
            DataFrame with financial indicators
        """
        try:
            ak_symbol = self._convert_to_akshare_format(symbol)

            df = ak.stock_financial_analysis_indicator(symbol=ak_symbol)

            if df.empty:
                return pd.DataFrame()

            df['ts_code'] = symbol

            return df

        except Exception as e:
            print(f"AkShare获取财务指标失败: {e}")
            return pd.DataFrame()

    def get_limit_up_stocks(self, date: str) -> pd.DataFrame:
        """Get limit-up stocks for a specific date

        Args:
            date: Date in YYYYMMDD format

        Returns:
            DataFrame with limit-up stock info
        """
        try:
            df = ak.stock_zt_pool_em(date=date)

            if df.empty:
                return pd.DataFrame()

            # Convert to Tushare format
            df['ts_code'] = df['代码'].apply(self._convert_to_tushare_format)

            return df

        except Exception as e:
            print(f"AkShare获取涨停板数据失败: {e}")
            return pd.DataFrame()

    def get_concept_stocks(self, concept_name: str) -> pd.DataFrame:
        """Get stocks in a concept board

        Args:
            concept_name: Concept board name (e.g., 'ChatGPT')

        Returns:
            DataFrame with stocks in the concept
        """
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept_name)

            if df.empty:
                return pd.DataFrame()

            # Convert to Tushare format
            df['ts_code'] = df['代码'].apply(self._convert_to_tushare_format)

            return df

        except Exception as e:
            print(f"AkShare获取概念板块数据失败: {e}")
            return pd.DataFrame()

    def get_concept_list(self) -> pd.DataFrame:
        """Get all concept boards

        Returns:
            DataFrame with concept board list
        """
        try:
            df = ak.stock_board_concept_name_em()

            if df.empty:
                return pd.DataFrame()

            return df

        except Exception as e:
            print(f"AkShare获取概念板块列表失败: {e}")
            return pd.DataFrame()
```

### Option 2: Extend Existing FinancialDataAPI

Add AkShare as an alternative data source to the existing `FinancialDataAPI` class:

```python
# data/api/financial_data.py

import akshare as ak
# ... existing imports ...

class FinancialDataAPI:
    def __init__(self, use_akshare: bool = False):
        """Initialize API with optional AkShare support

        Args:
            use_akshare: If True, use AkShare instead of Tushare
        """
        self.use_akshare = use_akshare
        if not use_akshare:
            self.ts_pro = get_tushare_pro()

    def get_kline_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get daily K-line data"""
        if self.use_akshare:
            return self._get_kline_daily_akshare(symbol, start_date, end_date)
        else:
            return self._get_kline_daily_tushare(symbol, start_date, end_date)

    def _get_kline_daily_akshare(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get K-line data using AkShare"""
        # Implementation from Option 1
        ...
```

## Database Integration

To save AkShare data to PostgreSQL:

```python
from quant_trading_alerts.data.storage.db_manager import DBManager

# Example usage
api = AkShareDataAPI()
db = DBManager()
db.connect()

# Get K-line data
df = api.get_kline_daily('000001.SZ', '20240101', '20240131')

# Save to database using existing DBManager methods
# Assuming kline_daily table exists and has matching schema
for _, row in df.iterrows():
    db.insert_kline_data(
        symbol=row['symbol'],
        date=row['date'].strftime('%Y%m%d'),
        open=row['open'],
        high=row['high'],
        low=row['low'],
        close=row['close'],
        volume=int(row['volume']),
        pct_chg=row['pct_chg'],
        amplitude=row['amplitude'],
        turnover=row['turnover']
    )

db.disconnect()
```

## Configuration

Update `.env` to include AkShare configuration:

```bash
# Data source selection
DATA_SOURCE=akshare  # Options: tushare, akshare, or both

# AkShare specific settings (if needed in future)
# AKSHARE_RATE_LIMIT=100  # Requests per minute
```

## Use Cases in quant-trading-alerts

### 1. Daily Data Sync

```python
# scripts/sync_akshare_data.py

from quant_trading_alerts.data.api.akshare_data import AkShareDataAPI
from quant_trading_alerts.data.storage.db_manager import DBManager

def sync_daily_data():
    """Sync daily market data using AkShare"""
    api = AkShareDataAPI()
    db = DBManager()
    db.connect()

    # Get stock list
    stocks = api.get_stock_list()

    # Sync K-line data for each stock
    for _, stock in stocks.iterrows():
        symbol = stock['ts_code']
        df = api.get_kline_daily(symbol, '20240101', '20240131')

        # Save to database
        # ... implementation ...

    db.disconnect()
```

### 2. Limit-up Stock Scanner

```python
# scripts/scan_limit_up.py

from quant_trading_alerts.data.api.akshare_data import AkShareDataAPI
from datetime import datetime

def scan_limit_up():
    """Scan for limit-up stocks today"""
    api = AkShareDataAPI()

    today = datetime.now().strftime('%Y%m%d')
    df = api.get_limit_up_stocks(today)

    print(f"Found {len(df)} limit-up stocks")
    print(df[['代码', '名称', '最新价', '涨跌幅', '封单金额']])
```

### 3. Concept Sector Analysis

```python
# scripts/analyze_concept.py

from quant_trading_alerts.data.api.akshare_data import AkShareDataAPI

def analyze_concept(concept_name: str):
    """Analyze a concept sector"""
    api = AkShareDataAPI()

    # Get concept board info
    concept_list = api.get_concept_list()
    concept_info = concept_list[concept_list['板块名称'] == concept_name]

    # Get stocks in concept
    stocks = api.get_concept_stocks(concept_name)

    print(f"Concept: {concept_name}")
    print(f"Change %: {concept_info['涨跌幅'].values[0]}")
    print(f"Stocks: {len(stocks)}")
```

## Testing

Create unit tests for the AkShare integration:

```python
# tests/test_data_api/test_akshare_api.py

import pytest
from quant_trading_alerts.data.api.akshare_data import AkShareDataAPI

@pytest.fixture
def akshare_api():
    return AkShareDataAPI()

def test_convert_to_tushare_format(akshare_api):
    assert akshare_api._convert_to_tushare_format('000001') == '000001.SZ'
    assert akshare_api._convert_to_tushare_format('600000') == '600000.SH'

def test_convert_to_akshare_format(akshare_api):
    assert akshare_api._convert_to_akshare_format('000001.SZ') == '000001'
    assert akshare_api._convert_to_akshare_format('600000.SH') == '600000'

def test_get_kline_daily(akshare_api):
    df = akshare_api.get_kline_daily('000001.SZ', '20240101', '20240110')

    assert not df.empty
    assert 'symbol' in df.columns
    assert 'date' in df.columns
    assert 'close' in df.columns
```

## Best Practices

1. **Error Handling**: Always wrap AkShare calls in try-except blocks
2. **Rate Limiting**: Add delays between batch requests to avoid being blocked
3. **Data Validation**: Check if returned DataFrame is empty before processing
4. **Code Conversion**: Always convert between Tushare and AkShare code formats
5. **Logging**: Log API errors for debugging

## Migration Path

1. **Phase 1**: Create `AkShareDataAPI` class alongside existing `FinancialDataAPI`
2. **Phase 2**: Add unit tests for AkShare integration
3. **Phase 3**: Update configuration to support data source selection
4. **Phase 4**: Gradually migrate specific data fetching to AkShare where beneficial
5. **Phase 5**: Monitor performance and optimize as needed
