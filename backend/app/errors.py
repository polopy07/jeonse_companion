"""오류 응답 형식 (docs/api/API_명세.md 1.5절).

모든 오류는 {"detail": {"code", "message", "hint", "fields"}} 한 가지 모양으로 보낸다.
- code: 화면이 분기할 때 쓰는 고정 영문 코드
- message: 사용자에게 그대로 보여 줄 수 있는 문장
- hint: 다음에 할 일 안내 (없으면 null)
- fields: 입력 형식 오류일 때 필드별 문제 [{field, message}] (없으면 빈 목록)
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import ErrorResponse


def responses(*codes: int) -> dict:
    """라우터의 responses= 에 넣어 OpenAPI 문서에 오류 형식을 표시한다."""
    return {code: {"model": ErrorResponse} for code in codes}


def api_error(status: int, code: str, message: str, hint: str | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "hint": hint, "fields": []})


def _field_name(loc: tuple) -> str:
    # ("body", "registry", "mortgage_amount") → "registry.mortgage_amount"
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts)


def _clean(msg: str) -> str:
    return msg.removeprefix("Value error, ")


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": _field_name(e["loc"]), "message": _clean(e["msg"])} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": {
        "code": "INVALID_INPUT",
        "message": "입력 값이 올바르지 않습니다",
        "hint": None,
        "fields": fields,
    }})


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
