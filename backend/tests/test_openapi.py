"""docs/api/openapi.json이 서버 코드와 같은 API인지 검사. 다르면 backend/에서 python export_openapi.py

설명 문구(`description`)만 양쪽에서 빼고 나머지(주소, 메서드, 요청 본문, 질의 변수, 응답, 스키마의 필드·타입)를
그대로 비교한다. starlette·FastAPI 버전에 따라 응답 설명 문구("Unprocessable Entity" → "Unprocessable Content" 등)가
바뀌어도 깨지지 않게 하기 위해서다. 파일 서식(들여쓰기·줄바꿈)은 검사하지 않는다.
"""
import json

from export_openapi import OPENAPI_PATH
from app.main import app


def strip_descriptions(node):
    if isinstance(node, dict):
        return {k: strip_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [strip_descriptions(v) for v in node]
    return node


def test_openapi_file_is_up_to_date():
    assert OPENAPI_PATH.exists(), "docs/api/openapi.json이 없습니다. backend/에서 python export_openapi.py로 만드세요"
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert strip_descriptions(committed) == strip_descriptions(app.openapi()), \
        "API가 바뀌었습니다. backend/에서 python export_openapi.py로 openapi.json을 다시 만드세요"


def test_comparison_catches_field_changes():
    # 리뷰에서 "변화 없음"으로 통과하던 변경들이 이제는 잡히는지 확인
    spec = strip_descriptions(app.openapi())
    schemas = spec["components"]["schemas"]

    renamed = json.loads(json.dumps(spec))
    props = renamed["components"]["schemas"]["CheckInput"]["properties"]
    props["official_price_renamed"] = props.pop("official_price")
    assert renamed != spec

    dropped = json.loads(json.dumps(spec))
    del dropped["components"]["schemas"]["CheckResult"]["properties"]["block_payment"]
    assert dropped != spec

    extra_param = json.loads(json.dumps(spec))
    op = extra_param["paths"]["/api/checks/{check_id}"]["get"]
    op.setdefault("parameters", []).append({"name": "x", "in": "query", "required": True, "schema": {"type": "string"}})
    assert extra_param != spec

    assert "CheckInput" in schemas and "CheckResult" in schemas
