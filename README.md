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

### MLB interface skeleton

The **MLB** navigation link opens `/mlb`. It includes a baseball-themed landing page, searchable sample cards and player previews at `/mlb/players/<MLB-ID>`. The three sample identities are Shohei Ohtani (660271), Aaron Judge (592450) and Juan Soto (665742), with 2025 team affiliations and links to official MLB profiles. This is not an imported active roster; the three profiles now have separately sourced Spotrac financial snapshots.

The player preview has a fixed Base State, a selectable comparison state from US MLB markets, a side-by-side placeholder table, and expandable **Open Contract Information** details. Tax results still say **Coming soon**. Reported cash now appears from Spotrac snapshots; there are no invented dollar amounts, deferred-income tax calculations, NFL schedule assumptions or requests to the NFL tax API. Toronto is represented in the seed team list without a US state; Canadian work/residence requires separate treatment before calculations are added.

`data/curated/mlb_interface_seed.json` contains the 30-team reference list and three sample profiles; `etl/mlb_interface.py` decorates the catalog for `/api/mlb/directory`. The front end is `dashboard/mlb.html`, `dashboard/mlb.js` and `dashboard/mlb.css`. The next stages are verified annual cash schedules (including deferrals), baseball schedules and spring-training duty-day allocation, followed by tax-rule validation.

### Spotrac MLB contract snapshots

The three MLB profiles now expose reported current-contract terms and annual cash from public Spotrac pages. `data/curated/mlb_contracts_spotrac.json` stores the checked snapshots and direct source URLs; no Premium history, live scraper or subscription is used. MLB tax and duty-day calculations remain unimplemented.

Ohtani's nominal $700M is separated into $2M annual playing-year cash in 2024–2033 and $68M deferred installments in 2034–2043. Judge's $360M schedule covers nine $40M years, 2023–2031. Soto's $765M base/signing schedule is distinguished from Spotrac's $765.5M cash total, which includes $500K of listed likely incentives in 2025/2026. His opt-out after 2029 and possible club increase are identified; the increased contract path is not selected automatically. N/A signing bonuses and unlisted deferred schedules are not presented as independently verified zero-dollar terms.

Player pages show the snapshots inside **Open Contract Information**, including annual cash tables, reported guarantees, deferrals, conditional terms, source links and check dates. The state comparison can display reported gross cash, but estimated take-home and personal taxes remain unavailable pending the MLB model. Financial tests verify that deferred dollars are not counted twice and listed incentives are not conflated with guaranteed base/signing cash.
