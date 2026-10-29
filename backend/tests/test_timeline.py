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


def _timeline(client, c: dict) -> list[dict]:
    r = client.get(f"/api/contracts/{c['id']}/timeline", headers=_h(c, "2027-01-10"))
    assert r.status_code == 200, r.text
    assert r.json()["today"] == "2027-01-10"
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
    events = _timeline(client, c)
    move = next(e for e in events if e["kind"] == "move")
    assert move["date"] == "2028-06-01" and "잔금일" in move["detail"]

    assert client.post(f"/api/contracts/{c['id']}/cancel", headers=_h(c)).status_code == 200
    events = _timeline(client, c)   # 무산된 계약도 기록으로 볼 수 있다
    assert any(e["kind"] == "cancel" for e in events)
    assert client.get(f"/api/contracts/{c['id']}/timeline", headers={"X-Contract-Token": "wrong"}).status_code == 404


def test_timeline_new_contract_has_only_start(client):
    c = _contract(client)
    assert [e["kind"] for e in _timeline(client, c)] == ["check", "contract"]
