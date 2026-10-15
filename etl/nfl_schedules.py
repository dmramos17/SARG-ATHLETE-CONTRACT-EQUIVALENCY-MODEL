"""Import complete calendar-year games and weekly team membership for the 2025 model."""
from collections import Counter, defaultdict
import argparse
import csv
from datetime import datetime, date, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SCHEDULE_SOURCE='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2025&limit=1000'
ALIASES={'LA':'LAR','JAC':'JAX','WSH':'WAS'}

def import_games(data,teams):
    games=[]
    for event in data['events']:
        competition=event['competitions'][0]
        competitors={r['homeAway']:ALIASES.get(r['team']['abbreviation'],r['team']['abbreviation']) for r in competition['competitors']}
        if any('NFL_'+t not in teams for t in competitors.values()):
            continue  # Pro Bowl is not a team employment event.
        day=datetime.fromisoformat(event['date'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
        if day.year!=2025:
            continue
        address=competition['venue']['address'];country=address.get('country')
        state=address.get('state') if country=='USA' else None
        if country=='USA' and not state:
            raise ValueError('US game is missing its actual venue state.')
        stage={1:'PRE',2:'REG',3:'POST'}[event['season']['type']]
        city=address.get('city','')
        locality={('PA','Philadelphia'):'PHL',('PA','Pittsburgh'):'PIT',('OH','Cincinnati'):'CIN',('OH','Cleveland'):'CLE',('MI','Detroit'):'DET',('MO','Kansas City'):'KCM'}.get((state,city))
        if state=='MD':locality='MDNR'
        games.append(dict(date=day.isoformat(),home=competitors['home'],away=competitors['away'],
                          stage=stage,season=event['season']['year'],week=event['week']['number'],
                          state=state,locality=locality,venue=competition['venue']['fullName'],city=city,country=country,
                          event_id=event['id'],source='https://www.espn.com/nfl/game/_/gameId/'+event['id']))
    games.sort(key=lambda r:(r['date'],r['event_id']))
    if len({g['event_id'] for g in games})!=len(games):raise ValueError('Duplicate schedule event.')
    if len(games)!=334 or Counter(g['stage'] for g in games)!=dict(PRE=49,REG=272,POST=13):
        raise ValueError('Incomplete 2025 calendar-year NFL schedule; review before importing.')
    return games


def import_memberships(rosters,eligible_ids,games):
    # Week observation dates are estimates of roster transition boundaries, not
    # transaction timestamps. Monday games belong to the preceding league week.
    anchors={}
    for game in games:
        day=date.fromisoformat(game['date'])
        monday=day-timedelta(days=day.weekday() or 7)
        if day.weekday()!=0:monday=day-timedelta(days=day.weekday())
        for team in (game['home'],game['away']):
            anchors[(game['season'],game['stage'],game['week'],team)]=monday
    output=defaultdict(dict)
    for row in rosters:
        identity=row.get('gsis_id')
        if identity not in eligible_ids:continue
        season=int(row['season']);raw_stage=row['game_type'];week=int(row['week']);team=ALIASES.get(row['team'],row['team'])
        if raw_stage=='REG':
            if season==2025:
                anchor=date(2025,9,1)+timedelta(weeks=week-1)
            elif season==2024 and week==18:
                anchor=date(2024,12,30)
            else:continue
        elif season==2024 and raw_stage in ('WC','DIV','CON','SB'):
            # nflverse postseason week numbers are league-season weeks 19–23.
            postseason_week={'WC':1,'DIV':2,'CON':3,'SB':5}[raw_stage]
            anchor=anchors.get((season,'POST',postseason_week,team))
            if anchor is None:continue
        else:continue
        key=anchor.isoformat();record=dict(start=key,team_id='NFL_'+team,status=row['status'],week=week,season=season)
        old=output[identity].get(key)
        if old is None or (record['status'] in ('ACT','INA'))>(old['status'] in ('ACT','INA')):
            output[identity][key]=record
    return {identity:sorted(rows.values(),key=lambda r:r['start']) for identity,rows in output.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scoreboard',type=Path,required=True)
    parser.add_argument('--rosters-2024',type=Path,required=True)
    parser.add_argument('--rosters-2025',type=Path,required=True)
    args=parser.parse_args()
    with (ROOT/'data/curated/teams.csv').open() as stream:teams={r['team_id']:r for r in csv.DictReader(stream) if r['league']=='NFL'}
    games=import_games(json.loads(args.scoreboard.read_text()),teams)
    (ROOT/'data/curated/nfl_games_calendar_2025.json').write_text(json.dumps(games,indent=2)+'\n')
    players=json.loads((ROOT/'data/snapshots/nfl_players_2025.json').read_text())['players']
    rosters=[]
    for path in (args.rosters_2024,args.rosters_2025):
        with path.open() as stream:rosters.extend(csv.DictReader(stream))
    memberships=import_memberships(rosters,{p['id'] for p in players},games)
    payload=dict(metadata=dict(accessed_date='2026-10-15',sources=[SCHEDULE_SOURCE,
        'https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2024.csv',
        'https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.csv'],
        sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.scoreboard,args.rosters_2024,args.rosters_2025)},
        observation_note='Weekly roster membership is used to approximate team transitions; exact transaction dates and individual attendance are not established.'),players=memberships)
    (ROOT/'data/snapshots/nfl_memberships_2025.json').write_text(json.dumps(payload,separators=(',',':'))+'\n')
    print(f'Imported {len(games)} games, {len(memberships)} player membership timelines.')

if __name__=='__main__':main()
