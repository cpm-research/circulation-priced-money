# Robustness plan: time and updating, adoption rule, network, launch and chains of failure

17 November 2026. Written before any run it describes and before any confirmation seed is read. It adds checks
around the model of `docs/ANALYSIS_PLAN.md`. It changes no rule of the model and no clause of the registered claim.
Every switch below is off by default and every record changes no value the model uses, so the final development map
must be reproduced value for value after the build (section 7). The analysis plan is amended once more at the new
freeze, to say that the engine gained these records and switches before any confirmation seed was read.

## 1. Why these checks

The model makes choices that a reader trained on agent-based models will question, and that the paper so far states
without testing:

1. **Updating.** Which decisions are taken by everyone at once, which by a random part of the population, and how the
   day's payments are settled. Synchronous updating can create results that a different schedule removes
   (Huberman and Glance 1993), so the scheme has to be stated, justified and tested.
2. **The adoption rule.** A person joins with a chance that rises in proportion to the share of its trading partners
   who are members. That is simple contagion. A payment money is a good with complements and a matter of trust, the
   textbook case for complex contagion, where a person needs enough of its contacts to have joined (Centola and Macy
   2007). Card and mobile payment adoption shows such complements in data (Higgins 2024; Crouzet, Gupta and
   Mezzanotti 2023).
3. **The network.** Sellers are drawn uniformly at random, so the economy is close to well mixed. Real payment
   networks have hub sellers and local circulation (Mattsson, Criscione and Takes 2023 for Sarafu).
4. **Launch.** The first members are scattered at random. A real launch starts in one place or with the largest
   sellers.
5. **Chains of failure.** The paper reports how many payments fail, and not how much of that failure is caused by
   other people's failures.
6. **Single runs and the grid.** Figures show seed means, and the stress boundary is located only between grid
   levels half a point apart.

## 2. What the engine does now

Established by reading every update in `src/cpm_abm/engine/` in the order it runs.

### 2.1 Time and updating

No rule visits people one after another and none draws a visiting order. Every rule is applied to all people in one
operation, and randomness enters only as an independent draw per person. A person's place in the arrays never gives
it priority. The one tie broken by list order is within one buyer: its equal-sized purchases go on its card in the
order they were created until the line is full, and the seller of each is a uniform draw.

| What happens | When | Who acts | What they read | How a scarce quantity is shared |
|---|---|---|---|---|
| Wages, bills, instalments, the card statement | Each person's own pay dates and billing dates (daily, weekly, fortnightly, monthly or 60-day cycles on a random phase); the statement on day 20 | Whoever has a date that day | Own balances | n/a |
| Settlement of a day's payments | Daily | Every payer with a payment due | Today's receipts, which depend on other payers' completion today | One simultaneous solution (below); pool cash pro rata to requests |
| Pool cash within a day | Daily | The pool | Its cash | Instalment purchases first, then bridges, then (day 20) card statements; pro rata within each |
| Pool terms | Start of month | The pool | Its own record of the last two completed months; losses with a three-month lag | One published set of prices |
| Owners' exit | Start of month | A random 15.3% of owners | Own realised return over up to 12 months | Paid pro rata from pool cash after two months' notice |
| Savers' entry | Start of month | A random 15.3% of savers | The published quote against the saver's alternative | Accepted pro rata up to the room |
| Cash buffer | Start of month | Everyone, every month | Own last month's daily cash flow; published bridge price and yield; for a member with no shortfall last month, the pool-wide share of requests served | n/a |
| Leaving | Month end | A random 15.3% of members | Own experience over 12 months | n/a |
| Joining | Month end | Every non-member, with chance 0.25% + 3.17% x contact share a month | The share of this month's trading partners (service and wage, both directions) who were members | n/a |
| Next month's spending | Month end | Everyone | Own net worth against the population mean | n/a |

The review chance is 1 - exp(-0.166) = 0.153 a month, the exact monthly chance of a clock that rings at rate 0.166
(Gillespie 1977). Leaving and joining read participation before either is applied, and the new status is set once.

**The day's settlement.** The unknown is each payer's completed share of its payments due that day. Receipts depend
on other payers' completed shares, so the solution is a fixed point. The code starts from every payer completing in
full and repeats the map until no share moves by more than 1e-14 (cap 20,000 sweeps). Cover is taken in a fixed
order: own money and the day's receipts, same-day savings, the pool, the card's cash advance, earned-wage access, and
only then failure. Three facts follow.

- Without pool rationing the map is monotone (more completion by others never lowers a payer's completion), so
  starting from full payment gives the greatest solution. This is the fictitious default algorithm of Eisenberg and
  Noe (2001), and payers who fail in its first round are those who would fail even if paid in full.
- More than one solution can exist. Two people with no money who owe each other the same day both pay in the
  code's solution and both fail in another. The code's choice is the netted outcome. Paying one at a time would
  leave such a pair unpaid, which is what the payment systems literature calls gridlock (Bech and Soramaki 2001).
  The choice is the same in every arrangement and is generous to completion.
- When pool cash is short, requests are served pro rata, and then the map is no longer monotone: more receipts for
  one borrower can raise its request and cut everyone else's share. The code detects a two-state cycle and defers
  the request that qualifies in one state and not in the other.

### 2.2 Adoption and the network

A non-member joins in a month with chance xi0 + xi1 x c, with xi0 = 0.03 / 12, xi1 = 0.38 / 12 and c the share of its
trading partners that month who were members. This is the Bass hazard on the realised network. Adoption by
influence that is linear in the adopting share of contacts is what Karsai, Iniguez, Kaski and Kertesz (2014)
measured on the Skype network. Each buyer makes 32 service purchases a month from sellers drawn uniformly, and pays
one wage to one person drawn uniformly at the start. With about 64 service partners a month drawn from everyone, a
person's contact share is the population share plus sampling noise. People are indexed in order of wealth, so any
spatial arrangement has to use positions drawn at random.

### 2.3 Failed payments

A payer short on a day completes the same share of each of its payments. A failed purchase is lost to its seller, and
a failed wage is re-queued, so a failure is missing income for someone else that day or later. The runs record
failed payments by person and month and, under distress, apart for the earners of a job in a spell.

## 3. What the stored development map already shows

Three development seeds, 4,000 people, 105 cells, 318 jobs. No new run.

**No flip-flop.** A synchronous artefact shows as a series that alternates around its trend month by month. For
every stored monthly series of every job, the trend (a centred five-month mean) was removed and two numbers
computed: the correlation between successive months' remainders, and the share of the remainder's variance at a
period of two months. White noise through the same filter gives -0.30 and 0.015 (95th percentile 0.059); a flip-flop
gives -0.93 and 0.93. Participation, pool capital, the charge, coupons, the quote, buffers, offers, exits, bridges
served, revolved balances and written-off loans all sit at the noise level (median share at most 0.06, no job above
0.27).

**One two-month rhythm, and it is the calendar.** The failed share of people not in a job-loss spell has a
period-two share of 0.17 under banks and 0.14 under best-case DeFi (largest 0.44), against 0.03 in the pool
arrangements. Its size is 0.3 to 1.3% of the series' level. Its direction is set by the seed: positive in at least
92% of the cells of every arrangement in seeds 20261021 and 20261023, and negative in at least 89% of them in seed
20261022 (in every cell under banks). An
artefact of everyone starting and re-choosing together would have one direction in every seed. A fixed direction per
seed is what the 60-day billing cycle gives, since each seed's population has slightly more 60-day billers in one
parity of months than in the other. The stores of the size check hold no monthly series, so the size dependence of
this rhythm is not yet shown.

**Same-day chains are short.** The largest number of sweeps a day needed in a month has median 4 under banks and
best-case DeFi (90th percentile 4, largest 27), 7 to 8 in the pool without the charge and 4 to 7 under CPM (90th
percentile 9 to 10). No day in any run needed more than 500.

**Under distress most extra failures fall on people who were not laid off.** The layoffs of any run can be re-drawn
exactly from its seed, and a run at a distress level differs from the same seed's run at level 0 only through the
extra layoffs. In one cell (outside rate 4.4%, launch 30%, 2 points against 0, months 25 to 60, counts of failed
shares), 80 to 88% of the excess failed payments are by people who lost no wage to an extra layoff (60 to 73% within
the distress year), in every arrangement. In the distress year the excess is smaller in the pool arrangements in all
three seeds (about 3,600 to 4,000 against about 5,000 under banks and best-case DeFi). Over months 25 to 60 the
excess is similar across arrangements, and in one seed larger in the pool arrangements. This reading mixes three
channels: missing income passed along the payment network, the money that extra layoffs' wages take out of the
household economy, and the shift in everyone's spending. It is the spread of distress to people not laid off. It is
not a measure of chain length.

## 4. Records added to every run

Both are observation only. A test asserts that every series the runs already store is identical with the records on.

**4.1 Own shortfall and knock-on, same day.** After the day's final solution, the failed amount of each payer is
split in two. The own-shortfall part is what it fails in the first sweep, with every payment owed to it that day
arriving in full, under the day's final pool queue. The knock-on part is the rest: failure that happens only because
receipts were short. Stored by month and arrangement: the two amounts, the number of payer-days with each, and the
number of days by how many payers had a knock-on failure (0, 1, 2 to 3, 4 to 7, 8 to 15, 16 to 31, 32 or more). The
split is that of fundamental and contagious default in Elsinger, Lehar and Summer (2006). They note that the round
in which a default appears has no economic meaning, so the number of sweeps is not reported as a depth. With pool
rationing a payer's knock-on part can be slightly negative, since a neighbour's failure can free pool cash for it;
the signed sum and the positive part are both stored.

Hand case. A holds nothing and owes B 10. B holds 4, owes C 10 and is owed A's 10. With full receipts A fails 10 and
B fails nothing. In the solution B receives nothing, pays 4 and fails 6. Failed 16: own shortfall 10, knock-on 6, one
payer with a knock-on failure.

**4.2 Dependence on netting.** After the day's final solution, take the largest set of payers who complete at least
one cent of the payments they have due today, have no means of their own today (no money, no same-day savings, no
credit granted today, no card receipts) and are paid today only by members of the set. Their completed payments
exist only because the solution is simultaneous. (The floor of one cent was added on 17 November after the first
run of the record: without it the set was non-empty on about 25 of 1,800 days, each time for one payer whose dues
were a rounding remainder below 10^-11 of a month's spending and whose completed value was zero to stored
precision.) Stored by month and arrangement: the days with a non-empty set, the payers in it, the value they
completed, the value lost when the set is held at zero and the map is repeated downward with the day's credit held
fixed, and the day's total completed value. Outside this set every payer has money of its own or is paid by someone
who has, so any order of settlement with retries until the day ends reaches the same outcome.

Hand case. A and B hold nothing and owe each other 10 on the same day. Both pay in the solution; the set is {A, B}
and the value is 20. If A holds 1, the set is empty: A pays 1, B passes it back, and the pair clears in ten rounds.

## 5. Switches, off by default

Each uses random streams of its own, so no existing draw moves. All five arrangements of a job share the same
network, thresholds and launch set, so every comparison stays paired.

**5.1 Buffer review share.** Each month a person re-chooses its cash buffer with chance alpha and otherwise keeps
last month's. The base is alpha = 1. This is alpha-asynchronous updating, the standard test of whether a result
depends on everyone moving at once. Values: 0.5 and 0.153, the model's own review chance. Hand case: alpha = 0.5,
draws 0.3 and 0.7, the first person re-chooses and the second keeps its buffer. The base keeps alpha = 1 because a
household that revisits its buffer twice a year is a different behaviour, not only a different schedule.

**5.2 Joining rule.** Base: chance xi0 + xi1 x c. Threshold rule: chance xi0 + xi1 if c is at least the person's
own threshold, else xi0. Thresholds are fixed per person. Three settings:

- *Uniform on 0 to 1.* The share of people whose threshold is met at contact share c is c, so the mean chance is
  xi0 + xi1 x c, the base. A check that the rule is built right, and the bridge between the two rules (Granovetter
  1978).
  *Corrected on 17 November, after this set was read.* The equality holds in the first month only. A threshold
  kept for the run sorts people: those with low thresholds join first, and the people still outside are those with
  the higher ones, so adoption falls behind the base. The base is the case in which a threshold is drawn afresh
  every month; what a threshold rule adds is that each person keeps its own. The set therefore measures what
  keeping the threshold does. The well-mixed path that follows the share outside threshold by threshold gives
  participation of 0.56 at month 60 from a launch of 20%, against the base's 0.69; the runs give 0.564 against
  0.690.
- *Measured.* Log-normal with log-mean -2 and log-spread 1 (mean 0.19), fitted by Karsai, Iniguez, Kikas, Kaski and
  Kertesz (2016) to adoption of a paid Skype service. Their share of people who never adopt (0.73) belongs to that
  product and is not used. Hand case: at c = 0.05 the threshold is met for a share Phi((ln 0.05 + 2) / 1) = 0.16 of
  people, so the mean chance is 0.0025 + 0.0317 x 0.16 = 0.0076 a month against the base's 0.0041. With measured
  thresholds the share whose threshold is met exceeds the contact share itself between about 2% and 97%, so
  adoption is faster than the base over that whole range. The 2.3% of people with a threshold above 1 join by
  innovation only.
- *Common threshold* of 0.1, 0.2 and 0.3, the design of Watts (2002), mapped against launch share. Hand case in a
  well-mixed population, ignoring leavers: below the threshold only innovation works, so reaching 0.2 takes
  ln((1 - a0) / 0.8) / 0.0025 months, 69 from a launch of 5% and 47 from 10%. A 5% launch does not tip within the
  60-month run; a 10% launch tips in year 4.

The mean-field path for any setting is A(t+1) = A + (xi0 + xi1 F(A))(1 - A) - lambda A with F the thresholds'
cumulative share, and is set beside the simulated path as the base's is.
*Corrected on 17 November.* That formula is the path when thresholds are drawn afresh each month. With thresholds
kept, the share of people outside is followed threshold by threshold: a person outside joins with chance xi0, and
with xi0 + xi1 once participation has reached its threshold; a member leaves with chance lambda; participation is
one less the mean share outside. This is the path set beside the simulated ones (`mean_field` in
`scripts/paper_figures.py`). The hand cases above for the measured and common thresholds do not depend on the
correction: they use the first month's chance and innovation alone.

**5.3 Sellers.** Base: uniform, redrawn every month. Two other worlds:

- *Ring.* People stand on a ring in random order. A purchase goes to one of the buyer's 32 nearest neighbours (16
  each side) with chance equal to the local share, and to anyone otherwise. Local share 1 is the clustered end, the
  ring of Watts and Strogatz (1998). Local share 0.35 is the midpoint of the share of card transactions within about
  a mile of home in two US cities, 28% and 43% (to be read in the original before it is printed). Every person's
  expected receipts are as in the base. Hand case: the person at position 100 with local share 1 buys only from
  positions 84 to 116.
- *Hubs.* A seller is chosen with chance proportional to a weight k^(-0.526) by rank k, which gives a number of
  partners with a tail exponent of 2.9 (Goh, Kahng and Kim 2001: exponent 1 + 1 / 0.526), the value measured on
  Sarafu. Larger weights go to larger spenders, so larger sellers are larger buyers. Hand case at 4,000 people: the
  largest seller takes about 0.9% of all service sales, about 16 months of mean spending a month, against its own
  service spending of about 7.6 (its whole spending is about 18); the median seller takes about 0.29 against service
  spending of 0.35. The exponent is for
  the number of partners; the source could not estimate the tail of amounts. The heavier fit of 2.2 is not run: at
  4,000 people it would give one person about 5% of all sales.

Wage links stay uniform in every world.

**5.4 Launch placement.** Base: each person independently with chance a0. Ring: the round(a0 x n) people on
consecutive positions (one neighbourhood). Hubs: the round(a0 x n) largest sellers. Each is nested across launch
levels as the base is. Hand case on the ring with local share 1 and a common threshold of 0.2, counting sellers
only: a person whose nearest member is 5 positions away has 12 of its 32 sellers inside the neighbourhood (38%) and
is above the threshold; one 12 positions away has 5 (16%) and is below. The front is 10 positions deep on each side
and each person in it joins at 3.4% a month (innovation and imitation together), so the neighbourhood grows by
roughly two people every three months at first. Clustering lets a launch below the threshold spread, slowly.

## 6. Runs

Development seeds 20261021 to 20261023, 4,000 people, every arrangement. No confirmation seed is used.

| Set | Cells | Variants | Jobs |
|---|---|---|---|
| Records | The six side-check cells (outside rate 4.4%; launch 5, 20, 60%; distress 0 and 2 points), base settings | 1 | 18 |
| Buffer review share | The same six cells | alpha 0.5, 0.153 | 36 |
| Adoption rule, uniform sellers | Outside rate 4.4%, no distress, seven launch levels | Measured thresholds; common 0.1, 0.2, 0.3 | 84 |
| Rule check | Outside rate 4.4%, no distress, launch 20% | Uniform thresholds | 3 |
| Ring | Outside rate 4.4%, no distress, seven launch levels | Local 1: base rule scattered and neighbourhood; threshold 0.2 scattered and neighbourhood. Local 0.35: base rule scattered; threshold 0.2 neighbourhood | 126 |
| Hubs | Outside rate 4.4%, no distress, seven launch levels | Base rule scattered and largest first; measured thresholds scattered and largest first | 84 |
| Stress in the other worlds | Outside rate 4.4%, 0 and 2 points, seven launch levels | Ring local 1 and hubs, base rule, scattered | 84 |
| Stress boundary | Outside rate 4.4%; launch 20, 30, 45%; distress 0, 1.6, 1.7, 1.8, 1.9 points | Base | 45 |

About 480 jobs, about 31 worker-hours, close to three hours on twelve cores. A stressed level is read against the same
seed's level 0 in the same run, so the two stress sets run level 0 as well; in the stress boundary set those nine jobs
repeat cells of the development map and must come out identical to it.

## 7. Proof that the main map is unchanged

After the build, the six side-check cells of the final development map (outside rate 4.4%; launch 5, 20 and 60%;
distress 0 and 2 points; 18 jobs) are rerun at 4,000 people with every switch at its default, and every value stored
before must be identical, as in the check of the modular code. The test suite must pass with none skipped. Only then
do the runs of section 6 start, and only then is the confirmation run's code frozen again.

Done on 17 November at commit 1284795: 433 tests passed with none skipped, and the rerun reproduced all 356,670
values the map stores for those jobs (59,850 by cell and seed, 296,820 monthly), with none differing and none
missing; the only additions were the 17 new record series in each arrangement. The check is repeated at the freeze
commit, since the netting record's floor of one cent (section 4.2) was added after it.

Repeated on 17 November at the freeze commit da2f11d: 462 tests passed with none skipped, and the rerun again
reproduced all 356,670 values with none differing and none missing. With the floor of one cent the netting set
was empty on every day of every run. The nine jobs of the stress boundary set with no distress, run on the
earlier commit, also reproduced the map: 116,325 values, none differing.

## 7a. What the runs showed

All 18 sets ran on the development seeds on 17 November and are shipped under `results/robust_*`, each with its
results card. The paper reports them in its results section: the update scheme; the adoption rule, the network
and the launch; chains of failure; and the stress boundary. In short: CPM's gain over banks and cards and over
best-case DeFi survives, by the rule of section 8, in all seven launch cells of all fifteen variants; what the
variants change is how fast the network fills. Two statements of this plan did not hold and are corrected in
place with their date: that uniform thresholds reproduce the base (section 5.2), and the netting record without
its floor (section 4.2). The rule fixed here for a critical mass turned out too weak to tell tipping from
innovation, and the paper says so.

## 8. Readings fixed before the runs

- **Every variant** reports, on the seed mean and for each seed: participation month by month and at month 60;
  CPM's gain over banks and over best-case DeFi in money and with completed purchases counted; the failed share in
  each arrangement; the bridge price; the charge. The table has the form of the existing side-check table, with the
  ratio to the base on the same cells and seeds.
- **"The gain survives"** in a world when CPM's money gain over banks and over best-case DeFi is positive on the seed
  mean in all seven launch cells and in at least two of three seeds in each. Otherwise the cells where it does not
  are named.
- **Critical mass** under a common threshold is the lowest launch level whose seed-mean participation at month 60
  exceeds its launch share by at least 0.05. It is set beside the hand case of section 5.2.
- **The buffer schedule** is read as the other side checks are: ratios to the base, no verdict word.
- **The two records** are reported for every arrangement: the knock-on share of failed value with its paired
  difference, CPM less banks, across seeds; and the share of completed payment value that depends on netting, with
  the number of days on which the set was not empty.
- **The stress boundary** is the lowest distress level, in steps of 0.1 point, at which a majority of seeds read a
  pool run by the rule already in the plan.
- Whatever these show is reported. No rule of the model changes because of them.

## 9. What the paper gains

- In the model section: a five-part summary (agents and their state, the network, the update rules, the control
  parameters, the order parameters), and a subsection on time and updating with the table of section 2.1, the
  statement on the day's settlement, the netting number and the buffer test.
- In the purpose paragraph: that the model compares designs and forecasts nothing; which controls are the
  environment (the outside rate, distress), which is the launch condition, and that the design is the contract.
- In the joining paragraph: the Bass form by name, the evidence for it, and where complements enter (through use and
  leaving).
- In the results: a subsection on the adoption rule and the network with one table and one figure; a paragraph and
  table on chains of failure; the finer stress boundary; single-seed paths behind the means in the participation and
  failed-payments figures.
- In the limits: the netting choice and the side it leans to; that same-day reuse of receipts is granted to every
  arrangement; that chains across days are read only as spread to people not laid off; that wage links are uniform
  in every world.

## 10. What stays outside

- Networks grown from data, or one that changes as people join.
- A heavier tail than 2.9 for sellers, and a tail of amounts as opposed to partners.
- Thresholds measured for a payment money: the measured distribution is from one paid online service.
- A count of chains across days. It needs a record of receipts lost by payee and a run in which the extra layoffs'
  wages stay inside the economy.
- More than three seeds for these checks. They are development evidence and are labelled so.

## 11. Sources

Read on the publisher's, journal's or authors' own pages unless marked.

- F. M. Bass (1969), "A New Product Growth for Model Consumer Durables", Management Science 15(5), 215-227. Hazard
  form not yet read in the original.
- M. L. Bech and K. Soramaki (2001), "Gridlock Resolution in Interbank Payment Systems", Bank of Finland Discussion
  Paper 9/2001.
- W. E. Beyeler, R. J. Glass, M. L. Bech and K. Soramaki (2007), "Congestion and cascades in payment systems",
  Physica A 384(2), 693-718. Cascades of settlement have a characteristic size; no power law of sizes is claimed.
- R. Baptista and others (2016), "Macroprudential policy in an agent-based model of the UK housing market", Bank of
  England Staff Working Paper 619. Monthly steps, a fixed sequence of markets, decisions as monthly chances.
- R. Axtell (2001), "Effects of Interaction Topology and Activation Regime in Several Multi-Agent Systems", MABS
  2000, LNCS, 33-48.
- D. Centola and M. Macy (2007), "Complex Contagions and the Weakness of Long Ties", American Journal of Sociology
  113(3), 702-734. The four mechanisms not yet read in the original.
- N. Crouzet, A. Gupta and F. Mezzanotti (2023), "Shocks and Technology Adoption: Evidence from Electronic Payment
  Systems", Journal of Political Economy 131(11). Abstract.
- L. Eisenberg and T. H. Noe (2001), "Systemic Risk in Financial Systems", Management Science 47(2), 236-249.
- H. Elsinger, A. Lehar and M. Summer (2006), "Risk Assessment for Banking Systems", Management Science 52(9),
  1301-1314.
- D. T. Gillespie (1977), "Exact stochastic simulation of coupled chemical reactions", Journal of Physical Chemistry
  81(25), 2340-2361.
- K.-I. Goh, B. Kahng and D. Kim (2001), "Universal Behavior of Load Distribution in Scale-Free Networks", Physical
  Review Letters 87, 278701.
- M. Granovetter (1978), "Threshold Models of Collective Behavior", American Journal of Sociology 83(6), 1420-1443.
  Abstract; the uniform case not yet read in the original.
- S. Higgins (2024), "Financial Technology Adoption: Network Externalities of Cashless Payments in Mexico", American
  Economic Review 114(11). Abstract.
- B. A. Huberman and N. S. Glance (1993), "Evolutionary games and computer simulations", PNAS 90(16), 7716-7718. One
  scenario of one model; the lesson taken is that the update scheme can change results, not that synchronous results
  are artefacts.
- M. Karsai, G. Iniguez, K. Kaski and J. Kertesz (2014), "Complex contagion process in spreading of online
  innovation", Journal of the Royal Society Interface 11(101).
- M. Karsai, G. Iniguez, R. Kikas, K. Kaski and J. Kertesz (2016), "Local cascades induced global contagion: How
  heterogeneous thresholds, exogenous effects, and unconcerned behaviour govern online adoption spreading",
  Scientific Reports 6, 27178.
- C. E. S. Mattsson, T. Criscione and F. W. Takes (2023), "Circulation of a digital community currency", Scientific
  Reports 13, 5864.
- F. Sultan, J. U. Farley and D. R. Lehmann (1990), "A Meta-Analysis of Applications of Diffusion Models", Journal
  of Marketing Research 27(1), 70-77. The paper's 213 applications are confirmed; its average coefficients of 0.03
  and 0.38, which the model uses, are confirmed only in papers that cite it and are to be read in the original.
- D. J. Watts (2002), "A simple model of global cascades on random networks", PNAS 99(9), 5766-5771.
- D. J. Watts and S. H. Strogatz (1998), "Collective dynamics of 'small-world' networks", Nature 393, 440-442.
- The share of card transactions close to home: a 2017 study of card data in Detroit and New York, to be read in
  the original and cited in full before it is printed.
