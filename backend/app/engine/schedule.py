"""오늘 기준 할 일 상태와 알림 시점 (FR-040, FR-041, FR-044, todos.yaml notifications).

오늘은 실제 날짜이거나 가상 날짜(시연)다. 기한은 할 일 엔진이 정하고, 여기서는 그 날짜와 오늘만 비교한다.
"""
from dataclasses import dataclass
from datetime import date, timedelta


def todo_state(status: str, start: date | None, due: date | None, remind: date | None, today: date) -> str:
    """done(끝냄) / upcoming(시작 전) / in_progress(할 때) / overdue(기한 지남).

    재알림(T6·T8)은 알림일(remind)이 시작이자 기한이다.
    """
    if status == "done":
        return "done"
    start = remind or start
    end = remind or due
    if start is not None and today < start:
        return "upcoming"
    if end is not None and today > end:
        return "overdue"
    return "in_progress"


def days_left(due: date | None, remind: date | None, today: date) -> int | None:
    """기한(재알림이면 알림일)까지 남은 날. 지났으면 음수, 기한이 없으면 None."""
    target = remind or due
    return None if target is None else (target - today).days


@dataclass
class Notice:
    kind: str          # start / due_before / remind
    notify_date: date
    days_before: int | None = None


def notices(start: date | None, due: date | None, remind: date | None, rule: dict) -> list[Notice]:
    """할 일 1개에서 생기는 알림 (todos.yaml notifications)."""
    out = []
    if remind is not None:
        out.append(Notice("remind", remind))
    elif rule.get("on_start") and start is not None:
        out.append(Notice("start", start))
    if due is not None:
        out += [Notice("due_before", due - timedelta(days=d), d) for d in rule.get("due_before_days", [])]
    return out


def due_on(notice: Notice, today: date, catch_up_days: int) -> bool:
    """오늘 보낼 알림인가. 알림일이 지났어도 catch_up_days 안이면 보낸다 (알림 실행을 건너뛴 날)."""
    return today - timedelta(days=catch_up_days) < notice.notify_date <= today
