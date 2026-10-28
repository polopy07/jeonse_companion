"""갈아타기 전입 경고 (FR-027, UC-008 *a, AC-008): 다음 집 계약의 전입신고(4번)를 지금 집 반환 확인(9번) 전에 끝내려 하면 409.

지금 집은 정답표 S1(반환 예정 2028-12-14), 다음 집은 S10(잔금·전입 2028-11-30).
"""
import pytest

from tests.test_contracts import _check, _detail
from tests.test_move import APT, BY_ID, _auth, _current, _next_input

MOVE_IN_DAY, RETURN_DAY = "2028-11-30", "2028-12-14"


@pytest.fixture(autouse=True)
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))


def _next_contract(client) -> dict:
    n = _next_input(BY_ID["S10"])
    body = {"check_id": _check(client, {**APT, "deposit": n["deposit"]})["id"],
            **{k: n[k] for k in ("contract_date", "balance_date", "end_date", "loan", "loan_execution_date",
                                 "guarantor", "brokered")}}
    r = client.post("/api/contracts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _moving(client, link: bool = True) -> tuple[dict, dict]:
    """지금 계약(갈아타기 저장)과 다음 집 계약. link면 둘을 연결한다."""
    cur, nxt = _current(client), _next_contract(client)
    r = client.post(f"/api/contracts/{cur['id']}/move", json=_next_input(BY_ID["S10"]),
                    headers={**_auth(cur), "X-Virtual-Today": "2028-06-14"})
    assert r.status_code == 200, r.text
    if link:
        r = _link(client, cur, nxt)
        assert r.status_code == 200, r.text
        assert r.json()["next_contract_id"] == nxt["id"]
    return cur, nxt


def _link(client, cur: dict, nxt: dict, token: str | None = None):
    return client.post(f"/api/contracts/{cur['id']}/move/next", headers=_auth(cur),
                       json={"next_contract_id": nxt["id"], "next_contract_token": token or nxt["access_token"]})


def _todo_id(c: dict, rule_id: str) -> int:
    return next(t["id"] for t in c["todos"] if t["rule_id"] == rule_id)


def _finish(client, c: dict, rule_id: str, day: str, **body):
    return client.patch(f"/api/todos/{_todo_id(c, rule_id)}", json={"status": "skipped", **body},
                        headers={**_auth(c), "X-Virtual-Today": day})


def test_move_in_before_return_warns(client):
    cur, nxt = _moving(client)
    r = _finish(client, nxt, "T4", MOVE_IN_DAY)
    assert r.status_code == 409
    d = _detail(r)
    assert d["code"] == "MOVE_IN_BEFORE_RETURN"
    assert RETURN_DAY in d["message"] and "대항력" in d["message"] and "임차권등기" in d["hint"]
    # 경고를 보고 그래도 끝내면 된다
    r = _finish(client, nxt, "T4", MOVE_IN_DAY, confirm_move_in=True)
    assert r.status_code == 200, r.text
    assert next(t for t in r.json()["todos"] if t["rule_id"] == "T4")["status"] == "skipped"


def test_no_warning_after_return_confirmed(client):
    cur, nxt = _moving(client)
    assert _finish(client, cur, "T9", RETURN_DAY).status_code == 200   # 지금 집 보증금을 돌려받음
    assert _finish(client, nxt, "T4", RETURN_DAY).status_code == 200


def test_evidence_upload_also_warns(client):
    cur, nxt = _moving(client)
    url = f"/api/todos/{_todo_id(nxt, 'T4')}/evidence"
    headers = {**_auth(nxt), "X-Virtual-Today": MOVE_IN_DAY}
    files = {"file": ("p.jpg", b"\xff\xd8 jpeg", "image/jpeg")}
    r = client.post(url, files=files, headers=headers)
    assert r.status_code == 409 and _detail(r)["code"] == "MOVE_IN_BEFORE_RETURN"
    r = client.post(url, files=files, data={"confirm_move_in": "true"}, headers=headers)
    assert r.status_code == 200, r.text


def test_no_warning_without_link_or_for_other_todos(client):
    cur, nxt = _moving(client, link=False)
    assert _finish(client, nxt, "T4", MOVE_IN_DAY).status_code == 200   # 연결하지 않은 계약은 모름

    cur, nxt = _moving(client)
    assert _finish(client, nxt, "T3", MOVE_IN_DAY).status_code == 200   # 전입신고가 아닌 할 일
    # 지금 계약이 무산됐으면 지킬 대항력이 없다
    assert client.post(f"/api/contracts/{cur['id']}/cancel", headers=_auth(cur)).status_code == 200
    assert _finish(client, nxt, "T4", MOVE_IN_DAY).status_code == 200


def test_link_errors(client):
    cur, nxt = _current(client), _next_contract(client)
    r = _link(client, cur, nxt)
    assert r.status_code == 404   # 갈아타기를 저장하지 않음
    client.post(f"/api/contracts/{cur['id']}/move", json=_next_input(BY_ID["S10"]), headers=_auth(cur))
    assert _link(client, cur, nxt, token="wrong").status_code == 404
    assert client.post(f"/api/contracts/{cur['id']}/move/next", headers=_auth(cur),
                       json={"next_contract_id": 999, "next_contract_token": "x"}).status_code == 404
    r = _link(client, cur, cur)
    assert r.status_code == 422

    # 다른 갈아타기에 이미 연결된 계약
    assert _link(client, cur, nxt).status_code == 200
    other = _current(client)
    client.post(f"/api/contracts/{other['id']}/move", json=_next_input(BY_ID["S10"]), headers=_auth(other))
    r = _link(client, other, nxt)
    assert r.status_code == 409 and _detail(r)["code"] == "NEXT_CONTRACT_LINKED"
    assert _link(client, cur, nxt).status_code == 200   # 같은 갈아타기에 다시 보내는 것은 됨

    # 무산된 다음 집 계약은 연결할 수 없다
    cancelled = _next_contract(client)
    client.post(f"/api/contracts/{cancelled['id']}/cancel", headers=_auth(cancelled))
    r = _link(client, cur, cancelled)
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"
    assert client.get(f"/api/contracts/{cur['id']}/move", headers=_auth(cur)).json()["next_contract_id"] == nxt["id"]
