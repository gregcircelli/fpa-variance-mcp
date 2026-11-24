"""Variance engine: pulls mapped actuals and budget, computes variances, flags
what needs a human look, and drafts first-pass commentary.

The MCP server is a thin layer over this module, so the logic is testable on
its own.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Level = Literal["division", "region", "consolidated"]

STD_LINES = ["revenue", "direct_labor", "subcontractors", "indirect_labor", "other_opex"]
COST_LINES = {"direct_labor", "subcontractors", "indirect_labor", "other_opex"}
LABELS = {
    "revenue": "Revenue",
    "direct_labor": "Direct labor",
    "subcontractors": "Subcontractors",
    "indirect_labor": "Indirect labor",
    "other_opex": "Other opex",
    "gross_margin": "Gross margin",
    "ebitda": "EBITDA",
}

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "fpa.db"


@dataclass
class Thresholds:
    """A line is flagged for review when the variance clears both bars:
    |variance| >= pct of budget AND |variance| >= abs_dollars. Two bars keep
    small divisions from flagging on noise and big ones from hiding real misses."""

    pct: float = 0.05
    abs_dollars: float = 25_000.0


class FPAData:
    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"{self.db_path} not found. Run `python scripts/generate_data.py` first."
            )

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # ---------- entity helpers ----------

    def entities(self) -> dict:
        with self._con() as con:
            rows = con.execute("SELECT division, region, source_erp FROM divisions ORDER BY region, division").fetchall()
            periods = [r[0] for r in con.execute("SELECT DISTINCT period FROM gl_actuals ORDER BY period")]
        regions: dict[str, list[str]] = {}
        for r in rows:
            regions.setdefault(r["region"], []).append(r["division"])
        return {
            "regions": regions,
            "divisions": {r["division"]: {"region": r["region"], "source_erp": r["source_erp"]} for r in rows},
            "actual_periods": periods,
        }

    def _divisions_for(self, level: Level, name: str | None) -> list[str]:
        ents = self.entities()
        if level == "consolidated":
            return list(ents["divisions"])
        if level == "region":
            if name not in ents["regions"]:
                raise ValueError(f"Unknown region {name!r}. Options: {sorted(ents['regions'])}")
            return ents["regions"][name]
        if level == "division":
            if name not in ents["divisions"]:
                raise ValueError(f"Unknown division {name!r}. Options: {sorted(ents['divisions'])}")
            return [name]
        raise ValueError(f"level must be division, region or consolidated, got {level!r}")

    @staticmethod
    def _periods(period: str, ytd: bool) -> list[str]:
        year, month = period.split("-")
        if not ytd:
            return [period]
        return [f"{year}-{m:02d}" for m in range(1, int(month) + 1)]

    # ---------- pulls ----------

    def actuals(self, level: Level, name: str | None, period: str, ytd: bool = False) -> dict[str, float]:
        """Actuals mapped to standard lines. Unmapped accounts are excluded here
        and surfaced by run_checks()."""
        divs = self._divisions_for(level, name)
        pers = self._periods(period, ytd)
        q = f"""
            SELECT m.std_line, SUM(g.amount) AS amt
            FROM gl_actuals g
            JOIN account_map m ON m.source_erp = g.source_erp AND m.native_account = g.native_account
            WHERE g.division IN ({",".join("?" * len(divs))})
              AND g.period IN ({",".join("?" * len(pers))})
            GROUP BY m.std_line
        """
        with self._con() as con:
            rows = con.execute(q, divs + pers).fetchall()
        out = {line: 0.0 for line in STD_LINES}
        out.update({r["std_line"]: r["amt"] for r in rows})
        return _with_subtotals(out)

    def budget(self, level: Level, name: str | None, period: str, ytd: bool = False) -> dict[str, float]:
        divs = self._divisions_for(level, name)
        pers = self._periods(period, ytd)
        q = f"""
            SELECT std_line, SUM(amount) AS amt FROM budget
            WHERE division IN ({",".join("?" * len(divs))})
              AND period IN ({",".join("?" * len(pers))})
            GROUP BY std_line
        """
        with self._con() as con:
            rows = con.execute(q, divs + pers).fetchall()
        out = {line: 0.0 for line in STD_LINES}
        out.update({r["std_line"]: r["amt"] for r in rows})
        return _with_subtotals(out)

    def drivers(self, level: Level, name: str | None, period: str, ytd: bool = False) -> dict:
        """Billable hours and effective bill rate, budget vs actual."""
        divs = self._divisions_for(level, name)
        pers = self._periods(period, ytd)
        q = f"""
            SELECT scenario, SUM(billable_hours) AS hrs, SUM(billable_hours * bill_rate) AS rev
            FROM drivers
            WHERE division IN ({",".join("?" * len(divs))})
              AND period IN ({",".join("?" * len(pers))})
            GROUP BY scenario
        """
        with self._con() as con:
            rows = {r["scenario"]: r for r in con.execute(q, divs + pers).fetchall()}
        out = {}
        for s in ("budget", "actual"):
            if s in rows and rows[s]["hrs"]:
                out[s] = {"hours": rows[s]["hrs"], "rate": rows[s]["rev"] / rows[s]["hrs"]}
        return out

    # ---------- variance ----------

    def variance_report(
        self,
        level: Level,
        name: str | None,
        period: str,
        ytd: bool = False,
        thresholds: Thresholds | None = None,
    ) -> dict:
        t = thresholds or Thresholds()
        act = self.actuals(level, name, period, ytd)
        bud = self.budget(level, name, period, ytd)
        drv = self.drivers(level, name, period, ytd)

        lines = []
        for line in STD_LINES + ["gross_margin", "ebitda"]:
            a, b = act[line], bud[line]
            var = a - b
            # Favorable = more revenue/profit, or less cost
            fav_var = -var if line in COST_LINES else var
            pct = var / b if b else None
            flagged = abs(var) >= t.abs_dollars and (pct is None or abs(pct) >= t.pct)
            lines.append({
                "line": line,
                "label": LABELS[line],
                "actual": round(a, 2),
                "budget": round(b, 2),
                "variance": round(var, 2),
                "variance_pct": round(pct, 4) if pct is not None else None,
                "favorable": fav_var >= 0,
                "needs_review": flagged,
            })

        bridge = _revenue_bridge(drv)
        divs = self._divisions_for(level, name)
        checks = self.run_checks(period, divisions=divs if level != "consolidated" else None)
        flagged = [l for l in lines if l["needs_review"]]
        movers = self._movers(level, name, period, ytd) if level != "division" else []
        commentary = _draft_commentary(lines, bridge, act, bud, t, movers)

        report = {
            "scope": {"level": level, "name": name or "Consolidated", "period": period, "ytd": ytd},
            "thresholds": {"pct": t.pct, "abs_dollars": t.abs_dollars},
            "lines": lines,
            "revenue_bridge": bridge,
            "margins": {
                "gross_margin_pct": {"actual": _safe_div(act["gross_margin"], act["revenue"]),
                                     "budget": _safe_div(bud["gross_margin"], bud["revenue"])},
                "ebitda_pct": {"actual": _safe_div(act["ebitda"], act["revenue"]),
                               "budget": _safe_div(bud["ebitda"], bud["revenue"])},
            },
            "ebitda_movers": movers,
            "draft_commentary": commentary,
            "data_checks": checks,
        }
        report["report_id"] = _report_id(report["scope"], report["thresholds"])
        report["status"] = (
            "BLOCKED: data checks failed, fix before distributing"
            if not checks["all_passed"]
            else "DRAFT: needs review" if flagged
            else "DRAFT: no lines over threshold, light review"
        )
        report["review_items"] = [
            f"{l['label']}: {_fmt_money(l['variance'])} ({_fmt_pct(l['variance_pct'])}) vs budget"
            for l in flagged
        ] + [f"Data check failed: {c['name']}: {c['detail']}" for c in checks["checks"] if not c["passed"]]
        return report

    def _movers(self, level: Level, name: str | None, period: str, ytd: bool, top: int = 3) -> list[dict]:
        """Divisions driving the EBITDA variance, largest absolute first."""
        out = []
        for d in self._divisions_for(level, name):
            var = self.actuals("division", d, period, ytd)["ebitda"] - self.budget("division", d, period, ytd)["ebitda"]
            out.append({"division": d, "ebitda_variance": round(var, 2)})
        return sorted(out, key=lambda x: abs(x["ebitda_variance"]), reverse=True)[:top]

    # ---------- checks ----------

    def run_checks(self, period: str, divisions: list[str] | None = None) -> dict:
        """The checks page. If any of these fail, nothing should go out.

        divisions: limit the mapping checks to these divisions (the roll-up check
        always runs on the whole company)."""
        checks = []
        divs = divisions or list(self.entities()["divisions"])
        ph = ",".join("?" * len(divs))
        with self._con() as con:
            unmapped = con.execute(
                f"""
                SELECT g.division, g.source_erp, g.native_account, SUM(g.amount) AS amt
                FROM gl_actuals g
                LEFT JOIN account_map m ON m.source_erp = g.source_erp AND m.native_account = g.native_account
                WHERE g.period = ? AND m.std_line IS NULL AND g.division IN ({ph})
                GROUP BY 1, 2, 3
                """,
                [period] + divs,
            ).fetchall()
            raw_total = con.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM gl_actuals WHERE period = ? AND division IN ({ph})",
                [period] + divs,
            ).fetchone()[0]

        checks.append({
            "name": "All GL accounts mapped",
            "passed": not unmapped,
            "detail": "OK" if not unmapped else "; ".join(
                f"{r['division']} {r['source_erp']} acct {r['native_account']} ({_fmt_money(r['amt'])}) has no mapping"
                for r in unmapped
            ),
        })

        # Mapped + unmapped must equal the raw GL pull
        mapped_total = sum(
            self.actuals("division", d, period)[l] for d in divs for l in STD_LINES
        )
        unmapped_total = sum(r["amt"] for r in unmapped)
        diff = raw_total - mapped_total - unmapped_total
        checks.append({
            "name": "Mapped actuals tie to raw GL",
            "passed": abs(diff) < 0.01,
            "detail": f"difference {_fmt_money(diff)}",
        })

        # Divisions -> regions -> consolidated tie-out on EBITDA
        ents = self.entities()
        cons = self.actuals("consolidated", None, period)["ebitda"]
        regions = sum(self.actuals("region", r, period)["ebitda"] for r in ents["regions"])
        divisions = sum(self.actuals("division", d, period)["ebitda"] for d in ents["divisions"])
        checks.append({
            "name": "Divisions and regions roll up to consolidated",
            "passed": abs(cons - regions) < 0.01 and abs(cons - divisions) < 0.01,
            "detail": f"consolidated {_fmt_money(cons)}, sum of regions {_fmt_money(regions)}, "
                      f"sum of divisions {_fmt_money(divisions)}",
        })

        return {"period": period, "all_passed": all(c["passed"] for c in checks), "checks": checks}

    # ---------- review log ----------

    def log_review(self, report_id: str, reviewer: str, decision: str, notes: str = "") -> dict:
        decision = decision.lower()
        if decision not in {"approved", "changes_requested"}:
            raise ValueError("decision must be 'approved' or 'changes_requested'")
        with self._con() as con:
            con.execute(
                "INSERT INTO reviews (report_id, reviewer, decision, notes) VALUES (?,?,?,?)",
                (report_id, reviewer, decision, notes),
            )
            rows = con.execute(
                "SELECT reviewer, decision, notes, logged_at FROM reviews WHERE report_id = ? ORDER BY logged_at",
                (report_id,),
            ).fetchall()
        return {"report_id": report_id, "history": [dict(r) for r in rows]}


# ---------- helpers ----------

def _with_subtotals(d: dict[str, float]) -> dict[str, float]:
    d = dict(d)
    d["gross_margin"] = d["revenue"] - d["direct_labor"] - d["subcontractors"]
    d["ebitda"] = d["gross_margin"] - d["indirect_labor"] - d["other_opex"]
    return d


def _revenue_bridge(drv: dict) -> dict | None:
    """Split revenue variance into volume (hours at budget rate) and rate.
    Above division level the rate piece also picks up mix between divisions."""
    if "budget" not in drv or "actual" not in drv:
        return None
    bh, br = drv["budget"]["hours"], drv["budget"]["rate"]
    ah, ar = drv["actual"]["hours"], drv["actual"]["rate"]
    volume = (ah - bh) * br
    rate = (ar - br) * ah
    return {
        "budget_hours": round(bh), "actual_hours": round(ah),
        "budget_rate": round(br, 2), "actual_rate": round(ar, 2),
        "volume_effect": round(volume, 2), "rate_effect": round(rate, 2),
        "total": round(volume + rate, 2),
    }


def _draft_commentary(
    lines: list[dict], bridge: dict | None, act: dict, bud: dict, t: Thresholds, movers: list[dict]
) -> list[str]:
    """First-pass bullets. Deliberately plain: a person (or the LLM client, under
    review) adds the 'why' from talking to the business."""
    by = {l["line"]: l for l in lines}
    out = []
    e = by["ebitda"]
    out.append(
        f"EBITDA {_fmt_money(e['actual'])} vs budget {_fmt_money(e['budget'])}, "
        f"{_fmt_money(abs(e['variance']))} {'favorable' if e['favorable'] else 'unfavorable'} "
        f"({_fmt_pct(e['variance_pct'])}). Margin {_fmt_pct(_safe_div(act['ebitda'], act['revenue']))} "
        f"vs {_fmt_pct(_safe_div(bud['ebitda'], bud['revenue']))} budget."
    )
    if movers:
        out.append("Biggest EBITDA movers: " + ", ".join(
            f"{m['division']} {_fmt_money(m['ebitda_variance'])}" for m in movers) + ".")

    r = by["revenue"]
    if bridge and abs(r["variance"]) >= t.abs_dollars:
        parts = []
        if abs(bridge["volume_effect"]) >= 1:
            parts.append(f"volume {_fmt_money(bridge['volume_effect'])} "
                         f"({bridge['actual_hours']:,} hrs vs {bridge['budget_hours']:,} budget)")
        if abs(bridge["rate_effect"]) >= 1:
            parts.append(f"rate/mix {_fmt_money(bridge['rate_effect'])} "
                         f"(${bridge['actual_rate']:.2f}/hr vs ${bridge['budget_rate']:.2f})")
        out.append(f"Revenue {_fmt_money(r['variance'])} vs budget ({_fmt_pct(r['variance_pct'])}): "
                   + ", ".join(parts) + ".")

    for key in ["direct_labor", "subcontractors", "indirect_labor", "other_opex"]:
        l = by[key]
        if not l["needs_review"]:
            continue
        text = (f"{l['label']} {_fmt_money(abs(l['variance']))} "
                f"{'under' if l['variance'] < 0 else 'over'} budget ({_fmt_pct(l['variance_pct'])}), "
                f"{'favorable' if l['favorable'] else 'unfavorable'}.")
        a_pct, b_pct = _safe_div(act[key], act["revenue"]), _safe_div(bud[key], bud["revenue"])
        if key in {"direct_labor", "subcontractors"} and a_pct is not None and b_pct is not None:
            if abs(a_pct - b_pct) < 0.005:
                text += f" In line with volume ({_fmt_pct(a_pct)} of revenue vs {_fmt_pct(b_pct)} budget)."
            else:
                text += (f" {_fmt_pct(a_pct)} of revenue vs {_fmt_pct(b_pct)} budget, so not just volume."
                         " [Add driver from the business]")
        else:
            text += " [Add driver from the business]"
        out.append(text)

    if not any(l["needs_review"] for l in lines):
        out.append("No line over the review threshold.")
    return out


def _report_id(scope: dict, thresholds: dict) -> str:
    raw = json.dumps({"scope": scope, "thresholds": thresholds}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def _safe_div(a: float, b: float) -> float | None:
    return a / b if b else None


def _fmt_money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000:
        return f"{sign}${x / 1_000_000:.2f}M"
    if x >= 1_000:
        return f"{sign}${x / 1_000:.0f}K"
    return f"{sign}${x:,.0f}"


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"
