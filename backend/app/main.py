"""전동기 백엔드. 실행: uvicorn app.main:app --reload (backend/ 폴더에서)"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import checks
from app.db import init_db
from app.rules.loader import get_rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_rules()   # 규칙 파일 오류는 서버 시작 때 바로 드러나게 한다
    init_db()
    yield


app = FastAPI(title="전동기 API", version="0.1.0", lifespan=lifespan)
app.include_router(checks.router)


@app.get("/health")
def health():
    rules = get_rules()
    return {"status": "ok", "rules_version": rules["verdict"]["version"]}
