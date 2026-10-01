"""Run from the repo root:  python -m unittest discover tests -v
Builds athlete_tax.db first if it does not exist."""
import subprocess
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.duty_days import (CompItem, DutyDay, RoadGame, TaxTables, allocate, build_season,  # noqa: E402
                           duty_day_ratios, estimate_state_local_tax, nonresident_tax, resident_tax)

DB = ROOT / "athlete_tax.db"


def setUpModule():
    if not DB.exists():
        subprocess.run([sys.executable, str(ROOT / "db" / "clean_tax_data.py")], check=True,
                       stdout=subprocess.DEVNULL)


def flat_days(n, state="MA", start=date(2026, 1, 2)):
    return [DutyDay(start + timedelta(days=i), "practice", state) for i in range(n)]


class DutyDayRules(unittest.TestCase):
    def test_travel_day_in_denominator_not_numerator(self):
        days = flat_days(10) + [DutyDay(date(2026, 9, 1), "travel", "CA"), DutyDay(date(2026, 9, 2), "game", "CA")]
        r = duty_day_ratios(days, 2026)
        self.assertEqual(r.total_days, 12)
        self.assertEqual(r.state_days["CA"], 1)
        self.assertEqual(r.unsourced_days, 1)

    def test_ma_example_2_injured_at_clinic_not_sourced(self):
        # 830 CMR 62.5A.2 Example 2: injured player at a private clinic in MA while his team plays there
        days = flat_days(20, "NY") + [DutyDay(date(2026, 9, 1), "injured_elsewhere", "MA"),
                                      DutyDay(date(2026, 9, 2), "injured_elsewhere", "MA")]
        r = duty_day_ratios(days, 2026)
        self.assertNotIn("MA", r.state_days)
        self.assertEqual(r.total_days, 22)

    def test_ma_example_3_rehab_at_team_facility_is_sourced(self):
        days = build_season(date(2026, 8, 1), date(2026, 8, 10), "MA", [],
                            injured={date(2026, 8, 5): "injured_team_facility"})
        self.assertEqual(duty_day_ratios(days, 2026).state_days["MA"], 10)

    def test_calendar_year_split(self):
        # NFL window July 2026 - January 2027: only 2026 days count for tax year 2026
        days = build_season(date(2026, 7, 21), date(2027, 1, 10), "MA", [])
        self.assertEqual(duty_day_ratios(days, 2026).total_days, (date(2026, 12, 31) - date(2026, 7, 21)).days + 1)
        self.assertEqual(duty_day_ratios(days, 2027).total_days, 10)

    def test_hillenmeyer_two_of_160(self):
        days = flat_days(158, "IL") + [DutyDay(date(2026, 12, 1), "meeting", "OH", "CLE"),
                                       DutyDay(date(2026, 12, 2), "game", "OH", "CLE")]
        self.assertAlmostEqual(duty_day_ratios(days, 2026).state_ratio("OH"), 0.0125)

    def test_tax_foundation_three_of_170(self):
        days = flat_days(167) + [DutyDay(date(2026, 12, 1) + timedelta(days=i), "game", "AZ") for i in range(3)]
        self.assertAlmostEqual(duty_day_ratios(days, 2026).state_ratio("AZ"), 3 / 170)

    def test_split_home_states_commanders(self):
        # practice in VA, home games in MD
        g = [date(2026, 9, 13), date(2026, 9, 27)]
        days = build_season(date(2026, 9, 1), date(2026, 9, 30), "VA", [], home_games=g, stadium_state="MD")
        r = duty_day_ratios(days, 2026)
        self.assertEqual(r.state_days, {"VA": 28, "MD": 2})


class SigningBonus(unittest.TestCase):
    def setUp(self):
        self.r = duty_day_ratios(flat_days(90, "MA") + flat_days(10, "CA", date(2026, 12, 1)), 2026)

    def test_three_part_bonus_goes_to_residence(self):
        a = allocate([CompItem("signing_bonus", 33_000_000)], self.r, {"MA": "residence_if_three_part_test",
                                                                       "CA": "residence_if_three_part_test"})
        self.assertEqual(a.sourced.get("MA", 0), 0)
        self.assertEqual(a.residence_only, 33_000_000)

    def test_refundable_bonus_fails_test_and_is_allocated(self):
        a = allocate([CompItem("signing_bonus", 10_000_000, nonrefundable=False)], self.r,
                     {"MA": "residence_if_three_part_test"})
        self.assertAlmostEqual(a.sourced["MA"], 9_000_000)

    def test_california_partial(self):
        b = CompItem("signing_bonus", 10_000_000, refundable_amount=4_000_000)
        a = allocate([b], self.r, {"CA": "partial_duty_days", "MA": "residence_if_three_part_test"})
        self.assertAlmostEqual(a.sourced["CA"], 400_000)   # 4M x 10%
        self.assertEqual(a.sourced["MA"], 0)

    def test_salary_follows_duty_days(self):
        a = allocate([CompItem("salary", 1_000_000)], self.r, {})
        self.assertAlmostEqual(a.sourced["MA"], 900_000)
        self.assertAlmostEqual(a.sourced["CA"], 100_000)


class TaxPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = TaxTables(DB)

    def test_tax_foundation_california_example(self):
        # Walczak (Tax Foundation, 2026-09-09): $100,000 total, $10,000 in CA -> $574 effective-rate
        self.assertAlmostEqual(nonresident_tax(self.t, "CA", 100_000, 10_000), 574, delta=1)

    def test_ma_visitor_below_surtax_line_pays_5pct(self):
        self.assertAlmostEqual(nonresident_tax(self.t, "MA", 19_819_000, 233_165), 233_165 * 0.05, places=2)

    def test_dc_and_no_tax_states(self):
        self.assertEqual(nonresident_tax(self.t, "DC", 10_000_000, 200_000), 0)
        self.assertEqual(nonresident_tax(self.t, "FL", 10_000_000, 200_000), 0)

    def test_resident_credit_is_capped(self):
        # MA resident, 10% of $20M sourced to CA: credit can't exceed MA's own tax on that slice
        r = duty_day_ratios(flat_days(90, "MA") + flat_days(10, "CA", date(2026, 12, 1)), 2026)
        a = allocate([CompItem("salary", 20_000_000)], r, {})
        out = estimate_state_local_tax(self.t, a, "MA")
        ma_on_slice = resident_tax(self.t, "MA", 20_000_000) * 0.10
        self.assertAlmostEqual(out["credit"], ma_on_slice, places=2)
        self.assertGreater(out["nonresident"]["CA"], out["credit"])

    def test_pittsburgh_fee_struck_down(self):
        self.assertEqual(self.t.local_nonresident_rate("PIT"), 0.0)

    def test_detroit_visitor_rate(self):
        self.assertAlmostEqual(self.t.local_nonresident_rate("DET"), 0.012)

    def test_philadelphia_midyear_change(self):
        self.assertAlmostEqual(self.t.local_nonresident_rate("PHL", on="06-30"), 0.0343)
        self.assertAlmostEqual(self.t.local_nonresident_rate("PHL", on="12-31"), 0.03425)


if __name__ == "__main__":
    unittest.main()