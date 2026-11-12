"""MLB cash-based U.S. tax illustrations from contract start through 2026.

Published fixtures are observations; attendance, travel and residence are
assumptions. No NFL calendars, opponent rotations or frozen-year forecasts.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import json
from etl.mlb_contract_terms import select_contract, boundaries

ROOT=Path(__file__).resolve().parents[1]
SUPPORTED_YEARS=tuple(range(2015,2027))
LOCALITIES={'Philadelphia':'PHL','Cincinnati':'CIN','Kansas City':'KCM'}

@lru_cache(maxsize=1)
def data():
    return json.loads((ROOT/'data/snapshots/mlb_players.json').read_text())

@lru_cache(maxsize=1)
def players():
    return {p['id']:p for p in data()['players']}

@lru_cache(maxsize=1)
def cash_index():
    return {(r['player_id'],r['year']):r for r in data()['cash']}

@lru_cache(maxsize=2048)
def contract_window(player_id):
    """A source's playing-year contract window, never a player's career span."""
    p=players()[player_id]
    reviewed=json.loads((ROOT/'data/curated/mlb_contracts_spotrac.json').read_text())['players'].get(player_id)
    chosen=select_contract(data(),p)
    start=reviewed['start_year'] if reviewed else boundaries(chosen)[0]
    end=reviewed['end_year'] if reviewed else boundaries(chosen)[1]
    known=bool(start and end)
    return dict(start=start,end=end,verified=known,years=list(range(start,min(end,2026)+1)) if known else [2025,2026],
                basis='Reported contract playing years through 2026' if known else 'Contract start unavailable; only the existing 2025/2026 annual cash window is shown')

@lru_cache(maxsize=1)
def schedule_data():
    return json.loads((ROOT/'data/snapshots/mlb_schedules.json').read_text())

@lru_cache(maxsize=1)
def games_index():
    result=defaultdict(list)
    snapshot=schedule_data()
    seen=set()
    for g in snapshot['games']:
        key=(g['year'],g['id'])
        if g['date']>data()['metadata']['as_of'] or g['abstract_status']!='Final' or any(word in g['status'].lower() for word in ('cancel','postpon','suspend')):continue
        if key in seen:continue
        seen.add(key)
        for tid in (g['home'],g['away']):
            if tid in data()['teams']:result[(tid,g['year'])].append(g)
    return result

def year_coverage(player_id,year):
    if year not in contract_window(player_id)['years']:return 'Outside the reported contract window through 2026.'
    cash=cash_index().get((player_id,year))
    if not cash or cash['amount']<=0:return 'Reported annual cash is not available.'
    clubs=data()['memberships'].get(player_id,{}).get(str(year),[])
    if not clubs:return 'No historical major-league team membership was imported for this year.'
    if len(clubs)!=1:return 'Multiple teams in this season; verified membership dates are needed before allocating duty days.'
    games=games_index().get((clubs[0],year),[])
    regular=[g for g in games if g['stage']=='R']
    expected=schedule_data()['metadata']['regular_game_counts'].get(str(year),{}).get(clubs[0])
    if not expected or expected<(58 if year==2020 else 160) or len(regular)!=expected:
        return 'The completed regular-season schedule does not reconcile to MLB standings; this year is excluded.'
    if any(not g['country'] or (g['country'] in ('USA','United States') and not g['state']) for g in games):
        return 'A game venue has no verified jurisdiction; this year is excluded.'
    return None

def location(game):
    state=game['state']
    local='MDNR' if state=='MD' else LOCALITIES.get(game['city']) if state else None
    return dict(state=state,country=game['country'],city=game['city'],locality=local)

@lru_cache(maxsize=512)
def calendar(team_id,year,early_camp=False,include_postseason=True):
    if year not in SUPPORTED_YEARS:raise ValueError('MLB estimates require imported historical schedules and stop at 2026.')
    info=data()['teams'][team_id]
    games=sorted((g for g in games_index().get((team_id,year),[]) if include_postseason or g['stage'] in ('S','R')),key=lambda g:(g['date'],g['id']))
    regular=[g for g in games if g['stage']=='R']
    if len(regular)<(58 if year==2020 else 160):raise ValueError('Completed MLB schedule is incomplete.')
    workout=info.get('workouts',{}).get(str(year))
    if workout:
        start=date.fromisoformat(workout['pitcher_catcher' if early_camp else 'position']);camp_basis='Published club first workout date'
    else:
        first=min(date.fromisoformat(g['date']) for g in games if g['stage']=='S')
        start=first-timedelta(days=12 if early_camp else 7)
        camp_basis='Estimated camp start: 12 days (pitchers/catchers) or 7 days (position players) before first published spring game; not a verified reporting date'
    end=max(date.fromisoformat(g['date']) for g in games if g['stage']!='S')
    spring_end=max((date.fromisoformat(g['date']) for g in games if g['stage']=='S'),default=date(year,3,25))
    if year==2020:spring_end=date(2020,3,12)
    by_day=defaultdict(list)
    for g in games:by_day[g['date']].append(g)
    rows=[];ambiguous=[];day=start
    while day<=end:
        if year==2020 and date(2020,3,12)<day<date(2020,7,1):
            day+=timedelta(days=1);continue
        scheduled=by_day[day.isoformat()]
        if scheduled:
            distinct={(g['state'],g['country']) for g in scheduled}
            if len(distinct)>1:
                if any(g['stage']!='S' for g in scheduled):raise ValueError('Conflicting regular-season venues for a duty date.')
                where=dict(state=info['spring_state'],country='USA',city=None,locality=None)
                ambiguous.append(day.isoformat());basis='split-squad location assumed at spring base'
            else:where=location(scheduled[0]);basis='published game venue'
        else:
            before=[g for g in games if date.fromisoformat(g['date'])<day]
            after=[g for g in games if date.fromisoformat(g['date'])>day]
            prior=before[-1] if before else None;following=after[0] if after else None
            if prior and following and following['venue_id']==prior['venue_id'] and (date.fromisoformat(following['date'])-date.fromisoformat(prior['date'])).days<=4:
                where=location(following);basis='off day between games at same venue'
            elif following and prior and (date.fromisoformat(following['date'])-day).days==1:
                where=location(following);basis='assumed arrival / travel destination'
            else:
                home_games=[g for g in games if g['stage']=='R' and g['home']==team_id]
                past_home=[g for g in home_games if g['date']<day.isoformat()]
                home=(past_home[-1] if past_home else home_games[0]) if home_games else None
                state=info['spring_state'] if day<=spring_end else home['state'] if home else info['state']
                where=dict(state=state,country='USA' if state else (home['country'] if home else 'Canada'),city=None,locality=None)
                basis='assumed spring base' if day<=spring_end else 'assumed team base / off day'
        rows.append(dict(date=day.isoformat(),basis=basis,games=[g['id'] for g in scheduled],**where))
        day+=timedelta(days=1)
    return dict(rows=rows,start=start.isoformat(),end=end.isoformat(),regular_games=len(regular),
                spring_games=sum(g['stage']=='S' for g in games),postseason_games=sum(g['stage'] not in ('S','R') for g in games),ambiguous_dates=ambiguous,camp_basis=camp_basis)

def calculation_inputs(player_id,year,residence,filing='single'):
    reason=year_coverage(player_id,year)
    if reason:raise ValueError(reason)
    p=players()[player_id];tid=data()['memberships'][player_id][str(year)][0]
    cal=calendar(tid,year,p['position_code'] in ('P','SP','RP','C','TWP','Y'))
    rows=cal['rows'];gross=cash_index()[player_id,year]['amount'];n=len(rows)
    counts=Counter(r['state'] for r in rows if r['state']);foreign=sum(not r['state'] for r in rows)
    early=sum(r['date'][5:]<'07-01' for r in rows);local=defaultdict(lambda:dict(early=0,late=0))
    for r in rows:
        locality=r['locality']
        if locality=='MDNR' and residence=='MD':continue
        # Do not carry the supported 2025/2026 local rates back into older years.
        if locality and year>=2025:local[locality]['early' if r['date'][5:]<'07-01' else 'late']+=gross/n
    inputs=dict(tax_year=year,residence=residence,filing=filing,salary=gross,bonus=0,other_cash=0,
                bonus_treatment='conditional',days=dict(counts),unsourced=foreign,early_cash=gross*early/n,local_work=dict(local))
    return inputs,cal

@lru_cache(maxsize=256)
def estimate(calculate,player_id,residence,filing='single'):
    if player_id not in players():raise ValueError('MLB player not found in the active roster snapshot.')
    states={t['state'] for t in data()['teams'].values() if t['state']}
    if residence not in states:raise ValueError('Choose a supported U.S. MLB comparison state. Canadian residence is not yet modeled.')
    if filing not in ('single','mfj'):raise ValueError('Choose a supported filing status.')
    annual=[];excluded=[];sources=[]
    window=contract_window(player_id)
    for year in window['years']:
        reason=year_coverage(player_id,year)
        if reason:excluded.append(dict(year=year,reason=reason));continue
        try:
            inputs,cal=calculation_inputs(player_id,year,residence,filing)
            result=calculate(inputs)
        except ValueError as error:
            excluded.append(dict(year=year,reason=str(error)));continue
        tid=data()['memberships'][player_id][str(year)][0]
        annual.append(dict(year=year,team=data()['teams'][tid]['name'],team_id=tid,cash=result['gross'],
            federal=result['national']['federal'],payroll=result['national']['payroll']['total'],state=result['tax']['total'],local=result['local']['total'],
            total_tax=result['total_tax'],remaining=result['remaining'],local_supported=year>=2025,duty_days=len(cal['rows']),
            foreign_days=inputs['unsourced'],regular_games=cal['regular_games'],spring_games=cal['spring_games'],postseason_games=cal['postseason_games'],
            start=cal['start'],end=cal['end'],camp_basis=cal['camp_basis'],ambiguous_dates=cal['ambiguous_dates'],state_days=inputs['days'],
            federal_tax_year=year,calendar=cal['rows'],source_url=cash_index()[player_id,year]['source_url']))
        sources.extend(result['sources'])
    total=lambda key:sum(row[key] for row in annual) if annual else None
    return dict(player_id=player_id,residence=residence,filing=filing,as_of=data()['metadata']['as_of'],annual=annual,excluded=excluded,
        included_years=[r['year'] for r in annual],contract_window=window,gross=total('cash'),total_tax=total('total_tax'),remaining=total('remaining'),future_taxes=False,
        scope='Known-years U.S. cash subtotal, not the after-tax value of the entire contract.',
        sources=list({(s['state'],s['source']):s for s in sources}.values()),notes=[
            'The window starts at the reported contract start and ends at the earlier of its reported end and 2026. Prior-deal income and 2027 onward are excluded. If contract boundaries are unavailable, the existing 2025/2026 annual cash window is labeled separately. Missing years are never silently zero-filled.',
            'MLB published venues include spring training, regular season and played postseason. A doubleheader counts as one duty date. 2025/2026 use published club workout dates; earlier camp starts are explicitly estimated from first spring games. The 2020 suspension from March 13 through June 30 is excluded; summer-camp reporting resumes July 1.',
            'Attendance is estimated for the full team season, from first workout through the last played postseason game. A single historical team is required. Call-ups, minor-league service, injuries, individual travel, All-Star/WBC participation and offseason work are unverified; these are not actual player duty-day records.',
            'Off days between games at the same venue stay there; other off days immediately before a game assume arrival at its venue, with remaining days at spring/team base. Split-squad games in different states assume the spring base and are flagged in the annual breakdown.',
            'Reported Spotrac total cash approximates calendar-year wages and may include listed incentives that are not verified earned income. All cash is treated as service wages; exact signing-bonus sourcing and payment dates are unverified. No AAV or prorated signing bonus is used as cash.',
            'U.S. resident, wage-only, standard-deduction federal model. State sourcing and resident credits are simplified; no residence-city tax, unsupported local/county tax, state payroll program, deductions or agent fees. Selected local work taxes are PHL, CIN, KCM and Maryland special nonresident tax; local payment timing is assumed uniform over duty days.',
            'Foreign duty days remain in the denominator. Canadian and other foreign income taxes and treaty/foreign-tax credits are excluded. Toronto/Canadian-residence base results are unavailable. U.S. comparison-state results assume U.S. tax residence and are U.S. components only.',
            'Deferred compensation is not moved into playing-year cash. Special FICA timing on deferred compensation is not modeled; Ohtani cash-based payroll estimates may omit liabilities attributable to vested deferrals.'
            ,'Historical state tables are annual published research inputs, with selected government corrections; some inflation thresholds may reflect the prior year noted by the source. State deductions, recapture, AMT and credits remain simplified. Pre-2025 local taxes are not yet supported and are explicitly excluded from those totals, rather than applying current rates backward.'
        ])
