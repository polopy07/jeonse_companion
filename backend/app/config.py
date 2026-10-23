"""환경 변수 설정."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def rules_dir() -> Path:
    return Path(os.environ.get("RULES_DIR", REPO_ROOT / "rules"))


def admin_token() -> str:
    """관리자 API(/api/admin) 토큰. 없으면 빈 문자열이고 관리자 API는 꺼진다."""
    return os.environ.get("ADMIN_TOKEN", "")


def require_contract_auth() -> bool:
    """계약 생성에 테스트 결제(payment_id), 계약 아래 API에 접근 토큰(X-Contract-Token)을 꼭 요구할지 (API 명세 1.8).

    앱 연결 전까지 기본은 false(없으면 통과, 보냈는데 틀리면 402·404). 배포 서버는 처음부터 true로 둔다.
    """
    return os.environ.get("REQUIRE_CONTRACT_AUTH", "false").strip().lower() in ("1", "true", "yes", "on")


def data_go_kr_service_key() -> str:
    """공공데이터포털 일반 인증키 (Decoding 키). 없으면 빈 문자열."""
    return os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
