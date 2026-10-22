"""이메일 보내기 (FR-041, NFR-008). EMAIL_BACKEND로 고른다.

- console(기본): 보내지 않고 서버 로그에만 찍는다. 로컬 개발·시연 리허설
- smtp: 실제로 보낸다 (SMTP_HOST·SMTP_PORT·SMTP_USER·SMTP_PASSWORD·SMTP_FROM, SMTP_STARTTLS 기본 true)
- memory: 테스트용. outbox에 쌓는다
"""
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class Mail:
    to: str
    subject: str
    body: str


outbox: list[Mail] = []   # memory 백엔드


class MailError(Exception):
    """보내지 못함. 문구에 비밀번호·서버 주소는 넣지 않는다."""


def backend() -> str:
    return os.environ.get("EMAIL_BACKEND", "console").strip().lower()


def send(mail: Mail) -> None:
    match backend():
        case "memory":
            outbox.append(mail)
        case "smtp":
            _send_smtp(mail)
        case _:
            logger.info("이메일 (console, 보내지 않음) to=%s subject=%s\n%s", mail.to, mail.subject, mail.body)


def _send_smtp(mail: Mail) -> None:
    host = os.environ.get("SMTP_HOST", "")
    sender = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    if not host or not sender:
        raise MailError("SMTP 설정이 없습니다 (SMTP_HOST, SMTP_FROM)")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, mail.to, mail.subject
    msg.set_content(mail.body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as smtp:
            if os.environ.get("SMTP_STARTTLS", "true").strip().lower() in ("1", "true", "yes", "on"):
                smtp.starttls()
            user = os.environ.get("SMTP_USER")
            if user:
                smtp.login(user, os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        raise MailError(type(e).__name__) from None
