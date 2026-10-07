"""DB 연결. DATABASE_URL만 바꾸면 PostgreSQL / SQLite 어느 쪽이든 동작한다."""
from functools import lru_cache

from sqlalchemy import create_engine
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

    Base.metadata.create_all(engine or get_engine())
