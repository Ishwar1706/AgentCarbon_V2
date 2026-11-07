from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
METER_FILE = PROJECT_ROOT / "datasets" / "generated" / "plant_meter_readings.csv"
SENSOR_FILE = PROJECT_ROOT / "datasets" / "generated" / "historical_scd40_readings.csv"
CALIBRATION_OUTPUT = PROJECT_ROOT / "datasets" / "generated" / "calibration_events.csv"
MAINTENANCE_OUTPUT = PROJECT_ROOT / "datasets" / "generated" / "maintenance_events.csv"
TRUST_OUTPUT = PROJECT_ROOT / "datasets" / "generated" / "trust_lifecycle_events.csv"


def verify_inputs() -> None:
    missing_files = [
        str(path)
        for path in [METER_FILE, SENSOR_FILE]
        if not path.exists()
    ]

    if missing_files:
        raise FileNotFoundError(
            "Required generated files are missing: "
            + ", ".join(missing_files)
        )


def create_calibration_events() -> pd.DataFrame:
    records = [
        {
            "event_id": "CAL-MAIN-001",
            "source_id": "MTR-MAIN-001",
            "source_type": "ELECTRICITY_METER",
            "event_timestamp": "2025-12-20T10:00:00+05:30",
            "calibration_status": "VALID",
            "calibration_method": "REFERENCE_METER_COMPARISON",
            "certificate_id": "CERT-MAIN-2025-001",
            "valid_from": "2025-12-20",
            "valid_until": "2026-12-19",
            "accuracy_class": "CLASS_0.5",
            "performed_by": "AUTHORIZED_DEMO_CALIBRATION_LAB",
            "document_type": "SYNTHETIC_CALIBRATION_CERTIFICATE",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "CAL-UTILITY-001",
            "source_id": "MTR-UTILITY-001",
            "source_type": "ELECTRICITY_METER",
            "event_timestamp": "2025-12-21T10:00:00+05:30",
            "calibration_status": "VALID",
            "calibration_method": "REFERENCE_METER_COMPARISON",
            "certificate_id": "CERT-UTILITY-2025-001",
            "valid_from": "2025-12-21",
            "valid_until": "2026-12-20",
            "accuracy_class": "CLASS_0.5",
            "performed_by": "AUTHORIZED_DEMO_CALIBRATION_LAB",
            "document_type": "SYNTHETIC_CALIBRATION_CERTIFICATE",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "CAL-EMS-001",
            "source_id": "MTR-EMS-001",
            "source_type": "ELECTRICITY_METER",
            "event_timestamp": "2025-12-22T10:00:00+05:30",
            "calibration_status": "VALID",
            "calibration_method": "REFERENCE_METER_COMPARISON",
            "certificate_id": "CERT-EMS-2025-001",
            "valid_from": "2025-12-22",
            "valid_until": "2026-12-21",
            "accuracy_class": "CLASS_1.0",
            "performed_by": "AUTHORIZED_DEMO_CALIBRATION_LAB",
            "document_type": "SYNTHETIC_CALIBRATION_CERTIFICATE",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "CAL-REFERENCE-001",
            "source_id": "MTR-REFERENCE-001",
            "source_type": "ELECTRICITY_METER",
            "event_timestamp": "2025-12-23T10:00:00+05:30",
            "calibration_status": "VALID",
            "calibration_method": "LAB_STANDARD_COMPARISON",
            "certificate_id": "CERT-REFERENCE-2025-001",
            "valid_from": "2025-12-23",
            "valid_until": "2026-12-22",
            "accuracy_class": "CLASS_0.2",
            "performed_by": "AUTHORIZED_DEMO_CALIBRATION_LAB",
            "document_type": "SYNTHETIC_CALIBRATION_CERTIFICATE",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "CAL-SCD40-001",
            "source_id": "SCD40-PAINT-001",
            "source_type": "CO2_SENSOR",
            "event_timestamp": "2025-12-24T10:00:00+05:30",
            "calibration_status": "VALID",
            "calibration_method": "CONTROLLED_REFERENCE_ENVIRONMENT",
            "certificate_id": "CERT-SCD40-2025-001",
            "valid_from": "2025-12-24",
            "valid_until": "2026-06-23",
            "accuracy_class": "PROTOTYPE_ENVIRONMENTAL_SENSOR",
            "performed_by": "AGENTCARBON_DEMO_TEAM",
            "document_type": "SYNTHETIC_CALIBRATION_CERTIFICATE",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
    ]

    return pd.DataFrame(records)


def create_maintenance_events() -> pd.DataFrame:
    records = [
        {
            "event_id": "INV-MAIN-001",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-03-10T09:00:00+05:30",
            "event_type": "ANOMALY_INVESTIGATION_OPENED",
            "work_order_id": "WO-MAIN-2026-001",
            "reported_issue": "PERSISTENT_UNDER_REPORTING",
            "action_taken": "REMOTE_DIAGNOSTIC_REVIEW",
            "result": "FIELD_INSPECTION_REQUIRED",
            "verified_by": "DEMO_MAINTENANCE_SUPERVISOR",
            "document_type": "SYNTHETIC_WORK_ORDER",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "MAINT-MAIN-001",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-04-30T18:00:00+05:30",
            "event_type": "METER_REPAIR_COMPLETED",
            "work_order_id": "WO-MAIN-2026-002",
            "reported_issue": "CALIBRATION_DRIFT_AND_UNDER_REPORTING",
            "action_taken": "METER_REPAIRED_AND_RECALIBRATED",
            "result": "SOURCE_READY_FOR_PROBATION",
            "verified_by": "DEMO_MAINTENANCE_SUPERVISOR",
            "document_type": "SYNTHETIC_WORK_ORDER",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
        {
            "event_id": "MAINT-SCD40-001",
            "source_id": "SCD40-PAINT-001",
            "event_timestamp": "2026-04-30T18:30:00+05:30",
            "event_type": "SENSOR_INSPECTION_COMPLETED",
            "work_order_id": "WO-SCD40-2026-001",
            "reported_issue": "ELEVATED_TREND_REVIEW",
            "action_taken": "SENSOR_CLEANED_AND_REFERENCE_CHECKED",
            "result": "SENSOR_OPERATION_CONFIRMED",
            "verified_by": "DEMO_MAINTENANCE_SUPERVISOR",
            "document_type": "SYNTHETIC_WORK_ORDER",
            "data_origin": "SYNTHETIC_DOCUMENT",
            "is_synthetic": True,
        },
    ]

    return pd.DataFrame(records)


def create_trust_lifecycle_events() -> pd.DataFrame:
    records = [
        {
            "event_id": "TRUST-MAIN-001",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-01-01T00:00:00+05:30",
            "previous_state": "REGISTERED",
            "new_state": "TRUSTED",
            "reason": "VALID_CALIBRATION_AND_NORMAL_BASELINE",
            "trigger_type": "SYSTEM_INITIALIZATION",
            "related_work_order_id": "NONE",
            "data_origin": "SYSTEM_DERIVED",
        },
        {
            "event_id": "TRUST-MAIN-002",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-03-01T00:30:00+05:30",
            "previous_state": "TRUSTED",
            "new_state": "WARNING",
            "reason": "PERSISTENT_DISAGREEMENT_WITH_INDEPENDENT_METERS",
            "trigger_type": "AUTOMATED_TRUST_RULE",
            "related_work_order_id": "WO-MAIN-2026-001",
            "data_origin": "SYSTEM_DERIVED",
        },
        {
            "event_id": "TRUST-MAIN-003",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-03-10T09:15:00+05:30",
            "previous_state": "WARNING",
            "new_state": "PENALIZED",
            "reason": "CONFIRMED_REPEATED_UNDER_REPORTING",
            "trigger_type": "AUTOMATED_TRUST_RULE",
            "related_work_order_id": "WO-MAIN-2026-001",
            "data_origin": "SYSTEM_DERIVED",
        },
        {
            "event_id": "TRUST-MAIN-004",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-04-30T18:00:00+05:30",
            "previous_state": "PENALIZED",
            "new_state": "REPAIRED",
            "reason": "VERIFIED_MAINTENANCE_EVENT_RECEIVED",
            "trigger_type": "VERIFIED_DOCUMENT_EVENT",
            "related_work_order_id": "WO-MAIN-2026-002",
            "data_origin": "SYSTEM_DERIVED",
        },
        {
            "event_id": "TRUST-MAIN-005",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-05-01T00:00:00+05:30",
            "previous_state": "REPAIRED",
            "new_state": "PROBATION",
            "reason": "CONTROLLED_POST_REPAIR_MONITORING_STARTED",
            "trigger_type": "TRUST_RECOVERY_RULE",
            "related_work_order_id": "WO-MAIN-2026-002",
            "data_origin": "SYSTEM_DERIVED",
        },
        {
            "event_id": "TRUST-MAIN-006",
            "source_id": "MTR-MAIN-001",
            "event_timestamp": "2026-05-01T12:00:00+05:30",
            "previous_state": "PROBATION",
            "new_state": "REHABILITATED",
            "reason": "FORTY_EIGHT_CONSISTENT_POST_REPAIR_RECORDS",
            "trigger_type": "TRUST_RECOVERY_RULE",
            "related_work_order_id": "WO-MAIN-2026-002",
            "data_origin": "SYSTEM_DERIVED",
        },
    ]

    return pd.DataFrame(records)


def validate_outputs(
    calibration: pd.DataFrame,
    maintenance: pd.DataFrame,
    trust: pd.DataFrame,
) -> None:
    event_frames = [calibration, maintenance, trust]
    total_missing = sum(int(frame.isna().sum().sum()) for frame in event_frames)
    all_event_ids = pd.concat([frame["event_id"] for frame in event_frames])
    duplicate_event_ids = int(all_event_ids.duplicated().sum())

    main_meter_states = trust.loc[
        trust["source_id"] == "MTR-MAIN-001",
        "new_state",
    ].tolist()

    expected_states = [
        "TRUSTED",
        "WARNING",
        "PENALIZED",
        "REPAIRED",
        "PROBATION",
        "REHABILITATED",
    ]

    print("=" * 65)
    print("EVIDENCE EVENT DATASET VALIDATION")
    print("=" * 65)
    print("Calibration events:", len(calibration))
    print("Maintenance events:", len(maintenance))
    print("Trust lifecycle events:", len(trust))
    print("Missing values:", total_missing)
    print("Duplicate event IDs:", duplicate_event_ids)
    print("Main-meter trust states:", " -> ".join(main_meter_states))

    if len(calibration) != 5:
        raise ValueError("Exactly five calibration events are required.")
    if len(maintenance) != 3:
        raise ValueError("Exactly three maintenance events are required.")
    if len(trust) != 6:
        raise ValueError("Exactly six trust lifecycle events are required.")
    if total_missing != 0:
        raise ValueError("Missing values were found in event datasets.")
    if duplicate_event_ids != 0:
        raise ValueError("Duplicate event IDs were found.")
    if main_meter_states != expected_states:
        raise ValueError("The main-meter trust lifecycle is invalid.")


def save_outputs(
    calibration: pd.DataFrame,
    maintenance: pd.DataFrame,
    trust: pd.DataFrame,
) -> None:
    calibration.to_csv(CALIBRATION_OUTPUT, index=False)
    maintenance.to_csv(MAINTENANCE_OUTPUT, index=False)
    trust.to_csv(TRUST_OUTPUT, index=False)

    print()
    print("Files created successfully:")
    print(CALIBRATION_OUTPUT)
    print(MAINTENANCE_OUTPUT)
    print(TRUST_OUTPUT)


def main() -> None:
    verify_inputs()
    calibration = create_calibration_events()
    maintenance = create_maintenance_events()
    trust = create_trust_lifecycle_events()
    validate_outputs(calibration, maintenance, trust)
    save_outputs(calibration, maintenance, trust)

    print()
    print("=" * 65)
    print("EVIDENCE EVENT GENERATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
