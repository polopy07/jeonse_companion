"""역전세 경보 재계산·리포트 (FR-036~038, POST /api/admin/alerts/recalculate, GET /api/contracts/{id}/alerts/latest).

시연 집 2채는 경보 계산 정답표(docs/validation/demo_houses.yaml)와 대조한다 (NFR-004).
"""
import pytest
from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Notification
from load_demo_trades import load as load_saved_trades
from tests.test_contracts import DATES, EOK, _check, _detail
from tests.test_demo_houses import ANSWERS

ADMIN = "test-admin-token"
# 계약 전 확인에서 정상(비율 43%)인 아파트. 반환보증에 들어 T5가 있다
CALM = {"housing_type": "apartment", "deposit": EOK, "official_price": 165_000_000, "exclusive_area": 59.85,
        "registry": {"mortgage": False}}


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)


def _recalc(client, body=None, **headers):
    r = client.post("/api/admin/alerts/recalculate", json=body, headers={"X-Admin-Token": ADMIN, **headers})
    assert r.status_code == 200, r.text
    return {x["contract_id"]: x for x in r.json()["results"]}


def _latest(client, contract):
    r = client.get(f"/api/contracts/{contract['id']}/alerts/latest",
                   headers={"X-Contract-Token": contract["access_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def _contract(client, check_body=CALM, **extra) -> dict:
    r = client.post("/api/contracts", json={"check_id": _check(client, check_body)["id"], **DATES,
                                            "guarantor": "HUG", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _t5(contract) -> dict:
    return next(t for t in contract["todos"] if t["rule_id"] == "T5")


def _alert_notices(contract_id) -> list[Notification]:
    with get_sessionmaker()() as db:
        return db.scalars(select(Notification).where(Notification.contract_id == contract_id,
                                                     Notification.kind == "alert")).all()


def test_demo_houses_recalculate_to_answer_sheet(client):
    # 정답표 기준일로 다시 계산해도 계약 전 확인과 같은 추정 주택가격·비율·단계가 나온다
    as_of, _ = load_saved_trades()
    houses = client.get("/api/demo-houses").json()["houses"]
    made = {}
    for house in houses:
        check = client.post("/api/checks", json=house["input"], headers={"X-Virtual-Today": as_of}).json()
        day = house["contract_day"] or {**ANSWERS["demo-villa"]["contract_day"]["dates"], "special_term_result": {}}
        r = client.post("/api/contracts", json={"check_id": check["id"], **day})
        made[house["id"]] = r.json()

    for hid, contract in made.items():   # 재계산 전: 계약을 시작할 때의 값
        exp = ANSWERS[hid]["expected"]
        rep = _latest(client, contract)
        assert (rep["recalculated"], rep["level"], rep["as_of"]) == (False, exp["alert_level"], as_of)
        assert rep["estimated_price"] == exp["estimated_price"] and round(rep["deposit_ratio"], 4) == exp["deposit_ratio"]
        assert rep["basis"]["trade"] == exp["trade_basis"] and rep["basis"]["nearby_jeonse"] == exp["nearby_jeonse"]
        assert rep["history"] == [{k: rep[k] for k in ("as_of", "level", "estimated_price", "deposit_ratio")}]

    results = _recalc(client, {"date": as_of})
    for hid, contract in made.items():
        exp = ANSWERS[hid]["expected"]
        res = results[contract["id"]]
        assert (res["level"], res["previous_level"], res["raised"]) == (exp["alert_level"], exp["alert_level"], False)
        rep = _latest(client, contract)
        assert rep["recalculated"] is True and rep["level"] == exp["alert_level"], hid
        assert rep["estimated_price"] == exp["estimated_price"], hid
        assert round(rep["deposit_ratio"], 4) == exp["deposit_ratio"], hid
        assert rep["basis"]["trade"] == exp["trade_basis"], hid
        assert rep["basis"]["nearby_jeonse"] == exp["nearby_jeonse"], hid
        assert rep["basis"]["official_estimate"] == exp["estimated_price"] and rep["basis"]["complex_known"]
        assert rep["previous_level"] == exp["alert_level"] and len(rep["history"]) == 2
        assert rep["data_limits"]
    villa = _latest(client, made["demo-villa"])["basis"]
    assert (villa["senior_debt"], villa["ratio_is_minimum"]) == (14_400_000, False)   # 시연용 가상 근저당


def test_level_up_moves_t5_and_notifies(client):
    c = _contract(client)
    assert c["alert_level"] is None and not _t5(c)["moved_to_top"]

    # 공시가격 새 발표: 8,500만 × 140% = 1억 1,900만 → 1억 ÷ 1.19억 = 84% → 주의
    res = _recalc(client, {"date": "2027-05-01", "official_prices": {str(c["id"]): 85_000_000}})[c["id"]]
    assert (res["level"], res["previous_level"], res["raised"]) == ("caution", None, True)
    assert res["estimated_price"] == 119_000_000

    got = client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": c["access_token"]}).json()
    assert got["alert_level"] == "caution" and got["official_price"] == 85_000_000
    assert _t5(got)["moved_to_top"]   # 주의 이상이면 반환보증 맨 위 (todos.yaml move_to_top_when)
    notices = _alert_notices(c["id"])
    assert len(notices) == 1 and "주의" in notices[0].title and notices[0].channel == "app"

    rep = _latest(client, c)
    assert (rep["label"], rep["previous_level"], round(rep["previous_ratio"], 4)) == ("주의", None, 0.4329)
    assert [h["as_of"] for h in rep["history"]] == [rep["history"][0]["as_of"], "2027-05-01"]

    # 같은 날 다시 불러도 이력·알림이 늘지 않는다
    _recalc(client, {"date": "2027-05-01"})
    assert len(_latest(client, c)["history"]) == 2 and len(_alert_notices(c["id"])) == 1

    # 다음 날 공시가격이 다시 오르면 단계가 내려가고(알림 없음) T5도 제자리로
    res = _recalc(client, {"date": "2027-05-02", "official_prices": {str(c["id"]): 165_000_000}})[c["id"]]
    assert (res["level"], res["previous_level"], res["raised"]) == (None, "caution", False)
    got = client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": c["access_token"]}).json()
    assert got["alert_level"] is None and not _t5(got)["moved_to_top"]
    assert len(_alert_notices(c["id"])) == 1 and len(_latest(client, c)["history"]) == 3


def test_virtual_today_and_contract_filter(client):
    a, b = _contract(client), _contract(client)
    results = _recalc(client, {"contract_ids": [b["id"]]}, **{"X-Virtual-Today": "2027-01-15"})
    assert list(results) == [b["id"]]
    assert _latest(client, b)["as_of"] == "2027-01-15" and _latest(client, a)["recalculated"] is False


def test_skips_cancelled_and_not_applicable(client):
    cancelled = _contract(client)
    client.post(f"/api/contracts/{cancelled['id']}/cancel", headers={"X-Contract-Token": cancelled["access_token"]})
    multi = _contract(client, {"housing_type": "multi_household", "deposit": EOK})   # 다가구: 경보 대상 아님
    assert _recalc(client, {"date": "2027-01-15"}) == {}

    r = client.get(f"/api/contracts/{multi['id']}/alerts/latest", headers={"X-Contract-Token": multi["access_token"]})
    assert r.status_code == 404 and _detail(r)["code"] == "NOT_FOUND"
    assert _latest(client, cancelled)["recalculated"] is False   # 무산된 계약도 기록으로 볼 수 있음


def test_access(client):
    c = _contract(client)
    r = client.get(f"/api/contracts/{c['id']}/alerts/latest", headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404
    r = client.post("/api/admin/alerts/recalculate", json={})
    assert r.status_code == 401 and _detail(r)["code"] == "ADMIN_TOKEN_INVALID"
    r = client.post("/api/admin/alerts/recalculate", json={"official_prices": {str(c["id"]): 0}},
                    headers={"X-Admin-Token": ADMIN})
    assert r.status_code == 422


def test_user_trade_price_kept_on_recalculation(client):
    # #107 리뷰 1번: 직접 넣은 매매 실거래가는 판정처럼 재계산에도 쓴다 (공시가격 × 140%로 돌아가지 않게)
    body = {**CALM, "official_price": EOK, "trade_price": 118_000_000}   # 1억 ÷ 1.18억 ≈ 84.7% → 주의
    c = _contract(client, body)
    assert c["alert_level"] == "caution"
    got = _recalc(client, {"date": "2027-03-01", "contract_ids": [c["id"]]})[c["id"]]
    assert (got["level"], got["estimated_price"]) == ("caution", 118_000_000)
    latest = _latest(client, c)
    assert latest["basis"]["trade_price_input"] == 118_000_000 and latest["basis"]["official_estimate"] == 140_000_000


def test_second_raise_same_day_updates_notice(client):
    # #107 리뷰 3번: 같은 날 주의 → 경고로 한 번 더 오르면 알림을 경고로 고친다 (알림은 하루 한 건)
    c = _contract(client)
    day = "2027-03-01"
    assert _recalc(client, {"date": day, "official_prices": {c["id"]: 89_000_000}})[c["id"]]["raised"] is True
    assert "주의" in _alert_notices(c["id"])[0].title
    again = _recalc(client, {"date": day, "official_prices": {c["id"]: 79_000_000}})[c["id"]]
    assert (again["level"], again["raised"]) == ("warning", True)
    notices = _alert_notices(c["id"])
    assert len(notices) == 1 and "경고" in notices[0].title
    # 같은 날 같은 단계로 다시 돌리면 올라간 것이 아니다
    assert _recalc(client, {"date": day})[c["id"]]["raised"] is False


def test_rewound_virtual_date_reuses_that_day(client):
    # #107 리뷰 4번: 가상 날짜를 되돌려 다시 계산하면 그날 기록을 고치고, 앞 단계는 그날보다 앞선 기록으로 본다
    c = _contract(client)
    _recalc(client, {"date": "2027-05-01", "official_prices": {c["id"]: 89_000_000}})   # 주의
    _recalc(client, {"date": "2027-05-10", "official_prices": {c["id"]: 79_000_000}})   # 경고
    again = _recalc(client, {"date": "2027-05-01"})[c["id"]]
    assert again["previous_level"] is None   # 5/10이 아니라 계약 시작(정상)
    days = [p["as_of"] for p in _latest(client, c)["history"]]
    assert days.count("2027-05-01") == 1 and days == sorted(days)


def test_history_sorted_with_start_point(client):
    # #107 리뷰 5번: 판정한 날(실제 날짜)보다 앞선 가상 날짜로 재계산해도 이력은 날짜순
    c = _contract(client)
    _recalc(client, {"date": "2020-01-01", "contract_ids": [c["id"]]})
    days = [p["as_of"] for p in _latest(client, c)["history"]]
    assert days == sorted(days) and days[0] == "2020-01-01"


def test_unknown_old_level_does_not_stop_batch(client):
    # #107 리뷰 6번: alert.yaml에서 빠진 단계 id가 예전 기록에 있어도 일괄 재계산이 500이 되지 않는다
    from app.models import Alert
    c = _contract(client)
    other = _contract(client)
    _recalc(client, {"date": "2027-03-01"})
    with get_sessionmaker()() as db:
        for a in db.scalars(select(Alert).where(Alert.contract_id == c["id"])):
            a.level = "removed_level"
        db.commit()
    got = _recalc(client, {"date": "2027-03-02"})
    assert {c["id"], other["id"]} <= set(got)
