"""Auditable NFL team and player calendar estimates; not attendance records."""
from bisect import bisect_right
from collections import Counter
from datetime import date, timedelta
from functools import lru_cache
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
with (ROOT/'data/processed/state_tax_profile_2026.csv').open() as stream:
    STATES={r['state_code']:r['state_name'] for r in csv.DictReader(stream)}
SUPPORTED_STATES=set(STATES)
# Only these camp starts were individually checked in the original demonstration.
CAMPS={
 'NE':('2025-07-23','https://www.patriots.com/news/new-england-patriots-announce-dates-for-training-camp'),
 'SEA':('2025-07-23','https://www.seahawks.com/news/seahawks-announce-public-training-camp-dates'),
 'DEN':('2025-07-22','https://www.denverbroncos.com/news/nfl-announces-broncos-training-camp-reporting-dates-joint-practice-with-49ers')}

@lru_cache(maxsize=1)
def teams():
    with (ROOT/'data/curated/teams.csv').open() as stream:
        return {r['team_id']:r for r in csv.DictReader(stream) if r['league']=='NFL'}

@lru_cache(maxsize=1)
def games():
    return json.loads((ROOT/'data/curated/nfl_games_calendar_2025.json').read_text())

@lru_cache(maxsize=1)
def memberships():
    return json.loads((ROOT/'data/snapshots/nfl_memberships_2025.json').read_text())

def validate(travel_days,weekly_off_day):
    if type(travel_days) is not int or not 0<=travel_days<=3:raise ValueError('Travel days must be 0–3.')
    if type(weekly_off_day) is not int or not -1<=weekly_off_day<=6:raise ValueError('Off-day choice must be -1 or a weekday from 0–6.')

def checked_day(value):
    if not isinstance(value,str):raise ValueError('Use YYYY-MM-DD dates.')
    day=date.fromisoformat(value)
    if day.year!=2025 or day.isoformat()!=value:raise ValueError('Every adjustment must use YYYY-MM-DD in 2025.')
    return day

@lru_cache(maxsize=256)
def team_calendar(team_id,travel_days=1,weekly_off_day=1):
    validate(travel_days,weekly_off_day)
    if not isinstance(team_id,str) or team_id not in teams():raise ValueError('Choose a supported NFL team.')
    team=team_id.removeprefix('NFL_');info=teams()[team_id];home=info['practice_state']
    schedule=[g for g in games() if team in (g['home'],g['away'])]
    if not schedule:raise ValueError('Missing 2025 team schedule.')
    camp_info=CAMPS.get(team)
    first_pre=min(date.fromisoformat(g['date']) for g in schedule if g['stage']=='PRE')
    camp=date.fromisoformat(camp_info[0]) if camp_info else min(date(2025,7,23),first_pre-timedelta(days=14))
    winter_end=max(date.fromisoformat(g['date']) for g in schedule if g['date']<'2025-03-01')
    calendar={}
    def put(day,event,state,locality=None,evidence='modeled',source=None,note=''):
        if day.year==2025:
            calendar[day.isoformat()]=dict(date=day.isoformat(),event=event,state=state,locality=locality,evidence=evidence,source=source,note=note,team_id=team_id)
    for start,end in [(date(2025,1,1),winter_end),(camp,date(2025,12,31))]:
        day=start
        while day<=end:
            if day.weekday()!=weekly_off_day:
                state=home;locality=info['practice_locality'] or None
                note='Assumed team-facility work; individual attendance and rehab location unverified.'
                # An explicitly modeled camp location, not a documented itinerary.
                if team=='DAL' and camp<=day<=date(2025,8,13):
                    state='CA';locality=None;note='Unverified camp assumption: Oxnard CA through August 13. Correct dates/locations if known.'
                put(day,'team service',state,locality,note=note)
            day+=timedelta(days=1)
    for game in schedule:
        day=date.fromisoformat(game['date'])
        if game['home']!=team or game['state'] is None or game['state']!=info['stadium_state']:
            for n in range(1,travel_days+1):
                put(day-timedelta(days=n),'travel / away preparation',game['state'],note='Assumed arrival and service in destination state; hotel city unverified.')
        put(day,'game · '+game['stage'],game['state'],game['locality'],'documented team event',game['source'],
            'Actual team game and venue; player attendance, travel or rehab location not verified.')
    # Model a continuous overseas stay for closely spaced international games.
    foreign=sorted([g for g in schedule if g['state'] is None],key=lambda g:g['date'])
    for first,second in zip(foreign,foreign[1:]):
        start=date.fromisoformat(first['date']);end=date.fromisoformat(second['date'])
        if (end-start).days<=9:
            for n in range(1,(end-start).days):
                day=start+timedelta(days=n)
                put(day,'overseas preparation',None,note='Assumed continuous overseas stay between international games; itinerary unverified.')
    joint={'NE':[('2025-08-13','MN'),('2025-08-14','MN')],'DEN':[('2025-08-07','CA')]}
    sources={'NE':'https://media.patriots.1rmg.com/wp-content/uploads/2025/03/09154140/2025-New-England-Patriots-Training-Camp-Release.pdf',
             'DEN':'https://www.49ers.com/news/day-12-of-49ers-training-camp-joint-practice-with-the-denver-broncos'}
    for value,state in joint.get(team,[]):
        put(date.fromisoformat(value),'joint practice',state,evidence='documented team event',source=sources[team],note='Documented team event; individual attendance assumed.')
    if team=='NE':put(date(2025,8,15),'away preparation','MN',note='Assumed stay between Minnesota joint practices and preseason game.')
    notes=[]
    if not camp_info:notes.append(f'{team}: service window starts {camp.isoformat()} by model assumption; actual training-camp start and joint practices have not been individually reviewed.')
    if team=='DAL':notes.append('Dallas camp is modeled in Oxnard CA through August 13; dates, player attendance and later camp movements require review.')
    return dict(calendar=calendar,camp_start=camp.isoformat(),winter_end=winter_end.isoformat(),home_state=home,
                sources=[camp_info[1]] if camp_info else [],notes=notes)

def summarize(rows,team_id,travel_days,weekly_off_day,extra_notes,sources,parameters):
    ordered=sorted(rows.values(),key=lambda r:r['date'])
    if not ordered:raise ValueError('Calendar needs at least one duty day.')
    state_days=Counter(r['state'] for r in ordered if r['state']);locality_days=Counter(r['locality'] for r in ordered if r['locality'])
    notes=['Residence assumes full-year domicile in the selected team practice state; actual player domicile is not established.',
           'Calendar year 2025 includes the January–February tail of the 2024 season. January 2026 is excluded.',
           'Tuesday off and one arrival day are defaults, not observed attendance. Bye weeks retain modeled service; offseason workouts need manual additions.',
           'Inactive or injured players may still travel or rehabilitate; this calendar does not infer actual rehab locations.',
           'Foreign service stays in the denominator without US state allocation. Foreign taxes and treaty relief are not modeled.',
           'City game venues are documented; practice-city sourcing and travel states are assumptions. Unknown hotel cities and unsupported local taxes are omitted.']+extra_notes
    return dict(tax_year=2025,team_id=team_id,residence_default=teams()[team_id]['practice_state'],total_days=len(ordered),
                state_days=dict(state_days),locality_days=dict(locality_days),unsourced_days=sum(r['state'] is None for r in ordered),
                evidence_counts=dict(Counter(r['evidence'] for r in ordered)),calendar=ordered,
                parameters=dict(travel_days=travel_days,weekly_off_day=weekly_off_day,**parameters),
                sources=sorted(set(sources)|{r['source'] for r in ordered if r['source']}),notes=notes)

def adjust(rows,home,excluded_dates,additional_days,overrides):
    if not isinstance(excluded_dates,(list,tuple)) or not isinstance(additional_days,(list,tuple)):raise ValueError('Calendar dates must be lists.')
    if overrides is not None and not isinstance(overrides,dict):raise ValueError('Location corrections must be a mapping.')
    rows={day:dict(record) for day,record in rows.items()}
    for value in additional_days:
        checked_day(value);rows[value]=dict(date=value,event='additional service',state=home,locality=None,evidence='user assumption',source=None,note='User-added offseason service date.',team_id=None)
    for value,state in (overrides or {}).items():
        checked_day(value)
        if value not in rows:raise ValueError('Location overrides need an existing duty date.')
        if state is not None and (not isinstance(state,str) or state not in SUPPORTED_STATES):raise ValueError('Choose a supported state for a location correction.')
        rows[value].update(state=state,locality=None,evidence='user assumption',note='User-changed duty location; city allocation cleared.')
    for value in excluded_dates:checked_day(value);rows.pop(value,None)
    return rows

def estimate_calendar(team_id,*,travel_days=1,weekly_off_day=1,excluded_dates=(),overrides=None,additional_days=()):
    validate(travel_days,weekly_off_day)
    base=team_calendar(team_id,travel_days,weekly_off_day)
    rows=adjust(base['calendar'],base['home_state'],excluded_dates,additional_days,overrides)
    return summarize(rows,team_id,travel_days,weekly_off_day,base['notes'],base['sources'],dict(camp_start=base['camp_start'],january_end=base['winter_end']))

def estimate_player_calendar(player,*,travel_days=1,weekly_off_day=1,excluded_dates=(),overrides=None,additional_days=()):
    """Use weekly 2024/2025 team observations to approximate transitions.

    Summer membership is extrapolated from the first 2025 weekly roster. A weekly
    roster is not a transaction log; these boundaries remain model assumptions.
    """
    validate(travel_days,weekly_off_day)
    timeline=memberships()['players'].get(player['id'],[])
    winter=[r for r in timeline if r['season']==2024]
    summer=[r for r in timeline if r['season']==2025]
    if not summer:raise ValueError('Missing weekly roster membership for this player.')
    team_ids={r['team_id'] for r in timeline if r['team_id'] in teams()}
    bases={team:team_calendar(team,travel_days,weekly_off_day) for team in team_ids}
    starts={2024:[r['start'] for r in winter],2025:[r['start'] for r in summer]}
    rows={};day=date(2025,1,1)
    while day.year==2025:
        value=day.isoformat();season=2024 if day<date(2025,3,1) else 2025;records=winter if season==2024 else summer
        index=bisect_right(starts[season],value)-1
        if records and (index>=0 or season==2025):
            membership=records[max(index,0)]
            if membership['status'] in ('ACT','INA','DEV','RES','EXE'):
                base=bases.get(membership['team_id']);event=base['calendar'].get(value) if base else None
                if event:rows[value]=dict(event)
        day+=timedelta(days=1)
    rows=adjust(rows,player['home_state'],excluded_dates,additional_days,overrides)
    notes=['Team assignment uses weekly roster observations, not exact transaction dates. Camp membership is extrapolated from the first 2025 roster observation.',
           'January–February uses 2024 roster evidence; players without that evidence receive no modeled winter service. Injury and reserve locations remain unverified.']
    for base in bases.values():notes.extend(base['notes'])
    sources=[source for base in bases.values() for source in base['sources']]+memberships()['metadata']['sources'][1:]
    return summarize(rows,player['team_id'],travel_days,weekly_off_day,notes,sources,
                     dict(camp_start=min(b['camp_start'] for b in bases.values()),january_end=max(b['winter_end'] for b in bases.values()),player_id=player['id']))
