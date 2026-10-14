"""패키지 시작·계약 당일 체크: 계약 생성과 할 일 9종 생성 (UC-003, FR-011, FR-014, FR-015, FR-017~020, FR-049).

계약 조건·특약 결과 변경 → 할 일 재계산 (UC-005, FR-021, FR-049·050).
"""
from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.alert import alert_level
from app.engine.special_terms import contract_day_guide
from app.engine.todos import build_todos, report_required
from app.errors import api_error, responses
from app.models import Contract, Todo, Verdict
from app.rules.loader import get_rules
from app.schemas import ContractInput, ContractOut, ContractPatch, TodoOut

router = APIRouter(prefix="/api/contracts", tags=["계약"])
# 화면에 그대로 보이는 안내. 만든 계약 id는 GET /api/checks/{id}의 contract_id로 찾는다
ALREADY_USED_HINT = "할 일 탭에서 이 계약의 할 일을 볼 수 있습니다. 다른 집이면 계약 전 확인을 다시 하세요"

# 판정 입력에서 그대로 가져오는 값 (fields.yaml 이름)
_FROM_CHECK = ("housing_type", "deposit", "official_price", "exclusive_area")
# 할 일 규칙(todos.yaml)이 읽는 계약 조건
_TODO_FIELDS = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "loan",
                "loan_execution_date", "guarantor", "brokered", "renewal_right_used")


def shown_special_terms(linkages: list[str], rules: dict) -> set[str]:
    """계약 당일 특약 예시(GET /api/checks/{id}/special-terms)로 보여 준 특약 id. 보여 준 기준과 받는 기준을 같게."""
    return {t.id for t in contract_day_guide(linkages, rules).terms}


def _check_special_terms(result: dict, linkages: list[str], rules: dict) -> None:
    """판정에서 보여 준 특약의 결과만 받는다. 보여 주지 않은 특약의 거절로 할 일이 바뀌지 않게."""
    known = {t["id"] for t in rules["special_terms"]["terms"]}
    shown = shown_special_terms(linkages, rules)
    errors = []
    for key in result:
        if key not in known:
            msg = f"규칙 파일에 없는 특약입니다: {key}"
        elif key not in shown:
            msg = f"이 판정에서 안내하지 않은 특약입니다: {key}"
        else:
            continue
        errors.append({"type": "value_error", "loc": ("body", "special_term_result", key),
                       "msg": f"Value error, {msg}", "input": key})
    if errors:
        raise RequestValidationError(errors)


def _alert_level(check: Verdict, rules: dict) -> str | None:
    # 시작할 때의 경보 단계는 판정 때 계산한 내 보증금 비율로 정한다. 계약 중 재계산(FR-037)은 4주차
    values = {"deposit_ratio": check.deposit_ratio, "deposit": check.inputs.get("deposit"),
              "nearby_jeonse_median": check.inputs.get("nearby_jeonse_median")}
    return alert_level(values, rules["alert"])


def _todo_values(row: Contract) -> dict:
    return {name: getattr(row, name) for name in _TODO_FIELDS}


def _sync_todos(row: Contract, check: Verdict, rules: dict) -> None:
    """계약 조건으로 할 일을 만들거나 다시 계산한다.

    같은 할 일(rule_id)은 id·상태·완료일·증빙을 그대로 두고 날짜·순서만 바꾼다. 끝낸 할 일의 완료일은
    뒤 할 일의 기준일로 쓴다 (T5 시작 = 전입신고 완료 다음 날). 조건이 바뀌어 더는 해당하지 않는 할 일은
    지우되, 이미 끝낸 것은 기록으로 맨 뒤에 남긴다.
    """
    row.report_required = report_required(_todo_values(row), rules["todos"])
    existing = {t.rule_id: t for t in row.todos}
    done_dates = {t.rule_id: t.done_date for t in row.todos if t.status == "done" and t.done_date}
    planned = build_todos(_todo_values(row), check.linkages, row.special_term_result, row.alert_level, rules,
                          done_dates=done_dates)
    version = str(rules["todos"]["version"])
    todos = []
    for p in planned:
        t = existing.pop(p.rule_id, None) or Todo(rule_id=p.rule_id, status="todo")
        t.title, t.detail, t.evidence = p.title, p.detail, p.evidence
        t.start_date, t.due_date, t.remind_date = p.start_date, p.due_date, p.remind_date
        t.prerequisites, t.required_checks = p.prerequisites, p.required_checks
        t.sort_order, t.pinned, t.moved_to_top = p.sort_order, p.pinned, p.moved_to_top
        t.rules_version = version
        todos.append(t)
    for t in sorted(existing.values(), key=lambda t: t.sort_order):
        if t.status == "done":
            t.sort_order = len(todos) + 1
            todos.append(t)
    row.todos = todos   # 남기지 않은 할 일은 delete-orphan으로 지워진다


def _to_out(row: Contract, db: Session) -> ContractOut:
    check = db.get(Verdict, row.check_id)
    return ContractOut(
        id=row.id,
        check_id=check.id,
        level=check.level,
        housing_type=row.housing_type,
        deposit=row.deposit,
        monthly_rent=row.monthly_rent,
        exclusive_area=row.exclusive_area,
        official_price=row.official_price,
        contract_date=row.contract_date,
        balance_date=row.balance_date,
        end_date=row.end_date,
        loan=row.loan,
        loan_execution_date=row.loan_execution_date,
        guarantor=row.guarantor,
        brokered=row.brokered,
        renewal_right_used=row.renewal_right_used,
        co_tenant=row.co_tenant,
        email=row.email,
        special_term_result=row.special_term_result,
        report_required=row.report_required,
        alert_level=row.alert_level,
        todos=[TodoOut.model_validate(t, from_attributes=True) for t in row.todos],
    )


@router.post("", response_model=ContractOut, status_code=201, responses=responses(404, 409, 422))
def create_contract(inp: ContractInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    check = db.get(Verdict, inp.check_id)
    if check is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다", "계약 전 확인을 먼저 하세요")
    level = next((lv for lv in rules["verdict"]["levels"] if lv["id"] == check.level), None)
    if level is None:
        raise api_error(409, "CHECK_OUTDATED", "판정 기준이 바뀌어 이 판정 결과로는 시작할 수 없습니다",
                        "계약 전 확인을 다시 하세요")
    if level.get("block_payment"):
        raise api_error(409, "CHECK_BLOCKED", f"\"{level['label']}\" 판정이라 패키지를 시작할 수 없습니다",
                        "계약을 다시 검토하고 공공 상담 창구에 문의하세요")
    if check.contract_id is not None:
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다", ALREADY_USED_HINT)
    _check_special_terms(inp.special_term_result, check.linkages, rules)

    row = Contract(
        **{name: check.inputs.get(name) for name in _FROM_CHECK},
        **inp.model_dump(),
    )
    row.verdicts.append(check)
    row.alert_level = _alert_level(check, rules)
    _sync_todos(row, check, rules)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:   # 같은 판정으로 동시에 들어온 요청 중 늦은 쪽 (check_id unique)
        db.rollback()
        first = db.query(Contract).filter_by(check_id=inp.check_id).one_or_none()
        if first is None:   # check_id가 아닌 다른 제약 위반이면 그대로 올린다
            raise
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다", ALREADY_USED_HINT) from None
    return _to_out(row, db)


@router.get("/{contract_id}", response_model=ContractOut, responses=responses(404, 422))
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    row = db.get(Contract, contract_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "계약이 없습니다")
    return _to_out(row, db)


@router.patch("/{contract_id}", response_model=ContractOut, responses=responses(404, 422))
def update_contract(contract_id: int, inp: ContractPatch, db: Session = Depends(get_db),
                    rules: dict = Depends(get_rules)):
    """계약 조건·특약 결과를 바꾸고 할 일을 다시 계산한다 (FR-021, FR-049·050)."""
    row = db.get(Contract, contract_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "계약이 없습니다")
    check = db.get(Verdict, row.check_id)
    changes = inp.model_dump(exclude_unset=True)
    terms = changes.pop("special_term_result", None) or {}
    _check_special_terms(terms, check.linkages, rules)

    # 바꾼 뒤의 계약 조건 전체가 계약 생성 때와 같은 규칙(날짜 순서, 대출 없으면 실행일 없음)을 지켜야 한다
    current = {name: getattr(row, name) for name in ContractInput.model_fields
               if name not in ("check_id", "special_term_result")}
    try:
        ContractInput(check_id=row.check_id, **{**current, **changes})
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from None

    for name, value in changes.items():
        setattr(row, name, value)
    if terms:
        row.special_term_result = {**row.special_term_result, **terms}
    _sync_todos(row, check, rules)
    db.commit()
    return _to_out(row, db)
