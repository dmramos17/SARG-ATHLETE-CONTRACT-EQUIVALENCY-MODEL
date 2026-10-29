"""Cash-timing and provenance safeguards for the three reported MLB contracts."""
import unittest
from etl.mlb_interface import catalog

class MlbContractData(unittest.TestCase):
    def setUp(self):
        self.players={p['id']:p for p in catalog()['players']}

    def test_contract_values_reconcile_to_scheduled_cash(self):
        for identity,value in [('660271',700000000),('592450',360000000),('665742',765000000)]:
            c=self.players[identity]['contract']
            self.assertEqual(c['headline_value'],value)
            self.assertEqual(sum(r['salary_cash']+r['signing_cash'] for r in c['annual']),value)
            self.assertEqual(len(c['annual']),len({r['year'] for r in c['annual']}))

    def test_ohtani_deferrals_are_not_paid_twice(self):
        c=self.players['660271']['contract']
        service=[r for r in c['annual'] if r['year']<=2033]
        deferred=[r for r in c['annual'] if r['year']>=2034]
        self.assertEqual(sum(r['reported_cash'] for r in service),20000000)
        self.assertEqual(sum(r['reported_cash'] for r in deferred),680000000)
        self.assertEqual([r['year'] for r in deferred],list(range(2034,2044)))
        self.assertTrue(all(r['reported_cash']==2000000 for r in service))

    def test_soto_incentives_and_signing_cash_remain_separate(self):
        c=self.players['665742']['contract']
        self.assertEqual(sum(r['signing_cash'] for r in c['annual']),75000000)
        self.assertEqual(sum(r['listed_incentives'] for r in c['annual']),500000)
        self.assertEqual(c['reported_cash_total'],765500000)
        self.assertEqual(c['scheduled_cash_total'],765000000)
        self.assertEqual(next(r for r in c['annual'] if r['year']==2027)['salary_cash'],42500000)
        self.assertTrue(any('opt-out' in n.lower() for n in c['notes']))

    def test_judge_has_nine_cash_years(self):
        c=self.players['592450']['contract']
        self.assertEqual([r['year'] for r in c['annual']],list(range(2023,2032)))
        self.assertTrue(all(r['reported_cash']==40000000 for r in c['annual']))
        self.assertIsNone(c['signing_bonus']) # N/A is not a verified zero-dollar signing bonus.

    def test_contract_data_does_not_enable_unbuilt_tax_model(self):
        for player in self.players.values():
            self.assertEqual(player['tax_status'],'coming_soon')
            self.assertEqual(player['contract_status'],'reported_snapshot')
            self.assertTrue(player['contract']['source_url'].startswith('https://www.spotrac.com/mlb/player/'))
            self.assertNotIn('estimated_tax',player['contract'])
