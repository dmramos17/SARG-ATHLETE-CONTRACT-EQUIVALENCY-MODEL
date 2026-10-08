"""2026 employee federal/payroll and selected local tax estimates.

Federal assumes wage-only income, standard deduction, no dependents/credits,
spouse income or AMT. Local wage bases are supplied by the scenario, not inferred
from state signing-bonus rules. City credits/exemptions are not modeled.
"""
from etl.duty_days import bracket_tax

FEDERAL_SOURCE = "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
PAYROLL_SOURCES = ["https://www.irs.gov/taxtopics/tc751",
                   "https://www.ssa.gov/oact/cola/cbb.html",
                   "https://www.irs.gov/taxtopics/tc560"]
NYC_SOURCE = "https://www.tax.ny.gov/pdf/current_forms/it/it2105i.pdf"


def federal_payroll(tables, wages):
    filing = tables.con.execute(
        "SELECT standard_deduction, addl_medicare_threshold FROM federal_filing_params "
        "WHERE tax_year=? AND filing_status=?", (tables.year, tables.fs)).fetchone()
    params = tables.con.execute(
        "SELECT ss_rate, ss_wage_base, medicare_rate, addl_medicare_rate FROM federal_payroll_params "
        "WHERE tax_year=?", (tables.year,)).fetchone()
    brackets = tables.con.execute(
        "SELECT lower_bound, rate FROM federal_brackets WHERE tax_year=? AND filing_status=? "
        "ORDER BY bracket_order", (tables.year, tables.fs)).fetchall()
    if not filing or not params or not brackets:
        raise ValueError("Federal tax data is missing for this year or filing status.")
    deduction, threshold = filing
    ss_rate, ss_base, medicare_rate, additional_rate = params
    taxable = max(0, wages - deduction)
    slices = []
    for index, (low, rate) in enumerate(brackets):
        upper = brackets[index + 1][0] if index + 1 < len(brackets) else taxable
        amount = max(0, min(taxable, upper) - low)
        if amount:
            slices.append(dict(lower=low, upper=upper, rate=rate, taxable=amount, tax=amount * rate))
    payroll = dict(social_security=min(wages, ss_base) * ss_rate,
                   medicare=wages * medicare_rate,
                   additional_medicare=max(0, wages - threshold) * additional_rate)
    payroll["total"] = sum(payroll.values())
    return dict(federal=bracket_tax(brackets, taxable), deduction=deduction,
                taxable_income=taxable, brackets=slices, payroll=payroll,
                social_security_base=ss_base, additional_medicare_threshold=threshold)


def local_rates(tables, locality, date):
    row = tables.con.execute(
        "SELECT resident_rate, nonresident_rate, taxes_nonresident_work, legal_status, "
        "verification_status, source FROM local_income_tax_rates WHERE locality_id=? "
        "AND effective_date<=? ORDER BY effective_date DESC LIMIT 1", (locality, date)).fetchone()
    if not row or row[3] != "in_force":
        raise ValueError("This locality does not have an active supported tax rate.")
    return row


def estimate_local(tables, resident_city, gross, early_cash, work):
    """work = {locality: {early: taxable wages, late: taxable wages}}.

    Early/late are amounts paid before/on-or-after July 1, respectively.
    Taxable work amounts are entered separately: bonus rules are city-specific.
    Resident-city work is skipped to prevent resident/nonresident double taxation.
    """
    rows, sources = [], []
    if resident_city:
        if resident_city == "NYC":
            bounds = [0, 12_000, 25_000, 50_000] if tables.fs == "single" else [0, 21_600, 45_000, 90_000]
            deduction = 8_000 if tables.fs == "single" else 16_050
            base = max(0, gross - deduction)
            tax = bracket_tax(list(zip(bounds, [.03078, .03762, .03819, .03876])), base)
            rows.append(dict(locality="NYC", kind="resident", period="Full year", base=base,
                             rate=None, tax=tax, deduction=deduction))
            sources.append(dict(state="NYC", status="verified", source=NYC_SOURCE))
        else:
            for period, base, date in [("Jan–Jun", early_cash, "2026-06-30"),
                                       ("Jul–Dec", gross - early_cash, "2026-12-31")]:
                resident, _, _, _, status, source = local_rates(tables, resident_city, date)
                if resident is None:
                    raise ValueError("Resident tax is not supported for this locality.")
                rows.append(dict(locality=resident_city, kind="resident", period=period,
                                 base=base, rate=resident, tax=base * resident))
                sources.append(dict(state=resident_city, status=status, source=source))
    for city, amounts in work.items():
        if city == resident_city:
            continue
        for key, period, date in [("early", "Jan–Jun", "2026-06-30"),
                                  ("late", "Jul–Dec", "2026-12-31")]:
            base = amounts[key]
            if not base:
                continue
            _, rate, taxes_work, _, status, source = local_rates(tables, city, date)
            rate = rate if taxes_work and rate is not None else 0
            rows.append(dict(locality=city, kind="nonresident", period=period,
                             base=base, rate=rate, tax=base * rate))
            sources.append(dict(state=city, status=status, source=source))
    return dict(total=sum(row["tax"] for row in rows), rows=rows,
                sources=[dict(values) for values in dict.fromkeys(tuple(row.items()) for row in sources)])
