"""시연 5분 흐름을 서버 API로 처음부터 끝까지 (기획서 MVP 시연, 최종 시연 11/3 리허설용).

수영구 빌라(시연 집, docs/validation/demo_houses.yaml)로 계약 전 확인 → 특약 예시 → 테스트 결제 → 계약 당일
(담보 설정 금지 "거절당함"으로 할 일 순서가 바뀌는 장면) → 가상 날짜로 계약 2년 → 반환보증 알림 이메일 →
공시가격 발표 뒤 경보 재계산 → 만기 6개월 전 갈아타기 → 만기일 반환 확인까지 이어서 돌린다.
배포 서버와 같게 결제·접근 토큰을 꼭 요구한다(REQUIRE_CONTRACT_AUTH=true). 기능별 세부는 각 테스트 파일에서 본다.
"""
import pytest

from app import mailer
from load_demo_trades import load as load_saved_trades

ADMIN = "demo-admin"
EMAIL = "tenant@example.com"


@pytest.fixture(autouse=True)
def demo_server(tmp_path, monkeypatch):
    monkeypatch.setenv("REQUIRE_CONTRACT_AUTH", "true")
    monkeypatch.setenv("ALLOW_VIRTUAL_TODAY", "true")
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    mailer.outbox.clear()


class Phone:
    """시연 휴대폰: 계약 접근 토큰을 들고 가상 날짜로 부른다."""

    def __init__(self, client):
        self.client, self.token, self.contract_id, self.day = client, None, None, None

    def headers(self) -> dict:
        h = {"X-Virtual-Today": self.day} if self.day else {}
        return {**h, "X-Contract-Token": self.token} if self.token else h

    def call(self, method: str, url: str, status: int = 200, **kw):
        r = self.client.request(method, url, headers={**self.headers(), **kw.pop("headers", {})}, **kw)
        assert r.status_code == status, f"{method} {url} → {r.status_code} {r.text}"
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r

    def contract(self) -> dict:
        return self.call("GET", f"/api/contracts/{self.contract_id}")

    def todo(self, rule_id: str, contract: dict | None = None) -> dict:
        return next(t for t in (contract or self.contract())["todos"] if t["rule_id"] == rule_id)

    def upload(self, rule_id: str) -> dict:
        return self.call("POST", f"/api/todos/{self.todo(rule_id)['id']}/evidence",
                         files={"file": (f"{rule_id}.jpg", b"\xff\xd8 demo photo", "image/jpeg")})

    def admin(self, url: str, body: dict) -> dict:
        return self.call("POST", url, json=body, headers={"X-Admin-Token": ADMIN})


def test_demo_flow_villa(client):
    phone = Phone(client)
    as_of, _ = load_saved_trades()
    villa = next(h for h in phone.call("GET", "/api/demo-houses")["houses"] if h["id"] == "demo-villa")
    scene = villa["contract_day"]

    # 1. 계약 전 확인 (무료): 시연 등기부의 근저당 1,440만 → 비율 95%, "확인 필요", 경보 경고
    phone.day = as_of
    check = phone.call("POST", "/api/checks", json=villa["input"], status=201)
    assert check["level"] == "check_needed" and round(check["deposit_ratio"], 4) == 0.9507
    assert check["linkages"] == ["L-MORTGAGE", "L-RATIO90"]
    terms = phone.call("GET", f"/api/checks/{check['id']}/special-terms")
    assert {"S-NO-MORTGAGE", "S-GUARANTEE-CANCEL"} <= {t["id"] for t in terms["terms"]}

    # 2. 결제 없이는 패키지를 시작할 수 없고, 테스트 결제(9,900원) 뒤에 계약 당일 체크
    phone.day = scene["contract_date"]
    body = {"check_id": check["id"], **{k: scene[k] for k in ("contract_date", "balance_date", "end_date")},
            "special_term_result": scene["special_term_result"], "guarantor": "HUG", "email": EMAIL}
    assert phone.call("POST", "/api/contracts", json=body, status=402)["detail"]["code"] == "PAYMENT_REQUIRED"
    payment = phone.call("POST", f"/api/checks/{check['id']}/payment", status=201)
    assert (payment["product"], payment["amount"]) == ("package", 9900)
    created = phone.call("POST", "/api/contracts", json={**body, "payment_id": payment["payment_id"]}, status=201)
    phone.token, phone.contract_id = created["access_token"], created["id"]
    assert created["alert_level"] == "warning"

    # 3. 핵심 장면: 담보 설정 금지 "거절당함" → 4번 전입신고가 맨 위, "넣음"으로 바꾸면 내려가고 다시 거절하면 올라감
    assert created["todos"][0]["rule_id"] == "T4"
    inserted = phone.call("PATCH", f"/api/contracts/{phone.contract_id}",
                          json={"special_term_result": {"S-NO-MORTGAGE": "inserted"}})
    assert inserted["todos"][0]["rule_id"] != "T4"
    rejected = phone.call("PATCH", f"/api/contracts/{phone.contract_id}",
                          json={"special_term_result": {"S-NO-MORTGAGE": "rejected"}})
    assert rejected["todos"][0]["rule_id"] == "T4"
    assert [t["id"] for t in rejected["todos"]] == [t["id"] for t in created["todos"]]   # 같은 할 일, 순서만
    assert client.get(f"/api/contracts/{phone.contract_id}").status_code == 404           # 토큰 없으면 못 봄

    # 4. 계약 당일: 비율 90% 이상이라 보증기관 상담(2번)이 오늘까지, 상담 기록 사진으로 끝냄
    t2 = phone.todo("T2", rejected)
    assert (t2["due_date"], t2["state"], t2["days_left"]) == (scene["contract_date"], "in_progress", 0)
    phone.upload("T2")

    # 5. 계약 후 30일 안 임대차 신고(1번) → 잔금일 아침 등기부 재비교(3번)·전입신고(4번)
    phone.day = "2026-10-20"
    phone.upload("T1")
    phone.day = scene["balance_date"]
    t3 = phone.todo("T3")
    assert t3["state"] == "in_progress" and "근저당 금액 변동 비교 (필수)" in t3["required_checks"]
    phone.upload("T3")
    after_move_in = phone.upload("T4")
    t5 = phone.todo("T5", after_move_in)
    assert t5["start_date"] == "2026-11-26"   # 전입신고 다음 날부터 반환보증 가입
    assert t5["due_date"] == "2027-11-25"     # HUG: 잔금일·전입일 중 늦은 날 + 계약 기간 절반

    # 6. 반환보증 가입 마감 7일 전: 알림 실행 → 앱 안 알림과 이메일 1종
    due_before = phone.admin("/api/admin/notifications/run", {"date": "2027-11-18"})
    kinds = {(n["todo_rule_id"], n["kind"], n["channel"]) for n in due_before["created"]}
    assert ("T5", "due_before", "email") in kinds and ("T5", "due_before", "app") in kinds
    assert due_before["email_sent"] >= 1 and mailer.outbox[-1].to == EMAIL and "반환보증" in mailer.outbox[-1].body

    # 7. 2027년 공시가격 발표(시연용 가상 값 1억 1,300만) → 경보 재계산 98%, 경고 유지
    recalc = phone.admin("/api/admin/alerts/recalculate",
                         {"date": "2027-05-01", "contract_ids": [phone.contract_id],
                          "official_prices": {str(phone.contract_id): 113_000_000}})
    item = recalc["results"][0]
    assert (item["level"], item["previous_level"], item["raised"]) == ("warning", "warning", False)
    phone.day = "2027-05-01"
    report = phone.call("GET", f"/api/contracts/{phone.contract_id}/alerts/latest")
    assert report["recalculated"] and round(report["deposit_ratio"], 2) == 0.98 and report["label"] == "경고"

    # 8. 만기 6개월 전: 갱신·이사 통보(7번) → "이사할게요" → 갈아타기 (다음 집 잔금이 만기보다 빠르면 자금 틈 경고)
    phone.day = "2028-05-24"
    assert phone.todo("T7")["state"] == "in_progress"
    move = phone.call("POST", f"/api/contracts/{phone.contract_id}/move", json={
        "contract_date": "2028-09-01", "balance_date": "2028-11-10", "end_date": "2030-11-09",
        "deposit": 150_000_000, "down_payment": 15_000_000, "guarantor": "HUG"})
    assert move["return_date"] == scene["end_date"] and move["gap_days"] == 14 and move["move_in_warning"]
    assert move["warnings"]

    # 9. 만기일: 9번 보증금 반환 확인 (돌려받음 → 이체 내역 사진). 갈아타기는 돌려받은 것으로 바뀐다
    phone.day = scene["end_date"]
    assert phone.todo("T9")["state"] == "in_progress"
    phone.upload("T9")
    assert phone.call("GET", f"/api/contracts/{phone.contract_id}/move")["returned"] is True

    # 기록함: 끝낸 할 일마다 증빙이 남는다
    done = {t["rule_id"]: t for t in phone.contract()["todos"] if t["evidence_uploaded"]}
    assert {"T1", "T2", "T3", "T4", "T9"} <= set(done)


def test_demo_flow_apartment(client):
    # 해운대 아파트: 근저당 없음 → "문제 항목 없음"이지만 비율 87%·주변 전세가 보증금보다 낮아 경보 주의 →
    # 반환보증 가입(5번)이 맨 위로 (특약 없이 계약)
    phone = Phone(client)
    as_of, _ = load_saved_trades()
    houses = {h["id"]: h for h in phone.call("GET", "/api/demo-houses")["houses"]}
    apt, villa_day = houses["demo-apartment"], houses["demo-villa"]["contract_day"]

    phone.day = as_of
    check = phone.call("POST", "/api/checks", json=apt["input"], status=201)
    assert (check["level"], check["linkages"]) == ("no_problem", [])
    payment = phone.call("POST", f"/api/checks/{check['id']}/payment", status=201)
    created = phone.call("POST", "/api/contracts", status=201, json={
        "check_id": check["id"], "payment_id": payment["payment_id"], "guarantor": "HUG",
        **{k: villa_day[k] for k in ("contract_date", "balance_date", "end_date")}})
    assert created["alert_level"] == "caution" and created["special_term_effects"] == []
    assert created["todos"][0]["rule_id"] == "T5" and created["todos"][0]["moved_to_top"]
