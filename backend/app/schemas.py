"""API 입출력 형식."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

HousingType = Literal["apartment", "row_house", "officetel", "multi_household", "detached"]


# 금액 입력 상한 1조 원. 이보다 크면 DB(BigInteger)에 닿기 전에 422로 막는다
MONEY_MAX = 10**12

# 금액 입력 필드는 이 타입을 쓴다 (상한을 빠뜨리지 않게)
Money = Annotated[int, Field(gt=0, le=MONEY_MAX)]          # 0원은 안 됨 (보증금·공시가격 등)
MoneyOrZero = Annotated[int, Field(ge=0, le=MONEY_MAX)]    # 0원 허용 (월세·채권최고액)


class ErrorField(BaseModel):
    field: str
    message: str


class ErrorDetail(BaseModel):
    code: str = Field(description="화면 분기용 고정 코드 (docs/api/API_명세.md 1.5절)")
    message: str = Field(description="사용자에게 보여 줄 문장")
    hint: str | None = Field(None, description="다음에 할 일 안내")
    fields: list[ErrorField] = Field(default_factory=list, description="입력 형식 오류일 때 필드별 문제")


class ErrorResponse(BaseModel):
    """모든 오류 응답의 형식."""

    detail: ErrorDetail


class RegistryInput(BaseModel):
    """등기부 "주요 등기사항 요약" 추출 결과 (사용자 확인값, FR-005)."""

    seizure: bool = False
    mortgage: bool = False
    mortgage_amount: MoneyOrZero = Field(0, description="근저당 채권최고액 합계 (원)")
    trust: bool = False

    @model_validator(mode="after")
    def mortgage_needs_amount(self):
        if self.mortgage and self.mortgage_amount <= 0:
            raise ValueError("근저당이 있으면 채권최고액 합계를 입력해야 합니다")
        return self


class RegistryEntryOut(BaseModel):
    rank: str
    purpose: str
    text: str


class RegistryMortgageOut(RegistryEntryOut):
    amount: int | None
    holder: str | None


class RegistryFieldsOut(BaseModel):
    """RegistryInput과 같은 이름. 채권최고액을 못 읽으면 mortgage=true, mortgage_amount=0으로 나갈 수 있어 검사는 하지 않는다."""

    seizure: bool
    mortgage: bool
    mortgage_amount: int
    trust: bool


class RegistryParseResult(BaseModel):
    """등기부 요약 추출 결과 (FR-005). 사용자가 확인·수정한 뒤 fields를 CheckInput.registry로 보낸다 (FR-006)."""

    fields: RegistryFieldsOut
    owners: list[str]
    mortgages: list[RegistryMortgageOut]
    seizures: list[RegistryEntryOut]
    trusts: list[RegistryEntryOut]
    others: list[RegistryEntryOut]
    warnings: list[str]


class ComplexInput(BaseModel):
    """실거래를 찾을 단지 (공공데이터포털 실거래가의 이름 그대로). 시연 집은 미리 매칭해 둔다."""

    lawd_cd: str = Field(pattern=r"^\d{5}$", description="법정동 시군구 코드 5자리")
    umd_name: str = Field(min_length=1, description="법정동 이름 (예: 광안동)")
    complex_name: str = Field(min_length=1, description="단지 이름 (아파트명·연립다세대명)")
    jibun: str | None = Field(None, description="지번. 연립다세대는 같은 이름이 많아 필수")


class CheckInput(BaseModel):
    """계약 전 확인 입력 (FR-001)."""

    housing_type: HousingType
    deposit: Money = Field(description="보증금 (원)")
    official_price: Money | None = Field(None, description="공동주택 공시가격 (원)")
    trade_price: Money | None = Field(None, description="같은 단지·비슷한 면적 매매 실거래가 (원)")
    exclusive_area: float | None = Field(None, gt=0, description="전용면적 (㎡)")
    registry: RegistryInput | None = Field(None, description="등기부를 올리기 전이면 비워 둠")
    trust_consent: Literal["unknown", "obtained", "unavailable"] = "unknown"
    building_violation: bool | None = Field(None, description="건축물대장 위반건축물 여부, 모르면 비워 둠")
    guarantor_consult: Literal["not_yet", "possible", "impossible"] = "not_yet"
    complex: ComplexInput | None = Field(
        None, description="주면 저장된 실거래에서 매매 실거래가(trade_price를 비워 둔 경우)와 주변 전세 시세를 찾는다. exclusive_area 필요")

    @model_validator(mode="after")
    def complex_needs_area(self):
        if self.complex is not None:
            if self.housing_type not in ("apartment", "row_house"):
                raise ValueError("실거래 단지 조회는 아파트·연립다세대만 됩니다")
            if self.exclusive_area is None:
                raise ValueError("단지로 실거래를 찾으려면 전용면적을 입력해야 합니다")
            if self.housing_type == "row_house" and not self.complex.jibun:
                raise ValueError("연립다세대는 지번을 입력해야 실거래를 찾을 수 있습니다")
        return self


class TradeBasisOut(BaseModel):
    """추정 주택가격에 쓴 매매 실거래 (같은 단지·비슷한 면적, 가장 최근 거래)."""

    price: int
    deal_date: date
    exclusive_area: float
    sample_count: int = Field(description="기간 안 같은 단지·비슷한 면적 매매 건수")
    used: bool = Field(description="공시가격 × 140%보다 낮아 추정 주택가격으로 썼는지")


class NearbyJeonseOut(BaseModel):
    """주변 전세 시세 (FR-004). 같은 단지·비슷한 면적의 최근 전세 거래 중앙값."""

    median: int | None = Field(description="표본 부족이면 null")
    sample_count: int
    low_sample: bool = Field(description="3건 미만이면 true (\"표본 부족\")")
    below_deposit: bool | None = Field(description="중앙값이 내 보증금보다 낮은지 (경보 주의 조건). 표본 부족이면 null")


class MatchedRuleOut(BaseModel):
    id: str
    label: str
    level: str
    linkage: str | None = None
    explanation: str | None = Field(None, description="걸린 항목의 쉬운 말 설명 (verdict.yaml). 규칙 v1.0 때 저장한 판정은 null")


class UncheckedItemOut(BaseModel):
    id: str
    label: str
    linkage: str | None = None
    guide: str | None = Field(None, description="직접 확인하는 방법 (verdict.yaml). 규칙 v1.0 때 저장한 판정은 null")


class CheckResult(BaseModel):
    id: int
    level: str
    label: str
    next_step: str
    block_payment: bool
    estimated_price: int | None
    deposit_ratio: float | None
    ratio_is_minimum: bool
    matched: list[MatchedRuleOut]
    linkages: list[str]
    unchecked: list[UncheckedItemOut]
    disclaimer: str
    rules_version: str
    as_of: date | None = Field(description="실거래를 볼 때 쓴 기준일 (X-Virtual-Today가 있으면 그날). 단지를 주지 않았으면 null")
    trade_basis: TradeBasisOut | None = Field(description="단지를 주고 매매 실거래를 찾았을 때만")
    nearby_jeonse: NearbyJeonseOut | None = Field(description="단지를 주었을 때만")


class TodoRefOut(BaseModel):
    id: str = Field(description="todos.yaml id")
    title: str


class TermOutcomeOut(BaseModel):
    warnings: list[str] = Field(description="보여 줄 경고")
    documents: list[str] = Field(description="기록함에 남길 서류")
    moves_to_top: list[TodoRefOut] = Field(description="할 일 목록 맨 위로 올라가는 할 일")
    adds_todos: list[TodoRefOut] = Field(description="새로 생기는 할 일 (todos.yaml extra_todos)")
    link_counsel: bool = Field(description="공공 상담 창구 안내를 붙이는지")


class LinkedRuleOut(BaseModel):
    id: str = Field(description="linkage.yaml id")
    label: str


class SpecialTermOut(BaseModel):
    id: str = Field(description="special_terms.yaml id. POST /api/contracts의 special_term_result 키")
    label: str
    text: str = Field(description="계약서에 옮겨 적을 특약 문구 (복사용)")
    source: str = Field(description="문구 출처")
    linked: list[LinkedRuleOut] = Field(description="이 특약을 보여 주게 한 연동 규칙 (판정에 걸린 항목)")
    if_inserted: TermOutcomeOut = Field(description="\"넣음\"을 고르면 생기는 것")
    if_rejected: TermOutcomeOut = Field(description="\"거절당함\"을 고르면 생기는 것")


class SpecialTermsResult(BaseModel):
    """계약 당일 특약 예시 (FR-039). 공공 자료가 안내하는 예시이며 추천이 아니다."""

    check_id: int
    level: str = Field(description="판정 단계 (verdict.yaml levels[].id)")
    terms: list[SpecialTermOut] = Field(description="판정에 맞는 특약 예시. 걸린 연동 규칙이 없으면 빈 목록")
    warnings: list[str] = Field(description="연동 규칙이 계약 당일에 보여 주는 경고")
    checks: list[str] = Field(description="연동 규칙이 계약 당일에 요구하는 확인 (예: 신탁사 동의서 확인)")
    disclaimer: str
    rules_version: str = Field(description="special_terms.yaml 버전")


Guarantor = Literal["HUG", "HF", "SGI", "none"]
SpecialTermResult = Literal["inserted", "rejected"]


class ContractInput(BaseModel):
    """패키지 시작·계약 당일 체크에서 입력하는 계약 조건 (FR-014, FR-049).

    주택 유형·보증금·공시가격·전용면적은 check_id의 판정 입력을 그대로 쓴다 (판정과 계약의 보증금이 갈리지 않게).
    """

    check_id: int = Field(description="POST /api/checks로 만든 판정 결과 id")
    contract_date: date = Field(description="계약일")
    balance_date: date = Field(description="잔금일")
    end_date: date = Field(description="만기일")
    monthly_rent: MoneyOrZero = Field(0, description="월세 (원, 전세면 0)")
    loan: bool = Field(False, description="전세대출 유무")
    loan_execution_date: date | None = Field(None, description="대출 실행일, 모르면 비워 둠")
    guarantor: Guarantor = Field("none", description="보증기관 (미가입은 none)")
    brokered: bool = Field(True, description="중개 거래 여부 (직거래면 false)")
    renewal_right_used: bool = Field(False, description="계약갱신요구권을 써서 갱신한 계약인지")
    co_tenant: bool = Field(False, description="공동 계약자(부부) 여부")
    email: str | None = Field(None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="알림 이메일")
    special_term_result: dict[str, SpecialTermResult] = Field(
        default_factory=dict, description="특약별 넣음/거절당함 (special_terms.yaml의 id가 키)")

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.balance_date < self.contract_date:
            raise ValueError("잔금일은 계약일과 같거나 뒤여야 합니다")
        if self.end_date <= self.balance_date:
            raise ValueError("만기일은 잔금일보다 뒤여야 합니다")
        if self.loan_execution_date is not None and not self.loan:
            raise ValueError("전세대출이 없으면 대출 실행일을 비워 두세요")
        return self


class TodoOut(BaseModel):
    """할 일 1개 (todos.yaml의 T1~T9). 목록은 sort_order 순서 (맨 위 규칙 → 고정 → 기한순)."""

    id: int
    rule_id: str = Field(description="todos.yaml id (T1~T9)")
    title: str
    detail: str | None = Field(description="보증기관·직거래·갱신 계약 등에 따라 바뀌는 안내")
    start_date: date | None
    due_date: date | None = Field(description="기한. 기관 기준이 아직 없으면 null (HF·SGI 반환보증)")
    remind_date: date | None = Field(description="재알림(T6, T8)의 알림일. 다른 할 일은 null")
    prerequisites: list[str] = Field(description="먼저 끝내야 하는 할 일 rule_id")
    required_checks: list[str] = Field(description="연동 규칙이 붙인 필수 확인 (예: 근저당 금액 변동 비교)")
    evidence: str | None = Field(description="완료 증빙으로 올릴 것")
    pinned: bool = Field(description="맨 위 고정 할 일 (T5~T9). 시작일 전이면 화면에서 흐리게")
    moved_to_top: bool = Field(description="특약 거절·경보로 맨 위에 올린 할 일")
    sort_order: int
    status: str = Field(description="todo / done / skipped")
    rules_version: str


class ContractOut(BaseModel):
    id: int
    check_id: int
    level: str = Field(description="시작할 때의 판정 단계 (verdict.yaml levels[].id)")
    housing_type: HousingType
    deposit: int
    monthly_rent: int
    exclusive_area: float | None
    official_price: int | None
    contract_date: date
    balance_date: date
    end_date: date
    loan: bool
    loan_execution_date: date | None
    guarantor: Guarantor
    brokered: bool
    renewal_right_used: bool
    co_tenant: bool
    email: str | None
    special_term_result: dict[str, SpecialTermResult]
    report_required: bool = Field(description="임대차 신고 대상인지 (FR-015). 비대상이면 T1 없이 T4에서 확정일자를 함께 받는다")
    alert_level: str | None = Field(description="시작할 때의 경보 단계 (alert.yaml levels[].id), 정상이면 null")
    todos: list[TodoOut] = Field(description="할 일 목록 (sort_order 순서)")


TradeHousingType = Literal["apartment", "row_house"]


class TradeCollectInput(BaseModel):
    """실거래가 수집 (관리자, FR-046). 공공데이터포털 API로 받아 저장한다."""

    lawd_cd: str = Field(pattern=r"^\d{5}$", description="법정동 시군구 코드 5자리 (예: 부산 수영구)")
    end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="마지막 계약년월 YYYY-MM. 이 달부터 거꾸로 months개월")
    months: int = Field(12, ge=1, le=24, description="받을 개월 수")
    housing_types: list[TradeHousingType] = Field(
        default_factory=lambda: ["apartment", "row_house"], min_length=1, description="받을 주택 유형")


class TradeCollectResult(BaseModel):
    lawd_cd: str
    months: list[str] = Field(description="받은 계약년월 YYYYMM (오래된 달부터)")
    received: dict[str, int] = Field(description="\"주택 유형.거래 종류\"별 받은 건수 (apartment.trade 등)")
    added: int = Field(description="새로 저장한 건수. 이미 있던 거래는 다시 저장하지 않는다")
    fetched_at: datetime = Field(description="받은 시각 (기준일 고정 검증용으로 거래와 함께 저장)")
