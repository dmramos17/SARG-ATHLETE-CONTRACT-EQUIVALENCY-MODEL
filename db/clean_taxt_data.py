#!/usr/bin/env python3
"""
clean_tax_data.py  --  raw Tax Foundation / jock-tax CSVs  ->  tidy CSVs  ->  SQLite

Run from anywhere:   python src/athlete_tax/clean_tax_data.py
Options:             --root PATH   repo root (default: two folders above this file)
                     --no-db       write the tidy CSVs but do not build athlete_tax.db

Pipeline
    data/ (or data/raw/)  raw downloads, never edited by hand
        |   this script: parse, de-footnote, reshape, apply documented overrides
        v
    data/processed/*.csv  tidy, schema-shaped, committed to Git (source of truth)
        |   this script: build DB from db/schema.sql, load, run checks
        v
    athlete_tax.db        generated; keep it in .gitignore

Every manual correction lives in the OVERRIDES section below, with its reason,
so nothing is changed silently. If an upstream file changes so an override no
longer applies, the script stops and tells you instead of guessing.
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

# =============================================================================
# OVERRIDES (each comes from the Week 3 memo; remove one once the raw source is fixed)
# =============================================================================

# Georgia HB 463 (signed 2026-05-11) cut the rate retroactive to 1/1/2026; the Tax Foundation
# table still shows 5.19%.
GA_RAW_RATE, GA_NEW_RATE = 0.0519, 0.0499

# Surtaxes are removed from the bracket rows and stored in state_surtaxes so they cannot be
# double-counted. `raw_threshold` is where the raw file bakes the surtax into a higher bracket.
#   MA: raw file shows 9% above $1,083,150 (the 2025 threshold). 2026 certified threshold is
#       $1,107,750 (Mass. DOR Form 1-ES / 2-ES).
#   CA: raw file shows the 1% Mental Health Services Tax folded into rates at/above $1,000,000.
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

STALE_2025_STATES = {"AR", "CA", "ND", "VT"}          # TF published 2025 bracket widths for 2026
STATE_ROW_STATUS = {"GA": "verified"}                  # confirmed against HB 463
# Nonresident rate method: CA/NY/NJ tax ALL income as if in-state, then multiply by the in-state
# share ('proration'). Everyone else defaults to 'direct' (brackets on the sourced slice) until checked.
PRORATION_STATES = {"CA", "NY", "NJ"}
# 21 states with athlete-specific duty-day rules (Tax Notes State, 2024-05-31)
ATHLETE_DUTY_DAY_RULE_STATES = {"AZ", "CO", "CT", "IA", "IL", "IN", "LA", "MA", "MD", "ME", "MI",
                                "MO", "NC", "NJ", "NY", "OR", "PA", "RI", "UT", "VA", "WI"}
STATE_NOTES = {
    "GA": "Rate 4.99% per HB 463 (signed 2026-05-11, retroactive to 1/1/2026); TF table shows 5.19%.",
    "MA": "5% flat + 4% surtax over $1,107,750 (see state_surtaxes).",
    "CA": "Top bracket 12.3% + 1% MHST (state_surtaxes). SDI not modeled.",
    "NY": "Benefit recapture NOT modeled: engine output is a lower bound for very high earners.",
    "SC": "Top rate temporarily 6% through 2026-06-30, scheduled to revert to 6.2%. Verify.",
    "MD": "Visitors also owe a special nonresident tax in lieu of county tax (not in brackets).",
    "WA": "No wage income tax; capital gains only (7%/9%). Capital-gains rates intentionally not loaded.",
    "DC": "DC cannot tax nonresidents' wages.",
}

# Federal parameters that are NOT in the Tax Foundation CSVs (Week 3 memo, IRS Rev. Proc. 2025-32)
FEDERAL_FILING_PARAMS = [  # tax_year, filing_status, standard_deduction, addl_medicare_threshold
    (2026, "single", 16_100, 200_000),
    (2026, "mfj", 32_200, 250_000),
]
FEDERAL_PAYROLL_PARAMS = [dict(tax_year=2026, ss_rate=0.062, ss_wage_base=184_500, medicare_rate=0.0145,
                               addl_medicare_rate=0.009, salt_cap_effective=10_000, salt_status="needs_check")]

# Cities. The raw file gives ONE rate per city with no resident/nonresident split, so the split is
# documented here. Anything marked needs_check must be verified before the engine relies on it.
LOCALITIES = {  # city name in CSV -> (locality_id, state_code)
    "New York City": ("NYC", "NY"), "Philadelphia": ("PHL", "PA"), "Cleveland": ("CLE", "OH"),
    "Columbus": ("COL", "OH"), "Pittsburgh": ("PIT", "PA"), "Detroit": ("DET", "MI"),
    "Kansas City": ("KCM", "MO"), "St. Louis": ("STL", "MO"),
}

# =============================================================================
# Lookups
# =============================================================================
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

# Raw file name patterns (matched against the lower-cased, letters+digits-only file stem)
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

# =============================================================================
# Helpers
# =============================================================================
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
    s = re.sub(r"\s*\([^)]*\)", "", str(s))        # footnote letters
    s = re.sub(r"^\s*-\s*", "", s)                  # continuation-row dash
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
    """rows = [(lower_bound, rate), ...] sorted ascending."""
    total = 0.0
    for i, (low, rate) in enumerate(rows):
        upper = rows[i + 1][0] if i + 1 < len(rows) else float("inf")
        if income > low:
            total += (min(income, upper) - low) * rate
    return total


# =============================================================================
# Federal
# =============================================================================
def clean_federal(path: Path, tax_year: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = ["rate", "single", "mfj", "hoh"]
    rows = []
    for fs in ("single", "mfj", "hoh"):
        prev_upper = 0.0
        for i, (r, rng) in enumerate(zip(df["rate"], df[fs]), start=1):
            nums = [float(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", str(rng).replace("\xa0", " "))]
            # Files differ: 2024/2025 write "$11,600 to ..." , 2026 writes "$12,401 to ...".
            # Using the previous bracket's upper bound as this bracket's lower bound handles both.
            lower = 0.0 if i == 1 else prev_upper
            if i > 1 and nums[0] not in (prev_upper, prev_upper + 1):
                sys.exit(f"ERROR: federal {tax_year} {fs}: bracket {i} starts at {nums[0]}, "
                         f"expected {prev_upper} or {prev_upper + 1}")
            prev_upper = nums[1] if len(nums) > 1 else None
            rows.append(dict(tax_year=tax_year, filing_status=fs, bracket_order=i, lower_bound=lower,
                             rate=pct(r), verification_status="needs_check",
                             source=f"Tax Foundation {tax_year} federal brackets"))
    out = pd.DataFrame(rows)
    if tax_year == 2026:   # IRS-published cumulative tax at the 37% threshold (see memo)
        ok = True
        for fs, top, expected in (("single", 640_600, 192_979.25), ("mfj", 768_700, 206_583.50)):
            b = out[out.filing_status == fs].sort_values("bracket_order")
            got = bracket_tax(list(zip(b.lower_bound, b.rate)), top)
            ok &= abs(got - expected) < 0.01
        if ok:
            out.loc[out.filing_status.isin(["single", "mfj"]), "verification_status"] = "verified"
    return out


# =============================================================================
# State brackets, profile, surtaxes, deductions
# =============================================================================
def parse_state_brackets(df: pd.DataFrame):
    d = df.iloc[:, [0, 1, 3, 4, 6]].copy()
    d.columns = ["raw", "s_rate", "s_low", "m_rate", "m_low"]
    out = {}
    for _, r in d.iterrows():
        name = clean_name(r["raw"])
        if name == "Washington":                       # capital-gains rates only, not wages
            continue
        if name not in STATE_CODES:
            sys.exit(f"ERROR: unrecognised state name in raw file: {name!r}")
        code = STATE_CODES[name]
        for fs, rate, low in (("single", r["s_rate"], r["s_low"]), ("mfj", r["m_rate"], r["m_low"])):
            if is_pct(rate) and is_money(low):         # skips 'none', NaN placeholder rows, text rows
                out.setdefault((code, fs), []).append((money(low), pct(rate)))
    for key, rows in out.items():
        rows.sort()
        if rows[0][0] > 0:                             # ID, MS, OH, ND, DE, MO, OK ...: 0% below first bracket
            rows.insert(0, (0.0, 0.0))
    return out


def apply_overrides(brackets: dict):
    # Georgia
    for fs in ("single", "mfj"):
        rows = brackets[("GA", fs)]
        if len(rows) != 1 or abs(rows[0][1] - GA_RAW_RATE) > 1e-9:
            sys.exit(f"ERROR: Georgia raw data is no longer a single {GA_RAW_RATE:.2%} bracket "
                     f"({rows}). Review the GA override.")
        brackets[("GA", fs)] = [(rows[0][0], GA_NEW_RATE)]
    # Surtaxes: subtract from the baked-in rates, then merge equal neighbours
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
    # Sanity: rates never fall as income rises
    for (code, fs), rows in brackets.items():
        rates = [r for _, r in rows]
        if rates != sorted(rates):
            sys.exit(f"ERROR: {code} {fs} rates are not non-decreasing: {rows}")
    return brackets


def build_state_tables(raw: pd.DataFrame, class_path):
    brackets = apply_overrides(parse_state_brackets(raw))
    # ---- brackets
    rows = []
    for (code, fs), lst in sorted(brackets.items()):
        status = ("stale_2025" if code in STALE_2025_STATES else STATE_ROW_STATUS.get(code, "needs_check"))
        for i, (low, rate) in enumerate(lst, start=1):
            rows.append(dict(tax_year=TAX_YEAR, state_code=code, filing_status=fs, bracket_order=i,
                             lower_bound=low, rate=rate, verification_status=status,
                             source="HB 463 (Georgia Economic Growth and Tax Relief Act of 2026)"
                             if code == "GA" else TF_SOURCE))
    brk = pd.DataFrame(rows)

    # ---- profile (derive tax type from the data)
    derived = {}
    for code in STATE_NAMES:
        if code == "WA":
            derived[code] = "cap_gains_only"
        elif (code, "single") not in brackets:
            derived[code] = "none"
        else:
            pos = {r for _, r in brackets[(code, "single")] if r > 0}
            derived[code] = "flat" if len(pos) == 1 else "graduated"
    if class_path is not None:                         # cross-check against TF's own classification
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
            nonresident_rate_method="proration" if code in PRORATION_STATES else "direct",
            nonresident_method_status=("verified" if (code in PRORATION_STATES or not taxes) else "needs_check"),
            has_athlete_duty_day_rule=int(code in ATHLETE_DUTY_DAY_RULE_STATES),
            notes=STATE_NOTES.get(code)))
    prof = pd.DataFrame(prof)

    # ---- surtaxes
    sur = pd.DataFrame([{"tax_year": TAX_YEAR, **{k: v for k, v in s.items() if k != "raw_threshold"}}
                        for s in SURTAXES])

    # ---- deductions / exemptions (single and married-joint columns only)
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
    return brk, prof, sur, pd.DataFrame(ded), brackets


# =============================================================================
# Sales tax, local, jock
# =============================================================================
def clean_sales(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path)
    return pd.DataFrame(dict(
        tax_year=TAX_YEAR, state_code=t["State"].map(lambda n: STATE_CODES[clean_name(n)]),
        state_rate=t["State Tax Rate"].map(pct), avg_local_rate=t["Average Local Tax Rate"].map(pct),
        max_local_rate=t["Max Local Rate"].map(pct), combined_rate=t["Combined Tax Rate"].map(pct)))


def clean_local(path: Path):
    c = pd.read_csv(path)
    loc, rates = [], []
    for _, r in c.iterrows():
        city = str(r["City"]).strip()
        if city not in LOCALITIES:
            sys.exit(f"ERROR: city {city!r} not in LOCALITIES. Add it (id, state) in the OVERRIDES section.")
        lid, st = LOCALITIES[city]
        csv_rate, csv_note = pct(r["City Rate"]), str(r["Notes"]).strip()
        loc.append(dict(locality_id=lid, locality_name=city, state_code=st))
        base = dict(locality_id=lid, verification_status="needs_check", source="city_jock_taxes.csv")
        if lid == "NYC":      # memo: residents only; commuter tax repealed 1999
            rates.append({**base, "effective_date": "2026-01-01", "resident_rate": csv_rate,
                          "nonresident_rate": 0.0, "taxes_nonresident_work": 0, "apportionment_method": "none",
                          "notes": f"CSV: {csv_note}. Per Week 3 memo NYC taxes residents only; visitors owe nothing."})
        elif lid == "PHL":    # memo: nonresident wage tax 3.43% before 2026-07-01, 3.425% from then
            for eff, rate in (("2026-01-01", 0.0343), ("2026-07-01", 0.03425)):
                rates.append({**base, "effective_date": eff, "resident_rate": None, "nonresident_rate": rate,
                              "taxes_nonresident_work": 1, "apportionment_method": None,
                              "verification_status": "verified",
                              "source": "City of Philadelphia Dept. of Revenue (via Week 3 memo)",
                              "notes": f"CSV says {csv_rate:.2%}; memo/city figures used instead. Resident rate not loaded."})
        elif lid == "PIT":   # memo: facility usage fee on nonresidents at publicly funded venues
            rates.append({**base, "effective_date": "2026-01-01", "resident_rate": None, "nonresident_rate": csv_rate,
                          "taxes_nonresident_work": 1, "apportionment_method": "flat_fee",
                          "notes": f"CSV: {csv_note}. Treated as the facility usage fee on nonresident performers; verify."})
        elif lid == "DET":
            rates.append({**base, "effective_date": "2026-01-01", "resident_rate": csv_rate, "nonresident_rate": None,
                          "taxes_nonresident_work": 1, "apportionment_method": None,
                          "notes": f"CSV: {csv_note}. 2.4% is likely the RESIDENT rate; the nonresident rate is "
                                   "commonly cited as half (1.2%). Verify before use."})
        else:                 # CLE, COL, KCM, STL
            rates.append({**base, "effective_date": "2026-01-01", "resident_rate": csv_rate, "nonresident_rate": csv_rate,
                          "taxes_nonresident_work": 1, "apportionment_method": None,
                          "notes": f"CSV: {csv_note}. Single CSV rate ASSUMED to apply equally to residents and "
                                   "nonresidents working in the city; verify."})
    return pd.DataFrame(loc), pd.DataFrame(rates)


def clean_jock(path: Path, brackets: dict) -> pd.DataFrame:
    j = pd.read_csv(path)
    method_map = {"duty days": "duty_day", "games played": "games_played"}
    rows, mismatches = [], 0
    surtax = {s["state_code"]: s["rate"] for s in SURTAXES}
    for _, r in j.iterrows():
        code = STATE_CODES[clean_name(r["State"])]
        raw_method = str(r["Allocation Method"]).strip()
        key = re.sub(r"\s*\(.*\)", "", raw_method).strip().lower()
        notes = [f"CSV allocation method: '{raw_method}'."]
        if key in method_map:
            method = method_map[key]
        else:                                          # 'Duty days or games played' (Ohio)
            method = "duty_day"
            notes.append("CSV gives two methods; duty_day used as default. Verify.")
        if method == "games_played" and code in ATHLETE_DUTY_DAY_RULE_STATES:
            notes.append("CONFLICT: Tax Notes (2024) lists an athlete duty-day rule for this state. "
                         "Read the statute and resolve.")
        if code == "CA":
            notes.append("CA allocates signing bonuses by duty days (Testaverde dispute): flag CA contracts.")
        # informational: does the CSV's 'Top Rate' agree with the bracket data?
        top_csv = float(re.search(r"[\d.]+", str(r["Top Rate"])).group()) / 100
        top_brk = max(rate for _, rate in brackets[(code, "single")]) + surtax.get(code, 0.0)
        mismatches += abs(top_csv - top_brk) > 0.0005
        rows.append(dict(
            state_code=code, league="ALL", tax_year=TAX_YEAR, sourcing_method=method, duty_day_definition=None,
            employer_withholding_required=None, composite_return_allowed=None,
            signing_bonus_sourcing={"CA": "duty_days", "NY": "residence"}.get(code, "unknown"),
            retaliatory_provision=1 if code == "IL" else None,
            statute_citation="35 ILCS 5/304" if code == "IL" else None,
            verification_status="needs_check", notes=" ".join(notes)))
    print(f"  jock file 'Top Rate' disagrees with the bracket data for {mismatches} of {len(j)} states "
          "(column ignored; brackets are the source of truth)")
    return pd.DataFrame(rows)


# =============================================================================
# Database
# =============================================================================
INT_COLS = {"has_athlete_duty_day_rule", "taxes_wages", "std_deduction_is_credit", "exemption_is_credit",
            "threshold_doubled_for_mfj", "applies_to_nonresidents", "withheld_by_employer",
            "taxes_nonresident_work", "employer_withholding_required", "composite_return_allowed",
            "retaliatory_provision", "bracket_order", "tax_year"}
LOAD_ORDER = [  # parents before children
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
    return ok


# =============================================================================
# Main
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
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
    p_city = find_raw(root, "city_jock"); loc, loc_rates = clean_local(p_city)
    p_sj = find_raw(root, "state_jock"); jock = clean_jock(p_sj, brackets)

    tables = {
        "state_tax_profile_2026.csv": prof, "state_income_tax_brackets_2026.csv": brk,
        "state_deductions_2026.csv": ded, "state_surtaxes_2026.csv": sur, "state_sales_tax_2026.csv": sales,
        "federal_brackets.csv": federal,
        "federal_filing_params.csv": pd.DataFrame(FEDERAL_FILING_PARAMS, columns=[
            "tax_year", "filing_status", "standard_deduction", "addl_medicare_threshold"]),
        "federal_payroll_params.csv": pd.DataFrame(FEDERAL_PAYROLL_PARAMS),
        "localities.csv": loc, "local_income_tax_rates.csv": loc_rates, "state_jock_tax_rules_2026.csv": jock,
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