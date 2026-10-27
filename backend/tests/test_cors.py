"""웹 개발용 CORS (웹은 개발 편의용, 시연·제공은 휴대폰 앱). 앱은 CORS_ORIGINS를 만들 때 한 번 읽어서 설정마다 다시 만든다."""
import pytest
from fastapi.testclient import TestClient

from app.config import cors_origins
from app.main import create_app

EXPO_WEB = "http://localhost:8081"


def _client(monkeypatch, origins: str | None) -> TestClient:
    if origins is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", origins)
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("처리하지 못한 오류")

    return TestClient(app, raise_server_exceptions=False)


def _preflight(c: TestClient, origin: str):
    return c.options("/api/checks", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-contract-token,x-virtual-today"})


def test_preflight_from_expo_web(monkeypatch):
    c = _client(monkeypatch, f"{EXPO_WEB},http://127.0.0.1:8081")
    r = _preflight(c, EXPO_WEB)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == EXPO_WEB
    assert "access-control-allow-credentials" not in r.headers


def test_server_error_keeps_cors_header(monkeypatch):
    # #105 리뷰 1번: 500도 허용한 웹 주소에는 CORS 헤더를 붙여, 브라우저가 CORS 오류가 아닌 {code, message}를 받게
    c = _client(monkeypatch, EXPO_WEB)
    r = c.get("/boom", headers={"Origin": EXPO_WEB})
    assert r.status_code == 500 and r.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert r.headers["access-control-allow-origin"] == EXPO_WEB
    r = c.get("/boom", headers={"Origin": "https://evil.example"})
    assert r.status_code == 500 and "access-control-allow-origin" not in r.headers


def test_other_origin_not_allowed(monkeypatch):
    c = _client(monkeypatch, EXPO_WEB)
    r = c.get("/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
    assert _preflight(c, "https://evil.example").status_code == 400


@pytest.mark.parametrize("origins", [None, ""])
def test_cors_off_by_default_and_when_empty(monkeypatch, origins):
    # #105 리뷰 2번: 기본은 끔(.env.example을 그대로 쓴 배포 서버도 꺼짐), 빈 값도 끔
    c = _client(monkeypatch, origins)
    r = _preflight(c, EXPO_WEB)
    assert "access-control-allow-origin" not in r.headers
    r = c.get("/boom", headers={"Origin": EXPO_WEB})
    assert r.status_code == 500 and "access-control-allow-origin" not in r.headers


def test_cors_origins_setting(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " http://192.168.0.10:8081/ , http://localhost:8081 ")
    assert cors_origins() == ["http://192.168.0.10:8081", "http://localhost:8081"]
    monkeypatch.delenv("CORS_ORIGINS")
    assert cors_origins() == []
