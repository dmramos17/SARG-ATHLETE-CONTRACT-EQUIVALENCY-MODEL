"""Cash conservation, rotations, calendar boundaries, and projection assumptions."""
import unittest
from dashboard.server import calculate
from etl.contract_projection import source_data,opponent_slots,season_variants,calendar,model_inputs,project

class ContractProjection(unittest.TestCase):
    def test_cash_components_and_term(self):
        data=source_data()
        self.assertEqual([c['year'] for c in data['cash']],list(range(2025,2031)))
        self.assertEqual(sum(c['cash'] for c in data['cash']),330000000)
        for c in data['cash']:
            self.assertEqual(c['cash'],sum(c[k] for k in ('base_salary','signing_bonus','roster_bonus','workout_bonus','unclassified_cash')))
            self.assertGreaterEqual(c['unclassified_cash'],0)

    def test_rotations_and_division_home_away(self):
        for year in range(2027,2031):
            slots=opponent_slots(year)
            self.assertEqual(len(slots),17)
            self.assertEqual(sum(len(s['opponent'])==4 for s in slots),3)
            for op in ('MIA','NE','NYJ'):
                self.assertEqual(sorted(s['home'] for s in slots if s['opponent']==op),[False,True])
            self.assertEqual(sum(len(s['opponent'])<=3 for s in slots),14)

    def test_published_schedules_and_actual_venues(self):
        for year in (2025,2026):
            schedule=season_variants(year)[0]
            self.assertEqual(len(schedule),17)
            jets=[g for g in schedule if g['opponent']=='NYJ' and not g['home']]
            self.assertEqual(jets[0]['state'],'NJ')
            self.assertTrue(any(g['date'].startswith(str(year+1)) for g in schedule))

    def test_calendar_uses_previous_season_january_once(self):
        rows=calendar(2027,season_variants(2026)[0],season_variants(2027)[0])
        self.assertEqual(len(rows),len({r['date'] for r in rows}))
        self.assertTrue(all(r['date'].startswith('2027-') for r in rows))
        self.assertEqual(next(r for r in rows if r['date']=='2027-01-03')['state'],'FL')
        self.assertFalse(any('2028-' in r['date'] for r in rows))

    def test_known_2026_playoffs_and_preseason_are_included(self):
        rows=calendar(2026,season_variants(2025)[0],season_variants(2026)[0])
        self.assertEqual(next(r for r in rows if r['date']=='2026-01-17')['state'],'CO')
        self.assertEqual(next(r for r in rows if r['date']=='2026-08-22')['state'],'OH')

    def test_qualifying_bonus_reclassifies_without_changing_cash(self):
        cash=source_data()['cash'][0];rows=calendar(2025,(),())
        base=model_inputs(cash,rows,'NY','single',False)
        qualified=model_inputs(cash,rows,'NY','single',True)
        self.assertEqual(qualified['bonus'],56745000)
        self.assertEqual(base['salary']+base['bonus'],qualified['salary']+qualified['bonus'])

    def test_projection_totals_ranges_and_frozen_law(self):
        out=project(calculate)
        self.assertEqual(out['gross'],330000000)
        self.assertEqual(out['tax_rule_year'],2025)
        self.assertAlmostEqual(out['gross'],out['remaining']+out['total_tax'])
        self.assertAlmostEqual(out['remaining'],sum(r['remaining'] for r in out['annual']))
        for r in out['annual']:
            self.assertLessEqual(r['low_remaining'],r['remaining']+.01)
            self.assertLessEqual(r['remaining'],r['high_remaining']+.01)
            self.assertAlmostEqual(r['total_tax'],r['federal']+r['payroll']+r['state']+r['local'])
        self.assertIn('frozen 2025',' '.join(out['notes']))

    def test_alternate_assumptions_and_validation(self):
        out=project(calculate,'TX','mfj',True,2)
        self.assertEqual(out['gross'],330000000)
        self.assertGreater(out['remaining'],project(calculate)['remaining'])
        with self.assertRaises(ValueError):project(calculate,travel_days=4)
        with self.assertRaises(ValueError):project(calculate,residence='XX')
