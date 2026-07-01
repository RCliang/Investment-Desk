"""
Deep analysis service — 编排 MinerU 解析 + LLM 多维度分析。

对外暴露：
- parse_reports / parse_status：解析 PDF 到 markdown（结果缓存到 report_contents 表）
- get_cached_markdown：读取已缓存的 markdown
- analyze_stream：SSE 流式 AI 多维度分析
- get_cached_analysis / compute_cache_key：分析结果缓存
- list_history：历史分析列表
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Iterator

from sqlalchemy.orm import Session

from app.config import MODEL_NAME
from app.models.models import ReportContent, DeepAnalysis
from app.services import mineru_service, oss_service
from app.services.llm_service import client as llm_client
from app.config import LLM_MAX_TOKENS

logger = logging.getLogger(__name__)

# 输入 token 上限（保守值，deepseek-chat 上下文窗口 64K，留一半给输出）
MAX_INPUT_TOKENS = 60000


# ═══════════════════════════════════════════════════════════════════
# 缓存键
# ═══════════════════════════════════════════════════════════════════

def compute_cache_key(code: str, oss_keys: list[str]) -> str:
    """排序 + hash 生成稳定缓存键"""
    sorted_keys = sorted(oss_keys)
    raw = f"{code}|{'|'.join(sorted_keys)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


# ═══════════════════════════════════════════════════════════════════
# 解析编排
# ═══════════════════════════════════════════════════════════════════

def parse_reports(code: str, oss_keys: list[str], db: Session) -> dict:
    """
    提交 PDF 给 MinerU 解析。已有缓存的自动跳过。

    返回:
        {
            "total": N,
            "cached": N,
            "submitted": N,
            "failed": N,
            "results": [{"oss_key", "status": "cached|submitted|failed", "error"?, "task_id"?}]
        }
    """
    results = []
    cached_count = 0
    submitted_count = 0
    failed_count = 0

    # 查已有缓存
    existing = {
        rc.oss_key for rc in
        db.query(ReportContent).filter(ReportContent.stock_code == code).all()
    }

    for oss_key in oss_keys:
        if oss_key in existing:
            results.append({"oss_key": oss_key, "status": "cached"})
            cached_count += 1
            continue

        # 检查 OSS 中是否存在该对象
        if not oss_service.object_exists(oss_key):
            results.append({
                "oss_key": oss_key,
                "status": "failed",
                "error": "oss_key_not_found",
            })
            failed_count += 1
            continue

        # 生成签名 URL 给 MinerU 拉取
        try:
            pdf_url = oss_service.sign_url(oss_key, expires=3600)
        except Exception as e:
            logger.warning("sign_url failed for %s: %s", oss_key, e)
            results.append({
                "oss_key": oss_key, "status": "failed",
                "error": "oss_sign_error",
            })
            failed_count += 1
            continue

        # 提交 MinerU
        try:
            task_id = mineru_service.submit_parse(
                pdf_url,
                meta={"oss_key": oss_key, "stock_code": code, "title": ""},
            )
            results.append({
                "oss_key": oss_key, "status": "submitted", "task_id": task_id,
            })
            submitted_count += 1
        except RuntimeError as e:
            logger.warning("submit_parse failed for %s: %s", oss_key, e)
            results.append({
                "oss_key": oss_key, "status": "failed",
                "error": str(e),
            })
            failed_count += 1

    return {
        "total": len(oss_keys),
        "cached": cached_count,
        "submitted": submitted_count,
        "failed": failed_count,
        "results": results,
    }


def parse_status(code: str, db: Session) -> dict:
    """
    轮询该股票所有未完成的解析任务，完成的写入 report_contents。

    返回:
        {
            "code": code,
            "total": N, "done": N, "pending": N, "failed": N,
            "details": [{"oss_key", "status", "token_count"?, "error"?}]
        }
    """
    # 该股票所有 pending task：通过进程内 task 表的 stock_code 过滤
    pending_tids = [
        tid for tid in mineru_service.list_pending()
        if (mineru_service.get_task_meta(tid) or {}).get("stock_code") == code
    ]

    # 已写入 DB 的（done 的子集）
    db_records = {
        rc.oss_key: rc for rc in
        db.query(ReportContent).filter(ReportContent.stock_code == code).all()
    }

    details = []
    pending_count = 0
    failed_count = 0
    done_count = 0

    for tid in pending_tids:
        meta = mineru_service.get_task_meta(tid) or {}
        oss_key = meta.get("oss_key", "")
        try:
            result = mineru_service.poll_result(tid)
        except RuntimeError as e:
            failed_count += 1
            details.append({
                "oss_key": oss_key, "status": "failed", "error": str(e),
            })
            continue

        if result is None:
            pending_count += 1
            details.append({"oss_key": oss_key, "status": "parsing"})
        else:
            # 完成 → 写入 DB
            rc = ReportContent(
                oss_key=oss_key,
                stock_code=code,
                title=meta.get("title", ""),
                markdown_text=result["markdown"],
                token_count=result["token_count"],
                parsed_at=datetime.now(),
            )
            db.add(rc)
            db.commit()
            done_count += 1
            details.append({
                "oss_key": oss_key, "status": "done",
                "token_count": result["token_count"],
            })

    # 已在 DB 的（之前完成的）
    for oss_key, rc in db_records.items():
        # 避免与刚写入的重复
        if any(d["oss_key"] == oss_key for d in details):
            continue
        done_count += 1
        details.append({
            "oss_key": oss_key, "status": "done",
            "token_count": rc.token_count or 0,
        })

    total = done_count + pending_count + failed_count
    return {
        "code": code,
        "total": total,
        "done": done_count,
        "pending": pending_count,
        "failed": failed_count,
        "details": details,
    }


def get_cached_markdown(
    code: str, oss_keys: list[str], db: Session,
) -> list[dict]:
    """从 DB 读取已解析的 markdown，按 parsed_at 倒序（最新优先）。"""
    records = (
        db.query(ReportContent)
        .filter(
            ReportContent.stock_code == code,
            ReportContent.oss_key.in_(oss_keys),
        )
        .order_by(ReportContent.parsed_at.desc())
        .all()
    )
    return [
        {
            "oss_key": rc.oss_key,
            "title": rc.title or "",
            "markdown_text": rc.markdown_text,
            "token_count": rc.token_count or 0,
            "parsed_at": rc.parsed_at.isoformat() if rc.parsed_at else "",
        }
        for rc in records
    ]


# ═══════════════════════════════════════════════════════════════════
# LLM 多维度分析
# ═══════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT_TEMPLATE = """你是一位专业的证券分析师。以下是关于股票代码 {code} 的 {n} 篇研究报告内容。

请从以下四个维度进行深度分析：

## 一、核心观点提取
逐篇提取每篇报告的核心投资观点、评级、目标价（如有）。每篇以子标题分隔。

## 二、估值与盈利预测汇总
汇总各机构的营收/净利润预测、PE/PB 估值。用 markdown 表格呈现对比。

## 三、多报告一致性分析
分析各报告观点的一致与分歧。明确指出哪些是市场共识，哪些存在争议。

## 四、行业与竞争格局
提取行业趋势判断、竞争对手对比、公司核心壁垒。

输出要求：
- 使用 markdown 格式
- 表格、列表、标题层次清晰
- 在每个维度末尾给出「关键结论」一句话总结
- 如果研报信息不全，明确指出"数据不足"而不是编造

---

以下是研报内容：

{reports}
"""


def _truncate_reports(reports: list[dict], max_tokens: int = MAX_INPUT_TOKENS) -> list[dict]:
    """
    累加 token_count，超过上限时按倒序截断（保留最新）。
    单篇超长时截取前 N 字符。
    """
    total = 0
    out = []
    for r in reports:  # reports 已是 parsed_at 倒序
        # 单篇最多 30K 字符（约 15K tokens）
        md = r["markdown_text"][:30000]
        tokens = r["token_count"]
        # 重新估算（防止上面截断后 token 数虚高）
        if len(md) < len(r["markdown_text"]):
            tokens = mineru_service.estimate_tokens(md)

        if total + tokens > max_tokens:
            # 该报告放不下，跳过
            logger.info("truncate: skip %s (would exceed %d tokens)",
                        r["oss_key"], max_tokens)
            continue
        total += tokens
        out.append({**r, "markdown_text": md, "token_count": tokens})
    return out


def _build_prompt(code: str, reports: list[dict]) -> str:
    """组装最终 prompt。"""
    sections = []
    for i, r in enumerate(reports, 1):
        title = r.get("title") or f"研报{i}"
        date = r.get("parsed_at", "")[:10]
        sections.append(
            f"【研报{i}】{title}（解析于 {date}）\n\n{r['markdown_text']}"
        )
    return ANALYSIS_PROMPT_TEMPLATE.format(
        code=code,
        n=len(reports),
        reports="\n\n---\n\n".join(sections),
    )


def analyze_stream(
    code: str, oss_keys: list[str], db: Session,
) -> Iterator[str]:
    """
    SSE 流式生成 AI 分析。

    yield:
        - 正常 chunk: 直接 yield 字符串（router 层包成 event: chunk）
        - 完成后由 router 负责发 event: done

    副作用：流结束后将完整 markdown 写入 deep_analyses 表。
    """
    # 读取 markdown
    reports = get_cached_markdown(code, oss_keys, db)
    if not reports:
        raise RuntimeError("no_parsed_reports: 请先完成 PDF 解析")

    # 截断
    truncated = _truncate_reports(reports)
    if not truncated:
        raise RuntimeError("all_reports_truncated: 研报总长度超出模型上下文")

    prompt = _build_prompt(code, truncated)

    if llm_client is None:
        # Mock 模式：返回简短占位
        full = _mock_analysis(code, len(reports))
        yield full
        _persist_analysis(code, oss_keys, full, db)
        return

    # 流式调用 LLM
    full_content = ""
    try:
        stream = llm_client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=LLM_MAX_TOKENS * 2,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_content += delta
                yield delta
    except Exception as e:
        logger.warning("LLM stream failed: %s", e)
        raise RuntimeError(f"llm_error: {e}")

    _persist_analysis(code, oss_keys, full_content, db)


def _persist_analysis(code: str, oss_keys: list[str], content: str, db: Session) -> None:
    """分析完成后持久化。"""
    cache_key = compute_cache_key(code, oss_keys)
    # 同 cache_key 覆盖（重新分析）
    existing = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if existing:
        existing.analysis_text = content
        existing.model_name = MODEL_NAME
        existing.created_at = datetime.now()
    else:
        db.add(DeepAnalysis(
            stock_code=code,
            oss_keys_json=json.dumps(oss_keys, ensure_ascii=False),
            cache_key=cache_key,
            analysis_text=content,
            model_name=MODEL_NAME,
        ))
    db.commit()


def get_cached_analysis(
    code: str, oss_keys: list[str], db: Session,
) -> dict | None:
    """命中缓存返回 {analysis_text, created_at}，否则 None。"""
    cache_key = compute_cache_key(code, oss_keys)
    record = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if not record:
        return None
    return {
        "analysis_text": record.analysis_text,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "model_name": record.model_name or "",
    }


def list_history(code: str, db: Session, limit: int = 20) -> dict:
    """该股票的历史分析列表。"""
    records = (
        db.query(DeepAnalysis)
        .filter(DeepAnalysis.stock_code == code)
        .order_by(DeepAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "code": code,
        "analyses": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "model_name": r.model_name or "",
                "report_count": len(json.loads(r.oss_keys_json or "[]")),
                "preview": (r.analysis_text or "")[:200],
            }
            for r in records
        ],
    }


def get_analysis_by_id(analysis_id: int, db: Session) -> dict | None:
    """按 id 拉取单条历史分析全文。"""
    r = db.query(DeepAnalysis).filter(DeepAnalysis.id == analysis_id).first()
    if not r:
        return None
    return {
        "id": r.id,
        "stock_code": r.stock_code,
        "oss_keys": json.loads(r.oss_keys_json or "[]"),
        "analysis_text": r.analysis_text,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "model_name": r.model_name or "",
    }


# ═══════════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════════

def _mock_analysis(code: str, n_reports: int) -> str:
    """LLM 未配置时的 mock 输出。"""
    return f"""# 股票 {code} 深度分析（Mock）

> 当前未配置 DEEPSEEK_API_KEY，以下为占位内容。

## 一、核心观点提取

基于 {n_reports} 篇研报的模拟提取结果。配置 LLM 后将生成真实分析。

## 二、估值与盈利预测汇总

| 机构 | 年份 | 营收预测 | 净利润预测 | PE |
|------|------|---------|-----------|-----|
| Mock | 2026E | 待填 | 待填 | 待填 |

## 三、多报告一致性分析

[Mock] 共识与分歧分析将在 LLM 配置后生成。

## 四、行业与竞争格局

[Mock] 行业趋势、竞争对手、核心壁垒将在 LLM 配置后生成。
"""
