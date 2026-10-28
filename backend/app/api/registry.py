"""등기부 요약 업로드·추출 API (UC-002, FR-005·FR-006)와 등기 항목 쉬운 말 설명 (FR-007).

추출 결과만 돌려주고 저장하지 않는다. 사용자가 확인·수정한 값을 POST /api/checks의 registry로 보낸다.
설명은 추출 결과를 먼저 보여 준 뒤 따로 부른다 (NFR-001: LLM 설명은 뒤에 채워도 됨).
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, UploadFile

from app import explain
from app.errors import api_error, responses
from app.registry import RegistryParseError, RegistrySummary, parse_registry_pdf
from app.rules.loader import get_rules
from app.schemas import ExplainInput, ExplainResult, ExplanationOut, RegistryParseResult

router = APIRouter(prefix="/api/registry", tags=["등기부 점검"])

MAX_PDF_BYTES = 10 * 1024 * 1024
MANUAL_INPUT_HINT = '인터넷등기소에서 열람한 뒤 "부동산정보요약"을 PDF로 저장해 다시 올리거나, 수동 입력 화면에서 직접 입력하세요'


@router.post("/parse", response_model=RegistryParseResult, responses=responses(413, 422))
async def parse_registry(file: UploadFile):
    pdf = await file.read(MAX_PDF_BYTES + 1)
    if len(pdf) > MAX_PDF_BYTES:
        raise api_error(413, "FILE_TOO_LARGE", "PDF는 10MB까지 올릴 수 있습니다")
    try:
        summary = parse_registry_pdf(pdf)
    except RegistryParseError as e:
        raise api_error(422, "REGISTRY_UNREADABLE", str(e), MANUAL_INPUT_HINT)
    return to_parse_result(summary)


@router.post("/explain", response_model=ExplainResult, responses=responses(422))
def explain_items(inp: ExplainInput, rules: dict = Depends(get_rules)):
    """확인한 등기 항목마다 쉬운 말 설명 (FR-007). 저장하지 않는다.

    LLM(ANTHROPIC_API_KEY가 있을 때)이 쓰고 금지 표현·숫자 검사를 통과한 설명은 source "llm", LLM이 꺼져 있거나
    실패·시간 초과(8초)·검사 탈락이면 rules/explain.yaml 템플릿 설명(source "template"). 어느 쪽이든 200이다.
    """
    items = [explain.Item(i.id, i.kind, i.purpose, i.amount) for i in inp.items]
    return ExplainResult(
        explanations=[ExplanationOut(id=e.id, kind=e.kind, text=e.text, source=e.source)
                      for e in explain.explain(items, rules)],
        disclaimer=rules["verdict"]["display"]["disclaimer"],
    )


def to_parse_result(summary: RegistrySummary) -> RegistryParseResult:
    return RegistryParseResult(
        fields=summary.to_fields(),
        owners=summary.owners,
        mortgages=[asdict(m) for m in summary.mortgages],
        leases=[asdict(lease) for lease in summary.leases],
        seizures=[asdict(e) for e in summary.seizures],
        trusts=[asdict(e) for e in summary.trusts],
        others=[asdict(e) for e in summary.others],
        warnings=summary.warnings,
    )
