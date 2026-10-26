"""갈아타기: 다음 집 날짜·돈 → 자금 틈, 대출 순서, 전입 순서 경고, 두 집 할 일 묶기 (FR-025~027, UC-008, UI-07).

다음 집 입력만 저장하고 계산은 읽을 때마다 다시 한다. 다음 집 계약 전 확인은 POST /api/checks (FR-028).
"""
from datetime import date

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.contracts import TOKEN_HEADER_DESC, _active, _contract_for
from app.clock import today as today_dep
from app.db import get_db
from app.engine.move import plan_move
from app.engine.schedule import days_left, todo_state
from app.engine.todos import build_todos
from app.errors import api_error, responses
from app.models import Contract, Move
from app.rules.loader import get_rules
from app.schemas import MoveInput, MoveOut, MoveTodoOut

router = APIRouter(prefix="/api/contracts", tags=["갈아타기"])

# 할 일 규칙(todos.yaml)이 읽는 다음 집 계약 조건
_NEXT_TODO_FIELDS = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "loan",
                     "loan_execution_date", "guarantor", "brokered", "renewal_right_used")


def _line(house: str, rule_id: str, title: str, start, due, remind, status: str, today: date) -> MoveTodoOut:
    return MoveTodoOut(house=house, rule_id=rule_id, title=title, start_date=start, due_date=due, remind_date=remind,
                       state=todo_state(status, start, due, remind, today), days_left=days_left(due, remind, today))


def _anchor(t: MoveTodoOut) -> date:
    return t.remind_date or t.start_date or t.due_date or date.max


def _to_out(row: Contract, move: Move, rules: dict, today: date) -> MoveOut:
    nxt = MoveInput.model_validate(move.next_inputs)
    t9 = next((t for t in row.todos if t.rule_id == "T9"), None)
    return_date = (t9.due_date if t9 is not None and t9.due_date is not None else row.end_date)
    returned = t9 is not None and t9.status == "done"
    plan = plan_move({"deposit": row.deposit, "loan": row.loan}, nxt.model_dump(), return_date, returned)

    planned = build_todos({name: getattr(nxt, name) for name in _NEXT_TODO_FIELDS}, linkages=[], special_terms={},
                          alert_level=None, rules=rules)
    next_todos = [_line("next", p.rule_id, p.title, p.start_date, p.due_date, p.remind_date, "todo", today)
                  for p in planned]
    current = [_line("current", t.rule_id, t.title, t.start_date, t.due_date, t.remind_date, t.status, today)
               for t in row.todos]
    # 날짜순, 같은 날이면 지금 집 먼저 (sorted는 안정 정렬이라 같은 집 안에서는 할 일 순서 그대로)
    merged = sorted(current + next_todos, key=lambda t: (_anchor(t), t.house != "current"))

    return MoveOut(
        contract_id=row.id, today=today, decided_on=move.decided_on, next=nxt,
        current_deposit=row.deposit, return_date=plan.return_date, returned=returned,
        next_balance=plan.next_balance, gap_days=plan.gap_days, gap_amount=plan.gap_amount,
        loan_order=plan.loan_order, loan_gap_days=plan.loan_gap_days,
        move_in_date=plan.move_in_date, move_in_warning=plan.move_in_warning, warnings=plan.warnings,
        next_todos=next_todos, todos=merged,
    )


@router.post("/{contract_id}/move", response_model=MoveOut, responses=responses(404, 409, 422))
def save_move(contract_id: int, inp: MoveInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
              today: date = Depends(today_dep),
              x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """갈아타기 저장 (FR-025~027). 다음 집 입력을 저장하고 자금 틈·대출 순서·전입 순서 경고·두 집 할 일을 돌려준다.

    다시 보내면 다음 집 입력을 바꾼다 (처음 저장한 날 decided_on은 그대로). 무산된 계약이면 409.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is None:
        move = Move(contract_id=row.id, decided_on=today)
        db.add(move)
    move.next_inputs = inp.model_dump(mode="json")
    db.commit()
    return _to_out(row, move, rules, today)


@router.get("/{contract_id}/move", response_model=MoveOut, responses=responses(404))
def get_move(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
             today: date = Depends(today_dep),
             x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """저장한 갈아타기를 지금 계약 상태로 다시 계산해 돌려준다. 저장한 적이 없으면 404."""
    row = _contract_for(contract_id, x_contract_token, db)
    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is None:
        raise api_error(404, "NOT_FOUND", "갈아타기를 시작하지 않았습니다", "만기 6개월 전 할 일에서 \"이사할게요\"를 고르세요")
    return _to_out(row, move, rules, today)
