from pathlib import Path

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILE = (
    PROJECT_ROOT
    / "datasets"
    / "source"
    / "Steel_industry_data.csv"
)

GENERATED_DIR = (
    PROJECT_ROOT
    / "datasets"
    / "generated"
)

OUTPUT_FILE = (
    GENERATED_DIR
    / "real_industrial_foundation.csv"
)


# ============================================================
# DATASET CONFIGURATION
# ============================================================

RECORDS_PER_DAY = 96
DAYS_PER_MONTH = 30
NUMBER_OF_MONTHS = 5

FIVE_MONTH_RECORDS = (
    RECORDS_PER_DAY
    * DAYS_PER_MONTH
    * NUMBER_OF_MONTHS
)

RECORDS_PER_MONTH = (
    RECORDS_PER_DAY
    * DAYS_PER_MONTH
)

DEMO_START_DATE = pd.Timestamp(
    "2026-01-01 00:00:00"
)


# ============================================================
# REQUIRED SOURCE COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "Date_Time",
    "Usage_kWh",
    "Lagging_Current_Reactive.Power_kVarh",
    "Leading_Current_Reactive_Power_kVarh",
    "CO2(tCO2)",
    "Lagging_Current_Power_Factor",
    "Leading_Current_Power_Factor",
    "NSM",
    "WeekStatus",
    "Day_Of_Week",
    "Load_Type",
]


NUMERIC_COLUMNS = [
    "Usage_kWh",
    "Lagging_Current_Reactive.Power_kVarh",
    "Leading_Current_Reactive_Power_kVarh",
    "CO2(tCO2)",
    "Lagging_Current_Power_Factor",
    "Leading_Current_Power_Factor",
    "NSM",
]


CATEGORICAL_COLUMNS = [
    "Date_Time",
    "WeekStatus",
    "Day_Of_Week",
    "Load_Type",
]


# ============================================================
# SOURCE DATA VALIDATION
# ============================================================

def validate_source_file() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            "The source dataset was not found.\n"
            f"Expected location: {SOURCE_FILE}\n\n"
            "Upload Steel_industry_data.csv into "
            "datasets/source/ before running the generator."
        )


def validate_required_columns(
    dataframe: pd.DataFrame,
) -> None:
    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            "The source dataset is missing these columns: "
            + ", ".join(missing_columns)
        )


# ============================================================
# LOAD AND CLEAN REAL SOURCE DATA
# ============================================================

def load_and_clean_source_data() -> pd.DataFrame:
    validate_source_file()

    dataframe = pd.read_csv(
        SOURCE_FILE
    )

    dataframe.columns = [
        str(column).strip()
        for column in dataframe.columns
    ]
    # Normalize aliases used by the original UCI/Kaggle steel dataset.
    # This keeps the source CSV untouched and makes fresh environments portable.
    dataframe = dataframe.rename(
        columns={
            "date": "Date_Time",
            "Day_of_week": "Day_Of_Week",
        }
    )
    validate_required_columns(
        dataframe
    )

    raw_timestamps = dataframe["Date_Time"].astype(str).str.strip()
    dataframe["timestamp"] = pd.to_datetime(
        raw_timestamps,
        format="%d/%m/%Y %H:%M",
        errors="coerce",
    )
    unresolved = dataframe["timestamp"].isna()
    if unresolved.any():
        dataframe.loc[unresolved, "timestamp"] = pd.to_datetime(
            raw_timestamps.loc[unresolved],
            format="%d-%m-%Y %H:%M",
            errors="coerce",
        )
    if dataframe["timestamp"].isna().any():
        invalid_examples = raw_timestamps[dataframe["timestamp"].isna()].head(3).tolist()
        raise ValueError(
            "Unsupported Date_Time values. Expected DD/MM/YYYY HH:MM or "
            f"DD-MM-YYYY HH:MM. Examples: {invalid_examples}"
        )

    for column in NUMERIC_COLUMNS:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    aggregation_rules = {
        column: "mean"
        for column in NUMERIC_COLUMNS
    }

    aggregation_rules.update({
        column: "first"
        for column in CATEGORICAL_COLUMNS
    })

    # Duplicate timestamps are combined by averaging numerical
    # measurements and retaining the first categorical value.
    cleaned = (
        dataframe
        .groupby(
            "timestamp",
            as_index=False,
        )
        .agg(aggregation_rules)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    # Replace zero or negative electricity values with missing
    # values and interpolate from neighbouring observations.
    cleaned.loc[
        cleaned["Usage_kWh"] <= 0,
        "Usage_kWh",
    ] = pd.NA

    cleaned["Usage_kWh"] = (
        cleaned["Usage_kWh"]
        .interpolate(
            method="linear",
            limit_direction="both",
        )
    )

    cleaned["Date_Time"] = (
        cleaned["timestamp"]
        .dt.strftime("%d-%m-%Y %H:%M")
    )

    return cleaned


# ============================================================
# VALIDATE CLEANED FULL-YEAR DATA
# ============================================================

def validate_cleaned_data(
    dataframe: pd.DataFrame,
) -> None:
    timestamp_intervals = (
        dataframe["timestamp"]
        .diff()
        .dt.total_seconds()
        .div(60)
        .dropna()
    )

    invalid_intervals = int(
        (timestamp_intervals != 15).sum()
    )

    duplicate_timestamps = int(
        dataframe["timestamp"]
        .duplicated()
        .sum()
    )

    zero_usage_rows = int(
        (
            dataframe["Usage_kWh"] <= 0
        ).sum()
    )

    missing_values = int(
        dataframe.isna()
        .sum()
        .sum()
    )

    print("=" * 65)
    print("CLEANED SOURCE DATA VALIDATION")
    print("=" * 65)

    print(
        f"Rows: {len(dataframe):,}"
    )

    print(
        "Duplicate timestamps:",
        duplicate_timestamps,
    )

    print(
        "Invalid 15-minute intervals:",
        invalid_intervals,
    )

    print(
        "Zero or negative Usage_kWh rows:",
        zero_usage_rows,
    )

    print(
        "Missing values:",
        missing_values,
    )

    print(
        "First timestamp:",
        dataframe["timestamp"].min(),
    )

    print(
        "Last timestamp:",
        dataframe["timestamp"].max(),
    )

    duplicate_timestamp_row = dataframe[
        dataframe["timestamp"]
        == pd.Timestamp(
            "2018-12-31 20:00:00"
        )
    ]

    corrected_zero_row = dataframe[
        dataframe["timestamp"]
        == pd.Timestamp(
            "2018-11-07 00:00:00"
        )
    ]

    print(
        "\nCombined duplicate timestamp:"
    )

    if not duplicate_timestamp_row.empty:
        print(
            duplicate_timestamp_row[
                [
                    "timestamp",
                    "Usage_kWh",
                    (
                        "Leading_Current_"
                        "Reactive_Power_kVarh"
                    ),
                    (
                        "Leading_Current_"
                        "Power_Factor"
                    ),
                ]
            ].to_string(index=False)
        )

    print(
        "\nInterpolated zero-value timestamp:"
    )

    if not corrected_zero_row.empty:
        print(
            corrected_zero_row[
                [
                    "timestamp",
                    "Usage_kWh",
                    "Load_Type",
                ]
            ].to_string(index=False)
        )

    if len(dataframe) != 35040:
        raise ValueError(
            "The cleaned dataset must contain "
            "exactly 35,040 unique timestamps."
        )

    if duplicate_timestamps != 0:
        raise ValueError(
            "Duplicate timestamps remain after cleaning."
        )

    if invalid_intervals != 0:
        raise ValueError(
            "The cleaned dataset is not continuous "
            "at 15-minute intervals."
        )

    if zero_usage_rows != 0:
        raise ValueError(
            "Zero or negative Usage_kWh values remain."
        )

    if missing_values != 0:
        raise ValueError(
            "Missing values remain after cleaning."
        )


# ============================================================
# SELECT THE BEST CONTINUOUS FIVE-MONTH PERIOD
# ============================================================

def select_five_month_period(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if len(dataframe) < FIVE_MONTH_RECORDS:
        raise ValueError(
            "The source dataset does not contain enough "
            "records for five 30-day months."
        )

    candidate_windows = []

    # Move one day at a time while evaluating possible
    # continuous 150-day periods.
    for start_index in range(
        0,
        len(dataframe) - FIVE_MONTH_RECORDS + 1,
        RECORDS_PER_DAY,
    ):
        candidate = dataframe.iloc[
            start_index:
            start_index + FIVE_MONTH_RECORDS
        ]

        usage_mean = float(
            candidate["Usage_kWh"].mean()
        )

        usage_standard_deviation = float(
            candidate["Usage_kWh"].std()
        )

        coefficient_of_variation = (
            usage_standard_deviation / usage_mean
            if usage_mean > 0
            else 0.0
        )

        load_type_count = int(
            candidate["Load_Type"].nunique()
        )

        maximum_load_ratio = float(
            (
                candidate["Load_Type"]
                == "Maximum_Load"
            ).mean()
        )

        medium_load_ratio = float(
            (
                candidate["Load_Type"]
                == "Medium_Load"
            ).mean()
        )

        light_load_ratio = float(
            (
                candidate["Load_Type"]
                == "Light_Load"
            ).mean()
        )

        # Reward windows containing all three load categories
        # and meaningful natural electricity variation.
        selection_score = (
            load_type_count
            + min(
                coefficient_of_variation,
                1.0,
            )
            + maximum_load_ratio
            + medium_load_ratio
            + light_load_ratio
        )

        candidate_windows.append({
            "start_index": start_index,
            "score": selection_score,
            "coefficient_of_variation": (
                coefficient_of_variation
            ),
            "load_type_count": load_type_count,
        })

    if not candidate_windows:
        raise ValueError(
            "No valid five-month candidate window "
            "could be created."
        )

    best_window = max(
        candidate_windows,
        key=lambda item: item["score"],
    )

    start_index = int(
        best_window["start_index"]
    )

    selected = dataframe.iloc[
        start_index:
        start_index + FIVE_MONTH_RECORDS
    ].copy()

    selected = selected.reset_index(
        drop=True
    )

    # Preserve the original timestamp for traceability.
    selected["source_timestamp"] = (
        selected["timestamp"]
    )

    # Remap the timestamps to a five-month demonstration
    # period while keeping the real measured values unchanged.
    selected["timestamp"] = pd.date_range(
        start=DEMO_START_DATE,
        periods=FIVE_MONTH_RECORDS,
        freq="15min",
    )

    selected["record_number"] = range(
        1,
        FIVE_MONTH_RECORDS + 1,
    )

    selected["day_number"] = (
        selected["record_number"]
        .sub(1)
        .floordiv(RECORDS_PER_DAY)
        .add(1)
    )

    selected["month_number"] = (
        selected["day_number"]
        .sub(1)
        .floordiv(DAYS_PER_MONTH)
        .add(1)
    )

    selected["day_in_month"] = (
        selected["day_number"]
        .sub(1)
        .mod(DAYS_PER_MONTH)
        .add(1)
    )

    selected["month_label"] = (
        "Month_"
        + selected["month_number"].astype(str)
    )

    scenario_mapping = {
        1: "NORMAL_BASELINE",
        2: "NORMAL_VARIATION",
        3: "SUBTLE_UNDER_REPORTING",
        4: "MAJOR_SPOOFING_AND_DRIFT",
        5: "REPAIR_AND_RECOVERY",
    }

    selected["month_scenario"] = (
        selected["month_number"]
        .map(scenario_mapping)
    )

    selected["data_origin"] = (
        "PUBLIC_REAL_DATA"
    )

    selected["source_dataset"] = (
        "UCI_STEEL_INDUSTRY_ENERGY_CONSUMPTION"
    )

    selected["is_synthetic"] = False

    print(
        "\nSelected source-data window:"
    )

    print(
        "Start index:",
        start_index,
    )

    print(
        "Selection score:",
        round(
            float(best_window["score"]),
            6,
        ),
    )

    print(
        "Coefficient of variation:",
        round(
            float(
                best_window[
                    "coefficient_of_variation"
                ]
            ),
            6,
        ),
    )

    return selected


# ============================================================
# VALIDATE THE FIVE-MONTH PERIOD
# ============================================================

def validate_five_month_period(
    dataframe: pd.DataFrame,
) -> None:
    rows_per_month = (
        dataframe
        .groupby("month_number")
        .size()
        .to_dict()
    )

    scenario_per_month = (
        dataframe
        .groupby("month_number")[
            "month_scenario"
        ]
        .first()
        .to_dict()
    )

    timestamp_intervals = (
        dataframe["timestamp"]
        .diff()
        .dt.total_seconds()
        .div(60)
        .dropna()
    )

    source_timestamp_intervals = (
        dataframe["source_timestamp"]
        .diff()
        .dt.total_seconds()
        .div(60)
        .dropna()
    )

    invalid_demo_intervals = int(
        (timestamp_intervals != 15).sum()
    )

    invalid_source_intervals = int(
        (
            source_timestamp_intervals != 15
        ).sum()
    )

    duplicate_demo_timestamps = int(
        dataframe["timestamp"]
        .duplicated()
        .sum()
    )

    missing_values = int(
        dataframe.isna()
        .sum()
        .sum()
    )

    print("\n" + "=" * 65)
    print("FIVE-MONTH FOUNDATION VALIDATION")
    print("=" * 65)

    print(
        f"Total records: {len(dataframe):,}"
    )

    print(
        "Demonstration period:",
        dataframe["timestamp"].min(),
        "to",
        dataframe["timestamp"].max(),
    )

    print(
        "Original source period:",
        dataframe["source_timestamp"].min(),
        "to",
        dataframe["source_timestamp"].max(),
    )

    print(
        "Rows per month:",
        rows_per_month,
    )

    print(
        "Scenarios:",
        scenario_per_month,
    )

    print(
        "Invalid demonstration intervals:",
        invalid_demo_intervals,
    )

    print(
        "Invalid source intervals:",
        invalid_source_intervals,
    )

    print(
        "Duplicate demonstration timestamps:",
        duplicate_demo_timestamps,
    )

    print(
        "Missing values:",
        missing_values,
    )

    print(
        "Load-type counts:",
        dataframe[
            "Load_Type"
        ].value_counts().to_dict(),
    )

    print(
        "Usage_kWh range:",
        round(
            float(
                dataframe["Usage_kWh"].min()
            ),
            3,
        ),
        "to",
        round(
            float(
                dataframe["Usage_kWh"].max()
            ),
            3,
        ),
    )

    print(
        "Usage_kWh mean:",
        round(
            float(
                dataframe["Usage_kWh"].mean()
            ),
            3,
        ),
    )

    if len(dataframe) != FIVE_MONTH_RECORDS:
        raise ValueError(
            "The selected period must contain "
            "exactly 14,400 records."
        )

    expected_months = {
        1,
        2,
        3,
        4,
        5,
    }

    actual_months = set(
        dataframe[
            "month_number"
        ].unique()
    )

    if actual_months != expected_months:
        raise ValueError(
            "The output does not contain exactly "
            "five demonstration months."
        )

    if any(
        count != RECORDS_PER_MONTH
        for count in rows_per_month.values()
    ):
        raise ValueError(
            "Each demonstration month must contain "
            "exactly 2,880 records."
        )

    if invalid_demo_intervals != 0:
        raise ValueError(
            "Demonstration timestamps are not "
            "continuous at 15-minute intervals."
        )

    if invalid_source_intervals != 0:
        raise ValueError(
            "The selected source period is not "
            "continuous at 15-minute intervals."
        )

    if duplicate_demo_timestamps != 0:
        raise ValueError(
            "Duplicate demonstration timestamps exist."
        )

    if missing_values != 0:
        raise ValueError(
            "Missing values exist in the "
            "five-month foundation."
        )

    if dataframe["Load_Type"].nunique() < 3:
        raise ValueError(
            "The selected period must contain "
            "Light, Medium, and Maximum load types."
        )

    if (
        dataframe["Usage_kWh"] <= 0
    ).any():
        raise ValueError(
            "The five-month dataset contains "
            "zero or negative electricity usage."
        )


# ============================================================
# SAVE THE REAL INDUSTRIAL FOUNDATION
# ============================================================

def save_real_foundation(
    dataframe: pd.DataFrame,
) -> Path:
    GENERATED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        (
            "Lagging_Current_"
            "Reactive.Power_kVarh"
        ),
        (
            "Leading_Current_"
            "Reactive_Power_kVarh"
        ),
        "CO2(tCO2)",
        (
            "Lagging_Current_"
            "Power_Factor"
        ),
        (
            "Leading_Current_"
            "Power_Factor"
        ),
        "NSM",
        "WeekStatus",
        "Day_Of_Week",
        "Load_Type",
        "data_origin",
        "source_dataset",
        "is_synthetic",
    ]

    dataframe[
        output_columns
    ].to_csv(
        OUTPUT_FILE,
        index=False,
    )

    return OUTPUT_FILE


# ============================================================
# DISPLAY FINAL SUMMARY
# ============================================================

def display_output_summary(
    output_path: Path,
) -> None:
    saved_data = pd.read_csv(
        output_path
    )

    print("\n" + "=" * 65)
    print("GENERATED FILE SUMMARY")
    print("=" * 65)

    print(
        "Output file:",
        output_path,
    )

    print(
        "File rows:",
        f"{len(saved_data):,}",
    )

    print(
        "File columns:",
        len(saved_data.columns),
    )

    print(
        "File size:",
        f"{output_path.stat().st_size / 1024:.2f} KB",
    )

    print("\nFirst record:")

    print(
        saved_data.head(1)
        .to_string(index=False)
    )

    print("\nLast record:")

    print(
        saved_data.tail(1)
        .to_string(index=False)
    )


# ============================================================
# MAIN EXECUTION
# ============================================================

def main() -> None:
    cleaned_data = load_and_clean_source_data()

    validate_cleaned_data(
        cleaned_data
    )

    five_month_data = select_five_month_period(
        cleaned_data
    )

    validate_five_month_period(
        five_month_data
    )

    output_path = save_real_foundation(
        five_month_data
    )

    display_output_summary(
        output_path
    )

    print("\n" + "=" * 65)
    print("DATASET GENERATION COMPLETED SUCCESSFULLY")
    print("=" * 65)

    print(
        "\nThe generated file contains the real "
        "industrial operating foundation only."
    )

    print(
        "Virtual meters, attacks, shop-level data, "
        "production data, and trust events will be "
        "added in the next stage."
    )


if __name__ == "__main__":
    main()
