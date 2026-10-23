"""특약 반영 분기 (부속표 E, FR-050, AC-016): 계약에 기록한 넣음/거절당함 → 안내·서류·할 일 순서."""
from tests.test_contracts import DATES, VILLA, _check

PHOTO = "특약이 보이는 계약서 사진"


def _create(client, terms: dict) -> dict:
    check = _check(client, VILLA)   # 근저당 있음·비율 96% → 담보 설정 금지, 보증 거절 시 해제 두 특약 모두 안내
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "guarantor": "HUG",
                                            "special_term_result": terms})
    assert r.status_code == 201, r.text
    return r.json()


def _effects(contract) -> dict:
    return {e["term_id"]: e for e in contract["special_term_effects"]}


def _top(contract) -> list[str]:
    return [t["rule_id"] for t in contract["todos"] if t["moved_to_top"]]


def test_no_mortgage_rejected_ac016(client):
    c = _create(client, {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "inserted"})
    e = _effects(c)
    rejected = e["S-NO-MORTGAGE"]
    assert rejected["result"] == "rejected" and rejected["label"] == "잔금일 다음 날까지 담보 설정 금지"
    assert any("잔금일 당일 전입신고" in w for w in rejected["warnings"])   # 위험 안내
    assert [t["id"] for t in rejected["moves_to_top"]] == ["T4"]
    assert rejected["documents"] == [] and rejected["link_counsel"] is False
    # 전입신고(T4)가 할 일 맨 위 (AC-016). 비율 96%라 경보로 올라간 반환보증 가입(T5)이 그 다음
    assert c["todos"][0]["rule_id"] == "T4"
    assert _top(c) == ["T4", "T5"]

    inserted = e["S-GUARANTEE-CANCEL"]
    assert inserted["documents"] == [PHOTO]          # 기록함에 남길 서류
    assert inserted["moves_to_top"] == []


def test_guarantee_cancel_rejected(client):
    c = _create(client, {"S-NO-MORTGAGE": "inserted", "S-GUARANTEE-CANCEL": "rejected"})
    rejected = _effects(c)["S-GUARANTEE-CANCEL"]
    assert [t["id"] for t in rejected["moves_to_top"]] == ["T2"]
    assert rejected["link_counsel"] is True          # 공공 상담 창구 연결
    assert any("계약금" in w for w in rejected["warnings"])
    assert c["todos"][0]["rule_id"] == "T2"
    assert "T4" not in _top(c)
    assert _effects(c)["S-NO-MORTGAGE"]["documents"] == [PHOTO]


def test_both_rejected_keeps_number_order(client):
    c = _create(client, {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "rejected"})
    assert _top(c) == ["T2", "T4", "T5"]   # 맨 위 단계 안에서는 번호순 (C7)


def test_patch_changes_branch(client):
    c = _create(client, {"S-NO-MORTGAGE": "inserted", "S-GUARANTEE-CANCEL": "inserted"})
    assert _top(c) == ["T5"]
    url = f"/api/contracts/{c['id']}"
    r = client.patch(url, json={"special_term_result": {"S-NO-MORTGAGE": "rejected"}})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["todos"][0]["rule_id"] == "T4"
    assert _effects(after)["S-NO-MORTGAGE"]["result"] == "rejected"
    assert _effects(after)["S-GUARANTEE-CANCEL"]["result"] == "inserted"   # 보내지 않은 특약은 그대로
    assert client.get(url).json()["special_term_effects"] == after["special_term_effects"]

    back = client.patch(url, json={"special_term_result": {"S-NO-MORTGAGE": "inserted"}}).json()
    assert _top(back) == ["T5"]
    assert _effects(back)["S-NO-MORTGAGE"]["documents"] == [PHOTO]


def test_no_terms_no_effects(client):
    c = _create(client, {})
    assert c["special_term_effects"] == []
    assert _top(c) == ["T5"]
