from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "plant_meter_readings.csv"
OUTPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "shop_energy_readings.csv"

RANDOM_SEED = 42
EXPECTED_RECORDS = 14_400
SHOP_COLUMNS = [
    "paint_shop_kwh",
    "body_shop_kwh",
    "press_shop_kwh",
    "assembly_shop_kwh",
    "utilities_kwh",
]


def load_meter_data() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            "plant_meter_readings.csv is missing. "
            "Run virtual_meter_generator.py first."
        )

    dataframe = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp", "source_timestamp"],
    )

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError("Input must contain exactly 14,400 records.")

    return dataframe


def create_shop_allocations(dataframe: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    result = dataframe.copy()
    total_usage = result["Usage_kWh"].to_numpy(dtype=float)
    load_type = result["Load_Type"].astype(str).to_numpy()

    base_shares = np.column_stack(
        [
            np.full(len(result), 0.30),
            np.full(len(result), 0.20),
            np.full(len(result), 0.18),
            np.full(len(result), 0.17),
            np.full(len(result), 0.15),
        ]
    )

    maximum_mask = load_type == "Maximum_Load"
    medium_mask = load_type == "Medium_Load"
    light_mask = load_type == "Light_Load"

    base_shares[maximum_mask] += np.array([0.020, 0.005, 0.010, 0.000, -0.035])
    base_shares[medium_mask] += np.array([0.010, 0.005, 0.000, 0.000, -0.015])
    base_shares[light_mask] += np.array([-0.015, -0.005, -0.005, -0.005, 0.030])

    natural_variation = rng.normal(0.0, 0.012, size=base_shares.shape)
    shares = np.clip(base_shares + natural_variation, 0.03, None)
    shares = shares / shares.sum(axis=1, keepdims=True)

    shop_values = total_usage[:, None] * shares

    for index, column in enumerate(SHOP_COLUMNS):
        result[column] = shop_values[:, index]

    result["shop_total_kwh"] = result[SHOP_COLUMNS].sum(axis=1)
    result["shop_balance_error_kwh"] = (
        result["shop_total_kwh"] - result["Usage_kWh"]
    )
    result["shop_balance_error_percent"] = (
        result["shop_balance_error_kwh"].abs()
        / result["Usage_kWh"]
        * 100.0
    )
    result["shop_data_origin"] = "CONTROLLED_SIMULATION"
    result["allocation_method"] = "NORMALIZED_DYNAMIC_SHARES"

    return result


def validate_shop_data(dataframe: pd.DataFrame) -> None:
    missing_values = int(dataframe[SHOP_COLUMNS].isna().sum().sum())
    non_positive_values = int((dataframe[SHOP_COLUMNS] <= 0).sum().sum())
    maximum_balance_error = float(
        dataframe["shop_balance_error_percent"].max()
    )

    monthly_totals = dataframe.groupby("month_number")[SHOP_COLUMNS].sum()
    share_summary = monthly_totals.div(monthly_totals.sum(axis=1), axis=0) * 100.0

    print("=" * 65)
    print("SHOP ENERGY DATASET VALIDATION")
    print("=" * 65)
    print(f"Total records: {len(dataframe):,}")
    print("Missing shop values:", missing_values)
    print("Non-positive shop values:", non_positive_values)
    print("Maximum balance error percent:", f"{maximum_balance_error:.10f}")
    print()
    print("Monthly shop shares percent:")
    print(share_summary.round(2).to_string())

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError("Shop dataset must contain exactly 14,400 records.")
    if missing_values != 0:
        raise ValueError("Missing shop-energy values were found.")
    if non_positive_values != 0:
        raise ValueError("Zero or negative shop-energy values were found.")
    if maximum_balance_error > 0.000001:
        raise ValueError("Shop energy does not reconcile with real plant usage.")


def save_shop_data(dataframe: pd.DataFrame) -> None:
    output_columns = [
        "record_number",
        "timestamp",
        "source_timestamp",
        "day_number",
        "day_in_month",
        "month_number",
        "month_label",
        "month_scenario",
        "Usage_kWh",
        "paint_shop_kwh",
        "body_shop_kwh",
        "press_shop_kwh",
        "assembly_shop_kwh",
        "utilities_kwh",
        "shop_total_kwh",
        "shop_balance_error_kwh",
        "shop_balance_error_percent",
        "Load_Type",
        "WeekStatus",
        "Day_Of_Week",
        "shop_data_origin",
        "allocation_method",
    ]

    result = dataframe.copy()
    numeric_columns = [
        "Usage_kWh",
        *SHOP_COLUMNS,
        "shop_total_kwh",
        "shop_balance_error_kwh",
        "shop_balance_error_percent",
    ]
    result[numeric_columns] = result[numeric_columns].round(6)
    result[output_columns].to_csv(OUTPUT_FILE, index=False)

    print()
    print("Dataset created successfully:")
    print(OUTPUT_FILE)
    print("File size:", f"{OUTPUT_FILE.stat().st_size / 1024:.2f} KB")


def main() -> None:
    meter_data = load_meter_data()
    shop_data = create_shop_allocations(meter_data)
    validate_shop_data(shop_data)
    save_shop_data(shop_data)

    print()
    print("=" * 65)
    print("SHOP ENERGY GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
