"""할 일 완료·나중에 올리기·되돌리기 (PATCH /api/todos/{id}, FR-020, FR-029·030, #43)."""
from datetime import date

from app.db import get_sessionmaker
from app.models import Contract, Todo
from tests.test_contract_patch import EOK, _contract

APT = {   # 연동 규칙 없음 → 2번(보증 가입 여부 확정)은 1번(임대차 신고)을 끝내야 시작 (FR-020)
    "housing_type": "apartment", "deposit": 200_000_000, "official_price": 3 * EOK, "exclusive_area": 84.9,
    "registry": {"mortgage": False},
}
DATES = {"contract_date": "2026-11-02", "balance_date": "2026-12-01", "end_date": "2028-11-30"}


def _todo(contract: dict, rule_id: str) -> dict:
    return next(t for t in contract["todos"] if t["rule_id"] == rule_id)


def _set(client, contract: dict, rule_id: str, body: dict, day: str = "2026-12-05"):
    return client.patch(f"/api/todos/{_todo(contract, rule_id)['id']}", json=body,
                        headers={"X-Contract-Token": contract["access_token"], "X-Virtual-Today": day})


def _apt_contract(client) -> dict:
    check = client.post("/api/checks", json=APT).json()
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "guarantor": "HUG"})
    assert r.status_code == 201, r.text
    return r.json()


def _detail(r) -> dict:
    return r.json()["detail"]


def test_skip_finishes_todo_and_moves_later_dates(client):
    # 나중에 올리기: 완료로 치고(기록함만 빈칸) 끝낸 날이 뒤 할 일의 기준일 (대출 없음: 전입신고 다음 날 → T5)
    c = _contract(client)
    r = _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-03"})
    assert r.status_code == 200, r.text
    t4, t5 = _todo(r.json(), "T4"), _todo(r.json(), "T5")
    assert (t4["status"], t4["done_date"], t5["start_date"]) == ("skipped", "2026-12-03", "2026-12-04")
    assert r.json()["today"] == "2026-12-05"

    # 계약 조건을 바꿔 다시 계산해도 나중에 올리기 한 할 일의 끝낸 날은 그대로 기준일
    r = client.patch(f"/api/contracts/{c['id']}", json={"email": "tenant@example.com"},
                     headers={"X-Contract-Token": c["access_token"]})
    assert _todo(r.json(), "T5")["start_date"] == "2026-12-04"


def test_done_needs_evidence(client):
    # FR-029: 증빙이 필요한 할 일은 증빙을 올려야 완료. 아직이면 나중에 올리기로 안내
    c = _contract(client)
    r = _set(client, c, "T4", {"status": "done"})
    assert r.status_code == 409 and _detail(r)["code"] == "EVIDENCE_REQUIRED"
    assert "나중에 올리기" in _detail(r)["hint"]

    with get_sessionmaker()() as db:
        db.get(Todo, _todo(c, "T4")["id"]).evidence_path = "records/t4.jpg"
        db.commit()
    r = _set(client, c, "T4", {"status": "done"})
    assert r.status_code == 200, r.text
    t4 = _todo(r.json(), "T4")
    assert (t4["status"], t4["evidence"]) == ("done", "확정일자 받은 계약서")
    assert _todo(r.json(), "T5")["start_date"] == "2026-12-06"   # 끝낸 날 = 오늘(가상 날짜 12/05)


def test_prerequisite_and_undo_order(client):
    c = _apt_contract(client)
    assert _todo(c, "T2")["prerequisites"] == ["T1"]

    r = _set(client, c, "T2", {"status": "skipped"}, day="2026-11-10")
    assert r.status_code == 409 and _detail(r)["code"] == "PREREQUISITE_NOT_DONE"
    assert _todo(c, "T1")["title"] in _detail(r)["message"]

    assert _set(client, c, "T1", {"status": "skipped"}, day="2026-11-10").status_code == 200
    assert _set(client, c, "T2", {"status": "skipped"}, day="2026-11-12").status_code == 200

    # 되돌리기는 뒤 할 일부터
    r = _set(client, c, "T1", {"status": "todo"}, day="2026-11-12")
    assert r.status_code == 409 and _detail(r)["code"] == "DEPENDENT_DONE"
    assert _set(client, c, "T2", {"status": "todo"}, day="2026-11-12").status_code == 200
    r = _set(client, c, "T1", {"status": "todo"}, day="2026-11-12")
    assert r.status_code == 200
    t1 = _todo(r.json(), "T1")
    assert (t1["status"], t1["done_date"]) == ("todo", None)


def test_balance_day_todos_not_before_start(client):
    # 잔금일 아침 재비교(T3)·전입신고(T4)는 잔금일 전 날짜로 끝내면 곧 다시 할 일로 돌아가므로 막는다
    c = _contract(client)
    r = _set(client, c, "T3", {"status": "skipped"}, day="2026-11-20")
    assert r.status_code == 409 and _detail(r)["code"] == "TODO_NOT_STARTED"
    assert "2026-12-01" in _detail(r)["message"]
    r = _set(client, c, "T3", {"status": "skipped", "done_date": "2026-11-30"}, day="2026-12-02")
    assert r.status_code == 409
    assert _set(client, c, "T3", {"status": "skipped"}, day="2026-12-01").status_code == 200


def test_done_date_not_after_today(client):
    c = _contract(client)
    r = _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-06"}, day="2026-12-05")
    assert r.status_code == 422
    assert r.json()["detail"]["fields"][0]["field"] == "done_date"
    r = _set(client, c, "T4", {"status": "finished"})
    assert r.status_code == 422


def test_access_and_cancelled(client):
    c = _contract(client)
    t4 = _todo(c, "T4")["id"]
    r = client.patch(f"/api/todos/{t4}", json={"status": "skipped"}, headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404
    assert client.patch("/api/todos/999999", json={"status": "skipped"}).status_code == 404

    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    r = _set(client, c, "T4", {"status": "skipped"})
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"


def test_done_date_not_before_contract_date(client):
    # #101 리뷰 1번: 끝낸 날은 뒤 할 일의 기준일이라 계약일보다 앞서면 막는다
    c = _contract(client)
    r = _set(client, c, "T2", {"status": "skipped", "done_date": "2020-01-01"}, day="2026-11-10")
    assert r.status_code == 422
    assert "계약일(2026-11-02)" in r.json()["detail"]["fields"][0]["message"]
    assert _set(client, c, "T2", {"status": "skipped", "done_date": "2026-11-02"}, day="2026-11-10").status_code == 200


def test_finished_todo_out_of_plan_cannot_be_reopened(client):
    # #101 리뷰 2번: 조건이 바뀌어 목록에서 빠진 끝낸 할 일은 기록으로만 남고, 되돌리면 재계산에서 지워지므로 막는다
    c = _contract(client)
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-01"}, day="2026-12-03")
    _set(client, c, "T5", {"status": "skipped", "done_date": "2026-12-03"}, day="2026-12-03")
    r = client.patch(f"/api/contracts/{c['id']}", json={"guarantor": "none"},
                     headers={"X-Contract-Token": c["access_token"]})
    assert _todo(r.json(), "T5")["status"] == "skipped"   # 보증 미가입이라 계획에는 없지만 기록으로 남음
    # 앱이 "되돌리기"를 숨기도록 응답에 archived (#111 리뷰 1번)
    assert _todo(r.json(), "T5")["archived"] is True and _todo(r.json(), "T4")["archived"] is False

    r = _set(client, c, "T5", {"status": "todo"}, day="2026-12-05")
    assert r.status_code == 409 and _detail(r)["code"] == "TODO_NOT_PLANNED"
    after = client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": c["access_token"]}).json()
    assert _todo(after, "T5")["status"] == "skipped"
    # 계획에 있는 할 일은 그대로 되돌릴 수 있다
    assert _set(client, c, "T4", {"status": "todo"}, day="2026-12-05").status_code == 200


def test_t6_record_cannot_be_reopened(client):
    # #104 리뷰 1번: T6은 T5를 끝내면 계획에서 빠진다(todo_not_done: T5). 기록으로 남은 T6을 되돌리면 막는다
    c = _contract(client)
    assert _set(client, c, "T6", {"status": "skipped"}, day="2026-12-03").status_code == 200
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-01"}, day="2026-12-03")
    _set(client, c, "T5", {"status": "skipped", "done_date": "2026-12-03"}, day="2026-12-03")
    r = _set(client, c, "T6", {"status": "todo"}, day="2026-12-05")
    assert r.status_code == 409 and _detail(r)["code"] == "TODO_NOT_PLANNED"
    after = client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": c["access_token"]}).json()
    assert _todo(after, "T6")["status"] == "skipped"


def test_record_does_not_block_undo(client):
    # #104 리뷰 5번: 기록으로만 남은 할 일의 예전 선행 조건이 계획 안의 할 일을 되돌리지 못하게 막지 않는다
    c = _contract(client)
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-01"}, day="2026-12-03")
    _set(client, c, "T5", {"status": "skipped", "done_date": "2026-12-03"}, day="2026-12-03")
    client.patch(f"/api/contracts/{c['id']}", json={"guarantor": "none"}, headers={"X-Contract-Token": c["access_token"]})
    with get_sessionmaker()() as db:
        db.get(Todo, _todo(c, "T5")["id"]).prerequisites = ["T4"]
        db.commit()
    assert _set(client, c, "T4", {"status": "todo"}, day="2026-12-05").status_code == 200


def test_day_before_contract_todo_can_finish_on_its_start(client):
    # #104 리뷰 2번: 계약 전날 하는 할 일(X-FIXED-DATE-STATUS 시작 = 계약일 −1일)은 그날 끝낼 수 있다
    c = _contract(client)
    with get_sessionmaker()() as db:
        row = db.get(Contract, c["id"])
        row.todos.append(Todo(rule_id="X-FIXED-DATE-STATUS", title="확정일자 부여현황 열람", rules_version="test",
                              status="todo", start_date=date(2026, 11, 1)))
        db.commit()
        todo_id = row.todos[-1].id
    headers = {"X-Contract-Token": c["access_token"], "X-Virtual-Today": "2026-11-05"}
    r = client.patch(f"/api/todos/{todo_id}", json={"status": "skipped", "done_date": "2026-10-31"}, headers=headers)
    assert r.status_code == 422 and "시작일(2026-11-01)" in r.json()["detail"]["fields"][0]["message"]
    r = client.patch(f"/api/todos/{todo_id}", json={"status": "skipped", "done_date": "2026-11-01"}, headers=headers)
    assert r.status_code == 200, r.text


def test_contract_date_not_after_done_dates(client):
    # #104 리뷰 4번: 계약일을 뒤로 바꿔 끝낸 날이 계약일보다 앞서게 되면 막는다 (뒤 기한이 당겨지지 않게)
    c = _contract(client)
    _set(client, c, "T1", {"status": "skipped", "done_date": "2026-11-02"}, day="2026-11-03")
    headers = {"X-Contract-Token": c["access_token"]}
    r = client.patch(f"/api/contracts/{c['id']}", json={"contract_date": "2026-11-05"}, headers=headers)
    assert r.status_code == 422, r.text
    assert _todo(c, "T1")["title"] in r.json()["detail"]["fields"][0]["message"]
    after = client.get(f"/api/contracts/{c['id']}", headers=headers).json()
    assert after["contract_date"] == "2026-11-02"
    # 되돌린 뒤에는 바꿀 수 있다
    _set(client, c, "T1", {"status": "todo"}, day="2026-11-03")
    assert client.patch(f"/api/contracts/{c['id']}", json={"contract_date": "2026-11-05"}, headers=headers).status_code == 200
