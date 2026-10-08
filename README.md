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

From the repository root, run:

```sh
python3 dashboard/server.py
```

Open http://127.0.0.1:8765 in your browser. Stop the server with Ctrl+C.
The dashboard uses Python's standard library, `etl/duty_days.py`, and
`etl/annual_taxes.py`; it needs no frontend packages. If the database is missing, generate it
with `python3 src/athlete_tax/clean_tax_data.py` (requires pandas).

Choose an existing player contract to load sourced, read-only compensation and
its tax estimate automatically. Expand **Adjust assumptions** to change residence,
filing status, bonus treatment, duty days, or local taxes, then update the estimate. The calculation
panel shows income allocation, and the sources panel exposes database verification
labels. Supported states: MA, TX, FL, NY, NJ, CA, PA, MI, OH, MO, MD.

This is a **2026 annual-tax research preview**. Federal tax applies progressive
brackets after the federal standard deduction. Employee payroll includes Social
Security (6.2% up to $184,500), Medicare (1.45% of all wages), and Additional
Medicare (0.9% above $200,000 single / $250,000 joint). Salary and cash signing
bonuses are assumed wage income, with no other income, spouse income, pre-tax
contributions, federal credits, itemized deductions, or AMT. Employer taxes and
state payroll programs (such as California SDI) are excluded.

Under **Adjust assumptions**, select a full-year residence city to model NYC progressive tax or resident rates
in Philadelphia, Detroit, Cleveland, Cincinnati, Columbus, Kansas City, or
St. Louis. For nonresident local work, enter taxable compensation by city and
payment half-year separately, including any taxable bonuses. NYC does not tax
nonresident wages. Maryland's special nonresident tax is available separately;
Maryland residents' county taxes and Pittsburgh are not modeled. Philadelphia
rates change July 1: Jan–Jun uses 3.74% resident / 3.43% nonresident, Jul–Dec uses
3.735% / 3.425%. Cash paid before July 1 controls the resident calculation.
Local tax bases are user assumptions; state bonus sourcing does not establish
city bonus sourcing. City credits, exemptions, refunds, and state credits for
city taxes are excluded and can cause overestimates. Blank local inputs mean
no modeled local tax, not a finding that the athlete owes none.

State nonresident rates and resident credits retain the existing simplified
methods; state deductions and NY high-income benefit recapture are excluded.
Preset cash and travel inputs are assumptions, not verified contract or schedule data.
Qualifying-bonus mode assumes no refundable portion in California. The server
binds to localhost for a local demonstration; it is not a production deployment.

Federal/payroll sources: [IRS 2026 brackets](https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill),
[SSA wage base](https://www.ssa.gov/oact/cola/cbb.html),
[IRS payroll rates](https://www.irs.gov/taxtopics/tc751), and
[Additional Medicare](https://www.irs.gov/taxtopics/tc560).
NYC brackets and standard deductions: [2026 NY estimated-tax instructions](https://www.tax.ny.gov/pdf/current_forms/it/it2105i.pdf).
Local rates otherwise come from the existing database with their verification
labels; Philadelphia's rates were checked against its official
[Wage Tax page](https://www.phila.gov/services/business-self-employment/business-taxes/wage-tax-employers/).

## Sourced player contract examples

The dashboard's **Player** selector includes 2026 cash snapshots
for Christian Gonzalez, Devon Witherspoon, and Patrick Surtain II. Choose a player to load the estimate automatically. The compensation summary
shows base salary, cash signing bonus,
and other cash compensation; cap charges and bonus proration are shown only as
context and do not enter the tax base. Other cash follows duty-day sourcing as a
prototype assumption; Surtain's option/other-bonus classification needs review.

Loading resets the hypothetical scenario to 164 home-state duty days and assumes
residence in that state. This is not a player's actual residence or travel
schedule. Local tax inputs and payment timing reset to zero; review those inputs
before interpreting the calculation. Filing status remains the user's selection.

The reviewed source file is `data/curated/demo_contracts_2026.json`, dated
October 7, 2026. Each record retains source URLs, scope, discrepancy notes, and
verification status. OverTheCap supplies the component breakdowns. Spotrac
team pages report slightly different cash/cap totals for Gonzalez and Surtain;
both observations are retained, with OTC cash used for the default inputs.
Witherspoon's annual cash lacks a second detailed source; the Seahawks link
corroborates the extension announcement only. No record is labeled fully verified.

On server startup, `etl/contract_data.py` saves these records into SQLite's
`research_contract_snapshots` table. To refresh those rows after editing the
curated file, run `python3 -m etl.contract_data`. The selector reads the curated
file, so it remains reproducible after rebuilding the generated database.
These are reviewed snapshots, not an automatic web scraper or a live API feed.
