"""DB 연결. DATABASE_URL만 바꾸면 PostgreSQL / SQLite 어느 쪽이든 동작한다."""
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import database_url


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db():
    """FastAPI 의존성: 요청마다 세션 1개."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def init_db(engine=None) -> None:
    # MVP는 시작할 때 테이블을 만든다. 스키마가 자주 바뀌기 시작하면 Alembic으로 옮긴다.
    from app import models  # noqa: F401  (테이블 등록)

    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """이미 있는 표에 새로 생긴 칸을 더한다 (create_all은 있는 표를 고치지 않음).

    새 칸은 비워 둘 수 있거나 server_default가 있는 것만 만든다. 칸 이름·종류를 바꾸거나 지우는 것은
    하지 않는다 → 그럴 때는 reset_demo_db.py로 다시 만든다.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}'"
                conn.execute(text(ddl))
