"""One-dimensional Split-Hopkinson pressure-bar (SHPB) reduction tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.integrate import cumulative_trapezoid


@dataclass(frozen=True)
class SHPBConfig:
    """Bar, specimen, and reference-rate inputs for a compression SHPB test."""

    bar_modulus_gpa: float = 210.0
    bar_density_kg_m3: float = 7_850.0
    bar_diameter_mm: float = 20.0
    specimen_diameter_mm: float = 8.0
    specimen_length_mm: float = 4.0
    static_proof_stress_mpa: float = 0.0
    reference_strain_rate_s: float = 1.0e-3

    def validate(self) -> None:
        for label, value in {
            "Bar modulus": self.bar_modulus_gpa,
            "Bar density": self.bar_density_kg_m3,
            "Bar diameter": self.bar_diameter_mm,
            "Specimen diameter": self.specimen_diameter_mm,
            "Specimen length": self.specimen_length_mm,
            "Reference strain rate": self.reference_strain_rate_s,
        }.items():
            if value <= 0.0:
                raise ValueError(f"{label} must be positive")
        if self.static_proof_stress_mpa < 0.0:
            raise ValueError("Static proof stress cannot be negative")


def prepare_shpb_waves(
    frame: pd.DataFrame,
    *,
    time_column: str,
    incident_column: str,
    reflected_column: str,
    transmitted_column: str,
    time_unit: str = "us",
) -> pd.DataFrame:
    """Extract SHPB strain-gauge histories and normalize compression positive."""

    columns = (time_column, incident_column, reflected_column, transmitted_column)
    missing = [name for name in columns if not name or name not in frame.columns]
    if missing:
        raise ValueError(f"Missing SHPB pulse columns: {missing}")
    data = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 8:
        raise ValueError("SHPB pulse file needs at least eight complete numeric rows")
    data.columns = (
        "time",
        "incident_bar_strain",
        "reflected_bar_strain",
        "transmitted_bar_strain",
    )
    scale = {"s": 1.0, "ms": 1.0e-3, "us": 1.0e-6}.get(time_unit)
    if scale is None:
        raise ValueError("SHPB time unit must be s, ms, or us")
    data["time_s"] = data.pop("time") * scale
    data = data.sort_values("time_s").drop_duplicates("time_s").reset_index(drop=True)
    if (np.diff(data["time_s"]) <= 0.0).any():
        raise ValueError("SHPB time values must increase")
    # Gauge polarity differs by acquisition chain; use the transmitted-pulse peak.
    sign = np.sign(
        data["transmitted_bar_strain"].iloc[
            np.abs(data["transmitted_bar_strain"]).argmax()
        ]
    )
    if sign == 0.0:
        raise ValueError("Transmitted pulse is identically zero")
    data[["incident_bar_strain", "reflected_bar_strain", "transmitted_bar_strain"]] *= (
        sign
    )
    return data


def _offset_proof_stress(
    strain: np.ndarray, stress: np.ndarray, modulus_mpa: float
) -> float | None:
    offset = stress - modulus_mpa * (strain - 0.002)
    crossings = np.flatnonzero(np.diff(np.signbit(offset)))
    if len(crossings) == 0:
        return None
    index = int(crossings[0])
    return float(
        np.interp(
            0.0, [offset[index], offset[index + 1]], [stress[index], stress[index + 1]]
        )
    )


def analyze_shpb(
    waves: pd.DataFrame, config: SHPBConfig
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Reduce incident/reflected/transmitted waves with 1-D SHPB equations."""

    config.validate()
    required = {
        "time_s",
        "incident_bar_strain",
        "reflected_bar_strain",
        "transmitted_bar_strain",
    }
    if not required <= set(waves.columns):
        raise ValueError("Use prepare_shpb_waves before SHPB reduction")
    data = (
        waves.loc[:, sorted(required)]
        .sort_values("time_s")
        .reset_index(drop=True)
        .copy()
    )
    time = data["time_s"].to_numpy(dtype=float)
    incident = data["incident_bar_strain"].to_numpy(dtype=float)
    reflected = data["reflected_bar_strain"].to_numpy(dtype=float)
    transmitted = data["transmitted_bar_strain"].to_numpy(dtype=float)
    modulus = config.bar_modulus_gpa * 1.0e3
    wave_speed = np.sqrt(config.bar_modulus_gpa * 1.0e9 / config.bar_density_kg_m3)
    bar_area = np.pi * (config.bar_diameter_mm**2) / 4.0
    specimen_area = np.pi * (config.specimen_diameter_mm**2) / 4.0
    area_ratio = bar_area / specimen_area
    length = config.specimen_length_mm
    strain_rate = -2.0 * wave_speed / (length * 1.0e-3) * reflected
    strain = np.concatenate(([0.0], cumulative_trapezoid(strain_rate, time)))
    transmitted_stress = modulus * area_ratio * transmitted
    incident_face_stress = modulus * area_ratio * (incident + reflected)
    equilibrium = np.abs(incident_face_stress - transmitted_stress) / np.maximum(
        (np.abs(incident_face_stress) + np.abs(transmitted_stress)) / 2.0, 1.0
    )
    response = pd.DataFrame(
        {
            "time_s": time,
            "specimen_engineering_strain": strain,
            "specimen_engineering_strain_rate_s-1": strain_rate,
            "transmitted_stress_MPa": transmitted_stress,
            "incident_face_stress_MPa": incident_face_stress,
            "stress_equilibrium_mismatch_fraction": equilibrium,
        }
    )
    waves_output = data.assign(
        incident_stress_MPa=modulus * incident,
        reflected_stress_MPa=modulus * reflected,
        transmitted_stress_MPa=modulus * transmitted,
    )
    positive = response["specimen_engineering_strain"] >= 0.0
    response = response.loc[positive].reset_index(drop=True)
    if len(response) < 5 or response["specimen_engineering_strain"].max() <= 0.0:
        raise ValueError(
            "The reflected pulse does not produce a positive compression strain history"
        )
    tangent_modulus = np.polyfit(
        response["specimen_engineering_strain"].iloc[: max(5, len(response) // 20)],
        response["transmitted_stress_MPa"].iloc[: max(5, len(response) // 20)],
        1,
    )[0]
    proof = _offset_proof_stress(
        response["specimen_engineering_strain"].to_numpy(),
        response["transmitted_stress_MPa"].to_numpy(),
        tangent_modulus,
    )
    mean_rate = float(np.mean(np.abs(response["specimen_engineering_strain_rate_s-1"])))
    dif = None
    rate_sensitivity = None
    if proof and config.static_proof_stress_mpa > 0.0:
        dif = proof / config.static_proof_stress_mpa
        rate_sensitivity = np.log(dif) / np.log(
            mean_rate / config.reference_strain_rate_s
        )
    summary: dict[str, object] = {
        "status": "ok",
        "wave_speed_m_s": float(wave_speed),
        "bar_to_specimen_area_ratio": float(area_ratio),
        "mean_strain_rate_s-1": mean_rate,
        "peak_strain_rate_s-1": float(
            np.max(np.abs(response["specimen_engineering_strain_rate_s-1"]))
        ),
        "maximum_stress_MPa": float(response["transmitted_stress_MPa"].max()),
        "dynamic_0.2_percent_proof_stress_MPa": proof,
        "dynamic_increase_factor": dif,
        "apparent_log_rate_sensitivity_m": rate_sensitivity,
        "median_equilibrium_mismatch_percent": float(
            100.0 * np.median(response["stress_equilibrium_mismatch_fraction"])
        ),
        "inputs": asdict(config),
        "reference": "https://doi.org/10.11395/aem.25-0008",
        "caveat": (
            "This is a one-dimensional, dispersion-unadjusted SHPB reduction. "
            "Interpret stress only after verifying pulse alignment, specimen force "
            "equilibrium, radial inertia/friction, and a near-constant strain rate."
        ),
    }
    return {"waves": waves_output, "response": response}, summary
