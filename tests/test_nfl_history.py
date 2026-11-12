"""Historical NFL estimates do not alter existing forecast results."""
import unittest
from unittest.mock import patch
from dashboard.server import calculate
from etl.league_projection import data, project_player, _project_player
from etl.nfl_history import contract_history


class NFLHistory(unittest.TestCase):
    def test_allen_forecast_preserved_and_history_capped(self):
        original = _project_player(calculate, '00-0034857')
        result = project_player(calculate, '00-0034857')
        self.assertEqual({k:result[k] for k in original}, original)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['year_end'], 2030)
        self.assertEqual(result['gross'], 330000000)
        self.assertEqual(result['history']['included_years'], [2025, 2026])
        self.assertEqual(result['history']['gross'], 113000000)
        self.assertAlmostEqual(result['history']['gross'], result['history']['total_tax'] + result['history']['remaining'])

    def test_year_specific_rules_and_unsupported_local_not_backfilled(self):
        player_id = next(k for k,c in data()['players'].items() if c['year_signed'] == 2020)
        seen = []
        def recording(inputs):
            seen.append(inputs)
            return calculate(inputs)
        result = contract_history(recording, player_id, 'FL')
        self.assertEqual(result['year_start'], 2020)
        self.assertTrue(any(i['tax_year'] == 2020 for i in seen))
        for inputs in seen:
            if inputs['tax_year'] < 2025:
                self.assertEqual(inputs['local_work'], {})
        for row in result['annual']:
            self.assertLessEqual(row['year'], 2026)
            self.assertEqual(row['tax_year'], row['year'])
            if row['year'] < 2025:
                self.assertFalse(row['local_supported'])
                self.assertIsNone(row['local'])

    def test_ambiguous_team_excluded_from_cash_and_tax_subtotals(self):
        player_id = next(k for k,c in data()['players'].items() if c['year_signed'] == 2020)
        original = data()['players'][player_id]
        bad = dict(original, cash=[dict(original['cash'][0], source_teams=['Bills','Ravens'])])
        fake = dict(data(), players={player_id:bad})
        with patch('etl.nfl_history.data',return_value=fake):
            result = contract_history(lambda _:self.fail('Ambiguous year must not calculate'),player_id,'NY')
        self.assertEqual(result['excluded_years'], [2020])
        self.assertIsNone(result['gross'])
        self.assertIsNone(result['total_tax'])

    def test_every_saved_active_profile_gets_historical_coverage(self):
        for player_id,contract in data()['players'].items():
            with self.subTest(player=contract['player']):
                result = contract_history(calculate,player_id,'FL')
                self.assertEqual([r['year'] for r in result['annual']], [r['year'] for r in contract['cash'] if contract['year_signed'] <= r['year'] <= 2026])
                self.assertEqual(result['gross'],sum(r['cash'] for r in result['annual'] if r['status']=='estimated') if result['included_years'] else None)
                if result['included_years']:
                    self.assertAlmostEqual(result['gross'],result['total_tax']+result['remaining'],places=5)
                for row in result['annual']:
                    if row['status']!='estimated':self.assertIsNone(row['remaining'])
