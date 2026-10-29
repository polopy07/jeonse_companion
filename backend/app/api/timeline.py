"""계약 타임라인 (FR-032, UI-06, #51): 계약 2년 기록을 날짜순으로.

계약 전 확인(판정·비율), 계약 당일 체크, 특약 넣음/거절당함, 끝낸 할 일과 증빙, 역전세 경보 재계산(단계 변화),
갈아타기 시작, 계약 무산을 한 목록으로 돌려준다. 지난 기록만 (앞으로 할 일은 할 일 목록에서 본다).
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
from app.engine.schedule import FINISHED
from app.engine.special_terms import term_effects
from app.errors import responses
from app.models import Move, Verdict
from app.rules.loader import get_rules
from app.schemas import TimelineEventOut, TimelineOut

router = APIRouter(prefix="/api/contracts", tags=["기록함"])

# 같은 날이면 이 순서 (계약 전 확인 → 계약 당일 → 특약 → 할 일 → 경보 → 갈아타기 → 무산)
KIND_ORDER = ("check", "contract", "special_term", "todo", "alert", "move", "cancel")
RESULT_LABEL = {"inserted": "넣음", "rejected": "거절당함"}


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
        ratio = f"내 보증금 비율 {_percent(check.deposit_ratio)}" if check.deposit_ratio is not None else None
        events.append(_Event(checked_on, "check", f"계약 전 확인: {level.get('label', check.level)}", ratio,
                             level=check.level))

    # 계약의 alert_level은 재계산으로 바뀌므로 계약 시작 때 값은 경보 이력의 첫 점에서
    start = f"시작 경보 {_alert_label(points[0]['level'], rules)}" if points else None
    events.append(_Event(row.contract_date, "contract", "계약 당일 체크", start))
    for e in term_effects(row.special_term_result or {}, rules):
        detail = " ".join(e.outcome.warnings) or (" ".join(e.outcome.documents) and
                                                  f"기록함에 남길 서류: {', '.join(e.outcome.documents)}") or None
        events.append(_Event(row.contract_date, "special_term", f"{e.label} 특약 {RESULT_LABEL[e.result]}", detail,
                             rule_id=e.term_id))

    for t in row.todos:
        if t.status not in FINISHED or t.done_date is None:
            continue
        verb = "완료" if t.status == "done" else "나중에 올리기"
        detail = f"증빙: {t.evidence}" if t.evidence_path else (f"증빙 아직 없음: {t.evidence}" if t.evidence else None)
        events.append(_Event(t.done_date, "todo", f"{verb}: {t.title}", detail, rule_id=t.rule_id, todo_id=t.id,
                             evidence_uploaded=t.evidence_path is not None))

    for prev, point in zip(points, points[1:]):   # 계약 시작 뒤의 재계산만 (시작 값은 계약 전 확인에)
        rank, before = level_rank(point["level"], rules["alert"]), level_rank(prev["level"], rules["alert"])
        change = "올라감" if rank > before else ("내려감" if rank < before else "그대로")
        events.append(_Event(date.fromisoformat(point["as_of"]), "alert",
                             f"역전세 경보 재계산: {_alert_label(point['level'], rules)} ({change})",
                             f"내 보증금 비율 {_percent(point['deposit_ratio'])}", level=point["level"]))

    move = db.scalar(select(Move).where(Move.contract_id == row.id))
    if move is not None:
        nxt = move.next_inputs or {}
        events.append(_Event(move.decided_on, "move", "갈아타기 시작",
                             f"다음 집 잔금일 {nxt['balance_date']}" if nxt.get("balance_date") else None))
    if row.status == "cancelled" and row.cancelled_at is not None:
        events.append(_Event(_kst_date(row.cancelled_at), "cancel", "계약 무산"))

    events.sort(key=lambda e: (e.date, KIND_ORDER.index(e.kind), e.todo_id or 0))
    return TimelineOut(contract_id=row.id, today=today, events=[TimelineEventOut(**e.__dict__) for e in events])
