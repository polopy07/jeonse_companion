"""API 입출력 형식."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

HousingType = Literal["apartment", "row_house", "officetel", "multi_household", "detached"]


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
    mortgage_amount: int = Field(0, ge=0, description="근저당 채권최고액 합계 (원)")
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


class CheckInput(BaseModel):
    """계약 전 확인 입력 (FR-001)."""

    housing_type: HousingType
    deposit: int = Field(gt=0, description="보증금 (원)")
    official_price: int | None = Field(None, gt=0, description="공동주택 공시가격 (원)")
    trade_price: int | None = Field(None, gt=0, description="같은 단지·비슷한 면적 매매 실거래가 (원)")
    exclusive_area: float | None = Field(None, gt=0, description="전용면적 (㎡)")
    registry: RegistryInput | None = Field(None, description="등기부를 올리기 전이면 비워 둠")
    trust_consent: Literal["unknown", "obtained", "unavailable"] = "unknown"
    building_violation: bool | None = Field(None, description="건축물대장 위반건축물 여부, 모르면 비워 둠")
    guarantor_consult: Literal["not_yet", "possible", "impossible"] = "not_yet"


class MatchedRuleOut(BaseModel):
    id: str
    label: str
    level: str
    linkage: str | None = None


class UncheckedItemOut(BaseModel):
    id: str
    label: str
    linkage: str | None = None


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
    monthly_rent: int = Field(0, ge=0, description="월세 (원, 전세면 0)")
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
