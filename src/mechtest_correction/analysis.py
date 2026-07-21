"""Corrected-curve properties and post-yield flow-law fitting."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeWarning, curve_fit


def offset_proof(
    strain: np.ndarray, stress: np.ndarray, modulus_mpa: float, offset: float
) -> tuple[float | None, float | None]:
    """Find the intersection with an elastic line shifted by ``offset`` strain."""

    difference = stress - modulus_mpa * (strain - offset)
    candidates = np.flatnonzero((difference[:-1] >= 0.0) & (difference[1:] < 0.0))
    if len(candidates) == 0:
        return None, None
    index = int(candidates[0])
    proof_strain = strain[index] - difference[index] * (
        strain[index + 1] - strain[index]
    ) / (difference[index + 1] - difference[index])
    return float(proof_strain), float(np.interp(proof_strain, strain, stress))


def _stress_at_strain(
    strain: np.ndarray, stress: np.ndarray, target: float
) -> float | None:
    if target < strain[0] or target > strain[-1]:
        return None
    return float(np.interp(target, strain, stress))


def calculate_mechanical_properties(
    curve: pd.DataFrame,
    *,
    mode: str,
    modulus_mpa: float,
    selected_offset: float = 0.002,
) -> dict[str, dict[str, float | str | None]]:
    """Return labelled tensile or compression properties from a corrected curve."""

    strain = curve["corrected_engineering_strain"].to_numpy(dtype=float)
    stress = curve["engineering_stress_MPa"].to_numpy(dtype=float)
    work = curve["cumulative_work_MJ_per_m3"].to_numpy(dtype=float)
    peak_index = int(np.argmax(stress))
    proof_002 = offset_proof(strain, stress, modulus_mpa, 0.0002)[1]
    proof_02 = offset_proof(strain, stress, modulus_mpa, 0.002)[1]
    selected_proof = offset_proof(strain, stress, modulus_mpa, selected_offset)[1]
    selected_percent = 100.0 * selected_offset
    common: dict[str, dict[str, float | str | None]] = {
        "elastic_modulus": {
            "label": "Target elastic modulus",
            "value": modulus_mpa / 1000.0,
            "unit": "GPa",
        },
        "selected_offset_proof_stress": {
            "label": f"Selected {selected_percent:g}% offset proof stress",
            "value": selected_proof,
            "unit": "MPa",
        },
        "proof_stress_0_2pct": {
            "label": "0.2% offset proof stress",
            "value": proof_02,
            "unit": "MPa",
        },
        "proof_stress_0_02pct": {
            "label": "0.02% offset proof stress",
            "value": proof_002,
            "unit": "MPa",
        },
        "terminal_engineering_strain": {
            "label": "Terminal engineering strain",
            "value": float(strain[-1]),
            "unit": "fraction",
        },
        "energy_to_end": {
            "label": "Energy absorbed to end",
            "value": float(work[-1]),
            "unit": "MJ/m^3",
        },
    }
    if mode == "tension":
        resilience = (
            None
            if selected_proof is None
            else float(selected_proof**2 / (2.0 * modulus_mpa))
        )
        return {
            **common,
            "ultimate_tensile_strength": {
                "label": "Ultimate tensile strength",
                "value": float(stress[peak_index]),
                "unit": "MPa",
            },
            "uniform_engineering_strain": {
                "label": "Engineering strain at UTS",
                "value": float(strain[peak_index]),
                "unit": "fraction",
            },
            "terminal_engineering_stress": {
                "label": "Terminal engineering stress",
                "value": float(stress[-1]),
                "unit": "MPa",
            },
            "modulus_of_resilience": {
                "label": "Modulus of resilience (selected proof stress)",
                "value": resilience,
                "unit": "MJ/m^3",
            },
            "toughness_to_end": {
                "label": "Toughness to end of recorded curve",
                "value": float(work[-1]),
                "unit": "MJ/m^3",
            },
        }
    targets = (0.01, 0.02, 0.05, 0.10, 0.20)
    specified = {
        f"stress_at_{int(100 * target)}pct_strain": {
            "label": f"Stress at {100 * target:g}% strain",
            "value": _stress_at_strain(strain, stress, target),
            "unit": "MPa",
        }
        for target in targets
    }
    return {
        **common,
        **specified,
        "maximum_compressive_stress": {
            "label": "Maximum recorded compressive stress",
            "value": float(stress[peak_index]),
            "unit": "MPa",
        },
        "strain_at_maximum_compressive_stress": {
            "label": "Strain at maximum compressive stress",
            "value": float(strain[peak_index]),
            "unit": "fraction",
        },
        "terminal_compressive_stress": {
            "label": "Terminal compressive stress",
            "value": float(stress[-1]),
            "unit": "MPa",
        },
    }


def _hollomon(x: np.ndarray, strength: float, exponent: float) -> np.ndarray:
    return strength * x**exponent


def _ludwik(
    x: np.ndarray, initial_stress: float, strength: float, exponent: float
) -> np.ndarray:
    return initial_stress + strength * x**exponent


def _swift(
    x: np.ndarray, strength: float, prestrain: float, exponent: float
) -> np.ndarray:
    return strength * (prestrain + x) ** exponent


def _voce(
    x: np.ndarray, saturation: float, initial_stress: float, characteristic: float
) -> np.ndarray:
    return saturation - (saturation - initial_stress) * np.exp(-x / characteristic)


MODEL_FUNCTIONS: dict[str, Callable[..., np.ndarray]] = {
    "Hollomon": _hollomon,
    "Ludwik": _ludwik,
    "Swift": _swift,
    "Voce": _voce,
}

MODEL_EQUATIONS = {
    "Hollomon": "sigma = K * epsilon_p^n",
    "Ludwik": "sigma = sigma_0 + K * epsilon_p^n",
    "Swift": "sigma = K * (epsilon_0 + epsilon_p)^n",
    "Voce": "sigma = sigma_sat - (sigma_sat - sigma_0) * exp(-epsilon_p/epsilon_c)",
    "Linear": "sigma = sigma_0 + H * epsilon_p",
}

MODEL_PARAMETER_NAMES = {
    "Hollomon": ("K_MPa", "n"),
    "Ludwik": ("sigma_0_MPa", "K_MPa", "n"),
    "Swift": ("K_MPa", "epsilon_0", "n"),
    "Voce": ("sigma_sat_MPa", "sigma_0_MPa", "epsilon_c"),
    "Linear": ("sigma_0_MPa", "H_MPa"),
}


def evaluate_flow_model(
    name: str, plastic_strain: np.ndarray, parameters: dict[str, float]
) -> np.ndarray:
    """Evaluate one stored flow-law fit."""

    ordered = [parameters[key] for key in MODEL_PARAMETER_NAMES[name]]
    if name == "Linear":
        return ordered[0] + ordered[1] * plastic_strain
    return MODEL_FUNCTIONS[name](plastic_strain, *ordered)


def _fit_statistics(observed: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    residual = observed - predicted
    ss_res = float(np.sum(residual**2))
    ss_total = float(np.sum((observed - np.mean(observed)) ** 2))
    r_squared = float("nan") if ss_total == 0.0 else 1.0 - ss_res / ss_total
    return r_squared, float(np.sqrt(np.mean(residual**2)))


def fit_flow_models(
    curve: pd.DataFrame,
    *,
    modulus_mpa: float,
    yield_offset: float = 0.002,
    end_criterion: str = "peak",
) -> dict[str, object]:
    """Fit flow laws to true stress versus true plastic strain after proof yield."""

    engineering_strain = curve["corrected_engineering_strain"].to_numpy(dtype=float)
    engineering_stress = curve["engineering_stress_MPa"].to_numpy(dtype=float)
    true_strain = curve["true_strain"].to_numpy(dtype=float)
    true_stress = curve["true_stress_MPa"].to_numpy(dtype=float)
    proof_strain, proof_stress = offset_proof(
        engineering_strain, engineering_stress, modulus_mpa, yield_offset
    )
    if proof_strain is None or proof_stress is None:
        return {
            "status": "unavailable",
            "reason": (
                "The selected offset line does not intersect the corrected curve."
            ),
            "models": {},
        }
    start_index = int(np.searchsorted(engineering_strain, proof_strain, side="left"))
    if end_criterion == "terminal":
        end_index = len(curve) - 1
        end_label = "terminal point"
    elif end_criterion == "peak":
        end_index = int(np.argmax(engineering_stress))
        end_label = "peak engineering stress (UTS/max)"
    else:
        raise ValueError("end_criterion must be 'peak' or 'terminal'")
    if end_index <= start_index + 5:
        return {
            "status": "unavailable",
            "reason": (
                "Fewer than six post-yield observations occur before the fit end."
            ),
            "models": {},
        }
    selection = np.arange(len(curve))
    true_plastic = true_strain - true_stress / modulus_mpa
    mask = (
        (selection >= start_index)
        & (selection <= end_index)
        & np.isfinite(true_plastic)
        & np.isfinite(true_stress)
        & (true_plastic > 1.0e-8)
    )
    x = true_plastic[mask]
    y = true_stress[mask]
    if len(x) < 6:
        return {
            "status": "unavailable",
            "reason": (
                "Fewer than six positive true-plastic-strain observations remain."
            ),
            "models": {},
        }
    if len(x) > 2000:
        sample = np.linspace(0, len(x) - 1, 2000, dtype=int)
        fit_x, fit_y = x[sample], y[sample]
    else:
        fit_x, fit_y = x, y
    maximum_stress = float(np.max(fit_y))
    initial_stress = float(fit_y[0])
    maximum_strain = float(np.max(fit_x))
    model_setup = {
        "Hollomon": (
            (maximum_stress / max(maximum_strain, 1e-4) ** 0.2, 0.2),
            ([0.0, 0.0], [1.0e7, 2.0]),
        ),
        "Ludwik": (
            (initial_stress, maximum_stress, 0.2),
            ([0.0, 0.0, 0.0], [2.0 * maximum_stress, 1.0e7, 2.0]),
        ),
        "Swift": (
            (
                maximum_stress / (0.002 + maximum_strain) ** 0.2,
                0.002,
                0.2,
            ),
            ([0.0, 1.0e-8, 0.0], [1.0e7, 1.0, 2.0]),
        ),
        "Voce": (
            (1.1 * maximum_stress, initial_stress, max(maximum_strain / 3.0, 1e-4)),
            (
                [maximum_stress, 0.0, 1.0e-8],
                [10.0 * maximum_stress, 2.0 * maximum_stress, 10.0],
            ),
        ),
    }
    models: dict[str, dict[str, object]] = {}
    for name, (initial, bounds) in model_setup.items():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                fitted, _ = curve_fit(
                    MODEL_FUNCTIONS[name],
                    fit_x,
                    fit_y,
                    p0=initial,
                    bounds=bounds,
                    maxfev=50_000,
                )
            parameters = {
                key: float(value)
                for key, value in zip(MODEL_PARAMETER_NAMES[name], fitted, strict=True)
            }
            predicted = evaluate_flow_model(name, x, parameters)
            r_squared, rmse = _fit_statistics(y, predicted)
            models[name] = {
                "equation": MODEL_EQUATIONS[name],
                "parameters": parameters,
                "R_squared": r_squared,
                "RMSE_MPa": rmse,
            }
        except (RuntimeError, ValueError, FloatingPointError) as exc:
            models[name] = {
                "equation": MODEL_EQUATIONS[name],
                "error": str(exc),
            }
    slope, intercept = np.polyfit(x, y, 1)
    linear_parameters = {"sigma_0_MPa": float(intercept), "H_MPa": float(slope)}
    linear_predicted = evaluate_flow_model("Linear", x, linear_parameters)
    linear_r2, linear_rmse = _fit_statistics(y, linear_predicted)
    models["Linear"] = {
        "equation": MODEL_EQUATIONS["Linear"],
        "parameters": linear_parameters,
        "R_squared": linear_r2,
        "RMSE_MPa": linear_rmse,
    }
    return {
        "status": "ok",
        "yield_offset_fraction": yield_offset,
        "yield_offset_percent": 100.0 * yield_offset,
        "yield_engineering_strain": proof_strain,
        "yield_stress_MPa": proof_stress,
        "fit_end_criterion": end_criterion,
        "fit_end_label": end_label,
        "fit_end_engineering_strain": float(engineering_strain[end_index]),
        "fit_end_engineering_stress_MPa": float(engineering_stress[end_index]),
        "fit_point_count": int(len(x)),
        "true_plastic_strain_min": float(x[0]),
        "true_plastic_strain_max": float(x[-1]),
        "models": models,
    }


def properties_frame(
    properties: dict[str, dict[str, float | str | None]],
) -> pd.DataFrame:
    """Convert the nested property mapping to an export-ready table."""

    return pd.DataFrame(
        [
            {
                "property": key,
                "label": item["label"],
                "value": item["value"],
                "unit": item["unit"],
            }
            for key, item in properties.items()
        ]
    )


def flow_models_frame(fits: dict[str, object]) -> pd.DataFrame:
    """Convert flow fits to one row per model."""

    rows = []
    for name, model in fits.get("models", {}).items():
        rows.append(
            {
                "model": name,
                "equation": model["equation"],
                "parameters": json.dumps(model.get("parameters", {}), sort_keys=True),
                "R_squared": model.get("R_squared"),
                "RMSE_MPa": model.get("RMSE_MPa"),
                "error": model.get("error"),
            }
        )
    return pd.DataFrame(rows)


def flow_fit_data_frame(
    curve: pd.DataFrame, fits: dict[str, object], modulus_mpa: float
) -> pd.DataFrame:
    """Return the selected experimental flow curve and every fitted prediction."""

    if fits.get("status") != "ok":
        return pd.DataFrame()
    true_plastic = (
        curve["true_strain"].to_numpy(dtype=float)
        - curve["true_stress_MPa"].to_numpy(dtype=float) / modulus_mpa
    )
    low = float(fits["true_plastic_strain_min"])
    high = float(fits["true_plastic_strain_max"])
    mask = (true_plastic >= low) & (true_plastic <= high)
    result = pd.DataFrame(
        {
            "true_plastic_strain": true_plastic[mask],
            "experimental_true_stress_MPa": curve.loc[
                mask, "true_stress_MPa"
            ].to_numpy(),
        }
    )
    for name, model in fits["models"].items():
        if "parameters" in model:
            result[f"{name}_true_stress_MPa"] = evaluate_flow_model(
                name,
                result["true_plastic_strain"].to_numpy(),
                model["parameters"],
            )
    return result
