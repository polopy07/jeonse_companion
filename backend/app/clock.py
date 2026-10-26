"""오늘 날짜. 시연·테스트용 가상 날짜(X-Virtual-Today)를 주면 그날을 오늘로 본다 (FR-044, API 명세 1.7).

실제 오늘은 한국 시간 기준이다. 서버가 UTC여도 00:00~09:00에 하루 전 날짜로 계산하지 않게.
배포 서버는 ALLOW_VIRTUAL_TODAY=false로 가상 날짜를 끈다 (아무 앱이나 다른 날짜 기준 결과를 받지 않게).
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import Header

from app.config import allow_virtual_today

KST = timezone(timedelta(hours=9))   # 한국은 서머타임이 없어 고정 오프셋으로 충분
VIRTUAL_TODAY_DESC = "시연용 가상 날짜 YYYY-MM-DD (API 명세 1.7). 없거나 서버가 끈 경우(ALLOW_VIRTUAL_TODAY=false) 실제 오늘"


def real_today() -> date:
    return datetime.now(KST).date()


def today(x_virtual_today: date | None = Header(None, description=VIRTUAL_TODAY_DESC)) -> date:
    if x_virtual_today is not None and allow_virtual_today():
        return x_virtual_today
    return real_today()
