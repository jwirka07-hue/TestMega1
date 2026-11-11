"""
Market assumptions the owner doesn't have to know — Southeast US.
Every number carries its source. Update quarterly; add a market by adding a row.
Last updated: Nov 10, 2026.

HOW CAP RATES ARE BUILT
  1. Each market has a multifamily cap rate from a local, transaction-based report.
  2. Industrial and office = multifamily + a sector spread (national survey).
  3. Each sector then gets a class adjustment (A / B / C) by building age or owner override.
"""

LINCOLN = "Lincoln Institute / MCFE 50-State Property Tax Comparison Study (taxes paid 2025)"

MARKETS = {
    # ---------------- Georgia ----------------
    "Atlanta, GA": {
        "mf_cap": 0.0557, "mf_cap_source": "Matthews, Atlanta Multifamily Q3 2026 — metro average 5.57%",
        "tax_commercial": 0.0162, "tax_apartment": 0.0161,
        "tax_source": f"{LINCOLN}: Atlanta commercial 1.62%, apartment 1.61%",
        "mf_vacancy": 0.059, "mf_vacancy_source": "Matthews, Atlanta Q2 2026 — vacancy 5.9%",
    },
    "Athens, GA": {
        "mf_cap": 0.0582, "mf_cap_source": "ASSUMPTION — Atlanta average + 25 bps for a smaller market; replace with local comps",
        "tax_commercial": 0.01242, "tax_apartment": 0.01242,
        "tax_source": "Athens-Clarke 12.25 + Clarke Co. Schools 18.80 = 31.05 mills × 40% assessment = 1.24% of value",
    },
    # ---------------- North Carolina ----------------
    "Charlotte, NC": {
        "mf_cap": 0.0500, "mf_cap_source": "Northmarq, Charlotte Multifamily Q3 2025 — cap rates averaged ~5.0% in 2025",
        "tax_commercial": 0.0070, "tax_apartment": 0.0068,
        "tax_source": f"{LINCOLN}: Charlotte commercial 0.70%, apartment 0.68%. NC reassesses on a county "
                      "revaluation cycle, not at sale.",
    },
    "Raleigh-Durham, NC": {
        "mf_cap": 0.0530, "mf_cap_source": "Lee & Associates, Raleigh Multifamily Q2 2026 — cap rate 5.3%",
        "tax_commercial": 0.0084, "tax_apartment": 0.0084,
        "tax_source": f"{LINCOLN}: Raleigh commercial 0.84% (apartment rate assumed equal)",
    },
    # ---------------- Tennessee ----------------
    "Nashville, TN": {
        "mf_cap": 0.0550, "mf_cap_source": "Northmarq, Nashville Multifamily Q3 2025 — averages in the mid-5% range",
        "tax_commercial": 0.0108, "tax_apartment": 0.0111,
        "tax_source": f"{LINCOLN}: Nashville commercial 1.08%, apartment 1.11%",
    },
    "Memphis, TN": {
        "mf_cap": 0.0760, "mf_cap_source": "Berkadia 2025 Forecast, Memphis — 2024 average cap rate 7.6%",
        "tax_commercial": 0.0202, "tax_apartment": 0.0202,
        "tax_source": f"{LINCOLN}: Memphis commercial 2.02% (apartment rate assumed equal)",
    },
    # ---------------- Florida ----------------
    "Miami / South Florida, FL": {
        "mf_cap": 0.0638, "mf_cap_source": "Lee & Associates, South Florida Multifamily Q2 2026 — cap rate 6.38%",
        "tax_commercial": 0.0179, "tax_apartment": 0.0179,
        "tax_source": f"{LINCOLN}: Miami commercial 1.79% (apartment rate assumed equal)",
    },
    "Tampa, FL": {
        "mf_cap": 0.0550, "mf_cap_source": "Northmarq, Tampa Multifamily Q1 2025 — average cap rate 5.5%",
        "tax_commercial": 0.0187, "tax_apartment": 0.0187,
        "tax_source": f"{LINCOLN}: Tampa commercial 1.87% (apartment rate assumed equal)",
    },
    "Orlando, FL": {
        "mf_cap": 0.0525, "mf_cap_source": "Northmarq, Orlando Multifamily Q4 2025 — cap rates ~5.0%–5.5% (midpoint used)",
        "tax_commercial": 0.0178, "tax_apartment": 0.0178,
        "tax_source": "ASSUMPTION — average of Jacksonville, Miami and Tampa commercial rates "
                      f"({LINCOLN}); Orlando not in study",
    },
    "Jacksonville, FL": {
        "mf_cap": 0.0530, "mf_cap_source": "Berkadia 2024 Forecast, Jacksonville — 2024 average 5.3% "
                                           "(Dec 2025 Country Club Lakes sale also 5.3%)",
        "tax_commercial": 0.0168, "tax_apartment": 0.0165,
        "tax_source": f"{LINCOLN}: Jacksonville commercial 1.68%, apartment 1.65%",
    },
    # ---------------- South Carolina ----------------
    "Charleston, SC": {
        "mf_cap": 0.0540, "mf_cap_source": "Berkadia 2025 Forecast, Charleston — 2024 average cap rate 5.4%",
        "tax_commercial": 0.0193, "tax_apartment": 0.0177,
        "tax_source": f"{LINCOLN}: Charleston commercial 1.93%, apartment 1.77%",
    },
    "Greenville, SC": {
        "mf_cap": 0.0570, "mf_cap_source": "Berkadia 2025 Forecast, Greenville — 2024 average cap rate 5.7%",
        "tax_commercial": 0.0193, "tax_apartment": 0.0177,
        "tax_source": "ASSUMPTION — Charleston rates used as a South Carolina proxy; Greenville not in study",
    },
    # ---------------- Alabama ----------------
    "Birmingham, AL": {
        "mf_cap": 0.0560, "mf_cap_source": "Berkadia 2024 Forecast, Birmingham — 2024 average cap rate 5.6%",
        "tax_commercial": 0.0104, "tax_apartment": 0.0102,
        "tax_source": f"ASSUMPTION — Huntsville rates (commercial 1.04%, apartment 1.02%) used as an Alabama "
                      f"proxy ({LINCOLN}); Birmingham not in study",
    },
}

# ---------------- Sector spreads over multifamily ----------------
# Apartment Loan Store national cap rate table (Nov 10, 2026), Class B:
#   Multifamily suburban 5.18% | All industrial 6.20% | Office suburban 7.85%
SECTOR_SPREAD = {"multifamily": 0.0, "industrial": 0.0102, "office": 0.0267}
SECTOR_SOURCE = ("Sector spread over multifamily from Apartment Loan Store national table, Nov 2026 "
                 "(Class B: multifamily 5.18%, industrial 6.20% → +102 bps, suburban office 7.85% → +267 bps)")

# ---------------- Class spreads, relative to Class B ----------------
CLASS_SPREAD = {
    "multifamily": {"A": -0.0043, "B": 0.0, "C": 0.0047},  # ALS suburban MF 4.75 / 5.18 / 5.65
    "industrial":  {"A": -0.0095, "B": 0.0, "C": 0.0130},  # ALS all industrial 5.25 / 6.20 / 7.50
    "office":      {"A": -0.0080, "B": 0.0, "C": 0.0085},  # ALS metro office 6.20 / 7.00 / 7.85
}
CLASS_SOURCE = "Class spreads from Apartment Loan Store national table, Nov 2026"

# Year-built thresholds for class (owner can override in the app)
CLASS_YEARS = {"multifamily": (2010, 1990), "industrial": (2005, 1985), "office": (2000, 1980)}


def property_class(sector: str, year_built: int) -> str:
    a_year, b_year = CLASS_YEARS[sector]
    if year_built >= a_year:
        return "A"
    if year_built >= b_year:
        return "B"
    return "C"


def cap_rate(sector: str, market: str, pclass: str) -> float:
    return MARKETS[market]["mf_cap"] + SECTOR_SPREAD[sector] + CLASS_SPREAD[sector][pclass]


# ---------------- Standard underwriting assumptions ----------------
# What a typical buyer applies. Values marked RULE OF THUMB are industry conventions, not survey data —
# review them and replace with local figures where you have them.
STANDARD = {
    "multifamily": {
        "vacancy_floor": 0.05, "credit_loss": 0.02, "mgmt_fee": 0.03,
        "reserves": 300,                 # $/unit/yr (v1 spec)
        "note": "Mgmt 3% of EGI, reserves $300/unit, credit loss 2% (v1 spec); "
                "vacancy floor 5% unless a market figure is listed (RULE OF THUMB)",
    },
    "industrial": {
        "vacancy_floor": 0.05, "credit_loss": 0.01, "mgmt_fee_gross": 0.03,
        "reserves_psf": 0.15,            # $/SF/yr structural reserve
        "note": "RULE OF THUMB — vacancy/credit loss 5% + 1%, reserves $0.15/SF, mgmt 3% of EGI "
                "on gross leases (assumed reimbursed on NNN)",
    },
    "office": {
        "vacancy_floor": 0.10, "credit_loss": 0.01, "mgmt_fee_gross": 0.03,
        "reserves_psf": 1.75,            # $/SF/yr incl. tenant improvements & leasing commissions
        "note": "RULE OF THUMB — vacancy/credit loss 10% + 1%, reserves incl. TI/leasing $1.75/SF, "
                "mgmt 3% of EGI on gross leases (assumed reimbursed on NNN)",
    },
}
CAP_RANGE = 0.0025   # ±25 bps around the market cap rate for the value range
