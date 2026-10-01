"""
Week 4 demo: Christian Gonzalez, tax year 2026, state + local tax under two residency scenarios.

ILLUSTRATIVE. Assumptions (all flagged):
  * 2026 cash: $33M signing bonus (assumed to pass the three-part test) + $2.26M base salary.
  * Duty-day window for tax year 2026: training camp 2026-07-21 through 2026-12-31 (needs_check);
    January 2026 days from the 2025 season are ignored.
  * Only the three division road games are known (fixed every year): @BUF (NY), @MIA (FL), @NYJ (NJ).
    Dates below are placeholders; the five other road games are unknown and left in Massachusetts,
    which slightly overstates MA days.
  * Each road trip = 1 arrival day with a team meeting + 1 game day.
Run from the repo root:  python analysis/gonzalez_week4_demo.py
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.duty_days import CompItem, RoadGame, TaxTables, allocate, build_season, duty_day_ratios, estimate_state_local_tax

road = [RoadGame(date(2026, 9, 20), "NY", projected=True),
        RoadGame(date(2026, 10, 18), "FL", projected=True),
        RoadGame(date(2026, 11, 22), "NJ", projected=True)]
days = build_season(date(2026, 7, 21), date(2026, 12, 31), "MA", road)
r = duty_day_ratios(days, 2026)
t = TaxTables(ROOT / "athlete_tax.db")
items = [CompItem("signing_bonus", 33_000_000), CompItem("salary", 2_260_000)]
alloc = allocate(items, r, t.bonus_rules())

print(f"Duty days in 2026: {r.total_days}  by state: {r.state_days}  unsourced: {r.unsourced_days}")
print(f"Income sourced to work states: { {k: round(v) for k, v in alloc.sourced.items()} }")
print(f"Residence-only income (bonus + unsourced days): ${alloc.residence_only:,.0f}\n")
for label, res in (("A. Massachusetts resident (domicile, or home + >183 days)", "MA"),
                   ("B. Domiciled in Texas (no state income tax)", None)):
    out = estimate_state_local_tax(t, alloc, res)
    print(label)
    print(f"   residence-state tax ${out['residence_tax']:,.0f}  credit -${out['credit']:,.0f}")
    print(f"   nonresident taxes { {k: round(v) for k, v in out['nonresident'].items()} }")
    print(f"   TOTAL state+local ${out['total']:,.0f}\n")