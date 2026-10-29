"""Import league contract cash and published rotations; no network at runtime.

Usage: python -m etl.projection_data --contracts FILE --fact-book FILE --scoreboard-dir DIR
Requires pyarrow and pypdf only for importing.
"""
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse, hashlib, json, re
from etl.player_directory import load_directory, dollars, normalize
from etl.estimated_duty_days import teams, games

ROOT=Path(__file__).resolve().parents[1]
ALIASES={'LA':'LAR','JAC':'JAX','WSH':'WAS','OAK':'LV','SD':'LAC','STL':'LAR'}
CITY_CODES=dict(zip(['Arizona','Atlanta','Baltimore','Buffalo','Carolina','Chicago','Cincinnati','Cleveland','Dallas','Denver','Detroit','Green Bay','Houston','Indianapolis','Jacksonville','Kansas City','Las Vegas','L.A. Chargers','L.A. Rams','Miami','Minnesota','New England','New Orleans','N.Y. Giants','N.Y. Jets','Philadelphia','Pittsburgh','San Francisco','Seattle','Tampa Bay','Tennessee','Washington'],['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LAR','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS']))

def rotations_from_pdf(path):
    from pypdf import PdfReader
    pages=PdfReader(path).pages
    text='\n'.join(pages[i].extract_text() for i in range(11,17))
    text=re.sub(r'(\w)\s*-\s*\n\s*(\w)',r'\1\2',text)
    text=re.sub(r'\s+',' ',text)
    text=re.sub(r'(20\d\d)\s*—\s*Home:',r'\1 — Home:',text)
    text=text.replace('MIami','Miami').replace('L.A Rams','L.A. Rams').replace('New Engalnd','New England')
    headings={t['team_name']:key.removeprefix('NFL_') for key,t in teams().items()}
    matches=list(re.finditer('|'.join(re.escape(k) for k in sorted(headings,key=len,reverse=True)),text))
    out={}
    for i,match in enumerate(matches):
        chunk=text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        team=headings[match.group()];years={}
        for year,home,away in re.findall(r'(202[5-9]|2030) — Home: (.*?) Away: (.*?)(?= 20(?:2[5-9]|30) — Home:| FUTURE OPPONENTS| Future Opponents_|$)',chunk):
            def parse(part):
                part=part.strip().rstrip('.')
                values=[]
                for name in part.split(','):
                    name=name.strip().rstrip('.')
                    if name.endswith(' TBD'):values.append(name[:-4]);continue
                    name=re.sub(r'\s+',' ',name)
                    if name not in CITY_CODES:raise ValueError(f'Unrecognized opponent {team} {year}: {name}')
                    values.append(CITY_CODES[name])
                return values
            years[year]=dict(home=parse(home),away=parse(away))
        out[team]=years
    if len(out)!=32:raise ValueError(f'Expected 32 rotation teams, found {len(out)}')
    for team,years in out.items():
        for year in map(str,range(2027,2031)):
            row=years[year];allops=row['home']+row['away']
            if len(allops)!=17 or sum(len(op)==4 for op in allops)!=3:raise ValueError(f'Bad rotation: {team} {year} {row}')
    return out

def import_published(paths):
    result={str(g['event_id']):g for g in games()}
    for path in paths:
        for event in json.loads(path.read_text())['events']:
            c=event['competitions'][0]
            competitors={t['homeAway']:ALIASES.get(t['team']['abbreviation'],t['team']['abbreviation']) for t in c['competitors']}
            if any('NFL_'+t not in teams() for t in competitors.values()):continue
            season=event['season']['year'];stage=event['season']['type']
            # No invented future playoff participation, even if a feed has placeholders.
            if stage not in (1,2,3) or (season>=2026 and stage==3):continue
            venue=c.get('venue') or {};address=venue.get('address') or {}
            if not address:raise ValueError(f'Missing actual venue: {event["id"]}')
            country=address.get('country');state=address.get('state') if country=='USA' else None
            if country=='USA' and not state:raise ValueError('US venue state missing')
            day=datetime.fromisoformat(event['date'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            city=address.get('city','');locality={('PA','Philadelphia'):'PHL',('OH','Cincinnati'):'CIN',('MO','Kansas City'):'KCM'}.get((state,city))
            if state=='MD':locality='MDNR'
            result[event['id']]=dict(date=day,home=competitors['home'],away=competitors['away'],state=state,city=city,locality=locality,
                stage={1:'PRE',2:'REG',3:'POST'}[stage],season=season,week=event['week']['number'],event_id=event['id'],
                source='https://www.espn.com/nfl/game/_/gameId/'+event['id'])
    return sorted(result.values(),key=lambda g:(g['date'],g['event_id']))

def build_contracts(raw,players):
    by_id=defaultdict(list);by_otc=defaultdict(list)
    for row in raw:
        by_id[row.get('gsis_id')].append(row);by_otc[str(row.get('otc_id'))].append(row)
    out={}
    for p in players:
        meta=p.get('contract') or {};signed=meta.get('year_signed') or 2025
        try:otc=p['source_url'].rstrip('/').split('/')[-1]
        except (KeyError,AttributeError):otc=''
        candidates=[r for r in by_id.get(p['id'],[]) or by_otc.get(otc,[]) if r.get('year_signed')==signed and dollars(r.get('value'))==meta.get('total_value') and r.get('years')==meta.get('years')]
        # Same contract may appear in multiple historical rows. Only collapse identical histories.
        unique={json.dumps(r.get('season_history'),sort_keys=True):r for r in candidates}
        notes=[];history=[];matched=False
        identity_rows=by_id.get(p['id'],[]) or by_otc.get(otc,[])
        later_signed=min([r['year_signed'] for r in identity_rows if r.get('year_signed') and r['year_signed']>signed]+[9999])
        draft_year=next((r.get('draft_year') for r in candidates if r.get('draft_year')),None)
        if len(unique)==1:
            history=next(iter(unique.values())).get('season_history') or [];matched=True
        elif len(unique)>1:
            # A unique 2025 team/cash match can disambiguate histories, never fuzzy names.
            exact=[r for r in unique.values() if any(str(s.get('year'))=='2025' and dollars(s.get('cash_paid'))==p.get('season_cash') and normalize(str(s.get('team'))).split(' ')[-1]==normalize(p['team']).split(' ')[-1] for s in r.get('season_history') or [])]
            if len(exact)==1:history=exact[0].get('season_history') or [];matched=True
        if not matched:
            notes.append('The source could not uniquely match this saved contract to a complete cash history. Only the existing 2025 cash record is available; missing years are not estimated from headline value.')
            history=p.get('season_history') or []
        yearly=defaultdict(list)
        for row in history:
            if str(row.get('year')).isdigit() and int(row['year'])>=signed:
                yearly[int(row['year'])].append(row)
        positives=[year for year,rs in yearly.items() if any((r.get('cash_paid') or 0)>0 for r in rs)]
        # Imported Parquet is in millions; fallback saved directory rows are already dollars.
        convert=dollars if matched else lambda x:x
        last=max([y for y in positives if y<later_signed]+[signed+(meta.get('years') or 1)-1,2025])
        if later_signed!=9999:notes.append(f'A later contract was signed in {later_signed}; cash from that year onward cannot be attributed to this saved contract and is left uncalculated.')
        if last>2045:raise ValueError('Unreasonable contract horizon')
        cash=[]
        for year in range(signed,last+1):
            rs=yearly.get(year,[])
            amounts=[convert(r.get('cash_paid')) for r in rs]
            usable=bool(rs) and year<later_signed and all(n is not None and n>0 for n in amounts)
            amount=sum(amounts) if usable else None
            parts={k:sum(convert(r.get(k)) or 0 for r in rs) if usable else None for k in ('base_salary','roster_bonus','workout_bonus')}
            if usable and sum(parts.values())>amount:
                # Annual base can exceed actual paid cash after release/trade. Never inflate wages.
                parts={k:None for k in parts};notes.append(f'{year}: reported salary components exceed paid cash; only total cash is used.')
            cash.append(dict(year=year,cash=amount,**parts,signing_bonus=None,
                unclassified_cash=amount-sum(v or 0 for v in parts.values()) if usable else None,
                source_teams=sorted({r.get('team') for r in rs if r.get('team')}),status='reported' if usable else 'cash_needed'))
        if not matched and p.get('season_cash') and not any(r['year']==2025 and r['cash'] for r in cash):
            next(r for r in cash if r['year']==2025).update(cash=p['season_cash'],status='reported')
        known=sum(r['cash'] or 0 for r in cash);missing=[r['year'] for r in cash if r['cash'] is None]
        if known!=meta.get('total_value'):
            notes.append('The cash window does not reconcile to headline new-money value. Extensions may replace existing years, and historical cash may reflect an earlier or restructured deal. This is a cash-window projection, not a verified allocation of the headline contract value.')
        out[p['id']]=dict(player_id=p['id'],player=p['name'],team_id=p['team_id'],year_signed=signed,draft_year=draft_year,reported_years=meta.get('years'),headline_value=meta.get('total_value'),
            reported_guarantees=meta.get('guaranteed'),cash=cash,matched=matched,missing_years=missing,reconciles_headline=not missing and known==meta.get('total_value'),
            notes=list(dict.fromkeys(notes)),source_url=p.get('source_url'),accessed_date='2026-10-28')
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--contracts',type=Path,required=True);parser.add_argument('--fact-book',type=Path,required=True);parser.add_argument('--scoreboard-dir',type=Path,required=True);a=parser.parse_args()
    import pyarrow.parquet as pq
    players=load_directory()['players'];table=pq.read_table(a.contracts)
    contracts=build_contracts(table.to_pylist(),players)
    rotations=rotations_from_pdf(a.fact_book)
    paths=sorted(a.scoreboard_dir.glob('nfl-scoreboard-20??.json'))
    published=import_published(paths)
    for season in range(2020,2027):
        counts=Counter(t for g in published if g['season']==season and g['stage']=='REG' for t in (g['home'],g['away']))
        expected=16 if season==2020 else 17
        if len(counts)!=32 or any(n!=(16 if season==2022 and team in ('BUF','CIN') else expected) for team,n in counts.items()):raise ValueError(f'Incomplete season {season}: {counts}')
    metadata=dict(accessed_date='2026-10-28',contract_source='https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet',contract_timestamp=(table.schema.metadata or {}).get(b'nflverse_timestamp',b'').decode(),
        rotation_source='https://static.www.nfl.com/league/apps/league-site/media-guides/2024/2024-Record-and-Fact-Book.pdf',schedule_source='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
        sha256={a.contracts.name:hashlib.sha256(a.contracts.read_bytes()).hexdigest(),a.fact_book.name:hashlib.sha256(a.fact_book.read_bytes()).hexdigest()},
        players=len(contracts),matched=sum(c['matched'] for c in contracts.values()),complete_cash_windows=sum(not c['missing_years'] for c in contracts.values()))
    out=dict(metadata=metadata,players=contracts,rotations=rotations,games=published)
    path=ROOT/'data/snapshots/contract_projections.json';path.write_text(json.dumps(out,separators=(',',':'))+'\n')
    print(metadata)
if __name__=='__main__':main()
