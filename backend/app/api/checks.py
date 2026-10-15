"""계약 전 확인 API (UC-001, FR-001~FR-010)와 판정에 맞는 특약 예시 (FR-039)."""
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.check import MissingInputError, run_check
from app.engine.market import ComplexKey, nearby_jeonse, pick_trade_price
from app.engine.special_terms import contract_day_guide
from app.errors import api_error, responses
from app.models import Trade, Verdict
from app.rules.loader import get_rules
from app.schemas import CheckInput, CheckResult, SpecialTermsResult

router = APIRouter(prefix="/api/checks", tags=["계약 전 확인"])


def _level(rules: dict, level_id: str) -> dict:
    level = next((lv for lv in rules["verdict"]["levels"] if lv["id"] == level_id), None)
    if level is None:   # 저장된 판정 단계가 지금 규칙 파일에 없음 (POST /api/contracts와 같은 기준)
        raise api_error(409, "CHECK_OUTDATED", "판정 기준이 바뀌어 이 판정 결과를 보여 줄 수 없습니다",
                        "계약 전 확인을 다시 하세요")
    return level


def _to_result(row: Verdict, rules: dict) -> CheckResult:
    level = _level(rules, row.level)
    return CheckResult(
        id=row.id,
        level=row.level,
        label=level["label"],
        next_step=level.get("next_step", ""),
        block_payment=bool(level.get("block_payment", False)),
        estimated_price=row.estimated_price,
        deposit_ratio=row.deposit_ratio,
        ratio_is_minimum=row.ratio_is_minimum,
        matched=row.matched_rules,
        linkages=row.linkages,
        unchecked=row.unchecked,
        disclaimer=rules["verdict"].get("display", {}).get("disclaimer", ""),
        rules_version=row.rules_version,
        as_of=(row.market or {}).get("as_of"),
        trade_basis=(row.market or {}).get("trade_basis"),
        nearby_jeonse=(row.market or {}).get("nearby_jeonse"),
        contract_id=row.contract_id,
    )


def _market(inp: CheckInput, db: Session, rules: dict, as_of: date):
    """단지를 주었으면 저장된 실거래에서 매매 실거래가와 주변 전세 시세를 찾는다."""
    c = inp.complex
    key = ComplexKey(inp.housing_type, c.lawd_cd, c.umd_name, c.complex_name, c.jibun)
    records = db.scalars(select(Trade).where(Trade.lawd_cd == c.lawd_cd, Trade.housing_type == inp.housing_type)).all()
    return (pick_trade_price(records, key, inp.exclusive_area, as_of, rules["alert"]),
            nearby_jeonse(records, key, inp.exclusive_area, as_of, rules["alert"]))


@router.post("", response_model=CheckResult, status_code=201, responses=responses(422))
def create_check(inp: CheckInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 x_virtual_today: date | None = Header(None, description="시연용 가상 날짜 YYYY-MM-DD (API 명세 1.7)")):
    market: dict = {}
    pick = nearby = None
    if inp.complex is not None:
        as_of = x_virtual_today or date.today()
        pick, nearby = _market(inp, db, rules, as_of)
        market["as_of"] = as_of.isoformat()
        if pick is not None and inp.trade_price is None:
            inp = inp.model_copy(update={"trade_price": pick.price})

    try:
        outcome = run_check(inp, rules)
    except MissingInputError as e:
        raise api_error(422, e.code, str(e), e.hint)

    if pick is not None:
        used = outcome.ratio is not None and inp.trade_price == pick.price and outcome.ratio.estimated_price == pick.price
        market["trade_basis"] = {**asdict(pick), "deal_date": pick.deal_date.isoformat(), "used": used}
    if nearby is not None:
        below = None if nearby.median is None else nearby.median < inp.deposit
        market["nearby_jeonse"] = {**asdict(nearby), "below_deposit": below}
        outcome.values["nearby_jeonse_median"] = nearby.median
        outcome.values["nearby_sample_count"] = nearby.sample_count

    v = outcome.verdict
    row = Verdict(
        inputs=outcome.values,
        estimated_price=outcome.ratio.estimated_price if outcome.ratio else None,
        deposit_ratio=outcome.ratio.ratio if outcome.ratio else None,
        ratio_is_minimum=outcome.ratio.is_minimum if outcome.ratio else False,
        level=v.level,
        matched_rules=[asdict(m) for m in v.matched],
        linkages=v.linkages,
        unchecked=v.unchecked,
        rules_version=v.rules_version,
        market=market,
    )
    db.add(row)
    db.commit()
    return _to_result(row, rules)


@router.get("/{check_id}", response_model=CheckResult, responses=responses(404, 409, 422))
def get_check(check_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    row = db.get(Verdict, check_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다")
    return _to_result(row, rules)


@router.get("/{check_id}/special-terms", response_model=SpecialTermsResult, responses=responses(404, 409, 422))
def get_special_terms(check_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    row = db.get(Verdict, check_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다")
    level = _level(rules, row.level)
    if level.get("block_payment"):
        # 패키지를 시작할 수 없는 판정에 특약 예시를 보여 주면 "특약만 넣으면 된다"로 읽힐 수 있다 (POST /api/contracts와 같은 기준)
        raise api_error(409, "CHECK_BLOCKED", f"\"{level['label']}\" 판정이라 특약 예시를 보여 주지 않습니다",
                        "계약을 다시 검토하고 공공 상담 창구에 문의하세요")
    guide = contract_day_guide(row.linkages, rules)
    return SpecialTermsResult.model_validate({
        "check_id": row.id,
        "level": row.level,
        "terms": [asdict(t) for t in guide.terms],
        "warnings": guide.warnings,
        "checks": guide.checks,
        "disclaimer": rules["verdict"].get("display", {}).get("disclaimer", ""),
        "rules_version": str(rules["special_terms"]["version"]),
    })
