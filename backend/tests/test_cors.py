"""웹 개발용 CORS (웹은 개발 편의용, 시연·제공은 휴대폰 앱)."""
from app.config import cors_origins

EXPO_WEB = "http://localhost:8081"


def test_preflight_from_expo_web(client):
    r = client.options("/api/checks", headers={
        "Origin": EXPO_WEB, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-contract-token,x-virtual-today"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == EXPO_WEB
    assert "access-control-allow-credentials" not in r.headers


def test_other_origin_not_allowed(client):
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
    r = client.options("/api/checks", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 400


def test_cors_origins_setting(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " http://192.168.0.10:8081/ , http://localhost:8081 ")
    assert cors_origins() == ["http://192.168.0.10:8081", "http://localhost:8081"]
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert cors_origins() == []
