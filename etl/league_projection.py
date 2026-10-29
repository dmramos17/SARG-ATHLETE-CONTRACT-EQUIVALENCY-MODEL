"""League-wide contract cash-window projections with explicit coverage limits."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from itertools import product
from pathlib import Path
import json
from etl.estimated_duty_days import teams, estimate_player_calendar, STATES
from etl.player_directory import find_player
from etl.contract_projection import model_inputs, project as allen_project

ROOT=Path(__file__).resolve().parents[1]
DIVISIONS={'AFCE':['BUF','MIA','NE','NYJ'],'AFCN':['BAL','CIN','CLE','PIT'],
 'AFCS':['HOU','IND','JAX','TEN'],'AFCW':['DEN','KC','LAC','LV'],
 'NFCE':['DAL','NYG','PHI','WAS'],'NFCN':['CHI','DET','GB','MIN'],
 'NFCS':['ATL','CAR','NO','TB'],'NFCW':['ARI','LAR','SF','SEA']}
DIVISION={team:div for div,group in DIVISIONS.items() for team in group}
NICKNAMES={t['team_name'].split()[-1]:key for key,t in teams().items()}
NICKNAMES.update({'Redskins':'NFL_WAS','Washington':'NFL_WAS','Football Team':'NFL_WAS'})

@lru_cache(maxsize=1)
def data():
    return json.loads((ROOT/'data/snapshots/contract_projections.json').read_text())

@lru_cache(maxsize=1)
def games_by_team():
    result=defaultdict(list)
    for game in data()['games']:
        for team in (game['home'],game['away']):result[team].append(game)
    return result

@lru_cache(maxsize=512)
def rotation(team,year):
    if str(year) in data()['rotations'][team]:return data()['rotations'][team][str(year)]
    if year<2025:raise ValueError('No published rotation for that year.')
    # Extend current 17-game format: conference division flips every 3 years,
    # cross-conference division every 4, standings conference slots every 6.
    own=DIVISION[team];conference=own[:3]
    result={'home':[],'away':[]}
    for other in DIVISIONS[own]:
        if other!=team:
            result['home'].append(other);result['away'].append(other)
    for lag,kind in [(3,'conference'),(4,'interconference'),(6,'standing_conference'),(4,'standing_interconference')]:
        previous=rotation(team,year-lag)
        for key in ('home','away'):
            for op in previous[key]:
                if op in DIVISIONS:
                    include=(op[:3]==conference) if kind=='standing_conference' else (op[:3]!=conference) if kind=='standing_interconference' else False
                else:
                    include=(DIVISION[op][:3]==conference and DIVISION[op]!=own) if kind=='conference' else (DIVISION[op][:3]!=conference) if kind=='interconference' else False
                if include:result['away' if key=='home' else 'home'].append(op)
    return result

def slots(team,year):
    row=rotation(team,year);result=[]
    for i in range(max(len(row['home']),len(row['away']))):
        for key in ('home','away'):
            if i<len(row[key]):result.append(dict(opponent=row[key][i],home=key=='home'))
    if len(result)!=17:raise ValueError(f'Incomplete {team} {year} rotation.')
    return result

@lru_cache(maxsize=1024)
def season_variants(team,year):
    if year<=2026:
        actual=[dict(g,opponent=g['away'] if g['home']==team else g['home'],home=g['home']==team,date_status='published')
                for g in games_by_team()[team] if g['season']==year and g['stage']=='REG']
        if not actual: return ((),) # Previous-year January may fall outside imported coverage.
        return (tuple(actual),)
    row=slots(team,year);unknown=[i for i,g in enumerate(row) if not g['home'] and g['opponent'] in DIVISIONS]
    result=[];start=date(year,9,7);start+=timedelta(days=(6-start.weekday())%7)
    for choice in product(*(DIVISIONS[row[i]['opponent']] for i in unknown)):
        chosen=dict(zip(unknown,choice));games=[]
        for i,g in enumerate(row):
            op=chosen.get(i,g['opponent']);info=teams()['NFL_'+(team if g['home'] else op)]
            games.append(dict(opponent=op,home=g['home'],state=info['stadium_state'],city=info['city'],
                locality=info['stadium_locality'] or None,date=(start+timedelta(weeks=i+(i>=8))).isoformat(),stage='REG',date_status='modeled'))
        result.append(tuple(games))
    return tuple(result)

def source_team(cash,default):
    named=cash.get('source_teams',[])
    codes={NICKNAMES.get(n) or NICKNAMES.get(n.split()[-1]) for n in named}
    return next(iter(codes)) if len(codes)==1 and None not in codes else default

@lru_cache(maxsize=128)
def calendar_variants(team_id,previous_id,year,travel_days,rookie=False):
    """Compress equivalent calendar allocations while retaining scenario weights."""
    team=team_id.removeprefix('NFL_');prior=previous_id.removeprefix('NFL_');info=teams()[team_id]
    previous=season_variants(prior,year-1) if not rookie else ((),)
    current=season_variants(team,year)
    additional=[]
    if year<=2026:
        # Actual preseason and completed prior-season postseason locations.
        tagged=[(g,team) for g in games_by_team()[team] if g['date'].startswith(str(year)) and g['stage']=='PRE']
        if not rookie:tagged += [(g,prior) for g in games_by_team()[prior] if g['date'].startswith(str(year)) and g['stage']=='POST']
        additional=[dict(g,opponent=g['away'] if g['home']==employer else g['home'],home=g['home']==employer) for g,employer in tagged]
    compressed={}
    for before,after in product(previous,current):
        winter=[g for g in (*before,*additional) if g['date'].startswith(str(year)) and g['date'][5:]<'03-01']
        windows=[(date(year,7,23),date(year,12,31),team_id)]
        if winter:windows.append((date(year,1,1),max(date.fromisoformat(g['date']) for g in winter),previous_id))
        rows={}
        for start,end,employer in windows:
            day=start;practice=teams()[employer]
            while day<=end:
                if day.weekday()!=1:rows[day.isoformat()]=dict(date=day.isoformat(),state=practice['practice_state'],locality=practice['practice_locality'] or None)
                day+=timedelta(days=1)
        for g in (*before,*after,*additional):
            match=date.fromisoformat(g['date'])
            if match.year!=year:continue
            for lag in range((0 if g['home'] else travel_days)+1):
                day=match-timedelta(days=lag)
                if day.year!=year:continue
                locality=g.get('locality')
                if g['state']=='MD':locality='MDNR'
                rows[day.isoformat()]=dict(date=day.isoformat(),state=g['state'],locality=locality)
        ordered=[rows[k] for k in sorted(rows)]
        signature=tuple(sorted(Counter((r['state'] or '',r.get('locality') or '',r['date'][5:]<'07-01') for r in ordered).items()))
        if signature not in compressed:compressed[signature]=[ordered,0]
        compressed[signature][1]+=1
    return tuple((rows,weight) for rows,weight in compressed.values())

def coverage(player_id):
    row=data()['players'][player_id]
    return dict(year_start=row['cash'][0]['year'],year_end=row['cash'][-1]['year'],missing_years=row['missing_years'],reconciles_headline=row['reconciles_headline'])

@lru_cache(maxsize=128)
def project_player(calculate,player_id,residence=None,filing='single',qualifying=False,travel_days=1):
    player=find_player(player_id)
    if not player:raise ValueError('Player not found in the 2025 directory.')
    if type(travel_days) is not int or not 0<=travel_days<=3:raise ValueError('Travel days must be 0–3.')
    residence=residence or player['home_state']
    if residence not in STATES:raise ValueError('Choose a supported residence state.')
    if filing not in ('single','mfj'):raise ValueError('Choose a supported filing status.')
    if player_id=='00-0034857':
        result=dict(allen_project(calculate,residence,filing,qualifying,travel_days))
        result.update(player_id=player_id,team=player['team'],team_id=player['team_id'],year_start=2025,year_end=2030,
            complete=True,headline_value=330000000,reconciles_headline=True,missing_years=[],reported_guarantees=result['reported_total_guarantees'],
            total_label='Scheduled contract cash',bonus_available=True,coverage_notes=[])
        return result
    contract=data()['players'][player_id];annual=[];previous_cash=None
    for cash in contract['cash']:
        year=cash['year'];historical=year<2025
        employer=source_team(cash,player['team_id']) if historical else player['team_id']
        prior=source_team(previous_cash,employer) if historical and previous_cash else employer
        previous_cash=cash
        schedule=[dict(g,opponent=g['away'] if g['home']==employer.removeprefix('NFL_') else g['home'],home=g['home']==employer.removeprefix('NFL_'),date_status='published')
            for g in games_by_team()[employer.removeprefix('NFL_')] if g['season']==year and g['stage']=='REG'] if year<=2026 else slots(employer.removeprefix('NFL_'),year)
        base=dict(**cash,opponents=schedule,scenarios=0,duty_days=None,schedule_basis='Published games; modeled attendance' if year<=2026 else 'Rotation projection; synthetic dates' if year<=2030 else 'Extrapolated rotation; synthetic dates')
        if cash['cash'] is None:
            annual.append(dict(base,total_tax=None,remaining=None,low_remaining=None,high_remaining=None,federal=None,payroll=None,state=None,local=None));continue
        if year==2025:
            variants=((estimate_player_calendar(player,travel_days=travel_days)['calendar'],1),)
        else:
            variants=calendar_variants(employer,prior,year,travel_days,year==contract.get('draft_year'))
        outcomes=[];normalized=dict(cash,signing_bonus=0)
        for rows,weight in variants:
            inputs=model_inputs(normalized,rows,residence,filing,False)
            result=calculate(inputs);outcomes.append((result,weight))
        count=sum(w for _,w in outcomes)
        mean=lambda f:sum(f(r)*w for r,w in outcomes)/count
        annual.append(dict(base,total_tax=mean(lambda r:r['total_tax']),remaining=mean(lambda r:r['remaining']),
            low_remaining=min(r['remaining'] for r,w in outcomes),high_remaining=max(r['remaining'] for r,w in outcomes),
            federal=mean(lambda r:r['national']['federal']),payroll=mean(lambda r:r['national']['payroll']['total']),
            state=mean(lambda r:r['tax']['total']),local=mean(lambda r:r['local']['total']),
            duty_days=len(variants[0][0]),scenarios=count))
    total=lambda key:sum(r[key] or 0 for r in annual)
    complete=not contract['missing_years']
    return dict(player=player['name'],player_id=player_id,team=player['team'],team_id=player['team_id'],annual=annual,
        year_start=annual[0]['year'],year_end=annual[-1]['year'],gross=total('cash') if any(r['cash'] is not None for r in annual) else None,
        total_tax=total('total_tax') if any(r['total_tax'] is not None for r in annual) else None,
        remaining=total('remaining') if any(r['remaining'] is not None for r in annual) else None,
        low_remaining=total('low_remaining') if any(r['remaining'] is not None for r in annual) else None,
        high_remaining=total('high_remaining') if any(r['remaining'] is not None for r in annual) else None,
        fully_guaranteed_at_signing=None,reported_total_guarantees=None,reported_guarantees=contract['reported_guarantees'],
        headline_value=contract['headline_value'],reconciles_headline=contract['reconciles_headline'],complete=complete,
        missing_years=contract['missing_years'],total_label='Reported cash window' if complete else 'Known-years cash subtotal',
        residence=residence,filing=filing,qualifying=False,bonus_available=False,travel_days=travel_days,tax_rule_year=2025,
        accessed_date=contract['accessed_date'],coverage_notes=contract['notes'],sources=[
            dict(name='OverTheCap player cash history via nflverse',url=contract['source_url'] or data()['metadata']['contract_source']),
            dict(name='nflverse contract import',url=data()['metadata']['contract_source']),
            dict(name='NFL Record & Fact Book: future opponents, pages 12–17',url=data()['metadata']['rotation_source']+'#page=12'),
            dict(name='NFL scheduling formula',url='https://operations.nfl.com/calendar-events/nfl-schedule/making-the-schedule'),
            dict(name='ESPN published calendar-year games, 2020–2027',url=data()['metadata']['schedule_source'])],
        notes=[
            'Frozen 2025 tax rules apply to EVERY year, including past years. Earlier-year results are comparable-rule illustrations, not actual historical taxes or a future-law forecast. No inflation or discounting is applied.',
            'The window begins in the reported signing year and ends at the later of the last positive reported cash year or the nominal signed-year-plus-term boundary. Extension start/end dates may differ. Only reported positive annual cash is calculated; missing and zero entries are not assumed tax-free. Void-year cap charges are not compensation.',
            'Headline contract value is shown separately from the cash-window total. Extension new money and replaced existing years may not reconcile. Complete means every year in the displayed window has usable cash, not that headline value or legal contract boundaries are verified.',
            'All imported cash is initially service wages. Signing and option bonus qualification cannot be established from cap proration; no signing cash is inferred. The reviewed Allen pilot retains its optional signing-bonus assumption.',
            '2025 uses each player\'s existing weekly-roster calendar. Before 2025, a single reported cash-history team selects the team schedule; multiple-team years fall back to the selected 2025 team. Midyear transactions and historical residence are unverified. Future years assume the player remains with the selected 2025 team and earns all scheduled cash.',
            'Outside 2025, camp begins July 23 in the team practice state, Tuesday is off, and chosen arrival days apply to road games. Published preseason and completed postseason are included where imported. Unpublished playoffs, joint practices, offseason service and future camp relocations are excluded.',
            'Calendar years include January service from the prior football season once. Known venues retain international and relocated games. For projections, dates alternate home/away with Sundays and a Week 9 bye; this order is synthetic. Future international designations and stadium moves are unknown.',
            '2027–2030 use published team rotation slots. Beyond 2030 the current 17-game format and division rotation cycles are extrapolated, with home/away reversal assumptions; these are not announced fixtures.',
            'Unknown away opponents are independently equally weighted among the four teams in the specified division. Results are scenario means. Ranges sum annual extrema and are scenario envelopes, not confidence intervals or assured achievable contract paths.',
            'Reported season cash approximates calendar-year wages. Exact payment timing is unverified; local payment halves assume uniform cash over modeled duty dates. State credit/deduction simplifications and unsupported local, county, foreign and state payroll taxes remain excluded. No residence-city tax is assumed.'
        ]+contract['notes'])
