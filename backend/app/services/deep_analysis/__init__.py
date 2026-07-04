"""Deep analysis structured extraction subpackage.

Public API:
- orchestrate: SSE async generator(替代老 analyze_stream)
- load_history: 历史列表(支持 v1/v2 混合)
- load_cached: 命中 v2 缓存
"""
from app.services.deep_analysis.runner import orchestrate, build_analysis_doc
from app.services.deep_analysis.storage import (
    load_markdown, load_cached, load_history, save_structured, make_cache_key,
)
from app.services.deep_analysis.analyzer import run_single_bucket, AnalyzerError
from app.services.deep_analysis.schemas import (
    FieldValue, BucketResult, AnalysisDoc,
)
from app.services.deep_analysis.templates import (
    BUCKET_TEMPLATES, ROUTING_TABLE, BUCKET_FIELD_DEFS,
    BUCKET_DISPLAY_NAMES, COMPANY_TYPES, COMPANY_TYPE_LABELS,
)

__all__ = [
    "orchestrate", "build_analysis_doc",
    "load_markdown", "load_cached", "load_history", "save_structured", "make_cache_key",
    "run_single_bucket", "AnalyzerError",
    "FieldValue", "BucketResult", "AnalysisDoc",
    "BUCKET_TEMPLATES", "ROUTING_TABLE", "BUCKET_FIELD_DEFS",
    "BUCKET_DISPLAY_NAMES", "COMPANY_TYPES", "COMPANY_TYPE_LABELS",
]
