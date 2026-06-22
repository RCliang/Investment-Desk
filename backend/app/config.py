import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "investlens.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 4096

CACHE_TTL_MARKET = 300       # 行情缓存 5 分钟
CACHE_TTL_FINANCIAL = 86400  # 财务缓存 1 天
CACHE_TTL_CHAIN = 604800     # 产业链缓存 7 天
