"""Rebuild every number, table and figure of the paper from the stored results, in one command.

    python scripts/rebuild_paper.py

It calls ``scripts/paper_numbers.py`` and ``scripts/paper_figures.py`` on the results shipped in ``results/``: the
confirmation map, which the headline numbers and the registered claim are read from; the development map, with its
two bound maps, its side checks and the robustness sets with the records run, all on the development seeds; and the
five population sizes of the size check. Then it writes the results card (``scripts/results_card.py``) of every
shipped folder. It runs no simulation. Afterwards compile the paper (``cd paper && tectonic cpm.tex``).

The folders and the labels the tables print are listed here once, so the paper's tables and this file cannot drift
apart.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                      # so that ``scripts`` imports as a package from any folder

from scripts import paper_figures, paper_numbers, results_card   # noqa: E402  (after the path is set)

RESULTS = ROOT / "results"
# The headline map: the confirmation map under the decided entry rule (entrants read the published quote).
MAP = RESULTS / "confirmation_quote"
# The development map. The side checks, the bounds and the robustness sets were run on its seeds and stand beside it;
# the seed plan was read from it.
BASE = RESULTS / "development_map"
# The confirmation map again, with savers acting on the pool's realised record and not on its quote: the second,
# pessimistic reading of the entry rule, on the same seeds.
SECOND = RESULTS / "confirmation_realised"
# The exploratory runs made after the confirmation was read: the rate cut (outside rates of 2.5, 3 and 3.5% on
# the exploratory seeds), and the side checks on three side seeds, each beside its own base.
CUT = RESULTS / "rate_cut"
EXPLORE_BASE = RESULTS / "explore_base"
EXPLORE = (("fixed cost 10 times", "explore_fixed_cost_x10"), ("fixed cost 100 times", "explore_fixed_cost_x100"),
           ("fixed cost 1,000 times", "explore_fixed_cost_x1000"), ("custody cost 0.44%", "explore_custody_044"),
           ("custody cost 0.74%", "explore_custody_074"), ("owners' spread 0", "explore_spread_0"),
           ("owners' spread 0.5 point", "explore_spread_050"), ("shock from month 12", "explore_shock_month_12"),
           ("shock from month 36", "explore_shock_month_36"))
LOW_RATES = RESULTS / "explore_low_rates"
# How the region figure reads a cell: a confirmation map is read as registered. Three development seeds are too few
# for the interval on the share of seeds, so a development map is read on a majority of seeds ("majority").
READING = "registered"
# The side checks: the label a table prints, and the folder. Each reruns three cells with one setting changed.
SIDES = (("leaving noise halved", "side_noise_half"), ("leaving noise doubled", "side_noise_double"),
         ("fixed cost low", "side_fixed_cost_low"), ("fixed cost high", "side_fixed_cost_high"),
         ("entrants read the track record", "side_entry_realised"),
         ("entrants read it with noise", "side_entry_leaving_rule"),
         ("failures past the fee cap at zero", "side_past_cap_0"), ("five failure fees a month", "side_fees_5"),
         ("card lines cut in the distress year", "side_card_lines_cut"),
         ("half re-choose their buffer each month", "robust_buffer_review_050"),
         ("15.3% re-choose their buffer each month", "robust_buffer_review_0153"))
# The robustness variants (docs/ROBUSTNESS_PLAN.md, section 5), each over seven launch levels with no distress at the
# outside rate 4.4%: by the sellers' world, the macro stem (letters only), the label the table prints and the folder.
# The base, the development map at the same cells and seeds, is first. A folder not yet shipped reads as pending.
ROBUST = (("Uniform", "Base", "linear joining (the base)", "development_map"),
          ("Uniform", "Measured", "measured thresholds", "robust_threshold_measured"),
          ("Uniform", "ThresholdTen", "common threshold 0.1", "robust_threshold_010"),
          ("Uniform", "ThresholdTwenty", "common threshold 0.2", "robust_threshold_020"),
          ("Uniform", "ThresholdThirty", "common threshold 0.3", "robust_threshold_030"),
          ("Ring", "Ring", "local share 1, linear joining", "robust_ring"),
          ("Ring", "RingNeighbourhood", "local share 1, linear, one neighbourhood", "robust_ring_neighbourhood"),
          ("Ring", "RingThreshold", "local share 1, threshold 0.2", "robust_ring_threshold_020"),
          ("Ring", "RingThresholdNeighbourhood", "local share 1, threshold 0.2, one neighbourhood",
           "robust_ring_threshold_020_neighbourhood"),
          ("Ring", "RingLocal", "local share 0.35, linear joining", "robust_ring_local_035"),
          ("Ring", "RingLocalThresholdNeighbourhood", "local share 0.35, threshold 0.2, one neighbourhood",
           "robust_ring_local_035_threshold_020_neighbourhood"),
          ("Hubs", "Hubs", "linear joining", "robust_hubs"),
          ("Hubs", "HubsLargest", "linear joining, largest sellers first", "robust_hubs_largest"),
          ("Hubs", "HubsMeasured", "measured thresholds", "robust_hubs_threshold_measured"),
          ("Hubs", "HubsMeasuredLargest", "measured thresholds, largest sellers first",
           "robust_hubs_threshold_measured_largest"))
RECORDS = "records_base"                           # the six side-check cells with the settlement records
BOUNDARY = "robust_stress_boundary"                # the stress boundary in steps of 0.1 point
RULE_CHECK = "robust_threshold_uniform_check"      # the threshold rule with uniform thresholds, one cell
# The bound maps: the whole grid on the same seeds with one accounting choice changed.
BOUNDS = (("loan losses at published rates", "bound_loan_losses"),
          ("lenders' interest returned", "bound_interest_returned"))
SIZES = (500, 1000, 2000, 4000, 8000)              # the population sizes of the size check


def labelled(flag, pairs):
    """The command-line words for a list of (label, folder) pairs: flag, "label=folder", flag, ..."""
    return [word for label, folder in pairs for word in (flag, f"{label}={RESULTS / folder}")]


def archived(folder, name="measures.json"):
    """The volumes of a store that the list of checksums names for ``folder`` and that are not there: the store
    is kept in the data archive (results/README.md) and has to be downloaded into the folder first."""
    sums = (RESULTS / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    listed = [line.split("  ", 1)[1] for line in sums if line]
    wanted = [path for path in listed if path.startswith(f"{folder.name}/{name}")]
    return [path for path in wanted if not (RESULTS / path).exists()]


def main():
    """Write paper/numbers.tex, paper/tables and paper/figures from the stored results."""
    missing = archived(MAP)
    if missing:
        sys.exit(f"The monthly series of {MAP.name} are not in results/: {', '.join(missing)}. They are kept in the "
                 "data archive (results/README.md); download them into that folder and run this again.")
    paper = ROOT / "paper"
    robust = [word for group, stem, label, folder in ROBUST for word in ("--robust", group, stem, label,
                                                                         str(RESULTS / folder))]
    paper_numbers.main(["--map", str(MAP), "--base", str(BASE), "--second", str(SECOND), "--cut", str(CUT),
                        "--explore-base", str(EXPLORE_BASE), *labelled("--explore", EXPLORE),
                        "--low-rates", str(LOW_RATES), "--out", str(paper),
                        *labelled("--side", SIDES),
                        *labelled("--bound", BOUNDS), *robust, "--records", str(RESULTS / RECORDS),
                        "--boundary", str(RESULTS / BOUNDARY), "--rule-check", str(RESULTS / RULE_CHECK)])
    paper_figures.main(["--map", str(MAP), "--cut", str(CUT), "--second", str(SECOND), "--network",
                        str(RESULTS / "population_network"), "--out",
                        str(paper / "figures"), "--reading", READING,
                        "--sizes", *(str(RESULTS / f"size_{n}") for n in SIZES), *robust])
    # The fixed results card of every shipped folder, beside its stores.
    for folder in sorted(p.parent for p in RESULTS.glob("*/summary.json.gz")):
        print(f"wrote {results_card.write_card(folder).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
