"""등기부 PDF → 요약 페이지 글자 (pdfplumber)."""
import io

import pdfplumber

from app.registry.parser import TITLE, RegistryParseError, RegistrySummary, parse_summary_text


def extract_summary_text(pdf: bytes) -> str:
    """"주요 등기사항 요약"이 처음 나오는 페이지부터 끝까지의 글자 (요약이 두 페이지에 걸칠 수 있음)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            pages = [page.extract_text() or "" for page in doc.pages]
    except Exception as e:  # pdfminer는 깨진 파일마다 다른 예외를 낸다
        raise RegistryParseError("PDF를 열 수 없습니다") from e

    if not any(p.strip() for p in pages):
        raise RegistryParseError("PDF에서 글자를 읽을 수 없습니다 (스캔한 이미지 PDF는 지원하지 않음)")

    start = next((i for i, p in enumerate(pages) if TITLE.search(p)), None)
    if start is None:
        raise RegistryParseError('"주요 등기사항 요약" 페이지를 찾지 못했습니다')
    return "\n".join(pages[start:])


def parse_registry_pdf(pdf: bytes) -> RegistrySummary:
    return parse_summary_text(extract_summary_text(pdf))
