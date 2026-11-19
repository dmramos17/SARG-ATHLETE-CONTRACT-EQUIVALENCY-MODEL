"""Offer comparison and bounded after-tax equivalency use real team allocations."""
from copy import deepcopy
import unittest
from dashboard.server import calculate
from etl.offer_lab import run,normalize,catalog,work_plan,MAX_SALARY


def payload(league='NFL',mode='compare'):
    return dict(league=league,mode=mode,start_year=2027,
                offer_a=dict(team_id='NFL_BUF' if league=='NFL' else '147',annual_salaries=[10000000,20000000,30000000]),
                offer_b=dict(team_id='NFL_MIA' if league=='NFL' else '119',annual_salaries=[10000000,20000000,30000000]))


class OfferLab(unittest.TestCase):
    def test_catalog_covers_teams_and_both_modes_validate(self):
        self.assertEqual(len(catalog()['teams']['NFL']),32)
        self.assertEqual(len(catalog()['teams']['MLB']),30)
        self.assertEqual(normalize(payload())['a']['residence'],'NY')
        self.assertEqual(normalize(payload())['b']['residence'],'FL')

    def test_same_team_same_residence_has_identical_results(self):
        p=payload();p['offer_b']=deepcopy(p['offer_a'])
        result=run(calculate,p)
        self.assertEqual(result['take_home_difference'],0)
        self.assertEqual(result['offer_a'],result['offer_b'])

    def test_same_residence_different_team_still_changes_state_sourcing(self):
        p=payload();p['offer_a']['residence']='FL';p['offer_b']['residence']='FL'
        result=run(calculate,p);a,b=result['offer_a'],result['offer_b']
        self.assertNotEqual(a['state'],b['state'])
        self.assertNotEqual(a['annual'][0]['state_shares'],b['annual'][0]['state_shares'])
        self.assertEqual(a['federal'],b['federal']);self.assertEqual(a['payroll'],b['payroll'])

    def test_both_leagues_conserve_income_and_work_shares(self):
        for league in ['NFL','MLB']:
            result=run(calculate,payload(league))
            for offer in [result['offer_a'],result['offer_b']]:
                self.assertAlmostEqual(offer['gross'],offer['remaining']+offer['total_tax'],places=5)
                self.assertAlmostEqual(offer['total_tax'],sum(offer[k] for k in ['federal','payroll','state','local']),places=5)
                for year in offer['annual']:
                    self.assertEqual(year['tax_year'],2026)
                    self.assertAlmostEqual(sum(year['state_days'].values())+year['foreign_days'],year['duty_days'])
                    self.assertLessEqual(sum(year['state_shares'].values()),1+1e-9)
                    self.assertEqual(year['cash'],sum(year[k] for k in ['remaining','total_tax']))

    def test_mlb_repeats_reference_cycle_without_postseason(self):
        r=run(calculate,payload('MLB'))
        self.assertEqual([y['template_year'] for y in r['offer_a']['annual']],[2025,2026,2025])
        self.assertEqual(r['offer_a']['annual'][0]['state_shares'],r['offer_a']['annual'][2]['state_shares'])
        rows=work_plan('MLB','147',2027,'position',1)[0][0][0]
        self.assertTrue(rows)

    def test_break_even_recalculates_tax_in_both_leagues(self):
        for league in ['NFL','MLB']:
            p=payload(league,'breakeven');r=run(calculate,p);s=r['solver']
            self.assertTrue(s['converged']);self.assertLessEqual(abs(s['residual']),1)
            self.assertEqual(r['offer_a']['gross'],60000000)
            self.assertAlmostEqual(r['offer_b']['annual'][1]['cash'],2*r['offer_b']['annual'][0]['cash'],delta=.02)
            check=payload(league);check['offer_b']['annual_salaries']=[y['cash'] for y in r['offer_b']['annual']]
            self.assertAlmostEqual(run(calculate,check)['offer_b']['remaining'],r['offer_a']['remaining'],delta=1)

    def test_flat_target_structure_and_identical_team_equivalence(self):
        p=payload(mode='breakeven');p['offer_b']['team_id']='NFL_BUF'
        r=run(calculate,p);self.assertAlmostEqual(r['offer_b']['gross'],r['offer_a']['gross'],delta=.01)
        p['structure']='flat';r=run(calculate,p)
        self.assertTrue(r['solver']['converged'])
        self.assertEqual(len({y['cash'] for y in r['offer_b']['annual']}),1)

    def test_zero_salary_year_is_zero_not_a_tax_engine_error(self):
        p=payload();p['offer_a']['annual_salaries']=[0,20000000,30000000]
        r=run(calculate,p);year=r['offer_a']['annual'][0]
        self.assertEqual(year['cash'],0);self.assertEqual(year['total_tax'],0);self.assertEqual(year['remaining'],0)

    def test_input_validation_rejects_nonfinite_negative_and_wrong_teams(self):
        cases=[]
        for value in [float('nan'),float('inf'),-1,True,MAX_SALARY+1,'1000000']:
            p=payload();p['offer_a']['annual_salaries'][0]=value;cases.append(p)
        for key,value in [('league','NBA'),('mode','x'),('start_year',2026),('travel_days',4),('filing','x'),('mlb_role','x'),('structure','x')]:
            p=payload();p[key]=value;cases.append(p)
        p=payload();p['offer_b']['team_id']='147';cases.append(p)
        p=payload();p['offer_a']['annual_salaries']=[0]*3;cases.append(p)
        p=payload();p['offer_b']['annual_salaries']=[1];cases.append(p)
        for p in cases:
            with self.subTest(case=p):
                with self.assertRaises(ValueError):normalize(p)

    def test_toronto_needs_explicit_us_residence_assumption(self):
        p=payload('MLB');p['offer_a']['team_id']='141'
        with self.assertRaises(ValueError):normalize(p)
        p['offer_a']['residence']='NY';r=run(calculate,p)
        self.assertEqual(r['offer_a']['residence'],'NY')
        self.assertGreater(r['offer_a']['annual'][0]['foreign_days'],50)

    def test_unreachable_target_is_reported_instead_of_false_match(self):
        p=payload(mode='breakeven');p['offer_a'].update(team_id='NFL_MIA',residence='FL',annual_salaries=[MAX_SALARY]);p['offer_b'].update(team_id='NFL_LAR',residence='CA')
        with self.assertRaisesRegex(ValueError,'cannot be matched'):
            run(calculate,p)

    def test_reporting_group_changes_mlb_spring_allocation(self):
        p=payload('MLB');position=run(calculate,p);p['mlb_role']='pitcher_catcher';early=run(calculate,p)
        self.assertGreater(early['offer_a']['annual'][0]['duty_days'],position['offer_a']['annual'][0]['duty_days'])


    def test_every_team_has_a_calculable_team_specific_offer(self):
        for league in ['NFL','MLB']:
            for team in catalog()['teams'][league]:
                with self.subTest(league=league,team=team['name']):
                    p=payload(league);p['offer_a'].update(team_id=team['id'],residence='FL',annual_salaries=[1000000]);p['offer_b'].update(residence='FL',annual_salaries=[1000000])
                    r=run(calculate,p)
                    self.assertEqual(r['offer_a']['gross'],1000000)
                    self.assertTrue(r['offer_a']['annual'][0]['state_days'])
