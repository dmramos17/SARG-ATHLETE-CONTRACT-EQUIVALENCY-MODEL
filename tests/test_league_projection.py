"""League projections: schedule completeness, cash coverage, and tax conservation."""
from collections import Counter
import unittest
from dashboard.server import calculate
from etl.league_projection import data, slots, calendar_variants, project_player, DIVISIONS
from etl.player_directory import load_directory
from etl.projection_data import build_contracts

class LeagueProjection(unittest.TestCase):
    def test_every_directory_player_has_contract_coverage(self):
        players=load_directory()['players']
        self.assertEqual(set(data()['players']),{p['id'] for p in players})
        for p in players:
            contract=data()['players'][p['id']]
            self.assertTrue(contract['cash'])
            self.assertEqual(contract['missing_years'],[r['year'] for r in contract['cash'] if r['cash'] is None])
            for row in contract['cash']:
                if row['cash'] is None:continue
                self.assertGreater(row['cash'],0)
                if row['base_salary'] is not None:
                    self.assertEqual(row['cash'],sum(row[k] or 0 for k in ('base_salary','roster_bonus','workout_bonus','signing_bonus','unclassified_cash')))

    def test_all_teams_rotations_extend_without_inventing_standings(self):
        for team in data()['rotations']:
            for year in range(2027,2036):
                row=slots(team,year)
                self.assertEqual(len(row),17)
                self.assertEqual(sum(g['opponent'] in DIVISIONS for g in row),3)
                self.assertFalse(any(g['opponent']==team for g in row))
                own=next(group for group in DIVISIONS.values() if team in group)
                for rival in set(own)-{team}:
                    self.assertEqual(sorted(g['home'] for g in row if g['opponent']==rival),[False,True])

    def test_published_schedules_include_all_games_and_cancellation(self):
        for season in range(2020,2027):
            counts=Counter(t for g in data()['games'] if g['season']==season and g['stage']=='REG' for t in (g['home'],g['away']))
            for team,n in counts.items():
                self.assertEqual(n,16 if season==2020 or season==2022 and team in ('BUF','CIN') else 17)
            self.assertEqual(len(counts),32)

    def test_calendar_year_and_venue_exceptions(self):
        variants=calendar_variants('NFL_NYG','NFL_NYG',2027,1)
        for rows,weight in variants:
            self.assertGreater(weight,0)
            self.assertTrue(all(r['date'].startswith('2027-') for r in rows))
            self.assertEqual(len(rows),len({r['date'] for r in rows}))
        # Washington practice is Virginia; home games are Maryland.
        rows=calendar_variants('NFL_WAS','NFL_WAS',2026,1)[0][0]
        self.assertTrue(any(r['state']=='VA' for r in rows))
        self.assertTrue(any(r['state']=='MD' and r['locality']=='MDNR' for r in rows))

    def test_preseason_road_trip_uses_current_employer_after_team_change(self):
        rows=calendar_variants('NFL_BUF','NFL_CLE',2026,1)[0][0]
        # Buffalo visits Cleveland: the previous employer must not make this a home game.
        self.assertEqual(next(r for r in rows if r['date']=='2026-08-21')['state'],'OH')

    def test_missing_years_are_not_zero_tax(self):
        record=next(c for c in data()['players'].values() if c['missing_years'])
        out=project_player(calculate,record['player_id'])
        self.assertFalse(out['complete'])
        self.assertEqual(out['total_label'],'Known-years cash subtotal')
        for row in out['annual']:
            if row['year'] in out['missing_years']:
                self.assertIsNone(row['remaining']);self.assertIsNone(row['total_tax'])
        self.assertEqual(out['gross'],sum(r['cash'] or 0 for r in out['annual']))

    def test_later_contract_cash_cannot_fill_the_old_deal(self):
        p=dict(id='test',name='Player',team='Buffalo Bills',team_id='NFL_BUF',source_url='https://overthecap.com/player/player/1/',season_cash=1000000,season_history=[],contract=dict(year_signed=2025,years=2,total_value=2000000,guaranteed=0))
        history=[dict(year='2025',team='Bills',cash_paid=1),dict(year='2026',team='Bills',cash_paid=20)]
        raw=[dict(gsis_id='test',otc_id=1,year_signed=2025,years=2,value=2,season_history=history),dict(gsis_id='test',otc_id=1,year_signed=2026,years=3,value=60,season_history=history)]
        c=build_contracts(raw,[p])['test']
        self.assertEqual(c['cash'][0]['cash'],1000000)
        self.assertIsNone(c['cash'][1]['cash'])
        self.assertEqual(c['missing_years'],[2026])

    def test_representative_players_across_all_32_teams(self):
        chosen={}
        for p in load_directory()['players']:
            c=data()['players'][p['id']]
            if c['missing_years']:continue
            # Prefer multiyear coverage to exercise both historical and projected calendars.
            if p['team_id'] not in chosen or len(c['cash'])>len(data()['players'][chosen[p['team_id']]['id']]['cash']):chosen[p['team_id']]=p
        self.assertEqual(len(chosen),32)
        for player in chosen.values():
            with self.subTest(player=player['name']):
                out=project_player(calculate,player['id'])
                self.assertAlmostEqual(out['gross'],out['remaining']+out['total_tax'])
                self.assertAlmostEqual(out['remaining'],sum(r['remaining'] or 0 for r in out['annual']))
                self.assertLessEqual(out['low_remaining'],out['remaining']+.01)
                self.assertLessEqual(out['remaining'],out['high_remaining']+.01)
                self.assertEqual(out['tax_rule_year'],2025)

    def test_validation_and_default_residence(self):
        with self.assertRaises(ValueError):project_player(calculate,'not-a-player')
        with self.assertRaises(ValueError):project_player(calculate,'00-0034857',residence='ZZ')
        with self.assertRaises(ValueError):project_player(calculate,'00-0034857',travel_days=5)
        with self.assertRaises(ValueError):project_player(calculate,'00-0034857',filing='other')
