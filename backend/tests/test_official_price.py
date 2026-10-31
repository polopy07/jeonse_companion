"""주소로 공동주택 공시가격 찾기: 브이월드 응답 해석, 동·호 맞추기, API (FR-001 확장).

브이월드 응답 모양은 검색 API 2.0 레퍼런스와 공동주택가격 속성 조회(ned/data/getApartHousingPriceAttr)를 따른 것이다.
실제 키로 부르지 않고 httpx.MockTransport로 응답을 흉내 낸다.
"""
import httpx
import pytest

from app.api import official_price as api
from app.api.admin import get_http_client
from app.main import app
from app.official_price.client import (OfficialPriceApiError, UnitPrice, fetch_prices, latest_prices, match_units,
                                       parse_prices, parse_search, search_parcels, unit_key)

PNU = "2650010500102120001"   # 가상 필지 (부산 수영구 광안동 212-1처럼 보이는 19자리)
KEY = "SECRET-VWORLD-KEY"


def _search_ok(*items):
    return {"response": {"status": "OK", "result": {"items": list(items)}}}


def _parcel(pnu=PNU, parcel="부산광역시 수영구 광안동 212-1", road="부산광역시 수영구 광안해변로 100"):
    return {"id": pnu, "address": {"parcel": parcel, "road": road}, "title": parcel}


def _field(dong, ho, price, area="59.85", year="2026", floor=None):
    return {"pnu": PNU, "stdrYear": year, "aphusNm": "가상광안아파트", "dongNm": dong, "hoNm": ho,
            "floorNm": floor, "prvuseAr": area, "pblntfPc": price}


def _prices(*fields, total=None, code="", wrap=True):
    data = {"field": list(fields), "totalCount": str(total if total is not None else len(fields)), "resultCode": code}
    return {"apartHousingPrices": data} if wrap else data


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# 응답 해석 ---------------------------------------------------------------------

def test_parse_search_keeps_only_pnu_ids():
    road_only = {"id": "26500105001021200010000123", "address": {"road": "부산광역시 수영구 광안해변로 100", "parcel": "광안동 212-1"}}
    parcels, fallbacks = parse_search(_search_ok(_parcel(), road_only))
    assert [(p.pnu, p.address) for p in parcels] == [(PNU, "부산광역시 수영구 광안동 212-1")]
    assert parcels[0].road_address == "부산광역시 수영구 광안해변로 100"
    assert fallbacks == ["부산광역시 수영구 광안동 212-1"]   # id가 PNU가 아니면 지번 주소로 다시 찾게
    assert parse_search({"response": {"status": "NOT_FOUND"}}) == ([], [])


def test_parse_search_road_result_real_shape():
    # 2026-10-31 실제 응답(도로명 "세실로 7"): id는 PNU, 지번 주소는 시·구 없이 "좌동 1331" → 도로명의 시·구를 붙인다
    item = {"id": "2635010700113310000", "address": {"road": "부산광역시 해운대구 세실로 7 (좌동,해운대상록아파트)",
                                                      "parcel": "좌동 1331"}}
    parcels, _ = parse_search(_search_ok(item))
    assert [(p.pnu, p.address) for p in parcels] == [("2635010700113310000", "부산광역시 해운대구 좌동 1331")]
    with pytest.raises(OfficialPriceApiError, match="INCORRECT_KEY"):
        parse_search({"response": {"status": "ERROR", "error": {"code": "INCORRECT_KEY", "text": "INCORRECT_KEY"}}})


def test_parse_prices_fields():
    units, total = parse_prices(_prices(_field("101동", "1203호", "165,000,000", floor="12"),
                                        _field("", "201", "116000000", area="30.09"),
                                        _field("101동", "1204호", "")))          # 가격 없는 줄은 뺀다
    assert total == 3
    assert units[0] == UnitPrice(stdr_year=2026, complex_name="가상광안아파트", dong="101동", ho="1203호", floor="12",
                                 exclusive_area=59.85, price=165_000_000)
    assert units[1].dong == "" and units[1].price == 116_000_000 and units[1].exclusive_area == 30.09
    assert len(units) == 2
    # 한 건이면 목록이 아니라 객체로 올 수 있다
    one, _ = parse_prices({"apartHousingPrices": {"field": _field("1동", "101호", "90000000"), "totalCount": "1"}})
    assert [u.ho for u in one] == ["101호"]
    # 공동주택이 아닌 필지는 apartHousingPrices가 없다
    assert parse_prices({}) == ([], 0)
    with pytest.raises(OfficialPriceApiError, match="INCORRECT_KEY"):
        parse_prices(_prices(code="INCORRECT_KEY"))
    # 인증키·서비스 주소 오류가 다른 모양으로 와도 "공시가격 없음"이 아니라 오류
    with pytest.raises(OfficialPriceApiError, match="INCORRECT_KEY"):
        parse_prices({"response": {"status": "ERROR", "error": {"code": "INCORRECT_KEY", "text": "INCORRECT_KEY"}}})


def test_unit_key_and_match():
    assert unit_key("101동", "동") == unit_key(" 0101 동", "동") == unit_key("101", "동") == unit_key("제101동", "동") == "101"
    assert unit_key("1203호", "호") == "1203" and unit_key("B01호", "호") == "B01"
    units = [UnitPrice(2026, "a", "101동", "1203호", None, 59.85, 1), UnitPrice(2026, "a", "102동", "1203호", None, 59.85, 2),
             UnitPrice(2026, "a", "", "201", None, 30.0, 3)]
    assert [u.price for u in match_units(units, "101", "1203")] == [1]
    assert [u.price for u in match_units(units, None, "1203호")] == [1, 2]   # 동을 안 주면 거르지 않는다
    assert [u.price for u in match_units(units, None, "201호")] == [3]       # 동이 없는 빌라
    assert match_units(units, "103", None) == []


# 호출 ------------------------------------------------------------------------

def test_search_tries_road_first_for_road_address_then_parcel():
    seen = []

    def handler(request):
        category = request.url.params["category"]
        seen.append(category)
        assert request.url.params["key"] == KEY and request.url.params["type"] == "address"
        if category == "road":
            return httpx.Response(200, json={"response": {"status": "NOT_FOUND"}})
        return httpx.Response(200, json=_search_ok(_parcel()))

    with _transport(handler) as c:
        assert [p.pnu for p in search_parcels(c, KEY, "수영구 광안해변로 100")] == [PNU]
    assert seen == ["road", "parcel"]
    seen.clear()
    with _transport(handler) as c:
        search_parcels(c, KEY, "수영구 광안동 212-1")
    assert seen == ["parcel"]


def test_search_road_result_without_pnu_retries_parcel():
    queries = []

    def handler(request):
        p = request.url.params
        queries.append((p["category"], p["query"]))
        if p["category"] == "road":
            return httpx.Response(200, json=_search_ok({"id": "도로명관리번호", "address": {
                "road": "부산광역시 수영구 광안해변로 100", "parcel": "광안동 212-1"}}))
        return httpx.Response(200, json=_search_ok(_parcel()))

    with _transport(handler) as c:
        assert [p.pnu for p in search_parcels(c, KEY, "수영구 광안해변로 100")] == [PNU]
    assert queries == [("road", "수영구 광안해변로 100"), ("parcel", "부산광역시 수영구 광안동 212-1")]


def test_fetch_prices_pages_and_sends_domain():
    pages = []

    def handler(request):
        p = request.url.params
        pages.append(int(p["pageNo"]))
        assert (p["pnu"], p["stdrYear"], p["domain"], p["format"]) == (PNU, "2026", "https://x.apps.dauai.org", "json")
        return httpx.Response(200, json=_prices(_field("101동", f"{p['pageNo']}01호", "100000000"), total=1500))

    with _transport(handler) as c:
        units = fetch_prices(c, KEY, "https://x.apps.dauai.org", PNU, 2026)
    assert pages == [1, 2] and [u.ho for u in units] == ["101호", "201호"]


def test_fetch_prices_drops_repeated_rows():
    # 실제 응답: 같은 호가 같은 값으로 두 번씩 온다. 빌라는 동 이름에 건물 이름이 들어온다
    rows = [_field("제이제이", "201", "116000000", area="30.03"), _field("제이제이", "201", "116000000", area="30.03"),
            _field("제이제이", "202", "122000000", area="31.5")]
    with _transport(lambda r: httpx.Response(200, json=_prices(*rows))) as c:
        units = fetch_prices(c, KEY, "", PNU, 2026)
    assert [(u.dong, u.ho, u.price) for u in units] == [("제이제이", "201", 116_000_000), ("제이제이", "202", 122_000_000)]
    assert [u.ho for u in match_units(units, None, "201호")] == ["201"]   # 동 칸을 비우고 호만


def test_latest_prices_falls_back_to_last_year():
    # 4월 말 공시 전에는 올해 값이 없다
    def handler(request):
        if request.url.params["stdrYear"] == "2026":
            return httpx.Response(200, json={"apartHousingPrices": {"field": [], "totalCount": "0"}})
        return httpx.Response(200, json=_prices(_field("101동", "1203호", "160000000", year="2025")))

    with _transport(handler) as c:
        units = latest_prices(c, KEY, "", PNU, 2026)
    assert [(u.stdr_year, u.price) for u in units] == [(2025, 160_000_000)]


# API ------------------------------------------------------------------------

@pytest.fixture
def vworld(monkeypatch):
    """브이월드 응답을 흉내 내는 handler를 끼운다. 부른 횟수는 calls에."""
    monkeypatch.setenv("VWORLD_API_KEY", KEY)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://jeonse.apps.dauai.org")
    monkeypatch.setattr(api, "_cache", {})
    state = {"handler": None, "calls": 0}

    def handler(request):
        state["calls"] += 1
        return state["handler"](request)

    def override():
        with _transport(handler) as c:
            yield c

    app.dependency_overrides[get_http_client] = override
    yield state
    app.dependency_overrides.pop(get_http_client, None)


def test_api_search(client, vworld):
    vworld["handler"] = lambda r: httpx.Response(200, json=_search_ok(_parcel()))
    r = client.get("/api/official-price/search", params={"address": "  수영구   광안동 212-1 "})
    assert r.status_code == 200, r.text
    assert r.json() == {"query": "수영구 광안동 212-1", "parcels": [
        {"pnu": PNU, "address": "부산광역시 수영구 광안동 212-1", "road_address": "부산광역시 수영구 광안해변로 100"}]}

    vworld["handler"] = lambda r: httpx.Response(200, json={"response": {"status": "NOT_FOUND"}})
    r = client.get("/api/official-price/search", params={"address": "없는 주소 999"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "ADDRESS_NOT_FOUND"


def test_api_price_by_unit_and_list(client, vworld):
    def handler(request):
        assert request.url.params["domain"] == "https://jeonse.apps.dauai.org"   # VWORLD_DOMAIN이 없으면 배포 주소
        return httpx.Response(200, json=_prices(_field("102동", "201호", "150000000"), _field("101동", "1203호", "165000000"),
                                                _field("101동", "201호", "140000000")))
    vworld["handler"] = handler

    r = client.get("/api/official-price", params={"pnu": PNU, "dong": "101", "ho": "1203"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["stdr_year"], body["complex_name"]) == (2026, "가상광안아파트")
    assert body["units"] == [{"dong": "101동", "ho": "1203호", "floor": None, "exclusive_area": 59.85,
                              "official_price": 165_000_000}]
    assert body["source"].endswith("2026년 1월 1일 기준")

    # 동·호를 안 주면 고르기 목록 (동 → 호 순), 같은 필지는 다시 부르지 않는다
    r = client.get("/api/official-price", params={"pnu": PNU})
    assert [(u["dong"], u["ho"]) for u in r.json()["units"]] == [("101동", "201호"), ("101동", "1203호"), ("102동", "201호")]
    assert vworld["calls"] == 1

    r = client.get("/api/official-price", params={"pnu": PNU, "dong": "103", "ho": "101"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "UNIT_NOT_FOUND"


def test_api_price_not_apartment(client, vworld):
    vworld["handler"] = lambda r: httpx.Response(200, json={})   # 다가구·단독 필지
    r = client.get("/api/official-price", params={"pnu": PNU})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "OFFICIAL_PRICE_NOT_FOUND"
    assert vworld["calls"] == 2   # 올해·지난해
    client.get("/api/official-price", params={"pnu": PNU})
    assert vworld["calls"] == 4   # 없음은 기억하지 않는다 (키·서비스 주소를 고친 뒤 바로 다시 찾게)


def test_api_price_key_error_is_not_not_found(client, vworld):
    vworld["handler"] = lambda r: httpx.Response(200, json={"response": {"status": "ERROR", "error": {
        "code": "INCORRECT_KEY", "text": "인증키 정보가 올바르지 않습니다"}}})
    r = client.get("/api/official-price", params={"pnu": PNU})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "OFFICIAL_PRICE_API_ERROR"


def test_api_errors_do_not_leak_key(client, vworld, caplog):
    vworld["handler"] = lambda r: httpx.Response(502, request=r)
    for path, params in (("/api/official-price/search", {"address": "수영구 광안동 212-1"}),
                         ("/api/official-price", {"pnu": PNU})):
        r = client.get(path, params=params)
        assert r.status_code == 502 and r.json()["detail"]["code"] == "OFFICIAL_PRICE_API_ERROR"
        assert KEY not in r.text
    assert KEY not in caplog.text

    assert client.get("/api/official-price", params={"pnu": "123"}).status_code == 422
    r = client.get("/api/official-price/search", params={"address": "      "})   # 공백만
    assert r.status_code == 422 and r.json()["detail"]["fields"][0]["field"] == "address"


def test_api_without_key(client, monkeypatch):
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    for path, params in (("/api/official-price/search", {"address": "수영구 광안동 212-1"}),
                         ("/api/official-price", {"pnu": PNU})):
        r = client.get(path, params=params)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "VWORLD_KEY_MISSING"
