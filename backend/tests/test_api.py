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


def _detail(r):
    d = r.json()["detail"]
    assert set(d) == {"code", "message", "hint", "fields"}, d   # 모든 오류가 같은 모양
    return d


def test_invalid_input_messages_are_korean(client):
    r = client.post("/api/checks", json={"housing_type": "villa", "registry": {"mortgage_amount": -1}})
    assert r.status_code == 422
    fields = {f["field"]: f["message"] for f in _detail(r)["fields"]}
    assert fields["housing_type"] == "다음 중 하나여야 합니다: apartment, row_house, officetel, multi_household, detached"
    assert fields["deposit"] == "필수 입력입니다"
    assert fields["registry.mortgage_amount"] == "0 이상이어야 합니다"
    assert fields["deposit"] != "Field required"


def test_invalid_body_shape_has_body_field(client):
    for r in (client.post("/api/checks", json=[]), client.post("/api/checks")):
        assert r.status_code == 422
        assert [f["field"] for f in _detail(r)["fields"]] == ["body"]
    r = client.post("/api/checks", content=b'{"deposit": ', headers={"content-type": "application/json"})
    assert r.status_code == 422
    fields = _detail(r)["fields"]
    assert [f["field"] for f in fields] == ["body"]
    assert fields[0]["message"] == "JSON 형식이 올바르지 않습니다"


def test_unknown_path_and_method_use_error_format(client):
    r = client.get("/api/check/999")
    assert r.status_code == 404
    assert _detail(r)["code"] == "NOT_FOUND"
    r = client.delete("/api/checks/1")
    assert r.status_code == 405
    assert _detail(r)["code"] == "METHOD_NOT_ALLOWED"
    assert "allow" in r.headers   # 프레임워크가 붙인 헤더 유지


def test_unhandled_exception_is_json_500(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    def boom(*a, **k):
        raise RuntimeError("내부 오류")

    monkeypatch.setattr("app.api.checks.run_check", boom)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/api/checks", json={"housing_type": "apartment", "deposit": 100_000_000, "official_price": 200_000_000})
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    assert _detail(r)["code"] == "INTERNAL_ERROR"
    assert "내부 오류" not in r.text   # 내부 정보를 응답에 싣지 않는다
