from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "shop_energy_readings.csv"
PRODUCTION_OUTPUT = PROJECT_ROOT / "datasets" / "generated" / "production_records.csv"
FUEL_OUTPUT = PROJECT_ROOT / "datasets" / "generated" / "fuel_consumption.csv"

RANDOM_SEED = 42
EXPECTED_DAYS = 150


def load_shop_data() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            "shop_energy_readings.csv is missing. "
            "Run shop_energy_generator.py first."
        )

    dataframe = pd.read_csv(INPUT_FILE, parse_dates=["timestamp"])

    if len(dataframe) != 14_400:
        raise ValueError("Shop-energy input must contain exactly 14,400 records.")

    return dataframe


def create_daily_base(dataframe: pd.DataFrame) -> pd.DataFrame:
    daily = (
        dataframe.groupby(
            [
                "day_number",
                "day_in_month",
                "month_number",
                "month_label",
                "month_scenario",
            ],
            as_index=False,
        )
        .agg(
            date=("timestamp", "min"),
            plant_energy_kwh=("Usage_kWh", "sum"),
            paint_shop_kwh=("paint_shop_kwh", "sum"),
            body_shop_kwh=("body_shop_kwh", "sum"),
            press_shop_kwh=("press_shop_kwh", "sum"),
            assembly_shop_kwh=("assembly_shop_kwh", "sum"),
            utilities_kwh=("utilities_kwh", "sum"),
        )
    )

    daily["date"] = pd.to_datetime(daily["date"]).dt.date.astype(str)

    if len(daily) != EXPECTED_DAYS:
        raise ValueError("Daily base must contain exactly 150 records.")

    return daily


def create_production_records(daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    result = daily.copy()

    energy = result["plant_energy_kwh"].to_numpy(dtype=float)
    energy_min = float(energy.min())
    energy_max = float(energy.max())
    energy_range = max(energy_max - energy_min, 1.0)
    normalized_energy = (energy - energy_min) / energy_range

    base_units = 35 + (normalized_energy * 115)
    operational_noise = rng.normal(0.0, 5.0, len(result))
    vehicles_produced = np.rint(base_units + operational_noise).astype(int)
    vehicles_produced = np.clip(vehicles_produced, 10, 180)

    result["vehicles_produced"] = vehicles_produced
    result["planned_vehicles"] = np.rint(vehicles_produced * rng.uniform(1.02, 1.10, len(result))).astype(int)
    result["rejected_units"] = rng.binomial(vehicles_produced, 0.018)
    result["accepted_units"] = result["vehicles_produced"] - result["rejected_units"]
    result["operating_hours"] = np.clip(
        12.0 + normalized_energy * 10.0 + rng.normal(0.0, 0.8, len(result)),
        10.0,
        24.0,
    )
    result["shift_count"] = np.where(result["operating_hours"] >= 20, 3, 2)
    result["energy_intensity_kwh_per_vehicle"] = (
        result["plant_energy_kwh"] / result["vehicles_produced"]
    )
    result["data_origin"] = "CONTROLLED_SIMULATION"
    result["derivation_basis"] = "REAL_DAILY_ENERGY_PATTERN"

    output_columns = [
        "day_number",
        "date",
        "day_in_month",
        "month_number",
        "month_label",
        "month_scenario",
        "plant_energy_kwh",
        "planned_vehicles",
        "vehicles_produced",
        "accepted_units",
        "rejected_units",
        "operating_hours",
        "shift_count",
        "energy_intensity_kwh_per_vehicle",
        "data_origin",
        "derivation_basis",
    ]

    result["plant_energy_kwh"] = result["plant_energy_kwh"].round(6)
    result["operating_hours"] = result["operating_hours"].round(2)
    result["energy_intensity_kwh_per_vehicle"] = result[
        "energy_intensity_kwh_per_vehicle"
    ].round(6)

    return result[output_columns]


def create_fuel_records(daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 1)
    result = daily.copy()

    paint_energy = result["paint_shop_kwh"].to_numpy(dtype=float)
    utility_energy = result["utilities_kwh"].to_numpy(dtype=float)

    natural_gas_scm = (
        0.060 * paint_energy
        + 0.020 * utility_energy
        + rng.normal(0.0, 3.0, len(result))
    )
    natural_gas_scm = np.clip(natural_gas_scm, 1.0, None)

    diesel_litres = (
        3.0
        + 0.0025 * utility_energy
        + rng.normal(0.0, 0.7, len(result))
    )
    diesel_litres = np.clip(diesel_litres, 0.5, None)

    result["natural_gas_scm"] = natural_gas_scm
    result["diesel_litres"] = diesel_litres
    result["natural_gas_source"] = "PAINT_OVEN_AND_BOILER"
    result["diesel_source"] = "BACKUP_GENERATOR"
    result["meter_status"] = "VALID"
    result["data_origin"] = "CONTROLLED_SIMULATION"
    result["derivation_basis"] = "SHOP_ENERGY_AND_UTILITIES_PATTERN"

    output_columns = [
        "day_number",
        "date",
        "day_in_month",
        "month_number",
        "month_label",
        "month_scenario",
        "natural_gas_scm",
        "diesel_litres",
        "natural_gas_source",
        "diesel_source",
        "meter_status",
        "data_origin",
        "derivation_basis",
    ]

    result["natural_gas_scm"] = result["natural_gas_scm"].round(6)
    result["diesel_litres"] = result["diesel_litres"].round(6)

    return result[output_columns]


def validate_outputs(
    production: pd.DataFrame,
    fuel: pd.DataFrame,
) -> None:
    print("=" * 65)
    print("DAILY PRODUCTION AND FUEL VALIDATION")
    print("=" * 65)
    print("Production rows:", len(production))
    print("Fuel rows:", len(fuel))
    print("Production missing values:", int(production.isna().sum().sum()))
    print("Fuel missing values:", int(fuel.isna().sum().sum()))
    print("Minimum vehicles produced:", int(production["vehicles_produced"].min()))
    print("Maximum vehicles produced:", int(production["vehicles_produced"].max()))
    print("Minimum natural gas SCM:", float(fuel["natural_gas_scm"].min()))
    print("Minimum diesel litres:", float(fuel["diesel_litres"].min()))

    print()
    print("Monthly production totals:")
    print(production.groupby("month_number")["vehicles_produced"].sum().to_string())

    print()
    print("Monthly fuel totals:")
    print(
        fuel.groupby("month_number")[["natural_gas_scm", "diesel_litres"]]
        .sum()
        .round(2)
        .to_string()
    )

    if len(production) != EXPECTED_DAYS or len(fuel) != EXPECTED_DAYS:
        raise ValueError("Both outputs must contain exactly 150 daily records.")
    if production.isna().any().any() or fuel.isna().any().any():
        raise ValueError("Missing values were found in generated daily data.")
    if (production["vehicles_produced"] <= 0).any():
        raise ValueError("Production values must be positive.")
    if (production["accepted_units"] < 0).any():
        raise ValueError("Accepted units cannot be negative.")
    if (fuel["natural_gas_scm"] <= 0).any():
        raise ValueError("Natural-gas values must be positive.")
    if (fuel["diesel_litres"] <= 0).any():
        raise ValueError("Diesel values must be positive.")


def save_outputs(
    production: pd.DataFrame,
    fuel: pd.DataFrame,
) -> None:
    production.to_csv(PRODUCTION_OUTPUT, index=False)
    fuel.to_csv(FUEL_OUTPUT, index=False)

    print()
    print("Files created successfully:")
    print(PRODUCTION_OUTPUT)
    print(FUEL_OUTPUT)


def main() -> None:
    shop_data = load_shop_data()
    daily_base = create_daily_base(shop_data)
    production = create_production_records(daily_base)
    fuel = create_fuel_records(daily_base)
    validate_outputs(production, fuel)
    save_outputs(production, fuel)

    print()
    print("=" * 65)
    print("DAILY PRODUCTION AND FUEL GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
