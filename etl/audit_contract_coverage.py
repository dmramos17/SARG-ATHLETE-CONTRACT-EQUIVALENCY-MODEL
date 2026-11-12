"""Offline roster-wide dollar/window coverage audit; no invented compensation."""
from collections import Counter
import json
from pathlib import Path
from etl.mlb_model import players
from etl.mlb_projection import project
from etl.league_projection import data as nfl_data


def audit(calculate):
    records=[]
    for pid,p in players().items():
        r=project(calculate,pid,'FL',full=True)
        records.append(dict(league='MLB',player_id=pid,player=p['name'],headline_value=r['headline_value'],
                            modeled_income=r['salary'],included_years=r['included_years'],excluded_years=[y['year'] for y in r['excluded']],
                            headline_gap=r['headline_gap'],complete=r['complete'],
                            unallocated_signing_bonus=r['unallocated_signing_bonus'],
                            issues=r['coverage_notes']+([r['reason']] if r['reason'] else [])))
    for pid,c in nfl_data()['players'].items():
        usable=[r for r in c['cash'] if r['cash'] is not None]
        modeled=sum(r['cash'] for r in usable) if usable else None
        headline=c['headline_value'];gap=headline-modeled if headline is not None and modeled is not None else None
        complete=bool(usable) and not c['missing_years'] and gap is not None and abs(gap)<=1
        records.append(dict(league='NFL',player_id=pid,player=c['player'],headline_value=headline,modeled_income=modeled,
                            included_years=[r['year'] for r in usable],excluded_years=c['missing_years'],headline_gap=gap,complete=complete,
                            issues=(['Missing annual cash.'] if c['missing_years'] else [])+(['Headline/model dollar mismatch.'] if gap is None or abs(gap)>1 else [])))
    counts={league:dict(Counter('reconciled' if r['complete'] else 'partial' if r['modeled_income'] is not None else 'unavailable'
                              for r in records if r['league']==league)) for league in ['NFL','MLB']}
    return dict(audited_date='2026-11-12',basis='Income coverage, not verified tax liability. MLB uses a common U.S. comparison residence solely to audit inputs; NFL preserves existing forecast cash windows.',counts=counts,players=records)


if __name__=='__main__':
    from dashboard.server import calculate
    result=audit(calculate)
    path=Path(__file__).resolve().parents[1]/'data/processed/contract_coverage_audit.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['counts']))
