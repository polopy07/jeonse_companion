"""갈아타기: 다음 집 날짜·돈 → 자금 틈, 대출 순서, 전입 순서 경고, 두 집 할 일 묶기 (FR-025~027, UC-008, UI-07).

다음 집 입력만 저장하고 계산은 읽을 때마다 다시 한다. 다음 집 계약 전 확인은 POST /api/checks (FR-028).
"""
from datetime import date

from fastapi import APIRouter, Depends, Header
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.contracts import _TODO_FIELDS, FINISHED, TOKEN_HEADER_DESC, _active, _contract_for
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

def _line(house: str, rule_id: str, title: str, start, due, remind, status: str, today: date) -> MoveTodoOut:
    return MoveTodoOut(house=house, rule_id=rule_id, title=title, start_date=start, due_date=due, remind_date=remind,
                       state=todo_state(status, start, due, remind, today), days_left=days_left(due, remind, today))


def _anchor(t: MoveTodoOut) -> date:
    return t.remind_date or t.start_date or t.due_date or date.max


def _to_out(row: Contract, move: Move, rules: dict, today: date) -> MoveOut:
    try:
        nxt = MoveInput.model_validate(move.next_inputs)
    except ValidationError:   # 저장한 뒤 검사 규칙이 바뀌어 예전 입력이 맞지 않음 → 500 대신 다시 입력하게
        raise api_error(409, "MOVE_INPUT_OUTDATED", "저장한 다음 집 정보가 지금 입력 규칙과 맞지 않습니다",
                        "다음 집 정보를 다시 입력하세요") from None
    t9 = next((t for t in row.todos if t.rule_id == "T9"), None)
    returned = t9 is not None and t9.status in FINISHED   # 나중에 올리기(skipped)도 반환 확인을 끝낸 것
    if returned and t9.done_date is not None:   # 돌려받은 날 (자금 틈·대출 순서는 이 날로, 경고는 내지 않음)
        return_date = t9.done_date
    else:
        return_date = t9.due_date if t9 is not None and t9.due_date is not None else row.end_date
    plan = plan_move({"deposit": row.deposit, "loan": row.loan}, nxt.model_dump(), return_date, returned)

    planned = build_todos({name: getattr(nxt, name) for name in _TODO_FIELDS}, linkages=[], special_terms={},
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

    다시 보내면 다음 집 입력을 바꾼다 (처음 저장한 날 decided_on은 그대로). 다음 집 계약일·잔금일이 지금 계약일보다
    앞서면 422. 무산된 계약이면 409.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    for name in ("contract_date", "balance_date"):
        if getattr(inp, name) < row.contract_date:
            raise RequestValidationError([{
                "type": "value_error", "loc": ("body", name), "input": getattr(inp, name).isoformat(),
                "msg": f"Value error, 다음 집 날짜는 지금 계약일({row.contract_date.isoformat()})보다 앞설 수 없습니다"}])
    inputs = inp.model_dump(mode="json")
    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is None:
        db.add(Move(contract_id=row.id, decided_on=today, next_inputs=inputs))
        try:
            db.commit()
        except IntegrityError:   # "이사할게요"를 연달아 눌러 먼저 저장한 요청이 있음 (moves.contract_id unique) → 그 행을 고친다
            db.rollback()
            move = db.scalar(select(Move).where(Move.contract_id == row.id))
            if move is None:
                raise
    if move is not None:
        move.next_inputs = inputs
        db.commit()
    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    return _to_out(row, move, rules, today)


@router.get("/{contract_id}/move", response_model=MoveOut, responses=responses(404, 409))
def get_move(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
             today: date = Depends(today_dep),
             x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """저장한 갈아타기를 지금 계약 상태로 다시 계산해 돌려준다. 저장한 적이 없으면 404."""
    row = _contract_for(contract_id, x_contract_token, db)
    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is None:
        raise api_error(404, "NOT_FOUND", "갈아타기를 시작하지 않았습니다", "만기 6개월 전 할 일에서 \"이사할게요\"를 고르세요")
    return _to_out(row, move, rules, today)
