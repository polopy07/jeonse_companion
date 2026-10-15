"""부산 전세 거래 건수 (기획서 '시장 규모와 매출 추정' 1단계 산식).

국토교통부 전월세 실거래가 4종(아파트, 연립다세대, 단독/다가구, 오피스텔)을 공공데이터포털에서 받아
부산 16개 구·군, 한 해 12개월의 전세(월세 0원) 건수를 센다. 계약 구분(신규/갱신/공백)도 나눠 센다.

    pip install httpx
    python docs/plan/figures/busan_jeonse_count.py [연도] [--env backend/.env] [--cache 폴더]

- 인증키는 env 파일의 DATA_GO_KR_SERVICE_KEY (Encoding·Decoding 키 모두 됨). 4종 모두 활용신청돼 있어야 한다
- 호출 수: 4종 × 16개 구·군 × 12개월 = 768번 (+ 1,000건 넘는 달은 페이지). 받은 응답은 --cache 폴더에 남겨 다시 돌릴 때 건너뜀
"""
import argparse
import json
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote

import httpx

BASE = "https://apis.data.go.kr/1613000"
SERVICES = {
    "아파트": "RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
    "연립다세대": "RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
    "단독다가구": "RTMSDataSvcSHRent/getRTMSDataSvcSHRent",
    "오피스텔": "RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent",
}
BUSAN = ["26110", "26140", "26170", "26200", "26230", "26260", "26290", "26320",
         "26350", "26380", "26410", "26440", "26470", "26500", "26530", "26710"]
PAGE = 1000


def load_key(env: Path) -> str:
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATA_GO_KR_SERVICE_KEY="):
            return unquote(line.split("=", 1)[1].strip())
    raise SystemExit(f"{env}에 DATA_GO_KR_SERVICE_KEY가 없습니다")


def fetch(client: httpx.Client, key: str, path: str, lawd: str, ymd: str) -> Counter:
    counts, page = Counter(), 1
    while True:
        for attempt in range(8):
            try:
                r = client.get(f"{BASE}/{path}", params={
                    "serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ymd, "pageNo": page, "numOfRows": PAGE}, timeout=30)
                r.raise_for_status()
                root = ET.fromstring(r.text)
                break
            except (httpx.HTTPError, ET.ParseError):   # 오류 문구에 키가 든 주소가 있어 출력하지 않는다
                time.sleep(3 * (attempt + 1))
        else:
            raise SystemExit(f"{path} {lawd} {ymd}: 공공데이터포털에 연결하지 못했습니다")
        if root.tag == "OpenAPI_ServiceResponse":
            raise SystemExit(f"{path}: {root.findtext('.//returnAuthMsg')} (활용신청이 됐는지 확인)")
        for it in root.iterfind(".//items/item"):
            rent = (it.findtext("monthlyRent") or "").strip().replace(",", "")
            kind = "전세" if rent in ("", "0") else "월세"
            counts[kind] += 1
            counts[f"{kind}_{(it.findtext('contractType') or '').strip() or '공백'}"] += 1
        total = int((root.findtext(".//totalCount") or "0").strip() or 0)
        if page * PAGE >= total:
            return counts
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("year", nargs="?", default="2025")
    ap.add_argument("--env", default="backend/.env", type=Path)
    ap.add_argument("--cache", default=".busan_rent_cache", type=Path)
    args = ap.parse_args()
    key = load_key(args.env)
    args.cache.mkdir(exist_ok=True)
    months = [f"{args.year}{m:02d}" for m in range(1, 13)]

    def one(job):
        name, lawd, ymd = job
        path = args.cache / f"{name}_{lawd}_{ymd}.json"
        if path.exists():
            return name, Counter(json.loads(path.read_text(encoding="utf-8")))
        counts = fetch(client, key, SERVICES[name], lawd, ymd)
        path.write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")
        return name, counts

    by_type = {name: Counter() for name in SERVICES}
    with httpx.Client() as client, ThreadPoolExecutor(3) as ex:
        for name, counts in ex.map(one, [(n, l, m) for n in SERVICES for l in BUSAN for m in months]):
            by_type[name].update(counts)

    total = sum(by_type.values(), Counter())
    print(f"부산 {args.year}년 전월세 실거래 (월세 0원 = 전세)")
    for name, c in [*by_type.items(), ("합계", total)]:
        share = c["전세"] / ((c["전세"] + c["월세"]) or 1) * 100
        print(f"{name:6} 전세 {c['전세']:7,} (신규 {c['전세_신규']:6,} · 갱신 {c['전세_갱신']:5,} · 공백 {c['전세_공백']:5,})"
              f"  월세 {c['월세']:7,}  전세 비중 {share:4.1f}%")


if __name__ == "__main__":
    main()
