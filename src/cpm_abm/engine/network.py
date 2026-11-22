"""Who trades with whom and who joins, under the robustness switches (docs/ROBUSTNESS_PLAN.md, section 5).

The ring's positions, the hubs' weights, the joining thresholds and the launch set are fixed for the run and built
from the seed and the population alone, so all five arms of a job share them, as they share every base draw. The
sellers of each month are drawn on streams of their own. With every switch at its default nothing here draws a number
and the base's sellers, joining chance and launch set are used unchanged.
"""
from dataclasses import dataclass

import numpy as np

from cpm_abm.engine.constants import (HUB_WEIGHT_EXPONENT, RING_SIDE, RING_STREAM, SELLER_STREAMS, THRESHOLD_LOG_MEAN,
                                      THRESHOLD_LOG_SPREAD, THRESHOLD_STREAM)


@dataclass(frozen=True, eq=False)
class Network:
    """The fixed network of one run: the seller rule, the ring's positions (``position``: each person's place;
    ``at``: who stands at each place), the hubs' weights and the joining thresholds; None where a switch is off."""
    sellers: str = "uniform"
    local_share: float = 1.0
    position: np.ndarray = None
    at: np.ndarray = None
    weight: np.ndarray = None
    threshold: np.ndarray = None

    def draw_sellers(self, buyer, base, seed, kind, month):
        """The sellers of the purchases of ``buyer`` (any shape) under this world's rule, on the stream of ``kind``
        ("service", "shock" or "term") for ``month``; ``base``, the base's uniform sellers, already drawn on their own
        stream, is returned unchanged with uniform sellers."""
        if self.sellers == "uniform":
            return base
        rng = np.random.default_rng(np.random.SeedSequence([seed, SELLER_STREAMS[kind], month]))
        flat = np.asarray(buyer).ravel()
        if self.sellers == "ring":
            chosen = ring_sellers(rng, flat, self.position, self.at, self.local_share)
        else:
            chosen = hub_sellers(rng, flat, self.weight)
        return chosen.reshape(np.shape(buyer))

    def launch_set(self, placement, a0, start_draw):
        """The people in P at launch: the base's (each with chance a0, ``start_draw`` < a0); or the round(a0 n) people
        on ring positions 0 up to that count ("neighbourhood"); or the round(a0 n) with the largest weights
        ("largest"). Each is nested across launch levels."""
        if placement == "scattered":
            return start_draw < a0
        count = int(round(a0 * start_draw.size))
        if placement == "neighbourhood":
            return self.position < count
        return rank_of(self.weight, largest_first=True) < count


def build_network(economy, spending):
    """The run's Network from the Economy and each person's initial spending: ring positions, a random permutation
    drawn once on its own stream (people are indexed in order of wealth, so places must be random), when the sellers or
    the launch use the ring; hub weights when they use hubs; thresholds under the threshold rule."""
    n, position, at, weight, threshold = economy.n, None, None, None, None
    if economy.sellers == "ring":
        position = np.random.default_rng(np.random.SeedSequence([economy.seed, RING_STREAM])).permutation(n)
        at = np.argsort(position)
    if economy.sellers == "hubs":
        weight = hub_weights(spending)
    if economy.joining == "threshold":
        threshold = thresholds(economy.thresholds, n, economy.seed)
    return Network(economy.sellers, economy.local_share, position, at, weight, threshold)


def rank_of(value, largest_first=True):
    """Each person's rank by ``value``, 0 for the largest (ties in index order)."""
    order = np.argsort(-value if largest_first else value, kind="stable")
    rank = np.empty(value.size, int)
    rank[order] = np.arange(value.size)
    return rank


def hub_weights(spending):
    """Each person's hub weight k^(-HUB_WEIGHT_EXPONENT), k its rank by initial spending, the largest spender 1."""
    return (rank_of(spending) + 1.0) ** -HUB_WEIGHT_EXPONENT


def thresholds(setting, n, seed):
    """Each person's joining threshold, fixed for the run: uniform on 0 to 1, or measured (log-normal, not truncated),
    drawn once on their own stream; or one common number for everyone, which draws nothing."""
    if not isinstance(setting, str):
        return np.full(n, float(setting))
    rng = np.random.default_rng(np.random.SeedSequence([seed, THRESHOLD_STREAM]))
    if setting == "uniform":
        return rng.random(n)
    return rng.lognormal(THRESHOLD_LOG_MEAN, THRESHOLD_LOG_SPREAD, n)


def threshold_chance(contact, threshold, xi0, xi1):
    """The monthly joining chance under the threshold rule: xi0 + xi1 where the contact share is at least the
    person's threshold and xi0 below it. A person with no partners this month has no contact share (NaN), and as in
    the base its chance is undefined and it does not join."""
    met = np.where(np.isnan(contact), np.nan, contact >= threshold)
    return xi0 + xi1 * met


def ring_sellers(rng, buyer, position, at, local_share):
    """One seller a purchase on the ring: with chance ``local_share`` one of the buyer's 2 x RING_SIDE nearest
    positions, RING_SIDE each side, uniformly, never itself; otherwise anyone else uniformly. Three draws a purchase,
    always all three, so the stream does not depend on the local share."""
    n = position.size
    local = rng.random(buyer.size) < local_share
    step = rng.integers(0, 2 * RING_SIDE, size=buyer.size)
    step = step - RING_SIDE + (step >= RING_SIDE)                    # -RING_SIDE to -1 and 1 to RING_SIDE
    anyone = (buyer + 1 + rng.integers(0, n - 1, size=buyer.size)) % n
    return np.where(local, at[(position[buyer] + step) % n], anyone)


def hub_sellers(rng, buyer, weight):
    """One seller a purchase with hubs: person j with chance weight_j over the weights of everyone but the buyer.
    One uniform draw a purchase, read on the cumulative weights with the buyer's own interval stepped over, so the
    draw is exact and needs no rejection."""
    n, cumulative = weight.size, np.cumsum(weight)
    start = cumulative - weight
    u = rng.random(buyer.size) * (cumulative[-1] - weight[buyer])
    u = u + weight[buyer] * (u >= start[buyer])
    seller = np.minimum(np.searchsorted(cumulative, u, side="right"), n - 1)
    # A draw that rounding leaves on the buyer's own interval edge goes to its neighbour (never seen in practice).
    return np.where(seller == buyer, np.where(buyer == n - 1, n - 2, buyer + 1), seller)
