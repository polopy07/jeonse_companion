"""할 일 기한 → 캘린더 구독 파일 (ICS, FR-042, #47).

앱의 ICS 내보내기(frontend/src/lib/ics.ts, #102)와 같은 규칙으로 만든다. 같은 계약·할 일은 같은 UID라
앱에서 내보낸 일정과 구독 일정이 캘린더에서 겹치지 않고 바뀐다.
- 끝나지 않은 할 일마다 하루 종일 일정 1개: 기한이 있으면 기한일, 재알림(T6·T8)은 알림일, 둘 다 없으면 만들지 않음
- 알림은 todos.yaml notifications.due_before_days(7·1일 전) 오전 9시 (하루 종일 일정은 그날 0시 기준)
- 집 주소·이름은 넣지 않는다 (구독 주소가 새도 집을 알 수 없게)
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

NOTICE = "알림은 보조 수단이에요. 기한은 앱의 할 일 목록과 보증기관 안내를 함께 확인하세요."
CALENDAR_NAME = "전동기 할 일"


@dataclass
class CalendarTodo:
    rule_id: str
    title: str
    detail: str | None
    start_date: date | None
    due_date: date | None
    remind_date: date | None
    status: str


def escape_text(s: str) -> str:
    """텍스트 값 이스케이프 (RFC 5545 3.3.11)."""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """한 줄이 75바이트를 넘으면 접는다 (RFC 5545 3.1). 한글이 바이트 중간에서 잘리지 않게 글자 단위로 센다."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (74 if out else 75):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def alarm_triggers(due_before_days: list[int]) -> list[str]:
    """기한 N일 전 오전 9시: 하루 종일 일정 0시에서 (N−1)일 15시간 전."""
    return [f"-P{d - 1}DT15H" if d > 1 else "-PT15H" for d in due_before_days]


def _event_day(t: CalendarTodo) -> date | None:
    return t.due_date or t.remind_date


def _event(contract_id: int, t: CalendarTodo, day: date, stamp: str, triggers: list[str]) -> list[str]:
    detail = [f"{t.start_date.isoformat()}부터 할 수 있어요." if t.start_date and t.start_date != day else None,
              t.detail, NOTICE]
    lines = [
        "BEGIN:VEVENT",
        f"UID:jeonse-{contract_id}-{t.rule_id}@jeonse-companion",   # 앱 내보내기와 같은 UID
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{escape_text(f'[전동기] {t.title}')}",
        f"DESCRIPTION:{escape_text(chr(10).join(d for d in detail if d))}",
        "TRANSP:TRANSPARENT",
    ]
    for trigger in triggers:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape_text(t.title)}", f"TRIGGER:{trigger}",
                  "END:VALARM"]
    return lines + ["END:VEVENT"]


def build_ics(contract_id: int, todos: list[CalendarTodo], due_before_days: list[int],
              now: datetime | None = None) -> str:
    """끝나지 않은 할 일 → ICS 본문 (줄바꿈 CRLF). 할 일이 없으면 일정 없는 캘린더 (구독한 일정이 지워진다)."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    triggers = alarm_triggers(due_before_days)
    events = [line for t in todos if t.status == "todo" and _event_day(t)
              for line in _event(contract_id, t, _event_day(t), stamp, triggers)]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jeonse-companion//todos//KO", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{escape_text(CALENDAR_NAME)}", *events, "END:VCALENDAR"]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
