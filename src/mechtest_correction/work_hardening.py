"""Derivative-based work-hardening and Kocks-Mecking analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


def _line_sse(x: np.ndarray, y: np.ndarray) -> float:
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (intercept + slope * x)
    return float(np.sum(residual**2))


def _three_stage_breaks(x: np.ndarray, theta: np.ndarray) -> tuple[int, int]:
    """Choose two derivative-curve breaks using three-piece linear SSE."""

    count = len(x)
    minimum = max(12, count // 10)
    step = max(2, count // 60)
    best = (minimum, count - minimum)
    best_sse = float("inf")
    for first in range(minimum, count - 2 * minimum + 1, step):
        for second in range(first + minimum, count - minimum + 1, step):
            sse = (
                _line_sse(x[:first], theta[:first])
                + _line_sse(x[first:second], theta[first:second])
                + _line_sse(x[second:], theta[second:])
            )
            if sse < best_sse:
                best_sse = sse
                best = (first, second)
    return best


def analyze_work_hardening(
    curve: pd.DataFrame,
    flow_fits: dict[str, object],
    *,
    modulus_mpa: float,
    smoothing_window: int = 51,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Calculate theta=d(true stress)/d(true plastic strain) and stage fits."""

    if flow_fits.get("status") != "ok":
        return pd.DataFrame(), {
            "status": "unavailable",
            "reason": "A valid post-yield fit interval is required.",
        }
    plastic = (
        curve["true_strain"].to_numpy(dtype=float)
        - curve["true_stress_MPa"].to_numpy(dtype=float) / modulus_mpa
    )
    stress = curve["true_stress_MPa"].to_numpy(dtype=float)
    low = float(flow_fits["true_plastic_strain_min"])
    high = float(flow_fits["true_plastic_strain_max"])
    mask = (
        np.isfinite(plastic)
        & np.isfinite(stress)
        & (plastic >= low)
        & (plastic <= high)
    )
    selected = pd.DataFrame(
        {"true_plastic_strain": plastic[mask], "true_stress_MPa": stress[mask]}
    ).drop_duplicates("true_plastic_strain")
    selected = selected.sort_values("true_plastic_strain")
    if len(selected) < 15:
        return pd.DataFrame(), {
            "status": "unavailable",
            "reason": "At least 15 unique post-yield points are required.",
        }
    count = min(1000, max(250, len(selected)))
    uniform_strain = np.linspace(
        float(selected["true_plastic_strain"].iloc[0]),
        float(selected["true_plastic_strain"].iloc[-1]),
        count,
    )
    uniform_stress = np.interp(
        uniform_strain,
        selected["true_plastic_strain"],
        selected["true_stress_MPa"],
    )
    window = max(7, int(smoothing_window))
    if window % 2 == 0:
        window += 1
    window = min(window, count - 1 if count % 2 == 0 else count)
    if window % 2 == 0:
        window -= 1
    smoothed_stress = savgol_filter(uniform_stress, window, 3, mode="interp")
    theta = np.gradient(smoothed_stress, uniform_strain)
    edge = max(2, window // 2)
    analysis_strain = uniform_strain[edge:-edge]
    analysis_stress = smoothed_stress[edge:-edge]
    analysis_theta = theta[edge:-edge]
    first, second = _three_stage_breaks(analysis_strain, analysis_theta)
    stage = np.full(len(analysis_strain), "Stage IV / late", dtype=object)
    stage[:first] = "Stage II / early"
    stage[first:second] = "Stage III / dynamic recovery"
    stage_three_stress = analysis_stress[first:second]
    stage_three_theta = analysis_theta[first:second]
    km_slope, km_intercept = np.polyfit(stage_three_stress, stage_three_theta, 1)
    km_prediction = km_intercept + km_slope * stage_three_stress
    residual = stage_three_theta - km_prediction
    total = stage_three_theta - np.mean(stage_three_theta)
    denominator = float(np.sum(total**2))
    km_r_squared = (
        None if denominator == 0.0 else 1.0 - float(np.sum(residual**2)) / denominator
    )
    saturation_stress = -float(km_intercept / km_slope) if km_slope < 0.0 else None
    data = pd.DataFrame(
        {
            "true_plastic_strain": analysis_strain,
            "true_stress_MPa": analysis_stress,
            "hardening_rate_theta_MPa": analysis_theta,
            "stage": stage,
        }
    )
    summary: dict[str, object] = {
        "status": "ok",
        "definition": "theta = d(true stress) / d(true plastic strain)",
        "smoothing_method": "Savitzky-Golay",
        "smoothing_window": window,
        "stage_method": "three-piece linear SSE segmentation of theta(epsilon_p)",
        "stage_II_end_true_plastic_strain": float(analysis_strain[first]),
        "stage_III_end_true_plastic_strain": float(analysis_strain[second]),
        "stage_III_KM_intercept_MPa": float(km_intercept),
        "stage_III_KM_slope": float(km_slope),
        "stage_III_KM_R_squared": km_r_squared,
        "KM_extrapolated_saturation_stress_MPa": saturation_stress,
        "caveat": (
            "Stage boundaries are data-driven derivative-curve segments and do not "
            "by themselves prove a specific dislocation mechanism."
        ),
    }
    return data, summary
