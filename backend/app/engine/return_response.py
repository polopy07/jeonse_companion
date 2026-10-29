"""반환 대응 단계와 청구 서류 대조 (FR-024, FR-034, FR-035, UC-009, todos.yaml return_response).

9번(반환 확인)에서 "못 받음"을 고르면 단계(R1~R4)를 할 일로 붙인다 (build_todos의 not_returned_date).
할 일이라 완료·나중에 올리기·증빙 사진은 PATCH·POST /api/todos/{id}를 그대로 쓴다.
서류 대조는 단계마다 적은 서류(할 일 id)의 증빙을 기록함에 올렸는지로 본다.
"""
from dataclasses import dataclass, field


@dataclass
class ReturnStep:
    id: str
    title: str
    detail: str
    link: dict | None
    evidence: str | None
    documents: list[str]


@dataclass
class DocumentCheck:
    rule_id: str               # 서류를 올리는 할 일 (T1~T9, R1~R4)
    name: str                  # 그 할 일의 증빙 이름
    uploaded: bool
    needed_by: list[str] = field(default_factory=list)   # 이 서류가 필요한 단계


def confirm_todo_id(rules: dict) -> str:
    """"보증금을 돌려받았나요?"를 묻는 할 일 (todos.yaml on_answer.not_returned, 지금은 T9)."""
    return next(t["id"] for t in rules["todos"]["todos"]
                if (t.get("on_answer") or {}).get("not_returned") == "switch_to_return_response")


def return_steps(guarantor: str, rules: dict) -> list[ReturnStep]:
    """보증기관에 맞춘 반환 대응 단계 (by_guarantor가 있으면 그 값으로 제목·안내·창구·증빙을 바꾼다)."""
    steps = []
    for step in rules["todos"]["return_response"]["steps"]:
        s = {**step, **step.get("by_guarantor", {}).get(guarantor, {})}
        steps.append(ReturnStep(id=step["id"], title=s["title"], detail=s["detail"], link=s.get("link"),
                                evidence=s.get("evidence"), documents=list(s.get("documents", []))))
    return steps


def check_documents(steps: list[ReturnStep], names: dict[str, str | None], uploaded: set[str]) -> list[DocumentCheck]:
    """단계별 서류를 기록함과 대조한다 (FR-035). 처음 나온 순서대로, 서류마다 필요한 단계를 모은다.

    names: 이 계약에 있는 할 일과 반환 대응 단계의 증빙 이름 {rule_id: 증빙}. 여기에 없거나 증빙이 없는 서류
           (신고 비대상의 T1, 보증 미가입의 T5)는 대조하지 않는다.
    uploaded: 기록함에 증빙을 올린 할 일 rule_id
    """
    docs: dict[str, DocumentCheck] = {}
    for step in steps:
        for rule_id in step.documents:
            if not names.get(rule_id):
                continue
            doc = docs.setdefault(rule_id, DocumentCheck(rule_id, names[rule_id], rule_id in uploaded))
            doc.needed_by.append(step.id)
    return list(docs.values())
