"""Print a readable variance report without an AI client.

python scripts/demo.py consolidated 2026-10
python scripts/demo.py division 2026-10 Tampa
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpa_variance_mcp.sample_data import build  # noqa: E402
from fpa_variance_mcp.variance import DEFAULT_DB, FPAData, _fmt_money, _fmt_pct  # noqa: E402


def render(r: dict) -> str:
    sc = r["scope"]
    out = [f"### {sc['name']} | {sc['period']}{' YTD' if sc['ytd'] else ''}", "",
           f"**Status:** {r['status']}  ", f"**Report ID:** `{r['report_id']}`", "",
           "| Line | Actual | Budget | Var $ | Var % | Review |", "|---|---:|---:|---:|---:|:---:|"]
    for l in r["lines"]:
        out.append(f"| {l['label']} | {_fmt_money(l['actual'])} | {_fmt_money(l['budget'])} | "
                   f"{_fmt_money(l['variance'])} | {_fmt_pct(l['variance_pct'])} | {'⚑' if l['needs_review'] else ''} |")
    out += ["", "**Draft commentary**", ""] + [f"- {c}" for c in r["draft_commentary"]]
    out += ["", "**Data checks**", ""] + [
        f"- {'✅' if c['passed'] else '❌'} {c['name']}: {c['detail']}" for c in r["data_checks"]["checks"]]
    return "\n".join(out)


if __name__ == "__main__":
    level = sys.argv[1] if len(sys.argv) > 1 else "consolidated"
    period = sys.argv[2] if len(sys.argv) > 2 else "2026-10"
    name = sys.argv[3] if len(sys.argv) > 3 else None
    if not DEFAULT_DB.exists():
        build(DEFAULT_DB)
    print(render(FPAData().variance_report(level, name, period)))
