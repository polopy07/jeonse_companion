"""추정 주택가격과 내 보증금 비율 (alert.yaml, 명세서 부속표 C, FR-003)."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DepositRatio:
    estimated_price: int
    senior_debt: int          # 선순위 채권 (근저당 채권최고액 합계)
    ratio: float
    is_minimum: bool          # 등기부를 올리기 전이라 선순위 채권을 0원으로 둔 최소 추정치


def estimate_price(official_price: int, trade_price: int | None, alert_rules: dict) -> int:
    """추정 주택가격 = 공시가격 × 140%. 같은 단지·비슷한 면적의 매매 실거래가가 있으면 둘 중 낮은 값."""
    cfg = alert_rules["estimated_price"]
    price = int(Decimal(official_price) * Decimal(str(cfg["official_price_multiplier"])))
    if trade_price and cfg["use_trade_price"] == "lower_of_two":
        price = min(price, trade_price)
    return price


def deposit_ratio(deposit: int, estimated_price: int, mortgage_amount: int | None, alert_rules: dict) -> DepositRatio:
    """내 보증금 비율 = (보증금 + 선순위 채권) ÷ 추정 주택가격.

    mortgage_amount가 None이면 등기부를 아직 올리지 않은 것으로 보고 규칙 파일의 기본값(0원)을 쓴다.
    """
    if estimated_price <= 0:
        raise ValueError("추정 주택가격은 0보다 커야 합니다")
    is_minimum = mortgage_amount is None
    if is_minimum:
        senior = alert_rules["deposit_ratio"]["before_registry_upload"]["senior_debt"]
    else:
        senior = mortgage_amount
    return DepositRatio(
        estimated_price=estimated_price,
        senior_debt=senior,
        ratio=(deposit + senior) / estimated_price,
        is_minimum=is_minimum,
    )
