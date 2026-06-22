import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


class AkShareService:

    def get_stock_hist(self, code: str, period: str = "daily",
                       start_date: str = "", end_date: str = "") -> list[dict]:
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period=period, start_date=start_date, end_date=end_date)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_stock_realtime(self) -> list[dict]:
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_stock_financial(self, code: str) -> list[dict]:
        df = ak.stock_financial_abstract(symbol=code)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_industry_stocks(self, industry: str) -> list[dict]:
        df = ak.stock_board_industry_cons_em(symbol=industry)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_fund_flow(self, code: str) -> list[dict]:
        market = "sh" if code.startswith("6") else "sz"
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")


akshare_service = AkShareService()
