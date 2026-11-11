"""
Benchmark test: the spec's 120-unit Athens worked example.
If this fails, the engine is wrong. Run with: python -m pytest -q
"""
import pytest
from engine import OperatingInputs, TaxInputs, direct_cap, cap_rate_sensitivity

OP = OperatingInputs(
    units=120, avg_rent=1450, vacancy=0.06, concessions_bad_debt=0.02,
    other_income=75, opex_per_unit=5200, mgmt_fee=0.03, reserves_per_unit=300,
)
TAX = TaxInputs(current_tax_bill=180_000, assessment_ratio=0.40, millage=0.030)


def test_operating_statement():
    r = direct_cap(OP, TAX, 0.055)
    assert r["gpr"] == 2_088_000
    assert r["egi"] == pytest.approx(2_028_960)
    assert r["expenses_before_tax"] == pytest.approx(720_868.8)
    assert r["noi_before_tax"] == pytest.approx(1_308_091.2)


def test_broker_case():
    r = direct_cap(OP, TAX, 0.055, reassess=False)
    assert r["noi"] == pytest.approx(1_128_091, abs=1)
    assert r["value"] == pytest.approx(20_510_745, abs=5)  # spec rounds mgmt to $60,869 mid-calc; engine is unrounded


def test_adjusted_case():
    r = direct_cap(OP, TAX, 0.055, reassess=True)
    assert r["value"] == pytest.approx(19_523_746, abs=5)  # spec rounds mgmt to $60,869 mid-calc; engine is unrounded
    assert r["taxes"] == pytest.approx(234_285, abs=1)
    assert r["value_per_unit"] == pytest.approx(162_698, abs=1)
    # Internal consistency: NOI / cap must equal value
    assert r["noi"] / 0.055 == pytest.approx(r["value"])


def test_tax_flag_impact():
    broker = direct_cap(OP, TAX, 0.055, reassess=False)["value"]
    adjusted = direct_cap(OP, TAX, 0.055, reassess=True)["value"]
    assert broker - adjusted == pytest.approx(987_000, abs=1_000)
    assert (broker - adjusted) / broker == pytest.approx(0.048, abs=0.001)


def test_sensitivity_table():
    rows = cap_rate_sensitivity(OP, TAX, [0.0525, 0.055, 0.0575])
    for r, expected in zip(rows, [20_280_481, 19_523_746, 18_821_453]):
        assert r["value"] == pytest.approx(expected, abs=5)


# ---------------- Industrial / office ----------------
from engine import income_value, estimate_commercial
import market_data as md


def test_income_value_closed_form():
    r = income_value(gpr=1_000_000, vacancy=0.05, credit=0.01, other_income=0, landlord_opex=100_000,
                     mgmt_fee=0.03, reserves=15_000, tax_rate=0.015, tax_share=1.0, cap=0.065)
    assert r["noi"] / r["cap_rate"] == pytest.approx(r["value"])
    assert r["taxes"] == pytest.approx(0.015 * r["value"])


def test_nnn_beats_gross_on_same_rent():
    args = ("industrial", 100_000, 800_000, 0.10, 0, None, 0, "Atlanta, GA", 2000)
    nnn = estimate_commercial(*args[:5], "NNN", *args[6:])["mid"]["value"]
    gross = estimate_commercial(*args[:5], "Gross", *args[6:])["mid"]["value"]
    assert nnn > gross  # landlord bears taxes only on vacant space under NNN


def test_sector_cap_ordering():
    for mkt in md.MARKETS:
        assert md.cap_rate("multifamily", mkt, "B") < md.cap_rate("industrial", mkt, "B") < md.cap_rate("office", mkt, "B")


def test_downtime_deduction():
    base = estimate_commercial("office", 50_000, 1_300_000, 0.1, 0, "Gross", 450_000, "Nashville, TN", 1995)
    hit = estimate_commercial("office", 50_000, 1_300_000, 0.1, 0, "Gross", 450_000, "Nashville, TN", 1995,
                              rollover_rent=260_000, downtime_months=6, releasing_cost=200_000)
    assert base["mid"]["value"] - hit["mid"]["value"] == pytest.approx(130_000 + 200_000)


# ---------------- Single-family home ----------------
from datetime import date
import home


def test_identical_comps_give_their_price():
    subj = {"sf": 2000, "beds": 3, "baths": 2, "year_built": 2000}
    c = dict(price=400_000, sale_date=date(2026, 11, 1), sf=2000, beds=3, baths=2, year_built=2000, condition="Similar")
    r = home.estimate_home(subj, [dict(c), dict(c), dict(c)], today=date(2026, 11, 10))
    assert r["value"] == pytest.approx(400_000)


def test_smaller_comp_adjusts_up_and_better_comp_down():
    subj = {"sf": 2000, "beds": 3, "baths": 2, "year_built": 2000}
    base = dict(price=400_000, sale_date=date(2026, 11, 1), beds=3, baths=2, year_built=2000)
    comps = [dict(base, sf=1800, condition="Similar"), dict(base, sf=2000, condition="Better than mine"),
             dict(base, sf=2000, condition="Similar")]
    adj = home.adjust_comps(subj, comps, today=date(2026, 11, 10))
    assert adj[0]["adjusted"] > 400_000 and adj[1]["adjusted"] < 400_000
