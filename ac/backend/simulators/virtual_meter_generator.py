from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "real_industrial_foundation.csv"
OUTPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "plant_meter_readings.csv"

RANDOM_SEED = 42
EXPECTED_RECORDS = 14_400


def load_foundation() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            "The five-month foundation is missing. "
            "Run five_month_dataset_generator.py first."
        )

    dataframe = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp", "source_timestamp"],
    )

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError(
            "The real foundation must contain exactly 14,400 records."
        )

    return dataframe


def add_normal_meter_measurements(dataframe: pd.DataFrame) -> pd.DataFrame:
    random_generator = np.random.default_rng(RANDOM_SEED)
    result = dataframe.copy()
    real_usage = result["Usage_kWh"].to_numpy(dtype=float)

    result["main_incomer_clean_kwh"] = real_usage * (
        1 + random_generator.normal(0, 0.010, len(result))
    )
    result["utility_billing_meter_kwh"] = real_usage * (
        1 + random_generator.normal(0, 0.006, len(result))
    )
    result["ems_total_meter_kwh"] = real_usage * (
        1 + random_generator.normal(0, 0.012, len(result))
    )
    result["independent_reference_meter_kwh"] = real_usage * (
        1 + random_generator.normal(0, 0.004, len(result))
    )
    result["main_incomer_meter_kwh"] = result[
        "main_incomer_clean_kwh"
    ].copy()

    meter_columns = [
        "main_incomer_clean_kwh",
        "main_incomer_meter_kwh",
        "utility_billing_meter_kwh",
        "ems_total_meter_kwh",
        "independent_reference_meter_kwh",
    ]
    result[meter_columns] = result[meter_columns].clip(lower=0.001)
    return result


def apply_monthly_scenarios(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    result["attack_flag"] = 0
    result["attack_type"] = "NONE"
    result["attack_magnitude_percent"] = 0.0
    result["attacked_source"] = "NONE"
    result["meter_state"] = "NORMAL"
    result["repair_event"] = 0

    month_3_mask = result["month_number"] == 3
    result.loc[month_3_mask, "main_incomer_meter_kwh"] *= 0.92
    result.loc[month_3_mask, "attack_flag"] = 1
    result.loc[month_3_mask, "attack_type"] = "UNDER_REPORTING_8_PERCENT"
    result.loc[month_3_mask, "attack_magnitude_percent"] = 8.0
    result.loc[month_3_mask, "attacked_source"] = "main_incomer_meter_kwh"
    result.loc[month_3_mask, "meter_state"] = "COMPROMISED"

    month_4_large_attack_mask = (
        (result["month_number"] == 4)
        & (result["day_in_month"] <= 15)
    )
    result.loc[
        month_4_large_attack_mask,
        "main_incomer_meter_kwh",
    ] *= 0.65
    result.loc[month_4_large_attack_mask, "attack_flag"] = 1
    result.loc[
        month_4_large_attack_mask,
        "attack_type",
    ] = "UNDER_REPORTING_35_PERCENT"
    result.loc[
        month_4_large_attack_mask,
        "attack_magnitude_percent",
    ] = 35.0
    result.loc[
        month_4_large_attack_mask,
        "attacked_source",
    ] = "main_incomer_meter_kwh"
    result.loc[
        month_4_large_attack_mask,
        "meter_state",
    ] = "COMPROMISED"

    month_4_drift_mask = (
        (result["month_number"] == 4)
        & (result["day_in_month"] >= 16)
    )
    number_of_drift_records = int(month_4_drift_mask.sum())
    drift_values = np.linspace(0.0, 0.15, number_of_drift_records)

    result.loc[
        month_4_drift_mask,
        "main_incomer_meter_kwh",
    ] *= 1.0 - drift_values
    result.loc[month_4_drift_mask, "attack_flag"] = 1
    result.loc[
        month_4_drift_mask,
        "attack_type",
    ] = "GRADUAL_DRIFT_0_TO_15_PERCENT"
    result.loc[
        month_4_drift_mask,
        "attack_magnitude_percent",
    ] = drift_values * 100.0
    result.loc[
        month_4_drift_mask,
        "attacked_source",
    ] = "main_incomer_meter_kwh"
    result.loc[month_4_drift_mask, "meter_state"] = "DRIFTING"

    month_5_mask = result["month_number"] == 5
    result.loc[month_5_mask, "meter_state"] = "REPAIRED"
    first_month_5_index = result.index[month_5_mask][0]
    result.loc[first_month_5_index, "repair_event"] = 1

    return result


def validate_meter_dataset(dataframe: pd.DataFrame) -> None:
    meter_columns = [
        "main_incomer_meter_kwh",
        "utility_billing_meter_kwh",
        "ems_total_meter_kwh",
        "independent_reference_meter_kwh",
    ]

    missing_values = int(dataframe[meter_columns].isna().sum().sum())
    non_positive_values = int((dataframe[meter_columns] <= 0).sum().sum())
    repair_event_count = int(dataframe["repair_event"].sum())

    attack_counts = {
        month: int(
            dataframe.loc[
                dataframe["month_number"] == month,
                "attack_flag",
            ].sum()
        )
        for month in range(1, 6)
    }

    print("=" * 65)
    print("VIRTUAL METER DATASET VALIDATION")
    print("=" * 65)
    print(f"Total records: {len(dataframe):,}")
    print("Missing meter values:", missing_values)
    print("Non-positive meter values:", non_positive_values)
    print("Repair events:", repair_event_count)

    for month, count in attack_counts.items():
        print(f"Month {month} attack records: {count}")

    print("\nScenario counts:")
    print(dataframe.groupby(["month_number", "attack_type"]).size())

    print("\nMeter-state counts:")
    print(dataframe["meter_state"].value_counts())

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError("The meter dataset must contain exactly 14,400 records.")
    if missing_values != 0:
        raise ValueError("Missing virtual-meter values were found.")
    if non_positive_values != 0:
        raise ValueError("Zero or negative meter values were found.")
    if repair_event_count != 1:
        raise ValueError("Exactly one repair event is required.")

    expected_attack_counts = {1: 0, 2: 0, 3: 2880, 4: 2880, 5: 0}
    if attack_counts != expected_attack_counts:
        raise ValueError(
            f"Unexpected monthly attack counts: {attack_counts}"
        )


def save_meter_dataset(dataframe: pd.DataFrame) -> None:
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
        "main_incomer_clean_kwh",
        "main_incomer_meter_kwh",
        "utility_billing_meter_kwh",
        "ems_total_meter_kwh",
        "independent_reference_meter_kwh",
        "attack_flag",
        "attack_type",
        "attack_magnitude_percent",
        "attacked_source",
        "meter_state",
        "repair_event",
        "Load_Type",
        "WeekStatus",
        "Day_Of_Week",
        "data_origin",
        "source_dataset",
    ]

    numeric_columns = [
        "Usage_kWh",
        "main_incomer_clean_kwh",
        "main_incomer_meter_kwh",
        "utility_billing_meter_kwh",
        "ems_total_meter_kwh",
        "independent_reference_meter_kwh",
        "attack_magnitude_percent",
    ]

    result = dataframe.copy()
    result[numeric_columns] = result[numeric_columns].round(6)
    result[output_columns].to_csv(OUTPUT_FILE, index=False)

    print("\nDataset created successfully:")
    print(OUTPUT_FILE)
    print("File size:", f"{OUTPUT_FILE.stat().st_size / 1024:.2f} KB")


def main() -> None:
    foundation = load_foundation()
    meter_data = add_normal_meter_measurements(foundation)
    meter_data = apply_monthly_scenarios(meter_data)
    validate_meter_dataset(meter_data)
    save_meter_dataset(meter_data)

    print("\n" + "=" * 65)
    print("VIRTUAL METER GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
