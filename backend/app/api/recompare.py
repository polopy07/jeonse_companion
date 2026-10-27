"""등기부 재비교: 계약 당일·잔금일 등기부를 다시 올려 계약 전 확인 때와 비교한다 (FR-023, FR-048, UC-006, UI-03).

다시 올린 등기부로 계약 전 확인과 같은 규칙의 판정을 다시 하고, 계약의 판정 기록(contract.verdicts)으로 남긴다.
그래서 역전세 경보 재계산의 선순위 채권도 마지막으로 올린 이 등기부를 쓴다 (app.alerts.senior_debt).
"""
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.contracts import TOKEN_HEADER_DESC, _active, _contract_for
from app.clock import today as today_dep
from app.db import get_db
from app.engine.check import MissingInputError, run_check
from app.engine.registry_compare import compare_registry
from app.errors import api_error, responses
from app.models import Contract, Verdict
from app.rules.loader import get_rules
from app.schemas import CheckInput, RegistryCompareInput, RegistryCompareItemOut, RegistryCompareOut, RegistryInput

router = APIRouter(prefix="/api/contracts", tags=["등기부 재비교"])

# 계약 전 확인 판정 입력에서 그대로 가져오는 것 (재비교는 등기부만 바꾼다)
_KEEP_VALUES = ("nearby_jeonse_median", "nearby_sample_count")


def _recheck_input(row: Contract, check: Verdict, registry: RegistryInput) -> CheckInput:
    """계약 전 확인과 같은 입력에 등기부만 바꾼다. 집 값은 계약의 지금 값(경보 재계산이 공시가격을 바꿀 수 있음)."""
    inputs, market = check.inputs or {}, check.market or {}
    basis = market.get("trade_basis") or {}
    trade = market.get("trade_price_input") or (basis.get("price") if basis.get("used") else None)
    return CheckInput(housing_type=row.housing_type, deposit=row.deposit, official_price=row.official_price,
                      trade_price=trade, exclusive_area=row.exclusive_area, registry=registry,
                      trust_consent=inputs.get("trust_consent") or "unknown",
                      building_violation=inputs.get("building.violation"),
                      guarantor_consult=inputs.get("guarantor_consult") or "not_yet")


def _level_label(level: str, rules: dict) -> str:
    return next((lv["label"] for lv in rules["verdict"]["levels"] if lv["id"] == level), level)


def _out(v: Verdict, row: Contract, check: Verdict, rules: dict) -> RegistryCompareOut:
    c = v.comparison
    items = [RegistryCompareItemOut(**i) for i in c["items"]]
    mortgage = next((i for i in items if i.field == "registry.mortgage_amount"), None)
    return RegistryCompareOut(
        id=v.id, contract_id=row.id, stage=v.stage, compared_on=date.fromisoformat(c["compared_on"]),
        baseline_check_id=check.id, items=items, changed=c["changed"], hold=c["hold"], advice=c["advice"],
        hint=c["hint"], mortgage_check_required=c["mortgage_check_required"],
        mortgage_check=mortgage if c["mortgage_check_required"] else None, baseline_missing=c["baseline_missing"],
        level_before=check.level, level_after=v.level, level_after_label=_level_label(v.level, rules),
        deposit_ratio_before=check.deposit_ratio, deposit_ratio_after=v.deposit_ratio,
    )


@router.post("/{contract_id}/registry-compare", response_model=RegistryCompareOut, status_code=201,
             responses=responses(404, 409, 422))
def compare(contract_id: int, inp: RegistryCompareInput, db: Session = Depends(get_db),
            rules: dict = Depends(get_rules), today: date = Depends(today_dep),
            x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """다시 올린 등기부 요약(POST /api/registry/parse 결과를 확인한 fields)을 계약 전 확인 때와 비교한다.

    - 항목별 변동(same / risk / eased). 새로 생기거나 늘어난 항목이 있으면 hold와 "계약 보류 후 상담"(계약 당일) /
      "잔금 보류 후 상담"(잔금일) 안내. 근저당이 말소되거나 줄어든 것은 변동으로만 보여 준다
    - 계약 전에 근저당이 있었으면 근저당 금액 비교를 필수 확인으로 돌려준다 (mortgage_check, FR-023)
    - 다시 판정한 결과를 계약의 판정 기록으로 남긴다 (경보 재계산은 이 등기부의 선순위 채권을 씀)
    무산된 계약은 409 CONTRACT_CANCELLED, 없는 계약이나 토큰이 틀리면 404.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    check = db.get(Verdict, row.check_id)
    stage = inp.stage or ("contract_day" if row.balance_date and today < row.balance_date else "balance_day")
    try:
        outcome = run_check(_recheck_input(row, check, inp.registry), rules)
    except MissingInputError as e:
        raise api_error(422, e.code, str(e), e.hint)
    for name in _KEEP_VALUES:
        if (check.inputs or {}).get(name) is not None:
            outcome.values[name] = check.inputs[name]

    result = compare_registry(check.inputs or {}, outcome.values, stage)
    verdict = outcome.verdict
    v = Verdict(
        contract_id=row.id, stage=stage,
        comparison={**asdict(result), "compared_on": today.isoformat()},
        inputs=outcome.values,
        estimated_price=outcome.ratio.estimated_price if outcome.ratio else None,
        deposit_ratio=outcome.ratio.ratio if outcome.ratio else None,
        ratio_is_minimum=outcome.ratio.is_minimum if outcome.ratio else False,
        level=verdict.level, matched_rules=[asdict(m) for m in verdict.matched], linkages=verdict.linkages,
        unchecked=verdict.unchecked, rules_version=verdict.rules_version, market={},
    )
    db.add(v)
    db.commit()
    return _out(v, row, check, rules)


@router.get("/{contract_id}/registry-compare", response_model=list[RegistryCompareOut], responses=responses(404))
def compare_history(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """이 계약의 등기부 재비교 기록 (올린 순서, 기록함 UC-006 사후조건). 무산된 계약도 볼 수 있다."""
    row = _contract_for(contract_id, x_contract_token, db)
    check = db.get(Verdict, row.check_id)
    return [_out(v, row, check, rules) for v in row.verdicts if v.stage is not None]
