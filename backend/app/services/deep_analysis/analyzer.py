"""Single-bucket LLM call with retry and schema completion."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config import MODEL_NAME
from app.services import llm_service
from app.services.deep_analysis.schemas import BucketResult, FieldValue
from app.services.deep_analysis.templates import (
    BUCKET_FIELD_DEFS, BUCKET_TEMPLATES,
)

logger = logging.getLogger(__name__)

# Module-level alias so tests can patch analyzer.llm_client.
# NOTE: deviation from plan — plan line 1228 reads `llm_client = llm_service.client`
# inside run_single_bucket as a local, which would make mocker.patch on
# "app.services.deep_analysis.analyzer.llm_client" ineffective. Promoting it
# to a module-level name preserves the plan's lazy-None-check intent while
# giving the tests a stable patch target.
llm_client = llm_service.client

BUCKET_SYSTEM_PROMPT = """你是研报结构化解析器。必须输出严格 JSON,不要 markdown 代码块。
所有声明的字段必须出现;找不到的字段填 {"value":null,"evidence":"unknown","quote":null}。"""

MAX_TOKENS = 2000
TIMEOUT_SECONDS = 60


class AnalyzerError(Exception):
    """单桶解析失败的统一异常。"""


def parse_bucket_result(bucket_id: str, raw_str: str) -> BucketResult:
    """json.loads → 补缺字段 → 忽略多余字段。非法 JSON 抛 ValueError(触发重试)。"""
    data = json.loads(raw_str)  # 可能抛 JSONDecodeError(是 ValueError 的子类)
    if not isinstance(data, dict):
        raise ValueError(f"top-level not dict: {type(data).__name__}")

    fields_in = data.get("fields", {}) if isinstance(data.get("fields"), dict) else {}
    expected = BUCKET_FIELD_DEFS.get(bucket_id, [])
    fields_out: dict[str, FieldValue] = {}
    for name in expected:
        raw = fields_in.get(name)
        if raw is None:
            fields_out[name] = FieldValue()
        else:
            try:
                fields_out[name] = FieldValue.model_validate(raw)
            except ValidationError:
                fields_out[name] = FieldValue()
    return BucketResult(bucket_id=bucket_id, fields=fields_out)


async def run_single_bucket(bucket_id: str, markdown_text: str) -> BucketResult:
    """调用 LLM,重试 1 次。返回 BucketResult 或抛 AnalyzerError。"""
    template = BUCKET_TEMPLATES[bucket_id]
    user_prompt = template.replace("{markdown}", markdown_text)

    # Reads the module-level alias (which tests may patch).
    if llm_client is None:
        raise AnalyzerError("LLM client not configured (DEEPSEEK_API_KEY missing)")

    last_err: Exception | None = None
    for attempt, temp in [(0, 0.1), (1, 0.0)]:
        try:
            resp = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": BUCKET_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=MAX_TOKENS,
                temperature=temp,
                timeout=TIMEOUT_SECONDS,
            )
            finish_reason = resp.choices[0].finish_reason
            content = resp.choices[0].message.content or ""
            if finish_reason == "length":
                # 视为 JSON 解析失败,触发重试
                raise ValueError(f"finish_reason=length (truncated output)")
            return parse_bucket_result(bucket_id, content)
        except ValueError as e:
            last_err = e
            logger.warning("bucket %s attempt %d failed: %s", bucket_id, attempt, e)
            continue
        except Exception as e:
            raise AnalyzerError(f"LLM call failed: {type(e).__name__}: {e}") from e

    raise AnalyzerError(f"JSON parse failed after retry: {last_err}")
