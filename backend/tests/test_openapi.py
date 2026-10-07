"""docs/api/openapi.json이 서버 코드와 같은지 검사. 다르면 backend/에서 python export_openapi.py"""
from export_openapi import OPENAPI_PATH, render


def test_openapi_file_is_up_to_date():
    assert OPENAPI_PATH.read_text(encoding="utf-8") == render(), "python export_openapi.py로 openapi.json을 다시 만드세요"
