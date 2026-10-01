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