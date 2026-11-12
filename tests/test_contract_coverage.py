"""Regression coverage for headline/term/bonus mismatches across the dashboard."""
import unittest
from dashboard.server import calculate
from etl.mlb_model import players,contract_window
from etl.mlb_interface import catalog
from etl.mlb_projection import project,salary_window,signing_payments
from etl.mlb_contract_terms import boundaries
from etl.player_comparison import directory,summary
from etl.league_projection import project_player,_project_player,data as nfl_data


class ContractCoverage(unittest.TestCase):
    def test_bichette_three_year_bonus_and_option_reconcile(self):
        result=project(calculate,'666182','NY',full=True)
        self.assertEqual(result['included_years'],[2026,2027,2028])
        self.assertEqual([r['salary'] for r in result['annual']],[42000000]*3)
        self.assertEqual([r['signing_cash'] for r in result['annual']],[40000000,0,0])
        self.assertEqual(result['salary'],126000000)
        self.assertEqual(result['conditional_years'],[2028])
        self.assertTrue(result['complete']);self.assertTrue(result['reconciles_headline'])
        self.assertEqual(result['headline_gap'],0)
        self.assertAlmostEqual(result['salary'],result['remaining']+result['total_tax'])
        self.assertGreater(result['remaining'],60000000)

    def test_metadata_and_comparison_use_same_correct_window(self):
        bo=next(p for p in catalog()['players'] if p['id']=='666182')
        self.assertEqual(bo['contract']['end_year'],2028)
        self.assertEqual(bo['contract']['years'],3)
        self.assertEqual(contract_window('666182')['end'],2028)
        out=summary(calculate,'MLB',next(p for p in directory('MLB') if p['id']=='666182'))
        self.assertTrue(out['complete']);self.assertEqual(out['income'],126000000)
        self.assertAlmostEqual(out['annual_take_home'],out['remaining']/3)

    def test_extra_club_options_do_not_inflate_the_headline_deal(self):
        example={'description':'5 yr, $20.5M (2023-27), 2028-29 club options','summary':{'startSeason':2023,'endSeason':2027,'endSeasonAll':2029,'YearsTotal':5}}
        self.assertEqual(boundaries(example),(2023,2027))
        example['description']='3 yr, $126M (2026-28), 2027-28 player options'
        example['summary'].update(startSeason=2026,endSeason=2027,endSeasonAll=2028,YearsTotal=3)
        self.assertEqual(boundaries(example),(2026,2028))

    def test_unallocated_bonus_cannot_be_complete_even_with_all_years(self):
        pid=next(pid for pid in players() if signing_payments(pid)['unresolved']>0 and project(calculate,pid,'FL',full=True)['year_complete'])
        result=project(calculate,pid,'FL',full=True)
        self.assertTrue(result['year_complete']);self.assertFalse(result['complete'])
        self.assertGreater(result['unallocated_signing_bonus'],0)
        self.assertTrue(any('signing bonus' in n for n in result['coverage_notes']))

    def test_all_mlb_complete_flags_require_full_dollar_and_year_coverage(self):
        for pid in players():
            result=project(calculate,pid,'FL',full=True)
            with self.subTest(player=pid):
                if result['complete']:
                    self.assertFalse(result['excluded']);self.assertTrue(result['reconciles_headline'])
                    self.assertEqual(result['unallocated_signing_bonus'],0)
                    self.assertAlmostEqual(result['salary'],result['headline_value'],delta=1)
                elif result['annual']:
                    self.assertTrue(result['excluded'] or result['coverage_notes'])

    def test_nfl_mismatch_flag_changes_no_forecast_amounts(self):
        pid=next(pid for pid,c in nfl_data()['players'].items() if not c['missing_years'] and not c['reconciles_headline'])
        original=_project_player(calculate,pid);result=project_player(calculate,pid)
        self.assertEqual({k:result[k] for k in original},original)
        self.assertFalse(result['coverage_complete']);self.assertTrue(result['coverage_issues'])
        self.assertNotEqual(result['headline_gap'],0)
