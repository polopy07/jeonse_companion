"""할 일 9종 생성 (todos.yaml, guarantors.yaml, linkage.yaml, 명세서 부속표 A, FR-015, FR-017~FR-020).

날짜 계산은 docs/validation/기한계산_정답표.md의 계산 약속을 따른다.
- C1 "N일"은 기준일 ± N일
- C2 월 이동은 같은 날짜로 옮기고, 그 달에 그 날이 없으면 말일
- C3 월과 일이 같이 있으면 월 먼저
- C4 주말·공휴일이어도 옮기지 않음
- C5 반환보증 가입 마감은 guarantors.yaml의 기준 (HUG: 잔금일·전입신고일 중 늦은 날 + 계약 기간 절반)
- C6 5번 시작일 = 대출 실행일 (전입신고가 더 늦거나 대출이 없으면 실제 전입신고 완료일 + 1일)
- C7 목록 순서는 todos.yaml의 order (맨 위 규칙 → 고정 → 기한순, 같은 단계는 번호순)
그 밖에: 아직 끝내지 않은 할 일을 기준일로 쓸 때는 그 할 일의 기한일에 끝낸 것으로 본다.
연동 규칙은 MVP 규칙만 적용한다 (계약 당일 특약 예시와 같은 범위).

날짜·조건·특약이 바뀌면 PATCH /api/contracts/{id}가 이 함수로 다시 계산한다 (끝낸 할 일의 완료일은 done_dates로).
9번(반환 확인)에서 "못 받음"을 골랐으면 반환 대응 단계(R1~R4, todos.yaml return_response)를 맨 위에 붙인다.
아직 하지 않는 것: 특약 반영 분기의 경고·서류(FR-050, 3주차), 추가 할 일 X-*(MVP 밖이거나 계약 중 경보 때 붙는 것).
"""
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.engine.return_response import confirm_todo_id, return_steps
from app.rules.conditions import evaluate


@dataclass
class PlannedTodo:
    rule_id: str
    title: str
    detail: str | None
    start_date: date | None
    due_date: date | None
    remind_date: date | None          # 재알림(T6, T8)은 기한 대신 알림일만 있다
    prerequisites: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    evidence: str | None = None
    pinned: bool = False
    moved_to_top: bool = False
    sort_order: int = 0


def add_months(d: date, months: int) -> date:
    """C2: 같은 날짜로 달을 옮기고, 그 달에 그 날이 없으면 말일."""
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def shift(base: date | None, spec: dict) -> date | None:
    """C3: 월을 먼저 옮기고 일을 더한다."""
    if base is None:
        return None
    return add_months(base, spec.get("offset_months", 0)) + timedelta(days=spec.get("offset_days", 0))


def report_required(values: dict, todo_rules: dict) -> bool:
    """임대차 신고 대상인지 (FR-015). 비대상 기준에 걸리지 않으면 대상."""
    return not evaluate(todo_rules["report_rule"]["exempt_when"], values)


class _Builder:
    def __init__(self, values: dict, linkages: list[str], special_terms: dict[str, str],
                 alert_level: str | None, rules: dict, done_dates: dict[str, date], not_returned_date: date | None):
        self.values = values
        self.rules = rules
        self.not_returned_date = not_returned_date
        # MVP 연동 규칙만 적용한다. MVP 밖 규칙(위반건축물 등)은 계약 당일 화면에 안내하지 않으므로
        # 할 일도 바꾸지 않는다
        mvp = {rule["id"] for rule in rules["linkage"]["rules"] if rule.get("mvp")}
        self.linkages = [lid for lid in linkages if lid in mvp]
        self.special_terms = special_terms
        self.alert_level = alert_level
        self.done_dates = done_dates
        self.todo_rules = rules["todos"]
        self.guarantee = rules["guarantors"]["guarantors"][values["guarantor"]]["return_guarantee_deadline"]
        self.alert_levels = [lv["id"] for lv in rules["alert"]["levels"]]
        self.after_contract = [
            action
            for rule in rules["linkage"]["rules"] if rule["id"] in self.linkages
            for action in rule.get("after_contract", [])
        ]
        self.plans: dict[str, PlannedTodo] = {}

    # 날짜 -----------------------------------------------------------------

    def anchor(self, name: str) -> date | None:
        if "." in name:   # "T4.done_date": 그 할 일을 끝낸 날. 아직이면 기한일에 끝낸 것으로 본다
            todo_id, attr = name.split(".")
            if attr != "done_date":
                raise ValueError(f"todos.yaml: 알 수 없는 기준일 {name}")
            return self.done_dates.get(todo_id) or self.plans[todo_id].due_date
        if name not in self.values:
            raise ValueError(f"todos.yaml: 알 수 없는 기준일 {name}")
        return self.values[name]

    def guarantee_deadline(self) -> date | None:
        """반환보증 가입 마감 (C5). 기관 기준을 확인하기 전(HF·SGI)이면 None."""
        anchor = self.guarantee["anchor"]
        if anchor is None:
            return None
        if anchor == "contract_period_half":
            balance, end = self.values["balance_date"], self.values["end_date"]
            moved_in = self.anchor("T4.done_date")
            return max(balance, moved_in) + timedelta(days=(end - balance).days // 2)
        raise ValueError(f"guarantors.yaml: 알 수 없는 마감 기준 {anchor}")

    def resolve(self, spec: dict | None) -> date | None:
        if spec is None:
            return None
        if "if_no_loan" in spec and not self.values["loan"]:
            spec = spec["if_no_loan"]
        if spec.get("from") == "guarantors.yaml":
            return shift(self.guarantee_deadline(), spec)
        base = self.anchor(spec["anchor"])
        later = spec.get("if_later")
        if later and base is None:
            # 기준일을 모르면(대출은 있는데 실행일을 비워 둠) 늦은 쪽 기준으로 대신 정한다 (T5: 전입신고 다음 날)
            return shift(self.anchor(later["anchor"]), later)
        if later:
            # 기준일보다 다른 날이 늦으면 그 날 기준 (T5: 전입신고가 대출 실행보다 늦으면 전입신고 다음 날, Q9)
            other = self.anchor(later["anchor"])
            if other is not None and other > base:
                return shift(other, later)
        return shift(base, spec)

    # 조건 -----------------------------------------------------------------

    def applies(self, rule: dict) -> bool:
        cond = rule.get("when_applies")
        if cond is None:
            return True
        if "todo_not_done" in cond:
            target = cond["todo_not_done"]
            return target in self.plans and target not in self.done_dates
        return evaluate(cond, self.values)

    def needs_guarantee(self, rule: dict) -> bool:
        return any((rule.get(k) or {}).get("from") == "guarantors.yaml" for k in ("due", "remind"))

    def moved_to_top(self, rule: dict) -> bool:
        for cond in rule.get("move_to_top_when", []):
            if "special_term" in cond and self.special_terms.get(cond["special_term"]) == cond["result"]:
                return True
            if "alert_level_gte" in cond and self.alert_level is not None:
                if self.alert_levels.index(self.alert_level) >= self.alert_levels.index(cond["alert_level_gte"]):
                    return True
        return False

    def detail(self, rule: dict) -> str | None:
        text = rule.get("detail")
        by_guarantor = rule.get("detail_by_guarantor")
        if by_guarantor:
            text = by_guarantor[self.values["guarantor"]]
        for variant in rule.get("variants", []):
            if evaluate(variant["when"], self.values):
                text = variant["detail"]
        return text

    # 생성 -----------------------------------------------------------------

    def plan(self, rule: dict) -> PlannedTodo | None:
        if not self.applies(rule):
            return None
        # 보증 미가입이면 반환보증 할 일(T5·T6)을 만들지 않는다 (정답표 S2)
        if self.needs_guarantee(rule) and self.guarantee is None:
            return None

        todo_id = rule["id"]
        start, due, remind = self.resolve(rule.get("start")), self.resolve(rule.get("due")), self.resolve(rule.get("remind"))
        if "remind" in rule and remind is None:
            return None   # 알림일을 정할 수 없는 재알림은 만들지 않는다 (HF·SGI 마감 미정, 정답표 S8)

        prerequisites = [p for p in rule.get("prerequisites", []) if p in self.plans]
        skip = rule.get("prerequisites_skip_when", [])
        if any(c.get("linkage") in self.linkages for c in skip):
            prerequisites = []

        required_checks = []
        for action in self.after_contract:
            if action.get("todo") != todo_id:
                continue
            if action["action"] == "set_due":   # 비율 90% 이상: 기한을 계약일 당일로 (정답표 Q3)
                due = self.anchor(action["anchor"])
                start = min(start, due) if start else due
            elif action["action"] == "require_check":
                required_checks.append(action["check"])

        return PlannedTodo(
            rule_id=todo_id,
            title=rule["title"],
            detail=self.detail(rule),
            start_date=start,
            due_date=due,
            remind_date=remind,
            prerequisites=prerequisites,
            required_checks=required_checks,
            evidence=rule.get("evidence"),
            pinned=todo_id in self.todo_rules["pinned"],
            moved_to_top=self.moved_to_top(rule),
        )

    def build(self) -> list[PlannedTodo]:
        for rule in self.todo_rules["todos"]:
            planned = self.plan(rule)
            if planned is not None:
                self.plans[rule["id"]] = planned
        # 반환 대응 중 늦게라도 돌려받아 9번을 끝내면 단계는 계획에서 뺀다 (끝낸 단계는 기록으로만 남는다, #124 리뷰)
        if self.not_returned_date is not None and confirm_todo_id(self.rules) not in self.done_dates:
            # 반환 대응 (FR-024, FR-034): 시작일은 "못 받음"을 고른 날, 기한은 없음. 가장 급한 일이라 맨 위로
            for step in return_steps(self.values["guarantor"], self.rules):
                self.plans[step.id] = PlannedTodo(
                    rule_id=step.id, title=step.title, detail=step.detail, start_date=self.not_returned_date,
                    due_date=None, remind_date=None, evidence=step.evidence, moved_to_top=True)
        return self.ordered()

    def ordered(self) -> list[PlannedTodo]:
        """C7: todos.yaml의 order 단계 순서로, 같은 단계 안에서는 번호순 (기한 단계는 기한 빠른 순 → 번호순)."""
        number = {r["id"]: i for i, r in enumerate(self.todo_rules["todos"])}
        steps = self.todo_rules["return_response"]["steps"]   # 반환 대응 단계는 맨 위 단계 안에서도 먼저
        number.update({s["id"]: i - len(steps) for i, s in enumerate(steps)})
        stages = self.todo_rules["order"]

        def stage(t: PlannedTodo) -> int:
            if t.moved_to_top:
                return stages.index("move_to_top")
            if t.pinned:
                return stages.index("pinned")
            return stages.index("due_date")

        def key(t: PlannedTodo):
            s = stage(t)
            when = (t.due_date or t.remind_date or date.max) if stages[s] == "due_date" else date.min
            return (s, when, number[t.rule_id])

        result = sorted(self.plans.values(), key=key)
        for i, t in enumerate(result, start=1):
            t.sort_order = i
        return result


def build_todos(values: dict, linkages: list[str], special_terms: dict[str, str], alert_level: str | None,
                rules: dict, done_dates: dict[str, date] | None = None,
                not_returned_date: date | None = None) -> list[PlannedTodo]:
    """계약 조건으로 할 일 목록을 만든다.

    values: fields.yaml 이름의 계약 조건 (contract_date, balance_date, end_date, deposit, monthly_rent,
            loan, loan_execution_date, guarantor, brokered, renewal_right_used)
    linkages: 판정에 걸린 연동 규칙 id (linkage.yaml)
    special_terms: 특약별 넣음/거절당함 {"S-NO-MORTGAGE": "rejected"}
    alert_level: 경보 단계 (alert.yaml levels[].id), 해당 없으면 None
    done_dates: 이미 끝낸 할 일의 완료일 {"T4": date(...)} (재계산용)
    not_returned_date: 9번(반환 확인)에서 "못 받음"을 고른 날. 있으면 반환 대응 단계(R1~R4)를 붙인다
    """
    values = {**values, "report_required": report_required(values, rules["todos"])}
    return _Builder(values, linkages, special_terms, alert_level, rules, done_dates or {}, not_returned_date).build()
