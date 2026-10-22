"""이메일 발송·재시도(FR-041, NFR-008)와 접근 링크 이메일로 다시 받기(#39)."""
from datetime import date, timedelta

import pytest

from app import mailer
from tests.test_contracts import DATES, VILLA, _check

ADMIN = "test-admin-token"
EMAIL = "tenant@example.com"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    mailer.outbox.clear()


def _contract(client, email=EMAIL) -> dict:
    r = client.post("/api/contracts", json={"check_id": _check(client, VILLA)["id"], **DATES, "guarantor": "HUG",
                                            "email": email})
    assert r.status_code == 201, r.text
    return r.json()


def _run(client, day: date) -> dict:
    r = client.post("/api/admin/notifications/run", json={"date": day.isoformat()}, headers={"X-Admin-Token": ADMIN})
    assert r.status_code == 200, r.text
    return r.json()


def _t5_due(contract) -> date:
    return date.fromisoformat(next(t for t in contract["todos"] if t["rule_id"] == "T5")["due_date"])


# ---- 알림 이메일 ----

def test_failed_email_is_retried(client, monkeypatch):
    c = _contract(client)
    day = _t5_due(c) - timedelta(days=7)

    def boom(mail):
        raise mailer.MailError("SMTPConnectError")

    monkeypatch.setattr(mailer, "send", boom)
    first = _run(client, day)
    assert first["email_failed"] == 1 and first["email_sent"] == 0
    assert [n["status"] for n in first["created"] if n["channel"] == "email"] == ["failed"]

    monkeypatch.undo()
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    again = _run(client, day)   # 새로 만들 알림은 없고, 실패한 이메일만 다시 보낸다
    assert again["created"] == [] and again["email_sent"] == 1
    assert len(mailer.outbox) == 1


def test_retry_stops_after_three(client, monkeypatch):
    c = _contract(client)
    day = _t5_due(c) - timedelta(days=7)
    calls = []

    def boom(mail):
        calls.append(mail)
        raise mailer.MailError("SMTPConnectError")

    monkeypatch.setattr(mailer, "send", boom)
    for _ in range(5):
        _run(client, day)
    assert len(calls) == 3


def test_cancelled_before_send_is_skipped(client, monkeypatch):
    c = _contract(client)
    day = _t5_due(c) - timedelta(days=7)
    monkeypatch.setattr(mailer, "send", lambda mail: (_ for _ in ()).throw(mailer.MailError("x")))
    _run(client, day)                                 # 실패로 남김
    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    monkeypatch.setattr(mailer, "send", lambda mail: mailer.outbox.append(mail))
    assert _run(client, day)["email_sent"] == 0       # 무산된 계약에는 다시 보내지 않는다
    assert mailer.outbox == []


def test_console_backend_does_not_send(client, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    c = _contract(client)
    out = _run(client, _t5_due(c) - timedelta(days=7))
    assert out["email_sent"] == 1 and mailer.outbox == []   # 서버 로그에만 찍힘


def test_smtp_without_settings_fails(client, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    c = _contract(client)
    out = _run(client, _t5_due(c) - timedelta(days=7))
    assert out["email_failed"] == 1


# ---- 접근 링크 다시 받기 ----

def _access_link(client, email):
    r = client.post("/api/contracts/access-link", json={"email": email})
    assert r.status_code == 202, r.text
    return r.json()


def test_access_link_gives_new_token(client, monkeypatch):
    c = _contract(client)
    monkeypatch.setenv("REQUIRE_CONTRACT_AUTH", "true")   # 토큰이 꼭 있어야 하는 서버
    res = _access_link(client, "Tenant@Example.com")   # 대소문자 무시
    assert len(mailer.outbox) == 1
    mail = mailer.outbox[0]
    assert mail.to == EMAIL and f"계약 {c['id']}" in mail.body
    token = mail.body.split("접근 코드: ")[1].split()[0]
    url = f"/api/contracts/{c['id']}"
    assert client.get(url, headers={"X-Contract-Token": token}).status_code == 200
    # 처음 휴대폰의 토큰도 그대로 쓸 수 있다
    assert client.get(url, headers={"X-Contract-Token": c["access_token"]}).status_code == 200
    # 없는 이메일도 같은 응답, 메일은 안 감
    assert _access_link(client, "nobody@example.com") == res
    assert len(mailer.outbox) == 1


def test_access_link_rate_limit_and_cancelled(client):
    c = _contract(client)
    for _ in range(5):
        _access_link(client, EMAIL)
    assert len(mailer.outbox) == 3   # 계약마다 한 시간에 3번
    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    mailer.outbox.clear()
    other = _contract(client, email="other@example.com")
    client.post(f"/api/contracts/{other['id']}/cancel", headers={"X-Contract-Token": other["access_token"]})
    _access_link(client, "other@example.com")
    assert mailer.outbox == []       # 무산된 계약은 보내지 않음


def test_access_link_uses_app_link(client, monkeypatch):
    monkeypatch.setenv("APP_LINK_BASE", "jeonse://contract")
    c = _contract(client)
    _access_link(client, EMAIL)
    assert f"jeonse://contract?contract={c['id']}&token=" in mailer.outbox[0].body


def test_access_link_mail_failure_keeps_no_token(client, monkeypatch):
    _contract(client)
    monkeypatch.setattr(mailer, "send", lambda mail: (_ for _ in ()).throw(mailer.MailError("x")))
    _access_link(client, EMAIL)
    monkeypatch.setattr(mailer, "send", lambda mail: mailer.outbox.append(mail))
    for _ in range(3):
        _access_link(client, EMAIL)
    assert len(mailer.outbox) == 3   # 실패한 요청은 횟수에 넣지 않음


def test_access_link_bad_email(client):
    assert client.post("/api/contracts/access-link", json={"email": "not-an-email"}).status_code == 422
