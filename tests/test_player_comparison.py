"""Recommendations use deal terms; comparisons always use fixed team residence."""
import unittest
from unittest.mock import patch
from dashboard.server import calculate
from etl.player_comparison import directory, suggestions, compare


class PlayerComparison(unittest.TestCase):
    def test_suggestions_same_league_exclude_self_and_are_ranked(self):
        for league,pid in [('NFL','00-0034857'),('MLB','592450')]:
            result=suggestions(league,pid)
            self.assertEqual(len(result),6)
            self.assertEqual(len({r['id'] for r in result}),6)
            self.assertTrue(all(r['league']==league and r['id']!=pid and r['headline_value'] and r['years'] for r in result))
            self.assertEqual([r['similarity_score'] for r in result],sorted(r['similarity_score'] for r in result))

    def test_value_and_term_both_affect_recommendations(self):
        rows=[dict(id='a',name='A',headline_value=100,years=5),dict(id='b',name='B',headline_value=100,years=10),dict(id='c',name='C',headline_value=90,years=5)]
        with patch('etl.player_comparison.directory',return_value=rows):
            self.assertEqual([r['id'] for r in suggestions('NFL','a')],['c','b'])
        rows[0]['headline_value']=None
        with patch('etl.player_comparison.directory',return_value=rows):self.assertEqual(suggestions('NFL','a'),[])

    def test_mlb_fixed_residence_contract_totals_and_ratios(self):
        result=compare(calculate,'MLB','592450','660271')
        judge,ohtani=result['players']
        self.assertEqual((judge['residence'],ohtani['residence']),('NY','CA'))
        self.assertEqual((judge['income'],ohtani['income']),(360000000,700000000))
        for p in result['players']:
            self.assertAlmostEqual(p['income'],p['remaining']+p['total_tax'])
            self.assertAlmostEqual(p['take_home_percentage'],100*p['remaining']/p['income'])
            self.assertAlmostEqual(p['annual_take_home'],p['remaining']/len(p['included_years']))

    def test_nfl_uses_existing_forecast_and_fixed_team_state(self):
        right=suggestions('NFL','00-0034857')[0]['id']
        result=compare(calculate,'NFL','00-0034857',right)
        allen=result['players'][0]
        self.assertEqual(allen['residence'],'NY')
        self.assertEqual(allen['income'],330000000)
        self.assertEqual(allen['included_years'],list(range(2025,2031)))

    def test_canadian_base_stays_unavailable(self):
        toronto=next(p for p in directory('MLB') if not p['residence'])
        result=compare(calculate,'MLB','592450',toronto['id'])['players'][1]
        self.assertIsNone(result['remaining']);self.assertIsNone(result['take_home_percentage'])
        self.assertTrue(any('Canadian' in n for n in result['notes']))

    def test_rejects_invalid_cross_league_and_duplicate_choices(self):
        for args in [('NBA','x','y'),('MLB','592450','592450'),('NFL','592450','660271')]:
            with self.assertRaises(ValueError):compare(calculate,*args)
