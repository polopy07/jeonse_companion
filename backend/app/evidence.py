"""증빙 사진·첫 계약 서류 파일 저장 (FR-029, FR-033, FR-051). DB에는 증빙 폴더 기준 상대 경로만 남긴다.

파일 형식·화질은 제한하지 않는다(FR-029). 크기만 막고, 돌려줄 때는 사진·PDF가 아니면 내려받기로 준다.
"""
import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import evidence_dir
from app.errors import api_error

MAX_EVIDENCE_BYTES = 20 * 1024 * 1024
# 화면에 바로 보여 주는 확장자 → 형식. 나머지(SVG·HTML 등 스크립트가 들어갈 수 있는 것 포함)는 내려받기로.
# mimetypes는 서버 환경마다 달라서(.heic 미등록, Windows 레지스트리) 직접 적는다
SHOWN_INLINE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
                ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif", ".pdf": "application/pdf"}
DOWNLOAD = "application/octet-stream"
_PENDING = "evidence_to_remove"   # 커밋한 뒤 지울 파일 (Session.info)


def max_size_label() -> str:
    return f"{MAX_EVIDENCE_BYTES // (1024 * 1024)}MB"


def _suffix(filename: str | None) -> str:
    """올린 파일 이름의 확장자 (영문·숫자만, 10자까지). 없으면 빈 문자열."""
    suffix = Path(filename or "").suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""


def read_upload(file: UploadFile) -> bytes:
    """올린 파일을 읽는다. MAX_EVIDENCE_BYTES를 넘으면 413 FILE_TOO_LARGE, 빈 파일이면 422."""
    data = file.file.read(MAX_EVIDENCE_BYTES + 1)
    if len(data) > MAX_EVIDENCE_BYTES:
        raise api_error(413, "FILE_TOO_LARGE", f"증빙 파일은 {max_size_label()}까지 올릴 수 있습니다",
                        "사진 크기를 줄여 다시 올리세요")
    if not data:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "file"), "input": None,
                                       "msg": "Value error, 빈 파일입니다"}])
    return data


def save(contract_id: int, prefix: int | str, data: bytes, filename: str | None) -> str:
    """계약 폴더에 저장한다. prefix는 할 일 id 또는 첫 계약 서류 종류 (같은 이름으로 덮어쓰지 않게 뒤에 임의 값)."""
    rel = f"{contract_id}/{prefix}-{uuid.uuid4().hex}{_suffix(filename)}"
    path = evidence_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def path_of(rel: str) -> Path:
    return evidence_dir() / rel


def remove(rel: str | None) -> None:
    if rel:
        path_of(rel).unlink(missing_ok=True)


def remove_after_commit(db: Session, rel: str | None) -> None:
    """DB에서 증빙을 뺀 변경이 커밋된 뒤에 파일을 지운다. 커밋이 실패하면(롤백) 파일은 남는다."""
    if rel:
        db.info.setdefault(_PENDING, []).append(rel)


@event.listens_for(Session, "after_commit")
def _remove_pending(db: Session) -> None:
    for rel in db.info.pop(_PENDING, []):
        remove(rel)


@event.listens_for(Session, "after_soft_rollback")
def _keep_pending(db: Session, previous_transaction) -> None:
    db.info.pop(_PENDING, None)


def remove_all() -> None:
    """시연 초기화: 계약별 폴더(계약 id 숫자 이름)만 지운다. EVIDENCE_DIR을 잘못 잡아도 다른 파일은 건드리지 않게."""
    root = evidence_dir()
    if not root.is_dir():
        return
    for sub in root.iterdir():
        if sub.is_dir() and sub.name.isdigit():
            shutil.rmtree(sub)


def media_type(rel: str) -> str:
    return SHOWN_INLINE.get(Path(rel).suffix.lower(), DOWNLOAD)


def file_response(rel: str | None, name: str) -> FileResponse:
    """올린 파일. 사진·PDF는 화면에 바로(inline), 다른 형식은 내려받기로. 없으면 404.

    개인 서류라 캐시하지 않는다 (같은 주소로 다시 올린 뒤 앞 사진이 휴대폰 캐시에서 보이지 않게, #122 리뷰).
    """
    path = path_of(rel) if rel else None
    if path is None or not path.is_file():
        raise api_error(404, "NOT_FOUND", "올린 파일이 없습니다")
    kind = media_type(rel)
    disposition = "inline" if kind != DOWNLOAD else "attachment"
    return FileResponse(path, media_type=kind, filename=f"{name}{path.suffix}", content_disposition_type=disposition,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
