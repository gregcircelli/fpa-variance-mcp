"""Excel export: turns a variance report into a formatted workbook.

Variances, percentages, subtotals, review flags and the revenue bridge are
written as Excel formulas, so the file still works if someone changes a number
or a threshold. Actuals, budget and driver inputs are the only hardcoded
values, in blue.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .variance import COST_LINES, LABELS, STD_LINES, FPAData, Level, Thresholds

FONT = "Arial"
BLUE = "0000FF"
GREEN = "008000"
MONEY = '$#,##0;($#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
HOURS = '#,##0;(#,##0);"-"'
RATE = '$#,##0.00'

DEFAULT_EXPORT_DIR = Path(__file__).resolve().parents[2] / "exports"

_thin = Side(style="thin", color="BFBFBF")
_header_fill = PatternFill("solid", fgColor="1F3864")
_input_fill = PatternFill("solid", fgColor="FFFF00")
_subtotal_border = Border(top=_thin)


def _f(bold=False, color="000000", size=10, italic=False):
    return Font(name=FONT, bold=bold, color=color, size=size, italic=italic)


def _header_row(ws, row, labels, start_col=1):
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=label)
        c.font = _f(bold=True, color="FFFFFF")
        c.fill = _header_fill
        c.alignment = Alignment(horizontal="center" if i else "left", vertical="center", wrap_text=True)


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def export_report(
    data: FPAData,
    level: Level,
    name: str | None,
    period: str,
    ytd: bool = False,
    thresholds: Thresholds | None = None,
    output_dir: str | Path | None = None,
) -> dict:
    t = thresholds or Thresholds()
    report = data.variance_report(level, name, period, ytd, t)
    scope = report["scope"]

    wb = Workbook()
    _variance_sheet(wb.active, report, t)
    _bridge_sheet(wb.create_sheet("Revenue Bridge"), report, data.drivers(level, name, period, ytd))
    if level != "division":
        _division_sheet(wb.create_sheet("By Division"), data, level, name, period, ytd)
    _commentary_sheet(wb.create_sheet("Commentary"), report)
    _checks_sheet(wb.create_sheet("Checks"), report)

    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    out_dir = Path(output_dir or os.environ.get("FPA_EXPORT_DIR") or DEFAULT_EXPORT_DIR).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = scope["name"].replace(" ", "_")
    path = out_dir / f"variance_{slug}_{period}{'_YTD' if ytd else ''}.xlsx"
    wb.save(path)
    return {"path": str(path), "report_id": report["report_id"], "status": report["status"],
            "sheets": wb.sheetnames}


# ---------- sheets ----------

def _variance_sheet(ws, report, t: Thresholds):
    ws.title = "Variance"
    sc = report["scope"]
    ws["A1"] = f"{sc['name']} | {sc['period']}{' YTD' if sc['ytd'] else ''} | Budget vs Actual"
    ws["A1"].font = _f(bold=True, size=14)
    ws["A2"] = f"Status: {report['status']}"
    ws["A2"].font = _f(bold=True, color="C00000" if report["status"].startswith("BLOCKED") else "000000")
    ws["A3"] = f"Report ID {report['report_id']} | generated {datetime.now():%Y-%m-%d %H:%M} | synthetic data"
    ws["A3"].font = _f(italic=True, color="595959", size=9)

    # Thresholds as live inputs: change them and the flags update
    ws["A5"], ws["A6"] = "Review threshold: % of budget", "Review threshold: $"
    ws["B5"], ws["B6"] = t.pct, t.abs_dollars
    ws["B5"].number_format, ws["B6"].number_format = "0.0%", MONEY
    for r in (5, 6):
        ws[f"A{r}"].font = _f()
        ws[f"B{r}"].font = _f(color=BLUE)
        ws[f"B{r}"].fill = _input_fill
    ws["C5"] = "Yellow cells are inputs. Flags recalculate."
    ws["C5"].font = _f(italic=True, color="595959", size=9)

    hdr = 8
    _header_row(ws, hdr, ["Line", "Actual ($)", "Budget ($)", "Variance ($)", "Variance %", "Fav / Unfav", "Review"])
    by = {l["line"]: l for l in report["lines"]}
    rows = {}
    r = hdr + 1
    for line in STD_LINES + ["gross_margin", "ebitda"]:
        rows[line] = r
        ws.cell(row=r, column=1, value=LABELS[line]).font = _f(bold=line in ("gross_margin", "ebitda"))
        r += 1

    for line, r in rows.items():
        if line == "gross_margin":
            a = f"=B{rows['revenue']}-B{rows['direct_labor']}-B{rows['subcontractors']}"
            b = f"=C{rows['revenue']}-C{rows['direct_labor']}-C{rows['subcontractors']}"
            color = "000000"
        elif line == "ebitda":
            a = f"=B{rows['gross_margin']}-B{rows['indirect_labor']}-B{rows['other_opex']}"
            b = f"=C{rows['gross_margin']}-C{rows['indirect_labor']}-C{rows['other_opex']}"
            color = "000000"
        else:
            a, b, color = round(by[line]["actual"], 2), round(by[line]["budget"], 2), BLUE
        ws.cell(row=r, column=2, value=a)
        ws.cell(row=r, column=3, value=b)
        ws.cell(row=r, column=4, value=f"=B{r}-C{r}")
        ws.cell(row=r, column=5, value=f'=IF(C{r}=0,"",D{r}/C{r})')
        if line in COST_LINES:
            ws.cell(row=r, column=6, value=f'=IF(D{r}<=0,"Fav","Unfav")')
        else:
            ws.cell(row=r, column=6, value=f'=IF(D{r}>=0,"Fav","Unfav")')
        ws.cell(row=r, column=7,
                value=f'=IF(AND(ABS(D{r})>=$B$6,OR(C{r}=0,ABS(D{r}/C{r})>=$B$5)),"Review","")')
        bold = line in ("gross_margin", "ebitda")
        for col in range(2, 8):
            c = ws.cell(row=r, column=col)
            c.font = _f(bold=bold, color=color if col in (2, 3) else "000000")
            c.number_format = MONEY if col in (2, 3, 4) else PCT if col == 5 else "General"
            c.alignment = Alignment(horizontal="right" if col < 6 else "center")
            if bold:
                c.border = _subtotal_border
        if bold:
            ws.cell(row=r, column=1).border = _subtotal_border

    m = rows["ebitda"] + 2
    ws.cell(row=m, column=1, value="Gross margin %").font = _f()
    ws.cell(row=m + 1, column=1, value="EBITDA margin %").font = _f()
    for i, line in enumerate(["gross_margin", "ebitda"]):
        for col, letter in ((2, "B"), (3, "C")):
            c = ws.cell(row=m + i, column=col,
                        value=f'=IF({letter}{rows["revenue"]}=0,"",{letter}{rows[line]}/{letter}{rows["revenue"]})')
            c.number_format, c.font = PCT, _f()
    ws.cell(row=m + 3, column=1,
            value="Blue = pulled from the actuals/budget database. Black = formula.").font = _f(italic=True, color="595959", size=9)

    ws.freeze_panes = ws.cell(row=hdr + 1, column=2)
    _widths(ws, [30, 15, 15, 15, 12, 12, 10])
    ws.sheet_properties.tabColor = "1F3864"
    # Remember where revenue variance sits, for the bridge tie-out
    report["_rev_var_cell"] = f"Variance!$D${rows['revenue']}"


def _bridge_sheet(ws, report, drv):
    ws["A1"] = "Revenue bridge: volume vs rate"
    ws["A1"].font = _f(bold=True, size=14)
    if "budget" not in drv or "actual" not in drv:
        ws["A3"] = "No driver data for this scope."
        return
    _header_row(ws, 3, ["Driver", "Budget", "Actual"])
    # Unrounded rates, so the bridge ties to the penny
    ws["A4"], ws["B4"], ws["C4"] = "Billable hours", drv["budget"]["hours"], drv["actual"]["hours"]
    ws["A5"], ws["B5"], ws["C5"] = "Effective bill rate ($/hr)", drv["budget"]["rate"], drv["actual"]["rate"]
    for r, fmt in ((4, HOURS), (5, RATE)):
        ws[f"A{r}"].font = _f()
        for col in "BC":
            ws[f"{col}{r}"].font = _f(color=BLUE)
            ws[f"{col}{r}"].number_format = fmt

    _header_row(ws, 7, ["Effect", "Amount ($)", "How it's calculated"])
    rows = [
        ("Volume", "=(C4-B4)*B5", "Change in hours x budget rate"),
        ("Rate / mix", "=(C5-B5)*C4", "Change in rate x actual hours (includes division mix above division level)"),
        ("Total revenue variance", "=B8+B9", ""),
        ("Per Variance tab", f"={report['_rev_var_cell']}", "Link to the Variance tab"),
        ("Difference", "=B10-B11", "Should be 0"),
    ]
    for i, (label, formula, note) in enumerate(rows, start=8):
        ws[f"A{i}"], ws[f"B{i}"], ws[f"C{i}"] = label, formula, note
        ws[f"A{i}"].font = _f(bold=label.startswith("Total"))
        ws[f"B{i}"].font = _f(bold=label.startswith("Total"), color=GREEN if label.startswith("Per") else "000000")
        ws[f"B{i}"].number_format = MONEY
        ws[f"C{i}"].font = _f(italic=True, color="595959", size=9)
    ws["A10"].border = ws["B10"].border = _subtotal_border
    _widths(ws, [28, 16, 70])


def _division_sheet(ws, data: FPAData, level, name, period, ytd):
    ws["A1"] = "By division: revenue and EBITDA vs budget"
    ws["A1"].font = _f(bold=True, size=14)
    _header_row(ws, 3, ["Division", "Region", "Revenue actual ($)", "Revenue budget ($)", "Revenue var ($)",
                        "EBITDA actual ($)", "EBITDA budget ($)", "EBITDA var ($)", "EBITDA var %"])
    ents = data.entities()["divisions"]
    divs = data._divisions_for(level, name)
    r = 4
    for d in divs:
        act, bud = data.actuals("division", d, period, ytd), data.budget("division", d, period, ytd)
        vals = [d, ents[d]["region"], round(act["revenue"], 2), round(bud["revenue"], 2), f"=C{r}-D{r}",
                round(act["ebitda"], 2), round(bud["ebitda"], 2), f"=F{r}-G{r}", f'=IF(G{r}=0,"",H{r}/G{r})']
        for col, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=col, value=v)
            hard = col in (3, 4, 6, 7)
            c.font = _f(color=BLUE if hard else "000000")
            c.number_format = PCT if col == 9 else MONEY if col >= 3 else "General"
        r += 1
    last = r - 1
    ws.cell(row=r, column=1, value="Total").font = _f(bold=True)
    for col in range(3, 9):
        L = get_column_letter(col)
        c = ws.cell(row=r, column=col, value=f"=SUM({L}4:{L}{last})")
        c.font, c.number_format, c.border = _f(bold=True), MONEY, _subtotal_border
    c = ws.cell(row=r, column=9, value=f'=IF(G{r}=0,"",H{r}/G{r})')
    c.font, c.number_format, c.border = _f(bold=True), PCT, _subtotal_border
    ws.cell(row=r, column=1).border = _subtotal_border
    ws.cell(row=r + 2, column=1,
            value="EBITDA from divisions should tie to the Variance tab; check below should be 0.").font = _f(italic=True, color="595959", size=9)
    ws.cell(row=r + 3, column=1, value="Tie-out to Variance tab EBITDA actual").font = _f()
    c = ws.cell(row=r + 3, column=6, value=f"=F{r}-Variance!$B${_ebitda_row()}")
    c.number_format, c.font = MONEY, _f(color=GREEN)
    ws.freeze_panes = "B4"
    _widths(ws, [14, 12, 17, 17, 15, 17, 17, 15, 12])


def _ebitda_row() -> int:
    # Variance tab layout: header on row 8, then 7 lines; EBITDA is the last
    return 8 + len(STD_LINES) + 2


def _commentary_sheet(ws, report):
    ws["A1"] = "Draft commentary (first pass, needs review)"
    ws["A1"].font = _f(bold=True, size=14)
    r = 3
    for line in report["draft_commentary"]:
        ws.cell(row=r, column=1, value=f"• {line}").font = _f()
        ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Review items").font = _f(bold=True)
    for item in report["review_items"] or ["None"]:
        r += 1
        ws.cell(row=r, column=1, value=f"• {item}").font = _f()
        ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [110])


def _checks_sheet(ws, report):
    ws["A1"] = "Data checks"
    ws["A1"].font = _f(bold=True, size=14)
    ws["A2"] = "Nothing should be distributed until every check passes."
    ws["A2"].font = _f(italic=True, color="595959", size=9)
    _header_row(ws, 4, ["Check", "Result", "Detail"])
    r = 5
    for c in report["data_checks"]["checks"]:
        ws.cell(row=r, column=1, value=c["name"]).font = _f()
        res = ws.cell(row=r, column=2, value="Pass" if c["passed"] else "FAIL")
        res.font = _f(bold=True, color="008000" if c["passed"] else "C00000")
        res.alignment = Alignment(horizontal="center")
        d = ws.cell(row=r, column=3, value=c["detail"])
        d.font, d.alignment = _f(), Alignment(wrap_text=True, vertical="top")
        r += 1
    _widths(ws, [44, 10, 80])
