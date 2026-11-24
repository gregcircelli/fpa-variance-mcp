import sqlite3

import pytest

from fpa_variance_mcp import FPAData, Thresholds
from fpa_variance_mcp.sample_data import build


@pytest.fixture()
def data(tmp_path):
    db = tmp_path / "fpa.db"
    build(db)
    return FPAData(db)


def test_rollup_ties(data):
    checks = data.run_checks("2026-09")
    assert checks["all_passed"], checks


def test_unmapped_account_blocks_report(data):
    report = data.variance_report("consolidated", None, "2026-10")
    assert report["status"].startswith("BLOCKED")
    assert any("69250" in item for item in report["review_items"])


def test_unmapped_account_only_blocks_its_own_division(data):
    assert data.variance_report("division", "Charlotte", "2026-10")["status"].startswith("BLOCKED")
    assert not data.variance_report("division", "Houston", "2026-10")["status"].startswith("BLOCKED")


def test_mapping_fix_unblocks(data):
    with sqlite3.connect(data.db_path) as con:
        con.execute("INSERT INTO account_map VALUES ('erp_c', '69250', 'other_opex')")
    assert data.run_checks("2026-10")["all_passed"]


def test_revenue_bridge_sums_to_variance(data):
    r = data.variance_report("division", "Houston", "2026-10")
    rev = next(l for l in r["lines"] if l["line"] == "revenue")
    assert r["revenue_bridge"]["total"] == pytest.approx(rev["variance"], abs=1)
    # Houston's planted story is a volume miss
    assert r["revenue_bridge"]["volume_effect"] < -100_000


def test_cost_sign_convention(data):
    r = data.variance_report("division", "Tampa", "2026-10")
    subs = next(l for l in r["lines"] if l["line"] == "subcontractors")
    assert subs["variance"] > 0 and not subs["favorable"]
    assert subs["needs_review"]


def test_thresholds_control_flags(data):
    loose = data.variance_report("division", "Austin", "2026-10", thresholds=Thresholds(0.5, 1e9))
    assert not any(l["needs_review"] for l in loose["lines"])


def test_ytd_is_sum_of_months(data):
    ytd = data.actuals("consolidated", None, "2026-03", ytd=True)["ebitda"]
    months = sum(data.actuals("consolidated", None, f"2026-0{m}")["ebitda"] for m in (1, 2, 3))
    assert ytd == pytest.approx(months)


def test_review_log(data):
    rid = data.variance_report("division", "Houston", "2026-10")["report_id"]
    out = data.log_review(rid, "Greg", "approved", "Houston start date slipped to Nov")
    assert out["history"][-1]["decision"] == "approved"
    with pytest.raises(ValueError):
        data.log_review(rid, "Greg", "maybe")


def test_bad_entity_raises(data):
    with pytest.raises(ValueError):
        data.actuals("division", "Boise", "2026-10")
