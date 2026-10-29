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
    """등기부 요약("부동산정보요약" 또는 증명서의 "주요 등기사항 요약") 추출 결과 (사용자 확인값, FR-005)."""

    seizure: bool = False
    mortgage: bool = False
    mortgage_amount: MoneyOrZero = Field(0, description="근저당 채권최고액 합계 (원)")
    lease_amount: MoneyOrZero = Field(
        0, description="을구 임차권·전세권 보증금 합계 (원). 선순위 채권에 넣는다. 이미 돌려받았거나 내 계약이면 확인 화면에서 뺀다")
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


class RegistryLeaseOut(RegistryEntryOut):
    amount: int | None = Field(description="임차보증금·전세금 (원). 읽지 못하면 null")
    holder: str | None = Field(description="임차권자·전세권자")
    same_deposit_as: str | None = Field(
        description="다른 항목과 같은 보증금으로 보고 fields.lease_amount에서 뺐으면 남긴 항목의 순위번호. "
                    "확인 화면은 이 항목을 뺀 상태로 보여 주고, 다른 보증금이면 사용자가 다시 넣는다")


class RegistryFieldsOut(BaseModel):
    """RegistryInput과 같은 이름. 채권최고액을 못 읽으면 mortgage=true, mortgage_amount=0으로 나갈 수 있어 검사는 하지 않는다."""

    seizure: bool
    mortgage: bool
    mortgage_amount: int
    lease_amount: int
    trust: bool


class RegistryParseResult(BaseModel):
    """등기부 요약 추출 결과 (FR-005). 사용자가 확인·수정한 뒤 fields를 CheckInput.registry로 보낸다 (FR-006)."""

    fields: RegistryFieldsOut
    owners: list[str]
    mortgages: list[RegistryMortgageOut]
    leases: list[RegistryLeaseOut] = Field(description="을구 임차권·전세권. 보증금이 fields.lease_amount에 들어 있어 확인 화면에서 항목별로 뺄 수 있게 보여 준다 "
                                                       "(same_deposit_as가 있는 항목은 같은 보증금이라 빠져 있음)")
    seizures: list[RegistryEntryOut]
    trusts: list[RegistryEntryOut]
    others: list[RegistryEntryOut]
    warnings: list[str]


RegistryItemKind = Literal["mortgage", "lease", "seizure", "trust", "other"]


class ExplainItemInput(BaseModel):
    """설명할 등기 항목 1개. 이름·원문 글자·주소는 받지 않는다 (LLM에 보내지 않게, AI-REQ-05)."""

    id: str = Field(min_length=1, max_length=40, description="화면에서 항목을 찾는 값 (예: 순위번호). 응답에 그대로 돌려준다")
    kind: RegistryItemKind = Field(description="mortgages→mortgage, leases→lease, seizures→seizure, trusts→trust, others→other")
    purpose: str = Field(min_length=1, max_length=30, description="등기 목적 (예: 근저당권설정, 주택임차권). 권리자 이름은 넣지 않는다")
    amount: int | None = Field(None, ge=0, description="채권최고액·보증금 (원). 사용자가 확인한 값")


class ExplainInput(BaseModel):
    """등기 항목 쉬운 말 설명 요청 (FR-007). POST /api/registry/parse 결과를 사용자가 확인한 뒤 보낸다."""

    items: list[ExplainItemInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError("항목 id가 겹칩니다")
        return self


class ExplanationOut(BaseModel):
    id: str
    kind: RegistryItemKind
    text: str = Field(description="쉬운 말 설명")
    source: Literal["llm", "template"] = Field(
        description="llm(LLM이 쓰고 금지 표현·숫자 검사를 통과) / template(LLM 꺼짐·실패·검사 탈락, rules/explain.yaml)")


class ExplainResult(BaseModel):
    explanations: list[ExplanationOut] = Field(description="보낸 순서대로")
    disclaimer: str = Field(description="결과 화면 공통 문구 (verdict.yaml display.disclaimer)")


RegistryStage = Literal["contract_day", "balance_day"]


class RegistryCompareInput(BaseModel):
    """계약 당일·잔금일에 다시 올린 등기부 요약 (FR-023, FR-048, UC-006). POST /api/registry/parse 결과를 확인·수정한 fields."""

    registry: RegistryInput
    stage: RegistryStage | None = Field(
        None, description="contract_day 계약 당일 / balance_day 잔금일. 비우면 오늘(가상 날짜)이 계약일까지면 계약 당일, 계약 다음 날부터는 잔금일")


class RegistryCompareItemOut(BaseModel):
    field: str = Field(description="fields.yaml 이름 (registry.seizure 등)")
    label: str
    before: bool | int | None = Field(description="계약 전 확인 때 값. 그때 등기부를 올리지 않았으면 null")
    after: bool | int = Field(description="다시 올린 등기부 값")
    change: Literal["same", "risk", "eased"] = Field(description="same 그대로 / risk 새로 생기거나 늘어남 / eased 없어지거나 줄어듦")


class RegistryCompareOut(BaseModel):
    """등기부 재비교 결과 (FR-023, FR-048). 다시 판정한 결과는 계약의 판정 기록으로 남는다 (경보 재계산의 선순위 채권도 이 등기부)."""

    id: int = Field(description="재비교로 다시 판정한 결과 id (verdicts.id)")
    contract_id: int
    stage: RegistryStage
    compared_on: date = Field(description="비교한 날 (가상 날짜면 그날)")
    baseline_check_id: int = Field(description="비교 기준인 계약 전 확인 판정 (계약의 check_id)")
    items: list[RegistryCompareItemOut]
    changed: bool = Field(description="바뀐 항목이 있는지 (줄어든 것 포함)")
    hold: bool = Field(description="새로 생기거나 늘어난 항목이 있어 보류를 안내하는지")
    advice: str | None = Field(description="hold일 때 \"계약 보류 후 상담\" / \"잔금 보류 후 상담\"")
    hint: str | None = Field(description="hold일 때 할 일 안내, 화면에 그대로")
    mortgage_check_required: bool = Field(description="계약 전에 근저당이 있었으면 true: 근저당 금액 비교가 필수 확인 (FR-023, L-MORTGAGE)")
    mortgage_check: RegistryCompareItemOut | None = Field(description="mortgage_check_required면 채권최고액 비교 항목")
    baseline_missing: bool = Field(description="계약 전 확인에서 등기부를 올리지 않아 다시 올린 등기부에 있는 것을 모두 위험으로 봄")
    level_before: str = Field(description="계약 전 확인 판정 단계 (verdict.yaml levels[].id)")
    level_after: str = Field(description="계약 전 확인 입력에 등기부만 바꿔 다시 판정한 단계 (달라지면 등기부 때문)")
    level_after_label: str
    deposit_ratio_before: float | None
    deposit_ratio_after: float | None = Field(
        description="다시 판정한 내 보증금 비율. 계약 전 확인 때 보증금·공시가격 기준이고, 계약의 지금 값은 경보(alert_level)에 반영")


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
    contract_id: int | None = Field(description="이 판정으로 만든 계약 id (POST /api/contracts). 아직 없으면 null")


class TodoRefOut(BaseModel):
    id: str = Field(description="todos.yaml id")
    title: str


class TermOutcomeOut(BaseModel):
    warnings: list[str] = Field(description="보여 줄 경고")
    documents: list[str] = Field(description="기록함에 남길 서류")
    moves_to_top: list[TodoRefOut] = Field(description="할 일 목록 맨 위로 올라가는 할 일")
    adds_todos: list[TodoRefOut] = Field(description="새로 생기는 할 일 (todos.yaml extra_todos)")
    link_counsel: bool = Field(description="공공 상담 창구 안내를 붙이는지")


class SpecialTermEffectOut(TermOutcomeOut):
    """계약에 기록한 특약 1개의 결과와 분기 (부속표 E, FR-050)."""

    term_id: str = Field(description="special_terms.yaml id")
    label: str
    result: Literal["inserted", "rejected"] = Field(description="inserted(넣음) / rejected(거절당함)")


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
ContractStatus = Literal["active", "cancelled"]


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
    co_tenant_email: str | None = Field(
        None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="공동 계약자 알림 이메일 (FR-043). co_tenant가 true일 때만, 알림 이메일과 다른 주소. 같은 알림 이메일을 "
                    "따로 받고, 이 주소로 접근 링크를 다시 받아 자기 휴대폰에서 같은 계약을 볼 수 있다")
    special_term_result: dict[str, SpecialTermResult] = Field(
        default_factory=dict, description="특약별 넣음/거절당함 (special_terms.yaml의 id가 키)")
    payment_id: int | None = Field(
        None, description="POST /api/checks/{id}/payment의 payment_id. 이 판정의 결제이거나 무산된 계약에서 풀린 결제. "
                          "서버 설정 REQUIRE_CONTRACT_AUTH가 true면 꼭 있어야 한다 (API 명세 1.8)")
    released_contract_token: str | None = Field(
        None, max_length=200,
        description="풀린 결제(released)를 payment_id로 다시 쓸 때만: 그 결제를 썼던 무산된 계약의 access_token "
                    "(API 명세 1.8). 지금 만드는 계약의 토큰이 아니라서 X-Contract-Token 헤더가 아니라 여기로 보낸다")

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.balance_date < self.contract_date:
            raise ValueError("잔금일은 계약일과 같거나 뒤여야 합니다")
        if self.end_date <= self.balance_date:
            raise ValueError("만기일은 잔금일보다 뒤여야 합니다")
        if self.loan_execution_date is not None and not self.loan:
            raise ValueError("전세대출이 없으면 대출 실행일을 비워 두세요")
        if self.co_tenant_email is not None:
            if not self.co_tenant:
                raise ValueError("공동 계약이 아니면 공동 계약자 이메일을 비워 두세요")
            if self.email and self.co_tenant_email.strip().lower() == self.email.strip().lower():
                raise ValueError("공동 계약자 이메일은 알림 이메일과 다른 주소여야 합니다")
        return self


class ContractPatch(BaseModel):
    """계약 조건·특약 결과 변경 (FR-021, FR-049·050). 보낸 칸만 바꾸고 할 일을 다시 계산한다.

    주택 유형·보증금은 판정에서 가져온 값이라 바꾸지 않는다 (보증금이 바뀌면 계약 전 확인부터 다시).
    """

    contract_date: date | None = Field(None, description="계약일")
    balance_date: date | None = Field(None, description="잔금일")
    end_date: date | None = Field(None, description="만기일")
    monthly_rent: MoneyOrZero | None = Field(None, description="월세 (원, 전세면 0)")
    loan: bool | None = Field(None, description="전세대출 유무")
    loan_execution_date: date | None = Field(None, description="대출 실행일. null을 보내면 \"모름\"으로 바꾼다")
    guarantor: Guarantor | None = Field(None, description="보증기관 (미가입은 none)")
    brokered: bool | None = Field(None, description="중개 거래 여부")
    renewal_right_used: bool | None = Field(None, description="계약갱신요구권을 써서 갱신한 계약인지")
    co_tenant: bool | None = Field(None, description="공동 계약자 여부")
    email: str | None = Field(None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                              description="알림 이메일. null을 보내면 지운다")
    co_tenant_email: str | None = Field(None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                                        description="공동 계약자 알림 이메일. null을 보내면 지운다 (공동 계약을 끄려면 함께 지움)")
    special_term_result: dict[str, SpecialTermResult] | None = Field(
        None, description="바꿀 특약만 보낸다 (보내지 않은 특약의 결과는 그대로). 그 판정에서 안내한 특약만 받는다")

    @model_validator(mode="after")
    def no_null_for_required(self):
        # 값이 꼭 있어야 하는 칸에 null을 보내면 막는다 (보내지 않은 칸은 그대로 둔다)
        nullable = {"loan_execution_date", "email", "co_tenant_email"}
        for name in self.model_fields_set - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name}은(는) 비워 둘 수 없습니다")
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
    evidence_uploaded: bool = Field(description="증빙 사진을 올렸는지. 보기는 GET /api/todos/{id}/evidence")
    pinned: bool = Field(description="맨 위 고정 할 일 (T5~T9). 시작일 전이면 화면에서 흐리게")
    moved_to_top: bool = Field(description="특약 거절·경보로 맨 위에 올린 할 일")
    sort_order: int
    status: str = Field(description="todo / done / skipped")
    done_date: date | None = Field(description="끝낸 날 (done·skipped). 뒤 할 일의 기준일")
    rules_version: str
    state: Literal["done", "upcoming", "in_progress", "overdue"] = Field(
        description="오늘(가상 날짜면 그날) 기준: done 끝냄(status skipped 포함) / upcoming 시작 전 / in_progress 할 때 / "
                    "overdue 기한 지남")
    days_left: int | None = Field(description="기한(재알림은 알림일)까지 남은 날. 지났으면 음수, 기한이 없으면 null")


class ContractDocumentOut(BaseModel):
    """첫 계약 서류 한 종류 (FR-051). 올리지 않은 종류도 uploaded: false로 넣는다."""

    kind: str = Field(description="todos.yaml first_documents id (contract 계약서 / down_payment 계약금 이체 내역)")
    label: str
    detail: str | None = Field(description="찍는 방법 안내")
    uploaded: bool = Field(description="올렸는지. 보기는 GET /api/contracts/{id}/documents/{kind}")
    uploaded_at: datetime | None


class ContractOut(BaseModel):
    id: int
    today: date = Field(description="할 일 상태를 계산한 오늘 (X-Virtual-Today를 보냈으면 그날)")
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
    co_tenant_email: str | None = Field(description="공동 계약자 알림 이메일 (FR-043)")
    special_term_result: dict[str, SpecialTermResult]
    report_required: bool = Field(description="임대차 신고 대상인지 (FR-015). 비대상이면 T1 없이 T4에서 확정일자를 함께 받는다")
    alert_level: str | None = Field(
        description="지금 경보 단계 (alert.yaml levels[].id), 정상이면 null. 계약을 시작할 때 정하고 경보 재계산(FR-037)으로 바뀐다")
    status: ContractStatus = Field(description="active / cancelled (계약 무산, FR-016)")
    not_returned_date: date | None = Field(
        description="9번(반환 확인)에서 \"못 받음\"을 고른 날 (FR-024). 반환 대응 중이면 날짜, 아니면 null")
    payment_id: int | None = Field(description="이 계약에 쓴 테스트 결제. 결제 없이 만든 계약이면 null")
    special_term_effects: list[SpecialTermEffectOut] = Field(
        description="기록한 특약 결과의 분기 (부속표 E): 넣음이면 기록함에 남길 서류, 거절당함이면 위험 안내·맨 위로 올라간 할 일·상담 창구")
    todos: list[TodoOut] = Field(description="할 일 목록 (sort_order 순서)")
    documents: list[ContractDocumentOut] = Field(description="첫 계약 서류 (계약서·계약금 이체 내역, FR-051)")


class ContractCreatedOut(ContractOut):
    access_token: str = Field(description="계약 접근 토큰. 이 응답에서 한 번만 준다. 계약 아래 API에 X-Contract-Token 헤더로 보낸다")


class LinkOut(BaseModel):
    label: str
    url: str


class ReturnStepOut(BaseModel):
    """반환 대응 한 단계 (FR-034). 반환 대응을 시작하면 같은 rule_id의 할 일로 붙는다 (끝내기·증빙은 /api/todos/{todo_id})."""

    rule_id: str = Field(description="todos.yaml return_response 단계 id (R1~R4)")
    todo_id: int | None = Field(description="이 단계의 할 일 id. 반환 대응을 시작하기 전(preview)이면 null")
    title: str
    detail: str
    link: LinkOut | None = Field(description="신청·청구 창구 (내용증명, 대법원 전자소송, 보증기관 등)")
    evidence: str | None = Field(description="끝낼 때 올릴 증빙. 없으면 null (공공 상담)")
    state: Literal["done", "current", "todo"] = Field(
        description="done(끝냄, 나중에 올리기 포함) / current(지금 할 단계: 끝내지 않은 첫 단계) / todo")
    done_date: date | None
    evidence_uploaded: bool
    documents: list[str] = Field(description="이 단계에 필요한 서류의 rule_id (documents에서 이름·대조 결과)")
    missing_documents: list[str] = Field(description="이 단계에 필요한데 기록함에 없는 서류 이름 (FR-035)")


class ReturnDocumentOut(BaseModel):
    """청구 서류 대조 한 줄 (FR-035). 서류는 그 할 일의 증빙이다."""

    rule_id: str = Field(description="서류를 올리는 할 일 (T1~T9, R1~R4)")
    todo_id: int | None = Field(description="기록함에 올릴 할 일 id. 반환 대응 시작 전의 R 단계는 null")
    name: str = Field(description="서류 이름 (그 할 일의 증빙)")
    uploaded: bool = Field(description="기록함에 올렸는지. 나중에 올리기(skipped)는 false")
    needed_by: list[str] = Field(description="이 서류가 필요한 단계 rule_id")


class ReturnGuideOut(BaseModel):
    """반환 대응 안내 (UI-08, FR-024·034·035). 일반 절차 안내이며 개별 법률 판단이 아니다."""

    contract_id: int
    today: date
    status: Literal["preview", "in_progress", "ended"] = Field(
        description="preview(아직 \"못 받음\"을 고르지 않음, 미리 점검) / in_progress(반환 대응 중) / "
                    "ended(반환 대응 중 9번 반환 확인을 끝냄)")
    end_date: date
    not_returned_date: date | None = Field(description="\"못 받음\"을 고른 날. preview면 null")
    guarantor: Guarantor
    steps: list[ReturnStepOut] = Field(description="단계 순서대로 (반환 요청 기록 → 내용증명 → 임차권등기명령 → 청구·상담)")
    documents: list[ReturnDocumentOut] = Field(description="청구 서류 대조. 이 계약에 없는 할 일의 서류는 빠진다")
    missing_count: int = Field(description="기록함에 없는 서류 수")
    help_desks: list[LinkOut] = Field(description="공공 상담 창구")
    disclaimer: str
    rules_version: str = Field(description="todos.yaml version")


PaymentProduct = Literal["package", "todo_only"]


class PaymentOut(BaseModel):
    """테스트 결제 (FR-013). 실제 돈은 나가지 않는다."""

    payment_id: int
    check_id: int
    product: PaymentProduct = Field(description="package(전동기 패키지) / todo_only(다가구·단독 할 일 관리만)")
    amount: int = Field(description="금액 (원). 판정 단계로 서버가 정한다")
    method: Literal["test"] = Field(description="결제 수단. MVP는 test만")
    status: Literal["paid", "used", "released"] = Field(
        description="paid(결제함) / used(계약에 씀) / released(계약 무산으로 풀림, 다음 계약에 다시 씀)")


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


class DemoContractDay(BaseModel):
    """시연 장면의 계약 날짜와 특약 결과. 그대로 POST /api/contracts에 넣는다."""

    contract_date: date
    balance_date: date
    end_date: date
    special_term_result: dict[str, SpecialTermResult]


class DemoHouseOut(BaseModel):
    """시연 집 1채 (docs/validation/demo_houses.yaml, 경보계산_정답표.md)."""

    id: str
    title: str
    address: str = Field(description="단지 주소와 면적·층대. 어느 세대인지는 적지 않는다")
    official_price_source: str = Field(description="공시가격 출처")
    input: CheckInput = Field(description="계약 전 확인 입력값. 그대로 POST /api/checks로 보낸다")
    registry: RegistryParseResult = Field(
        description="시연 등기부를 읽은 결과 (POST /api/registry/parse와 같은 형식). 이름·주소는 가린 값이다")
    virtual: list[str] = Field(description="실제 자료가 아닌 시연용 가상 값. 화면과 발표 자료에 \"시연용 가상\"으로 표시한다")
    contract_day: DemoContractDay | None = Field(description="계약 당일 시연 장면. 없으면 계약 전 확인까지만 보여 주는 집")


class DemoHousesResult(BaseModel):
    as_of: date = Field(description="정답표 기대값의 실거래 기준일. 같은 결과를 보려면 실거래 저장본을 넣고 X-Virtual-Today에 이 날짜를 보낸다")
    houses: list[DemoHouseOut]


class AccessLinkInput(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                       description="계약을 만들 때 넣은 알림 이메일 또는 공동 계약자 이메일")


class AccessLinkResult(BaseModel):
    message: str = Field(description="이메일이 있든 없든 같은 문구 (계약이 있는지 알아내지 못하게)")


date_ = date   # 필드 이름 date와 겹치지 않게 쓰는 별칭


class NotificationRunInput(BaseModel):
    date: date_ | None = Field(None, description="이 날을 오늘로 보고 알림을 만든다 (가상 날짜). 없으면 X-Virtual-Today, 그것도 없으면 실제 오늘")


class NotificationOut(BaseModel):
    contract_id: int
    todo_rule_id: str
    kind: Literal["start", "due_before", "remind", "evidence"] = Field(
        description="start 시작일 / due_before 기한 며칠 전 / remind 재알림 / evidence 나중에 올리기 한 증빙을 올리라는 알림")
    notify_date: date_
    channel: Literal["app", "email", "email_co"] = Field(description="app / email(계약 이메일) / email_co(공동 계약자 이메일)")
    status: Literal["sent", "pending", "failed", "skipped"] = Field(
        description="app은 sent. email은 sent(보냄) / failed(못 보냄, 다음 실행에서 다시) / skipped(알림 이메일 없음·그사이 무산·완료)")
    title: str


class NotificationRunResult(BaseModel):
    date: date_
    email_sent: int = Field(description="이번 실행에서 보낸 이메일 수 (앞서 실패한 것 다시 보낸 것 포함)")
    email_failed: int = Field(description="보내지 못한 이메일 수. 다음 실행에서 3번까지 다시 보낸다")
    created: list[NotificationOut] = Field(description="이번 실행에서 새로 만든 알림. 이미 만든 알림은 다시 만들지 않는다")


class MoveInput(BaseModel):
    """갈아타기: 다음 집 계약 조건 (FR-025, UI-07). 만기 6개월 전 할 일(7번)에서 "이사할게요"를 고르면 입력한다.

    다음 집 계약 전 확인(POST /api/checks)은 따로 한다 (FR-028). 여기서는 날짜·돈으로 자금 틈과 할 일만 계산한다.
    """

    contract_date: date = Field(description="다음 집 계약일")
    balance_date: date = Field(description="다음 집 잔금일")
    end_date: date = Field(description="다음 집 만기일")
    deposit: Money = Field(description="다음 집 보증금 (원)")
    down_payment: MoneyOrZero = Field(description="다음 집 계약금 (원). 잔금 = 보증금 − 계약금")
    monthly_rent: MoneyOrZero = Field(0, description="월세 (원, 전세면 0)")
    loan: bool = Field(False, description="다음 집 전세대출 유무")
    loan_execution_date: date | None = Field(None, description="다음 집 대출 실행일, 모르면 비워 둠 (잔금일로 본다)")
    guarantor: Guarantor = Field("none", description="다음 집 보증기관 (미가입은 none)")
    brokered: bool = Field(True, description="중개 거래 여부")
    renewal_right_used: bool = Field(False, description="계약갱신요구권을 써서 갱신한 계약인지")
    move_in_date: date | None = Field(None, description="다음 집 전입 예정일. 없으면 잔금일")

    @model_validator(mode="after")
    def dates_and_money(self):
        if self.balance_date < self.contract_date:
            raise ValueError("잔금일은 계약일과 같거나 뒤여야 합니다")
        if self.end_date <= self.balance_date:
            raise ValueError("만기일은 잔금일보다 뒤여야 합니다")
        if self.down_payment >= self.deposit:
            raise ValueError("계약금은 보증금보다 적어야 합니다")
        if self.move_in_date is not None and self.move_in_date < self.balance_date:
            raise ValueError("전입 예정일은 잔금일과 같거나 뒤여야 합니다")
        if self.loan_execution_date is not None and not self.loan:
            raise ValueError("전세대출이 없으면 대출 실행일을 비워 두세요")
        # 새 대출은 다음 집 잔금을 치르는 돈이라 계약일과 잔금일 사이 (틀린 날짜로 대출 순서 차이가 수백 일이 되지 않게)
        if self.loan_execution_date is not None and not self.contract_date <= self.loan_execution_date <= self.balance_date:
            raise ValueError("대출 실행일은 다음 집 계약일과 잔금일 사이여야 합니다")
        return self


class MoveTodoOut(BaseModel):
    """지금 집과 다음 집 할 일을 하나로 묶은 목록의 한 줄 (FR-025)."""

    house: Literal["current", "next"] = Field(description="current 지금 집 / next 다음 집")
    rule_id: str = Field(description="todos.yaml id (T1~T9)")
    title: str
    start_date: date | None
    due_date: date | None
    remind_date: date | None
    state: Literal["done", "upcoming", "in_progress", "overdue"] = Field(description="오늘 기준 상태 (TodoOut.state와 같음)")
    days_left: int | None


class MoveOut(BaseModel):
    contract_id: int = Field(description="지금 계약 id")
    today: date = Field(description="계산한 오늘 (X-Virtual-Today를 보냈으면 그날)")
    decided_on: date = Field(description="갈아타기를 처음 저장한 날")
    next: MoveInput = Field(description="저장한 다음 집 입력")
    current_deposit: int = Field(description="지금 집 보증금 (원)")
    return_date: date = Field(description="지금 집 보증금 반환 예정일 (9번 할 일 기한, 없으면 만기일)")
    returned: bool = Field(description="지금 집 반환 확인(9번 할 일)을 끝냈는지")
    next_balance: int = Field(description="다음 집 잔금 = 보증금 − 계약금 (원)")
    gap_days: int = Field(description="반환 예정일이 다음 집 잔금일보다 늦은 일수. 늦지 않으면 0")
    gap_amount: int = Field(description="그동안 비는 금액 = min(지금 집 보증금, 다음 집 잔금). 틈이 없으면 0 (PO 결정 Q5)")
    loan_order: Literal["new_loan_first", "old_repayment_first"] | None = Field(
        description="두 집 모두 전세대출일 때: new_loan_first 새 대출 실행이 기존 대출 상환보다 먼저 / "
                    "old_repayment_first 기존 대출 상환 뒤 새 대출. 아니면 null")
    loan_gap_days: int | None = Field(description="새 대출 실행이 기존 대출 상환보다 먼저인 일수")
    move_in_date: date = Field(description="다음 집 전입 예정일 (입력이 없으면 잔금일)")
    move_in_warning: bool = Field(description="전입 예정일이 반환 예정일과 같거나 앞서면 true (반환 확인을 끝냈으면 false, FR-027)")
    next_contract_id: int | None = Field(
        None, description="다음 집으로 만든 계약 (POST .../move/next로 연결). 연결하면 그 계약의 전입신고를 끝낼 때 경고한다")
    warnings: list[str] = Field(description="화면에 그대로 보여 줄 안내 (자금 틈·대출 순서·전입 순서)")
    next_todos: list[MoveTodoOut] = Field(description="다음 집 할 일 9종 (다음 집 날짜로 계산, 할 일 순서대로). "
                                                       "다음 집 계약 전 확인의 연동 규칙·특약은 계약을 만들 때 반영된다")
    todos: list[MoveTodoOut] = Field(description="지금 집 + 다음 집 할 일을 날짜순으로 묶은 목록 (FR-025)")


class CalendarLinkOut(BaseModel):
    """캘린더 구독 주소 (FR-042, #47). 이 응답에서 한 번만 준다 (서버에는 토큰 해시만)."""

    url: str = Field(description="https 구독 주소 (구글 캘린더 \"URL로 추가\"에 넣음)")
    webcal_url: str = Field(description="webcal:// 주소 (휴대폰에서 열면 캘린더 앱이 구독을 묻는다)")
    created_at: datetime


class MoveLinkInput(BaseModel):
    """갈아타기에 다음 집 계약 연결 (FR-027). 다음 집 계약을 만든 휴대폰이 그 계약의 접근 토큰을 함께 보낸다."""

    next_contract_id: int
    next_contract_token: str = Field(min_length=1, description="다음 집 계약을 만들 때 받은 access_token")


class TodoPatch(BaseModel):
    """할 일 완료·나중에 올리기·되돌리기 (FR-020, FR-029·030, UI-04)."""

    status: Literal["done", "skipped", "todo"] = Field(
        description="done 완료(증빙을 올린 할 일만) / skipped 나중에 올리기(완료 처리, 기록함은 빈칸) / todo 되돌리기")
    done_date: date | None = Field(
        None, description="끝낸 날. 없으면 오늘(가상 날짜면 그날). 뒤 할 일의 기준일이 된다 (예: 전입신고 완료 다음 날 → 반환보증 시작)")
    confirm_move_in: bool = Field(
        False, description="갈아타기 다음 집의 전입신고를 지금 집 반환 확인 전에 끝낼 때, 경고(409 MOVE_IN_BEFORE_RETURN)를 "
                           "보고 그래도 끝내면 true (FR-027)")


AlertLevel = Literal["caution", "warning", "danger"]


class AlertBasisOut(BaseModel):
    """경보 계산 근거 (FR-038, UI-09)."""

    as_of: date_ = Field(description="계산 기준일 (실거래 기간·공시가격 기준)")
    official_price: int = Field(description="계산에 쓴 공시가격 (원)")
    official_estimate: int = Field(description="공시가격 × 140% (원)")
    multiplier: float = Field(description="공시가격에 곱한 비율 (alert.yaml estimated_price.official_price_multiplier)")
    trade: TradeBasisOut | None = Field(description="같은 단지·비슷한 면적 매매 실거래. 단지를 모르거나 거래가 없으면 null")
    trade_price_input: int | None = Field(
        None, description="계약 전 확인 때 사용자가 직접 넣은 매매 실거래가 (원). 있으면 판정 때처럼 단지 실거래 대신 이 값을 쓴다")
    nearby_jeonse: NearbyJeonseOut | None = Field(description="주변 전세 시세. 단지를 모르면 null")
    senior_debt: int = Field(description="선순위 채권 (근저당 채권최고액 + 임차권·전세권 보증금, 마지막으로 올린 등기부)")
    ratio_is_minimum: bool = Field(description="등기부를 올리지 않아 선순위 채권을 0원으로 둔 최소 추정치인지")
    complex_known: bool = Field(description="실거래를 찾을 단지를 아는지 (모르면 공시가격으로만 계산)")
    rules_version: str | None = Field(description="재계산에 쓴 alert.yaml 버전. 계약 시작 값은 null")


class AlertPointOut(BaseModel):
    as_of: date_ = Field(description="계산 기준일")
    level: AlertLevel | None = Field(description="경보 단계 (alert.yaml levels[].id), 정상이면 null")
    estimated_price: int = Field(description="추정 주택가격 (원)")
    deposit_ratio: float = Field(description="내 보증금 비율 = (보증금 + 선순위 채권) ÷ 추정 주택가격")


class AlertReportOut(AlertPointOut):
    """최근 역전세 경보 (FR-036~038, UI-09). 재계산한 적이 없으면 계약을 시작할 때(계약 전 확인)의 값."""

    contract_id: int
    label: str | None = Field(description="단계 이름 (주의 / 경고 / 위험), 정상이면 null")
    recalculated: bool = Field(description="계약 중 재계산한 값인지. false면 계약을 시작할 때의 값")
    previous_level: AlertLevel | None = Field(description="바로 앞 계산의 단계. 앞 계산이 없으면 null")
    previous_ratio: float | None = Field(description="바로 앞 계산의 내 보증금 비율. 앞 계산이 없으면 null")
    basis: AlertBasisOut
    history: list[AlertPointOut] = Field(description="계약 시작부터의 계산 이력 (기준일 순서, 마지막이 이 값)")
    data_limits: list[str] = Field(description="데이터 한계 안내 (alert.yaml recalculation.data_limits), 화면에 그대로")


class AlertRecalcInput(BaseModel):
    date: date_ | None = Field(None, description="이 날을 기준일로 다시 계산한다 (가상 날짜). 없으면 X-Virtual-Today, 그것도 없으면 실제 오늘")
    contract_ids: list[int] | None = Field(None, description="이 계약만 다시 계산. 없으면 진행 중 계약 모두")
    official_prices: dict[int, Money] | None = Field(
        None, description="공시가격 새 발표 적재: {계약 id: 새 공시가격(원)}. 계약의 공시가격을 바꾼 뒤 계산한다. 없는 계약 id는 무시")


class AlertRecalcItem(BaseModel):
    contract_id: int
    level: AlertLevel | None
    previous_level: AlertLevel | None = Field(description="앞 계산(없으면 계약 시작)의 단계")
    raised: bool = Field(description="단계가 올라갔는지. 올라가면 앱 안 알림을 만든다")
    estimated_price: int
    deposit_ratio: float


class AlertRecalcResult(BaseModel):
    date: date_
    results: list[AlertRecalcItem] = Field(description="다시 계산한 계약 (공시가격이 없는 계약·무산된 계약은 빠짐)")
