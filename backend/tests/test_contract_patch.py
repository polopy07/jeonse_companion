"""계약 조건·특약 결과 변경 → 할 일 재계산 (PATCH /api/contracts/{id}, FR-021, FR-049·050, AC-006·016)."""
from datetime import date

from app.db import get_sessionmaker
from app.engine.todos import build_todos
from app.models import Contract, Todo
from app.rules.loader import get_rules

EOK = 100_000_000
VILLA = {   # 근저당 있음·비율 90% 이상 → 확인 필요, 연동 규칙 L-MORTGAGE·L-RATIO90, 경보 경고
    "housing_type": "row_house", "deposit": 150_000_000, "official_price": 2 * EOK, "exclusive_area": 49.5,
    "registry": {"mortgage": True, "mortgage_amount": 120_000_000},
}
DATES = {"contract_date": "2026-11-02", "balance_date": "2026-12-01", "end_date": "2028-11-30"}


def _contract(client, **body) -> dict:
    check = client.post("/api/checks", json=VILLA).json()
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "guarantor": "HUG", **body})
    assert r.status_code == 201, r.text
    return r.json()


def _patch(client, contract_id: int, body: dict):
    return client.patch(f"/api/contracts/{contract_id}", json=body)


def _engine_todos(contract: dict, linkages: list[str], done_dates=None):
    """같은 조건으로 엔진을 바로 부른 결과 (엔진은 기한 정답표 재계산 시나리오로 따로 검증됨)."""
    values = {k: contract[k] for k in ("deposit", "monthly_rent", "loan", "guarantor", "brokered", "renewal_right_used")}
    for k in ("contract_date", "balance_date", "end_date", "loan_execution_date"):
        values[k] = contract[k] and date.fromisoformat(contract[k])
    return build_todos(values, linkages, contract["special_term_result"], contract["alert_level"], get_rules(),
                       done_dates=done_dates)


def _dates(todos) -> list:
    return [(t["rule_id"], t["start_date"], t["due_date"], t["remind_date"]) for t in todos]


def test_balance_date_change_recalculates_todos(client):
    # AC-006: 잔금일을 바꾸면 연결된 기한이 모두 다시 계산된다. 같은 할 일은 id가 그대로
    created = _contract(client, loan=True, loan_execution_date="2026-12-01")
    r = _patch(client, created["id"], {"balance_date": "2026-12-22", "loan_execution_date": "2026-12-22"})
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["balance_date"] == "2026-12-22" and changed["contract_date"] == "2026-11-02"

    expected = _engine_todos(changed, ["L-MORTGAGE", "L-RATIO90"])
    assert _dates(changed["todos"]) == [
        (t.rule_id, t.start_date and t.start_date.isoformat(), t.due_date and t.due_date.isoformat(),
         t.remind_date and t.remind_date.isoformat()) for t in expected]
    by_id = {t["rule_id"]: t for t in changed["todos"]}
    assert by_id["T3"]["due_date"] == "2026-12-22" and by_id["T4"]["due_date"] == "2026-12-22"
    assert {t["rule_id"]: t["id"] for t in changed["todos"]} == {t["rule_id"]: t["id"] for t in created["todos"]}
    assert client.get(f"/api/contracts/{created['id']}").json() == changed


def test_special_term_rejected_moves_move_in_to_top(client):
    # AC-016: 담보 설정 금지 특약을 "거절당함"으로 바꾸면 전입신고(T4)가 맨 위로. 보내지 않은 특약은 그대로
    created = _contract(client, special_term_result={"S-NO-MORTGAGE": "inserted", "S-GUARANTEE-CANCEL": "inserted"})
    assert not {t["rule_id"]: t for t in created["todos"]}["T4"]["moved_to_top"]
    r = _patch(client, created["id"], {"special_term_result": {"S-NO-MORTGAGE": "rejected"}})
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["special_term_result"] == {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "inserted"}
    assert changed["todos"][0]["rule_id"] == "T4" and changed["todos"][0]["moved_to_top"]


def test_done_todo_keeps_status_and_moves_later_dates(client):
    # 전입신고를 끝낸 날이 반환보증 가입(T5) 시작의 기준 (대출 없음: 완료 다음 날, 정답표 C6)
    created = _contract(client)
    with get_sessionmaker()() as db:
        t4 = db.query(Todo).filter_by(contract_id=created["id"], rule_id="T4").one()
        t4.status, t4.done_date = "done", date(2026, 12, 5)
        db.commit()
    r = _patch(client, created["id"], {"email": "tenant@example.com"})
    assert r.status_code == 200, r.text
    by_id = {t["rule_id"]: t for t in r.json()["todos"]}
    assert by_id["T4"]["status"] == "done"
    assert by_id["T5"]["start_date"] == "2026-12-06"

    # 보증 미가입으로 바꾸면 반환보증 할 일(T5·T6)은 없어진다. 끝낸 할 일은 남는다
    with get_sessionmaker()() as db:
        t5 = db.query(Todo).filter_by(contract_id=created["id"], rule_id="T5").one()
        t5.status, t5.done_date = "done", date(2026, 12, 10)
        db.commit()
    r = _patch(client, created["id"], {"guarantor": "none"})
    ids = [t["rule_id"] for t in r.json()["todos"]]
    assert "T6" not in ids
    assert ids[-1] == "T5" and r.json()["todos"][-1]["status"] == "done"
    assert [t["sort_order"] for t in r.json()["todos"]] == list(range(1, len(ids) + 1))


def test_loan_execution_date_can_be_cleared(client):
    created = _contract(client, loan=True, loan_execution_date="2026-12-01")
    r = _patch(client, created["id"], {"loan_execution_date": None})
    assert r.status_code == 200, r.text
    assert r.json()["loan_execution_date"] is None and r.json()["loan"] is True


def _detail(r):
    return r.json()["detail"]


def test_invalid_changes_are_422(client):
    created = _contract(client)
    # 바꾼 뒤의 날짜 순서도 계약 생성 때와 같은 규칙으로 검사
    r = _patch(client, created["id"], {"end_date": "2026-11-30"})
    assert r.status_code == 422
    assert _detail(r)["fields"] == [{"field": "body", "message": "만기일은 잔금일보다 뒤여야 합니다"}]
    # 꼭 있어야 하는 칸은 null로 지울 수 없다
    r = _patch(client, created["id"], {"balance_date": None})
    assert r.status_code == 422
    # 대출을 없애면서 실행일을 남기면 안 됨
    r = _patch(client, created["id"], {"loan": True, "loan_execution_date": "2026-12-01"})
    assert r.status_code == 200
    r = _patch(client, created["id"], {"loan": False})
    assert r.status_code == 422
    # 이 판정에서 안내하지 않은 특약
    r = _patch(client, created["id"], {"special_term_result": {"S-TAX-CERT": "rejected"}})
    assert r.status_code == 422
    # 실패한 요청은 아무것도 바꾸지 않는다
    with get_sessionmaker()() as db:
        assert db.get(Contract, created["id"]).end_date == date(2028, 11, 30)


def test_unknown_contract_is_404(client):
    r = _patch(client, 999, {"email": "a@b.co"})
    assert r.status_code == 404
    assert _detail(r)["code"] == "NOT_FOUND"
