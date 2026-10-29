"""반환 대응 (POST·DELETE /api/contracts/{id}/return-response, GET /api/contracts/{id}/return-guide,
FR-024·034·035, UC-009, AC-009, #52)."""
import pytest

from tests.test_contract_patch import _contract, _patch
from tests.test_todo_complete import _set, _todo

END = "2028-11-30"   # test_contract_patch.DATES 만기일
PHOTO = b"\xff\xd8\xff\xe0 fake jpeg"
STEPS = ["R1", "R2", "R3", "R4"]


@pytest.fixture(autouse=True)
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))


def _h(c: dict, day: str = END) -> dict:
    return {"X-Contract-Token": c["access_token"], "X-Virtual-Today": day}


def _start(client, c: dict, day: str = END):
    return client.post(f"/api/contracts/{c['id']}/return-response", headers=_h(c, day))


def _guide(client, c: dict, day: str = END) -> dict:
    r = client.get(f"/api/contracts/{c['id']}/return-guide", headers=_h(c, day))
    assert r.status_code == 200, r.text
    return r.json()


def _upload(client, c: dict, rule_id: str, day: str = END):
    r = client.post(f"/api/todos/{_todo(c, rule_id)['id']}/evidence", files={"file": ("p.jpg", PHOTO, "image/jpeg")},
                    headers=_h(c, day))
    assert r.status_code == 200, r.text
    return r.json()


def _keep(c: dict, body: dict) -> dict:
    """응답(ContractOut)에 접근 토큰을 붙여 다음 요청에 쓴다 (토큰은 계약을 만들 때만 받음)."""
    return {**body, "access_token": c["access_token"]}


def _code(r) -> str:
    return r.json()["detail"]["code"]


def _states(guide: dict) -> list[str]:
    return [s["state"] for s in guide["steps"]]


def test_preview_before_not_returned(client):
    # "못 받음" 전에도 청구 서류를 미리 점검할 수 있다 (경보 위험 단계). 단계는 할 일이 아직 없음
    c = _contract(client)
    g = _guide(client, c, "2027-05-01")
    assert (g["status"], g["not_returned_date"], g["end_date"]) == ("preview", None, END)
    assert [s["rule_id"] for s in g["steps"]] == STEPS
    assert _states(g) == ["todo"] * 4 and all(s["todo_id"] is None for s in g["steps"])
    r4 = g["steps"][3]
    assert r4["title"] == "반환보증 청구" and r4["link"]["url"] == "https://www.khug.or.kr"
    # 미리 점검은 지금 준비할 수 있는 할 일 서류만, 처음 나온 순서로: 계약서(T4) → 신고필증(T1) → 보증서(T5)
    # (반환 요청·내용증명·등기부는 "못 받음" 뒤 단계에서 생기는 서류라 세지 않음, #124 리뷰)
    assert [d["rule_id"] for d in g["documents"]] == ["T4", "T1", "T5"]
    assert next(d for d in g["documents"] if d["rule_id"] == "T4") == {
        "rule_id": "T4", "todo_id": _todo(c, "T4")["id"], "name": "확정일자 받은 계약서", "uploaded": False,
        "needed_by": STEPS}
    assert g["missing_count"] == 3
    assert g["steps"][1]["missing_documents"] == ["확정일자 받은 계약서"]
    assert g["disclaimer"] and [h["label"] for h in g["help_desks"]] == ["대법원 전자소송", "대한법률구조공단 상담"]


def test_not_returned_adds_steps_on_top(client):
    # AC-009: 만기일에 "못 받음"을 고르면 반환 대응 단계가 맨 위 할 일로 붙는다
    c = _contract(client)
    r = _start(client, c, "2028-11-29")
    assert r.status_code == 409 and _code(r) == "RETURN_NOT_DUE"

    r = _start(client, c)
    assert r.status_code == 200, r.text
    body = _keep(c, r.json())
    assert body["not_returned_date"] == END
    assert [t["rule_id"] for t in body["todos"][:4]] == STEPS
    r1 = body["todos"][0]
    assert (r1["start_date"], r1["due_date"], r1["moved_to_top"], r1["state"]) == (END, None, True, "in_progress")
    assert r1["evidence"] == "반환 요청 기록 (문자·통화 캡처)"
    assert _todo(body, "T9")["status"] == "todo"   # 9번은 돌려받을 때 끝낸다

    again = _start(client, c, "2028-12-03")   # 다시 보내도 같은 할 일·시작일
    assert again.status_code == 200
    assert [(t["id"], t["start_date"]) for t in again.json()["todos"][:4]] == [(t["id"], END) for t in body["todos"][:4]]

    g = _guide(client, body)
    assert (g["status"], g["not_returned_date"]) == ("in_progress", END)
    assert _states(g) == ["current", "todo", "todo", "todo"]
    assert [s["todo_id"] for s in g["steps"]] == [_todo(body, r)["id"] for r in STEPS]


def test_steps_and_documents_follow_records(client):
    # 단계 끝내기·증빙은 할 일 API 그대로. 기록함에 올린 서류는 대조에서 빠진다 (FR-035)
    c = _contract(client)
    c = _keep(c, _start(client, c).json())
    c = _keep(c, _upload(client, c, "R1", "2028-12-01"))
    c = _keep(c, _upload(client, c, "T4", "2028-12-01"))
    g = _guide(client, c, "2028-12-01")
    assert _states(g) == ["done", "current", "todo", "todo"]
    assert g["steps"][0]["evidence_uploaded"] and g["steps"][0]["done_date"] == "2028-12-01"
    assert g["steps"][1]["missing_documents"] == []
    assert {d["rule_id"] for d in g["documents"] if not d["uploaded"]} == {"T1", "R2", "T5", "R3"}
    assert g["missing_count"] == 4

    # 증빙이 필요한 단계는 증빙 없이 끝낼 수 없고, 나중에 올리기는 끝낸 것으로 치되 서류는 빠진 채로
    assert _set(client, c, "R2", {"status": "done"}, day="2028-12-02").json()["detail"]["code"] == "EVIDENCE_REQUIRED"
    r = _set(client, c, "R2", {"status": "skipped"}, day="2028-12-02")
    assert r.status_code == 200, r.text
    g = _guide(client, c, "2028-12-02")
    assert _states(g) == ["done", "done", "current", "todo"]
    assert next(d for d in g["documents"] if d["rule_id"] == "R2")["uploaded"] is False


def test_already_returned_and_ended(client):
    c = _contract(client)
    assert _set(client, c, "T9", {"status": "skipped"}, day=END).status_code == 200
    r = _start(client, c)
    assert r.status_code == 409 and _code(r) == "ALREADY_RETURNED"

    # 반환 대응 중 늦게라도 돌려받으면 9번을 끝낸다 → 끝남. 남은 단계는 할 일에서 빠지고(맨 위에 남지 않게),
    # 끝낸 단계는 기록(archived)으로 남는다 (#124 리뷰 1번)
    c2 = _contract(client)
    c2 = _keep(c2, _start(client, c2).json())
    c2 = _keep(c2, _upload(client, c2, "R1", day="2028-12-05"))
    r = _set(client, c2, "T9", {"status": "skipped"}, day="2028-12-20")
    assert r.status_code == 200
    todos = {t["rule_id"]: t for t in r.json()["todos"]}
    assert [s for s in STEPS if s in todos] == ["R1"]
    assert todos["R1"]["status"] == "done" and not todos["R1"]["moved_to_top"]
    assert r.json()["todos"][-1]["rule_id"] == "R1"   # 기록은 맨 뒤 (계획에서 빠진 끝낸 할 일)
    g = _guide(client, c2, "2028-12-20")
    assert g["status"] == "ended" and _states(g) == ["done", "todo", "todo", "todo"]
    assert g["steps"][0]["evidence_uploaded"] is True

    # 9번을 되돌리면 단계가 다시 할 일로 (끝낸 1단계는 그대로)
    r = _set(client, c2, "T9", {"status": "todo"}, day="2028-12-21")
    assert r.status_code == 200, r.text
    todos = {t["rule_id"]: t for t in r.json()["todos"]}
    assert all(s in todos for s in STEPS) and todos["R1"]["status"] == "done" and todos["R1"]["moved_to_top"]
    assert [t["rule_id"] for t in r.json()["todos"][:4]] == STEPS   # 다시 맨 위
    assert _guide(client, c2, "2028-12-21")["status"] == "in_progress"


def test_undo_not_returned(client):
    c = _contract(client)
    r = client.delete(f"/api/contracts/{c['id']}/return-response", headers=_h(c))
    assert r.status_code == 409 and _code(r) == "RETURN_NOT_STARTED"

    c = _keep(c, _start(client, c).json())
    c = _keep(c, _upload(client, c, "R1"))
    r = client.delete(f"/api/contracts/{c['id']}/return-response", headers=_h(c))
    assert r.status_code == 409 and _code(r) == "RETURN_STEP_DONE"

    assert _set(client, c, "R1", {"status": "todo"}, day=END).status_code == 200
    r = client.delete(f"/api/contracts/{c['id']}/return-response", headers=_h(c))
    assert r.status_code == 200, r.text
    body = _keep(c, r.json())
    assert body["not_returned_date"] is None and not any(t["rule_id"] in STEPS for t in body["todos"])
    assert _guide(client, body)["status"] == "preview"


def test_no_guarantor_gets_public_counsel(client):
    # 보증 미가입: 4단계는 공공 상담, 보증서(T5)는 이 계약에 없어 대조하지 않는다
    c = _contract(client, guarantor="none")
    c = _keep(c, _start(client, c).json())
    g = _guide(client, c)
    r4 = g["steps"][3]
    assert (r4["title"], r4["evidence"], r4["link"]["url"]) == ("공공 상담 받기", None, "https://www.klac.or.kr")
    assert "T5" not in [d["rule_id"] for d in g["documents"]] and g["missing_count"] == 5
    assert _set(client, c, "R4", {"status": "done"}, day=END).status_code == 200   # 증빙 없는 단계


def test_end_date_cannot_move_past_not_returned(client):
    c = _contract(client)
    c = _keep(c, _start(client, c).json())
    r = _patch(client, c["id"], {"end_date": "2028-12-31"})
    assert r.status_code == 422 and "반환 대응" in r.text
    assert _patch(client, c["id"], {"end_date": "2028-11-20"}).status_code == 200   # 앞당기는 것은 됨


def test_cancelled_and_token(client):
    c = _contract(client)
    assert client.get(f"/api/contracts/{c['id']}/return-guide", headers={"X-Contract-Token": "wrong"}).status_code == 404
    assert client.post(f"/api/contracts/{c['id']}/cancel", headers=_h(c)).status_code == 200
    r = _start(client, c)
    assert r.status_code == 409 and _code(r) == "CONTRACT_CANCELLED"
    assert _guide(client, c)["status"] == "preview"   # 무산된 계약도 기록으로 볼 수 있다


def test_steps_get_start_notification(client, monkeypatch):
    # 반환 대응 단계도 다른 할 일처럼 시작일에 앱 알림이 간다
    monkeypatch.setenv("ADMIN_TOKEN", "t")
    c = _contract(client)
    _start(client, c)
    r = client.post("/api/admin/notifications/run", json={"date": END}, headers={"X-Admin-Token": "t"})
    assert r.status_code == 200, r.text
    kinds = {(n["todo_rule_id"], n["kind"]) for n in r.json()["created"]}
    assert {("R1", "start"), ("R4", "start")} <= kinds
