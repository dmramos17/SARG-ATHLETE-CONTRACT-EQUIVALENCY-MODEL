"""Install year-specific research tax inputs for MLB's historical window."""
from functools import lru_cache
from pathlib import Path
import csv,json,sqlite3
ROOT=Path(__file__).resolve().parents[1]
OHIO_SOURCE='https://tax.ohio.gov/individual/file-now/annual-tax-rates'
OHIO_FORMULAS={
 2020:[(0,0,0),(22150,316.18,.0285),(44250,946.03,.03326),(88450,2416.12,.03802),(110650,3260.16,.04413),(221300,8143.14,.04797)],
 2021:[(0,0,0),(25000,346.16,.02765),(44250,878.42,.03226),(88450,2304.31,.03688),(110650,3123.05,.0399)],
 2022:[(0,0,0),(26050,360.69,.02765),(46100,915.07,.03226),(92150,2400.64,.03688),(115300,3254.41,.0399)],
 2023:[(0,0,0),(26050,360.69,.0275),(100000,2394.32,.03688),(115300,2958.58,.0375)],
 2024:[(0,0,0),(26050,360.69,.0275),(100000,2394.32,.035)]}

def ohio_tax(year,income):
    rows=OHIO_FORMULAS.get(year)
    if not rows:return None
    low,base,rate=next((r for r in reversed(rows) if income>r[0]),rows[0])
    return base+max(0,income-low)*rate

@lru_cache(maxsize=1)
def federal_history():
    return json.loads((ROOT/'data/curated/mlb_historical_federal.json').read_text())

def sync_mlb_history(db=ROOT/'athlete_tax.db'):
    with sqlite3.connect(db) as con:
        with (ROOT/'data/processed/state_income_tax_brackets_2015_2024.csv').open() as f:
            rows=list(csv.DictReader(f))
        con.executemany('INSERT OR REPLACE INTO state_income_tax_brackets VALUES (:tax_year,:state_code,:filing_status,:bracket_order,:lower_bound,:rate,:verification_status,:source)',rows)
        for text_year,p in federal_history().items():
            year=int(text_year)
            for filing,lows in p['brackets'].items():
                con.executemany('INSERT OR REPLACE INTO federal_brackets VALUES (?,?,?,?,?,?,?)',[(year,filing,i,low,rate,'provisional',p['source']) for i,(low,rate) in enumerate(zip(lows,p['rates']),1)])
                con.execute('INSERT OR REPLACE INTO federal_filing_params VALUES (?,?,?,?)',(year,filing,p['standard_deduction'][filing],200000 if filing=='single' else 250000))
            con.execute("INSERT OR REPLACE INTO federal_payroll_params VALUES (?,?,?,?,?,?,?)",(year,.062,p['ss_wage_base'],.0145,.009,0,'provisional'))
            con.execute("INSERT OR REPLACE INTO state_surtaxes VALUES (?,?,?,?,?,?,?,?,?,?,?)",(year,'CA','CA 1% Mental Health Services Tax',1000000,.01,0,1,0,'provisional',f'https://www.ftb.ca.gov/forms/{year}/','Simplified nonresident proration; state deductions and credits are not modeled'))
            if year in OHIO_FORMULAS:
                con.execute("DELETE FROM state_income_tax_brackets WHERE tax_year=? AND state_code='OH'",(year,))
                con.executemany('INSERT INTO state_income_tax_brackets VALUES (?,?,?,?,?,?,?,?)',[(year,'OH',filing,i,low,rate,'provisional',OHIO_SOURCE) for filing in ('single','mfj') for i,(low,base,rate) in enumerate(OHIO_FORMULAS[year],1)])
            if year>=2023:
                threshold=1000000 if year==2023 else 1053750
                con.execute("INSERT OR REPLACE INTO state_surtaxes VALUES (?,?,?,?,?,?,?,?,?,?,?)",(year,'MA','MA 4% millionaires surtax',threshold,.04,0,1,0,'provisional',f'https://www.mass.gov/doc/{year}-schedule-4-surtax/download','Surtax applies to sourced income; simplified taxable-income base'))

def personal_exemption(year,filing,wages):
    if year not in (2015,2016,2017):return 0
    import math
    amount=4000 if year==2015 else 4050
    threshold={2015:(258250,309900),2016:(259400,311300),2017:(261500,313800)}[year][filing=='mfj']
    reduction=min(1,.02*math.ceil(max(0,wages-threshold)/2500))
    return amount*(2 if filing=='mfj' else 1)*(1-reduction)
