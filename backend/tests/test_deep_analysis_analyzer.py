"""analyzer.py: 单桶 LLM 调用 + 重试 + schema 补全。"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.deep_analysis.analyzer import (
    AnalyzerError, parse_bucket_result, run_single_bucket,
)
from app.services.deep_analysis.schemas import BucketResult


def _mock_resp(content: str, finish_reason: str = "stop"):
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = content
    m.choices[0].finish_reason = finish_reason
    return m


# ── parse_bucket_result ─────────────────────────────────────────────

def test_parse_happy_path():
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {
            "domestic_share": {"value": "15%", "evidence": "medium", "quote": "..."},
        },
    })
    br = parse_bucket_result("industry_chain", raw)
    assert isinstance(br, BucketResult)
    assert br.fields["domestic_share"].value == "15%"


def test_parse_missing_field_auto_filled():
    """模板声明的字段缺失,自动补 unknown,不抛错。"""
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "15%"}},
    })
    br = parse_bucket_result("industry_chain", raw)
    # industry_chain 在 BUCKET_FIELD_DEFS 声明 5 个字段
    assert len(br.fields) == 5
    assert br.fields["competitors"].evidence == "unknown"
    assert br.fields["competitors"].value is None


def test_parse_extra_field_ignored():
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {
            "domestic_share": {"value": "x"},
            "unknown_field": {"value": "y"},
        },
    })
    br = parse_bucket_result("industry_chain", raw)
    assert "unknown_field" not in br.fields


def test_parse_invalid_json_raises_value_error():
    with pytest.raises(ValueError):
        parse_bucket_result("industry_chain", "not a json")


# ── run_single_bucket ───────────────────────────────────────────────

def test_happy_path_single_call(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_resp(json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "15%", "evidence": "medium"}},
    }))
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...markdown..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 1


def test_retry_on_invalid_json_then_success(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp("not a json"),
        _mock_resp(json.dumps({
            "bucket_id": "industry_chain",
            "fields": {"domestic_share": {"value": "15%"}},
        })),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 2


def test_give_up_after_two_bad_jsons(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp("bad1"),
        _mock_resp("bad2"),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    with pytest.raises(AnalyzerError, match="JSON parse failed after retry"):
        asyncio.run(run_single_bucket("industry_chain", "...md..."))


def test_missing_field_does_not_retry(mocker):
    """缺字段 → 直接补 unknown,不重试。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_resp(json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "x"}},  # 只给 1 个,缺 4 个
    }))
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert len(result.fields) == 5  # 5 个字段都被填充
    assert mock_client.chat.completions.create.call_count == 1


def test_finish_reason_length_triggers_retry(mocker):
    """LLM 输出截断(finish_reason=length)视为 JSON 失败,触发重试。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp('{"bucket_id":"industry_chain","fields":', finish_reason="length"),
        _mock_resp(json.dumps({
            "bucket_id": "industry_chain",
            "fields": {"domestic_share": {"value": "15%"}},
        })),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 2


def test_llm_call_exception_raises_analyzer_error(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("network timeout")
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    with pytest.raises(AnalyzerError, match="LLM call failed"):
        asyncio.run(run_single_bucket("industry_chain", "...md..."))
