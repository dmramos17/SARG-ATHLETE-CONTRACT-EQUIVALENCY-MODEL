"""Rebuild offline MLB roster/schedule/contract snapshots from public sources.

Run with --cash-2025 and --cash-2026 pointing at saved public Spotrac cash
ranking rows (year, source_url, accessed_date, rows: name/spotrac_id/cash/team).
RosterResource payroll Salary/AAV/prorated bonuses are NEVER cash inputs.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import date
from pathlib import Path
import argparse
import json
import re
import subprocess
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
API = 'https://statsapi.mlb.com/api/v1'
OFFLINE = False
SLUGS = dict(zip(
    ['ATH','PIT','SD','SEA','SF','STL','TB','TEX','TOR','MIN','PHI','ATL','CWS','MIA','NYY','MIL','LAA','ARI','BAL','BOS','CHC','CIN','CLE','COL','DET','HOU','KC','LAD','WSH','NYM'],
    ['athletics','pirates','padres','mariners','giants','cardinals','rays','rangers','blue-jays','twins','phillies','braves','white-sox','marlins','yankees','brewers','angels','diamondbacks','orioles','red-sox','cubs','reds','guardians','rockies','tigers','astros','royals','dodgers','nationals','mets']))
ALIASES = {'AZ':'ARI','CHW':'CWS','KCR':'KC','SDP':'SD','SFG':'SF','TBR':'TB','WSN':'WSH'}
WORKOUTS = {
 2025: {'ARI':(12,17),'ATH':(12,17),'CHC':(9,14),'CWS':(12,17),'CIN':(12,17),'CLE':(13,18),'COL':(13,18),'KC':(12,17),'LAD':(11,15),'LAA':(12,17),'MIL':(13,18),'SD':(12,17),'SF':(12,17),'SEA':(13,18),'TEX':(12,17),'ATL':(12,18),'BAL':(13,18),'BOS':(12,17),'DET':(12,17),'HOU':(13,18),'MIA':(12,17),'MIN':(13,17),'NYM':(12,17),'NYY':(12,17),'PHI':(12,17),'PIT':(12,17),'STL':(12,17),'TB':(12,17),'TOR':(13,18),'WSH':(12,18)},
 2026: {'ARI':(10,15),'ATH':(11,16),'CHC':(11,16),'CWS':(10,15),'CIN':(11,16),'CLE':(12,17),'COL':(12,17),'KC':(11,16),'LAD':(13,17),'LAA':(11,16),'MIL':(12,17),'SD':(11,15),'SF':(10,15),'SEA':(12,17),'TEX':(10,15),'ATL':(10,15),'BAL':(11,16),'BOS':(10,15),'DET':(11,15),'HOU':(11,16),'MIA':(11,16),'MIN':(12,16),'NYM':(11,16),'NYY':(12,16),'PHI':(11,16),'PIT':(11,16),'STL':(12,16),'TB':(12,17),'TOR':(11,16),'WSH':(11,16)}}
WORKOUT_SOURCES = {2025:'https://www.mlb.com/news/spring-training-2025-workout-dates-media-days',2026:'https://www.mlb.com/news/spring-training-2026-first-workout-dates'}

def normalized(name):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', name).encode('ascii','ignore').decode().lower())

def fetch(url, cache):
    path = cache / (re.sub(r'[^a-zA-Z0-9]', '_', url)[-210:] + '.txt')
    if not path.exists():
        if OFFLINE:raise RuntimeError(f'Not present in local source cache: {url}')
        time.sleep(1)  # Pace public-source requests; do not retry rate-limited pages in a loop.
        result = subprocess.run(['curl','-g','-sS','-L','--fail','--max-time','60',url],capture_output=True)
        if result.returncode:
            raise RuntimeError(f'Public source failed: {url}: {result.stderr.decode()[:200]}')
        path.write_bytes(result.stdout)
    return path.read_text()

def payroll_contracts(html):
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if not match:
        raise ValueError('RosterResource page does not contain its published payroll data.')
    queries = json.loads(match.group(1))['props']['pageProps']['dehydratedState']['queries']
    return next(q['state']['data']['dataContract'] for q in queries if isinstance(q['state']['data'],dict) and 'dataContract' in q['state']['data'])

def build(as_of, cash_files, cache):
    seed = json.loads((ROOT/'data/curated/mlb_interface_seed.json').read_text())
    team_info = {t['code']: t for t in seed['teams']}
    api_teams = json.loads(fetch(f'{API}/teams?sportId=1&season=2026',cache))['teams']
    assert len(api_teams)==30
    teams = {}
    for t in api_teams:
        code = ALIASES.get(t['abbreviation'],t['abbreviation'])
        teams[str(t['id'])] = dict(team_info[code],id=str(t['id']),slug=SLUGS[code],
            spring_state='FL' if code in {'ATL','BAL','BOS','DET','HOU','MIA','MIN','NYM','NYY','PHI','PIT','STL','TB','TOR','WSH'} else 'AZ',
            workouts={str(y):dict(pitcher_catcher=f'{y}-02-{WORKOUTS[y][code][0]:02}',position=f'{y}-02-{WORKOUTS[y][code][1]:02}') for y in WORKOUTS})
    tasks=[]
    for tid,t in teams.items():
        tasks.append(('active',tid,2026,f'{API}/teams/{tid}/roster?rosterType=active&date={as_of}&hydrate=person'))
        for year in (2025,2026):
            tasks.append(('membership',tid,year,f'{API}/teams/{tid}/roster?rosterType=fullSeason&season={year}'))
            tasks.append(('contract',tid,year,f'https://www.fangraphs.com/roster-resource/payroll/{t["slug"]}?season={year}'))
    for year in (2025,2026):
        tasks.append(('schedule','',year,f'{API}/schedule?sportId=1&season={year}&gameTypes=S,R,F,D,L,W&hydrate=venue(location)'))
        tasks.append(('standings','',year,f'{API}/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason'))
    def download(task):
        kind,tid,year,url=task
        try:
            return task,fetch(url,cache)
        except RuntimeError as error:
            if kind=='contract':return task,dict(error=str(error))
            raise
    players={}; memberships=defaultdict(lambda:defaultdict(set)); contracts=defaultdict(list); games=[]; failures=[];game_counts={}
    with ThreadPoolExecutor(max_workers=1) as pool:
        for index,(task,raw) in enumerate(pool.map(download,tasks),1):
            kind,tid,year,url=task
            if isinstance(raw,dict):
                failures.append(dict(source_url=url,error=raw['error']));continue
            if kind=='active':
                for r in json.loads(raw)['roster']:
                    if r['status']['code']!='A':continue
                    person=r['person'];pid=str(person['id']);team=teams[tid]
                    if pid in players and players[pid]['team_id']!=tid:raise ValueError('Duplicate active player across teams')
                    players[pid]=dict(id=pid,name=person['fullName'],team_id=tid,team_code=team['code'],team=team['name'],base_state=team['state'],position=r['position']['name'],position_code=r['position']['abbreviation'],source=f'https://www.mlb.com/player/{pid}',roster_status=r['status']['description'])
            elif kind=='membership':
                for r in json.loads(raw)['roster']:memberships[str(r['person']['id'])][str(year)].add(tid)
            elif kind=='contract':
                for c in payroll_contracts(raw):
                    summary=c['contractSummary'];pid=str(summary.get('MLBAMID') or '')
                    if pid:contracts[pid].append(dict(source_season=year,team_id=tid,source_url=url,description=c['description'],summary=summary,annual=c['contractYears']))
            elif kind=='standings':
                game_counts[str(year)]={str(t['team']['id']):t['gamesPlayed'] for r in json.loads(raw)['records'] for t in r['teamRecords']}
            else:
                for day in json.loads(raw)['dates']:
                    for g in day['games']:
                        # Retain cancellations for auditing, but never count them as duty-day games.
                        venue=g.get('venue',{});loc=venue.get('location',{})
                        games.append(dict(id=g['gamePk'],year=year,date=g['officialDate'],stage=g['gameType'],home=str(g['teams']['home']['team']['id']),away=str(g['teams']['away']['team']['id']),status=g['status']['detailedState'],abstract_status=g['status']['abstractGameState'],venue=venue.get('name'),venue_id=venue.get('id'),state=loc.get('stateAbbrev') if loc.get('country') in ('USA','United States') else None,country=loc.get('country'),city=loc.get('city')))
            if index%25==0:print(f'Imported {index}/{len(tasks)} public source pages',flush=True)
    cash=[];cash_sources=[]
    for file in cash_files:
        source=json.loads(Path(file).read_text());year=source['year']
        cash_sources.append(source)
        assert year in (2025,2026)
        names=defaultdict(list)
        for r in source['rows']:names[normalized(r['name'])].append(r)
        for pid,p in players.items():
            aliases={normalized(p['name'])}
            aliases.update(normalized(c['summary']['playerName']) for c in contracts[pid])
            matches={r['spotrac_id']:r for name in aliases for r in names[name]}
            if len(matches)>1:
                matches={i:r for i,r in matches.items() if ALIASES.get(r['team'],r['team'])==p['team_code']}
            if len(matches)==1:
                r=next(iter(matches.values()))
                cash.append(dict(player_id=pid,year=year,amount=r['cash'],name=r['name'],spotrac_id=r['spotrac_id'],source_url=source['source_url'],accessed_date=source['accessed_date'],basis='Spotrac reported total cash; listed incentives may be included; not verified W-2 income'))
    # Only persist the contracts and memberships needed by the searchable active roster.
    directory=dict(metadata=dict(as_of=as_of,season=2026,scope='MLB Stats API active roster endpoint; status A only. Offseason counts can differ from the in-season 26-man roster. Snapshot, not live.',roster_source=f'{API}/teams/{{teamId}}/roster?rosterType=active&date={as_of}',schedule_years=[2025,2026],tax_years=[2025,2026],future_taxes=False,workout_sources=WORKOUT_SOURCES,contract_source_failures=failures),teams=teams,players=sorted(players.values(),key=lambda p:p['name'].casefold()),memberships={pid:{y:sorted(ids) for y,ids in memberships[pid].items()} for pid in players},contracts={pid:contracts[pid] for pid in players},cash=cash)
    target=ROOT/'data/snapshots'
    (target/'mlb_players.json').write_text(json.dumps(directory,ensure_ascii=False,separators=(',',':'))+'\n')
    (target/'mlb_reported_cash.json').write_text(json.dumps(cash_sources,ensure_ascii=False,separators=(',',':'))+'\n')
    (target/'mlb_schedules.json').write_text(json.dumps(dict(metadata=dict(as_of=as_of,source=f'{API}/schedule',years=[2025,2026],regular_game_counts=game_counts,standings_source=f'{API}/standings',scope='Published spring, regular and postseason games with actual venue metadata. No future schedule synthesis.'),games=games),ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(players=len(players),teams=len(teams),cash_records=len(cash),games=len(games))))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',default=date.today().isoformat())
    parser.add_argument('--cash-2025',required=True)
    parser.add_argument('--cash-2026',required=True)
    parser.add_argument('--cache',type=Path,default=Path('/private/tmp/sarg-mlb-source-cache'))
    parser.add_argument('--offline',action='store_true',help='Rebuild from cached public pages without network requests')
    args=parser.parse_args();date.fromisoformat(args.as_of);args.cache.mkdir(parents=True,exist_ok=True)
    OFFLINE=args.offline
    build(args.as_of,[args.cash_2025,args.cash_2026],args.cache)
