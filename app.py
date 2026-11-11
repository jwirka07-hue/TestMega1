"""
Southeast Commercial Property Value Estimator — Streamlit app
Tabs: Apartments | Industrial | Office
Run locally:  streamlit run app.py
"""
import streamlit as st

import market_data as md
import rentroll
from datetime import date, timedelta

import pandas as pd

import home
from engine import estimate_value, estimate_commercial

st.set_page_config(page_title="Southeast Property Value Estimator", page_icon="🏠", layout="centered")

MARKET_LIST = list(md.MARKETS.keys())


def money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


# ======================================================================
# Shared pieces
# ======================================================================
def tax_override_inputs(key: str):
    """Owner's actual tax rate = current bill / county appraised value (works in every state)."""
    st.markdown("**Property taxes**")
    t1, t2 = st.columns(2)
    bill = t1.number_input("Current annual property tax bill ($)", min_value=0.0, value=None,
                           step=1000.0, key=f"{key}_bill")
    appraised = t2.number_input("County appraised / market value on that bill ($)", min_value=0.0,
                                value=None, step=10000.0, key=f"{key}_appr",
                                help="Both numbers are on your tax bill or the county assessor's website. "
                                     "Together they give your real tax rate, which varies by city and county.")
    if bill and appraised:
        rate = bill / appraised
        st.caption(f"Your effective tax rate: {money(bill)} ÷ {money(appraised)} = **{rate:.2%}** of value")
        return rate
    return None


def class_override_input(key: str, sector: str):
    labels = {"Use year built": None, "Class A": "A", "Class B": "B", "Class C": "C"}
    help_text = {
        "multifamily": "A = newer, top amenities; B = solid, older; C = dated, workforce housing.",
        "industrial": "A = modern bulk/distribution, 28'+ clear; B = functional, older; C = small, low clear, dated.",
        "office": "A = newest, best-located, top finishes; B = well-maintained, older; C = dated, functionally obsolete.",
    }[sector]
    choice = st.selectbox("Building class", list(labels), key=f"{key}_class", help=help_text)
    return labels[choice]


def condition_inputs(key: str, items: list[str]):
    st.markdown("**Condition and upcoming repairs**")
    cols = st.columns(2)
    checked = [cols[i % 2].checkbox(label, key=f"{key}_chk{i}") for i, label in enumerate(items)]
    capex = st.number_input("Estimated cost of major repairs needed in the next 2–3 years ($)",
                            min_value=0.0, value=0.0, step=10000.0, key=f"{key}_capex",
                            help="Buyers subtract this from the price dollar for dollar.")
    if any(checked) and capex == 0:
        st.warning("You checked a major system near the end of its life. A buyer will price in that "
                   "replacement — enter an estimated cost above for a more realistic number.")
    return capex


def show_results(r: dict, per_label: str, units_or_sf: float, extra_rows_note: str = ""):
    mid, low, high = r["mid"], r["low"], r["high"]
    st.divider()
    st.markdown("### Estimated value")
    st.markdown(f"## {money(low['value'])} – {money(high['value'])}")
    k1, k2, k3 = st.columns(3)
    k1.metric("Midpoint", money(mid["value"]))
    k2.metric(per_label, money(mid["value_per_unit"]))
    k3.metric("Cap rate", f"{r['cap_rate']:.2%}")

    for w in r["warnings"]:
        st.warning(w)
    if r["notes"]:
        st.markdown("**Based on the extra information you added:**\n" + "\n".join(f"- {n}" for n in r["notes"]))
    if mid["noi"] <= 0:
        st.error("Expenses exceed income, so there's no positive NOI to value. Check the expense figure.")

    with st.expander("How we got this number", expanded=True):
        tax_label = (f"Property taxes on vacant space ({r['tax_rate']:.2%} of value × {r['tax_share']:.0%} vacant)"
                     if r.get("nnn") else f"Property taxes, reset to sale price ({r['tax_rate']:.2%} of value)")
        rows = [
            ("Gross potential rent", mid["gpr"]),
            (f"Vacancy ({r['vacancy_used']:.1%})", mid["vacancy"]),
            (f"Concessions + bad debt ({r['credit_loss_used']:.1%})", mid["concessions_bad_debt"]),
            ("Other income", mid["other_income"]),
            ("**Effective gross income**", mid["egi"]),
            ("Operating expenses you pay", -mid["opex"]),
            ("Management", -mid["management"]),
            ("Reserves", -mid["reserves"]),
            (tax_label, -mid["taxes"]),
            ("**Net operating income**", mid["noi"]),
        ]
        st.markdown("| Line | Annual |\n|---|---:|\n" + "\n".join(f"| {k} | {money(v)} |" for k, v in rows))
        if r["deductions"]:
            line = (f"**Value** = NOI ÷ cap rate − one-time costs = {money(mid['noi'])} ÷ {r['cap_rate']:.2%} − "
                    f"{money(r['deductions'])} = {money(mid['value_before_deductions'])} − "
                    f"{money(r['deductions'])} = **{money(mid['value'])}**")
        else:
            line = f"**Value** = NOI ÷ cap rate = {money(mid['noi'])} ÷ {r['cap_rate']:.2%} = **{money(mid['value'])}**"
        st.markdown(line + f"  \nRange uses cap rates of {r['cap_rate'] + md.CAP_RANGE:.2%} (low) to "
                    f"{r['cap_rate'] - md.CAP_RANGE:.2%} (high). Priced as Class {r['property_class']}.")
        if extra_rows_note:
            st.caption(extra_rows_note)

    with st.expander("Assumptions and sources"):
        st.markdown(f"- **Standard underwriting:** {r['assumptions']}")
        for k, v in r["sources"].items():
            st.markdown(f"- **{k}:** {v}")


# ======================================================================
# Apartments tab
# ======================================================================
def apartments_tab():
    K = "mf"
    st.subheader("1. Your property")
    c1, c2 = st.columns(2)
    market = c1.selectbox("Market", MARKET_LIST, key=f"{K}_mkt")
    year = c2.number_input("Year built", 1900, 2027, value=None, step=1, placeholder="e.g. 1998", key=f"{K}_yr")

    st.subheader("2. Rent roll")
    up = st.file_uploader("Upload your rent roll (CSV or Excel)", type=["csv", "xlsx", "xls"], key=f"{K}_up",
                          help="Needs a unit column and a rent column. Status and market rent columns help.")
    st.download_button("Download a blank template", rentroll.template().to_csv(index=False),
                       "apartment_rent_roll_template.csv", "text/csv", key=f"{K}_tpl")
    rr = None
    with st.expander("No rent roll handy? Enter totals instead"):
        m1, m2, m3 = st.columns(3)
        mu = m1.number_input("Total units", min_value=0, value=None, step=1, key=f"{K}_mu")
        mo = m2.number_input("Occupied units", min_value=0, value=None, step=1, key=f"{K}_mo")
        mr = m3.number_input("Average rent ($/mo)", min_value=0.0, value=None, step=25.0, key=f"{K}_mr")
    if up is not None:
        try:
            rr = rentroll.summarize(rentroll.read_file(up))
            st.success(f"Read {rr['units']} units · {rr['occupied']} occupied · "
                       f"average rent {money(rr['avg_in_place_rent'])}/mo")
            for w in rr["warnings"]:
                st.info(w)
        except Exception as e:
            st.error(f"Couldn't read that file: {e}")
    elif mu and mr and mo is not None:
        if mo > mu:
            st.error("Occupied units can't be more than total units.")
        else:
            rr = {"units": int(mu), "physical_vacancy": (mu - mo) / mu, "gpr_annual": mu * mr * 12}

    st.subheader("3. Income and expenses")
    e1, e2 = st.columns(2)
    opex = e1.number_input("Annual operating expenses ($)", min_value=0.0, value=None, step=1000.0, key=f"{K}_opex",
                           help="Utilities, repairs, payroll, insurance, admin, marketing. Leave OUT property "
                                "taxes, management fees and reserves — we add those at what a buyer would pay.")
    other = e2.number_input("Other monthly income ($, optional)", min_value=0.0, value=0.0, step=100.0,
                            key=f"{K}_oth", help="Parking, pet fees, laundry — total per month.")

    with st.expander("Add Other Information to Improve Accuracy"):
        st.caption("All optional. Each answer replaces a market assumption with your property's actual numbers.")
        st.markdown("**Property type and class**")
        p1, p2 = st.columns(2)
        with p1:
            ptype = st.selectbox("Property type", ["Conventional", "Student housing", "Affordable / rent-restricted"],
                                 key=f"{K}_ptype")
        with p2:
            cls = class_override_input(K, "multifamily")
        tax_rate = tax_override_inputs(K)
        st.markdown("**Income detail (from your T-12)**")
        i1, i2 = st.columns(2)
        collected = i1.number_input("Rent actually collected, last 12 months ($)", min_value=0.0, value=None,
                                    step=10000.0, key=f"{K}_coll",
                                    help="Total rent received after vacancy, concessions and bad debt.")
        conc = i2.number_input("Move-in specials / concessions (% of rent)", 0.0, 50.0, 0.0, 0.5, key=f"{K}_conc",
                               help="Example: one month free on a 12-month lease ≈ 8.3%.")
        util = i1.number_input("Utility reimbursements collected ($/month)", min_value=0.0, value=0.0, step=100.0,
                               key=f"{K}_util", help="RUBS billed back to residents, if not in other income.")
        ins = i2.number_input("Expected insurance increase at renewal ($/year)", min_value=0.0, value=0.0,
                              step=1000.0, key=f"{K}_ins")
        capex = condition_inputs(K, ["Roof is 20+ years old", "Most HVAC systems are 15+ years old",
                                     "Polybutylene or galvanized plumbing", "Most units have original interiors"])

    ready = rr is not None and year and opex
    if st.button("Estimate value", type="primary", disabled=not ready, use_container_width=True, key=f"{K}_go"):
        r = estimate_value(rr["units"], rr["gpr_annual"], rr["physical_vacancy"], other, opex, market, int(year),
                           tax_rate_override=tax_rate, collected_rent_annual=collected or None,
                           concessions_pct=conc / 100, utility_reimb_monthly=util, insurance_increase=ins,
                           capex_needed=capex, property_type=ptype, class_override=cls)
        show_results(r, "Per unit", rr["units"])


# ======================================================================
# Industrial & office tabs (shared layout, sector-specific details)
# ======================================================================
SECTOR_UI = {
    "industrial": {
        "default_lease": 0, "size_hint": "e.g. 100,000",
        "opex_help_gross": "Insurance, repairs, utilities, landscaping, etc. Leave OUT property taxes, "
                           "management and reserves — we add those.",
        "other_help": "Trailer parking, cell towers, solar leases — total per year.",
        "condition": ["Roof is 20+ years old", "Parking / truck court needs repaving",
                      "Dock doors or levelers need replacing", "Sprinklers or fire system out of date"],
    },
    "office": {
        "default_lease": 1, "size_hint": "e.g. 50,000",
        "opex_help_gross": "Utilities, janitorial, repairs, insurance, security, admin. Leave OUT property "
                           "taxes, management and reserves — we add those.",
        "other_help": "Parking, antenna, storage — total per year.",
        "condition": ["Roof is 20+ years old", "HVAC / chillers 20+ years old",
                      "Elevators need modernization", "Common areas / lobby dated"],
    },
}
LEASE_TYPES = ["NNN (tenants pay taxes, insurance, CAM)", "Gross / full-service (I pay expenses)"]


def commercial_tab(sector: str):
    K = sector[:3]
    ui = SECTOR_UI[sector]

    st.subheader("1. Your property")
    c1, c2 = st.columns(2)
    market = c1.selectbox("Market", MARKET_LIST, key=f"{K}_mkt")
    year = c2.number_input("Year built", 1900, 2027, value=None, step=1, placeholder="e.g. 1995", key=f"{K}_yr")

    st.subheader("2. Tenant rent roll")
    up = st.file_uploader("Upload your rent roll (CSV or Excel)", type=["csv", "xlsx", "xls"], key=f"{K}_up",
                          help="One row per tenant or suite: Tenant, SF, Annual Rent (or Monthly Rent or Rent/SF), "
                               "Lease End. Mark empty suites 'Vacant'.")
    st.download_button("Download a blank template", rentroll.commercial_template().to_csv(index=False),
                       f"{sector}_rent_roll_template.csv", "text/csv", key=f"{K}_tpl")
    rr = None
    with st.expander("No rent roll handy? Enter totals instead"):
        m1, m2, m3 = st.columns(3)
        msf = m1.number_input("Building SF", min_value=0.0, value=None, step=1000.0, key=f"{K}_msf",
                              placeholder=ui["size_hint"])
        mlsf = m2.number_input("Leased SF", min_value=0.0, value=None, step=1000.0, key=f"{K}_mlsf")
        mpsf = m3.number_input("Average rent ($/SF/yr)", min_value=0.0, value=None, step=0.25, key=f"{K}_mpsf")
    if up is not None:
        try:
            rr = rentroll.summarize_commercial(rentroll.read_file(up))
            walt = f" · WALT {rr['walt']:.1f} yrs" if rr["walt"] is not None else ""
            st.success(f"Read {rr['tenants']} tenants · {rr['total_sf']:,.0f} SF · "
                       f"{1 - rr['physical_vacancy']:.0%} leased · ${rr['avg_rent_psf']:,.2f}/SF{walt}")
            for w in rr["warnings"]:
                st.info(w)
        except Exception as e:
            st.error(f"Couldn't read that file: {e}")
    elif msf and mpsf and mlsf is not None:
        if mlsf > msf:
            st.error("Leased SF can't be more than building SF.")
        else:
            rr = {"total_sf": msf, "physical_vacancy": 1 - mlsf / msf, "gpr_annual": msf * mpsf,
                  "walt": None, "rollover_rent": 0.0, "rollover_sf": 0.0, "top_tenant_share": None}

    st.subheader("3. Leases and expenses")
    lease = st.radio("How are your leases structured?", LEASE_TYPES, index=ui["default_lease"],
                     key=f"{K}_lease", horizontal=True)
    nnn = lease.startswith("NNN")
    e1, e2 = st.columns(2)
    if nnn:
        opex = e1.number_input("Expenses tenants don't reimburse ($/yr)", min_value=0.0, value=0.0, step=1000.0,
                               key=f"{K}_opex_nnn",
                               help="On NNN leases most costs pass through to tenants. Enter only what you "
                                    "absorb yourself (structural repairs, unreimbursed admin). 0 is fine.")
    else:
        opex = e1.number_input("Annual operating expenses ($)", min_value=0.0, value=None, step=1000.0,
                               key=f"{K}_opex_gross", help=ui["opex_help_gross"])
    other = e2.number_input("Other annual income ($, optional)", min_value=0.0, value=0.0, step=1000.0,
                            key=f"{K}_oth", help=ui["other_help"])

    # ---------- Improve accuracy ----------
    with st.expander("Add Other Information to Improve Accuracy"):
        st.caption("All optional. Each answer replaces a market assumption with your property's actual numbers.")
        warnings = []
        st.markdown("**Building**")
        b1, b2 = st.columns(2)
        with b1:
            cls = class_override_input(K, sector)
        with b2:
            if sector == "industrial":
                clear = st.selectbox("Clear height", ["Not sure", "Under 24 ft", "24–32 ft", "32 ft+"],
                                     key=f"{K}_clear",
                                     help="Distance from floor to the lowest overhead obstruction.")
                if clear == "Under 24 ft":
                    warnings.append("Clear heights under 24 ft limit modern distribution users, which narrows "
                                    "the buyer pool. Consider selecting Class C.")
            else:
                parking = st.selectbox("Parking ratio (spaces per 1,000 SF)",
                                       ["Not sure", "Under 3", "3–4", "4+"], key=f"{K}_park")
                if parking == "Under 3":
                    warnings.append("Low parking ratios limit which tenants can lease the space and can "
                                    "slow re-leasing.")

        tax_rate = tax_override_inputs(K)

        st.markdown("**Leasing**")
        l1, l2 = st.columns(2)
        conc = l1.number_input("Free rent / concessions (% of rent)", 0.0, 50.0, 0.0, 0.5, key=f"{K}_conc",
                               help="Average free rent given on recent leases. "
                                    "Example: 3 months free on a 5-year lease = 5%.")
        default_roll = float(rr["rollover_rent"]) if rr else 0.0
        roll = l2.number_input("Annual rent on leases expiring in the next 12 months ($)", min_value=0.0,
                               value=default_roll, step=10000.0, key=f"{K}_roll_{int(default_roll)}",
                               help="Filled in from your rent roll's lease end dates when available.")
        down = l1.number_input("Expected months vacant before re-leasing", 0.0, 36.0,
                               0.0, 1.0, key=f"{K}_down",
                               help="Only for leases you expect won't renew. Lost rent is deducted from value.")
        relet = l2.number_input("Cost to re-lease that space — improvements + commissions ($)", min_value=0.0,
                                value=0.0, step=10000.0, key=f"{K}_relet")

        capex = condition_inputs(K, ui["condition"])

        if rr and rr.get("top_tenant_share") and rr["top_tenant_share"] >= 0.5:
            warnings.append(f"Your largest tenant pays {rr['top_tenant_share']:.0%} of the rent. Buyers price "
                            "single-tenant risk heavily — value depends on that tenant's credit and lease term.")
        if rr and rr.get("walt") is not None and rr["walt"] < 2:
            warnings.append(f"Weighted average lease term is only {rr['walt']:.1f} years. Short remaining terms "
                            "usually mean a higher cap rate than shown here.")
        if sector == "office" and rr and rr["physical_vacancy"] > 0.25:
            warnings.append("Office buildings with more than 25% vacancy are usually valued on the cost and time "
                            "to lease up, which this quick estimate doesn't model. Treat the value as an upper bound.")

    ready = rr is not None and year and (opex is not None)
    if st.button("Estimate value", type="primary", disabled=not ready, use_container_width=True, key=f"{K}_go"):
        r = estimate_commercial(sector, rr["total_sf"], rr["gpr_annual"], rr["physical_vacancy"], other,
                                lease, opex or 0.0, market, int(year),
                                tax_rate_override=tax_rate, class_override=cls, concessions_pct=conc / 100,
                                rollover_rent=roll, downtime_months=down, releasing_cost=relet,
                                capex_needed=capex, warnings_in=warnings)
        note = ("On NNN leases tenants reimburse taxes, insurance and common-area costs for the space they "
                "occupy, so only the vacant share and unreimbursed costs reduce NOI.") if nnn else ""
        show_results(r, "Per SF", rr["total_sf"], note)



# ======================================================================
# Home tab (sales comparison approach)
# ======================================================================
def home_tab():
    K = "home"
    st.caption("Homes are valued by comparing them to recent nearby sales — the way appraisers do it.")

    st.subheader("1. Your home")
    a1, a2, a3 = st.columns(3)
    sf = a1.number_input("Heated square feet", min_value=200, max_value=20000, value=None, step=50, key=f"{K}_sf")
    beds = a2.number_input("Bedrooms", 0, 15, value=None, step=1, key=f"{K}_beds")
    baths = a3.number_input("Bathrooms", 0.0, 15.0, value=None, step=0.5, key=f"{K}_baths",
                            help="Count a half bath as 0.5.")
    b1, b2 = st.columns(2)
    year = b1.number_input("Year built", 1800, 2027, value=None, step=1, key=f"{K}_yr")
    b2.text_input("Address (optional)", placeholder="123 Oak St, Athens, GA", key=f"{K}_addr")

    st.subheader("2. Recent nearby sales")
    st.markdown("Find 3–5 homes that **sold** in the last 6–12 months, within about a mile, and similar in size. "
                "On Zillow or Redfin, search your area and filter to *Sold*.")
    n = st.radio("How many sales will you enter?", [3, 4, 5], horizontal=True, key=f"{K}_n")
    comps = []
    for i in range(n):
        with st.container(border=True):
            st.markdown(f"**Sale {i + 1}**")
            r1 = st.columns([2, 1.2, 1.2])
            addr = r1[0].text_input("Address", key=f"{K}_a{i}", placeholder="e.g. 210 Pine St")
            price = r1[1].number_input("Sale price ($)", min_value=0.0, value=None, step=5000.0, key=f"{K}_p{i}")
            sdate = r1[2].date_input("Sale date", value=None, max_value=date.today(),
                                     min_value=date.today() - timedelta(days=3 * 365), key=f"{K}_d{i}",
                                     format="MM/DD/YYYY")
            r2 = st.columns([1, 0.8, 0.8, 1, 1.6])
            csf = r2[0].number_input("Sq ft", min_value=0, value=None, step=50, key=f"{K}_s{i}")
            cb = r2[1].number_input("Beds", 0, 15, value=None, step=1, key=f"{K}_b{i}")
            cba = r2[2].number_input("Baths", 0.0, 15.0, value=None, step=0.5, key=f"{K}_ba{i}")
            cy = r2[3].number_input("Year built", 1800, 2027, value=None, step=1, key=f"{K}_y{i}")
            cond = r2[4].selectbox("Condition vs. mine", list(home.CONDITION_SHIFT), index=1, key=f"{K}_c{i}")
            if all(v is not None for v in (price, sdate, csf, cb, cba, cy)) and price > 0 and csf > 0:
                comps.append({"address": addr or f"Sale {i + 1}", "price": float(price), "sale_date": sdate,
                              "sf": float(csf), "beds": float(cb), "baths": float(cba), "year_built": int(cy),
                              "condition": cond})
    if comps:
        st.success(f"{len(comps)} complete sale{'s' if len(comps) != 1 else ''} entered"
                   + ("" if len(comps) >= 3 else " — need at least 3."))

    with st.expander("Add Other Information to Improve Accuracy"):
        st.caption("All optional.")
        st.markdown("**Market movement since those sales**")
        appr = st.number_input("Home price change in your area over the past year (%)", -20.0, 20.0, 0.0, 0.5,
                               key=f"{K}_appr",
                               help="Shown on Zillow/Redfin market pages for your zip code. Older comps are "
                                    "adjusted forward to today's prices at this rate.")
        st.markdown("**Repairs needed**")
        h1, h2 = st.columns(2)
        chk = [h1.checkbox("Roof is 20+ years old", key=f"{K}_chk1"),
               h1.checkbox("HVAC is 15+ years old", key=f"{K}_chk2"),
               h2.checkbox("Foundation, drainage or moisture issues", key=f"{K}_chk3"),
               h2.checkbox("Kitchen and baths are original", key=f"{K}_chk4")]
        capex = st.number_input("Estimated cost of repairs a buyer would expect you to fix ($)", min_value=0.0,
                                value=0.0, step=1000.0, key=f"{K}_capex",
                                help="Only items not already reflected in your condition ratings above.")
        if any(chk[:3]) and capex == 0:
            st.warning("Buyers and inspectors will flag this. Enter an estimated cost for a more realistic number.")
        if chk[3]:
            st.info("If your comps are updated and your home isn't, mark them 'Better than mine' in the table.")
        st.markdown("**If you rent it out**")
        r1, r2 = st.columns(2)
        rent = r1.number_input("Monthly rent ($)", min_value=0.0, value=0.0, step=50.0, key=f"{K}_rent")
        costs = r2.number_input("Annual taxes + insurance + HOA + maintenance ($)", min_value=0.0, value=0.0,
                                step=500.0, key=f"{K}_costs")

    ready = sf and beds is not None and baths is not None and year and len(comps) >= 3
    if st.button("Estimate value", type="primary", disabled=not ready, use_container_width=True, key=f"{K}_go"):
        subject = {"sf": sf, "beds": beds, "baths": baths, "year_built": int(year)}
        r = home.estimate_home(subject, comps, appreciation=appr / 100, capex=capex)

        st.divider()
        st.markdown("### Estimated value")
        st.markdown(f"## {money(r['low'])} – {money(r['high'])}")
        k1, k2, k3 = st.columns(3)
        k1.metric("Weighted estimate", money(r["value"]))
        k2.metric("Per sq ft", money(r["per_sf"]))
        k3.metric("Comps used", len(r["comps"]))
        if r["spread_pct"] > 0.20:
            st.warning(f"Your adjusted comps are {r['spread_pct']:.0%} apart. Look for sales closer to your home "
                       "in size, age and location to tighten the range.")
        for c in r["comps"]:
            if c["flags"]:
                st.info(f"**{c['address']}:** " + ", ".join(c["flags"]) + " — weighted less.")

        with st.expander("How we got this number", expanded=True):
            names = [c["address"] for c in r["comps"]]
            rows = [("Sale price", [c["price"] for c in r["comps"]])]
            for line in r["comps"][0]["lines"]:
                rows.append((line, [c["lines"][line] for c in r["comps"]]))
            rows.append(("**Adjusted price**", [c["adjusted"] for c in r["comps"]]))
            header = "| | " + " | ".join(names) + " |\n|---|" + "---:|" * len(names) + "\n"
            body = "\n".join(f"| {k} | " + " | ".join(money(v) for v in vals) + " |" for k, vals in rows)
            body += "\n| Gross adjustment | " + " | ".join(f"{c['gross_pct']:.0%}" for c in r["comps"]) + " |"
            body += "\n| **Weight** | " + " | ".join(f"**{c['weight']:.0%}**" for c in r["comps"]) + " |"
            st.markdown(header + body)
            calc = " + ".join(f"{money(c['adjusted'])} × {c['weight']:.0%}" for c in r["comps"])
            st.markdown(f"**Estimate** = {calc}" + (f" − {money(capex)} repairs" if capex else "")
                        + f" = **{money(r['value'])}**")
            st.caption("Each comp is adjusted to look like your home: if a comp is smaller, we add value; if it's "
                       "nicer, we subtract. Comps needing smaller adjustments get more weight. The range is the "
                       "lowest to highest adjusted comp.")

        if rent:
            rc = home.rental_check(r["value"], rent, costs)
            with st.expander("As a rental", expanded=True):
                st.markdown(f"- **Gross yield:** {money(rent * 12)} ÷ {money(r['value'])} = **{rc['gross_yield']:.1%}**\n"
                            f"- **Net yield (cap rate):** ({money(rent * 12)} × 95% occupancy − {money(costs)}) ÷ "
                            f"{money(r['value'])} = **{rc['net_yield']:.1%}**\n"
                            f"- **Price-to-rent ratio:** {rc['price_to_rent']:.1f}× annual rent")

        with st.expander("Assumptions"):
            st.markdown(f"- **Adjustments:** {r['assumptions']}\n"
                        f"- **Market change applied:** {appr:.1f}% per year since each sale\n"
                        "- Values reflect the comps you entered; better comps give a better estimate.")


# ======================================================================
# Page
# ======================================================================
st.title("What's your property worth?")
st.caption("Southeast real estate · Pick your property type, enter a few details, get a value range.")

tab_home, tab_mf, tab_ind, tab_off = st.tabs(["🏠 Home", "🏘️ Apartments", "🏭 Industrial", "🏢 Office"])
with tab_home:
    home_tab()
with tab_mf:
    apartments_tab()
with tab_ind:
    commercial_tab("industrial")
with tab_off:
    commercial_tab("office")

st.divider()
st.caption("This is an automated estimate for informational purposes only. It is not an appraisal or broker "
           "opinion of value and should not be relied on for lending, tax or legal decisions.")
