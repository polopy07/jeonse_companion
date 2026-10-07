"""등기부 요약 업로드·추출 API (UC-002, FR-005·FR-006).

추출 결과만 돌려주고 저장하지 않는다. 사용자가 확인·수정한 값을 POST /api/checks의 registry로 보낸다.
"""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, UploadFile

from app.registry import RegistryParseError, parse_registry_pdf
from app.schemas import RegistryParseResult

router = APIRouter(prefix="/api/registry", tags=["등기부 점검"])

MAX_PDF_BYTES = 10 * 1024 * 1024
MANUAL_INPUT_HINT = "등기부 요약을 읽지 못했습니다. 수동 입력 화면에서 직접 입력하세요"


@router.post("/parse", response_model=RegistryParseResult)
async def parse_registry(file: UploadFile):
    pdf = await file.read(MAX_PDF_BYTES + 1)
    if len(pdf) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF는 10MB까지 올릴 수 있습니다")
    try:
        summary = parse_registry_pdf(pdf)
    except RegistryParseError as e:
        raise HTTPException(status_code=422, detail={"message": str(e), "hint": MANUAL_INPUT_HINT})

    return RegistryParseResult(
        fields=summary.to_fields(),
        owners=summary.owners,
        mortgages=[asdict(m) for m in summary.mortgages],
        seizures=[asdict(e) for e in summary.seizures],
        trusts=[asdict(e) for e in summary.trusts],
        others=[asdict(e) for e in summary.others],
        warnings=summary.warnings,
    )
