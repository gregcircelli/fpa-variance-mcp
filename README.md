# fpa-variance-mcp

An MCP server that lets an AI assistant pull actuals and budget from a multi-ERP finance database and draft the first pass of monthly variance analysis at the division, region or consolidated level. It also runs the data checks first and won't call anything final without a human sign-off.

This is a clean-room rebuild of a tool I built in my FP&A role against our planning system (OneStream), where actuals from several ERPs are consolidated and divisions roll up into regions. That version saved me 5–10 hours a week on monthly reporting. Everything here (code, data, chart of accounts) is new and synthetic. No employer code or data is included.

## The problem

Month-end variance work is mostly mechanical: pull actuals, line them up against budget, find what moved, and write it up for each division, each region and the consolidated view. The slow part isn't the math. It's the pulls and the first draft of the commentary, repeated across every entity.

There's also a trust problem. If one ERP books to a new account that hasn't been mapped, the dashboard, the management package and the board deck stop tying out, and you find out when someone asks why two numbers don't match.

## What it does

- **Pulls on a standard P&L.** Each division books in its own ERP with its own account names. A mapping table translates them to one management P&L (revenue, direct labor, subs, indirect labor, other opex, gross margin, EBITDA).
- **Variance by line**, month or YTD, at any level, with the right sign convention (lower cost = favorable).
- **Revenue bridge.** Splits the revenue variance into volume (hours at budget rate) and rate. Above division level the rate piece includes mix.
- **Flags what needs a look.** A line is flagged when the variance clears both a % and a $ threshold, so small divisions don't flag on noise and big ones can't hide a real miss.
- **Drafts commentary.** Plain first-pass bullets with the numbers, the biggest movers, and whether a cost variance just tracks volume or is something else. Anything it can't know (the "why") is left as a placeholder for the business to fill in.
- **Checks before anything goes out.** Every report runs a checks page: all GL accounts mapped, mapped actuals tie to the raw GL, divisions and regions roll up to consolidated. If a check fails, the report status is `BLOCKED`.
- **Review gate.** Reports are always `DRAFT` until a reviewer signs off with `log_review`, which records who approved what against a report ID.
- **Excel export.** `export_to_excel` writes the report to a formatted workbook: variances, subtotals, margins and review flags are live formulas, the review thresholds are editable inputs, the revenue bridge ties back to the variance tab, and region/consolidated exports add a by-division tab that ties to the total. A blocked report says so on the first tab.

The AI client does the writing on top of the tool output. The tools do the numbers, so the numbers come from the data and not from the model.

## Tools

| Tool | What it does |
|---|---|
| `list_entities` | Regions, divisions, source ERP, periods with actuals |
| `get_actuals` / `get_budget` | Standard P&L for a division, region or consolidated, month or YTD |
| `variance_report` | Variances, revenue bridge, flags, draft commentary, checks, status |
| `run_checks` | The checks page on its own |
| `export_to_excel` | Same report as a formatted .xlsx (Variance, Revenue Bridge, By Division, Commentary, Checks) |
| `log_review` | Record an approval or a request for changes against a report |

There's also a `monthly_variance_commentary` prompt that tells the client how to write the commentary from the report.

## Sample data

`sample_data.py` builds a SQLite database for a made-up ~$100M services business: six divisions in two regions, on three ERPs with different charts of accounts, a full-year 2026 budget, and actuals through October. October has a few planted stories so there's something to find:

- Houston: a project start slipped, so hours and revenue came in short (volume miss)
- Atlanta: a new rate card, so bill rate is up (rate upside)
- Tampa: subcontractor spend well over budget
- Dallas: indirect labor under budget from open reqs
- Charlotte: a new GL account in one ERP with no mapping yet, which blocks the consolidated report

See [`examples/sample_output.md`](examples/sample_output.md) for what the reports look like.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/fpa-variance-mcp.git
cd fpa-variance-mcp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python scripts/generate_data.py  # builds data/fpa.db (the server also does this on first run)
python scripts/demo.py division 2026-10 Tampa
pytest
```

### Connect it to Claude Desktop

Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config), using the full path to the Python in your virtual environment:

```json
{
  "mcpServers": {
    "fpa-variance": {
      "command": "/full/path/to/fpa-variance-mcp/.venv/bin/python",
      "args": ["-m", "fpa_variance_mcp.server"]
    }
  }
}
```

Restart Claude Desktop, then ask something like "Write the October variance commentary for the Southeast region", "Why is consolidated EBITDA flat when Houston missed?" or "Export the Southeast October report to Excel."

Exports go to the repo's `exports/` folder (git-ignored) unless you pass `output_dir` or set `FPA_EXPORT_DIR`.

With Claude Code: `claude mcp add fpa-variance -- /full/path/to/.venv/bin/python -m fpa_variance_mcp.server`

## Project layout

```
src/fpa_variance_mcp/
  variance.py      # the engine: pulls, variances, bridge, flags, commentary, checks, review log
  export.py        # Excel export with live formulas
  server.py        # MCP tools over the engine
  sample_data.py   # synthetic multi-ERP dataset
scripts/           # generate_data.py, demo.py
tests/             # pytest
examples/          # sample output
```

## What I'd add next

- A forecast scenario next to budget (latest estimate vs budget vs prior year)
- Pulling the "why" from project-level data (which projects drove the hours miss)
- Writing the approved commentary straight into the management package template
- A mid-month flash estimate from partial-month hours
