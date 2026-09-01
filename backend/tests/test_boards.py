"""Tests for the market board heat stack (板块冷热).

Layers covered:
  1. Board classification: perf/style blacklists, suffix rules, region.
  2. THS tag split: thematic vs earnings-style (业绩线).
  3. Heat computation on a synthetic universe: percentile bounds,
     mainline detection for the sustained outperformer, theme matching.
  4. Query layer: zombie filter in the display set, heatmap shapes,
     detail excess-return chaining.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.quant import board_service as bs


# ── Classification ──────────────────────────────────────────────────────────

class TestClassifyBoard:

    def test_blacklists_take_priority(self):
        ct: dict[str, str] = {}
        assert bs._classify_board("融资融券", "m:90+t:2", ct) == "index"
        assert bs._classify_board("小盘股", "m:90+t:1", ct) == "index"
        assert bs._classify_board("2026中报预增", "m:90+t:1", ct) == "perf"
        assert bs._classify_board("2025年报扭亏", "m:90+t:3", ct) == "perf"

    def test_suffix_and_region_rules(self):
        ct: dict[str, str] = {}
        assert bs._classify_board("华为概念", "m:90+t:1", ct) == "concept"
        assert bs._classify_board("贵州板块", "m:90+t:1", ct) == "region"
        assert bs._classify_board("黑龙江", "m:90+t:2", ct) == "region"
        assert bs._classify_board("其他家电Ⅱ", "m:90+t:2", ct) == "industry"

    def test_concept_cross_check(self):
        ct = {"白酒": "industry", "AI眼镜": "concept"}
        assert bs._classify_board("白酒", "m:90+t:9", ct) == "industry"
        assert bs._classify_board("AI眼镜", "m:90+t:9", ct) == "concept"

    def test_fs_fallback(self):
        ct: dict[str, str] = {}
        assert bs._classify_board("算力租赁", "m:90+t:2", ct) == "industry"
        assert bs._classify_board("算力租赁", "m:90+t:1", ct) == "concept"


# ── THS tag split ───────────────────────────────────────────────────────────

def test_theme_tag_type_split():
    assert bs._PERF_TAG_RE.search("半年报增长")
    assert bs._PERF_TAG_RE.search("中报扭亏")
    assert not bs._PERF_TAG_RE.search("算力租赁")
    assert not bs._PERF_TAG_RE.search("AI应用")


# ── Heat computation (synthetic universe) ───────────────────────────────────

@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import chain_models  # noqa: F401 register tables

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_universe(db) -> list[date]:
    """5 boards × 40 weekdays + benchmark + THS themes.

    BK01 持续主线: steady +0.9%/day with positive inflow → mainline.
    BK02 一日游:  flat except one +9% spike → not mainline.
    BK04 平庸股:  tracks the benchmark → bottom-mid heat.
    BK05 僵尸概念: 2 members → excluded from display by the zombie filter.
    """
    from app.models.chain_models import BoardDaily, BoardMeta, ThemeDaily

    start = date(2026, 5, 1)
    days = [start + timedelta(days=i) for i in range(45)
            if (start + timedelta(days=i)).weekday() < 5]
    boards = {
        "BK01": ("持续主线", "industry"),
        "BK02": ("一日游", "concept"),
        "BK03": ("退潮股", "concept"),
        "BK04": ("平庸股", "industry"),
        "BK05": ("僵尸概念", "concept"),
    }
    for code, (name, t) in boards.items():
        db.add(BoardMeta(bk_code=code, name=name, bk_type=t,
                         member_hint=2 if code == "BK05" else 50,
                         first_seen=days[0], last_seen=days[-1], is_active=True))
    db.add(BoardMeta(bk_code=bs.BENCHMARK_CODE, name="沪深300",
                     bk_type="benchmark", first_seen=days[0], last_seen=days[-1],
                     is_active=True))

    rows = []
    for i, d in enumerate(days):
        rows.append({"date": d, "bk_code": bs.BENCHMARK_CODE, "change_pct": 0.05})
        rows.append({"date": d, "bk_code": "BK01", "change_pct": 0.9,
                     "main_net": 5e8, "turnover_yi": 20.0,
                     "up_cnt": 40, "down_cnt": 10})
        rows.append({"date": d, "bk_code": "BK02",
                     "change_pct": 9.0 if i == 30 else 0.0,
                     "main_net": 6e8 if i == 30 else -1e8,
                     "turnover_yi": 15.0, "up_cnt": 25, "down_cnt": 25})
        rows.append({"date": d, "bk_code": "BK03",
                     "change_pct": 1.2 if i < 25 else -1.0,
                     "main_net": 4e8 if i < 25 else -5e8,
                     "turnover_yi": 18.0, "up_cnt": 42, "down_cnt": 8})
        rows.append({"date": d, "bk_code": "BK04", "change_pct": 0.05,
                     "main_net": 0.0, "turnover_yi": 10.0,
                     "up_cnt": 25, "down_cnt": 25})
        rows.append({"date": d, "bk_code": "BK05", "change_pct": 0.1,
                     "main_net": 1e6, "turnover_yi": 0.4, "up_cnt": 1, "down_cnt": 1})
    db.bulk_insert_mappings(BoardDaily, rows)
    db.bulk_insert_mappings(ThemeDaily, [
        {"date": d, "tag": "持续主线", "tag_type": "theme", "strong_cnt": 6}
        for d in days[-20:]])
    db.commit()
    return days


class TestHeatComputation:

    def test_heat_bounds_and_mainline(self, db_session):
        from app.models.chain_models import BoardHeat
        days = _seed_universe(db_session)

        result = bs.compute_and_store_heat(db_session)
        assert result["dates"] == len(days)
        assert result["boards"] == 5

        final = {r.bk_code: r for r in db_session.query(BoardHeat)
                 .filter(BoardHeat.date == days[-1]).all()}
        for r in final.values():
            assert 0.0 <= r.heat <= 100.0
            assert 0.0 <= r.heat_ema <= 100.0
        # sustained outperformer with positive inflow → mainline, top rank
        assert final["BK01"].tag == "mainline"
        assert final["BK01"].heat_rank == 1
        # theme matched → theme_cnt from the THS series
        assert final["BK01"].theme_cnt == 6
        # one-day spike must NOT be a mainline
        assert final["BK02"].tag in ("cool", "starting")
        # benchmark hugging board ranks below the outperformers
        assert final["BK04"].heat_rank > final["BK01"].heat_rank

    def test_zombie_filter_and_query_layer(self, db_session):
        from app.models.chain_models import BoardHeat
        days = _seed_universe(db_session)
        bs.compute_and_store_heat(db_session)

        ov = bs.get_overview(db_session, days=20)
        names = {b["name"] for b in ov["industries"] + ov["concepts"]}
        assert "僵尸概念" not in names          # member_hint=2 < 8
        assert "持续主线" in names
        assert all(b["spark"] and len(b["spark"]["heat"]) >= 2
                   for b in ov["industries"] + ov["concepts"])

        hm = bs.get_heatmap(db_session, days=30)
        assert len(hm["dates"]) == min(30, len(days))
        assert all(len(r["values"]) == len(hm["dates"]) for r in hm["rows"])

        det = bs.get_board_detail(db_session, "BK01", days=100)
        assert det["name"] == "持续主线"
        # cumulative excess strictly positive for the steady outperformer
        assert det["excess"][-1] > 10.0
        assert det["latest"]["tag"] == "mainline"

    def test_theme_trends_shape(self, db_session):
        days = _seed_universe(db_session)
        th = bs.get_theme_trends(db_session, days=20)
        assert "持续主线" in th["themes"]
        assert all(len(v) == len(th["dates"]) for v in th["themes"].values())

    def test_idempotent_rerun(self, db_session):
        from app.models.chain_models import BoardHeat
        days = _seed_universe(db_session)
        bs.compute_and_store_heat(db_session)
        bs.compute_and_store_heat(db_session)
        n = db_session.query(BoardHeat).filter(
            BoardHeat.date == days[-1]).count()
        assert n == 5  # no duplicate rows after recompute
