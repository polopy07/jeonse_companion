"""rules/ 폴더의 YAML 규칙 파일 검사.

- YAML 문법, 공통 머리말(version, as_of, basis)
- 조건의 field 이름이 fields.yaml에 있는지, op가 허용된 값인지
- 동작(action) 이름이 허용된 값인지
- 서로 가리키는 ID(할 일, 특약, 연동 규칙, 판정 단계)가 실제로 있는지

사용: python3 rules/check_rules.py
"""
import re
import sys
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent
FILES = ["fields", "verdict", "alert", "linkage", "special_terms", "todos", "guarantors"]
OPS = {"==", "!=", ">=", ">", "<=", "<", "in"}
ACTIONS = {
    "show_special_term", "show_warning", "require_check", "require_document", "add_todo",
    "move_to_top", "move_next", "set_due", "escalate_verdict", "link_counsel",
}
DATE_FIELDS = {"contract_date", "balance_date", "end_date", "loan_execution_date"}


def load():
    data = {}
    for name in FILES:
        with open(RULES_DIR / f"{name}.yaml", encoding="utf-8") as f:
            data[name] = yaml.safe_load(f)
    return data


def walk(node, path=""):
    """모든 dict를 (경로, dict) 형태로 돌려준다."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


# 화면에 나가는 문구가 들어 있는 키. basis·note·rule 같은 내부 설명은 법령·공공 자료를 인용할 수 있어 검사하지 않는다
DISPLAY_KEYS = {
    "label", "explanation", "guide", "text", "detail", "title", "disclaimer", "next_step", "before_contract",
    "document", "check", "complete_with", "evidence", "low_sample_label", "consult",
}
DISPLAY_PARENTS = {"detail_by_guarantor"}   # 이 키 아래의 값은 모두 화면 문구


def is_display_path(path: str) -> bool:
    keys = [k for k in re.split(r"\.|\[\d+\]", path) if k]
    return keys[-1] in DISPLAY_KEYS or (len(keys) > 1 and keys[-2] in DISPLAY_PARENTS)


def walk_text(node, path=""):
    """모든 문자열 값과 그 위치."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_text(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_text(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def main():
    errors = []
    data = load()

    for name, doc in data.items():
        for key in ("version", "as_of", "basis"):
            if key not in doc:
                errors.append(f"{name}.yaml: '{key}' 없음")

    fields = set(data["fields"]["fields"])
    todo_ids = {t["id"] for t in data["todos"]["todos"]} | {t["id"] for t in data["todos"]["extra_todos"]}
    term_ids = {t["id"] for t in data["special_terms"]["terms"]}
    linkage_ids = {r["id"] for r in data["linkage"]["rules"]}
    level_ids = {lv["id"] for lv in data["verdict"]["levels"]}

    if len(todo_ids) != len(data["todos"]["todos"]) + len(data["todos"]["extra_todos"]):
        errors.append("todos.yaml: 할 일 id 중복")

    for name, doc in data.items():
        if name == "fields":
            continue
        for path, d in walk(doc):
            where = f"{name}.yaml:{path}"
            if "field" in d and "op" in d:
                if d["field"] not in fields:
                    errors.append(f"{where}: 없는 field '{d['field']}'")
                if d["op"] not in OPS:
                    errors.append(f"{where}: 허용되지 않은 op '{d['op']}'")
                if "value_field" in d and d["value_field"] not in fields:
                    errors.append(f"{where}: 없는 value_field '{d['value_field']}'")
            if "action" in d:
                if d["action"] not in ACTIONS:
                    errors.append(f"{where}: 허용되지 않은 action '{d['action']}'")
                if "todo" in d and d["todo"] not in todo_ids:
                    errors.append(f"{where}: 없는 할 일 '{d['todo']}'")
                if d["action"] == "show_special_term" and d.get("term") not in term_ids:
                    errors.append(f"{where}: 없는 특약 '{d.get('term')}'")
                if d["action"] == "escalate_verdict" and d.get("to") not in level_ids:
                    errors.append(f"{where}: 없는 판정 단계 '{d.get('to')}'")
                if d["action"] == "set_due" and d.get("anchor") not in DATE_FIELDS:
                    errors.append(f"{where}: set_due의 anchor는 날짜 필드여야 함")
            if "special_term" in d and d["special_term"] not in term_ids:
                errors.append(f"{where}: 없는 특약 '{d['special_term']}'")
            if "linkage" in d and d["linkage"] not in linkage_ids:
                errors.append(f"{where}: 없는 연동 규칙 '{d['linkage']}'")
            if "anchor" in d and isinstance(d["anchor"], str) and "." not in d["anchor"]:
                if d["anchor"] not in DATE_FIELDS and d["anchor"] != "contract_period_half":
                    errors.append(f"{where}: 기준 날짜(anchor) '{d['anchor']}'가 날짜 필드가 아님")

    for t in data["special_terms"]["terms"]:
        for lid in t.get("shown_when", []):
            if lid not in linkage_ids:
                errors.append(f"special_terms.yaml:{t['id']}: shown_when에 없는 연동 규칙 '{lid}'")
    for tid in data["todos"]["pinned"]:
        if tid not in todo_ids:
            errors.append(f"todos.yaml: pinned에 없는 할 일 '{tid}'")
    for tid in data["todos"]["todos"]:
        for p in tid.get("prerequisites", []):
            if p not in todo_ids:
                errors.append(f"todos.yaml:{tid['id']}: 없는 선행 할 일 '{p}'")

    # 걸린 항목 설명·확인 못 한 항목 안내 (화면 문구)
    for lv in data["verdict"]["levels"]:
        for r in lv.get("rules", []):
            if not r.get("explanation"):
                errors.append(f"verdict.yaml:{r['id']}: explanation 없음")
    for u in data["verdict"].get("unchecked_items", []):
        if not u.get("guide"):
            errors.append(f"verdict.yaml:{u['id']}: guide 없음")

    # 화면에 나가는 문구에 쓰지 않는 표현 (NFR-014, verdict.yaml display.forbidden_phrases)
    forbidden = data["verdict"].get("display", {}).get("forbidden_phrases", [])
    for name, doc in data.items():
        for path, text in walk_text(doc):
            if not is_display_path(path):
                continue
            for phrase in forbidden:
                if phrase in text:
                    errors.append(f"{name}.yaml:{path}: 쓰지 않는 표현 '{phrase}'")

    # 특약 결과로 맨 위로 올리는 할 일은 두 곳에 적는다: 화면 안내(special_terms.yaml on_*)와 할 일 엔진(todos.yaml move_to_top_when)
    by_terms = {
        (t["id"], result, a["todo"])
        for t in data["special_terms"]["terms"]
        for result in ("inserted", "rejected")
        for a in t.get(f"on_{result}", []) if a["action"] == "move_to_top"
    }
    by_todos = {
        (c["special_term"], c["result"], t["id"])
        for t in data["todos"]["todos"]
        for c in t.get("move_to_top_when", []) if "special_term" in c
    }
    for term, result, todo in sorted(by_terms - by_todos):
        errors.append(f"todos.yaml:{todo}: special_terms.yaml {term} {result}의 move_to_top이 move_to_top_when에 없음")
    for term, result, todo in sorted(by_todos - by_terms):
        errors.append(f"special_terms.yaml:{term}: todos.yaml {todo}의 move_to_top_when({result})이 on_{result}에 없음")

    # 특약 거절 등으로 추가하는 할 일도 같은 식으로 맞춘다 (special_terms.yaml add_todo ↔ todos.yaml extra_todos added_by)
    adds_by_terms = {
        (t["id"], result, a["todo"])
        for t in data["special_terms"]["terms"]
        for result in ("inserted", "rejected")
        for a in t.get(f"on_{result}", []) if a["action"] == "add_todo"
    }
    adds_by_todos = {
        (src.split(".")[0], src.split(".")[1], t["id"])
        for t in data["todos"]["extra_todos"]
        for src in t.get("added_by", []) if src.split(".")[0] in term_ids
    }
    for term, result, todo in sorted(adds_by_terms - adds_by_todos):
        errors.append(f"todos.yaml:{todo}: special_terms.yaml {term} {result}의 add_todo가 added_by에 없음")
    for term, result, todo in sorted(adds_by_todos - adds_by_terms):
        errors.append(f"special_terms.yaml:{term}: todos.yaml {todo}의 added_by({result})가 on_{result}에 없음")

    mvp_linkage = [r["id"] for r in data["linkage"]["rules"] if r.get("mvp")]
    mvp_terms = [t["id"] for t in data["special_terms"]["terms"] if t.get("mvp")]

    if errors:
        print(f"규칙 검사 실패 ({len(errors)}건)")
        for e in errors:
            print(" -", e)
        return 1
    print("규칙 검사 통과")
    print(f" - 필드 {len(fields)}개, 판정 규칙 {sum(len(lv.get('rules', [])) for lv in data['verdict']['levels'])}개, "
          f"연동 규칙 {len(linkage_ids)}개(MVP {len(mvp_linkage)}개: {', '.join(mvp_linkage)}), "
          f"특약 {len(term_ids)}개(MVP {len(mvp_terms)}개: {', '.join(mvp_terms)}), 할 일 {len(todo_ids)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
