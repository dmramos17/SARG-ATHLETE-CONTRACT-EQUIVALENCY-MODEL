"""Load reviewed contract snapshots without treating cap proration as cash."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/curated/demo_contracts_2026.json"


def load_contracts(path=DATA):
    records = json.loads(Path(path).read_text())
    seen = set()
    for row in records:
        if row["id"] in seen:
            raise ValueError("Duplicate contract snapshot.")
        seen.add(row["id"])
        cash = sum(row[key] for key in ("base_salary", "signing_bonus_cash", "other_cash"))
        if cash != row["annual_cash"] or any(row[key] < 0 for key in ("base_salary", "signing_bonus_cash", "other_cash")):
            raise ValueError("Contract cash does not reconcile.")
        if not row["sources"] or not row["accessed_date"]:
            raise ValueError("Contract needs source provenance.")
    return records


def sync_contracts(db=ROOT / "athlete_tax.db"):
    records = load_contracts()
    with sqlite3.connect(str(db)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS research_contract_snapshots "
                           "(snapshot_id TEXT PRIMARY KEY, player_name TEXT NOT NULL, "
                           "tax_year INTEGER NOT NULL, accessed_date TEXT NOT NULL, "
                           "verification_status TEXT NOT NULL, data_json TEXT NOT NULL)")
        connection.executemany("INSERT OR REPLACE INTO research_contract_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                               [(r["id"], r["player"], r["year"], r["accessed_date"], r["status"], json.dumps(r)) for r in records])
    return records


if __name__ == "__main__":
    print(f"Loaded {len(sync_contracts())} sourced contract snapshots.")
