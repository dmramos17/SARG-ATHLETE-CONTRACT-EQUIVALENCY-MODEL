"""Recent homepage cards use saved signing years, never contract start as a date."""
import unittest
from etl.recent_contracts import recent_contracts
from etl.player_directory import load_directory
from etl.mlb_interface import catalog


class RecentContracts(unittest.TestCase):
    def test_latest_three_years_exclude_old_high_value_and_unknown_dates(self):
        rows=[dict(id='old',value=999,signing_year=2022),dict(id='new',value=100,signing_year=2025),dict(id='middle',value=200,signing_year=2024),dict(id='unknown',value=1000,signing_year=None)]
        result=recent_contracts(rows)
        self.assertEqual(result['ids'],['middle','new'])
        self.assertEqual((result['start_year'],result['end_year']),(2023,2025))
        self.assertEqual(recent_contracts([])['ids'],[])

    def test_nfl_features_more_than_one_signing_year(self):
        d=load_directory();cards=[p for p in d['players'] if p['id'] in d['featured_ids']]
        self.assertEqual(len(cards),6)
        self.assertGreater(len({p['contract']['year_signed'] for p in cards}),1)
        self.assertTrue(all(p['contract']['year_signed']>=d['metadata']['recent_start_year'] for p in cards))

    def test_mlb_cards_have_known_signing_dates_and_are_not_fixed_examples(self):
        d=catalog();by_id={p['id']:p for p in d['players']}
        self.assertEqual(len(d['featured_ids']),6)
        self.assertNotEqual(d['featured_ids'],['660271','592450','665742'])
        values=[]
        for pid in d['featured_ids']:
            c=by_id[pid]['contract'];values.append(c['headline_value'])
            self.assertGreaterEqual(c['signing_year'],d['metadata']['recent_start_year'])
            self.assertLessEqual(c['signing_date'],d['metadata']['as_of'])
        self.assertEqual(values,sorted(values,reverse=True))
