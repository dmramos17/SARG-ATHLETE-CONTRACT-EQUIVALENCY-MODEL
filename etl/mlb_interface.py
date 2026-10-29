"""Three MLB player profiles with sourced contract snapshots; taxes are not modeled."""
from functools import lru_cache
from pathlib import Path
import json
from etl.estimated_duty_days import STATES

@lru_cache(maxsize=1)
def catalog():
    data=json.loads((Path(__file__).resolve().parents[1]/'data/curated/mlb_interface_seed.json').read_text())
    snapshots=json.loads((Path(__file__).resolve().parents[1]/'data/curated/mlb_contracts_spotrac.json').read_text())
    by_team={t['code']:t for t in data['teams']}
    players=[dict(p,team=by_team[p['team_code']]['name'],base_state=by_team[p['team_code']]['state'],
                  contract_status='reported_snapshot',contract=snapshots['players'].get(p['id']),tax_status='coming_soon') for p in data['players']]
    state_codes={t['state'] for t in data['teams'] if t['state']}
    return dict(metadata=dict(data['metadata'],contract_status='reported_snapshot',contracts_accessed_date=snapshots['metadata']['accessed_date']),players=players,
                comparison_states=[dict(code=s,name=STATES[s]) for s in sorted(state_codes,key=lambda s:STATES[s])])
