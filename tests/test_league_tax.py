"""League-wide model coverage, real venue exceptions, and cash-data guardrails."""
from collections import Counter
import unittest
from dashboard.server import calculate
from etl.estimated_duty_days import games,teams,estimate_calendar,estimate_player_calendar
from etl.historical_taxes import sync_historical_taxes
from etl.player_directory import load_directory
from etl.player_tax import tax_contract,with_tax_info

class LeagueTax(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sync_historical_taxes()
        cls.players=load_directory()['players']

    def test_complete_calendar_year_schedule(self):
        self.assertEqual(len(games()),334)
        self.assertEqual(Counter(g['stage'] for g in games()),dict(PRE=49,REG=272,POST=13))
        self.assertEqual(len({g['event_id'] for g in games()}),334)
        self.assertEqual(len(teams()),32)
        self.assertEqual(sum(g['state'] is None for g in games()),7)

    def test_all_32_team_calendars_conserve_dates(self):
        for team in teams():
            with self.subTest(team=team):
                result=estimate_calendar(team)
                self.assertEqual(result['total_days'],sum(result['state_days'].values())+result['unsourced_days'])
                self.assertEqual(result['total_days'],len({r['date'] for r in result['calendar']}))
                self.assertTrue(all(r['date'].startswith('2025-') for r in result['calendar']))

    def test_super_bowl_and_relocated_playoff_use_actual_venues(self):
        phi={r['date']:r for r in estimate_calendar('NFL_PHI')['calendar']}
        self.assertEqual(phi['2025-02-09']['state'],'LA')
        lar={r['date']:r for r in estimate_calendar('NFL_LAR')['calendar']}
        self.assertEqual(lar['2025-01-13']['state'],'AZ')

    def test_foreign_games_use_no_us_state_and_model_continuous_stay(self):
        minimum=estimate_calendar('NFL_MIN');rows={r['date']:r for r in minimum['calendar']}
        self.assertIsNone(rows['2025-09-28']['state'])
        self.assertIsNone(rows['2025-10-02']['state'])
        self.assertIsNone(rows['2025-10-05']['state'])
        self.assertEqual(rows['2025-10-02']['evidence'],'modeled')

    def test_previous_team_is_used_for_winter_and_rookies_have_no_invented_winter(self):
        darnold=next(p for p in self.players if p['name']=='Sam Darnold')
        rows={r['date']:r for r in estimate_player_calendar(darnold)['calendar']}
        self.assertEqual(rows['2025-01-13']['team_id'],'NFL_MIN')
        self.assertEqual(rows['2025-01-13']['state'],'AZ')
        self.assertEqual(rows['2025-09-07']['team_id'],'NFL_SEA')
        ward=next(p for p in self.players if p['name']=='Cam Ward')
        self.assertFalse(any(r['date']<'2025-03-01' for r in estimate_player_calendar(ward)['calendar']))

    def test_missing_and_zero_cash_require_verified_input(self):
        unavailable=[p for p in self.players if p['season_cash'] is None or p['season_cash']<=0]
        self.assertEqual(len(unavailable),76)
        for player in unavailable:
            row=tax_contract(player);view=with_tax_info(player)
            self.assertTrue(row['needs_cash'])
            self.assertIsNone(row['annual_cash'])
            self.assertFalse(view['tax_ready'])
            self.assertIsNotNone(view['estimate_id'])  # Tax page still exists.
            self.assertGreater(estimate_player_calendar(player)['total_days'],0)

    def test_imported_cash_is_not_derived_from_cap_or_apy(self):
        allen=next(p for p in self.players if p['name']=='Josh Allen')
        row=tax_contract(allen)
        self.assertEqual(row['annual_cash'],58000000)
        self.assertEqual(row['base_salary'],58000000)
        self.assertEqual(row['signing_bonus_cash'],0)
        self.assertEqual(row['bonus_assumption'],'conditional')
        self.assertNotEqual(row['annual_cash'],row['cap_charge'])
        self.assertNotEqual(row['annual_cash'],row['aav'])
        self.assertFalse(row['reviewed_snapshot'])

    def test_every_player_with_positive_cash_calculates(self):
        ready=0
        for player in self.players:
            row=tax_contract(player)
            if row['needs_cash']:continue
            ready+=1
            with self.subTest(player=player['name']):
                duty=estimate_player_calendar(player)
                # Include supported city/statewide local bases and payment halves
                # in the sweep, not only federal and state calculations.
                gross=row['annual_cash'];service=row['base_salary']+row['other_cash']
                early=round(gross*sum(d['date']<'2025-07-01' for d in duty['calendar'])/duty['total_days'],2)
                local_days=Counter()
                for day in duty['calendar']:
                    city=('MDNR' if row['home_state']!='MD' else None) if day['state']=='MD' else day['locality']
                    if city in ('PHL','CIN','KCM','MDNR'):
                        local_days[(city,'early' if day['date']<'2025-07-01' else 'late')]+=1
                work={}
                for (city,period),count in local_days.items():
                    amounts=work.setdefault(city,dict(early=0,late=0))
                    amounts[period]=min(round(service*count/duty['total_days'],2),early if period=='early' else gross-early)
                out=calculate(dict(tax_year=2025,salary=row['base_salary'],bonus=row['signing_bonus_cash'],
                                   other_cash=row['other_cash'],residence=row['home_state'],
                                   days=duty['state_days'],unsourced=duty['unsourced_days'],
                                   early_cash=early,local_work=work))
                self.assertAlmostEqual(out['gross'],row['annual_cash'])
                self.assertAlmostEqual(out['gross'],out['remaining']+out['total_tax'])
                self.assertGreater(out['total_tax'],0)
                self.assertLess(out['total_tax'],out['gross'])
        self.assertEqual(ready,2181)

if __name__=='__main__':unittest.main()
