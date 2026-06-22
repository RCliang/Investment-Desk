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
