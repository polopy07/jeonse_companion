"""시연 집 2채 (FR-001, FR-046, #38).

docs/validation/demo_houses.yaml(경보 계산 정답표)의 입력값과 시연 등기부를 돌려준다. 화면은 input을 그대로
POST /api/checks로, contract_day를 POST /api/contracts로 보내면 정답표와 같은 장면이 된다.
"""
import yaml
from fastapi import APIRouter

from app.api.registry import to_parse_result
from app.config import REPO_ROOT
from app.registry import parse_summary_text
from app.schemas import DemoHouseOut, DemoHousesResult

DEMO_HOUSES = REPO_ROOT / "docs" / "validation" / "demo_houses.yaml"   # 등기부 예시 경로도 저장소 기준

router = APIRouter(prefix="/api/demo-houses", tags=["시연"])


@router.get("", response_model=DemoHousesResult)
def demo_houses():
    demo = yaml.safe_load(DEMO_HOUSES.read_text(encoding="utf-8"))
    houses = []
    for h in demo["houses"]:
        summary = parse_summary_text((REPO_ROOT / h["registry_fixture"]).read_text(encoding="utf-8"))
        houses.append(DemoHouseOut(
            id=h["id"],
            title=h["title"],
            address=h["complex_address"],
            official_price_source=h["official_price_source"],
            input=h["input"],
            registry=to_parse_result(summary),
            virtual=h.get("virtual", []),
            contract_day=({**h["contract_day"]["dates"], "special_term_result": h["contract_day"]["special_term_result"]}
                          if "contract_day" in h else None),
        ))
    return DemoHousesResult(as_of=demo["as_of"], houses=houses)
