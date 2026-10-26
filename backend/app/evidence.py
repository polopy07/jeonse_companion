"""증빙 사진 파일 저장 (FR-029, FR-033). DB에는 증빙 폴더 기준 상대 경로만 남긴다.

파일 형식·화질은 제한하지 않는다(FR-029). 크기만 막고, 돌려줄 때는 사진·PDF가 아니면 내려받기로 준다.
"""
import mimetypes
import re
import uuid
from pathlib import Path

from app.config import evidence_dir

MAX_EVIDENCE_BYTES = 20 * 1024 * 1024
SHOWN_INLINE = ("image/", "application/pdf")   # 이 형식만 화면에 바로 보여 주고, 나머지는 내려받기로


def _suffix(filename: str | None) -> str:
    """올린 파일 이름의 확장자 (영문·숫자만, 10자까지). 없으면 빈 문자열."""
    suffix = Path(filename or "").suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""


def save(contract_id: int, todo_id: int, data: bytes, filename: str | None) -> str:
    rel = f"{contract_id}/{todo_id}-{uuid.uuid4().hex}{_suffix(filename)}"
    path = evidence_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def path_of(rel: str) -> Path:
    return evidence_dir() / rel


def remove(rel: str | None) -> None:
    if rel:
        path_of(rel).unlink(missing_ok=True)


def media_type(rel: str) -> str:
    guessed = mimetypes.guess_type(rel)[0] or "application/octet-stream"
    return guessed if guessed.startswith(SHOWN_INLINE) else "application/octet-stream"
