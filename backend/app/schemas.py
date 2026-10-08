"""API 입출력 형식."""
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
