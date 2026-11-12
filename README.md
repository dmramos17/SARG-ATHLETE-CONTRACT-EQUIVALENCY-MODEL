# SARG-ATHLETE-CONTRACT-EQUIVALENCY-MODEL

Tax-equivalency and recommendation engine for professional athlete contracts across state tax jurisdictions.

On September 8, 2026, the New England Patriots and Christian Gonzalez agreed to a four-year, $135 million
extension. Massachusetts adds a 4% surtax on income over $1,107,750 (2026). This project asks what that
contract is really worth after tax, and what another team would need to offer to match it.

## Quick start (from the repo root)
    pip install pandas
    python db/clean_tax_data.py              # build athlete_tax.db, run 16 checks
    python -m unittest discover tests -v     # 18 tests
    python analysis/gonzalez_week4_demo.py   # residency scenarios, tax year 2026

## Layout
    data/                 raw Tax Foundation downloads (never edited by hand)
    data/curated/         hand-researched tables, every row sourced (jock rules, local taxes, teams, league rules)
    data/raw/legacy/      old jock-tax CSVs, archived (contained errors; no longer read)
    data/processed/       tidy CSVs written by the pipeline (commit these)
    db/schema.sql         SQLite schema v2
    db/clean_tax_data.py  pipeline: raw -> processed -> athlete_tax.db -> checks
    etl/duty_days.py      duty-day allocation and state/local tax preview (Week 4)
    analysis/             demos and analysis scripts
    tests/                unit tests

athlete_tax.db is generated: keep it in .gitignore.

## Local browser dashboard (no Streamlit)

```sh
python3 src/athlete_tax/clean_tax_data.py  # initial database, requires pandas
python3 dashboard/server.py
```

Open [Athlete Tax Lab](http://127.0.0.1:8765/). The dashboard is a local HTML/JavaScript
interface with a Python standard-library server. Every indexed 2025 player now has
a tax page. The original three cash examples are retained for Christian Gonzalez,
Devon Witherspoon and Patrick Surtain II.
Reported annual cash is $2,122,988, $3,646,468 and $22,170,000 respectively,
from OverTheCap season history. These are reported season cash totals, not verified
calendar-year W-2 wages. Payment timing, incentives and postseason earnings need
player-level records. Prior signing/option bonus cap proration is excluded from cash.
The original 2026 snapshots remain available in the repository for earlier analysis.

### Estimated duty-day calendar

`etl/estimated_duty_days.py` constructs a unique date-by-date **calendar-year 2025**
team service estimate for all 32 teams. It includes January–February 2025 games from the 2024 season,
2025 preseason, the previously sourced out-of-state joint practices, and an
estimated camp-to-December service window. January 2026 is excluded. Default counts are
144 days for NE, 144 for SEA and 150 for DEN. These are model outputs, not actual
player duty-day totals or confidence intervals.

- Actual game dates and venue jurisdictions come from the saved NFL schedule
  subset in `data/curated/nfl_games_calendar_2025.json`, with source URLs.
  The expanded saved calendar contains 334 ESPN game events: 49 preseason,
  272 regular-season games played within calendar 2025, and 13 postseason games
  from the 2024 season. Actual venue addresses determine states, including seven
  international games, the relocated Rams–Vikings Arizona playoff and the February
  2025 Super Bowl in Louisiana. Pro Bowl events are excluded. UTC timestamps are
  converted to US Eastern game dates to avoid shifting night games to the next day.
- Other service-window dates assume practice, meetings or team-facility work in
  the team's practice state. Tuesday is assumed off, unless a game, joint practice
  or modeled travel/preparation event takes precedence.
- Away games assume one destination service day before the game. This does not
  establish the actual itinerary or each state's treatment of travel days.
- Full-year residence defaults to the team practice state. It remains editable
  and is not a claim about actual player domicile.
- Offseason workouts/minicamps are omitted unless added. Bye-week service and
  injury rehabilitation remain assumptions. Inactive games do not automatically
  remove duty days; use individual travel/rehab evidence to correct locations.
- Foreign duty remains in the denominator without a US state allocation. Foreign
  income tax, tax treaties and federal foreign-tax credits are not modeled.

Expand **Adjust assumptions** to choose 0–3 arrival days, select a weekly off day,
exclude dates, add offseason service dates, or correct a date's work state
(`2025-09-14=WA`; `FOREIGN` for no US state allocation). Click **Rebuild calendar &
update taxes**. Rebuilding replaces manual state totals and local wage bases.
The **Explore estimated 2025 duty days** panel distinguishes documented team events
from modeled dates and user adjustments. Download its calendar as CSV for review.
Manual state-day edits change the tax estimate only, not the daily calendar.

### Tax calculation and limits

The demo uses 2025 federal brackets, the updated $15,750 single / $31,500 joint
standard deduction, and the $176,100 Social Security wage base. Employee Medicare
and Additional Medicare use annual wages. Wage-only income, no spouse income,
itemizing, credits or AMT are assumed. Employer taxes and state payroll programs
are excluded. Sources: [IRS 2025 instructions](https://www.irs.gov/instructions/i1040gi),
[SSA wage bases](https://www.ssa.gov/oact/cola/cbb.html),
[IRS payroll](https://www.irs.gov/taxtopics/tc751).

2025 state brackets are saved separately in
`data/processed/state_income_tax_brackets_2025.csv`; they are never relabeled 2026
rows. The published Tax Foundation 2025 table is retained in
`data/raw/historical/state_tax_table_2025.html`. Explicit historical corrections
use California FTB, Maryland Comptroller, Ohio statute and Wisconsin DOR sources
listed on each row. MA's $1,083,150 surtax threshold and California's fixed $1M
mental-health threshold are separate sourced inputs. Some uncorrected published
brackets remain provisional; the source table notes prior-year inflation bounds
for certain states. State deductions/exemptions, NY benefit recapture and detailed
resident credits/sourcing are omitted. These are research estimates, not tax returns.

The calendar preloads supported local wage bases using modeled city work dates,
including home practice-city assumptions. Maryland special nonresident tax uses
all modeled Maryland work dates when residence is outside Maryland. Hotel cities
are not inferred. 2025 local rates are loaded for
Philadelphia (3.44% visitor Jan–Jun, 3.43% Jul–Dec), Cincinnati (1.8%), Kansas City
(1%) and Maryland special nonresident tax (2.25%). Payments default to a uniform amount per modeled duty date, with work date used
as a proxy for payment date; actual payroll timing must be reviewed. City credits/exemptions, Pittsburgh's
2025 litigation-dependent treatment, Detroit/Cleveland, Indiana county, Maryland
resident-county and other unsupported local taxes are omitted, not verified
exemptions. These gaps are displayed on the tax page. An unsupported
local rate produces an error when selected. The omissions can move estimated tax
in either direction. Local rates and athlete-specific taxable bases remain provisional.

`etl/historical_taxes.py` installs the saved 2025 inputs when the server starts.
`etl/contract_data.py` syncs reviewed cash snapshots into SQLite. No live scraper
or paid data subscription is required to run the saved demonstration.

```sh
python3 -m unittest discover -s tests
```

## Search-first NFL player directory (2025)

The home page at `/` now introduces the project and searches **2,257 unique
players across all 32 teams**. The definition is ACT or INA status in at least one
2025 regular-season weekly roster. This is season-wide historical coverage;
it includes players later injured, released or traded, and is not a single-date
53-man roster. Practice-squad-only and reserve-only records are excluded.

Type a player’s name, team, or position. The suggestion list supports mouse/touch,
arrow keys, Enter and Escape, and handles punctuation in names. Search matches
names first and falls back to team/position searches. Each player has a linkable
`/players/<gsis-id>` page showing sourced contract context and available 2025
season cash. Players without a GSIS ID receive a deterministic name ID.

The six home-page contract cards feature the largest matched deals signed in
2025, sorted by total reported value. They are not a live transaction feed or a
claim about the order of signings within the year. Separate tax-example cards
link to `/taxes/gonzalez-2025`, `/taxes/witherspoon-2025`, and
`/taxes/surtain-2025`. Direct links select the corresponding existing example.

The directory has reported season cash for **2,214 players**. Tax pages
are available for all 2,257 players. There are 2,181 prefilled provisional estimates
using positive reported season cash; 76 players have missing/zero cash and need a
verified amount before calculation. All imported cash initially follows service-wage
sourcing. A signing-bonus amount and its assumed treatment can be adjusted; no
bonus cash is inferred from salary-cap proration. The original three examples
retain their separate reviewed cash breakdowns. Imported estimates are labeled
unreviewed, and neither exact player attendance nor bonus qualification is claimed.
Multiple 2025 season rows are displayed separately, never added blindly. Total
contract value, average annual value, salary-cap charge, and cash remain separate.

### Rebuild the saved directory

The server requires only Python’s standard library and the saved
`data/snapshots/nfl_players_2025.json`. Regeneration additionally needs PyArrow:

```sh
.venv/bin/python -m pip install -r requirements-import.txt
curl -L --fail https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.csv -o /tmp/roster_weekly_2025.csv
curl -L --fail https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet -o /tmp/historical_contracts.parquet
.venv/bin/python -m etl.player_directory --rosters /tmp/roster_weekly_2025.csv --contracts /tmp/historical_contracts.parquet --accessed-date 2026-10-15
```

Use the actual access date when refreshing; restart the server afterward to clear
its directory cache. Source URLs, SHA-256 checksums, source update timestamp,
unit conversion, coverage counts, and join method are retained in the snapshot.
The older contracts CSV release dates to 2022 and must not be used as 2025 input.
The current Parquet data provides nested season history and stores amounts in
millions; the importer converts these to integer USD. It matches **2,255 players
by GSIS ID** and two by an unambiguous exact name. The reviewed examples also
use OTC identity to handle the Pat/Patrick Surtain name variation. No fuzzy name
match is silently promoted to an estimate. Later signings are excluded from the
2025 contract selection, regardless of the source’s current active-contract flag.

Source documentation: [weekly roster loader](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html),
[historical contracts](https://nflreadr.nflverse.com/reference/load_contracts.html),
[contract fields and units](https://nflreadr.nflverse.com/articles/dictionary_contracts.html).
The saved source update is October 15, 2026; this is a retrospective 2025 import,
not a snapshot of what was publicly known during the 2025 season.


### League-wide tax and membership model

`etl/nfl_schedules.py` rebuilds the complete game calendar and compact weekly
membership snapshot. Source inputs are downloaded separately; the site itself
makes no external requests. To regenerate with saved public sources:

```sh
curl -L --fail 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2025&limit=1000' -o /tmp/nfl-scoreboard-2025.json
curl -L --fail https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2024.csv -o /tmp/roster_weekly_2024.csv
.venv/bin/python -m etl.nfl_schedules --scoreboard /tmp/nfl-scoreboard-2025.json --rosters-2024 /tmp/roster_weekly_2024.csv --rosters-2025 /tmp/roster_weekly_2025.csv
```

`data/snapshots/nfl_memberships_2025.json` retains source URLs and checksums.
January–February team assignments use 2024 roster observations; summer/regular
season uses 2025 observations, including changes of team. For example, Sam
Darnold’s January 2025 calendar uses Minnesota, then Seattle in the 2025 season.
Rookies without 2024 roster evidence are not assigned invented winter service.
Roster status ACT/INA/DEV/RES/EXE is treated as possible team service; it does not
establish where an inactive or injured player actually worked. CUT/RET observations
stop modeled service until a later team-service observation. Weekly boundaries
are proxies for transaction dates, and summer team membership is extrapolated
from the first 2025 weekly observation. Individual corrections remain editable.

The original three camp starts and joint practices remain sourced. For the other
29 teams, camp starts are **model assumptions**: July 23, or 14 days before the
first preseason game if earlier. This is not a claim about actual reporting dates.
Other joint practices are not inferred. Dallas camp is explicitly modeled in
Oxnard CA through August 13 with unverified bounds; the page flags this assumption.
Closely spaced international fixtures use an assumed continuous overseas stay.

`etl/player_tax.py` distinguishes imported tax inputs from the original examples.
All positive reported cash initially counts as service wages, regardless of its
source cap components. This can overstate nonresident tax where a qualifying
bonus is actually residence-sourced. The tax page permits an explicit assumed
cash-signing-bonus reclassification and bonus treatment. Missing and zero cash
are never converted into a $0 liability or annual-average estimate; those pages
provide the calendar and require a verified annual cash amount. Payroll timing,
foreign tax, unsupported local taxes, state deductions and high-income recapture
remain limitations. Georgia’s 2025 flat rate was corrected to 5.19% using the
[2025 DOR instructions](https://dor.georgia.gov/document/document/2025-it-511-individual-income-tax-booklet/download).

The test suite exercises all 32 team calendars and every positive-cash player’s
calculation, checks unique dates and allocation totals, verifies international and
relocated venues, and checks the missing/zero-cash guardrail. Restart the server
after rebuilding schedule or roster files to clear the in-memory caches.

### Josh Allen full-contract pilot

Josh Allen's tax page now has an **Entire contract · 2025–2030** view. The source snapshot in `data/curated/josh_allen_contract_projection.json` records reported cash of $58M, $55M, $53M, $54M, $52.5M and $57.5M, totaling $330M. It separates base salary, the reported 2025 signing cash, roster/workout bonuses and the remaining unclassified cash. Prorated cap bonuses and void years are excluded from cash. The full scheduled value is conditional on earning the contract; it is not all fully guaranteed.

`etl/contract_projection.py` combines published 2025/2026 regular-season matchups with Buffalo's 2027–2030 home/away rotation slots from the NFL 2024 Record & Fact Book (page 12). Unknown away opponents are enumerated across each division, with equal independent weights; these are jurisdiction scenarios, not standings predictions. Home TBD opponents do not affect work location. Future order, Sunday dates and a Week 9 bye are synthetic. Calendar-year service includes January games from the prior season. The original 2025 calendar remains the baseline; 2026 also includes published preseason trips and January postseason from the 2025 season. Unpublished postseason/preseason trips and joint practices are excluded. Later calendars assume July 23 camp in New York and Tuesday off, and allow 0–3 arrival days. International relocations and future stadium moves are unknown and excluded.

Every year deliberately uses **frozen 2025 tax rules**, including deductions, payroll limits and selected local rates. No future-law or inflation forecast is implied. The default sources all cash as service wages, with an optional assumed qualifying residence-only treatment for the $56.745M 2025 signing bonus. Other bonus classifications remain unverified. Each year reports mean taxes/take-home across opponent scenarios. The six-year range sums annual extrema; it is an envelope, not a confidence interval or a guaranteed jointly achievable path. No discounting is applied. Unsupported taxes and other limitations of the annual model still apply. The full-contract view has its own explicit controls and does not inherit annual-page manual duty-day overrides.

API: `/api/contract-projection?player=00-0034857&residence=NY&filing=single&qualifying=0&travel_days=1`. The league-wide extension below now supports every player, with explicit cash coverage notices.

### League-wide entire-contract projections

Every player tax page now offers **Entire contract**. The selected player's own cash history, team schedule, residence default and projection window replace the Allen-only pilot settings. Allen's reviewed six-year pilot remains intact. Other players use imported annual cash without inferring signing/option bonus cash from cap proration.

The reproducible importer is `etl/projection_data.py`; runtime calculations live in `etl/league_projection.py`. `data/snapshots/contract_projections.json` contains the source metadata, player cash windows, published games and 32-team rotation slots. Runtime uses only local snapshots, with no network or Parquet/PDF dependencies. Import requirements add `pypdf` alongside `pyarrow`.

```sh
.venv/bin/python -m etl.projection_data \
  --contracts /path/to/historical_contracts.parquet \
  --fact-book /path/to/2024-Record-and-Fact-Book.pdf \
  --scoreboard-dir /path/to/scoreboards
```

The scoreboard directory should contain ESPN calendar-year responses named `nfl-scoreboard-2020.json` through `nfl-scoreboard-2024.json`, `nfl-scoreboard-2026.json` and `nfl-scoreboard-2027.json`. The existing curated 2025 calendar is reused. Import checks complete regular seasons through 2026, including the canceled 2022 BUF–CIN game, excluding unannounced future postseason. Source fingerprints and timestamps are saved. PDF extraction normalizes known typography/spelling errors and validates all 32 teams' 2027–2030 rotation slot counts.

The cash window starts at the reported signing year and ends at the later of the last positive reported cash year or the nominal signing-year-plus-term boundary. Extension effective years are not reliably supplied: **this window is not automatically a verified allocation of headline new money**. Headline value and reported guarantees appear separately. Usable cash is shown only when positively reported; missing/zero years remain uncalculated. Later-contract cash cannot fill a prior saved contract's years. Identical duplicate histories are collapsed, while ambiguous histories are not guessed. A complete displayed cash window is distinguished from a window that reconciles to headline value.

For pre-2025 years, the team named in a unique annual cash-history row selects the published team schedule; uncertain multi-team years use the selected 2025 team and are identified as assumptions. 2025 retains the existing player-specific weekly-roster calendar. Future years assume the player stays with their selected 2025 team. Generic calendars use a July 23 camp and Tuesday off, with published venue exceptions retained. Rookie draft-year calendars omit January service. Published preseason/completed postseason are included; unknown future playoffs, practice camps outside the home state, joint practices and offseason service are excluded.

The 2027–2030 opponent slots come from NFL Record & Fact Book pages 12–17. Later years extrapolate the current 17-game formula and home/away reversals at three-, four- and six-year rotation intervals; those fixtures are not announced schedules. Equivalent state/local duty-day allocations are compressed while retaining equal scenario weights. Opponent uncertainty is evaluated at the calendar-year boundary, including January games from the prior season once.

All years, including historical years, use frozen 2025 tax rules. These are comparable-rule illustrations, **not actual historical tax returns or future-law forecasts**. Full scheduled cash assumes the payments are earned; release, injury, guarantee vesting, endorsements and incentives are not predicted. The annual model's state/local omissions remain. Missing years produce clearly labeled known-years subtotals, never apparent full-contract totals or zero-tax years.

Import coverage on October 28, 2026: **2,257 matched players; 1,782 complete displayed cash windows and 475 partial windows**. A calculation sweep processed all 2,257 records with no errors; 2,184 have at least one calculable cash year. Complete-window counts do not certify legal contract boundaries or reconciliation to headline value.

### Contract-only view and Allen residence comparison

Tax pages now open directly to the entire-contract projection; the standalone 2025 estimate tab and its form are removed. The teammate selector remains available. Changing assumed residence recalculates automatically; advanced settings still use the update button.

Josh Allen pilots a two-column comparison of reported cash, scenario-mean take-home and estimated taxes. New York is the fixed residence baseline, while each new residence selection replaces the second column. Both calculations use identical filing, bonus and travel assumptions. A new selection never appends a third state. Request sequencing prevents slow earlier responses from replacing the latest choice, and baseline responses are reused for unchanged assumptions. Other players retain the single-residence contract summary.

The residence comparison now applies to every player. The baseline uses that player's existing team-practice-state residence assumption; each new residence selection replaces the second column automatically. Missing cash keeps both columns labeled as known-years subtotals and never produces a zero-income comparison. The update button now lives inside Advanced settings and applies the same filing, bonus and travel choices to both columns.

### MLB active-roster explorer and known-schedule tax estimates

`/mlb` searches **1,097 unique active-status players across all 30 MLB teams** from the MLB Stats API active roster endpoint, dated **November 5, 2026**. This is an offseason snapshot of status `A`, not a claim that every club has an in-season 26-man list. Injured/non-active lists and free agents outside the returned active rosters are not silently added. The three featured cards remain Ohtani, Judge and Soto; search opens every imported profile at `/mlb/players/<MLB-ID>`.

The import matches **1,065 players to reported annual cash**, and **955 have at least one eligible current-contract cash/schedule year through 2026** (1,361 eligible player-years). Missing cash, absent historical membership and multiple-team seasons have explicit exclusion reasons. Estimates never substitute current-team fixtures for an unresolved traded-player year or impute cash from AAV. Reported contract start/end dates define each player’s window, ending at 2026. The earliest current reported contract starts in 2015 (Giancarlo Stanton). Players without verified contract boundaries retain a separately labeled 2025/2026 annual-cash view; prior-career income is not used to guess the contract start.

The MLB-specific duty calendar imports published spring-training, regular-season and played postseason games with actual venue jurisdictions. Completed regular-season game counts reconcile to MLB standings for all 30 teams in both years. 2025/2026 use official first workout dates by role. Earlier camp starts are estimates: 12 days before first spring game for pitchers/catchers and 7 days for position players. The 2020 shutdown (March 13–June 30) is excluded; summer-camp reporting resumes July 1. Historical team affiliations come from official season appearances; no-appearance years stay missing. Doubleheaders count once per date; off days and arrival destinations are modeled, and cross-state split-squad dates are flagged. Known relocations (Athletics in Sacramento, 2025 Rays in Tampa) and international venues are retained. Foreign days stay in the denominator. This is estimated full-team-season attendance: individual call-ups, injuries, minor-league duty, All-Star/WBC participation, travel and offseason work remain unverified.

`/api/mlb/taxes?player=<MLB-ID>&residence=<US-state>&filing=single` computes federal, employee payroll, state and selected local U.S. components using each year's own 2015–2026 tax inputs. It returns included and excluded years, annual breakdowns, estimated calendars, sources and assumptions. State/local simplifications of the shared research engine remain. Toronto/Canadian residence is not treated as a tax-free state: its base result is unavailable, while a U.S. comparison explicitly assumes U.S. residence. Canadian/foreign taxes and treaty/foreign-tax credits are excluded from every displayed U.S. subtotal.

**No future tax projections are generated.** Contract headline values and reported future payment terms remain viewable, but **2027 onward, future options and deferred installments do not enter tax totals**. The displayed amounts are known-years cash/U.S. tax subtotals, not the entire contract's after-tax expected value. Reported cash approximates calendar-year wages and may include listed incentives; all cash is initially service wages. Signing-bonus qualification, exact payment dates and deferred-compensation FICA timing remain unverified. Ohtani's model uses $2M annual cash in 2024–2026, not $70M salary/AAV or the $680M future deferrals; special payroll treatment of vested deferred compensation is not modeled.

The interface keeps a fixed **Base State**, a replaceable comparison-state column, filing assumptions under **Advanced settings**, annual tax breakdowns, duty-day/source disclosures and **Open/Close Contract Information**. Changing states replaces the second comparison and preserves the base. Missing figures remain unavailable, never zero-income estimates.

Data and refresh workflow:

- `data/snapshots/mlb_players.json`: active identities, historical full-season club memberships, reported cash matches and available FanGraphs RosterResource contract terms.
- `data/snapshots/mlb_schedules.json`: 34,038 published fixture records across 2015–2026, including cancellations retained for audit; only played games enter calendars. Postponed/suspended placeholder rows are excluded before deduplication so they cannot displace a rescheduled played fixture. Standings counts independently check regular-season completeness.
- `data/snapshots/mlb_reported_cash.json`: saved public Spotrac 2015–2026 total-cash rankings, with URLs and check dates. Exact normalized-name matches are used; ambiguous names require team disambiguation and otherwise stay unmatched.
- `data/curated/mlb_contracts_spotrac.json`: the original three reviewed detailed payment snapshots, preserved separately from newer bulk cash snapshots. Ohtani deferrals and Soto listed incentives/options remain separate from guaranteed base/signing cash.
- `etl/mlb_import.py`: reproducible public-source import. It accepts exported cash ranking JSON (`year`, `source_url`, `accessed_date`, and `rows` with `name`, `spotrac_id`, `cash`, `team`). Example: `.venv/bin/python -m etl.mlb_import --as-of 2026-11-05 --cash-2025 <saved-2025.json> --cash-2026 <saved-2026.json>`. `--offline` rebuilds from the download cache without network requests. Source failures are recorded; no login, Premium history or access-control bypass is used. Rate-limited contract pages are left missing.
- `etl/mlb_model.py`: contract-window eligibility, baseball calendars and year-specific U.S. calculations. `etl/mlb_interface.py` serves catalog coverage. Runtime uses saved local data and performs no web scraping.

At this snapshot, full contract terms were available for 683 active profiles; other profiles retain cash information where matched. Payroll salary, prorated signing bonuses, CBT/luxury-tax amounts and AAV are displayed as source/accounting terms only and never used as cash. Tests cover roster uniqueness, all-team standings reconciliation, relocations, foreign days, doubleheaders, missing/multi-team inputs, Ohtani deferrals, matching tax-year rules, residence comparisons and a complete active-player calculation sweep.


### MLB history from contract start through 2026

Every player with reported contract boundaries now uses `startSeason`/`endSeason` from the selected source contract (or the reviewed Spotrac contract), stopping at the earlier of the reported end and **2026**. Historical income from replaced/previous deals is excluded. Aaron Judge includes **2023–2026 and $160M reported cash**; Ohtani includes **2024–2026 and $6M cash**, while future deferrals stay excluded. Stanton includes **2015–2026**, including Miami affiliations for 2015–2017 and reported prorated 2020 cash. Missing current-contract years are explicitly listed and never treated as zero.

`etl/mlb_history_import.py` adds the saved historical Spotrac cash rankings, MLB published schedules/venues and standings, and official year-by-year appearance clubs. It can use either per-year JSON files in `--cash-dir` or the combined saved cash snapshot. Run it after a fresh base roster import; runtime reads offline snapshots. All **360 team/year regular-season calendars** reconcile to MLB standings, including 2020's shortened season. Multi-club years remain excluded pending verified membership dates.

Historical tax inputs are installed by `etl/mlb_historical_taxes.py` through the existing startup sync. `data/curated/mlb_historical_federal.json` holds annual federal brackets, standard deductions and Social Security limits; pre-2018 personal exemptions use income phaseout. `data/processed/state_income_tax_brackets_2015_2024.csv` is generated by `etl/build_mlb_historical_taxes.py` from the saved Tax Foundation 2015–2024 workbook, with government corrections for selected later rate changes. Archived California schedules for every 2015–2024 year are transcribed in `data/curated/mlb_historical_ca_brackets.json`; CA mental-health surtax remains separate. Massachusetts surtax starts in 2023 with the appropriate annual threshold. Ohio 2020–2024 base-amount formulas are separate from marginal slices. The builder regenerates the data from tracked source assets, with no runtime spreadsheet/PDF dependency.

**Historical estimates remain provisional.** Some annual state-compilation inflation thresholds may reflect the previous year as footnoted by the source; deductions, recapture, AMT and jurisdiction-specific credits remain simplified. **Local taxes before 2025 are not modeled** and display “Not modeled”; those annual totals contain federal, employee payroll and state components only. The application does not apply 2025/2026 local rates backward. Sources and these omissions are visible in the interface. Earlier camp/attendance dates are estimated, even when game dates and venues are known.

### NFL contract-start-through-2026 view

NFL pages now include an expandable **Contract start through 2026 · year-specific taxes** view for every profile in the saved 2025 active/inactive roster directory. The existing full-contract forecast, frozen 2025 rules, future opponent scenarios, ranges and totals remain unchanged. `/api/contract-projection` adds a separate `history` object; it does not merge historical-rule results into forecast totals.

The supplemental view begins in the reported signing year (currently 2020–2025) and stops at the earlier of the reported cash-window end or 2026. It uses the existing published game venues, each year's federal/payroll/state inputs, 2025 weekly roster calendars and otherwise estimated team duty calendars. Only years with usable cash and resolved team/schedule coverage enter both subtotal sides. Missing/ambiguous years remain visible as unavailable. Residence changes update the base/comparison subtotals and selected-state annual breakdown. Allen's supplemental 2025–2026 reported cash is $113M; his original $330M 2025–2030 forecast remains intact.

These are estimated historical-rule results, not actual tax returns. Signing-year windows can differ from legal extension effective dates. Historical practice states and first-window January affiliations are assumptions. Before 2025, selected local taxes are **not modeled**, rather than filled using later rates. State table/credit simplifications remain provisional. 2026 scheduled attendance and cash remain estimates. Supplemental and full-contract windows overlap and must not be added together.

### MLB future annual salary scenarios

MLB profiles now also show **Future salary projections**, separate from the existing historical cash estimates. `/api/mlb/projection?player=<id>&residence=<state>&filing=single` calculates reported future base salaries from the selected current FanGraphs RosterResource contract for every active profile with available terms. Profiles without future contract years or reported salaries show explicit coverage messages; no contract or salary is invented for arbitration/free-agent placeholders.

Odd future years repeat the current club's **2025** estimated duty-day distribution; even years repeat **2026**. Spring training and regular season are retained, while reference postseason games are excluded. State/local shares, foreign-location days and modeled travel/off days are reused without claiming future dates or special-event venues are announced. All federal, employee payroll, state and supported local calculations use fixed **2026** rules, including nominal thresholds and limits. Each salary is run through the tax engine, rather than multiplying by one effective rate. Selected residence and filing assumptions apply to every included future year.

Deferred-payment timing is deliberately set aside for this scenario: Ohtani uses the reported **$70M nominal annual base salary** for 2027–2033, with no later installment added. Historical Ohtani cash remains $2M per playing year in the separate historical panel. The two panels are not combined into an entire-contract total because their income/timing bases differ. Future signing-bonus proration, CBT/AAV, buyouts and incentives are not added to base salary. Judge has $200M of future base salary for 2027–2031. Included option/vesting/opt-out years explicitly assume continuation and are not guaranteed; Soto's 2030–2039 path is conditional. Unknown annual amounts and estimates/placeholders are excluded from both salary and tax totals.

The model continues to assume the player stays with the saved current team. Unknown future schedule changes, stadium moves, international designations, postseason participation, transactions and actual individual attendance are not predicted. Canadian-resident base estimates remain unavailable; U.S. comparisons exclude Canadian and other foreign taxes/credits. All state sourcing and credits remain provisional under the existing research engine. NFL projections are unchanged.

### MLB contract-wide comparison layout

The MLB main comparison now matches the NFL layout: contract-wide modeled income, estimated take-home and estimated U.S. taxes, then Open/Close Contract Information and annual breakdowns. Historical reported-cash estimates remain available in an expandable section. The former Work pattern / contract status column is removed; conditional years have an asterisk and an explanation below the summary.

The UI requests `/api/mlb/projection?...&scope=full`; the existing default future-only API remains available. Full scope uses reported nominal annual base salaries across the selected contract and adds separately verified signing cash from reviewed contracts in its reported year (no prorated bonus is inferred). Historical years use their existing published-calendar coverage and matching tax-year rules; future years retain the repeating two-year patterns and fixed 2026 rules. Deferred-payment timing is set aside consistently throughout the main scenario. Judge's modeled window totals $360M; Ohtani's $700M; Soto's $765M including $75M signing cash. Missing historical allocation inputs or salaries are excluded and labeled, with headline value shown separately. Unsupported historical local taxes remain excluded. Other unverified compensation is not filled from headline value.

### Same-league player comparison

`/compare` supports NFL and MLB player search, similar-deal suggestions, and side-by-side contract/tax estimates. Home navigation and player profiles link to it; profile links preselect that player. A shareable URL retains league and selected IDs. Each player uses its fixed saved team-location residence with single filing and the existing model defaults; actual residence/citizenship is unverified.

Suggestions exclude the selected player and require reported positive headline value and length. They rank the mean of two symmetric proportional gaps: `abs(valueA-valueB)/max(valueA,valueB)` and `abs(yearsA-yearsB)/max(yearsA,yearsB)`, with equal weights. Ties sort by name/ID. Tax outcomes do not influence recommendations, and an exact headline match is not required. Manual search allows any other player in that league.

The table separates headline value from modeled income and reports estimated take-home, U.S. tax, take-home percentage of modeled income, average annual take-home over included years, and included-year coverage. Partial windows, excluded years and conditional amounts remain visible. NFL retains its frozen-2025 whole-contract forecast; MLB uses its full nominal salary/verified-signing scenario with historical rules and frozen-2026 future rules. Canadian team-residence estimates remain unavailable rather than zero. The tool is descriptive: different dates, salaries, lengths and schedules prevent treating player-to-player differences as a pure tax-location effect.

APIs: `/api/compare/directory?league=MLB`, `/api/compare/suggestions?league=MLB&player=592450`, and `/api/compare?league=MLB&left=592450&right=660271`. Invalid leagues, mixed-league IDs and duplicate selections are rejected. No residence override is accepted by the comparison model.

Player comparison presentation uses aligned left/right athlete cards with team accent colors, take-home emphasis and percentage bars. MLB headshots load from MLB's public image CDN; MLB team logos load from MLB's team-logo CDN, and NFL logos from ESPN's public team-logo CDN. Failed photos are removed; failed logos leave a team abbreviation. Coverage/model notes remain expandable below the financial rows. These images are external assets and can change or be unavailable; calculations do not depend on them. NFL headshots are not inferred from names or GSIS IDs.

### Contract coverage safeguards (November 12, 2026)

All main comparison/profile totals distinguish **headline-reconciled estimates**, **partial-contract estimates**, and unavailable results. A complete MLB salary scenario now requires every modeled year, dollar reconciliation to the reported headline within $1, and no known unallocated signing bonus. NFL gains separate `coverage_complete`, `headline_gap` and `coverage_issues` fields for display; its existing future cash, tax calculations, scenarios and ranges are unchanged. NFL's legacy `complete` field continues to describe annual-cash coverage only. The UI and player comparison use the stricter dollar-and-year coverage status.

`etl/mlb_contract_terms.py` centralizes contract selection and boundaries for the catalog, historical window and salary projection. It prioritizes the source's explicit headline playing-year range, falling back to reported start plus term, then the end field. This includes in-deal player options such as Bichette's 2028 salary without automatically adding extra club/vesting years outside the quoted headline contract. Missing terms are not filled from AAV or headline value.

`data/curated/mlb_signing_bonus_payments.json` records contract-matched, sourced payment-year additions. Bichette's 2026 $40M signing bonus is supported by AP's January contract report; the Mets' release confirms the three-year window and MLB's October report confirms exercise of the 2027 option. His modeled annual income is $42M each for 2026–2028 ($2M salary plus $40M signing cash in 2026), totaling $126M, with only 2028 still conditional under these sources. The bonus remains service wages under the existing model; its legal sourcing is not independently determined. Reviewed payments are matched to contract identity/window/value so a replaced contract cannot donate its bonus. Prorated bonuses and balancing amounts are never substituted for payment-year information.

Known signing bonuses without verified payment years stay explicitly unallocated; neither they nor other missing compensation are silently invented. Any headline/model difference is prominently identified as **not taxes**, and take-home percentages/averages are labeled as using included income/years. The raw source snapshot is preserved. Run `.venv/bin/python -m etl.audit_contract_coverage` to regenerate `data/processed/contract_coverage_audit.json`, covering all 2,257 NFL and 1,097 MLB profiles. The audit records income/window gaps rather than certifying tax liability or legal guarantees.

### Interactive horizontal tax breakdown

Every NFL and MLB player tax page includes a shared horizontal stacked breakdown immediately below the residence comparison. Each bar represents 100% of **included modeled income**, not headline value, with take-home, federal, employee payroll, state-after-credits and supported local segments. A different residence adds a second aligned bar; changing the state replaces it. Both bars cover the whole included contract window, not one annual salary.

Hover, focus or tap a segment/legend category for dollars, percentage and a short explanation. Legend controls expose zero or very small categories without widening their plotted shares. Keyboard users can navigate with Tab and activate controls with Enter/Space. Partial-contract labels and omitted pre-2025 local-tax disclosures remain visible; unavailable residence/income results never draw a zero-tax bar. The shared frontend checks that annual components reconcile to modeled income before drawing. No model calculations or future assumptions change. Run `node --test tests/test_tax_breakdown.js` for chart-data safeguards.
