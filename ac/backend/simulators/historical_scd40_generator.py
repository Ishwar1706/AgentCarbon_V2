from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "plant_meter_readings.csv"
OUTPUT_FILE = PROJECT_ROOT / "datasets" / "generated" / "historical_scd40_readings.csv"

RANDOM_SEED = 42
EXPECTED_RECORDS = 14_400
SENSOR_ID = "SCD40-PAINT-001"
LOCATION = "Paint Shop Demo Point"


def load_meter_data() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            "plant_meter_readings.csv is missing. "
            "Run virtual_meter_generator.py first."
        )

    dataframe = pd.read_csv(INPUT_FILE, parse_dates=["timestamp"])

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError("Input must contain exactly 14,400 records.")

    return dataframe


def create_historical_sensor_data(dataframe: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    result = dataframe[
        [
            "record_number",
            "timestamp",
            "day_number",
            "day_in_month",
            "month_number",
            "month_label",
            "month_scenario",
            "Load_Type",
        ]
    ].copy()

    load_adjustment = result["Load_Type"].map(
        {
            "Light_Load": 0.0,
            "Medium_Load": 110.0,
            "Maximum_Load": 230.0,
        }
    ).fillna(0.0)

    hour = result["timestamp"].dt.hour.to_numpy()
    working_period = ((hour >= 7) & (hour <= 21)).astype(float)

    co2_ppm = (
        520.0
        + load_adjustment.to_numpy(dtype=float)
        + working_period * 90.0
        + rng.normal(0.0, 28.0, len(result))
    )

    temperature_c = (
        25.5
        + working_period * 2.2
        + rng.normal(0.0, 0.8, len(result))
    )

    humidity_percent = (
        58.0
        - working_period * 5.0
        + rng.normal(0.0, 3.0, len(result))
    )

    month_3_mask = result["month_number"] == 3
    co2_ppm[month_3_mask] += np.linspace(0.0, 140.0, int(month_3_mask.sum()))

    month_4_mask = result["month_number"] == 4
    month_4_count = int(month_4_mask.sum())
    co2_ppm[month_4_mask] += np.linspace(80.0, 500.0, month_4_count)

    month_5_mask = result["month_number"] == 5
    co2_ppm[month_5_mask] -= np.linspace(0.0, 90.0, int(month_5_mask.sum()))

    result["sensor_id"] = SENSOR_ID
    result["location"] = LOCATION
    result["sequence_number"] = result["record_number"]
    result["co2_ppm"] = np.clip(co2_ppm, 400.0, 2000.0)
    result["temperature_c"] = np.clip(temperature_c, 18.0, 45.0)
    result["humidity_percent"] = np.clip(humidity_percent, 20.0, 90.0)
    result["device_status"] = "ONLINE"
    result["calibration_status"] = "VALID"
    result["data_origin"] = "SIMULATED_HARDWARE"
    result["sensor_scenario"] = "NORMAL"

    result.loc[month_3_mask, "sensor_scenario"] = "ELEVATED_TREND"
    result.loc[month_4_mask, "sensor_scenario"] = "GRADUAL_CO2_DRIFT"
    result.loc[month_5_mask, "sensor_scenario"] = "POST_MAINTENANCE_RECOVERY"

    result["co2_ppm"] = result["co2_ppm"].round(2)
    result["temperature_c"] = result["temperature_c"].round(2)
    result["humidity_percent"] = result["humidity_percent"].round(2)

    return result


def validate_sensor_data(dataframe: pd.DataFrame) -> None:
    missing_values = int(dataframe.isna().sum().sum())
    duplicate_sequences = int(dataframe["sequence_number"].duplicated().sum())
    invalid_co2 = int(((dataframe["co2_ppm"] < 400) | (dataframe["co2_ppm"] > 2000)).sum())

    print("=" * 65)
    print("HISTORICAL SCD40 DATASET VALIDATION")
    print("=" * 65)
    print(f"Total records: {len(dataframe):,}")
    print("Missing values:", missing_values)
    print("Duplicate sequence numbers:", duplicate_sequences)
    print("CO2 values outside configured range:", invalid_co2)
    print("Minimum CO2 ppm:", float(dataframe["co2_ppm"].min()))
    print("Maximum CO2 ppm:", float(dataframe["co2_ppm"].max()))

    print()
    print("Monthly average CO2 ppm:")
    print(dataframe.groupby("month_number")["co2_ppm"].mean().round(2).to_string())

    print()
    print("Scenario counts:")
    print(dataframe["sensor_scenario"].value_counts().to_string())

    if len(dataframe) != EXPECTED_RECORDS:
        raise ValueError("Historical SCD40 data must contain 14,400 records.")
    if missing_values != 0:
        raise ValueError("Missing values were found.")
    if duplicate_sequences != 0:
        raise ValueError("Duplicate sequence numbers were found.")
    if invalid_co2 != 0:
        raise ValueError("Invalid CO2 values were found.")


def save_sensor_data(dataframe: pd.DataFrame) -> None:
    output_columns = [
        "record_number",
        "timestamp",
        "day_number",
        "day_in_month",
        "month_number",
        "month_label",
        "month_scenario",
        "sensor_id",
        "location",
        "sequence_number",
        "co2_ppm",
        "temperature_c",
        "humidity_percent",
        "device_status",
        "calibration_status",
        "sensor_scenario",
        "data_origin",
    ]

    dataframe[output_columns].to_csv(OUTPUT_FILE, index=False)
    print()
    print("Dataset created successfully:")
    print(OUTPUT_FILE)


def main() -> None:
    meter_data = load_meter_data()
    sensor_data = create_historical_sensor_data(meter_data)
    validate_sensor_data(sensor_data)
    save_sensor_data(sensor_data)

    print()
    print("=" * 65)
    print("HISTORICAL SCD40 GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
