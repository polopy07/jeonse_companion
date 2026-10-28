"""가상 날짜로 할 일 상태와 알림 (FR-040, FR-041, FR-044, API 명세 1.7)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import clock, mailer
from app.engine.schedule import days_left, todo_state
from tests.test_contracts import DATES, VILLA, _check

ADMIN = "test-admin-token"
D = date.fromisoformat


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    mailer.outbox.clear()


def _contract(client, email="tenant@example.com") -> dict:
    body = {"check_id": _check(client, VILLA)["id"], **DATES, "guarantor": "HUG"}
    if email:
        body["email"] = email
    r = client.post("/api/contracts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _todo(contract, rule_id) -> dict:
    return next(t for t in contract["todos"] if t["rule_id"] == rule_id)


def _run(client, day: date) -> list[dict]:
    r = client.post("/api/admin/notifications/run", json={"date": day.isoformat()}, headers={"X-Admin-Token": ADMIN})
    assert r.status_code == 200, r.text
    assert r.json()["date"] == day.isoformat()
    return r.json()["created"]


# ---- 할 일 상태 ----

def test_todo_state_rules():
    s, e = D("2026-12-01"), D("2026-12-10")
    assert todo_state("todo", s, e, None, D("2026-11-30")) == "upcoming"
    assert todo_state("todo", s, e, None, s) == "in_progress"
    assert todo_state("todo", s, e, None, e) == "in_progress"
    assert todo_state("todo", s, e, None, D("2026-12-11")) == "overdue"
    assert todo_state("done", s, e, None, D("2027-01-01")) == "done"
    assert todo_state("skipped", s, e, None, D("2027-01-01")) == "done"   # 건너뛴 할 일도 끝낸 것과 같게
    # 재알림은 알림일이 시작이자 기한
    r = D("2027-11-15")
    assert todo_state("todo", None, None, r, D("2027-11-14")) == "upcoming"
    assert todo_state("todo", None, None, r, r) == "in_progress"
    assert days_left(e, None, D("2026-12-07")) == 3
    assert days_left(e, None, D("2026-12-12")) == -2
    assert days_left(None, r, D("2027-11-05")) == 10
    assert days_left(None, None, D("2027-11-05")) is None


@pytest.fixture
def real_today(monkeypatch):
    """실제 오늘을 고정한다 (응답 뒤 다시 부른 real_today와 비교하면 한국 시간 자정을 걸칠 때 실패해서)."""
    day = D("2026-10-27")
    monkeypatch.setattr(clock, "real_today", lambda: day)
    return day


def test_virtual_today_changes_state(client, real_today):
    c = _contract(client)
    url = f"/api/contracts/{c['id']}"
    before = client.get(url, headers={"X-Virtual-Today": "2026-11-20"}).json()
    assert before["today"] == "2026-11-20"
    t3 = _todo(before, "T3")    # 잔금일 아침 등기부 재비교 (12/01)
    assert t3["state"] == "upcoming" and t3["days_left"] == 11

    on = client.get(url, headers={"X-Virtual-Today": "2026-12-01"}).json()
    assert _todo(on, "T3")["state"] == "in_progress" and _todo(on, "T3")["days_left"] == 0
    after = client.get(url, headers={"X-Virtual-Today": "2026-12-05"}).json()
    assert _todo(after, "T3")["state"] == "overdue" and _todo(after, "T3")["days_left"] == -4
    # 헤더가 없으면 실제 오늘 (한국 시간)
    assert client.get(url).json()["today"] == real_today.isoformat()
    # 형식이 틀린 가상 날짜는 422
    r = client.get(url, headers={"X-Virtual-Today": "2026-1-8"})
    assert r.status_code == 422 and r.json()["detail"]["fields"][0]["message"] == "YYYY-MM-DD 형식으로 입력하세요"


def test_virtual_today_off_on_deploy(client, monkeypatch, real_today):
    # 배포 서버(ALLOW_VIRTUAL_TODAY=false)는 헤더를 무시하고 실제 오늘로 계산한다 (#92 리뷰)
    c = _contract(client)
    t3 = _todo(c, "T3")["id"]
    on = client.patch(f"/api/todos/{t3}", json={"status": "skipped", "done_date": "2026-12-05"},
                      headers={"X-Contract-Token": c["access_token"], "X-Virtual-Today": "2026-12-10"})
    assert on.status_code == 200, on.text
    client.patch(f"/api/todos/{t3}", json={"status": "todo"}, headers={"X-Contract-Token": c["access_token"]})

    monkeypatch.setenv("ALLOW_VIRTUAL_TODAY", "false")
    for header in ("2030-01-01", "2026-1-8", ""):   # 형식이 틀린 값도 422 없이 무시
        got = client.get(f"/api/contracts/{c['id']}", headers={"X-Virtual-Today": header})
        assert got.status_code == 200 and got.json()["today"] == real_today.isoformat()
    # 계약 전 확인의 기준일, 할 일 끝낸 날 검사도 실제 오늘 기준 (#95 리뷰)
    apt = {"housing_type": "apartment", "deposit": 2 * 10**8, "official_price": 3 * 10**8, "exclusive_area": 84.9,
           "registry": {}, "complex": {"lawd_cd": "26350", "umd_name": "우동", "complex_name": "가상해운대아파트"}}
    check = client.post("/api/checks", json=apt, headers={"X-Virtual-Today": "2030-01-01"}).json()   # 단지 정보가 있어야 as_of
    assert check["as_of"] == real_today.isoformat()
    off = client.patch(f"/api/todos/{t3}", json={"status": "skipped", "done_date": "2026-12-05"},
                       headers={"X-Contract-Token": c["access_token"], "X-Virtual-Today": "2026-12-10"})
    assert off.status_code == 422   # 실제 오늘(10/27)보다 뒤


def test_real_today_is_korea_time(monkeypatch):
    # UTC 10/26 16:30 = 한국 10/27 01:30 → 오늘은 10/27 (#92 리뷰: 서버가 UTC여도 하루 어긋나지 않게)
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26, 16, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", FakeDatetime)
    assert clock.real_today() == D("2026-10-27")


# ---- 알림 실행 ----

def test_return_guarantee_email_ac010(client):
    c = _contract(client)
    due = D(_todo(c, "T5")["due_date"])
    created = _run(client, due - timedelta(days=7))
    t5 = [n for n in created if n["todo_rule_id"] == "T5" and n["kind"] == "due_before"]
    assert {(n["channel"], n["status"]) for n in t5} == {("app", "sent"), ("email", "sent")}
    assert "7일 전" in t5[0]["title"]
    # 반환보증 가입 마감 이메일이 실제로 나감 (AC-010)
    mail = next(m for m in mailer.outbox if "반환보증" in m.subject)
    assert mail.to == "tenant@example.com" and "7일 전" in mail.subject
    assert f"기한: {due.isoformat()}" in mail.body and "보조 수단" in mail.body
    # 같은 날 다시 불러도 다시 만들지 않는다
    assert _run(client, due - timedelta(days=7)) == []


def test_remind_t6(client):
    c = _contract(client)
    remind = D(_todo(c, "T6")["remind_date"])
    created = _run(client, remind)
    t6 = {n["channel"]: n for n in created if n["todo_rule_id"] == "T6"}
    assert t6["email"]["kind"] == "remind" and t6["email"]["status"] == "sent"
    assert t6["app"]["title"] == _todo(c, "T6")["title"]


def test_start_notice_app_only(client):
    c = _contract(client)
    t3 = _todo(c, "T3")
    created = _run(client, D(t3["start_date"]))
    t3_notes = [n for n in created if n["todo_rule_id"] == "T3"]
    assert ("start", t3["start_date"]) in {(n["kind"], n["notify_date"]) for n in t3_notes}
    assert {n["channel"] for n in t3_notes} == {"app"}   # 이메일은 반환보증만 (MVP 1종)


def test_catch_up_window(client):
    c = _contract(client)
    due = D(_todo(c, "T5")["due_date"])
    # 7일 전·1일 전 둘 다 지나간 날(기한 하루 뒤)에 처음 실행: 7일 안에 있는 1일 전 알림만
    created = _run(client, due + timedelta(days=1))
    kinds = {(n["kind"], n["notify_date"]) for n in created if n["todo_rule_id"] == "T5" and n["channel"] == "email"}
    assert kinds == {("due_before", (due - timedelta(days=1)).isoformat())}
    # 몇 달 건너뛰면 지난 알림은 쏟아지지 않는다
    assert [n for n in _run(client, due + timedelta(days=120)) if n["todo_rule_id"] == "T5"] == []


def test_no_email_is_skipped(client):
    c = _contract(client, email=None)
    due = D(_todo(c, "T5")["due_date"])
    email = [n for n in _run(client, due - timedelta(days=1)) if n["channel"] == "email"]
    assert email and all(n["status"] == "skipped" for n in email)


def test_done_and_cancelled_are_not_notified(client):
    c = _contract(client)
    t3 = _todo(c, "T3")
    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    assert [n for n in _run(client, D(t3["start_date"])) if n["contract_id"] == c["id"]] == []


def test_virtual_today_header_for_run(client):
    c = _contract(client)
    day = D(_todo(c, "T3")["start_date"])
    r = client.post("/api/admin/notifications/run", headers={"X-Admin-Token": ADMIN, "X-Virtual-Today": day.isoformat()})
    assert r.status_code == 200 and r.json()["date"] == day.isoformat()
    assert any(n["todo_rule_id"] == "T3" for n in r.json()["created"])


def test_run_needs_admin(client):
    assert client.post("/api/admin/notifications/run", json={}).status_code == 401
