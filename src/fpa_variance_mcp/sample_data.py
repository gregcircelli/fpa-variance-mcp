"""Generate a synthetic FP&A dataset in SQLite.

Everything here is made up. The shape mirrors a typical multi-ERP services
business: divisions roll up to regions, each division books actuals in its own
ERP with its own chart of accounts, and a mapping table translates native
accounts to a standard management P&L.

Run:  python scripts/generate_data.py   -> data/fpa.db
(The server also builds it automatically on first run if it is missing.)
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

SEED = 42
YEAR = 2026
ACTUALS_THROUGH = 10  # Jan-Oct actuals, full-year budget

# division, region, source ERP, budgeted billable hours / month, budget bill rate
DIVISIONS = [
    ("Austin", "Central", "erp_a", 9_000, 165.0),
    ("Dallas", "Central", "erp_a", 11_000, 160.0),
    ("Houston", "Central", "erp_b", 10_000, 155.0),
    ("Atlanta", "Southeast", "erp_b", 8_500, 150.0),
    ("Tampa", "Southeast", "erp_c", 7_000, 145.0),
    ("Charlotte", "Southeast", "erp_c", 6_500, 150.0),
]

# Standard management P&L lines
STD_LINES = ["revenue", "direct_labor", "subcontractors", "indirect_labor", "other_opex"]

# Each ERP names things differently. (native account, standard line)
ACCOUNT_MAP = {
    "erp_a": [("4000-Labor Revenue", "revenue"), ("5000-Direct Labor", "direct_labor"),
              ("5200-Subconsultants", "subcontractors"), ("6000-Indirect Labor", "indirect_labor"),
              ("6500-Office & Other", "other_opex")],
    "erp_b": [("REV-SVC", "revenue"), ("COS-LAB", "direct_labor"), ("COS-SUB", "subcontractors"),
              ("OH-LAB", "indirect_labor"), ("OH-GEN", "other_opex")],
    "erp_c": [("41100", "revenue"), ("51100", "direct_labor"), ("51500", "subcontractors"),
              ("61100", "indirect_labor"), ("69000", "other_opex")],
}

# Seasonality on hours (holidays, summer PTO)
SEASONALITY = [0.95, 0.97, 1.03, 1.02, 1.04, 0.98, 0.94, 1.02, 1.01, 1.05, 0.98, 0.91]

# Cost assumptions as % of revenue (budget)
DIRECT_LABOR_PCT = 0.36
SUB_PCT = 0.12
INDIRECT_PCT = 0.17
OPEX_PCT = 0.11

# Planted stories for the October actuals, so the variance report has something to say
OCT_STORIES = {
    "Houston": {"hours": 0.86},              # volume miss: project start slipped
    "Atlanta": {"rate": 1.06},               # rate upside: new rate card
    "Tampa": {"sub_pct": 0.19},              # subcontractor overrun
    "Dallas": {"indirect": 0.85},            # indirect labor favorable: open reqs
}


def build(db_path: Path) -> None:
    rng = random.Random(SEED)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE divisions (division TEXT PRIMARY KEY, region TEXT, source_erp TEXT);
        CREATE TABLE account_map (source_erp TEXT, native_account TEXT, std_line TEXT,
                                  PRIMARY KEY (source_erp, native_account));
        CREATE TABLE drivers (scenario TEXT, period TEXT, division TEXT,
                              billable_hours REAL, bill_rate REAL,
                              PRIMARY KEY (scenario, period, division));
        CREATE TABLE budget (period TEXT, division TEXT, std_line TEXT, amount REAL,
                             PRIMARY KEY (period, division, std_line));
        CREATE TABLE gl_actuals (period TEXT, division TEXT, source_erp TEXT,
                                 native_account TEXT, amount REAL);
        CREATE TABLE reviews (report_id TEXT, reviewer TEXT, decision TEXT, notes TEXT,
                              logged_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """
    )

    for div, region, erp, _, _ in DIVISIONS:
        cur.execute("INSERT INTO divisions VALUES (?,?,?)", (div, region, erp))
    for erp, rows in ACCOUNT_MAP.items():
        cur.executemany("INSERT INTO account_map VALUES (?,?,?)", [(erp, a, l) for a, l in rows])

    native = {erp: {line: acct for acct, line in rows} for erp, rows in ACCOUNT_MAP.items()}

    for div, _, erp, base_hours, base_rate in DIVISIONS:
        for m in range(1, 13):
            period = f"{YEAR}-{m:02d}"
            hours = round(base_hours * SEASONALITY[m - 1])
            rate = base_rate
            rev = hours * rate
            cur.execute("INSERT INTO drivers VALUES ('budget',?,?,?,?)", (period, div, hours, rate))
            bud = {
                "revenue": rev,
                "direct_labor": rev * DIRECT_LABOR_PCT,
                "subcontractors": rev * SUB_PCT,
                "indirect_labor": rev * INDIRECT_PCT,
                "other_opex": rev * OPEX_PCT,
            }
            for line, amt in bud.items():
                cur.execute("INSERT INTO budget VALUES (?,?,?,?)", (period, div, line, round(amt, 2)))

            if m > ACTUALS_THROUGH:
                continue

            # Actuals: budget plus normal noise, plus planted October stories
            story = OCT_STORIES.get(div, {}) if m == ACTUALS_THROUGH else {}
            a_hours = round(hours * rng.uniform(0.97, 1.03) * story.get("hours", 1.0))
            a_rate = round(rate * rng.uniform(0.99, 1.01) * story.get("rate", 1.0), 2)
            a_rev = a_hours * a_rate
            # Direct labor follows hours (cost per hour roughly fixed), not revenue
            dl = bud["direct_labor"] / hours * a_hours * rng.uniform(0.98, 1.02)
            subs = a_rev * story.get("sub_pct", SUB_PCT * rng.uniform(0.92, 1.08))
            indirect = bud["indirect_labor"] * rng.uniform(0.97, 1.03) * story.get("indirect", 1.0)
            opex = bud["other_opex"] * rng.uniform(0.95, 1.05)
            cur.execute("INSERT INTO drivers VALUES ('actual',?,?,?,?)", (period, div, a_hours, a_rate))

            act = {"revenue": a_rev, "direct_labor": dl, "subcontractors": subs,
                   "indirect_labor": indirect, "other_opex": opex}
            for line, amt in act.items():
                cur.execute("INSERT INTO gl_actuals VALUES (?,?,?,?,?)",
                            (period, div, erp, native[erp][line], round(amt, 2)))

    # A new account shows up in one ERP in October with no mapping yet.
    # This is the classic reason a dashboard and a board deck stop tying out.
    cur.execute("INSERT INTO gl_actuals VALUES (?,?,?,?,?)",
                (f"{YEAR}-{ACTUALS_THROUGH:02d}", "Charlotte", "erp_c", "69250", 18_400.00))

    con.commit()
    con.close()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "data" / "fpa.db"
    build(out)
    print(f"Wrote {out}")
