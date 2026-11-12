"""Future MLB salary scenarios preserve historical cash and use frozen-rule patterns."""
from unittest.mock import patch
import unittest
from dashboard.server import calculate
from etl.mlb_model import players, estimate
from etl.mlb_projection import salary_window, pattern, projection_inputs, project


class MlbFutureProjection(unittest.TestCase):
    def test_judge_salary_and_template_rotation(self):
        result = project(calculate,'592450','NY')
        self.assertEqual(result['included_years'],list(range(2027,2032)))
        self.assertEqual(result['salary'],200000000)
        self.assertEqual([r['template_year'] for r in result['annual']],[2025,2026,2025,2026,2025])
        self.assertTrue(all(r['tax_year']==2026 for r in result['annual']))
        self.assertEqual(result['annual'][0]['federal'],result['annual'][1]['federal'])
        self.assertEqual(result['annual'][0]['payroll'],result['annual'][1]['payroll'])
        self.assertEqual(result['annual'][0]['state_days'],result['annual'][2]['state_days'])
        self.assertAlmostEqual(result['salary'],result['remaining']+result['total_tax'])

    def test_no_deferred_timing_or_prorated_signing_bonus_added(self):
        ohtani=project(calculate,'660271','CA')
        self.assertEqual(ohtani['salary'],490000000)
        self.assertTrue(all(r['salary']==70000000 for r in ohtani['annual']))
        self.assertEqual(max(ohtani['included_years']),2033)
        historical=estimate(calculate,'660271','CA')
        self.assertEqual(historical['gross'],6000000)
        soto=project(calculate,'665742','NY')
        self.assertEqual(soto['annual'][0]['salary'],42500000)
        self.assertEqual(soto['conditional_years'],list(range(2030,2040)))

    def test_patterns_reconcile_and_never_repeat_postseason(self):
        for tid in {p['team_id'] for p in players().values()}:
            for year in [2025,2026]:
                cal=pattern(tid,year,False)
                self.assertEqual(cal['postseason_games'],0)
                self.assertGreaterEqual(cal['regular_games'],160)
        inputs,cal,_=projection_inputs('592450',2027,40000000,'NY')
        self.assertEqual(sum(inputs['days'].values())+inputs['unsourced'],len(cal['rows']))
        self.assertGreater(inputs['unsourced'],0)
        self.assertEqual(len(cal['rows']),len({r['date'] for r in cal['rows']}))

    def test_comparison_preserves_salary_and_federal_changes_state(self):
        ny=project(calculate,'592450','NY');fl=project(calculate,'592450','FL')
        self.assertEqual(ny['salary'],fl['salary'])
        self.assertNotEqual(ny['remaining'],fl['remaining'])
        for a,b in zip(ny['annual'],fl['annual']):
            self.assertEqual(a['federal'],b['federal']);self.assertEqual(a['payroll'],b['payroll'])

    def test_missing_salaries_are_excluded_not_zero(self):
        rows=dict(salary_window('592450'),annual=[dict(year=2027,salary=None,reason='Missing annual salary.')])
        with patch('etl.mlb_projection.salary_window',return_value=rows):
            result=project(lambda _:self.fail('Missing salary must not calculate'),'592450','FL')
        self.assertIsNone(result['salary']);self.assertIsNone(result['total_tax'])
        self.assertEqual(result['excluded'],[dict(year=2027,reason='Missing annual salary.')])

    def test_all_active_profiles_have_results_or_explicit_coverage(self):
        projected=0
        for pid in players():
            with self.subTest(player=pid):
                result=project(calculate,pid,'FL')
                if result['annual']:
                    projected+=1
                    self.assertAlmostEqual(result['salary'],result['remaining']+result['total_tax'],places=5)
                    self.assertTrue(all(r['year']>2026 and r['tax_year']==2026 for r in result['annual']))
                else:
                    self.assertTrue(result['reason'] or result['excluded'])
                    self.assertIsNone(result['remaining'])
        self.assertGreater(projected,100)

    def test_bad_inputs_and_canadian_residence_rejected(self):
        for args in [('bad','NY','single'),('592450','ON','single'),('592450','NY','bad')]:
            with self.assertRaises(ValueError):project(calculate,*args)

    def test_contract_wide_scenario_and_verified_signing_cash(self):
        for pid,total,start,end in [('592450',360000000,2023,2031),('660271',700000000,2024,2033),('665742',765000000,2025,2039)]:
            with self.subTest(player=pid):
                result=project(calculate,pid,'NY',full=True)
                self.assertEqual(result['salary'],total)
                self.assertEqual(result['included_years'],list(range(start,end+1)))
                self.assertAlmostEqual(result['salary'],result['total_tax']+result['remaining'])
                for row in result['annual']:
                    self.assertEqual(row['tax_year'],min(row['year'],2026))
        soto=project(calculate,'665742','NY',full=True)
        self.assertEqual(soto['annual'][0]['signing_cash'],75000000)
        self.assertEqual(soto['annual'][1]['signing_cash'],0)

    def test_contract_wide_coverage_for_every_profile(self):
        for pid in players():
            result=project(calculate,pid,'FL',full=True)
            with self.subTest(player=pid):
                if result['annual']:
                    self.assertAlmostEqual(result['salary'],sum(r['salary'] for r in result['annual']))
                    self.assertAlmostEqual(result['salary'],result['total_tax']+result['remaining'],places=5)
                else:self.assertTrue(result['reason'] or result['excluded'])
