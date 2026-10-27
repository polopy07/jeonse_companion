"""등기부 재비교 (POST·GET /api/contracts/{id}/registry-compare, FR-023, FR-048, UC-006)."""
from app.engine.registry_compare import compare_registry
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

def _contract(client, body=VILLA) -> dict:
    r = client.post("/api/contracts", json={"check_id": _check(client, body)["id"], **DATES})
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


def test_access_and_cancelled(client):
    c = _contract(client)
    r = client.post(f"/api/contracts/{c['id']}/registry-compare", json={"registry": SAME},
                    headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404
    assert _compare(client, c, {"mortgage": True, "mortgage_amount": 0}).status_code == 422   # 근저당인데 금액 없음
    client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": c["access_token"]})
    r = _compare(client, c, SAME)
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"
