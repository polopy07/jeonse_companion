"""역전세 경보 계약 중 재계산 (FR-036·037·038, alert.yaml recalculation).

공시가격·실거래가가 새로 들어오면 진행 중 계약의 내 보증금 비율을 다시 계산해 경보 이력(alerts)에 남긴다.
경보 단계가 바뀌면 계약의 alert_level을 바꾸고 할 일을 다시 계산한다 (주의 이상이면 T5 맨 위, todos.yaml).
단계가 올라가면 앱 안 알림을 만든다.
"""
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.contracts import _sync_todos
from app.engine.alert import alert_level, level_rank
from app.engine.market import ComplexKey, nearby_jeonse, pick_trade_price
from app.engine.price import deposit_ratio, estimate_price
from app.models import Alert, Contract, Notification, Trade, Verdict

ALERT_TODO_ID = "ALERT"   # notifications.todo_rule_id 자리 (할 일이 아닌 경보 알림)


@dataclass
class Calculation:
    level: str | None
    estimated_price: int
    deposit_ratio: float
    basis: dict   # 계산에 쓴 공시가격·실거래가·주변 전세·선순위 채권·기준일 (FR-038)


@dataclass
class Recalculated:
    contract_id: int
    level: str | None
    previous_level: str | None
    raised: bool
    estimated_price: int
    deposit_ratio: float


def senior_debt(row: Contract) -> int | None:
    """마지막으로 올린 등기부의 선순위 채권 (근저당 채권최고액 + 임차권·전세권 보증금). 올린 적 없으면 None."""
    for v in reversed(row.verdicts):   # 계약 당일·잔금일 재비교 판정이 있으면 그것이 최근 (FR-048, FR-023)
        inputs = v.inputs or {}
        if inputs.get("registry.mortgage_amount") is not None:
            return inputs["registry.mortgage_amount"] + (inputs.get("registry.lease_amount") or 0)
    return None


def calculate(row: Contract, check: Verdict, db: Session, rules: dict, as_of: date) -> Calculation:
    """계약의 지금 공시가격·저장된 실거래·마지막 등기부로 경보를 계산한다 (계약 전 확인과 같은 규칙)."""
    cfg = rules["alert"]
    complex_ = (check.market or {}).get("complex")
    pick = nearby = None
    if complex_ is not None and row.exclusive_area:
        key = ComplexKey(row.housing_type, complex_["lawd_cd"], complex_["umd_name"], complex_["complex_name"],
                         complex_.get("jibun"))
        records = db.scalars(select(Trade).where(Trade.lawd_cd == key.lawd_cd,
                                                 Trade.housing_type == row.housing_type)).all()
        pick = pick_trade_price(records, key, row.exclusive_area, as_of, cfg)
        nearby = nearby_jeonse(records, key, row.exclusive_area, as_of, cfg)

    official_estimate = estimate_price(row.official_price, None, cfg)
    price = estimate_price(row.official_price, pick.price if pick else None, cfg)
    ratio = deposit_ratio(row.deposit, price, senior_debt(row), cfg)
    median = nearby.median if nearby else None
    level = alert_level({"deposit_ratio": ratio.ratio, "deposit": row.deposit, "nearby_jeonse_median": median}, cfg)
    basis = {
        "as_of": as_of.isoformat(),
        "official_price": row.official_price,
        "official_estimate": official_estimate,
        "multiplier": cfg["estimated_price"]["official_price_multiplier"],
        "trade": None if pick is None else {**asdict(pick), "deal_date": pick.deal_date.isoformat(),
                                            "used": price == pick.price},
        "nearby_jeonse": None if nearby is None else {
            **asdict(nearby), "below_deposit": None if median is None else median < row.deposit},
        "senior_debt": ratio.senior_debt,
        "ratio_is_minimum": ratio.is_minimum,
        "complex_known": complex_ is not None,
        "rules_version": str(cfg["version"]),
    }
    return Calculation(level, price, ratio.ratio, basis)


def start_point(check: Verdict, rules: dict) -> dict | None:
    """계약을 시작할 때의 경보 (계약 전 확인 판정 값). 경보를 계산하지 않는 집(공시가격 없음)이면 None."""
    if check.deposit_ratio is None or check.estimated_price is None:
        return None
    market, inputs = check.market or {}, check.inputs or {}
    as_of = market.get("as_of") or check.created_at.date().isoformat()
    official = inputs.get("official_price")   # 판정 때 공시가격 (계약의 공시가격은 재계산 때 바뀔 수 있음)
    senior = 0 if check.ratio_is_minimum else         (inputs.get("registry.mortgage_amount") or 0) + (inputs.get("registry.lease_amount") or 0)
    return {
        "as_of": as_of,
        "level": _level_at_start(check, rules),
        "estimated_price": check.estimated_price,
        "deposit_ratio": check.deposit_ratio,
        "basis": {
            "as_of": as_of,
            "official_price": official,
            "official_estimate": estimate_price(official, None, rules["alert"]),
            "multiplier": rules["alert"]["estimated_price"]["official_price_multiplier"],
            "trade": market.get("trade_basis"),
            "nearby_jeonse": market.get("nearby_jeonse"),
            "senior_debt": senior,
            "ratio_is_minimum": check.ratio_is_minimum,
            "complex_known": "complex" in market,
            "rules_version": None,   # 계약 시작 값은 판정 때 계산 (재계산만 alert.yaml 버전을 남긴다)
        },
    }


def _level_at_start(check: Verdict, rules: dict) -> str | None:
    inputs = check.inputs or {}
    return alert_level({"deposit_ratio": check.deposit_ratio, "deposit": inputs.get("deposit"),
                        "nearby_jeonse_median": inputs.get("nearby_jeonse_median")}, rules["alert"])


def history(row: Contract, check: Verdict, rules: dict) -> list[dict]:
    """계약 시작 + 재계산 이력 (기준일 순서). 경보를 계산하지 않는 집이면 빈 목록."""
    start = start_point(check, rules)
    if start is None:
        return []
    points = [start]
    for a in sorted(row.alerts, key=lambda a: (a.as_of or date.min, a.id)):
        points.append({"as_of": a.as_of.isoformat(), "level": a.level, "estimated_price": a.estimated_price,
                       "deposit_ratio": a.deposit_ratio, "basis": a.basis})
    return points


def recalculate(db: Session, day: date, rules: dict, contract_ids: list[int] | None = None,
                official_prices: dict[int, int] | None = None) -> list[Recalculated]:
    """진행 중 계약의 경보를 day 기준으로 다시 계산한다 (FR-037). 같은 날 다시 부르면 그날 이력을 바꾼다.

    official_prices: {계약 id: 새 공시가격} (공시가격 새 발표 적재, FR-046). 없는 계약 id는 무시한다.
    공시가격이 없는 계약(다가구·단독 등 경보 대상 아님)은 건너뛴다.
    """
    query = select(Contract).where(or_(Contract.status == "active", Contract.status.is_(None))).order_by(Contract.id)
    if contract_ids is not None:
        query = query.where(Contract.id.in_(contract_ids))
    official_prices = official_prices or {}
    results = []
    for row in db.scalars(query).all():   # 무산된 계약은 다시 계산하지 않는다 (FR-016)
        if row.id in official_prices:
            row.official_price = official_prices[row.id]
        check = db.get(Verdict, row.check_id)
        if row.official_price is None or check is None:
            continue
        calc = calculate(row, check, db, rules, day)

        alerts = sorted(row.alerts, key=lambda a: (a.as_of or date.min, a.id))
        same_day = alerts[-1] if alerts and alerts[-1].as_of == day else None
        earlier = [a for a in alerts if a is not same_day]
        previous = earlier[-1].level if earlier else _level_at_start(check, rules)
        if same_day is None:
            same_day = Alert(contract_id=row.id, as_of=day)
            row.alerts.append(same_day)
        same_day.level, same_day.estimated_price = calc.level, calc.estimated_price
        same_day.deposit_ratio, same_day.basis = calc.deposit_ratio, calc.basis

        raised = level_rank(calc.level, rules["alert"]) > level_rank(previous, rules["alert"])
        if calc.level != row.alert_level:
            row.alert_level = calc.level
            _sync_todos(row, check, rules)
        if raised:
            _notify(db, row, calc, day, rules)
        results.append(Recalculated(row.id, calc.level, previous, raised, calc.estimated_price, calc.deposit_ratio))
    db.commit()
    return results


def _notify(db: Session, row: Contract, calc: Calculation, day: date, rules: dict) -> None:
    """경보 단계가 올라가면 앱 안 알림 (alert.yaml recalculation.notify_when). 같은 날은 한 번만."""
    exists = db.scalar(select(Notification.id).where(
        Notification.contract_id == row.id, Notification.todo_rule_id == ALERT_TODO_ID,
        Notification.kind == "alert", Notification.notify_date == day, Notification.channel == "app"))
    if exists is not None:
        return
    label = next(lv["label"] for lv in rules["alert"]["levels"] if lv["id"] == calc.level)
    db.add(Notification(contract_id=row.id, todo_rule_id=ALERT_TODO_ID, kind="alert", notify_date=day, channel="app",
                        status="sent", title=f"역전세 경보가 {label} 단계로 올랐어요 (내 보증금 비율 {calc.deposit_ratio:.1%})"))
