"""
MinerU cloud API client — PDF 转 Markdown。

依赖配置:
- MINERU_API_URL:服务地址(默认 https://mineru.net/api/v4,Precision Extract API v4)
- MINERU_API_KEY:API token,未配置时启用 mock 模式
- MINERU_MODEL_VERSION:解析模型(pipeline / vlm / MinerU-HTML,默认 pipeline)

接口约定(mineru.net Precision Extract API):
- POST {API_URL}/extract/task        提交解析任务
    body: {"url": "<pdf_url>", "model_version": "...", "enable_table": true,
           "enable_formula": true, "language": "ch"}
    resp: {"code":0, "data": {"task_id":"..."}}
- GET  {API_URL}/extract/task/{task_id}   轮询任务状态
    resp: {"code":0, "data": {"state":"pending|running|converting|done|failed",
                              "full_zip_url":"...", "err_msg":"..."}}
    state=done 时,需自行 GET full_zip_url 下载 ZIP 并提取 full.md
"""

from __future__ import annotations

import io
import logging
import time
import zipfile

import requests

from app.config import MINERU_API_URL, MINERU_API_KEY, MINERU_MODEL_VERSION

logger = logging.getLogger(__name__)

# 进程内任务表(MVP):task_id -> {oss_key, stock_code, title, submitted_at}
# 多 worker 部署需换成 DB 表,见 plan Phase 5 「不在本计划范围内的事项」
_pending_tasks: dict[str, dict] = {}

# 已知错误码 -> 友好标识(覆盖 mineru.net /extract/task 文档中的常见错误)
# 让 deep_analysis_service.parse_reports 返回的 results[].error 字段自描述
_MINERU_ERROR_CODES: dict[int, str] = {
    -1:     "invalid_request",       # 含 A0202 invalid token
    -60018: "daily_quota_exceeded",  # 当日免费页数耗尽
    -60019: "concurrent_limit",      # 并发任务超限
    -60020: "file_too_large",        # >200MB
    -60021: "file_too_long",         # >200 页
}

# 模块加载时检测 legacy 占位 URL,避免静默失败(非致命)
if MINERU_API_URL and "mineru.dottore.com" in MINERU_API_URL:
    logger.warning(
        "MINERU_API_URL points to legacy placeholder 'mineru.dottore.com' "
        "(DNS does not resolve). Update .env to https://mineru.net/api/v4."
    )


def is_configured() -> bool:
    """是否配置了真实的 MinerU API key。"""
    return bool(MINERU_API_KEY)


def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。
    中文按 1.5 字符/token,英文/数字按 4 字符/token(OpenAI 经验值)。
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 4)


def _download_and_extract_markdown(zip_url: str) -> str:
    """
    下载 MinerU 结果 ZIP 并提取 full.md。

    ZIP 内容由 MinerU 生成,典型包括 full.md / layout.json / images/ 等。
    本函数只关心 full.md;名字匹配三级降级:
        1. 精确 'full.md'
        2. 大小写变体 'Full.md' / 'FULL.MD'
        3. 任意路径后缀匹配 '*.full.md'(忽略大小写)

    Raises:
        RuntimeError: 下载失败、解压失败或缺失 full.md
    """
    try:
        r = requests.get(zip_url, stream=True, timeout=60)
        r.raise_for_status()
        content = r.content  # ZIP 需完整字节才能 seek
    except requests.RequestException as e:
        raise RuntimeError(f"mineru_zip_download_failed: {e}")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            # 三级降级匹配 full.md
            target: str | None = None
            for candidate in ("full.md", "Full.md", "FULL.MD"):
                if candidate in names:
                    target = candidate
                    break
            if target is None:
                hits = [n for n in names if n.lower().endswith("full.md")]
                if hits:
                    target = hits[0]
            if target is None:
                raise RuntimeError(
                    f"mineru_zip_missing_full_md: entries={names[:10]}"
                )
            with zf.open(target) as f:
                return f.read().decode("utf-8", errors="replace")
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"mineru_zip_bad_zip: {e}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"mineru_zip_extract_failed: {e}")


def submit_parse(pdf_url: str, meta: dict | None = None) -> str:
    """
    提交 PDF 给 MinerU 解析。

    Args:
        pdf_url: PDF 的可访问 URL(OSS signed URL 或公网 URL)
        meta: 附加元数据 {"oss_key", "stock_code", "title"},存入进程表

    Returns:
        task_id(mock 模式下返回 fake id)

    Raises:
        RuntimeError: API 调用失败
    """
    meta = meta or {}

    if not is_configured():
        # Mock 模式:返回 fake task_id,poll 时返回简短 markdown
        task_id = f"mock_{int(time.time() * 1000)}_{len(_pending_tasks)}"
        _pending_tasks[task_id] = {
            **meta,
            "submitted_at": time.time(),
            "mock": True,
        }
        logger.info("[mineru:mock] submit task=%s url=%s", task_id, pdf_url)
        return task_id

    payload = {
        "url": pdf_url,
        "model_version": MINERU_MODEL_VERSION,
        "enable_table": True,
        "enable_formula": True,
        "language": "ch",
    }
    headers = {
        "Authorization": f"Bearer {MINERU_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(
            f"{MINERU_API_URL}/extract/task",
            json=payload, headers=headers, timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("MinerU submit failed (network): %s", e)
        raise RuntimeError(f"mineru_submit_network_error: {e}")

    if r.status_code != 200:
        logger.warning("MinerU submit HTTP %d: %s", r.status_code, r.text[:200])
        raise RuntimeError(f"mineru_submit_http_{r.status_code}: {r.text[:200]}")

    try:
        body = r.json()
    except ValueError:
        raise RuntimeError(f"mineru_submit_invalid_json: {r.text[:200]}")

    code = body.get("code")
    if code != 0:
        msg = body.get("msg", "unknown")
        label = _MINERU_ERROR_CODES.get(code, f"code_{code}")
        logger.warning("MinerU submit error code=%s msg=%s", code, msg)
        raise RuntimeError(f"mineru_submit_{label}: {msg}")

    task_id = (body.get("data") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"mineru_submit_no_task_id: {body}")

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

    # Mock 模式:模拟 3 秒解析延迟
    if entry.get("mock"):
        if time.time() - entry["submitted_at"] < 3:
            return None
        oss_key = entry.get("oss_key", "unknown.pdf")
        title = entry.get("title", "")
        md = (
            f"# [Mock 解析] {title}\n\n"
            f"源文件:`{oss_key}`\n\n"
            "这是 MinerU 未配置时的占位 markdown。"
            "请在 `.env` 中设置 `MINERU_API_KEY` 以启用真实解析。\n"
        )
        # mock 完成后清理
        _pending_tasks.pop(task_id, None)
        return {"markdown": md, "token_count": estimate_tokens(md)}

    headers = {"Authorization": f"Bearer {MINERU_API_KEY}"}
    try:
        r = requests.get(
            f"{MINERU_API_URL}/extract/task/{task_id}",
            headers=headers, timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("MinerU poll failed (network): %s", e)
        return None  # 网络错误视作仍在处理,下次再试

    if r.status_code != 200:
        logger.warning("MinerU poll HTTP %d: %s", r.status_code, r.text[:200])
        return None

    try:
        body = r.json()
    except ValueError:
        return None

    if body.get("code") != 0:
        # 轮询接口出错(含 invalid_token 等)按失败处理
        code = body.get("code")
        msg = body.get("msg", "unknown")
        label = _MINERU_ERROR_CODES.get(code, f"code_{code}")
        _pending_tasks.pop(task_id, None)
        raise RuntimeError(f"mineru_poll_{label}: {msg}")

    data = body.get("data") or {}
    state = (data.get("state") or "").lower()

    if state == "done":
        zip_url = data.get("full_zip_url")
        if not zip_url:
            _pending_tasks.pop(task_id, None)
            raise RuntimeError("mineru_done_missing_zip_url")
        try:
            md = _download_and_extract_markdown(zip_url)
        finally:
            _pending_tasks.pop(task_id, None)
        return {"markdown": md, "token_count": estimate_tokens(md)}

    if state == "failed":
        err = data.get("err_msg") or "unknown"
        _pending_tasks.pop(task_id, None)
        raise RuntimeError(f"mineru_parse_failed: {err}")

    # state in {pending, running, converting} -> 仍在处理
    return None


def list_pending() -> list[str]:
    """返回所有仍在解析中的 task_id。"""
    return list(_pending_tasks.keys())


def get_task_meta(task_id: str) -> dict | None:
    """读取任务的元数据(oss_key 等)。"""
    return _pending_tasks.get(task_id)
