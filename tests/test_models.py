import pytest
from pydantic import ValidationError

from handshake.models import Offer, Scenario


def make_scenario(**overrides) -> Scenario:
    data = dict(
        id="s1",
        item="bike",
        public_listing_price=10000,
        buyer_max=9000,
        seller_min=8000,
        max_rounds=6,
        currency="TRY",
    )
    return Scenario(**{**data, **overrides})


def test_zopa_is_buyer_max_minus_seller_min():
    assert make_scenario(buyer_max=9000, seller_min=8000).zopa == 1000


def test_offer_rejects_non_positive_price():
    with pytest.raises(ValidationError):
        Offer(price=0, message="x")


def test_offer_is_frozen():
    offer = Offer(price=5, message="x")
    with pytest.raises(ValidationError):
        offer.price = 6


def test_offer_defaults():
    offer = Offer(price=5, message="x")
    assert offer.accept is False
    assert offer.walk_away is False
