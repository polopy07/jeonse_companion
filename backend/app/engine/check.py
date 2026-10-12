"""계약 전 확인: 입력 → 내 보증금 비율 → 판정."""
from dataclasses import dataclass

from app.engine.price import DepositRatio, deposit_ratio, estimate_price
from app.engine.verdict import NOT_APPLICABLE, VerdictResult, judge
from app.schemas import CheckInput


class MissingInputError(ValueError):
    """계산에 꼭 필요한 입력이 빠졌다. code·hint는 API 오류 응답(docs/api/API_명세.md 1.5절)에 그대로 실린다."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.hint = hint


@dataclass
class CheckOutcome:
    values: dict              # fields.yaml 이름 → 값 (판정에 쓴 그대로 저장)
    ratio: DepositRatio | None
    verdict: VerdictResult


def to_values(inp: CheckInput) -> dict:
    """입력을 규칙 파일의 필드 이름으로 바꾼다."""
    values = {
        "housing_type": inp.housing_type,
        "deposit": inp.deposit,
        "official_price": inp.official_price,
        "exclusive_area": inp.exclusive_area,
        "trust_consent": inp.trust_consent,
        "building.violation": inp.building_violation,
        "guarantor_consult": inp.guarantor_consult,
    }
    if inp.registry is not None:
        values.update({
            "registry.seizure": inp.registry.seizure,
            "registry.mortgage": inp.registry.mortgage,
            "registry.mortgage_amount": inp.registry.mortgage_amount,
            "registry.trust": inp.registry.trust,
        })
    return values


def run_check(inp: CheckInput, rules: dict) -> CheckOutcome:
    values = to_values(inp)

    ratio = None
    if inp.official_price is not None:
        price = estimate_price(inp.official_price, inp.trade_price, rules["alert"])
        ratio = deposit_ratio(inp.deposit, price, values.get("registry.mortgage_amount"), rules["alert"])
        values["estimated_price"] = ratio.estimated_price
        values["deposit_ratio"] = ratio.ratio

    verdict = judge(values, rules["verdict"])

    # 비율 없이 판정하면 비율 규칙(P-2, C-2)이 빠져 "문제 항목 없음"이 잘못 나올 수 있다.
    if ratio is None and verdict.level != NOT_APPLICABLE:
        raise MissingInputError(
            "MISSING_OFFICIAL_PRICE",
            "공시가격이 있어야 내 보증금 비율을 계산할 수 있습니다",
            "공시가격 알리미에서 공동주택 공시가격을 찾아 입력하세요",
        )

    return CheckOutcome(values=values, ratio=ratio, verdict=verdict)
