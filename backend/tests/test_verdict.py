import pytest

from app.engine.check import MissingInputError, run_check
from app.schemas import CheckInput, RegistryInput

EOK = 100_000_000


def check(rules, **kw):
    kw.setdefault("housing_type", "row_house")
    kw.setdefault("deposit", 1 * EOK)
    kw.setdefault("official_price", 2 * EOK)   # 추정 주택가격 2.8억
    return run_check(CheckInput(**kw), rules)


def ids(outcome):
    return [m.id for m in outcome.verdict.matched]


def test_no_problem(rules):
    out = check(rules, registry=RegistryInput())
    assert out.verdict.level == "no_problem"
    assert out.verdict.matched == []
    assert not out.verdict.block_payment
    assert [u["id"] for u in out.verdict.unchecked] == ["U-TAX"]
    assert out.verdict.disclaimer == "정보 제공이며 보증하지 않습니다."


def test_multi_household_is_not_applicable(rules):
    out = check(rules, housing_type="multi_household", official_price=None,
                registry=RegistryInput(mortgage=True, mortgage_amount=EOK))
    assert out.verdict.level == "not_applicable"
    assert ids(out) == ["NA-1"]                      # 근저당(C-1)은 보여 주지 않음
    assert "U-OTHER-DEPOSITS" in [u["id"] for u in out.verdict.unchecked]
    assert out.ratio is None


def test_seizure_is_problem(rules):
    out = check(rules, registry=RegistryInput(seizure=True))
    assert out.verdict.level == "problem"
    assert out.verdict.block_payment
    assert ids(out) == ["P-1"]


def test_ratio_100_is_problem_and_shows_lower_items(rules):
    out = check(rules, deposit=280_000_000, registry=RegistryInput())
    assert out.verdict.level == "problem"
    assert ids(out) == ["P-2", "C-2"]
    assert out.verdict.linkages == ["L-RATIO90"]


def test_ratio_90_is_check_needed(rules):
    out = check(rules, deposit=252_000_000, registry=RegistryInput())
    assert out.verdict.level == "check_needed"
    assert ids(out) == ["C-2"]


def test_ratio_before_registry_uses_minimum_estimate(rules):
    out = check(rules, deposit=252_000_000)
    assert out.ratio.is_minimum
    assert out.verdict.level == "check_needed"


def test_mortgage_raises_ratio(rules):
    # 시연 빌라와 같은 모양: 보증금 1.5억 + 근저당 1.2억 = 2.7억 / 2.8억 ≈ 96%
    out = check(rules, deposit=150_000_000,
                registry=RegistryInput(mortgage=True, mortgage_amount=120_000_000))
    assert out.verdict.level == "check_needed"
    assert ids(out) == ["C-1", "C-2"]
    assert out.verdict.linkages == ["L-MORTGAGE", "L-RATIO90"]


def test_trust(rules):
    unknown = check(rules, registry=RegistryInput(trust=True))
    assert ids(unknown) == ["C-3"]
    unavailable = check(rules, registry=RegistryInput(trust=True), trust_consent="unavailable")
    assert unavailable.verdict.level == "problem"
    assert ids(unavailable) == ["P-3"]
    obtained = check(rules, registry=RegistryInput(trust=True), trust_consent="obtained")
    assert obtained.verdict.level == "no_problem"


def test_violation(rules):
    assert ids(check(rules, building_violation=True)) == ["C-4"]
    out = check(rules, building_violation=True, guarantor_consult="impossible")
    assert out.verdict.level == "problem"
    assert ids(out) == ["P-4"]
    assert check(rules, building_violation=True, guarantor_consult="possible").verdict.level == "no_problem"


def test_missing_official_price(rules):
    with pytest.raises(MissingInputError) as e:
        check(rules, official_price=None)
    assert e.value.code == "MISSING_OFFICIAL_PRICE"


def test_mortgage_without_amount_is_rejected():
    with pytest.raises(ValueError):
        RegistryInput(mortgage=True)
