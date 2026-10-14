"""시연 집 정답표의 실거래 저장본(docs/validation/demo_trades_<기준일>.json)을 DB에 넣는다.

시연·검증은 저장본으로 한다 (기획서 v4.35). 공공데이터 API로 새로 받으면 기준일 뒤 거래가 섞여 정답표와 달라진다.
backend/ 폴더에서 DATABASE_URL을 서버와 같게 두고 실행: python load_demo_trades.py
같은 거래는 한 번만 들어가므로 여러 번 실행해도 된다.
"""
import json
from datetime import date, datetime

import yaml

from app.config import REPO_ROOT
from app.db import get_sessionmaker, init_db
from app.trades.client import TradeRecord
from app.trades.collect import save

VALIDATION = REPO_ROOT / "docs" / "validation"


def load() -> tuple[str, int]:
    """기준일과 새로 넣은 건수를 돌려준다."""
    demo = yaml.safe_load((VALIDATION / "demo_houses.yaml").read_text(encoding="utf-8"))
    snap = json.loads((VALIDATION / demo["trades"]).read_text(encoding="utf-8"))
    records = [TradeRecord(**{**r, "deal_date": date.fromisoformat(r["deal_date"])}) for r in snap["records"]]
    with get_sessionmaker()() as db:
        added = save(db, records, "api", datetime.fromisoformat(snap["fetched_at"]))
    return demo["as_of"], added


if __name__ == "__main__":
    init_db()
    as_of, added = load()
    print(f"실거래 저장본 기준일 {as_of}: {added}건 새로 넣음. 같은 결과를 보려면 X-Virtual-Today: {as_of}")
