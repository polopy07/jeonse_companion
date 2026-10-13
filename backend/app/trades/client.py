"""공공데이터포털 국토교통부 실거래가 API (아파트·연립다세대의 매매·전월세) 호출과 응답 해석.

- 요청: serviceKey(Decoding 키), LAWD_CD(법정동 시군구 5자리), DEAL_YMD(계약년월 YYYYMM), pageNo, numOfRows
- 응답: XML. header.resultCode가 정상 코드가 아니거나, 인증 오류 형식(OpenAPI_ServiceResponse)이면 TradeApiError
- 금액은 만 원 단위 문자열("82,000")로 오므로 원 단위 정수로 바꾼다
"""
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/1613000"

# (주택 유형, 거래 종류) → 서비스 경로. 주택 유형 이름은 rules/fields.yaml housing_type과 같다
ENDPOINTS = {
    ("apartment", "trade"): "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    ("apartment", "rent"): "RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
    ("row_house", "trade"): "RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    ("row_house", "rent"): "RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
}

# 단지 이름 태그는 주택 유형마다 다르다
NAME_TAG = {"apartment": "aptNm", "row_house": "mhouseNm"}

OK_CODES = {"000", "00"}   # 일부 서비스는 "00"
PAGE_SIZE = 1000


class TradeApiError(RuntimeError):
    """API가 오류를 돌려줬거나 응답을 읽을 수 없음."""


@dataclass(frozen=True)
class TradeRecord:
    housing_type: str            # apartment / row_house
    kind: str                    # trade(매매) / rent(전월세)
    lawd_cd: str
    umd_name: str                # 법정동
    jibun: str | None
    complex_name: str            # 단지 이름 (아파트명, 연립다세대명)
    exclusive_area: float        # 전용면적 ㎡
    floor: int | None
    deal_date: date
    price: int | None            # 매매가 (원)
    deposit: int | None          # 보증금 (원)
    monthly_rent: int | None     # 월세 (원)
    build_year: int | None
    cancelled: bool              # 해제 신고된 매매
    contract_type: str | None = None   # 전월세 계약 구분: 신규 / 갱신 / None(공백)


def _text(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    value = el.text.strip()
    return value or None


def _manwon(value: str | None) -> int | None:
    """"82,000" (만 원) → 820000000 (원)."""
    if value is None:
        return None
    return int(value.replace(",", "")) * 10_000


def _int(value: str | None) -> int | None:
    return int(value) if value is not None and value.lstrip("-").isdigit() else None


def parse_response(xml_text: str, housing_type: str, kind: str, lawd_cd: str) -> tuple[list[TradeRecord], int]:
    """응답 XML → (거래 목록, 전체 건수)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise TradeApiError(f"응답을 XML로 읽을 수 없습니다: {e}") from e

    if root.tag == "OpenAPI_ServiceResponse":   # 인증키·호출 한도 오류는 이 형식으로 온다
        msg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "알 수 없는 오류"
        raise TradeApiError(f"공공데이터포털 오류: {msg}")

    code = root.findtext("./header/resultCode") or root.findtext(".//resultCode")
    if code not in OK_CODES:
        msg = root.findtext("./header/resultMsg") or root.findtext(".//resultMsg") or ""
        raise TradeApiError(f"공공데이터포털 오류 {code}: {msg}")

    total = _int(root.findtext(".//totalCount")) or 0
    records = []
    for item in root.iterfind(".//items/item"):
        year, month, day = (_int(_text(item, t)) for t in ("dealYear", "dealMonth", "dealDay"))
        area = _text(item, "excluUseAr")
        name = _text(item, NAME_TAG[housing_type])
        if None in (year, month, day) or area is None or name is None:
            continue   # 날짜·면적·단지 이름이 없으면 매칭에 쓸 수 없다
        records.append(TradeRecord(
            housing_type=housing_type,
            kind=kind,
            lawd_cd=lawd_cd,
            umd_name=_text(item, "umdNm") or "",
            jibun=_text(item, "jibun"),
            complex_name=name,
            exclusive_area=float(area),
            floor=_int(_text(item, "floor")),
            deal_date=date(year, month, day),
            price=_manwon(_text(item, "dealAmount")) if kind == "trade" else None,
            deposit=_manwon(_text(item, "deposit")) if kind == "rent" else None,
            monthly_rent=_manwon(_text(item, "monthlyRent")) if kind == "rent" else None,
            build_year=_int(_text(item, "buildYear")),
            cancelled=kind == "trade" and (_text(item, "cdealType") or "").upper() == "O",
            contract_type=_text(item, "contractType") if kind == "rent" else None,
        ))
    return records, total


def fetch_month(client: httpx.Client, service_key: str, housing_type: str, kind: str,
                lawd_cd: str, deal_ymd: str) -> list[TradeRecord]:
    """한 달 치 거래를 모든 페이지에 걸쳐 받는다."""
    url = f"{BASE_URL}/{ENDPOINTS[(housing_type, kind)]}"
    records: list[TradeRecord] = []
    page = 1
    while True:
        params = {"serviceKey": service_key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd,
                  "pageNo": page, "numOfRows": PAGE_SIZE}
        try:
            resp = client.get(url, params=params, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # httpx 오류 문구에는 serviceKey가 든 요청 주소가 들어가므로 응답·로그에 싣지 않는다
            logger.warning("공공데이터포털 HTTP %s: %s", e.response.status_code, url)
            raise TradeApiError(f"공공데이터포털에 연결하지 못했습니다: HTTP {e.response.status_code}") from None
        except httpx.HTTPError as e:
            logger.warning("공공데이터포털 연결 오류 %s: %s", type(e).__name__, url)
            raise TradeApiError(f"공공데이터포털에 연결하지 못했습니다: {type(e).__name__}") from None
        batch, total = parse_response(resp.text, housing_type, kind, lawd_cd)
        records.extend(batch)
        # 걸러 낸 뒤의 건수(batch)가 아니라 전체 건수로 끝을 정한다. 한 페이지가 모두 걸러져도 다음 페이지는 받는다
        if page * PAGE_SIZE >= total:
            return records
        page += 1
