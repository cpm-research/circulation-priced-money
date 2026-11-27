"""The second registered run: its settings, its grid, its saver readings and its side sets, in one place.

The base model of the run is the first run's model with the settings below; every other Economy field keeps its
default. ``docs/DECISIONS.md`` gives the reasons for each setting at length (section "The second run: conserved money,
the stress year and the horizon").

* Population: 4,000 people (``notes.POPULATION``, which the runner already uses).
* Lengths: a burn-in of 60 months, 300 months after launch, and the stress year 121 to 132 months after launch
  (``distress_start`` 120). The longest loans run 60 months, so the instalment book needs 60 months to fill, and the
  slowest launch level needs 254 months to settle; the stress year falls ten years after launch.
* The edge, ``edge`` "conserved" and ``owners_share`` 0.10: each month what households lost across the edge and to
  inflation goes back to households, a tenth by fixed ownership shares and the rest by receipts. 0.10 is the sourced
  share, with 1.0 as the outer reading (a side set below).
* Three changes to the pool's reading of cash and receipts and to card statements: standby ``reserved``, so that long
  loans take only the cash above the standby that demurrage pays for; ``receipts_window`` 2, so that the pool reads
  the mean of the last two months of receipts; ``statement_dates`` "own", each card holder's statement on its own
  date.
* ``purchases`` "poisson_size": a Poisson number of purchases a month with mean 32, each of the same size. A slowdown
  needs purchases of fixed size, so that its fall is a fall in their number.
* The stress year. ``distress_wages`` "outside": the payer of a marked job still owes the wage, to outside the
  household economy (``docs/DECISIONS.md``, "The harsh stress": a payer who kept the wage would gain, and 2008 to 2009
  shows no such gainer). Under the conserved edge that wage is not lost: it is part of the month's flow across the
  edge and comes back to all households through the monthly payout (``_World._return_edge``), a tenth by ownership
  shares and the rest by receipts. So the stress year moves money from the laid-off workers to everyone and destroys
  none. The payer keeping the wage is a side set below. ``distress_purchases`` 0.0174: at the 2-point level 1.74% of
  purchases are dropped, the measured fall of real personal consumption expenditures in 2008 to 2009 (PCECC96), in
  proportion below it.
* Card lines cut in the stress year, ``card_line_cut`` True with ``card_cut_months`` 120: at the start of the stress
  year each open line falls by its tier's sourced share of the 2008 to 2012 cut (total lines fell 32.4%, CFPB, CARD
  Act Report, 2013) times the distress level over 2 points, for the measured ten years. At distress level 0 nothing is
  cut. The first run holds the lines; that is a side set below.
* Real DeFi, ``usdc_yield`` "none": M0 is stablecoin payments with no yield and no credit. The stablecoin pays its
  holder nothing ("DeFi" means payments and yield as they are; the reserve yield is a side set below), and nobody
  holds the collateral its lending needs (``CRYPTO_SHARE`` 0), so nobody can borrow: the people able to borrow and
  the borrowing drawn are stored beside M0's results, both zero.
* Savings and durables, ``durable_savings`` "kept": the savings a person keeps in its own cash, as a participant's
  wallet holds them, are not spent on a durable before it borrows, exactly as a bank customer's savings account is
  not. Otherwise the same person would pay for a durable out of its wallet, borrow less, keep no cushion and fail
  payments it never fails under banks. The first run's rule is a side set below.
* Six readings of the engine, each a setting of the Economy whose default is the first run's rule:
  ``experience_rewards`` True, the leaving rule charges each participant the card rewards it gave up on card-eligible
  purchases paid from the wallet; ``card_cut_on`` "room", the stress year's line cut takes its share of each holder's
  room above its starting balance, not of the whole line, so nobody is left with no room only because of a balance
  the model never lets it repay; ``screen_card_owed`` True, the lending screen counts a holder's closed card
  statement and unbilled card purchases among what is owed; ``buffer_reserve`` "share_of_spare", the buffer replay's
  money held back from a saver offering money to the pool is the deposit share of what is above the candidate buffer,
  as the dealing leaves it; ``stress_paydays`` "merged", a worker's wage and the wage owed outside for the same job
  and pay date count as one obligation for failed shares, fee units and the failure fee; and ``payout`` "paid", the
  monthly payout returns what was paid across the edge, not what was booked when a debt to the outside was created.
  The first run's rule for each is a side set below.
* A day whose settlement cycles, ``settle_cycle`` "hold": where the day's sweeps repeat without reaching a fixed
  point, a request for same-day credit stands for the rest of the day, so the day settles and the run goes on. It
  changes no day that settles without it, and each use is counted in the stored series ``settle_held``. The first
  run's rule stops the run on such a day, so it has no side set.
* The grid: outside rates 2, 2.5, 3, 3.5, 4.4 and 6% a year; launch levels 0.05, 0.1, 0.2, 0.3, 0.45, 0.6 and 0.8;
  distress levels 0, 0.5, 1, 1.5 and 2 points (0 to 0.02 extra layoffs per job a month), 210 cells. The launch and
  distress levels are the first run's.
* Both saver readings on every cell, ``entry_reads`` "quote" and "realised". Under the quote reading the saver meets
  the entry hurdle by construction: at a positive capital target the quote is owners' alternative and a tie enters,
  so capital under it shows the pool's room and its exits, not a saver's choice; the realised record is the reading
  that tests whether savers stay.
* The five arrangements of the first run, S0, M0, U, M1 and M2 (``notes.ARMS`` beside S0).
* Seeds: the existing sets (``grid.SEEDS``) for development and the side sets; the confirmation seeds are the second
  run's own block, never run, from 20261701 upward, whose count is the planner's count at the spreads' bounds rounded
  up to the next ten, at most 100, fixed from the three-seed map (``grid.second_confirmation_count``).

Every setting named here is a field of the Economy; ``economy`` refuses one that is not, so a misspelt setting cannot
run the model with its defaults without saying so.

The side sets, 43 in all, each state the settings they change from the base and the cells they run on (at 4.4% a year
unless stated; where no cells are named, launch levels 0.2 and 0.6 with no distress and with 2 points):

* ``savers_trust_<phi>``: a share phi of savers read the pool's record, the rest the quote, phi 0 to 1 in steps of
  0.1; launch 0.3 and 0.8, no distress. The share needs the quote reading, so these sets run on it alone.
* ``owners_follow_reviewers`` and ``owners_follow_all``: owners who file after an exit goes unpaid, at the next
  dealing every owner whose review comes up, or every owner (``Economy.owners_follow``); launch 0.45 and 0.8 at every
  distress level (six cells are wanted, the five levels at 0.45 and 2 points at 0.8, and these are the smallest cross
  the runner selects that holds them).
* ``wages_first``: overdue wages paid first and from all the payer's money, before a due bridge is collected and
  without the buffer the base keeps (``collect_first`` "wages"); launch 0.05, 0.3 and 0.8, no distress and 2 points.
  ``wages_first_same_budget``, on its cells: overdue wages paid first from the money above the buffer only, the
  base's budget, so that only the order changes (``collect_first`` "wages_same_budget").
* ``random_distress_<k>``: distress years at random dates, k = 1, 2 and 4 expected in a run; launch 0.05, 0.3 and
  0.8, at 2 points with its own no-distress twin. Card lines are held in these sets: the cut is defined at the one
  dated stress year, and the Economy refuses it with random ones.
* ``uncharged_peak``: the pool without demurrage given the capital target of the pool with it, on the cells of
  ``wages_first``. ``uncharged_matched``, on the same cells: the target and also the cash held back from term loans
  of the pool with demurrage (``uncharged_standby`` "reserved"), so that the two pools differ only by the charge.
* ``owners_everything``: everything households pay the financial side to its owners, ``owners_share`` 1.0, the outer
  reading.
* ``owners_nothing``: nothing of the returned flow by ownership shares, all of it by receipts, ``owners_share`` 0.0,
  on the cells of ``owners_everything``, so that the table of who pays and who receives can be shown at the shares 0,
  0.10 and 1.
* ``banks_supported``: card lines held through the stress year, ``card_line_cut`` False, the model's reading of banks
  with outside support.
* ``slowdown_<x>``: harsher slowdowns, 6.2% (goods), 8.9% (income other than wages and transfers, which fell 8.9% from
  October 2008 to July 2009: FRED PI, PCTR and A576RC1), 9.9% (retail and food services), 11.9% (durable goods) and
  13.3% (velocity of M2) of purchases dropped at 2 points, the measured falls.
* ``defi_reserve_yield``: the stablecoin's holder paid the reserve yield, banks' and DeFi's kinder reading.
* ``wages_kept``: the payer of a marked job keeps the wage, ``distress_wages`` "kept", so the money stays with the
  payers in place of returning to everyone through the payout.
* ``leave_noise_half`` and ``leave_noise_twice``: the leaving rule's noise at half and at twice its scale
  (``leave_noise`` 0.5 and 2), shown beside every result.
* ``one_wage_each``: every person pays one wage and receives exactly one, ``wage_links`` "one_each", where otherwise
  about 37% of people receive none (``population.wage_links_one_each``).
* ``durables_from_savings``: a durable is paid from all own money above the buffer, wallet savings included,
  ``durable_savings`` "used", the first run's rule, so that both readings exist.
* The opposite of each choice of the base that leans towards the pool arrangement, so that both readings exist:
  ``loan_losses_sourced``, every lender discharges the sourced charge-off rate of the bank loans its loans replace,
  ``loan_losses`` "sourced"; and ``shocks_on``, the unexpected expenses of the Fed survey, ``shocks`` True. The other
  two such choices already have their sets, ``banks_supported`` and ``defi_reserve_yield``.
* The rules the base changes from the first run's, each restored so that both readings exist: ``rewards_uncounted``
  (``experience_rewards`` False), ``cut_whole_line`` (``card_cut_on`` "line"), ``payout_accrued`` (``payout``
  "accrued"); and, for the three of those rules that lean towards the pool arrangement and have no set above,
  ``standby_measured`` (``standby`` "measured", term loans may take the standby cash), ``receipts_one_month``
  (``receipts_window`` 1) and ``buffer_share_of_liquid`` (``buffer_reserve`` "share_of_liquid"); each on the cells of
  ``owners_everything``.
* ``no_failure_fee``: no failure fee, read with the Economy's existing settings: a monthly cap of zero fees
  (``fees_a_month`` 0) and failures past the cap priced at $0 in the buffer choice (``buffer_prices_past_cap`` False),
  as the experience replays price them; on the cells of ``owners_everything``.

The shares of savers' trust near each cell's predicted tipping share, to be added once a map is read, are not set
here.
"""
from dataclasses import fields
from itertools import chain, repeat

from cpm_abm.engine.settings import Economy

# The run's lengths, months: burn-in, months after launch, and the month after launch at
# which the stress year starts, so that it covers months 121 to 132.
LENGTHS = dict(burn_in=60, months=300, distress_start=120)

# The base settings of the run, away from the Economy's defaults (the module docstring describes each).
BASE = dict(edge="conserved", owners_share=0.10, standby="reserved", receipts_window=2, purchases="poisson_size",
            statement_dates="own", distress_wages="outside", distress_purchases=0.0174, card_line_cut=True,
            card_cut_months=120, usdc_yield="none", durable_savings="kept", experience_rewards=True,
            card_cut_on="room", screen_card_owed=True, buffer_reserve="share_of_spare", stress_paydays="merged",
            payout="paid", settle_cycle="hold")
# Card lines held: no cut, and no months of it (0, the Economy's default).
_HELD = dict(card_line_cut=False, card_cut_months=0)

# The grid: outside rates a year, launch levels and distress levels (extra layoffs per job a month), 6 x 7 x 5 cells.
RATES = (0.02, 0.025, 0.03, 0.035, 0.044, 0.06)
A0S = (0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8)
DISTRESS = (0.0, 0.005, 0.01, 0.015, 0.02)
GRID = dict(r_out=RATES, a0=A0S, distress=DISTRESS)

# The saver readings every cell runs on (``Economy.entry_reads``).
READS = ("quote", "realised")

# The cells a side study runs on where none are named: 4.4%, launch 0.2 and 0.6, no distress and 2 points; and the
# cells of the three studies run at launch 0.05, 0.3 and 0.8.
_SIDE_CELLS = dict(r_out=(0.044,), a0=(0.2, 0.6), distress=(0.0, 0.02))
_THREE_LAUNCHES = dict(r_out=(0.044,), a0=(0.05, 0.3, 0.8), distress=(0.0, 0.02))

# The side studies: for each, the cells, the saver readings and its sets, each set the settings it changes from BASE.
STUDIES = dict(
    savers_trust=dict(cells=dict(r_out=(0.044,), a0=(0.3, 0.8), distress=(0.0,)), reads=("quote",),
                      sets={f"savers_trust_{k / 10:.1f}": dict(sceptical_share=k / 10) for k in range(11)}),
    owners_follow=dict(cells=dict(r_out=(0.044,), a0=(0.45, 0.8), distress=DISTRESS), reads=READS,
                       sets=dict(owners_follow_reviewers=dict(owners_follow="reviewers"),
                                 owners_follow_all=dict(owners_follow="all"))),
    wages_first=dict(cells=_THREE_LAUNCHES, reads=READS,
                     sets=dict(wages_first=dict(collect_first="wages"),
                               wages_first_same_budget=dict(collect_first="wages_same_budget"))),
    random_distress=dict(cells=_THREE_LAUNCHES, reads=READS,
                         sets={f"random_distress_{k}": dict(distress_dates="random", distress_expected=float(k),
                                                            **_HELD) for k in (1, 2, 4)}),
    uncharged_peak=dict(cells=_THREE_LAUNCHES, reads=READS,
                        sets=dict(uncharged_peak=dict(uncharged_target="peak"),
                                  uncharged_matched=dict(uncharged_target="peak", uncharged_standby="reserved"))),
    owners_everything=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(owners_everything=dict(owners_share=1.0))),
    owners_nothing=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(owners_nothing=dict(owners_share=0.0))),
    banks_supported=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(banks_supported=dict(_HELD))),
    slowdown=dict(cells=_SIDE_CELLS, reads=READS,
                  sets={f"slowdown_{x}": dict(distress_purchases=x) for x in (0.062, 0.089, 0.099, 0.119, 0.133)}),
    defi_reserve_yield=dict(cells=_SIDE_CELLS, reads=READS,
                            sets=dict(defi_reserve_yield=dict(usdc_yield="reserve"))),
    wages_kept=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(wages_kept=dict(distress_wages="kept"))),
    one_wage_each=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(one_wage_each=dict(wage_links="one_each"))),
    loan_losses_sourced=dict(cells=_SIDE_CELLS, reads=READS,
                             sets=dict(loan_losses_sourced=dict(loan_losses="sourced"))),
    shocks_on=dict(cells=_SIDE_CELLS, reads=READS, sets=dict(shocks_on=dict(shocks=True))),
    leave_noise=dict(cells=_SIDE_CELLS, reads=READS,
                     sets=dict(leave_noise_half=dict(leave_noise=0.5), leave_noise_twice=dict(leave_noise=2.0))),
    durables_from_savings=dict(cells=_SIDE_CELLS, reads=READS,
                               sets=dict(durables_from_savings=dict(durable_savings="used"))),
    as_released=dict(cells=_SIDE_CELLS, reads=READS,
                     sets=dict(rewards_uncounted=dict(experience_rewards=False),
                               cut_whole_line=dict(card_cut_on="line"), payout_accrued=dict(payout="accrued"),
                               standby_measured=dict(standby="measured"),
                               receipts_one_month=dict(receipts_window=1),
                               buffer_share_of_liquid=dict(buffer_reserve="share_of_liquid"))),
    no_failure_fee=dict(cells=_SIDE_CELLS, reads=READS,
                        sets=dict(no_failure_fee=dict(fees_a_month=0.0, buffer_prices_past_cap=False))),
)

# Every side set by name, and the study it belongs to.
SIDE_SETS = dict(chain.from_iterable(study["sets"].items() for study in STUDIES.values()))
_STUDY_OF = dict(chain.from_iterable(zip(study["sets"], repeat(study)) for study in STUDIES.values()))
NAMES = ("base", *SIDE_SETS)


def settings(name="base", reading="quote"):
    """The settings of the second run's ``name`` ("base" or a side set) at saver reading ``reading``, unchecked: the
    lengths, the base settings, the set's changes and the reading (``economy`` checks them)."""
    if name not in NAMES:
        raise ValueError(f"The second run is 'base' or a side set {sorted(SIDE_SETS)}, not {name!r}")
    if reading not in reads(name):
        raise ValueError(f"{name} runs on the saver readings {reads(name)}, not {reading!r}")
    return {**LENGTHS, **BASE, **SIDE_SETS.get(name, {}), "entry_reads": reading}


def unknown(name="base", reading="quote"):
    """The settings of ``name`` at ``reading`` that are not fields of the Economy, in order of name; none when the
    Economy has every one."""
    known = {field.name for field in fields(Economy)}
    return sorted(set(settings(name, reading)) - known)


def economy(name="base", reading="quote"):
    """The Economy settings of the second run's ``name`` ("base" or a side set) at saver reading ``reading``, as a
    dict to give the Economy (``settings``). A setting that is not a field of the Economy is refused, so the run
    cannot go ahead on an engine that lacks one of its rules."""
    missing = unknown(name, reading)
    if missing:
        raise ValueError(f"{name} sets {missing}, which the Economy does not have")
    return settings(name, reading)


def cells(name="base"):
    """The cells ``name`` runs on, as a selection of the grid (r_out, a0, distress)."""
    if name not in NAMES:
        raise ValueError(f"The second run is 'base' or a side set {sorted(SIDE_SETS)}, not {name!r}")
    return dict(GRID) if name == "base" else dict(_STUDY_OF[name]["cells"])


def reads(name="base"):
    """The saver readings ``name`` runs on: both, except where the set itself mixes them (savers' trust)."""
    return READS if name == "base" else _STUDY_OF[name]["reads"]

