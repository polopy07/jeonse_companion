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


def level_rank(level: str | None, alert_rules: dict) -> int:
    """단계 높낮이 비교용 순서. 정상(None)은 -1, 그 위로 levels 순서 (주의 0, 경고 1, 위험 2).

    alert.yaml에서 단계 id를 바꾸거나 지워 예전 기록의 단계를 모르면 정상(-1)으로 본다 (일괄 재계산 전체가 멈추지 않게).
    """
    ids = [lv["id"] for lv in alert_rules["levels"]]
    return ids.index(level) if level in ids else -1
