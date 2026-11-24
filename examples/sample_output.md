# Sample output

Generated with `python scripts/demo.py` on the synthetic dataset. In practice the AI client calls the same tools and writes the narrative on top of this.

## October, consolidated: blocked by an unmapped account

### Consolidated | 2026-10

**Status:** BLOCKED: data checks failed, fix before distributing  
**Report ID:** `0d2ccf5aed`

| Line | Actual | Budget | Var $ | Var % | Review |
|---|---:|---:|---:|---:|:---:|
| Revenue | $8.42M | $8.46M | -$48K | -0.6% |  |
| Direct labor | $3.00M | $3.05M | -$51K | -1.7% |  |
| Subcontractors | $1.08M | $1.02M | $69K | 6.8% | ⚑ |
| Indirect labor | $1.38M | $1.44M | -$59K | -4.1% |  |
| Other opex | $927K | $931K | -$4K | -0.4% |  |
| Gross margin | $4.34M | $4.40M | -$66K | -1.5% |  |
| EBITDA | $2.03M | $2.03M | -$2K | -0.1% |  |

**Draft commentary**

- EBITDA $2.03M vs budget $2.03M, $2K unfavorable (-0.1%). Margin 24.1% vs 24.0% budget.
- Biggest EBITDA movers: Houston -$101K, Dallas $89K, Tampa -$66K.
- Revenue -$48K vs budget (-0.6%): volume -$120K (53,824 hrs vs 54,600 budget), rate/mix $72K ($156.35/hr vs $155.00).
- Subcontractors $69K over budget (6.8%), unfavorable. 12.9% of revenue vs 12.0% budget, so not just volume. [Add driver from the business]

**Data checks**

- ❌ All GL accounts mapped: Charlotte erp_c acct 69250 ($18K) has no mapping
- ✅ Mapped actuals tie to raw GL: difference $0
- ✅ Divisions and regions roll up to consolidated: consolidated $2.03M, sum of regions $2.03M, sum of divisions $2.03M

## October, Houston: volume miss

### Houston | 2026-10

**Status:** DRAFT: needs review  
**Report ID:** `f383437eff`

| Line | Actual | Budget | Var $ | Var % | Review |
|---|---:|---:|---:|---:|:---:|
| Revenue | $1.42M | $1.63M | -$211K | -13.0% | ⚑ |
| Direct labor | $505K | $586K | -$81K | -13.8% | ⚑ |
| Subcontractors | $168K | $195K | -$27K | -13.9% | ⚑ |
| Indirect labor | $275K | $277K | -$1K | -0.5% |  |
| Other opex | $178K | $179K | -$590 | -0.3% |  |
| Gross margin | $744K | $846K | -$103K | -12.1% | ⚑ |
| EBITDA | $290K | $391K | -$101K | -25.8% | ⚑ |

**Draft commentary**

- EBITDA $290K vs budget $391K, $101K unfavorable (-25.8%). Margin 20.5% vs 24.0% budget.
- Revenue -$211K vs budget (-13.0%): volume -$202K (9,197 hrs vs 10,500 budget), rate/mix -$9K ($154.04/hr vs $155.00).
- Direct labor $81K under budget (-13.8%), favorable. In line with volume (35.6% of revenue vs 36.0% budget).
- Subcontractors $27K under budget (-13.9%), favorable. In line with volume (11.9% of revenue vs 12.0% budget).

**Data checks**

- ✅ All GL accounts mapped: OK
- ✅ Mapped actuals tie to raw GL: difference $0
- ✅ Divisions and regions roll up to consolidated: consolidated $2.03M, sum of regions $2.03M, sum of divisions $2.03M

## October, Tampa: subcontractor overrun

### Tampa | 2026-10

**Status:** DRAFT: needs review  
**Report ID:** `6b417764dc`

| Line | Actual | Budget | Var $ | Var % | Review |
|---|---:|---:|---:|---:|:---:|
| Revenue | $1.08M | $1.07M | $16K | 1.6% |  |
| Direct labor | $388K | $384K | $4K | 1.1% |  |
| Subcontractors | $206K | $128K | $78K | 60.8% | ⚑ |
| Indirect labor | $177K | $181K | -$5K | -2.5% |  |
| Other opex | $122K | $117K | $4K | 3.8% |  |
| Gross margin | $489K | $554K | -$66K | -11.8% | ⚑ |
| EBITDA | $190K | $256K | -$66K | -25.6% | ⚑ |

**Draft commentary**

- EBITDA $190K vs budget $256K, $66K unfavorable (-25.6%). Margin 17.6% vs 24.0% budget.
- Subcontractors $78K over budget (60.8%), unfavorable. 19.0% of revenue vs 12.0% budget, so not just volume. [Add driver from the business]

**Data checks**

- ✅ All GL accounts mapped: OK
- ✅ Mapped actuals tie to raw GL: difference $0
- ✅ Divisions and regions roll up to consolidated: consolidated $2.03M, sum of regions $2.03M, sum of divisions $2.03M
