import pytest

from app.engine.price import deposit_ratio, estimate_price

EOK = 100_000_000


def test_estimated_price_is_official_times_140(rules):
    assert estimate_price(2 * EOK, None, rules["alert"]) == 280_000_000


def test_estimated_price_uses_lower_trade_price(rules):
    assert estimate_price(2 * EOK, 250_000_000, rules["alert"]) == 250_000_000
    assert estimate_price(2 * EOK, 300_000_000, rules["alert"]) == 280_000_000


def test_ratio_before_registry_is_minimum(rules):
    r = deposit_ratio(140_000_000, 280_000_000, None, rules["alert"])
    assert r.senior_debt == 0
    assert r.is_minimum
    assert r.ratio == 0.5


def test_ratio_includes_mortgage(rules):
    r = deposit_ratio(140_000_000, 280_000_000, 84_000_000, rules["alert"])
    assert not r.is_minimum
    assert r.ratio == 0.8


def test_ratio_boundary_is_exact(rules):
    # 2.52억 ÷ 2.8억 = 정확히 90% → 경계값에서 소수점 오차로 판정이 빠지면 안 된다
    assert deposit_ratio(252_000_000, 280_000_000, 0, rules["alert"]).ratio >= 0.9
    assert deposit_ratio(280_000_000, 280_000_000, 0, rules["alert"]).ratio >= 1.0


def test_ratio_rejects_zero_price(rules):
    with pytest.raises(ValueError):
        deposit_ratio(1, 0, 0, rules["alert"])
