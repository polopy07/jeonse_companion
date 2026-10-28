"""공동 계약자 알림 (FR-043, #58): 부부 계약이면 두 사람이 각자 알림 이메일을 받고, 각자 접근 링크를 받는다."""
from datetime import timedelta

import pytest

from app import mailer
from tests.test_contracts import DATES, VILLA, _check
from tests.test_email import ADMIN, EMAIL, _access_link, _run, _t5_due

CO = "partner@example.com"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    mailer.outbox.clear()


def _create(client, **body):
    return client.post("/api/contracts", json={"check_id": _check(client, VILLA)["id"], **DATES, "guarantor": "HUG",
                                               "email": EMAIL, **body})


def test_both_get_alert_email(client):
    r = _create(client, co_tenant=True, co_tenant_email=CO)
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["co_tenant"], c["co_tenant_email"]) == (True, CO)

    res = _run(client, _t5_due(c) - timedelta(days=7))
    emails = sorted((n["todo_rule_id"], n["channel"], n["status"]) for n in res["created"] if n["channel"] != "app")
    assert emails == [("T5", "email", "sent"), ("T5", "email_co", "sent")]
    assert res["email_sent"] == 2
    assert sorted(m.to for m in mailer.outbox) == sorted([EMAIL, CO])
    assert mailer.outbox[0].body == mailer.outbox[1].body   # 같은 알림
    # 같은 날 다시 실행해도 한 번만
    assert _run(client, _t5_due(c) - timedelta(days=7))["created"] == []


def test_one_address_failing_does_not_stop_other(client, monkeypatch):
    c = _create(client, co_tenant=True, co_tenant_email=CO).json()
    sent = []

    def send(mail):
        if mail.to == CO:
            raise mailer.MailError("mailbox full")
        sent.append(mail.to)

    monkeypatch.setattr(mailer, "send", send)
    res = _run(client, _t5_due(c) - timedelta(days=7))
    assert (res["email_sent"], res["email_failed"]) == (1, 1) and sent == [EMAIL]


def test_validation(client):
    r = _create(client, co_tenant_email=CO)   # 공동 계약이 아닌데 공동 계약자 이메일
    assert r.status_code == 422 and "공동 계약" in r.text
    r = _create(client, co_tenant=True, co_tenant_email="Tenant@Example.com")   # 알림 이메일과 같은 주소
    assert r.status_code == 422 and "다른 주소" in r.text
    assert _create(client, co_tenant=True, co_tenant_email="not-an-email").status_code == 422
    assert _create(client, co_tenant=True).status_code == 201   # 공동 계약이어도 이메일은 비워 둘 수 있다


def test_patch_add_and_remove(client):
    c = _create(client).json()
    url, h = f"/api/contracts/{c['id']}", {"X-Contract-Token": c["access_token"]}
    assert client.patch(url, json={"co_tenant_email": CO}, headers=h).status_code == 422   # 공동 계약이 아님
    r = client.patch(url, json={"co_tenant": True, "co_tenant_email": CO}, headers=h)
    assert r.status_code == 200 and r.json()["co_tenant_email"] == CO
    assert client.patch(url, json={"co_tenant": False}, headers=h).status_code == 422   # 이메일이 남아 있음
    r = client.patch(url, json={"co_tenant": False, "co_tenant_email": None}, headers=h)
    assert r.status_code == 200 and r.json()["co_tenant_email"] is None


def test_co_tenant_gets_own_access_link(client, monkeypatch):
    c = _create(client, co_tenant=True, co_tenant_email=CO).json()
    monkeypatch.setenv("REQUIRE_CONTRACT_AUTH", "true")
    _access_link(client, "Partner@Example.com")
    assert len(mailer.outbox) == 1 and mailer.outbox[0].to == CO
    token = mailer.outbox[0].body.split("접근 코드: ")[1].split()[0]
    assert client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": token}).status_code == 200
