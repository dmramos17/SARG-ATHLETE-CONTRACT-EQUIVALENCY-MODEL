"""Add reported historical contract cash and completed MLB calendars, ending 2026.

Uses saved public Spotrac year rankings and MLB Stats API season-appearance
clubs for older memberships. Never infers cash from payroll or AAV.
"""
from pathlib import Path
from collections import defaultdict
import argparse,json
from etl.mlb_import import API, fetch, normalized, ALIASES
from etl.mlb_model import contract_window, data
ROOT=Path(__file__).resolve().parents[1]

def build(cash_dir,cache):
    snapshot=data();schedule=json.loads((ROOT/'data/snapshots/mlb_schedules.json').read_text())
    old_sources=json.loads((ROOT/'data/snapshots/mlb_reported_cash.json').read_text())
    sources={s['year']:s for s in old_sources}
    for year in range(2015,2025):
        file=cash_dir/f'mlb-spotrac-cash-{year}.json'
        if file.exists():sources[year]=json.loads(file.read_text())
        elif year not in sources:raise ValueError(f'Missing saved public cash rows for {year}.')
    for year,source in sources.items():
        if year!=source['year'] or not source['source_url'].endswith(f'/year/{year}/sort/cash_total'):raise ValueError('Cash source year mismatch')
    cash={(r['player_id'],r['year']):r for r in snapshot['cash']}
    known_ids=defaultdict(set)
    for r in snapshot['cash']:known_ids[r['player_id']].add(r['spotrac_id'])
    historical=[p for p in snapshot['players'] if contract_window(p['id'])['verified'] and contract_window(p['id'])['start']<2025]
    for p in historical:
        window=contract_window(p['id'])
        for year in window['years']:
            if year>=2025:continue
            source=sources[year]
            matches=[r for r in source['rows'] if r['spotrac_id'] in known_ids[p['id']]]
            if not matches:
                names={normalized(p['name'])}|{normalized(c['summary']['playerName']) for c in snapshot['contracts'].get(p['id'],[])}
                matches=[r for r in source['rows'] if normalized(r['name']) in names]
            if len(matches)!=1:continue
            r=matches[0]
            cash[p['id'],year]=dict(player_id=p['id'],year=year,amount=r['cash'],name=r['name'],spotrac_id=r['spotrac_id'],source_url=source['source_url'],accessed_date=source['accessed_date'],basis='Spotrac reported historical total cash; listed incentives may be included; not verified W-2 income')
    # Batch official career-season appearances; teamless aggregate rows are not clubs.
    for offset in range(0,len(historical),20):
        ids=','.join(p['id'] for p in historical[offset:offset+20])
        url=f'{API}/people?personIds={ids}&hydrate=stats(group=[hitting,pitching],type=[yearByYear])'
        result=json.loads(fetch(url,cache))
        for person in result['people']:
            pid=str(person['id']);clubs=defaultdict(set)
            for group in person.get('stats',[]):
                for r in group.get('splits',[]):
                    tid=str(r.get('team',{}).get('id',''));year=int(r['season'])
                    if 2015<=year<2025 and tid in snapshot['teams'] and year in contract_window(pid)['years']:
                        clubs[str(year)].add(tid)
            for year,tids in clubs.items():snapshot['memberships'].setdefault(pid,{})[year]=sorted(tids)
        print(f'Imported historical club records for {min(offset+20,len(historical))}/{len(historical)} players',flush=True)
    existing=set(schedule['metadata']['years'])
    for year in range(2015,2025):
        if year in existing:continue
        raw=json.loads(fetch(f'{API}/schedule?sportId=1&season={year}&gameTypes=S,R,F,D,L,W&hydrate=venue(location)',cache))
        for day in raw['dates']:
            for g in day['games']:
                v=g.get('venue',{});loc=v.get('location',{})
                schedule['games'].append(dict(id=g['gamePk'],year=year,date=g['officialDate'],stage=g['gameType'],home=str(g['teams']['home']['team']['id']),away=str(g['teams']['away']['team']['id']),status=g['status']['detailedState'],abstract_status=g['status']['abstractGameState'],venue=v.get('name'),venue_id=v.get('id'),state=loc.get('stateAbbrev') if loc.get('country') in ('USA','United States') else None,country=loc.get('country'),city=loc.get('city')))
        standings=json.loads(fetch(f'{API}/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason',cache))
        schedule['metadata']['regular_game_counts'][str(year)]={str(t['team']['id']):t['gamesPlayed'] for r in standings['records'] for t in r['teamRecords']}
        print(f'Imported published {year} venues and standings',flush=True)
    schedule['metadata']['years']=list(range(2015,2027))
    snapshot['cash']=sorted(cash.values(),key=lambda r:(r['player_id'],r['year']))
    snapshot['metadata'].update(schedule_years=list(range(2015,2027)),tax_years=list(range(2015,2027)),historical_membership_source=f'{API}/people?personIds={{MLB-IDs}}&hydrate=stats(group=[hitting,pitching],type=[yearByYear])',historical_membership_basis='2015–2024 clubs from official regular-season appearances, not verified roster dates. No-appearance years remain unavailable.',historical_cash_scope='Reported current-contract playing years only, ending at 2026; prior-deal cash excluded.')
    for name,value in [('mlb_players.json',snapshot),('mlb_schedules.json',schedule),('mlb_reported_cash.json',list(sources.values()))]:
        (ROOT/'data/snapshots'/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(historical_players=len(historical),cash_records=len(cash),games=len(schedule['games']))))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cash-dir',type=Path,default=Path('/private/tmp'));parser.add_argument('--cache',type=Path,default=Path('/private/tmp/sarg-mlb-source-cache'))
    args=parser.parse_args();args.cache.mkdir(exist_ok=True,parents=True);build(args.cash_dir,args.cache)
