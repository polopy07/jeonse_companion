"""등기부 재비교: 계약 당일·잔금일에 다시 올린 등기부 요약을 계약 전 확인 때와 항목별로 비교한다 (FR-023, FR-048, UC-006).

항목마다 그대로(same) / 위험해짐(risk: 새로 생기거나 늘어남) / 줄어듦(eased: 없어지거나 줄어듦)으로 나눈다.
위험해진 항목이 하나라도 있으면 계약 당일은 "계약 보류 후 상담", 잔금일은 "잔금 보류 후 상담"을 안내한다.
근저당이 말소되거나 줄어든 것은 변동으로 보여 주되 보류는 안내하지 않는다 (잔금 때 말소하기로 한 근저당 등).
계약 전 확인에서 등기부를 올리지 않았으면 앞 값은 None이고, 다시 올린 등기부에 있는 것은 모두 위험으로 본다.
"""
from dataclasses import dataclass, field

STAGE_LABEL = {"contract_day": "계약 당일", "balance_day": "잔금일"}
HOLD_ADVICE = {"contract_day": "계약 보류 후 상담", "balance_day": "잔금 보류 후 상담"}
HOLD_HINT = "계약 전 확인 뒤 등기부가 바뀌었습니다. {action}하고 공인중개사·임대인에게 바뀐 이유를 확인한 뒤 공공 상담 창구에 문의하세요"

# (항목 이름, 화면 이름, 종류). flag는 있음/없음, amount는 금액(원)
ITEMS = [
    ("registry.seizure", "압류·가압류·경매", "flag"),
    ("registry.mortgage", "근저당", "flag"),
    ("registry.mortgage_amount", "근저당 채권최고액 합계", "amount"),
    ("registry.lease_amount", "임차권·전세권 보증금 합계", "amount"),
    ("registry.trust", "신탁", "flag"),
]


@dataclass
class CompareItem:
    field: str
    label: str
    before: bool | int | None   # 계약 전 확인 때 값 (등기부를 올리지 않았으면 None)
    after: bool | int
    change: str                 # same / risk / eased


@dataclass
class CompareResult:
    items: list[CompareItem]
    changed: bool               # 바뀐 항목이 있는지 (줄어든 것 포함)
    hold: bool                  # 위험해진 항목이 있어 보류를 안내하는지
    advice: str | None          # "계약 보류 후 상담" / "잔금 보류 후 상담"
    hint: str | None
    mortgage_check_required: bool   # 계약 전에 근저당이 있었으면 근저당 금액 비교가 필수 (FR-023, L-MORTGAGE)
    baseline_missing: bool      # 계약 전 확인에서 등기부를 올리지 않음
    risk_labels: list[str] = field(default_factory=list)


def _change(kind: str, before, after) -> str:
    if before is None:   # 비교할 앞 값이 없으면 있는 것은 위험으로
        return "risk" if (after if kind == "flag" else after > 0) else "same"
    if before == after:
        return "same"
    if kind == "flag":
        return "risk" if after else "eased"
    return "risk" if after > before else "eased"


def compare_registry(before: dict, after: dict, stage: str) -> CompareResult:
    """before: 계약 전 확인 판정 입력(fields.yaml 이름). after: 다시 올린 등기부 {registry.* 값}. stage: contract_day / balance_day."""
    baseline_missing = before.get("registry.mortgage") is None
    items = []
    for name, label, kind in ITEMS:
        old = None if baseline_missing else before.get(name) or (False if kind == "flag" else 0)
        new = after.get(name) or (False if kind == "flag" else 0)
        items.append(CompareItem(name, label, old, new, _change(kind, old, new)))
    risks = [i.label for i in items if i.change == "risk"]
    hold = bool(risks)
    action = HOLD_ADVICE[stage]
    return CompareResult(
        items=items,
        changed=any(i.change != "same" for i in items),
        hold=hold,
        advice=action if hold else None,
        hint=HOLD_HINT.format(action=action.removesuffix(" 후 상담")) if hold else None,
        mortgage_check_required=bool(before.get("registry.mortgage")),
        baseline_missing=baseline_missing,
        risk_labels=risks,
    )
