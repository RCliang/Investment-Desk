import tushare as ts
from app.config import TUSHARE_TOKEN
from datetime import datetime


class TushareService:

    def __init__(self, token: str = None):
        token = token or TUSHARE_TOKEN
        self.pro = ts.pro_api(token) if token else None
        if self.pro:
            self.pro._DataApi__token = token
            self.pro._DataApi__http_url = 'http://lianghua.nanyangqiankun.top'

    def get_daily(self, ts_code: str, start_date: str = "", end_date: str = "") -> list[dict]:
        if not self.pro:
            return []
        df = self.pro.daily(ts_code=ts_code, start_date=start_date or "20260101", end_date=end_date or datetime.now().strftime("%Y%m%d"))
        return df.to_dict(orient="records") if not df.empty else []

    def get_daily_basic(self, ts_code: str, trade_date: str = "") -> list[dict]:
        if not self.pro:
            return []
        df = self.pro.daily_basic(ts_code=ts_code, trade_date=trade_date or datetime.now().strftime("%Y%m%d"), fields="ts_code,trade_date,close,turnover_rate,pe,pb,ps,total_mv,circ_mv")
        return df.to_dict(orient="records") if not df.empty else []

    def get_financial_indicator(self, ts_code: str) -> list[dict]:
        if not self.pro:
            return []
        df = self.pro.fina_indicator(ts_code=ts_code, fields="ts_code,end_date,roe,roa,netprofit_margin,grossprofit_margin")
        return df.to_dict(orient="records") if not df.empty else []

    def get_stock_basic(self) -> list[dict]:
        if not self.pro:
            return []
        df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date")
        return df.to_dict(orient="records") if not df.empty else []


tushare_service = TushareService()
