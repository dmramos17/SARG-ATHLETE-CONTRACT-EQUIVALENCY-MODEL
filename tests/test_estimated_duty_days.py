import unittest
from etl.estimated_duty_days import estimate_calendar
from etl.contract_data import load_contracts
from etl.historical_taxes import sync_historical_taxes
from dashboard.server import calculate

class EstimatedDutyDays(unittest.TestCase):
    def test_calendar_conserves_days_and_has_no_duplicates(self):
        for team in ('NFL_NE','NFL_SEA','NFL_DEN'):
            result=estimate_calendar(team)
            self.assertEqual(result['total_days'],sum(result['state_days'].values())+result['unsourced_days'])
            dates=[r['date'] for r in result['calendar']]
            self.assertEqual(len(dates),len(set(dates)))
            self.assertTrue(all(d.startswith('2025-') for d in dates))
            self.assertTrue(all(r['source'] for r in result['calendar'] if r['evidence']=='documented team event'))

    def test_january_postseason_and_london_are_in_correct_jurisdictions(self):
        den=estimate_calendar('NFL_DEN');rows={r['date']:r for r in den['calendar']}
        self.assertEqual(rows['2025-01-12']['state'],'NY')
        self.assertIsNone(rows['2025-10-12']['state'])
        self.assertEqual(den['unsourced_days'],2)
        ne=estimate_calendar('NFL_NE');rows={r['date']:r for r in ne['calendar']}
        self.assertEqual(rows['2025-12-28']['state'],'NJ')
        self.assertEqual(rows['2025-08-13']['state'],'MN')
        self.assertEqual(rows['2025-08-15']['state'],'MN')

    def test_game_beats_weekly_rest_and_extra_travel_conserves_calendar(self):
        default=estimate_calendar('NFL_SEA');extra=estimate_calendar('NFL_SEA',travel_days=3,weekly_off_day=6)
        self.assertEqual(sum(r['event'].startswith('game') for r in default['calendar']),20)
        self.assertEqual(sum(r['event'].startswith('game') for r in extra['calendar']),20)
        self.assertGreater(extra['state_days']['CA'],default['state_days']['CA'])

    def test_individual_adjustments_change_denominator_and_evidence(self):
        base=estimate_calendar('NFL_SEA')
        adjusted=estimate_calendar('NFL_SEA',excluded_dates=['2025-09-14'],additional_days=['2025-06-10'],overrides={'2025-09-13':'WA'})
        self.assertEqual(adjusted['total_days'],base['total_days'])
        self.assertNotIn('PA',adjusted['state_days'])
        self.assertEqual(adjusted['evidence_counts']['user assumption'],2)

    def test_invalid_adjustments_are_rejected(self):
        for kwargs in ({'travel_days':4},{'travel_days':True},{'weekly_off_day':7},{'excluded_dates':['2026-01-01']},{'overrides':{'2025-06-01':'WA'}},{'overrides':{'2025-09-14':'ZZ'}}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                estimate_calendar('NFL_SEA',**kwargs)

    def test_all_historical_contracts_calculate_and_cash_reconciles(self):
        sync_historical_taxes()
        for contract in load_contracts():
            duty=estimate_calendar(contract['team_id'])
            result=calculate(dict(tax_year=2025,salary=contract['base_salary'],bonus=contract['signing_bonus_cash'],other_cash=contract['other_cash'],residence=contract['home_state'],days=duty['state_days'],unsourced=duty['unsourced_days']))
            self.assertEqual(result['gross'],contract['annual_cash'])
            self.assertEqual(result['tax_year'],2025)
            self.assertAlmostEqual(result['gross'],result['remaining']+result['total_tax'])
            self.assertEqual(result['national']['deduction'],15750)
            self.assertEqual(result['national']['social_security_base'],176100)

    def test_historical_philadelphia_rates_are_not_2026(self):
        sync_historical_taxes()
        result=calculate(dict(tax_year=2025,salary=100000,residence='TX',days={'PA':100},early_cash=50000,local_work={'PHL':{'early':50000,'late':50000}}))
        self.assertAlmostEqual(result['local']['total'],50000*(.0344+.0343))
        self.assertFalse(any('2026' in r['source'] and 'federal' in r['state'].lower() for r in result['sources']))

    def test_massachusetts_visitor_surtax_uses_sourced_income(self):
        sync_historical_taxes()
        result=calculate(dict(tax_year=2025,salary=2000000,residence='TX',days={'TX':99,'MA':1}))
        self.assertAlmostEqual(result['tax']['nonresident']['MA'],1000)

    def test_ohio_published_base_amount_is_preserved(self):
        sync_historical_taxes()
        result=calculate(dict(tax_year=2025,salary=125000,residence='TX',days={'OH':100}))
        self.assertAlmostEqual(result['tax']['nonresident']['OH'],2394.32+25000*.03125)

if __name__=='__main__':unittest.main()
