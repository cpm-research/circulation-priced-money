"""Every number and table the paper quotes, from a stored map's JSON, so that no number in the paper is typed by hand.

Run from the repository root once a map has finished:
    python -X utf8 scripts/paper_numbers.py --map results/<map> [--side name=results/<folder> ...] [--out paper]

It reads only the JSON the population runner wrote (summary.json, cells.json and measures.json; failure_counts.json
is never needed) and imports nothing from the runner. From the code it takes only the registered seed design: the
confirmation count and its extension (src/cpm_abm/experiment/grid.py), the claim's levels and margins
(notes.py) and the interval arithmetic (statistics.py), so that the paper's sample sizes are the ones the code runs.
It runs no simulation. It writes three things into --out:

  numbers.tex          one LaTeX macro per number, \\newcommand{\\Name}{value}, with a header naming the results folder,
                       its git commit, the source hashes, the seeds and the population;
  tables/*.tex         booktabs tabular bodies (no table environment, no caption: the paper wraps them);
  numbers_report.txt   one line per macro and per table cell: its value and the JSON path(s) and cells it came from,
                       then a list of everything the paper asks for that the result does not store.

A field the result does not store never stops the script and is never filled in: its macro or table cell is written
as a visible placeholder (PLACEHOLDER) and the report says what is missing. A number that would be ambiguous (two
cells with the same place, files from different commits, cells disagreeing on something that must be constant) stops
the script with a clear message instead.

The arrangements keep the runner's code names inside the JSON: S0 banks and cards, M0 best-case DeFi, U the pool
without the holding charge, M1 CPM, M2 indexed CPM. "CPM" in a macro name is M1.
"""
import argparse
import gzip
import io
import json
import re
import sys
from itertools import chain, product, repeat
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _folder in (ROOT / "scripts", ROOT / "src"):     # the experiment layer imports from both
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

from cpm_abm.economy_abm import Economy  # noqa: E402
from cpm_abm.experiment.grid import CONFIRMATION_COUNT, CONFIRMATION_EXTENSION  # noqa: E402
from cpm_abm.experiment.notes import (CLAIM_ALPHA, CLAIM_MARGIN, DIP_MARGIN, SEED_ASSURANCE,  # noqa: E402
                                      SEED_CAP, SEED_POWER)
from cpm_abm.experiment.statistics import (bonferroni_cells, seeds_needed, spread_bound, spread_resolved,  # noqa: E402
                                           t_interval, wilson_bounds)

# ----------------------------------------------------------------------------------------------------------------------
# What the paper reads, in one place
# ----------------------------------------------------------------------------------------------------------------------
ARMS = ("S0", "M0", "U", "M1", "M2")                  # the runner's arrangements, in the order the paper lists them
# M0's name in a store of the second run, where DeFi pays no yield and lends nothing.
DEFI_SECOND = "DeFi (stablecoin payments)"


def second_run_store(summary):
    """Whether a stored summary is of a run of the second run, read from its economy as
    ``cpm_abm.experiment.notes.second_run`` reads an Economy: the conserved edge, the extra layoffs' wages kept,
    purchases dropped in the stress year or distress years at random; a released store, whose economy has none of
    them or predates them, reads False."""
    economy = (summary or {}).get("economy") or {}
    return bool(economy.get("edge", "open") not in (None, "open")
                or economy.get("distress_wages", "outside") not in (None, "outside")
                or (economy.get("distress_purchases") or 0) > 0
                or economy.get("distress_dates", "dated") not in (None, "dated"))


def defi_named(text, summary):
    """``text`` with M0's released name, best-case DeFi, read as DeFi (stablecoin payments) in a store of the second
    run (``second_run_store``), and as it is for a released store."""
    if not second_run_store(summary):
        return text
    return text.replace("best-case DeFi", DEFI_SECOND).replace("Best-case DeFi", DEFI_SECOND)
NAMES = dict(S0="Banks and cards", M0="Best-case DeFi", U="Pool without the holding charge", M1="CPM",
             M2="Indexed CPM")
CPM = "M1"                                            # the paper's CPM is the nominal one
MONTHLY_KEPT = ARMS                                   # the arms whose monthly series this script keeps (the chains
                                                      # of failure and the period-two reading read every arm)
STRESS_RATE = 0.044                                   # the outside rate the stress table is read at
HEADLINE = 0.02                                       # 2 points of distress, the stress headline
RUN_LINE = 0.6                                        # a pool run: bridges served in years 4 and 5 below this
TARGET_SHARE = 0.95                                   # pool capital "at its target": at least this share of N*
GAP_MONTHS = (12, 36, 60)                             # months after launch the participation path is read at
YEARS_1_3, YEARS_4_5 = slice(0, 36), slice(36, 60)    # monthly series: index k is month k + 1 after launch
LAMBDAS = np.linspace(0.0, 0.2, 4001)                 # the grid one leaving rate lambda is fitted on, a month
PLACEHOLDER = r"\textbf{??}"                          # what a number the result does not store is written as
TOL = 1e-9                                            # how far a value assumed constant may wander
# A distress level and the word a macro names it by.
LEVEL_WORDS = ((0.0, "Zero"), (0.005, "Half"), (0.01, "One"), (0.015, "OneHalf"), (0.02, "Two"))
# Circulation: yearly records by year after launch, index k is year k + 1; the paper's second window is years 4
# and 5. The arrangements read, and the people each covers: banks and cards have no network, so everyone (the
# engine files them all as non-participants); the three arrangements with a network are read for their
# participants (in the network at least half the year's months).
CIRCULATION_YEARS = slice(3, 5)
CIRCULATION_ARMS = ("S0", "M0", "U", "M1")
CIRCULATION_GROUP = dict(S0="non_participants", M0="participants", U="participants", M1="participants")
GROUP = "<group>"                                     # stands for the arrangement's group inside a stored path


class _Missing:
    """The marker for a key the stored JSON does not hold (as against a stored None, which means undefined)."""

    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


# ----------------------------------------------------------------------------------------------------------------------
# Formatting: per cent, dollars, shares and ranges, in LaTeX text mode
# ----------------------------------------------------------------------------------------------------------------------
def thousands(whole):
    """A whole number with LaTeX thousands separators: 4000 reads 4{,}000."""
    return f"{int(whole):,}".replace(",", "{,}")


def signed(body, negative):
    """``body`` with a typeset minus in front when ``negative``."""
    return ("$-$" + body) if negative else body


def pct(value, places):
    """A per cent figure to ``places`` decimals with its sign: 3.631 at 3 places reads 3.631\\%."""
    body = f"{abs(value):.{places}f}"
    return signed(body, value < 0 and float(body) > 0) + r"\%"


def usd(value):
    """Dollars: whole dollars from $10 up, one decimal below; the sign in front of the dollar sign."""
    size = abs(float(value))
    body = thousands(np.floor(size + 0.5)) if size >= 10 else f"{size:.1f}"   # round half up, not to even
    return signed(r"\$" + body, value < 0 and float(body.replace("{,}", "")) > 0)


def share(value, places=3):
    """A share or ratio as a plain decimal, three places by default."""
    body = f"{abs(value):.{places}f}"
    return signed(body, value < 0 and float(body) > 0)


def span(low, high, fmt):
    """A range written "low to high" (never with a dash); one value when both ends read the same."""
    a, b = fmt(low), fmt(high)
    return a if a == b else f"{a} to {b}"


def stored_places(values, most=4):
    """The decimals the runner stored ``values`` to: the most any finite value shows (3.631 shows 3), at most
    ``most``. Per cent figures are quoted to this precision."""
    seen = np.ravel(np.asarray(values, float))
    seen = seen[np.isfinite(seen)]
    # repr gives the shortest text that reads back the float, so a stored 3.631 shows exactly its three decimals.
    shown = [most if "e" in repr(float(v)) else len(repr(float(v)).split(".")[1].rstrip("0")) for v in seen]
    return min(max(shown, default=0), most)


def latex_pct_fmt(values):
    """The per cent formatter at the stored precision of ``values``."""
    places = stored_places(values)
    return lambda value: pct(value, places)


# ----------------------------------------------------------------------------------------------------------------------
# Reading the stored JSON
# ----------------------------------------------------------------------------------------------------------------------
def shipped_files(folder, name):
    """The files a store is shipped as in ``folder``, in order: ``name``.gz, or its volumes ``name``.gz.1of6 to .6of6
    (scripts/pack_results.py cuts a store over 50 MB into them); empty when the folder holds none."""
    folder = Path(folder)
    if (folder / (name + ".gz")).exists():
        return [folder / (name + ".gz")]
    found = sorted((int(m.group(1)), int(m.group(2)), p) for p in folder.glob(name + ".gz.*of*")
                   if (m := re.search(r"\.gz\.(\d+)of(\d+)$", p.name)))
    if [(k, n) for k, n, _ in found] != [(k, len(found)) for k in range(1, len(found) + 1)]:
        raise ValueError(f"{folder}: the volumes of {name} are not a whole set: {[p.name for _, _, p in found]}")
    return [p for _, _, p in found]


def stored_text(folder, name):
    """The text of one stored file of a results folder: ``name`` as the runner writes it, or as results are shipped,
    compressed (``shipped_files``; volumes are joined in order). None when the folder holds neither."""
    plain = Path(folder) / name
    if plain.exists():
        return plain.read_text(encoding="utf-8")
    files = shipped_files(folder, name)
    if not files:
        return None
    data = b"".join(gzip.decompress(p.read_bytes()) for p in files)
    with io.TextIOWrapper(io.BytesIO(data), encoding="utf-8") as source:     # line ends read as read_text reads them
        return source.read()


def dig(item, path):
    """The value at ``path`` (keys, or indices for lists) inside ``item``, or MISSING where the JSON stops short."""
    for key in path:
        if isinstance(item, dict) and key in item:
            item = item[key]
        elif isinstance(item, list) and isinstance(key, int) and -len(item) <= key < len(item):
            item = item[key]
        else:
            return MISSING
    return item


def column(items, path):
    """The float at ``path`` in each of ``items`` as an array (NaN where missing or None), and how many items do not
    hold the key at all."""
    found = [dig(item, path) for item in items]
    values = np.array([np.nan if v is MISSING or v is None else float(v) for v in found], float)
    return values, sum(v is MISSING for v in found)


def cell_key(item):
    """A cell's or job's place on the grid: (r_out, a0, distress) as floats."""
    return float(item["r_out"]), float(item["a0"]), float(item["distress"])


def stream_jobs(text):
    """The jobs of a compact store (measures.json), decoded one at a time, with the header before them: the runner
    writes the jobs as the store's last key, and a quote inside a JSON string is escaped, so the first '"jobs":['
    is the key itself."""
    opening = '"jobs":['
    start = text.find(opening)
    if start < 0:
        raise ValueError("measures.json holds no jobs list: not a store the population runner wrote")
    header = json.loads(text[:start] + '"jobs":[]}')            # the store without its jobs, for its provenance
    decoder, place, jobs = json.JSONDecoder(), start + len(opening), []
    while text[place] != "]":
        found, place = decoder.raw_decode(text, place)
        jobs.append(found)
        place += text[place] == ","                              # step over the comma between two jobs
    return header, jobs


def as_arrays(series):
    """One arm's monthly series as float arrays (None, undefined, becomes NaN)."""
    return {key: np.array(values, dtype=float) for key, values in series.items()}


def kept_monthly(job):
    """What this script keeps of a measures.json job: its place, seed, the monthly series of MONTHLY_KEPT and the
    yearly circulation records the circulation table reads (``kept_circulation``)."""
    arms = job.get("monthly") or {}
    return dict(r_out=job["r_out"], a0=job["a0"], distress=job["distress"], seed=job["seed"],
                recirculated=job.get("recirculated", False),
                monthly={arm: as_arrays(arms[arm]) for arm in MONTHLY_KEPT if arm in arms},
                circulation=kept_circulation(job))


def kept_circulation(job):
    """The yearly circulation records of one measures.json job, by arrangement (CIRCULATION_ARMS): for each stored
    path the circulation table reads (CIRCULATION_PATHS, the group filled in), its list by year after launch, or
    MISSING where the job does not store it. A few short lists a job, so the whole map's ``series`` is never kept."""
    series = job.get("series") or {}

    def one(arm, path):
        """One stored yearly list (or MISSING) at ``path`` with the arrangement's group in place of GROUP."""
        found = dig(series, [arm] + [CIRCULATION_GROUP[arm] if key == GROUP else key for key in path])
        return found if isinstance(found, list) else MISSING

    return {arm: {path_text(path): one(arm, path) for path in CIRCULATION_PATHS} for arm in CIRCULATION_ARMS}


def describe(cells):
    """The cells a number was computed from, compactly: the full product of their r_out, a0 and distress values
    when they form one, otherwise each cell listed."""
    if not cells:
        return "no cells"
    keys = sorted(map(cell_key, cells))
    rates, launches, levels = (sorted({k[i] for k in keys}) for i in range(3))
    name = lambda values, scale: ",".join(f"{v * scale:g}" for v in values)
    if len(keys) == len(rates) * len(launches) * len(levels):
        return (f"{len(keys)} cells: r_out {name(rates, 100)}% x a0 {name(launches, 1)} x distress "
                f"{name(levels, 100)} pt")
    return f"{len(keys)} cells: " + "; ".join(f"({r * 100:g}%, {a:g}, {d * 100:g} pt)" for r, a, d in keys)


class Store:
    """One stored map: summary.json's cells (the convention the map was run under), cells.json's jobs and the monthly
    series of measures.json, each indexed by grid place. Built from a folder (``from_folder``) or from dictionaries
    already in memory (the test)."""

    def __init__(self, summary, jobs=None, monthly=None, folder="(in memory)"):
        self.summary, self.folder = summary, str(folder)
        convention = bool(dig(summary, ["economy", "lender_income_recirculated"]) or False)
        # Only the cells of the map's own convention (lenders' interest kept or returned) are the map.
        self.cells = [c for c in summary.get("cells", [])
                      if c is not None and bool(c.get("recirculated")) == convention]
        keys = list(map(cell_key, self.cells))
        if len(set(keys)) != len(keys):
            raise ValueError(f"{self.folder}: two cells share a grid place, so every cell number is ambiguous")
        self.index = dict(zip(keys, self.cells))
        same = lambda j: bool(j.get("recirculated")) == convention
        self.jobs = self._by_place([j for j in (jobs or []) if same(j)])
        self.monthly = self._by_place([j for j in (monthly or []) if same(j)])
        self.has_jobs, self.has_monthly = jobs is not None, monthly is not None

    @staticmethod
    def _by_place(jobs):
        """Jobs grouped by grid place, each group in seed order."""
        found = {}
        for job in sorted(jobs, key=lambda j: j["seed"]):
            found.setdefault(cell_key(job), []).append(job)
        return found

    @classmethod
    def from_folder(cls, folder):
        """Read a results folder: summary.json (required), cells.json and measures.json (each optional; without one
        its numbers are placeholders). Refuses files written by different commits, which cannot be one map."""
        folder = Path(folder)
        # Each store is read as written by the runner (name.json) or as shipped, compressed (name.json.gz).
        texts = {name: stored_text(folder, name) for name in ("summary.json", "cells.json", "measures.json")}
        if texts["summary.json"] is None:
            raise FileNotFoundError(f"{folder} holds no summary.json: not a population map")
        summary = json.loads(texts["summary.json"])
        commit = dig(summary, ["provenance", "git_commit"])
        jobs = None if texts["cells.json"] is None else json.loads(texts["cells.json"])
        header, monthly = (None, None)
        if texts["measures.json"] is not None:
            header, raw = stream_jobs(texts["measures.json"])
            monthly = list(map(kept_monthly, raw))
        others = [(name, dig(stored, ["provenance", "git_commit"])) for name, stored in
                  (("cells.json", jobs), ("measures.json", header)) if stored is not None]
        mixed = [name for name, theirs in others if theirs != commit]
        if mixed:
            raise ValueError(f"{folder}: {', '.join(mixed)} written by a different commit than summary.json")
        found = cls(summary, None if jobs is None else jobs["jobs"], monthly, folder)
        # The spread of distress (scripts/spread_of_distress.py) is a reading of the map written after it, optional.
        spread = stored_text(folder, "spread.json")
        found.spread = None if spread is None else json.loads(spread)
        return found

    @classmethod
    def pending(cls, folder):
        """A set not yet run (its folder does not exist): a store with no cells, so every number read from it is a
        placeholder and the report says the set is pending."""
        found = cls(dict(cells=[]), None, None, folder)
        found.is_pending = True
        return found

    @classmethod
    def from_folder_or_pending(cls, folder):
        """``from_folder`` where the folder holds a summary.json, else ``pending``."""
        has = any((Path(folder) / name).exists() for name in ("summary.json", "summary.json.gz"))
        return cls.from_folder(folder) if has else cls.pending(folder)

    is_pending = False
    spread = None                             # spread.json's dictionary where the folder ships it

    def pick(self, distress=None, r_out=None, arm=None):
        """The map's cells at a distress level and outside rate (None: all), holding ``arm`` if given, in grid
        order."""
        keep = lambda k, c: ((distress is None or abs(k[2] - distress) < TOL) and (r_out is None or abs(k[0] - r_out)
                             < TOL) and (arm is None or arm in c))
        return [self.index[k] for k in sorted(self.index) if keep(k, self.index[k])]


# ----------------------------------------------------------------------------------------------------------------------
# The ledger: every number with its source, and everything not stored
# ----------------------------------------------------------------------------------------------------------------------
class Ledger:
    """The report being built: one line per number (where it goes, its text, where it came from) and one per thing
    the result does not store."""

    def __init__(self):
        self.lines, self.missing, self.notes = [], [], []

    def add(self, where, text, source):
        """Record that ``where`` (a macro or a table cell) reads ``text``, computed from ``source``."""
        self.lines.append(f"{where} = {text}    <- {source}")
        return text

    def lack(self, where, why):
        """Record that ``where`` is a placeholder because ``why``; returns the placeholder."""
        self.missing.append(f"{where}: {why}")
        self.lines.append(f"{where} = {PLACEHOLDER}    <- NOT STORED: {why}")
        return PLACEHOLDER


def reduce(ledger, where, values, absent, how, fmt, source):
    """One number from an array of per-cell (or per-seed) values: ``how`` names the statistic ("median", "mean",
    "low", "high", "range", "p10", "only"), ``fmt`` formats it. A key absent from any item, or a value undefined
    everywhere, gives the placeholder and a report line; never a number from part of the cells."""
    if values.size == 0:
        return ledger.lack(where, f"no cells to read ({source})")
    if absent:
        return ledger.lack(where, f"not stored in {absent} of {values.size} items: {source}")
    seen = values[np.isfinite(values)]
    if seen.size == 0:
        return ledger.lack(where, f"stored as undefined (None) in every item: {source}")
    reading = dict(median=lambda: fmt(np.median(seen)), mean=lambda: fmt(seen.mean()), low=lambda: fmt(seen.min()),
                   high=lambda: fmt(seen.max()), range=lambda: span(seen.min(), seen.max(), fmt),
                   p10=lambda: fmt(np.percentile(seen, 10)), only=lambda: constant_text(seen, fmt, where))[how]()
    defined = "" if seen.size == values.size else f", defined in {seen.size} of {values.size}"
    return ledger.add(where, reading, f"{how} of {source}{defined}")


def constant_text(values, fmt, where):
    """The one value of an array that must not vary; stops the script when it does."""
    if np.ptp(values) > TOL:
        raise ValueError(f"{where}: the values must be one number but range from {values.min()} to {values.max()}")
    return fmt(values[0])


def path_text(path):
    """A JSON path as text, keys joined by dots."""
    return ".".join(map(str, path))


def read(ledger, where, cells, path, how, fmt, file="summary.json"):
    """``reduce`` on ``path`` in each of the summary ``cells``, the source written as file, cells and path."""
    values, absent = column(cells, path)
    return reduce(ledger, where, values, absent, how, fmt, f"{file}: cells[{describe(cells)}].{path_text(path)}")


def failure_path(arm):
    """Where a cell stores an arrangement's failure share in the second window, % of spending: S0 at the cell's top
    level, every other arm inside its own block."""
    return ["S0_failures_pct"] if arm == "S0" else [arm, "failures_pct"]


# ----------------------------------------------------------------------------------------------------------------------
# Per-seed readings from cells.json and measures.json
# ----------------------------------------------------------------------------------------------------------------------
def seed_values(store, key, path):
    """One cell's per-seed values at ``path`` inside each cells.json job (NaN for None), and how many jobs lack it."""
    return column(store.jobs.get(key, []), path)


def monthly_block(store, key, arm, series):
    """One cell's monthly ``series`` of ``arm`` as a seeds x months array, or None where a seed does not store it."""
    found = [job["monthly"].get(arm, {}).get(series) for job in store.monthly.get(key, [])]
    if not found or any(values is None for values in found):
        return None
    return np.vstack(found)


def window_mean(block, span_):
    """Each seed's mean of a seeds x months block over the months ``span_`` (NaN where all are undefined)."""
    part = block[:, span_]
    seen = np.isfinite(part).sum(axis=1)
    return np.divide(np.nansum(part, axis=1), seen, out=np.full(seen.size, np.nan), where=seen > 0)


def bridges_served(store, key, arm=CPM):
    """Each seed's bridges served in years 4 and 5 (bridges drawn over bridges wanted): the runner's stored W2 figure
    in cells.json, else the mean of the stored monthly series over months 37 to 60. Returns (values, source) or
    (None, why)."""
    values, absent = seed_values(store, key, ["arms", arm, "bridges_drawn_over_wanted"])
    if values.size and not absent:
        return values, f"cells.json: jobs[{key}].arms.{arm}.bridges_drawn_over_wanted (W2 mean, each seed)"
    block = monthly_block(store, key, arm, "bridges_drawn_over_wanted")
    if block is not None:
        return (window_mean(block, YEARS_4_5),
                f"measures.json: jobs[{key}].monthly.{arm}.bridges_drawn_over_wanted[36:60]")
    return None, f"no per-seed bridges served for {key} (cells.json and measures.json)"


# ----------------------------------------------------------------------------------------------------------------------
# (1) The macros
# ----------------------------------------------------------------------------------------------------------------------
def seed_count(store, ledger, name):
    """The number of seeds a map ran, as the macro ``name``. Refuses a map whose cells ran another number."""
    seeds = dig(store.summary, ["seeds"])
    if seeds is MISSING:
        return ledger.lack(name, "summary.json: seeds")
    counts = {int(c.get("seeds", -1)) for c in store.cells}
    if counts and counts != {len(seeds)}:
        raise ValueError(f"cells ran {sorted(counts)} seeds but the map lists {len(seeds)}: the seed count is "
                         "ambiguous")
    return ledger.add(name, str(len(seeds)), f"{Path(store.folder).name}/summary.json: len(seeds), seed_set "
                      f"{dig(store.summary, ['seed_set'])!r}")


def macros(store, ledger, base=None):
    """Every macro the paper uses, as an ordered dict name -> LaTeX text, each recorded in ``ledger``. ``base`` is
    the development map the seed count was planned on (None: the map itself)."""
    out = {}
    summary = store.summary
    base = store if base is None else base
    n = dig(summary, ["economy", "n"])
    out["NumPeople"] = (ledger.lack("NumPeople", "summary.json: economy.n") if n is MISSING else
                        ledger.add("NumPeople", thousands(n), "summary.json: economy.n"))
    out["NumSeeds"] = seed_count(store, ledger, "NumSeeds")
    out["NumSeedsDev"] = seed_count(base, ledger, "NumSeedsDev")
    if dig(base.summary, ["seeds"]) is not MISSING and dig(base.summary, ["seed_set"]) != "development":
        ledger.notes.append(f"NumSeedsDev counts the {dig(base.summary, ['seed_set'])!r} seed set, not the "
                            "development seeds")
    zero, stress = store.pick(distress=0.0), store.pick(distress=HEADLINE)
    out.update(fixed_or_range(ledger, "FailBanks", zero, failure_path("S0")))
    out.update(low_high(ledger, "FailDefi", zero, failure_path("M0")))
    out.update(low_high(ledger, "FailCpm", zero, failure_path(CPM)))
    out.update(fixed_or_range(ledger, "FailBanksStress", stress, failure_path("S0")))
    out.update(low_high(ledger, "FailCpmStress", stress, failure_path(CPM)))
    out.update(low_high(ledger, "Charge", store.pick(distress=0.0, arm=CPM), [CPM, "c_pct"]))
    out["RunAdoption"] = run_adoption(store, ledger)
    out.update(prose_macros(store, ledger, base))
    out.update(circulation_macros(store, ledger))
    return out


def prose_macros(store, ledger, base=None):
    """The numbers the abstract and the running text quote, at the precision prose carries: one decimal for failure
    shares and bridge prices, two for the holding charge, whole dollars for gains. Each comes from the same stored
    fields as the tables and is recorded in the report in the same way. The seed plan is read on ``base``, the
    development map the confirmation count was fixed on (None: the map itself)."""
    zero, stress = store.pick(distress=0.0), store.pick(distress=HEADLINE)
    cpm, pool = store.pick(distress=0.0, arm=CPM), store.pick(distress=0.0, arm="U")
    one, two = (lambda v: pct(v, 1)), (lambda v: pct(v, 2))
    gain = lambda yard, *tail: [CPM, "against", yard, *tail, "gain_usd_a_year"]
    rescue_even = lambda yard: [CPM, "real_cost", "break_even_rescue_usd", f"against_{yard}", "cell"]
    completed_cents = lambda arm: [CPM, "real_cost", "cents_per_dollar_completed", arm]
    # Each macro: name, the cells it reads, the stored path, the statistic over cells, the format.
    specs = (("FailBanksMean", zero, failure_path("S0"), "mean", one),
             ("FailDefiMean", zero, failure_path("M0"), "mean", one),
             ("FailPoolMean", zero, failure_path("U"), "mean", one),
             ("FailCpmMean", zero, failure_path(CPM), "mean", one),
             ("FailBanksStressMean", stress, failure_path("S0"), "mean", one),
             ("FailDefiStressMean", stress, failure_path("M0"), "mean", one),
             ("FailCpmStressMean", stress, failure_path(CPM), "mean", one),
             ("GainBanksMedian", cpm, gain("S0"), "median", usd),
             ("GainBanksFaceMedian", cpm, gain("S0", "complete_gain", "face"), "median", usd),
             ("GainDefiMedian", cpm, gain("M0"), "median", usd),
             ("GainDefiFaceMedian", cpm, gain("M0", "complete_gain", "face"), "median", usd),
             ("GainBanksBoundLow", cpm, gain("S0", "bound"), "low", usd),
             ("GainDefiBoundLow", cpm, gain("M0", "bound"), "low", usd),
             ("RealCostBanksLow", cpm, [CPM, "against", "S0", "real_saving_usd_a_year", "total"], "low", usd),
             ("RealCostDefiLow", cpm, [CPM, "against", "M0", "real_saving_usd_a_year", "total"], "low", usd),
             ("RealCostDefiHigh", cpm, [CPM, "against", "M0", "real_saving_usd_a_year", "total"], "high", usd),
             # The two read-outs stored beside the real cost. The cost of one rescued payment at which CPM and the
             # yardstick use the same real resources (the model costs a rescue at $2), over the cells:
             ("RescueEvenDefiLow", cpm, rescue_even("M0"), "low", cents),
             ("RescueEvenDefiMedian", cpm, rescue_even("M0"), "median", cents),
             ("RescueEvenDefiHigh", cpm, rescue_even("M0"), "high", cents),
             ("RescueEvenBanksLow", cpm, rescue_even("S0"), "low", cents),
             ("RescueEvenBanksMedian", cpm, rescue_even("S0"), "median", cents),
             ("RescueEvenBanksHigh", cpm, rescue_even("S0"), "high", cents),
             # and each arrangement's real cost a year per dollar of purchases completed, in cents.
             ("CentsCompletedBanks", cpm, completed_cents("S0"), "mean", lambda v: f"{v:.3f}"),
             ("CentsCompletedDefi", cpm, completed_cents("M0"), "mean", lambda v: f"{v:.3f}"),
             ("CentsCompletedCpm", cpm, completed_cents(CPM), "mean", lambda v: f"{v:.3f}"),
             # The share of people more than $2 a year behind the yardstick, completed purchases at their price.
             ("ShareBehindBanks", cpm, [CPM, "against", "S0", "dispersion", "face", "below_margin_share"], "median",
              lambda v: pct(100 * v, 1)),
             ("ShareBehindDefi", cpm, [CPM, "against", "M0", "dispersion", "face", "below_margin_share"], "median",
              lambda v: pct(100 * v, 1)),
             # The same share in money alone, and the gain in money of the median person and of the person at the
             # fifth percentile, each the median over cells.
             ("ShareBehindBanksMoney", cpm, [CPM, "against", "S0", "dispersion", "wealth", "below_margin_share"],
              "median", lambda v: pct(100 * v, 1)),
             ("ShareBehindDefiMoney", cpm, [CPM, "against", "M0", "dispersion", "wealth", "below_margin_share"],
              "median", lambda v: pct(100 * v, 1)),
             ("PersonMedianBanks", cpm, [CPM, "against", "S0", "dispersion", "wealth", "percentiles_usd_a_year", "50"],
              "median", usd),
             ("PersonMedianDefi", cpm, [CPM, "against", "M0", "dispersion", "wealth", "percentiles_usd_a_year", "50"],
              "median", usd),
             ("PersonFifthBanks", cpm, [CPM, "against", "S0", "dispersion", "wealth", "percentiles_usd_a_year", "5"],
              "median", usd),
             ("PersonFifthDefi", cpm, [CPM, "against", "M0", "dispersion", "wealth", "percentiles_usd_a_year", "5"],
              "median", usd),
             ("ChargeFrom", cpm, [CPM, "c_pct"], "low", two),
             ("ChargeTo", cpm, [CPM, "c_pct"], "high", two),
             ("BridgePriceCpm", cpm, [CPM, "r_b_pct"], "mean", one),
             ("BridgePricePoolLow", pool, ["U", "r_b_pct"], "low", one),
             ("BridgePricePoolHigh", pool, ["U", "r_b_pct"], "high", one))
    out = {name: read(ledger, name, cells, path, how, fmt) for name, cells, path, how, fmt in specs}
    # The claim read on a majority of seeds, over the cells with no distress (``majority_code``).
    codes = np.array([majority_code(cell) for cell in cpm])
    source = f"summary.json cells[{describe(cpm)}].{CPM}.region.verdict_majority and .verdict_majority_bound"
    out["CellsNoDistress"] = ledger.add("CellsNoDistress", str(len(cpm)), f"count of {describe(cpm)}")
    out["StableAsBuilt"] = ledger.add("StableAsBuilt", str(int((codes >= 2).sum())), "stable as built: " + source)
    out["StableBoth"] = ledger.add("StableBoth", str(int((codes == 3).sum())), "stable both ways: " + source)
    out.update(grid_macros(store, ledger))
    out.update(buys_macros(store, ledger))
    out.update(owners_macros(store, ledger))
    out.update(seed_macros(store if base is None else base, ledger))
    out.update(claim_macros(store, ledger))
    out.update(group_macros(store, ledger))
    out.update(lender_macros(store, ledger))
    return out


LENDER_SHARE = 0.10                          # the sourced share of outside lenders' income that returns to households


def lender_macros(store, ledger):
    """The household gain when a share of outside lenders' income returns to households as the lenders' owners, read
    from the map as stored as a ledger line with no change in behaviour: CPM's gain in money over each yardstick less
    LENDER_SHARE times the income CPM takes away from outside lenders (what households pay them under the yardstick
    less what they pay under CPM, a person a year). Also the share at which that gain reaches zero. Medians over the
    cells with no distress."""
    cells = store.pick(distress=0.0, arm=CPM)
    months = dig(store.summary, ["economy", "months"])
    if months is MISSING or not cells:
        return {name: ledger.lack(name, "summary.json: economy.months, or no cell with no distress")
                for name in ("GainBanksShared", "GainDefiShared", "LenderShareZeroBanks", "LenderShareZeroDefi")}
    paid_path = lambda arm: (["S0_transfers"] if arm == "S0" else [arm, "transfers"]) + ["outside_lenders", "paid_usd"]
    mine, lacking = column(cells, paid_path(CPM))

    def pair(name, yard):
        """The two macros against one yardstick."""
        theirs, absent = column(cells, paid_path(yard))
        gain, missing = column(cells, [CPM, "against", yard, "gain_usd_a_year"])
        less = (theirs - mine) * 12 / months                                  # $ a person a year
        source = (f"summary.json: cells[{describe(cells)}]: {CPM}.against.{yard}.gain_usd_a_year and "
                  f"{path_text(paid_path(yard))} less {path_text(paid_path(CPM))}, over {months} months")
        gaps = lacking + absent + missing
        zero_at = np.divide(gain, less, out=np.full(gain.shape, np.nan), where=less > 0)
        return {f"Gain{name}Shared": reduce(ledger, f"Gain{name}Shared", gain - LENDER_SHARE * less, gaps, "median",
                                             usd, f"gain less {LENDER_SHARE} of the lenders' income taken away; "
                                             + source),
                f"LenderShareZero{name}": reduce(ledger, f"LenderShareZero{name}", zero_at, gaps, "median",
                                                 lambda v: share(v, 2), "gain over the lenders' income taken away; "
                                                 + source)}

    return {**pair("Banks", "S0"), **pair("Defi", "M0")}


CONFIRMATION_SEEDS = CONFIRMATION_COUNT     # the registered confirmation count, against which cells are judged
GRID_SOURCE = "src/cpm_abm/experiment/grid.py"
# The arms whose Bonferroni level the yes-or-no readings are quoted at: CPM over its cells and indexed CPM over its own.
WILSON_LEVELS = (("", None), ("Bonf", CPM), ("BonfIndexed", "M2"))


def fewest_above_half(total, alpha):
    """The fewest of ``total`` seeds whose share has its Wilson lower bound at 1 - alpha above one half
    (``wilson_bounds``). Example: of 30 seeds 21 at 95%, 24 at the Bonferroni level over 21 cells and 23 over 14;
    of 60, 38, 42 and 42."""
    return next(hits for hits in range(total + 1) if wilson_bounds(hits, total, alpha)[0] > 0.5)


def arm_alpha(arm):
    """An arm's Bonferroni level as the code sets it (``bonferroni_cells`` at the engine's inflation): 0.05 over 21
    cells for CPM and over 14 for indexed CPM."""
    return CLAIM_ALPHA / bonferroni_cells(arm, SimpleNamespace(inflation=Economy.inflation))


def cents_down(value):
    """Dollars to the cent below, so a spread quoted as resolved is one that is: 2.597 reads \\$2.59."""
    return r"\$" + f"{np.floor(value * 100 + 1e-9) / 100:.2f}"


def assured_reading(reading, seeds_per_cell, alpha):
    """One stored planner reading's assured seeds: its spread at the upper end of its
    one-sided interval at SEED_ASSURANCE (``spread_bound``), its degrees of freedom stored or, in a map stored before
    the rule, cells x (seeds - 1), and the seeds that bound needs at the reading's margin (``seeds_needed``; None
    beyond its reach). Returns (freedom, bound, seeds)."""
    freedom = reading.get("freedom")
    if freedom is None:
        freedom = int(reading["cells"]) * (seeds_per_cell - 1)
    bound = spread_bound(reading["spread"], freedom)
    margin = abs(CLAIM_MARGIN) if reading["reading"].startswith("cost") else DIP_MARGIN
    return freedom, bound, seeds_needed(bound, margin, alpha)


def assured_macros(store, ledger):
    """The planner's assured count on this map, from the readings its summary holds: the largest over the readings
    of the seeds each needs with its spread at the bound, at most SEED_CAP, with the reading that sets it (its
    spread, degrees of freedom and bound)."""
    names = ("SeedsAssured", "SpreadBinding", "FreedomBinding", "SpreadBindingBound")
    path = "summary.json: claim_statistics.seeds.readings"
    readings = dig(store.summary, ["claim_statistics", "seeds", "readings"])
    levels = dig(store.summary, ["claim_statistics", "bonferroni"])
    seeds = dig(store.summary, ["seeds"])
    if MISSING in (readings, levels, seeds) or not readings:
        return {name: ledger.lack(name, f"{path}, claim_statistics.bonferroni or seeds") for name in names}
    found = []
    for reading in readings:
        if reading.get("spread") is None:
            continue
        freedom, bound, needed = assured_reading(reading, len(seeds), levels[reading["arm"]]["alpha"])
        found.append((np.inf if needed is None else needed, reading, freedom, bound))
    if not found:
        return {name: ledger.lack(name, f"no reading with a spread in {path}") for name in names}
    # The reading that sets the count; at a tie, the one with the larger bound.
    most, binding, freedom, bound = max(found, key=lambda entry: (entry[0], entry[3]))
    where = (f"{path}[{binding['arm']}, {binding['reading']}, distress {binding['distress']}], "
             f"{len(seeds)} seeds a cell, at claim_statistics.bonferroni.{binding['arm']}.alpha")
    rule = f"spread_bound at assurance {SEED_ASSURANCE}, then seeds_needed at power {SEED_POWER}, at most {SEED_CAP}"
    return dict(
        SeedsAssured=ledger.add("SeedsAssured", str(int(min(most, SEED_CAP))),
                                f"largest over {len(found)} readings of {path}: {rule}; set by {where}"),
        SpreadBinding=ledger.add("SpreadBinding", f"{binding['spread']:.4f}", f"spread of {where}"),
        FreedomBinding=ledger.add("FreedomBinding", str(int(freedom)),
                                  f"freedom of {where}" if binding.get("freedom") is not None else
                                  f"cells x (seeds - 1) of {where}"),
        SpreadBindingBound=ledger.add("SpreadBindingBound", f"{bound:.3f}", f"{rule.split(',')[0]} of {where}"))


def design_macros(ledger):
    """The registered seed design, from the code: the confirmation count, its extension and the assurance; at each
    count the fewest seeds whose share reads above one half at 95% and at the Bonferroni levels; and the largest
    spread at which the confirmation count resolves the $2 margin at CPM's Bonferroni level with 80% power."""
    out = dict(SeedsConfirm=ledger.add("SeedsConfirm", str(CONFIRMATION_COUNT), f"{GRID_SOURCE}: CONFIRMATION_COUNT"),
               SeedsExtended=ledger.add("SeedsExtended", str(CONFIRMATION_EXTENSION),
                                        f"{GRID_SOURCE}: CONFIRMATION_EXTENSION"),
               SeedAssurance=ledger.add("SeedAssurance", f"{SEED_ASSURANCE:g}",
                                        "src/cpm_abm/experiment/notes.py: SEED_ASSURANCE"))
    counts = (("WilsonConfirm", CONFIRMATION_COUNT, "CONFIRMATION_COUNT"),
              ("WilsonExtended", CONFIRMATION_EXTENSION, "CONFIRMATION_EXTENSION"))
    for (stem, total, name), (tail, arm) in product(counts, WILSON_LEVELS):
        alpha = CLAIM_ALPHA if arm is None else arm_alpha(arm)
        level = "95%" if arm is None else f"{arm}'s Bonferroni level, alpha {alpha:.6f}"
        out[stem + tail] = ledger.add(stem + tail, str(fewest_above_half(total, alpha)),
                                      f"fewest of {name} = {total} with wilson_bounds lower above 0.5 at {level}")
    resolved = spread_resolved(CONFIRMATION_COUNT, abs(CLAIM_MARGIN), arm_alpha(CPM))
    out["SpreadResolved"] = ledger.add("SpreadResolved", cents_down(resolved),
                                       f"spread_resolved({CONFIRMATION_COUNT}, {abs(CLAIM_MARGIN)}, "
                                       f"{CPM}'s Bonferroni level) = {resolved:.4f}, to the cent below")
    return out


def seed_macros(store, ledger):
    """The seed planner's reading of this map: its own count over all planned readings, its assured count, the most
    seeds any cell with no distress needs on its own spread, and how many such cells need more than the confirmation
    count; then the registered seed design (``design_macros``)."""
    planned = dig(store.summary, ["claim_statistics", "seeds", "seeds"])
    cells = store.pick(distress=0.0, arm=CPM)
    needed, absent = column(cells, [CPM, "claim", "seeds_needed"])
    source = f"summary.json: cells[{describe(cells)}].{CPM}.claim.seeds_needed"
    whole = lambda v: str(int(round(v)))
    over = np.array([float(np.sum(needed[np.isfinite(needed)] > CONFIRMATION_SEEDS))])
    return dict(
        SeedsPlanned=(ledger.lack("SeedsPlanned", "summary.json: claim_statistics.seeds.seeds") if planned is MISSING
                      or planned is None else ledger.add("SeedsPlanned", str(int(planned)),
                                                         "summary.json: claim_statistics.seeds.seeds")),
        **assured_macros(store, ledger),
        SeedsCellMost=reduce(ledger, "SeedsCellMost", needed, absent, "high", whole, source),
        CellsUnderpowered=reduce(ledger, "CellsUnderpowered", over, absent, "only",
                                 lambda v: "no" if v == 0 else whole(v),
                                 f"count above {CONFIRMATION_SEEDS} of {source}"),
        **design_macros(ledger))


# The claim's counts over the cells with no distress that the running text quotes: macro, what a cell does to be
# counted, the test on its claim block, and how the count is written.
NONE_AS_NO = lambda count: "no" if count == 0 else str(count)
CLAIM_COUNTS = (("ClaimCellsAsBuilt", "passes (a), (b) and (d) as built", lambda b: flag(b, "all_as_built"), str),
                ("ClaimCellsBoth", "passes as built and under the cash-advance bound",
                 lambda b: bounded(b, flag(b, "all")), str),
                ("ClaimCellsFalsified", "has a falsifier fire", lambda b: flag(dig(b, ["worse_than_M0"]), "fires"),
                 NONE_AS_NO),
                ("ClaimCellsUnderpowered", "is underpowered at the seeds the map ran",
                 lambda b: flag(b, "underpowered"), NONE_AS_NO))


def claim_macros(store, ledger):
    """The registered claim as the map's summary stores it, for the running text: the cells in CPM's region at each
    distress level; over the cells with no distress, how many pass without the bound, pass also under the
    cash-advance bound, have a falsifier fire and are underpowered at the seeds the map ran (CLAIM_COUNTS); the
    cells that pass at the Bonferroni level; and the seed planner's reading of this map, its count and the most
    seeds a cell with no distress needs on its own spread."""
    out = {}
    slices = dig(store.summary, ["claim_statistics", "regions", CPM])
    for level, word in LEVEL_WORDS:
        name = f"RegionCells{word}"
        where = f"summary.json: claim_statistics.regions.{CPM}, distress {level:g}"
        found = [] if slices is MISSING else [s for s in slices if abs(s["distress"] - level) < TOL]
        out[name] = (ledger.add(name, str(len(found[0]["region"])), where + ": cells in region") if found else
                     ledger.lack(name, where))
    cells = store.pick(distress=0.0, arm=CPM)
    blocks = [dig(c, [CPM, "claim"]) for c in cells]
    for name, what, test, fmt in CLAIM_COUNTS:
        found = [None if b is MISSING else test(b) for b in blocks]
        where = f"summary.json: cells[{describe(cells)}].{CPM}.claim: a cell {what}"
        out[name] = (ledger.lack(name, where) if not found or any(f is None for f in found) else
                     ledger.add(name, fmt(sum(found)), where))
    holds = dig(store.summary, ["claim_statistics", "holds_somewhere", CPM])
    where = f"summary.json: claim_statistics.holds_somewhere.{CPM}"
    out["ClaimHoldsSomewhere"] = (ledger.lack("ClaimHoldsSomewhere", where) if holds is MISSING else
                                  ledger.add("ClaimHoldsSomewhere", str(len(holds)), "count of " + where))
    planned = dig(store.summary, ["claim_statistics", "seeds", "seeds"])
    where = "summary.json: claim_statistics.seeds.seeds"
    out["ClaimSeedsPlanned"] = (ledger.lack("ClaimSeedsPlanned", where) if planned is MISSING or planned is None else
                                ledger.add("ClaimSeedsPlanned", str(int(planned)), where))
    needed, absent = column(cells, [CPM, "claim", "seeds_needed"])
    out["ClaimSeedsCellMost"] = reduce(ledger, "ClaimSeedsCellMost", needed, absent, "high",
                                       lambda v: str(int(round(v))),
                                       f"summary.json: cells[{describe(cells)}].{CPM}.claim.seeds_needed")
    out.update(indexed_macros(store, ledger))
    return out


INDEXED = "M2"                                        # indexed CPM, the runner's name


def indexed_macros(store, ledger):
    """Indexed CPM's own registered reading: the cells in its region at each distress level (IndexedRegion + the
    level's word); the cells with no distress in which it is defined, the rest being its declared limit
    (IndexedValid); the cells that pass at its Bonferroni level (IndexedHolds); and over the defined cells the
    median gain in money over banks and cards and over best-case DeFi, with CPM's at the same cells beside
    (IndexedGainBanks, IndexedGainDefi, IndexedCpmGainBanks, IndexedCpmGainDefi)."""
    out = {}
    slices = dig(store.summary, ["claim_statistics", "regions", INDEXED])
    for level, word in LEVEL_WORDS:
        name = f"IndexedRegion{word}"
        where = f"summary.json: claim_statistics.regions.{INDEXED}, distress {level:g}"
        found = [] if slices is MISSING else [s for s in slices if abs(s["distress"] - level) < TOL]
        out[name] = (ledger.add(name, str(len(found[0]["region"])), where + ": cells in region") if found else
                     ledger.lack(name, where))
    cells = store.pick(distress=0.0, arm=INDEXED)
    limits = [dig(c, [INDEXED, "region", "declared_limit"]) for c in cells]
    where = f"summary.json: cells[{describe(cells)}].{INDEXED}.region.declared_limit"
    if not cells or any(limit is MISSING for limit in limits):
        out["IndexedValid"] = ledger.lack("IndexedValid", where)
        valid = []
    else:
        valid = [c for c, limit in zip(cells, limits) if not limit]
        out["IndexedValid"] = ledger.add("IndexedValid", str(len(valid)), where + " is false")
    holds = dig(store.summary, ["claim_statistics", "holds_somewhere", INDEXED])
    where = f"summary.json: claim_statistics.holds_somewhere.{INDEXED}"
    out["IndexedHolds"] = (ledger.lack("IndexedHolds", where) if holds is MISSING else
                           ledger.add("IndexedHolds", str(len(holds)), "count of " + where))
    for name, arm, yard in (("IndexedGainBanks", INDEXED, "S0"), ("IndexedGainDefi", INDEXED, "M0"),
                            ("IndexedCpmGainBanks", CPM, "S0"), ("IndexedCpmGainDefi", CPM, "M0")):
        out[name] = read(ledger, name, valid, [arm, "against", yard, "gain_usd_a_year"], "median", usd)
    return out


# The group clause by leg, for the running text: macro, the claim block (without the bound, or under the cash-advance
# bound) and the leg (against best-case DeFi with completed purchases at their price; against banks and cards at
# the zero end of the bracket, the complete gain with a seller's extra sales valued at nothing, which for a group is
# not its gain in money alone).
GROUP_LEGS = (("GroupLowDefiFace", "d", "M0_face"), ("GroupLowDefiFaceBound", "d_bound", "M0_face"),
              ("GroupLowBanksZero", "d", "S0_zero"), ("GroupLowBanksZeroBound", "d_bound", "S0_zero"))
# What every seed of every cell is checked for in the report's notes: the stored share and what it says.
STANDING = (("pool_formed_share", "the pool forms"), ("households_hold_90_W2_share", "households hold 90% of it"),
            ("issuer_never_leaves_share", "the issuer never leaves"))


def group_macros(store, ledger):
    """The group clause over the cells with no distress, for the running text: by leg (GROUP_LEGS) the lowest 95%
    lower bound of any group's gain in any cell, with the cell and group in the report; the fewest persistent
    seeds in any such cell; and, as notes, whether in every seed of every cell of the grid the pool forms,
    households hold it and the issuer stays (STANDING)."""
    cells = store.pick(distress=0.0, arm=CPM)
    out = {}
    for name, clause, leg in GROUP_LEGS:
        path = [CPM, "claim", clause, "at_95", "groups", leg]
        found = [dig(c, path) for c in cells]
        where = f"summary.json: cells[{describe(cells)}].{path_text(path)}.<group>.lower, the lowest"
        if not found or any(f is MISSING or not f for f in found):
            out[name] = ledger.lack(name, where)
            continue
        entries = lambda c, groups: ((g["lower"], cell_key(c), group) for group, g in groups.items())
        low = min(chain.from_iterable(map(entries, cells, found)))     # every group of every cell, in order
        out[name] = ledger.add(name, usd(low[0]), f"{where}: cell {low[1]}, group {low[2]}")
    seeds, absent = column(cells, [CPM, "region", "persistent_seeds"])
    out["SeedsPersistentLeast"] = reduce(ledger, "SeedsPersistentLeast", seeds, absent, "low",
                                         lambda v: str(int(round(v))), f"summary.json: cells[{describe(cells)}]."
                                         f"{CPM}.region.persistent_seeds")
    every = store.pick(arm=CPM)
    for key, what in STANDING:
        shares, missing = column(every, [CPM, key])
        if every and not missing and np.isfinite(shares).all():
            ledger.notes.append(f"{what} in every seed of every one of {len(every)} cells: {bool((shares >= 1).all())} "
                                f"(lowest summary.json cells[].{CPM}.{key} is {shares.min():g})")
    return out


# The two readings of the entry rule side by side, the confirmation map with savers acting on the published quote
# and with savers acting on the pool's realised record: the row's label, its macro stem, the stored path, the
# statistic over the cells with no distress and the format.
READING_ROWS = (
    ("Bridges served, CPM", "ServedCpm", [CPM, "bridges_drawn_over_wanted"], lambda v: share(v, 2)),
    ("Bridges served, pool without the charge", "ServedPool", ["U", "bridges_drawn_over_wanted"], lambda v: share(v, 2)),
    ("Bridge price, CPM", "PriceCpm", [CPM, "r_b_pct"], lambda v: pct(v, 1)),
    ("Bridge price, pool without the charge", "PricePool", ["U", "r_b_pct"], lambda v: pct(v, 1)),
    ("Payments that fail, banks and cards", "FailBanks", ["S0_failures_pct"], lambda v: pct(v, 2)),
    ("Payments that fail, pool without the charge", "FailPool", ["U", "failures_pct"], lambda v: pct(v, 2)),
    ("Payments that fail, CPM", "FailCpm", [CPM, "failures_pct"], lambda v: pct(v, 2)),
    ("Gain over banks and cards", "GainBanks", [CPM, "against", "S0", "gain_usd_a_year"], usd),
    ("Gain over best-case DeFi", "GainDefi", [CPM, "against", "M0", "gain_usd_a_year"], usd),
    ("Gain over the pool without the charge", "GainOverPool", [CPM, "against", "U", "gain_usd_a_year"], usd))
READING_LABELS = ("Cells in the registered region, no distress", "Seeds in which the pool persists",
                  "Pool capital over its target", *(row[0] for row in READING_ROWS),
                  "Cells of the grid with every gain positive", "Cells of the grid with fewer failed payments than both")


def reading_column(store, ledger, tag):
    """One reading's column of the two-readings table, in the order of READING_LABELS, and its macros, each named
    Read + ``tag`` + its stem. Medians are over the cells with no distress; the last two rows count over the grid."""
    cells = store.pick(distress=0.0, arm=CPM)
    name, src = (lambda stem: f"Read{tag}{stem}"), file_of(store)
    out, shown = {}, []

    def keep(stem, text):
        out[name(stem)] = text
        shown.append(text)

    slices = dig(store.summary, ["claim_statistics", "regions", CPM])
    zero = [] if slices is MISSING else [s for s in slices if abs(s["distress"]) < TOL]
    where = f"{src}: claim_statistics.regions.{CPM}, distress 0"
    keep("Region", ledger.add(name("Region"), str(len(zero[0]["region"])), where + ": cells in region") if zero else
         ledger.lack(name("Region"), where))
    seeds, absent = column(cells, [CPM, "region", "persistent_seeds"])
    whole, source = (lambda v: str(int(round(v)))), f"{src}: cells[{describe(cells)}].{CPM}.region.persistent_seeds"
    low = reduce(ledger, name("PersistentLow"), seeds, absent, "low", whole, source)
    high = reduce(ledger, name("PersistentHigh"), seeds, absent, "high", whole, source)
    out[name("PersistentLow")], out[name("PersistentHigh")] = low, high
    shown.append(low if low == high else f"{low} to {high}")
    capital, lacking = column(cells, [CPM, "N"])
    target, missing = column(cells, [CPM, "N_star"])
    ratio = np.divide(capital, target, out=np.full(capital.shape, np.nan), where=target > 0)
    keep("Capital", reduce(ledger, name("Capital"), ratio, lacking + missing, "median", lambda v: share(v, 2),
                           f"{src}: cells[{describe(cells)}].{CPM}.N over .{CPM}.N_star"))
    for _, stem, path, fmt in READING_ROWS:
        keep(stem, read(ledger, name(stem), cells, path, "median", fmt, file=src))
    count, positive, fewer = grid_counts(store)
    keep("GainPositive", ledger.add(name("GainPositive"), str(positive),
                                    f"{src}: cells of {count} with every reading of the gain above zero"))
    keep("FewerFailures", ledger.add(name("FewerFailures"), str(fewer),
                                     f"{src}: cells of {count} in which CPM fails fewer payments than both"))
    return shown, out


def readings_table(store, second, ledger):
    """The confirmation map under the two entry readings, ``store`` (savers act on the published quote) and
    ``second`` (savers act on the pool's realised record): the table and the macros of both columns."""
    first, macros_first = reading_column(store, ledger, "First")
    other, macros_second = reading_column(second, ledger, "Second")
    rows = [[label, a, b] for label, a, b in zip(READING_LABELS, first, other)]
    table = dict(spec="lrr", head=["", "Quote rule", "Record rule"], rows=rows,
                 rule_before=[3, 3 + len(READING_ROWS)])
    lower = {}
    for name, yard in (("ReadSecondGainBanksLower", "S0"), ("ReadSecondGainDefiLower", "M0")):
        path = [CPM, "against", yard, "gain_usd_a_year"]
        levels = [(lambda values, absent: np.nan if absent or not values.size else float(np.nanmedian(values)))(
            *column(one.pick(distress=0.0, arm=CPM), path)) for one in (second, store)]
        lower[name] = change_macro(ledger, name, *levels, f"median over the cells with no distress of {path_text(path)}, "
                                   f"{file_of(second)} against {file_of(store)}")
    slices = dig(second.summary, ["claim_statistics", "regions", CPM])
    stressed = [] if slices is MISSING else [s for s in slices if abs(s["distress"] - HEADLINE) < TOL]
    where = f"{file_of(second)}: claim_statistics.regions.{CPM}, distress {HEADLINE:g}"
    lower["ReadSecondRegionTwo"] = (ledger.add("ReadSecondRegionTwo", str(len(stressed[0]["region"])),
                                               where + ": cells in region") if stressed else
                                    ledger.lack("ReadSecondRegionTwo", where))
    return table, {**macros_first, **macros_second, **lower}


# The pool's path: what the path table reads of CPM's monthly records, the word each year after launch is named by
# in a macro, and the table's columns for each reading (macro stem, heading).
PATH_SERIES = ("N", "Q", "bridges_drawn_over_wanted")
YEAR_WORDS = ("One", "Two", "Three", "Four", "Five")
PATH_COLUMNS = (("Ratio", "Capital over target"), ("Capital", r"Capital, \$"), ("Target", r"Target, \$"),
                ("Served", "Bridges served"))


def yearly(block):
    """A seeds x months block as seeds x years means over the whole years from launch (NaN for a year with no
    defined month)."""
    count = block.shape[1] // 12
    part = block[:, :count * 12].reshape(block.shape[0], count, 12)
    seen = np.isfinite(part).sum(axis=2)
    return np.divide(np.nansum(part, axis=2), seen, out=np.full(seen.shape, np.nan), where=seen > 0)


def path_columns(store, ledger, tag):
    """One reading's columns of the path table and its macros (Path + ``tag`` + the column's stem + the year's
    word): for each year after launch the median over the cells with no distress of the seed mean of pool capital
    over its target, capital and the target in dollars a person, and bridges served, each a mean of the year's
    months."""
    cells, out = store.pick(distress=0.0, arm=CPM), {}
    unit = dig(store.summary, ["constants", "MONTH_USD"])
    folder = Path(store.folder).name
    blocks = {key: {name: monthly_block(store, key, CPM, name) for name in PATH_SERIES} for key in map(cell_key, cells)}
    lacking = [key for key, found in blocks.items() if any(block is None for block in found.values())]
    source = f"{folder}/measures.json: jobs in cells[{describe(cells)}].monthly.{CPM}"
    if not cells or lacking or unit is MISSING:
        why = f"{source}: {', '.join(PATH_SERIES)} not stored for every seed, or no cells, or no MONTH_USD"
        columns = [[ledger.lack(f"Path{tag}{stem}{word}", why) for stem, _ in PATH_COLUMNS] for word in YEAR_WORDS]
        out.update({f"Path{tag}{stem}{word}": PLACEHOLDER for (stem, _), word in product(PATH_COLUMNS, YEAR_WORDS)})
        return columns, out

    def by_year(found):
        """One cell's four paths by year after launch, the seed mean of each year: capital over its target, capital
        and the target in dollars a person, and bridges served (the stems of ``PATH_COLUMNS``)."""
        capital, target = found["N"], found["Q"]
        ratio = np.divide(capital, target, out=np.full(capital.shape, np.nan), where=target > 0)
        paths = dict(Ratio=ratio, Capital=capital * float(unit), Target=target * float(unit),
                     Served=found["bridges_drawn_over_wanted"])
        return {stem: np.nanmean(yearly(block), axis=0) for stem, block in paths.items()}

    by_cell = [by_year(found) for found in blocks.values()]
    formats = dict(Ratio=lambda v: share(v, 2), Capital=usd, Target=usd, Served=lambda v: share(v, 2))

    def year_row(k, word):
        """The table's row for year ``k + 1`` after launch: each column's median over the cells, written as its
        macro."""
        row = []
        for stem, _ in PATH_COLUMNS:
            values = np.array([cell[stem][k] if k < cell[stem].size else np.nan for cell in by_cell], float)
            name = f"Path{tag}{stem}{word}"
            out[name] = reduce(ledger, name, values, 0, "median", formats[stem],
                               f"{source}: year {k + 1} after launch, the seed mean in each cell")
            row.append(out[name])
        return row

    return [year_row(k, word) for k, word in enumerate(YEAR_WORDS)], out


def path_table(store, second, ledger):
    """The pool year by year after launch under the two entry readings, ``store`` (savers act on the published quote)
    and ``second`` (savers act on the pool's realised record), with no distress: the table and both readings'
    macros (``path_columns``)."""
    first, macros_first = path_columns(store, ledger, "First")
    other, macros_second = path_columns(second, ledger, "Second")
    rows = [[str(k + 1), *a, *b] for k, (a, b) in enumerate(zip(first, other))]
    width = len(PATH_COLUMNS)
    over = (f" & \\multicolumn{{{width}}}{{c}}{{Quote rule}}"
            f" & \\multicolumn{{{width}}}{{c}}{{Record rule}} \\\\")
    head = ["Year after launch"] + [title for _, title in PATH_COLUMNS] * 2
    return dict(spec="l" + "r" * (2 * width), over=over, head=head, rows=rows), {**macros_first, **macros_second}


# CPM's gain in money over banks and cards split by the flow it comes from (each cell's ``split``, dollars a person
# over the run): the row's macro stem, its label and the components of the split it adds up.
SOURCE_ROWS = (("Yield", "Reserve return on P and other outside income", ("other_outside_flows",)),
               ("Interest", "Interest saved on outside loans", ("outside_interest_saved",)),
               ("Card", "Card fees saved, less rewards given up", ("card_fees_saved", "card_rewards")),
               ("Fees", "Cash-advance, late and failure fees saved",
                ("advance_fees_saved", "late_fees_saved", "penalties_saved")),
               ("Pool", "The pool's operating cost", ("pool_costs",)),
               ("Savings", "Savings income given up, inflation and valuation",
                ("savings_income", "inflation", "valuation")),
               ("Other", "Conversion fees, gas and wages to the outside",
                ("conversion_fees_saved", "gas_to_validators", "wages_to_outside")))
RATE_WORDS = {0.02: "Two", 0.044: "FourFour", 0.06: "Six"}    # the grid's outside rates and their macro words


def sources_table(store, ledger):
    """Where CPM's gain in money over banks and cards comes from with no distress, by outside rate: the median over
    launch levels of each group of the stored split, a year, and of their sum. The macros name each row and the sum
    by rate (Source + the row's stem + the rate's word)."""
    months, rates = dig(store.summary, ["economy", "months"]), dig(store.summary, ["r_out"])
    out = {}
    if MISSING in (months, rates):
        return dict(spec="l", head=[""], rows=[[ledger.lack("sources", "summary.json: economy.months or r_out")]]), out
    cells = {rate: store.pick(distress=0.0, r_out=rate, arm=CPM) for rate in rates}
    where = lambda rate: f"summary.json: cells[{describe(cells[rate])}]"

    def entry(label, stem, rate, values, absent, fmt, source):
        """One number of the table, and its macro where the row has a stem."""
        text = reduce(ledger, f"sources[{label}, rate {rate * 100:g}%]", values, absent, "median", fmt, source)
        if stem and rate in RATE_WORDS:
            name = f"Source{stem}{RATE_WORDS[rate]}"
            out[name] = ledger.lack(name, source) if text == PLACEHOLDER else ledger.add(name, text, source)
        return text

    def split_sum(rate, names):
        """The sum of the named components of the split in each cell at ``rate``, a year, and how many are absent."""
        parts = [column(cells[rate], [CPM, "split", name]) for name in names]
        return sum(values for values, _ in parts) * 12 / months, sum(absent for _, absent in parts)

    rows = [[label] + [entry(label, stem, rate, *split_sum(rate, names), usd,
                             f"{where(rate)}.{CPM}.split: {' + '.join(names)}, a year") for rate in rates]
            for stem, label, names in SOURCE_ROWS]
    every = tuple(chain.from_iterable(names for _, _, names in SOURCE_ROWS))
    rows.append(["Gain over banks and cards"] + [entry("gain", "Total", rate, *split_sum(rate, every), usd,
                                                       f"{where(rate)}.{CPM}.split: every component, a year")
                                                 for rate in rates])
    # Each line named in the text as a share of the gain, from the two medians the table prints at that rate.
    for (stem, _, names), rate in product(SOURCE_ROWS[:2], rates):
        if rate not in RATE_WORDS:
            continue
        part, lacking = split_sum(rate, names)
        total, missing = split_sum(rate, every)
        name = f"Source{stem}Share{RATE_WORDS[rate]}"
        source = f"{where(rate)}.{CPM}.split: the median of {' + '.join(names)} over the median of every component"
        if lacking or missing or not part.size or abs(np.nanmedian(total)) < TOL:
            out[name] = ledger.lack(name, source)
        else:
            out[name] = ledger.add(name, whole_pct(np.nanmedian(part) / np.nanmedian(total)), source)
    head = ["Outside rate"] + [pct(rate * 100, 1) for rate in rates]
    return dict(spec="l" + "r" * len(rates), head=head, rows=rows, rule_before=[len(SOURCE_ROWS)]), out


# The two vehicle-loan tiers on which the pool's instalment coupon and the outside lender's rate change sides inside
# the range of outside rates run (the grid's and the cut's): the macro stem, the label, and the place in each stored
# ``outside_rates`` entry's ``vehicle`` (new or used, then the score tier). Every other tier and product stays on one
# side at all six rates.
CROSSING_LOANS = (("NewCar", "new car", 0, 3), ("UsedCar", "used car", 1, 4))


def class_mean(record, name):
    """One by-class record of a cell averaged over people (the classes weighted by their sizes), or MISSING."""
    values, sizes = dig(record, [name]), dig(record, ["class_sizes"])
    if MISSING in (values, sizes) or values is None:
        return MISSING
    values, sizes = np.array([np.nan if v is None else v for v in values], float), np.asarray(sizes, float)
    seen = np.isfinite(values) & (sizes > 0)
    return float((values[seen] * sizes[seen]).sum() / sizes[seen].sum()) if seen.any() else None


def tier_label(store, kind, tier):
    """A vehicle-loan tier in words from the stored score edges: "new car, scores 661 to 780"."""
    edges = dig(store.summary, ["constants", "VEHICLE_TIER_SCORES"])
    if edges is MISSING or not 0 < tier <= len(edges):
        return kind
    low = int(edges[tier - 1])
    return f"{kind}, scores {low} and above" if tier == len(edges) else f"{kind}, scores {low} to {int(edges[tier]) - 1}"


def lending_table(store, cut, ledger):
    """What is asked of the pool by outside rate with no distress, over the map's rates and the rate cut's (marked):
    the pool's instalment coupon (each cell's mean over seeds, cells.json) beside the outside lender's rate on the
    two vehicle-loan tiers of CROSSING_LOANS (summary.json: outside_rates), then the median over launch levels of
    the pool's instalment lending and its bridging refused (the by-class records averaged over people, dollars a
    person a year), the capital target in dollars a person, pool capital over the target and bridges served. The
    macros are Lend + the row's stem + the rate's word."""
    owner = {}
    for one in ([] if cut is None else [cut]) + [store]:      # the map last, so a rate both ran is read on the map
        listed = dig(one.summary, ["r_out"])
        owner.update({float(rate): one for rate in ([] if listed is MISSING else listed)})
    rates, words, out = sorted(owner), {**RATE_WORDS, **CUT_WORDS}, {}
    if not rates:
        return dict(spec="l", head=[""], rows=[[ledger.lack("lending", "summary.json: r_out")]]), out
    cells = {rate: owner[rate].pick(distress=0.0, r_out=rate, arm=CPM) for rate in rates}

    def entry(label, stem, rate, values, absent, how, fmt, source):
        """One number of the table and its macro."""
        source = f"{Path(owner[rate].folder).name}/{source}"
        text = reduce(ledger, f"lending[{label}, rate {rate * 100:g}%]", np.asarray(values, float), absent, how, fmt,
                      source)
        if rate in words:
            name = f"Lend{stem}{words[rate]}"
            out[name] = ledger.lack(name, source) if text == PLACEHOLDER else ledger.add(name, text, source)
        return text

    def coupon(rate):
        """Each cell's mean over seeds of the pool's instalment coupon, % a year, and the cells that lack it."""
        found = [seed_values(owner[rate], cell_key(cell), ["arms", CPM, "r_term_pct"]) for cell in cells[rate]]
        lacking = sum(values.size == 0 or absent > 0 or not np.isfinite(values).any() for values, absent in found)
        return [np.nan if values.size == 0 or not np.isfinite(values).any() else float(np.nanmean(values))
                for values, _ in found], lacking

    def outside(rate, kind, tier):
        """The outside lender's rate on one vehicle-loan tier at ``rate``, % a year, as a one-item list."""
        listed = dig(owner[rate].summary, ["outside_rates"])
        mine = [row for row in ([] if listed is MISSING else listed) if abs(float(row["r_out"]) - rate) < TOL]
        value = dig(mine[0], ["vehicle", kind, tier]) if mine else MISSING
        return ([np.nan], 1) if value is MISSING else ([float(value) * 100], 0)

    def by_class(rate, name):
        """One by-class record averaged over people in each cell at ``rate``, and the cells that lack it."""
        found = [class_mean(dig(cell, [CPM, "by_class"]), name) for cell in cells[rate]]
        return [np.nan if v is MISSING or v is None else v for v in found], sum(v is MISSING for v in found)

    def capital(rate):
        """Each cell's capital target in dollars a person and its capital over the target."""
        unit = dig(owner[rate].summary, ["constants", "MONTH_USD"])
        held, lacking = column(cells[rate], [CPM, "N"])
        target, missing = column(cells[rate], [CPM, "N_star"])
        ratio = np.divide(held, target, out=np.full(held.shape, np.nan), where=target > 0)
        dollars = target * (np.nan if unit is MISSING else float(unit))
        return (dollars, missing + (unit is MISSING)), (ratio, lacking + missing)

    two = lambda value: pct(value, 2)
    where = lambda rate: f"cells[{describe(cells[rate])}]"
    rows = [["Pool's instalment coupon"] + [entry("instalment coupon", "Coupon", rate, *coupon(rate), "median", two,
                                                  f"cells.json: jobs in {where(rate)}.arms.{CPM}.r_term_pct, the mean "
                                                  "over seeds in each cell") for rate in rates]]
    for stem, kind, place, tier in CROSSING_LOANS:
        label = "Outside lender, " + tier_label(store, kind, tier)
        rows.append([label] + [entry(label, stem, rate, *outside(rate, place, tier), "only", two,
                                     f"summary.json: outside_rates[r_out {rate * 100:g}%].vehicle[{place}][{tier}]")
                               for rate in rates])
    rows.append([r"Pool instalment lending, \$ a person a year"]
                + [entry("instalment lending", "Term", rate, *by_class(rate, "term_pool"), "median", usd,
                         f"summary.json: {where(rate)}.{CPM}.by_class.term_pool, the classes weighted by size")
                   for rate in rates])
    rows.append([r"Capital target, \$ a person"]
                + [entry("capital target", "Target", rate, *capital(rate)[0], "median", usd,
                         f"summary.json: {where(rate)}.{CPM}.N_star x constants.MONTH_USD") for rate in rates])
    rows.append(["Pool capital over its target"]
                + [entry("capital over target", "Capital", rate, *capital(rate)[1], "median", lambda v: share(v, 2),
                         f"summary.json: {where(rate)}.{CPM}.N over .{CPM}.N_star") for rate in rates])
    rows.append([r"Bridging refused, \$ a person a year"]
                + [entry("bridging refused", "Refused", rate, *by_class(rate, "bridge_refused"), "median", usd,
                         f"summary.json: {where(rate)}.{CPM}.by_class.bridge_refused, the classes weighted by size")
                   for rate in rates])
    served = [CPM, "bridges_drawn_over_wanted"]
    rows.append(["Bridges served"] + [entry("bridges served", "Served", rate, *column(cells[rate], served), "median",
                                            lambda v: share(v, 2), f"summary.json: {where(rate)}.{path_text(served)}")
                                      for rate in rates])
    # The lowest outside rate against the stress table's rate, from the medians the table prints.
    low, central = min(rates), STRESS_RATE
    middle = lambda values, absent: np.nan if absent or not len(values) else float(np.nanmedian(np.asarray(values, float)))
    if any(abs(rate - central) < TOL for rate in rates) and low < central - TOL:
        central = next(rate for rate in rates if abs(rate - central) < TOL)
        for name, read_at in (("LendTermMore", lambda rate: by_class(rate, "term_pool")),
                              ("LendTargetMore", lambda rate: capital(rate)[0]),
                              ("LendRefusedMore", lambda rate: by_class(rate, "bridge_refused"))):
            out[name] = change_macro(ledger, name, middle(*read_at(low)), middle(*read_at(central)),
                                     f"the median at {low * 100:g}% against the median at {central * 100:g}%, "
                                     "the lending table's rows")
    head = ["Outside rate"] + [pct(rate * 100, 1) + (CUT_MARK if owner[rate] is not store else "") for rate in rates]
    return dict(spec="l" + "r" * len(rates), head=head, rows=rows, rule_before=[1 + len(CROSSING_LOANS)]), out


def grid_macros(store, ledger):
    """Counts over every cell of the grid, at every level of distress: the cells, the cells in which CPM's mean gain
    over banks and cards and over best-case DeFi is positive on every reading (money alone and with completed
    purchases at their price, without the bound and under the cash-advance bound), and the cells in which CPM fails
    fewer payments than both."""
    cells = store.pick(arm=CPM)
    count, positive, fewer = grid_counts(store)
    where = f"summary.json: cells[{describe(cells)}]"
    return dict(
        CellsAll=ledger.add("CellsAll", str(count), f"count of {describe(cells)}"),
        CellsGainPositive=ledger.add("CellsGainPositive", str(positive), f"{where}: cells with every one of "
                                     + "; ".join(path_text(p) for p in GAIN_READINGS) + " above zero"),
        CellsFewerFailures=ledger.add("CellsFewerFailures", str(fewer), f"{where}: cells with {CPM}.failures_pct "
                                      "below S0_failures_pct and below M0.failures_pct"))


# Every reading of CPM's mean gain: against banks and cards and against best-case DeFi, in money alone and with
# completed purchases at their price, each without the bound and under the cash-advance bound.
GAIN_READINGS = tuple([CPM, "against", yard, *tail, "gain_usd_a_year"] for yard, tail in product(
    ("S0", "M0"), ((), ("bound",), ("complete_gain", "face"), ("complete_gain", "face", "bound"))))


def grid_counts(store):
    """Over every cell of a map that holds CPM: the number of cells, the cells in which every reading of the gain
    is above zero, and the cells in which CPM fails fewer payments than banks and cards and than best-case DeFi."""
    cells = store.pick(arm=CPM)
    gains = np.array([column(cells, path)[0] for path in GAIN_READINGS])       # readings x cells, NaN where absent
    fails = np.array([column(cells, failure_path(arm))[0] for arm in (CPM, "S0", "M0")])
    positive = int((gains > 0).all(axis=0).sum())                              # a NaN is not above zero
    fewer = int(((fails[0] < fails[1]) & (fails[0] < fails[2])).sum())
    return len(cells), positive, fewer


def low_high(ledger, stem, cells, path):
    """The macros stem + Low and stem + High: the lowest and highest stored per cent over ``cells``."""
    values, _ = column(cells, path)
    fmt = latex_pct_fmt(values)
    return {stem + side: read(ledger, stem + side, cells, path, how, fmt) for side, how in (("Low", "low"),
                                                                                           ("High", "high"))}


def fixed_or_range(ledger, stem, cells, path):
    """One macro when the value is the same in every cell (banks do not depend on the launch level); otherwise
    stem + Low and stem + High, with stem itself reading "low to high" so the paper still compiles."""
    values, absent = column(cells, path)
    fmt = latex_pct_fmt(values)
    seen = values[np.isfinite(values)]
    if absent or seen.size == 0 or np.ptp(seen) <= TOL:
        return {stem: read(ledger, stem, cells, path, "only" if seen.size and not absent else "low", fmt)}
    ledger.notes.append(f"{stem} varies over cells, so {stem}Low and {stem}High are written and {stem} is the range")
    return {stem: read(ledger, stem, cells, path, "range", fmt), **low_high(ledger, stem, cells, path)}


def lowest_run(store, rate):
    """At one outside rate and 2 points of distress, the lowest launch level at which any seed of CPM shows a pool
    run (bridges served in years 4 and 5 below RUN_LINE): (a0, cells read, None), (None, cells, None) when no seed
    runs, or (None, cells, why) when a cell does not store the per-seed figure or no cell was run."""
    cells = store.pick(distress=HEADLINE, r_out=rate, arm=CPM)
    if not cells:
        return None, cells, f"no cell at {HEADLINE * 100:g} points and r_out {rate * 100:g}%"
    found = [bridges_served(store, cell_key(c)) for c in cells]
    lacking = [why for values, why in found if values is None]
    if lacking:
        return None, cells, lacking[0]
    runs = np.array([bool(np.any(values < RUN_LINE)) for values, _ in found])
    launches = np.array([c["a0"] for c in cells], float)
    return (float(launches[runs].min()) if runs.any() else None), cells, None


def run_adoption(store, ledger, rate=STRESS_RATE):
    """The macro RunAdoption: the lowest launch participation at which any seed of CPM shows a pool run at 2 points
    of distress, at the stress table's outside rate (``lowest_run``); "none" when no seed runs. The same reading at
    the map's other outside rates goes to the report's notes."""
    lowest, cells, why = lowest_run(store, rate)
    others = [(r, lowest_run(store, r)) for r in sorted({k[0] for k in store.index} - {rate})]
    ledger.notes += [f"RunAdoption at r_out {r * 100:g}% would read "
                     + (why or ("none" if low is None else f"{low * 100:g}%")) for r, (low, _, why) in others]
    if why:
        return ledger.lack("RunAdoption", why)
    source = (f"min a0 with any seed's bridges served (years 4 and 5) < {RUN_LINE}: cells.json jobs at "
              f"{describe(cells)}, arms.{CPM}.bridges_drawn_over_wanted")
    return ledger.add("RunAdoption", "none" if lowest is None else f"{lowest * 100:g}" + r"\%", source)


# ----------------------------------------------------------------------------------------------------------------------
# (2) The tables, each a list of rows (lists of LaTeX cells) with a column specification and a header
# ----------------------------------------------------------------------------------------------------------------------
def class_weighted(cells, block, key):
    """Each cell's population mean of a by-class record (classes weighted by their sizes), and how many cells lack
    it. ``block`` is the path to the by_class record."""
    sizes, a = column_matrix(cells, block + ["class_sizes"])
    parts, b = column_matrix(cells, block + [key])
    total = np.nansum(sizes, axis=1)
    values = np.divide(np.nansum(parts * sizes, axis=1), total, out=np.full(len(cells), np.nan), where=total > 0)
    return values, max(a, b)


def column_matrix(cells, path):
    """The list at ``path`` in each cell as a cells x entries array (NaN for None), and how many cells lack it."""
    found = [dig(c, path) for c in cells]
    absent = sum(v is MISSING or not isinstance(v, list) for v in found)
    width = max((len(v) for v in found if isinstance(v, list)), default=0)
    pad = lambda v: (v if isinstance(v, list) else []) + [None] * (width - (len(v) if isinstance(v, list) else 0))
    return np.array([pad(v) for v in found], dtype=float).reshape(len(cells), width), absent


def arrangements_table(store, ledger):
    """Each arrangement's failed payments with no distress and at 2 points (the mean over cells and the range) and
    purchases completed with no distress ($ a person a year, class-weighted, mean over cells)."""
    zero, stress = store.pick(distress=0.0), store.pick(distress=HEADLINE)

    def row(arm):
        """One arrangement's row."""
        name, cells_0, cells_2 = NAMES[arm], [c for c in zero if arm in c or arm == "S0"], \
            [c for c in stress if arm in c or arm == "S0"]
        fmt = latex_pct_fmt(column(zero + stress, failure_path(arm))[0])
        tag = lambda col: f"arrangements[{name}, {col}]"
        block = ["S0_by_class"] if arm == "S0" else [arm, "by_class"]
        bought, absent = class_weighted(cells_0, block, "completed")
        return [name,
                read(ledger, tag("failed, none, mean"), cells_0, failure_path(arm), "mean", fmt),
                read(ledger, tag("failed, none, range"), cells_0, failure_path(arm), "range", fmt),
                read(ledger, tag("failed, 2 points, mean"), cells_2, failure_path(arm), "mean", fmt),
                read(ledger, tag("failed, 2 points, range"), cells_2, failure_path(arm), "range", fmt),
                reduce(ledger, tag("purchases completed"), bought, absent, "mean", usd,
                       f"summary.json: cells[{describe(cells_0)}].{path_text(block)}.completed weighted by "
                       "class_sizes")]

    head = ["Arrangement", "Failed, none (mean)", "Failed, none (range)", "Failed, 2 points (mean)",
            "Failed, 2 points (range)", r"Purchases completed (\$ a person a year)"]
    return dict(spec="l" + "r" * 5, head=head, rows=[row(arm) for arm in ARMS])


# The gains table's rows: label, path inside a cell's CPM.against.<yardstick> block, formatter.
GAIN_ROWS = (("Wealth gain", ["gain_usd_a_year"], usd),
             ("Complete gain at face value", ["complete_gain", "face", "gain_usd_a_year"], usd),
             ("Complete gain at zero", ["complete_gain", "zero", "gain_usd_a_year"], usd),
             ("Wealth gain under the cash-advance bound", ["bound", "gain_usd_a_year"], usd),
             ("Complete gain at face, under the bound", ["complete_gain", "face", "bound", "gain_usd_a_year"], usd),
             ("Complete gain at zero, under the bound", ["complete_gain", "zero", "bound", "gain_usd_a_year"], usd),
             ("Cash-advance fees and interest saved", ["advance_saving_usd_a_year"], usd),
             ("Real cost saved", ["real_saving_usd_a_year", "total"], usd),
             (r"Share below $-$\$2 a year, complete gain at face", ["dispersion", "face", "below_margin_share"],
              lambda v: pct(100 * v, 1)),
             ("Wealth gain read at month 36", ["gain_usd_a_year_at_month", "36"], usd),
             ("Wealth gain read at month 48", ["gain_usd_a_year_at_month", "48"], usd))

# The clause counts: label and a test on a cell's CPM claim block (None where the block does not store it).
CLAUSE_COUNTS = (("Clause (a)", lambda b: status(b, "a")), ("Clause (b)", lambda b: status(b, "b")),
                 ("Clause (c), reported", lambda b: status(b, "c")), ("Clause (d) as built", lambda b: status(b, "d")),
                 ("Clause (d) under the bound", lambda b: status(b, "d_bound")),
                 ("All of (a), (b), (d) as built", lambda b: flag(b, "all_as_built")),
                 ("All of (a), (b), (d) under the bound", lambda b: both(status(b, "a"), status(b, "b"),
                                                                         status(b, "d_bound"))),
                 # A claim block without (d) under the bound has "all" and "in_region" without the bound only, so
                 # they are read here only from a block that stores (d) under the bound.
                 ("All, as built and under the bound", lambda b: bounded(b, flag(b, "all"))),
                 ("In the region (largest joined block)", lambda b: bounded(b, flag(b, "in_region"))))


def bounded(block, value):
    """``value`` when the claim block stores clause (d) under the cash-advance bound, else None (not stored): an
    older block's "all" and "in_region" did not ask for the bound."""
    return value if status(block, "d_bound") is not None else None


def status(block, name):
    """Whether a claim block's clause ``name`` passes at 95%, None where not stored."""
    found = dig(block, [name, "status"])
    return None if found is MISSING else found == "pass"


def flag(block, name):
    """A claim block's True/False ``name``, None where not stored."""
    found = dig(block, [name])
    return None if found is MISSING or found is None else bool(found)


def both(*parts):
    """All of ``parts`` true, None when any is not stored."""
    return None if any(p is None for p in parts) else all(parts)


def gains_table(store, ledger):
    """CPM against banks and against best-case DeFi over the cells with no distress: each gain's median and range
    over cells, the lowest group lower bound over cells (without and under the bound) and the number of cells
    passing each clause."""
    cells = store.pick(distress=0.0, arm=CPM)
    against = tuple(product((("S0", "banks"), ("M0", "DeFi")), ("median", "range")))   # the four value columns

    def gain_row(label, path, fmt):
        """One gain's row: its median and range over cells against banks, then against best-case DeFi."""
        return [label] + [read(ledger, f"gains[{label}, {name}, {how}]", cells, [CPM, "against", other] + path, how,
                               fmt) for (other, name), how in against]

    rows = [gain_row(*spec) for spec in GAIN_ROWS]
    lowest = [lowest_bound(store, ledger, cells, clause, label) for clause, label in
              (("d", "Lowest group lower bound, as built"), ("d_bound", "Lowest group lower bound, under the bound"))]
    blocks = [dig(c, [CPM, "claim"]) for c in cells]
    counts = [[label, r"\multicolumn{4}{l}{" + count_cells(ledger, label, blocks, test, cells) + "}"]
              for label, test in CLAUSE_COUNTS]
    head = ["", "Banks (median)", "Banks (range)", "DeFi (median)", "DeFi (range)"]
    return dict(spec="lrrrr", head=head, rows=rows + lowest + counts, rule_before=[len(rows), len(rows) + 2])


def lowest_bound(store, ledger, cells, clause, label):
    """The lowest 95% lower bound of any group's complete gain over ``cells`` (claim block ``clause``), with the
    cell, group, yardstick and end it belongs to in the report."""
    path = [CPM, "claim", clause, "at_95", "lowest", "lower"]
    values, absent = column(cells, path)
    text = reduce(ledger, f"gains[{label}]", values, absent, "low", usd, f"summary.json: cells[{describe(cells)}]."
                  f"{path_text(path)}")
    if text != PLACEHOLDER and np.isfinite(values).any():
        at = int(np.nanargmin(values))
        who = dig(cells[at], [CPM, "claim", clause, "at_95", "lowest"])
        ledger.notes.append(f"{label}: cell {cell_key(cells[at])}, group {who.get('group')}, against "
                            f"{who.get('against')}, end {who.get('end')}")
    return [label, r"\multicolumn{4}{l}{" + text + "}"]


def count_cells(ledger, label, blocks, test, cells):
    """How many of the cells pass ``test`` on their claim block, "k of n"; the placeholder when any does not store
    what the test reads."""
    where = f"gains[{label}, cells passing]"
    found = [None if b is MISSING else test(b) for b in blocks]
    if not found or any(f is None for f in found):
        stored = sum(f is not None for f in found)
        return ledger.lack(where, f"stored in {stored} of {len(found)} cells' {CPM}.claim ({describe(cells)})")
    return ledger.add(where, f"{sum(found)} of {len(found)}", f"summary.json: cells[{describe(cells)}].{CPM}.claim")


# The charge table's columns: label, path in an arm's block, formatter (None: a gain over U, read on CPM only).
CHARGE_COLUMNS = (("Bridge price", ["r_b_pct"], lambda v: pct(v, 2)),
                  ("Gross coupon", ["r_g_pct"], lambda v: pct(v, 2)),
                  ("Bridges served", ["bridges_drawn_over_wanted"], share),
                  ("Demurrage $c$", ["c_pct"], lambda v: pct(v, 3)),
                  (r"$\theta$", ["theta"], share),
                  ("Payments that fail", ["failures_pct"], lambda v: pct(v, 3)),
                  (r"Gain over the pool without the charge", ["against", "U", "gain_usd_a_year"], usd))


def charge_table(store, ledger):
    """What the holding charge does, CPM against the pool without the charge, by outside rate, over the cells with
    no distress: each entry the median over the launch levels (the report gives the range too). The gain of CPM over
    the pool without the charge is CPM's own paired reading against U, so the U row leaves it blank."""
    rates = sorted({k[0] for k in store.index if k[2] == 0.0})

    def entry(cells, arm, label, path, fmt):
        """One table cell: the median over ``cells``, the range recorded beside it in the report."""
        if arm == "U" and path[0] == "against":
            return ""
        where = f"charge[r_out {cells[0]['r_out'] * 100:g}%, {NAMES[arm]}, {label}]"
        read(ledger, where + " range", cells, [arm] + path, "range", fmt)
        return read(ledger, where, cells, [arm] + path, "median", fmt)

    def row(rate, arm):
        """One (outside rate, arrangement) row over that rate's launch levels."""
        cells = store.pick(distress=0.0, r_out=rate, arm=arm)
        return [pct(rate * 100, 1), NAMES[arm]] + [entry(cells, arm, *col) for col in CHARGE_COLUMNS]

    rows = [row(rate, arm) for rate, arm in product(rates, ("U", CPM)) if store.pick(distress=0.0, r_out=rate, arm=arm)]
    return dict(spec="ll" + "r" * len(CHARGE_COLUMNS), head=["Outside rate", "Arrangement"] +
                [label for label, _, _ in CHARGE_COLUMNS], rows=rows)


# CPM less the pool without the charge by distress level: the columns of each reading (macro stem, heading).
CHARGE_GAIN_COLUMNS = (("Median", "Median gain"), ("Low", "Lowest lower bound"), ("Above", "Cells above zero"),
                       ("Fewer", "Cells with fewer failures"))


def charge_gain_columns(store, ledger, tag):
    """One reading's columns of the charge-gain table, a row for each distress level, and its macros (ChargeGain +
    ``tag`` + the column's stem + the level's word). CPM's gain in money over the pool without the charge is paired
    seed by seed, since both run on the same people and draws: the median over the level's cells of the stored seed
    mean; the lowest, over those cells, of the lower end of the 95% t interval of the per-seed gains (cells.json);
    the cells whose lower end is above zero; and the cells in which CPM fails fewer payments than the pool without
    the charge. Also ChargeGain + ``tag`` + AboveAll, FewerAll and Cells, the same counts over the whole grid."""
    out, columns, totals = {}, [], dict(Above=0, Fewer=0, Cells=0)
    folder = Path(store.folder).name
    gain = [CPM, "against", "U", "gain_usd_a_year"]
    for level, word in LEVEL_WORDS:
        cells = store.pick(distress=level, arm=CPM)
        name = lambda stem: f"ChargeGain{tag}{stem}{word}"
        where = f"{folder}/summary.json: cells[{describe(cells)}]"
        median = read(ledger, name("Median"), cells, gain, "median", usd, file=f"{folder}/summary.json")
        found = [seed_values(store, cell_key(cell), ["arms"] + gain) for cell in cells]
        source = f"{folder}/cells.json: jobs in cells[{describe(cells)}].arms.{path_text(gain)}, each seed"
        if not cells or any(values.size < 2 or absent for values, absent in found):
            low = ledger.lack(name("Low"), source)
            above = ledger.lack(name("Above"), source)
        else:
            lower = np.array([t_interval(values)["lower_95"] for values, _ in found], float)
            low = ledger.add(name("Low"), usd(lower.min()), f"the lowest lower end of the 95% t interval, {source}")
            above = ledger.add(name("Above"), str(int((lower > 0).sum())), f"cells with that lower end above zero, {source}")
            totals["Above"] += int((lower > 0).sum())
        mine, lacking = column(cells, failure_path(CPM))
        other, missing = column(cells, failure_path("U"))
        if not cells or lacking or missing:
            fewer = ledger.lack(name("Fewer"), f"{where}: failures_pct of {CPM} and U")
        else:
            fewer = ledger.add(name("Fewer"), str(int((mine < other).sum())), f"{where}: {CPM}'s failed share below U's")
            totals["Fewer"] += int((mine < other).sum())
        totals["Cells"] += len(cells)
        row = dict(Median=median, Low=low, Above=above, Fewer=fewer)
        out.update({name(stem): text for stem, text in row.items()})
        columns.append([row[stem] for stem, _ in CHARGE_GAIN_COLUMNS])
    whole = any(PLACEHOLDER in row for row in columns)
    for stem, count in totals.items():
        name = f"ChargeGain{tag}{stem}All" if stem != "Cells" else f"ChargeGain{tag}Cells"
        out[name] = (ledger.lack(name, f"{folder}: a level's count is not stored") if whole and stem != "Cells" else
                     ledger.add(name, str(count), f"{folder}: the levels' counts added"))
    return columns, out


def charge_gain_table(store, second, ledger):
    """CPM less the pool without the charge by distress level under the two entry readings (``charge_gain_columns``),
    ``second`` None for the first reading alone: the table and the macros."""
    readings = [("First", "Quote rule", store)]
    if second is not None:
        readings.append(("Second", "Record rule", second))
    blocks, out = [], {}
    for tag, _, one in readings:
        columns, macros = charge_gain_columns(one, ledger, tag)
        blocks.append(columns)
        out.update(macros)
    rows = [[f"{level * 100:g} pt", *chain.from_iterable(block[k] for block in blocks)]
            for k, (level, _) in enumerate(LEVEL_WORDS)]
    width = len(CHARGE_GAIN_COLUMNS)
    over = "".join(f" & \\multicolumn{{{width}}}{{c}}{{{title}}}" for _, title, _ in readings) + r" \\"
    head = ["Distress"] + [title for _, title in CHARGE_GAIN_COLUMNS] * len(readings)
    return dict(spec="l" + "r" * (width * len(readings)), over=over, head=head, rows=rows), out


# ----------------------------------------------------------------------------------------------------------------------
# What the holding charge buys: the charge paid, and the liquidity support it pays for, by arrangement
# ----------------------------------------------------------------------------------------------------------------------
def second_window(cells, path):
    """The years 4 and 5 value at ``path`` in each cell: the second element where the runner stores a pair of
    windows, else the stored number itself. NaN where undefined, and how many cells do not hold the key at all."""
    found = [dig(cell, path) for cell in cells]
    last = lambda value: value[1] if isinstance(value, list) else value
    values = np.array([np.nan if v is MISSING or last(v) is None else float(last(v)) for v in found], float)
    return values, sum(v is MISSING for v in found)


def liquidity_path(key):
    """Where each arrangement stores a liquidity record: banks and cards at the cell's top level, the others in
    their own block. Returns a function of the arrangement."""
    return lambda arm: ["S0_liquidity", key] if arm == "S0" else [arm, "liquidity", key]


def pool_only(*path):
    """A record only the two pool arrangements have (None for banks and cards and best-case DeFi)."""
    return lambda arm: [arm, *path] if arm in ("U", CPM) else None


def cpm_only(*path):
    """A record only CPM has (None for every other arrangement)."""
    return lambda arm: [arm, *path] if arm == CPM else None


BUYS_ARMS = ("S0", "M0", "U", CPM)
# Each row: label, where an arrangement stores it (None: it does not apply), format. A shortfall is what a payer's
# own money and same-day savings could not pay; "covered" is the part a lender paid (the pool, the card, revolving on
# the card, earned-wage access). Precautionary money is households' chosen buffers plus the pool's idle cash.
BUYS_ROWS = (
    (r"Demurrage paid by holders, \$ a person a year", pool_only("demurrage", "charges_usd_a_year"), usd),
    (r"Bridge price to the borrower, \% a year", pool_only("r_b_pct"), lambda v: pct(v, 1)),
    (r"Shortfalls a lender covered, \$ a person a year", liquidity_path("shortfall_covered_usd_a_year"), usd),
    (r"\quad by the pool", liquidity_path("pool_bridges_usd_a_year"), usd),
    (r"\quad on the card", liquidity_path("card_bridging_usd_a_year"), usd),
    (r"\quad revolved on the card", liquidity_path("revolved_usd_a_year"), usd),
    (r"Payments that failed, \$ a person a year", liquidity_path("failed_usd_a_year"), usd),
    (r"Precautionary money held, \$ a person", liquidity_path("precautionary_usd"), usd),
    (r"\quad of which pool cash standing by", liquidity_path("pool_idle_usd"), usd),
    ("Precautionary money per dollar of shortfall covered", liquidity_path("precautionary_per_dollar_covered"),
     lambda v: share(v, 2)),
    (r"Gain over the pool without the charge, \$ a person a year", cpm_only("against", "U", "gain_usd_a_year"), usd))


def buys_source(cells, path):
    """The source text of a liquidity-support number."""
    return f"summary.json: cells[{describe(cells)}].{path_text(path)}, years 4 and 5 (the second stored window)"


def buys_table(store, ledger):
    """What the holding charge buys: for each arrangement, over the cells with no distress, the charge holders pay
    and the liquidity support it goes with, each the median over cells of the years 4 and 5 value (the report gives
    the range). The pool without the charge beside CPM, on the same people and draws, is what the charge changes;
    banks and cards and best-case DeFi show the same measures for today's arrangements."""
    cells = store.pick(distress=0.0)

    def entry(label, where_of, fmt, arm):
        """One table cell: the median over cells, with the range recorded beside it in the report."""
        path = where_of(arm)
        if path is None:
            return ""
        values, absent = second_window(cells, path)
        where = f"buys[{label}, {NAMES[arm]}]"
        reduce(ledger, where + " range", values, absent, "range", fmt, buys_source(cells, path))
        return reduce(ledger, where, values, absent, "median", fmt, buys_source(cells, path))

    rows = [[label] + [entry(label, where_of, fmt, arm) for arm in BUYS_ARMS] for label, where_of, fmt in BUYS_ROWS]
    return dict(spec="l" + "r" * len(BUYS_ARMS), head=[""] + [NAMES[arm] for arm in BUYS_ARMS], rows=rows)


def buys_macros(store, ledger):
    """The same readings as macros for the running text (medians over the cells with no distress), and the net
    gain of CPM over the pool without the charge in years 4 and 5 (GainOverPoolLate) for each dollar of charge paid
    in those years (GainPerChargeDollar, the median over cells of the cell's own ratio)."""
    cells = store.pick(distress=0.0)
    two = lambda v: share(v, 2)
    specs = (("ChargeDollars", CPM, pool_only("demurrage", "charges_usd_a_year"), usd),
             ("PoolBridgingPool", "U", liquidity_path("pool_bridges_usd_a_year"), usd),
             ("PoolBridgingCpm", CPM, liquidity_path("pool_bridges_usd_a_year"), usd),
             ("RevolvedPool", "U", liquidity_path("revolved_usd_a_year"), usd),
             ("RevolvedCpm", CPM, liquidity_path("revolved_usd_a_year"), usd),
             ("FailedDollarsPool", "U", liquidity_path("failed_usd_a_year"), usd),
             ("FailedDollarsCpm", CPM, liquidity_path("failed_usd_a_year"), usd),
             ("StandbyPool", "U", liquidity_path("pool_idle_usd"), usd),
             ("StandbyCpm", CPM, liquidity_path("pool_idle_usd"), usd),
             ("PrecautionBanks", "S0", liquidity_path("precautionary_per_dollar_covered"), two),
             ("PrecautionDefi", "M0", liquidity_path("precautionary_per_dollar_covered"), two),
             ("PrecautionPool", "U", liquidity_path("precautionary_per_dollar_covered"), two),
             ("PrecautionCpm", CPM, liquidity_path("precautionary_per_dollar_covered"), two),
             ("GainOverPool", CPM, cpm_only("against", "U", "gain_usd_a_year"), usd))

    def one(name, arm, where_of, fmt):
        """One macro: the median over cells."""
        values, absent = second_window(cells, where_of(arm))
        return reduce(ledger, name, values, absent, "median", fmt, buys_source(cells, where_of(arm)))

    out = {name: one(name, arm, where_of, fmt) for name, arm, where_of, fmt in specs}
    # The change from the pool without the charge to CPM in the medians quoted side by side, as a whole per cent.
    for name, where_of in (("StandbyChange", liquidity_path("pool_idle_usd")),
                           ("PoolBridgingChange", liquidity_path("pool_bridges_usd_a_year")),
                           ("RevolvedChange", liquidity_path("revolved_usd_a_year"))):
        levels = [(lambda values, absent: np.nan if absent else float(np.nanmedian(values)))(
            *second_window(cells, where_of(arm))) for arm in (CPM, "U")]
        out[name] = change_macro(ledger, name, *levels, f"medians of {buys_source(cells, where_of(CPM))}, CPM against "
                                 "the pool without the charge")
    # Both sides on years 4 and 5: the gain over the pool without the charge earned after month SHOCK_END, over the
    # charge collected in the same months. (The stored whole-run gain covers five years and the stored charge two,
    # so their ratio mixed two windows.)
    gain, lacking = earned_after_shock(store, cells, "U")
    charge, absent = second_window(cells, [CPM, "demurrage", "charges_usd_a_year"])
    source = (f"summary.json: cells[{describe(cells)}]: the gain over U earned after month {SHOCK_END} "
              f"({CPM}.against.U.gain_usd_a_year_at_month, end and {SHOCK_END})")
    out["GainOverPoolLate"] = reduce(ledger, "GainOverPoolLate", gain, lacking, "median", usd, source + ", a year")
    # A cell with no charge has no ratio (NaN), so it is left out of the median.
    ratio = np.divide(gain, charge, out=np.full(gain.shape, np.nan), where=charge > 0)
    out["GainPerChargeDollar"] = reduce(
        ledger, "GainPerChargeDollar", ratio, lacking + absent, "median", lambda v: share(v, 1),
        f"{source} over {CPM}.demurrage.charges_usd_a_year (years 4 and 5), each cell's ratio")
    return out


MARKS = np.array(["", r"$\times$", r"$\circ$", r"$\bullet$"])   # not run, fails, passes outside the region, in it


def region_table(store, ledger):
    """For each distress level, the number of cells in the claim's region (CPM) and the grid of marks by outside
    rate (rows) and launch level (columns): in the region, passing outside the largest joined block, failing, or
    not run (blank). Read from summary.json's claim_statistics.regions."""
    slices = dig(store.summary, ["claim_statistics", "regions", CPM])
    rates, launches = dig(store.summary, ["r_out"]), dig(store.summary, ["a0"])
    head = ["Distress", "Outside rate"] + ([f"{a * 100:g}\\%" for a in launches] if launches is not MISSING else []) \
        + ["Cells in region"]
    if MISSING in (slices, rates, launches):
        return dict(spec="ll", head=head[:2], rows=[[ledger.lack("region", "summary.json: claim_statistics.regions."
                                                                 f"{CPM}, r_out or a0"), ""]])
    places = list(product(range(len(slices)), rates, launches))
    as_set = lambda s, key: {(float(r), float(a)) for r, a in s[key]}
    passing, inside = [as_set(s, "passing") for s in slices], [as_set(s, "region") for s in slices]
    # One code per (level, rate, launch): 0 not run, 1 fails, 2 passes outside the region, 3 in the region.
    code = np.array([0 if (r, a, slices[k]["distress"]) not in store.index or CPM not in store.index[(r, a, slices[k][
        "distress"])] else 3 if (r, a) in inside[k] else 2 if (r, a) in passing[k] else 1 for k, r, a in places])
    grid = MARKS[code.reshape(len(slices), len(rates), len(launches))]
    sizes = [ledger.add(f"region[distress {s['distress'] * 100:g} pt, cells in region]", str(len(s["region"])),
                        f"summary.json: claim_statistics.regions.{CPM}[{k}].region") for k, s in enumerate(slices)]
    ledger.add("region[marks]", "grid", f"summary.json: claim_statistics.regions.{CPM}[*].passing and .region, "
               "cells present in summary.json: cells")
    if not any(status(dig(c, [CPM, "claim"]), "d_bound") is not None for c in store.pick(distress=0.0, arm=CPM)):
        # A map written without the cash-advance bound stores the region without the bound only.
        ledger.notes.append("region: no claim block stores (d) under the cash-advance bound, so the stored region is "
                            "the region as built only")
    rows = [[f"{slices[k]['distress'] * 100:g} pt" if j == 0 else "", pct(rates[j] * 100, 1)] + list(grid[k, j])
            + [sizes[k] if j == 0 else ""] for k, j in product(range(len(slices)), range(len(rates)))]
    return dict(spec="ll" + "c" * len(launches) + "r", head=head, rows=rows)


MAJORITY_MARKS = np.array(["", r"$\times$", r"$\circ$", r"$\bullet$"])   # not run, not stable, unbounded only, both


def majority_code(cell):
    """One cell read on a majority of its seeds, from the runner's stored view: 3 stable without the bound and under
    the cash-advance bound, 2 stable without the bound only, 1 not stable, 0 not stored."""
    view = dig(cell, [CPM, "region"])
    as_built, bound = dig(view, ["verdict_majority"]), dig(view, ["verdict_majority_bound"])
    if MISSING in (view, as_built):
        return 0
    return 1 if as_built != "stable" else 3 if bound == "stable" else 2


def majority_table(store, ledger):
    """The claim read on a majority of seeds, for a map whose seeds are too few for the interval on the share of
    seeds (three development seeds cannot pass it): for each distress level the grid of marks by outside rate
    (rows) and launch level (columns), and the count of cells stable without the bound and stable both ways. Read
    from each cell's stored view (summary.json cells[].M1.region.verdict_majority and .verdict_majority_bound)."""
    rates, launches, levels = (dig(store.summary, [key]) for key in ("r_out", "a0", "distress"))
    if MISSING in (rates, launches, levels):
        return dict(spec="ll", head=["Distress", "Outside rate"],
                    rows=[[ledger.lack("region_majority", "summary.json: r_out, a0 or distress"), ""]])
    # The store's index is keyed by (outside rate, launch level, distress level); a place not run reads 0.
    found = [store.index.get((r, a, d), {}) for d, r, a in product(levels, rates, launches)]
    code = np.array([majority_code(cell) for cell in found]).reshape(len(levels), len(rates), len(launches))
    grid = MAJORITY_MARKS[code]
    counts = [(ledger.add(f"region_majority[distress {d * 100:g} pt, stable as built]", str(int((code[k] >= 2).sum())),
                          f"summary.json cells[].{CPM}.region.verdict_majority == stable"),
               ledger.add(f"region_majority[distress {d * 100:g} pt, stable both ways]", str(int((code[k] == 3).sum())),
                          f"summary.json cells[].{CPM}.region.verdict_majority and .verdict_majority_bound == stable"))
              for k, d in enumerate(levels)]
    rows = [[f"{levels[k] * 100:g} pt" if j == 0 else "", pct(rates[j] * 100, 1)] + list(grid[k, j])
            + ([counts[k][0], counts[k][1]] if j == 0 else ["", ""])
            for k, j in product(range(len(levels)), range(len(rates)))]
    return dict(spec="ll" + "c" * len(launches) + "rr",
                head=["Distress", "Outside rate"] + [f"{a * 100:g}\\%" for a in launches]
                + ["Stable as built", "Stable both ways"], rows=rows)


def stress_table(store, ledger, rate=STRESS_RATE):
    """By launch level and distress level at the stress rate, CPM: bridges served in years 4 and 5 (seed mean), the
    seeds with a pool run (years 4 and 5 below RUN_LINE), the registered flag (years 4 and 5 below the seed's own
    years 1 to 3), the share of money offered at the dealing that found no room, and bridge and term write-offs ($ a
    person a year), the last four from the monthly series."""
    cells = store.pick(r_out=rate, arm=CPM)
    month_usd = dig(store.summary, ["constants", "MONTH_USD"])

    def row(cell):
        """One (launch, distress) row."""
        key = cell_key(cell)
        tag = lambda col: f"stress[a0 {key[1]:g}, distress {key[2] * 100:g} pt, {col}]"
        served, source = bridges_served(store, key)
        seeds = len(store.jobs.get(key, [])) or len(store.monthly.get(key, []))
        if served is None:
            mean = runs = ledger.lack(tag("bridges served"), source)
        else:
            mean = reduce(ledger, tag("bridges served"), served, 0, "mean", share, source)
            runs = ledger.add(tag("seeds with a run"), f"{int(np.sum(served < RUN_LINE))} of {served.size}",
                              f"count of {source} < {RUN_LINE}")
        block = monthly_block(store, key, CPM, "bridges_drawn_over_wanted")
        src = f"measures.json: jobs[{key}].monthly.{CPM}"
        # The registered flag: a seed whose years 4 and 5 serve fewer bridges than its own years 1 to 3.
        fell = None if block is None else int(np.sum(window_mean(block, YEARS_4_5) < window_mean(block, YEARS_1_3)))
        flagged = (ledger.lack(tag("registered flag"), f"{src}.bridges_drawn_over_wanted") if block is None else
                   ledger.add(tag("registered flag"), f"{fell} of {block.shape[0]}",
                              f"{src}.bridges_drawn_over_wanted: mean of [36:60] < mean of [0:36], by seed"))
        offers, unused = (monthly_block(store, key, CPM, s) for s in ("offers", "offers_unused"))
        if offers is None or unused is None:
            room = ledger.lack(tag("offers unused"), f"{src}.offers and .offers_unused")
        else:
            total = np.nansum(offers[:, YEARS_4_5], axis=1)
            ratio = np.divide(np.nansum(unused[:, YEARS_4_5], axis=1), total, out=np.full(total.size, np.nan),
                              where=total > 0)
            room = reduce(ledger, tag("offers unused"), 100 * ratio, 0, "mean", lambda v: pct(v, 1),
                          f"{src}: sum offers_unused[36:60] / sum offers[36:60], seed mean")
        written = [write_offs(ledger, tag(f"{kind} write-offs"), monthly_block(store, key, CPM, f"written_off_{kind}"),
                              month_usd, f"{src}.written_off_{kind}") for kind in ("bridge", "term")]
        # A cell with no stored job at all still gets its row, of placeholders, so the gap is visible.
        if not seeds:
            ledger.notes.append(f"stress: no stored job for {key}")
        return [pct(key[1] * 100, 0), f"{key[2] * 100:g}", mean, runs, flagged, room, *written]

    head = ["Launch", "Distress (pt)", "Bridges served, years 4 and 5", f"Seeds with a run (below {RUN_LINE})",
            "Seeds below years 1 to 3", "Offers unused", r"Bridge write-offs (\$)", r"Term write-offs (\$)"]
    order = sorted(cells, key=lambda c: (c["a0"], c["distress"]))
    if not order:
        return dict(spec="l", head=["Launch"], rows=[[ledger.lack("stress", f"no cell at r_out {rate * 100:g}%")]])
    return dict(spec="rr" + "r" * 6, head=head, rows=list(map(row, order)))


def write_offs(ledger, where, block, month_usd, source):
    """Seed mean of the write-offs in years 4 and 5, $ a person a year: the monthly series (months of mean spending
    a person) summed over the 24 months, halved and times the dollars of a month."""
    if block is None or month_usd is MISSING:
        return ledger.lack(where, source if block is None else "summary.json: constants.MONTH_USD")
    yearly = np.nansum(block[:, YEARS_4_5], axis=1) / 2 * float(month_usd)
    return reduce(ledger, where, yearly, 0, "mean", usd, f"{source}[36:60] summed / 2 x MONTH_USD, seed mean")


def owners_excess(store, rate):
    """Owners' return less their alternative in the second window, % a year, in every seed of the cells with no
    distress at ``rate``: the values, how many jobs lack the field, and the source as the report writes it."""
    keys = [cell_key(c) for c in store.pick(distress=0.0, r_out=rate, arm=CPM)]
    found = [seed_values(store, k, ["arms", CPM, "owners_excess", "W2"]) for k in keys]
    values = np.concatenate([v for v, _ in found]) if found else np.array([])
    source = f"cells.json: jobs at {len(keys)} cells (r_out {rate * 100:g}%, distress 0), arms.{CPM}.owners_excess.W2"
    return values, sum(a for _, a in found), source


def owners_macros(store, ledger):
    """Owners' return less their alternative for the running text, as sizes in percentage points a year over the
    outside rates: the median furthest from zero (OwnersMedianWorst) and, at the tenth percentile, the smallest and
    the largest shortfall (OwnersTenthLeast, OwnersTenthWorst)."""
    rates = sorted({k[0] for k in store.index if k[2] == 0.0})
    found = [owners_excess(store, rate) for rate in rates]
    names = ("OwnersMedianWorst", "OwnersTenthLeast", "OwnersTenthWorst")
    usable = [values[np.isfinite(values)] for values, _, _ in found]
    if not found or any(absent or not seen.size for (_, absent, _), seen in zip(found, usable)):
        return {name: ledger.lack(name, f"cells.json: arms.{CPM}.owners_excess.W2 at every outside rate") for name in names}
    medians = np.array([np.median(seen) for seen in usable])
    tenths = np.array([np.percentile(seen, 10) for seen in usable])
    source = f"cells.json: arms.{CPM}.owners_excess.W2, seed-cells with no distress, by outside rate"
    size = lambda value: share(abs(value), 2)
    return dict(OwnersMedianWorst=ledger.add("OwnersMedianWorst", size(medians[np.argmax(np.abs(medians))]),
                                             f"the median furthest from zero over the rates; {source}"),
                OwnersTenthLeast=ledger.add("OwnersTenthLeast", size(tenths.max()),
                                            f"the tenth percentile nearest zero over the rates; {source}"),
                OwnersTenthWorst=ledger.add("OwnersTenthWorst", size(tenths.min()),
                                            f"the lowest tenth percentile over the rates; {source}"))


def owners_table(store, ledger):
    """Owners' return less their alternative in the second window (% a year), across the seed-cells with no distress,
    by outside rate: median, mean and 10th percentile, over the seed-cells whose households held capital (the
    runner stores None for the others; their count is shown)."""
    rates = sorted({k[0] for k in store.index if k[2] == 0.0})

    def row(rate):
        """One outside rate's row."""
        values, absent, source = owners_excess(store, rate)
        tag = lambda col: f"owners[r_out {rate * 100:g}%, {col}]"
        fmt = lambda v: pct(v, 2)
        stats = [reduce(ledger, tag(how), values, absent, how, fmt, source) for how in ("median", "mean", "p10")]
        held = ledger.add(tag("seed-cells"), f"{int(np.isfinite(values).sum())} of {values.size}", source)
        return [pct(rate * 100, 1)] + stats + [held]

    return dict(spec="lrrrr", head=["Outside rate", "Median", "Mean", "10th percentile", "Seed-cells with capital"],
                rows=list(map(row, rates)))


# ----------------------------------------------------------------------------------------------------------------------
# Circulation: how fast money turns over, how concentrated that is, and how long money is held before it is spent
# ----------------------------------------------------------------------------------------------------------------------
def group_sum(parts):
    """The aggregate velocity of everyone from the two groups' records, by year: ``parts`` holds, as rows, the
    participants' sum of MicroVelocity, their head count, the non-participants' sum and their head count. A group
    with nobody in it stores its sum as undefined, which counts zero here; an undefined sum of a group with people
    stays undefined (NaN)."""
    sums, people = parts[0::2], parts[1::2]
    return np.where(people == 0, 0.0, sums).sum(axis=0)


# The aggregate velocity's four stored parts, coin ages under last in first out (``group_sum``), and the same
# aggregate from outflows, which no right-censoring touches (a check written to the report's notes).
EVERYONE = tuple(["holding_velocity", "lifo", g, key]
                 for g, key in product(("participants", "non_participants"), ("sum", "people")))
EVERYONE_OUTFLOW = tuple(["microvelocity", "e_p_savings", g, key]
                         for g, key in product(("participants", "non_participants"), ("sum", "people")))


def one_place(value):
    """A plain number to one decimal: turns a year or days."""
    return share(value, 1)


# The table's rows: question, label, unit, stored paths (GROUP is the arrangement's group), how the paths combine
# into one value a year (None: the one path itself), whose people the row covers (None: the arrangement's group),
# format. Turnover is on E and P (the wallet); MicroVelocity and holding times are on E, P and outside savings, the
# money the coin ages follow. MicroVelocity is read from the coin ages, the authors' estimator; a person's V_i is
# all but the same under either ordering (it counts each unit's value over the days it is held), so one is shown.
CIRCULATION_ROWS = (
    ("(a)", "Wallet turnover, median person", "turns a year", (["turnover", "e_p", GROUP, "median"],), None, None,
     one_place),
    ("(a)", "Wallet turnover, balance-weighted mean", "turns a year", (["turnover", "e_p", GROUP, "weighted"],), None,
     None, one_place),
    ("(b)", "MicroVelocity, top tenth's share of the group's sum", "share",
     (["holding_velocity", "lifo", GROUP, "top_tenth_share"],), None, None, share),
    ("(b)", "MicroVelocity, median person", "turns a year", (["holding_velocity", "lifo", GROUP, "median"],), None,
     None, lambda v: share(v, 5)),
    ("(b)", "Aggregate velocity, MicroVelocity summed over everyone", "turns a year", EVERYONE, group_sum,
     "everyone", lambda v: share(v, 2)),
    ("(c)", "Mean holding time of money spent, last in first out", "days",
     (["holding_velocity", "lifo", GROUP, "mean_tau"],), None, None, one_place),
    ("(c)", "Mean holding time of money spent, first in first out", "days",
     (["holding_velocity", "fifo", GROUP, "mean_tau"],), None, None, one_place))
# Every stored path the table and its checks read, kept from each job (``kept_circulation``).
CIRCULATION_PATHS = (tuple({path_text(p): p for p in chain.from_iterable(row[3] for row in CIRCULATION_ROWS)}.values())
                     + EVERYONE_OUTFLOW)


def people_of(arm, override=None):
    """Whose people a row covers, in words: everyone under banks and cards (no network), else the participants."""
    return override or ("everyone" if CIRCULATION_GROUP[arm] == "non_participants" else "participants")


def circulation_cell(store, key, arm, paths, combine):
    """One cell's value of a circulation record for ``arm``: each seed's mean over years 4 and 5 (undefined where
    either year is), then the mean over seeds. Returns (value, absent): NaN where undefined, and ``absent`` true
    when a seed does not store a path (or the cell has no stored job)."""
    jobs = store.monthly.get(key, [])
    found = [[dig(job, ["circulation", arm, path_text(p)]) for p in paths] for job in jobs]
    if not found or any(v is MISSING for v in chain.from_iterable(found)):
        return np.nan, True
    # seeds x paths x years, None (undefined) as NaN; then each seed's yearly value and its window mean.
    blocks = [np.array(lists, dtype=float) for lists in found]
    yearly = [block[0] if combine is None else combine(block) for block in blocks]
    seeds = np.array([np.mean(y[CIRCULATION_YEARS]) if y.size >= CIRCULATION_YEARS.stop else np.nan for y in yearly])
    return float(np.mean(seeds)), False


def circulation_values(store, cells, arm, paths, combine):
    """``circulation_cell`` over ``cells``: (values, cells lacking a stored path)."""
    found = [circulation_cell(store, cell_key(c), arm, paths, combine) for c in cells]
    return np.array([v for v, _ in found], float), sum(a for _, a in found)


def circulation_source(cells, arm, paths):
    """The source text of a circulation number: the jobs, the stored paths (group filled in) and the reading."""
    shown = ", ".join("series." + arm + "." + path_text([CIRCULATION_GROUP[arm] if k == GROUP else k for k in p])
                      for p in paths)
    return (f"measures.json: jobs at {describe(cells)}, {shown}, years 4 and 5 (index 3:5), each seed's mean of "
            "the two years, then the seed mean")


def circulation_table(store, ledger):
    """How money circulates under each arrangement, over the cells with no distress: for each statistic and
    arrangement (banks and cards, best-case DeFi, the pool without the charge, CPM), whose people it covers and the
    median and range over cells of the seed means of years 4 and 5. (a) Wallet turnover, (b) MicroVelocity's
    concentration and the aggregate velocity, (c) the mean holding time of money spent, under both orderings."""
    cells = store.pick(distress=0.0)

    def row(spec, arm):
        """One (statistic, arrangement) row."""
        question, label, unit, paths, combine, who, fmt = spec
        values, absent = circulation_values(store, cells, arm, paths, combine)
        source = circulation_source(cells, arm, paths)
        where = lambda how: f"circulation[{label}, {NAMES[arm]}, {how}]"
        return [question if arm == CIRCULATION_ARMS[0] else "", label if arm == CIRCULATION_ARMS[0] else "",
                unit if arm == CIRCULATION_ARMS[0] else "", NAMES[arm], people_of(arm, who),
                reduce(ledger, where("median"), values, absent, "median", fmt, source),
                reduce(ledger, where("range"), values, absent, "range", fmt, source)]

    rows = [row(spec, arm) for spec, arm in product(CIRCULATION_ROWS, CIRCULATION_ARMS)]
    circulation_checks(store, ledger, cells)
    per = len(CIRCULATION_ARMS)
    return dict(spec="lllllrr", head=["", "Statistic", "Unit", "Arrangement", "People", "Median", "Range"], rows=rows,
                rule_before=list(range(per, len(rows), per)))


def circulation_checks(store, ledger, cells):
    """The report's note on the aggregate velocity from the coin ages against the same from outflows (no money is
    right-censored there): the coin-age estimator leaves out money unspent when the run ends, as its authors' does,
    so year 5 reads a little low. Median over cells, by arrangement."""
    for arm in CIRCULATION_ARMS:
        ages, _ = circulation_values(store, cells, arm, EVERYONE, group_sum)
        flows, _ = circulation_values(store, cells, arm, EVERYONE_OUTFLOW, group_sum)
        if np.isfinite(ages).any() and np.isfinite(flows).any():
            ledger.notes.append(f"circulation: {NAMES[arm]}, aggregate velocity, years 4 and 5, median over cells: "
                                f"{np.nanmedian(ages):.3f} turns a year from coin ages (last in first out), "
                                f"{np.nanmedian(flows):.3f} from outflows (microvelocity.e_p_savings)")


def circulation_macros(store, ledger):
    """HoldingDaysCpm and HoldingDaysPool: the mean holding time of money spent by participants, in days, under
    last in first out, years 4 and 5, median over the cells with no distress, for CPM and for the pool without the
    charge: the circulation table's own reading."""
    cells = store.pick(distress=0.0)
    path = (["holding_velocity", "lifo", GROUP, "mean_tau"],)
    found = {}
    for name, arm in (("HoldingDaysCpm", CPM), ("HoldingDaysPool", "U")):
        values, absent = circulation_values(store, cells, arm, path, None)
        found[name] = reduce(ledger, name, values, absent, "median", one_place, circulation_source(cells, arm, path))
    # The aggregate velocity of everyone (MicroVelocity summed over all people), median over the same cells.
    for name, arm in (("VelocityBanks", "S0"), ("VelocityDefi", "M0"), ("VelocityPool", "U"), ("VelocityCpm", CPM)):
        values, absent = circulation_values(store, cells, arm, EVERYONE, group_sum)
        # Two decimals: the pool's velocity with and without the charge differ in the second.
        found[name] = reduce(ledger, name, values, absent, "median", lambda v: share(v, 2),
                             circulation_source(cells, arm, EVERYONE))
    return found


# ----------------------------------------------------------------------------------------------------------------------
# Docking: theory against simulation
# ----------------------------------------------------------------------------------------------------------------------
def alternative(store, key):
    """Owners' alternative a in one cell, % a year: the runner's stored alternative_pct, which is one number in a
    run, so every seed of a cell must store the same (else the script stops). NaN where not stored."""
    values, absent = seed_values(store, key, ["arms", CPM, "owners_excess", "alternative_pct"])
    if absent or not values.size or not np.isfinite(values).any():
        return np.nan
    return float(constant_text(values[np.isfinite(values)], float, f"owners' alternative in {key}"))


def per_cell_monthly(store, keys, read):
    """``read(blocks)`` for each cell, ``blocks`` a function of a series name giving the seeds x months array of
    CPM (None if any seed lacks it); NaN for a cell ``read`` cannot compute (it returns None)."""
    values = [read(lambda series, k=k: monthly_block(store, k, CPM, series)) for k in keys]
    return np.array([np.nan if v is None else v for v in values], float)


def ratio_w2(blocks, top, bottom):
    """Seed mean of each seed's W2 mean of series ``top`` over its W2 mean of ``bottom``; None if not stored."""
    a, b = blocks(top), blocks(bottom)
    if a is None or b is None:
        return None
    return float(np.nanmean(window_mean(a, YEARS_4_5) / window_mean(b, YEARS_4_5)))


def below_target(blocks):
    """Share of the cell's seed-months after launch with pool capital N below TARGET_SHARE of its limit N*, over
    the months where N* is positive; None if not stored."""
    held, target = blocks("N"), blocks("Q")
    if held is None or target is None:
        return None
    seen = np.isfinite(held) & np.isfinite(target) & (target > 0)
    return float(np.mean(held[seen] < TARGET_SHARE * target[seen])) if seen.any() else None


def quote_at_target(blocks):
    """Seed mean of the published quote, % a year, over the months the pool's capital is at its target (N at least
    TARGET_SHARE of N*); None if not stored or never at target."""
    held, target, quote = blocks("N"), blocks("Q"), blocks("quote")
    if held is None or target is None or quote is None:
        return None
    at = np.isfinite(held) & np.isfinite(target) & (target > 0) & (held >= TARGET_SHARE * target)
    kept = np.where(at, quote, np.nan)
    seen = np.isfinite(kept).sum(axis=1) > 0
    return float(np.mean(1200 * np.nanmean(kept[seen], axis=1))) if seen.any() else None


def participation_path(launch, j0, j1, lambdas, months):
    """The participation path A(t+1) = A + (j0 + j1 A)(1 - A) - lambda A from A(0) = launch, for every launch level
    and every lambda at once: a lambdas x launches x (months + 1) array. One loop over time, which a recursion
    needs; everything else is vectorised."""
    path = np.empty((lambdas.size, launch.size, months + 1))
    path[:, :, 0] = launch[None, :]
    for t in range(months):
        a = path[:, :, t]
        path[:, :, t + 1] = a + (j0 + j1 * a) * (1 - a) - lambdas[:, None] * a
    return path


def docking_table(store, ledger):
    """Theory against simulation over CPM's cells with no distress, one row per prediction: the formula value and
    the simulated value (each low to high over cells) and the largest gap over cells. Predictions whose inputs the
    result does not store are placeholders, named in the report."""
    cells = store.pick(distress=0.0, arm=CPM)
    keys = [cell_key(c) for c in cells]
    a = np.array([alternative(store, k) for k in keys])                         # owners' alternative, % a year
    get = lambda path: column(cells, [CPM] + path)[0]
    c, theta, r_g, r_b = get(["c_pct"]), get(["theta"]), get(["r_g_pct"]), get(["r_b_pct"])
    coverage = get(["coverage"])
    book_over_wallet = per_cell_monthly(store, keys, lambda b: ratio_w2(b, "P_bar", "p_bt"))
    below = per_cell_monthly(store, keys, below_target)
    quote = per_cell_monthly(store, keys, quote_at_target)
    src = f"over {describe(cells)}"
    rows = [
        dock(ledger, r"Demurrage rate $c = aB/W$ (the standby part $(a - p)S/W$ is not stored), \% a year",
             a * book_over_wallet,
             c, lambda v: pct(v, 3), f"a: cells.json owners_excess.alternative_pct; B/W: measures.json monthly P_bar "
             f"/ p_bt, W2; c: summary.json {CPM}.c_pct; {src}"),
        dock(ledger, r"$\theta = a / r_g$", a / r_g, theta, share,
             f"a as above; r_g: summary.json {CPM}.r_g_pct; theta: {CPM}.theta; {src}"),
        # The bridge price is the gross coupon less the covered capital part. Its other form, o + f + the learned
        # loss, cannot be rebuilt from a stored result (neither f nor the learned loss is stored); the equation
        # test checks that form exactly on a run's own records.
        dock(ledger, r"Bridge price $= r_g - \kappa a$, \% a year", r_g - coverage * a, r_b,
             lambda v: pct(v, 2), f"r_g: summary.json {CPM}.r_g_pct; kappa: {CPM}.coverage; a as above; "
             f"r_b: {CPM}.r_b_pct; {src}"),
        dock(ledger, f"Seed-months with capital below {TARGET_SHARE} of its target", np.zeros(len(keys)), below,
             share, f"measures.json monthly N and Q after launch; {src}"),
        dock(ledger, r"Quote at the target $= a$, \% a year", a, quote, lambda v: pct(v, 2),
             f"measures.json monthly quote where N >= {TARGET_SHARE} Q; a as above; {src}"),
    ]
    # How each row holds. The simulation computes the charge, the bridge price and the quote by the contract's own
    # equations, and theta is a ratio of recorded flows that the coupon fixes, so those rows hold by construction:
    # they check that the code runs the contract as written and that its records add up. Where capital stands
    # against its target and how participation moves are behaviour, which the propositions predict.
    kinds = [BY_CONSTRUCTION, BY_CONSTRUCTION, BY_CONSTRUCTION, IN_PART, BY_CONSTRUCTION]
    rows = [row + [kind] for row, kind in zip(rows, kinds)]
    rows += [row + [PREDICTION] for row in participation_rows(store, ledger, cells, keys)]
    return dict(spec="lrrrl", head=["Quantity", "Formula", "Simulated", "Largest gap", "Holds"], rows=rows)


# How a row of the docking table holds; capital is at its target only when offers fill the room, so in part.
BY_CONSTRUCTION, PREDICTION, IN_PART = "by construction", "as predicted", "in part"


def dock(ledger, label, formula, simulated, fmt, source):
    """One docking row: formula and simulated values, each low to high over cells, and the largest absolute gap.
    A placeholder wherever any cell lacks an input (no number from part of the cells)."""
    where = lambda col: f"docking[{label}, {col}]"
    cells = formula.size
    missing = lambda values: not values.size or not np.isfinite(values).all()
    texts = [ledger.lack(where(col), f"not computable in every cell from stored fields: {source}") if missing(values)
             else ledger.add(where(col), span(values.min(), values.max(), fmt), f"{source} ({cells} cells)")
             for col, values in (("formula", formula), ("simulated", simulated))]
    gap = np.abs(simulated - formula)
    texts.append(ledger.lack(where("gap"), "an input is not stored") if PLACEHOLDER in texts else
                 ledger.add(where("gap"), fmt(gap.max()), f"max over cells of |simulated - formula|: {source}"))
    return [label] + texts


def participation_rows(store, ledger, cells, keys):
    """Participation at months 12, 36 and 60 after launch against the path A(t+1) = A + (j0 + j1 A)(1 - A) -
    lambda A from each cell's launch level, j0 and j1 the stored xi0 and xi1 and one lambda fitted (least squares
    over every cell and the three months, on LAMBDAS). The simulated value is each cell's seed mean of the stored
    monthly A (index m - 1 for month m)."""
    j0, j1 = (dig(store.summary, ["inputs", name]) for name in ("xi0", "xi1"))
    blocks = [monthly_block(store, k, CPM, "A") for k in keys]
    label = lambda m: f"Participation at month {m}"
    if MISSING in (j0, j1) or not blocks or any(b is None for b in blocks):
        why = "summary.json inputs.xi0/xi1" if MISSING in (j0, j1) else "measures.json monthly A of every seed"
        lacking = lambda m: [label(m)] + [ledger.lack(f"docking[{label(m)}, {col}]", why)
                                          for col in ("formula", "simulated", "gap")]
        return list(map(lacking, GAP_MONTHS))
    at = np.array(GAP_MONTHS) - 1                                         # month m sits at index m - 1
    simulated = np.array([np.nanmean(b[:, at], axis=0) for b in blocks])  # cells x months
    launch = np.array([c["a0"] for c in cells], float)
    # The model at the three months for every lambda and cell: lambdas x cells x months.
    path = participation_path(launch, float(j0), float(j1), LAMBDAS, int(at.max()))[:, :, at]
    error = np.nansum((path - simulated[None]) ** 2, axis=(1, 2))
    best = int(np.argmin(error))
    ledger.notes.append(f"Participation path: lambda fitted {LAMBDAS[best]:.5f} a month (grid {LAMBDAS[0]} to "
                        f"{LAMBDAS[-1]}, step {LAMBDAS[1] - LAMBDAS[0]:.5f}); xi0 {j0}, xi1 {j1}")
    if best == LAMBDAS.size - 1:
        # Zero is a true floor (no one leaving), but the upper end is only the grid's: widen LAMBDAS if this shows.
        ledger.notes.append("Participation path: the fitted lambda sits at the top of its grid")
    model = path[best]
    src = (f"model: summary.json inputs.xi0, xi1, fitted lambda {LAMBDAS[best]:.5f}; simulated: measures.json monthly "
           f"{CPM}.A seed mean; over {describe(cells)}")
    return [dock(ledger, label(m), model[:, k], simulated[:, k], share, f"{src}, index {m - 1}")
            for k, m in enumerate(GAP_MONTHS)]


# ----------------------------------------------------------------------------------------------------------------------
# Side results
# ----------------------------------------------------------------------------------------------------------------------
# The side table's three blocks of columns: heading, the distress level read, the stored path, the format.
SIDE_BLOCKS = (("Gain over banks and cards", 0.0, [CPM, "against", "S0", "gain_usd_a_year"], usd),
               ("Gain over best-case DeFi", 0.0, [CPM, "against", "M0", "gain_usd_a_year"], usd),
               (f"Bridges served at {HEADLINE * 100:g} points", HEADLINE, [CPM, "bridges_drawn_over_wanted"],
                lambda v: share(v, 2)))


def label_of(name):
    """A result's name as a table prints it: underscores become spaces and a per cent sign is escaped."""
    return name.replace("_", " ").replace(r"\%", "%").replace("%", r"\%")


def file_of(store):
    """A result's summary file as the report names it: the folder's name, never its place on a machine."""
    return f"{Path(store.folder).name}/summary.json"


def base_label(store):
    """What the side and bound tables call the map their rows stand beside: the development map, or the main map
    where it ran on another seed set."""
    return "development map" if dig(store.summary, ["seed_set"]) == "development" else "main map"


def side_table(main, sides, ledger, label=None):
    """The side checks beside the main map, one row per result: CPM's gain in money over banks and cards and over
    best-case DeFi with no distress, and bridges served in years 4 and 5 at the headline distress level, at each
    launch level the side checks ran (cells at the stress table's outside rate)."""
    at_rate = lambda store: {k for k in store.index if abs(k[0] - STRESS_RATE) < TOL}
    # A side check not yet run has no cells; its row is placeholders and the other results set the columns.
    shared = at_rate(main).intersection(*(at_rate(side) for _, side in sides if not side.is_pending))
    launches = sorted({k[1] for k in shared if k[2] == 0.0})

    def value(name, store, block, launch):
        """One number: this result, this block of columns, this launch level."""
        label, level, path, fmt = block
        where = f"side[{name}, {label}, launch {launch * 100:g}%]"
        key = next((k for k in at_rate(store) if abs(k[1] - launch) < TOL and abs(k[2] - level) < TOL), None)
        if key is None:
            return ledger.lack(where, f"{file_of(store)}: no cell at launch {launch} and distress {level}")
        return read(ledger, where, [store.index[key]], path, "only", fmt, file=file_of(store))

    rows = [[label_of(name)] + [value(name, store, block, a) for block, a in product(SIDE_BLOCKS, launches)]
            for name, store in ((label or base_label(main), main), *sides)]
    over = " & " + " & ".join(f"\\multicolumn{{{len(launches)}}}{{c}}{{{block[0]}}}" for block in SIDE_BLOCKS) + r" \\"
    head = ["Launch participation"] + [f"{a * 100:g}\\%" for a in launches] * len(SIDE_BLOCKS)
    return dict(spec="l" + "r" * (len(launches) * len(SIDE_BLOCKS)), over=over, head=head, rows=rows,
                rule_before=[1])


def bounds_table(main, bounds, ledger):
    """The bound maps beside the main map, one row per map, each a whole map on the same seeds with one accounting
    choice changed: CPM's median gain over banks and cards and over best-case DeFi with no distress (in money
    alone, and with completed purchases at their price), the cells of the whole grid in which every gain is
    positive and in which CPM fails fewer payments than both, the mean bridge price, and the cells with no
    distress that are stable on a majority of seeds (without the bound, and also under the cash-advance bound)."""
    gain = lambda yard, *tail: [CPM, "against", yard, *tail, "gain_usd_a_year"]

    def row(name, store):
        """One map's row."""
        zero = store.pick(distress=0.0, arm=CPM)
        tag = lambda column_name: f"bounds[{name}, {column_name}]"
        cells, positive, fewer = grid_counts(store)
        codes = np.array([majority_code(cell) for cell in zero])
        median = lambda column_name, path: read(ledger, tag(column_name), zero, path, "median", usd,
                                                file=file_of(store))
        return [label_of(name),
                median("gain over banks", gain("S0")), median("gain over DeFi", gain("M0")),
                median("gain over banks, purchases counted", gain("S0", "complete_gain", "face")),
                median("gain over DeFi, purchases counted", gain("M0", "complete_gain", "face")),
                ledger.add(tag("cells with every gain positive"), f"{positive} of {cells}", file_of(store)),
                ledger.add(tag("cells with fewer failed payments"), f"{fewer} of {cells}", file_of(store)),
                read(ledger, tag("bridge price"), zero, [CPM, "r_b_pct"], "mean", lambda v: pct(v, 1),
                     file=file_of(store)),
                ledger.add(tag("stable as built"), f"{int((codes >= 2).sum())} of {len(zero)}", file_of(store)),
                ledger.add(tag("stable both ways"), f"{int((codes == 3).sum())} of {len(zero)}", file_of(store))]

    head = ["Map", "Gain over banks", "Gain over DeFi", "Banks, purchases counted", "DeFi, purchases counted",
            "Every gain positive", "Fewer failed payments", "Bridge price", "Stable as built", "Stable both ways"]
    return dict(spec="l" + "r" * (len(head) - 1), head=head,
                rows=[row(name, store) for name, store in ((base_label(main), main), *bounds)], rule_before=[1])


# ----------------------------------------------------------------------------------------------------------------------
# Robustness: the adoption rule, the sellers' network and the launch (docs/ROBUSTNESS_PLAN.md, sections 5 and 8)
# ----------------------------------------------------------------------------------------------------------------------
ROBUST_RATE = STRESS_RATE                 # every robustness set runs at the outside rate of the side checks
ROBUST_SHOWN = (0.05, 0.2, 0.6)           # the launch levels whose participation at month 60 the table shows
END_MONTH = 60                            # participation is read at month 60 after launch (index 59)
CRITICAL_RISE = 0.05                      # critical mass: participation at month 60 above the launch share by this
SETTINGS = ("buffer_review", "joining", "thresholds", "sellers", "local_share", "launch")   # what a set changes
ORDINALS = ("First", "Second", "Third")   # macro names for the three development seeds, in seed order


def absent_why(store, what):
    """Why a number is a placeholder: the set is not yet run, or ``what`` is not stored."""
    return f"{Path(store.folder).name}: set not yet run" if store.is_pending else what


def participation_at(store, key, month=END_MONTH, arm=CPM):
    """Each seed's participation under ``arm`` at ``month`` after launch, the stored monthly A at index month - 1:
    (values, source), or (None, why) where a seed does not store it."""
    block = monthly_block(store, key, arm, "A")
    source = f"measures.json: jobs[{key}].monthly.{arm}.A[{month - 1}]"
    if block is None or block.shape[1] < month:
        return None, absent_why(store, source)
    return block[:, month - 1], source


def seeds_needed_to_survive(seeds):
    """How many seeds must show a positive gain for it to survive: two thirds of them, rounded up (two of three)."""
    return int(np.ceil(2 * seeds / 3 - TOL))


def survives(store, cell, yard):
    """Whether CPM's money gain over ``yard`` survives in one cell by the plan's rule (section 8): positive on the
    seed mean (summary.json) and in at least two of three seeds (cells.json). None where either is not stored."""
    path = [CPM, "against", yard, "gain_usd_a_year"]
    mean = dig(cell, path)
    seeds, absent = seed_values(store, cell_key(cell), ["arms"] + path)
    if mean is MISSING or mean is None or absent or not seeds.size or not np.isfinite(seeds).all():
        return None
    return bool(mean > 0 and np.sum(seeds > 0) >= seeds_needed_to_survive(seeds.size))


def common_threshold(store):
    """The common threshold a set joins by (a number under the threshold rule), else None (the linear rule, or
    thresholds uniform or measured)."""
    if dig(store.summary, ["economy", "joining"]) != "threshold":
        return None
    found = dig(store.summary, ["economy", "thresholds"])
    return float(found) if isinstance(found, (int, float)) and not isinstance(found, bool) else None


def launch_text(value):
    """A launch share as the tables print it: 0.1 reads 10\\%."""
    return f"{value * 100:g}" + r"\%"


def critical_mass(store, ledger, where):
    """The plan's critical mass (section 8): the lowest launch level whose seed-mean participation at month 60
    exceeds its launch share by at least CRITICAL_RISE; "none" if no launch level does. The launch share is the
    cell's launch level a0."""
    cells = store.pick(distress=0.0, r_out=ROBUST_RATE, arm=CPM)
    found = [(float(c["a0"]), participation_at(store, cell_key(c))) for c in cells]
    lacking = [why for _, (values, why) in found if values is None]
    if not cells or lacking:
        return ledger.lack(where, absent_why(store, lacking[0] if lacking else "no cell with no distress"))
    rise = [(a, float(np.mean(values)) - a) for a, (values, _) in found]
    above = [a for a, gain in rise if gain >= CRITICAL_RISE - TOL]
    return ledger.add(where, "none" if not above else launch_text(min(above)),
                      f"lowest a0 whose seed mean of measures.json monthly {CPM}.A[{END_MONTH - 1}] exceeds a0 by at "
                      f"least {CRITICAL_RISE} in {file_of(store)}; rises "
                      + ", ".join(f"{a:g}: {gain:+.3f}" for a, gain in rise))


SHOCK_END = 36                                        # the last month of the distress year, after launch


def earned_after_shock(store, cells, yard):
    """CPM's gain in money over ``yard`` earned after the distress year in each of ``cells``, a year, and how many
    cells lack a stored gain. The summary stores the mean wealth gain at month SHOCK_END and at the end, each
    annualised over the months elapsed, so what is earned in between is
    (end x months - at SHOCK_END x SHOCK_END) / (months - SHOCK_END)."""
    months = dig(store.summary, ["economy", "months"])
    path = [CPM, "against", yard, "gain_usd_a_year_at_month"]
    end, lacking = column(cells, path + ["end"])
    at, missing = column(cells, path + [str(SHOCK_END)])
    if months is MISSING:
        return np.full(end.shape, np.nan), len(cells)
    return (end * months - at * SHOCK_END) / (months - SHOCK_END), lacking + missing


def after_shock_macros(store, ledger, tag=""):
    """CPM's gain in money earned after the distress year, months SHOCK_END + 1 to the end, in dollars a person a
    year, against banks and cards and against best-case DeFi. The summary stores the mean wealth gain at month
    SHOCK_END and at the end, each annualised over the months elapsed, so what is earned in between is
    (end x months - at SHOCK_END x SHOCK_END) / (months - SHOCK_END). Macros, each GainAfter + ``tag`` + Banks or
    Defi + : Positive and Behind, the cells of the grid in which it is and is not above zero; Low, the lowest cell;
    MedianZero and
    MedianTwo, the median over the cells with no distress and at the stress headline. The cells in which it is not
    above zero are listed in the report's notes."""
    months, out = dig(store.summary, ["economy", "months"]), {}
    folder = Path(store.folder).name

    def against(word, yard):
        """The macros of the gain earned after the shock against one yardstick, ``yard``, named by ``word``,
        and the cells where it is not above zero, in the report's notes."""
        name = lambda tail: f"GainAfter{tag}{word}{tail}"
        path = [CPM, "against", yard, "gain_usd_a_year_at_month"]
        source = f"{folder}/summary.json: {path_text(path)}, end and {SHOCK_END}"

        earned = lambda cells: earned_after_shock(store, cells, yard)       # noqa: E731
        cells = store.pick(arm=CPM)
        values, absent = earned(cells)
        if not cells or absent:
            out.update({name(tail): ledger.lack(name(tail), source) for tail in ("Positive", "Behind", "Low",
                                                                                 "MedianZero", "MedianTwo",
                                                                                 "LowerTwo")})
            return
        out[name("Positive")] = ledger.add(name("Positive"), str(int((values > 0).sum())),
                                           f"cells of {len(cells)} with the gain earned after month {SHOCK_END} above "
                                           f"zero; {source}")
        out[name("Behind")] = ledger.add(name("Behind"), str(int((~(values > 0)).sum())),
                                         f"cells of {len(cells)} with it not above zero; {source}")
        out[name("Low")] = reduce(ledger, name("Low"), values, 0, "low", usd, source)
        for tail, level in (("MedianZero", 0.0), ("MedianTwo", HEADLINE)):
            out[name(tail)] = reduce(ledger, name(tail), *earned(store.pick(distress=level, arm=CPM)), "median", usd,
                                     f"{source}, distress {level * 100:g} pt")
        levels = [(lambda values, absent: np.nan if absent or not values.size else float(np.nanmedian(values)))(
            *earned(store.pick(distress=level, arm=CPM))) for level in (HEADLINE, 0.0)]
        out[name("LowerTwo")] = change_macro(ledger, name("LowerTwo"), *levels,
                                             f"the median at {HEADLINE * 100:g} pt against the median with no distress; "
                                             f"{source}")
        behind = [cell_key(cell) for cell, value in zip(cells, values) if not value > 0]
        if behind:
            ledger.notes.append(f"{folder}: the gain earned after month {SHOCK_END} against {NAMES[yard]} is not "
                                "above zero at (outside rate, launch, distress): "
                                + "; ".join(f"({r * 100:g}%, {a * 100:g}%, {d * 100:g} pt)" for r, a, d in behind))

    for word, yard in (("Banks", "S0"), ("Defi", "M0")):
        against(word, yard)
    return out


NO_CARD_CLASSES = (0, 1)                              # the two classes without a card, in the classes' stored order


def shortfall_macros(store, ledger):
    """What fails, over the cells with no distress (medians over cells), under banks and cards and under CPM, from
    the by-class records: FailedValue + Banks or Cpm, the value not paid on its first due date, bills, purchases and
    wages together, dollars a person a year; FailedWageShare + Banks or Cpm, the share of that value that is wages
    (the rest is purchases lost); NoCardFailedShare + Banks or Cpm, the share of it whose payer holds no card; and
    NoCardPeople, the share of people who hold none. The failed share of the payments table is another measure: it
    leaves wages out of both the value unpaid and the value due."""
    cells, out = store.pick(distress=0.0, arm=CPM), {}
    whole = lambda v: pct(100 * v, 0)

    def shares(record):
        """One by-class record's three shares, or None where it lacks a field."""
        sizes, failed, wages = (dig(record, [name]) for name in ("class_sizes", "failed", "wages_late"))
        if MISSING in (sizes, failed, wages) or None in list(failed) + list(wages):
            return None
        sizes, failed, wages = (np.asarray(values, float) for values in (sizes, failed, wages))
        value, mine = failed * sizes, list(NO_CARD_CLASSES)
        return ((wages * sizes).sum() / value.sum(), value[mine].sum() / value.sum(), sizes[mine].sum() / sizes.sum(),
                value.sum() / sizes.sum())

    def failed_of(word, path):
        """The shortfall macros of one arrangement, named by ``word``, from its by-class records at ``path``."""
        found = [shares(dig(cell, path)) for cell in cells]
        source = f"summary.json: cells[{describe(cells)}].{path_text(path)}: class_sizes, failed, wages_late"
        wanted = [(f"FailedWageShare{word}", 0, whole), (f"NoCardFailedShare{word}", 1, whole),
                  (f"FailedValue{word}", 3, usd)]
        if word == "Banks":
            wanted.append(("NoCardPeople", 2, lambda v: pct(100 * v, 1)))
        for name, k, fmt in wanted:
            if not found or any(one is None for one in found):
                out[name] = ledger.lack(name, source)
            else:
                out[name] = reduce(ledger, name, np.array([one[k] for one in found], float), 0, "median", fmt, source)

    for word, path in (("Banks", ["S0_by_class"]), ("Cpm", [CPM, "by_class"])):
        failed_of(word, path)
    return out


def whole_pct(value):
    """A share as a whole per cent, its size alone: 0.337 and -0.337 both read 34\\%. The text says which way."""
    return pct(abs(100 * value), 0)


def change_macro(ledger, name, new, old, source):
    """The relative change from ``old`` to ``new`` as a whole per cent without its sign, recorded with both levels;
    a placeholder where either is undefined or ``old`` is zero."""
    if not (np.isfinite(new) and np.isfinite(old)) or abs(old) < TOL:
        return ledger.lack(name, source)
    return ledger.add(name, whole_pct(new / old - 1), f"{new:.4g} against {old:.4g}: {source}")


OUTSIDE_SPREAD = "banks_and_funds"                    # the spread banks and funds keep on balances: yield forgone


def percent_macros(store, ledger):
    """The scale-free readings the abstract and the running text lead with, over the cells with no distress unless
    said. FailCut + Banks, Defi, PoolBanks, BanksStress, DefiStress: the relative cut in the mean failed share
    (CPM against banks and cards and against best-case DeFi, the pool without the charge against banks, and CPM
    against each at the stress headline). Outside...: what households pay the intermediaries outside the household
    economy net of what they pay back (each cell's stored transfers, a year): its median under banks and cards,
    best-case DeFi and CPM (OutsidePaid + Banks, Defi, Cpm); CPM's cut cell by cell, the median, lowest and highest
    against banks (OutsideCutBanks, ...Low, ...High) and the median against DeFi (OutsideCutDefi); and the median
    cut against banks leaving out the spread on balances (OutsideCashCutBanks). BridgeCutLow and BridgeCutHigh:
    the lowest and highest cut of the bridge price against the pool without the charge. And the gain in money as a
    share of a year of the model's unit of spending (GainBanksSpending, GainDefiSpending, with Face for completed
    purchases at their price, and PersonMedian...Spending for the median person)."""
    out = {}
    zero, stress = store.pick(distress=0.0), store.pick(distress=HEADLINE)
    cpm = store.pick(distress=0.0, arm=CPM)
    mean_of = lambda cells, arm: (lambda values, absent: np.nan if absent or not values.size else
                                  float(np.nanmean(values)))(*column(cells, failure_path(arm)))
    for name, cells, new, old in (("FailCutBanks", zero, CPM, "S0"), ("FailCutDefi", zero, CPM, "M0"),
                                  ("FailCutPoolBanks", zero, "U", "S0"), ("FailCutBanksStress", stress, CPM, "S0"),
                                  ("FailCutDefiStress", stress, CPM, "M0")):
        out[name] = change_macro(ledger, name, mean_of(cells, new), mean_of(cells, old),
                                 f"summary.json: cells[{describe(cells)}]: mean failed share, {NAMES[new]} against "
                                 f"{NAMES[old]}")
    months, unit = dig(store.summary, ["economy", "months"]), dig(store.summary, ["constants", "MONTH_USD"])

    def paid(cells, path, cash=False):
        """What households pay outside a year in each cell, the spread on balances left out when ``cash``."""
        found = [dig(cell, path) for cell in cells]
        if months is MISSING or not found or any(one is MISSING for one in found):
            return None
        total = lambda lines: sum((line or {}).get("paid_usd") or 0.0 for key, line in lines.items()
                                  if key != "total" and not (cash and key == OUTSIDE_SPREAD))
        return np.array([total(lines) for lines in found], float) * 12 / months

    arms = dict(Banks=["S0_transfers"], Defi=["M0", "transfers"], Cpm=[CPM, "transfers"])
    levels = {word: paid(cpm, path) for word, path in arms.items()}
    source = f"summary.json: cells[{describe(cpm)}]: transfers, every line's paid_usd, a year"
    names = ("OutsidePaidBanks", "OutsidePaidDefi", "OutsidePaidCpm", "OutsideCutBanks", "OutsideCutBanksLow",
             "OutsideCutBanksHigh", "OutsideCutDefi", "OutsideCashCutBanks")
    if any(values is None for values in levels.values()):
        out.update({name: ledger.lack(name, source) for name in names})
    else:
        for word, values in levels.items():
            out[f"OutsidePaid{word}"] = reduce(ledger, f"OutsidePaid{word}", values, 0, "median", usd, source)
        cut = 1 - levels["Cpm"] / levels["Banks"]
        for name, how in (("OutsideCutBanks", "median"), ("OutsideCutBanksLow", "low"), ("OutsideCutBanksHigh", "high")):
            out[name] = reduce(ledger, name, cut, 0, how, whole_pct, f"each cell's cut, CPM against banks; {source}")
        out["OutsideCutDefi"] = reduce(ledger, "OutsideCutDefi", 1 - levels["Cpm"] / levels["Defi"], 0, "median",
                                       whole_pct, f"each cell's cut, CPM against best-case DeFi; {source}")
        cash = 1 - paid(cpm, arms["Cpm"], True) / paid(cpm, arms["Banks"], True)
        out["OutsideCashCutBanks"] = reduce(ledger, "OutsideCashCutBanks", cash, 0, "median", whole_pct,
                                            f"each cell's cut without {OUTSIDE_SPREAD}; {source}")
    mine, lacking = column(cpm, [CPM, "r_b_pct"])
    other, missing = column(cpm, ["U", "r_b_pct"])
    cut = 1 - np.divide(mine, other, out=np.full(mine.shape, np.nan), where=other > 0)
    source = f"summary.json: cells[{describe(cpm)}]: each cell's {CPM}.r_b_pct against U.r_b_pct"
    out["BridgeCutLow"] = reduce(ledger, "BridgeCutLow", cut, lacking + missing, "low", whole_pct, source)
    out["BridgeCutHigh"] = reduce(ledger, "BridgeCutHigh", cut, lacking + missing, "high", whole_pct, source)
    gain = lambda yard, *tail: [CPM, "against", yard, *tail]
    for name, path in (("GainBanksSpending", gain("S0", "gain_usd_a_year")),
                       ("GainDefiSpending", gain("M0", "gain_usd_a_year")),
                       ("GainBanksFaceSpending", gain("S0", "complete_gain", "face", "gain_usd_a_year")),
                       ("GainDefiFaceSpending", gain("M0", "complete_gain", "face", "gain_usd_a_year")),
                       ("PersonMedianBanksSpending", gain("S0", "dispersion", "wealth", "percentiles_usd_a_year", "50")),
                       ("PersonMedianDefiSpending", gain("M0", "dispersion", "wealth", "percentiles_usd_a_year", "50"))):
        values, absent = column(cpm, path)
        scale = np.nan if unit is MISSING else 100 / (12 * float(unit))
        out[name] = reduce(ledger, name, values * scale, absent + (unit is MISSING), "median", lambda v: pct(v, 2),
                           f"summary.json: cells[{describe(cpm)}].{path_text(path)} over 12 x constants.MONTH_USD")
    return out


def robust_stress_macros(robust, ledger):
    """The robustness variants that also hold cells under the stress headline (HEADLINE points of distress at
    ROBUST_RATE): for each, RobustStress<stem>Cells, the mean over those cells of the failed share under CPM, banks
    and cards and best-case DeFi (...FailCpm, ...FailBanks, ...FailDefi), the cells in which CPM fails fewer
    payments than both (...Fewer), the cells in which its gain in money over both is positive (...GainPositive)
    and bridges served at the highest launch level (...ServedHigh). A variant with no such cell gets no macro."""
    out = {}

    def variant(stem, store):
        """One variant's macros under the stress headline, none where it holds no such cell."""
        cells = [c for c in store.pick(distress=HEADLINE, r_out=ROBUST_RATE, arm=CPM)]
        if not cells:
            return
        name, src = (lambda tail: f"RobustStress{stem}{tail}"), f"{file_of(store)}: cells[{describe(cells)}]"
        out[name("Cells")] = ledger.add(name("Cells"), str(len(cells)), src)
        fails = {}
        for tail, arm in (("FailCpm", CPM), ("FailBanks", "S0"), ("FailDefi", "M0")):
            fails[arm], absent = column(cells, failure_path(arm))
            out[name(tail)] = reduce(ledger, name(tail), fails[arm], absent, "mean", lambda v: pct(v, 2),
                                     f"{src}.{path_text(failure_path(arm))}")
        fewer = int(((fails[CPM] < fails["S0"]) & (fails[CPM] < fails["M0"])).sum())
        out[name("Fewer")] = ledger.add(name("Fewer"), str(fewer), f"{src}: CPM's failed share below both others'")
        gains = np.array([column(cells, [CPM, "against", yard, "gain_usd_a_year"])[0] for yard in ("S0", "M0")])
        out[name("GainPositive")] = ledger.add(name("GainPositive"), str(int((gains > 0).all(axis=0).sum())),
                                               f"{src}: {CPM}.against.S0 and .M0 gain_usd_a_year both above zero")
        top = max(cells, key=lambda c: c["a0"])
        out[name("ServedHigh")] = read(ledger, name("ServedHigh"), [top], [CPM, "bridges_drawn_over_wanted"], "only",
                                       lambda v: share(v, 2), file=file_of(store))

    for _, stem, _, store in robust:
        variant(stem, store)
    return out


def robust_table(robust, ledger):
    """The robustness table and its macros. ``robust`` lists (group, stem, label, store), the base first: one row per
    variant over its launch cells with no distress at ROBUST_RATE. Participation at month 60 from the launch levels
    ROBUST_SHOWN (seed means); CPM's gain in money over banks and over best-case DeFi (median over cells and the
    lowest to highest cell); the cells in which each gain survives by the plan's rule; the failed share under CPM and
    under banks, the bridge price and the holding charge (medians over cells); and under a common threshold the
    critical mass. Macros: for each variant Robust<stem>SurviveBanks, ...SurviveDefi (the counts) and ...PartFive
    (participation at month 60 from 5% launch), and for a common threshold Robust<stem>CriticalMass."""
    out, rows, rules, last = {}, [], [], None
    gain = lambda yard: [CPM, "against", yard, "gain_usd_a_year"]
    for group, stem, label, store in robust:
        if group != last and rows:
            rules.append(len(rows))
        cells = store.pick(distress=0.0, r_out=ROBUST_RATE, arm=CPM)
        tag = lambda column_name: f"robust[{group}, {label}, {column_name}]"
        src = file_of(store)
        if store.is_pending:
            ledger.notes.append(f"robust[{group}, {label}]: {Path(store.folder).name} not yet run; its row is "
                                "placeholders")
        else:
            settings = [(name, dig(store.summary, ["economy", name])) for name in SETTINGS]
            ledger.notes.append(f"robust[{group}, {label}]: {Path(store.folder).name} settings: " + (
                "none stored (run before the switches existed, so every switch at its default)"
                if all(value is MISSING for _, value in settings) else
                ", ".join(f"{name} {value!r}" for name, value in settings)))

        def part(launch):
            """Participation at month 60 from one launch level, the seed mean."""
            where = tag(f"participation at month {END_MONTH}, launch {launch * 100:g}%")
            key = next((cell_key(c) for c in cells if abs(c["a0"] - launch) < TOL), None)
            if key is None:
                return ledger.lack(where, absent_why(store, f"{src}: no cell at launch {launch:g}, no distress"))
            values, source = participation_at(store, key)
            if values is None:
                return ledger.lack(where, source)
            return reduce(ledger, where, values, 0, "mean", lambda v: share(v, 2), source)

        def count(yard, name):
            """The cells in which the gain over ``yard`` survives, as "k of n", and k alone for the macro."""
            where = tag(f"cells where the gain over {name} survives")
            found = [survives(store, c, yard) for c in cells]
            if not found or any(f is None for f in found):
                text = ledger.lack(where, absent_why(store, f"{src} and cells.json: {CPM}.against.{yard}."
                                                            "gain_usd_a_year in every cell and seed"))
                return text, text
            failing = [f"{c['a0']:g}" for c, f in zip(cells, found) if not f]
            source = (f"{src}: {CPM}.against.{yard}.gain_usd_a_year > 0 on the seed mean and in at least two of three "
                      f"seeds (cells.json arms.{CPM}.against.{yard}), over {describe(cells)}; not surviving at a0 "
                      + (", ".join(failing) or "none"))
            return ledger.add(where, f"{sum(found)} of {len(found)}", source), str(sum(found))

        banks, banks_count = count("S0", "banks")
        defi, defi_count = count("M0", "DeFi")
        median = lambda name, path, fmt: read(ledger, tag(name), cells, path, "median", fmt, file=src)
        spread = lambda name, path, fmt: read(ledger, tag(name), cells, path, "range", fmt, file=src)
        threshold = common_threshold(store)
        # A set not yet run does not say whether it has a common threshold, so its critical mass is a placeholder.
        mass = (critical_mass(store, ledger, tag("critical mass")) if threshold is not None else
                ledger.lack(tag("critical mass"), absent_why(store, "")) if store.is_pending else "")
        shown = [part(a) for a in ROBUST_SHOWN]
        rows.append([group if group != last else "", label, *shown,
                     median("gain over banks, median", gain("S0"), usd),
                     spread("gain over banks, range", gain("S0"), usd),
                     median("gain over DeFi, median", gain("M0"), usd),
                     spread("gain over DeFi, range", gain("M0"), usd),
                     banks, defi,
                     median("failed payments, CPM", failure_path(CPM), lambda v: pct(v, 2)),
                     median("failed payments, banks", failure_path("S0"), lambda v: pct(v, 2)),
                     median("bridge price", [CPM, "r_b_pct"], lambda v: pct(v, 2)),
                     median("holding charge", [CPM, "c_pct"], lambda v: pct(v, 3)), mass])
        named = (("SurviveBanks", banks_count, "cells where the gain over banks survives"),
                 ("SurviveDefi", defi_count, "cells where the gain over DeFi survives"),
                 ("PartFive", shown[0], f"participation at month {END_MONTH}, launch 5%"))
        out.update({f"Robust{stem}{name}": ledger.add(f"Robust{stem}{name}", text, f"as {tag(column_name)}")
                    for name, text, column_name in named})
        if threshold is not None or store.is_pending:
            out[f"Robust{stem}CriticalMass"] = ledger.add(f"Robust{stem}CriticalMass", mass,
                                                           f"as {tag('critical mass')}, common threshold "
                                                           + ("pending" if threshold is None else f"{threshold:g}"))
        last = group
    over = (r" & & \multicolumn{3}{c}{Participation at month " + str(END_MONTH) + "}"
            r" & \multicolumn{2}{c}{Gain over banks} & \multicolumn{2}{c}{Gain over DeFi}"
            r" & \multicolumn{2}{c}{Cells where it survives} & \multicolumn{2}{c}{Failed payments} & & & \\")
    head = ["Sellers", "Joining and launch", *(f"from {launch_text(a)}" for a in ROBUST_SHOWN), "Median", "Range",
            "Median", "Range", "Banks", "DeFi", "CPM", "Banks", "Bridge price", "Demurrage", "Critical mass"]
    return dict(spec="ll" + "r" * (len(head) - 2), over=over, head=head, rows=rows, rule_before=rules), out


def rule_check_macros(main, check, ledger):
    """The rule check (uniform thresholds under the threshold rule, which in a well-mixed population has the base's
    mean joining chance): the largest gap, over the months after launch, between its participation under CPM and
    the base's at the same cell, for each seed (RuleCheckGap<First|Second|Third>Seed) and on the seed mean
    (RuleCheckGapMean)."""
    names = ["RuleCheckGapMean"] + [f"RuleCheckGap{word}Seed" for word in ORDINALS]
    keys = [cell_key(c) for c in check.pick(distress=0.0, arm=CPM)]
    if len(keys) != 1:
        why = absent_why(check, f"{file_of(check)} holds {len(keys)} cells with no distress, not one")
        return {name: ledger.lack(name, why) for name in names}
    key = keys[0]
    by_seed = lambda store: {job["seed"]: job["monthly"].get(CPM, {}).get("A") for job in store.monthly.get(key, [])}
    mine, base = by_seed(check), by_seed(main)
    seeds = sorted(set(mine) & set(base))
    if not seeds or any(mine[s] is None or base[s] is None for s in seeds):
        return {name: ledger.lack(name, f"measures.json monthly {CPM}.A at {key} in {file_of(check)} and "
                                        f"{file_of(main)}") for name in names}
    if len(seeds) > len(ORDINALS):
        ledger.notes.append(f"rule check: {len(seeds)} seeds; the macros name the first {len(ORDINALS)}")
    gaps = np.abs(np.array([mine[s] for s in seeds]) - np.array([base[s] for s in seeds]))
    source = (f"largest over months of |{file_of(check)} - {file_of(main)}| in measures.json jobs[{key}].monthly."
              f"{CPM}.A")
    out = {"RuleCheckGapMean": ledger.add("RuleCheckGapMean", share(np.nanmax(np.abs(np.nanmean(
        np.array([mine[s] for s in seeds]), axis=0) - np.nanmean(np.array([base[s] for s in seeds]), axis=0)))),
        source + f", seed means over {len(seeds)} seeds")}
    for word, seed, row in zip(ORDINALS, seeds, gaps):
        out[f"RuleCheckGap{word}Seed"] = ledger.add(f"RuleCheckGap{word}Seed", share(np.nanmax(row)),
                                                    source + f", seed {seed}")
    for word in ORDINALS[len(seeds):]:
        out[f"RuleCheckGap{word}Seed"] = ledger.lack(f"RuleCheckGap{word}Seed", f"fewer than three seeds at {key}")
    return out


# ----------------------------------------------------------------------------------------------------------------------
# Chains of failure: the settlement records (docs/ROBUSTNESS_PLAN.md, section 4)
# ----------------------------------------------------------------------------------------------------------------------
KNOCK_DAYS = ("knock_on_days_0", "knock_on_days_1", "knock_on_days_2_3", "knock_on_days_4_7", "knock_on_days_8_15",
              "knock_on_days_16_31", "knock_on_days_32_up")       # the days by how many payers had a knock-on failure
CHAIN_SERIES = ("own_shortfall", "knock_on", "knock_on_n", "netting_days", "netting_value", "cash_completed",
                *KNOCK_DAYS)
# The table's readings: label, key in ``chain_readings``, format.
# Knock-on share: of failed value; payers a day: with a knock-on failure; days with 32 or more: such payers; netting
# share: of completed cash-route value; netting days: with a non-empty set, over the run.
CHAIN_COLUMNS = (("Knock-on share", "knock_share", lambda v: pct(100 * v, 2)),
                 ("Payers a day", "payers_a_day", lambda v: share(v, 1)),
                 ("Days with 32 or more", "many_days", lambda v: pct(100 * v, 1)),
                 ("Netting share", "netting_share", lambda v: pct(100 * v, 3)),
                 ("Netting days", "netting_days", one_place))


def run_days(store):
    """The days of a run after launch, months times the days of a month (summary.json economy.months and
    constants.DAYS), or None where either is not stored."""
    months, days = dig(store.summary, ["economy", "months"]), dig(store.summary, ["constants", "DAYS"])
    return None if MISSING in (months, days) else int(months) * int(days)


def chain_sums(store, key, arm):
    """Each seed's sums over the months after launch of ``arm``'s settlement records in one cell, name -> array by
    seed; None where a seed does not store one of them."""
    found = {name: monthly_block(store, key, arm, name) for name in CHAIN_SERIES}
    if any(block is None for block in found.values()):
        return None
    return {name: np.nansum(block, axis=1) for name, block in found.items()}


def chain_readings(sums, days):
    """The chain readings of one cell from ``chain_sums``, each seed's value: the knock-on share of failed value
    (knock-on over own shortfall plus knock-on), payers with a knock-on failure a day (payer-days over ``days``),
    the share of days on which 32 or more payers had one (over the days the records count), the share of completed
    cash-route value that rests on netting, and the days with a non-empty netting set. Example: own
    shortfall 10 and knock-on 6 give a share of 6 / 16."""
    ratio = lambda top, bottom: np.divide(top, bottom, out=np.full(np.shape(top), np.nan), where=bottom > 0)
    counted = np.sum([sums[name] for name in KNOCK_DAYS], axis=0)
    return dict(knock_share=ratio(sums["knock_on"], sums["own_shortfall"] + sums["knock_on"]),
                payers_a_day=sums["knock_on_n"] / days, many_days=ratio(sums["knock_on_days_32_up"], counted),
                netting_share=ratio(sums["netting_value"], sums["cash_completed"]),
                netting_days=sums["netting_days"], counted=counted)


def chain_table(records, ledger):
    """Chains of failure from the records run, and their macros: for each arrangement, with no distress and at 2
    points, each chain reading's median over the launch cells (each cell its seed mean) and its range. Macros: the
    knock-on share under banks and under CPM (KnockOnBanks, KnockOnCpm, with Stress at 2 points), CPM less banks
    paired by seed (KnockOnGap, the median over cells of the seed mean, and KnockOnGapRange over every seed and
    cell), the largest netting share in any job and arrangement (NettingShareMost), and the share of days with 32 or
    more payers with a knock-on failure under banks, the pool without the charge and CPM (ManyKnockOn<arm>)."""
    days = run_days(records)
    levels = ((0.0, "", "None"), (HEADLINE, "Stress", f"{HEADLINE * 100:g} points"))
    readings = {}                                          # (level, arm) -> list over cells of each seed's readings
    for (level, _, _), arm in product(levels, ARMS):
        cells = records.pick(distress=level)
        found = [chain_sums(records, cell_key(c), arm) for c in cells]
        readings[(level, arm)] = (None if days is None or not cells or any(f is None for f in found)
                                  else [chain_readings(f, days) for f in found], cells)
    stored = chain.from_iterable(found for found, _ in readings.values() if found)
    counts = {int(v) for v in chain.from_iterable(r["counted"] for r in stored)}
    if counts and counts != {days}:
        ledger.notes.append(f"chains: the days the records count are {sorted(counts)}, not the run's {days}")
    why = lambda level, arm: absent_why(records, f"{file_of(records)}: measures.json monthly {arm}."
                                                 f"{', '.join(CHAIN_SERIES)} at distress {level * 100:g} pt, and "
                                                 "economy.months, constants.DAYS")
    source = lambda level, arm, key: (f"measures.json: jobs at {describe(readings[(level, arm)][1])}, monthly {arm}, "
                                      f"{key} from the sums over the months, seed mean of each cell")

    def per_cell(level, arm, key):
        """Each cell's seed mean of one reading, or None where not stored."""
        found = readings[(level, arm)][0]
        return None if found is None else np.array([np.nanmean(r[key]) for r in found])

    def entry(level, arm, label, key, fmt, how):
        """One table cell or macro: the median or range over cells."""
        where = f"chains[{NAMES[arm]}, distress {level * 100:g} pt, {label}, {how}]"
        values = per_cell(level, arm, key)
        if values is None:
            return ledger.lack(where, why(level, arm))
        return reduce(ledger, where, values, 0, how, fmt, source(level, arm, key))

    rows, rules = [], []
    columns = tuple(product(CHAIN_COLUMNS, ("median", "range")))
    for (level, _, name), (k, arm) in product(levels, enumerate(ARMS)):
        if k == 0 and rows:                                  # a rule before each level but the first
            rules.append(len(rows))
        rows.append([name if k == 0 else "", NAMES[arm]] + [entry(level, arm, label, key, fmt, how)
                                                            for (label, key, fmt), how in columns])
    out = {}
    share_fmt = CHAIN_COLUMNS[0][2]

    def knock_on(level, tail):
        """One distress level's macros, in order: knock-on shares under banks and CPM, CPM's gap to banks paired by
        seed (median and range), and the share of days with many knock-on failures under banks, the pool and CPM."""
        for arm, name in (("S0", "Banks"), (CPM, "Cpm")):
            values = per_cell(level, arm, "knock_share")
            macro = f"KnockOn{name}{tail}"
            out[macro] = (ledger.lack(macro, why(level, arm)) if values is None else
                          reduce(ledger, macro, values, 0, "median", share_fmt, source(level, arm, "knock_share")))
        cpm, banks = readings[(level, CPM)][0], readings[(level, "S0")][0]
        for macro, how in ((f"KnockOnGap{tail}", "median"), (f"KnockOnGap{tail}Range", "range")):
            if cpm is None or banks is None:
                out[macro] = ledger.lack(macro, why(level, CPM))
                continue
            gaps = [c["knock_share"] - b["knock_share"] for c, b in zip(cpm, banks)]   # paired by seed, cell by cell
            values = np.array([np.nanmean(g) for g in gaps]) if how == "median" else np.concatenate(gaps)
            out[macro] = reduce(ledger, macro, values, 0, how, share_fmt,
                                f"CPM less banks, the same seeds, knock_share: {source(level, CPM, 'knock_share')}"
                                + ("" if how == "median" else "; every seed and cell"))
        for arm, name in (("S0", "Banks"), ("U", "Pool"), (CPM, "Cpm")):
            values, macro = per_cell(level, arm, "many_days"), f"ManyKnockOn{name}{tail}"
            out[macro] = (ledger.lack(macro, why(level, arm)) if values is None else
                          reduce(ledger, macro, values, 0, "median", CHAIN_COLUMNS[2][2],
                                 source(level, arm, "many_days")))

    for level, tail, _ in levels:
        knock_on(level, tail)
    def netting(level, arm, found, cells):
        """Every job's netting share in one level's arrangement, each with the arrangement, its cell and the level."""
        jobs = chain.from_iterable(zip(r["netting_share"], repeat(c)) for r, c in zip(found, cells))
        return [(float(v), arm, cell_key(c), level) for v, c in jobs]

    every = list(chain.from_iterable(netting(level, arm, found, cells)
                                     for (level, arm), (found, cells) in readings.items() if found))
    if not every or any(found is None for found, _ in readings.values()):
        out["NettingShareMost"] = ledger.lack("NettingShareMost", why(0.0, "every arm"))
    else:
        most = max(every, key=lambda item: np.nan_to_num(item[0], nan=-1.0))
        if most[0] == 0:
            ledger.notes.append("chains: netting_value is zero in every job and arrangement, so no completed value "
                                "rests on netting; netting_days counts the days the set was not empty")
        out["NettingShareMost"] = ledger.add("NettingShareMost", CHAIN_COLUMNS[3][2](most[0]),
                                             f"largest over every job and arrangement of netting_value / "
                                             f"cash_completed summed over the months; at {NAMES[most[1]]}, "
                                             f"{most[2]}")
    head = ["Distress", "Arrangement"] + [f"{label} ({how})" for (label, _, _), how in product(CHAIN_COLUMNS,
                                                                                               ("median", "range"))]
    return dict(spec="ll" + "r" * (len(head) - 2), head=head, rows=rows, rule_before=rules), out


# ----------------------------------------------------------------------------------------------------------------------
# The stress boundary in steps of 0.1 point (docs/ROBUSTNESS_PLAN.md, section 8)
# ----------------------------------------------------------------------------------------------------------------------
BOUNDARY_LAUNCHES = ((0.2, "Twenty"), (0.3, "Thirty"), (0.45, "FortyFive"))   # launch level and its macro word
BOUNDARY_LEVELS = (0.015, 0.016, 0.017, 0.018, 0.019, 0.02)                    # the levels the table shows


def boundary_store(main, boundary, key):
    """The store holding cell ``key``: the stress boundary set for its finer levels, the map for the others."""
    return boundary if key in boundary.index else main


def runs_at(main, boundary, launch, level):
    """At one launch level and distress level (outside rate STRESS_RATE): each seed's bridges served in years 4 and
    5 under CPM and its source, read by ``bridges_served`` from whichever store holds the cell; (None, why) where
    neither does."""
    key = next((k for k in set(main.index) | set(boundary.index) if abs(k[0] - STRESS_RATE) < TOL
                and abs(k[1] - launch) < TOL and abs(k[2] - level) < TOL), None)
    if key is None:
        return None, absent_why(boundary, f"no cell at launch {launch:g} and distress {level * 100:g} pt")
    store = boundary_store(main, boundary, key)
    values, source = bridges_served(store, key)
    return values, f"{Path(store.folder).name}/{source}" if values is not None else source


def majority_runs(values):
    """Whether more than half of the seeds read a pool run (bridges served in years 4 and 5 below RUN_LINE)."""
    return bool(np.sum(values < RUN_LINE) > values.size / 2)


def boundary_table(main, boundary, ledger):
    """The stress boundary: for each launch level of BOUNDARY_LAUNCHES and each distress level of BOUNDARY_LEVELS,
    bridges served in years 4 and 5 (seed mean) and the seeds with a pool run, by the stress table's rule (a seed's
    bridges served below RUN_LINE); the finer levels from the stress boundary set, 1.5 and 2 points from the map.
    Macros Boundary<launch>: the lowest distress level, over every level either store holds at that launch, at
    which a majority of seeds read a run, or "none up to 2 points"."""
    rows, out = [], {}

    def entries(level, launch):
        """The table's two entries at one distress level and launch level: bridges served and the seeds with a run."""
        tag = lambda col: f"boundary[a0 {launch:g}, distress {level * 100:.1f} pt, {col}]"
        values, source = runs_at(main, boundary, launch, level)
        if values is None:
            return [ledger.lack(tag("bridges served"), source), ledger.lack(tag("seeds with a run"), source)]
        return [reduce(ledger, tag("bridges served"), values, 0, "mean", share, source),
                ledger.add(tag("seeds with a run"), f"{int(np.sum(values < RUN_LINE))} of {values.size}",
                           f"count of {source} < {RUN_LINE}")]

    for level in BOUNDARY_LEVELS:
        rows.append([f"{level * 100:.1f}", *chain.from_iterable(entries(level, launch)
                                                               for launch, _ in BOUNDARY_LAUNCHES)])
    for launch, word in BOUNDARY_LAUNCHES:
        macro = f"Boundary{word}"
        levels = sorted({k[2] for k in set(main.index) | set(boundary.index) if abs(k[0] - STRESS_RATE) < TOL
                         and abs(k[1] - launch) < TOL and TOL < k[2] < HEADLINE + TOL} | set(BOUNDARY_LEVELS))
        found = [(level, *runs_at(main, boundary, launch, level)) for level in levels]
        lacking = [why for _, values, why in found if values is None]
        if lacking:
            out[macro] = ledger.lack(macro, lacking[0])
            continue
        majority = [level for level, values, _ in found if majority_runs(values)]
        text = f"{majority[0] * 100:.1f} points" if majority else f"none up to {HEADLINE * 100:g} points"
        out[macro] = ledger.add(macro, text, f"lowest distress at a0 {launch:g} with more than half of the seeds' "
                                f"bridges served below {RUN_LINE}, over levels "
                                f"{', '.join(f'{v * 100:g}' for v in levels)} pt; "
                                f"majority at " + (", ".join(f"{v * 100:g}" for v in majority) or "none"))
        if majority:
            below = [level for level in levels if level < majority[0]]
            if below and majority[0] - below[-1] > 0.001 + TOL:
                ledger.notes.append(f"{macro}: the level below {majority[0] * 100:g} points that was run is "
                                    f"{below[-1] * 100:g}, more than 0.1 point lower")
    over = " & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{Launch {launch_text(a)}}}" for a, _ in BOUNDARY_LAUNCHES) \
        + r" \\"
    head = ["Distress (pt)"] + ["Bridges served", f"Seeds with a run"] * len(BOUNDARY_LAUNCHES)
    out.update(repeat_check(main, boundary, ledger))
    return dict(spec="r" + "rr" * len(BOUNDARY_LAUNCHES), over=over, head=head, rows=rows), out


def same_values(old, new, path, differ):
    """Compare ``new`` with ``old`` over everything ``old`` holds (a key ``old`` lacks is not read); append the path
    of each difference to ``differ``; return the number of values compared. Values must be equal exactly; NaN
    equals NaN, as a stored None (undefined) equals None."""
    if isinstance(old, dict):
        total = 0
        for key, value in old.items():
            if not isinstance(new, dict) or key not in new:
                differ.append(path + [key])
                total += 1
            else:
                total += same_values(value, new[key], path + [key], differ)
        return total
    if isinstance(old, (list, np.ndarray)):
        old_list, new_list = list(np.ravel(old)) if isinstance(old, np.ndarray) else old, \
            (list(np.ravel(new)) if isinstance(new, np.ndarray) else new)
        if not isinstance(new_list, list) or len(old_list) != len(new_list):
            differ.append(path)
            return max(len(old_list), 1)
        if any(isinstance(v, (dict, list)) for v in old_list):
            return sum(same_values(a, b, path + [k], differ) for k, (a, b) in enumerate(zip(old_list, new_list)))
        differ.extend(path + [k] for k, (a, b) in enumerate(zip(old_list, new_list)) if not equal_value(a, b))
        return len(old_list)
    if not equal_value(old, new):
        differ.append(path)
    return 1


def equal_value(a, b):
    """Two stored values are the same: equal, or both undefined (None or NaN)."""
    undefined = lambda v: v is None or (isinstance(v, float) and np.isnan(v))
    return (undefined(a) and undefined(b)) or (not undefined(a) and not undefined(b) and a == b)


def repeat_check(main, boundary, ledger, level=0.0):
    """The stress boundary set runs level 0 too, and those jobs repeat cells of the map: every value the map stores
    for them (cells.json jobs, the monthly series of measures.json and the summary cells) must come out the same.
    Written to the report's notes, with the counts as BoundaryRepeatValues and BoundaryRepeatDiffer."""
    keys = [k for k in boundary.index if abs(k[2] - level) < TOL and k in main.index]
    names = ("BoundaryRepeatValues", "BoundaryRepeatDiffer")
    if not keys:
        return {name: ledger.lack(name, absent_why(boundary, "no level-0 cell shared with the map")) for name in names}

    def compared(old_of, new_of):
        """One kind of record compared over the shared cells, the map's (``old_of``) against the set's (``new_of``):
        the values compared, the paths that differ and the records read."""
        differ, total, jobs = [], 0, 0
        for key in keys:
            old, new = old_of(key), new_of(key)
            jobs += len(old)
            total += same_values(old, new, [str(key)], differ)
        return total, differ, jobs

    found = {}
    for label, old_of, new_of in (
            ("cells.json jobs", lambda k: main.jobs.get(k, []), lambda k: boundary.jobs.get(k, [])),
            ("measures.json monthly", lambda k: [j["monthly"] for j in main.monthly.get(k, [])],
             lambda k: [j["monthly"] for j in boundary.monthly.get(k, [])]),
            ("summary.json cells", lambda k: [main.index[k]], lambda k: [boundary.index[k]])):
        found[label] = total, differ, jobs = compared(old_of, new_of)
        ledger.notes.append(f"repeat check, {Path(boundary.folder).name} against {Path(main.folder).name} at distress "
                            f"{level * 100:g}, {len(keys)} cells, {label} ({jobs} records): {total} values compared, "
                            f"{len(differ)} differ" + (f"; first: {', '.join(map(path_text, differ[:5]))}"
                                                       if differ else ""))
    jobs_part = [found[label] for label in ("cells.json jobs", "measures.json monthly")]
    source = f"cells.json jobs and measures.json monthly series of {len(keys)} level-0 cells, against the map"
    return dict(BoundaryRepeatValues=ledger.add("BoundaryRepeatValues", thousands(sum(t for t, _, _ in jobs_part)),
                                                source),
                BoundaryRepeatDiffer=ledger.add("BoundaryRepeatDiffer", str(sum(len(d) for _, d, _ in jobs_part)),
                                                source))


# ----------------------------------------------------------------------------------------------------------------------
# The period-two reading: does any stored series alternate month by month? (docs/ROBUSTNESS_PLAN.md, section 3)
# ----------------------------------------------------------------------------------------------------------------------
FOCUS_SERIES = "failure_share_rest"       # the failed share of people not in a job-loss spell
SHORTEST = 24                             # a series shorter than two years is not read


def trend_remainder(series):
    """A monthly series less its centred five-month mean; the two months at each end, which have no centred mean,
    are dropped."""
    x = np.asarray(series, float)
    return x[2:-2] - np.convolve(x, np.ones(5) / 5, mode="valid")


def alternation(size):
    """+1, -1, +1, ...: the period-two pattern, +1 at even places."""
    return np.where(np.arange(size) % 2 == 0, 1.0, -1.0)


def period_two_share(remainder):
    """The share of a remainder's variance at a period of two months: the squared mean of r_t (-1)^t over the mean
    square of r, both about r's mean. 1 for a pure alternation and about 1/T for white noise; NaN for a constant."""
    r = np.asarray(remainder, float) - np.mean(remainder)
    power = float(np.mean(r * r))
    return float(np.mean(r * alternation(r.size)) ** 2 / power) if power > 0 else np.nan


def alternating_amplitude(remainder):
    """The signed alternating amplitude of a remainder, the mean of r_t (-1)^t: positive when the even months of the
    stored series sit above their trend. A remainder starts at stored month index 2, which is even, so the sign of
    a place in the remainder is the sign of its month."""
    r = np.asarray(remainder, float)
    return float(np.mean(r * alternation(r.size)))


def reference_shares(draws=2000, months=60, seed=1):
    """What a period-two share is set against: white noise through the same filter (the mean and the 95th percentile
    over ``draws`` series of ``months``) and a flip-flop of size 1 with noise of 0.3 drawn after them. About 0.015,
    0.059 and 0.93."""
    rng = np.random.default_rng(seed)
    noise = [period_two_share(trend_remainder(x)) for x in rng.standard_normal((draws, months))]
    flip = alternation(months) + 0.3 * rng.standard_normal(months)
    return float(np.mean(noise)), float(np.percentile(noise, 95)), period_two_share(trend_remainder(flip))


def series_reading(values):
    """One stored monthly series read for a period of two: (share, signed amplitude, amplitude over the series' mean
    absolute level). The share is read on the defined months of a series with at least SHORTEST of them and some
    variation; the amplitude only on a series defined in every month. NaN where a part is not read."""
    x = np.asarray(values, float)
    seen = x[np.isfinite(x)]
    share_ = np.nan
    if seen.size >= SHORTEST and np.ptp(seen) > 0:
        remainder = trend_remainder(seen)
        share_ = period_two_share(remainder) if np.ptp(remainder) > 0 else np.nan
    if x.size < SHORTEST or not np.isfinite(x).all():
        return share_, np.nan, np.nan
    amplitude, level = alternating_amplitude(trend_remainder(x)), float(np.mean(np.abs(x)))
    return share_, amplitude, (abs(amplitude) / level if level > 0 else np.nan)


def period_two_rows(store):
    """Every stored monthly series of every job and arrangement, read by ``series_reading``: a list of (arm, series,
    seed, share, amplitude, amplitude over level)."""
    def of_job(job):
        """One job's readings, arrangement by arrangement and series by series."""
        series = chain.from_iterable(zip(repeat(arm), block.items()) for arm, block in job["monthly"].items())
        return [(arm, name, job["seed"], *series_reading(values)) for arm, (name, values) in series]

    return list(chain.from_iterable(map(of_job, chain.from_iterable(store.monthly.values()))))


def period_two_table(store, ledger):
    """The period-two reading of the map's monthly series, and its macros. Rows: the failed share of people not in a
    spell under each arrangement (the median and largest share over jobs, the median amplitude as a share of the
    series' level, and for each seed the share of jobs whose amplitude is positive); every other series (the largest
    of the series' median shares, and the largest share in any job); the white-noise and flip-flop references.
    Macros: PeriodTwoOthersMost, PeriodTwoOthersJobMost, PeriodTwo<Banks|Defi|Pool|Cpm>, PeriodTwoRestMost,
    PeriodTwoAmplitude (the range over arrangements and seeds of the median amplitude over level), PeriodTwoSign<First|
    Second|Third>Seed (the range over arrangements of the share positive), PeriodTwoWhiteNoise, PeriodTwoWhiteNoiseTop
    and PeriodTwoFlipFlop."""
    rows = period_two_rows(store)
    seeds = sorted({row[2] for row in rows})
    names = ["PeriodTwoOthersMost", "PeriodTwoOthersJobMost", "PeriodTwoBanks", "PeriodTwoDefi", "PeriodTwoPool",
             "PeriodTwoCpm", "PeriodTwoRestMost", "PeriodTwoAmplitude"] + [f"PeriodTwoSign{w}Seed" for w in ORDINALS]
    noise, top, flip = reference_shares()
    reference = dict(PeriodTwoWhiteNoise=ledger.add("PeriodTwoWhiteNoise", share(noise), "reference_shares(): mean "
                                                    "over 2,000 white-noise series of 60 months, seed 1"),
                     PeriodTwoWhiteNoiseTop=ledger.add("PeriodTwoWhiteNoiseTop", share(top),
                                                       "reference_shares(): 95th percentile of the same"),
                     PeriodTwoFlipFlop=ledger.add("PeriodTwoFlipFlop", share(flip, 2),
                                                  "reference_shares(): a flip-flop with noise 0.3"))
    head = ["Series", "Median share", "Largest share", "Amplitude over level"] + [f"Positive, seed {s}"
                                                                                  for s in seeds[:len(ORDINALS)]]
    source = f"measures.json: every job's monthly series ({describe(store.cells)})"
    if not rows:
        why = absent_why(store, "measures.json monthly series")
        found = {name: ledger.lack(name, why) for name in names}
        return dict(spec="lrrr", head=head[:4], rows=[[ledger.lack("periodtwo", why), "", "", ""]]), {**found,
                                                                                                    **reference}
    arms, names_, seed_of = (np.array([row[k] for row in rows]) for k in range(3))
    share_, amp, ratio = (np.array([row[k] for row in rows], float) for k in (3, 4, 5))
    focus = names_ == FOCUS_SERIES
    out = {}
    groups = {(a, n) for a, n in zip(arms[~focus], names_[~focus])}
    medians = {g: np.nanmedian(share_[(arms == g[0]) & (names_ == g[1])]) for g in groups
               if np.isfinite(share_[(arms == g[0]) & (names_ == g[1])]).any()}
    most = max(medians, key=medians.get)
    out["PeriodTwoOthersMost"] = ledger.add("PeriodTwoOthersMost", share(medians[most], 2),
                                            f"largest over {len(medians)} series (arrangement and name, all but "
                                            f"{FOCUS_SERIES}) of the median over jobs of period_two_share; set by "
                                            f"monthly.{most[0]}.{most[1]}; {source}")
    others = np.where(focus, np.nan, share_)
    job_most = int(np.nanargmax(others))
    out["PeriodTwoOthersJobMost"] = ledger.add("PeriodTwoOthersJobMost", share(others[job_most], 2),
                                               f"largest period_two_share of any job in those series; at monthly."
                                               f"{arms[job_most]}.{names_[job_most]}, seed {seed_of[job_most]}")
    for arm, name in (("S0", "Banks"), ("M0", "Defi"), ("U", "Pool"), (CPM, "Cpm")):
        pick = focus & (arms == arm)
        out[f"PeriodTwo{name}"] = reduce(ledger, f"PeriodTwo{name}", share_[pick], 0, "median", lambda v: share(v, 2),
                                         f"period_two_share of monthly.{arm}.{FOCUS_SERIES}, every job; {source}")
    out["PeriodTwoRestMost"] = reduce(ledger, "PeriodTwoRestMost", share_[focus], 0, "high", lambda v: share(v, 2),
                                      f"period_two_share of monthly.<every arm>.{FOCUS_SERIES}; {source}")
    by_arm_seed = np.array([np.nanmedian(ratio[focus & (arms == a) & (seed_of == s)]) for a, s in product(ARMS, seeds)
                            if (focus & (arms == a) & (seed_of == s)).any()])
    out["PeriodTwoAmplitude"] = reduce(ledger, "PeriodTwoAmplitude", by_arm_seed, 0, "range",
                                       lambda v: pct(100 * v, 1), f"|alternating_amplitude| over the mean absolute "
                                       f"level of monthly.<arm>.{FOCUS_SERIES}, median over jobs of each arrangement "
                                       f"and seed, low to high; {source}")
    positive = lambda a, s: np.mean(amp[focus & (arms == a) & (seed_of == s) & np.isfinite(amp)] > 0)
    for word, seed in zip(ORDINALS, seeds):
        values = np.array([positive(a, seed) for a in ARMS if (focus & (arms == a) & (seed_of == seed)).any()])
        out[f"PeriodTwoSign{word}Seed"] = reduce(ledger, f"PeriodTwoSign{word}Seed", values, 0, "range",
                                                 lambda v: pct(100 * v, 0), f"share of jobs with alternating_amplitude "
                                                 f"> 0 in monthly.<arm>.{FOCUS_SERIES}, seed {seed}, low to high over "
                                                 f"arrangements; {source}")
    for word in ORDINALS[len(seeds):]:
        out[f"PeriodTwoSign{word}Seed"] = ledger.lack(f"PeriodTwoSign{word}Seed", "fewer than three seeds stored")

    def arm_row(arm):
        """One arrangement's row for the focus series."""
        pick = focus & (arms == arm)
        where = lambda col: f"periodtwo[{NAMES[arm]}, {col}]"
        src = f"monthly.{arm}.{FOCUS_SERIES}; {source}"
        two = lambda v: share(v, 2)
        return [NAMES[arm], reduce(ledger, where("median share"), share_[pick], 0, "median", two, src),
                reduce(ledger, where("largest share"), share_[pick], 0, "high", lambda v: share(v, 2), src),
                reduce(ledger, where("amplitude over level"), ratio[pick], 0, "median", lambda v: pct(100 * v, 2), src)
                ] + [ledger.add(where(f"positive, seed {s}"), pct(100 * positive(arm, s), 0),
                                f"share of jobs with alternating_amplitude > 0, seed {s}; {src}")
                     for s in seeds[:len(ORDINALS)]]

    width = len(head)
    blank = [""] * (width - 3)
    table_rows = [arm_row(arm) for arm in ARMS if (focus & (arms == arm)).any()]
    table_rows += [["Every other series (largest median; largest job)", out["PeriodTwoOthersMost"],
                    out["PeriodTwoOthersJobMost"], *blank],
                   ["White noise through the same filter (mean; 95th percentile)", reference["PeriodTwoWhiteNoise"],
                    reference["PeriodTwoWhiteNoiseTop"], *blank],
                   ["A flip-flop with noise 0.3 of its size", reference["PeriodTwoFlipFlop"], "", *blank]]
    return dict(spec="l" + "r" * (width - 1), head=head, rows=table_rows,
                rule_before=[len(table_rows) - 3]), {**out, **reference}


# ----------------------------------------------------------------------------------------------------------------------
# The spread of distress to people not laid off (spread.json, written by scripts/spread_of_distress.py)
# ----------------------------------------------------------------------------------------------------------------------
SPREAD_ARMS = ("S0", "M0", "U", CPM)                  # the arrangements the spread table shows
SPREAD_LEVELS = ((0.005, "Half"), (0.01, "One"), (0.015, "OneHalf"), (0.02, "Two"))   # level and its macro word


def spread_cells(store, level):
    """The cells of spread.json at one distress level, in grid order (empty where the store is absent)."""
    cells = [c for c in ((store.spread or {}).get("cells") or []) if abs(float(c["distress"]) - level) < TOL]
    return sorted(cells, key=lambda c: (float(c["r_out"]), float(c["a0"])))


def spread_means(cells, arm, key):
    """Each cell's seed mean of spread.json's ``arms.<arm>.<key>`` (a list by seed), as an array, and how many cells
    do not store it."""
    found = [dig(c, ["arms", arm, key]) for c in cells]
    values = np.array([np.nan if not isinstance(v, list) or not v else np.mean(np.array(v, float)) for v in found])
    return values, sum(not isinstance(v, list) for v in found)


def spread_ratio(cells, arm, top, bottom):
    """Each cell's ratio of two seed means (the share of the excess on people not hit), NaN where the bottom is not
    positive, and how many cells do not store either."""
    a, lacking = spread_means(cells, arm, top)
    b, absent = spread_means(cells, arm, bottom)
    return np.divide(a, b, out=np.full(a.shape, np.nan), where=b > 0), lacking + absent


def spread_table(store, ledger):
    """The spread of distress: for each distress level and each arrangement of SPREAD_ARMS, over the level's cells
    (each its seed mean), the excess failed shares a person a year over months 25 to 60 (median and range), the
    share of it on people not hit in the wide and the narrow reading (medians of others / excess and others_narrow
    / excess), the excess in the distress year (median and range) and the share of it on people not hit (others_year
    / excess_year). Macros: for each level, the cells in which the excess is lower under CPM than under banks, over
    months 25 to 60 (SpreadLower<level>) and in the distress year (SpreadLowerYear<level>), and the median over cells
    of CPM's seed mean less banks' (SpreadGap<level>, SpreadGapYear<level>); SpreadCells, the cells at a level; and
    the lowest and highest wide and narrow share in the table (SpreadWideLow, SpreadWideHigh, SpreadNarrowLow,
    SpreadNarrowHigh)."""
    excess, part = (lambda v: share(v, 3)), (lambda v: share(v, 2))
    src = lambda cells, what: (f"{Path(store.folder).name}/spread.json: cells[{describe(cells)}].{what}, seed means"
                               if cells else absent_why(store, f"{Path(store.folder).name}/spread.json not shipped"))
    rows, rules, out, wide, narrow = [], [], {}, [], []

    def level_rows(level, word):
        """One distress level's rows, one for each arrangement of SPREAD_ARMS, and its macros, in that order."""
        cells = spread_cells(store, level)
        if rows:
            rules.append(len(rows))
        for k, arm in enumerate(SPREAD_ARMS):
            where = lambda col: f"spread[{level * 100:g} pt, {NAMES[arm]}, {col}]"
            stat = lambda col, values, absent, how, fmt, what: (
                reduce(ledger, where(col), values, absent, how, fmt, src(cells, what)) if cells else
                ledger.lack(where(col), src(cells, what)))
            e, e_absent = spread_means(cells, arm, "excess")
            y, y_absent = spread_means(cells, arm, "excess_year")
            w, w_absent = spread_ratio(cells, arm, "others", "excess")
            n, n_absent = spread_ratio(cells, arm, "others_narrow", "excess")
            q, q_absent = spread_ratio(cells, arm, "others_year", "excess_year")
            row = [f"{level * 100:g} pt" if k == 0 else "", NAMES[arm],
                   stat("excess, median", e, e_absent, "median", excess, f"arms.{arm}.excess"),
                   stat("excess, range", e, e_absent, "range", excess, f"arms.{arm}.excess"),
                   stat("share on people not hit, wide", w, w_absent, "median", part,
                        f"arms.{arm}.others over .excess"),
                   stat("share on people not hit, narrow", n, n_absent, "median", part,
                        f"arms.{arm}.others_narrow over .excess"),
                   stat("excess in the distress year, median", y, y_absent, "median", excess,
                        f"arms.{arm}.excess_year"),
                   stat("excess in the distress year, range", y, y_absent, "range", excess,
                        f"arms.{arm}.excess_year"),
                   stat("share on people not hit, distress year", q, q_absent, "median", part,
                        f"arms.{arm}.others_year over .excess_year")]
            rows.append(row)
            if cells and not (w_absent or n_absent):
                wide.append(np.nanmedian(w))
                narrow.append(np.nanmedian(n))
        for tail, key, label in (("", "excess", "months 25 to 60"), ("Year", "excess_year", "the distress year")):
            mine, a = spread_means(cells, CPM, key)
            banks, b = spread_means(cells, "S0", key)
            what = f"arms.{CPM}.{key} and arms.S0.{key}, the same seeds"
            if not cells or a or b:
                out[f"SpreadLower{tail}{word}"] = ledger.lack(f"SpreadLower{tail}{word}", src(cells, what))
                out[f"SpreadGap{tail}{word}"] = ledger.lack(f"SpreadGap{tail}{word}", src(cells, what))
                continue
            out[f"SpreadLower{tail}{word}"] = ledger.add(
                f"SpreadLower{tail}{word}", str(int(np.sum(mine < banks))),
                f"cells of {len(cells)} with CPM's seed mean below banks', {label}; " + src(cells, what))
            out[f"SpreadGap{tail}{word}"] = reduce(ledger, f"SpreadGap{tail}{word}", mine - banks, 0, "median",
                                                   excess, f"CPM less banks, {label}; " + src(cells, what))

    for level, word in SPREAD_LEVELS:
        level_rows(level, word)
    counts = {len(spread_cells(store, level)) for level, _ in SPREAD_LEVELS}
    out["SpreadCells"] = (ledger.add("SpreadCells", str(counts.pop()), src(spread_cells(store, HEADLINE), "cells"))
                          if len(counts) == 1 and 0 not in counts else
                          ledger.lack("SpreadCells", src([], "") if store.spread is None else
                                      f"spread.json levels hold {sorted(counts)} cells"))
    for (name, values), (how, tail) in product((("Wide", wide), ("Narrow", narrow)),
                                               (("low", "Low"), ("high", "High"))):
        out[f"Spread{name}{tail}"] = (
            reduce(ledger, f"Spread{name}{tail}", np.array(values), 0, how, part,
                   f"the spread table's {name.lower()} shares, every level and arrangement shown")
            if len(values) == len(SPREAD_LEVELS) * len(SPREAD_ARMS) else
            ledger.lack(f"Spread{name}{tail}", src([], "")))
    head = ["Distress", "Arrangement", "Excess (median)", "Excess (range)", "Not hit, wide", "Not hit, narrow",
            "Distress year (median)", "Distress year (range)", "Not hit, distress year"]
    return dict(spec="ll" + "r" * (len(head) - 2), head=head, rows=rows, rule_before=rules), out


# ----------------------------------------------------------------------------------------------------------------------
# The exploratory runs made after the confirmation map was read (docs/ANALYSIS_PLAN.md, its additions)
# ----------------------------------------------------------------------------------------------------------------------
CUT_MARK = r"$^{\dagger}$"                                  # marks a rate of the rate cut in the table of six rates
CUT_WORDS = {0.025: "TwoFive", 0.03: "Three", 0.035: "ThreeFive"}   # the cut's rates and their macro words
EXPLORE_LAUNCHES = (0.05, 0.2, 0.6)                          # the launch levels of the side checks' cells


def region_marks(store):
    """Each of a map's CPM cells read from its stored regions: {(distress, rate, launch): 3 in the map's region,
    2 passing outside it, 1 not passing}."""
    slices = dig(store.summary, ["claim_statistics", "regions", CPM])

    def marked(piece):
        """The marks of one distress slice's CPM cells."""
        inside = {(float(r), float(a)) for r, a in piece["region"]}
        passing = {(float(r), float(a)) for r, a in piece["passing"]}
        return {(level, rate, launch): 3 if (rate, launch) in inside else 2 if (rate, launch) in passing else 1
                for (rate, launch, level), cell in store.index.items()
                if abs(level - piece["distress"]) < TOL and CPM in cell}

    out = {}
    for piece in [] if slices is MISSING else slices:
        out.update(marked(piece))
    return out


def cut_table(store, cut, ledger):
    """The claim over the registered map's outside rates and the rate cut's together: for each distress level a row
    for each rate, the cut's marked, with the cell's mark at each launch level and the cells passing. Also the cut's
    macros: its seeds joined, set aside and tried, its counts over its grid, and the cells passing at each of its
    rates and each distress level (CutPass + the level's word + the rate's word)."""
    registered, extra = region_marks(store), region_marks(cut)
    marks, own = {**registered, **extra}, {key[1] for key in extra}
    levels, rates, launches = (sorted({key[k] for key in marks}) for k in range(3))
    words, out, rows, rules = dict(LEVEL_WORDS), {}, [], []
    for level, (j, rate) in product(levels, enumerate(rates)):
        if j == 0:                                           # a rule before each level
            rules.append(len(rows))
        codes = [marks.get((level, rate, launch), 0) for launch in launches]
        source = f"{file_of(cut if rate in own else store)}: claim_statistics.regions.{CPM}, distress {level:g}"
        passing = ledger.add(f"cut[distress {level * 100:g} pt, rate {rate * 100:g}%, cells passing]",
                             str(sum(code >= 2 for code in codes)), source)
        rows.append([f"{level * 100:g} pt" if j == 0 else "", pct(rate * 100, 1) + (CUT_MARK if rate in own else ""),
                     *MARKS[codes], passing])
        if rate in CUT_WORDS and level in words:
            name = f"CutPass{words[level]}{CUT_WORDS[rate]}"
            out[name] = ledger.add(name, passing, source)
    seeds, aside = dig(cut.summary, ["seeds"]), dig(cut.summary, ["provenance", "joined_from_parts", "set_aside"])
    joined, left = (0 if seeds is MISSING else len(seeds)), (0 if aside is MISSING else len(aside))
    count, positive, fewer = grid_counts(cut)
    src = file_of(cut)
    out.update(CutSeeds=ledger.add("CutSeeds", str(joined), f"{src}: len(seeds)"),
               CutSeedsAside=ledger.add("CutSeedsAside", str(left), f"{src}: provenance.joined_from_parts.set_aside"),
               CutSeedsTried=ledger.add("CutSeedsTried", str(joined + left), "the two above added"),
               CutCells=ledger.add("CutCells", str(count), f"{src}: cells holding {CPM}"),
               CutGainPositive=ledger.add("CutGainPositive", str(positive), f"{src}: cells with every gain above zero"),
               CutFewerFailures=ledger.add("CutFewerFailures", str(fewer), f"{src}: cells failing fewer than both"))
    head = ["Distress", "Outside rate"] + [f"{a * 100:g}\\%" for a in launches] + ["Cells passing"]
    return dict(spec="ll" + "c" * len(launches) + "r", head=head, rows=rows, rule_before=rules[1:]), out


def at_cell(ledger, where, store, launch, level, path, fmt, rate=STRESS_RATE):
    """One stored number of one cell of a side check, as text recorded in the ledger (a placeholder where the set
    does not hold the cell or the field)."""
    key = next((k for k in store.index if abs(k[0] - rate) < TOL and abs(k[1] - launch) < TOL
                and abs(k[2] - level) < TOL), None)
    source = f"{file_of(store)}: cell (r_out {rate:g}, a0 {launch:g}, distress {level:g}).{path_text(path)}"
    value = MISSING if key is None else dig(store.index[key], path)
    return ledger.lack(where, source) if value is MISSING or value is None else ledger.add(where, fmt(value), source)


def cost_a_year(store):
    """The pool's fixed cost of a side check in dollars a person a year (C_fix a month in months of mean spending)."""
    fixed, month = dig(store.summary, ["inputs", "C_fix"]), dig(store.summary, ["constants", "MONTH_USD"])
    return None if MISSING in (fixed, month) else float(fixed) * 12 * float(month)


def cents(value):
    """Dollars as the spiral table prints them: cents under ten dollars, whole dollars above."""
    return r"\$" + (f"{value:.2f}" if value < 10 else f"{value:,.0f}".replace(",", "{,}"))


def explore_tables(base, sets, low, ledger):
    """The exploratory side checks on the side seeds, each beside ``base`` (the same six cells at the build's
    settings): the side-check table of ``sets`` ((label, Store) pairs); the spiral table of the sets that change
    the fixed cost; the low-rates table of ``low``; and the macros the text quotes. Returns (tables, macros)."""
    tables, out = dict(explore=side_table(base, sets, ledger, label="base")), {}
    gain = lambda yard: [CPM, "against", yard, "gain_usd_a_year"]
    # The spiral: the fixed cost at its sourced level and at its multiples.
    spiral = [("sourced", base)] + [(label, store) for label, store in sets
                                    if str(dig(store.summary, ["fixed_cost"])).startswith("times")]
    rows = []
    for label, store in spiral:
        tag = lambda what, launch: f"spiral[{label}, {what}, launch {launch * 100:g}%]"
        cost = cost_a_year(store)
        rows.append([label_of(label), ledger.lack(f"spiral[{label}, cost]", "inputs.C_fix") if cost is None else
                     ledger.add(f"spiral[{label}, cost]", cents(cost), f"{file_of(store)}: inputs.C_fix x 12 x MONTH_USD")]
                    + [at_cell(ledger, tag("bridge price", a), store, a, 0.0, [CPM, "r_b_pct"], lambda v: pct(v, 1))
                       for a in EXPLORE_LAUNCHES]
                    + [at_cell(ledger, tag("participation", a), store, a, 0.0, [CPM, "A_W2"], lambda v: share(v, 2))
                       for a in EXPLORE_LAUNCHES]
                    + [at_cell(ledger, tag("gain over banks", a), store, a, 0.0, gain("S0"), usd)
                       for a in EXPLORE_LAUNCHES])
    launches = [f"{a * 100:g}\\%" for a in EXPLORE_LAUNCHES]
    over = (" & & " + " & ".join(f"\\multicolumn{{3}}{{c}}{{{title}}}" for title in
                                 ("Bridge price", "Participation, years 4 and 5", "Gain over banks and cards")) + r" \\")
    tables["spiral"] = dict(spec="lr" + "r" * 9, over=over, head=["Fixed cost", r"\$ a person a year"] + launches * 3,
                            rows=rows, rule_before=[1])
    # The low rates beside the base's rate.
    rows = []
    for rate, store in ((0.005, low), (0.01, low), (STRESS_RATE, base)):
        if store is None:
            continue
        tag = lambda what, launch: f"lowrates[{rate * 100:g}%, {what}, launch {launch * 100:g}%]"
        cell = lambda what, launch, level, path, fmt: at_cell(ledger, tag(what, launch), store, launch, level, path, fmt,
                                                              rate=rate)
        rows.append([pct(rate * 100, 1), cell("charge", 0.2, 0.0, [CPM, "c_pct"], lambda v: pct(v, 3))]
                    + [cell("gain over banks", a, 0.0, gain("S0"), usd) for a in EXPLORE_LAUNCHES]
                    + [cell("gain over DeFi", a, 0.0, gain("M0"), usd) for a in EXPLORE_LAUNCHES]
                    + [cell("failed under CPM at 2 points", a, HEADLINE, [CPM, "failures_pct"], lambda v: pct(v, 2))
                       for a in EXPLORE_LAUNCHES]
                    + [cell("failed under banks at 2 points", 0.2, HEADLINE, ["S0_failures_pct"], lambda v: pct(v, 2))])
    over = (" & & " + " & ".join(f"\\multicolumn{{3}}{{c}}{{{title}}}" for title in
                                 ("Gain over banks and cards", "Gain over best-case DeFi",
                                  f"Failed under CPM, {HEADLINE * 100:g} points")) + r" & \\")
    tables["lowrates"] = dict(spec="lr" + "r" * 10, over=over,
                              head=["Outside rate", "Demurrage"] + launches * 3 + [f"Banks, {HEADLINE * 100:g} points"],
                              rows=rows, rule_before=[len(rows) - 1])
    # The macros the text quotes: the fixed cost at each level, and the seeds the side checks ran on.
    for name, (label, store) in zip(("Sourced", "Ten", "Hundred", "Thousand"), spiral):
        cost = cost_a_year(store)
        out[f"SpiralCost{name}"] = (ledger.lack(f"SpiralCost{name}", "inputs.C_fix") if cost is None else
                                    ledger.add(f"SpiralCost{name}", cents(cost), f"{file_of(store)}: inputs.C_fix"))
    out["ExploreSeeds"] = seed_count(base, ledger, "ExploreSeeds")

    def lowest_highest(stem, store, level, path, fmt):
        """The macros stem + Low and stem + High: a stored number's lowest and highest over the launch levels."""
        keys = [k for k, a in product(store.index, EXPLORE_LAUNCHES)
                if abs(k[0] - STRESS_RATE) < TOL and abs(k[1] - a) < TOL and abs(k[2] - level) < TOL]
        found = [dig(store.index[k], path) for k in keys]
        source = (f"{file_of(store)}: cells at r_out {STRESS_RATE:g}, distress {level:g}: {path_text(path)}, over "
                  f"launch levels")
        numbers = bool(found) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in found)
        for tail, pick in (("Low", min), ("High", max)):
            out[stem + tail] = (ledger.add(stem + tail, fmt(pick(found)), source) if numbers else
                                ledger.lack(stem + tail, source))

    # The sets the text quotes are found by the setting they change, not by their label.
    setting = lambda store, name: dig(store.summary, ["economy", name])
    costly = max((s for _, s in sets if isinstance(setting(s, "issuer_cost"), float)),
                 key=lambda s: setting(s, "issuer_cost"), default=None)
    early = next((s for _, s in sets if setting(s, "distress_start") == 12), None)
    late = next((s for _, s in sets if setting(s, "distress_start") == 36), None)
    two = lambda v: pct(v, 2)
    lowest_highest("ExploreBaseDefi", base, 0.0, gain("M0"), usd)
    for stem, store, level, path, fmt in (("ExploreCustodyDefi", costly, 0.0, gain("M0"), usd),
                                          ("ExploreShockEarlyFail", early, HEADLINE, [CPM, "failures_pct"], two),
                                          ("ExploreShockEarlyBanks", early, HEADLINE, ["S0_failures_pct"], two),
                                          ("ExploreShockLateFail", late, HEADLINE, [CPM, "failures_pct"], two),
                                          ("ExploreShockLateBanks", late, HEADLINE, ["S0_failures_pct"], two)):
        if store is not None:
            lowest_highest(stem, store, level, path, fmt)
    return tables, out


# ----------------------------------------------------------------------------------------------------------------------
# (3) Writing
# ----------------------------------------------------------------------------------------------------------------------
def header(store, base=None):
    """The comment lines numbers.tex opens with: where the numbers came from."""
    prov = store.summary.get("provenance", {})
    beside = [] if base is None or base is store else [
        f"% Side checks, bounds, robustness sets and the seed plan are read beside: {Path(base.folder).name} "
        f"(seed set {base.summary.get('seed_set')}, {len(base.summary.get('seeds') or [])} seeds)"]
    sources = [f"%   {name}: {digest}" for name, digest in sorted((prov.get("sources") or {}).items())]
    seeds = store.summary.get("seeds") or []
    return "\n".join([
        "% Numbers quoted in the paper, one macro each. WRITTEN BY scripts/paper_numbers.py: do not edit by hand.",
        # The folder is named, not located: a path on one machine means nothing to a reader.
        f"% Results folder: {Path(store.folder).name}",
        "% Source files as the run hashed them (sha256):", *sources,
        f"% Seed set: {store.summary.get('seed_set')}, {len(seeds)} seeds: {', '.join(map(str, seeds))}",
        f"% Population: {dig(store.summary, ['economy', 'n'])} people", *beside,
        f"% A macro reading {PLACEHOLDER} is a number this result does not store; numbers_report.txt says which."])


def tabular(table):
    """A booktabs tabular body from a table's spec, head and rows (rules where ``rule_before`` says). A table may
    carry ``over``, one ready line of grouped headings printed above the head."""
    line = lambda cells: " & ".join(map(str, cells)) + r" \\"
    rules = set(table.get("rule_before", []))
    body = [(r"\midrule" + "\n" if k in rules else "") + line(row) for k, row in enumerate(table["rows"])]
    over = [table["over"]] if table.get("over") else []
    return "\n".join([f"\\begin{{tabular}}{{{table['spec']}}}", r"\toprule", *over, line(table["head"]), r"\midrule",
                      *body, r"\bottomrule", r"\end{tabular}", ""])


def build(store, sides=(), ledger=None, bounds=(), robust=(), records=None, boundary=None, rule_check=None,
          base=None, second=None, cut=None, explore=None):
    """Every macro and table from ``store`` (and ``sides`` and ``bounds``, each name and Store pairs; ``robust``,
    (group, stem, label, Store) for each robustness variant, the base first; ``records``, the records run;
    ``boundary``, the stress boundary set; ``rule_check``, the threshold rule with uniform thresholds): returns
    (macros, tables, ledger). A set not yet run is a pending Store, whose numbers are placeholders.

    ``base`` is the development map, given when ``store`` is a confirmation map. The side checks, the bounds, the
    stress boundary and the rule check were run on the development seeds, so their tables stand beside the base
    and not beside ``store``; the seed plan, the update-scheme reading and the spread of distress, which need the
    development seeds or their per-person records, are read on it too. None: ``store`` is its own base.

    ``second`` is the same map run under the second entry reading (savers act on the pool's realised record),
    read from its summary and, for the pool's path year by year, CPM's monthly capital, target and bridges served
    (``path_store``); with it the table of the two readings, the path table and their macros are written. ``cut`` is the
    rate cut, and ``explore`` the side checks on the side seeds as (base, [(label, Store), ...], low rates); each
    is exploratory and adds its own tables and macros. The side checks are read from their summaries alone; the cut
    from its summary and, for the pool's instalment coupon, its per-seed store (``seed_store``)."""
    ledger = ledger or Ledger()
    base = store if base is None else base
    found = macros(store, ledger, base)
    extra = {}
    if robust:
        extra["robustness"], more = robust_table(robust, ledger)
        found.update(more)
        found.update(robust_stress_macros(robust, ledger))
    if rule_check is not None:
        found.update(rule_check_macros(base, rule_check, ledger))
    if records is not None:
        extra["chains"], more = chain_table(records, ledger)
        found.update(more)
    if boundary is not None:
        extra["boundary"], more = boundary_table(base, boundary, ledger)
        found.update(more)
    if second is not None:
        extra["readings"], more = readings_table(store, second, ledger)
        found.update(more)
        extra["path"], more = path_table(store, second, ledger)
        found.update(more)
    if cut is not None:
        extra["cut"], more = cut_table(store, cut, ledger)
        found.update(more)
    if explore is not None:
        more_tables, more = explore_tables(*explore, ledger)
        extra.update(more_tables)
        found.update(more)
    found.update(after_shock_macros(store, ledger))
    found.update(shortfall_macros(store, ledger))
    found.update(percent_macros(store, ledger))
    if second is not None:
        found.update(after_shock_macros(second, ledger, "Second"))
    extra["sources"], more = sources_table(store, ledger)
    found.update(more)
    extra["chargegain"], more = charge_gain_table(store, second, ledger)
    found.update(more)
    extra["lending"], more = lending_table(store, cut, ledger)
    found.update(more)
    extra["periodtwo"], more = period_two_table(base, ledger)
    found.update(more)
    extra["spread"], more = spread_table(base, ledger)
    found.update(more)
    tables = dict(arrangements=arrangements_table(store, ledger), gains=gains_table(store, ledger),
                  charge=charge_table(store, ledger), buys=buys_table(store, ledger),
                  region=region_table(store, ledger),
                  region_majority=majority_table(store, ledger),
                  stress=stress_table(store, ledger), owners=owners_table(store, ledger),
                  docking=docking_table(store, ledger), circulation=circulation_table(store, ledger))
    if sides:
        tables["side"] = side_table(base, sides, ledger)
    if bounds:
        tables["bounds"] = bounds_table(base, bounds, ledger)
    tables.update(extra)
    pending = [Path(s.folder).name for s in [side for _, side in sides] + [r[3] for r in robust]
               + [records, boundary, rule_check] if s is not None and s.is_pending]
    if pending:
        ledger.notes.append("sets not yet run, their numbers placeholders: " + ", ".join(pending))
    for one in dict.fromkeys((store, base)):
        which = "" if base is store else f"{Path(one.folder).name}: "
        if not one.has_jobs:
            ledger.notes.append(which + "cells.json not read: every per-seed number is a placeholder")
        if not one.has_monthly:
            ledger.notes.append(which + "measures.json not read: every monthly-series number is a placeholder")
    return found, tables, ledger


def write(out, store, found, tables, ledger, base=None):
    """Write numbers.tex, tables/*.tex and numbers_report.txt into ``out``."""
    out = Path(out)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    names = [name for name in found if not name.isalpha()]
    if names:
        raise ValueError(f"macro names must be letters only: {names}")
    text = header(store, base) + "\n" + "\n".join(f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in found.items())
    folder = Path(store.folder).name
    # Every file is written with LF line ends on every system (newline="\n"), so the same result gives the same bytes.
    (out / "numbers.tex").write_text(text + "\n", encoding="utf-8", newline="\n")
    for name, table in tables.items():
        (out / "tables" / f"{name}.tex").write_text(f"% Written by scripts/paper_numbers.py from {folder}.\n"
                                                   + tabular(table), encoding="utf-8", newline="\n")
    report = [f"Paper numbers from {folder}", "", "MACROS AND TABLE CELLS", *ledger.lines, "", "NOTES",
              *(ledger.notes or ["none"]), "", "NOT STORED (written as placeholders)", *(ledger.missing or ["none"])]
    (out / "numbers_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")


def summary_store(folder):
    """A map read from its summary alone, which is all the two-readings table needs; None where no folder is given."""
    if folder is None:
        return None
    text = stored_text(folder, "summary.json")
    if text is None:
        raise FileNotFoundError(f"{folder} holds no summary.json: not a population map")
    return Store(json.loads(text), folder=folder)


def each_job(text):
    """The jobs of a compact store (measures.json), decoded and handed over one at a time, so a reader that keeps
    little of each never holds the whole store."""
    opening = '"jobs":['
    start = text.find(opening)
    if start < 0:
        raise ValueError("measures.json holds no jobs list: not a store the population runner wrote")
    decoder, place = json.JSONDecoder(), start + len(opening)
    while text[place] != "]":
        found, place = decoder.raw_decode(text, place)
        yield found
        place += text[place] == ","                              # step over the comma between two jobs


def path_store(folder):
    """A map read from its summary, its per-seed store and, of its monthly store (measures.json, where the folder
    holds it), CPM's PATH_SERIES alone: what the tables of the two entry readings need of the second. None where no
    folder is given."""
    found = seed_store(folder)
    text = None if found is None else stored_text(folder, "measures.json")
    if text is None:
        return found
    kept = []
    for job in each_job(text):
        series = (job.get("monthly") or {}).get(CPM)
        if series is not None:
            kept.append(dict(r_out=job["r_out"], a0=job["a0"], distress=job["distress"], seed=job["seed"],
                             recirculated=job.get("recirculated", False),
                             monthly={CPM: as_arrays({name: series[name] for name in PATH_SERIES if name in series})}))
    jobs = list(chain.from_iterable(found.jobs.values())) if found.has_jobs else None
    return Store(found.summary, jobs, kept, folder)


def seed_store(folder):
    """A map read from its summary and its per-seed store (cells.json, where the folder holds it), without the
    monthly series; None where no folder is given."""
    found = summary_store(folder)
    text = None if found is None else stored_text(folder, "cells.json")
    return found if text is None else Store(found.summary, json.loads(text)["jobs"], folder=folder)


def side_pair(text):
    """A --side argument name=folder as (name, folder)."""
    name, sep, folder = text.partition("=")
    if not sep or not name or not folder:
        raise argparse.ArgumentTypeError(f"--side takes name=<folder>, got {text!r}")
    return name, folder


def main(argv=None):
    """The command line: read the map (and any side results), write the numbers, tables and report."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", required=True, type=Path, help="the results folder of the map")
    parser.add_argument("--side", type=side_pair, action="append", default=[],
                        help="a side check on a few cells, name=<folder>; may be given more than once")
    parser.add_argument("--bound", type=side_pair, action="append", default=[],
                        help="a bound map over the whole grid, name=<folder>; may be given more than once")
    parser.add_argument("--robust", nargs=4, action="append", default=[], metavar=("GROUP", "STEM", "LABEL", "FOLDER"),
                        help="a robustness variant: its group (the sellers), its macro stem (letters only), the label "
                             "the table prints and its folder; the base first; may be given more than once")
    parser.add_argument("--records", type=Path, help="the records run (the chains table)")
    parser.add_argument("--boundary", type=Path, help="the stress boundary set")
    parser.add_argument("--rule-check", type=Path, help="the threshold rule with uniform thresholds")
    parser.add_argument("--base", type=Path, help="the development map the side checks, bounds and robustness sets "
                        "were run beside, where --map is a confirmation map (default: the map itself)")
    parser.add_argument("--second", type=Path, help="the same map under the second entry reading (savers act on the "
                        "pool's realised record); its summary is read and, for the pool's path, three monthly "
                        "series of CPM")
    parser.add_argument("--cut", type=Path, help="the rate cut, an exploratory map at finer outside rates")
    parser.add_argument("--explore-base", type=Path, help="the base of the exploratory side checks")
    parser.add_argument("--explore", type=side_pair, action="append", default=[],
                        help="an exploratory side check, name=<folder>; may be given more than once")
    parser.add_argument("--low-rates", type=Path, help="the exploratory side check at low outside rates")
    parser.add_argument("--out", type=Path, default=Path("paper"), help="where numbers.tex and tables/ go")
    args = parser.parse_args(argv)
    store = Store.from_folder(args.map)
    # A folder named twice (the map is the robustness table's base) is read once; a folder not yet written is a set
    # still to run, read as pending.
    read = {Path(args.map).resolve(): store}

    def get(folder):
        """The store of ``folder``, read once; None where no folder is given."""
        if folder is None:
            return None
        place = Path(folder).resolve()
        if place not in read:
            read[place] = Store.from_folder_or_pending(folder)
        return read[place]

    sides = [(name, get(folder)) for name, folder in args.side]
    bounds = [(name, Store.from_folder(folder)) for name, folder in args.bound]
    robust = [(group, stem, label, get(folder)) for group, stem, label, folder in args.robust]
    base = get(args.base)                             # read once, also where it is the robustness table's base
    if base is not None and base.is_pending:
        raise FileNotFoundError(f"{args.base} holds no summary.json: not a population map")
    found, tables, ledger = build(store, sides, bounds=bounds, robust=robust, records=get(args.records),
                                  boundary=get(args.boundary), rule_check=get(args.rule_check), base=base,
                                  second=path_store(args.second), cut=seed_store(args.cut),
                                  explore=None if args.explore_base is None else (
                                      summary_store(args.explore_base),
                                      [(name, summary_store(folder)) for name, folder in args.explore],
                                      summary_store(args.low_rates)))
    write(args.out, store, found, tables, ledger, base)
    print(f"Wrote {len(found)} macros and {len(tables)} tables to {args.out}; {len(ledger.missing)} placeholders "
          f"(see {args.out / 'numbers_report.txt'})")


if __name__ == "__main__":
    main()
