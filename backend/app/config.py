"""환경 변수 설정."""
import os
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def rules_dir() -> Path:
    return Path(os.environ.get("RULES_DIR", REPO_ROOT / "rules"))


def admin_token() -> str:
    """관리자 API(/api/admin) 토큰. 없으면 빈 문자열이고 관리자 API는 꺼진다."""
    return os.environ.get("ADMIN_TOKEN", "")


def data_go_kr_service_key() -> str:
    """공공데이터포털 일반 인증키를 Decoding 키로. 없으면 빈 문자열.

    포털은 같은 키를 Encoding(%2B·%3D 등)과 Decoding 두 가지로 보여 준다. 요청할 때 params로 보내면
    다시 인코딩되므로 Encoding 키가 들어오면 풀어서 쓴다 (Decoding 키에는 %가 없어 그대로).
    """
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    return unquote(key) if "%" in key else key
