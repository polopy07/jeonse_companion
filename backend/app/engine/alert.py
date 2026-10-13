"""역전세 경보 단계 (alert.yaml levels, 명세서 부속표 C, FR-036)."""
from app.rules.conditions import evaluate


def alert_level(values: dict, alert_rules: dict) -> str | None:
    """걸린 단계 중 가장 높은 단계의 id. 하나도 안 걸리면(정상) None.

    values: fields.yaml 이름 (deposit_ratio, deposit, nearby_jeonse_median). 모르는 값은 조건을 만족하지 않는다.
    """
    level = None
    for lv in alert_rules["levels"]:   # 낮은 단계부터 적혀 있다
        if evaluate(lv["when"], values):
            level = lv["id"]
    return level
