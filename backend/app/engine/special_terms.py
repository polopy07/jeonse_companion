"""판정 결과에 맞는 특약 예시 (special_terms.yaml, linkage.yaml, 명세서 부속표 D·E, FR-039)와
계약에 기록한 특약 결과(넣음/거절당함)의 분기 (부속표 E, FR-050).

특약은 "추천"이 아니라 "이런 결과일 때 공공 자료가 안내하는 특약 예시"로 보여 준다.
MVP는 MVP 연동 규칙(근저당, 비율 90% 이상, 신탁)에 연결된 MVP 특약만 보여 준다 (FR-022, FR-050).
"""
from dataclasses import dataclass, field


@dataclass
class TodoRef:
    id: str
    title: str


@dataclass
class TermOutcome:
    """특약을 넣었을 때 / 거절당했을 때 생기는 것 (on_inserted / on_rejected)."""

    warnings: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    moves_to_top: list[TodoRef] = field(default_factory=list)
    adds_todos: list[TodoRef] = field(default_factory=list)
    link_counsel: bool = False


@dataclass
class LinkedRule:
    id: str
    label: str


@dataclass
class SpecialTermExample:
    id: str
    label: str
    text: str
    source: str
    linked: list[LinkedRule]
    if_inserted: TermOutcome
    if_rejected: TermOutcome


@dataclass
class TermEffect:
    """계약에 기록한 특약 1개의 결과와 그 분기 (부속표 E). 할 일 순서는 todos.yaml move_to_top_when이 바꾼다."""

    term_id: str
    label: str
    result: str               # inserted / rejected
    outcome: TermOutcome


@dataclass
class ContractDayGuide:
    terms: list[SpecialTermExample]
    warnings: list[str]       # 연동 규칙이 계약 당일에 보여 주는 경고 (linkage.yaml contract_day)
    checks: list[str]         # 연동 규칙이 계약 당일에 요구하는 확인 (예: 신탁사 동의서 확인)


def _outcome(actions: list[dict], todo_titles: dict[str, str]) -> TermOutcome:
    out = TermOutcome()
    for a in actions:
        match a["action"]:
            case "show_warning":
                out.warnings.append(a["text"])
            case "require_document":
                out.documents.append(a["document"])
            case "move_to_top":
                out.moves_to_top.append(TodoRef(a["todo"], todo_titles[a["todo"]]))
            case "add_todo":
                out.adds_todos.append(TodoRef(a["todo"], todo_titles[a["todo"]]))
            case "link_counsel":
                out.link_counsel = True
            case _:
                raise ValueError(f"special_terms.yaml: 알 수 없는 동작 {a['action']}")
    return out


def contract_day_guide(linkages: list[str], rules: dict) -> ContractDayGuide:
    """판정에 걸린 연동 규칙(linkages)으로 계약 당일 특약 예시와 경고를 만든다."""
    linkage_by_id = {r["id"]: r for r in rules["linkage"]["rules"]}
    # 규칙 파일에서 없어진 연동 규칙 id(옛 판정)는 건너뛴다
    active = [linkage_by_id[i] for i in linkages if i in linkage_by_id and linkage_by_id[i].get("mvp")]
    active_ids = [r["id"] for r in active]
    todo_titles = _todo_titles(rules)

    terms = []
    for term in rules["special_terms"]["terms"]:
        linked = [r for r in active if r["id"] in term["shown_when"]]
        if not term.get("mvp") or not linked:
            continue
        terms.append(SpecialTermExample(
            id=term["id"],
            label=term["label"],
            text=term["text"],
            source=term["source"],
            linked=[LinkedRule(r["id"], r["label"]) for r in linked],
            if_inserted=_outcome(term.get("on_inserted", []), todo_titles),
            if_rejected=_outcome(term.get("on_rejected", []), todo_titles),
        ))

    day_actions = [a for lid in active_ids for a in linkage_by_id[lid].get("contract_day", [])]
    return ContractDayGuide(
        terms=terms,
        warnings=[a["text"] for a in day_actions if a["action"] == "show_warning"],
        checks=[a["check"] for a in day_actions if a["action"] == "require_check"],
    )


def _todo_titles(rules: dict) -> dict[str, str]:
    return {t["id"]: t["title"] for t in rules["todos"]["todos"] + rules["todos"].get("extra_todos", [])}


def term_effects(results: dict[str, str], rules: dict) -> list[TermEffect]:
    """계약의 특약 결과 {"S-NO-MORTGAGE": "rejected", ...}로 분기를 만든다 (special_terms.yaml 순서).

    넣음: 기록함에 남길 서류(특약이 보이는 계약서 사진)·안내. 거절당함: 위험 안내·맨 위로 올라가는 할 일·상담 창구.
    규칙 파일에서 없어진 특약은 건너뛴다.
    """
    titles = _todo_titles(rules)
    effects = []
    for term in rules["special_terms"]["terms"]:
        result = results.get(term["id"])
        if result not in ("inserted", "rejected"):
            continue
        actions = term.get("on_inserted" if result == "inserted" else "on_rejected", [])
        effects.append(TermEffect(term["id"], term["label"], result, _outcome(actions, titles)))
    return effects
