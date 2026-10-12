EOK = 100_000_000


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "rules_version": "1.1"}


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


def test_integer_fields_say_integer(client):
    r = client.post("/api/checks", json={"housing_type": "apartment", "deposit": 1.5, "official_price": 200_000_000})
    assert r.status_code == 422
    fields = {f["field"]: f["message"] for f in _detail(r)["fields"]}
    assert fields["deposit"] == "정수로 입력하세요"


def test_registry_file_sent_as_text_is_korean(client):
    r = client.post("/api/registry/parse", data={"file": "not a file"})
    assert r.status_code == 422
    fields = {f["field"]: f["message"] for f in _detail(r)["fields"]}
    assert fields["file"] == "파일을 올려야 합니다"


def test_choices_and_value_error_messages():
    from app.errors import _choices, _message
    assert _choices("'a', 'b' or 'c'") == "a, b, c"
    assert _choices("1 or 2") == "1, 2"
    assert _message({"type": "literal_error", "msg": "Input should be 1 or 2", "ctx": {"expected": "1 or 2"}}) == "다음 중 하나여야 합니다: 1, 2"
    assert _message({"type": "literal_error", "msg": "Input should be 1 or 2", "ctx": {}}) == "Input should be 1 or 2"
    assert _message({"type": "value_error", "msg": "Value error, 근저당이 있으면 채권최고액 합계를 입력해야 합니다"}) == "근저당이 있으면 채권최고액 합계를 입력해야 합니다"
    assert _message({"type": "value_error", "msg": "Value error, something internal"}) == "값이 올바르지 않습니다"


def test_plain_http_exception_keeps_reason_and_logs(caplog):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from app import errors

    mini = FastAPI()
    errors.install(mini)

    @mini.get("/blocked")
    def blocked():
        raise HTTPException(409, "문제 항목 판정이라 패키지를 시작할 수 없습니다")

    with caplog.at_level("WARNING", logger="app.errors"):
        r = TestClient(mini).get("/blocked")
    assert r.status_code == 409
    d = _detail(r)
    assert d["code"] == "HTTP_ERROR"
    assert d["message"] == "문제 항목 판정이라 패키지를 시작할 수 없습니다"
    assert "문제 항목 판정이라" in caplog.text


def _special_terms(client, body):
    check = client.post("/api/checks", json=body).json()
    r = client.get(f"/api/checks/{check['id']}/special-terms")
    assert r.status_code == 200, r.text
    return r.json()


def test_special_terms_for_mortgage_and_high_ratio(client):
    # 근저당 + 비율 96%: 담보 설정 금지, 보증·대출 거절 시 해제 (FR-039)
    out = _special_terms(client, {
        "housing_type": "row_house", "deposit": 150_000_000, "official_price": 2 * EOK,
        "registry": {"mortgage": True, "mortgage_amount": 120_000_000},
    })
    assert out["level"] == "check_needed"
    assert [t["id"] for t in out["terms"]] == ["S-NO-MORTGAGE", "S-GUARANTEE-CANCEL"]
    no_mortgage, cancel = out["terms"]
    assert no_mortgage["linked"] == [{"id": "L-MORTGAGE", "label": "근저당 있음"}]
    assert no_mortgage["text"].startswith("임대인은 잔금 지급일 다음 날까지")
    assert no_mortgage["source"]
    # 거절당함 → 경고 + 전입신고(T4) 맨 위 (AC-016), 넣음 → 계약서 사진
    assert no_mortgage["if_rejected"]["moves_to_top"] == [{"id": "T4", "title": "전입신고"}]
    assert "전입신고" in no_mortgage["if_rejected"]["warnings"][0]
    assert no_mortgage["if_inserted"]["documents"] == ["특약이 보이는 계약서 사진"]
    assert cancel["linked"] == [{"id": "L-RATIO90", "label": "내 보증금 비율 90% 이상"}]
    assert cancel["if_rejected"]["moves_to_top"] == [{"id": "T2", "title": "보증 가입 여부 확정"}]
    assert cancel["if_rejected"]["link_counsel"] is True
    assert out["warnings"] == [
        "선순위 채권(근저당 채권최고액)을 반영한 내 보증금 비율을 다시 계산했습니다",
        "반환보증 가입이 어려울 수 있습니다",
    ]
    assert out["disclaimer"] == "정보 제공이며 보증하지 않습니다."
    assert out["rules_version"] == "1.1"


def test_special_terms_trust_asks_for_consent(client):
    # 신탁은 특약 예시 대신 계약 당일 동의서 확인 (linkage.yaml L-TRUST)
    out = _special_terms(client, {
        "housing_type": "apartment", "deposit": EOK, "official_price": 2 * EOK, "registry": {"trust": True},
    })
    assert out["terms"] == []
    assert out["checks"] == ["신탁사 동의서 확인"]


def test_special_terms_skip_non_mvp(client):
    # 위반건축물(L-VIOLATION)은 MVP 밖이라 연결된 특약을 보여 주지 않는다. 체납 완납증명(S-TAX-CERT)도 MVP 밖
    out = _special_terms(client, {
        "housing_type": "apartment", "deposit": EOK, "official_price": 2 * EOK, "registry": {},
        "building_violation": True,
    })
    assert out["level"] == "check_needed"
    assert out["terms"] == [] and out["warnings"] == [] and out["checks"] == []


def test_special_terms_no_problem_and_not_found(client):
    out = _special_terms(client, {"housing_type": "apartment", "deposit": EOK, "official_price": 2 * EOK, "registry": {}})
    assert out["level"] == "no_problem" and out["terms"] == []
    r = client.get("/api/checks/999/special-terms")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_check_result_has_explanations(client):
    r = client.post("/api/checks", json={
        "housing_type": "row_house", "deposit": 150_000_000, "official_price": 2 * EOK,
        "registry": {"mortgage": True, "mortgage_amount": 120_000_000},
    })
    created = r.json()
    explained = {m["id"]: m["explanation"] for m in created["matched"]}
    assert explained["C-1"].startswith("집이 경매로 넘어가면")
    assert explained["C-2"].startswith("반환보증 가입이 어려운 구간")
    assert created["unchecked"][0]["id"] == "U-TAX"
    assert "완납증명서" in created["unchecked"][0]["guide"]
    assert created["rules_version"] == "1.1"
    assert client.get(f"/api/checks/{created['id']}").json() == created


def test_not_applicable_explanation(client):
    r = client.post("/api/checks", json={"housing_type": "detached", "deposit": EOK})
    created = r.json()
    assert created["matched"][0]["id"] == "NA-1"
    assert "다른 세대의 보증금" in created["matched"][0]["explanation"]
    assert [u["id"] for u in created["unchecked"]] == ["U-TAX", "U-OTHER-DEPOSITS"]
    assert all(u["guide"] for u in created["unchecked"])
