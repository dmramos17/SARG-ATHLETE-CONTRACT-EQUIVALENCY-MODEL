"""Every-team ranking for one Offer Lab offer (etl/offer_rank.py)."""
import unittest

from dashboard.server import calculate
from etl.offer_lab import catalog
from etl.offer_rank import rank


def mlb_team(code):
    return next(t for t in catalog()['teams']['MLB'] if t['code'] == code)


class OfferRank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = dict(league='MLB', start_year=2027,
                           offer_a=dict(team_id=mlb_team('NYY')['id'], annual_salaries=[20_000_000] * 3))
        cls.result = rank(calculate, cls.payload)

    def test_ranks_every_us_team_and_excludes_toronto(self):
        codes = {r['team']['code'] for r in self.result['rows']}
        self.assertEqual(len(codes), len(catalog()['teams']['MLB']) - 1)
        self.assertEqual([e['team']['code'] for e in self.result['excluded']], ['TOR'])

    def test_reference_team_matches_itself(self):
        ref = [r for r in self.result['rows'] if r['is_reference']]
        self.assertEqual(len(ref), 1)
        self.assertAlmostEqual(ref[0]['take_home_difference'], 0, places=2)
        self.assertLessEqual(abs(ref[0]['breakeven_difference']), 1)

    def test_sorted_with_shared_ranks_and_converged_breakevens(self):
        rows = self.result['rows']
        self.assertEqual([r['take_home'] for r in rows], sorted((r['take_home'] for r in rows), reverse=True))
        self.assertEqual(rows[0]['rank'], 1)
        for r in rows:
            self.assertTrue(r['converged'], r['team']['code'])
            # Teams with more take-home for the same salaries need a lower break-even salary.
            self.assertEqual(r['take_home_difference'] > 1, r['breakeven_difference'] < -1)

    def test_fixed_residence_rule_uses_offer_a_residence(self):
        fixed = rank(calculate, dict(self.payload, residence_rule='fixed'))
        self.assertTrue(all(r['residence'] == 'NY' for r in fixed['rows']))

    def test_repeat_request_is_cached(self):
        self.assertIs(rank(calculate, self.payload), self.result)

    def test_validation(self):
        with self.assertRaises(ValueError):
            rank(calculate, dict(self.payload, residence_rule='moon'))
        with self.assertRaises(ValueError):
            rank(calculate, dict(self.payload, offer_a=None))


if __name__ == '__main__':
    unittest.main()