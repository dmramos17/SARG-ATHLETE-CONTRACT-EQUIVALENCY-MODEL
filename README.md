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
interface with a Python standard-library server. It defaults to **2025** cash
snapshots for Christian Gonzalez, Devon Witherspoon and Patrick Surtain II.
Reported annual cash is $2,122,988, $3,646,468 and $22,170,000 respectively,
from OverTheCap season history. These are reported season cash totals, not verified
calendar-year W-2 wages. Payment timing, incentives and postseason earnings need
player-level records. Prior signing/option bonus cap proration is excluded from cash.
The original 2026 snapshots remain available in the repository for earlier analysis.

### Estimated duty-day calendar

`etl/estimated_duty_days.py` constructs a unique date-by-date **calendar-year 2025**
team service estimate. It includes January 2025 games from the 2024 season,
2025 preseason, documented out-of-state joint practices, and the period from
training camp through December 31. January 2026 is excluded. Default counts are
144 days for NE, 144 for SEA and 150 for DEN. These are model outputs, not actual
player duty-day totals or confidence intervals.

- Actual game dates and venue jurisdictions come from the saved NFL schedule
  subset in `data/curated/nfl_games_calendar_2025.json`, with source URLs.
  Regular/postseason dates come from the public nflverse dataset; preseason dates
  come from team publications. The Denver–Jets London venue is explicitly corrected
  rather than assigning it to New Jersey.
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

The calendar preloads local wage bases only for documented city game venues;
it does not assume hotels are in the stadium city. 2025 local rates are loaded for
Philadelphia (3.44% visitor Jan–Jun, 3.43% Jul–Dec), Cincinnati (1.8%), Kansas City
(1%) and Maryland special nonresident tax (2.25%). Service cash is assumed paid
July–December until timing is edited. City credits/exemptions, Pittsburgh's
2025 litigation-dependent treatment, Indiana county taxes and other unsupported
local jurisdictions are omitted, not treated as verified exemptions. An unsupported
local rate produces an error when selected. The omissions can move estimated tax
in either direction. Local rates and athlete-specific taxable bases remain provisional.

`etl/historical_taxes.py` installs the saved 2025 inputs when the server starts.
`etl/contract_data.py` syncs reviewed cash snapshots into SQLite. No live scraper
or paid data subscription is required to run the saved demonstration.

```sh
python3 -m unittest discover -s tests
```
