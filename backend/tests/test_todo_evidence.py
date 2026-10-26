"""증빙 사진 올리기·보기·삭제 (POST·GET·DELETE /api/todos/{id}/evidence, FR-029·030·031·033, #44·#45)."""
import pytest

from app import evidence
from tests.test_contract_patch import _contract
from tests.test_todo_complete import _set, _todo

ADMIN = "test-admin-token"
PHOTO = b"\xff\xd8\xff\xe0 fake jpeg"


@pytest.fixture(autouse=True)
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    return tmp_path / "evidence"


def _headers(c: dict, day: str = "2026-12-05") -> dict:
    return {"X-Contract-Token": c["access_token"], "X-Virtual-Today": day}


def _upload(client, c: dict, rule_id: str, data: bytes = PHOTO, name: str = "photo.jpg", day: str = "2026-12-05",
            **form):
    return client.post(f"/api/todos/{_todo(c, rule_id)['id']}/evidence", files={"file": (name, data, "image/jpeg")},
                       data=form, headers=_headers(c, day))


def test_upload_finishes_todo_and_can_be_viewed(client, evidence_tmp):
    c = _contract(client)
    r = _upload(client, c, "T4", done_date="2026-12-03")
    assert r.status_code == 200, r.text
    t4 = _todo(r.json(), "T4")
    assert (t4["status"], t4["done_date"], t4["evidence_uploaded"]) == ("done", "2026-12-03", True)
    assert _todo(r.json(), "T5")["start_date"] == "2026-12-04"   # 끝낸 날 다음 날 반환보증 시작
    assert len(list(evidence_tmp.rglob("*.jpg"))) == 1

    r = client.get(f"/api/todos/{t4['id']}/evidence", headers=_headers(c))
    assert r.status_code == 200 and r.content == PHOTO
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/todos/{t4['id']}/evidence", headers={"X-Contract-Token": "wrong"}).status_code == 404


def test_upload_after_skip_fills_record_and_keeps_date(client, evidence_tmp):
    # 나중에 올리기 한 할 일에 나중에 올리면 완료로 바뀌고 끝낸 날은 그대로
    c = _contract(client)
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-02"})
    r = _upload(client, c, "T4", day="2026-12-20")
    t4 = _todo(r.json(), "T4")
    assert (t4["status"], t4["done_date"]) == ("done", "2026-12-02")

    # 다시 올리면 앞 사진을 바꾼다 (파일은 하나만 남음)
    r = _upload(client, c, "T4", data=b"second", name="scan.pdf", day="2026-12-20")
    assert r.status_code == 200
    files = list(evidence_tmp.rglob("*.*"))
    assert len(files) == 1 and files[0].suffix == ".pdf" and files[0].read_bytes() == b"second"
    r = client.get(f"/api/todos/{t4['id']}/evidence", headers=_headers(c))
    assert r.headers["content-type"] == "application/pdf"


def test_upload_follows_finish_rules(client):
    c = _contract(client)
    r = _upload(client, c, "T3", day="2026-11-20")   # 잔금일 전
    assert r.status_code == 409 and r.json()["detail"]["code"] == "TODO_NOT_STARTED"
    r = _upload(client, c, "T4", data=b"")
    assert r.status_code == 422
    r = _upload(client, c, "T4", done_date="2026-12-09")   # 오늘(12/05)보다 뒤
    assert r.status_code == 422


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(evidence, "MAX_EVIDENCE_BYTES", 10)
    c = _contract(client)
    r = _upload(client, c, "T4", data=b"x" * 11)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_other_types_are_downloaded(client):
    c = _contract(client)
    r = _upload(client, c, "T4", data=b"<script>alert(1)</script>", name="note.html")
    t4 = _todo(r.json(), "T4")
    r = client.get(f"/api/todos/{t4['id']}/evidence", headers=_headers(c))
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")


def test_delete_keeps_done_as_skipped(client, evidence_tmp):
    # FR-033: 언제든 지울 수 있고, 완료는 그대로 두되 기록함은 빈칸(나중에 올리기)
    c = _contract(client)
    t4 = _todo(_upload(client, c, "T4").json(), "T4")
    r = client.delete(f"/api/todos/{t4['id']}/evidence", headers=_headers(c))
    assert r.status_code == 200, r.text
    after = _todo(r.json(), "T4")
    assert (after["status"], after["done_date"], after["evidence_uploaded"]) == ("skipped", t4["done_date"], False)
    assert not list(evidence_tmp.rglob("*.*"))
    assert client.delete(f"/api/todos/{t4['id']}/evidence", headers=_headers(c)).status_code == 404
    assert client.get(f"/api/todos/{t4['id']}/evidence", headers=_headers(c)).status_code == 404


def test_cancelled_contract_can_delete_but_not_upload(client):
    c = _contract(client)
    t4 = _todo(_upload(client, c, "T4").json(), "T4")
    client.post(f"/api/contracts/{c['id']}/cancel", headers=_headers(c))
    r = _upload(client, c, "T4")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_CANCELLED"
    assert client.get(f"/api/todos/{t4['id']}/evidence", headers=_headers(c)).status_code == 200
    r = client.delete(f"/api/todos/{t4['id']}/evidence", headers=_headers(c))
    assert r.status_code == 200 and _todo(r.json(), "T4")["evidence_uploaded"] is False


def test_skipped_todo_gets_evidence_reminder(client):
    # FR-030: 나중에 올리기 한 할 일은 끝낸 날 7일 뒤 증빙을 올리라고 다시 알림 (앱 안 알림만, 한 번)
    c = _contract(client)
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-01"}, day="2026-12-01")

    def run(day):
        r = client.post("/api/admin/notifications/run", json={"date": day}, headers={"X-Admin-Token": ADMIN})
        assert r.status_code == 200, r.text
        return [n for n in r.json()["created"] if n["kind"] == "evidence"]

    assert run("2026-12-07") == []
    made = run("2026-12-08")
    assert [(n["todo_rule_id"], n["channel"], n["notify_date"]) for n in made] == [("T4", "app", "2026-12-08")]
    assert "증빙" in made[0]["title"]
    assert run("2026-12-09") == []

    # 증빙을 올리면 더 알리지 않는다
    c2 = _contract(client)
    _set(client, c2, "T4", {"status": "skipped", "done_date": "2026-12-01"}, day="2026-12-01")
    _upload(client, c2, "T4", day="2026-12-03")
    assert [n for n in run("2026-12-08") if n["contract_id"] == c2["id"]] == []
