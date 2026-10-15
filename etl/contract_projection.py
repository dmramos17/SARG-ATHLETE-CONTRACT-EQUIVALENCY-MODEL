"""Josh Allen pilot: reported yearly cash, calendar-year work, frozen 2025 tax law."""
from collections import Counter
from datetime import date, timedelta
from functools import lru_cache
from itertools import product
import json
from pathlib import Path
from etl.estimated_duty_days import teams, estimate_calendar

ROOT=Path(__file__).resolve().parents[1]
DIVISIONS={'AFCN':['BAL','CIN','CLE','PIT'],'AFCS':['HOU','IND','JAX','TEN'],
           'AFCW':['DEN','KC','LAC','LV'],'NFCN':['CHI','DET','GB','MIN'],
           'NFCS':['ATL','CAR','NO','TB'],'NFCE':['DAL','NYG','PHI','WAS'],
           'NFCW':['ARI','LAR','SF','SEA']}

@lru_cache(maxsize=1)
def source_data():
    return json.loads((ROOT/'data/curated/josh_allen_contract_projection.json').read_text())

def opponent_slots(year):
    """Published rotation slots; division codes mean a standings-dependent team."""
    rotation=source_data()['rotations'][str(year)]
    slots=[]
    for i in range(max(len(rotation['home']),len(rotation['away']))):
        for key,home in [('home',True),('away',False)]:
            if i<len(rotation[key]):slots.append(dict(opponent=rotation[key][i],home=home))
    return slots

@lru_cache(maxsize=8)
def season_variants(year):
    if year in (2025,2026):
        return (tuple(source_data()['published_schedules'][str(year)]),)
    slots=opponent_slots(year)
    # Only away TBD slots change work jurisdictions. Home TBD opponents stay in NY.
    away_tbd=[i for i,s in enumerate(slots) if not s['home'] and s['opponent'] in DIVISIONS]
    variants=[]
    for choices in product(*(DIVISIONS[slots[i]['opponent']] for i in away_tbd)):
        chosen=dict(zip(away_tbd,choices));rows=[]
        # Synthetic order, a Week 9 bye, and Sundays are assumptions, never fixtures.
        start=date(year,9,7)
        start+=timedelta(days=(6-start.weekday())%7)
        for i,s in enumerate(slots):
            op=chosen.get(i,s['opponent'])
            team=teams().get('NFL_'+op)
            rows.append(dict(opponent=op,home=s['home'],date=(start+timedelta(weeks=i+(i>=8))).isoformat(),
                             state='NY' if s['home'] else team['stadium_state'],
                             city='Orchard Park' if s['home'] else team['city'],date_status='modeled'))
        variants.append(tuple(rows))
    return tuple(variants)

def calendar(year, previous, current, travel_days=1):
    """Calendar-year windows include the prior season's January games once."""
    if year==2025:
        return estimate_calendar('NFL_BUF',travel_days=travel_days)['calendar']
    days={}
    additional=source_data()['additional_2026_games'] if year==2026 else []
    winter=[g for g in (*previous,*additional) if g['date'].startswith(str(year)) and g['date'][5:]<'03-01']
    windows=[(date(year,7,23),date(year,12,31))]
    if winter:windows.append((date(year,1,1),max(date.fromisoformat(g['date']) for g in winter)))
    for start,end in windows:
        day=start
        while day<=end:
            if day.weekday()!=1:days[day.isoformat()]=dict(date=day.isoformat(),state='NY',locality=None,event='Modeled team service')
            day+=timedelta(days=1)
    for g in (*previous,*current,*additional):
        match=date.fromisoformat(g['date'])
        if match.year!=year:continue
        for lag in range((0 if g['home'] else travel_days)+1):
            day=match-timedelta(days=lag)
            if day.year!=year:continue
            state=g['state'];city=g.get('city')
            locality={'Philadelphia':'PHL','Cincinnati':'CIN','Kansas City':'KCM'}.get(city)
            if state=='MD':locality='MDNR'
            days[day.isoformat()]=dict(date=day.isoformat(),state=state,locality=locality,
                                      event=('vs ' if g['home'] else 'at ')+g['opponent'])
    return [days[k] for k in sorted(days)]

def model_inputs(cash, rows, residence, filing, qualifying):
    gross=cash['cash'];bonus=cash['signing_bonus'] if qualifying else 0
    counts=Counter(d['state'] for d in rows if d['state'])
    early=round(gross*sum(d['date'][5:]<'07-01' for d in rows)/len(rows),2)
    local_days=Counter()
    for d in rows:
        city=d.get('locality')
        if city=='MDNR' and residence=='MD':continue
        if city in ('PHL','CIN','KCM','MDNR'):
            local_days[(city,'early' if d['date'][5:]<'07-01' else 'late')]+=1
    work={}
    for (city,period),n in local_days.items():
        work.setdefault(city,dict(early=0,late=0))[period]=min(round((gross-bonus)*n/len(rows),2),early if period=='early' else round(gross-early,2))
    return dict(tax_year=2025,salary=gross-bonus,bonus=bonus,other_cash=0,residence=residence,
                filing=filing,bonus_treatment='qualifying' if qualifying else 'conditional',
                days=dict(counts),unsourced=sum(d['state'] is None for d in rows),
                early_cash=early,local_work=work,resident_city='')

@lru_cache(maxsize=32)
def project(calculate, residence='NY',filing='single',qualifying=False,travel_days=1):
    if type(travel_days) is not int or not 0<=travel_days<=3:raise ValueError('Travel days must be 0–3.')
    data=source_data();annual=[]
    for cash in data['cash']:
        year=cash['year'];outcomes=[];representative=None
        previous=season_variants(year-1) if year>2025 else ((),)
        current=season_variants(year)
        for before,after in product(previous,current):
            rows=calendar(year,before,after,travel_days)
            inputs=model_inputs(cash,rows,residence,filing,qualifying)
            # Keep repeated outcomes to preserve equal opponent weighting.
            if representative is None:representative=rows
            result=calculate(inputs);outcomes.append(result)
        mean=lambda f:sum(f(r) for r in outcomes)/len(outcomes)
        annual.append(dict(**cash,total_tax=mean(lambda r:r['total_tax']),remaining=mean(lambda r:r['remaining']),
            low_remaining=min(r['remaining'] for r in outcomes),high_remaining=max(r['remaining'] for r in outcomes),
            federal=mean(lambda r:r['national']['federal']),payroll=mean(lambda r:r['national']['payroll']['total']),
            state=mean(lambda r:r['tax']['total']),local=mean(lambda r:r['local']['total']),
            duty_days=len(representative),schedule_basis='Published 2025 calendar' if year==2025 else 'Published regular-season matchups; modeled camp' if year==2026 else 'Rotation projection; synthetic dates',
            scenarios=len(outcomes),opponents=(source_data()['published_schedules'][str(year)]+(source_data()['additional_2026_games'] if year==2026 else [])) if year<=2026 else opponent_slots(year)))
    total=lambda k:sum(r[k] for r in annual)
    return dict(player=data['player'],annual=annual,gross=total('cash'),total_tax=total('total_tax'),remaining=total('remaining'),
                low_remaining=total('low_remaining'),high_remaining=total('high_remaining'),
                fully_guaranteed_at_signing=data['fully_guaranteed_at_signing'],reported_total_guarantees=data['reported_total_guarantees'],
                residence=residence,filing=filing,qualifying=qualifying,travel_days=travel_days,tax_rule_year=2025,
                sources=data['sources'],accessed_date=data['accessed_date'],notes=[
                'All six years use frozen 2025 tax rules, deductions, payroll limits and selected local rates. This isolates cash and schedule effects; it is not a forecast of future tax law or inflation.',
                'Assumes Allen remains with Buffalo, keeps the selected full-year residence, and earns every scheduled payment. $147M was fully guaranteed at signing; $250M reported total guarantees includes conditional/vesting guarantees. $330M is not all fully guaranteed.',
                'Reported season cash approximates calendar-year wages; exact payment dates and W-2 totals remain unverified. Local payment halves assume cash is uniform over modeled service dates. Cash uses the current reported contract snapshot, not the original signing-day payment schedule. Future restructures, termination, incentives and endorsements are excluded. Void years have no modeled cash.',
                'Default allocates all cash as service wages, matching the annual model. Optional residence-only treatment applies only to the reported $56.745M 2025 signing bonus; its legal qualification is assumed. Other cash, including future option conversions, remains service wages.',
                '2025 retains the existing calendar model, including early-2025 postseason. 2026 adds published January 2025-season playoff games and preseason games. Later calendars use July 23 camp, Tuesday off, regular-season games and selected arrival days. Unpublished preseason games, joint practices and future playoffs are excluded.',
                'January service is assigned to its calendar year from the prior football season. Future game order and a Week 9 bye are synthetic. The 2026 Week 18 date is provisional. Unknown international games and future stadium moves are not modeled.',
                'For unknown away opponents, all four teams in each specified division receive equal weight independently. These are jurisdiction scenarios, not predicted standings. Displayed take-home is the scenario mean.',
                'The total range sums annual minimum and maximum take-home. It is a scenario envelope, not a confidence interval or a guaranteed achievable six-year path. It does not capture tax-law, residence or roster uncertainty.',
                'State calculations retain the annual model simplifications. Unsupported city/county taxes, foreign taxes, state payroll programs and personal deductions/credits are excluded. No New York City residence tax is assumed.'
                ])
