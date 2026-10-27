"""알림 실행: 그날 보낼 알림을 만든다 (FR-040, FR-041, FR-044, todos.yaml notifications).

시연에서는 POST /api/admin/notifications/run으로 가상 날짜를 넘겨 부르고, 출시 때는 서버 안 스케줄러가 매일 부른다.
같은 할 일·종류·알림일·경로는 한 번만 만든다. 이메일은 pending으로 만든 뒤 deliver가 보낸다.
보내지 못하면 failed로 남기고 다음 실행에서 MAX_ATTEMPTS번까지 다시 보낸다 (NFR-008).
"""
import logging
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import mailer
from app.engine.schedule import Notice, due_on, notices
from app.models import Contract, Notification, Todo

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
DONE = ("done", "skipped")   # 알리지 않는 할 일 상태


def _title(todo: Todo, notice: Notice) -> str:
    if notice.kind == "evidence":
        return f"증빙을 아직 안 올렸어요: {todo.title} ({todo.evidence})"
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

    evidence_after = cfg.get("evidence_after_days")
    created = []

    def add(c: Contract, t: Todo, n: Notice, channels: list[str]) -> None:
        for channel in channels:
            key = (c.id, t.rule_id, n.kind, n.notify_date, channel)
            if key in made:
                continue
            made.add(key)
            status = "sent" if channel == "app" else ("pending" if c.email else "skipped")
            row = Notification(contract_id=c.id, todo_rule_id=t.rule_id, kind=n.kind, notify_date=n.notify_date,
                               channel=channel, status=status, title=_title(t, n))
            db.add(row)
            created.append(row)

    for c in contracts:   # 무산된 계약은 알림을 보내지 않는다 (FR-016)
        for t in c.todos:
            # 나중에 올리기(FR-030): 나중에 올리기로 바꾼 날(증빙을 지운 날)로부터 며칠 뒤 증빙을 올리라고 다시 알린다
            # (앱 안 알림만). 끝낸 날 기준이면 예전 날짜로 끝내거나 오래된 증빙을 지웠을 때 따라잡기 창을 넘겨 안 간다
            skipped_on = t.skipped_date or t.done_date
            if (evidence_after is not None and t.status == "skipped" and t.evidence and not t.evidence_path
                    and skipped_on is not None):
                n = Notice("evidence", skipped_on + timedelta(days=evidence_after))
                if due_on(n, day, catch_up):
                    add(c, t, n, ["app"])
            if t.status in DONE:
                continue
            for n in notices(t.start_date, t.due_date, t.remind_date, cfg):
                if due_on(n, day, catch_up):
                    add(c, t, n, ["app"] + (["email"] if t.rule_id in email_todos else []))
    db.commit()
    return created


def _email_body(todo: Todo, n: Notification, rules: dict) -> str:
    when = todo.remind_date or todo.due_date
    lines = ["안녕하세요, 전동기입니다.", "", n.title, "", f"- 할 일: {todo.title}"]
    if when is not None:
        lines.append(f"- {'알림일' if todo.remind_date else '기한'}: {when.isoformat()}")
    if todo.detail:
        lines.append(f"- 안내: {todo.detail}")
    lines += ["", "앱의 할 일 목록에서 자세한 내용을 보고, 끝내면 증빙 사진을 올려 주세요.",
              "이 알림은 보조 수단이에요. 기한은 앱의 할 일 목록과 보증기관 안내를 함께 확인하세요."]
    disclaimer = rules["verdict"].get("display", {}).get("disclaimer")
    if disclaimer:
        lines += ["", disclaimer]
    return "\n".join(lines)


def deliver(db: Session, day: date, rules: dict) -> tuple[int, int]:
    """보내지 않은 이메일 알림(pending, 다시 보낼 failed)을 보낸다. (보냄, 실패) 수를 돌려준다.

    알림일이 catch_up_days보다 오래된 것은 문구(남은 날)가 지났으므로 보내지 않는다. 메일마다 저장해서,
    중간에 예외가 나도 이미 보낸 메일이 다음 실행에서 또 나가지 않게 한다.
    """
    since = day - timedelta(days=rules["todos"]["notifications"].get("catch_up_days", 1))
    rows = db.scalars(select(Notification).where(
        Notification.channel == "email",
        or_(Notification.status == "pending",
            (Notification.status == "failed") & (Notification.attempts < MAX_ATTEMPTS)),
    ).order_by(Notification.id)).all()
    sent = failed = 0
    for n in rows:
        contract = db.get(Contract, n.contract_id)
        todo = next((t for t in contract.todos if t.rule_id == n.todo_rule_id), None) if contract else None
        if (contract is None or contract.status == "cancelled" or not contract.email or todo is None
                or todo.status in DONE or n.notify_date <= since):
            n.status = "skipped"   # 그사이 무산·완료·이메일 삭제, 또는 너무 지난 알림
            db.commit()
            continue
        n.attempts = (n.attempts or 0) + 1
        try:
            mailer.send(mailer.Mail(contract.email, f"[전동기] {n.title}", _email_body(todo, n, rules)))
        except mailer.MailError as e:
            n.status, n.last_error = "failed", str(e)[:200]
            failed += 1
            logger.warning("알림 이메일 실패 (알림 %s, %s번째): %s", n.id, n.attempts, e)
        else:
            n.status, n.last_error = "sent", None
            sent += 1
        db.commit()
    return sent, failed
