"""Rank every team in a league for one hypothetical offer.

Built entirely on etl.offer_lab (normalize, evaluate, solve); nothing there is
changed. For the reference offer (Offer A) this reports, for each team:
  * take-home if that team paid the SAME salaries, and
  * the break-even salary that team would need to pay for the SAME whole-contract
    take-home as the reference offer (offer_lab.solve, $1 tolerance).

Residence rule:
  * "team": each team's saved team/practice state (the Offer Lab default), so the
    ranking shows where a player who lives where he works keeps the most.
  * "fixed": every team uses Offer A's residence, isolating work-location
    (jock-tax) effects from residence effects.

Teams without a U.S. base state (the Toronto Blue Jays) are listed as excluded
because Canadian taxes are not modeled.
"""
import json
from collections import OrderedDict

from etl.offer_lab import catalog, evaluate, normalize, solve
from etl.estimated_duty_days import STATES

RULES = ('team', 'fixed')


_RESULTS = OrderedDict()  # last few full rankings, so repeating a request is instant


def _memo(calculate):
    """Reuse identical tax calculations within one ranking (the break-even search
    starts from the same salaries as the same-offer estimate)."""
    seen = {}

    def cached(inputs):
        key = json.dumps(inputs, sort_keys=True, default=str)
        if key not in seen:
            seen[key] = calculate(inputs)
        return seen[key]
    return cached


def rank(calculate, payload):
    key = json.dumps(payload, sort_keys=True, default=str)
    if key in _RESULTS:
        _RESULTS.move_to_end(key)
        return _RESULTS[key]
    result = _rank(_memo(calculate), payload)
    _RESULTS[key] = result
    while len(_RESULTS) > 16:
        _RESULTS.popitem(last=False)
    return result


def _rank(calculate, payload):
    if not isinstance(payload, dict):
        raise ValueError('Offer inputs must be an object.')
    rule = payload.get('residence_rule', 'team')
    if rule not in RULES:
        raise ValueError('Choose each team’s state or Offer A’s residence.')
    offer_a = payload.get('offer_a')
    if not isinstance(offer_a, dict):
        raise ValueError('Offer A is required.')
    # Validate every shared input with the Offer Lab's own rules (break-even mode
    # needs no Offer B salaries; Offer B's team is a placeholder that is replaced).
    config = normalize(dict(payload, mode='breakeven', offer_b=dict(team_id=offer_a.get('team_id'))))
    reference = evaluate(calculate, config, config['a'])
    if reference['remaining'] <= 0:
        raise ValueError('Offer A needs positive modeled take-home before teams can be ranked.')
    years = len(config['a']['salaries'])
    rows, excluded = [], []
    for team in catalog()['teams'][config['league']]:
        residence = team['base_state'] if rule == 'team' else config['a']['residence']
        if not team['base_state'] or residence not in STATES:
            excluded.append(dict(team=team, reason='Canadian taxes are not modeled.'))
            continue
        offer = dict(team=team, residence=residence, salaries=config['a']['salaries'])
        same = evaluate(calculate, config, offer)
        best, solver = solve(calculate, dict(config, b=offer), reference)
        rows.append(dict(
            team=team, residence=residence, residence_name=STATES[residence],
            is_reference=team['id'] == config['a']['team']['id'] and residence == config['a']['residence'],
            take_home=same['remaining'], take_home_difference=same['remaining'] - reference['remaining'],
            take_home_percentage=same['take_home_percentage'], total_tax=same['total_tax'],
            federal=same['federal'], payroll=same['payroll'], state=same['state'], local=same['local'],
            breakeven_total=solver['required_gross'], breakeven_annual=solver['required_gross'] / years,
            breakeven_difference=solver['gross_difference'],
            breakeven_annual_difference=solver['gross_difference'] / years,
            converged=solver['converged']))
    rows.sort(key=lambda r: (-round(r['take_home'], 2), r['team']['name']))
    for index, row in enumerate(rows):
        first = index
        while first and round(rows[first - 1]['take_home'], 2) == round(row['take_home'], 2):
            first -= 1
        row['rank'] = first + 1
    return dict(
        league=config['league'], start_year=config['start'], years=years, tax_year=2026,
        residence_rule=rule, filing=config['filing'],
        reference=dict(team=config['a']['team'], residence=config['a']['residence'],
                       residence_name=STATES[config['a']['residence']], gross=reference['gross'],
                       take_home=reference['remaining'], take_home_percentage=reference['take_home_percentage'],
                       annual_salaries=config['a']['salaries']),
        rows=rows, excluded=excluded,
        notes=['Same assumptions as the Offer Lab: salary-only offers, fixed 2026 tax rules, modeled work '
               'locations, U.S. taxes only.',
               'Break-even keeps Offer A’s year-by-year salary proportions and matches whole-contract '
               'take-home within $1.',
               'Each team’s state as residence mixes residence and work-location effects; Offer A’s '
               'residence for every team isolates work-location (jock-tax) effects.'])