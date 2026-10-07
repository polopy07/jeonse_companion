"""계약 전 확인 API (UC-001, FR-001~FR-010)."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.check import MissingInputError, run_check
from app.models import Verdict
from app.rules.loader import get_rules
from app.schemas import CheckInput, CheckResult

router = APIRouter(prefix="/api/checks", tags=["계약 전 확인"])


def _level(rules: dict, level_id: str) -> dict:
    return next(lv for lv in rules["verdict"]["levels"] if lv["id"] == level_id)


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
    )


@router.post("", response_model=CheckResult, status_code=201)
def create_check(inp: CheckInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    try:
        outcome = run_check(inp, rules)
    except MissingInputError as e:
        raise HTTPException(status_code=422, detail=str(e))

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
    )
    db.add(row)
    db.commit()
    return _to_result(row, rules)


@router.get("/{check_id}", response_model=CheckResult)
def get_check(check_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    row = db.get(Verdict, check_id)
    if row is None:
        raise HTTPException(status_code=404, detail="판정 결과가 없습니다")
    return _to_result(row, rules)
