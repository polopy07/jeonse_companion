from app.rules.conditions import evaluate


def test_simple_ops():
    assert evaluate({"field": "deposit_ratio", "op": ">=", "value": 0.9}, {"deposit_ratio": 0.9})
    assert not evaluate({"field": "deposit_ratio", "op": ">=", "value": 0.9}, {"deposit_ratio": 0.89})
    assert evaluate({"field": "housing_type", "op": "in", "value": ["detached"]}, {"housing_type": "detached"})
    assert evaluate({"field": "registry.trust", "op": "==", "value": False}, {"registry.trust": False})


def test_value_field():
    cond = {"field": "nearby_jeonse_median", "op": "<", "value_field": "deposit"}
    assert evaluate(cond, {"nearby_jeonse_median": 1, "deposit": 2})
    assert not evaluate(cond, {"nearby_jeonse_median": 1})


def test_all_any():
    a = {"field": "x", "op": "==", "value": 1}
    b = {"field": "y", "op": "==", "value": 2}
    assert evaluate({"all": [a, b]}, {"x": 1, "y": 2})
    assert not evaluate({"all": [a, b]}, {"x": 1, "y": 3})
    assert evaluate({"any": [a, b]}, {"x": 0, "y": 2})


def test_missing_value_is_false():
    # 모르는 값은 "해당 없음"이 아니라 "아직 판단 못 함"이므로 조건을 만족하지 않는다
    assert not evaluate({"field": "registry.seizure", "op": "==", "value": True}, {})
    assert not evaluate({"field": "registry.seizure", "op": "!=", "value": True}, {})
