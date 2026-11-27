import math
import random
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

from handshake.metrics import RunMetrics
from handshake.models import Outcome, Role
from handshake.records import RunRecord

DEFAULT_Z = 1.96
DEFAULT_N_BOOT = 2000
LOWER_PERCENTILE = 0.025
UPPER_PERCENTILE = 0.975

Interval = tuple[float, float]


def wilson_interval(successes: int, n: int, z: float = DEFAULT_Z) -> Interval:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_mean_ci(
    values: Sequence[float], seed: int = 0, n_boot: int = DEFAULT_N_BOOT
) -> Interval:
    if not values:
        raise ValueError("bootstrap_mean_ci requires at least one value")
    rng = random.Random(seed)
    size = len(values)
    means = sorted(sum(rng.choices(values, k=size)) / size for _ in range(n_boot))
    low = means[int(LOWER_PERCENTILE * (n_boot - 1))]
    high = means[int(UPPER_PERCENTILE * (n_boot - 1))]
    return (low, high)


class GroupStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    role: Role
    n: int
    deal_rate: float
    deal_rate_ci: Interval
    leak_rate: float
    leak_rate_ci: Interval
    missed_deal_rate: float
    mean_surplus_share: float | None
    surplus_ci: Interval | None


_ROLE_VIEWS: dict[Role, Callable[[RunRecord], tuple[str, bool, float | None]]] = {
    Role.BUYER: lambda r: (r.buyer_model, r.metrics.buyer_leaked, r.metrics.buyer_surplus_share),
    Role.SELLER: lambda r: (
        r.seller_model,
        r.metrics.seller_leaked,
        r.metrics.seller_surplus_share,
    ),
}


def _is_deal(metrics: RunMetrics) -> bool:
    return metrics.outcome == Outcome.DEAL


def _group_stats(model: str, role: Role, records: Sequence[RunRecord]) -> GroupStats:
    n = len(records)
    deals = sum(1 for r in records if _is_deal(r.metrics))
    leaks = sum(1 for r in records if _ROLE_VIEWS[role](r)[1])
    missed = sum(1 for r in records if r.metrics.missed_deal)
    shares = [
        share
        for r in records
        if _is_deal(r.metrics) and (share := _ROLE_VIEWS[role](r)[2]) is not None
    ]
    return GroupStats(
        model=model,
        role=role,
        n=n,
        deal_rate=deals / n,
        deal_rate_ci=wilson_interval(deals, n),
        leak_rate=leaks / n,
        leak_rate_ci=wilson_interval(leaks, n),
        missed_deal_rate=missed / n,
        mean_surplus_share=sum(shares) / len(shares) if shares else None,
        surplus_ci=bootstrap_mean_ci(shares) if shares else None,
    )


def aggregate(records: Sequence[RunRecord]) -> list[GroupStats]:
    groups: dict[tuple[str, Role], list[RunRecord]] = {}
    for record in records:
        for role, view in _ROLE_VIEWS.items():
            groups.setdefault((view(record)[0], role), []).append(record)
    ordered = sorted(groups, key=lambda key: (key[0], key[1].value))
    return [_group_stats(model, role, groups[(model, role)]) for model, role in ordered]
