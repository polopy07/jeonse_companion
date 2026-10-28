"""오늘 날짜. 시연·테스트용 가상 날짜(X-Virtual-Today)를 주면 그날을 오늘로 본다 (FR-044, API 명세 1.7).

실제 오늘은 한국 시간 기준이다. 서버가 UTC여도 00:00~09:00에 하루 전 날짜로 계산하지 않게.
배포 서버는 ALLOW_VIRTUAL_TODAY=false로 가상 날짜를 끈다 (아무 앱이나 다른 날짜 기준 결과를 받지 않게).
시연을 배포 서버에서 하면 시연 서버는 true로 둔다 (가상 날짜 5분 시연).
"""
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import Header
from fastapi.exceptions import RequestValidationError

from app.config import allow_virtual_today

KST = timezone(timedelta(hours=9))   # 한국은 서머타임이 없어 고정 오프셋으로 충분
VIRTUAL_TODAY_DESC = "시연용 가상 날짜 YYYY-MM-DD (API 명세 1.7). 없거나 서버가 끈 경우(ALLOW_VIRTUAL_TODAY=false) 실제 오늘"


def real_today() -> date:
    return datetime.now(KST).date()


def today(x_virtual_today: str | None = Header(None, description=VIRTUAL_TODAY_DESC)) -> date:
    # 문자열로 받아 켜져 있을 때만 읽는다: 끈 서버는 형식이 틀린 값도 422 없이 무시한다
    if x_virtual_today is None or not allow_virtual_today():
        return real_today()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x_virtual_today):   # fromisoformat은 20261108도 받아서
            raise ValueError
        return date.fromisoformat(x_virtual_today)
    except ValueError:
        raise RequestValidationError([{"type": "date_parsing", "loc": ("header", "x-virtual-today"),
                                       "input": x_virtual_today, "msg": "Input should be a valid date"}]) from None
