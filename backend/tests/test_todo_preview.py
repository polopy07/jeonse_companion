"""결제 전 할 일 종류 미리보기 (GET /api/checks/{id}/todo-preview, FR-012, #56)."""
from tests.test_contract_patch import DATES, VILLA
from tests.test_contracts import EOK, _check


def _preview(client, check_id: int):
    return client.get(f"/api/checks/{check_id}/todo-preview")


def test_preview_lists_kinds_without_dates(client):
    # 빌라(근저당·비율 90% 이상): 보증 상담(2번)이 계약 당일까지로 당겨지고, 경보 경고라 반환보증(5번)이 맨 위
    check = _check(client, VILLA)
    r = _preview(client, check["id"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["product"], p["amount"], p["report_required"]) == ("package", 9900, True)
    items = {t["rule_id"]: t for t in p["todos"]}
    # 맨 위로 올라가는 할 일(경보 경고 → 5번) 먼저, 나머지는 번호순
    assert list(items) == ["T5", "T1", "T2", "T3", "T4", "T6", "T7", "T8", "T9"]
    assert items["T2"]["timing"] == "계약 당일까지"
    assert items["T1"]["timing"].startswith("계약 직후") and items["T9"]["timing"] == "만기일"
    assert items["T5"]["moved_to_top"] and p["todos"][0]["rule_id"] == "T5"
    assert "반환보증" in items["T5"]["note"] and items["T6"]["note"] and items["T8"]["note"]
    assert items["T4"]["evidence"] == "확정일자 받은 계약서" and items["T9"]["pinned"]
    # 날짜는 주지 않는다 (기한·알림·기록함은 패키지에서만)
    assert not any(k in t for t in p["todos"] for k in ("start_date", "due_date", "remind_date"))
    assert p["assumption"] and p["package_note"]


def test_preview_matches_contract(client):
    # 가정과 같은 조건(전세·HUG·대출 없음)으로 계약하면 같은 할 일이 생기고, 맨 위 할 일도 같다
    check = _check(client, VILLA)
    preview = _preview(client, check["id"]).json()["todos"]
    contract = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "guarantor": "HUG"}).json()
    assert {t["rule_id"] for t in preview} == {t["rule_id"] for t in contract["todos"]}
    assert preview[0]["rule_id"] == contract["todos"][0]["rule_id"]
    t2 = next(t for t in contract["todos"] if t["rule_id"] == "T2")
    assert t2["due_date"] == contract["contract_date"]   # 미리보기의 "계약 당일까지"와 같음


def test_preview_small_deposit_and_blocked(client):
    # 보증금 6천만 이하 전세는 임대차 신고 비대상 → 1번 없음
    small = _check(client, {"housing_type": "apartment", "deposit": 50_000_000, "official_price": 3 * EOK,
                            "exclusive_area": 59.9, "registry": {"mortgage": False}})
    p = _preview(client, small["id"]).json()
    assert p["report_required"] is False and "T1" not in {t["rule_id"] for t in p["todos"]}

    blocked = _check(client, {**VILLA, "registry": {"seizure": True, "mortgage": False}})
    assert blocked["level"] == "problem"
    r = _preview(client, blocked["id"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CHECK_BLOCKED"
    assert _preview(client, 99999).status_code == 404
