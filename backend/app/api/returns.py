"""반환 대응: 만기일 "못 받음" → 반환 대응 단계·청구 서류 대조 (FR-024, FR-034, FR-035, UC-009, UI-08, #52).

"못 받음"을 고르면 단계(R1~R4)를 계약의 할 일로 붙인다. 단계를 끝내거나 증빙(반환 요청 캡처, 내용증명 사본 등)을
올리는 것은 다른 할 일과 같이 PATCH·POST /api/todos/{id}로 한다. 나중에 돈을 돌려받으면 9번을 끝내면 된다.
"""
from datetime import date

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.contracts import TOKEN_HEADER_DESC, _active, _contract_for, _sync_todos, _to_out
from app.clock import today as today_dep
from app.db import get_db
from app.engine.return_response import check_documents, confirm_todo_id, return_steps
from app.engine.schedule import FINISHED
from app.errors import api_error, responses
from app.models import Contract, Verdict
from app.rules.loader import get_rules
from app.schemas import ContractOut, LinkOut, ReturnDocumentOut, ReturnGuideOut, ReturnStepOut

router = APIRouter(prefix="/api/contracts", tags=["반환 대응"])


def _step_ids(rules: dict) -> set[str]:
    return {s["id"] for s in rules["todos"]["return_response"]["steps"]}


def _resync(row: Contract, db: Session, rules: dict, today: date) -> ContractOut:
    _sync_todos(row, db.get(Verdict, row.check_id), rules)
    db.commit()
    return _to_out(row, db, rules, today)


@router.post("/{contract_id}/return-response", response_model=ContractOut, responses=responses(404, 409, 422))
def start_return_response(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                          today: date = Depends(today_dep),
                          x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """9번(반환 확인)에서 "못 받음" (FR-024). 오늘을 시작일로 반환 대응 단계(R1~R4)를 맨 위 할 일로 붙인다.

    - 만기일 전이면 409 RETURN_NOT_DUE
    - 9번을 이미 끝냈으면(돌려받음) 409 ALREADY_RETURNED
    - 이미 시작했으면 바꾸지 않고 그대로 돌려준다 (다시 보내도 같음)
    무산된 계약은 409 CONTRACT_CANCELLED, 없는 계약이나 토큰이 틀리면 404.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    if row.not_returned_date is not None:
        return _to_out(row, db, rules, today)
    if today < row.end_date:
        raise api_error(409, "RETURN_NOT_DUE", f"만기일({row.end_date.isoformat()}) 전에는 반환 대응을 시작할 수 없습니다",
                        "만기일에 보증금을 돌려받지 못했을 때 고르세요")
    confirm = next((t for t in row.todos if t.rule_id == confirm_todo_id(rules)), None)
    if confirm is not None and confirm.status in FINISHED:
        raise api_error(409, "ALREADY_RETURNED", "보증금 반환을 확인한 계약입니다",
                        "잘못 끝냈으면 반환 확인 할 일을 먼저 되돌리세요")
    row.not_returned_date = today
    return _resync(row, db, rules, today)


@router.delete("/{contract_id}/return-response", response_model=ContractOut, responses=responses(404, 409, 422))
def undo_return_response(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                         today: date = Depends(today_dep),
                         x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """"못 받음"을 잘못 골랐을 때 되돌린다. 반환 대응 단계 할 일을 지운다.

    시작하지 않았으면 409 RETURN_NOT_STARTED, 끝낸 단계(나중에 올리기 포함)가 있으면 409 RETURN_STEP_DONE
    (기록이 지워지지 않게: 단계를 먼저 되돌리거나, 돈을 돌려받았으면 9번을 끝낸다). 무산된 계약은 409.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    if row.not_returned_date is None:
        raise api_error(409, "RETURN_NOT_STARTED", "반환 대응을 시작하지 않은 계약입니다")
    steps = _step_ids(rules)
    finished = [t for t in row.todos if t.rule_id in steps and t.status in FINISHED]
    if finished:
        raise api_error(409, "RETURN_STEP_DONE",
                        f"이미 끝낸 반환 대응 단계가 있습니다: {', '.join(t.title for t in finished)}",
                        "돈을 돌려받았으면 반환 확인 할 일을 끝내세요. 잘못 고른 거면 끝낸 단계를 먼저 되돌리세요")
    row.not_returned_date = None
    return _resync(row, db, rules, today)


@router.get("/{contract_id}/return-guide", response_model=ReturnGuideOut, responses=responses(404, 422))
def return_guide(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 today: date = Depends(today_dep),
                 x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """반환 대응 안내 (UI-08): 단계와 진행, 청구 서류 대조 (FR-034·035). 무산된 계약도 기록으로 볼 수 있다.

    "못 받음"을 고르기 전에도 볼 수 있다(preview): 경보가 위험일 때 청구 서류를 미리 점검하는 데 쓴다.
    preview에서는 지금 준비할 수 있는 할 일(T) 서류만 대조한다 (반환 대응 단계 서류는 "못 받음" 뒤에 생김).
    """
    row = _contract_for(contract_id, x_contract_token, db)
    started = row.not_returned_date is not None
    steps = return_steps(row.guarantor, rules)
    step_ids = {s.id for s in steps}
    # 돌려받아 끝난 뒤에는 끝낸 단계가 기록(archived)으로만 남으므로 단계는 기록까지 본다
    by_rule = {t.rule_id: t for t in row.todos if not t.archived or t.rule_id in step_ids}
    confirm = by_rule.get(confirm_todo_id(rules))
    ended = started and confirm is not None and confirm.status in FINISHED

    names = {rule_id: t.evidence for rule_id, t in by_rule.items()}
    if started:
        names |= {s.id: s.evidence for s in steps}
    uploaded = {rule_id for rule_id, t in by_rule.items() if t.evidence_path}
    docs = check_documents(steps, names, uploaded)
    missing = {d.rule_id for d in docs if not d.uploaded}

    out_steps, current_found = [], ended or not started
    for s in steps:
        t = by_rule.get(s.id) if started else None
        if t is not None and t.status in FINISHED:
            state = "done"
        elif not current_found:
            state, current_found = "current", True
        else:
            state = "todo"
        out_steps.append(ReturnStepOut(
            rule_id=s.id, todo_id=t.id if t else None, title=s.title, detail=s.detail,
            link=LinkOut(**s.link) if s.link else None, evidence=s.evidence, state=state,
            done_date=t.done_date if t else None, evidence_uploaded=bool(t and t.evidence_path),
            documents=s.documents, missing_documents=[names[d] for d in s.documents if d in missing]))

    cfg = rules["todos"]["return_response"]
    return ReturnGuideOut(
        contract_id=row.id,
        today=today,
        status="preview" if not started else ("ended" if ended else "in_progress"),
        end_date=row.end_date,
        not_returned_date=row.not_returned_date,
        guarantor=row.guarantor,
        steps=out_steps,
        documents=[ReturnDocumentOut(rule_id=d.rule_id, todo_id=by_rule[d.rule_id].id if d.rule_id in by_rule else None,
                                     name=d.name, uploaded=d.uploaded, needed_by=d.needed_by) for d in docs],
        missing_count=len(missing),
        help_desks=[LinkOut(**h) for h in cfg["help_desks"]],
        disclaimer=cfg["disclaimer"],
        rules_version=str(rules["todos"]["version"]),
    )
