"""Build a reproducible 2025 player directory from nflverse weekly rosters and OTC history.

Runtime reads only the compact saved JSON. The import command needs pyarrow;
no subscriptions, scraping, or external requests occur during a site visit.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/snapshots/nfl_players_2025.json'
ROSTER_SOURCE = 'https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2025.csv'
CONTRACT_SOURCE = 'https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet'


def normalize(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def dollars(value):
    if value is None:
        return None
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        return None
    return int((value * 1_000_000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def build_directory(rosters, contract_rows, reviewed, teams, accessed_date):
    """ACT/INA in any 2025 regular-season week; one identity with all observed teams.

    Prefer GSIS joins. Exact unique name joins are explicitly labeled and never
    fuzzy. Contract units in this Parquet schema are millions of dollars.
    """
    all_rosters = defaultdict(list)
    eligible = set()
    for row in rosters:
        if str(row.get('season')) != '2025' or row.get('game_type') != 'REG':
            continue
        name = row.get('full_name', '').strip()
        if not name:
            continue
        identity = row.get('gsis_id') or 'name-' + normalize(name).replace(' ', '-')
        all_rosters[identity].append(row)
        if row.get('status') in ('ACT', 'INA'):
            eligible.add(identity)
    by_id, by_name = defaultdict(list), defaultdict(list)
    for row in contract_rows:
        if row.get('gsis_id'):
            by_id[row['gsis_id']].append(row)
        by_name[normalize(row['player'])].append(row)
    reviewed_names = {normalize(row['player']): row for row in reviewed}
    reviewed_otc = {int(source['url'].rstrip('/').split('/')[-1]): row
                    for row in reviewed for source in row['sources']
                    if source['name'] == 'OverTheCap' and source['url'].rstrip('/').split('/')[-1].isdigit()}
    aliases = {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS'}
    players = []
    for identity in sorted(eligible):
        appearances = sorted(all_rosters[identity], key=lambda r: int(r.get('week') or 0))
        latest = appearances[-1]
        active = [r for r in appearances if r['status'] in ('ACT', 'INA')]
        team_codes = sorted({aliases.get(r['team'], r['team']) for r in active})
        primary = aliases.get(active[-1]['team'], active[-1]['team'])
        team = teams.get('NFL_' + primary)
        if not team:
            raise ValueError('Unknown NFL team: ' + primary)
        candidates = by_id.get(identity, [])
        match_method = 'gsis_id' if candidates else None
        if not candidates:
            named = by_name.get(normalize(latest['full_name']), [])
            otc_ids = {r['otc_id'] for r in named}
            roster_names = {key for key in eligible if normalize(all_rosters[key][0]['full_name']) == normalize(latest['full_name'])}
            if len(otc_ids) == 1 and len(roster_names) == 1:
                candidates, match_method = named, 'unique_exact_name'
        # Later contracts cannot become 2025 contract cards.
        candidates = [r for r in candidates if r.get('year_signed') is not None and r['year_signed'] <= 2025]
        chosen = max(candidates, key=lambda r: (r['year_signed'], r.get('value') or 0)) if candidates else None
        history = []
        if chosen:
            for row in chosen.get('season_history') or []:
                if str(row.get('year')) != '2025':
                    continue
                history.append({key: dollars(row.get(key)) for key in ('base_salary','roster_bonus','workout_bonus','per_game_roster_bonus','cash_paid','cap_number','prorated_bonus','option_bonus')} | {'team': row.get('team'), 'year': 2025})
        cash = history[0]['cash_paid'] if len(history) == 1 else None
        model = reviewed_otc.get(chosen['otc_id']) if chosen else None
        model = model or reviewed_names.get(normalize(latest['full_name']))
        if model and model['team_id'] != 'NFL_' + primary:
            model = None
        source_url = chosen.get('player_page') if chosen else None
        if source_url and not source_url.startswith('https://overthecap.com/'):
            source_url = None
        contract = None
        if chosen:
            contract = dict(year_signed=chosen['year_signed'], years=chosen.get('years'),
                            total_value=dollars(chosen.get('value')), average_per_year=dollars(chosen.get('apy')),
                            guaranteed=dollars(chosen.get('guaranteed')), team_at_signing=chosen.get('team'),
                            source=source_url, match_method=match_method, status='imported_unreviewed')
        players.append(dict(id=identity,name=latest['full_name'],position=latest['position'],
                            jersey_number=active[-1].get('jersey_number') or None,
                            team=team['team_name'],team_code=primary,team_id='NFL_'+primary,
                            teams=team_codes,home_state=team['practice_state'],
                            latest_roster_status=latest['status'],last_observed_week=int(latest['week']),
                            active_weeks=len({r['week'] for r in active}),
                            contract=contract,season_cash=cash,season_history=history,
                            estimate_id=model['id'] if model else None,
                            estimate_cash=model['annual_cash'] if model else None,
                            data_status='estimate_available' if model else 'contract_details' if contract else 'roster_only',
                            source_url=source_url,accessed_date=accessed_date))
    players.sort(key=lambda p: normalize(p['name']))
    if len({p['id'] for p in players}) != len(players):
        raise ValueError('Duplicate player identity.')
    featured = sorted([p for p in players if p['contract'] and p['contract']['year_signed'] == 2025 and p['contract']['total_value']],
                      key=lambda p:p['contract']['total_value'],reverse=True)[:6]
    return dict(metadata=dict(season=2025,accessed_date=accessed_date,roster_definition='Players with ACT or INA status in at least one 2025 regular-season weekly roster. Includes later injured, released and traded players; not a single-date 53-man roster.',
                              player_count=len(players),team_count=len({t for p in players for t in p['teams']}),
                              contract_count=sum(p['contract'] is not None for p in players),
                              cash_count=sum(p['season_cash'] is not None for p in players),
                              estimate_count=sum(p['estimate_id'] is not None for p in players),
                              contract_units='Source Parquet amounts are millions of USD; stored amounts are USD.',
                              sources=[ROSTER_SOURCE,CONTRACT_SOURCE],
                              featured_definition='Largest reported total contract values among matched contracts signed in 2025; signing dates within the year are not supplied.'),
                featured_ids=[p['id'] for p in featured],players=players)


@lru_cache(maxsize=1)
def load_directory():
    return json.loads(DATA.read_text())


def summary(player):
    return {key:player[key] for key in ('id','name','position','team','team_code','teams','data_status','estimate_id')}


def search_players(query, limit=10):
    tokens = normalize(query).split()
    if not tokens:
        return []
    matches = []
    name_matches = []
    for player in load_directory()['players']:
        name = normalize(player['name'])
        haystack = normalize(' '.join((player['name'],player['team'],player['team_code'],player['position'])))
        compact_query = ''.join(tokens)
        if all(token in haystack for token in tokens) or compact_query in haystack.replace(' ', ''):
            rank = (not name.replace(' ', '').startswith(compact_query), name)
            matches.append((rank,player))
            if all(token in name for token in tokens) or compact_query in name.replace(' ', ''):
                name_matches.append((rank,player))
    matches = name_matches or matches
    matches.sort(key=lambda row:row[0])
    return [summary(p) for _,p in matches[:limit]]


def find_player(player_id):
    return next((p for p in load_directory()['players'] if p['id']==player_id),None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rosters',type=Path,required=True)
    parser.add_argument('--contracts',type=Path,required=True)
    parser.add_argument('--accessed-date',default=date.today().isoformat())
    args=parser.parse_args()
    import pyarrow.parquet as pq  # Optional import-only dependency.
    schema=pq.read_schema(args.contracts)
    required = {'gsis_id', 'otc_id', 'player', 'year_signed', 'season_history'}
    if not required.issubset(schema.names):
        raise ValueError('Use the current historical-contracts Parquet release, not the stale CSV.')
    history_fields = {field.name for field in schema.field('season_history').type.value_type}
    if not {'year', 'team', 'cash_paid', 'base_salary', 'cap_number'}.issubset(history_fields):
        raise ValueError('The source is missing required season cash fields.')
    with args.rosters.open() as stream:
        rosters=list(csv.DictReader(stream))
    with (ROOT/'data/curated/teams.csv').open() as stream:
        teams={r['team_id']:r for r in csv.DictReader(stream)}
    reviewed=json.loads((ROOT/'data/curated/demo_contracts_2025.json').read_text())
    directory=build_directory(rosters,pq.read_table(args.contracts).to_pylist(),reviewed,teams,args.accessed_date)
    directory['metadata']['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.rosters,args.contracts)}
    directory['metadata']['contract_source_timestamp']=(schema.metadata or {}).get(b'nflverse_timestamp',b'unknown').decode()
    DATA.parent.mkdir(parents=True,exist_ok=True)
    DATA.write_text(json.dumps(directory,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(directory['metadata'],indent=2))


if __name__=='__main__':
    main()
