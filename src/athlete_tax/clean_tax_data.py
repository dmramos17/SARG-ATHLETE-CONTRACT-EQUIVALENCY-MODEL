#!/usr/bin/env python3
"""
clean_tax_data.py  --  raw Tax Foundation / jock-tax CSVs  ->  tidy CSVs  ->  SQLite

Run from the repo root:   python db/clean_tax_data.py
Options:                  --root PATH   repo root (default: auto-detected, the folder that contains db/schema.sql)
                          --no-db       write the tidy CSVs but do not build athlete_tax.db

Week 4 changes (see Code Status Report):
  * root auto-detection (the old default, parents[2], pointed one folder ABOVE the repo)
  * nonresident_rate_method = 'proration' (effective-rate) for every taxing state, per Tax Foundation 2026
  * jock-tax rules, local taxes, teams and league duty-day rules now load from data/curated/*.csv
    (hand-researched, every row sourced). The legacy state_jock_taxes.csv / city_jock_taxes.csv had
    wrong methods (IL, PA "games played"), a struck-down Pittsburgh fee, Detroit's resident rate for
    visitors, and no Cincinnati or Maryland rows, so they are no longer read.
  * Georgia standard deduction updated for HB 463
  * new checks: Tax Foundation's California effective-rate example ($574), MA visitor below surtax line
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

TAX_YEAR = 2026
TF_SOURCE = "Tax Foundation, State Individual Income Tax Rates and Brackets 2026 (as of 2026-01-01)"

GA_RAW_RATE, GA_NEW_RATE = 0.0519, 0.0499

SURTAXES = [
    dict(state_code="MA", surtax_name="MA 4% millionaires surtax", raw_threshold=1_083_150,
         threshold=1_107_750, rate=0.04, threshold_doubled_for_mfj=0, applies_to_nonresidents=1,
         withheld_by_employer=0, verification_status="verified",
         source="Mass. DOR 2026 Form 1-ES/2-ES instructions",
         notes="Marginal, not a cliff. Not doubled for joint filers. Nonresidents owe it only on "
               "MA-sourced income above the threshold. Employer withholds only the flat 5%; surtax "
               "is settled on the individual return."),
    dict(state_code="CA", surtax_name="CA 1% Mental Health Services Tax", raw_threshold=1_000_000,
         threshold=1_000_000, rate=0.01, threshold_doubled_for_mfj=0, applies_to_nonresidents=1,
         withheld_by_employer=0, verification_status="needs_check",
         source="Tax Foundation 2026; Week 3 memo",
         notes="Threshold not doubled or indexed. applies_to_nonresidents and withheld_by_employer "
               "are defaults, not confirmed. 1.3% SDI payroll tax not modeled."),
]

STALE_2025_STATES = {"AR", "CA", "ND", "VT"}
STATE_ROW_STATUS = {"GA": "verified"}
# Week 4: Tax Foundation (Walczak, 2026-09-09) reports that every state uses the effective-rate
# (proration) method for athletes. CA/NY/NJ were confirmed in Week 3; the rest are 'needs_check'.
PRORATION_CONFIRMED = {"CA", "NY", "NJ"}
ATHLETE_DUTY_DAY_RULE_STATES = {"AZ", "CO", "CT", "IA", "IL", "IN", "LA", "MA", "MD", "ME", "MI",
                                "MO", "NC", "NJ", "NY", "OR", "PA", "RI", "UT", "VA", "WI"}
STATE_NOTES = {
    "GA": "Rate 4.99% per HB 463 (signed 2026-05-11, retroactive to 1/1/2026); TF table shows 5.19%.",
    "MA": "5% flat + 4% surtax over $1,107,750 (see state_surtaxes).",
    "CA": "Top bracket 12.3% + 1% MHST (state_surtaxes). SDI not modeled.",
    "NY": "Benefit recapture NOT modeled: engine output is a lower bound for very high earners.",
    "IL": "Duty days in statute; 3-part signing-bonus test; no retaliatory clause in current text.",
    "PA": "General working-days rule (61 Pa. Code 109.8); not games played.",
    "SC": "Top rate temporarily 6% through 2026-06-30, scheduled to revert to 6.2%. Verify.",
    "MD": "Visitors also owe a special nonresident tax in lieu of county tax (not in brackets).",
    "WA": "No wage income tax; capital gains only (7%/9%). Capital-gains rates intentionally not loaded.",
    "DC": "DC cannot tax nonresidents' wages.",
}

FEDERAL_FILING_PARAMS = [
    (2026, "single", 16_100, 200_000),
    (2026, "mfj", 32_200, 250_000),
]
FEDERAL_PAYROLL_PARAMS = [dict(tax_year=2026, ss_rate=0.062, ss_wage_base=184_500, medicare_rate=0.0145,
                               addl_medicare_rate=0.009, salt_cap_effective=10_000, salt_status="needs_check")]

LOCALITIES = {
    "New York City": ("NYC", "NY"), "Philadelphia": ("PHL", "PA"), "Cleveland": ("CLE", "OH"),
    "Columbus": ("COL", "OH"), "Pittsburgh": ("PIT", "PA"), "Detroit": ("DET", "MI"),
    "Kansas City": ("KCM", "MO"), "St. Louis": ("STL", "MO"),
}

STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Washington DC": "DC", "DC": "DC", "D.C.": "DC",
}
STATE_NAMES = {c: n for n, c in STATE_CODES.items() if n not in ("DC", "D.C.")}
STATE_NAMES["DC"] = "District of Columbia"

PATTERNS = {
    "fed_2026": r"^2026taxbracketsandfederalincometaxrates",
    "fed_2025": r"^2025taxbracketsandfederalincometaxrates",
    "fed_2024": r"^2024taxbrackets.*federaltaxbrackets",
    "state_main": r"^2026stateincometaxratesandbrackets.*foundation$",
    "state_class": r"^2026stateincometaxratesandbrackets.*foundation1$",
    "sales": r"^2026salestaxrates",
    "city_jock": r"^cityjocktaxes",
    "state_jock": r"^statejocktaxes",
}


def find_raw(root: Path, key: str, required: bool = True):
    hits = []
    for folder in (root / "data", root / "data" / "raw"):
        if folder.is_dir():
            hits += [p for p in sorted(folder.glob("*.csv"))
                     if re.search(PATTERNS[key], re.sub(r"[^a-z0-9]", "", p.stem.lower()))]
    if not hits:
        if required:
            sys.exit(f"ERROR: no raw file for '{key}' (pattern /{PATTERNS[key]}/) in data/ or data/raw/")
        print(f"  skipped '{key}': file not found")
        return None
    if len(hits) > 1:
        print(f"  WARNING: {len(hits)} files match '{key}', using {hits[0].name}")
    return hits[0]


def clean_name(s: str) -> str:
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"^\s*-\s*", "", s)
    return s.replace("*", "").strip()


def is_pct(x) -> bool:
    return isinstance(x, str) and x.strip().endswith("%") and re.match(r"^[\d.]+%$", x.strip()) is not None


def pct(x) -> float:
    return round(float(str(x).strip().rstrip("%")) / 100, 6)


def money(x):
    m = re.search(r"\$?([\d,]+(?:\.\d+)?)", str(x))
    return float(m.group(1).replace(",", "")) if m else None


def is_money(x) -> bool:
    return isinstance(x, str) and re.match(r"^\$[\d,]+(\.\d+)?$", x.strip()) is not None


def bracket_tax(rows, income: float) -> float:
    total = 0.0
    for i, (low, rate) in enumerate(rows):
        upper = rows[i + 1][0] if i + 1 < len(rows) else float("inf")
        if income > low:
            total += (min(income, upper) - low) * rate
    return total


def clean_federal(path: Path, tax_year: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = ["rate", "single", "mfj", "hoh"]
    rows = []
    for fs in ("single", "mfj", "hoh"):
        prev_upper = 0.0
        for i, (r, rng) in enumerate(zip(df["rate"], df[fs]), start=1):
            nums = [float(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", str(rng).replace("\xa0", " "))]
            lower = 0.0 if i == 1 else prev_upper
            if i > 1 and nums[0] not in (prev_upper, prev_upper + 1):
                sys.exit(f"ERROR: federal {tax_year} {fs}: bracket {i} starts at {nums[0]}, "
                         f"expected {prev_upper} or {prev_upper + 1}")
            prev_upper = nums[1] if len(nums) > 1 else None
            rows.append(dict(tax_year=tax_year, filing_status=fs, bracket_order=i, lower_bound=lower,
                             rate=pct(r), verification_status="needs_check",
                             source=f"Tax Foundation {tax_year} federal brackets"))
    out = pd.DataFrame(rows)
    if tax_year == 2026:
        ok = True
        for fs, top, expected in (("single", 640_600, 192_979.25), ("mfj", 768_700, 206_583.50)):
            b = out[out.filing_status == fs].sort_values("bracket_order")
            got = bracket_tax(list(zip(b.lower_bound, b.rate)), top)
            ok &= abs(got - expected) < 0.01
        if ok:
            out.loc[out.filing_status.isin(["single", "mfj"]), "verification_status"] = "verified"
    return out


def parse_state_brackets(df: pd.DataFrame):
    d = df.iloc[:, [0, 1, 3, 4, 6]].copy()
    d.columns = ["raw", "s_rate", "s_low", "m_rate", "m_low"]
    out = {}
    for _, r in d.iterrows():
        name = clean_name(r["raw"])
        if name == "Washington":
            continue
        if name not in STATE_CODES:
            sys.exit(f"ERROR: unrecognised state name in raw file: {name!r}")
        code = STATE_CODES[name]
        for fs, rate, low in (("single", r["s_rate"], r["s_low"]), ("mfj", r["m_rate"], r["m_low"])):
            if is_pct(rate) and is_money(low):
                out.setdefault((code, fs), []).append((money(low), pct(rate)))
    for key, rows in out.items():
        rows.sort()
        if rows[0][0] > 0:
            rows.insert(0, (0.0, 0.0))
    return out


def apply_overrides(brackets: dict):
    for fs in ("single", "mfj"):
        rows = brackets[("GA", fs)]
        if len(rows) != 1 or abs(rows[0][1] - GA_RAW_RATE) > 1e-9:
            sys.exit(f"ERROR: Georgia raw data is no longer a single {GA_RAW_RATE:.2%} bracket "
                     f"({rows}). Review the GA override.")
        brackets[("GA", fs)] = [(rows[0][0], GA_NEW_RATE)]
    for s in SURTAXES:
        for fs in ("single", "mfj"):
            rows = brackets[(s["state_code"], fs)]
            if not any(abs(low - s["raw_threshold"]) < 1e-6 for low, _ in rows):
                sys.exit(f"ERROR: {s['state_code']} {fs}: no bracket at ${s['raw_threshold']:,}. "
                         "Tax Foundation may have updated its table; review SURTAXES.")
            new, changed = [], False
            for low, rate in rows:
                if low >= s["raw_threshold"]:
                    rate, changed = round(rate - s["rate"], 6), True
                if new and abs(new[-1][1] - rate) < 1e-9:
                    continue
                new.append((low, rate))
            if not changed:
                sys.exit(f"ERROR: {s['state_code']} {fs}: nothing at/above ${s['raw_threshold']:,} to strip.")
            brackets[(s["state_code"], fs)] = new
    for (code, fs), rows in brackets.items():
        rates = [r for _, r in rows]
        if rates != sorted(rates):
            sys.exit(f"ERROR: {code} {fs} rates are not non-decreasing: {rows}")
    return brackets


def build_state_tables(raw: pd.DataFrame, class_path):
    brackets = apply_overrides(parse_state_brackets(raw))
    rows = []
    for (code, fs), lst in sorted(brackets.items()):
        status = ("stale_2025" if code in STALE_2025_STATES else STATE_ROW_STATUS.get(code, "needs_check"))
        for i, (low, rate) in enumerate(lst, start=1):
            rows.append(dict(tax_year=TAX_YEAR, state_code=code, filing_status=fs, bracket_order=i,
                             lower_bound=low, rate=rate, verification_status=status,
                             source="HB 463 (Georgia Economic Growth and Tax Relief Act of 2026)"
                             if code == "GA" else TF_SOURCE))
    brk = pd.DataFrame(rows)

    derived = {}
    for code in STATE_NAMES:
        if code == "WA":
            derived[code] = "cap_gains_only"
        elif (code, "single") not in brackets:
            derived[code] = "none"
        else:
            pos = {r for _, r in brackets[(code, "single")] if r > 0}
            derived[code] = "flat" if len(pos) == 1 else "graduated"
    if class_path is not None:
        cls = pd.read_csv(class_path)
        for col, label in zip(cls.columns, ("none", "flat", "graduated")):
            for n in cls[col].dropna():
                n = clean_name(n)
                if not n:
                    continue
                code = STATE_CODES[n]
                want = "cap_gains_only" if code == "WA" else label
                if derived[code] != want:
                    print(f"  NOTE: {code}: derived '{derived[code]}' but TF classification says '{want}'")
    prof = []
    for code, name in sorted(STATE_NAMES.items(), key=lambda kv: kv[1]):
        taxes = derived[code] in ("flat", "graduated")
        prof.append(dict(
            state_code=code, state_name=name, income_tax_type=derived[code], taxes_wages=int(taxes),
            nonresident_rate_method="proration",
            nonresident_method_status=("verified" if (code in PRORATION_CONFIRMED or not taxes) else "needs_check"),
            has_athlete_duty_day_rule=int(code in ATHLETE_DUTY_DAY_RULE_STATES),
            notes=STATE_NOTES.get(code)))
    prof = pd.DataFrame(prof)

    sur = pd.DataFrame([{"tax_year": TAX_YEAR, **{k: v for k, v in s.items() if k != "raw_threshold"}}
                        for s in SURTAXES])

    def parse_amt(x):
        if pd.isna(x) or str(x).strip().lower().startswith("n.a"):
            return None, 0
        m = re.search(r"\$([\d,]+)", str(x))
        return (float(m.group(1).replace(",", "")), int("credit" in str(x).lower())) if m else (None, 0)

    ded = []
    for _, r in raw.iterrows():
        if str(r.iloc[0]).strip().startswith("-"):
            continue
        name = clean_name(r.iloc[0])
        if name == "Washington" or name not in STATE_CODES:
            continue
        for fs, sd, pe in (("single", r.iloc[7], r.iloc[9]), ("mfj", r.iloc[8], r.iloc[10])):
            (sd_v, sd_c), (pe_v, pe_c) = parse_amt(sd), parse_amt(pe)
            if sd_v is None and pe_v is None:
                continue
            ded.append(dict(tax_year=TAX_YEAR, state_code=STATE_CODES[name], filing_status=fs,
                            standard_deduction=sd_v, std_deduction_is_credit=sd_c,
                            personal_exemption=pe_v, exemption_is_credit=pe_c))
    ded = pd.DataFrame(ded)
    # Georgia HB 463 raised the single standard deduction from $12,000 to $15,000 for 2026.
    ded.loc[(ded.state_code == "GA") & (ded.filing_status == "single"), "standard_deduction"] = 15_000
    return brk, prof, sur, ded, brackets


def clean_sales(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path)
    return pd.DataFrame(dict(
        tax_year=TAX_YEAR, state_code=t["State"].map(lambda n: STATE_CODES[clean_name(n)]),
        state_rate=t["State Tax Rate"].map(pct), avg_local_rate=t["Average Local Tax Rate"].map(pct),
        max_local_rate=t["Max Local Rate"].map(pct), combined_rate=t["Combined Tax Rate"].map(pct)))


def load_curated(root: Path):
    """Week 4 hand-researched tables. Every row carries a source and a verification_status."""
    cur = root / "data" / "curated"
    need = ["local_tax_rates_2026.csv", "jock_tax_rules_2026.csv", "teams.csv", "league_duty_day_rules.csv"]
    missing = [f for f in need if not (cur / f).exists()]
    if missing:
        sys.exit(f"ERROR: missing curated files in data/curated/: {missing}")
    lt = pd.read_csv(cur / "local_tax_rates_2026.csv")
    loc = lt[["locality_id", "locality_name", "state_code"]].drop_duplicates("locality_id")
    rates = lt.drop(columns=["locality_name", "state_code"])
    jock = pd.read_csv(cur / "jock_tax_rules_2026.csv")
    teams = pd.read_csv(cur / "teams.csv")
    rules = pd.read_csv(cur / "league_duty_day_rules.csv")
    # sanity checks on hand-entered data
    bad = jock[jock.sourcing_method == "games_played"]
    if len(bad):
        sys.exit(f"ERROR: games_played found for {list(bad.state_code)}; no 2026 source supports it.")
    for col in ("stadium_state", "practice_state"):
        us = teams[teams.country == "US"]
        if us[col].isna().any():
            sys.exit(f"ERROR: US team missing {col}: {list(us[us[col].isna()].team_id)}")
    return loc, rates, jock, teams, rules


INT_COLS = {"has_athlete_duty_day_rule", "taxes_wages", "std_deduction_is_credit", "exemption_is_credit",
            "threshold_doubled_for_mfj", "applies_to_nonresidents", "withheld_by_employer",
            "taxes_nonresident_work", "employer_withholding_required", "composite_return_allowed",
            "retaliatory_provision", "bracket_order", "tax_year", "typical_total_duty_days"}
LOAD_ORDER = [
    ("state_tax_profile", "state_tax_profile_2026.csv"),
    ("state_income_tax_brackets", "state_income_tax_brackets_2026.csv"),
    ("state_deductions", "state_deductions_2026.csv"),
    ("state_surtaxes", "state_surtaxes_2026.csv"),
    ("state_sales_tax", "state_sales_tax_2026.csv"),
    ("federal_brackets", "federal_brackets.csv"),
    ("federal_filing_params", "federal_filing_params.csv"),
    ("federal_payroll_params", "federal_payroll_params.csv"),
    ("localities", "localities.csv"),
    ("local_income_tax_rates", "local_income_tax_rates.csv"),
    ("state_jock_tax_rules", "state_jock_tax_rules_2026.csv"),
    ("teams", "teams.csv"),
    ("league_duty_day_rules", "league_duty_day_rules.csv"),
]


def build_db(root: Path, processed: Path) -> sqlite3.Connection:
    db = root / "athlete_tax.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((root / "db" / "schema.sql").read_text())
    for table, fname in LOAD_ORDER:
        df = pd.read_csv(processed / fname)
        for c in df.columns:
            if c in INT_COLS:
                df[c] = df[c].astype("Int64")
        df.to_sql(table, con, if_exists="append", index=False)
    con.commit()
    return con


def run_checks(con: sqlite3.Connection) -> bool:
    ok = True
    print("\nSchema check views (each must return 0 rows):")
    for v in ("v_check_bracket_start", "v_check_bracket_order", "v_check_state_coverage"):
        n = con.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
        print(f"  {v:28s} {n}  {'OK' if n == 0 else 'FAIL'}")
        ok &= n == 0

    def rows(code, fs="single"):
        return con.execute("SELECT lower_bound, rate FROM state_income_tax_brackets WHERE tax_year=? AND "
                           "state_code=? AND filing_status=? ORDER BY bracket_order", (TAX_YEAR, code, fs)).fetchall()

    print("\nReproducing the Week 3 memo's numbers (brackets on a $233,165 slice, 2 of 170 duty days):")
    for code, expected in (("NY", 13_357), ("CA", 18_123), ("NJ", 12_728), ("MA", 11_658), ("PA", 7_158)):
        got = bracket_tax(rows(code), 233_165)
        good = abs(got - expected) <= 1
        print(f"  {code}: memo ${expected:>7,}  engine ${got:>10,.2f}  {'OK' if good else 'FAIL'}")
        ok &= good
    ma = bracket_tax(rows("MA"), 33_000_000) + 0.04 * (33_000_000 - 1_107_750)
    good = abs(ma - 2_930_000) < 5_000
    print(f"  MA $33M signing bonus: memo ~$2.93M  got ${ma:,.0f}  {'OK' if good else 'FAIL'}")
    ok &= good
    for fs, top, exp in (("single", 640_600, 192_979.25), ("mfj", 768_700, 206_583.50)):
        b = con.execute("SELECT lower_bound, rate FROM federal_brackets WHERE tax_year=2026 AND filing_status=? "
                        "ORDER BY bracket_order", (fs,)).fetchall()
        got = bracket_tax(b, top)
        good = abs(got - exp) < 0.01
        print(f"  Federal {fs} cumulative tax at ${top:,}: IRS ${exp:,.2f}  got ${got:,.2f}  {'OK' if good else 'FAIL'}")
        ok &= good
    # Week 4 checks
    print("\nWeek 4 checks:")
    ca = rows("CA")
    eff = bracket_tax(ca, 100_000) * (10_000 / 100_000)
    good = abs(eff - 574) < 1
    print(f"  CA effective-rate example (Tax Foundation 2026): TF $574  got ${eff:,.2f}  {'OK' if good else 'FAIL'}")
    ok &= good
    direct = bracket_tax(ca, 10_000)
    good = abs(direct - 100) < 0.01
    print(f"  CA brackets-on-slice for the same $10,000: TF $100  got ${direct:,.2f}  {'OK' if good else 'FAIL'}")
    ok &= good
    pit = con.execute("SELECT legal_status FROM local_income_tax_rates WHERE locality_id='PIT'").fetchone()
    good = pit is not None and pit[0] == "struck_down"
    print(f"  Pittsburgh facility fee marked struck_down: {'OK' if good else 'FAIL'}")
    ok &= good
    il = con.execute("SELECT sourcing_method, retaliatory_provision FROM state_jock_tax_rules WHERE state_code='IL'").fetchone()
    good = il == ("duty_day", 0)
    print(f"  Illinois = duty days, no retaliatory clause: {'OK' if good else 'FAIL'}")
    ok &= good
    n_teams = con.execute("SELECT league, COUNT(*) FROM teams GROUP BY league").fetchall()
    good = dict(n_teams) == {"MLB": 30, "NFL": 32, "NHL": 32}
    print(f"  Teams loaded {dict(n_teams)}: {'OK' if good else 'FAIL'}")
    ok &= good
    return ok


def find_repo_root() -> Path:
    """Walk up from this file until we find the folder that holds db/schema.sql."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "db" / "schema.sql").exists():
            return parent
    return Path.cwd()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=find_repo_root())
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()
    root, processed = args.root.resolve(), args.root.resolve() / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    print(f"Repo root: {root}\n\nReading raw files:")

    fed = []
    for key, yr in (("fed_2024", 2024), ("fed_2025", 2025), ("fed_2026", 2026)):
        p = find_raw(root, key, required=(yr == 2026))
        if p is not None:
            print(f"  {p.name}")
            fed.append(clean_federal(p, yr))
    federal = pd.concat(fed, ignore_index=True)

    p_state = find_raw(root, "state_main"); print(f"  {p_state.name}")
    p_class = find_raw(root, "state_class", required=False)
    brk, prof, sur, ded, brackets = build_state_tables(pd.read_csv(p_state), p_class)

    p_sales = find_raw(root, "sales", required=False)
    sales = clean_sales(p_sales) if p_sales else pd.DataFrame(
        columns=["tax_year", "state_code", "state_rate", "avg_local_rate", "max_local_rate", "combined_rate"])
    loc, loc_rates, jock, teams, rules = load_curated(root)

    tables = {
        "state_tax_profile_2026.csv": prof, "state_income_tax_brackets_2026.csv": brk,
        "state_deductions_2026.csv": ded, "state_surtaxes_2026.csv": sur, "state_sales_tax_2026.csv": sales,
        "federal_brackets.csv": federal,
        "federal_filing_params.csv": pd.DataFrame(FEDERAL_FILING_PARAMS, columns=[
            "tax_year", "filing_status", "standard_deduction", "addl_medicare_threshold"]),
        "federal_payroll_params.csv": pd.DataFrame(FEDERAL_PAYROLL_PARAMS),
        "localities.csv": loc, "local_income_tax_rates.csv": loc_rates, "state_jock_tax_rules_2026.csv": jock,
        "teams.csv": teams, "league_duty_day_rules.csv": rules,
    }
    print("\nWriting data/processed/:")
    for fname, df in tables.items():
        df.to_csv(processed / fname, index=False)
        print(f"  {fname:38s} {len(df):>4} rows")

    if args.no_db:
        return
    print("\nBuilding athlete_tax.db from db/schema.sql ...")
    con = build_db(root, processed)
    ok = run_checks(con)
    print("\nVerification status of loaded state bracket rows:")
    for st, n in con.execute("SELECT verification_status, COUNT(*) FROM state_income_tax_brackets GROUP BY 1"):
        print(f"  {st:12s} {n}")
    con.close()
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED: do not use this database yet")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()