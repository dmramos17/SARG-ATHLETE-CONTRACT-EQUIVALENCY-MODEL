"""Nominal MLB future salaries: repeat 2025/2026 work patterns, freeze 2026 law.

A salary scenario, not a cash-payment forecast. Deferred-payment timing,
prorated bonuses and luxury-tax/AAV accounting are deliberately not modeled.
"""
from collections import Counter, defaultdict
from functools import lru_cache
import math
from etl.mlb_model import data, players, calendar, games_index, schedule_data, calculation_inputs
from pathlib import Path
import json
from etl.mlb_contract_terms import select_contract, boundaries


@lru_cache(maxsize=2048)
def salary_window(player_id, full=False):
    p = players()[player_id]
    chosen = select_contract(data(),p)
    if not chosen:
        return dict(annual=[], reason='Reported contract terms and future annual salaries are unavailable.', start=None, end=None, source_url=None)
    summary = chosen['summary']; start = boundaries(chosen)[0]; end = boundaries(chosen)[1]
    if not start or not end:
        return dict(annual=[], reason='Reported contract start/end years are unavailable.', start=start, end=end, source_url=chosen['source_url'])
    annual = []
    for year in range(start if full else max(2027, start), end + 1):
        rows = [r for r in chosen['annual'] if r['Season'] == year and r['ContractId'] == summary['ContractId']]
        row = rows[0] if len(rows) == 1 else None
        amount = row.get('BaseSalary') if row else None
        phase = row.get('Type') if row else None
        reason = None
        if row is None:
            reason = 'A unique annual salary is not reported for this contract year.'
        elif row.get('isEstimate') or any(word in (phase or '') for word in ('ARB', 'FREE AGENT', 'PLACEHOLDER', 'TBD')):
            reason = 'Arbitration, placeholder, free-agent or estimated salaries are not reported contract salaries.'
        elif not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
            reason = 'A positive reported annual base salary is unavailable.'
        annual.append(dict(year=year, salary=amount if not reason else None, phase=phase,
                           conditional=bool(phase and phase != 'GUARANTEED'), reason=reason,
                           source_url=chosen['source_url']))
    return dict(annual=annual, start=start, end=end, headline_value=summary.get('ContractTotal'), signing_bonus=summary.get('SigningBonus') or 0, contract_id=summary.get('ContractId'), source_url=chosen['source_url'],
                reason=None if annual else 'No reported contract years remain after 2026.')


@lru_cache(maxsize=2048)
def signing_payments(player_id):
    window=salary_window(player_id,True)
    reviewed=json.loads((Path(__file__).resolve().parents[1]/'data/curated/mlb_contracts_spotrac.json').read_text())['players'].get(player_id,{})
    payments={};sources=[];exercised=[]
    if reviewed and (reviewed['start_year'],reviewed['end_year'],reviewed['headline_value'])==(window['start'],window['end'],window.get('headline_value')):
        payments={r['year']:r.get('signing_cash',0) for r in reviewed.get('annual',[]) if window['start']<=r['year']<=window['end'] and r.get('signing_cash')}
        sources.append(dict(name='Reviewed Spotrac signing cash',url=reviewed['source_url']))
    extra=json.loads((Path(__file__).resolve().parents[1]/'data/curated/mlb_signing_bonus_payments.json').read_text()).get(player_id,{})
    if extra and (extra['contract_id'],extra['start_year'],extra['end_year'],extra['headline_value'])==(window.get('contract_id'),window['start'],window['end'],window.get('headline_value')):
        payments={r['year']:r['amount'] for r in extra['payments']};sources.extend(extra['sources']);exercised=extra.get('exercised_options',[])
    unresolved=max(0,window.get('signing_bonus',0)-sum(payments.values()))
    return dict(payments=payments,unresolved=unresolved,sources=sources,exercised=exercised)


@lru_cache(maxsize=120)
def pattern(team_id, template_year, early_camp):
    regular = [g for g in games_index().get((team_id, template_year), []) if g['stage'] == 'R']
    expected = schedule_data()['metadata']['regular_game_counts'].get(str(template_year), {}).get(team_id)
    if not expected or expected < 160 or len(regular) != expected:
        raise ValueError('The reference schedule does not reconcile to published regular-season counts.')
    cal = calendar(team_id, template_year, early_camp, include_postseason=False)
    if any(not r['country'] or (r['country'] in ('USA','United States') and not r['state']) for r in cal['rows']):
        raise ValueError('Reference work locations have unresolved jurisdictions.')
    return cal


def projection_inputs(player_id, year, salary, residence, filing='single'):
    p = players()[player_id]
    template_year = 2025 if year % 2 else 2026
    cal = pattern(p['team_id'], template_year, p['position_code'] in ('P','SP','RP','C','TWP','Y'))
    rows = cal['rows']; n = len(rows)
    counts = Counter(r['state'] for r in rows if r['state'])
    local = defaultdict(lambda: dict(early=0, late=0))
    for r in rows:
        locality = r['locality']
        if locality and not (locality == 'MDNR' and residence == 'MD'):
            local[locality]['early' if r['date'][5:] < '07-01' else 'late'] += salary / n
    inputs = dict(tax_year=2026, residence=residence, filing=filing, salary=salary, bonus=0, other_cash=0,
                  bonus_treatment='conditional', days=dict(counts), unsourced=sum(not r['state'] for r in rows),
                  early_cash=salary*sum(r['date'][5:] < '07-01' for r in rows)/n, local_work=dict(local))
    return inputs, cal, template_year


@lru_cache(maxsize=256)
def project(calculate, player_id, residence, filing='single', full=False):
    if player_id not in players():
        raise ValueError('MLB player not found in the active roster snapshot.')
    if residence not in {t['state'] for t in data()['teams'].values() if t['state']}:
        raise ValueError('Choose a supported U.S. MLB comparison state. Canadian residence is not yet modeled.')
    if filing not in ('single','mfj'):
        raise ValueError('Choose a supported filing status.')
    window = salary_window(player_id,True) if full else salary_window(player_id); p = players()[player_id]
    bonus=signing_payments(player_id); signing=bonus['payments']
    annual = []; excluded = []; sources = []
    for row in window['annual']:
        if row['reason']:
            excluded.append(dict(year=row['year'], reason=row['reason'])); continue
        try:
            amount=row['salary']+(signing.get(row['year'],0) if full else 0)
            if full and row['year']<=2026:
                inputs,cal=calculation_inputs(player_id,row['year'],residence,filing)
                ratio=amount/inputs['salary']; inputs['salary']=amount; inputs['early_cash']*=ratio
                inputs['local_work']={k:{half:value*ratio for half,value in periods.items()} for k,periods in inputs['local_work'].items()}
                template=row['year']
            else:
                inputs, cal, template = projection_inputs(player_id, row['year'], amount, residence, filing)
            result = calculate(inputs)
        except ValueError as error:
            excluded.append(dict(year=row['year'], reason=str(error))); continue
        annual.append(dict(year=row['year'], salary=amount, base_salary=row['salary'], signing_cash=signing.get(row['year'],0) if full else 0, phase='OPTION EXERCISED' if row['year'] in bonus['exercised'] else row['phase'], conditional=row['conditional'] and row['year'] not in bonus['exercised'],
                           team=p['team'], team_id=p['team_id'], template_year=template, tax_year=inputs['tax_year'], local_supported=inputs['tax_year']>=2025,
                           federal=result['national']['federal'], payroll=result['national']['payroll']['total'],
                           state=result['tax']['total'], local=result['local']['total'],
                           total_tax=result['total_tax'], remaining=result['remaining'], duty_days=len(cal['rows']),
                           state_days=inputs['days'], foreign_days=inputs['unsourced'],
                           regular_games=cal['regular_games'], spring_games=cal['spring_games'],
                           postseason_games=cal['postseason_games'], source_url=row['source_url']))
        sources.extend(result['sources'])
    total = lambda key: sum(r[key] for r in annual) if annual else None
    modeled=total('salary');headline=window.get('headline_value')
    reconciles=modeled is not None and headline is not None and abs(modeled-headline)<=1
    year_complete=bool(annual) and not excluded
    complete=year_complete and (not full or (reconciles and bonus['unresolved']==0))
    coverage_notes=[]
    if full and modeled is not None and not reconciles:
        coverage_notes.append(f'Modeled income ${modeled:,.0f} does not reconcile to the ${headline:,.0f} headline value.' if headline is not None else 'The headline value is unavailable; full-dollar coverage cannot be confirmed.')
    if full and bonus['unresolved']:
        coverage_notes.append(f"${bonus['unresolved']:,.0f} of reported signing bonus has no verified payment-year allocation and is excluded; no prorated bonus or balancing amount is substituted.")
    if excluded:coverage_notes.append('Years with unavailable inputs are excluded from both income and tax totals.')
    return dict(player_id=player_id, residence=residence, filing=filing, annual=annual, excluded=excluded,
                included_years=[r['year'] for r in annual], start=window['start'], end=window['end'],
                reason=window['reason'], salary=total('salary'), total_tax=total('total_tax'), remaining=total('remaining'),
                complete=complete,year_complete=year_complete,reconciles_headline=reconciles,headline_value=headline,
                headline_gap=headline-modeled if headline is not None and modeled is not None else None,unallocated_signing_bonus=bonus['unresolved'],coverage_notes=coverage_notes,payment_sources=bonus['sources'],conditional_years=[r['year'] for r in annual if r['conditional']],
                source_url=window['source_url'], as_of=data()['metadata']['as_of'], tax_year=2026,
                scope='full' if full else 'future',
                sources=list({(s['state'],s['source']):s for s in sources}.values()), notes=([
                    'Contract-wide salary scenario: reported nominal base salaries plus separately verified signing cash where available. Deferred-payment timing is set aside consistently across every playing year. Historical cash estimates are preserved in the separate expandable section.',
                    'Through 2026, published schedules and matching tax-year rules are used with the existing historical membership/coverage checks. From 2027, 2025/2026 work patterns repeat under fixed 2026 rules. Local taxes before 2025 are not modeled.',
                    'Totals include calculated years only. Missing salaries, historical cash/membership needed to establish duty calendars, and unsupported years are excluded and listed. Signing bonuses without a verified payment year, incentives, buyouts and other compensation are not inferred. Modeled income may not reconcile to the reported headline value.',
                    'Option, vesting and opt-out years assume continuation at the reported salary; these amounts are conditional, not guaranteed. Citizenship, actual residence and individual attendance are unverified. Canadian and foreign taxes remain excluded.'
                ]+coverage_notes if full else [
                    'Future years repeat the current team’s 2025 pattern in odd years and 2026 pattern in even years. Spring training and regular-season duty-day shares repeat; reference postseason games are excluded. These are work-location templates, not announced future fixtures.',
                    '2026 federal brackets, deductions, employee payroll limits and supported state/local rules stay fixed in nominal dollars. Annual salary is recalculated under the brackets; one flat effective tax rate is not assumed. No inflation or discounting is applied.',
                    'Uses reported annual base salary for the selected current contract. Deferral timing is ignored: Ohtani is modeled at $70M of nominal annual salary, rather than $2M of paid cash or luxury-tax AAV. No deferred installment is added later. Historical cash estimates remain separate and are not combined with this salary scenario.',
                    'Signing-bonus proration, AAV, buyouts and unverified incentives are not added to base salary. This is a future salary subtotal, not a reconciliation to headline contract value or a forecast of all cash payments.',
                    'The player stays with the saved roster team. Included option, vesting and opt-out years assume continuation at the reported salary and are explicitly conditional; their amounts are not guaranteed. Arbitration and free-agent placeholders are excluded rather than estimated.',
                    'Reference special-event venues and team bases repeat as a simplifying assumption; future international designations, stadium moves, schedule changes, postseason appearances, individual attendance and transactions are not predicted.',
                    'Residence stays at the selected comparison assumption. Foreign duty days stay in the denominator; Canadian and other foreign taxes and credits are excluded. Toronto’s Canadian-resident base result remains unavailable. U.S. figures use the existing provisional state credits, local coverage and duty-day assumptions.'
                ]))
