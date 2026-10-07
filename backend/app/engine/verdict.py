"""판정 엔진 (verdict.yaml, 명세서 부속표 B, FR-009, FR-010).

단계를 위에서부터 차례로 보고 규칙이 하나라도 걸린 첫 단계로 판정한다.
걸린 항목은 그 단계와 아래 단계의 것을 모두 돌려준다 (화면에 모두 보여 줌).
"""
from dataclasses import dataclass, field

from app.rules.conditions import evaluate

NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class MatchedRule:
    id: str
    label: str
    level: str
    linkage: str | None = None


@dataclass
class VerdictResult:
    level: str
    label: str
    next_step: str
    block_payment: bool
    matched: list[MatchedRule] = field(default_factory=list)
    linkages: list[str] = field(default_factory=list)
    unchecked: list[dict] = field(default_factory=list)
    disclaimer: str = ""
    rules_version: str = ""


def judge(values: dict, verdict_rules: dict) -> VerdictResult:
    """values: fields.yaml 이름을 키로 하는 입력·계산 값."""
    levels = verdict_rules["levels"]

    hits_by_level = {
        lv["id"]: [r for r in lv.get("rules", []) if evaluate(r["when"], values)]
        for lv in levels
    }
    chosen_index = next(
        (i for i, lv in enumerate(levels) if hits_by_level[lv["id"]]),
        next(i for i, lv in enumerate(levels) if lv.get("default")),
    )
    chosen = levels[chosen_index]

    # 대상 아님(다가구·단독)은 점검 대상이 아니므로 다른 단계의 항목을 보여 주지 않는다.
    shown_levels = [chosen] if chosen["id"] == NOT_APPLICABLE else levels[chosen_index:]
    matched = [
        MatchedRule(id=r["id"], label=r["label"], level=lv["id"], linkage=r.get("linkage"))
        for lv in shown_levels
        for r in hits_by_level[lv["id"]]
    ]
    linkages = list(dict.fromkeys(m.linkage for m in matched if m.linkage))

    unchecked = [
        {"id": u["id"], "label": u["label"], "linkage": u.get("linkage")}
        for u in verdict_rules.get("unchecked_items", [])
        if "applies_when" not in u or evaluate(u["applies_when"], values)
    ]

    return VerdictResult(
        level=chosen["id"],
        label=chosen["label"],
        next_step=chosen.get("next_step", ""),
        block_payment=bool(chosen.get("block_payment", False)),
        matched=matched,
        linkages=linkages,
        unchecked=unchecked,
        disclaimer=verdict_rules.get("display", {}).get("disclaimer", ""),
        rules_version=str(verdict_rules["version"]),
    )
