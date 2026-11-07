from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd


METER_COLUMNS: Final[list[str]] = [
    "main_incomer_meter_kwh",
    "utility_billing_meter_kwh",
    "ems_total_meter_kwh",
    "independent_reference_meter_kwh",
]

SUPPORTING_METER_COLUMNS: Final[list[str]] = [
    "utility_billing_meter_kwh",
    "ems_total_meter_kwh",
    "independent_reference_meter_kwh",
]


@dataclass(frozen=True)
class TrustConfig:
    initial_trust: float = 0.90
    minimum_trust: float = 0.05
    maximum_trust: float = 0.99
    warning_trust_threshold: float = 0.80
    penalized_trust_threshold: float = 0.60
    rehabilitation_trust_threshold: float = 0.80
    attack_ema_alpha: float = 0.70
    normal_ema_alpha: float = 0.95
    recovery_ema_alpha: float = 0.97
    persistence_required: int = 3
    probation_records_required: int = 48
    minimum_warning_disparity: float = 0.04
    minimum_severe_disparity: float = 0.08
    supporting_meter_trust: tuple[float, float, float] = (0.94, 0.92, 0.97)


class DynamicTrustEngine:
    """Static-vs-dynamic trust analysis for four plant electricity meters.

    Ground-truth columns such as attack_flag and attack_type are never used by
    the detection or trust-update logic. They are retained only for evaluation.
    """

    def __init__(self, config: TrustConfig | None = None) -> None:
        self.config = config or TrustConfig()

    @staticmethod
    def _validate_input(dataframe: pd.DataFrame) -> None:
        required = {
            "record_number",
            "timestamp",
            "month_number",
            "Usage_kWh",
            "repair_event",
            *METER_COLUMNS,
        }
        missing = sorted(required.difference(dataframe.columns))
        if missing:
            raise ValueError("Missing trust-engine columns: " + ", ".join(missing))
        if dataframe.empty:
            raise ValueError("Trust-engine input cannot be empty.")
        if dataframe["record_number"].duplicated().any():
            raise ValueError("record_number values must be unique.")
        if dataframe[METER_COLUMNS].isna().any().any():
            raise ValueError("Meter readings cannot contain missing values.")
        if (dataframe[METER_COLUMNS] <= 0).any().any():
            raise ValueError("Meter readings must be positive.")

    def calibrate_thresholds(self, dataframe: pd.DataFrame) -> tuple[float, float]:
        calibration = dataframe.loc[dataframe["month_number"] == 1]
        if calibration.empty:
            calibration = dataframe.iloc[: min(2880, len(dataframe))]

        main_values = calibration["main_incomer_meter_kwh"].to_numpy(float)
        support_values = calibration[SUPPORTING_METER_COLUMNS].to_numpy(float)
        references = np.median(support_values, axis=1)
        disparities = np.abs(main_values - references) / np.maximum(
            np.abs(references), 1e-9
        )

        median_disparity = float(np.median(disparities))
        mad = float(np.median(np.abs(disparities - median_disparity)))
        robust_sigma = 1.4826 * mad

        warning = max(
            median_disparity + 6.0 * robust_sigma,
            self.config.minimum_warning_disparity,
        )
        severe = max(
            warning * 2.0,
            self.config.minimum_severe_disparity,
        )
        return float(warning), float(severe)

    def _reliability_score(
        self,
        disparity: float,
        warning_threshold: float,
        severe_threshold: float,
    ) -> float:
        if disparity <= warning_threshold:
            score = np.exp(
                -0.5 * (disparity / max(warning_threshold, 1e-9)) ** 2
            )
        elif disparity <= severe_threshold:
            position = (disparity - warning_threshold) / max(
                severe_threshold - warning_threshold, 1e-9
            )
            score = 0.70 * (1.0 - position)
        else:
            score = 0.10 * np.exp(-12.0 * (disparity - severe_threshold))

        return float(
            np.clip(score, self.config.minimum_trust, self.config.maximum_trust)
        )

    def analyze(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        self._validate_input(dataframe)
        result = dataframe.copy().sort_values("record_number").reset_index(drop=True)
        result["timestamp"] = pd.to_datetime(result["timestamp"], errors="raise")

        warning_threshold, severe_threshold = self.calibrate_thresholds(result)
        row_count = len(result)

        output: dict[str, list] = {
            "static_fused_kwh": [],
            "dynamic_fused_kwh": [],
            "supporting_reference_kwh": [],
            "main_meter_disparity": [],
            "main_meter_reliability": [],
            "main_meter_trust": [],
            "main_meter_dynamic_weight": [],
            "static_main_meter_weight": [],
            "fault_detected": [],
            "trust_state": [],
            "static_absolute_error": [],
            "dynamic_absolute_error": [],
            "warning_disparity_threshold": [],
            "severe_disparity_threshold": [],
        }

        current_trust = self.config.initial_trust
        suspicious_streak = 0
        probation_counter = 0
        maintenance_seen = False

        support_trust = np.asarray(self.config.supporting_meter_trust, dtype=float)

        meter_matrix = result[METER_COLUMNS].to_numpy(dtype=float)
        repair_array = result["repair_event"].to_numpy(dtype=int)
        usage_array = result["Usage_kWh"].to_numpy(dtype=float)

        for position in range(row_count):
            meter_values = meter_matrix[position]
            main_value = float(meter_values[0])
            support_values = meter_values[1:]
            reference_value = float(np.median(support_values))
            disparity = float(
                abs(main_value - reference_value) / max(abs(reference_value), 1e-9)
            )
            reliability = self._reliability_score(
                disparity, warning_threshold, severe_threshold
            )

            repair_event = int(repair_array[position]) == 1
            if repair_event:
                maintenance_seen = True
                probation_counter = 0
                suspicious_streak = 0

            if disparity > warning_threshold:
                suspicious_streak += 1
            else:
                suspicious_streak = 0

            fault_detected = suspicious_streak >= self.config.persistence_required

            if not maintenance_seen:
                alpha = (
                    self.config.attack_ema_alpha
                    if fault_detected
                    else self.config.normal_ema_alpha
                )
                current_trust = (
                    alpha * current_trust + (1.0 - alpha) * reliability
                )
            else:
                if disparity <= warning_threshold:
                    probation_counter += 1
                    current_trust = (
                        self.config.recovery_ema_alpha * current_trust
                        + (1.0 - self.config.recovery_ema_alpha)
                        * self.config.maximum_trust
                    )
                else:
                    probation_counter = 0
                    current_trust = (
                        self.config.attack_ema_alpha * current_trust
                        + (1.0 - self.config.attack_ema_alpha) * reliability
                    )

            current_trust = float(
                np.clip(
                    current_trust,
                    self.config.minimum_trust,
                    self.config.maximum_trust,
                )
            )

            if maintenance_seen:
                if (
                    probation_counter >= self.config.probation_records_required
                    and current_trust >= self.config.rehabilitation_trust_threshold
                ):
                    state = "REHABILITATED"
                else:
                    state = "PROBATION"
            elif current_trust < self.config.penalized_trust_threshold:
                state = "PENALIZED"
            elif current_trust < self.config.warning_trust_threshold:
                state = "WARNING"
            else:
                state = "TRUSTED"

            static_weights = np.full(4, 0.25, dtype=float)
            trust_vector = np.concatenate(([current_trust], support_trust))
            dynamic_weights = trust_vector / trust_vector.sum()

            static_fused = float(np.sum(static_weights * meter_values))
            dynamic_fused = float(np.sum(dynamic_weights * meter_values))
            ground_truth = float(usage_array[position])

            output["static_fused_kwh"].append(static_fused)
            output["dynamic_fused_kwh"].append(dynamic_fused)
            output["supporting_reference_kwh"].append(reference_value)
            output["main_meter_disparity"].append(disparity)
            output["main_meter_reliability"].append(reliability)
            output["main_meter_trust"].append(current_trust)
            output["main_meter_dynamic_weight"].append(float(dynamic_weights[0]))
            output["static_main_meter_weight"].append(0.25)
            output["fault_detected"].append(int(fault_detected))
            output["trust_state"].append(state)
            output["static_absolute_error"].append(abs(static_fused - ground_truth))
            output["dynamic_absolute_error"].append(abs(dynamic_fused - ground_truth))
            output["warning_disparity_threshold"].append(warning_threshold)
            output["severe_disparity_threshold"].append(severe_threshold)

        for column, values in output.items():
            result[column] = values

        numeric_output_columns = [
            column
            for column in output
            if column not in {"fault_detected", "trust_state"}
        ]
        result[numeric_output_columns] = result[numeric_output_columns].round(8)
        return result

    @staticmethod
    def summarize(analyzed: pd.DataFrame) -> pd.DataFrame:
        required = {
            "month_number",
            "month_label",
            "month_scenario",
            "static_absolute_error",
            "dynamic_absolute_error",
            "main_meter_trust",
            "main_meter_dynamic_weight",
            "fault_detected",
        }
        missing = required.difference(analyzed.columns)
        if missing:
            raise ValueError("Analyze the dataset before creating a summary.")

        summary = (
            analyzed.groupby(
                ["month_number", "month_label", "month_scenario"],
                as_index=False,
            )
            .agg(
                static_mae_kwh=("static_absolute_error", "mean"),
                dynamic_mae_kwh=("dynamic_absolute_error", "mean"),
                minimum_main_meter_trust=("main_meter_trust", "min"),
                final_main_meter_trust=("main_meter_trust", "last"),
                minimum_main_meter_weight=("main_meter_dynamic_weight", "min"),
                detected_records=("fault_detected", "sum"),
            )
        )
        summary["mae_reduction_percent"] = np.where(
            summary["static_mae_kwh"] > 0,
            (
                (summary["static_mae_kwh"] - summary["dynamic_mae_kwh"])
                / summary["static_mae_kwh"]
                * 100.0
            ),
            0.0,
        )
        numeric_columns = summary.select_dtypes(include=["number"]).columns
        summary[numeric_columns] = summary[numeric_columns].round(6)
        return summary
