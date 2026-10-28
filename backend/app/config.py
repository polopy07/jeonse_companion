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


def require_contract_auth() -> bool:
    """계약 생성에 테스트 결제(payment_id), 계약 아래 API에 접근 토큰(X-Contract-Token)을 꼭 요구할지 (API 명세 1.8).

    앱 연결 전까지 기본은 false(없으면 통과, 보냈는데 틀리면 402·404). 배포 서버는 처음부터 true로 둔다.
    """
    return os.environ.get("REQUIRE_CONTRACT_AUTH", "false").strip().lower() in ("1", "true", "yes", "on")


def allow_virtual_today() -> bool:
    """X-Virtual-Today(시연용 가상 날짜)를 받을지 (API 명세 1.7).

    로컬 개발·시연은 기본 true. 배포 서버는 false로 두어 헤더를 무시하고 실제 오늘(한국 시간)로만 계산한다.
    """
    return os.environ.get("ALLOW_VIRTUAL_TODAY", "true").strip().lower() in ("1", "true", "yes", "on")


def evidence_dir() -> Path:
    """증빙 사진을 저장할 폴더 (FR-029). 기본은 backend/data/evidence (git 제외). 출시 때는 암호화 저장소로 (출시 준비)."""
    return Path(os.environ.get("EVIDENCE_DIR", REPO_ROOT / "backend" / "data" / "evidence"))


def app_link_base() -> str:
    """접근 링크 이메일의 링크 앞부분 (예: 앱 딥링크 jeonse://contract). 없으면 링크 대신 접근 코드만 보낸다."""
    return os.environ.get("APP_LINK_BASE", "").strip()


def llm_explain_enabled() -> bool:
    """등기 항목 쉬운 말 설명에 LLM을 쓸지 (FR-007). ANTHROPIC_API_KEY가 있을 때만 켜고, LLM_EXPLAIN=false면 끈다.
    꺼져 있으면 rules/explain.yaml 템플릿 설명만 쓴다 (테스트·CI·키 없는 개발 환경)."""
    if os.environ.get("LLM_EXPLAIN", "true").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def llm_model(default: str) -> str:
    """설명에 쓸 모델. 기본은 rules/explain.yaml llm.model, LLM_MODEL로 바꾼다."""
    return os.environ.get("LLM_MODEL", "").strip() or default


def data_go_kr_service_key() -> str:
    """공공데이터포털 일반 인증키를 Decoding 키로. 없으면 빈 문자열.

    포털은 같은 키를 Encoding(%2B·%3D 등)과 Decoding 두 가지로 보여 준다. 요청할 때 params로 보내면
    다시 인코딩되므로 Encoding 키가 들어오면 풀어서 쓴다 (Decoding 키에는 %가 없어 그대로).
    """
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    return unquote(key) if "%" in key else key
