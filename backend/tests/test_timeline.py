"""계약 타임라인 (GET /api/contracts/{id}/timeline, FR-032, UI-06, #51)."""
import pytest

from tests.test_contract_patch import _contract
from tests.test_move import BY_ID, _next_input
from tests.test_todo_complete import _set

ADMIN = "t"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)


def _h(c: dict, day: str | None = None) -> dict:
    return {"X-Contract-Token": c["access_token"], **({"X-Virtual-Today": day} if day else {})}


def _timeline(client, c: dict, day: str = "2027-01-10") -> list[dict]:
    r = client.get(f"/api/contracts/{c['id']}/timeline", headers=_h(c, day))
    assert r.status_code == 200, r.text
    assert r.json()["today"] == day
    return r.json()["events"]


def test_timeline_collects_two_years(client):
    # 빌라(확인 필요, 경보 경고), 담보 설정 금지 거절
    c = _contract(client, special_term_result={"S-NO-MORTGAGE": "rejected"})
    client.post(f"/api/todos/{next(t['id'] for t in c['todos'] if t['rule_id'] == 'T4')}/evidence",
                files={"file": ("p.jpg", b"\xff\xd8 jpeg", "image/jpeg")}, headers=_h(c, "2026-12-01"))
    _set(client, c, "T1", {"status": "skipped", "done_date": "2026-11-20"})
    client.post("/api/admin/alerts/recalculate", headers={"X-Admin-Token": ADMIN},
                json={"date": "2026-12-20", "contract_ids": [c["id"]], "official_prices": {str(c["id"]): 300_000_000}})

    events = _timeline(client, c)
    kinds = [e["kind"] for e in events]
    assert kinds[:3] == ["check", "contract", "special_term"]
    check = events[0]
    assert check["title"] == "계약 전 확인: 확인 필요" and check["level"] == "check_needed" and "%" in check["detail"]
    assert events[1]["date"] == "2026-11-02" and "경고" in events[1]["detail"]
    term = events[2]
    assert term["title"].startswith("잔금일 다음 날까지 담보 설정 금지") and term["title"].endswith("거절당함")
    assert term["rule_id"] == "S-NO-MORTGAGE" and term["detail"]

    todos = [e for e in events if e["kind"] == "todo"]
    assert [(e["date"], e["rule_id"], e["evidence_uploaded"]) for e in todos] == [
        ("2026-11-20", "T1", False), ("2026-12-01", "T4", True)]
    assert todos[0]["title"].startswith("나중에 올리기") and todos[1]["title"] == "완료: 전입신고"

    alert = next(e for e in events if e["kind"] == "alert")
    assert alert["date"] == "2026-12-20" and "(내려감)" in alert["title"]   # 공시가격 3억 → 비율이 낮아짐
    assert [e["date"] for e in events] == sorted(e["date"] for e in events)


def test_timeline_move_and_cancel(client):
    c = _contract(client)
    client.post(f"/api/contracts/{c['id']}/move", json=_next_input(BY_ID["S10-b"]), headers=_h(c, "2028-06-01"))
    events = _timeline(client, c, "2028-06-01")
    move = next(e for e in events if e["kind"] == "move")
    assert move["date"] == "2028-06-01" and "잔금일" in move["detail"]
    assert not any(e["kind"] == "move" for e in _timeline(client, c))   # 그 전 날짜로 보면 아직 없음

    assert client.post(f"/api/contracts/{c['id']}/cancel", headers=_h(c)).status_code == 200
    events = _timeline(client, c)   # 무산된 계약도 기록으로 볼 수 있다
    assert any(e["kind"] == "cancel" for e in events)
    assert [e["kind"] for e in _timeline(client, c, "2026-11-01")] == ["check"]   # 계약일 전으로 보면 무산도 아직 없음
    assert client.get(f"/api/contracts/{c['id']}/timeline", headers={"X-Contract-Token": "wrong"}).status_code == 404


def test_timeline_new_contract_has_only_start(client):
    c = _contract(client)
    assert [e["kind"] for e in _timeline(client, c)] == ["check", "contract"]


def test_timeline_registry_documents_and_return(client):
    # 계약 당일 재비교(변동 없음) → 첫 계약 서류 → 잔금일 재비교(압류가 새로 생겨 보류 안내) → 만기일 "못 받음"
    c = _contract(client)
    h = {"X-Contract-Token": c["access_token"]}
    same = {"mortgage": True, "mortgage_amount": 120_000_000}
    for day, registry in (("2026-11-02", same), ("2026-12-01", {**same, "seizure": True})):
        r = client.post(f"/api/contracts/{c['id']}/registry-compare", json={"registry": registry},
                        headers={**h, "X-Virtual-Today": day})
        assert r.status_code == 201, r.text
    r = client.post(f"/api/contracts/{c['id']}/documents", data={"kind": "contract"},
                    files={"file": ("p.jpg", b"\xff\xd8 jpeg", "image/jpeg")}, headers=h)
    assert r.status_code == 200, r.text
    assert client.post(f"/api/contracts/{c['id']}/return-response",
                       headers={**h, "X-Virtual-Today": "2028-11-30"}).status_code == 200

    r = client.get(f"/api/contracts/{c['id']}/timeline", headers={**h, "X-Virtual-Today": "2028-12-01"})
    events = r.json()["events"]
    registry = [e for e in events if e["kind"] == "registry"]
    assert [(e["date"], e["title"]) for e in registry] == [
        ("2026-11-02", "등기부 재비교(계약 당일): 변동 없음"), ("2026-12-01", "등기부 재비교(잔금일): 보류 안내")]
    assert registry[0]["detail"] is None
    assert registry[1]["detail"].startswith("잔금 보류 후 상담 · ") and "새로 생기거나 늘어남" in registry[1]["detail"]
    # 같은 날 재비교가 부른 경보 재계산은 단계가 그대로면 따로 쌓지 않는다
    assert not any(e["kind"] == "alert" and e["date"] in ("2026-11-02", "2026-12-01") and "(그대로)" in e["title"]
                   for e in events)

    # 첫 계약 서류는 올린 실제 날짜와 상관없이 계약일에 (잔금일에 보든 만기 뒤에 보든 같음)
    doc = next(e for e in events if e["kind"] == "document")
    assert (doc["date"], doc["rule_id"]) == ("2026-11-02", "contract") and doc["title"].startswith("첫 계약 서류: 계약서")
    ret = next(e for e in events if e["kind"] == "return")
    assert (ret["date"], ret["title"]) == ("2028-11-30", "보증금 못 받음: 반환 대응 시작")
    kinds = [e["kind"] for e in events if e["date"] == "2026-11-02"]
    assert kinds == sorted(kinds, key=["check", "contract", "registry", "special_term", "document"].index)

    r = client.get(f"/api/contracts/{c['id']}/timeline", headers={**h, "X-Virtual-Today": "2026-12-01"})
    assert next(e["date"] for e in r.json()["events"] if e["kind"] == "document") == "2026-11-02"

    # 가상 날짜가 계약일 전이면 계약 당일 체크와 함께 첫 계약 서류도 아직 없다
    r = client.get(f"/api/contracts/{c['id']}/timeline", headers={**h, "X-Virtual-Today": "2026-11-01"})
    assert [e["kind"] for e in r.json()["events"]] == ["check"]


def test_timeline_only_up_to_today(client):
    # 가상 날짜를 되돌리면 그 뒤에 끝낸 할 일·재계산은 아직 일어나지 않은 것으로 뺀다
    c = _contract(client)
    _set(client, c, "T1", {"status": "skipped", "done_date": "2026-11-20"})
    client.post("/api/admin/alerts/recalculate", headers={"X-Admin-Token": ADMIN},
                json={"date": "2026-12-20", "contract_ids": [c["id"]], "official_prices": {str(c["id"]): 300_000_000}})
    r = client.get(f"/api/contracts/{c['id']}/timeline", headers=_h(c, "2026-11-10"))
    assert [e["kind"] for e in r.json()["events"]] == ["check", "contract"]
    assert [e["kind"] for e in _timeline(client, c)] == ["check", "contract", "todo", "alert"]
