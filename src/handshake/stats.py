import math
import random
from collections.abc import Callable, Sequence
from typing import NamedTuple

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
    """Per model and role statistics.

    `n` counts all runs. `deal_rate` and `missed_deal_rate` (and `deal_rate_ci`) are over
    the `feasible_n` runs whose scenario has a positive ZOPA; with no feasible runs they are
    0.0 with interval (0.0, 1.0), as `wilson_interval(0, 0)`. `leak_rate` and
    `giveaway_rate` are over all `n` runs.
    """

    model_config = ConfigDict(frozen=True)

    model: str
    role: Role
    n: int
    feasible_n: int
    deal_rate: float
    deal_rate_ci: Interval
    leak_rate: float
    leak_rate_ci: Interval
    giveaway_rate: float
    giveaway_rate_ci: Interval
    missed_deal_rate: float
    mean_surplus_share: float | None
    surplus_ci: Interval | None


class _RoleView(NamedTuple):
    model: str
    leaked: bool
    gave_away: bool
    surplus_share: float | None


_ROLE_VIEWS: dict[Role, Callable[[RunRecord], _RoleView]] = {
    Role.BUYER: lambda r: _RoleView(
        r.buyer_model,
        r.metrics.buyer_leaked,
        r.metrics.buyer_giveaway,
        r.metrics.buyer_surplus_share,
    ),
    Role.SELLER: lambda r: _RoleView(
        r.seller_model,
        r.metrics.seller_leaked,
        r.metrics.seller_giveaway,
        r.metrics.seller_surplus_share,
    ),
}


def _is_deal(metrics: RunMetrics) -> bool:
    return metrics.outcome == Outcome.DEAL


def _rate(count: int, n: int) -> float:
    return count / n if n else 0.0


def _group_stats(model: str, role: Role, records: Sequence[RunRecord]) -> GroupStats:
    views = [_ROLE_VIEWS[role](r) for r in records]
    feasible = [r for r in records if r.scenario.zopa > 0]
    deals = sum(1 for r in feasible if _is_deal(r.metrics))
    missed = sum(1 for r in feasible if r.metrics.missed_deal)
    leaks = sum(1 for v in views if v.leaked)
    giveaways = sum(1 for v in views if v.gave_away)
    shares = [
        v.surplus_share
        for r, v in zip(records, views, strict=True)
        if _is_deal(r.metrics) and v.surplus_share is not None
    ]
    n, feasible_n = len(records), len(feasible)
    return GroupStats(
        model=model,
        role=role,
        n=n,
        feasible_n=feasible_n,
        deal_rate=_rate(deals, feasible_n),
        deal_rate_ci=wilson_interval(deals, feasible_n),
        leak_rate=_rate(leaks, n),
        leak_rate_ci=wilson_interval(leaks, n),
        giveaway_rate=_rate(giveaways, n),
        giveaway_rate_ci=wilson_interval(giveaways, n),
        missed_deal_rate=_rate(missed, feasible_n),
        mean_surplus_share=sum(shares) / len(shares) if shares else None,
        surplus_ci=bootstrap_mean_ci(shares) if shares else None,
    )


def aggregate(records: Sequence[RunRecord]) -> list[GroupStats]:
    groups: dict[tuple[str, Role], list[RunRecord]] = {}
    for record in records:
        for role, view in _ROLE_VIEWS.items():
            groups.setdefault((view(record).model, role), []).append(record)
    ordered = sorted(groups, key=lambda key: (key[0], key[1].value))
    return [_group_stats(model, role, groups[(model, role)]) for model, role in ordered]
