"""데이터 모델: 계약, 할 일, 판정, 경보 (명세서 DATA-05 등).

필드 이름은 rules/fields.yaml과 맞춘다 (점(.)은 밑줄로 바꿈).
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# PostgreSQL에서는 JSONB, SQLite에서는 JSON
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Contract(Base):
    """계약 1건. 계약 당일 체크에서 날짜·조건을 입력하면 만든다 (FR-014)."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    housing_type: Mapped[str] = mapped_column(String(32))
    deposit: Mapped[int] = mapped_column(Integer)
    monthly_rent: Mapped[int] = mapped_column(Integer, default=0)
    exclusive_area: Mapped[float | None] = mapped_column(Float)
    official_price: Mapped[int | None] = mapped_column(Integer)

    contract_date: Mapped[date | None] = mapped_column(Date)
    balance_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    loan: Mapped[bool] = mapped_column(Boolean, default=False)
    loan_execution_date: Mapped[date | None] = mapped_column(Date)
    guarantor: Mapped[str] = mapped_column(String(8), default="none")
    brokered: Mapped[bool] = mapped_column(Boolean, default=True)
    renewal_right_used: Mapped[bool] = mapped_column(Boolean, default=False)
    co_tenant: Mapped[bool] = mapped_column(Boolean, default=False)

    # 특약별 넣음/거절당함 {"S-NO-MORTGAGE": "rejected", ...} (FR-049)
    special_term_result: Mapped[dict] = mapped_column(JSONType, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    todos: Mapped[list["Todo"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    verdicts: Mapped[list["Verdict"]] = relationship(back_populates="contract")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class Verdict(Base):
    """판정 결과 1회분. 계약 전 무료 확인은 계약 없이 저장한다 (FR-009)."""

    __tablename__ = "verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))

    inputs: Mapped[dict] = mapped_column(JSONType)           # 판정에 쓴 입력 값 (fields.yaml 이름)
    estimated_price: Mapped[int | None] = mapped_column(Integer)
    deposit_ratio: Mapped[float | None] = mapped_column(Float)
    ratio_is_minimum: Mapped[bool] = mapped_column(Boolean, default=False)  # 등기부 전 최소 추정치

    level: Mapped[str] = mapped_column(String(32))           # verdict.yaml levels[].id
    matched_rules: Mapped[list] = mapped_column(JSONType)    # 걸린 규칙 [{id, label, level, linkage}]
    linkages: Mapped[list] = mapped_column(JSONType)         # linkage.yaml id 목록
    unchecked: Mapped[list] = mapped_column(JSONType)        # 확인 못 한 항목 (FR-010)
    rules_version: Mapped[str] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contract: Mapped[Contract | None] = relationship(back_populates="verdicts")


class Todo(Base):
    """계약별 할 일 (todos.yaml의 T1~T9, 추가 할 일 X-*)."""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    rule_id: Mapped[str] = mapped_column(String(32))         # T1, T2, ..., X-LANDLORD-PLAN
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="todo")   # todo / done / skipped
    done_date: Mapped[date | None] = mapped_column(Date)
    evidence_path: Mapped[str | None] = mapped_column(String(500))     # 기록함 증빙 사진

    contract: Mapped[Contract] = relationship(back_populates="todos")


class Alert(Base):
    """역전세 경보 계산 이력 (FR-036, FR-037)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    level: Mapped[str | None] = mapped_column(String(16))    # caution / warning / danger, 해당 없으면 None
    estimated_price: Mapped[int] = mapped_column(Integer)
    deposit_ratio: Mapped[float] = mapped_column(Float)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)   # 계산에 쓴 공시가격·실거래가·기준일
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contract: Mapped[Contract] = relationship(back_populates="alerts")
