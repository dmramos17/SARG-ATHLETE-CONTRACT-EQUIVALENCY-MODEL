"""Select one source contract and consistently resolve its headline playing years."""
import re


def select_contract(snapshot,player):
    terms=[t for t in snapshot['contracts'].get(player['id'],[]) if t['team_id']==player['team_id'] and not t['summary'].get('isFutureContract')]
    return max(terms,key=lambda t:(t['source_season'],t['summary'].get('startSeason') or 0),default=None)


def boundaries(contract):
    if not contract:return None,None
    summary=contract['summary']
    # The printed headline window includes in-deal player options, without adding
    # extra club/vesting options outside that quoted deal. endSeason/endSeasonAll
    # alone can respectively truncate a deal or append extra conditional years.
    match=re.search(r'\((20\d{2})(?:\s*[-–]\s*(20\d{2}|\d{2}))?\)',contract.get('description') or '')
    if match:
        start=int(match[1]);end=int(match[2]) if match[2] else start
        if end<100:end=2000+end
        if start<=end<=start+25:return start,end
    start=summary.get('startSeason');years=summary.get('YearsTotal')
    if isinstance(start,int) and isinstance(years,(int,float)) and years==int(years) and 0<years<=25:
        return start,start+int(years)-1
    return start,summary.get('endSeason')
