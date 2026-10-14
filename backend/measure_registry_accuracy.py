"""등기부 요약 추출 정확도 측정 (중간 점검 10/20: 검증 샘플 10건 항목 기준 95% 이상).

정답표 docs/validation/registry_answers.yaml과 파서 결과를 항목별로 대조한다.
backend/ 폴더에서 실행: python measure_registry_accuracy.py
tests/test_registry_accuracy.py가 같은 계산으로 기준을 검사한다. 결과 문서는 docs/validation/등기부추출_정확도.md
"""
from dataclasses import dataclass, field

import yaml

from app.config import REPO_ROOT
from app.registry import parse_summary_text

ANSWERS = REPO_ROOT / "docs" / "validation" / "registry_answers.yaml"
FIXTURES = REPO_ROOT / "backend" / "tests" / "fixtures" / "registry"
PASS_RATE = 0.95


@dataclass
class SampleScore:
    file: str
    correct: int = 0
    total: int = 0
    skipped: int = 0        # 원문에서 보이지 않아 채점에서 뺀 항목
    misses: list[str] = field(default_factory=list)

    def check(self, item: str, expected, actual) -> None:
        self.total += 1
        if expected == actual:
            self.correct += 1
        else:
            self.misses.append(f"{item}: 정답 {expected!r}, 파서 {actual!r}")

    def extra(self, item: str) -> None:
        """정답에 없는데 파서가 읽은 것 (잘못 찾은 항목)도 틀린 항목 1개로 센다."""
        self.total += 1
        self.misses.append(f"{item}: 정답에 없음")


def score_sample(answer: dict) -> SampleScore:
    s = SampleScore(answer["file"])
    parsed = parse_summary_text((FIXTURES / answer["file"]).read_text(encoding="utf-8"))

    for name in answer["owners"]:
        s.check(f"소유자 {name}", True, name in parsed.owners)
    for name in parsed.owners:
        if name not in answer["owners"]:
            s.extra(f"소유자 {name}")

    gapgu = {e.rank: "seizure" for e in parsed.seizures} | {e.rank: "trust" for e in parsed.trusts}
    for e in answer["gapgu"]:
        s.check(f"갑구 {e['rank']}번 종류", e["kind"], gapgu.pop(e["rank"], None))

    mortgages = {m.rank: m for m in parsed.mortgages}
    for e in answer["mortgages"]:
        m = mortgages.pop(e["rank"], None)
        s.check(f"을구 {e['rank']}번 채권최고액", e["amount"], m and m.amount)
        s.check(f"을구 {e['rank']}번 근저당권자", e["holder"], m and m.holder)

    leases = {lease.rank: lease for lease in parsed.leases}
    for e in answer["leases"]:
        lease = leases.pop(e["rank"], None)
        s.check(f"을구 {e['rank']}번 등기목적", e["purpose"], lease and lease.purpose)
        s.check(f"을구 {e['rank']}번 보증금", e["amount"], lease and lease.amount)
        if e.get("holder_visible", True):
            s.check(f"을구 {e['rank']}번 권리자", e["holder"], lease and lease.holder)
        else:
            s.skipped += 1

    for rank in gapgu:
        s.extra(f"갑구 {rank}번")
    for rank in [*mortgages, *leases]:
        s.extra(f"을구 {rank}번")
    for e in parsed.others:   # 분류하지 못하고 사용자 확인으로 넘긴 등기도 틀린 항목으로 센다
        s.extra(f"분류 못 한 {e.rank}번 '{e.purpose}'")

    fields = parsed.to_fields()
    for key, expected in answer["fields"].items():
        s.check(f"판정 입력 {key}", expected, fields[key])
    return s


def measure() -> list[SampleScore]:
    answers = yaml.safe_load(ANSWERS.read_text(encoding="utf-8"))
    return [score_sample(a) for a in answers["samples"]]


if __name__ == "__main__":
    scores = measure()
    correct, total = sum(s.correct for s in scores), sum(s.total for s in scores)
    print("| 샘플 | 맞음 / 항목 | 틀린 항목 |\n| --- | --- | --- |")
    for s in scores:
        skipped = f" (보이지 않아 뺀 항목 {s.skipped})" if s.skipped else ""
        print(f"| `{s.file}` | {s.correct} / {s.total}{skipped} | {'; '.join(s.misses) or '-'} |")
    rate = correct / total
    print(f"\n전체 {correct} / {total} = {rate:.1%} (기준 {PASS_RATE:.0%}, {'통과' if rate >= PASS_RATE else '미달'})")
