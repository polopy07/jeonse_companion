"""데이터 모델: 계약, 할 일, 판정, 경보 (명세서 DATA-05 등).

필드 이름은 rules/fields.yaml과 맞춘다 (점(.)은 밑줄로 바꿈).
"""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# PostgreSQL에서는 JSONB, SQLite에서는 JSON
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Contract(Base):
    """계약 1건. 계약 당일 체크에서 날짜·조건을 입력하면 만든다 (FR-014)."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 패키지를 시작한 판정(verdicts.id). 한 판정으로 계약 1개만 만들도록 DB가 막는다 (동시 요청 대비).
    # verdicts.contract_id와 서로 가리키므로 외래 키는 걸지 않는다
    check_id: Mapped[int] = mapped_column(Integer, unique=True)
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
    email: Mapped[str | None] = mapped_column(String(254))   # 알림 이메일 (FR-014, NFR-011 회원 식별도 이메일만)

    # 특약별 넣음/거절당함 {"S-NO-MORTGAGE": "rejected", ...} (FR-049)
    special_term_result: Mapped[dict] = mapped_column(JSONType, default=dict)
    # 만들 때의 규칙으로 정해 저장한다. 할 일과 같은 시점 기준이라, 규칙이 바뀌어도 한 응답 안에서 어긋나지 않는다
    report_required: Mapped[bool] = mapped_column(Boolean, default=True)   # 임대차 신고 대상 (FR-015)
    alert_level: Mapped[str | None] = mapped_column(String(16))            # 시작할 때의 경보 단계 (정상이면 null)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    todos: Mapped[list["Todo"]] = relationship(back_populates="contract", cascade="all, delete-orphan",
                                               order_by="Todo.sort_order")
    # 패키지를 시작한 판정(check_id)과 계약 당일·잔금일 재비교 판정 (FR-048, FR-023)
    verdicts: Mapped[list["Verdict"]] = relationship(back_populates="contract", order_by="Verdict.id")
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
    # 단지를 주었을 때 실거래 근거 {as_of, trade_basis, nearby_jeonse} (FR-003, FR-004). 기준일을 함께 남긴다 (NFR-014)
    market: Mapped[dict] = mapped_column(JSONType, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contract: Mapped[Contract | None] = relationship(back_populates="verdicts")


class Todo(Base):
    """계약별 할 일 (todos.yaml의 T1~T9, 추가 할 일 X-*). 종류·기한·상태·선행 조건·근거를 저장한다 (FR-017)."""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    rule_id: Mapped[str] = mapped_column(String(32))         # T1, T2, ..., X-LANDLORD-PLAN
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(String(500))          # 보증기관·직거래·갱신 계약 등 조건별 안내 (FR-018)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    remind_date: Mapped[date | None] = mapped_column(Date)            # 재알림(T6, T8)은 기한 대신 알림일
    prerequisites: Mapped[list] = mapped_column(JSONType, default=list)     # 먼저 끝내야 하는 할 일 rule_id (FR-020)
    required_checks: Mapped[list] = mapped_column(JSONType, default=list)   # 연동 규칙이 붙인 필수 확인 (FR-022)
    evidence: Mapped[str | None] = mapped_column(String(200))         # 완료 증빙으로 올릴 것
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    moved_to_top: Mapped[bool] = mapped_column(Boolean, default=False)   # 특약 거절·경보로 맨 위에 올림 (FR-019)
    rules_version: Mapped[str] = mapped_column(String(16))
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


class Trade(Base):
    """실거래 1건 (공공데이터포털 API 또는 내려받은 파일, DATA-02, FR-046).

    같은 거래를 다시 받아도 한 번만 저장한다 (deal_key). 받은 날짜(fetched_at)를 같이 둔다.
    """

    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("deal_key", name="uq_trades_deal_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_key: Mapped[str] = mapped_column(String(300))       # 같은 거래인지 가르는 값 (유형·종류·지역·단지·면적·층·날짜·금액)
    housing_type: Mapped[str] = mapped_column(String(32))    # apartment / row_house
    kind: Mapped[str] = mapped_column(String(8))             # trade / rent
    lawd_cd: Mapped[str] = mapped_column(String(5), index=True)
    umd_name: Mapped[str] = mapped_column(String(50))
    jibun: Mapped[str | None] = mapped_column(String(30))
    complex_name: Mapped[str] = mapped_column(String(100))
    exclusive_area: Mapped[float] = mapped_column(Float)
    floor: Mapped[int | None] = mapped_column(Integer)
    deal_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[int | None] = mapped_column(BigInteger)        # 매매가 (원)
    deposit: Mapped[int | None] = mapped_column(BigInteger)      # 보증금 (원)
    monthly_rent: Mapped[int | None] = mapped_column(BigInteger) # 월세 (원)
    build_year: Mapped[int | None] = mapped_column(Integer)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_type: Mapped[str | None] = mapped_column(String(8))   # 전월세: 신규 / 갱신 / null
    source: Mapped[str] = mapped_column(String(8))            # api / file
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
