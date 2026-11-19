"""Hypothetical guaranteed salary offers and a bounded after-tax equivalency solver.

No reported contract, player record, or existing forecast is modified.
"""
from collections import Counter,defaultdict
from functools import lru_cache
import math
from etl.estimated_duty_days import teams as nfl_teams,STATES
from etl.league_projection import calendar_variants
from etl.contract_projection import model_inputs
from etl.mlb_model import data as mlb_data
from etl.mlb_projection import pattern as mlb_pattern

MAX_SALARY=1_000_000_000
MAX_YEARS=10


@lru_cache(maxsize=1)
def catalog():
    groups={}
    for league in ('NFL','MLB'):
        rows=[]
        if league=='NFL':
            for tid,t in nfl_teams().items():
                rows.append(dict(id=tid,name=t['team_name'],code=tid.removeprefix('NFL_'),base_state=t['practice_state'],
                                 logo_url=f"https://a.espncdn.com/i/teamlogos/nfl/500/{tid.removeprefix('NFL_').lower()}.png"))
        else:
            for tid,t in mlb_data()['teams'].items():
                rows.append(dict(id=tid,name=t['name'],code=t['code'],base_state=t['state'],
                                 logo_url=f'https://www.mlbstatic.com/team-logos/{tid}.svg'))
        groups[league]=sorted(rows,key=lambda t:t['name'])
    return dict(teams=groups,states=[dict(code=k,name=v) for k,v in sorted(STATES.items(),key=lambda item:item[1])],
                tax_year=2026,max_years=MAX_YEARS,max_salary=MAX_SALARY,start_year_min=2027,start_year_max=2030)


def normalize(payload):
    if not isinstance(payload,dict):raise ValueError('Offer inputs must be an object.')
    league=payload.get('league','NFL');mode=payload.get('mode','compare')
    if league not in ('NFL','MLB'):raise ValueError('Choose NFL or MLB.')
    if mode not in ('compare','breakeven'):raise ValueError('Choose comparison or break-even mode.')
    start=payload.get('start_year',2027)
    if type(start) is not int or not 2027<=start<=2030:raise ValueError('Choose a first salary year from 2027 through 2030.')
    filing=payload.get('filing','single');role=payload.get('mlb_role','position');travel=payload.get('travel_days',1)
    if filing not in ('single','mfj'):raise ValueError('Choose single or joint filing.')
    if role not in ('position','pitcher_catcher'):raise ValueError('Choose an MLB reporting group.')
    if type(travel) is not int or not 0<=travel<=3:raise ValueError('Away arrival days must be 0–3.')
    def offer(key,need_salary):
        row=payload.get(key)
        if not isinstance(row,dict):raise ValueError('Both team selections are required.')
        team=next((t for t in catalog()['teams'][league] if t['id']==row.get('team_id')),None)
        if not team:raise ValueError('Choose a team from the selected league.')
        if row.get('residence') is not None and not isinstance(row.get('residence'),str):raise ValueError('Choose a supported U.S. residence.')
        residence=row.get('residence') or team['base_state']
        if residence not in STATES:raise ValueError('Canadian-resident taxes are not modeled. Choose an explicit U.S. residence assumption for this offer.')
        salaries=[]
        if need_salary:
            values=row.get('annual_salaries')
            if not isinstance(values,list) or not 1<=len(values)<=MAX_YEARS:raise ValueError('Enter 1–10 annual salary amounts.')
            for value in values:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=MAX_SALARY:
                    raise ValueError('Annual salaries must be finite numbers between $0 and $1 billion.')
                salaries.append(round(value,2))
            if sum(salaries)<=0:raise ValueError('Each offer must have positive total salary.')
        return dict(team=team,residence=residence,salaries=salaries)
    a=offer('offer_a',True);b=offer('offer_b',mode=='compare')
    if mode=='compare' and len(a['salaries'])!=len(b['salaries']):raise ValueError('Both offers must cover the same salary years.')
    structure=payload.get('structure','same_pattern')
    if structure not in ('same_pattern','flat'):raise ValueError('Choose equal annual pay or the reference offer’s salary proportions.')
    return dict(league=league,mode=mode,start=start,filing=filing,role=role,travel=travel,a=a,b=b,structure=structure)


@lru_cache(maxsize=256)
def work_plan(league,tid,year,role,travel):
    if league=='NFL':
        variants=calendar_variants(tid,tid,year,travel)
        return variants,None
    template=2025 if year%2 else 2026
    cal=mlb_pattern(tid,template,role=='pitcher_catcher')
    return ((cal['rows'],1),),template


def inputs_for(rows,salary,residence,filing):
    inputs=model_inputs(dict(cash=salary,signing_bonus=0),rows,residence,filing,False)
    inputs['tax_year']=2026
    return inputs


def evaluate(calculate,config,offer,salaries=None):
    salaries=offer['salaries'] if salaries is None else salaries
    annual=[];sources={}
    for index,salary in enumerate(salaries):
        year=config['start']+index
        variants,template=work_plan(config['league'],offer['team']['id'],year,config['role'],config['travel'])
        weight_sum=sum(weight for _,weight in variants)
        amounts=Counter();days=Counter();shares=Counter();foreign=0;duty=0;net_values=[]
        for rows,weight in variants:
            n=len(rows)
            if not n:raise ValueError('The selected team/year has no modeled duty calendar.')
            count=Counter(r['state'] for r in rows if r['state'])
            foreign+=sum(not r['state'] for r in rows)*weight;duty+=n*weight
            for state,value in count.items():days[state]+=value*weight;shares[state]+=value/n*weight
            if salary:
                result=calculate(inputs_for(rows,salary,offer['residence'],config['filing']))
                components=dict(federal=result['national']['federal'],payroll=result['national']['payroll']['total'],
                                state=result['tax']['total'],local=result['local']['total'],total_tax=result['total_tax'],remaining=result['remaining'])
                for source in result['sources']:sources[(source['state'],source['source'])]=source
            else:components=dict(federal=0,payroll=0,state=0,local=0,total_tax=0,remaining=0)
            for key,value in components.items():amounts[key]+=value*weight
            net_values.append(components['remaining'])
        annual.append(dict(year=year,cash=salary,**{k:v/weight_sum for k,v in amounts.items()},
                           low_remaining=min(net_values),high_remaining=max(net_values),tax_year=2026,local_supported=True,
                           template_year=template,duty_days=duty/weight_sum,foreign_days=foreign/weight_sum,
                           scenarios=weight_sum,state_days={k:v/weight_sum for k,v in days.items()},
                           state_shares={k:v/weight_sum for k,v in shares.items()},
                           schedule_basis=f'Repeating {template} spring/regular-season work pattern' if template else 'Team rotation scenarios; modeled dates and attendance'))
    total=lambda key:sum(r[key] for r in annual)
    gross=sum(salaries)
    return dict(team=offer['team'],residence=offer['residence'],residence_name=STATES[offer['residence']],
                annual=annual,gross=gross,total_tax=total('total_tax'),remaining=total('remaining'),
                federal=total('federal'),payroll=total('payroll'),state=total('state'),local=total('local'),
                low_remaining=total('low_remaining'),high_remaining=total('high_remaining'),
                take_home_percentage=total('remaining')/gross*100 if gross else None,
                annual_take_home=total('remaining')/len(annual),complete=True,sources=list(sources.values()))


def solve(calculate,config,reference):
    a=config['a'];b=config['b'];count=len(a['salaries']);target=reference['remaining']
    if target<=0:raise ValueError('The reference must have positive modeled take-home to solve an equivalent offer.')
    proportions=[1/count]*count if config['structure']=='flat' else [v/sum(a['salaries']) for v in a['salaries']]
    cap=MAX_SALARY/max(proportions);evaluations=0
    def candidate(total):
        nonlocal evaluations
        evaluations+=1
        salaries=[min(MAX_SALARY,round(total*p,2)) for p in proportions]
        return evaluate(calculate,config,b,salaries)
    low=0;low_net=0;high=min(reference['gross'],cap);upper=candidate(high);best=upper
    while upper['remaining']<target and abs(upper['remaining']-target)>1 and high<cap:
        low=high;low_net=upper['remaining'];high=min(high*2,cap);upper=candidate(high)
        if abs(upper['remaining']-target)<abs(best['remaining']-target):best=upper
    if upper['remaining']<target-1:raise ValueError('The target cannot be matched within the $1 billion annual salary limit.')
    high_net=upper['remaining']
    if abs(upper['remaining']-target)<abs(best['remaining']-target):best=upper
    for _ in range(40):
        if abs(best['remaining']-target)<=1:break
        # Safeguarded secant step; bisection supplies progress near thresholds.
        proposed=low+(target-low_net)*(high-low)/(high_net-low_net) if high_net>low_net else (low+high)/2
        if not low<proposed<high:proposed=(low+high)/2
        value=candidate(proposed);net=value['remaining']
        if abs(net-target)<abs(best['remaining']-target):best=value
        if net<target:low=proposed;low_net=net
        else:high=proposed;high_net=net
    return best,dict(converged=abs(best['remaining']-target)<=1,target_take_home=target,matched_take_home=best['remaining'],
                     residual=best['remaining']-target,tolerance=1,evaluations=evaluations,structure=config['structure'],
                     required_gross=best['gross'],gross_difference=best['gross']-reference['gross'])


def run(calculate,payload):
    config=normalize(payload)
    reference=evaluate(calculate,config,config['a'])
    if config['mode']=='breakeven':alternative,solver=solve(calculate,config,reference)
    else:alternative=evaluate(calculate,config,config['b']);solver=None
    return dict(league=config['league'],mode=config['mode'],start_year=config['start'],years=len(config['a']['salaries']),
                tax_year=2026,offer_a=reference,offer_b=alternative,solver=solver,
                take_home_difference=alternative['remaining']-reference['remaining'],notes=[
                    'Hypothetical salary-only illustration. Entered amounts are assumed fully earned and paid as service wages in their listed years. Bonuses, incentives, options, deferrals, deductions/agent fees and discounting are excluded.',
                    'Both offers cover the same salary years. All years use fixed 2026 federal, employee payroll, state and supported local tax inputs; this is not a forecast of future tax law. Filing defaults to single; joint filing assumes no spouse income.',
                    'NFL uses each selected team’s existing rotation-based work-location scenarios with modeled camp, road arrival days and synthetic dates. Unknown away opponents are equally weighted; take-home is the scenario mean. January service assumes the same employer, even in the first offer year. Unpublished postseason and individual attendance are not predicted.',
                    'MLB repeats the selected team’s 2025 spring/regular-season work pattern in odd future years and 2026 in even years. Played reference postseason games are excluded. Reporting group determines modeled spring start. Future special-event venues and relocations are not predictions.',
                    'Residence initially follows the team’s saved practice/team state but can be changed independently. Actual residence, citizenship, transactions and attendance are unverified. Canadian and other foreign taxes/credits, unsupported local taxes, state payroll programs and tax-return-specific adjustments remain excluded.',
                    'A break-even result matches whole-contract estimated U.S. take-home, not each year independently. It fixes the chosen target salary pattern and solves for its total; it is not a unique offer across all possible payment schedules. Salaries are rounded to cents; the displayed solver residual reports whether the $1 matching tolerance was reached.'
                ])
