"""주소로 공동주택 공시가격 찾기 (FR-001 확장, 브이월드).

계약 전 확인 화면에서 주소 → 필지(PNU) 후보 → 동·호 → 공시가격으로 공시가격·전용면적 칸을 채운다. 저장하지 않고,
사용자가 확인한 값을 POST /api/checks의 official_price·exclusive_area로 보낸다. 못 찾거나 브이월드가 응답하지 않으면
화면은 지금처럼 직접 입력으로 넘어간다 (시연 집 2채는 GET /api/demo-houses의 미리 넣은 값).
"""
import re
import threading
import time

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError

from app.api.admin import get_http_client
from app.clock import real_today
from app.config import vworld_api_key, vworld_domain
from app.errors import api_error, responses
from app.official_price.client import (OfficialPriceApiError, UnitPrice, latest_prices, match_units, search_parcels,
                                       unit_key)
from app.schemas import OfficialPriceOut, ParcelOut, ParcelSearchOut, UnitPriceOut

router = APIRouter(prefix="/api/official-price", tags=["계약 전 확인"])

SOURCE = "국토교통부 공동주택가격 (브이월드 공간정보 오픈플랫폼)"
MANUAL_HINT = "부동산 공시가격 알리미(realtyprice.kr)에서 찾아 공시가격을 직접 입력하세요"

# 공시가격은 1년에 한 번 바뀌므로 같은 필지를 다시 묻지 않게 하루 동안 기억한다 (브이월드 호출 한도·응답 시간)
CACHE_SECONDS = 24 * 60 * 60
CACHE_MAX = 512
_cache: dict[tuple[str, int], tuple[float, list[UnitPrice]]] = {}
_cache_lock = threading.Lock()


def _key() -> str:
    key = vworld_api_key()
    if not key:
        raise api_error(503, "VWORLD_KEY_MISSING", "공시가격 자동 조회가 꺼져 있습니다", MANUAL_HINT)
    return key


def _api_failed(e: OfficialPriceApiError):
    return api_error(502, "OFFICIAL_PRICE_API_ERROR", str(e), MANUAL_HINT)


@router.get("/search", response_model=ParcelSearchOut, responses=responses(404, 422, 502, 503))
def search(address: str = Query(min_length=2, max_length=200, description="도로명 또는 지번 주소"),
           http: httpx.Client = Depends(get_http_client)):
    """주소 → 필지 후보 (PNU). 도로명·지번 아무거나 받는다."""
    query = re.sub(r"\s+", " ", address).strip()
    if len(query) < 2:   # 공백만 넣으면 min_length를 통과하므로 정리한 뒤 다시 본다
        raise RequestValidationError([{"type": "string_too_short", "loc": ("query", "address"), "input": address,
                                       "msg": "String should have at least 2 characters", "ctx": {"min_length": 2}}])
    try:
        parcels = search_parcels(http, _key(), query)
    except OfficialPriceApiError as e:
        raise _api_failed(e)
    if not parcels:
        raise api_error(404, "ADDRESS_NOT_FOUND", "주소를 찾지 못했습니다",
                        "시·구·동과 번지(또는 도로명과 건물번호)까지 넣어 다시 검색하거나 공시가격을 직접 입력하세요")
    return ParcelSearchOut(query=query, parcels=[ParcelOut(pnu=p.pnu, address=p.address, road_address=p.road_address)
                                                 for p in parcels])


def _prices(http: httpx.Client, key: str, pnu: str, this_year: int) -> list[UnitPrice]:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get((pnu, this_year))
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    units = latest_prices(http, key, vworld_domain(), pnu, this_year)
    if not units:   # 없음은 기억하지 않는다 (키·서비스 주소를 고친 뒤 바로 다시 찾을 수 있게)
        return units
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[(pnu, this_year)] = (now, units)
    return units


def _order(value: str, suffix: str) -> tuple[int, str]:
    k = unit_key(value, suffix)
    return (int(k), k) if k.isdigit() else (10**9, k)


@router.get("", response_model=OfficialPriceOut, responses=responses(404, 422, 502, 503))
def official_price(pnu: str = Query(pattern=r"^\d{19}$", description="GET /api/official-price/search의 필지 고유번호"),
                   dong: str | None = Query(None, max_length=20, description="동 (예: 101동, 101). 동이 없는 빌라는 비움"),
                   ho: str | None = Query(None, max_length=20, description="호 (예: 1203호, 1203)"),
                   http: httpx.Client = Depends(get_http_client)):
    """필지의 공동주택 공시가격. dong·ho를 주면 그 호만, 안 주면 모든 호 (동·호 고르기 목록)."""
    key = _key()
    try:
        units = _prices(http, key, pnu, real_today().year)
    except OfficialPriceApiError as e:
        raise _api_failed(e)
    if not units:
        raise api_error(404, "OFFICIAL_PRICE_NOT_FOUND", "이 주소에는 공동주택 공시가격이 없습니다",
                        "아파트·연립·다세대만 있습니다(다가구·단독은 경보 대상 아님). 주소가 맞는지 확인하거나 " + MANUAL_HINT)
    matched = match_units(units, dong, ho)
    if not matched:
        raise api_error(404, "UNIT_NOT_FOUND", "그 동·호의 공시가격을 찾지 못했습니다",
                        "동·호를 빼고 다시 불러 목록에서 고르거나 공시가격을 직접 입력하세요")
    matched = sorted(matched, key=lambda u: (_order(u.dong, "동"), _order(u.ho, "호")))
    return OfficialPriceOut(
        pnu=pnu,
        stdr_year=matched[0].stdr_year,
        complex_name=matched[0].complex_name,
        units=[UnitPriceOut(dong=u.dong, ho=u.ho, floor=u.floor, exclusive_area=u.exclusive_area,
                            official_price=u.price) for u in matched],
        source=f"{SOURCE}, {matched[0].stdr_year}년 1월 1일 기준",
    )
