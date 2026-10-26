"""테스트 결제(POST /api/checks/{id}/payment), 계약 접근 토큰, 계약 무산 (API 명세 1.8, 결정 자료 #86·#88)."""
import pytest
from sqlalchemy import text

from app.api import contracts
from app.db import get_engine, init_db
from tests.test_contracts import DATES, EOK, VILLA, _check, _detail

HOUSE = {"housing_type": "multi_household", "deposit": EOK}   # 다가구 → 할 일 관리만 4,900원


@pytest.fixture
def strict(monkeypatch):
    """배포 서버 설정: 결제·토큰을 꼭 요구한다."""
    monkeypatch.setenv("REQUIRE_CONTRACT_AUTH", "true")


def _pay(client, check_id) -> dict:
    r = client.post(f"/api/checks/{check_id}/payment")
    assert r.status_code == 201, r.text
    return r.json()


def _contract(client, check_id, payment_id=None, headers=None) -> dict:
    body = {"check_id": check_id, **DATES}
    if payment_id is not None:
        body["payment_id"] = payment_id
    r = client.post("/api/contracts", json=body, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()


def _auth(contract) -> dict:
    return {"X-Contract-Token": contract["access_token"]}


# ---- 테스트 결제 ----

def test_payment_amount_by_level(client):
    villa = _pay(client, _check(client)["id"])
    assert villa["product"] == "package" and villa["amount"] == 9_900
    assert villa["method"] == "test" and villa["status"] == "paid"
    house = _pay(client, _check(client, HOUSE)["id"])
    assert house["product"] == "todo_only" and house["amount"] == 4_900


def test_payment_twice_returns_same(client):
    check = _check(client)
    first = _pay(client, check["id"])
    r = client.post(f"/api/checks/{check['id']}/payment")
    assert r.status_code == 200
    assert r.json() == first


def test_payment_blocked_and_missing(client):
    blocked = _check(client, {**VILLA, "registry": {"seizure": True}})
    r = client.post(f"/api/checks/{blocked['id']}/payment")
    assert r.status_code == 409 and _detail(r)["code"] == "CHECK_BLOCKED"
    r = client.post("/api/checks/999/payment")
    assert r.status_code == 404 and _detail(r)["code"] == "NOT_FOUND"


def test_payment_after_contract_is_409(client):
    check = _check(client)
    _contract(client, check["id"], _pay(client, check["id"])["payment_id"])
    r = client.post(f"/api/checks/{check['id']}/payment")
    assert r.status_code == 409 and _detail(r)["code"] == "CHECK_ALREADY_USED"


# ---- 계약 생성의 결제 확인 (402) ----

def test_contract_uses_payment(client):
    check = _check(client)
    pay = _pay(client, check["id"])
    c = _contract(client, check["id"], pay["payment_id"])
    assert c["payment_id"] == pay["payment_id"] and c["status"] == "active"
    assert len(c["access_token"]) >= 40
    # 쓴 결제는 다른 판정에 쓸 수 없다
    other = _check(client)
    r = client.post("/api/contracts", json={"check_id": other["id"], **DATES, "payment_id": pay["payment_id"]})
    assert r.status_code == 402 and _detail(r)["code"] == "PAYMENT_REQUIRED"


def test_payment_of_other_check_is_402(client):
    pay = _pay(client, _check(client)["id"])
    other = _check(client)
    r = client.post("/api/contracts", json={"check_id": other["id"], **DATES, "payment_id": pay["payment_id"]})
    assert r.status_code == 402 and _detail(r)["code"] == "PAYMENT_REQUIRED"
    r = client.post("/api/contracts", json={"check_id": other["id"], **DATES, "payment_id": 999})
    assert r.status_code == 402


def test_without_payment_passes_until_required(client):
    # 앱 연결 전(기본): 결제 없이도 계약을 만든다
    c = _contract(client, _check(client)["id"])
    assert c["payment_id"] is None


def test_without_payment_is_402_when_required(client, strict):
    r = client.post("/api/contracts", json={"check_id": _check(client)["id"], **DATES})
    assert r.status_code == 402 and _detail(r)["code"] == "PAYMENT_REQUIRED"


# ---- 계약 접근 토큰 ----

def test_token_checks(client):
    c = _contract(client, _check(client)["id"])
    url = f"/api/contracts/{c['id']}"
    assert client.get(url, headers=_auth(c)).status_code == 200
    # 보냈는데 틀리면 언제나 계약이 없을 때와 같은 404
    r = client.get(url, headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404 and _detail(r)["code"] == "NOT_FOUND"
    assert client.patch(url, json={"monthly_rent": 0}, headers={"X-Contract-Token": "wrong"}).status_code == 404
    # 앱 연결 전(기본)에는 토큰 없이도 통과
    assert client.get(url).status_code == 200


def test_token_required(client, strict):
    check = _check(client)
    c = _contract(client, check["id"], _pay(client, check["id"])["payment_id"])
    url = f"/api/contracts/{c['id']}"
    r = client.get(url)
    missing = client.get("/api/contracts/999", headers=_auth(c))
    assert r.status_code == 404 and missing.status_code == 404
    assert r.json() == {**missing.json()}   # 남의 계약과 없는 계약을 구별할 수 없다
    assert client.get(url, headers=_auth(c)).status_code == 200
    assert client.patch(url, json={"monthly_rent": 0}).status_code == 404
    assert client.patch(url, json={"monthly_rent": 0}, headers=_auth(c)).status_code == 200


def test_token_not_stored_in_plain(client):
    c = _contract(client, _check(client)["id"])
    with get_engine().connect() as conn:
        stored = conn.execute(text("SELECT access_token_hash FROM contracts WHERE id = :i"), {"i": c["id"]}).scalar()
    assert stored and stored != c["access_token"] and len(stored) == 64


# ---- 계약 무산 (FR-016) ----

def test_cancel_releases_payment_for_next_house(client):
    check = _check(client)
    pay = _pay(client, check["id"])
    c = _contract(client, check["id"], pay["payment_id"])
    r = client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert len(r.json()["todos"]) == len(c["todos"])   # 할 일은 기록으로 남는다

    # 무산된 계약: 보기만 되고 바꾸는 요청은 409
    url = f"/api/contracts/{c['id']}"
    assert client.get(url, headers=_auth(c)).json()["status"] == "cancelled"
    r = client.patch(url, json={"monthly_rent": 0}, headers=_auth(c))
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"
    r = client.post(f"{url}/cancel", headers=_auth(c))
    assert r.status_code == 409 and _detail(r)["code"] == "CONTRACT_CANCELLED"

    # 풀린 결제를 다음 집 판정의 계약에 다시 쓴다 (무산된 계약의 토큰과 함께, 한 번만)
    nxt = _check(client)
    c2 = _contract(client, nxt["id"], pay["payment_id"], headers=_auth(c))
    assert c2["payment_id"] == pay["payment_id"]
    third = _check(client)
    r = client.post("/api/contracts", json={"check_id": third["id"], **DATES, "payment_id": pay["payment_id"]},
                    headers=_auth(c))
    assert r.status_code == 402


def test_released_payment_product_rules(client):
    # 패키지 결제 → 다가구(할 일 관리만) 집: 그대로 씀
    villa = _check(client)
    pay = _pay(client, villa["id"])
    c = _contract(client, villa["id"], pay["payment_id"])
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))
    reused = _contract(client, _check(client, HOUSE)["id"], pay["payment_id"], headers=_auth(c))
    assert reused["payment_id"] == pay["payment_id"]

    # 할 일 관리만 결제 → 패키지 집: 다시 결제 (402)
    house = _check(client, HOUSE)
    small = _pay(client, house["id"])
    c = _contract(client, house["id"], small["payment_id"])
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))
    r = client.post("/api/contracts", json={"check_id": _check(client)["id"], **DATES, "payment_id": small["payment_id"]},
                    headers=_auth(c))
    assert r.status_code == 402
    assert "다시 결제" in _detail(r)["hint"]


def test_released_payment_needs_owner_token(client):
    # 결제 번호만 알아서는 남의 풀린 결제를 쓸 수 없다 (#89 리뷰). 배포 설정과 상관없이 언제나
    check = _check(client)
    pay = _pay(client, check["id"])
    c = _contract(client, check["id"], pay["payment_id"])
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))
    other = _contract(client, _check(client)["id"])   # 다른 사람의 계약 토큰

    nxt = _check(client)
    body = {"check_id": nxt["id"], **DATES, "payment_id": pay["payment_id"]}
    for headers in ({}, {"X-Contract-Token": "wrong"}, _auth(other)):
        r = client.post("/api/contracts", json=body, headers=headers)
        assert r.status_code == 402 and _detail(r)["code"] == "PAYMENT_REQUIRED"
    assert _contract(client, nxt["id"], pay["payment_id"], headers=_auth(c))["payment_id"] == pay["payment_id"]


def test_released_payment_taken_once_under_race(client, monkeypatch):
    # 같은 풀린 결제로 두 계약이 동시에 들어와 둘 다 확인을 통과해도, 먼저 커밋한 쪽만 쓴다 (#89 리뷰)
    check = _check(client)
    pay = _pay(client, check["id"])
    c = _contract(client, check["id"], pay["payment_id"])
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_auth(c))

    original = contracts._alert_level

    def other_request_commits_first(check, rules):
        # 이 요청이 결제를 확인한 뒤, 계약을 저장하기 전에 다른 요청이 같은 결제를 먼저 씀
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE payments SET status = 'used', contract_id = 999 WHERE id = :id"),
                         {"id": pay["payment_id"]})
        return original(check, rules)

    monkeypatch.setattr(contracts, "_alert_level", other_request_commits_first)
    nxt = _check(client)
    r = client.post("/api/contracts", json={"check_id": nxt["id"], **DATES, "payment_id": pay["payment_id"]},
                    headers=_auth(c))
    assert r.status_code == 402 and _detail(r)["code"] == "PAYMENT_REQUIRED"
    assert client.get(f"/api/checks/{nxt['id']}").json()["contract_id"] is None   # 늦은 쪽 계약은 남지 않는다


def test_cancel_needs_token(client):
    c = _contract(client, _check(client)["id"])
    r = client.post(f"/api/contracts/{c['id']}/cancel", headers={"X-Contract-Token": "wrong"})
    assert r.status_code == 404


# ---- 예전 DB에 새 칸 더하기 ----

def test_init_db_adds_new_columns(client):
    engine = get_engine()
    c = _contract(client, _check(client)["id"])
    with engine.begin() as conn:   # 이번 PR 전의 contracts 표처럼 새 칸을 지운다
        for col in ("access_token_hash", "payment_id", "status", "cancelled_at"):
            conn.execute(text(f"ALTER TABLE contracts DROP COLUMN {col}"))
    init_db(engine)
    r = client.get(f"/api/contracts/{c['id']}")
    assert r.status_code == 200 and r.json()["status"] == "active"
