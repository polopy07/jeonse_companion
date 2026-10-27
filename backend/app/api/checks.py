"""계약 전 확인 API (UC-001, FR-001~FR-010)와 판정에 맞는 특약 예시 (FR-039), 테스트 결제 (FR-013)."""
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.check import MissingInputError, run_check
from app.engine.market import ComplexKey, nearby_jeonse, pick_trade_price
from app.engine.payment import PRODUCTS, product_for
from app.engine.special_terms import contract_day_guide
from app.errors import api_error, responses
from app.models import Payment, Trade, Verdict
from app.rules.loader import get_rules
from app.schemas import CheckInput, CheckResult, PaymentOut, SpecialTermsResult

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


def trade_records(db: Session, lawd_cd: str, housing_type: str) -> list[Trade]:
    return list(db.scalars(select(Trade).where(Trade.lawd_cd == lawd_cd, Trade.housing_type == housing_type)).all())


def find_market(db: Session, housing_type: str, complex_: dict, exclusive_area: float | None, rules: dict, as_of: date,
                records: list[Trade] | None = None):
    """단지(lawd_cd·umd_name·complex_name·jibun)로 저장된 실거래에서 매매 실거래가와 주변 전세 시세를 찾는다.
    계약 전 확인과 계약 중 경보 재계산(app.alerts)이 같이 쓴다. records를 주면 다시 불러오지 않는다."""
    key = ComplexKey(housing_type, complex_["lawd_cd"], complex_["umd_name"], complex_["complex_name"],
                     complex_.get("jibun"))
    if records is None:
        records = trade_records(db, key.lawd_cd, housing_type)
    return (pick_trade_price(records, key, exclusive_area, as_of, rules["alert"]),
            nearby_jeonse(records, key, exclusive_area, as_of, rules["alert"]))


def _market(inp: CheckInput, db: Session, rules: dict, as_of: date):
    """단지를 주었으면 저장된 실거래에서 매매 실거래가와 주변 전세 시세를 찾는다."""
    return find_market(db, inp.housing_type, inp.complex.model_dump(), inp.exclusive_area, rules, as_of)


@router.post("", response_model=CheckResult, status_code=201, responses=responses(422))
def create_check(inp: CheckInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 x_virtual_today: date | None = Header(None, description="시연용 가상 날짜 YYYY-MM-DD (API 명세 1.7)")):
    market: dict = {}
    if inp.trade_price is not None:   # 사용자가 직접 넣은 매매 실거래가. 경보 재계산도 판정처럼 이 값을 먼저 쓴다 (FR-037)
        market["trade_price_input"] = inp.trade_price
    pick = nearby = None
    if inp.complex is not None:
        as_of = x_virtual_today or date.today()
        pick, nearby = _market(inp, db, rules, as_of)
        market["as_of"] = as_of.isoformat()
        market["complex"] = inp.complex.model_dump()   # 계약 중 경보 재계산(FR-037)에서 같은 단지 실거래를 다시 찾는다
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


def payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(payment_id=p.id, check_id=p.check_id, product=p.product, amount=p.amount,
                      method=p.method, status=p.status)


@router.post("/{check_id}/payment", response_model=PaymentOut, status_code=201, responses=responses(404, 409, 422))
def create_payment(check_id: int, response: Response, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    """테스트 결제 (FR-013, API 명세 1.8). 금액은 판정 단계로 서버가 정한다. 실제 돈은 나가지 않는다.

    같은 판정에 다시 누르면 새로 만들지 않고 앞서 한 결제를 200으로 돌려준다 (두 번 눌러도 결제 1건).
    """
    row = db.get(Verdict, check_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다")
    level = _level(rules, row.level)
    if level.get("block_payment"):
        raise api_error(409, "CHECK_BLOCKED", f"\"{level['label']}\" 판정이라 패키지를 시작할 수 없습니다",
                        "계약을 다시 검토하고 공공 상담 창구에 문의하세요")
    if row.contract_id is not None:
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다",
                        "할 일 탭에서 이 계약의 할 일을 볼 수 있습니다. 다른 집이면 계약 전 확인을 다시 하세요")
    existing = db.scalars(select(Payment).where(Payment.check_id == check_id, Payment.status == "paid")).first()
    if existing is not None:
        response.status_code = 200
        return payment_out(existing)
    product = product_for(row.level)
    p = Payment(check_id=check_id, product=product, amount=PRODUCTS[product], method="test", status="paid")
    db.add(p)
    db.commit()
    return payment_out(p)
