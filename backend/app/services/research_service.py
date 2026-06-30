"""
Research service — 研报搜索数据源封装。
两个数据源：
1. 东财 reportapi（按股票代码）
2. iwencai 语义搜索（按关键词）
"""

import json
import logging
import secrets
import time
import random

import requests

from app.config import IWENCAI_API_KEY, IWENCAI_BASE_URL

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
REPORT_API = "https://reportapi.eastmoney.com/report/list"
PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"

# ── 东财限流（独立 session，不与 astock_service 共享）──
_em_session = requests.Session()
_em_session.headers.update({"User-Agent": UA})
_EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def _em_get(url: str, params: dict | None = None, headers: dict | None = None,
            timeout: int = 30):
    """东财专用限流请求入口"""
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return _em_session.get(url, params=params, headers=headers, timeout=timeout)
    finally:
        _em_last_call[0] = time.time()


# ═══════════════════════════════════════════════════════════════════
# 数据源 1：东财 reportapi — 按股票代码搜索
# ═══════════════════════════════════════════════════════════════════

def fetch_reports_by_code(code: str, max_pages: int = 2) -> list[dict]:
    """
    东财 reportapi 按股票代码拉研报列表。
    max_pages 上限 5（每页 100 条）。
    返回标准化的研报元数据列表。
    """
    max_pages = min(max_pages, 5)
    all_records = []

    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        try:
            r = _em_get(REPORT_API, params=params,
                        headers={"Referer": "https://data.eastmoney.com/"})
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            logger.warning("东财 reportapi 请求失败 (page %d): %s", page, e)
            break

        rows = d.get("data") or []
        if not rows:
            break

        for row in rows:
            info_code = row.get("infoCode") or ""
            all_records.append({
                "title": row.get("title") or "",
                "publish_date": (row.get("publishDate") or "")[:10],
                "org_name": row.get("orgSName") or "",
                "rating": row.get("emRatingName") or "",
                "eps_this_year": _safe_float(row.get("predictThisYearEps")),
                "eps_next_year": _safe_float(row.get("predictNextYearEps")),
                "eps_year_after": _safe_float(row.get("predictNextTwoYearEps")),
                "industry": row.get("indvInduName") or "",
                "info_code": info_code,
                "pdf_url": PDF_TPL.format(info_code=info_code) if info_code else "",
            })

        total_pages = d.get("TotalPage") or 1
        if page >= total_pages:
            break

    return all_records


# ═══════════════════════════════════════════════════════════════════
# 数据源 2：iwencai 语义搜索 — 按关键词
# ═══════════════════════════════════════════════════════════════════

def search_reports_by_keyword(keyword: str, size: int = 50) -> list[dict]:
    """
    iwencai NL 语义搜索研报。
    需要 IWENCAI_API_KEY 已配置。
    返回去重后的研报元数据列表。
    """
    if not IWENCAI_API_KEY:
        raise RuntimeError("IWENCAI_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {IWENCAI_API_KEY}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": "normal",
        "X-Claw-Skill-Id": "report-search",
        "X-Claw-Skill-Version": "2.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }
    payload = {
        "channels": ["report"],
        "app_id": "AIME_SKILL",
        "query": keyword,
        "size": size,
    }

    r = requests.post(
        f"{IWENCAI_BASE_URL}/v1/comprehensive/search",
        json=payload, headers=headers, timeout=30,
    )
    if r.status_code != 200:
        logger.warning("iwencai HTTP %d: %s", r.status_code, r.text[:200])
        raise RuntimeError(f"iwencai HTTP {r.status_code}")

    data = r.json()
    if data.get("status_code", 0) != 0:
        msg = data.get("status_msg", "unknown error")
        logger.warning("iwencai error: %s", msg)
        raise RuntimeError(f"iwencai error: {msg}")

    articles = data.get("data") or []
    articles = _dedup_articles(articles)

    results = []
    for a in articles:
        extra = a.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except json.JSONDecodeError:
                extra = {}
        stocks = a.get("stock_infos") or []
        results.append({
            "title": a.get("title") or "",
            "publish_date": (a.get("publish_date") or "")[:10],
            "org_name": extra.get("organization", ""),
            "stock_codes": [s.get("code", "") for s in stocks if s.get("code")],
            "source": "iwencai",
        })

    return results


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _safe_float(val) -> float | None:
    """安全转换为 float，失败返回 None"""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _dedup_articles(articles: list[dict]) -> list[dict]:
    """同一 uid 仅保留 score 最高的段落"""
    best: dict[str, dict] = {}
    for a in articles:
        uid = a.get("uid", "") or f"{a.get('title', '')}|{a.get('publish_date', '')}"
        score = float(a.get("score", 0))
        if uid not in best or score > float(best[uid].get("score", 0)):
            best[uid] = a
    return sorted(best.values(), key=lambda x: x.get("publish_date", ""), reverse=True)
