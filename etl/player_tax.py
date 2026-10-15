"""Turn sourced annual cash into explicit, provisional NFL tax-model inputs."""
from copy import deepcopy
from functools import lru_cache
from etl.contract_data import load_contracts

@lru_cache(maxsize=1)
def reviewed_contracts():
    return {r['id']:r for r in load_contracts()}

def tax_contract(player):
    reviewed_id=player.get('estimate_id')
    if reviewed_id in reviewed_contracts():
        row=deepcopy(reviewed_contracts()[reviewed_id])
        row.update(player_id=player['id'],reviewed_snapshot=True,needs_cash=False,bonus_assumption='qualifying')
        return row
    cash=player.get('season_cash')
    needs_cash=cash is None or cash<=0
    contract=player.get('contract') or {}
    season=player['season_history'][0] if len(player.get('season_history',[]))==1 else {}
    notes=['Imported, unreviewed tax estimate: reported season cash is a proxy for calendar-year wages, not a verified W-2.',
           'All cash is initially modeled as service wages. Signing/option bonus cash and qualification are not inferred from cap proration. You may reclassify an assumed signing-bonus amount.',
           'Full-year domicile defaults to the last observed 2025 team practice state; this is an assumption, particularly for traded players.',
           'Weekly 2024/2025 roster observations approximate team transitions. Exact transactions, individual travel, offseason services and injury locations remain unverified.']
    if needs_cash:notes.append('The source lacks positive usable 2025 cash. Supply a verified annual cash amount before calculating; no zero-tax result is inferred.')
    return dict(id=player['id'],player_id=player['id'],player=player['name'],team=player['team'],team_id=player['team_id'],
                home_state=player['home_state'],year=2025,extension_value=contract.get('total_value'),
                extension_years=contract.get('years'),aav=contract.get('average_per_year'),fully_guaranteed=None,
                total_guarantees=contract.get('guaranteed'),base_salary=0 if needs_cash else cash,
                signing_bonus_cash=0,other_cash=0,annual_cash=None if needs_cash else cash,
                cap_charge=season.get('cap_number'),cap_bonus_proration=None,
                status='cash_required' if needs_cash else 'imported_unreviewed',accessed_date=player['accessed_date'],
                sources=[dict(name='OverTheCap via nflverse',url=player.get('source_url') or 'https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet',scope='Reported 2025 season cash; model initially allocates it all as service wages.')],
                notes=notes,reviewed_snapshot=False,needs_cash=needs_cash,bonus_assumption='conditional')

def with_tax_info(player):
    """Attach runtime coverage without rewriting the source snapshot or its reviewed IDs."""
    view=dict(player);row=tax_contract(player)
    view.update(estimate_id=row['id'],estimate_cash=row['annual_cash'],tax_ready=not row['needs_cash'],
                reviewed_example=row['reviewed_snapshot'],data_status='cash_required' if row['needs_cash'] else 'estimate_available')
    return view
