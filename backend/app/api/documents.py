"""계약 당일 첫 계약 서류: 계약서 사진·계약금 이체 내역 (FR-051, UC-003 5단계, UI-03·05, #46).

할 일 증빙과 달리 할 일을 끝내지 않고 기록함에만 남는다. 종류(todos.yaml first_documents)마다 1장,
다시 올리면 앞 파일을 바꾼다. 파일 저장·크기 제한·보기 형식은 증빙 사진과 같다 (app.evidence).
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, Header, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import evidence
from app.api.contracts import TOKEN_HEADER_DESC, _active, _contract_for, _to_out
from app.clock import today as today_dep
from app.db import get_db
from app.errors import api_error, responses
from app.models import Contract, ContractDocument
from app.rules.loader import get_rules
from app.schemas import ContractOut

router = APIRouter(prefix="/api/contracts", tags=["첫 계약 서류"])


def _kinds(rules: dict) -> list[str]:
    return [k["id"] for k in rules["todos"]["first_documents"]]


def _saved(row: Contract, kind: str, rules: dict) -> ContractDocument | None:
    """그 종류로 올린 서류. 규칙에 없는 종류면 404."""
    if kind not in _kinds(rules):
        raise api_error(404, "NOT_FOUND", "없는 서류 종류입니다", f"종류는 {', '.join(_kinds(rules))} 중 하나예요")
    return next((d for d in row.documents if d.kind == kind), None)


@router.post("/{contract_id}/documents", response_model=ContractOut, responses=responses(404, 409, 413, 422))
def upload_document(contract_id: int, kind: str = Form(description="서류 종류 (todos.yaml first_documents id)"),
                    file: UploadFile = ..., db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """첫 계약 서류 1장 올리기 (FR-051). 형식·화질은 제한하지 않고 20MB까지 (넘으면 413), 빈 파일·없는 종류는 422.
    같은 종류를 다시 올리면 앞 파일을 바꾼다. 계약 전체를 돌려준다(documents). 무산된 계약이면 409."""
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    if kind not in _kinds(rules):
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "kind"), "input": kind,
                                       "msg": f"Value error, 서류 종류는 {', '.join(_kinds(rules))} 중 하나입니다"}])
    data = evidence.read_upload(file)
    doc = next((d for d in row.documents if d.kind == kind), None)
    new = evidence.save(row.id, kind, data, file.filename)
    if doc is None:
        doc = ContractDocument(kind=kind, path=new)
        row.documents.append(doc)
    else:
        evidence.remove_after_commit(db, doc.path)
        doc.path = new
    doc.uploaded_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        evidence.remove(new)   # DB에 남지 않은 새 파일만 지운다 (같은 종류를 동시에 처음 올린 경우 포함)
        raise
    return _to_out(row, db, rules, today)


@router.get("/{contract_id}/documents/{kind}", response_class=FileResponse, responses=responses(404))
def get_document(contract_id: int, kind: str, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """올린 첫 계약 서류 파일 (기록함 보기, UI-05). 사진·PDF는 화면에 바로, 다른 형식은 내려받기. 무산된 계약도 볼 수 있다."""
    row = _contract_for(contract_id, x_contract_token, db)
    doc = _saved(row, kind, rules)
    return evidence.file_response(doc.path if doc else None, f"document-{kind}")


@router.delete("/{contract_id}/documents/{kind}", response_model=ContractOut, responses=responses(404))
def delete_document(contract_id: int, kind: str, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """첫 계약 서류 삭제 (FR-033, 언제든 직접 지울 수 있음: 무산된 계약도). 올린 서류가 없으면 404."""
    row = _contract_for(contract_id, x_contract_token, db)
    doc = _saved(row, kind, rules)
    if doc is None:
        raise api_error(404, "NOT_FOUND", "올린 서류가 없습니다")
    evidence.remove_after_commit(db, doc.path)
    row.documents.remove(doc)
    db.commit()
    return _to_out(row, db, rules, today)
