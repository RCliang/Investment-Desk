"""
MinerU service smoke test.

- MINERU_API_KEY 未配置时：跑 mock 模式（无需外部依赖）
- MINERU_API_KEY 已配置时：跳过（真实 API 调用在 Task 5.1 端到端测试中验证）
"""

import time

import pytest

from app.config import MINERU_API_KEY
from app.services import mineru_service as m


def test_estimate_tokens_empty():
    assert m.estimate_tokens("") == 0


def test_estimate_tokens_english():
    # 8 个英文字符 -> 8/4 = 2 tokens
    assert m.estimate_tokens("abcdefgh") == 2


def test_estimate_tokens_chinese():
    # 6 个中文字符 -> 6/1.5 = 4 tokens
    assert m.estimate_tokens("一二三四五六") == 4


def test_estimate_tokens_mixed():
    # 3 中文 (3/1.5=2) + 4 英文 (4/4=1) = 3
    assert m.estimate_tokens("一二三abcd") == 3


def test_is_configured_reflects_env():
    assert m.is_configured() == bool(MINERU_API_KEY)


@pytest.mark.skipif(bool(MINERU_API_KEY), reason="真实模式下 mock 测试无意义")
def test_mock_submit_and_poll_lifecycle():
    """Mock 模式：提交 → 立即 poll 返回 None → 延迟后 poll 返回结果 → 再 poll 报 unknown"""
    tid = m.submit_parse(
        "https://example.com/sample.pdf",
        meta={"oss_key": "reports/TEST001/sample.pdf", "title": "测试报告"},
    )
    assert tid.startswith("mock_")

    # 立即 poll，仍在处理
    assert m.poll_result(tid) is None

    # 等待 mock 延迟（3 秒）
    time.sleep(3.2)
    result = m.poll_result(tid)
    assert result is not None
    assert "markdown" in result
    assert result["token_count"] > 0
    assert "测试报告" in result["markdown"]

    # 任务应已从 pending 清理
    assert tid not in m.list_pending()

    # 再 poll 同一 task_id：unknown_task
    with pytest.raises(RuntimeError, match="unknown_task"):
        m.poll_result(tid)


@pytest.mark.skipif(bool(MINERU_API_KEY), reason="真实模式下 mock 测试无意义")
def test_mock_get_task_meta_and_list_pending():
    """get_task_meta / list_pending 在 mock 模式下应正确反映状态"""
    assert m.list_pending() == []
    assert m.get_task_meta("nonexistent") is None

    tid = m.submit_parse("https://example.com/x.pdf", meta={"oss_key": "k1"})
    assert tid in m.list_pending()
    meta = m.get_task_meta(tid)
    assert meta is not None
    assert meta["oss_key"] == "k1"
    assert meta["mock"] is True
