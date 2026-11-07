from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "datasets" / "generated"
METER_FILE = GENERATED_DIR / "plant_meter_readings.csv"
FUEL_FILE = GENERATED_DIR / "fuel_consumption.csv"
PRODUCTION_FILE = GENERATED_DIR / "production_records.csv"
FACTOR_OUTPUT = GENERATED_DIR / "emission_factors.csv"
DAILY_OUTPUT = GENERATED_DIR / "daily_carbon_emissions.csv"
CLAIM_OUTPUT = GENERATED_DIR / "monthly_carbon_claims.csv"


def create_emission_factors() -> pd.DataFrame:
    records = [
        {
            "factor_id": "EF-ELECTRICITY-IN-2023-24",
            "activity_type": "PURCHASED_ELECTRICITY",
            "scope": "SCOPE_2",
            "factor_value": 0.727,
            "factor_unit": "kgCO2_per_kWh",
            "source_authority": "CENTRAL_ELECTRICITY_AUTHORITY_INDIA",
            "source_document": "CO2_BASELINE_DATABASE_VERSION_20",
            "source_year": "2023-24",
            "effective_from": "2025-01-01",
            "effective_until": "2026-12-31",
            "verification_status": "OFFICIAL_SOURCE_REFERENCED",
            "notes": "Weighted average Indian grid factor used for prototype Scope 2 calculation",
        },
        {
            "factor_id": "EF-NATURAL-GAS-DEMO-001",
            "activity_type": "NATURAL_GAS",
            "scope": "SCOPE_1",
            "factor_value": 2.0,
            "factor_unit": "kgCO2e_per_SCM",
            "source_authority": "PROTOTYPE_CONFIG",
            "source_document": "DEMO_FACTOR_REGISTRY",
            "source_year": "2026",
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
            "verification_status": "REQUIRES_AUTHORIZED_FACTOR_BEFORE_REAL_DEPLOYMENT",
            "notes": "Configurable demonstration factor; not for regulatory reporting",
        },
        {
            "factor_id": "EF-DIESEL-DEMO-001",
            "activity_type": "DIESEL",
            "scope": "SCOPE_1",
            "factor_value": 2.68,
            "factor_unit": "kgCO2e_per_litre",
            "source_authority": "PROTOTYPE_CONFIG",
            "source_document": "DEMO_FACTOR_REGISTRY",
            "source_year": "2026",
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
            "verification_status": "REQUIRES_AUTHORIZED_FACTOR_BEFORE_REAL_DEPLOYMENT",
            "notes": "Configurable demonstration factor; not for regulatory reporting",
        },
    ]
    return pd.DataFrame(records)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = [METER_FILE, FUEL_FILE, PRODUCTION_FILE]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing generated inputs: " + ", ".join(missing))

    meters = pd.read_csv(METER_FILE, parse_dates=["timestamp"])
    fuel = pd.read_csv(FUEL_FILE)
    production = pd.read_csv(PRODUCTION_FILE)
    return meters, fuel, production


def create_daily_emissions(
    meters: pd.DataFrame,
    fuel: pd.DataFrame,
    production: pd.DataFrame,
    factors: pd.DataFrame,
) -> pd.DataFrame:
    electricity_factor = float(
        factors.loc[factors["activity_type"] == "PURCHASED_ELECTRICITY", "factor_value"].iloc[0]
    )
    gas_factor = float(
        factors.loc[factors["activity_type"] == "NATURAL_GAS", "factor_value"].iloc[0]
    )
    diesel_factor = float(
        factors.loc[factors["activity_type"] == "DIESEL", "factor_value"].iloc[0]
    )

    daily_meter = (
        meters.groupby(
            ["day_number", "day_in_month", "month_number", "month_label", "month_scenario"],
            as_index=False,
        )
        .agg(
            date=("timestamp", "min"),
            real_usage_kwh=("Usage_kWh", "sum"),
            claimed_main_meter_kwh=("main_incomer_meter_kwh", "sum"),
            verified_reference_kwh=("independent_reference_meter_kwh", "sum"),
            utility_meter_kwh=("utility_billing_meter_kwh", "sum"),
            ems_meter_kwh=("ems_total_meter_kwh", "sum"),
            attack_records=("attack_flag", "sum"),
            repair_events=("repair_event", "sum"),
        )
    )
    daily_meter["date"] = pd.to_datetime(daily_meter["date"]).dt.date.astype(str)

    merged = daily_meter.merge(
        fuel[["day_number", "natural_gas_scm", "diesel_litres"]],
        on="day_number",
        how="inner",
        validate="one_to_one",
    ).merge(
        production[["day_number", "vehicles_produced", "accepted_units"]],
        on="day_number",
        how="inner",
        validate="one_to_one",
    )

    merged["claimed_scope2_kgco2"] = (
        merged["claimed_main_meter_kwh"] * electricity_factor
    )
    merged["verified_scope2_kgco2"] = (
        merged["verified_reference_kwh"] * electricity_factor
    )
    merged["scope1_natural_gas_kgco2e"] = (
        merged["natural_gas_scm"] * gas_factor
    )
    merged["scope1_diesel_kgco2e"] = (
        merged["diesel_litres"] * diesel_factor
    )
    merged["scope1_total_kgco2e"] = (
        merged["scope1_natural_gas_kgco2e"]
        + merged["scope1_diesel_kgco2e"]
    )
    merged["claimed_total_kgco2e"] = (
        merged["claimed_scope2_kgco2"] + merged["scope1_total_kgco2e"]
    )
    merged["verified_total_kgco2e"] = (
        merged["verified_scope2_kgco2"] + merged["scope1_total_kgco2e"]
    )
    merged["emission_discrepancy_kgco2e"] = (
        merged["verified_total_kgco2e"] - merged["claimed_total_kgco2e"]
    )
    merged["emission_discrepancy_percent"] = (
        merged["emission_discrepancy_kgco2e"].abs()
        / merged["verified_total_kgco2e"]
        * 100.0
    )
    merged["verified_emission_intensity_kgco2e_per_vehicle"] = (
        merged["verified_total_kgco2e"] / merged["vehicles_produced"]
    )
    merged["data_origin"] = "SYSTEM_DERIVED"

    numeric_columns = merged.select_dtypes(include="number").columns
    merged[numeric_columns] = merged[numeric_columns].round(6)
    return merged


def create_monthly_claims(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        daily.groupby(
            ["month_number", "month_label", "month_scenario"],
            as_index=False,
        )
        .agg(
            period_start=("date", "min"),
            period_end=("date", "max"),
            claimed_electricity_kwh=("claimed_main_meter_kwh", "sum"),
            verified_electricity_kwh=("verified_reference_kwh", "sum"),
            natural_gas_scm=("natural_gas_scm", "sum"),
            diesel_litres=("diesel_litres", "sum"),
            vehicles_produced=("vehicles_produced", "sum"),
            claimed_scope2_kgco2=("claimed_scope2_kgco2", "sum"),
            verified_scope2_kgco2=("verified_scope2_kgco2", "sum"),
            scope1_total_kgco2e=("scope1_total_kgco2e", "sum"),
            claimed_total_kgco2e=("claimed_total_kgco2e", "sum"),
            verified_total_kgco2e=("verified_total_kgco2e", "sum"),
            attack_records=("attack_records", "sum"),
            repair_events=("repair_events", "sum"),
        )
    )

    monthly["claim_id"] = monthly["month_number"].map(
        lambda value: f"CLAIM-2026-{value:02d}"
    )
    monthly["verification_cycle_id"] = monthly["month_number"].map(
        lambda value: f"VERIFY-2026-{value:02d}"
    )
    monthly["claim_discrepancy_kgco2e"] = (
        monthly["verified_total_kgco2e"] - monthly["claimed_total_kgco2e"]
    )
    monthly["claim_discrepancy_percent"] = (
        monthly["claim_discrepancy_kgco2e"].abs()
        / monthly["verified_total_kgco2e"]
        * 100.0
    )
    monthly["verified_intensity_kgco2e_per_vehicle"] = (
        monthly["verified_total_kgco2e"] / monthly["vehicles_produced"]
    )

    def recommendation(row: pd.Series) -> str:
        if row["month_number"] in (1, 2):
            return "RECOMMEND_APPROVAL"
        if row["month_number"] in (3, 4):
            return "MANUAL_REVIEW"
        return "APPROVAL_AFTER_PROBATION_REVIEW"

    monthly["verification_recommendation"] = monthly.apply(recommendation, axis=1)
    monthly["claim_status"] = "SUBMITTED"
    monthly["data_origin"] = "SYSTEM_DERIVED"
    monthly["is_synthetic_claim"] = True

    ordered_columns = [
        "claim_id",
        "verification_cycle_id",
        "month_number",
        "month_label",
        "month_scenario",
        "period_start",
        "period_end",
        "claimed_electricity_kwh",
        "verified_electricity_kwh",
        "natural_gas_scm",
        "diesel_litres",
        "vehicles_produced",
        "claimed_scope2_kgco2",
        "verified_scope2_kgco2",
        "scope1_total_kgco2e",
        "claimed_total_kgco2e",
        "verified_total_kgco2e",
        "claim_discrepancy_kgco2e",
        "claim_discrepancy_percent",
        "verified_intensity_kgco2e_per_vehicle",
        "attack_records",
        "repair_events",
        "claim_status",
        "verification_recommendation",
        "data_origin",
        "is_synthetic_claim",
    ]

    numeric_columns = monthly.select_dtypes(include="number").columns
    monthly[numeric_columns] = monthly[numeric_columns].round(6)
    return monthly[ordered_columns]


def validate_outputs(
    factors: pd.DataFrame,
    daily: pd.DataFrame,
    claims: pd.DataFrame,
) -> None:
    print("=" * 65)
    print("CARBON CALCULATION DATASET VALIDATION")
    print("=" * 65)
    print("Emission factors:", len(factors))
    print("Daily emission rows:", len(daily))
    print("Monthly claims:", len(claims))
    print("Daily missing values:", int(daily.isna().sum().sum()))
    print("Claim missing values:", int(claims.isna().sum().sum()))

    print()
    print("Monthly claim summary:")
    print(
        claims[
            [
                "claim_id",
                "claim_discrepancy_percent",
                "attack_records",
                "verification_recommendation",
            ]
        ].to_string(index=False)
    )

    if len(factors) != 3:
        raise ValueError("Exactly three emission factors are required.")
    if len(daily) != 150:
        raise ValueError("Daily emission output must contain 150 rows.")
    if len(claims) != 5:
        raise ValueError("Monthly claim output must contain five rows.")
    if daily.isna().any().any() or claims.isna().any().any():
        raise ValueError("Missing values were found in carbon outputs.")
    if (daily["verified_total_kgco2e"] <= 0).any():
        raise ValueError("Verified emissions must be positive.")


def save_outputs(
    factors: pd.DataFrame,
    daily: pd.DataFrame,
    claims: pd.DataFrame,
) -> None:
    factors.to_csv(FACTOR_OUTPUT, index=False)
    daily.to_csv(DAILY_OUTPUT, index=False)
    claims.to_csv(CLAIM_OUTPUT, index=False)

    print()
    print("Files created successfully:")
    print(FACTOR_OUTPUT)
    print(DAILY_OUTPUT)
    print(CLAIM_OUTPUT)


def main() -> None:
    factors = create_emission_factors()
    meters, fuel, production = load_inputs()
    daily = create_daily_emissions(meters, fuel, production, factors)
    claims = create_monthly_claims(daily)
    validate_outputs(factors, daily, claims)
    save_outputs(factors, daily, claims)

    print()
    print("=" * 65)
    print("CARBON CALCULATION AND CLAIM GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
