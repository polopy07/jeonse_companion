"""갈아타기 (FR-025~027, UC-008, AC-008): 자금 틈·대출 순서·전입 순서를 정답표 S10·S10-b와 대조."""
from datetime import date

import pytest

from app.engine.move import MOVE_IN_BEFORE_RETURN, MOVE_IN_SAME_DAY, plan_move
from tests.test_contracts import EOK, _check, _detail
from tests.test_todos import BY_ID, _assert_matches, _build, _values

D = date.fromisoformat
S1 = BY_ID["S1"]
# 정답표 S1과 같은 지금 계약을 API로 만들 때 쓰는 집 (보증금 2.5억, 문제 항목이 없게 공시가격을 넉넉히)
APT = {"housing_type": "apartment", "deposit": 250_000_000, "official_price": 3 * EOK, "exclusive_area": 84.9,
       "registry": {"mortgage": False}}


def _next_input(s: dict) -> dict:
    """정답표 next_contract → MoveInput (계약금이 없으면 보증금의 10%)."""
    n = s["next_contract"]
    keys = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "loan", "loan_execution_date",
            "guarantor", "brokered", "renewal_right_used", "down_payment_date", "move_in_date")
    body = {k: n[k] for k in keys if k in n}
    body["down_payment"] = n.get("deposit_down_payment", n["deposit"] // 10)
    return body


# ---- 엔진: 정답표 대조 ----

@pytest.mark.parametrize("sid", ["S10", "S10-b"])
def test_switch_matches_answer_sheet(rules, sid):
    s = BY_ID[sid]
    current = _values(S1["input"])
    return_date = D(S1["expected"]["T9"]["due"])          # 지금 집 반환 예정일 = S1의 9번 기한
    nxt = _next_input(s)
    for k in ("contract_date", "balance_date", "end_date", "loan_execution_date", "down_payment_date", "move_in_date"):
        if nxt.get(k):
            nxt[k] = D(nxt[k])
    plan = plan_move({"deposit": current["deposit"], "loan": current["loan"]}, nxt, return_date)

    exp = s["expected"]
    assert plan.gap_days == exp["gap_days"]
    if "gap_amount" in exp:
        assert plan.gap_amount == exp["gap_amount"]
    else:
        assert plan.gap_amount == 0
    assert plan.loan_order == exp["loan_order"]
    assert plan.move_in_warning is exp["move_in_warning"]
    _assert_matches(_build(rules, s, inp=s["next_contract"]), exp["next_contract_todos"])


def test_s10_numbers_from_table():
    # 정답표 본문의 숫자: 잔금 2억 8,800만, 새 대출이 14일 먼저
    nxt = {"balance_date": D("2028-11-30"), "deposit": 320_000_000, "down_payment": 32_000_000, "loan": True,
           "loan_execution_date": D("2028-11-30"), "move_in_date": None}
    plan = plan_move({"deposit": 250_000_000, "loan": True}, nxt, D("2028-12-14"))
    assert plan.next_balance == 288_000_000
    assert plan.loan_gap_days == 14
    assert plan.move_in_date == D("2028-11-30")   # 전입 예정일이 없으면 잔금일
    assert len(plan.warnings) == 3                 # 자금 틈·대출 순서·전입 순서


def test_gap_amount_is_smaller_one():
    # 다음 집 잔금이 지금 집 보증금보다 작으면 잔금만큼만 빈다 (Q5)
    nxt = {"balance_date": D("2028-11-30"), "deposit": 200_000_000, "down_payment": 20_000_000, "loan": False,
           "loan_execution_date": None, "move_in_date": D("2028-12-20")}
    plan = plan_move({"deposit": 250_000_000, "loan": True}, nxt, D("2028-12-14"))
    assert (plan.gap_days, plan.gap_amount) == (14, 180_000_000)
    assert plan.loan_order is None and not plan.move_in_warning   # 다음 집 대출 없음, 반환 뒤 전입


def test_move_in_same_day_warns_unless_returned():
    # 같은 날 전입도 경고하되, 날짜를 바꾸라는 경고가 아니라 "보증금 먼저, 전입신고 나중" 순서 안내 (Q12)
    nxt = {"balance_date": D("2028-12-14"), "deposit": 300_000_000, "down_payment": 30_000_000, "loan": False,
           "loan_execution_date": None, "move_in_date": None}
    plan = plan_move({"deposit": 250_000_000, "loan": False}, nxt, D("2028-12-14"))
    assert plan.move_in_warning
    assert plan.warnings == [MOVE_IN_SAME_DAY.format(ret="2028-12-14", move_in="2028-12-14")]
    assert not plan_move({"deposit": 250_000_000, "loan": False}, nxt, D("2028-12-14"), returned=True).move_in_warning


def test_move_in_before_return_asks_to_check_dates():
    nxt = {"balance_date": D("2028-11-30"), "deposit": 300_000_000, "down_payment": 30_000_000, "loan": False,
           "loan_execution_date": None, "move_in_date": None}
    plan = plan_move({"deposit": 250_000_000, "loan": False}, nxt, D("2028-12-14"))
    assert plan.warnings[-1] == MOVE_IN_BEFORE_RETURN.format(ret="2028-12-14", move_in="2028-11-30")


# ---- API ----

def _current(client) -> dict:
    inp = S1["input"]
    body = {"check_id": _check(client, APT)["id"], **{k: inp[k] for k in (
        "contract_date", "balance_date", "end_date", "loan", "loan_execution_date", "guarantor", "brokered")}}
    r = client.post("/api/contracts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _auth(c) -> dict:
    return {"X-Contract-Token": c["access_token"]}


def test_move_api_s10(client):
    c = _current(client)
    url = f"/api/contracts/{c['id']}/move"
    assert client.get(url, headers=_auth(c)).status_code == 404

    r = client.post(url, json=_next_input(BY_ID["S10"]), headers={**_auth(c), "X-Virtual-Today": "2028-06-14"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["decided_on"] == "2028-06-14" and m["today"] == "2028-06-14"
    assert m["return_date"] == "2028-12-14" and m["returned"] is False
    assert (m["gap_days"], m["gap_amount"], m["next_balance"]) == (14, 250_000_000, 288_000_000)
    assert (m["loan_order"], m["loan_gap_days"]) == ("new_loan_first", 14)
    assert m["move_in_date"] == "2028-11-30" and m["move_in_warning"] is True
    assert any("대항력" in w for w in m["warnings"])

    # 다음 집 할 일은 정답표와 같고, 두 집 할 일은 날짜순으로 하나로 묶인다
    exp = BY_ID["S10"]["expected"]["next_contract_todos"]
    nxt = {t["rule_id"]: t for t in m["next_todos"]}
    assert set(nxt) == set(exp)
    assert nxt["T5"]["due_date"] == exp["T5"]["due"] and nxt["T6"]["remind_date"] == exp["T6"]["remind"]
    assert len(m["todos"]) == len(c["todos"]) + len(m["next_todos"])
    anchors = [t["remind_date"] or t["start_date"] or t["due_date"] for t in m["todos"]]
    assert anchors == sorted(anchors)
    # 7번(만기 6개월 전)은 오늘 할 일, 다음 집 할 일은 아직 시작 전
    assert next(t for t in m["todos"] if t["house"] == "current" and t["rule_id"] == "T7")["state"] == "in_progress"
    assert all(t["state"] == "upcoming" for t in m["next_todos"])

    # 다시 저장하면 다음 집 입력만 바뀐다 (S10-b: 틈 없음)
    r = client.post(url, json=_next_input(BY_ID["S10-b"]), headers={**_auth(c), "X-Virtual-Today": "2028-07-01"})
    m = r.json()
    assert m["decided_on"] == "2028-06-14"
    assert (m["gap_days"], m["gap_amount"], m["loan_order"], m["move_in_warning"]) == (0, 0, "old_repayment_first", False)
    assert client.get(url, headers=_auth(c)).json()["next"]["balance_date"] == "2028-12-20"


def test_move_follows_current_contract_changes(client):
    # 지금 계약의 만기를 PATCH로 바꾸면 반환 예정일·자금 틈도 다시 계산된다
    c = _current(client)
    url = f"/api/contracts/{c['id']}"
    client.post(f"{url}/move", json=_next_input(BY_ID["S10"]), headers=_auth(c))
    client.patch(url, json={"end_date": "2028-12-20"}, headers=_auth(c))
    m = client.get(f"{url}/move", headers=_auth(c)).json()
    assert m["return_date"] == "2028-12-20" and m["gap_days"] == 20


def test_move_validation_and_access(client):
    c = _current(client)
    url = f"/api/contracts/{c['id']}/move"
    body = _next_input(BY_ID["S10"])
    for bad in ({"down_payment": body["deposit"]}, {"move_in_date": "2028-11-29"}, {"end_date": "2028-11-30"},
                {"loan": False}):
        r = client.post(url, json={**body, **bad}, headers=_auth(c))
        assert r.status_code == 422, bad
    assert client.post(url, json=body, headers={"X-Contract-Token": "wrong"}).status_code == 404
    assert client.post("/api/contracts/999/move", json=body).status_code == 404

    # 무산된 계약은 갈아타기를 저장할 수 없다
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))
    r = client.post(url, json=body, headers=_auth(c))
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"
