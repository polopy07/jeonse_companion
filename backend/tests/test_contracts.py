"""계약 생성 API (POST·GET /api/contracts)."""
from app.db import get_sessionmaker
from app.models import Verdict

EOK = 100_000_000

VILLA = {   # 시연 빌라: 근저당 있음, 비율 96% → 확인 필요
    "housing_type": "row_house",
    "deposit": 150_000_000,
    "official_price": 2 * EOK,
    "exclusive_area": 49.5,
    "registry": {"mortgage": True, "mortgage_amount": 120_000_000},
}
DATES = {"contract_date": "2026-11-02", "balance_date": "2026-12-01", "end_date": "2028-11-30"}


def _check(client, body=VILLA) -> dict:
    r = client.post("/api/checks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _detail(r):
    d = r.json()["detail"]
    assert set(d) == {"code", "message", "hint", "fields"}, d
    return d


def test_create_and_get_contract(client):
    check = _check(client)
    body = {
        "check_id": check["id"], **DATES,
        "loan": True, "loan_execution_date": "2026-12-01", "guarantor": "HUG",
        "email": "tenant@example.com",
        "special_term_result": {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "inserted"},
    }
    r = client.post("/api/contracts", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["check_id"] == check["id"]
    assert created["level"] == "check_needed"
    # 주택 정보는 판정 입력에서 가져온다
    assert created["housing_type"] == "row_house"
    assert created["deposit"] == 150_000_000
    assert created["official_price"] == 2 * EOK
    assert created["exclusive_area"] == 49.5
    # 입력하지 않은 조건은 기본값
    assert created["monthly_rent"] == 0
    assert created["brokered"] is True
    assert created["renewal_right_used"] is False
    assert created["co_tenant"] is False
    assert created["balance_date"] == "2026-12-01"
    assert created["special_term_result"] == {"S-NO-MORTGAGE": "rejected", "S-GUARANTEE-CANCEL": "inserted"}

    r = client.get(f"/api/contracts/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_not_applicable_can_start(client):
    # 다가구·단독은 "대상 아님"이어도 할 일 관리만 시작할 수 있다 (AC-004)
    check = _check(client, {"housing_type": "multi_household", "deposit": EOK})
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert r.status_code == 201, r.text
    assert r.json()["level"] == "not_applicable"
    assert r.json()["official_price"] is None


def test_problem_check_is_blocked(client):
    # "문제 항목" 판정이면 패키지를 시작할 수 없다 (FR-011, AC-003)
    check = _check(client, {**VILLA, "registry": {"seizure": True}})
    assert check["level"] == "problem"
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert r.status_code == 409
    assert _detail(r)["code"] == "CHECK_BLOCKED"


def test_check_used_twice_is_409(client):
    check = _check(client)
    first = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert first.status_code == 201
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert r.status_code == 409
    d = _detail(r)
    assert d["code"] == "CHECK_ALREADY_USED"
    assert f"/api/contracts/{first.json()['id']}" in d["hint"]


def test_unknown_check_is_404(client):
    r = client.post("/api/contracts", json={"check_id": 999, **DATES})
    assert r.status_code == 404
    assert _detail(r)["code"] == "NOT_FOUND"


def test_unknown_contract_is_404(client):
    r = client.get("/api/contracts/999")
    assert r.status_code == 404
    assert _detail(r)["code"] == "NOT_FOUND"


def test_dates_must_be_in_order(client):
    check = _check(client)
    cases = [
        ({"balance_date": "2026-11-01"}, "잔금일은 계약일과 같거나 뒤여야 합니다"),
        ({"end_date": "2026-12-01"}, "만기일은 잔금일보다 뒤여야 합니다"),
        ({"loan_execution_date": "2026-12-01"}, "전세대출이 없으면 대출 실행일을 비워 두세요"),
    ]
    for change, message in cases:
        r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, **change})
        assert r.status_code == 422, change
        d = _detail(r)
        assert d["code"] == "INVALID_INPUT"
        assert d["fields"] == [{"field": "body", "message": message}]


def test_same_day_balance_is_allowed(client):
    check = _check(client)
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "balance_date": DATES["contract_date"]})
    assert r.status_code == 201, r.text


def test_invalid_contract_fields(client):
    check = _check(client)
    r = client.post("/api/contracts", json={
        "check_id": check["id"], **DATES,
        "guarantor": "KB", "email": "not-an-email", "monthly_rent": -1,
        "special_term_result": {"S-NO-MORTGAGE": "maybe"},
    })
    assert r.status_code == 422
    fields = {f["field"]: f["message"] for f in _detail(r)["fields"]}
    assert fields["guarantor"] == "다음 중 하나여야 합니다: HUG, HF, SGI, none"
    assert fields["monthly_rent"] == "0 이상이어야 합니다"
    assert fields["special_term_result.S-NO-MORTGAGE"] == "다음 중 하나여야 합니다: inserted, rejected"
    assert fields["email"] == "형식이 올바르지 않습니다"


def test_unknown_special_term_is_422(client):
    check = _check(client)
    r = client.post("/api/contracts", json={
        "check_id": check["id"], **DATES, "special_term_result": {"S-UNKNOWN": "inserted"},
    })
    assert r.status_code == 422
    d = _detail(r)
    assert d["code"] == "INVALID_INPUT"
    assert d["fields"] == [{"field": "special_term_result.S-UNKNOWN", "message": "규칙 파일에 없는 특약입니다: S-UNKNOWN"}]


def _update_verdict(check_id: int, **values) -> None:
    with get_sessionmaker()() as db:
        row = db.get(Verdict, check_id)
        for k, v in values.items():
            setattr(row, k, v)
        db.commit()


def test_unshown_special_term_is_422(client):
    # 근저당 없는 아파트("문제 없음")에서는 담보 설정 금지 특약을 보여 주지 않으므로 결과도 받지 않는다
    check = _check(client, {"housing_type": "apartment", "deposit": EOK, "official_price": 3 * EOK,
                            "registry": {"mortgage": False}})
    assert check["linkages"] == []
    r = client.post("/api/contracts", json={
        "check_id": check["id"], **DATES, "special_term_result": {"S-NO-MORTGAGE": "rejected"},
    })
    assert r.status_code == 422
    assert _detail(r)["fields"] == [
        {"field": "special_term_result.S-NO-MORTGAGE", "message": "이 판정에서 안내하지 않은 특약입니다: S-NO-MORTGAGE"}]


def test_concurrent_second_contract_is_409(client):
    # 두 요청이 모두 "아직 안 씀"으로 읽은 경우: 늦은 쪽은 check_id unique에 막혀 409, 먼저 만든 계약은 그대로
    check = _check(client)
    first = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert first.status_code == 201
    _update_verdict(check["id"], contract_id=None)
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert r.status_code == 409
    d = _detail(r)
    assert d["code"] == "CHECK_ALREADY_USED"
    assert f"/api/contracts/{first.json()['id']}" in d["hint"]
    assert client.get(f"/api/contracts/{first.json()['id']}").status_code == 200


def test_outdated_level_is_409(client):
    # 규칙 버전이 바뀌어 저장된 판정 단계를 지금 규칙에서 못 찾으면 다시 확인하라고 안내한다
    check = _check(client)
    _update_verdict(check["id"], level="removed_level")
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES})
    assert r.status_code == 409
    assert _detail(r)["code"] == "CHECK_OUTDATED"
    # 판정 결과 조회도 500이 아니라 같은 409
    r = client.get(f"/api/checks/{check['id']}")
    assert r.status_code == 409
    assert _detail(r)["code"] == "CHECK_OUTDATED"
