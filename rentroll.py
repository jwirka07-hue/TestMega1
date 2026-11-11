"""
Read an owner's rent roll (CSV or Excel) without making them reformat it.
Finds the unit / rent / status columns by common names.
"""
import pandas as pd

ALIASES = {
    "unit": ["unit", "unit #", "unit number", "unit no", "apt", "apartment", "unit id"],
    "rent": ["rent", "current rent", "in-place rent", "in place rent", "actual rent",
             "lease rent", "contract rent", "monthly rent"],
    "market_rent": ["market rent", "market", "asking rent"],
    "status": ["status", "unit status", "occupancy", "occupancy status"],
}
VACANT_WORDS = ("vacant", "down", "model", "offline", "non-rev", "admin")


def _norm(s) -> str:
    return str(s).strip().lower().replace("_", " ")


def _find(columns, field):
    norm = {_norm(c): c for c in columns}
    for alias in ALIASES[field]:
        if alias in norm:
            return norm[alias]
    if field == "rent":  # fallback: any column with 'rent' that isn't market rent
        for n, c in norm.items():
            if "rent" in n and "market" not in n and "asking" not in n:
                return c
    return None


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[$,\s]", "", regex=True), errors="coerce"
    ).fillna(0)


def read_file(uploaded) -> pd.DataFrame:
    name = getattr(uploaded, "name", str(uploaded)).lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded)
    return pd.read_csv(uploaded)


def summarize(df: pd.DataFrame) -> dict:
    df = df.dropna(how="all")
    rent_col = _find(df.columns, "rent")
    if rent_col is None:
        raise ValueError("Couldn't find a rent column. Name it 'Rent' and try again.")

    status_col = _find(df.columns, "status")
    mkt_col = _find(df.columns, "market_rent")
    warnings = []

    rent = _money(df[rent_col])
    if status_col:
        status = df[status_col].astype(str).str.lower()
        vacant = status.apply(lambda s: any(w in s for w in VACANT_WORDS)) | (rent <= 0)
    else:
        vacant = rent <= 0
        warnings.append("No status column found — units with $0 rent were treated as vacant.")

    units = len(df)
    occupied = int((~vacant).sum())
    if occupied == 0:
        raise ValueError("Every unit looks vacant. Check that the rent column has amounts.")

    avg_occ_rent = rent[~vacant].mean()

    # Vacant units are counted at market rent if given, otherwise at the average occupied rent
    if mkt_col:
        mkt = _money(df[mkt_col])
        vacant_rent = mkt[vacant].where(mkt[vacant] > 0, avg_occ_rent)
    else:
        vacant_rent = pd.Series(avg_occ_rent, index=df.index[vacant])
        if vacant.any():
            warnings.append("No market rent column — vacant units were valued at the average occupied rent.")

    gpr_monthly = rent[~vacant].sum() + vacant_rent.sum()

    return {
        "units": units,
        "occupied": occupied,
        "vacant": units - occupied,
        "physical_vacancy": (units - occupied) / units,
        "avg_in_place_rent": avg_occ_rent,
        "gpr_annual": gpr_monthly * 12,
        "warnings": warnings,
    }


def template() -> pd.DataFrame:
    return pd.DataFrame({
        "Unit": ["101", "102", "103"],
        "Rent": [1450, 1500, 0],
        "Market Rent": [1500, 1550, 1500],
        "Status": ["Occupied", "Occupied", "Vacant"],
    })


# ---------------- Commercial (industrial / office) tenant rent rolls ----------------
COMM_ALIASES = {
    "tenant": ["tenant", "tenant name", "lessee", "occupant", "suite tenant"],
    "sf": ["sf", "rsf", "nrsf", "square feet", "sq ft", "size", "rentable sf", "leased sf", "area"],
    "annual_rent": ["annual rent", "annual base rent", "base rent", "rent", "yearly rent", "abr"],
    "monthly_rent": ["monthly rent", "monthly base rent", "rent/month", "rent per month"],
    "rent_psf": ["rent/sf", "rent psf", "$/sf", "rent per sf", "annual rent/sf", "rate"],
    "lease_end": ["lease end", "lease expiration", "expiration", "expires", "lease exp", "end date"],
}


def _cfind(columns, field):
    norm = {_norm(c): c for c in columns}
    for alias in COMM_ALIASES[field]:
        if alias in norm:
            return norm[alias]
    return None


def summarize_commercial(df: pd.DataFrame, today=None) -> dict:
    df = df.dropna(how="all")
    today = pd.Timestamp(today or pd.Timestamp.today().normalize())
    sf_col = _cfind(df.columns, "sf")
    if sf_col is None:
        raise ValueError("Couldn't find a square footage column. Name it 'SF' and try again.")
    sf = _money(df[sf_col])
    warnings = []

    mcol, acol, pcol = (_cfind(df.columns, k) for k in ("monthly_rent", "annual_rent", "rent_psf"))
    if mcol:
        rent = _money(df[mcol]) * 12
    elif pcol:
        rent = _money(df[pcol]) * sf
    elif acol:
        rent = _money(df[acol])
    else:
        raise ValueError("Couldn't find a rent column. Use 'Annual Rent', 'Monthly Rent' or 'Rent/SF'.")

    tcol = _cfind(df.columns, "tenant")
    name = df[tcol].astype(str).str.lower() if tcol else pd.Series("", index=df.index)
    vacant = name.str.contains("vacant") | (rent <= 0)

    total_sf = sf.sum()
    leased_sf = sf[~vacant].sum()
    if leased_sf == 0:
        raise ValueError("Every space looks vacant. Check the rent column.")
    avg_psf = rent[~vacant].sum() / leased_sf
    gpr = rent[~vacant].sum() + sf[vacant].sum() * avg_psf
    if vacant.any():
        warnings.append(f"Vacant space ({sf[vacant].sum():,.0f} SF) valued at the average in-place rent "
                        f"of ${avg_psf:,.2f}/SF to compute potential rent.")

    # Lease expirations: weighted average lease term (WALT) and 12-month rollover
    walt, rollover_rent, rollover_sf = None, 0.0, 0.0
    ecol = _cfind(df.columns, "lease_end")
    if ecol:
        ends = pd.to_datetime(df[ecol], errors="coerce")
        occ = ~vacant & ends.notna()
        if occ.any():
            yrs = ((ends[occ] - today).dt.days / 365.25).clip(lower=0)
            walt = float((yrs * rent[occ]).sum() / rent[occ].sum())
            soon = occ & (ends <= today + pd.DateOffset(months=12))
            rollover_rent, rollover_sf = float(rent[soon].sum()), float(sf[soon].sum())
    else:
        warnings.append("No lease end column — lease rollover risk not measured.")

    top_share = float(rent[~vacant].max() / rent[~vacant].sum())
    return {
        "tenants": int((~vacant).sum()), "total_sf": float(total_sf), "leased_sf": float(leased_sf),
        "physical_vacancy": float(1 - leased_sf / total_sf), "avg_rent_psf": float(avg_psf),
        "gpr_annual": float(gpr), "walt": walt, "rollover_rent": rollover_rent,
        "rollover_sf": rollover_sf, "top_tenant_share": top_share, "warnings": warnings,
    }


def commercial_template() -> pd.DataFrame:
    return pd.DataFrame({
        "Tenant": ["Acme Logistics", "Blue Ridge Supply", "Vacant"],
        "SF": [60000, 25000, 15000],
        "Annual Rent": [480000, 212500, 0],
        "Lease End": ["2029-06-30", "2027-03-31", ""],
    })
