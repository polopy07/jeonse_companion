EOK = 100_000_000


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "rules_version": "1.0"}


def test_create_and_get_check(client):
    body = {
        "housing_type": "row_house",
        "deposit": 150_000_000,
        "official_price": 2 * EOK,
        "registry": {"mortgage": True, "mortgage_amount": 120_000_000},
    }
    r = client.post("/api/checks", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["level"] == "check_needed"
    assert created["label"] == "확인 필요"
    assert created["estimated_price"] == 280_000_000
    assert round(created["deposit_ratio"], 4) == 0.9643
    assert [m["id"] for m in created["matched"]] == ["C-1", "C-2"]
    assert created["linkages"] == ["L-MORTGAGE", "L-RATIO90"]

    r = client.get(f"/api/checks/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_missing_official_price_is_422(client):
    r = client.post("/api/checks", json={"housing_type": "apartment", "deposit": EOK})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "MISSING_OFFICIAL_PRICE"
    assert "공시가격" in detail["message"]


def test_not_applicable_needs_no_price(client):
    r = client.post("/api/checks", json={"housing_type": "detached", "deposit": EOK})
    assert r.status_code == 201
    assert r.json()["level"] == "not_applicable"


def test_unknown_check_is_404(client):
    r = client.get("/api/checks/999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_invalid_input_lists_fields(client):
    r = client.post("/api/checks", json={
        "housing_type": "villa", "deposit": 100_000_000,
        "registry": {"mortgage": True, "mortgage_amount": 0},
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_INPUT"
    fields = {f["field"]: f["message"] for f in detail["fields"]}
    assert "housing_type" in fields
    assert fields["registry"] == "근저당이 있으면 채권최고액 합계를 입력해야 합니다"
