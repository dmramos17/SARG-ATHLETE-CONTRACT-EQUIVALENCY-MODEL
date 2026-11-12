"""Same-league comparisons using fixed saved team residence assumptions."""
from functools import lru_cache
from etl.player_directory import load_directory
from etl.mlb_interface import catalog
from etl.estimated_duty_days import STATES
from etl.league_projection import project_player
from etl.mlb_projection import project as mlb_project


@lru_cache(maxsize=2)
def directory(league):
    league=league.upper()
    if league not in ('NFL','MLB'):raise ValueError('Choose NFL or MLB.')
    raw=load_directory()['players'] if league=='NFL' else catalog()['players']
    result=[]
    for p in raw:
        c=p.get('contract') or {}
        residence=p.get('home_state') if league=='NFL' else p.get('base_state')
        result.append(dict(id=p['id'],name=p['name'],team=p['team'],league=league,
                           team_code=p['team_code'],team_id=p['team_id'],
                           photo_url=(f"https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto:best/v1/people/{p['id']}/headshot/67/current" if league=='MLB' else None),
                           logo_url=(f"https://www.mlbstatic.com/team-logos/{p['team_id']}.svg" if league=='MLB' else f"https://a.espncdn.com/i/teamlogos/nfl/500/{p['team_code'].lower()}.png"),
                           residence=residence,residence_name=STATES.get(residence,'Ontario, Canada · not modeled'),
                           headline_value=c.get('total_value') if league=='NFL' else c.get('headline_value'),
                           years=c.get('years'),url=('/taxes/' if league=='NFL' else '/mlb/players/')+p['id']))
    return result


def suggestions(league, player_id, limit=6):
    rows=directory(league);p=next((r for r in rows if r['id']==player_id),None)
    if not p:raise ValueError('Player not found in this league.')
    if not p['headline_value'] or not p['years']:return []
    scored=[]
    for candidate in rows:
        if candidate['id']==player_id or not candidate['headline_value'] or not candidate['years']:continue
        # Symmetric proportional differences give dollars and years equal importance.
        value_gap=abs(candidate['headline_value']-p['headline_value'])/max(candidate['headline_value'],p['headline_value'])
        term_gap=abs(candidate['years']-p['years'])/max(candidate['years'],p['years'])
        scored.append(dict(candidate,similarity_score=(value_gap+term_gap)/2))
    return sorted(scored,key=lambda r:(r['similarity_score'],r['name'],r['id']))[:limit]


def summary(calculate,league,player):
    row=dict(player);residence=row['residence']
    if not residence:
        return dict(row,income=None,total_tax=None,remaining=None,take_home_percentage=None,annual_take_home=None,
                    included_years=[],excluded_years=[],conditional_years=[],complete=False,
                    notes=['Canadian residence is not modeled. This player’s team-based tax estimate is unavailable.'])
    if league=='NFL':
        result=project_player(calculate,row['id'],residence)
        income=result['gross'];complete=result['coverage_complete']
        annual=[r for r in result['annual'] if r['remaining'] is not None]
        excluded=result['missing_years'];conditional=[]
        notes=['NFL uses the existing full-contract cash projection and frozen 2025 tax rules. Future opponent scenarios use their mean.']
        if not complete:notes.append('Partial projection: only included cash years contribute to income, tax, take-home and annual averages.')
        notes.extend(result['coverage_notes']);notes.extend(result['coverage_issues'])
    else:
        result=mlb_project(calculate,row['id'],residence,full=True)
        income=result['salary'];complete=result['complete'];annual=result['annual']
        excluded=[r['year'] for r in result['excluded']];conditional=result['conditional_years']
        notes=['MLB uses reported nominal salaries and verified signing cash with deferred-payment timing set aside. Historical years use matching rules; future years repeat 2025/2026 work patterns under fixed 2026 rules.']
        if result['reason']:notes.append(result['reason'])
        notes.extend(result['coverage_notes'])
        notes.extend(f"{r['year']} excluded: {r['reason']}" for r in result['excluded'])
        if income is not None and row['headline_value'] is not None and abs(income-row['headline_value'])>1:
            notes.append('Modeled income differs from the reported headline value; unverified compensation is not filled in.')
        if any(r['year']<2025 for r in annual):notes.append('Local taxes before 2025 are not modeled and are excluded from those totals.')
        if conditional:notes.append('Conditional option/vesting/opt-out years assume continuation; those amounts are not guaranteed.')
    remaining=result['remaining']
    return dict(row,income=income,total_tax=result['total_tax'],remaining=remaining,
                take_home_percentage=remaining/income*100 if income and remaining is not None else None,
                annual_take_home=remaining/len(annual) if annual and remaining is not None else None,
                included_years=[r['year'] for r in annual],excluded_years=excluded,conditional_years=conditional,
                headline_gap=row['headline_value']-income if row['headline_value'] is not None and income is not None else None,
                unallocated_signing_bonus=result.get('unallocated_signing_bonus',0),complete=complete,notes=notes)


def compare(calculate,league,left_id,right_id):
    league=league.upper();rows={p['id']:p for p in directory(league)}
    if left_id not in rows or right_id not in rows:raise ValueError('Choose two players from the selected league.')
    if left_id==right_id:raise ValueError('Choose two different players.')
    return dict(league=league,players=[summary(calculate,league,rows[pid]) for pid in (left_id,right_id)],
                assumptions='Each player uses the saved team-based residence, single filing, and the model’s default attendance assumptions. Residence and citizenship are not verified. U.S. components only; Canadian and other foreign taxes are excluded. Different contracts can cover different calendar years; this is not an isolated measure of tax-location effects.')
