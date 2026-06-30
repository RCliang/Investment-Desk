# Research API Design Spec

Date: 2026-06-30

## Overview

新增独立的 `/api/research` router，提供两个研报搜索接口：
1. 按股票代码搜索近 1 年研报（东财 reportapi）
2. 按行业关键词深度语义搜索（iwencai）

这是内部 pipeline 接口，不暴露给前端。返回研报元数据 + PDF URL，不负责下载。

## API Endpoints

### GET /api/research/reports

按股票代码搜索研报列表。

**Parameters:**
- `code` (required, str): 6 位股票代码，如 `301095`
- `max_pages` (optional, int, default=2, max=5): 东财分页数，每页 100 条

**Response:**
```json
{
  "code": "301095",
  "total": 39,
  "reports": [
    {
      "title": "EDA/PDA工具体系完善...",
      "publish_date": "2026-06-24",
      "org_name": "中邮证券",
      "rating": "买入",
      "eps_this_year": 0.63,
      "eps_next_year": 0.95,
      "eps_year_after": null,
      "industry": "电子",
      "info_code": "AP202606241823819112",
      "pdf_url": "https://pdf.dfcfw.com/pdf/H3_AP202606241823819112_1.pdf"
    }
  ]
}
```

**Cache:** key=`research:code:{code}:pages{max_pages}`, TTL=7 days

### GET /api/research/search

按关键词语义搜索研报（iwencai NL）。

**Parameters:**
- `keyword` (required, str): 搜索关键词，如 `EDA 硅光 国产替代`
- `size` (optional, int, default=50): 返回条数上限

**Response:**
```json
{
  "keyword": "EDA 硅光 国产替代",
  "total": 12,
  "reports": [
    {
      "title": "广立微（301095）：Effective EDA Platform Construction",
      "publish_date": "2026-05-31",
      "org_name": "华泰证券",
      "stock_codes": ["301095"],
      "source": "iwencai"
    }
  ]
}
```

**Cache:** key=`research:kw:{md5(keyword)}:s{size}`, TTL=7 days

## Architecture

### File Structure

```
backend/app/
├── routers/research.py          # 路由：参数校验、缓存、调用 service
└── services/research_service.py # 服务：东财 reportapi + iwencai 数据源
```

### Service Layer (research_service.py)

独立的东财限流逻辑（不与 astock_service 共享 session）：
- `_em_session`: 独立 requests.Session，Keep-Alive
- `_em_min_interval = 1.0s` + 随机抖动 0.1~0.5s
- 单次 timeout = 30s

两个核心函数：
- `fetch_reports_by_code(code, max_pages) -> list[dict]`
- `search_reports_by_keyword(keyword, size) -> list[dict]`

### Router Layer (research.py)

- 参数校验（Pydantic Query params）
- 缓存读写：复用 `data_cache` 表
- 调用 service，格式化响应

### Caching

复用现有 `data_cache` 表（无需新建表），key 前缀 `research:`：
- `research:code:301095:pages2`
- `research:kw:<md5>:s50`

TTL: 604800 秒（7 天），通过 `config.CACHE_TTL_RESEARCH` 配置。

## Config Changes

`app/config.py` 新增：
```python
IWENCAI_API_KEY = os.getenv("IWENCAI_API_KEY", "")
IWENCAI_BASE_URL = os.getenv("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
CACHE_TTL_RESEARCH = 604800
```

`.env.example` 新增：
```
IWENCAI_API_KEY=
IWENCAI_BASE_URL=https://openapi.iwencai.com
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| 东财超时/返回空 | 200 + `{"total": 0, "reports": [], "error": "upstream_timeout"}` |
| 东财风控 (403/429) | 200 + `{"total": 0, "reports": [], "error": "rate_limited"}` |
| iwencai key 未配置 | 503 + `{"detail": "IWENCAI_API_KEY not configured"}` |
| iwencai 非 200 响应 | 200 + `{"total": 0, "reports": [], "error": "iwencai_error"}` |
| code 非 6 位数字 | 422 (FastAPI validation) |
| keyword 空串 | 422 (FastAPI validation) |

## Registration

`app/main.py` 新增一行：
```python
from app.routers import research
app.include_router(research.router)
```

## Change Summary

1. **New** `app/services/research_service.py`
2. **New** `app/routers/research.py`
3. **Modify** `app/config.py` — 加 iwencai env vars + CACHE_TTL_RESEARCH
4. **Modify** `app/main.py` — 注册 router
5. **Modify** `.env.example` — 加 iwencai 配置模板
