from pathlib import Path
import time
import pandas as pd


# CONFIGURATION

RESULTS_DIR = Path(
    r"C:\Users\rache\NZB_MacroEnergy\NZB_S0_testes\results_001"
)

PERIODS = {
    1: 2025,
    2: 2030,
    3: 2035,
    4: 2040,
    5: 2045,
    6: 2050,
}

FLOWS_SUBFOLDER = "full_time_series"

FLOWS_CANDIDATES = ["flows.csv", "flows.csv.gz", "flows.csv.zip", "flows.zip"]

OUTPUT_FILE = "flows_summary.csv"

OUTPUT_FILE_BIOMASS = "flows_summary_biomass.csv"


BIOMASS_FEEDSTOCKS = [
    "Biomass_wood",
    "Corn",
    "Macauba",
    "RiceStraw",
    "Soybean",
    "Sugarcane",
]

CHUNK_SIZE = 500_000


# EP wood demand

# One entry per EP file (charcoal_mass and firewood_mass are separate files).
# Both are already expressed as WOOD mass, on a wet (as-harvested) basis -
# used as-is below, no moisture conversion needed.
# .csv, .xlsx and .xls are all accepted.
EP_DEMAND_FILES = [
    # r"C:\Users\rache\OneDrive\Área de Trabalho\S0\S0\S0\EP2MACRO\EXO_DEMAND\charcoal mass_S0.csv",
    # r"C:\Users\rache\OneDrive\Área de Trabalho\S0\S0\S0\EP2MACRO\EXO_DEMAND\firewood mass_S0.csv",
]

# Must match one of BIOMASS_FEEDSTOCKS exactly (case-sensitive).
EP_DEMAND_FEEDSTOCK = "Biomass_wood"


# Wood moisture content (as-harvested)

# MACRO reports Biomass_wood on a DRY basis, unlike the other biomass
# feedstocks (Corn, Macauba, RiceStraw, Soybean, Sugarcane), which already
# arrive on a wet (as-harvested) basis and are used as-is. Since every output
# of this script is now on a wet basis, MACRO's wood values are converted
# dry -> wet using this moisture content before being summed with EP's wood
# demand (which already arrives on a wet basis - see EP_DEMAND_FILES above):
#   wet_tonnes = dry_tonnes / (1 - WOOD_MOISTURE_CONTENT)
# Same figure previously used as EP_MOISTURE_CONTENT for EP's own wood demand.
WOOD_MOISTURE_CONTENT = 0.51


# Sanity check on configuration
if EP_DEMAND_FEEDSTOCK not in BIOMASS_FEEDSTOCKS:
    raise ValueError(
        f"EP_DEMAND_FEEDSTOCK = '{EP_DEMAND_FEEDSTOCK}' is not in BIOMASS_FEEDSTOCKS "
        f"{BIOMASS_FEEDSTOCKS}. Names are case-sensitive."
    )


# Table 1: all comodities

usecols = ["commodity", "value"]

all_periods_summary = []

total_start_time = time.time()


def find_flows_file(period_folder: Path) -> Path | None:
    for name in FLOWS_CANDIDATES:
        candidate = period_folder / FLOWS_SUBFOLDER / name
        if candidate.is_file():
            return candidate
    return None


def _looks_like_year(label) -> bool:
    try:
        return 1990 <= int(float(str(label).strip())) <= 2100
    except (TypeError, ValueError):
        return False


def _sheet_to_year_totals(df: pd.DataFrame, label: str) -> pd.Series:
    """Collapse one EP sheet into {year: total}, summing over all Brazilian
    regions/rows. Accepts both wide (one column per year) and long
    (year column + value column) layouts."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # --- wide layout: years as columns ---
    year_cols = [c for c in df.columns if _looks_like_year(c)]
    if year_cols:
        totals = df[year_cols].apply(pd.to_numeric, errors="coerce").sum()
        totals.index = [int(float(c)) for c in year_cols]
        return totals.sort_index()

    # --- long layout: one row per region/year ---
    year_col = next(
        (c for c in df.columns if c.lower() in {"year", "ano", "period", "periodo"}),
        None,
    )
    if year_col is None:
        raise ValueError(
            f"[{label}] Could not find a year column or year-named columns. "
            f"Columns found: {list(df.columns)}"
        )

    value_col = next(
        (
            c
            for c in df.columns
            if c.lower() in {"value", "valor", "demand", "demanda", "mass", "massa"}
        ),
        None,
    )
    if value_col is None:
        numeric = [c for c in df.select_dtypes("number").columns if c != year_col]
        if not numeric:
            raise ValueError(
                f"[{label}] Could not find a value column. Columns: {list(df.columns)}"
            )
        value_col = numeric[-1]
        print(f"  [INFO] {label}: using '{value_col}' as the value column.")

    years = pd.to_numeric(df[year_col], errors="coerce")
    values = pd.to_numeric(df[value_col], errors="coerce")
    totals = values.groupby(years).sum()
    totals.index = totals.index.astype(int)
    return totals.sort_index()


def load_ep_wood_demand() -> pd.Series:
    """Return total EP wood demand per year, on a wet (as-harvested) basis.

    Reads every file in EP_DEMAND_FILES (charcoal_mass and firewood_mass live in
    separate files), sums over all Brazilian regions within each file, and adds
    the files together year by year. EP's figures already arrive on a wet
    basis, so no moisture conversion is applied here."""
    if not EP_DEMAND_FILES:
        print("[INFO] EP_DEMAND_FILES is empty - EP wood demand treated as 0 for all years.")
        return pd.Series(dtype=float)

    total_wet = pd.Series(dtype=float)
    files_read = 0

    for entry in EP_DEMAND_FILES:
        ep_path = Path(entry)
        if not ep_path.is_file():
            print(f"[WARNING] EP demand file not found: {ep_path} - skipped.")
            continue

        print(f"Reading EP wood demand from: {ep_path}")

        if ep_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            df = pd.read_excel(ep_path)
        else:
            df = pd.read_csv(ep_path)

        per_year = _sheet_to_year_totals(df, ep_path.stem)
        print(
            f"  - {ep_path.stem}: {len(df)} rows -> {len(per_year)} years, "
            f"wet total = {per_year.sum():,.2f}"
        )
        total_wet = total_wet.add(per_year, fill_value=0.0)
        files_read += 1

    if files_read == 0:
        print("[WARNING] No EP demand file could be read - demand treated as 0.")
        return pd.Series(dtype=float)

    if files_read < len(EP_DEMAND_FILES):
        print(
            f"[WARNING] Only {files_read} of {len(EP_DEMAND_FILES)} EP files were read - "
            f"the total below is incomplete."
        )

    print("  -> EP wood demand, wet basis:")
    for year, value in total_wet.items():
        print(f"       {year}: {value:,.2f}")

    return total_wet


for period_num, year in PERIODS.items():
    period_folder = RESULTS_DIR / f"results_period_{period_num}"
    flows_path = find_flows_file(period_folder)

    if flows_path is None:
        print(
            f"[WARNING] No flows file found in "
            f"{period_folder / FLOWS_SUBFOLDER} (looked for: {FLOWS_CANDIDATES}), skipping."
        )
        continue

    print(f"Processing period {period_num} (year {year}): {flows_path}")
    period_start_time = time.time()

    partial_sums = []
    for chunk in pd.read_csv(flows_path, usecols=usecols, chunksize=CHUNK_SIZE):
        grouped = chunk.groupby("commodity", as_index=False)["value"].sum()
        partial_sums.append(grouped)

    period_summary = (
        pd.concat(partial_sums, ignore_index=True)
        .groupby("commodity", as_index=False)["value"]
        .sum()
    )
    period_summary.insert(0, "year", year)
    all_periods_summary.append(period_summary)

    period_elapsed = time.time() - period_start_time
    print(f"  -> period {period_num} completed in {period_elapsed:.1f} seconds")

final = (
    pd.concat(all_periods_summary, ignore_index=True)
    .sort_values(["year", "commodity"])
    .reset_index(drop=True)
)

final.to_csv(OUTPUT_FILE, index=False)

print(f"\nSummary saved to: {OUTPUT_FILE}")
print(final)


# Table 2: biomass

biomass = final[final["commodity"].isin(BIOMASS_FEEDSTOCKS)]

biomass_table = (
    biomass.pivot_table(
        index="year", columns="commodity", values="value", aggfunc="sum"
    )
    .reindex(columns=BIOMASS_FEEDSTOCKS)  # ensures all columns and the requested order
    .fillna(0)
    .abs()  # convert to absolute value (module)
    .reset_index()
)

# Step 1: MACRO wood flows -> wet basis. All other biomass feedstocks
# already arrive on a wet (as-harvested) basis from MACRO and are kept as-is
# below, since every output of this script is now on a wet basis.
biomass_table[EP_DEMAND_FEEDSTOCK] = biomass_table[EP_DEMAND_FEEDSTOCK] / (
    1 - WOOD_MOISTURE_CONTENT
)

# Step 2: add EP wood demand (already on a wet basis - used as-is)
ep_wood_demand = load_ep_wood_demand()

biomass_table[EP_DEMAND_FEEDSTOCK] = biomass_table[EP_DEMAND_FEEDSTOCK] + (
    biomass_table["year"].map(ep_wood_demand).fillna(0.0)
)

missing_years = sorted(set(PERIODS.values()) - set(ep_wood_demand.index))
if not ep_wood_demand.empty and missing_years:
    print(f"[WARNING] No EP demand found for years {missing_years} - treated as 0.")

biomass_table.to_csv(OUTPUT_FILE_BIOMASS, index=False)

print(f"\nBiomass table (wet basis) saved to: {OUTPUT_FILE_BIOMASS}")
print(biomass_table)

total_elapsed = time.time() - total_start_time
minutes, seconds = divmod(total_elapsed, 60)
print(f"\nTotal execution time: {int(minutes)} min {seconds:.1f} s")