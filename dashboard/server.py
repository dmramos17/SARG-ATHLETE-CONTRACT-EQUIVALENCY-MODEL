"""Local research dashboard. Run: python dashboard/server.py"""
from __future__ import annotations

import json
import math
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.duty_days import CompItem, DutyDayRatios, TaxTables, allocate, estimate_state_local_tax
from etl.annual_taxes import federal_payroll, estimate_local, FEDERAL_SOURCE, PAYROLL_SOURCES
from etl.contract_data import load_contracts, sync_contracts
from etl.estimated_duty_days import estimate_calendar, estimate_player_calendar, STATES as ALL_STATES
from etl.historical_taxes import sync_historical_taxes, FEDERAL_2025_SOURCE
from etl.player_directory import load_directory, search_players, find_player
from etl.player_tax import tax_contract, with_tax_info
from etl.league_projection import project_player
from etl.mlb_interface import catalog as mlb_catalog

STATES = {"MA": "Massachusetts", "TX": "Texas", "FL": "Florida", "NY": "New York", "NJ": "New Jersey", "CA": "California"}
STATES.update({"PA": "Pennsylvania", "MI": "Michigan", "OH": "Ohio", "MO": "Missouri", "MD": "Maryland"})
STATES.update({"WA": "Washington", "CO": "Colorado"})
STATES.update({"AZ":"Arizona", "GA":"Georgia", "IN":"Indiana", "LA":"Louisiana",
               "MN":"Minnesota", "NC":"North Carolina", "NV":"Nevada", "TN":"Tennessee", "WI":"Wisconsin"})
STATES.update(ALL_STATES)
LOCALITIES = {"NYC": ("New York City", "NY"), "PHL": ("Philadelphia", "PA"),
              "DET": ("Detroit", "MI"), "CLE": ("Cleveland", "OH"),
              "CIN": ("Cincinnati", "OH"), "COL": ("Columbus", "OH"),
              "KCM": ("Kansas City", "MO"), "STL": ("St. Louis", "MO"),
              "MDNR": ("Maryland special nonresident tax", "MD")}


def calculate(data):
    year = data.get("tax_year", 2026)
    if type(year) is not int or year not in (2025, 2026):
        raise ValueError("Choose tax year 2025 or 2026.")
    residence = data.get("residence")
    if residence not in STATES:
        raise ValueError("Choose one of the supported residence states.")
    filing = data.get("filing", "single")
    if filing not in ("single", "mfj"):
        raise ValueError("Choose a supported filing status.")
    def amount(key):
        value = float(data.get(key, 0))
        if not math.isfinite(value) or not 0 <= value <= 1_000_000_000:
            raise ValueError("Compensation must be between $0 and $1 billion.")
        return value
    salary, bonus, other = amount("salary"), amount("bonus"), amount("other_cash")
    gross = salary + bonus + other
    if gross <= 0:
        raise ValueError("Enter compensation greater than zero.")
    days = data.get("days", {})
    if not isinstance(days, dict) or set(days) - set(STATES):
        raise ValueError("Duty days contain an unsupported state.")
    counts = {}
    for state, value in days.items():
        number = float(value)
        if not math.isfinite(number) or number != int(number) or not 0 <= number <= 366:
            raise ValueError("Duty days must be whole numbers from 0 to 366.")
        if number:
            counts[state] = int(number)
    unsourced = float(data.get("unsourced", 0))
    if not math.isfinite(unsourced) or unsourced != int(unsourced) or not 0 <= unsourced <= 366:
        raise ValueError("Unsourced days must be whole numbers from 0 to 366.")
    total_days = sum(counts.values()) + int(unsourced)
    if not 1 <= total_days <= 365:
        raise ValueError(f"Total {year} duty days must be between 1 and 365.")
    treatment = data.get("bonus_treatment", "qualifying")
    if treatment not in ("qualifying", "conditional"):
        raise ValueError("Choose a supported signing-bonus treatment.")
    city = data.get("resident_city", "")
    if city and (city not in LOCALITIES or city == "MDNR" or LOCALITIES[city][1] != residence):
        raise ValueError("Residence city must be in the selected residence state.")
    early_cash = float(data.get("early_cash", 0))
    if not math.isfinite(early_cash) or not 0 <= early_cash <= gross:
        raise ValueError("Cash paid before July 1 must be between $0 and total compensation.")
    local_work = data.get("local_work", {})
    if not isinstance(local_work, dict) or set(local_work) - set(LOCALITIES):
        raise ValueError("Unsupported local work jurisdiction.")
    normalized_work = {}
    state_local_bases = {}
    for locality, periods in local_work.items():
        if not isinstance(periods, dict) or set(periods) - {"early", "late"}:
            raise ValueError("Local compensation needs early and late payment amounts.")
        amounts = {key: float(periods.get(key, 0)) for key in ("early", "late")}
        if any(not math.isfinite(v) or v < 0 for v in amounts.values()):
            raise ValueError("Local taxable compensation must be a nonnegative finite amount.")
        if amounts["early"] > early_cash or amounts["late"] > gross - early_cash:
            raise ValueError("Local taxable compensation cannot exceed cash paid in that period.")
        state = LOCALITIES[locality][1]
        if sum(amounts.values()) and not counts.get(state):
            raise ValueError(f"Add duty days in {state} before entering local work compensation.")
        if locality == "MDNR" and residence == "MD" and sum(amounts.values()):
            raise ValueError("Maryland special nonresident tax does not apply to Maryland residents; county taxes are not yet modeled.")
        if locality not in ("NYC", city):
            state_local_bases[state] = state_local_bases.get(state, 0) + sum(amounts.values())
            if state_local_bases[state] > gross:
                raise ValueError("Combined local wage bases in a state cannot exceed total compensation.")
        normalized_work[locality] = amounts
    tables = TaxTables(ROOT / "athlete_tax.db", year, filing)
    try:
        for state in set(counts) | {residence}:
            if tables.taxes_wages(state) and not tables.brackets(state):
                raise ValueError(f"Missing {year} tax brackets for {state}; estimate cannot proceed.")
        ratios = DutyDayRatios(year, total_days, counts, {}, int(unsourced))
        items = [CompItem("salary", salary), CompItem("roster_bonus", other), CompItem("signing_bonus", bonus,
                 conditioned_on_play=treatment == "conditional")]
        allocation = allocate(items, ratios, tables.bonus_rules())
        tax = estimate_state_local_tax(tables, allocation, residence)
        national = federal_payroll(tables, gross)
        local = estimate_local(tables, city, gross, early_cash, normalized_work)
        combined = tax["total"] + national["federal"] + national["payroll"]["total"] + local["total"]
        rows = [{"state": s, "name": STATES[s], "days": n, "ratio": n / total_days,
                 "salary_sourced": salary * n / total_days,
                 "total_sourced": allocation.sourced.get(s, 0),
                 "nonresident_tax": tax["nonresident"].get(s, 0),
                 "is_residence": s == residence} for s, n in counts.items()]
        sources = [dict(state="Federal", status="verified", source=FEDERAL_2025_SOURCE if year == 2025 else FEDERAL_SOURCE)]
        sources += [dict(state="Payroll", status="verified", source=url) for url in PAYROLL_SOURCES]
        sources += local["sources"]
        for state in sorted(set(counts) | {residence}):
            for table in ("state_income_tax_brackets", "state_surtaxes"):
                query = f"SELECT DISTINCT verification_status, source FROM {table} WHERE tax_year=? AND state_code=?"
                params = [year, state]
                if table == "state_income_tax_brackets":
                    query += " AND filing_status=?"
                    params.append(filing)
                for status, source in tables.con.execute(query, params):
                    sources.append({"state": state, "status": status, "source": source})
        notes = list(allocation.notes)
        if local["total"]:
            notes.append("Local taxes are before city exemptions, refunds, and cross-jurisdiction credits (including state credits for city tax). These omissions can overstate combined tax.")
        if year == 2025:
            notes.append("2025 demo: reported season cash approximates calendar-year wages. State estimates omit deductions, exemptions, benefit recapture and some jurisdiction-specific sourcing/credits; state rows remain provisional. Pittsburgh, Cleveland, Detroit, Indiana county and Maryland resident-county taxes, other unsupported local taxes, foreign tax and state payroll programs are excluded.")
        for state in sorted(set(counts) | {residence}) if year == 2026 else []:
            profile = tables.con.execute("SELECT notes FROM state_tax_profile WHERE state_code=?", (state,)).fetchone()
            if profile and profile[0]:
                notes.append(f"{state}: {profile[0]}")
        return {"tax_year": year, "gross": gross, "remaining": gross - combined,
                "effective_rate": combined / gross, "total_tax": combined,
                "tax": tax, "national": national, "local": local,
                "rows": rows, "total_days": total_days,
                "residence_only": allocation.residence_only,
                "notes": notes, "sources": sources}
    finally:
        tables.con.close()


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        if path == "/api/contracts":
            requested = parse_qs(url.query).get('player', [''])[0]
            reviewed = [tax_contract(p) for p in load_directory()['players'] if p.get('estimate_id')]
            if requested:
                player = find_player(requested) or next((p for p in load_directory()['players'] if p.get('estimate_id') == requested), None)
                if not player:
                    self.respond(404, {'error': 'Player not found.'})
                    return
                chosen = tax_contract(player)
                teammates = sorted(
                    (p for p in load_directory()['players']
                     if p['team_id'] == player['team_id'] and p['id'] != player['id']),
                    key=lambda p: p['name'].casefold(),
                )
                reviewed = [chosen] + [tax_contract(p) for p in teammates]
            self.respond(200, reviewed)
        elif path == '/api/contract-projection':
            query = parse_qs(url.query)
            requested = query.get('player', [''])[0]
            player = find_player(requested) or next((p for p in load_directory()['players'] if p.get('estimate_id') == requested), None)
            if not player:
                self.respond(404, {'error': 'Player not found in the 2025 directory.'})
                return
            try:
                result = project_player(calculate, player['id'], query.get('residence', [player['home_state']])[0],
                                 query.get('filing', ['single'])[0],
                                 query.get('qualifying', ['0'])[0] == '1',
                                 int(query.get('travel_days', ['1'])[0]))
                self.respond(200, result)
            except (ValueError, TypeError) as error:
                self.respond(400, {'error': str(error)})
        elif path == "/api/directory":
            directory = load_directory()
            by_id = {p['id']: with_tax_info(p) for p in directory['players']}
            metadata = dict(directory['metadata'])
            metadata.update(estimate_count=sum(p['tax_ready'] for p in by_id.values()),
                            cash_required_count=sum(not p['tax_ready'] for p in by_id.values()),schedule_team_count=32)
            self.respond(200, dict(metadata=metadata,
                                   featured=[by_id[i] for i in directory['featured_ids']],
                                   tax_examples=[p for p in by_id.values() if p['reviewed_example']]))
        elif path == "/api/players":
            query = parse_qs(url.query).get('q', [''])[0]
            if len(query) > 120:
                self.respond(400, {'error': 'Search must be 120 characters or fewer.'})
                return
            self.respond(200, {'players': [dict(row, **{k:v for k,v in with_tax_info(find_player(row['id'])).items()
                                                       if k in ('estimate_id','estimate_cash','tax_ready','reviewed_example','data_status')})
                                           for row in search_players(query)]})
        elif path.startswith('/api/players/'):
            player = find_player(path.removeprefix('/api/players/'))
            self.respond(200 if player else 404, with_tax_info(player) if player else {'error': 'Player not found in the 2025 directory.'})
        elif path == '/api/mlb/directory':
            self.respond(200, mlb_catalog())
        elif path in ('/mlb', '/mlb/') or path.startswith('/mlb/players/'):
            self.respond(200, Path(__file__).with_name('mlb.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ("/", "/index.html"):
            self.respond(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
        elif path.startswith('/players/'):
            self.respond(200, Path(__file__).with_name('player.html').read_bytes(), 'text/html; charset=utf-8')
        elif path.startswith('/taxes/') and (path.removeprefix('/taxes/') in {r['id'] for r in load_contracts()} or find_player(path.removeprefix('/taxes/'))):
            self.respond(200, Path(__file__).with_name('tax.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ('/styles.css', '/home.js', '/player.js', '/common.js', '/projection.js', '/mlb.js', '/mlb.css'):
            kind = 'text/css' if path.endswith('.css') else 'text/javascript'
            self.respond(200, Path(__file__).with_name(path[1:]).read_bytes(), kind+'; charset=utf-8')
        else:
            self.respond(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/api/calculate", "/api/duty-days"):
            self.respond(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16_384:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected calculation inputs.")
            if self.path == "/api/duty-days":
                player = find_player(data['player_id']) if data.get('player_id') else None
                if data.get('player_id') and not player:
                    raise ValueError('Player membership record not found.')
                result = (estimate_player_calendar if player else estimate_calendar)(player if player else data.get("team_id", ""), travel_days=data.get("travel_days",1),
                                           weekly_off_day=data.get("weekly_off_day",1),
                                           excluded_dates=data.get("excluded_dates",[]),
                                           additional_days=data.get("additional_days",[]), overrides=data.get("overrides",{}))
            else:
                result = calculate(data)
        except (ValueError, TypeError, OverflowError) as exc:
            self.respond(400, {"error": str(exc)})
            return
        except Exception:
            self.respond(500, {"error": "Calculation unavailable. Check the server terminal and tax database."})
            return
        self.respond(200, result)


if __name__ == "__main__":
    if not (ROOT / "athlete_tax.db").exists():
        sys.exit("Missing athlete_tax.db. Run python src/athlete_tax/clean_tax_data.py first.")
    sync_contracts()
    sync_historical_taxes()
    print("Athlete Tax Lab: http://127.0.0.1:8765", flush=True)
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
