"""MCP server exposing the variance engine to an AI client (Claude Desktop,
Claude Code, or any MCP-compatible client).

Run:  python -m fpa_variance_mcp.server
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

from .sample_data import build
from .variance import DEFAULT_DB, FPAData, Thresholds

Level = Literal["division", "region", "consolidated"]

mcp = MCPServer(
    name="fpa-variance",
    instructions=(
        "Tools for monthly FP&A variance analysis over a multi-ERP actuals database. "
        "Always run variance_report before writing commentary, and never present a report "
        "as final: if status is BLOCKED, say what failed and stop; if it is DRAFT, list the "
        "review_items and ask the reviewer to confirm drivers before anything is distributed."
    ),
)

_data: FPAData | None = None


def data() -> FPAData:
    global _data
    if _data is None:
        path = Path(os.environ.get("FPA_DB_PATH") or DEFAULT_DB)
        if not path.exists():
            build(path)  # first run: create the synthetic dataset
        _data = FPAData(path)
    return _data


@mcp.tool()
def list_entities() -> dict:
    """List regions, divisions (with source ERP) and periods that have actuals."""
    return data().entities()


@mcp.tool()
def get_actuals(level: Level, period: str, name: str | None = None, ytd: bool = False) -> dict:
    """Actuals on the standard management P&L.

    level: division, region or consolidated. name: the division or region (omit for consolidated).
    period: YYYY-MM. ytd: true for year-to-date through that month.
    """
    return data().actuals(level, name, period, ytd)


@mcp.tool()
def get_budget(level: Level, period: str, name: str | None = None, ytd: bool = False) -> dict:
    """Budget on the standard management P&L. Same arguments as get_actuals."""
    return data().budget(level, name, period, ytd)


@mcp.tool()
def variance_report(
    level: Level,
    period: str,
    name: str | None = None,
    ytd: bool = False,
    threshold_pct: float = 0.05,
    threshold_abs: float = 25_000,
) -> dict:
    """Budget vs actual by line with a volume/rate revenue bridge, lines flagged for
    review, first-pass commentary, and the data checks for the period.

    A line is flagged when |variance| is at least threshold_pct of budget AND at least
    threshold_abs dollars. The report's status tells you whether it can go out.
    """
    return data().variance_report(level, name, period, ytd, Thresholds(threshold_pct, threshold_abs))


@mcp.tool()
def run_checks(period: str) -> dict:
    """Pre-distribution checks: unmapped GL accounts, mapped actuals tie to raw GL,
    and divisions/regions roll up to consolidated."""
    return data().run_checks(period)


@mcp.tool()
def log_review(report_id: str, reviewer: str, decision: Literal["approved", "changes_requested"], notes: str = "") -> dict:
    """Record a human sign-off (or a request for changes) against a report_id.
    Only call this when the reviewer has explicitly said so."""
    return data().log_review(report_id, reviewer, decision, notes)


@mcp.prompt()
def monthly_variance_commentary(period: str, level: str = "consolidated", name: str = "") -> str:
    """Draft the monthly variance commentary for a period."""
    target = f"{level} {name}".strip()
    return (
        f"Run variance_report for {target}, period {period}, and then the YTD view. "
        "Write management commentary: lead with EBITDA vs budget, then the two or three lines "
        "that explain it, using the revenue bridge to separate volume from rate. Keep it to "
        "short bullets with numbers. Mark anything you're inferring rather than reading from "
        "the data as [confirm with division lead]. End with the review_items and the status."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
