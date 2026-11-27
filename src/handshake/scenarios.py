import random

from handshake.models import Scenario

ITEMS = (
    "2018 Honda Civic",
    "2016 Toyota Corolla",
    "2019 Mazda 3",
    "2017 Ford Focus",
    "2015 Volkswagen Golf",
    "2020 Hyundai Elantra",
)
KINDS = ("wide", "narrow", "none")

MAX_ROUNDS = 6
CURRENCY = "USD"
ROUNDING_STEP = 100

MIN_LISTING_PRICE = 8_000
MAX_LISTING_PRICE = 30_000

# Fractions of the listing price, as (low, high) bands.
WIDE_ZOPA_BAND = (0.22, 0.28)
NARROW_ZOPA_BAND = (0.025, 0.035)
NO_ZOPA_GAP_BAND = (0.03, 0.08)
WIDE_SELLER_MIN_BAND = (0.60, 0.70)
NARROW_SELLER_MIN_BAND = (0.75, 0.85)
NO_ZOPA_SELLER_MIN_BAND = (0.80, 0.90)


def _round_to_step(value: float) -> int:
    return round(value / ROUNDING_STEP) * ROUNDING_STEP


def _fraction(rng: random.Random, band: tuple[float, float], base: int) -> int:
    return _round_to_step(base * rng.uniform(*band))


def _build_scenario(rng: random.Random, seed: int, index: int) -> Scenario:
    kind = KINDS[index % len(KINDS)]
    listing = _round_to_step(rng.randint(MIN_LISTING_PRICE, MAX_LISTING_PRICE))
    item = rng.choice(ITEMS)

    if kind == "wide":
        seller_min = _fraction(rng, WIDE_SELLER_MIN_BAND, listing)
        buyer_max = seller_min + _fraction(rng, WIDE_ZOPA_BAND, listing)
    elif kind == "narrow":
        seller_min = _fraction(rng, NARROW_SELLER_MIN_BAND, listing)
        buyer_max = seller_min + _fraction(rng, NARROW_ZOPA_BAND, listing)
    else:
        seller_min = _fraction(rng, NO_ZOPA_SELLER_MIN_BAND, listing)
        buyer_max = seller_min - _fraction(rng, NO_ZOPA_GAP_BAND, listing)

    return Scenario(
        id=f"scenario-{seed}-{index}",
        item=item,
        public_listing_price=listing,
        buyer_max=buyer_max,
        seller_min=seller_min,
        max_rounds=MAX_ROUNDS,
        currency=CURRENCY,
    )


def generate_scenarios(seed: int, count: int = 12) -> list[Scenario]:
    rng = random.Random(seed)
    return [_build_scenario(rng, seed, index) for index in range(count)]
