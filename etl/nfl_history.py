"""Year-specific NFL estimates alongside, never replacing, the frozen-rule forecast."""
from functools import lru_cache
from etl.league_projection import data, source_team, calendar_variants, games_by_team
from etl.estimated_duty_days import estimate_player_calendar, teams
from etl.contract_projection import model_inputs, source_data as allen_data
from etl.player_directory import find_player
from etl.mlb_historical_taxes import federal_history
from etl.annual_taxes import FEDERAL_SOURCE


@lru_cache(maxsize=128)
def contract_history(calculate, player_id, residence, filing='single', qualifying=False, travel_days=1):
    player = find_player(player_id)
    if not player:
        raise ValueError('Player not found in the 2025 directory.')
    contract = data()['players'][player_id]
    cash_rows = [c for c in contract['cash'] if contract['year_signed'] <= c['year'] <= 2026]
    reviewed = {c['year']: c for c in allen_data()['cash']} if player_id == '00-0034857' else {}
    annual = []
    previous = None
    for cash in cash_rows:
        year = cash['year']
        employer = source_team(cash, None)
        # Weekly roster membership resolves 2025 trades; other years require one source team.
        if year == 2025:
            employer = player['team_id']
        base = dict(year=year, cash=cash['cash'], team=teams()[employer]['team_name'] if employer else None,
                    tax_year=year, local_supported=year >= 2025, federal=None, payroll=None,
                    state=None, local=None, total_tax=None, remaining=None, duty_days=None,
                    status='unavailable', reason=None)
        reason = None
        if cash['cash'] is None:
            reason = 'Reported annual cash is missing or cannot be attributed to this contract.'
        elif not employer:
            reason = 'A single historical team is not verified; transaction dates are needed.'
        elif not any(g['season'] == year and g['stage'] == 'REG' for g in games_by_team()[employer.removeprefix('NFL_')]):
            reason = 'Published regular-season schedule is unavailable.'
        elif year != 2025 and previous and source_team(previous, None) is None:
            reason = 'Prior-year team is unresolved; January duty days need transaction dates.'
        if reason:
            base['reason'] = reason
        else:
            if year == 2025:
                rows = estimate_player_calendar(player, travel_days=travel_days)['calendar']
            else:
                prior = source_team(previous, employer) if previous else employer
                rows = calendar_variants(employer, prior, year, travel_days, year == contract.get('draft_year'))[0][0]
            normalized = dict(cash, signing_bonus=0)
            bonus_qualifies = qualifying and year in reviewed and bool(reviewed[year]['signing_bonus'])
            if bonus_qualifies:
                normalized['signing_bonus'] = reviewed[year]['signing_bonus']
            inputs = model_inputs(normalized, rows, residence, filing, bonus_qualifies)
            inputs['tax_year'] = year
            if year < 2025:
                inputs['local_work'] = {}
            result = calculate(inputs)
            base.update(status='estimated', federal=result['national']['federal'],
                        payroll=result['national']['payroll']['total'], state=result['tax']['total'],
                        local=result['local']['total'] if year >= 2025 else None,
                        total_tax=result['total_tax'], remaining=result['remaining'], duty_days=len(rows))
        annual.append(base)
        previous = cash
    included = [r for r in annual if r['status'] == 'estimated']
    sources = [dict(name='Reported contract cash: OverTheCap via nflverse', url=contract['source_url']),
               dict(name='Published NFL games and venues: ESPN', url=data()['metadata']['schedule_source']),
               dict(name='Historical state tax compilation and government corrections', url='https://taxfoundation.org/data/all/state/state-income-tax-rates/')]
    for year in sorted({r['year'] for r in included}):
        sources.append(dict(name=f'{year} federal tax rules', url=federal_history()[str(year)]['source'] if year < 2025 else FEDERAL_SOURCE if year == 2026 else 'https://www.irs.gov/pub/irs-prior/i1040gi--2025.pdf'))
    return dict(year_start=contract['year_signed'], year_end=min(2026, contract['cash'][-1]['year']),
                residence=residence, annual=annual, included_years=[r['year'] for r in included],
                excluded_years=[r['year'] for r in annual if r['status'] != 'estimated'],
                gross=sum(r['cash'] for r in included) if included else None,
                total_tax=sum(r['total_tax'] for r in included) if included else None,
                remaining=sum(r['remaining'] for r in included) if included else None,
                sources=sources, notes=[
                    'A separate estimate using each calendar year’s federal, employee payroll and state tax inputs. This subtotal overlaps the full-contract forecast above; do not add them together. The existing forecast and its future projections remain unchanged.',
                    'Covers the saved 2025 player directory and the reported signing-year cash window through the earlier of its end or 2026. Extension signing years can differ from legal effective dates. Missing or ambiguous years are excluded from both cash and tax subtotals.',
                    'Published game venues are used; duty days and attendance remain estimates. 2025 uses weekly rosters. Other years use one reported cash-history team, July 23 camp, Tuesday off and selected road arrival days. January includes prior-season service once; first-window January affiliation is assumed to match that year’s team unless the player is a rookie.',
                    'Historical practice locations are assumed to match each team’s saved practice state; camp moves and midyear transactions outside 2025 are unverified. The selected residence is a comparison assumption across every included year, not the player’s actual historical residence.',
                    'Historical state tables and simplified credits/deductions remain provisional. Local taxes before 2025 are not modeled and are excluded from those totals. Foreign taxes, residence-city taxes and unsupported local/payroll taxes are excluded.',
                    '2026 includes published scheduled games and reported cash, with modeled attendance and earnings; it is not a completed tax return. Unpublished postseason participation is excluded. Cash is treated as service wages except the optional reviewed Allen signing-bonus assumption.'
                ])
