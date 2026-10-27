"""역전세 경보 계약 중 재계산 (FR-036·037·038, alert.yaml recalculation).

공시가격·실거래가가 새로 들어오면 진행 중 계약의 내 보증금 비율을 다시 계산해 경보 이력(alerts)에 남긴다.
경보 단계가 바뀌면 계약의 alert_level을 바꾸고 할 일을 다시 계산한다 (주의 이상이면 T5 맨 위, todos.yaml).
단계가 올라가면 앱 안 알림을 만든다.
"""
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.checks import find_market, trade_records
from app.api.contracts import _alert_level, _sync_todos
from app.engine.alert import alert_level, level_rank
from app.engine.price import deposit_ratio, estimate_price
from app.models import Alert, Contract, Notification, Verdict

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


def _senior_of(inputs: dict) -> int | None:
    """판정 입력의 선순위 채권 (근저당 채권최고액 + 임차권·전세권 보증금). 등기부를 올리지 않았으면 None (판정과 같은 규칙)."""
    if inputs.get("registry.mortgage_amount") is None:
        return None
    return inputs["registry.mortgage_amount"] + (inputs.get("registry.lease_amount") or 0)


def senior_debt(row: Contract) -> int | None:
    """마지막으로 올린 등기부의 선순위 채권. 올린 적 없으면 None."""
    for v in reversed(row.verdicts):   # 계약 당일·잔금일 재비교 판정이 있으면 그것이 최근 (FR-048, FR-023)
        senior = _senior_of(v.inputs or {})
        if senior is not None:
            return senior
    return None


def calculate(row: Contract, check: Verdict, db: Session, rules: dict, as_of: date,
              records_cache: dict | None = None) -> Calculation:
    """계약의 지금 공시가격·저장된 실거래·마지막 등기부로 경보를 계산한다 (계약 전 확인과 같은 규칙).

    records_cache: {(lawd_cd, 주택 유형): 실거래 목록}. 여러 계약을 다시 계산할 때 같은 구를 한 번만 불러온다.
    """
    cfg = rules["alert"]
    market = check.market or {}
    complex_ = market.get("complex")
    pick = nearby = None
    if complex_ is not None and row.exclusive_area:
        records = None
        if records_cache is not None:
            k = (complex_["lawd_cd"], row.housing_type)
            if k not in records_cache:
                records_cache[k] = trade_records(db, *k)
            records = records_cache[k]
        pick, nearby = find_market(db, row.housing_type, complex_, row.exclusive_area, rules, as_of, records)

    # 판정과 같은 규칙: 사용자가 직접 넣은 매매 실거래가가 있으면 그 값, 없으면 같은 단지 실거래
    user_trade = market.get("trade_price_input")
    trade_price = user_trade if user_trade is not None else (pick.price if pick else None)
    official_estimate = estimate_price(row.official_price, None, cfg)
    price = estimate_price(row.official_price, trade_price, cfg)
    ratio = deposit_ratio(row.deposit, price, senior_debt(row), cfg)
    median = nearby.median if nearby else None
    level = alert_level({"deposit_ratio": ratio.ratio, "deposit": row.deposit, "nearby_jeonse_median": median}, cfg)
    basis = {
        "as_of": as_of.isoformat(),
        "official_price": row.official_price,
        "official_estimate": official_estimate,
        "multiplier": cfg["estimated_price"]["official_price_multiplier"],
        "trade": None if pick is None else {**asdict(pick), "deal_date": pick.deal_date.isoformat(),
                                            "used": user_trade is None and price == pick.price},
        "trade_price_input": user_trade,
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
    senior = 0 if check.ratio_is_minimum else (_senior_of(inputs) or 0)
    return {
        "as_of": as_of,
        "level": _alert_level(check, rules),
        "estimated_price": check.estimated_price,
        "deposit_ratio": check.deposit_ratio,
        "basis": {
            "as_of": as_of,
            "official_price": official,
            "official_estimate": estimate_price(official, None, rules["alert"]),
            "multiplier": rules["alert"]["estimated_price"]["official_price_multiplier"],
            "trade": market.get("trade_basis"),
            "trade_price_input": market.get("trade_price_input"),
            "nearby_jeonse": market.get("nearby_jeonse"),
            "senior_debt": senior,
            "ratio_is_minimum": check.ratio_is_minimum,
            "complex_known": "complex" in market,
            "rules_version": None,   # 계약 시작 값은 판정 때 계산 (재계산만 alert.yaml 버전을 남긴다)
        },
    }


def _known(level: str | None, rules: dict) -> str | None:
    """지금 alert.yaml에 없는 예전 단계 id는 정상(None)으로 돌려준다 (level_rank와 같은 기준, 응답 형식이 깨지지 않게)."""
    return level if level_rank(level, rules["alert"]) >= 0 else None


def history(row: Contract, check: Verdict, rules: dict) -> list[dict]:
    """계약 시작 + 재계산 이력 (기준일 순서, 같은 날이면 계약 시작 먼저). 경보를 계산하지 않는 집이면 빈 목록.

    계약 시작의 기준일은 판정한 날(실제 날짜)일 수 있어, 가상 날짜로 그보다 앞선 날을 재계산해도 날짜순이 깨지지 않게 함께 정렬한다.
    """
    start = start_point(check, rules)
    if start is None:
        return []
    points = [(start["as_of"], 0, 0, start)]
    for a in row.alerts:
        point = {"as_of": a.as_of.isoformat(), "level": _known(a.level, rules), "estimated_price": a.estimated_price,
                 "deposit_ratio": a.deposit_ratio, "basis": a.basis}
        points.append(((a.as_of or date.min).isoformat(), 1, a.id or 0, point))
    return [p for *_, p in sorted(points, key=lambda x: x[:3])]


def recalculate(db: Session, day: date, rules: dict, contract_ids: list[int] | None = None,
                official_prices: dict[int, int] | None = None) -> list[Recalculated]:
    """진행 중 계약의 경보를 day 기준으로 다시 계산한다 (FR-037). 같은 날 다시 부르면 그날 이력을 바꾼다.

    official_prices: {계약 id: 새 공시가격} (공시가격 새 발표 적재, FR-046). 없는 계약 id는 무시한다.
    공시가격이 없는 계약(다가구·단독 등 경보 대상 아님)은 건너뛴다. 가상 날짜를 되돌려 앞선 날을 다시 계산하면
    그날 기록을 찾아 바꾸고, 앞 단계는 그날보다 앞선 기록으로 본다.
    """
    cfg = rules["alert"]
    query = select(Contract).where(or_(Contract.status == "active", Contract.status.is_(None))).order_by(Contract.id)
    if contract_ids is not None:
        query = query.where(Contract.id.in_(contract_ids))
    official_prices = official_prices or {}
    records_cache: dict = {}
    results = []
    for row in db.scalars(query).all():   # 무산된 계약은 다시 계산하지 않는다 (FR-016)
        if row.id in official_prices:
            row.official_price = official_prices[row.id]
        check = db.get(Verdict, row.check_id)
        if row.official_price is None or check is None:
            continue
        calc = calculate(row, check, db, rules, day, records_cache)

        same_day = next((a for a in row.alerts if a.as_of == day), None)
        earlier = sorted((a for a in row.alerts if a.as_of is not None and a.as_of < day), key=lambda a: (a.as_of, a.id))
        previous = earlier[-1].level if earlier else _alert_level(check, rules)
        # 이번 계산으로 올라갔는지: 앞 기록과, 같은 날 앞서 계산한 단계(이미 알렸을 수 있음) 가운데 높은 쪽과 비교
        baseline = max(level_rank(previous, cfg), level_rank(same_day.level, cfg) if same_day else -1)
        if same_day is None:
            same_day = Alert(contract_id=row.id, as_of=day)
            row.alerts.append(same_day)
        same_day.level, same_day.estimated_price = calc.level, calc.estimated_price
        same_day.deposit_ratio, same_day.basis = calc.deposit_ratio, calc.basis

        raised = level_rank(calc.level, cfg) > baseline
        if calc.level != row.alert_level:
            row.alert_level = calc.level
            _sync_todos(row, check, rules)
        if raised:
            _notify(db, row, calc, day, rules)
        results.append(Recalculated(row.id, calc.level, _known(previous, rules), raised, calc.estimated_price,
                                    calc.deposit_ratio))
    db.commit()
    return results


def _notify(db: Session, row: Contract, calc: Calculation, day: date, rules: dict) -> None:
    """경보 단계가 올라가면 앱 안 알림 (alert.yaml recalculation.notify_when). 같은 날은 한 건만 두고,
    같은 날 다시 올라가면(주의 → 경고) 그 알림을 새 단계로 고친다."""
    label = next(lv["label"] for lv in rules["alert"]["levels"] if lv["id"] == calc.level)
    title = f"역전세 경보가 {label} 단계로 올랐어요 (내 보증금 비율 {calc.deposit_ratio:.1%})"
    same_day = db.scalar(select(Notification).where(
        Notification.contract_id == row.id, Notification.todo_rule_id == ALERT_TODO_ID,
        Notification.kind == "alert", Notification.notify_date == day, Notification.channel == "app"))
    if same_day is not None:
        same_day.title, same_day.status = title, "sent"
        return
    db.add(Notification(contract_id=row.id, todo_rule_id=ALERT_TODO_ID, kind="alert", notify_date=day, channel="app",
                        status="sent", title=title))
