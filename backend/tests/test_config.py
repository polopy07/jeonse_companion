"""환경 변수 설정."""
from app.config import REPO_ROOT, data_go_kr_service_key, database_url


def test_service_key_decoding_kept(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "abc+def/ghi==")
    assert data_go_kr_service_key() == "abc+def/ghi=="


def test_service_key_encoding_unquoted(monkeypatch):
    # 포털 마이페이지의 Encoding 키를 그대로 넣어도 Decoding 키로 바꿔 쓴다 (params로 보내면 다시 인코딩됨)
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", " abc%2Bdef%2Fghi%3D%3D\n")
    assert data_go_kr_service_key() == "abc+def/ghi=="


def test_service_key_missing(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    assert data_go_kr_service_key() == ""


def test_database_default_is_sqlite_file(monkeypatch):
    # MVP 기본 DB는 backend/data/jeonse.db (DATABASE_URL이 없거나 빈 값이면)
    for value in (None, "", "  "):
        if value is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", value)
        assert database_url() == f"sqlite:///{REPO_ROOT / 'backend' / 'data' / 'jeonse.db'}"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    assert database_url().startswith("postgresql")
