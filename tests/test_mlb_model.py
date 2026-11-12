"""Boundary tests for MLB source coverage, cash timing and historical sourcing."""
from collections import Counter
from unittest.mock import patch
import math
import unittest
from dashboard.server import calculate
from etl.mlb_interface import catalog
from etl.mlb_model import (SUPPORTED_YEARS, data, players, cash_index, games_index,
                           schedule_data, calendar, year_coverage, estimate, calculation_inputs, contract_window)

class MlbKnownSchedules(unittest.TestCase):
    def test_roster_is_unique_and_covers_every_mlb_team(self):
        roster=catalog()['players']
        self.assertEqual(len(roster),len({p['id'] for p in roster}))
        self.assertEqual(len({p['team_id'] for p in roster}),30)
        self.assertGreater(len(roster),750)
        self.assertTrue(all(p['roster_status']=='Active' for p in roster))

    def test_every_imported_team_schedule_reconciles_with_official_standings(self):
        for year,counts in schedule_data()['metadata']['regular_game_counts'].items():
            self.assertEqual(len(counts),30)
            for tid,expected in counts.items():
                actual=sum(g['stage']=='R' for g in games_index()[tid,int(year)])
                self.assertEqual(actual,expected,(year,tid))

    def test_doubleheaders_are_one_date_and_foreign_days_stay_in_denominator(self):
        inputs,cal=calculation_inputs('592450',2025,'NY')
        dates=[r['date'] for r in cal['rows']]
        self.assertEqual(len(dates),len(set(dates)))
        self.assertTrue(any(len(r['games'])>1 for r in cal['rows']))
        self.assertGreater(inputs['unsourced'],0)
        self.assertEqual(sum(inputs['days'].values())+inputs['unsourced'],len(dates))

    def test_real_venues_preserve_relocations_and_international_games(self):
        for tid,expected in [('133','CA'),('139','FL')]:
            games=[g for g in games_index()[tid,2025] if g['stage']=='R' and g['home']==tid]
            self.assertTrue(any(g['state']==expected for g in games))
        games=games_index()['119',2025]
        self.assertTrue(any(g['country']=='Japan' and g['state'] is None for g in games))

    def test_multi_team_years_are_excluded_instead_of_using_current_team(self):
        pid,year=next((p,y) for p,years in data()['memberships'].items() for y,clubs in years.items()
                      if len(clubs)>1 and (p,int(y)) in cash_index() and int(y) in contract_window(p)['years'])
        self.assertIn('Multiple teams',year_coverage(pid,int(year)))
        with self.assertRaises(ValueError):calculation_inputs(pid,int(year),'FL')

    def test_missing_cash_stays_missing(self):
        pid=next(p for p in players() if all((p,y) not in cash_index() for y in SUPPORTED_YEARS))
        result=estimate(calculate,pid,'FL')
        self.assertIsNone(result['gross'])
        self.assertIsNone(result['total_tax'])
        self.assertIsNone(result['remaining'])
        self.assertFalse(result['annual'])

    def test_ohtani_cash_is_not_aav_and_no_deferred_future_taxes(self):
        result=estimate(calculate,'660271','CA')
        self.assertEqual(result['gross'],6000000)
        self.assertEqual(result['included_years'],[2024,2025,2026])
        self.assertFalse(result['future_taxes'])
        self.assertTrue(all(r['cash']==2000000 for r in result['annual']))
        with self.assertRaises(ValueError):calendar('119',2027)

    def test_each_year_uses_its_own_rules_and_federal_payroll_stay_residence_independent(self):
        ny=estimate(calculate,'592450','NY');fl=estimate(calculate,'592450','FL')
        for a,b in zip(ny['annual'],fl['annual']):
            self.assertEqual(a['federal_tax_year'],a['year'])
            self.assertEqual(a['federal'],b['federal'])
            self.assertEqual(a['payroll'],b['payroll'])
            self.assertEqual(a['cash'],b['cash'])
            self.assertAlmostEqual(a['remaining']+a['total_tax'],a['cash'])
        self.assertNotEqual(ny['annual'][0]['federal'],ny['annual'][1]['federal'])
        self.assertNotEqual(ny['total_tax'],fl['total_tax'])

    def test_malformed_inputs_fail_and_canada_is_not_treated_as_a_no_tax_state(self):
        for pid,state,filing in [('bad','FL','single'),('592450','ON','single'),('592450','NY','bad')]:
            with self.assertRaises(ValueError):estimate(calculate,pid,state,filing)

    def test_estimated_spring_reporting_dates_differ_by_role(self):
        pitchers=calendar('147',2025,True);position=calendar('147',2025,False)
        self.assertLess(pitchers['start'],position['start'])
        self.assertGreater(len(pitchers['rows']),len(position['rows']))

    def test_incomplete_schedule_fails_closed(self):
        original=games_index()
        incomplete=dict(original)
        incomplete['147',2025]=[g for g in original['147',2025] if g['stage']!='R'][::]
        with patch('etl.mlb_model.games_index',return_value=incomplete):
            self.assertIn('standings',year_coverage('592450',2025))

    def test_all_active_players_have_finite_reconciled_results_or_explicit_exclusions(self):
        for p in players().values():
            result=estimate(calculate,p['id'],p['base_state'] or 'NY')
            window=contract_window(p['id'])
            self.assertEqual(len(result['annual'])+len(result['excluded']),len(window['years']))
            self.assertTrue(set(result['included_years']).issubset(window['years']))
            self.assertTrue(all(y<=2026 for y in result['included_years']))
            for row in result['annual']:
                for field in ('cash','federal','payroll','state','local','total_tax','remaining'):
                    self.assertTrue(math.isfinite(row[field]),(p['id'],field))
                self.assertAlmostEqual(row['remaining']+row['total_tax'],row['cash'])
                self.assertEqual(sum(row['state_days'].values())+row['foreign_days'],row['duty_days'])

    def test_judge_starts_with_his_2023_contract_and_stops_at_2026(self):
        result=estimate(calculate,'592450','NY')
        self.assertEqual(result['included_years'],[2023,2024,2025,2026])
        self.assertEqual(result['gross'],160000000)
        self.assertFalse(result['excluded'])
        y2023=result['annual'][0]
        # Independent IRS 2023 high-income worksheet: 37% less $39,668.
        self.assertAlmostEqual(y2023['federal'],(40000000-13850)*.37-39668)
        self.assertAlmostEqual(y2023['payroll'],160200*.062+40000000*.0145+(40000000-200000)*.009)
        self.assertFalse(y2023['local_supported'])

    def test_stanton_uses_his_historical_miami_club_and_the_2020_shutdown(self):
        result=estimate(calculate,'519317','NY')
        self.assertEqual(result['included_years'],list(range(2015,2027)))
        self.assertTrue(all(r['team_id']=='146' for r in result['annual'][:3]))
        row=next(r for r in result['annual'] if r['year']==2020)
        self.assertEqual(row['regular_games'],60)
        self.assertEqual(row['cash'],9629630) # reported prorated cash, not a full-year salary
        self.assertFalse(any('2020-03-12'<r['date']<'2020-07-01' for r in row['calendar']))

    def test_previous_contract_cash_does_not_leak_into_new_deals(self):
        self.assertEqual(estimate(calculate,'665742','NY')['included_years'],[2025,2026])
        self.assertNotIn(2024,contract_window('665742')['years'])
        p=next(p for p in catalog()['players'] if p['contract_window']['start']==2026 and p['tax_years'])
        self.assertEqual(p['tax_years'],[2026])

    def test_postponed_rows_do_not_displace_the_real_played_fixture(self):
        for year in (2020,2021):
            for tid in ('108','147'):
                self.assertTrue(all('postpon' not in g['status'].lower() for g in games_index()[tid,year]))

    def test_historical_federal_regimes_and_exemption_phaseout(self):
        from etl.mlb_historical_taxes import personal_exemption,federal_history
        self.assertEqual(federal_history()['2015']['rates'][-1],.396)
        self.assertEqual(federal_history()['2023']['rates'][-1],.37)
        self.assertEqual(personal_exemption(2015,'single',100000),4000)
        self.assertEqual(personal_exemption(2015,'single',6550000),0)
        self.assertEqual(personal_exemption(2023,'mfj',100000),0)

if __name__=='__main__':unittest.main()
