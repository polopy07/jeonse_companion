"""규칙 파일의 조건(when) 계산.

    {field: deposit_ratio, op: ">=", value: 0.9}
    {field: nearby_jeonse_median, op: "<", value_field: deposit}
    {all: [...]} / {any: [...]}

값이 없는(None) 필드는 아직 모르는 값이므로 조건을 만족하지 않는 것으로 본다.
"""
import operator

OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "in": lambda actual, expected: actual in expected,
}


def evaluate(cond: dict, values: dict) -> bool:
    if "all" in cond:
        return all(evaluate(c, values) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, values) for c in cond["any"])

    actual = values.get(cond["field"])
    expected = values.get(cond["value_field"]) if "value_field" in cond else cond["value"]
    if actual is None or expected is None:
        return False
    return OPS[cond["op"]](actual, expected)
