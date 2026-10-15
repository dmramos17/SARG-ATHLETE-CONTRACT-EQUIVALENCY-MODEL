"""Identity, historical year boundaries, currency units and real search coverage."""
import unittest
from etl.player_directory import build_directory, dollars, search_players, load_directory, find_player

TEAMS = {'NFL_NE':{'team_name':'New England Patriots','practice_state':'MA'},
         'NFL_SEA':{'team_name':'Seattle Seahawks','practice_state':'WA'}}

def roster(identity, name, week=1, team='NE', status='ACT', season='2025', game_type='REG'):
    return dict(gsis_id=identity, full_name=name, week=str(week), team=team, status=status,
                season=season, game_type=game_type, position='QB',jersey_number='9')

def contract(identity, name, signed=2025, value=20, otc_id=1):
    return dict(gsis_id=identity,player=name,year_signed=signed,years=2,value=value,apy=value/2,
                guaranteed=10,otc_id=otc_id,player_page='https://overthecap.com/player/example/1/',
                team='Patriots',season_history=[dict(year='2025',team='Patriots',base_salary=1,
                    cash_paid=5,cap_number=2,prorated_bonus=1,option_bonus=0)])

class PlayerDirectory(unittest.TestCase):
    def build(self,rosters,contracts,reviewed=()):
        return build_directory(rosters,contracts,reviewed,TEAMS,'2026-10-15')

    def test_includes_season_active_players_even_if_later_on_reserve(self):
        data=self.build([roster('a','Player One'),roster('a','Player One',week=18,status='RES'),
                         roster('b','Practice Only',status='DEV'),roster('c','Old Player',season='2024'),
                         roster('d','Postseason Only',game_type='WC')],[])
        self.assertEqual([p['name'] for p in data['players']],['Player One'])
        self.assertEqual(data['players'][0]['latest_roster_status'],'RES')
        self.assertEqual(data['players'][0]['active_weeks'],1)

    def test_trade_keeps_one_identity_and_both_active_teams(self):
        data=self.build([roster('a','Player One'),roster('a','Player One',week=10,team='SEA')],[])
        self.assertEqual(len(data['players']),1)
        self.assertEqual(data['players'][0]['teams'],['NE','SEA'])
        self.assertEqual(data['players'][0]['team_code'],'SEA')

    def test_same_name_players_use_distinct_gsis_ids(self):
        data=self.build([roster('a','Josh Allen'),roster('b','Josh Allen',team='SEA')],
                        [contract('a','Josh Allen',value=20),contract('b','Josh Allen',value=40)])
        self.assertEqual({p['id']:p['contract']['total_value'] for p in data['players']},{'a':20000000,'b':40000000})

    def test_future_extension_never_becomes_2025_contract(self):
        data=self.build([roster('a','Player One')],[contract('a','Player One',signed=2024,value=20),
                                                  contract('a','Player One',signed=2026,value=200)])
        self.assertEqual(data['players'][0]['contract']['year_signed'],2024)
        self.assertEqual(data['players'][0]['contract']['total_value'],20000000)
        self.assertEqual(data['featured_ids'],[])

    def test_dollar_conversion_keeps_cash_distinct_from_cap(self):
        data=self.build([roster('a','Player One')],[contract('a','Player One')])
        self.assertEqual(dollars(0.000001),1)
        self.assertIsNone(dollars(None))
        self.assertIsNone(dollars(float('nan')))
        player=data['players'][0]
        self.assertEqual(player['season_cash'],5000000)
        self.assertEqual(player['season_history'][0]['cap_number'],2000000)
        self.assertIsNone(player['estimate_id'])

    def test_missing_cash_is_unknown_not_zero(self):
        row=contract('a','Player One');row['season_history'][0]['cash_paid']=None
        data=self.build([roster('a','Player One')],[row])
        self.assertIsNone(data['players'][0]['season_cash'])

    def test_otc_identity_links_reviewed_alias_without_fuzzy_name_match(self):
        model=dict(player='Patrick Surtain II',team_id='NFL_NE',id='surtain-2025',annual_cash=22170000,
                   sources=[dict(name='OverTheCap',url='https://overthecap.com/player/patrick-surtain-ii/1')])
        data=self.build([roster('a','Pat Surtain II')],[contract('a','Pat Surtain II')],[model])
        self.assertEqual(data['players'][0]['estimate_id'],'surtain-2025')

    def test_real_directory_has_all_teams_unique_players_and_estimate_links(self):
        data=load_directory();players=data['players']
        self.assertGreater(len(players),2000)
        self.assertEqual(len({p['id'] for p in players}),len(players))
        self.assertEqual(len({team for p in players for team in p['teams']}),32)
        self.assertEqual(sum(p['estimate_id'] is not None for p in players),3)
        self.assertTrue(all(p['contract']['year_signed']<=2025 for p in players if p['contract']))

    def test_search_handles_punctuation_and_no_results(self):
        self.assertTrue(any('Chase' in p['name'] for p in search_players('jamarr')))
        self.assertTrue(any('Mahomes' in p['name'] for p in search_players('patrick mah')))
        self.assertEqual(search_players('zzzzzzzzzzzzzz'),[])
        self.assertEqual(search_players(''),[])
        self.assertLessEqual(len(search_players('a')),10)
        self.assertIsNone(find_player('../../etc/passwd'))

if __name__=='__main__':unittest.main()
