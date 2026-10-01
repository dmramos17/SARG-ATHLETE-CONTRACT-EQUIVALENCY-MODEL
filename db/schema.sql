-- =====================================================================
-- Athlete Tax Policy Equivalency Analytics -- SQLite schema (v1)
--
-- CONVENTIONS
--   * Rates are decimal fractions (0.0535 = 5.35%), never percent strings.
--   * Money is REAL, in whole dollars (cents allowed).
--   * Dates are ISO text (YYYY-MM-DD). Seasons are the starting year (2026).
--   * Bracket tables store a THRESHOLD (lower_bound) per row; the upper bound
--     is derived by the v_*_brackets views. The first bracket of every
--     schedule MUST start at 0 (a 0% bracket is inserted when a state has a
--     zero-rate band, e.g. Ohio, Delaware, Mississippi). v_check_* views
--     return rows that break this; they must be empty after every load.
--   * verification_status: 'verified' | 'needs_check' | 'stale_2025' | 'provisional'
--   * Surtaxes (MA 4%, CA 1% MHST) live ONLY in state_surtaxes. Do not also
--     load them as bracket rows or they are double-counted.
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

-- ---------------------------------------------------------------------
-- 1. STATE-LEVEL TAX DATA
-- ---------------------------------------------------------------------

-- One row per state + DC. Structural attributes that do not change by year.
CREATE TABLE state_tax_profile (
    state_code                  TEXT PRIMARY KEY CHECK (length(state_code) = 2),
    state_name                  TEXT NOT NULL UNIQUE,
    income_tax_type             TEXT NOT NULL
        CHECK (income_tax_type IN ('none','flat','graduated','cap_gains_only')),
    taxes_wages                 INTEGER NOT NULL CHECK (taxes_wages IN (0,1)),
    -- How the state taxes the sourced slice of a NONRESIDENT athlete:
    --   direct    = run brackets on the in-state income only
    --   proration = compute tax on ALL income, then multiply by in-state share
    -- (CA, NY, NJ are proration; everything else defaults to direct.)
    nonresident_rate_method     TEXT NOT NULL DEFAULT 'direct'
        CHECK (nonresident_rate_method IN ('direct','proration')),
    nonresident_method_status   TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (nonresident_method_status IN ('verified','needs_check','stale_2025','provisional')),
    has_athlete_duty_day_rule   INTEGER CHECK (has_athlete_duty_day_rule IN (0,1)),
    notes                       TEXT
);

-- Brackets in LONG form (one row per bracket per filing status).
-- The Tax Foundation export is wide and has "- Alabama" continuation rows;
-- the cleaning step turns it into this shape.
CREATE TABLE state_income_tax_brackets (
    tax_year            INTEGER NOT NULL,
    state_code          TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    filing_status       TEXT    NOT NULL CHECK (filing_status IN ('single','mfj')),
    bracket_order       INTEGER NOT NULL CHECK (bracket_order >= 1),
    lower_bound         REAL    NOT NULL CHECK (lower_bound >= 0),
    rate                REAL    NOT NULL CHECK (rate >= 0 AND rate <= 1),
    verification_status TEXT    NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source              TEXT,
    PRIMARY KEY (tax_year, state_code, filing_status, bracket_order),
    UNIQUE      (tax_year, state_code, filing_status, lower_bound)
);

-- Standard deduction / personal exemption. Barely matters at athlete income
-- levels, but the engine should still know whether something is a credit.
CREATE TABLE state_deductions (
    tax_year                  INTEGER NOT NULL,
    state_code                TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    filing_status             TEXT    NOT NULL CHECK (filing_status IN ('single','mfj')),
    standard_deduction        REAL,
    std_deduction_is_credit   INTEGER NOT NULL DEFAULT 0 CHECK (std_deduction_is_credit IN (0,1)),
    personal_exemption        REAL,
    exemption_is_credit       INTEGER NOT NULL DEFAULT 0 CHECK (exemption_is_credit IN (0,1)),
    PRIMARY KEY (tax_year, state_code, filing_status)
);

-- Millionaire's taxes / surtaxes, kept apart from brackets.
--   MA: 4% over $1,107,750 (2026); threshold not doubled for joint filers;
--       applies to nonresidents on MA-sourced income only; employer withholds
--       only the flat 5%, so the surtax is settled on the player's return.
--   CA: 1% Mental Health Services Tax over $1,000,000.
CREATE TABLE state_surtaxes (
    tax_year                   INTEGER NOT NULL,
    state_code                 TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    surtax_name                TEXT    NOT NULL,
    threshold                  REAL    NOT NULL,
    rate                       REAL    NOT NULL CHECK (rate > 0 AND rate <= 1),
    threshold_doubled_for_mfj  INTEGER NOT NULL DEFAULT 0 CHECK (threshold_doubled_for_mfj IN (0,1)),
    applies_to_nonresidents    INTEGER NOT NULL DEFAULT 1 CHECK (applies_to_nonresidents IN (0,1)),
    withheld_by_employer       INTEGER NOT NULL DEFAULT 0 CHECK (withheld_by_employer IN (0,1)),
    verification_status        TEXT    NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source                     TEXT,
    notes                      TEXT,
    PRIMARY KEY (tax_year, state_code, surtax_name)
);

-- Cost-of-living layer (dashboard feature); from the Tax Foundation sales tax file.
CREATE TABLE state_sales_tax (
    tax_year         INTEGER NOT NULL,
    state_code       TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    state_rate       REAL    NOT NULL,
    avg_local_rate   REAL,
    max_local_rate   REAL,
    combined_rate    REAL,
    PRIMARY KEY (tax_year, state_code)
);

-- ---------------------------------------------------------------------
-- 2. FEDERAL TAX DATA
-- ---------------------------------------------------------------------

CREATE TABLE federal_brackets (
    tax_year            INTEGER NOT NULL,
    filing_status       TEXT    NOT NULL CHECK (filing_status IN ('single','mfj','mfs','hoh')),
    bracket_order       INTEGER NOT NULL CHECK (bracket_order >= 1),
    lower_bound         REAL    NOT NULL CHECK (lower_bound >= 0),
    rate                REAL    NOT NULL CHECK (rate >= 0 AND rate <= 1),
    verification_status TEXT    NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source              TEXT,
    PRIMARY KEY (tax_year, filing_status, bracket_order),
    UNIQUE      (tax_year, filing_status, lower_bound)
);

CREATE TABLE federal_filing_params (
    tax_year                  INTEGER NOT NULL,
    filing_status             TEXT    NOT NULL CHECK (filing_status IN ('single','mfj','mfs','hoh')),
    standard_deduction        REAL    NOT NULL,
    addl_medicare_threshold   REAL,
    PRIMARY KEY (tax_year, filing_status)
);

CREATE TABLE federal_payroll_params (
    tax_year             INTEGER PRIMARY KEY,
    ss_rate              REAL NOT NULL,
    ss_wage_base         REAL NOT NULL,
    medicare_rate        REAL NOT NULL,
    addl_medicare_rate   REAL NOT NULL,
    salt_cap_effective   REAL,            -- ~10,000 for athletes after phase-down
    salt_status          TEXT DEFAULT 'needs_check'
);

-- ---------------------------------------------------------------------
-- 3. LOCAL (CITY) TAXES  -- rates change mid-year, so key by effective date
-- ---------------------------------------------------------------------

CREATE TABLE localities (
    locality_id   TEXT PRIMARY KEY,                    -- e.g. 'PHL','NYC','DET'
    locality_name TEXT NOT NULL,
    state_code    TEXT NOT NULL REFERENCES state_tax_profile(state_code)
);

CREATE TABLE local_income_tax_rates (
    locality_id               TEXT NOT NULL REFERENCES localities(locality_id),
    effective_date            TEXT NOT NULL,
    resident_rate             REAL CHECK (resident_rate    BETWEEN 0 AND 1),
    nonresident_rate          REAL CHECK (nonresident_rate BETWEEN 0 AND 1),
    taxes_nonresident_work    INTEGER CHECK (taxes_nonresident_work IN (0,1)),
    apportionment_method      TEXT
        CHECK (apportionment_method IN ('duty_day','days_worked','games_played','flat_fee','none')),
    verification_status       TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source                    TEXT,
    notes                     TEXT,
    PRIMARY KEY (locality_id, effective_date)
);

-- ---------------------------------------------------------------------
-- 4. JOCK TAX RULES (per state and league: formulas differ by both)
-- ---------------------------------------------------------------------

CREATE TABLE state_jock_tax_rules (
    state_code                    TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    league                        TEXT    NOT NULL CHECK (league IN ('ALL','NFL','MLB','NHL','NBA')),
    tax_year                      INTEGER NOT NULL,
    sourcing_method               TEXT    NOT NULL
        CHECK (sourcing_method IN ('duty_day','games_played','flat_fee','general_nonresident')),
    duty_day_definition           TEXT,     -- what counts: games, practices, meetings, travel
    employer_withholding_required INTEGER CHECK (employer_withholding_required IN (0,1)),
    composite_return_allowed      INTEGER CHECK (composite_return_allowed IN (0,1)),
    -- Three-part test (Clark): if a bonus is nonrefundable, paid separately,
    -- and not conditioned on playing, only the residence state taxes it.
    signing_bonus_sourcing        TEXT NOT NULL DEFAULT 'unknown'
        CHECK (signing_bonus_sourcing IN ('residence','duty_days','unknown')),
    retaliatory_provision         INTEGER CHECK (retaliatory_provision IN (0,1)),  -- e.g. Illinois
    statute_citation              TEXT,
    verification_status           TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    notes                         TEXT,
    PRIMARY KEY (state_code, league, tax_year)
);

-- ---------------------------------------------------------------------
-- 5. TEAMS, PLAYERS, SCHEDULE
-- ---------------------------------------------------------------------

-- Stadium and practice jurisdictions are separate on purpose:
-- Lions practice in Allen Park, Browns in Berea, Commanders in VA / games in MD.
CREATE TABLE teams (
    team_id            TEXT PRIMARY KEY,                -- e.g. 'NFL_NE'
    league             TEXT NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    team_name          TEXT NOT NULL,
    city               TEXT,
    country            TEXT NOT NULL DEFAULT 'US',      -- non-US teams are out of scope for v1
    stadium_state      TEXT REFERENCES state_tax_profile(state_code),
    stadium_locality   TEXT REFERENCES localities(locality_id),
    practice_state     TEXT REFERENCES state_tax_profile(state_code),
    practice_locality  TEXT REFERENCES localities(locality_id)
);

CREATE TABLE players (
    player_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name        TEXT NOT NULL,
    league           TEXT NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    position         TEXT,
    residence_state  TEXT REFERENCES state_tax_profile(state_code),  -- separate from team state
    external_id      TEXT,                              -- e.g. Pro-Football-Reference id
    UNIQUE (league, full_name, external_id)
);

-- Needed by the duty-day apportionment module (Week 7).
CREATE TABLE schedule_games (
    game_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    league           TEXT NOT NULL,
    season           INTEGER NOT NULL,
    game_date        TEXT NOT NULL,
    home_team_id     TEXT NOT NULL REFERENCES teams(team_id),
    away_team_id     TEXT NOT NULL REFERENCES teams(team_id),
    venue_state      TEXT REFERENCES state_tax_profile(state_code),
    venue_locality   TEXT REFERENCES localities(locality_id),
    is_postseason    INTEGER NOT NULL DEFAULT 0 CHECK (is_postseason IN (0,1)),
    is_neutral_site  INTEGER NOT NULL DEFAULT 0 CHECK (is_neutral_site IN (0,1))
);
CREATE INDEX idx_schedule_season ON schedule_games (league, season);

-- ---------------------------------------------------------------------
-- 6. CONTRACTS (headline terms + year-by-year cash flow)
-- ---------------------------------------------------------------------

CREATE TABLE contracts (
    contract_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id                 INTEGER NOT NULL REFERENCES players(player_id),
    team_id                   TEXT    NOT NULL REFERENCES teams(team_id),
    signed_date               TEXT,
    first_season              INTEGER NOT NULL,
    last_season               INTEGER NOT NULL,         -- last REAL season, excluding void years
    total_value               REAL    NOT NULL,
    aav                       REAL,
    total_guaranteed          REAL,
    -- Residence at signing drives signing-bonus sourcing; keep it per contract.
    residence_state_at_signing TEXT REFERENCES state_tax_profile(state_code),
    is_extension              INTEGER NOT NULL DEFAULT 0 CHECK (is_extension IN (0,1)),
    verification_status       TEXT NOT NULL DEFAULT 'provisional'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source_primary            TEXT,                     -- e.g. Spotrac URL
    source_secondary          TEXT,                     -- e.g. OverTheCap URL
    accessed_date             TEXT,
    notes                     TEXT,
    CHECK (last_season >= first_season),
    -- Project rule: 'verified' requires two independent sources.
    CHECK (verification_status <> 'verified'
           OR (source_primary IS NOT NULL AND source_secondary IS NOT NULL))
);
CREATE INDEX idx_contracts_player ON contracts (player_id);

-- Cash paid vs. cap charge are different things: model both.
CREATE TABLE contract_years (
    contract_id                 INTEGER NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    season                      INTEGER NOT NULL,
    base_salary                 REAL NOT NULL DEFAULT 0,
    signing_bonus_cash          REAL NOT NULL DEFAULT 0,  -- cash actually paid this year
    signing_bonus_cap_proration REAL NOT NULL DEFAULT 0,  -- cap accounting only
    roster_bonus                REAL NOT NULL DEFAULT 0,
    per_game_bonus              REAL NOT NULL DEFAULT 0,  -- per-game roster bonuses
    workout_bonus               REAL NOT NULL DEFAULT 0,
    incentives_ltbe             REAL NOT NULL DEFAULT 0,  -- "likely to be earned"
    incentives_nltbe            REAL NOT NULL DEFAULT 0,  -- "not likely to be earned"
    guaranteed_cash             REAL NOT NULL DEFAULT 0,
    cap_hit                     REAL,
    is_void_year                INTEGER NOT NULL DEFAULT 0 CHECK (is_void_year IN (0,1)),
    notes                       TEXT,
    PRIMARY KEY (contract_id, season)
);

-- Convenience: guaranteed-type cash per year (excludes incentives) for the tax engine.
CREATE VIEW v_contract_year_cash AS
SELECT contract_id, season,
       base_salary + signing_bonus_cash + roster_bonus + per_game_bonus + workout_bonus
           AS cash_ex_incentives,
       incentives_ltbe, incentives_nltbe, is_void_year
FROM contract_years;

-- ---------------------------------------------------------------------
-- 7. SALARY CAP AND PERFORMANCE
-- ---------------------------------------------------------------------

CREATE TABLE salary_cap (
    league      TEXT    NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    season      INTEGER NOT NULL,
    cap_type    TEXT    NOT NULL CHECK (cap_type IN ('hard_cap','luxury_tax_threshold')),  -- MLB = CBT
    cap_amount  REAL    NOT NULL,
    cap_floor   REAL,
    notes       TEXT,
    PRIMARY KEY (league, season)
);

CREATE TABLE performance (
    player_id      INTEGER NOT NULL REFERENCES players(player_id),
    season         INTEGER NOT NULL,
    team_id        TEXT REFERENCES teams(team_id),
    games_played   INTEGER,
    games_started  INTEGER,
    snaps          INTEGER,
    PRIMARY KEY (player_id, season)
);

-- League-specific metrics (PFF grades, WAR, ice time) in long form so the
-- schema does not change per league. Missing rows are fine (paywalled data).
CREATE TABLE performance_metrics (
    player_id     INTEGER NOT NULL REFERENCES players(player_id),
    season        INTEGER NOT NULL,
    metric_name   TEXT    NOT NULL,
    metric_value  REAL,
    source        TEXT,
    PRIMARY KEY (player_id, season, metric_name)
);

-- ---------------------------------------------------------------------
-- 8. VALIDATION VIEWS -- every one of these must return ZERO rows
-- ---------------------------------------------------------------------

CREATE VIEW v_federal_brackets AS
SELECT *, LEAD(lower_bound) OVER (
           PARTITION BY tax_year, filing_status ORDER BY bracket_order) AS upper_bound
FROM federal_brackets;

CREATE VIEW v_state_brackets AS
SELECT *, LEAD(lower_bound) OVER (
           PARTITION BY tax_year, state_code, filing_status ORDER BY bracket_order) AS upper_bound
FROM state_income_tax_brackets;

-- Every schedule must start at $0.
CREATE VIEW v_check_bracket_start AS
SELECT 'federal' AS tbl, tax_year, NULL AS state_code, filing_status
FROM federal_brackets GROUP BY tax_year, filing_status HAVING MIN(lower_bound) <> 0
UNION ALL
SELECT 'state', tax_year, state_code, filing_status
FROM state_income_tax_brackets GROUP BY tax_year, state_code, filing_status HAVING MIN(lower_bound) <> 0;

-- Thresholds must rise with bracket_order.
CREATE VIEW v_check_bracket_order AS
SELECT 'federal' AS tbl, tax_year, NULL AS state_code, filing_status, bracket_order
FROM v_federal_brackets WHERE upper_bound IS NOT NULL AND upper_bound <= lower_bound
UNION ALL
SELECT 'state', tax_year, state_code, filing_status, bracket_order
FROM v_state_brackets WHERE upper_bound IS NOT NULL AND upper_bound <= lower_bound;

-- States that tax wages but have no bracket rows (or vice versa).
CREATE VIEW v_check_state_coverage AS
SELECT p.state_code, 'taxes wages but no brackets' AS problem
FROM state_tax_profile p
WHERE p.taxes_wages = 1
  AND NOT EXISTS (SELECT 1 FROM state_income_tax_brackets b WHERE b.state_code = p.state_code)
UNION ALL
SELECT DISTINCT b.state_code, 'has brackets but taxes_wages = 0'
FROM state_income_tax_brackets b JOIN state_tax_profile p USING (state_code)
WHERE p.taxes_wages = 0;