from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .analysis import calculate_mechanical_properties, fit_flow_models
from .io import normalize_units, sign_factor
from .models import CorrectionConfig, CorrectionResult


def _r_squared(observed: np.ndarray, predicted: np.ndarray) -> float:
    residual = observed - predicted
    total = observed - np.mean(observed)
    denominator = float(np.sum(total**2))
    return (
        float("nan")
        if denominator == 0.0
        else 1.0 - float(np.sum(residual**2)) / denominator
    )


def _strictly_monotonic(values: np.ndarray, increment: float) -> np.ndarray:
    result = values.copy()
    for i in range(1, len(result)):
        result[i] = max(result[i], result[i - 1] + increment)
    return result


def _proof_intersection(
    strain: np.ndarray,
    stress: np.ndarray,
    modulus_mpa: float,
    offset: float,
) -> tuple[float | None, float | None]:
    difference = stress - modulus_mpa * (strain - offset)
    candidates = np.flatnonzero((difference[:-1] >= 0.0) & (difference[1:] < 0.0))
    if len(candidates) == 0:
        return None, None
    i = int(candidates[0])
    proof_strain = strain[i] - difference[i] * (strain[i + 1] - strain[i]) / (
        difference[i + 1] - difference[i]
    )
    proof_stress = np.interp(proof_strain, strain, stress)
    return float(proof_strain), float(proof_stress)


def _true_curve(
    mode: str, strain: np.ndarray, stress: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    if mode == "tension":
        return np.log1p(strain), stress * (1.0 + strain)
    if np.any(strain >= 1.0):
        raise ValueError("Compression engineering strain must remain below 1.0")
    return -np.log1p(-strain), stress * (1.0 - strain)


def correct_curve(frame: pd.DataFrame, config: CorrectionConfig) -> CorrectionResult:
    """Apply a target-modulus strain-compliance correction.

    ``frame`` must contain ``engineering_strain`` and ``engineering_stress``.
    Raw values are retained in the audit output; internal stress units are MPa
    and strain is fractional.
    """

    config.validate()
    required = {"engineering_strain", "engineering_stress"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Input frame must contain columns {sorted(required)}")

    normalized = normalize_units(
        frame,
        strain_unit=config.strain_unit,
        stress_unit=config.stress_unit,
    )
    raw_strain_input = frame["engineering_strain"].to_numpy(dtype=float, copy=True)
    raw_stress_input = frame["engineering_stress"].to_numpy(dtype=float, copy=True)
    strain = normalized["engineering_strain"].to_numpy(dtype=float, copy=True)
    stress = normalized["engineering_stress_mpa"].to_numpy(dtype=float, copy=True)
    strain_multiplier = sign_factor(strain, config.strain_sign)
    stress_multiplier = sign_factor(stress, config.stress_sign)
    strain *= strain_multiplier
    stress *= stress_multiplier

    if not np.all(np.isfinite(strain)) or not np.all(np.isfinite(stress)):
        raise ValueError("Stress and strain must be finite")
    if len(strain) < 3:
        raise ValueError("At least three observations are required")
    if np.nanmax(strain) <= 0.0 or np.nanmax(stress) <= 0.0:
        raise ValueError("Normalized stress and strain must reach positive values")

    nonincreasing = int(np.sum(np.diff(strain) <= 0.0))
    if nonincreasing > max(2, int(0.01 * len(strain))):
        raise ValueError(
            "The normalized strain history is not monotonic; split unloading or cyclic "
            "segments before applying this correction"
        )
    if nonincreasing:
        warnings.warn(
            f"Input contains {nonincreasing} non-increasing strain steps",
            stacklevel=2,
        )

    fit_variable = strain if config.fit_axis == "strain" else stress
    fit_mask = (fit_variable >= config.fit_min) & (fit_variable <= config.fit_max)
    if int(np.sum(fit_mask)) < 5:
        raise ValueError("The selected fit interval contains fewer than five points")

    fit_stress = stress[fit_mask]
    fit_strain = strain[fit_mask]
    strain_per_mpa, toe_strain = np.polyfit(fit_stress, fit_strain, 1)
    apparent_modulus_mpa = 1.0 / strain_per_mpa
    predicted_fit_strain = strain_per_mpa * fit_stress + toe_strain
    fit_r2 = _r_squared(fit_strain, predicted_fit_strain)

    system_compliance = strain_per_mpa - 1.0 / config.target_modulus_mpa
    if system_compliance <= 0.0:
        raise ValueError(
            "The target modulus does not exceed the apparent modulus, so the assumed "
            "positive system-compliance correction is not defined"
        )

    compliance_removed = system_compliance * stress
    corrected_before_monotonic = strain - compliance_removed - toe_strain
    if config.exclude_before_fit:
        usable = fit_variable >= config.fit_min
    else:
        usable = np.ones(len(strain), dtype=bool)
    usable &= corrected_before_monotonic >= 0.0
    if int(np.sum(usable)) < 3:
        raise ValueError("Too few usable rows remain after toe exclusion")

    usable_before = corrected_before_monotonic[usable]
    local_reversals = int(np.sum(np.diff(usable_before) <= 0.0))
    if config.monotonic:
        usable_corrected = _strictly_monotonic(usable_before, config.strict_increment)
    else:
        usable_corrected = usable_before.copy()
    adjustment = usable_corrected - usable_before

    corrected_full = np.full(len(strain), np.nan)
    adjustment_full = np.full(len(strain), np.nan)
    corrected_full[usable] = usable_corrected
    adjustment_full[usable] = adjustment

    usable_stress = stress[usable]
    source_rows = np.flatnonzero(usable) + 1
    if config.add_origin:
        corrected_strain = np.r_[0.0, usable_corrected]
        corrected_stress = np.r_[0.0, usable_stress]
        corrected_source = np.r_[0, source_rows]
    else:
        corrected_strain = usable_corrected
        corrected_stress = usable_stress
        corrected_source = source_rows

    if np.any(np.diff(corrected_strain) <= 0.0):
        raise ValueError(
            "Corrected strain is not strictly increasing; enable monotonic "
            "reconstruction"
        )

    true_strain, true_stress = _true_curve(
        config.mode, corrected_strain, corrected_stress
    )
    increments = np.diff(corrected_strain)
    trapezoids = increments * (corrected_stress[1:] + corrected_stress[:-1]) / 2.0
    cumulative_work = np.r_[0.0, np.cumsum(trapezoids)]
    offset_line = config.target_modulus_mpa * (corrected_strain - config.offset_strain)
    proof_strain, proof_stress = _proof_intersection(
        corrected_strain,
        corrected_stress,
        config.target_modulus_mpa,
        config.offset_strain,
    )

    audit = pd.DataFrame(
        {
            "source_row": np.arange(1, len(strain) + 1),
            "input_engineering_strain": raw_strain_input,
            "input_engineering_stress": raw_stress_input,
            "normalized_engineering_strain": strain,
            "normalized_engineering_stress_MPa": stress,
            "compliance_strain_removed": compliance_removed,
            "toe_strain_removed": toe_strain,
            "corrected_strain_before_monotonic": corrected_before_monotonic,
            "usable_after_toe": usable,
            "monotonic_adjustment_strain": adjustment_full,
            "corrected_engineering_strain": corrected_full,
        }
    )
    curve = pd.DataFrame(
        {
            "corrected_point": np.arange(len(corrected_strain)),
            "source_row": corrected_source,
            "corrected_engineering_strain": corrected_strain,
            "engineering_stress_MPa": corrected_stress,
            "true_strain": true_strain,
            "true_stress_MPa": true_stress,
            "cumulative_work_MJ_per_m3": cumulative_work,
            "target_elastic_line_MPa": config.target_modulus_mpa * corrected_strain,
            "offset_line_MPa": offset_line,
            "stress_minus_offset_line_MPa": corrected_stress - offset_line,
        }
    )

    fit_indices = np.flatnonzero(fit_mask & usable)
    recovered_output_modulus = None
    if len(fit_indices) >= 5:
        output_slope, _ = np.polyfit(
            stress[fit_indices], corrected_full[fit_indices], 1
        )
        recovered_output_modulus = float(1.0 / output_slope)

    peak_true_index = int(np.argmax(true_stress))
    caveats = [
        "Target modulus is an external assumption, not a modulus measured by this run.",
        "Engineering stress values are preserved; only strain is reconstructed.",
    ]
    if config.mode == "tension":
        caveats.append(
            "Tensile true stress is valid only before necking unless "
            "instantaneous area is measured."
        )
    else:
        caveats.append(
            "Compression true stress assumes homogeneous constant-volume deformation."
        )
    if fit_r2 < 0.995:
        caveats.append(
            "The selected compliance interval has fit R-squared below 0.995."
        )

    summary: dict[str, object] = {
        "mode": config.mode,
        "target_modulus_GPa": config.target_modulus_mpa / 1000.0,
        "apparent_modulus_GPa": apparent_modulus_mpa / 1000.0,
        "recovered_output_modulus_GPa": (
            None
            if recovered_output_modulus is None
            else recovered_output_modulus / 1000.0
        ),
        "fit_axis": config.fit_axis,
        "fit_min": config.fit_min,
        "fit_max": config.fit_max,
        "fit_point_count": int(np.sum(fit_mask)),
        "fit_R_squared_strain_on_stress": fit_r2,
        "raw_strain_per_stress_per_MPa": float(strain_per_mpa),
        "system_compliance_strain_per_MPa": float(system_compliance),
        "toe_strain_removed": float(toe_strain),
        "strain_sign_multiplier": strain_multiplier,
        "stress_sign_multiplier": stress_multiplier,
        "input_points": len(strain),
        "usable_measured_points": int(np.sum(usable)),
        "excluded_points": int(np.sum(~usable)),
        "local_reversals_before_monotonic": local_reversals,
        "maximum_monotonic_adjustment_strain": float(np.max(adjustment)),
        "offset_strain": config.offset_strain,
        "proof_strain": proof_strain,
        "proof_stress_MPa": proof_stress,
        "terminal_corrected_engineering_strain": float(corrected_strain[-1]),
        "terminal_engineering_stress_MPa": float(corrected_stress[-1]),
        "maximum_true_stress_MPa": float(true_stress[peak_true_index]),
        "true_strain_at_maximum_true_stress": float(true_strain[peak_true_index]),
        "absorbed_energy_to_end_MJ_per_m3": float(cumulative_work[-1]),
        "caveats": caveats,
    }
    summary["mechanical_properties"] = calculate_mechanical_properties(
        curve,
        mode=config.mode,
        modulus_mpa=config.target_modulus_mpa,
        selected_offset=config.offset_strain,
    )
    summary["flow_model_fits"] = fit_flow_models(
        curve,
        modulus_mpa=config.target_modulus_mpa,
        yield_offset=config.offset_strain,
        end_criterion="peak",
    )
    return CorrectionResult(
        config=config, audit=audit, corrected_curve=curve, summary=summary
    )
