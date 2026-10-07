"""테스트 설정.

기본은 임시 SQLite 파일. PostgreSQL로 돌리려면:
    TEST_DATABASE_URL=postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse_test pytest
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, get_engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.rules.loader import get_rules  # noqa: E402


@pytest.fixture(scope="session")
def rules():
    return get_rules()


@pytest.fixture
def client():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    init_db(engine)
    with TestClient(app) as c:
        yield c
