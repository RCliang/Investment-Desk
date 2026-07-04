"""
Deep analysis smoke test — 真实 LLM 端到端验证。

默认跳过(标记 @pytest.mark.smoke)。带 DEEPSEEK_API_KEY 时显式运行:
    DEEPSEEK_API_KEY=xxx pytest backend/tests -m smoke
"""
import asyncio
import json
from datetime import datetime

import pytest

from app.config import DEEPSEEK_API_KEY
from app.db import SessionLocal
from app.models.models import Base, ReportContent, DeepAnalysis
from app.services.deep_analysis import orchestrate, storage
from app.services.deep_analysis.schemas import AnalysisDoc
from app.services import llm_service
from app.db import sync_engine


@pytest.mark.smoke
@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY not configured")
def test_smoke_equipment_full_pipeline():
    """真实 LLM,4 个桶(equipment 模式 5 个桶),至少 3 个 bucket_done。"""
    # 准备一份真 markdown(1500 字模拟研报)
    markdown = """
    北方华创(002371)是国内领先的半导体设备厂商,主要产品包括刻蚀机、PVD、CVD、清洗设备等。
    国产化率方面,目前我国半导体设备国产化率约 15%-20%,部分细分领域如刻蚀机已突破 30%。
    主要竞争对手包括中微公司、拓荆科技、芯源微等。客户端认证方面,公司产品已进入中芯国际、
    长江存储、华虹半导体等主流晶圆厂的供应链体系。在产业链环节上,公司位于半导体设备制造中游,
    上游零部件仍有较高进口依赖,下游客户为晶圆代工厂和 IDM 厂商。
    """ * 10  # 重复 10 次凑到 >200 字

    # 用真 DB(测试用 in-memory 避免污染生产)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 灌入 markdown
        db.add(ReportContent(
            oss_key="smoke.pdf", stock_code="002371", title="北方华创深度",
            markdown_text=markdown, token_count=1000, parsed_at=datetime.now(),
        ))
        db.commit()

        # 验证 LLM client 可用
        assert llm_service.client is not None, "DEEPSEEK_API_KEY 未生效"

        # 跑 orchestrate(equipment 模式 5 个桶)
        events = []
        async def collect():
            async for evt in orchestrate(db, "002371", ["smoke.pdf"], "equipment", force_refresh=True):
                events.append(evt)
        asyncio.run(collect())

        event_types = [e["event"] for e in events]
        assert event_types[0] == "start"
        assert event_types[-1] == "done"

        done_bucket_count = event_types.count("bucket_done")
        error_bucket_count = event_types.count("bucket_error")
        # 5 个桶,允许部分失败,但至少 3 个成功
        assert done_bucket_count >= 3, f"只有 {done_bucket_count} 个桶成功(失败 {error_bucket_count})"

        # 验证持久化
        cached = storage.load_cached(db, "002371", ["smoke.pdf"], "equipment")
        assert cached is not None
        assert cached.company_type == "equipment"
        assert len(cached.buckets) >= 3

        # 验证字段提取出了真信息(至少一个非 unknown 字段)
        non_unknown_count = 0
        for bucket in cached.buckets:
            for fv in bucket.fields.values():
                if fv.evidence != "unknown":
                    non_unknown_count += 1
        assert non_unknown_count >= 5, f"提取的非 unknown 字段太少({non_unknown_count} 个)"
    finally:
        db.close()
        engine.dispose()
