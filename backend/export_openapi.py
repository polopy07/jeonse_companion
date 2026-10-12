"""API 형식 파일(docs/api/openapi.json)을 서버 코드에서 다시 만든다.

API를 바꾸면 backend/ 폴더에서 실행: python export_openapi.py
tests/test_openapi.py가 파일이 코드와 같은지 검사한다.
"""
import json
from pathlib import Path

from app.main import app

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OPENAPI_PATH.write_text(render(), encoding="utf-8")
    print(f"저장: {OPENAPI_PATH}")
