"""Install the explicitly sourced 2025 demo inputs, never relabel 2026 rows."""
import csv
import sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FEDERAL_2025_SOURCE = 'https://www.irs.gov/instructions/i1040gi'

def sync_historical_taxes(db=ROOT / 'athlete_tax.db'):
    with sqlite3.connect(db) as con:
        with (ROOT/'data/processed/state_income_tax_brackets_2025.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        con.executemany('INSERT OR REPLACE INTO state_income_tax_brackets VALUES (:tax_year,:state_code,:filing_status,:bracket_order,:lower_bound,:rate,:verification_status,:source)',rows)
        con.executemany('INSERT OR REPLACE INTO federal_filing_params VALUES (?,?,?,?)',[(2025,'single',15750,200000),(2025,'mfj',31500,250000)])
        con.execute("INSERT OR REPLACE INTO federal_payroll_params VALUES (2025,.062,176100,.0145,.009,10000,'needs_check')")
        con.execute("INSERT OR REPLACE INTO state_surtaxes VALUES (2025,'CA','CA 1% Mental Health Services Tax',1000000,.01,0,1,0,'provisional','https://www.ftb.ca.gov/forms/2025/2025-540-booklet.html','Fixed threshold; simplified nonresident proration')")
        # MA visitor surtax depends on MA-sourced income, not worldwide wages.
        con.execute("DELETE FROM state_income_tax_brackets WHERE tax_year=2025 AND state_code='MA' AND bracket_order>1")
        con.execute("INSERT OR REPLACE INTO state_surtaxes VALUES (2025,'MA','MA 4% millionaires surtax',1083150,.04,0,1,0,'provisional','https://www.mass.gov/doc/2025-schedule-4-surtax/download','Surtax on sourced income; simplified taxable-income base')")
        # Explicit historical local rows. Other localities fail closed in 2025.
        local=[('PHL','2025-01-01',.0375,.0344,'https://employee.phila.gov/wp-content/uploads/2026/01/One-Philly-How-to-Navigate-Your-2025-W-2_January-2026_Final-1.pdf'),('PHL','2025-07-01',.0374,.0343,'https://www.phila.gov/2025-06-18-philly-extends-deadline-for-relief-program-announces-tax-cuts/'),('CIN','2025-01-01',.018,.018,'https://www.cincinnati-oh.gov/finance/income-taxes/athletes-entertainers/'),('KCM','2025-01-01',.01,.01,'https://www.kcmo.gov/city-hall/departments/finance/tax-home/tax-forms'),('MDNR','2025-01-01',None,.0225,'https://www.marylandtaxes.gov/forms/25-forms/Withholding-Guide.pdf')]
        for city,date,res,non,source in local:
            con.execute("INSERT OR REPLACE INTO local_income_tax_rates (locality_id,effective_date,resident_rate,nonresident_rate,taxes_nonresident_work,apportionment_method,tax_base,legal_status,verification_status,source,notes) VALUES (?,?,?,?,1,'duty_day','wage','in_force','provisional',?,'2025 rate; modeled taxable wage base and athlete apportionment require review')",(city,date,res,non,source))
