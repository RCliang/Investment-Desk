"""
MinerU cloud API client — PDF 转 Markdown。

依赖配置：
- MINERU_API_URL：服务地址（默认 https://mineru.dottore.com/api/v1）
- MINERU_API_KEY：API key，未配置时启用 mock 模式

接口约定（基于 spec 假设；实际端点需根据所用 MinerU 服务调整）：
- POST {API_URL}/parse         提交解析任务
    body: {"url": "<pdf_url>"}
    resp: {"code":0, "data": {"task_id":"..."}}
- GET  {API_URL}/parse/{task_id}  轮询任务状态
    resp: {"code":0, "data": {"status":"processing|done|failed", "markdown":"...", "error":"..."}}
"""

from __future__ import annotations

import logging
import time

import requests

from app.config import MINERU_API_URL, MINERU_API_KEY

logger = logging.getLogger(__name__)

# 进程内任务表（MVP）：task_id -> {oss_key, stock_code, title, submitted_at}
# 多 worker 部署需换成 DB 表，见 plan Phase 5 「不在本计划范围内的事项」
_pending_tasks: dict[str, dict] = {}


def is_configured() -> bool:
    """是否配置了真实的 MinerU API key。"""
    return bool(MINERU_API_KEY)


def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。
    中文按 1.5 字符/token，英文/数字按 4 字符/token（OpenAI 经验值）。
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 4)


def submit_parse(pdf_url: str, meta: dict | None = None) -> str:
    """
    提交 PDF 给 MinerU 解析。

    Args:
        pdf_url: PDF 的可访问 URL（OSS signed URL 或公网 URL）
        meta: 附加元数据 {"oss_key", "stock_code", "title"}，存入进程表

    Returns:
        task_id（mock 模式下返回 fake id）

    Raises:
        RuntimeError: API 调用失败
    """
    meta = meta or {}

    if not is_configured():
        # Mock 模式：返回 fake task_id，poll 时返回简短 markdown
        task_id = f"mock_{int(time.time() * 1000)}_{len(_pending_tasks)}"
        _pending_tasks[task_id] = {
            **meta,
            "submitted_at": time.time(),
            "mock": True,
        }
        logger.info("[mineru:mock] submit task=%s url=%s", task_id, pdf_url)
        return task_id

    payload = {"url": pdf_url}
    headers = {"Authorization": f"Bearer {MINERU_API_KEY}"}

    try:
        r = requests.post(
            f"{MINERU_API_URL}/parse", json=payload, headers=headers, timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("MinerU submit failed (network): %s", e)
        raise RuntimeError(f"mineru_submit_network_error: {e}")

    if r.status_code != 200:
        logger.warning("MinerU submit HTTP %d: %s", r.status_code, r.text[:200])
        raise RuntimeError(f"mineru_submit_http_{r.status_code}")

    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("mineru_submit_invalid_json")

    # 兼容 {"code":0} 或 {"status":"ok"} 两种风格
    if data.get("code", 0) != 0 and not data.get("data"):
        raise RuntimeError(f"mineru_submit_error: {data.get('msg') or data}")

    task_id = (data.get("data") or {}).get("task_id")
    if not task_id:
        raise RuntimeError("mineru_submit_no_task_id")

    _pending_tasks[task_id] = {
        **meta,
        "submitted_at": time.time(),
        "mock": False,
    }
    logger.info("[mineru] submit task=%s url=%s", task_id, pdf_url)
    return task_id


def poll_result(task_id: str) -> dict | None:
    """
    轮询单个任务的解析结果。

    Returns:
        - 完成: {"markdown": "...", "token_count": N}
        - 失败: raises RuntimeError
        - 进行中: None
    """
    entry = _pending_tasks.get(task_id)
    if entry is None:
        raise RuntimeError(f"mineru_unknown_task: {task_id}")

    # Mock 模式：模拟 3 秒解析延迟
    if entry.get("mock"):
        if time.time() - entry["submitted_at"] < 3:
            return None
        oss_key = entry.get("oss_key", "unknown.pdf")
        title = entry.get("title", "")
        md = (
            f"# [Mock 解析] {title}\n\n"
            f"源文件：`{oss_key}`\n\n"
            "这是 MinerU 未配置时的占位 markdown。"
            "请在 `.env` 中设置 `MINERU_API_KEY` 以启用真实解析。\n"
        )
        # mock 完成后清理
        _pending_tasks.pop(task_id, None)
        return {"markdown": md, "token_count": estimate_tokens(md)}

    headers = {"Authorization": f"Bearer {MINERU_API_KEY}"}
    try:
        r = requests.get(
            f"{MINERU_API_URL}/parse/{task_id}", headers=headers, timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("MinerU poll failed (network): %s", e)
        return None  # 网络错误视作仍在处理，下次再试

    if r.status_code != 200:
        logger.warning("MinerU poll HTTP %d: %s", r.status_code, r.text[:200])
        return None

    try:
        data = r.json().get("data") or {}
    except ValueError:
        return None

    status = data.get("status", "").lower()
    if status == "done" or data.get("markdown"):
        md = data.get("markdown") or ""
        _pending_tasks.pop(task_id, None)
        return {"markdown": md, "token_count": estimate_tokens(md)}
    if status == "failed":
        _pending_tasks.pop(task_id, None)
        raise RuntimeError(f"mineru_parse_failed: {data.get('error', 'unknown')}")
    return None


def list_pending() -> list[str]:
    """返回所有仍在解析中的 task_id。"""
    return list(_pending_tasks.keys())


def get_task_meta(task_id: str) -> dict | None:
    """读取任务的元数据（oss_key 等）。"""
    return _pending_tasks.get(task_id)
