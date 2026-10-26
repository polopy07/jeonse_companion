"""역전세 경보 리포트 (FR-036~038, UI-09)."""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app import alerts
from app.api.contracts import TOKEN_HEADER_DESC, _contract_for
from app.db import get_db
from app.errors import api_error, responses
from app.models import Verdict
from app.rules.loader import get_rules
from app.schemas import AlertReportOut

router = APIRouter(prefix="/api/contracts", tags=["역전세 경보"])

_POINT = ("as_of", "level", "estimated_price", "deposit_ratio")


@router.get("/{contract_id}/alerts/latest", response_model=AlertReportOut, responses=responses(404))
def latest_alert(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """최근 경보 단계·계산 근거·기준일. 재계산한 적이 없으면 계약을 시작할 때의 값. 무산된 계약도 볼 수 있다."""
    row = _contract_for(contract_id, x_contract_token, db)
    check = db.get(Verdict, row.check_id)
    points = [] if check is None else alerts.history(row, check, rules)
    if not points:
        raise api_error(404, "NOT_FOUND", "경보를 계산하지 않는 계약입니다",
                        "다가구·단독 등 공시가격이 없는 집은 역전세 경보 대상이 아닙니다")
    last, prev = points[-1], (points[-2] if len(points) > 1 else None)
    label = next((lv["label"] for lv in rules["alert"]["levels"] if lv["id"] == last["level"]), None)
    return AlertReportOut(
        contract_id=row.id,
        **{k: last[k] for k in _POINT},
        label=label,
        recalculated=len(points) > 1,
        previous_level=prev["level"] if prev else None,
        previous_ratio=prev["deposit_ratio"] if prev else None,
        basis=last["basis"],
        history=[{k: p[k] for k in _POINT} for p in points],
        data_limits=rules["alert"]["recalculation"].get("data_limits", []),
    )
