"""실거래 수집·저장 (FR-046). 시연 집이 있는 구의 아파트·연립다세대 최근 N개월."""
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.todos import add_months
from app.models import Trade
from app.trades.client import TradeRecord, fetch_month

LOOKUP_CHUNK = 1000


@dataclass
class CollectResult:
    fetched_at: datetime
    months: list[str]                      # YYYYMM, 오래된 달부터
    received: dict[str, int]               # "apartment.trade" → 받은 건수
    added: int                             # 새로 저장한 건수 (이미 있던 거래는 빼고)


def months_back(end_month: date, count: int) -> list[str]:
    """end_month가 든 달부터 거꾸로 count개월 → ["202511", ..., "202610"]."""
    first = end_month.replace(day=1)
    return [add_months(first, -i).strftime("%Y%m") for i in reversed(range(count))]


def deal_key(r: TradeRecord) -> str:
    amount = r.price if r.kind == "trade" else f"{r.deposit}/{r.monthly_rent}"
    return "|".join(str(v) for v in (r.housing_type, r.kind, r.lawd_cd, r.umd_name, r.jibun, r.complex_name,
                                      f"{r.exclusive_area:.3f}", r.floor, r.deal_date.isoformat(), amount))


def numbered_keys(records: list[TradeRecord]) -> dict[str, TradeRecord]:
    """같은 값으로 보이는 거래에 순번을 붙인다.

    공개 자료에는 동·호수가 없어서, 같은 날 같은 층·면적·금액으로 거래한 다른 집이 똑같은 줄로 온다
    (수영구 2026-09 아파트 매매 106건 중 2건, 2026-10-12 확인). 한 건으로 합치지 않고 "#1", "#2"로 나눈다.
    같은 달을 다시 받으면 같은 순번이 나오므로 두 번 저장되지 않는다.
    """
    seen: Counter[str] = Counter()
    keyed = {}
    for r in records:
        base = deal_key(r)
        seen[base] += 1
        keyed[f"{base}#{seen[base]}"] = r
    return keyed


def save(db: Session, records: list[TradeRecord], source: str, fetched_at: datetime) -> int:
    """새 거래만 저장하고 저장한 건수를 돌려준다. 이미 있던 거래가 해제 신고되면 해제 표시만 고친다.

    records는 한 번에 받은 거래 전체(같은 달은 빠짐없이)여야 순번이 맞는다.
    """
    keys = numbered_keys(records)
    key_list = list(keys)
    existing = {}
    for i in range(0, len(key_list), LOOKUP_CHUNK):   # IN (...) 바인드 파라미터 한도(PostgreSQL 65,535)에 닿지 않게 나눠 조회
        chunk = key_list[i:i + LOOKUP_CHUNK]
        existing.update({t.deal_key: t for t in db.scalars(select(Trade).where(Trade.deal_key.in_(chunk)))})
    added = 0
    for key, r in keys.items():
        if key in existing:
            existing[key].cancelled = r.cancelled
            existing[key].contract_type = r.contract_type
            continue
        db.add(Trade(deal_key=key, source=source, fetched_at=fetched_at, **r.__dict__))
        added += 1
    db.commit()
    return added


def collect(db: Session, client: httpx.Client, service_key: str, lawd_cd: str, end_month: date,
            months: int, housing_types: list[str], kinds: tuple[str, ...] = ("trade", "rent")) -> CollectResult:
    fetched_at = datetime.now(timezone.utc)
    yms = months_back(end_month, months)
    received: Counter[str] = Counter()
    records: list[TradeRecord] = []
    for housing_type in housing_types:
        for kind in kinds:
            for ym in yms:
                batch = fetch_month(client, service_key, housing_type, kind, lawd_cd, ym)
                received[f"{housing_type}.{kind}"] += len(batch)
                records.extend(batch)
    added = save(db, records, "api", fetched_at)
    return CollectResult(fetched_at=fetched_at, months=yms, received=dict(received), added=added)
