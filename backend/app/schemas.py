"""API 입출력 형식."""
from datetime import date
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
