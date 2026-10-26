"""전동기 백엔드. 실행: uvicorn app.main:app --reload (backend/ 폴더에서)"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.api import admin, checks, contracts, demo, registry
from app.config import cors_origins
from app.db import init_db
from app.rules.loader import get_rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_rules()   # 규칙 파일 오류는 서버 시작 때 바로 드러나게 한다
    init_db()
    yield


app = FastAPI(title="전동기 API", version="0.1.0", lifespan=lifespan)
errors.install(app)
if cors_origins():
    # 웹(expo start --web)으로 개발할 때 브라우저가 API를 부르게. 쿠키는 쓰지 않고 계약 토큰은 헤더로 보낸다
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=False, allow_methods=["*"],
                       allow_headers=["Content-Type", "X-Contract-Token", "X-Virtual-Today", "X-Admin-Token"])
app.include_router(checks.router)
app.include_router(contracts.router)
app.include_router(registry.router)
app.include_router(demo.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    rules = get_rules()
    return {"status": "ok", "rules_version": rules["verdict"]["version"]}
