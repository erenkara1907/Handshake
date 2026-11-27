import pytest

from handshake.metrics import RunMetrics
from handshake.models import Outcome, Role, Scenario
from handshake.records import RunRecord
from handshake.referee import Verdict
from handshake.stats import aggregate, bootstrap_mean_ci, wilson_interval

SELLER_MIN = 80


def _scenario(zopa: int) -> Scenario:
    return Scenario(
        id="s",
        item="car",
        public_listing_price=100,
        buyer_max=SELLER_MIN + zopa,
        seller_min=SELLER_MIN,
        max_rounds=5,
        currency="EUR",
    )


def _record(
    buyer: str,
    seller: str,
    outcome: Outcome = Outcome.DEAL,
    buyer_share: float | None = 0.6,
    seller_share: float | None = 0.4,
    seller_leaked: bool = False,
    zopa: int = 10,
) -> RunRecord:
    return RunRecord(
        run_id="r",
        scenario_id="s",
        scenario=_scenario(zopa),
        buyer_model=buyer,
        seller_model=seller,
        repeat=0,
        verdict=Verdict(outcome=outcome, price=None, reason="r"),
        metrics=RunMetrics(
            outcome=outcome,
            rounds=1,
            buyer_surplus_share=buyer_share,
            seller_surplus_share=seller_share,
            missed_deal=outcome in (Outcome.NO_DEAL, Outcome.MAX_ROUNDS),
            buyer_leaked=False,
            seller_leaked=seller_leaked,
            buyer_giveaway=False,
            seller_giveaway=False,
        ),
        turns=[],
    )


def test_wilson_known_value() -> None:
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.237, abs=0.001)
    assert high == pytest.approx(0.763, abs=0.001)


def test_wilson_zero_n_is_full_range() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_bootstrap_deterministic_for_seed() -> None:
    values = [0.1, 0.4, 0.5, 0.9, 0.3]
    assert bootstrap_mean_ci(values, seed=3) == bootstrap_mean_ci(values, seed=3)


def test_bootstrap_ci_brackets_mean() -> None:
    low, high = bootstrap_mean_ci([0.1, 0.4, 0.5, 0.9, 0.3])
    assert low <= 0.44 <= high


def test_bootstrap_constant_values_collapse() -> None:
    assert bootstrap_mean_ci([0.5, 0.5, 0.5]) == (0.5, 0.5)


def test_bootstrap_empty_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_mean_ci([])


def test_aggregate_groups_by_model_and_role() -> None:
    groups = aggregate([_record("m", "x"), _record("y", "m")])
    keyed = {(g.model, g.role): g for g in groups}
    assert set(keyed) == {
        ("m", Role.BUYER),
        ("m", Role.SELLER),
        ("x", Role.SELLER),
        ("y", Role.BUYER),
    }
    assert keyed[("m", Role.BUYER)].n == 1
    assert keyed[("m", Role.SELLER)].n == 1
    assert keyed[("m", Role.BUYER)].mean_surplus_share == pytest.approx(0.6)
    assert keyed[("m", Role.SELLER)].mean_surplus_share == pytest.approx(0.4)


def test_aggregate_rates_and_sorting() -> None:
    records = [
        _record("m", "z", seller_leaked=True),
        _record("m", "z", outcome=Outcome.NO_DEAL, buyer_share=None, seller_share=None),
    ]
    groups = aggregate(records)
    assert [(g.model, g.role) for g in groups] == [("m", Role.BUYER), ("z", Role.SELLER)]
    seller = groups[1]
    assert seller.deal_rate == 0.5
    assert seller.leak_rate == 0.5
    assert seller.missed_deal_rate == 0.5


def test_aggregate_surplus_none_without_deals() -> None:
    record = _record("m", "z", outcome=Outcome.NO_DEAL, buyer_share=None, seller_share=None)
    for group in aggregate([record]):
        assert group.mean_surplus_share is None
        assert group.surplus_ci is None
        assert group.deal_rate == 0.0


def test_aggregate_empty() -> None:
    assert aggregate([]) == []
