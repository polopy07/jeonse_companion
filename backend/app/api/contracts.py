"""패키지 시작·계약 당일 체크: 계약 생성과 할 일 9종 생성 (UC-003, FR-011, FR-014, FR-015, FR-017~020, FR-049)."""
from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.alert import alert_level
from app.engine.todos import build_todos, report_required
from app.errors import api_error, responses
from app.models import Contract, Todo, Verdict
from app.rules.loader import get_rules
from app.schemas import ContractInput, ContractOut, TodoOut

router = APIRouter(prefix="/api/contracts", tags=["계약"])

# 판정 입력에서 그대로 가져오는 값 (fields.yaml 이름)
_FROM_CHECK = ("housing_type", "deposit", "official_price", "exclusive_area")
# 할 일 규칙(todos.yaml)이 읽는 계약 조건
_TODO_FIELDS = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "loan",
                "loan_execution_date", "guarantor", "brokered", "renewal_right_used")


def _check_special_terms(result: dict, rules: dict) -> None:
    known = {t["id"] for t in rules["special_terms"]["terms"]}
    errors = [
        {"type": "value_error", "loc": ("body", "special_term_result", key),
         "msg": f"Value error, 규칙 파일에 없는 특약입니다: {key}", "input": key}
        for key in result if key not in known
    ]
    if errors:
        raise RequestValidationError(errors)


def _alert_level(check: Verdict, rules: dict) -> str | None:
    # 시작할 때의 경보 단계는 판정 때 계산한 내 보증금 비율로 정한다. 계약 중 재계산(FR-037)은 4주차
    values = {"deposit_ratio": check.deposit_ratio, "deposit": check.inputs.get("deposit"),
              "nearby_jeonse_median": check.inputs.get("nearby_jeonse_median")}
    return alert_level(values, rules["alert"])


def _todo_values(row: Contract) -> dict:
    return {name: getattr(row, name) for name in _TODO_FIELDS}


def _create_todos(row: Contract, check: Verdict, rules: dict) -> None:
    planned = build_todos(_todo_values(row), check.linkages, row.special_term_result, _alert_level(check, rules), rules)
    version = str(rules["todos"]["version"])
    for t in planned:
        row.todos.append(Todo(
            rule_id=t.rule_id, title=t.title, detail=t.detail,
            start_date=t.start_date, due_date=t.due_date, remind_date=t.remind_date,
            prerequisites=t.prerequisites, required_checks=t.required_checks, evidence=t.evidence,
            sort_order=t.sort_order, pinned=t.pinned, moved_to_top=t.moved_to_top,
            status="todo", rules_version=version,
        ))


def _to_out(row: Contract, rules: dict) -> ContractOut:
    check = row.verdicts[0]
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
        report_required=report_required(_todo_values(row), rules["todos"]),
        alert_level=_alert_level(check, rules),
        todos=[TodoOut.model_validate(t, from_attributes=True) for t in row.todos],
    )


@router.post("", response_model=ContractOut, status_code=201, responses=responses(404, 409, 422))
def create_contract(inp: ContractInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    _check_special_terms(inp.special_term_result, rules)

    check = db.get(Verdict, inp.check_id)
    if check is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다", "계약 전 확인을 먼저 하세요")
    level = next(lv for lv in rules["verdict"]["levels"] if lv["id"] == check.level)
    if level.get("block_payment"):
        raise api_error(409, "CHECK_BLOCKED", f"\"{level['label']}\" 판정이라 패키지를 시작할 수 없습니다",
                        "계약을 다시 검토하고 공공 상담 창구에 문의하세요")
    if check.contract_id is not None:
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다",
                        f"만든 계약은 GET /api/contracts/{check.contract_id}로 볼 수 있습니다")

    row = Contract(
        **{name: check.inputs.get(name) for name in _FROM_CHECK},
        **inp.model_dump(exclude={"check_id"}),
    )
    row.verdicts.append(check)
    _create_todos(row, check, rules)
    db.add(row)
    db.commit()
    return _to_out(row, rules)


@router.get("/{contract_id}", response_model=ContractOut, responses=responses(404, 422))
def get_contract(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    row = db.get(Contract, contract_id)
    if row is None:
        raise api_error(404, "NOT_FOUND", "계약이 없습니다")
    return _to_out(row, rules)
