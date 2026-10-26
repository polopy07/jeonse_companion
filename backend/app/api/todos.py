"""할 일 완료·나중에 올리기·되돌리기 (FR-020, FR-029·030, UC-004, UI-04).

끝낸 날은 뒤 할 일의 기준일이라(T5 시작 = 전입신고 완료 다음 날) 바꿀 때마다 계약의 할 일을 다시 계산하고
계약 전체(ContractOut)를 돌려준다.
"""
from datetime import date

from fastapi import APIRouter, Depends, Header
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.api.contracts import FINISHED, TOKEN_HEADER_DESC, _active, _contract_for, _sync_todos, _to_out
from app.clock import today as today_dep
from app.db import get_db
from app.errors import api_error, responses
from app.models import Todo, Verdict
from app.rules.loader import get_rules
from app.schemas import ContractOut, TodoPatch

router = APIRouter(prefix="/api/todos", tags=["할 일"])


def _titles(todos: list[Todo]) -> str:
    return ", ".join(t.title for t in todos)


@router.patch("/{todo_id}", response_model=ContractOut, responses=responses(404, 409, 422))
def update_todo(todo_id: int, inp: TodoPatch, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                today: date = Depends(today_dep),
                x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """할 일을 끝내거나(done·skipped) 되돌린다(todo). 할 일과 계약은 계약 접근 토큰으로 확인한다.

    - done: 증빙이 필요한 할 일은 증빙을 올려야 끝낼 수 있다 (FR-029). 아직이면 409 EVIDENCE_REQUIRED → "나중에 올리기"
    - skipped: 나중에 올리기. 완료로 치고 기록함은 빈칸 (FR-030)
    - 먼저 끝낼 할 일(prerequisites)이 남았으면 409 PREREQUISITE_NOT_DONE (FR-020)
    - 잔금일에 하는 할 일(T3·T4, reopen_if_done_before_start)은 시작일 전 날짜로 끝낼 수 없다 (409 TODO_NOT_STARTED)
    - 되돌리기는 이 할 일을 먼저 끝내야 하는 뒤 할 일이 끝나 있으면 409 DEPENDENT_DONE
    무산된 계약은 409 CONTRACT_CANCELLED, 없는 할 일이나 토큰이 틀리면 404.
    """
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise api_error(404, "NOT_FOUND", "할 일이 없습니다", "계약을 다시 불러오세요")
    row = _contract_for(todo.contract_id, x_contract_token, db)
    _active(row)
    by_rule = {t.rule_id: t for t in row.todos}

    if inp.status == "todo":
        after = [t for t in row.todos if todo.rule_id in (t.prerequisites or []) and t.status in FINISHED]
        if after:
            raise api_error(409, "DEPENDENT_DONE", f"이 할 일 다음에 하는 할 일을 이미 끝냈습니다: {_titles(after)}",
                            "뒤 할 일을 먼저 되돌리세요")
        todo.status, todo.done_date = "todo", None
    else:
        done_date = inp.done_date or today
        if done_date > today:   # 오늘은 가상 날짜일 수 있어 형식 검사(schemas)가 아니라 여기서 본다
            raise RequestValidationError([{"type": "value_error", "loc": ("body", "done_date"), "input": str(done_date),
                                           "msg": "Value error, 끝낸 날은 오늘보다 뒤일 수 없습니다"}])
        before = [by_rule[r] for r in (todo.prerequisites or []) if r in by_rule and by_rule[r].status not in FINISHED]
        if before:
            raise api_error(409, "PREREQUISITE_NOT_DONE", f"먼저 끝낼 할 일이 있습니다: {_titles(before)}",
                            "앞 할 일을 먼저 끝내세요")
        reopenable = {t["id"] for t in rules["todos"]["todos"] if t.get("reopen_if_done_before_start")}
        if todo.rule_id in reopenable and todo.start_date and done_date < todo.start_date:
            raise api_error(409, "TODO_NOT_STARTED", f"{todo.start_date.isoformat()} 전에는 끝낼 수 없는 할 일입니다",
                            "잔금일 당일에 해야 하는 일이에요. 잔금일이 바뀌었으면 계약 날짜를 먼저 고치세요")
        if inp.status == "done" and todo.evidence and not todo.evidence_path:
            raise api_error(409, "EVIDENCE_REQUIRED", f"증빙({todo.evidence})을 올려야 끝낼 수 있습니다",
                            "증빙 사진을 올리거나 \"나중에 올리기\"를 고르세요")
        todo.status, todo.done_date = inp.status, done_date

    _sync_todos(row, db.get(Verdict, row.check_id), rules)
    db.commit()
    return _to_out(row, db, rules, today)
