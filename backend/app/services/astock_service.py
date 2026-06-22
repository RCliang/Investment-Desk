import httpx
import time
import random
from typing import Optional

AK_TOOL_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _em_get(url: str, params: dict = None) -> dict:
    time.sleep(1 + random.random())
    with httpx.Client(timeout=10) as client:
        r = client.get(url, params=params, headers=AK_TOOL_HEADERS)
        r.raise_for_status()
        return r.json()


class AStockService:

    def get_stock_quote_tx(self, code: str) -> Optional[dict]:
        market_prefix = "sh" if code.startswith("6") else "sz"
        url = f"http://qt.gtimg.cn/q={market_prefix}{code}"
        with httpx.Client(timeout=5) as client:
            r = client.get(url, headers=AK_TOOL_HEADERS)
            if not r.text.startswith("v_"):
                return None
            parts = r.text.split("~")
            if len(parts) < 50:
                return None
            return {
                "code": code,
                "name": parts[1],
                "price": float(parts[3]),
                "last_close": float(parts[4]),
                "change_pct": float(parts[32]) if parts[32] else 0,
                "pe": float(parts[39]) if parts[39] else 0,
                "pb": float(parts[46]) if parts[46] else 0,
                "total_mv": float(parts[44]) if parts[44] else 0,
            }

    def get_stock_concept_blocks(self, code: str) -> list:
        market = "0" if code.startswith("6") else "1"
        secid = f"{market}.{code}"
        url = "https://push2.eastmoney.com/api/qt/slist/get"
        params = {"spt": 3, "fltt": 2, "invt": 2, "secid": secid, "fields": "f12,f14,f3,f62"}
        data = _em_get(url, params)
        return data.get("data", {}).get("diff", []) if data.get("data") else []

    def get_research_reports(self, code: str, page: int = 1, size: int = 10) -> list:
        url = "https://reportapi.eastmoney.com/report/list"
        params = {"industryCode": "*", "pageSize": size, "industry": "", "rating": "", "ratingChange": "", "companyType": "", "reportType": "0", "pageNum": page, "qType": "1", "beginTime": "", "endTime": "", "code": code}
        data = _em_get(url, params)
        return data.get("data", []) if data else []

    def get_fund_flow_minute(self, code: str) -> list:
        market = "1" if code.startswith("0") else "0"
        secid = f"{market}.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {"secid": secid, "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65", "lmt": 0, "klt": 101, "secid2": ""}
        data = _em_get(url, params)
        klines = data.get("data", {}).get("klines", [])
        return [{"time": line.split(",")[0], "main_net_inflow": float(line.split(",")[1]) if len(line.split(",")) > 1 else 0} for line in klines]


astock_service = AStockService()
