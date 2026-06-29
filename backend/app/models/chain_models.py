"""
SQLAlchemy models for the AI chain knowledge base (v1).

Scope: Structured entities for the Layer → SubIndustry → Company → Concept
hierarchy defined in CONTEXT.md, plus per-ticker time-series tables populated
from the backfill JSON files in backend/data/.

Naming convention: All v1 chain tables prefixed with `chain_` to avoid
collision with the v0 tables (chain_analyses / data_cache / reports / plans).

Lifecycle: Per CONTEXT.md, every entity carries a `lifecycle` column taking
one of: 'canonical' (default, visible) / 'generated' (hidden, awaiting
review) / 'deprecated' (hidden, retained for history). Backfill-loaded rows
default to 'generated' since they are AI-extracted and should be reviewed
before being surfaced as canonical.

Loader: backend/scripts/load_seed_to_db.py performs idempotent upserts.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, Date,
)
from sqlalchemy.sql import func

from app.db import Base


# ── Lifecycle constants (match CONTEXT.md §Data lifecycle) ────────────────
LIFECYCLE_CANONICAL = "canonical"
LIFECYCLE_GENERATED = "generated"
LIFECYCLE_DEPRECATED = "deprecated"


# ── Static structural entities ────────────────────────────────────────────

class Layer(Base):
    """A horizontal slice of the AI chain. v1 seed: 5 rows, fixed set.

    Per ADR-0002 the seed layer set is closed; amendments require an ADR.
    """
    __tablename__ = "chain_layers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False)        # e.g. "I", "II"
    name_zh = Column(String(64), nullable=False)                  # e.g. "能源与电力"
    name_en = Column(String(64), nullable=False)                  # e.g. "Energy"
    layer_order = Column(Integer, nullable=False, unique=True)    # 1..5
    lifecycle = Column(String(16), nullable=False,
                       default=LIFECYCLE_CANONICAL, index=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())


class SubIndustry(Base):
    """A node within a Layer grouping companies with similar products.

    v1 seed: 48 rows, adopted verbatim from aichainmap.com (ADR-0007).
    """
    __tablename__ = "chain_sub_industries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(16), unique=True, nullable=False,
                      index=True)                                  # e.g. "II-M-1"
    layer_id = Column(Integer, ForeignKey("chain_layers.id"),
                      nullable=False, index=True)
    name_zh = Column(String(128), nullable=False)
    name_en = Column(String(128), default="")
    lifecycle = Column(String(16), nullable=False,
                       default=LIFECYCLE_CANONICAL, index=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())


class Company(Base):
    """An operating business assigned to one or more Sub-industries.

    Reference Companies (NVIDIA, TSMC, ...) live in the same table,
    distinguished by is_reference=True and listing_market outside
    {SH, SZ, BJ}. CN companies carry listing_ticker for joining market data.
    """
    __tablename__ = "chain_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name_zh = Column(String(128), nullable=False, index=True)
    name_en = Column(String(128), default="")
    listing_market = Column(String(8), index=True)                # SH/SZ/BJ/HK/NASDAQ/...
    listing_ticker = Column(String(16), index=True)               # 688981 / NVDA / ...
    is_reference = Column(Boolean, default=False, index=True)     # True for foreign peers
    lifecycle = Column(String(16), nullable=False,
                       default=LIFECYCLE_GENERATED, index=True)   # backfill default
    description = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now())


class Concept(Base):
    """A thematic tag spanning Layers/Sub-industries (e.g., 国产替代, AI眼镜).

    Derived from EM slist concept_blocks output. Classified into
    industry/concept/region/index by name pattern.
    """
    __tablename__ = "chain_concepts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    tag_type = Column(String(16), nullable=False, index=True,
                      default="concept")                          # industry/concept/region/index
    lifecycle = Column(String(16), nullable=False,
                       default=LIFECYCLE_GENERATED, index=True)
    created_at = Column(DateTime, server_default=func.now())


# ── Junction tables (M:N cross-references) ────────────────────────────────

class SubIndustryCompany(Base):
    """A Company's membership in a Sub-industry. M:N.

    A Company may appear in multiple Sub-industries across Layers (e.g.,
    中芯国际 appears in II-U-1 and others). Role reserved for future use
    (e.g., 'lead' vs 'participant').
    """
    __tablename__ = "chain_sub_industry_companies"
    __table_args__ = (
        UniqueConstraint("sub_industry_id", "company_id",
                         name="uq_subind_company"),
        Index("ix_subind_company_subind", "sub_industry_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sub_industry_id = Column(Integer, ForeignKey("chain_sub_industries.id"),
                             nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("chain_companies.id"),
                        nullable=False, index=True)
    role = Column(String(32), default="member")                   # lead / member / alternative
    created_at = Column(DateTime, server_default=func.now())


class CompanyConcept(Base):
    """A Concept tagging a Company (e.g., 600519 tagged with 酿酒概念).

    Sourced from EM slist concept_blocks backfill.
    """
    __tablename__ = "chain_company_concepts"
    __table_args__ = (
        UniqueConstraint("company_id", "concept_id",
                         name="uq_company_concept"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("chain_companies.id"),
                        nullable=False, index=True)
    concept_id = Column(Integer, ForeignKey("chain_concepts.id"),
                        nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())


# ── Time-series market data tables (one row per ticker per snapshot) ──────

class Quote(Base):
    """Latest real-time quote snapshot per ticker. Tencent source.

    Refresh cadence: every 5 minutes during trading (per CLAUDE.md).
    Stored as a single latest row per ticker; history not retained in v1.
    """
    __tablename__ = "chain_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), unique=True, nullable=False, index=True)
    name = Column(String(64), default="")
    price = Column(Float)
    last_close = Column(Float)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    change_amt = Column(Float)
    change_pct = Column(Float)
    amount_wan = Column(Float)                                     # 成交额 (万元)
    turnover_pct = Column(Float)                                   # 换手率
    pe_ttm = Column(Float)
    pe_static = Column(Float)
    pb = Column(Float)
    mcap_yi = Column(Float)                                        # 总市值 (亿)
    float_mcap_yi = Column(Float)                                  # 流通市值 (亿)
    limit_up = Column(Float)
    limit_down = Column(Float)
    vol_ratio = Column(Float)
    amplitude_pct = Column(Float)
    fetched_at = Column(DateTime, nullable=False, index=True,
                        server_default=func.now())
    source = Column(String(32), default="tencent")


class FinanceSnapshot(Base):
    """Latest quarterly finance snapshot per ticker. mootdx source.

    Refresh cadence: daily after close (per CLAUDE.md TTL).
    """
    __tablename__ = "chain_finance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), unique=True, nullable=False, index=True)
    eps = Column(Float)                                            # 每股收益
    bvps = Column(Float)                                           # 每股净资产
    roe_pct = Column(Float)                                        # 净资产收益率%
    net_margin_pct = Column(Float)                                 # 销售净利率%
    gross_margin_pct = Column(Float)                               # 销售毛利率%
    revenue_yi = Column(Float)                                     # 营业收入 (亿)
    net_profit_yi = Column(Float)                                  # 净利润 (亿)
    debt_ratio_pct = Column(Float)                                 # 资产负债率%
    float_shares = Column(Float)                                   # 流通股本 (万股)
    total_shares = Column(Float)                                   # 总股本 (万股)
    fetched_at = Column(DateTime, nullable=False, index=True,
                        server_default=func.now())
    source = Column(String(32), default="mootdx")


class LockupEvent(Base):
    """Historical + upcoming lockup expiry event. EM datacenter source.

    Each row = one (ticker, date) lockup event. 'is_upcoming' flag
    distinguishes past from next-90-day forward.
    """
    __tablename__ = "chain_lockup_events"
    __table_args__ = (
        UniqueConstraint("ticker", "date", "type",
                         name="uq_lockup_event"),
        Index("ix_lockup_ticker_date", "ticker", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    type = Column(String(64), default="")                          # 解禁股本类型
    shares_wan = Column(Float)                                     # 解禁股数 (万股)
    ratio_pct = Column(Float)                                      # 占解禁前流通股本比例%
    mcap_wan = Column(Float)                                       # 解禁市值 (万元)
    total_shares_ratio_pct = Column(Float)                         # 占总股本比例%
    is_upcoming = Column(Boolean, default=False, index=True)
    fetched_at = Column(DateTime, nullable=False, server_default=func.now())


class HolderPeriod(Base):
    """Quarterly holder-num disclosure per ticker. EM datacenter source.

    Each row = one (ticker, end_date) disclosure. History retained
    for trend analysis.
    """
    __tablename__ = "chain_holder_periods"
    __table_args__ = (
        UniqueConstraint("ticker", "end_date", name="uq_holder_period"),
        Index("ix_holder_ticker_date", "ticker", "end_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), nullable=False, index=True)
    end_date = Column(Date, nullable=False)                        # 报告期
    notice_date = Column(Date)                                     # 披露日
    holder_num = Column(Integer)                                   # 股东户数
    change_num = Column(Integer)                                   # 较上期变化数
    change_ratio_pct = Column(Float)                               # 环比%
    avg_free_shares = Column(Float)                                # 户均流通股
    avg_hold_amt_yi = Column(Float)                                # 户均持股金额 (亿)
    close_price = Column(Float)
    fetched_at = Column(DateTime, nullable=False, server_default=func.now())


class MarginDaily(Base):
    """Daily margin trading record. EM datacenter source.

    Each row = one (ticker, date) daily margin snapshot. 30 days of
    history retained per backfill cycle.
    """
    __tablename__ = "chain_margin_daily"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_margin_daily"),
        Index("ix_margin_ticker_date", "ticker", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), nullable=False, index=True)
    date = Column(Date, nullable=False)
    rzye_yi = Column(Float)                                        # 融资余额 (亿)
    rqye_yi = Column(Float)                                        # 融券余额 (亿)
    rzrqye_yi = Column(Float)                                      # 合计 (亿)
    rzmre_yi = Column(Float)                                       # 融资买入额 (亿)
    rzche_yi = Column(Float)                                       # 融资偿还额 (亿)
    rzjme_yi = Column(Float)                                       # 融资净买额 (亿)
    rqmcl_wan = Column(Float)                                      # 融券卖出量 (万股)
    rqchl_wan = Column(Float)                                      # 融券偿还量 (万股)
    rqjmg_wan = Column(Float)                                      # 融券净买股 (万股)
    rzyezb_pct = Column(Float)                                     # 融资余额占比%
    close_price = Column(Float)
    change_pct = Column(Float)
    fetched_at = Column(DateTime, nullable=False, server_default=func.now())


class ResearchReport(Base):
    """Sell-side analyst research report metadata. EM reportapi source.

    PDF content never scraped in v1 (per CONTEXT.md line 94).
    Each row = one report identified by (ticker, info_code).
    """
    __tablename__ = "chain_research_reports"
    __table_args__ = (
        UniqueConstraint("ticker", "info_code", name="uq_report_info_code"),
        Index("ix_report_ticker_date", "ticker", "publish_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(16), nullable=False, index=True)
    publish_date = Column(Date, nullable=False, index=True)
    broker = Column(String(64), default="")                        # orgSName
    title = Column(String(512), default="")
    rating = Column(String(32), default="")                        # emRatingName
    industry = Column(String(64), default="")                      # indvInduName
    info_code = Column(String(64), default="")                     # PDF URL key
    predict_this_year_eps = Column(Float)
    predict_next_year_eps = Column(Float)
    predict_next_two_year_eps = Column(Float)
    fetched_at = Column(DateTime, nullable=False, server_default=func.now())


class ChainRefreshLog(Base):
    """Audit trail for every data refresh run (manual, scheduled, or CLI).

    One row per refresh attempt. Lifecycle: insert with status='running'
    on start, update to 'succeeded' or 'failed' on completion.

    The freshness endpoint reads the most recent 'succeeded' row per
    refresh_type to compute last_success_at / minutes_ago.
    """
    __tablename__ = "chain_refresh_log"
    __table_args__ = (
        Index("ix_refresh_type_status", "refresh_type", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    refresh_type = Column(String(16), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False,
                        server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False,
                    default="running")  # running | succeeded | failed
    rows_affected = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    triggered_by = Column(String(16), nullable=False,
                          default="manual")  # manual | scheduler | cli


__all__ = [
    # Static entities
    "Layer", "SubIndustry", "Company", "Concept",
    # Junctions
    "SubIndustryCompany", "CompanyConcept",
    # Time-series
    "Quote", "FinanceSnapshot", "LockupEvent", "HolderPeriod",
    "MarginDaily", "ResearchReport",
    # Refresh log
    "ChainRefreshLog",
    # Constants
    "LIFECYCLE_CANONICAL", "LIFECYCLE_GENERATED", "LIFECYCLE_DEPRECATED",
]
