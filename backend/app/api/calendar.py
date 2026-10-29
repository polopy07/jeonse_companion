"""캘린더 구독 (FR-042, #47): 보기 전용 구독 주소 만들기·끊기와 구독 파일.

앱의 ICS 내보내기(#102)는 내보낸 때의 일정이라 날짜가 바뀌면 다시 내보내야 한다. 구독 주소를 캘린더에 넣으면
캘린더 앱이 주기적으로 불러와 바뀐 기한이 저절로 반영된다. 캘린더 앱은 헤더를 보낼 수 없어 주소에 보기 전용 토큰을
넣고, 이 토큰은 계약 API에 쓸 수 없다. 캘린더 앱이 서버에 닿아야 하므로 실제 구독은 배포 서버에서 된다.
"""
import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.contracts import TOKEN_HEADER_DESC, _active, _contract_for
from app.config import public_base_url
from app.db import get_db
from app.engine.calendar import CalendarTodo, build_ics
from app.errors import api_error, responses
from app.models import CalendarToken, Contract
from app.rules.loader import get_rules
from app.schemas import CalendarLinkOut

router = APIRouter(prefix="/api", tags=["캘린더 구독"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _revoke_all(contract_id: int, db: Session) -> int:
    now = datetime.now(timezone.utc)
    return db.execute(update(CalendarToken).where(CalendarToken.contract_id == contract_id,
                                                  CalendarToken.revoked_at.is_(None)).values(revoked_at=now)).rowcount


@router.post("/contracts/{contract_id}/calendar-link", response_model=CalendarLinkOut, status_code=201,
             responses=responses(404, 409))
def create_calendar_link(contract_id: int, request: Request, db: Session = Depends(get_db),
                         x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """캘린더 구독 주소를 만든다. 앞서 만든 주소는 끊는다(한 계약에 살아 있는 주소는 하나). 무산된 계약이면 409."""
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    _revoke_all(row.id, db)
    token = secrets.token_urlsafe(32)
    link = CalendarToken(contract_id=row.id, token_hash=_hash(token), created_at=datetime.now(timezone.utc))
    db.add(link)
    db.commit()
    path = request.app.url_path_for("calendar_feed", token=token)
    url = f"{public_base_url() or str(request.base_url).rstrip('/')}{path}"
    return CalendarLinkOut(url=url, webcal_url="webcal://" + url.split("://", 1)[1], created_at=link.created_at)


@router.delete("/contracts/{contract_id}/calendar-link", status_code=204, responses=responses(404))
def delete_calendar_link(contract_id: int, db: Session = Depends(get_db),
                         x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """구독 주소를 끊는다 (주소가 샜거나 더 쓰지 않을 때). 그 뒤 캘린더 앱이 불러오면 404. 끊을 주소가 없으면 404."""
    row = _contract_for(contract_id, x_contract_token, db)
    if not _revoke_all(row.id, db):
        raise api_error(404, "NOT_FOUND", "만든 구독 주소가 없습니다")
    db.commit()
    return Response(status_code=204)


@router.get("/calendar/{token}.ics", name="calendar_feed", response_class=Response,
            responses={200: {"content": {"text/calendar": {}}, "description": "ICS 본문"}, **responses(404)})
def calendar_feed(token: str, db: Session = Depends(get_db), rules: dict = Depends(get_rules)):
    """구독 파일 (캘린더 앱이 주기적으로 부른다). 끝나지 않은 할 일만, 앱 내보내기와 같은 UID.
    끊은 주소나 없는 주소는 404, 무산된 계약은 일정 없는 캘린더(구독한 일정이 지워진다)."""
    link = db.scalar(select(CalendarToken).where(CalendarToken.token_hash == _hash(token),
                                                 CalendarToken.revoked_at.is_(None)))
    row = db.get(Contract, link.contract_id) if link is not None else None
    if row is None:
        raise api_error(404, "NOT_FOUND", "구독 주소가 없거나 끊겼습니다", "앱에서 구독 주소를 다시 만드세요")
    todos = [] if row.status == "cancelled" else [
        CalendarTodo(t.rule_id, t.title, t.detail, t.start_date, t.due_date, t.remind_date, t.status)
        for t in row.todos if not t.archived]
    body = build_ics(row.id, todos, rules["todos"]["notifications"].get("due_before_days", []))
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'inline; filename="jeonse-todos.ics"', "Cache-Control": "no-cache"})
