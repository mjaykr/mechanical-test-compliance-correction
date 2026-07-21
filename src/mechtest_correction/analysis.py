"""Mode-specific mechanical properties calculated from corrected curves."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _offset_proof(
    strain: np.ndarray, stress: np.ndarray, modulus_mpa: float, offset: float
) -> tuple[float | None, float | None]:
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
    curve: pd.DataFrame, *, mode: str, modulus_mpa: float
) -> dict[str, dict[str, float | str | None]]:
    """Return labelled tensile or compression properties from a corrected curve."""

    strain = curve["corrected_engineering_strain"].to_numpy(dtype=float)
    stress = curve["engineering_stress_MPa"].to_numpy(dtype=float)
    work = curve["cumulative_work_MJ_per_m3"].to_numpy(dtype=float)
    peak_index = int(np.argmax(stress))
    proof_01 = _offset_proof(strain, stress, modulus_mpa, 0.001)[1]
    proof_02 = _offset_proof(strain, stress, modulus_mpa, 0.002)[1]
    common: dict[str, dict[str, float | str | None]] = {
        "elastic_modulus": {
            "label": "Target elastic modulus",
            "value": modulus_mpa / 1000.0,
            "unit": "GPa",
        },
        "proof_stress_0_2pct": {
            "label": "0.2% proof stress",
            "value": proof_02,
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
            None if proof_02 is None else float(proof_02**2 / (2.0 * modulus_mpa))
        )
        return {
            **common,
            "proof_stress_0_1pct": {
                "label": "0.1% proof stress",
                "value": proof_01,
                "unit": "MPa",
            },
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
                "label": "Modulus of resilience (from 0.2% proof stress)",
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
