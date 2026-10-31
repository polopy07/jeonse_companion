"""브이월드(공간정보 오픈플랫폼) 주소 검색·공동주택가격 속성 조회 호출과 응답 해석.

- 주소 검색(검색 API 2.0): GET /req/search?service=search&request=search&version=2.0&type=address&category=parcel|road
  &query=<주소>&format=json&errorformat=json&key=<인증키>. 지번 결과의 items[].id가 PNU(필지 고유번호 19자리)
- 공동주택가격(국가중점데이터): GET /ned/data/getApartHousingPriceAttr?pnu=<PNU>&stdrYear=<기준연도>&format=json
  &numOfRows=&pageNo=&key=<인증키>&domain=<서비스 주소>. 응답 apartHousingPrices.field[]에 호별
  aphusNm(단지명)·dongNm·hoNm·floorNm·prvuseAr(전용면적)·pblntfPc(공시가격, 원)
- 공동주택이 아닌 필지(다가구·단독 등)는 apartHousingPrices가 없거나 field가 비어 있다
"""
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.vworld.kr/req/search"
PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
TIMEOUT = 6          # 초. 계약 전 확인 화면에서 기다리는 시간이라 짧게 두고(앱은 15초에 끊음), 넘으면 직접 입력으로
PAGE_SIZE = 1000     # 공동주택가격 한 페이지 최대 건수
MAX_PAGES = 20       # 큰 단지도 2만 세대를 넘지 않는다. 응답이 이상해도 끝없이 부르지 않게
SEARCH_SIZE = 5      # 주소 후보 수
OK_CODES = {"", "00", "000", "INFO-000"}

PNU = re.compile(r"^\d{19}$")
ROAD_ADDRESS = re.compile(r"(로|길)\s*\d")   # "수영로 123", "광안해변로 219번길 5"


class OfficialPriceApiError(RuntimeError):
    """브이월드가 오류를 돌려줬거나 응답을 읽을 수 없음."""


@dataclass(frozen=True)
class Parcel:
    pnu: str
    address: str          # 지번 주소 (검색 결과의 정식 주소)
    road_address: str | None


@dataclass(frozen=True)
class UnitPrice:
    stdr_year: int
    complex_name: str
    dong: str             # 동 이름 그대로 ("101동", 동이 없는 빌라는 "")
    ho: str               # 호 이름 그대로 ("1203호", "201")
    floor: str | None
    exclusive_area: float | None
    price: int            # 공시가격 (원)


def _get_json(client: httpx.Client, url: str, params: dict) -> dict:
    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # 오류 문구에는 인증키가 든 요청 주소가 들어가므로 응답·로그에 싣지 않는다
        logger.warning("브이월드 HTTP %s: %s", e.response.status_code, url)
        raise OfficialPriceApiError(f"브이월드에 연결하지 못했습니다: HTTP {e.response.status_code}") from None
    except httpx.HTTPError as e:
        logger.warning("브이월드 연결 오류 %s: %s", type(e).__name__, url)
        raise OfficialPriceApiError(f"브이월드에 연결하지 못했습니다: {type(e).__name__}") from None
    try:
        body = resp.json()
    except ValueError:
        raise OfficialPriceApiError("브이월드 응답을 JSON으로 읽을 수 없습니다") from None
    if not isinstance(body, dict):
        raise OfficialPriceApiError("브이월드 응답 형식이 다릅니다")
    return body


def _str(value) -> str:
    return "" if value is None else str(value).strip()


# 주소 검색 ---------------------------------------------------------------------

def _error_text(response: dict, status: str) -> str:
    error = response.get("error") or {}
    return _str(error.get("text")) or _str(error.get("code")) or status or "알 수 없는 오류"


def _region(road: str) -> str:
    """도로명 주소의 앞 두 칸 ("부산광역시 해운대구 세실로 7 (...)" → "부산광역시 해운대구")."""
    return " ".join(road.split()[:2])


def parse_search(body: dict) -> tuple[list[Parcel], list[str]]:
    """검색 API 응답 → (필지 후보, PNU가 없는 결과의 지번 주소).

    지번 결과와 실제 도로명 결과(2026-10-31 확인)는 id가 PNU(19자리)다. 도로명 결과의 id가 PNU가 아니면
    지번 주소로 한 번 더 찾을 수 있게 따로 돌려준다. 도로명 결과의 지번 주소는 "좌동 1331"처럼 시·구가 없어
    도로명 주소의 시·구를 붙인다.
    """
    response = body.get("response") or {}
    status = _str(response.get("status")).upper()
    if status == "NOT_FOUND":
        return [], []
    if status != "OK":
        raise OfficialPriceApiError(f"브이월드 주소 검색 오류: {_error_text(response, status)}")
    parcels, fallbacks = [], []
    for item in ((response.get("result") or {}).get("items") or []):
        address = item.get("address") or {}
        parcel, road = _str(address.get("parcel")), _str(address.get("road"))
        if parcel and road and not parcel.startswith(_region(road).split()[0]):
            parcel = f"{_region(road)} {parcel}"
        pnu = _str(item.get("id"))
        if PNU.match(pnu):
            parcels.append(Parcel(pnu=pnu, address=parcel or _str(item.get("title")), road_address=road or None))
        elif parcel:
            fallbacks.append(parcel)
    return parcels, fallbacks


def _search(client: httpx.Client, key: str, query: str, category: str) -> tuple[list[Parcel], list[str]]:
    params = {"service": "search", "request": "search", "version": "2.0", "type": "address", "category": category,
              "query": query, "size": SEARCH_SIZE, "page": 1, "format": "json", "errorformat": "json", "key": key}
    return parse_search(_get_json(client, SEARCH_URL, params))


def search_parcels(client: httpx.Client, key: str, query: str) -> list[Parcel]:
    """주소(도로명·지번 아무거나) → 필지 후보. 도로명처럼 보이면 도로명부터, 못 찾으면 다른 쪽으로 한 번 더."""
    order = ("road", "parcel") if ROAD_ADDRESS.search(query) else ("parcel", "road")
    for category in order:
        found, fallbacks = _search(client, key, query, category)
        if found:
            return found
        if category == "road" and fallbacks:   # 도로명 결과의 id가 PNU가 아니면 그 결과의 지번 주소로
            found, _ = _search(client, key, fallbacks[0], "parcel")
            if found:
                return found
    return []


# 공동주택가격 ------------------------------------------------------------------

def _area(value) -> float | None:
    try:
        return float(_str(value).replace(",", ""))
    except ValueError:
        return None


def parse_prices(body: dict) -> tuple[list[UnitPrice], int]:
    """공동주택가격 응답 → (호별 가격, 전체 건수). 공동주택이 아닌 필지는 빈 목록."""
    data = body.get("apartHousingPrices")
    if not data:
        # 인증키·서비스 주소 오류는 다른 모양({"response": {"status": "ERROR", ...}})으로 올 수 있다.
        # "공시가격 없음"(404)으로 보이지 않게 오류로 낸다
        response = body.get("response") or {}
        status = _str(response.get("status")).upper()
        if status == "ERROR" or body.get("error"):
            raise OfficialPriceApiError(f"브이월드 공동주택가격 오류: {_error_text(response or body, status)}")
        return [], 0
    code = _str(data.get("resultCode"))
    if code not in OK_CODES:
        raise OfficialPriceApiError(f"브이월드 공동주택가격 오류 {code}: {_str(data.get('resultMsg'))}")
    fields = data.get("field") or []
    if isinstance(fields, dict):   # 한 건이면 목록이 아니라 객체로 오는 경우
        fields = [fields]
    units = []
    for f in fields:
        price = _str(f.get("pblntfPc")).replace(",", "")
        year = _str(f.get("stdrYear"))
        if not price.isdigit() or int(price) <= 0 or not year.isdigit():
            continue
        units.append(UnitPrice(stdr_year=int(year), complex_name=_str(f.get("aphusNm")), dong=_str(f.get("dongNm")),
                               ho=_str(f.get("hoNm")), floor=_str(f.get("floorNm")) or None,
                               exclusive_area=_area(f.get("prvuseAr")), price=int(price)))
    total = _str(data.get("totalCount"))
    return units, int(total) if total.isdigit() else len(units)


def fetch_prices(client: httpx.Client, key: str, domain: str, pnu: str, year: int) -> list[UnitPrice]:
    """한 필지·한 기준연도의 호별 공동주택가격을 모든 페이지에 걸쳐 받는다.

    브이월드는 같은 호를 같은 값으로 두 번씩 보내기도 해서(실제 응답: 부산 해운대 상록 1,000세대가 2,000줄)
    동·호·전용면적·가격이 모두 같은 줄은 한 번만 남긴다.
    """
    units: list[UnitPrice] = []
    for page in range(1, MAX_PAGES + 1):
        params = {"pnu": pnu, "stdrYear": year, "format": "json", "numOfRows": PAGE_SIZE, "pageNo": page, "key": key}
        if domain:
            params["domain"] = domain
        batch, total = parse_prices(_get_json(client, PRICE_URL, params))
        units.extend(batch)
        if not batch or page * PAGE_SIZE >= total:
            break
    return list(dict.fromkeys(units))   # UnitPrice는 frozen dataclass라 같은 값이면 같은 키, 순서는 처음 나온 대로


def latest_prices(client: httpx.Client, key: str, domain: str, pnu: str, this_year: int,
                  years_back: int = 1) -> list[UnitPrice]:
    """가장 최근 기준연도의 가격. 올해 공시(4월 말) 전이면 올해 값이 없어 지난해까지 찾는다
    (공동주택이 아닌 필지는 두 번 다 비어 있으니, 앱이 오래 기다리지 않게 더 거슬러 가지 않는다)."""
    for year in range(this_year, this_year - years_back - 1, -1):
        units = fetch_prices(client, key, domain, pnu, year)
        if units:
            return units
    return []


# 동·호 맞추기 -----------------------------------------------------------------

def unit_key(value: str, suffix: str) -> str:
    """"101동"·"제101동"·"101"·" 0101 동" → "101". 동·호 이름은 단지마다 표기가 달라 숫자·글자만 남겨 비교한다."""
    v = re.sub(r"\s+", "", value or "")
    v = v.removesuffix(suffix)
    if re.fullmatch(r"제\d+", v):
        v = v[1:]
    return v.lstrip("0") or v


def match_units(units: list[UnitPrice], dong: str | None, ho: str | None) -> list[UnitPrice]:
    """동·호로 거른다. 주지 않은 쪽은 거르지 않는다 (동이 없는 빌라는 호만)."""
    out = units
    if dong:
        out = [u for u in out if unit_key(u.dong, "동") == unit_key(dong, "동")]
    if ho:
        out = [u for u in out if unit_key(u.ho, "호") == unit_key(ho, "호")]
    return out
