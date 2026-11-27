from handshake.scenarios import generate_scenarios

SEED = 42
COUNT = 12
MIN_PER_KIND = 3


def test_same_seed_same_scenarios():
    assert generate_scenarios(SEED) == generate_scenarios(SEED)


def test_different_seed_differs():
    assert generate_scenarios(SEED) != generate_scenarios(SEED + 1)


def test_mix_contains_positive_and_nonpositive_zopa():
    scenarios = generate_scenarios(SEED, count=COUNT)
    assert len(scenarios) == COUNT
    assert sum(s.zopa <= 0 for s in scenarios) >= MIN_PER_KIND
    assert sum(s.zopa > 0 for s in scenarios) >= MIN_PER_KIND


def test_ids_unique():
    scenarios = generate_scenarios(SEED, count=COUNT)
    assert len({s.id for s in scenarios}) == COUNT


def test_seller_min_below_listing_price():
    for s in generate_scenarios(SEED, count=COUNT):
        assert s.seller_min < s.public_listing_price


def test_all_values_positive_ints():
    for s in generate_scenarios(SEED, count=COUNT):
        for value in (
            s.public_listing_price,
            s.buyer_max,
            s.seller_min,
            s.max_rounds,
        ):
            assert isinstance(value, int)
            assert value > 0
