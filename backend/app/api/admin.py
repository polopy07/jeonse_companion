"""관리자: 공공 데이터 적재 (FR-046), 알림 실행 (FR-041·044). 환경 변수 ADMIN_TOKEN과 같은 X-Admin-Token 헤더가 있어야 부를 수 있다."""
import secrets
from datetime import date

import httpx
from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import notifications
from app.clock import today as today_dep
from app.config import admin_token, data_go_kr_service_key
from app.db import get_db
from app.errors import api_error, responses
from app.rules.loader import get_rules
from app.schemas import NotificationOut, NotificationRunInput, NotificationRunResult, TradeCollectInput, TradeCollectResult
from app.trades.client import TradeApiError
from app.trades.collect import collect



def require_admin(x_admin_token: str | None = Header(None, description="환경 변수 ADMIN_TOKEN과 같은 값")):
    # 한 번에 공공데이터포털을 수십 번 부르므로 아무나 부르지 못하게 한다 (인증키 일일 호출 한도)
    expected = admin_token()
    if not expected:
        raise api_error(403, "ADMIN_DISABLED", "관리자 API가 꺼져 있습니다", "서버 환경 변수 ADMIN_TOKEN을 설정하세요")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise api_error(401, "ADMIN_TOKEN_INVALID", "관리자 토큰이 없거나 맞지 않습니다", "X-Admin-Token 헤더에 ADMIN_TOKEN 값을 넣으세요")


router = APIRouter(prefix="/api/admin", tags=["관리자"], dependencies=[Depends(require_admin)])


def get_http_client():
    with httpx.Client() as client:
        yield client


@router.post("/trades", response_model=TradeCollectResult, status_code=201, responses=responses(401, 403, 409, 422, 502, 503))
def collect_trades(inp: TradeCollectInput, db: Session = Depends(get_db),
                   http: httpx.Client = Depends(get_http_client)):
    key = data_go_kr_service_key()
    if not key:
        raise api_error(503, "SERVICE_KEY_MISSING", "공공데이터포털 인증키가 설정되지 않았습니다",
                        "서버 환경 변수 DATA_GO_KR_SERVICE_KEY에 Decoding 키를 넣으세요")
    end = date.fromisoformat(f"{inp.end_month}-01")
    try:
        result = collect(db, http, key, inp.lawd_cd, end, inp.months, inp.housing_types)
    except TradeApiError as e:
        raise api_error(502, "TRADE_API_ERROR", str(e), "잠시 후 다시 시도하거나 내려받은 파일로 적재하세요")
    except IntegrityError:   # 같은 거래를 동시에 수집한 다른 요청이 먼저 저장함 (uq_trades_deal_key)
        db.rollback()
        raise api_error(409, "TRADES_COLLECT_CONFLICT", "다른 수집과 겹쳐 저장하지 못했습니다",
                        "다른 수집이 끝난 뒤 다시 시도하세요. 이미 저장된 거래는 다시 저장하지 않습니다") from None
    return TradeCollectResult(
        lawd_cd=inp.lawd_cd,
        months=result.months,
        received=result.received,
        added=result.added,
        fetched_at=result.fetched_at,
    )


@router.post("/notifications/run", response_model=NotificationRunResult, responses=responses(401, 403, 422))
def run_notifications(inp: NotificationRunInput | None = None, db: Session = Depends(get_db),
                      rules: dict = Depends(get_rules), today: date = Depends(today_dep)):
    """그날 보낼 알림을 만든다 (시연용 한 번 실행). 날짜는 본문 date → X-Virtual-Today → 실제 오늘 순서로 정한다.

    같은 알림은 한 번만 만들어서 여러 번 불러도 된다. 무산된 계약·끝낸 할 일은 알리지 않는다.
    """
    day = inp.date if inp is not None and inp.date is not None else today
    created = notifications.run(db, day, rules)
    return NotificationRunResult(date=day, created=[NotificationOut(
        contract_id=n.contract_id, todo_rule_id=n.todo_rule_id, kind=n.kind, notify_date=n.notify_date,
        channel=n.channel, status=n.status, title=n.title) for n in created])
