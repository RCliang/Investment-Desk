from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from app.db import Base


class ChainAnalysis(Base):
    __tablename__ = "chain_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    industry = Column(String(100), nullable=False, index=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class DataCache(Base):
    __tablename__ = "data_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(500), unique=True, nullable=False, index=True)
    result_json = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    industry = Column(String(100), nullable=False, index=True)
    chain_analysis_id = Column(Integer, nullable=True)
    content_md = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class InvestmentPlan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)  # buy / sell
    position_ratio = Column(Float, nullable=False)
    target_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReportContent(Base):
    """研报 PDF 解析后的 markdown 缓存。同一份 PDF（oss_key）只解析一次。"""
    __tablename__ = "report_contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    oss_key = Column(String(500), unique=True, nullable=False, index=True)
    stock_code = Column(String(6), nullable=False, index=True)
    title = Column(String(500), default="")
    markdown_text = Column(Text, nullable=False)
    parsed_at = Column(DateTime, server_default=func.now())
    token_count = Column(Integer, default=0)


class DeepAnalysis(Base):
    """AI 多维度分析结果持久化。相同 code + oss_keys 组合可复用缓存。"""
    __tablename__ = "deep_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(6), nullable=False, index=True)
    oss_keys_json = Column(Text, nullable=False)  # JSON list
    cache_key = Column(String(64), unique=True, nullable=False, index=True)  # 排序+hash，用于命中判断
    analysis_text = Column(Text)                       # 改:去掉 nullable=False (v2 可能只写 struct)
    analysis_struct_json = Column(Text)                # 新:v2 结构化桶数据
    analysis_version = Column(String(20), default="v1")  # 新:schema 版本
    company_type = Column(String(50))                  # 新:equipment/material/packaging/ip/general
    model_name = Column(String(100), default="")
    created_at = Column(DateTime, server_default=func.now())
