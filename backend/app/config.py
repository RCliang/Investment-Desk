import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from backend/ directory so local dev doesn't need system env vars.
# Explicit path ensures it's found regardless of CWD (e.g. when uvicorn runs
# from repo root). Production deployments should still use real env vars.
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "data" / "investlens.db"

# DeepSeek API (OpenAI-compatible interface)
# 申请：https://platform.deepseek.com/
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 可选模型：deepseek-chat (V3 通用对话) / deepseek-reasoner (R1 推理增强)
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

LLM_MAX_TOKENS = 4096

CACHE_TTL_MARKET = 300       # 行情缓存 5 分钟
CACHE_TTL_FINANCIAL = 86400  # 财务缓存 1 天
CACHE_TTL_CHAIN = 604800     # 产业链缓存 7 天
CACHE_TTL_RESEARCH = 604800  # 研报缓存 7 天

# iwencai (同花顺 SkillHub) — 研报语义搜索
IWENCAI_API_KEY = os.getenv("IWENCAI_API_KEY", "")
IWENCAI_BASE_URL = os.getenv("IWENCAI_BASE_URL", "https://openapi.iwencai.com")

# 阿里云 OSS — 研报 PDF 存储
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_BUCKET = os.getenv("OSS_BUCKET", "")

# Refresh API token — required for POST /api/chainkb/refresh/* endpoints.
# Generate with: python -c "import secrets; print(secrets.token_hex(16))"
# If left empty, refresh endpoints return 503 (refuse to run unauthenticated).
ADMIN_REFRESH_TOKEN = os.getenv("ADMIN_REFRESH_TOKEN", "")

# CORS allowed origins (comma-separated)
# Example: "http://localhost:5173,http://localhost:3000,http://47.116.178.209:3000"
# If empty, allows all origins (not recommended for production)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")
