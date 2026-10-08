"""Auditable team-calendar estimates, not records of individual player attendance."""
from collections import Counter
from datetime import date, timedelta
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUPPORTED_STATES={'MA','TX','FL','NY','NJ','CA','PA','MI','OH','MO','MD','WA','CO','AZ','GA','IN','LA','MN','NC','NV','TN','WI'}
CAMPS={
 'NE':('2025-07-23','https://www.patriots.com/news/new-england-patriots-announce-dates-for-training-camp'),
 'SEA':('2025-07-23','https://www.seahawks.com/news/seahawks-announce-public-training-camp-dates'),
 'DEN':('2025-07-22','https://www.denverbroncos.com/news/nfl-announces-broncos-training-camp-reporting-dates-joint-practice-with-49ers')}

def estimate_calendar(team_id, *, travel_days=1, weekly_off_day=1, excluded_dates=(), overrides=None, additional_days=()):
    """Tuesday off by default; game/travel beats weekly rest. Destination allocation
    on arrival is an assumption, not a universal state travel-day tax rule.
    Explicit excluded dates remove duty entirely. Overrides change one day's state;
    additional offseason service dates enter the denominator. Tax year is 2025.
    """
    if not isinstance(team_id,str): raise ValueError('Choose a supported team.')
    if not isinstance(excluded_dates,list) and not isinstance(excluded_dates,tuple): raise ValueError('Excluded dates must be a list.')
    if not isinstance(additional_days,list) and not isinstance(additional_days,tuple): raise ValueError('Additional dates must be a list.')
    if overrides is not None and not isinstance(overrides,dict): raise ValueError('Location corrections must be a mapping.')
    team=team_id.removeprefix('NFL_')
    if team not in CAMPS: raise ValueError('No reviewed 2025 calendar for this team.')
    if type(travel_days) is not int or not 0<=travel_days<=3: raise ValueError('Travel days must be 0–3.')
    if type(weekly_off_day) is not int or not -1<=weekly_off_day<=6: raise ValueError('Off-day choice must be -1 or a weekday from 0–6.')
    with (ROOT/'data/curated/teams.csv').open() as stream:
        teams={r['team_id']:r for r in csv.DictReader(stream)}
    home=teams[team_id]['practice_state']
    games=[g for g in json.loads((ROOT/'data/curated/nfl_games_calendar_2025.json').read_text()) if team in (g['home'],g['away'])]
    camp,camp_source=CAMPS[team]; camp=date.fromisoformat(camp)
    january_end=max(date.fromisoformat(g['date']) for g in games if g['date']<'2025-02-01')
    calendar={}
    def put(day,event,state,locality=None,evidence='modeled',source=None,note=''):
        if day.year==2025:
            calendar[day.isoformat()]=dict(date=day.isoformat(),event=event,state=state,locality=locality,evidence=evidence,source=source,note=note)
    for start,end in [(date(2025,1,1),january_end),(camp,date(2025,12,31))]:
        day=start
        while day<=end:
            if day.weekday()!=weekly_off_day:
                put(day,'team service',home,note='Assumed practice, meeting or team-facility service; attendance unverified.')
            day+=timedelta(days=1)
    # Away games and international fixtures use actual venue rather than team name.
    for g in games:
        day=date.fromisoformat(g['date'])
        if g['home']!=team or g['state'] is None:
            for n in range(1,travel_days+1):
                put(day-timedelta(days=n),'travel / away preparation',g['state'],None,note='Assumed arrival and service in destination state; city hotel location unknown.')
        put(day,'game · '+g['stage'],g['state'],g['locality'],'documented team event',g['source'],'Team game documented; individual participation, travel or rehab location not verified.')
    # Documented out-of-state joint practices (team attendance only).
    joint={'NE':[('2025-08-13','MN'),('2025-08-14','MN')], 'DEN':[('2025-08-07','CA')], 'SEA':[]}
    joint_source={'NE':'https://media.patriots.1rmg.com/wp-content/uploads/2025/03/09154140/2025-New-England-Patriots-Training-Camp-Release.pdf','DEN':'https://www.49ers.com/news/day-12-of-49ers-training-camp-joint-practice-with-the-denver-broncos','SEA':camp_source}
    for day,state in joint[team]:
        put(date.fromisoformat(day),'joint practice',state,evidence='documented team event',source=joint_source[team],note='Team event; individual attendance assumed.')
    if team == 'NE':
        put(date(2025,8,15),'away preparation','MN',note='Assumed stay between Minnesota joint practices and preseason game.')
    def checked_day(value):
        if not isinstance(value,str): raise ValueError('Use YYYY-MM-DD dates.')
        d=date.fromisoformat(value)
        if d.year!=2025 or d.isoformat()!=value: raise ValueError('Every adjustment must use YYYY-MM-DD in 2025.')
        return d
    for value in additional_days:
        put(checked_day(value),'additional service',home,evidence='user assumption',note='User-added offseason service date.')
    for value,state in (overrides or {}).items():
        checked_day(value)
        if value not in calendar: raise ValueError('Location overrides need an existing duty date.')
        if state is not None and (not isinstance(state,str) or state not in SUPPORTED_STATES): raise ValueError('Choose a state supported by the dashboard for a location correction.')
        calendar[value].update(state=state,locality=None,evidence='user assumption',note='Location changed by user; city location cleared.')
    for value in excluded_dates:
        checked_day(value);calendar.pop(value,None)
    rows=sorted(calendar.values(),key=lambda r:r['date'])
    if not rows: raise ValueError('Calendar needs at least one duty day.')
    states=Counter(r['state'] for r in rows if r['state'])
    locals=Counter(r['locality'] for r in rows if r['locality'])
    evidence=Counter(r['evidence'] for r in rows)
    return dict(tax_year=2025,team_id=team_id,residence_default=home,total_days=len(rows),state_days=dict(states),locality_days=dict(locals),unsourced_days=sum(r['state'] is None for r in rows),evidence_counts=dict(evidence),calendar=rows,parameters=dict(travel_days=travel_days,weekly_off_day=weekly_off_day,camp_start=camp.isoformat(),january_end=january_end.isoformat()),sources=sorted({r['source'] for r in rows if r['source']}|{camp_source}),notes=['Residence assumes full-year domicile in the team practice state; no player domicile is established.','Includes January 2025 tail of the 2024 season, preseason, and July–December service. January 2026 is excluded.','Default Tuesday off is assumed. Bye-week service remains modeled unless excluded. Offseason workouts and minicamps are omitted unless added.','Injury, inactive games and personal absences do not automatically eliminate duty: travel and team-facility rehab require player-level evidence.','International days remain in the denominator with no US state allocation. Foreign tax and treaty relief are not modeled.','Local allocation counts documented city game venues only; away hotel and practice locations are not inferred.'])
