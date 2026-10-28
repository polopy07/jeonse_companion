"""캘린더 구독 (POST·DELETE /api/contracts/{id}/calendar-link, GET /api/calendar/{token}.ics, FR-042, #47)."""
from datetime import date, datetime, timezone

from app.engine.calendar import CalendarTodo, alarm_triggers, build_ics, fold
from tests.test_contract_patch import _contract
from tests.test_todo_complete import _set


def _h(c: dict) -> dict:
    return {"X-Contract-Token": c["access_token"]}


def _link(client, c: dict):
    return client.post(f"/api/contracts/{c['id']}/calendar-link", headers=_h(c))


def _feed_path(url: str) -> str:
    return url.split("://", 1)[1].split("/", 1)[1]


def _events(text: str) -> dict:
    """UID → (DTSTART, SUMMARY). 접힌 줄은 펴서 본다."""
    out, cur = {}, {}
    for line in text.replace("\r\n ", "").split("\r\n"):
        key, _, value = line.partition(":")
        if line == "BEGIN:VEVENT":
            cur = {}
        elif key in ("UID", "DTSTART;VALUE=DATE", "SUMMARY"):
            cur[key] = value
        elif line == "END:VEVENT":
            out[cur["UID"]] = (cur["DTSTART;VALUE=DATE"], cur["SUMMARY"])
    return out


def test_build_ics_matches_app_rules():
    # 앱 내보내기(frontend/src/lib/ics.ts)와 같은 UID·날짜·알림
    todos = [CalendarTodo("T5", "반환보증 가입", "HUG; 기준", date(2026, 12, 2), date(2027, 6, 1), None, "todo"),
             CalendarTodo("T6", "반환보증 가입 마감 전 재알림", None, None, None, date(2027, 5, 2), "todo"),
             CalendarTodo("T4", "전입신고", None, date(2026, 12, 1), date(2026, 12, 1), None, "done"),
             CalendarTodo("T7", "통보", None, None, None, None, "todo")]
    text = build_ics(3, todos, [7, 1], now=datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    events = _events(text)
    assert events == {"jeonse-3-T5@jeonse-companion": ("20270601", "[전동기] 반환보증 가입"),
                      "jeonse-3-T6@jeonse-companion": ("20270502", "[전동기] 반환보증 가입 마감 전 재알림")}
    assert "DTEND;VALUE=DATE:20270602" in text and "TRIGGER:-P6DT15H" in text and "TRIGGER:-PT15H" in text
    assert "HUG\; 기준" in text.replace("\r\n ", "")          # 이스케이프
    assert "2026-12-02부터 할 수 있어요." in text.replace("\r\n ", "")
    assert alarm_triggers([7, 1]) == ["-P6DT15H", "-PT15H"]
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert all(len(p.encode()) <= 75 for p in fold("가" * 60).split("\r\n "))


def test_subscribe_feed_and_follow_changes(client):
    c = _contract(client)
    r = _link(client, c)
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["url"].startswith("http://testserver/api/calendar/") and link["url"].endswith(".ics")
    assert link["webcal_url"] == "webcal://" + link["url"].split("://", 1)[1]

    feed = client.get("/" + _feed_path(link["url"]))     # 캘린더 앱은 헤더 없이 부른다
    assert feed.status_code == 200
    assert feed.headers["content-type"].startswith("text/calendar")
    events = _events(feed.text)
    open_todos = [t for t in c["todos"] if t["status"] == "todo" and (t["due_date"] or t["remind_date"])]
    assert set(events) == {f"jeonse-{c['id']}-{t['rule_id']}@jeonse-companion" for t in open_todos}

    # 끝낸 할 일은 빠지고, 잔금일을 바꾸면 구독 파일의 날짜도 바뀐다 (다시 내보낼 필요 없음)
    _set(client, c, "T4", {"status": "skipped", "done_date": "2026-12-03"})
    assert f"jeonse-{c['id']}-T4@jeonse-companion" not in _events(client.get("/" + _feed_path(link["url"])).text)
    t3_uid = f"jeonse-{c['id']}-T3@jeonse-companion"
    before = _events(client.get("/" + _feed_path(link["url"])).text)[t3_uid][0]
    client.patch(f"/api/contracts/{c['id']}", json={"balance_date": "2026-12-10"}, headers=_h(c))
    after = _events(client.get("/" + _feed_path(link["url"])).text)[t3_uid][0]
    assert (before, after) == ("20261201", "20261210")


def test_feed_token_is_view_only_and_revocable(client):
    c = _contract(client)
    first = _link(client, c).json()
    token = _feed_path(first["url"]).rsplit("/", 1)[1].removesuffix(".ics")
    # 보기 전용: 계약 API에는 쓸 수 없다
    assert client.get(f"/api/contracts/{c['id']}", headers={"X-Contract-Token": token}).status_code == 404

    # 다시 만들면 앞 주소는 끊긴다
    second = _link(client, c).json()
    assert client.get("/" + _feed_path(first["url"])).status_code == 404
    assert client.get("/" + _feed_path(second["url"])).status_code == 200
    assert client.get("/api/calendar/nope.ics").status_code == 404

    assert client.delete(f"/api/contracts/{c['id']}/calendar-link", headers=_h(c)).status_code == 204
    assert client.get("/" + _feed_path(second["url"])).status_code == 404
    assert client.delete(f"/api/contracts/{c['id']}/calendar-link", headers=_h(c)).status_code == 404
    assert client.post(f"/api/contracts/{c['id']}/calendar-link",
                       headers={"X-Contract-Token": "wrong"}).status_code == 404


def test_cancelled_contract_feed_is_empty(client):
    c = _contract(client)
    link = _link(client, c).json()
    assert client.post(f"/api/contracts/{c['id']}/cancel", headers=_h(c)).status_code == 200
    feed = client.get("/" + _feed_path(link["url"]))
    assert feed.status_code == 200 and "BEGIN:VEVENT" not in feed.text   # 구독한 일정이 지워지게
    r = _link(client, c)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_CANCELLED"


def test_public_base_url(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://jeonse.example.ac.kr/")
    link = _link(client, _contract(client)).json()
    assert link["url"].startswith("https://jeonse.example.ac.kr/api/calendar/")
    assert link["webcal_url"].startswith("webcal://jeonse.example.ac.kr/api/calendar/")
