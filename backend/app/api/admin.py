"""관리자: 공공 데이터 적재 (FR-046). MVP는 관리자 인증 없이 로컬·시연 서버에서만 쓴다."""
from datetime import date

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import data_go_kr_service_key
from app.db import get_db
from app.errors import api_error, responses
from app.schemas import TradeCollectInput, TradeCollectResult
from app.trades.client import TradeApiError
from app.trades.collect import collect

router = APIRouter(prefix="/api/admin", tags=["관리자"])


def get_http_client():
    with httpx.Client() as client:
        yield client


@router.post("/trades", response_model=TradeCollectResult, status_code=201, responses=responses(422, 502, 503))
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
    return TradeCollectResult(
        lawd_cd=inp.lawd_cd,
        months=result.months,
        received=result.received,
        added=result.added,
        fetched_at=result.fetched_at,
    )
