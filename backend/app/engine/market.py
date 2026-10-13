"""저장한 실거래로 매매 실거래가·주변 전세 시세 계산 (alert.yaml estimated_price·nearby_jeonse, FR-003, FR-004).

같은 단지 = 같은 시군구·법정동·단지 이름(띄어쓰기 무시). 연립다세대는 같은 이름이 많아 지번도 같아야 한다.
비슷한 면적 = 전용면적이 내 집의 ±10% 안. 기간 = 기준일(as_of) 포함 이전 12개월.
"""
from dataclasses import dataclass
from datetime import date
from statistics import median

from app.engine.todos import add_months


@dataclass(frozen=True)
class ComplexKey:
    housing_type: str
    lawd_cd: str
    umd_name: str
    complex_name: str
    jibun: str | None = None     # 연립다세대는 필수


@dataclass(frozen=True)
class TradePick:
    price: int
    deal_date: date
    exclusive_area: float
    sample_count: int            # 기간 안 같은 단지·비슷한 면적 매매 건수


@dataclass(frozen=True)
class NearbyJeonse:
    median: int | None           # 표본 부족이면 None
    sample_count: int
    low_sample: bool


def _norm(name: str | None) -> str:
    return "".join((name or "").split())


def same_complex(record, key: ComplexKey) -> bool:
    if (record.housing_type, record.lawd_cd) != (key.housing_type, key.lawd_cd):
        return False
    if _norm(record.umd_name) != _norm(key.umd_name) or _norm(record.complex_name) != _norm(key.complex_name):
        return False
    if key.housing_type == "row_house" and _norm(record.jibun) != _norm(key.jibun):
        return False
    return True


def _window(records, key: ComplexKey, area: float, tolerance: float, as_of: date, months: int):
    start = add_months(as_of, -months)
    low, high = area * (1 - tolerance), area * (1 + tolerance)
    return [
        r for r in records
        if same_complex(r, key) and low <= r.exclusive_area <= high and start < r.deal_date <= as_of
    ]


def pick_trade_price(records, key: ComplexKey, area: float, as_of: date, alert_rules: dict) -> TradePick | None:
    """같은 단지·비슷한 면적의 매매 실거래가. 가장 최근 거래, 같은 날이면 낮은 값 (alert.yaml)."""
    cfg = alert_rules["estimated_price"]
    if cfg["trade_price_pick"] != "latest":
        raise ValueError(f"alert.yaml: 알 수 없는 trade_price_pick {cfg['trade_price_pick']}")
    trades = [
        r for r in _window(records, key, area, cfg["similar_area_tolerance"], as_of, cfg["lookback_months"])
        if r.kind == "trade" and r.price and not (cfg.get("exclude_cancelled") and r.cancelled)
    ]
    if not trades:
        return None
    best = min(trades, key=lambda r: (-r.deal_date.toordinal(), r.price))
    return TradePick(price=best.price, deal_date=best.deal_date, exclusive_area=best.exclusive_area,
                     sample_count=len(trades))


def nearby_jeonse(records, key: ComplexKey, area: float, as_of: date, alert_rules: dict) -> NearbyJeonse:
    """같은 단지·비슷한 면적의 최근 전세 거래 중앙값 (FR-004). 3건 미만이면 표본 부족. 갱신 계약은 뺀다."""
    cfg = alert_rules["nearby_jeonse"]
    if cfg["statistic"] != "median":
        raise ValueError(f"alert.yaml: 알 수 없는 statistic {cfg['statistic']}")
    rents = [
        r for r in _window(records, key, area, cfg["similar_area_tolerance"], as_of, cfg["lookback_months"])
        if r.kind == "rent" and r.deposit and not (cfg.get("jeonse_only") and r.monthly_rent)
        and not (cfg.get("exclude_renewal") and r.contract_type == "갱신")
    ]
    if len(rents) < cfg["min_sample"]:
        return NearbyJeonse(median=None, sample_count=len(rents), low_sample=True)
    return NearbyJeonse(median=int(median(r.deposit for r in rents)), sample_count=len(rents), low_sample=False)
