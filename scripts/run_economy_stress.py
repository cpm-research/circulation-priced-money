"""Stress checks on M1 and M2 against S0 at development scale: how much of the gain survives each stress.

Run from the repository root:
    python -X utf8 scripts/run_economy_stress.py --output results/YYYY-MM-DD_stress_n100
Stresses (each alone, against the core-aligned baseline): outside lenders' interest recirculated to households,
SHED unexpected-expense shocks on, and the conversion fee on every routine E-P crossing. N = 100 is the
development size, so this is not a population run.
"""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cpm_abm.catalogue import finite_catalogue  # noqa: E402  (the pinned PySPG iterator)
from cpm_abm.economy_abm import Economy, simulate  # noqa: E402
from run_economy_figures import DOLLARS, engine_inputs, provenance, persistence, windows  # noqa: E402

STRESSES = dict(baseline={}, lender_interest_recirculated=dict(lender_income_recirculated=True),
                shocks_on=dict(shocks=True), routine_conversion_fees=dict(routine_conversion=True))
ARMS = ("M1", "M2")
SEEDS = (20261021, 20261022, 20261023)


def run(args):
    """One (stress, arm, seed): the arm and its S0 pair, gains, participation, failures, charge, issuer, verdict."""
    stress, arm, seed, n = args
    economy = replace(Economy(n=n, seed=seed), **STRESSES[stress])
    # No provider fee (P payments run on stablecoin rails), as in every runner that builds cell inputs.
    inputs = engine_inputs()
    m, s0 = simulate(inputs, 0.6, economy, arm), simulate(inputs, 0.6, economy, "S0")
    end = economy.burn_in + economy.months
    gain = (m["wealth"][end] - s0["wealth"][end]) * DOLLARS
    _, w2 = windows(m)
    a, b = m["series"], s0["series"]
    flow = lambda key: float(np.nanmean(a[key][w2] - b[key][w2]) * DOLLARS)
    return dict(stress=stress, arm=arm, seed=seed, mean_gain_usd=float(gain.mean()), better_off=float((gain >= 0).mean()),
                A_launch=float(a["A"][economy.burn_in]), A_W2=float(a["A"][w2].mean()),
                failures_pct=float(a["failure_share"][w2].mean() * 100), failures_S0_pct=float(b["failure_share"][w2].mean() * 100),
                c_pct=float(np.nanmean(a["c"][w2]) * 1200), issuer_usd=float(np.nanmean(a["issuer"][w2]) * DOLLARS),
                outside_interest_saved_usd=-flow("out_interest"), penalties_saved_usd=-flow("penalties"),
                inflation_term_usd=flow("inflation"), verdict=persistence(m, 0.6)["verdict"])


def summarise(rows, stress, arm):
    """Seed means for one stress and arm, and the share of the baseline gain that survives."""
    mine = [r for r in rows if r["stress"] == stress and r["arm"] == arm]
    base = [r for r in rows if r["stress"] == "baseline" and r["arm"] == arm]
    mean = lambda key, group: float(np.mean([r[key] for r in group]))
    keys = ("mean_gain_usd", "better_off", "A_launch", "A_W2", "failures_pct", "failures_S0_pct", "c_pct", "issuer_usd",
            "outside_interest_saved_usd", "penalties_saved_usd", "inflation_term_usd")
    out = {key: round(mean(key, mine), 3) for key in keys}
    out["gain_surviving"] = round(mean("mean_gain_usd", mine) / mean("mean_gain_usd", base), 3)
    out["verdicts"] = [r["verdict"][:12] for r in mine]
    return out


def jobs(n):
    """Every (stress, arm, seed, n) job, a PySPG catalogue (``finite_catalogue``) over the stresses, arms and seeds, the
    last advancing fastest. Example: the first three are the baseline M1 run at each seed in turn; 4 x 2 x 3 = 24."""
    sweep = finite_catalogue(dict(stress=list(STRESSES), arm=list(ARMS), seed=list(SEEDS)))
    return [(p["stress"], p["arm"], p["seed"], n) for p in sweep]


def summary_keys():
    """The summary's (arm, stress) pairs, a PySPG catalogue over the arms and stresses, the stress advancing fastest.
    Example: M1 with each of the four stresses, then M2 with each."""
    return [(p["arm"], p["stress"]) for p in finite_catalogue(dict(arm=list(ARMS), stress=list(STRESSES)))]


def main():
    """Run every stress, arm and seed; write rows and the summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()
    if args.n >= 1000:
        raise ValueError("Stress checks at N = 1,000 are population runs and need a deliberate decision to run")
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Output must stay in this workspace")
    output.mkdir(parents=True, exist_ok=False)
    rows = list(map(run, jobs(args.n)))
    summary = {f"{arm} | {stress}": summarise(rows, stress, arm) for arm, stress in summary_keys()}
    with (output / "stress.json").open("x", encoding="utf-8") as target:
        json.dump(dict(provenance=provenance("scripts/run_economy_stress.py"), economy=asdict(Economy(n=args.n)),
                       stresses=STRESSES, seeds=SEEDS, population_runs=0,
                       summary=summary, rows=rows), target, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
