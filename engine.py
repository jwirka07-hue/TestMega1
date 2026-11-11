"""
CRE Valuation Engine — v1, Step 1: direct capitalization.

Design rule from the spec: the AI reads and writes; this module does the math.
Every number in the memo must trace back to a function in this file.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass
class OperatingInputs:
    units: int
    avg_rent: float                 # $/unit/month, in-place
    vacancy: float                  # % of GPR
    concessions_bad_debt: float     # % of GPR
    other_income: float             # $/unit/month
    opex_per_unit: float            # $/unit/year, EXCLUDING taxes, mgmt, reserves
    mgmt_fee: float                 # % of EGI
    reserves_per_unit: float        # $/unit/year


@dataclass
class TaxInputs:
    current_tax_bill: float         # seller's in-place bill (broker case)
    assessment_ratio: float = 0.40  # Georgia assesses at 40% of FMV
    millage: float = 0.030          # 30 mills = $30 per $1,000 of assessed value

    @property
    def effective_rate(self) -> float:
        """Tax as a % of market value."""
        return self.assessment_ratio * self.millage


def operating_statement(op: OperatingInputs) -> dict:
    """Revenue and expenses down to NOI before property taxes."""
    gpr = op.units * op.avg_rent * 12
    vacancy = gpr * op.vacancy
    concessions = gpr * op.concessions_bad_debt
    other = op.units * op.other_income * 12
    egi = gpr - vacancy - concessions + other

    opex = op.units * op.opex_per_unit
    mgmt = egi * op.mgmt_fee
    reserves = op.units * op.reserves_per_unit
    total_exp = opex + mgmt + reserves

    return {
        "gpr": gpr,
        "vacancy": -vacancy,
        "concessions_bad_debt": -concessions,
        "other_income": other,
        "egi": egi,
        "opex": opex,
        "management": mgmt,
        "reserves": reserves,
        "expenses_before_tax": total_exp,
        "noi_before_tax": egi - total_exp,
    }


def direct_cap(op: OperatingInputs, tax: TaxInputs, cap_rate: float,
               reassess: bool = True) -> dict:
    """
    Direct cap value.

    reassess=False -> broker case: uses the seller's current tax bill.
    reassess=True  -> adjusted case: taxes reset to the purchase price.
        Taxes depend on value and value depends on taxes, so solve:
            V = (NOI_pre - t*V) / c   ->   V = NOI_pre / (c + t)
        Because taxes are linear in value this closed form is exact;
        no iteration is needed.
    """
    stmt = operating_statement(op)
    noi_pre = stmt["noi_before_tax"]

    if reassess:
        value = noi_pre / (cap_rate + tax.effective_rate)
        taxes = tax.effective_rate * value
    else:
        taxes = tax.current_tax_bill
        value = (noi_pre - taxes) / cap_rate

    noi = noi_pre - taxes
    return {
        **stmt,
        "taxes": taxes,
        "noi": noi,
        "cap_rate": cap_rate,
        "value": value,
        "value_per_unit": value / op.units,
        "case": "adjusted (taxes reassessed)" if reassess else "broker (in-place taxes)",
    }


def cap_rate_sensitivity(op: OperatingInputs, tax: TaxInputs,
                         cap_rates: list[float], reassess: bool = True) -> list[dict]:
    rows = []
    for c in cap_rates:
        r = direct_cap(op, tax, c, reassess)
        rows.append({"cap_rate": c, "value": r["value"], "per_unit": r["value_per_unit"]})
    return rows


def _finish(r_mid, r_low, r_high, units_or_sf, deductions):
    """Subtract one-time items (repairs, re-leasing) dollar for dollar; recompute per-unit."""
    for r in (r_mid, r_low, r_high):
        r["value_before_deductions"] = r["value"]
        r["value"] = r["value"] - deductions
        r["value_per_unit"] = r["value"] / units_or_sf


def income_value(gpr, vacancy, credit, other_income, landlord_opex, mgmt_fee,
                 reserves, tax_rate, tax_share, cap):
    """
    General direct-cap engine for any income property.
    Landlord pays property tax at tax_rate x value x tax_share
    (tax_share = 1 for gross leases; = vacancy for NNN, where tenants reimburse occupied space).
    Solved in closed form:  V = NOI_before_tax / (cap + tax_rate x tax_share)
    """
    vac = gpr * vacancy
    cred = gpr * credit
    egi = gpr - vac - cred + other_income
    mgmt = egi * mgmt_fee
    exp = landlord_opex + mgmt + reserves
    noi_pre = egi - exp
    eff_tax = tax_rate * tax_share
    value = noi_pre / (cap + eff_tax)
    taxes = eff_tax * value
    return {
        "gpr": gpr, "vacancy": -vac, "concessions_bad_debt": -cred, "other_income": other_income,
        "egi": egi, "opex": landlord_opex, "management": mgmt, "reserves": reserves,
        "expenses_before_tax": exp, "noi_before_tax": noi_pre, "taxes": taxes,
        "noi": noi_pre - taxes, "cap_rate": cap, "value": value,
    }


def _tax_rate(market_row, kind, override, notes):
    if override:
        notes.append(f"Your property tax rate ({override:.2%} of value) used instead of the market default.")
        return override
    return market_row[kind]


def estimate_value(units: int, gpr_annual: float, physical_vacancy: float,
                   other_income_monthly: float, opex_annual: float,
                   market: str, year_built: int,
                   *,  # ---- optional "improve accuracy" inputs ----
                   tax_rate_override: float | None = None,     # tax bill / appraised value
                   collected_rent_annual: float | None = None,
                   concessions_pct: float = 0.0,
                   utility_reimb_monthly: float = 0.0,
                   insurance_increase: float = 0.0,
                   capex_needed: float = 0.0,
                   property_type: str = "Conventional",
                   class_override: str | None = None) -> dict:
    """Apartments: what a buyer would likely pay."""
    import market_data as md

    m = md.MARKETS[market]
    std = md.STANDARD["multifamily"]
    notes = []
    pclass = class_override or md.property_class("multifamily", year_built)
    cap = md.cap_rate("multifamily", market, pclass)
    floor = m.get("mf_vacancy", std["vacancy_floor"])
    vacancy = max(physical_vacancy, floor)

    credit = max(std["credit_loss"], concessions_pct)
    if concessions_pct > std["credit_loss"]:
        notes.append(f"Concessions of {concessions_pct:.1%} used in place of the standard {std['credit_loss']:.0%}.")
    if collected_rent_annual:
        actual_loss = max(0.0, 1 - collected_rent_annual / gpr_annual)
        if actual_loss - vacancy > credit:
            credit = actual_loss - vacancy
            notes.append(f"Rent collected is {actual_loss:.1%} below potential, so collection loss was raised to {credit:.1%}.")
        else:
            notes.append(f"Rent collected ({actual_loss:.1%} below potential) is in line with the assumptions.")
    if utility_reimb_monthly:
        notes.append(f"Utility reimbursements of ${utility_reimb_monthly:,.0f}/mo added to other income.")
    if insurance_increase:
        notes.append(f"Expected insurance increase of ${insurance_increase:,.0f}/yr added to expenses.")
    tax_rate = _tax_rate(m, "tax_apartment", tax_rate_override, notes)

    args = dict(gpr=gpr_annual, vacancy=vacancy, credit=credit,
                other_income=(other_income_monthly + utility_reimb_monthly) * 12,
                landlord_opex=opex_annual + insurance_increase, mgmt_fee=std["mgmt_fee"],
                reserves=units * std["reserves"], tax_rate=tax_rate, tax_share=1.0)
    mid = income_value(cap=cap, **args)
    low = income_value(cap=cap + md.CAP_RANGE, **args)
    high = income_value(cap=cap - md.CAP_RANGE, **args)
    _finish(mid, low, high, units, capex_needed)
    if capex_needed:
        notes.append(f"${capex_needed:,.0f} of near-term repairs deducted from value.")

    warnings = []
    if property_type == "Student housing":
        warnings.append("Student housing is leased by the bed and trades at different cap rates than "
                        "conventional apartments. This estimate uses conventional assumptions and may be off.")
    elif property_type == "Affordable / rent-restricted":
        warnings.append("Rent-restricted properties have capped rent growth and often trade at different cap "
                        "rates. This estimate uses conventional assumptions and may be off.")

    return {
        "mid": mid, "low": low, "high": high, "cap_rate": cap, "property_class": pclass,
        "vacancy_used": vacancy, "credit_loss_used": credit, "tax_rate": tax_rate,
        "deductions": capex_needed, "notes": notes, "warnings": warnings,
        "assumptions": std["note"],
        "sources": {"Cap rate": m["mf_cap_source"], "Class adjustment": md.CLASS_SOURCE,
                    "Property tax": "Owner-provided" if tax_rate_override else m["tax_source"],
                    "Vacancy": m.get("mf_vacancy_source", "5% underwriting floor (rule of thumb)")},
    }


def estimate_commercial(sector: str, total_sf: float, gpr_annual: float, physical_vacancy: float,
                        other_income_annual: float, lease_type: str, landlord_opex: float,
                        market: str, year_built: int,
                        *,  # ---- optional "improve accuracy" inputs ----
                        tax_rate_override: float | None = None,
                        class_override: str | None = None,
                        concessions_pct: float = 0.0,
                        rollover_rent: float = 0.0,        # annual rent on leases expiring in 12 months
                        downtime_months: float = 0.0,      # expected months vacant before re-leasing
                        releasing_cost: float = 0.0,       # TI + commissions to re-lease, $
                        capex_needed: float = 0.0,
                        warnings_in: list | None = None) -> dict:
    """Industrial or office: what a buyer would likely pay."""
    import market_data as md

    m = md.MARKETS[market]
    std = md.STANDARD[sector]
    notes, warnings = [], list(warnings_in or [])
    pclass = class_override or md.property_class(sector, year_built)
    cap = md.cap_rate(sector, market, pclass)
    vacancy = max(physical_vacancy, std["vacancy_floor"])
    credit = max(std["credit_loss"], concessions_pct)
    if concessions_pct > std["credit_loss"]:
        notes.append(f"Free rent / concessions of {concessions_pct:.1%} used in place of the standard {std['credit_loss']:.0%}.")
    tax_rate = _tax_rate(m, "tax_commercial", tax_rate_override, notes)

    nnn = lease_type.startswith("NNN")
    args = dict(gpr=gpr_annual, vacancy=vacancy, credit=credit, other_income=other_income_annual,
                landlord_opex=landlord_opex, mgmt_fee=0.0 if nnn else std["mgmt_fee_gross"],
                reserves=total_sf * std["reserves_psf"], tax_rate=tax_rate,
                tax_share=vacancy if nnn else 1.0)
    mid = income_value(cap=cap, **args)
    low = income_value(cap=cap + md.CAP_RANGE, **args)
    high = income_value(cap=cap - md.CAP_RANGE, **args)

    downtime_loss = rollover_rent * downtime_months / 12
    deductions = capex_needed + releasing_cost + downtime_loss
    _finish(mid, low, high, total_sf, deductions)   # "per unit" = per SF here
    if downtime_loss:
        notes.append(f"Leases expiring within 12 months: {downtime_months:g} months of lost rent "
                     f"(${downtime_loss:,.0f}) deducted.")
    if releasing_cost:
        notes.append(f"Re-leasing costs of ${releasing_cost:,.0f} deducted.")
    if capex_needed:
        notes.append(f"${capex_needed:,.0f} of near-term repairs deducted from value.")

    return {
        "mid": mid, "low": low, "high": high, "cap_rate": cap, "property_class": pclass,
        "vacancy_used": vacancy, "credit_loss_used": credit, "tax_rate": tax_rate,
        "tax_share": args["tax_share"], "nnn": nnn, "deductions": deductions,
        "notes": notes, "warnings": warnings, "assumptions": std["note"],
        "sources": {"Market cap rate (multifamily base)": m["mf_cap_source"],
                    "Sector adjustment": md.SECTOR_SOURCE, "Class adjustment": md.CLASS_SOURCE,
                    "Property tax": "Owner-provided" if tax_rate_override else m["tax_source"]},
    }
