"""등기부 재비교 (POST·GET /api/contracts/{id}/registry-compare, FR-023, FR-048, UC-006)."""
from datetime import date

from app.alerts import senior_debt
from app.engine.registry_compare import compare_registry
from app.models import Contract, Verdict
from tests.test_contracts import DATES, EOK, VILLA, _check, _detail

BEFORE = {"registry.seizure": False, "registry.mortgage": True, "registry.mortgage_amount": 120_000_000,
          "registry.lease_amount": 0, "registry.trust": False}
SAME = {"mortgage": True, "mortgage_amount": 120_000_000}
APT_NO_REGISTRY = {"housing_type": "apartment", "deposit": 2 * EOK, "official_price": 3 * EOK, "exclusive_area": 84.9}


def _changes(result) -> dict:
    return {i.field: i.change for i in result.items if i.change != "same"}


# ---- 엔진 ----

def test_same_registry_has_no_change():
    r = compare_registry(BEFORE, {f"registry.{k}": v for k, v in SAME.items()}, "balance_day")
    assert (r.changed, r.hold, r.advice) == (False, False, None)
    assert r.mortgage_check_required is True   # 계약 전에 근저당이 있었으면 금액 비교가 필수 (FR-023)


def test_increase_or_new_item_is_risk_and_holds():
    after = {**BEFORE, "registry.mortgage_amount": 180_000_000, "registry.seizure": True}
    r = compare_registry(BEFORE, after, "balance_day")
    assert _changes(r) == {"registry.mortgage_amount": "risk", "registry.seizure": "risk"}
    assert (r.hold, r.advice) == (True, "잔금 보류 후 상담")
    assert compare_registry(BEFORE, after, "contract_day").advice == "계약 보류 후 상담"


def test_released_mortgage_is_change_without_hold():
    # 잔금 때 말소하기로 한 근저당이 없어진 것은 변동으로 보여 주되 보류는 안내하지 않는다
    after = {**BEFORE, "registry.mortgage": False, "registry.mortgage_amount": 0}
    r = compare_registry(BEFORE, after, "balance_day")
    assert _changes(r) == {"registry.mortgage": "eased", "registry.mortgage_amount": "eased"}
    assert (r.changed, r.hold) == (True, False)


def test_missing_baseline_treats_present_items_as_risk():
    after = {"registry.seizure": False, "registry.mortgage": True, "registry.mortgage_amount": 50_000_000,
             "registry.lease_amount": 0, "registry.trust": False}
    r = compare_registry({"deposit": EOK}, after, "contract_day")
    assert r.baseline_missing is True and r.mortgage_check_required is False
    assert _changes(r) == {"registry.mortgage": "risk", "registry.mortgage_amount": "risk"}
    assert all(i.before is None for i in r.items)


# ---- API ----

def _contract(client, body=VILLA, **extra) -> dict:
    r = client.post("/api/contracts", json={"check_id": _check(client, body)["id"], **DATES, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _compare(client, c, registry, day="2026-12-01", **extra):
    return client.post(f"/api/contracts/{c['id']}/registry-compare", json={"registry": registry, **extra},
                       headers={"X-Contract-Token": c["access_token"], "X-Virtual-Today": day})


def test_balance_day_no_change(client):
    c = _contract(client)
    r = _compare(client, c, SAME)
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["stage"], out["compared_on"], out["baseline_check_id"]) == ("balance_day", "2026-12-01", c["check_id"])
    assert (out["changed"], out["hold"], out["advice"]) == (False, False, None)
    # 근저당이 있던 집은 근저당 금액 비교를 필수로 보여 준다 (FR-023, AC-001)
    assert out["mortgage_check_required"] is True
    assert out["mortgage_check"] == {"field": "registry.mortgage_amount", "label": "근저당 채권최고액 합계",
                                     "before": 120_000_000, "after": 120_000_000, "change": "same"}
    assert out["level_after"] == out["level_before"] and out["deposit_ratio_after"] == out["deposit_ratio_before"]


def test_contract_day_new_seizure_holds_and_rejudges(client):
    # 점검한 날과 계약일이 다를 때 계약 당일 재비교 (FR-048): 잔금일 전이면 계약 당일로 본다
    c = _contract(client)
    out = _compare(client, c, {**SAME, "seizure": True, "mortgage_amount": 150_000_000}, day="2026-11-02").json()
    assert out["stage"] == "contract_day"
    assert (out["hold"], out["advice"]) == (True, "계약 보류 후 상담")
    assert {i["field"]: i["change"] for i in out["items"] if i["change"] != "same"} == {
        "registry.seizure": "risk", "registry.mortgage_amount": "risk"}
    assert out["level_after"] == "problem" and out["deposit_ratio_after"] > out["deposit_ratio_before"]


def test_history_and_stage_override(client):
    c = _contract(client)
    _compare(client, c, SAME, day="2026-11-02")
    _compare(client, c, {"mortgage": False, "mortgage_amount": 0}, day="2026-11-20", stage="balance_day")
    r = client.get(f"/api/contracts/{c['id']}/registry-compare", headers={"X-Contract-Token": c["access_token"]})
    assert r.status_code == 200
    got = [(x["stage"], x["compared_on"], x["changed"], x["hold"]) for x in r.json()]
    assert got == [("contract_day", "2026-11-02", False, False), ("balance_day", "2026-11-20", True, False)]


def test_compare_without_baseline_registry(client):
    c = _contract(client, APT_NO_REGISTRY)
    out = _compare(client, c, {"mortgage": True, "mortgage_amount": 50_000_000}).json()
    assert out["baseline_missing"] is True and out["hold"] is True and out["mortgage_check"] is None


def test_latest_registry_feeds_alert_recalculation(client, monkeypatch):
    # 재비교한 등기부가 경보 재계산의 선순위 채권이 된다 (app.alerts.senior_debt)
    monkeypatch.setenv("ADMIN_TOKEN", "t")
    c = _contract(client)
    _compare(client, c, {**SAME, "mortgage_amount": 150_000_000})
    r = client.post("/api/admin/alerts/recalculate", json={"date": "2026-12-02", "contract_ids": [c["id"]]},
                    headers={"X-Admin-Token": "t"})
    assert r.status_code == 200, r.text
    latest = client.get(f"/api/contracts/{c['id']}/alerts/latest", headers={"X-Contract-Token": c["access_token"]})
    assert latest.json()["basis"]["senior_debt"] == 150_000_000


def _get(client, c) -> dict:
    return client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": c["access_token"]}).json()


def test_new_linkages_change_todos_and_alert_right_away(client):
    # 계약 전에는 근저당 없음(비율 48%). 계약 당일 등기부에 근저당 2억이 새로 생기면 비율 95% (PO 2026-10-28)
    c = _contract(client, APT_NO_REGISTRY, guarantor="HUG")
    assert c["alert_level"] is None
    out = _compare(client, c, {"mortgage": True, "mortgage_amount": 2 * EOK}, day="2026-11-02").json()
    assert out["hold"] is True and out["deposit_ratio_after"] > 0.9
    got = _get(client, c)
    todos = {t["rule_id"]: t for t in got["todos"]}
    assert got["alert_level"] == "warning" and todos["T5"]["moved_to_top"]      # 경보 바로 다시 계산
    assert any("근저당 금액" in x for x in todos["T3"]["required_checks"])        # L-MORTGAGE
    assert todos["T2"]["due_date"] == DATES["contract_date"]                       # L-RATIO90
    latest = client.get(f"/api/contracts/{c['id']}/alerts/latest", headers={"X-Contract-Token": c["access_token"]})
    assert latest.json()["as_of"] == "2026-11-02" and latest.json()["basis"]["senior_debt"] == 2 * EOK

    # 근저당이 말소된 등기부를 다시 올려도 할 일의 연동은 빼지 않는다. 경보는 다시 내려감
    _compare(client, c, {"mortgage": False, "mortgage_amount": 0}, day="2026-12-01")
    got = _get(client, c)
    todos = {t["rule_id"]: t for t in got["todos"]}
    assert got["alert_level"] is None
    assert any("근저당 금액" in x for x in todos["T3"]["required_checks"])


def test_level_change_is_from_registry_only(client, monkeypatch):
    # 경보 재계산으로 계약의 공시가격이 내려가도, 재비교 판정은 계약 전 확인 때 값으로 해 등기부가 같으면 그대로
    monkeypatch.setenv("ADMIN_TOKEN", "t")
    c = _contract(client)
    r = client.post("/api/admin/alerts/recalculate",
                    json={"date": "2026-11-20", "official_prices": {str(c["id"]): 150_000_000}},
                    headers={"X-Admin-Token": "t"})
    assert r.status_code == 200, r.text
    out = _compare(client, c, SAME, day="2026-12-01").json()
    assert out["changed"] is False
    assert (out["level_after"], out["deposit_ratio_after"]) == (out["level_before"], out["deposit_ratio_before"])


def test_stage_after_contract_date_is_balance_day(client):
    # 계약한 다음 날부터 잔금일 전까지 올린 등기부는 "잔금 보류" (이미 계약했으니 "계약 보류"가 아님)
    c = _contract(client)
    out = _compare(client, c, {**SAME, "seizure": True}, day="2026-11-10").json()
    assert (out["stage"], out["advice"]) == ("balance_day", "잔금 보류 후 상담")


def test_latest_registry_is_by_compared_date():
    # 가상 날짜를 되돌려 앞선 날로 다시 비교해도(id는 더 큼) 최근 등기부는 비교한 날로 고른다. as_of 뒤 것은 안 씀
    def verdict(id_, amount, on=None):
        return Verdict(id=id_, inputs={"registry.mortgage_amount": amount, "registry.lease_amount": 0},
                       comparison={"compared_on": on} if on else None, stage="balance_day" if on else None)

    row = Contract(verdicts=[verdict(1, 120_000_000), verdict(2, 150_000_000, "2026-12-01"),
                             verdict(3, 130_000_000, "2026-11-02")])
    assert senior_debt(row) == 150_000_000
    assert senior_debt(row, date(2026, 11, 5)) == 130_000_000
    assert senior_debt(row, date(2026, 10, 30)) == 120_000_000   # 재비교 전이면 계약 전 확인 등기부


def test_access_and_cancelled(client):
    c = _contract(client)
    r = client.post(f"/api/contracts/{c['id']}/registry-compare", json={"registry": SAME},
                    headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404
    assert _compare(client, c, {"mortgage": True, "mortgage_amount": 0}).status_code == 422   # 근저당인데 금액 없음
    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    r = _compare(client, c, SAME)
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"
