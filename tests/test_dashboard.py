"""Verify the dashboard preserves engine results and rejects invalid allocations."""
import unittest
from dashboard.server import calculate


class DashboardCalculation(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(salary=2_260_000, bonus=33_000_000, residence="MA",
                           days={"MA": 158, "NY": 2, "FL": 2, "NJ": 2})

    def test_presets_match_existing_demo(self):
        ma = calculate(self.inputs)
        tx = calculate(dict(self.inputs, residence="TX"))
        self.assertAlmostEqual(ma["tax"]["total"], 3_129_971, delta=1)
        self.assertAlmostEqual(tx["tax"]["total"], 157_421, delta=1)
        self.assertAlmostEqual(ma["gross"], ma["remaining"] + ma["total_tax"])
        self.assertAlmostEqual(sum(r["total_sourced"] for r in ma["rows"]) + ma["residence_only"], ma["gross"])

    def test_invalid_inputs(self):
        for change in ({"days": {}}, {"days": {"MA": 366}}, {"days": {"MA": 1.5}},
                       {"salary": -1}, {"salary": float("nan")}, {"residence": "ZZ"},
                       {"unsourced": -1}, {"filing": "bad"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                calculate(dict(self.inputs, **change))

    def test_conditional_bonus_is_sourced_to_work_states(self):
        result = calculate(dict(self.inputs, bonus_treatment="conditional"))
        self.assertAlmostEqual(result["residence_only"], 0, places=6)
        self.assertAlmostEqual(sum(r["total_sourced"] for r in result["rows"]), result["gross"])

    def test_federal_standard_deduction_and_progressive_brackets(self):
        result = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="TX", days={"TX": 100}))
        # $83,900 taxable: 12,400 @10%, 38,000 @12%, 33,500 @22%.
        self.assertAlmostEqual(result["national"]["federal"], 13_170)
        self.assertAlmostEqual(result["national"]["payroll"]["total"], 7_650)
        self.assertAlmostEqual(result["remaining"], 79_180)

    def test_payroll_cap_bonus_and_joint_threshold(self):
        single = calculate(self.inputs)["national"]
        joint = calculate(dict(self.inputs, filing="mfj"))["national"]
        self.assertAlmostEqual(single["payroll"]["social_security"], 11_439)
        self.assertAlmostEqual(single["payroll"]["medicare"], 35_260_000 * .0145)
        self.assertAlmostEqual(single["payroll"]["additional_medicare"], (35_260_000 - 200_000) * .009)
        self.assertAlmostEqual(single["payroll"]["additional_medicare"] - joint["payroll"]["additional_medicare"], 450)
        self.assertEqual(joint["deduction"], 32_200)

    def test_zero_taxable_income_and_medicare_boundary(self):
        low = calculate(dict(self.inputs, salary=10_000, bonus=0))["national"]
        self.assertEqual(low["federal"], 0)
        edge = calculate(dict(self.inputs, salary=200_000, bonus=0))["national"]
        self.assertEqual(edge["payroll"]["additional_medicare"], 0)

    def test_philadelphia_payment_periods(self):
        result = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="TX", days={"PA": 100},
                                early_cash=50_000, local_work={"PHL": {"early": 50_000, "late": 50_000}}))
        self.assertAlmostEqual(result["local"]["total"], 50_000 * .0343 + 50_000 * .03425)

    def test_city_resident_not_taxed_twice(self):
        result = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="PA", days={"PA": 100},
                                resident_city="PHL", early_cash=50_000,
                                local_work={"PHL": {"early": 50_000, "late": 50_000}}))
        self.assertAlmostEqual(result["local"]["total"], 50_000 * .0374 + 50_000 * .03735)
        self.assertTrue(all(row["kind"] == "resident" for row in result["local"]["rows"]))

    def test_nyc_resident_progressive_and_visitor_exempt(self):
        resident = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="NY", days={"NY": 100}, resident_city="NYC"))
        self.assertAlmostEqual(resident["local"]["total"], 12_000 * .03078 + 13_000 * .03762 + 25_000 * .03819 + 42_000 * .03876)
        visitor = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="TX", days={"NY": 100},
                                 local_work={"NYC": {"early": 0, "late": 100_000}}))
        self.assertEqual(visitor["local"]["total"], 0)

    def test_local_validation(self):
        for change in ({"resident_city": "NYC"}, {"resident_city": "PIT"}, {"early_cash": -1},
                       {"local_work": {"DET": {"late": 10_000}}},
                       {"local_work": {"PHL": {"early": 10_000}}},
                       {"local_work": {"PHL": {"late": float("inf")}}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                calculate(dict(self.inputs, **change))

    def test_detroit_cincinnati_and_maryland_nonresident(self):
        for city, state, rate in [("DET", "MI", .012), ("CIN", "OH", .018), ("MDNR", "MD", .0225)]:
            result = calculate(dict(self.inputs, salary=100_000, bonus=0, residence="TX", days={state: 100},
                                    local_work={city: {"late": 10_000}}))
            self.assertAlmostEqual(result["local"]["total"], 10_000 * rate)

    def test_contract_cash_is_used_instead_of_cap_proration(self):
        from etl.contract_data import load_contracts
        for row in load_contracts():
            result = calculate(dict(self.inputs, salary=row["base_salary"], bonus=row["signing_bonus_cash"],
                                    other_cash=row["other_cash"], residence=row["home_state"],
                                    days={row["home_state"]: 164}))
            self.assertEqual(result["gross"], row["annual_cash"])
            self.assertNotEqual(result["gross"], row["cap_charge"])
            self.assertAlmostEqual(sum(r["total_sourced"] for r in result["rows"]) + result["residence_only"], result["gross"])
