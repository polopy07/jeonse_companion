"""알림 실행: 그날 보낼 알림을 만든다 (FR-040, FR-041, FR-044, todos.yaml notifications).

시연에서는 POST /api/admin/notifications/run으로 가상 날짜를 넘겨 부르고, 출시 때는 서버 안 스케줄러가 매일 부른다.
같은 할 일·종류·알림일·경로는 한 번만 만든다. 이메일은 pending으로 남기고 발송은 이메일 기능이 맡는다.
"""
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.engine.schedule import Notice, due_on, notices
from app.models import Contract, Notification, Todo


def _title(todo: Todo, notice: Notice) -> str:
    if notice.kind == "remind":
        return todo.title
    if notice.kind == "start":
        return f"오늘부터: {todo.title}"
    return f"{todo.title} — 기한 {notice.days_before}일 전 ({todo.due_date.isoformat()}까지)"


def run(db: Session, day: date, rules: dict) -> list[Notification]:
    cfg = rules["todos"]["notifications"]
    catch_up = cfg.get("catch_up_days", 1)
    email_todos = set(cfg.get("email_todos", []))
    contracts = db.scalars(select(Contract).where(or_(Contract.status == "active", Contract.status.is_(None)))).all()
    # 이미 만든 알림 (catch_up 안의 것만 보면 된다)
    since = day - timedelta(days=catch_up)
    made = {
        (n.contract_id, n.todo_rule_id, n.kind, n.notify_date, n.channel)
        for n in db.scalars(select(Notification).where(Notification.notify_date > since))
    }

    created = []
    for c in contracts:   # 무산된 계약은 알림을 보내지 않는다 (FR-016)
        for t in c.todos:
            if t.status == "done":
                continue
            for n in notices(t.start_date, t.due_date, t.remind_date, cfg):
                if not due_on(n, day, catch_up):
                    continue
                for channel in ["app"] + (["email"] if t.rule_id in email_todos else []):
                    key = (c.id, t.rule_id, n.kind, n.notify_date, channel)
                    if key in made:
                        continue
                    made.add(key)
                    status = "sent" if channel == "app" else ("pending" if c.email else "skipped")
                    row = Notification(contract_id=c.id, todo_rule_id=t.rule_id, kind=n.kind, notify_date=n.notify_date,
                                       channel=channel, status=status, title=_title(t, n))
                    db.add(row)
                    created.append(row)
    db.commit()
    return created
