"""docs/api/openapi.json이 서버 코드와 같은 API인지 검사. 다르면 backend/에서 python export_openapi.py

FastAPI·pydantic 버전마다 스키마 글자가 조금씩 달라지므로 파일 전체를 글자 단위로 비교하지 않고,
프론트가 기대는 것(주소, 메서드, 응답 상태 코드와 응답 형식 이름, 정의된 형식 이름)만 비교한다.
"""
import json

from export_openapi import OPENAPI_PATH
from app.main import app


def _schema_name(response: dict) -> str | None:
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref") or schema.get("items", {}).get("$ref")
    return ref.rsplit("/", 1)[-1] if ref else None


def summarize(spec: dict) -> dict:
    ops = {
        f"{method.upper()} {path}": {code: _schema_name(resp) for code, resp in sorted(op.get("responses", {}).items())}
        for path, item in spec["paths"].items()
        for method, op in item.items()
    }
    return {"operations": ops, "schemas": sorted(spec.get("components", {}).get("schemas", {}))}


def test_openapi_file_is_up_to_date():
    assert OPENAPI_PATH.exists(), "docs/api/openapi.json이 없습니다. backend/에서 python export_openapi.py로 만드세요"
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert summarize(committed) == summarize(app.openapi()), "API가 바뀌었습니다. python export_openapi.py로 openapi.json을 다시 만드세요"
