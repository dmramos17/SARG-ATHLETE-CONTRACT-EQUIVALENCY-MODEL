"""
etl/duty_days.py -- Week 4: duty-day allocation formulas.

Implements the uniform nonresident-athlete rule (FTA model, adopted e.g. in MA 830 CMR 62.5A.2,
35 ILCS 5/304(a)(2)(B)(iv), N.J.A.C. 18:35-5.1):

  * Duty days run from the start of official preseason training through the team's last game,
    including postseason, and are counted per CALENDAR tax year.
  * Every duty day is in the denominator.
  * A day is sourced to the state where it happens only if a game, practice, meeting, promotional
    event, or rehab AT A TEAM FACILITY happens that day. Travel days with no team event and
    injured days away from team facilities stay in the denominator but are not sourced anywhere
    (they fall to the residence state).
  * Suspended-without-pay days are not duty days at all (excluded before counting).

Then, per compensation item:
  * Salary, roster, per-game, performance, playoff bonuses -> allocated by the duty-day ratio.
  * Signing bonus -> residence state only if it passes the three-part test (nonrefundable, paid
    separately, not conditioned on playing). California allocates the conditional/refundable part
    by duty days. Rules come from state_jock_tax_rules.signing_bonus_sourcing.

Tax helpers (preview of the Week 7 engine):
  * Nonresident state tax uses the effective-rate method for every state (Tax Foundation 2026):
    tax on ALL income as if earned in the state x (sourced / total). Exception: the MA surtax
    applies only to MA-sourced income above the threshold (Mass. DOR).
  * Resident state tax on all income, minus a credit for other states' tax, capped at the resident
    state's own tax on that income.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SOURCED_EVENTS = {"game", "practice", "meeting", "injured_team_facility", "offseason_service", "promotional"}
UNSOURCED_EVENTS = {"travel", "injured_elsewhere"}
ALL_EVENTS = SOURCED_EVENTS | UNSOURCED_EVENTS


# --------------------------------------------------------------------------- duty days
@dataclass(frozen=True)
class DutyDay:
    day: date
    event: str                     # one of ALL_EVENTS
    state: str | None              # where the player physically is (None = outside the US / unknown)
    locality: str | None = None    # locality_id when a city tax may apply
    projected: bool = False        # True for future schedules we had to assume

    def __post_init__(self):
        if self.event not in ALL_EVENTS:
            raise ValueError(f"unknown event type {self.event!r}")

    @property
    def counts_in_state(self) -> bool:
        return self.event in SOURCED_EVENTS


@dataclass
class RoadGame:
    game_day: date
    state: str
    locality: str | None = None
    arrive_day_event: str = "meeting"   # NFL teams usually hold a walkthrough/meeting on arrival
    days_before: int = 1                # arrive this many days before the game
    projected: bool = False


def build_season(window_start: date, window_end: date, practice_state: str, road_games: list[RoadGame],
                 home_games: list[date] = (), stadium_state: str | None = None,
                 practice_locality: str | None = None, stadium_locality: str | None = None,
                 off_days: list[date] = (), injured: dict[date, str] | None = None) -> list[DutyDay]:
    """Lay out every calendar day in the duty-day window.

    Default day = practice at the practice site. Home games happen at the stadium (which can be a
    different state: Commanders VA/MD, Capitals VA/DC, Flyers NJ/PA). Road trips put arrival and
    game days in the road state. Off days ("days off" inside the window) are still duty days per the
    uniform rule but have no event, so they are modeled as unsourced 'travel'-type days at home.
    `injured` maps a date to 'injured_team_facility' or 'injured_elsewhere'.
    """
    stadium_state = stadium_state or practice_state
    injured = injured or {}
    days: dict[date, DutyDay] = {}
    d = window_start
    while d <= window_end:
        days[d] = DutyDay(d, "practice", practice_state, practice_locality)
        d += timedelta(days=1)
    for d in off_days:
        if d in days:
            days[d] = DutyDay(d, "travel", practice_state, None)  # in denominator, not sourced
    for d in home_games:
        if d in days:
            days[d] = DutyDay(d, "game", stadium_state, stadium_locality)
    for g in road_games:
        for k in range(g.days_before, 0, -1):
            a = g.game_day - timedelta(days=k)
            if a in days:
                days[a] = DutyDay(a, g.arrive_day_event, g.state, g.locality, g.projected)
        if g.game_day in days:
            days[g.game_day] = DutyDay(g.game_day, "game", g.state, g.locality, g.projected)
    for d, ev in injured.items():
        if d in days:
            # injured at a team facility: sourced where the team facility is (practice site);
            # injured elsewhere: never sourced (MA 830 CMR 62.5A.2(3)(d), Example 2)
            st = practice_state if ev == "injured_team_facility" else days[d].state
            days[d] = DutyDay(d, ev, st, None)
    return [days[k] for k in sorted(days)]


@dataclass
class DutyDayRatios:
    tax_year: int
    total_days: int
    state_days: dict[str, int]
    locality_days: dict[str, int]
    unsourced_days: int

    def state_ratio(self, state: str) -> float:
        return self.state_days.get(state, 0) / self.total_days if self.total_days else 0.0

    def locality_ratio(self, loc: str) -> float:
        return self.locality_days.get(loc, 0) / self.total_days if self.total_days else 0.0


def duty_day_ratios(days: list[DutyDay], tax_year: int) -> DutyDayRatios:
    """Count duty days for ONE calendar tax year (seasons crossing New Year are split)."""
    yr = [d for d in days if d.day.year == tax_year]
    st, loc = defaultdict(int), defaultdict(int)
    unsourced = 0
    for d in yr:
        if d.counts_in_state and d.state:
            st[d.state] += 1
            if d.locality:
                loc[d.locality] += 1
        else:
            unsourced += 1
    return DutyDayRatios(tax_year, len(yr), dict(st), dict(loc), unsourced)


# --------------------------------------------------------------------------- compensation
@dataclass
class CompItem:
    kind: str                      # salary | roster_bonus | per_game_bonus | performance_bonus | signing_bonus
    amount: float
    # signing-bonus attributes (three-part test)
    nonrefundable: bool = True
    paid_separately: bool = True
    conditioned_on_play: bool = False
    refundable_amount: float = 0.0  # CA allocates the part that must be earned back by services

    @property
    def passes_three_part_test(self) -> bool:
        return self.nonrefundable and self.paid_separately and not self.conditioned_on_play


@dataclass
class Allocation:
    sourced: dict[str, float] = field(default_factory=lambda: defaultdict(float))     # state -> $
    sourced_local: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    residence_only: float = 0.0     # income only the residence state may tax
    total: float = 0.0
    notes: list[str] = field(default_factory=list)


def allocate(items: list[CompItem], ratios: DutyDayRatios, bonus_rules: dict[str, str]) -> Allocation:
    """Source each compensation item to work states.

    bonus_rules: state_code -> signing_bonus_sourcing value from state_jock_tax_rules
                 ('residence_if_three_part_test' | 'partial_duty_days' | 'duty_days' | 'unknown' | ...)
    'unknown' is treated like the three-part test (the majority rule) and noted.
    """
    out = Allocation()
    for it in items:
        out.total += it.amount
        if it.kind != "signing_bonus":
            for s, n in ratios.state_days.items():
                out.sourced[s] += it.amount * n / ratios.total_days
            for l, n in ratios.locality_days.items():
                out.sourced_local[l] += it.amount * n / ratios.total_days
            out.residence_only += it.amount * ratios.unsourced_days / ratios.total_days
            continue
        # signing bonus
        allocated_any = 0.0
        for s, n in ratios.state_days.items():
            rule = bonus_rules.get(s, "unknown")
            share = n / ratios.total_days
            if rule == "duty_days" or (rule != "partial_duty_days" and not it.passes_three_part_test):
                amt = it.amount * share
            elif rule == "partial_duty_days":
                amt = it.refundable_amount * share if it.passes_three_part_test else it.amount * share
            else:
                amt = 0.0
                if rule == "unknown":
                    out.notes.append(f"{s}: signing-bonus rule unknown; three-part test assumed")
            out.sourced[s] += amt
            allocated_any += amt
        out.residence_only += it.amount - allocated_any
    out.sourced = dict(out.sourced)
    out.sourced_local = dict(out.sourced_local)
    return out


# --------------------------------------------------------------------------- tax (preview)
class TaxTables:
    """Thin reader over athlete_tax.db built by db/clean_tax_data.py."""

    def __init__(self, db_path: str | Path, tax_year: int = 2026, filing_status: str = "single"):
        self.con = sqlite3.connect(str(db_path))
        self.year, self.fs = tax_year, filing_status

    def brackets(self, state: str):
        return self.con.execute(
            "SELECT lower_bound, rate FROM state_income_tax_brackets WHERE tax_year=? AND state_code=? "
            "AND filing_status=? ORDER BY bracket_order", (self.year, state, self.fs)).fetchall()

    def surtaxes(self, state: str):
        return self.con.execute(
            "SELECT threshold, rate FROM state_surtaxes WHERE tax_year=? AND state_code=?",
            (self.year, state)).fetchall()

    def taxes_wages(self, state: str) -> bool:
        r = self.con.execute("SELECT taxes_wages FROM state_tax_profile WHERE state_code=?", (state,)).fetchone()
        return bool(r and r[0])

    def bonus_rules(self) -> dict[str, str]:
        return dict(self.con.execute("SELECT state_code, signing_bonus_sourcing FROM state_jock_tax_rules "
                                     "WHERE tax_year=? AND league='ALL'", (self.year,)).fetchall())

    def local_nonresident_rate(self, locality: str, on: str = "12-31") -> float:
        r = self.con.execute(
            "SELECT nonresident_rate, legal_status FROM local_income_tax_rates WHERE locality_id=? "
            "AND effective_date <= ? ORDER BY effective_date DESC LIMIT 1",
            (locality, f"{self.year}-{on}")).fetchone()
        if not r or r[1] != "in_force" or r[0] is None:
            return 0.0
        return float(r[0])


def bracket_tax(rows, income: float) -> float:
    total = 0.0
    for i, (low, rate) in enumerate(rows):
        upper = rows[i + 1][0] if i + 1 < len(rows) else float("inf")
        if income > low:
            total += (min(income, upper) - low) * rate
    return total


def resident_tax(t: TaxTables, state: str, income: float) -> float:
    if not t.taxes_wages(state):
        return 0.0
    return bracket_tax(t.brackets(state), income) + sum(max(0.0, income - th) * r for th, r in t.surtaxes(state))


def nonresident_tax(t: TaxTables, state: str, total_income: float, sourced: float) -> float:
    """Effective-rate method; MA surtax applied only to MA-sourced income above the threshold."""
    if sourced <= 0 or not t.taxes_wages(state) or state == "DC":
        return 0.0
    base = bracket_tax(t.brackets(state), total_income) * sourced / total_income
    surtax = sum(max(0.0, sourced - th) * r for th, r in t.surtaxes(state))
    return base + surtax


def estimate_state_local_tax(t: TaxTables, alloc: Allocation, residence_state: str | None) -> dict:
    """State + local tax for one tax year. residence_state=None means a no-tax-state domicile."""
    res = residence_state if residence_state and t.taxes_wages(residence_state) else None
    nonres = {s: nonresident_tax(t, s, alloc.total, amt)
              for s, amt in alloc.sourced.items() if s != res}
    home = resident_tax(t, res, alloc.total) if res else 0.0
    credit = 0.0
    if res:
        for s, tax in nonres.items():
            # credit capped at what the residence state would charge on that same income
            cap = home * alloc.sourced[s] / alloc.total
            credit += min(tax, cap)
    local = {l: amt * t.local_nonresident_rate(l) for l, amt in alloc.sourced_local.items()}
    total = home - credit + sum(nonres.values()) + sum(local.values())
    return dict(residence_tax=home, credit=credit, nonresident=nonres, local=local, total=total)