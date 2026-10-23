"""테스트 결제의 상품·금액 (FR-013, 기획서 v4.35 수익 모델, API 명세 1.8).

판정 단계로 상품을 정한다: 다가구·단독(대상 아님)은 할 일 관리만, 나머지는 전동기 패키지.
"""
PRODUCTS = {
    "package": 9_900,     # 전동기 패키지: 계약 당일 체크·맞춤 할 일·기록함·계약 중 경보
    "todo_only": 4_900,   # 다가구·단독: 할 일 관리만
}
# 상품의 높낮이. 풀린 결제는 같거나 낮은 상품의 계약에 다시 쓸 수 있다 (패키지 → 할 일 관리만 OK, 반대는 다시 결제)
_RANK = {"todo_only": 1, "package": 2}


def product_for(level_id: str) -> str:
    return "todo_only" if level_id == "not_applicable" else "package"


def covers(paid: str, needed: str) -> bool:
    return _RANK[paid] >= _RANK[needed]
