-- =====================================================================
-- Athlete Tax Policy Equivalency Analytics -- SQLite schema (v2, Week 4)
-- v2 changes are marked "-- v2".
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

-- Curated research snapshots retain field provenance and unresolved discrepancies.
-- These are not promoted into verified contract_years until component sourcing is checked.
CREATE TABLE research_contract_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    player_name TEXT NOT NULL,
    tax_year INTEGER NOT NULL,
    accessed_date TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE state_tax_profile (
    state_code                  TEXT PRIMARY KEY CHECK (length(state_code) = 2),
    state_name                  TEXT NOT NULL UNIQUE,
    income_tax_type             TEXT NOT NULL
        CHECK (income_tax_type IN ('none','flat','graduated','cap_gains_only')),
    taxes_wages                 INTEGER NOT NULL CHECK (taxes_wages IN (0,1)),
    nonresident_rate_method     TEXT NOT NULL DEFAULT 'direct'
        CHECK (nonresident_rate_method IN ('direct','proration')),
    nonresident_method_status   TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (nonresident_method_status IN ('verified','needs_check','stale_2025','provisional')),
    has_athlete_duty_day_rule   INTEGER CHECK (has_athlete_duty_day_rule IN (0,1)),
    notes                       TEXT
);

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

CREATE TABLE state_sales_tax (
    tax_year         INTEGER NOT NULL,
    state_code       TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    state_rate       REAL    NOT NULL,
    avg_local_rate   REAL,
    max_local_rate   REAL,
    combined_rate    REAL,
    PRIMARY KEY (tax_year, state_code)
);

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
    salt_cap_effective   REAL,
    salt_status          TEXT DEFAULT 'needs_check'
);

CREATE TABLE localities (
    locality_id   TEXT PRIMARY KEY,
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
    tax_base                  TEXT,                                   -- v2: wage | income | earnings | special_nonresident_tax | facility_usage_fee
    legal_status              TEXT NOT NULL DEFAULT 'in_force'        -- v2: Pittsburgh's fee was struck down 2025-09-25
        CHECK (legal_status IN ('in_force','struck_down','repealed')),
    verification_status       TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source                    TEXT,
    notes                     TEXT,
    PRIMARY KEY (locality_id, effective_date)
);

CREATE TABLE state_jock_tax_rules (
    state_code                    TEXT    NOT NULL REFERENCES state_tax_profile(state_code),
    league                        TEXT    NOT NULL CHECK (league IN ('ALL','NFL','MLB','NHL','NBA')),
    tax_year                      INTEGER NOT NULL,
    sourcing_method               TEXT    NOT NULL
        CHECK (sourcing_method IN ('duty_day','games_played','flat_fee','general_nonresident','not_taxed')),  -- v2: not_taxed (DC)
    duty_day_definition           TEXT,
    employer_withholding_required INTEGER CHECK (employer_withholding_required IN (0,1)),
    composite_return_allowed      INTEGER CHECK (composite_return_allowed IN (0,1)),
    signing_bonus_sourcing        TEXT NOT NULL DEFAULT 'unknown'
        CHECK (signing_bonus_sourcing IN ('residence','duty_days','unknown',
                                          'residence_if_three_part_test',   -- v2: MA, IL, NY
                                          'partial_duty_days')),            -- v2: CA (conditional part allocated)
    retaliatory_provision         INTEGER CHECK (retaliatory_provision IN (0,1)),
    statute_citation              TEXT,
    verification_status           TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    notes                         TEXT,
    source_url                    TEXT,                                     -- v2
    PRIMARY KEY (state_code, league, tax_year)
);

CREATE TABLE teams (
    team_id            TEXT PRIMARY KEY,
    league             TEXT NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    team_name          TEXT NOT NULL,
    city               TEXT,
    country            TEXT NOT NULL DEFAULT 'US',
    stadium_state      TEXT REFERENCES state_tax_profile(state_code),
    stadium_locality   TEXT REFERENCES localities(locality_id),
    practice_state     TEXT REFERENCES state_tax_profile(state_code),
    practice_locality  TEXT REFERENCES localities(locality_id),
    spring_training_state TEXT REFERENCES state_tax_profile(state_code),   -- v2: MLB (FL or AZ)
    notes              TEXT                                                -- v2
);

CREATE TABLE players (
    player_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name        TEXT NOT NULL,
    league           TEXT NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    position         TEXT,
    residence_state  TEXT REFERENCES state_tax_profile(state_code),
    external_id      TEXT,
    UNIQUE (league, full_name, external_id)
);

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

CREATE TABLE contracts (
    contract_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id                 INTEGER NOT NULL REFERENCES players(player_id),
    team_id                   TEXT    NOT NULL REFERENCES teams(team_id),
    signed_date               TEXT,
    first_season              INTEGER NOT NULL,
    last_season               INTEGER NOT NULL,
    total_value               REAL    NOT NULL,
    aav                       REAL,
    total_guaranteed          REAL,
    residence_state_at_signing TEXT REFERENCES state_tax_profile(state_code),
    is_extension              INTEGER NOT NULL DEFAULT 0 CHECK (is_extension IN (0,1)),
    verification_status       TEXT NOT NULL DEFAULT 'provisional'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional')),
    source_primary            TEXT,
    source_secondary          TEXT,
    accessed_date             TEXT,
    notes                     TEXT,
    CHECK (last_season >= first_season),
    CHECK (verification_status <> 'verified'
           OR (source_primary IS NOT NULL AND source_secondary IS NOT NULL))
);
CREATE INDEX idx_contracts_player ON contracts (player_id);

CREATE TABLE contract_years (
    contract_id                 INTEGER NOT NULL REFERENCES contracts(contract_id) ON DELETE CASCADE,
    season                      INTEGER NOT NULL,
    base_salary                 REAL NOT NULL DEFAULT 0,
    signing_bonus_cash          REAL NOT NULL DEFAULT 0,
    signing_bonus_cap_proration REAL NOT NULL DEFAULT 0,
    roster_bonus                REAL NOT NULL DEFAULT 0,
    per_game_bonus              REAL NOT NULL DEFAULT 0,
    workout_bonus               REAL NOT NULL DEFAULT 0,
    incentives_ltbe             REAL NOT NULL DEFAULT 0,
    incentives_nltbe            REAL NOT NULL DEFAULT 0,
    guaranteed_cash             REAL NOT NULL DEFAULT 0,
    cap_hit                     REAL,
    is_void_year                INTEGER NOT NULL DEFAULT 0 CHECK (is_void_year IN (0,1)),
    notes                       TEXT,
    PRIMARY KEY (contract_id, season)
);

CREATE VIEW v_contract_year_cash AS
SELECT contract_id, season,
       base_salary + signing_bonus_cash + roster_bonus + per_game_bonus + workout_bonus
           AS cash_ex_incentives,
       incentives_ltbe, incentives_nltbe, is_void_year
FROM contract_years;

CREATE TABLE salary_cap (
    league      TEXT    NOT NULL CHECK (league IN ('NFL','MLB','NHL','NBA')),
    season      INTEGER NOT NULL,
    cap_type    TEXT    NOT NULL CHECK (cap_type IN ('hard_cap','luxury_tax_threshold')),
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

CREATE TABLE performance_metrics (
    player_id     INTEGER NOT NULL REFERENCES players(player_id),
    season        INTEGER NOT NULL,
    metric_name   TEXT    NOT NULL,
    metric_value  REAL,
    source        TEXT,
    PRIMARY KEY (player_id, season, metric_name)
);

CREATE VIEW v_federal_brackets AS
SELECT *, LEAD(lower_bound) OVER (
           PARTITION BY tax_year, filing_status ORDER BY bracket_order) AS upper_bound
FROM federal_brackets;

CREATE VIEW v_state_brackets AS
SELECT *, LEAD(lower_bound) OVER (
           PARTITION BY tax_year, state_code, filing_status ORDER BY bracket_order) AS upper_bound
FROM state_income_tax_brackets;

CREATE VIEW v_check_bracket_start AS
SELECT 'federal' AS tbl, tax_year, NULL AS state_code, filing_status
FROM federal_brackets GROUP BY tax_year, filing_status HAVING MIN(lower_bound) <> 0
UNION ALL
SELECT 'state', tax_year, state_code, filing_status
FROM state_income_tax_brackets GROUP BY tax_year, state_code, filing_status HAVING MIN(lower_bound) <> 0;

CREATE VIEW v_check_bracket_order AS
SELECT 'federal' AS tbl, tax_year, NULL AS state_code, filing_status, bracket_order
FROM v_federal_brackets WHERE upper_bound IS NOT NULL AND upper_bound <= lower_bound
UNION ALL
SELECT 'state', tax_year, state_code, filing_status, bracket_order
FROM v_state_brackets WHERE upper_bound IS NOT NULL AND upper_bound <= lower_bound;

CREATE VIEW v_check_state_coverage AS
SELECT p.state_code, 'taxes wages but no brackets' AS problem
FROM state_tax_profile p
WHERE p.taxes_wages = 1
  AND NOT EXISTS (SELECT 1 FROM state_income_tax_brackets b WHERE b.state_code = p.state_code)
UNION ALL
SELECT DISTINCT b.state_code, 'has brackets but taxes_wages = 0'
FROM state_income_tax_brackets b JOIN state_tax_profile p USING (state_code)
WHERE p.taxes_wages = 0;

-- ---------------------------------------------------------------------
-- 9. v2 (WEEK 4): DUTY DAYS AND RESIDENCY
-- ---------------------------------------------------------------------

-- League-level duty-day window (FTA uniform rule). Typical totals are defaults only;
-- the engine counts real days from duty_day_events when they exist.
CREATE TABLE league_duty_day_rules (
    league                  TEXT PRIMARY KEY CHECK (league IN ('NFL','MLB','NHL','NBA')),
    window_start            TEXT NOT NULL,
    window_end              TEXT NOT NULL,
    typical_total_duty_days INTEGER,
    tax_quirk               TEXT,
    source                  TEXT,
    verification_status     TEXT NOT NULL DEFAULT 'needs_check'
        CHECK (verification_status IN ('verified','needs_check','stale_2025','provisional'))
);

-- Residence is per player per tax year. MA (830 CMR 62.5A.2) counts a person as a resident
-- if domiciled there OR keeping a permanent abode there and spending >183 days.
CREATE TABLE player_residency (
    player_id        INTEGER NOT NULL REFERENCES players(player_id),
    tax_year         INTEGER NOT NULL,
    residence_state  TEXT REFERENCES state_tax_profile(state_code),
    residence_basis  TEXT NOT NULL DEFAULT 'domicile'
        CHECK (residence_basis IN ('domicile','statutory_resident','assumed')),
    source           TEXT,
    PRIMARY KEY (player_id, tax_year)
);

-- One row per player per calendar day in the duty-day window ("Duty Days" table on the Week 2 slide).
-- counts_in_state = 0 for travel days with no team event and injured days away from team facilities:
-- those days stay in the denominator but are not sourced to the state they happen in.
CREATE TABLE duty_day_events (
    player_id        INTEGER REFERENCES players(player_id),
    team_id          TEXT NOT NULL REFERENCES teams(team_id),
    event_date       TEXT NOT NULL,
    tax_year         INTEGER NOT NULL,
    event_type       TEXT NOT NULL CHECK (event_type IN
        ('game','practice','meeting','travel','injured_team_facility','injured_elsewhere',
         'offseason_service','promotional')),
    state_code       TEXT REFERENCES state_tax_profile(state_code),
    locality_id      TEXT REFERENCES localities(locality_id),
    counts_in_state  INTEGER NOT NULL CHECK (counts_in_state IN (0,1)),
    is_projected     INTEGER NOT NULL DEFAULT 0 CHECK (is_projected IN (0,1)),
    PRIMARY KEY (team_id, event_date, player_id)
);

-- Duty-day ratio per team/player, tax year and state.
CREATE VIEW v_duty_day_ratio AS
WITH tot AS (
    SELECT team_id, player_id, tax_year, COUNT(*) AS total_days
    FROM duty_day_events GROUP BY team_id, player_id, tax_year)
SELECT e.team_id, e.player_id, e.tax_year, e.state_code,
       SUM(e.counts_in_state) AS state_days, t.total_days,
       1.0 * SUM(e.counts_in_state) / t.total_days AS ratio
FROM duty_day_events e
JOIN tot t ON t.team_id = e.team_id AND t.tax_year = e.tax_year
          AND (t.player_id IS e.player_id)
GROUP BY e.team_id, e.player_id, e.tax_year, e.state_code;
