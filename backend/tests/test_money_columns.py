"""큰 금액 저장 (PostgreSQL int4 최대 2,147,483,647원 ≈ 21.4억을 넘는 값).

SQLite는 정수 크기를 가리지 않아 넘침이 드러나지 않는다. 그래서 칸 형식(BigInteger)을 따로 검사하고,
API 테스트는 TEST_DATABASE_URL로 PostgreSQL에서 돌렸을 때 실제로 저장되는지 확인한다.
"""
from sqlalchemy import BigInteger

from app.db import get_sessionmaker
from app.models import Alert, Contract, Verdict

EOK = 100_000_000
INT4_MAX = 2_147_483_647

# 원 단위 금액 칸
MONEY_COLUMNS = [
    (Contract, "deposit"),
    (Contract, "monthly_rent"),
    (Contract, "official_price"),
    (Verdict, "estimated_price"),
    (Alert, "estimated_price"),
]

BIG_APARTMENT = {   # 공시가격 20억 → 추정 주택가격 28억, 보증금 25억
    "housing_type": "apartment",
    "deposit": 25 * EOK,
    "official_price": 20 * EOK,
}
DATES = {"contract_date": "2026-11-02", "balance_date": "2026-12-01", "end_date": "2028-11-30"}


def test_money_columns_are_bigint():
    for model, name in MONEY_COLUMNS:
        assert isinstance(model.__table__.c[name].type, BigInteger), f"{model.__tablename__}.{name}"


def test_check_with_big_amounts(client):
    r = client.post("/api/checks", json=BIG_APARTMENT)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["estimated_price"] == 28 * EOK
    assert created["estimated_price"] > INT4_MAX

    r = client.get(f"/api/checks/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_contract_with_big_amounts(client):
    check = client.post("/api/checks", json=BIG_APARTMENT).json()
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "monthly_rent": 30 * EOK})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["deposit"] == 25 * EOK
    assert created["official_price"] == 20 * EOK
    assert created["monthly_rent"] == 30 * EOK

    r = client.get(f"/api/contracts/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_alert_with_big_estimated_price(client):
    # 경보 API가 아직 없어 모델로 직접 저장한다
    check = client.post("/api/checks", json=BIG_APARTMENT).json()
    contract = client.post("/api/contracts", json={"check_id": check["id"], **DATES}).json()
    with get_sessionmaker()() as db:
        db.add(Alert(contract_id=contract["id"], level=None, estimated_price=28 * EOK, deposit_ratio=0.8929))
        db.commit()
        assert db.query(Alert).one().estimated_price == 28 * EOK


def test_amount_over_limit_is_422(client):
    # 1조 원을 넘는 금액은 DB에 닿기 전에 422 (BigInteger 범위를 넘으면 저장 때 500이 났다)
    huge = 10**19
    cases = [
        ("/api/checks", {**BIG_APARTMENT, "official_price": huge}, "official_price"),
        ("/api/checks", {"housing_type": "detached", "deposit": huge}, "deposit"),
        ("/api/checks", {**BIG_APARTMENT, "trade_price": huge}, "trade_price"),
        ("/api/checks", {**BIG_APARTMENT, "registry": {"mortgage": True, "mortgage_amount": huge}}, "registry.mortgage_amount"),
    ]
    for path, body, field in cases:
        r = client.post(path, json=body)
        assert r.status_code == 422, (field, r.text)
        fields = {f["field"]: f["message"] for f in r.json()["detail"]["fields"]}
        assert fields[field] == "1,000,000,000,000 이하여야 합니다"

    check = client.post("/api/checks", json=BIG_APARTMENT).json()
    r = client.post("/api/contracts", json={"check_id": check["id"], **DATES, "monthly_rent": huge})
    assert r.status_code == 422
    assert r.json()["detail"]["fields"] == [{"field": "monthly_rent", "message": "1,000,000,000,000 이하여야 합니다"}]
