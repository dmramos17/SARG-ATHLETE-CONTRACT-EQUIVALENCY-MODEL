"""Searchable current active MLB roster, sourced contracts and tax coverage."""
from functools import lru_cache
from pathlib import Path
import json
from etl.estimated_duty_days import STATES
from etl.mlb_model import data, cash_index, year_coverage, contract_window
from etl.mlb_projection import salary_window
from etl.mlb_contract_terms import select_contract, boundaries
from etl.recent_contracts import recent_contracts

@lru_cache(maxsize=1)
def catalog():
    snapshot=data()
    reviewed=json.loads((Path(__file__).resolve().parents[1]/'data/curated/mlb_contracts_spotrac.json').read_text())['players']
    result=[]
    for original in snapshot['players']:
        p=dict(original)
        window=contract_window(p['id']);years=window['years']
        records=[r for y in years if (r:=cash_index().get((p['id'],y)))]
        contract=reviewed.get(p['id'])
        chosen=select_contract(snapshot,p)
        if contract:
            contract=dict(contract,source_name='Spotrac',detailed_cash=True)
        elif chosen:
            s=chosen['summary']
            contract=dict(team=p['team'],years=boundaries(chosen)[1]-boundaries(chosen)[0]+1 if all(boundaries(chosen)) else s['YearsTotal'],headline_value=s['ContractTotal'],start_year=boundaries(chosen)[0],end_year=boundaries(chosen)[1],
                reported_guarantees=None,average_annual_value=None,signing_bonus=s['SigningBonus'],deferred_total=None,
                source_url=chosen['source_url'],source_name='FanGraphs RosterResource',accessed_date=snapshot['metadata']['as_of'],
                description=chosen['description'],detailed_cash=False,annual=[dict(year=r['Season'],base_salary=r['BaseSalary'],prorated_bonus=r['ProratedSigningBonus'],phase=r['Type']) for r in chosen['annual'] if r['ContractId'] is not None],
                notes=['Reported contract terms are separate from annual cash. Payroll salary, AAV and prorated signing bonuses are not tax inputs. Cash below comes from the separate Spotrac year rankings. Options, incentives, deferrals and legal guarantees require individual review.'])
        if contract:
            signed=(chosen['summary'].get('ContractDate') or '')[:10] if chosen else ''
            contract['signing_date']=signed if signed and signed<=snapshot['metadata']['as_of'] else None
            contract['signing_year']=int(signed[:4]) if contract['signing_date'] else None
        included=[y for y in years if year_coverage(p['id'],y) is None]
        future=salary_window(p['id'])
        p.update(projection_years=[r['year'] for r in future['annual'] if not r['reason']],projection_reason=future['reason'],contract=contract,contract_status='reported_snapshot' if contract else 'cash_only' if records else 'not_reported',cash_records=records,
                 tax_status='provisional' if included else 'inputs_required',tax_years=included,
                 contract_window=window,coverage=[dict(year=y,reason=year_coverage(p['id'],y)) for y in years])
        result.append(p)
    recent=recent_contracts([dict(id=p['id'],value=p['contract']['headline_value'],signing_year=p['contract']['signing_year']) for p in result if p['contract']])
    states={t['state'] for t in snapshot['teams'].values() if t['state']}
    return dict(metadata=dict(snapshot['metadata'],recent_start_year=recent['start_year'],recent_end_year=recent['end_year'],featured_definition=recent['definition'],player_count=len(result),team_count=len(snapshot['teams']),estimate_count=sum(bool(p['tax_years']) for p in result),
                              projection_count=sum(bool(p['projection_years']) for p in result),cash_count=sum(bool(p['cash_records']) for p in result),contract_count=sum(p['contract'] is not None for p in result)),
                players=result,featured_ids=recent['ids'],
                comparison_states=[dict(code=s,name=STATES[s]) for s in sorted(states,key=lambda s:STATES[s])])
