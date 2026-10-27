"""증빙 사진 파일 저장 (FR-029, FR-033). DB에는 증빙 폴더 기준 상대 경로만 남긴다.

파일 형식·화질은 제한하지 않는다(FR-029). 크기만 막고, 돌려줄 때는 사진·PDF가 아니면 내려받기로 준다.
"""
import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import evidence_dir

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
