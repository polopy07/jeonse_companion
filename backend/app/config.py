"""환경 변수 설정."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def rules_dir() -> Path:
    return Path(os.environ.get("RULES_DIR", REPO_ROOT / "rules"))
