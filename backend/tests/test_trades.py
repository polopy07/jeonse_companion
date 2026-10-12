"""실거래가: 응답 해석, 수집·저장, 매매 실거래가·주변 전세 시세, 계약 전 확인 연결 (FR-003, FR-004, FR-046)."""
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.api.admin import get_http_client
from app.engine.market import ComplexKey, nearby_jeonse, pick_trade_price
from app.main import app
from app.trades.client import TradeApiError, TradeRecord, fetch_month, parse_response
from app.trades.collect import months_back

FIXTURES = Path(__file__).parent / "fixtures" / "trades"
EOK = 100_000_000


def _xml(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# 응답 해석 ---------------------------------------------------------------------

def test_parse_apartment_trades():
    records, total = parse_response(_xml("apt_trade.xml"), "apartment", "trade", "26350")
    assert total == 3
    first = records[0]
    assert first.complex_name == "가상해운대아파트"
    assert first.umd_name == "우동" and first.jibun == "1234"
    assert first.price == 340_000_000                        # 만 원 → 원
    assert first.deal_date == date(2026, 9, 12)
    assert first.exclusive_area == 84.97 and first.floor == 12
    assert first.cancelled is False
    assert records[1].cancelled is True                       # 해제 신고 (cdealType O)
    assert first.deposit is None and first.monthly_rent is None


def test_parse_row_house_rents():
    records, _ = parse_response(_xml("rh_rent.xml"), "row_house", "rent", "26500")
    assert [(r.deposit, r.monthly_rent) for r in records] == [(130_000_000, 0), (20_000_000, 450_000)]
    assert records[0].complex_name == "가상광안빌라" and records[0].jibun == "45-6"
    assert all(r.price is None and not r.cancelled for r in records)


def test_auth_error_and_bad_code():
    with pytest.raises(TradeApiError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        parse_response(_xml("auth_error.xml"), "apartment", "trade", "26350")
    bad = "<response><header><resultCode>03</resultCode><resultMsg>NO_DATA</resultMsg></header></response>"
    with pytest.raises(TradeApiError, match="03"):
        parse_response(bad, "apartment", "trade", "26350")
    with pytest.raises(TradeApiError, match="XML"):
        parse_response("<html>", "apartment", "trade", "26350")


def test_fetch_month_sends_params_and_pages(monkeypatch):
    monkeypatch.setattr("app.trades.client.PAGE_SIZE", 2)
    seen = []

    def handler(request: httpx.Request):
        q = parse_qs(urlparse(str(request.url)).query)
        seen.append((request.url.path, q["LAWD_CD"][0], q["DEAL_YMD"][0], q["pageNo"][0], q["serviceKey"][0]))
        if q["pageNo"][0] == "1":
            return httpx.Response(200, text=_xml("apt_trade.xml"))   # totalCount 3 → 2쪽 필요
        return httpx.Response(200, text=re.sub(r"<item>.*?</item>", "", _xml("apt_trade.xml"), count=2))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records = fetch_month(client, "KEY+/=", "apartment", "trade", "26350", "202609")
    assert seen[0] == ("/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade", "26350", "202609", "1", "KEY+/=")
    assert [s[3] for s in seen] == ["1", "2"]
    assert len(records) == 3 + 1


def test_fetch_month_http_error():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        with pytest.raises(TradeApiError, match="연결하지 못했습니다"):
            fetch_month(client, "k", "row_house", "rent", "26500", "202609")


def test_months_back():
    assert months_back(date(2026, 10, 1), 3) == ["202608", "202609", "202610"]
    assert months_back(date(2026, 2, 28), 12)[0] == "202503"


# 매매 실거래가·주변 전세 시세 --------------------------------------------------------

APT = ComplexKey("apartment", "26350", "우동", "가상해운대아파트")
VILLA = ComplexKey("row_house", "26500", "광안동", "가상광안빌라", "45-6")


def _r(key: ComplexKey, kind: str, d: date, area=84.97, price=None, deposit=None, rent=0, cancelled=False, **kw):
    return TradeRecord(housing_type=key.housing_type, kind=kind, lawd_cd=key.lawd_cd,
                       umd_name=kw.get("umd", key.umd_name), jibun=kw.get("jibun", key.jibun),
                       complex_name=kw.get("name", key.complex_name), exclusive_area=area, floor=1,
                       deal_date=d, price=price, deposit=deposit, monthly_rent=rent if kind == "rent" else None,
                       build_year=None, cancelled=cancelled)


def test_pick_latest_trade(rules):
    records = [
        _r(APT, "trade", date(2026, 8, 2), price=335 * 10**6),
        _r(APT, "trade", date(2026, 9, 12), price=340 * 10**6),
        _r(APT, "trade", date(2026, 9, 12), price=338 * 10**6, area=80.0),          # 같은 날이면 낮은 값
        _r(APT, "trade", date(2026, 9, 20), price=300 * 10**6, cancelled=True),     # 해제 신고는 빼기
        _r(APT, "trade", date(2026, 9, 25), price=200 * 10**6, area=59.9),          # 면적 ±10% 밖
        _r(APT, "trade", date(2026, 9, 26), price=210 * 10**6, name="다른아파트"),
        _r(APT, "trade", date(2025, 10, 12), price=100 * 10**6),                    # 12개월 밖 (기준일 2026-10-12)
    ]
    pick = pick_trade_price(records, APT, 84.97, date(2026, 10, 12), rules["alert"])
    assert (pick.price, pick.deal_date, pick.sample_count) == (338 * 10**6, date(2026, 9, 12), 3)
    # 띄어쓰기가 달라도 같은 단지
    spaced = ComplexKey("apartment", "26350", "우동", "가상해운대 아파트")
    assert pick_trade_price(records, spaced, 84.97, date(2026, 10, 12), rules["alert"]).price == 338 * 10**6
    # 기준일 2025-10-01이면 12개월 안(2024-10-02 ~ 2025-10-01)에 거래가 없다
    assert pick_trade_price(records, APT, 84.97, date(2025, 10, 1), rules["alert"]) is None


def test_nearby_jeonse_median_and_low_sample(rules):
    d = date(2026, 9, 1)
    records = [
        _r(VILLA, "rent", d, area=49.5, deposit=130 * 10**6),
        _r(VILLA, "rent", d, area=50.0, deposit=120 * 10**6),
        _r(VILLA, "rent", d, area=49.0, deposit=20 * 10**6, rent=450_000),           # 월세는 빼기
        _r(VILLA, "rent", d, area=49.5, deposit=110 * 10**6, jibun="99-1"),           # 다른 지번
    ]
    low = nearby_jeonse(records, VILLA, 49.5, date(2026, 10, 12), rules["alert"])
    assert (low.median, low.sample_count, low.low_sample) == (None, 2, True)
    records.append(_r(VILLA, "rent", d, area=52.0, deposit=140 * 10**6))
    ok = nearby_jeonse(records, VILLA, 49.5, date(2026, 10, 12), rules["alert"])
    assert (ok.median, ok.sample_count, ok.low_sample) == (130 * 10**6, 3, False)


# 수집 API -------------------------------------------------------------------------

@pytest.fixture
def fake_portal():
    calls = []

    def handler(request: httpx.Request):
        q = parse_qs(urlparse(str(request.url)).query)
        calls.append((request.url.path.rsplit("/", 1)[-1], q["DEAL_YMD"][0]))
        path = request.url.path
        if "AptTrade" in path and q["DEAL_YMD"][0] == "202609":
            return httpx.Response(200, text=_xml("apt_trade.xml"))
        empty = "<response><header><resultCode>000</resultCode></header><body><items/><totalCount>0</totalCount></body></response>"
        return httpx.Response(200, text=empty)

    def override():
        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    yield calls
    app.dependency_overrides.pop(get_http_client, None)


def test_collect_trades(client, fake_portal, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    body = {"lawd_cd": "26350", "end_month": "2026-10", "months": 2, "housing_types": ["apartment"]}
    r = client.post("/api/admin/trades", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["months"] == ["202609", "202610"]
    assert out["received"] == {"apartment.trade": 3, "apartment.rent": 0}
    assert out["added"] == 3
    assert datetime.fromisoformat(out["fetched_at"]).tzinfo is not None
    assert len(fake_portal) == 4                               # 매매·전월세 × 2개월

    again = client.post("/api/admin/trades", json=body).json()
    assert again["added"] == 0                                 # 같은 거래는 다시 저장하지 않음


def test_collect_needs_key(client, fake_portal, monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    r = client.post("/api/admin/trades", json={"lawd_cd": "26350", "end_month": "2026-10"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "SERVICE_KEY_MISSING"


def test_collect_portal_error(client, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "bad")

    def override():
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=_xml("auth_error.xml")))) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    try:
        r = client.post("/api/admin/trades", json={"lawd_cd": "26350", "end_month": "2026-10", "months": 1})
    finally:
        app.dependency_overrides.pop(get_http_client, None)
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["code"] == "TRADE_API_ERROR" and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in d["message"]


def test_collect_input_checks(client):
    r = client.post("/api/admin/trades", json={"lawd_cd": "2635", "end_month": "2026-13", "months": 0})
    assert r.status_code == 422
    assert {f["field"] for f in r.json()["detail"]["fields"]} == {"lawd_cd", "end_month", "months"}


# 계약 전 확인 연결 -----------------------------------------------------------------

def _store(records):
    from app.db import get_sessionmaker
    from app.trades.collect import save
    with get_sessionmaker()() as db:
        save(db, records, "api", datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_check_uses_trade_price_and_nearby_jeonse(client):
    _store([
        _r(APT, "trade", date(2026, 9, 12), price=340 * 10**6),
        _r(APT, "rent", date(2026, 9, 1), deposit=240 * 10**6),
        _r(APT, "rent", date(2026, 9, 5), deposit=230 * 10**6),
        _r(APT, "rent", date(2026, 9, 9), deposit=220 * 10**6),
    ])
    body = {
        "housing_type": "apartment", "deposit": 250 * 10**6, "official_price": 260 * 10**6, "exclusive_area": 84.9,
        "registry": {}, "complex": {"lawd_cd": "26350", "umd_name": "우동", "complex_name": "가상해운대아파트"},
    }
    r = client.post("/api/checks", json=body, headers={"X-Virtual-Today": "2026-10-12"})
    assert r.status_code == 201, r.text
    out = r.json()
    # 공시가격 × 140% = 3억 6,400만 > 실거래 3억 4,000만 → 실거래를 씀 (AC-002)
    assert out["estimated_price"] == 340 * 10**6
    assert out["as_of"] == "2026-10-12"
    assert out["trade_basis"] == {"price": 340 * 10**6, "deal_date": "2026-09-12", "exclusive_area": 84.97,
                                  "sample_count": 1, "used": True}
    assert out["nearby_jeonse"] == {"median": 230 * 10**6, "sample_count": 3, "low_sample": False, "below_deposit": True}
    assert client.get(f"/api/checks/{out['id']}").json() == out

    # 주변 전세 시세가 내 보증금보다 낮으면 경보 "주의" (비율 73.5%여도)
    c = client.post("/api/contracts", json={"check_id": out["id"], "contract_date": "2026-11-02",
                                             "balance_date": "2026-12-01", "end_date": "2028-11-30"}).json()
    assert c["alert_level"] == "caution"


def test_check_without_trades_or_complex(client):
    body = {"housing_type": "apartment", "deposit": EOK, "official_price": 2 * EOK, "exclusive_area": 84.9, "registry": {}}
    plain = client.post("/api/checks", json=body).json()
    assert plain["as_of"] is None and plain["trade_basis"] is None and plain["nearby_jeonse"] is None
    body["complex"] = {"lawd_cd": "26350", "umd_name": "우동", "complex_name": "없는아파트"}
    none = client.post("/api/checks", json=body).json()
    assert none["trade_basis"] is None
    assert none["nearby_jeonse"] == {"median": None, "sample_count": 0, "low_sample": True, "below_deposit": None}
    assert none["estimated_price"] == 280 * 10**6


def test_check_complex_input_rules(client):
    villa = {"housing_type": "row_house", "deposit": EOK, "official_price": 2 * EOK, "exclusive_area": 49.5,
             "complex": {"lawd_cd": "26500", "umd_name": "광안동", "complex_name": "가상광안빌라"}}
    r = client.post("/api/checks", json=villa)
    assert r.status_code == 422
    assert r.json()["detail"]["fields"] == [{"field": "body", "message": "연립다세대는 지번을 입력해야 실거래를 찾을 수 있습니다"}]
    no_area = {**villa, "housing_type": "apartment", "exclusive_area": None}
    r = client.post("/api/checks", json=no_area)
    assert r.json()["detail"]["fields"][0]["message"] == "단지로 실거래를 찾으려면 전용면적을 입력해야 합니다"
    r = client.post("/api/checks", json={**villa, "complex": {**villa["complex"], "jibun": "45-6"}},
                    headers={"X-Virtual-Today": "2026-13-01"})
    assert r.status_code == 422
    assert r.json()["detail"]["fields"][0]["field"] == "x-virtual-today"
