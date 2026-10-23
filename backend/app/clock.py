"""오늘 날짜. 시연·테스트용 가상 날짜(X-Virtual-Today)를 주면 그날을 오늘로 본다 (FR-044, API 명세 1.7)."""
from datetime import date

from fastapi import Header

VIRTUAL_TODAY_DESC = "시연용 가상 날짜 YYYY-MM-DD (API 명세 1.7). 없으면 실제 오늘"


def today(x_virtual_today: date | None = Header(None, description=VIRTUAL_TODAY_DESC)) -> date:
    return x_virtual_today or date.today()
