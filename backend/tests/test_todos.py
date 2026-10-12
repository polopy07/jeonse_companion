"""할 일 9종 생성을 기한 정답표(docs/validation/deadline_scenarios.yaml)와 대조 (AC-005, NFR-003)."""
import copy
from datetime import date

import pytest
import yaml

from app.config import REPO_ROOT
from app.engine.alert import alert_level
from app.engine.todos import add_months, build_todos

SCENARIOS = yaml.safe_load((REPO_ROOT / "docs" / "validation" / "deadline_scenarios.yaml").read_text(encoding="utf-8"))
CONTRACT_FIELDS = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "brokered",
                   "guarantor", "loan", "renewal_right_used", "loan_execution_date")


def _values(inp: dict) -> dict:
    values = {k: inp.get(k) for k in CONTRACT_FIELDS}
    for k in ("contract_date", "balance_date", "end_date", "loan_execution_date"):
        if values[k] is not None:
            values[k] = date.fromisoformat(values[k])
    return values


def _build(rules, s: dict, inp: dict | None = None, done_dates: dict | None = None):
    return build_todos(
        _values(inp or s["input"]),
        linkages=s.get("linkage", []),
        special_terms=s.get("special_terms", {}),
        alert_level=s.get("alert_level"),
        rules=rules,
        done_dates=done_dates,
    )


def _actual(todos) -> dict:
    out = {}
    for t in todos:
        if t.remind_date is not None:
            out[t.rule_id] = {"remind": t.remind_date.isoformat()}
        else:
            out[t.rule_id] = {"start": t.start_date and t.start_date.isoformat(),
                              "due": t.due_date and t.due_date.isoformat()}
    return out


def _assert_matches(todos, expected: dict):
    actual = _actual(todos)
    for todo_id, want in expected.items():
        if want == "not_created":
            assert todo_id not in actual, f"{todo_id}는 만들지 않아야 함"
        else:
            assert actual.get(todo_id) == want, f"{todo_id}: {actual.get(todo_id)} != {want}"
    # 정답표에 없는 할 일이 더 생기지 않았는지 (신고 비대상의 T1처럼 표에서 빠진 것)
    created = {k for k, v in expected.items() if v != "not_created"}
    assert set(actual) == created


BY_ID = {s["id"]: s for s in SCENARIOS["scenarios"]}


@pytest.mark.parametrize("sid", [s["id"] for s in SCENARIOS["scenarios"] if "input" in s])
def test_scenario_dates_and_order(rules, sid):
    s = BY_ID[sid]
    todos = _build(rules, s)
    _assert_matches(todos, s["expected"])
    assert [t.rule_id for t in todos] == s["expected_order"]
    assert [t.sort_order for t in todos] == list(range(1, len(todos) + 1))


@pytest.mark.parametrize("sid", ["S10", "S10-b"])
def test_next_contract_after_switch(rules, sid):
    # 갈아타기 다음 집도 같은 엔진으로 할 일을 만든다 (자금 틈·전입 순서는 3주차)
    s = BY_ID[sid]
    todos = _build(rules, s, inp=s["next_contract"])
    _assert_matches(todos, s["expected"]["next_contract_todos"])


@pytest.mark.parametrize("r", SCENARIOS["recalculation"], ids=lambda r: r["id"])
def test_recalculation(rules, r):
    # 바뀐 입력으로 다시 만들면 정답표의 재계산 결과와 같아야 한다 (저장된 할 일을 고치는 일은 3주차)
    base = BY_ID[r["base"]]
    change = dict(r["change"])
    done_dates = {}
    if "T4_done_date" in change:
        done_dates["T4"] = date.fromisoformat(change.pop("T4_done_date"))
    todos = _build(rules, base, inp={**base["input"], **change}, done_dates=done_dates)
    actual = _actual(todos)
    for todo_id, want in r["expected"].items():
        assert actual[todo_id] == want, f"{todo_id}: {actual[todo_id]} != {want}"
    before = _actual(_build(rules, base))
    for todo_id in r["unchanged"]:
        assert actual[todo_id] == before[todo_id], f"{todo_id}는 바뀌지 않아야 함"


def test_prerequisites(rules):
    s1 = {t.rule_id: t for t in _build(rules, BY_ID["S1"])}
    assert s1["T2"].prerequisites == ["T1"]
    s2 = {t.rule_id: t for t in _build(rules, BY_ID["S2"])}
    assert s2["T2"].prerequisites == []          # 신고 비대상이라 T1 없음 (AC-018)
    s9 = {t.rule_id: t for t in _build(rules, BY_ID["S9"])}
    assert s9["T2"].prerequisites == []          # 비율 90% 이상이면 T1을 기다리지 않음 (Q3)


def test_moved_to_top_and_pinned(rules):
    s7 = _build(rules, BY_ID["S7"])
    assert [t.rule_id for t in s7 if t.moved_to_top] == ["T4"]    # AC-016
    s9 = _build(rules, BY_ID["S9"])
    assert [t.rule_id for t in s9 if t.moved_to_top] == ["T2", "T5"]
    assert [t.rule_id for t in s9 if t.pinned] == ["T5", "T6", "T7", "T8", "T9"]


def test_details_and_checks(rules):
    s4 = {t.rule_id: t for t in _build(rules, BY_ID["S4"])}
    assert "직거래" in s4["T2"].detail
    s1 = {t.rule_id: t for t in _build(rules, BY_ID["S1"])}
    assert s1["T2"].detail == "전세보증 사전심사 신청"
    assert s1["T3"].required_checks == []
    s5 = {t.rule_id: t for t in _build(rules, BY_ID["S5"])}
    assert "갱신요구권" in s5["T7"].detail
    s6 = {t.rule_id: t for t in _build(rules, BY_ID["S6"])}
    assert s6["T3"].required_checks == ["근저당 금액 변동 비교 (필수)"]


def test_add_months_clamps_to_month_end():
    assert add_months(date(2028, 8, 31), -6) == date(2028, 2, 29)   # 윤년
    assert add_months(date(2027, 8, 31), -6) == date(2027, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)


def test_alert_level(rules):
    alert = rules["alert"]
    assert alert_level({"deposit_ratio": 0.79}, alert) is None
    assert alert_level({"deposit_ratio": 0.8}, alert) == "caution"
    assert alert_level({"deposit_ratio": 0.92}, alert) == "warning"
    assert alert_level({"deposit_ratio": 1.0}, alert) == "danger"
    assert alert_level({"deposit_ratio": None}, alert) is None


def test_moved_to_top_comes_before_pinned(rules):
    # Q4: 맨 위 규칙 → 고정 → 기한순. 지금 규칙은 맨 위로 가는 할 일이 모두 고정 항목보다 번호가 앞이라
    # 순서만 봐서는 단계 구분이 드러나지 않으므로, 고정 항목(T9)에 맨 위 규칙을 붙여 확인한다.
    tweaked = copy.deepcopy(rules)
    t9 = next(t for t in tweaked["todos"]["todos"] if t["id"] == "T9")
    t9["move_to_top_when"] = [{"special_term": "S-NO-MORTGAGE", "result": "rejected"}]
    todos = _build(tweaked, BY_ID["S7"])
    assert [t.rule_id for t in todos] == ["T4", "T9", "T5", "T6", "T7", "T8", "T1", "T2", "T3"]
