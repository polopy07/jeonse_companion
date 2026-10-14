"""등기부 요약 추출 정확도 (중간 점검 기준: 검증 샘플 10건 항목 95% 이상, docs/validation/등기부추출_정확도.md)."""
import copy

import yaml

from measure_registry_accuracy import ANSWERS, PASS_RATE, measure, score_sample


def test_registry_accuracy_meets_midterm_bar():
    scores = measure()
    assert len(scores) == 10
    correct, total = sum(s.correct for s in scores), sum(s.total for s in scores)
    assert correct / total >= PASS_RATE
    # 지금은 모든 항목이 맞는다. 파서를 고쳐 틀린 항목이 생기면 여기서 드러난다
    assert [m for s in scores for m in s.misses] == []


def test_scoring_counts_wrong_and_extra_items():
    # 채점이 틀린 값·없는 값·잘못 찾은 값을 실제로 틀렸다고 세는지 (정답을 일부러 바꿔서)
    answer = copy.deepcopy(next(a for a in yaml.safe_load(ANSWERS.read_text(encoding="utf-8"))["samples"]
                                if a["file"] == "iros_apartment_mortgage.txt"))
    answer["mortgages"][0]["amount"] = 40_000_000     # 틀린 값
    answer["owners"] = []                             # 파서가 찾은 소유자는 "정답에 없음"
    answer["gapgu"] = [{"rank": "3", "kind": "seizure"}]   # 파서가 못 찾은 등기
    s = score_sample(answer)
    assert len(s.misses) == 3 and s.correct == s.total - 3
