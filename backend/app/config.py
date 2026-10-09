"""환경 변수 설정."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def rules_dir() -> Path:
    return Path(os.environ.get("RULES_DIR", REPO_ROOT / "rules"))


def data_go_kr_service_key() -> str:
    """공공데이터포털 일반 인증키 (Decoding 키). 없으면 빈 문자열."""
    return os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
