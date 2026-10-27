"""할 일 완료·나중에 올리기·되돌리기와 증빙 사진 (FR-020, FR-029~031, FR-033, UC-004, UI-04·05).

끝낸 날은 뒤 할 일의 기준일이라(T5 시작 = 전입신고 완료 다음 날) 바꿀 때마다 계약의 할 일을 다시 계산하고
계약 전체(ContractOut)를 돌려준다.
"""
from datetime import date

from fastapi import APIRouter, Depends, Form, Header, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import evidence
from app.api.contracts import FINISHED, TOKEN_HEADER_DESC, _active, _contract_for, _sync_todos, _to_out, done_floor
from app.clock import today as today_dep
from app.db import get_db
from app.errors import api_error, responses
from app.models import Contract, Todo, Verdict
from app.rules.loader import get_rules
from app.schemas import ContractOut, TodoPatch

router = APIRouter(prefix="/api/todos", tags=["할 일"])


def _titles(todos: list[Todo]) -> str:
    return ", ".join(t.title for t in todos)


def _todo_and_contract(todo_id: int, token: str | None, db: Session) -> tuple[Todo, Contract]:
    """할 일과 그 계약. 없는 할 일이나 토큰이 틀리면 404."""
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise api_error(404, "NOT_FOUND", "할 일이 없습니다", "계약을 다시 불러오세요")
    return todo, _contract_for(todo.contract_id, token, db)


def _bad_done_date(done_date: date, msg: str):
    raise RequestValidationError([{"type": "value_error", "loc": ("body", "done_date"), "input": str(done_date),
                                   "msg": f"Value error, {msg}"}])


def _finish_date(todo: Todo, row: Contract, done_date: date | None, today: date, rules: dict) -> date:
    """끝낼 수 있는지 보고 끝낸 날을 정한다 (완료·나중에 올리기·증빙 올리기 공통)."""
    done_date = done_date or today
    # 오늘은 가상 날짜일 수 있고 계약일은 계약마다 달라 형식 검사(schemas)가 아니라 여기서 본다
    if done_date > today:
        _bad_done_date(done_date, "끝낸 날은 오늘보다 뒤일 수 없습니다")
    floor = done_floor(row, todo)
    if done_date < floor:
        label = "계약일" if floor == row.contract_date else "이 할 일 시작일"
        _bad_done_date(done_date, f"끝낸 날은 {label}({floor.isoformat()})보다 앞설 수 없습니다")
    by_rule = {t.rule_id: t for t in row.todos}
    before = [by_rule[r] for r in (todo.prerequisites or []) if r in by_rule and by_rule[r].status not in FINISHED]
    if before:
        raise api_error(409, "PREREQUISITE_NOT_DONE", f"먼저 끝낼 할 일이 있습니다: {_titles(before)}",
                        "앞 할 일을 먼저 끝내세요")
    reopenable = {t["id"] for t in rules["todos"]["todos"] if t.get("reopen_if_done_before_start")}
    if todo.rule_id in reopenable and todo.start_date and done_date < todo.start_date:
        raise api_error(409, "TODO_NOT_STARTED", f"{todo.start_date.isoformat()} 전에는 끝낼 수 없는 할 일입니다",
                        "잔금일 당일에 해야 하는 일이에요. 잔금일이 바뀌었으면 계약 날짜를 먼저 고치세요")
    return done_date


def _save(row: Contract, db: Session, rules: dict, today: date) -> ContractOut:
    _sync_todos(row, db.get(Verdict, row.check_id), rules)
    db.commit()
    return _to_out(row, db, rules, today)


@router.patch("/{todo_id}", response_model=ContractOut, responses=responses(404, 409, 422))
def update_todo(todo_id: int, inp: TodoPatch, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                today: date = Depends(today_dep),
                x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """할 일을 끝내거나(done·skipped) 되돌린다(todo). 할 일과 계약은 계약 접근 토큰으로 확인한다.

    - done: 증빙이 필요한 할 일은 증빙을 올려야 끝낼 수 있다 (FR-029). 아직이면 409 EVIDENCE_REQUIRED → "나중에 올리기"
    - skipped: 나중에 올리기. 완료로 치고 기록함은 빈칸 (FR-030)
    - 먼저 끝낼 할 일(prerequisites)이 남았으면 409 PREREQUISITE_NOT_DONE (FR-020)
    - 잔금일에 하는 할 일(T3·T4, reopen_if_done_before_start)은 시작일 전 날짜로 끝낼 수 없다 (409 TODO_NOT_STARTED)
    - 되돌리기는 이 할 일을 먼저 끝내야 하는 뒤 할 일이 끝나 있으면 409 DEPENDENT_DONE, 조건이 바뀌어 지금 계약에 없는
      끝낸 할 일(기록으로만 남은 것)이면 409 TODO_NOT_PLANNED
    - 끝낸 날이 오늘보다 뒤이거나 계약일(계약 전날 하는 할 일은 시작일)보다 앞서면 422
    무산된 계약은 409 CONTRACT_CANCELLED, 없는 할 일이나 토큰이 틀리면 404.
    """
    todo, row = _todo_and_contract(todo_id, x_contract_token, db)
    _active(row)

    if inp.status == "todo":
        # 조건이 바뀌어 지금 계약에 없는 할 일은 끝낸 기록(증빙 포함)으로만 남는다. 되돌리면 재계산에서 지워지므로 막는다
        if todo.archived:
            raise api_error(409, "TODO_NOT_PLANNED", "지금 계약 조건에는 없는 할 일이라 되돌릴 수 없습니다",
                            "끝낸 기록으로만 남아요. 계약 조건을 바꿔 다시 생기면 그때 되돌리세요")
        # 기록으로만 남은 할 일은 되돌릴 수 없으니 뒤 할 일로 치지 않는다 (서로 막혀 어느 쪽도 못 되돌리지 않게)
        after = [t for t in row.todos if not t.archived and todo.rule_id in (t.prerequisites or [])
                 and t.status in FINISHED]
        if after:
            raise api_error(409, "DEPENDENT_DONE", f"이 할 일 다음에 하는 할 일을 이미 끝냈습니다: {_titles(after)}",
                            "뒤 할 일을 먼저 되돌리세요")
        todo.status, todo.done_date = "todo", None
    else:
        done_date = _finish_date(todo, row, inp.done_date, today, rules)
        if inp.status == "done" and todo.evidence and not todo.evidence_path:
            raise api_error(409, "EVIDENCE_REQUIRED", f"증빙({todo.evidence})을 올려야 끝낼 수 있습니다",
                            "증빙 사진을 올리거나 \"나중에 올리기\"를 고르세요")
        todo.status, todo.done_date = inp.status, done_date
        if inp.status == "skipped":
            todo.skipped_date = today   # 증빙 재알림은 이날부터 센다 (FR-030)
    return _save(row, db, rules, today)


@router.post("/{todo_id}/evidence", response_model=ContractOut, responses=responses(404, 409, 413, 422))
def upload_evidence(todo_id: int, file: UploadFile, done_date: date | None = Form(None),
                    db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """증빙 사진 1장을 올려 할 일을 끝낸다 (FR-029, 기록함에 남음 FR-031). 형식·화질은 제한하지 않고 20MB까지.

    아직 끝내지 않은 할 일은 완료(done)로, 나중에 올리기(skipped)였던 할 일은 기록함을 채워 완료로 바꾼다
    (끝낸 날은 그대로, 보낸 done_date가 있으면 그날). 다시 올리면 앞의 사진을 바꾼다.
    아직 끝내지 않은 할 일과 done_date를 보낸 경우는 끝낼 수 있는 조건이 PATCH와 같다 (선행 조건, 잔금일 전,
    미래 날짜). 이미 끝낸 할 일에 사진만 올리면 저장된 끝낸 날·앞 할 일은 다시 보지 않는다. 무산된 계약이면 409.
    """
    todo, row = _todo_and_contract(todo_id, x_contract_token, db)
    _active(row)
    data = file.file.read(evidence.MAX_EVIDENCE_BYTES + 1)
    if len(data) > evidence.MAX_EVIDENCE_BYTES:
        raise api_error(413, "FILE_TOO_LARGE", f"증빙 파일은 {evidence.max_size_label()}까지 올릴 수 있습니다",
                        "사진 크기를 줄여 다시 올리세요")
    if not data:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "file"), "input": None,
                                       "msg": "Value error, 빈 파일입니다"}])
    if todo.status in FINISHED and done_date is None:
        finished_on = todo.done_date
    else:
        finished_on = _finish_date(todo, row, done_date, today, rules)

    old = todo.evidence_path
    new = evidence.save(row.id, todo.id, data, file.filename)
    todo.evidence_path = new
    todo.status, todo.done_date = "done", finished_on
    evidence.remove_after_commit(db, old)
    try:
        _sync_todos(row, db.get(Verdict, row.check_id), rules)
        db.commit()
    except Exception:
        db.rollback()
        evidence.remove(new)   # DB에 남지 않은 새 파일만 지운다 (커밋한 뒤의 오류는 파일을 그대로 둠)
        raise
    return _to_out(row, db, rules, today)


@router.get("/{todo_id}/evidence", response_class=FileResponse, responses=responses(404))
def get_evidence(todo_id: int, db: Session = Depends(get_db),
                 x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """올린 증빙 파일 (기록함 보기, UI-05). 사진·PDF는 화면에 바로, 다른 형식은 내려받기로 준다. 무산된 계약도 볼 수 있다."""
    todo, _ = _todo_and_contract(todo_id, x_contract_token, db)
    path = evidence.path_of(todo.evidence_path) if todo.evidence_path else None
    if path is None or not path.is_file():
        raise api_error(404, "NOT_FOUND", "올린 증빙이 없습니다")
    media_type = evidence.media_type(todo.evidence_path)
    disposition = "inline" if media_type != evidence.DOWNLOAD else "attachment"
    return FileResponse(path, media_type=media_type, filename=f"evidence-{todo.rule_id}{path.suffix}",
                        content_disposition_type=disposition, headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{todo_id}/evidence", response_model=ContractOut, responses=responses(404))
def delete_evidence(todo_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """증빙 삭제 (FR-033, 언제든 직접 지울 수 있음: 무산된 계약도). 파일을 지우고, 완료했던 할 일은
    "나중에 올리기"(skipped)로 바뀐다 (완료는 그대로, 기록함만 빈칸). 올린 증빙이 없으면 404."""
    todo, row = _todo_and_contract(todo_id, x_contract_token, db)
    if not todo.evidence_path:
        raise api_error(404, "NOT_FOUND", "올린 증빙이 없습니다")
    evidence.remove_after_commit(db, todo.evidence_path)
    todo.evidence_path = None
    if todo.status == "done":
        todo.status, todo.skipped_date = "skipped", today
    if row.status == "cancelled":   # 무산된 계약은 할 일을 다시 계산하지 않는다 (기록만 남음)
        db.commit()
        return _to_out(row, db, rules, today)
    return _save(row, db, rules, today)
