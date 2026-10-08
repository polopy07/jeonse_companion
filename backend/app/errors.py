"""오류 응답 형식 (docs/api/API_명세.md 1.5절).

모든 오류는 {"detail": {"code", "message", "hint", "fields"}} 한 가지 모양으로 보낸다.
- code: 화면이 분기할 때 쓰는 고정 영문 코드
- message: 사용자에게 그대로 보여 줄 수 있는 문장
- hint: 다음에 할 일 안내 (없으면 null)
- fields: 입력 형식 오류일 때 필드별 문제 [{field, message}] (없으면 빈 목록)

우리 코드가 올리는 오류(api_error), 입력 검증 오류, 프레임워크가 내는 오류(없는 주소·허용 안 되는 메서드),
처리하지 못한 예외(500)가 모두 이 모양으로 나간다.
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)

# 프레임워크가 문자열 detail로 내는 오류의 코드·문구
_STATUS_ERRORS = {
    404: ("NOT_FOUND", "요청한 주소를 찾을 수 없습니다"),
    405: ("METHOD_NOT_ALLOWED", "이 주소에서 허용되지 않는 요청 방식입니다"),
}
_DEFAULT_HTTP_ERROR = ("HTTP_ERROR", "요청을 처리할 수 없습니다")


def responses(*codes: int) -> dict:
    """라우터의 responses= 에 넣어 OpenAPI 문서에 오류 형식을 표시한다."""
    return {code: {"model": ErrorResponse} for code in codes}


def _detail(code: str, message: str, hint: str | None = None, fields: list | None = None) -> dict:
    return {"code": code, "message": message, "hint": hint, "fields": fields or []}


def api_error(status: int, code: str, message: str, hint: str | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail=_detail(code, message, hint))


# 위치 목록의 첫 요소 (요청의 어느 부분인지)
_LOCATIONS = ("body", "query", "path", "header", "cookie")
BODY_FIELD = "body"   # 특정 필드가 아니라 요청 본문 전체가 문제일 때


def _field_name(error: dict) -> str:
    # ("body", "registry", "mortgage_amount") → "registry.mortgage_amount"
    # ("header", "x-virtual-today") → "x-virtual-today"
    loc = tuple(error["loc"])
    if error["type"] == "json_invalid":   # loc가 ("body", <깨진 글자 위치>)
        return BODY_FIELD
    if loc and loc[0] in _LOCATIONS:      # 맨 앞 하나만 뗀다. 안쪽 필드 이름이 body 등이어도 남는다
        loc = loc[1:]
    return ".".join(str(p) for p in loc) or BODY_FIELD


def _quoted_list(expected: str) -> str:
    # "'a', 'b' or 'c'" → "a, b, c"
    return expected.replace("' or '", "', '").replace("'", "")


def _message(error: dict) -> str:
    """pydantic 오류를 한국어 문장으로. 목록에 없는 종류는 원문(영어)을 그대로 쓴다."""
    ctx = error.get("ctx") or {}
    match error["type"]:
        case "missing":
            return "필수 입력입니다"
        case "literal_error" | "enum":
            return f"다음 중 하나여야 합니다: {_quoted_list(str(ctx.get('expected', '')))}"
        case "int_parsing" | "int_type" | "int_from_float" | "float_parsing" | "float_type":
            return "숫자로 입력하세요"
        case "bool_parsing" | "bool_type":
            return "true 또는 false로 입력하세요"
        case "string_type":
            return "문자로 입력하세요"
        case "greater_than":
            return f"{ctx.get('gt')}보다 커야 합니다"
        case "greater_than_equal":
            return f"{ctx.get('ge')} 이상이어야 합니다"
        case "less_than":
            return f"{ctx.get('lt')}보다 작아야 합니다"
        case "less_than_equal":
            return f"{ctx.get('le')} 이하여야 합니다"
        case "json_invalid":
            return "JSON 형식이 올바르지 않습니다"
        case "model_attributes_type" | "dict_type":
            return "객체 형태로 보내야 합니다"
        case "date_parsing" | "date_type" | "date_from_datetime_parsing":
            return "YYYY-MM-DD 형식으로 입력하세요"
        case "value_error":   # 우리가 validator에서 직접 쓴 한국어 문장
            return error["msg"].removeprefix("Value error, ")
        case _:
            return error["msg"]


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": _field_name(e), "message": _message(e)} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": _detail("INVALID_INPUT", "입력 값이 올바르지 않습니다", fields=fields)})


async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:   # api_error로 올린 것은 그대로
        content = {"detail": exc.detail}
    else:
        code, message = _STATUS_ERRORS.get(exc.status_code, _DEFAULT_HTTP_ERROR)
        content = {"detail": _detail(code, message)}
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리하지 못한 오류: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": _detail(
        "INTERNAL_ERROR", "서버에 문제가 생겼습니다", "잠시 후 다시 시도하세요")})


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
