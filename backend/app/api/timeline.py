"""계약 타임라인 (FR-032, UI-06, #51): 계약 2년 기록을 날짜순으로.

계약 전 확인(판정·비율), 계약 당일 체크, 등기부 재비교, 특약 넣음/거절당함, 첫 계약 서류, 끝낸 할 일과 증빙,
역전세 경보 재계산(단계 변화), 반환 대응 시작, 갈아타기 시작, 계약 무산을 한 목록으로 돌려준다.
지난 기록만 (오늘(가상 날짜)까지, 앞으로 할 일은 할 일 목록에서 본다).
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts
from app.api.contracts import TOKEN_HEADER_DESC, _contract_for
from app.clock import KST
from app.clock import today as today_dep
from app.db import get_db
from app.engine.alert import level_rank
from app.engine.registry_compare import STAGE_LABEL
from app.engine.schedule import FINISHED
from app.engine.special_terms import term_effects
from app.errors import responses
from app.models import Move, Verdict
from app.rules.loader import get_rules
from app.schemas import TimelineEventOut, TimelineOut

router = APIRouter(prefix="/api/contracts", tags=["기록함"])

# 같은 날이면 이 순서 (계약 전 확인 → 계약 당일 → 등기부 재비교 → 특약 → 첫 계약 서류 → 할 일 → 경보 → 반환 대응
# → 갈아타기 → 무산)
KIND_ORDER = ("check", "contract", "registry", "special_term", "document", "todo", "alert", "return", "move", "cancel")
RESULT_LABEL = {"inserted": "넣음", "rejected": "거절당함"}
CHANGE_LABEL = {"risk": "새로 생기거나 늘어남", "eased": "없어지거나 줄어듦"}


@dataclass
class _Event:
    date: date
    kind: str
    title: str
    detail: str | None = None
    rule_id: str | None = None
    todo_id: int | None = None
    evidence_uploaded: bool | None = None
    level: str | None = None


def _alert_label(level: str | None, rules: dict) -> str:
    return next((lv["label"] for lv in rules["alert"]["levels"] if lv["id"] == level), "정상")


def _kst_date(dt: datetime) -> date:
    """저장 시각(SQLite는 시간대 없이 UTC로 읽힘) → 한국 날짜."""
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(KST).date()


def _percent(ratio: float) -> str:
    return f"{ratio * 100:.1f}%"


def _registry_event(v: Verdict) -> _Event:
    """등기부 재비교 1회 (FR-023, FR-048). 바뀐 항목과 보류 안내를 한 줄로."""
    c = v.comparison
    result = "보류 안내" if c["hold"] else ("바뀜" if c["changed"] else "변동 없음")
    changes = ", ".join(f"{i['label']} {CHANGE_LABEL[i['change']]}" for i in c["items"] if i["change"] != "same")
    detail = " · ".join(x for x in (c["advice"] if c["hold"] else None, changes) if x) or None
    return _Event(date.fromisoformat(c["compared_on"]), "registry",
                  f"등기부 재비교({STAGE_LABEL[v.stage]}): {result}", detail, level=v.level)


@router.get("/{contract_id}/timeline", response_model=TimelineOut, responses=responses(404, 422))
def timeline(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
             today: date = Depends(today_dep),
             x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """계약 2년 기록을 날짜순으로 (FR-032). 무산된 계약도 기록으로 볼 수 있다."""
    row = _contract_for(contract_id, x_contract_token, db)
    check = db.get(Verdict, row.check_id)
    events: list[_Event] = []

    points = alerts.history(row, check, rules) if check is not None else []
    if check is not None:
        level = next((lv for lv in rules["verdict"]["levels"] if lv["id"] == check.level), {})
        checked_on = date.fromisoformat(points[0]["as_of"]) if points else _kst_date(check.created_at)
        checked_on = min(checked_on, today)   # 판정한 날은 실제 날짜라 가상 날짜를 앞으로 돌려도 빠지지 않게
        ratio = f"내 보증금 비율 {_percent(check.deposit_ratio)}" if check.deposit_ratio is not None else None
        events.append(_Event(checked_on, "check", f"계약 전 확인: {level.get('label', check.level)}", ratio,
                             level=check.level))

    # 계약의 alert_level은 재계산으로 바뀌므로 계약 시작 때 값은 경보 이력의 첫 점에서
    start = f"시작 경보 {_alert_label(points[0]['level'], rules)}" if points else None
    events.append(_Event(row.contract_date, "contract", "계약 당일 체크", start))
    for v in row.verdicts:
        if v.stage is not None and v.comparison:
            events.append(_registry_event(v))
    for e in term_effects(row.special_term_result or {}, rules):
        detail = " ".join(e.outcome.warnings) or (" ".join(e.outcome.documents) and
                                                  f"기록함에 남길 서류: {', '.join(e.outcome.documents)}") or None
        events.append(_Event(row.contract_date, "special_term", f"{e.label} 특약 {RESULT_LABEL[e.result]}", detail,
                             rule_id=e.term_id))

    # 첫 계약 서류는 올린 시각(실제 시각)만 있어, 가상 날짜 시연에서 계약일 전·오늘 뒤로 가지 않게 그 사이로
    doc_labels = {k["id"]: k["label"] for k in rules["todos"]["first_documents"]}
    for d in sorted(row.documents, key=lambda d: d.kind):
        on = min(max(_kst_date(d.uploaded_at), row.contract_date or date.min), today)
        events.append(_Event(on, "document", f"첫 계약 서류: {doc_labels.get(d.kind, d.kind)}", rule_id=d.kind))

    for t in row.todos:
        if t.status not in FINISHED or t.done_date is None:
            continue
        verb = "완료" if t.status == "done" else "나중에 올리기"
        detail = f"증빙: {t.evidence}" if t.evidence_path else (f"증빙 아직 없음: {t.evidence}" if t.evidence else None)
        events.append(_Event(t.done_date, "todo", f"{verb}: {t.title}", detail, rule_id=t.rule_id, todo_id=t.id,
                             evidence_uploaded=t.evidence_path is not None))

    # 등기부 재비교는 경보를 바로 다시 계산하므로, 그날 단계가 그대로인 재계산은 재비교 항목과 겹쳐 빼고 바뀐 것만
    compared_on = {e.date for e in events if e.kind == "registry"}
    for prev, point in zip(points, points[1:]):   # 계약 시작 뒤의 재계산만 (시작 값은 계약 전 확인에)
        rank, before = level_rank(point["level"], rules["alert"]), level_rank(prev["level"], rules["alert"])
        change = "올라감" if rank > before else ("내려감" if rank < before else "그대로")
        if change == "그대로" and date.fromisoformat(point["as_of"]) in compared_on:
            continue
        events.append(_Event(date.fromisoformat(point["as_of"]), "alert",
                             f"역전세 경보 재계산: {_alert_label(point['level'], rules)} ({change})",
                             f"내 보증금 비율 {_percent(point['deposit_ratio'])}", level=point["level"]))

    if row.not_returned_date is not None:
        events.append(_Event(row.not_returned_date, "return", "보증금 못 받음: 반환 대응 시작",
                             "반환 대응 단계를 할 일 맨 위에 붙임 (반환 대응 안내에서 단계·청구 서류 확인)"))

    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is not None:
        nxt = move.next_inputs or {}
        events.append(_Event(move.decided_on, "move", "갈아타기 시작",
                             f"다음 집 잔금일 {nxt['balance_date']}" if nxt.get("balance_date") else None))
    if row.status == "cancelled" and row.cancelled_at is not None:
        events.append(_Event(min(_kst_date(row.cancelled_at), today), "cancel", "계약 무산"))

    # 가상 날짜를 되돌리면 그 뒤의 기록(그 뒤 날짜로 끝낸 할 일·재계산 등)은 아직 일어나지 않은 것으로 뺀다
    events = [e for e in events if e.date <= today]
    events.sort(key=lambda e: (e.date, KIND_ORDER.index(e.kind), e.todo_id or 0))
    return TimelineOut(contract_id=row.id, today=today, events=[TimelineEventOut(**e.__dict__) for e in events])
