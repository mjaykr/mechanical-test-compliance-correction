"""Microstructure-aware strengthening models for W-Ni-Fe heavy alloys."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from .analysis import flow_fit_data_frame
from .models import CorrectionResult


@dataclass(frozen=True)
class MicrostructureConfig:
    """Inputs for a two-phase Hall-Petch strengthening projection."""

    tungsten_grain_size_um: float = 30.0
    matrix_grain_size_um: float = 8.0
    tungsten_volume_fraction: float = 0.90
    base_stress_mpa: float = 300.0
    tungsten_k_mpa_sqrt_um: float = 810.0
    matrix_k_mpa_sqrt_um: float = 350.0

    def validate(self) -> None:
        if self.tungsten_grain_size_um <= 0 or self.matrix_grain_size_um <= 0:
            raise ValueError("Both phase grain sizes must be positive")
        if not 0.0 < self.tungsten_volume_fraction < 1.0:
            raise ValueError("Tungsten volume fraction must be between 0 and 1")
        if self.base_stress_mpa < 0:
            raise ValueError("Base stress cannot be negative")
        if self.tungsten_k_mpa_sqrt_um < 0 or self.matrix_k_mpa_sqrt_um < 0:
            raise ValueError("Hall-Petch coefficients cannot be negative")


@dataclass(frozen=True)
class DislocationConfig:
    """Effective Taylor and Kocks-Mecking parameters for the composite curve."""

    taylor_factor: float = 2.75
    alpha: float = 0.30
    shear_modulus_gpa: float = 161.0
    burgers_vector_nm: float = 0.274
    friction_stress_mpa: float = 300.0

    def validate(self) -> None:
        positive = {
            "Taylor factor": self.taylor_factor,
            "alpha": self.alpha,
            "shear modulus": self.shear_modulus_gpa,
            "Burgers vector": self.burgers_vector_nm,
        }
        for label, value in positive.items():
            if value <= 0:
                raise ValueError(f"{label} must be positive")
        if self.friction_stress_mpa < 0:
            raise ValueError("Friction stress cannot be negative")


@dataclass(frozen=True)
class MicromechanicalConfig:
    """Bilinear phase properties for WHA load-sharing bounds."""

    tungsten_volume_fraction: float = 0.90
    tungsten_modulus_gpa: float = 411.0
    matrix_modulus_gpa: float = 200.0
    tungsten_yield_mpa: float = 750.0
    matrix_yield_mpa: float = 350.0
    tungsten_hardening_mpa: float = 1500.0
    matrix_hardening_mpa: float = 900.0

    def validate(self) -> None:
        if not 0.0 < self.tungsten_volume_fraction < 1.0:
            raise ValueError("Tungsten volume fraction must be between 0 and 1")
        for label, value in {
            "W modulus": self.tungsten_modulus_gpa,
            "matrix modulus": self.matrix_modulus_gpa,
            "W yield stress": self.tungsten_yield_mpa,
            "matrix yield stress": self.matrix_yield_mpa,
            "W tangent modulus": self.tungsten_hardening_mpa,
            "matrix tangent modulus": self.matrix_hardening_mpa,
        }.items():
            if value <= 0:
                raise ValueError(f"{label} must be positive")


@dataclass(frozen=True)
class AdvancedWHAConfig:
    """Explicit assumptions for advanced WHA sensitivity views."""

    tungsten_poisson_ratio: float = 0.28
    matrix_poisson_ratio: float = 0.31
    ww_contiguity: float = 0.45
    porosity_fraction: float = 0.0
    interface_strength_mpa: float = 150.0
    contiguity_coefficient_mpa: float = 100.0
    porosity_strength_exponent: float = 1.5
    tungsten_density_multiplier: float = 1.30
    matrix_density_multiplier: float = 0.50

    def validate(self) -> None:
        for label, value in {
            "W Poisson ratio": self.tungsten_poisson_ratio,
            "matrix Poisson ratio": self.matrix_poisson_ratio,
        }.items():
            if not 0.0 < value < 0.5:
                raise ValueError(f"{label} must be between 0 and 0.5")
        for label, value in {
            "W-W contiguity": self.ww_contiguity,
            "porosity": self.porosity_fraction,
        }.items():
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{label} must be between 0 and 1")
        for label, value in {
            "interface strength": self.interface_strength_mpa,
            "contiguity coefficient": self.contiguity_coefficient_mpa,
            "porosity exponent": self.porosity_strength_exponent,
            "W density multiplier": self.tungsten_density_multiplier,
            "matrix density multiplier": self.matrix_density_multiplier,
        }.items():
            if value < 0.0:
                raise ValueError(f"{label} cannot be negative")


def analyze_hall_petch(
    result: CorrectionResult, config: MicrostructureConfig
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Project phase-weighted Hall-Petch contributions without claiming a fit."""

    config.validate()
    fraction = config.tungsten_volume_fraction
    matrix_fraction = 1.0 - fraction
    w_contribution = (
        fraction
        * config.tungsten_k_mpa_sqrt_um
        / np.sqrt(config.tungsten_grain_size_um)
    )
    matrix_contribution = (
        matrix_fraction
        * config.matrix_k_mpa_sqrt_um
        / np.sqrt(config.matrix_grain_size_um)
    )
    predicted = config.base_stress_mpa + w_contribution + matrix_contribution
    measured = result.summary.get("proof_stress_MPa")
    current_min = min(config.tungsten_grain_size_um, config.matrix_grain_size_um)
    current_max = max(config.tungsten_grain_size_um, config.matrix_grain_size_um)
    grain_size = np.geomspace(max(0.25, current_min / 5.0), current_max * 5.0, 240)
    fixed_matrix = (
        config.base_stress_mpa
        + matrix_fraction
        * config.matrix_k_mpa_sqrt_um
        / np.sqrt(config.matrix_grain_size_um)
    )
    fixed_tungsten = (
        config.base_stress_mpa
        + fraction
        * config.tungsten_k_mpa_sqrt_um
        / np.sqrt(config.tungsten_grain_size_um)
    )
    data = pd.DataFrame(
        {
            "grain_size_um": grain_size,
            "vary_W_grain_size_predicted_yield_MPa": (
                fixed_matrix
                + fraction * config.tungsten_k_mpa_sqrt_um / np.sqrt(grain_size)
            ),
            "vary_matrix_grain_size_predicted_yield_MPa": (
                fixed_tungsten
                + matrix_fraction * config.matrix_k_mpa_sqrt_um / np.sqrt(grain_size)
            ),
        }
    )
    summary: dict[str, object] = {
        "status": "ok",
        "method": "phase-weighted Hall-Petch projection",
        "base_stress_MPa": config.base_stress_mpa,
        "W_Hall_Petch_contribution_MPa": float(w_contribution),
        "matrix_Hall_Petch_contribution_MPa": float(matrix_contribution),
        "predicted_yield_stress_MPa": float(predicted),
        "measured_proof_stress_MPa": measured,
        "prediction_minus_measured_MPa": (
            None if measured is None else float(predicted - float(measured))
        ),
        "reference": "https://doi.org/10.1016/S0921-5093(00)01369-1",
        "inputs": asdict(config),
        "caveat": (
            "This is a projection using supplied coefficients, not a Hall-Petch "
            "regression. Fitting sigma_0 and k requires multiple specimens with "
            "independently measured grain sizes."
        ),
    }
    return data, summary


def hall_petch_contributions(summary: dict[str, object]) -> pd.DataFrame:
    """Return the exact stacked-bar values used by the strengthening plot."""

    if summary.get("status") != "ok":
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "mechanism": ["Base", "W grain size", "Matrix grain size"],
            "contribution_MPa": [
                summary["base_stress_MPa"],
                summary["W_Hall_Petch_contribution_MPa"],
                summary["matrix_Hall_Petch_contribution_MPa"],
            ],
        }
    )


def analyze_dislocation_density(
    result: CorrectionResult, config: DislocationConfig
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Infer effective Taylor density and fit Kocks-Mecking density evolution."""

    config.validate()
    fit_data = flow_fit_data_frame(
        result.corrected_curve,
        result.summary["flow_model_fits"],
        result.config.target_modulus_mpa,
    )
    if len(fit_data) < 12:
        return pd.DataFrame(), {
            "status": "unavailable",
            "reason": "At least 12 post-yield flow points are required.",
        }
    strain = fit_data["true_plastic_strain"].to_numpy(dtype=float)
    stress_mpa = fit_data["experimental_true_stress_MPa"].to_numpy(dtype=float)
    valid = stress_mpa > config.friction_stress_mpa
    strain = strain[valid]
    stress_mpa = stress_mpa[valid]
    if len(strain) < 12:
        return pd.DataFrame(), {
            "status": "unavailable",
            "reason": "Too few flow stresses exceed the selected friction stress.",
        }
    factor_pa_m = (
        config.taylor_factor
        * config.alpha
        * config.shear_modulus_gpa
        * 1.0e9
        * config.burgers_vector_nm
        * 1.0e-9
    )
    sqrt_density = (stress_mpa - config.friction_stress_mpa) * 1.0e6 / factor_pa_m
    density = sqrt_density**2
    shifted = strain - strain[0]
    initial = float(sqrt_density[0])

    def evolution(x, saturation, beta):
        return saturation + (initial - saturation) * np.exp(-beta * x)

    lower_saturation = max(float(np.max(sqrt_density)), initial) * 1.000001
    try:
        parameters, _ = curve_fit(
            evolution,
            shifted,
            sqrt_density,
            p0=(lower_saturation * 1.2, 5.0),
            bounds=((lower_saturation, 1.0e-8), (lower_saturation * 100.0, 1.0e4)),
            maxfev=50_000,
        )
        saturation, beta = (float(value) for value in parameters)
        fitted_sqrt_density = evolution(shifted, saturation, beta)
        k2 = 2.0 * beta
        k1 = k2 * saturation
        status = "ok"
        fit_error = None
    except (RuntimeError, ValueError) as exc:
        fitted_sqrt_density = np.full_like(sqrt_density, np.nan)
        saturation = beta = k1 = k2 = float("nan")
        status = "fit_unavailable"
        fit_error = str(exc)
    fitted_stress = (
        config.friction_stress_mpa + factor_pa_m * fitted_sqrt_density / 1.0e6
    )
    fitted_density = fitted_sqrt_density**2
    finite = np.isfinite(fitted_stress)
    rmse = (
        None
        if not finite.any()
        else float(np.sqrt(np.mean((stress_mpa[finite] - fitted_stress[finite]) ** 2)))
    )
    data = pd.DataFrame(
        {
            "true_plastic_strain": strain,
            "true_stress_MPa": stress_mpa,
            "apparent_dislocation_density_m-2": density,
            "KM_fitted_dislocation_density_m-2": fitted_density,
            "KM_fitted_true_stress_MPa": fitted_stress,
        }
    )
    summary: dict[str, object] = {
        "status": status,
        "definition": "sigma = sigma_0 + M alpha mu b sqrt(rho)",
        "initial_apparent_density_m-2": float(density[0]),
        "terminal_apparent_density_m-2": float(density[-1]),
        "saturation_density_m-2": (
            None if not np.isfinite(saturation) else float(saturation**2)
        ),
        "KM_storage_k1_m-1": None if not np.isfinite(k1) else float(k1),
        "KM_recovery_k2": None if not np.isfinite(k2) else float(k2),
        "stress_fit_RMSE_MPa": rmse,
        "reference": "https://doi.org/10.1016/j.jmps.2015.08.015",
        "inputs": asdict(config),
        "fit_error": fit_error,
        "caveat": (
            "rho is an effective apparent composite density. Absolute phase-specific "
            "density requires independently justified M, alpha, mu, b, sigma_0 and "
            "preferably XRD, EBSD or TEM calibration."
        ),
    }
    return data, summary


def _phase_stress(
    strain: np.ndarray, modulus_mpa: float, yield_mpa: float, tangent_mpa: float
) -> np.ndarray:
    yield_strain = yield_mpa / modulus_mpa
    return np.where(
        strain <= yield_strain,
        modulus_mpa * strain,
        yield_mpa + tangent_mpa * (strain - yield_strain),
    )


def _phase_strain(
    stress_mpa: float, modulus_mpa: float, yield_mpa: float, tangent_mpa: float
) -> float:
    if stress_mpa <= yield_mpa:
        return stress_mpa / modulus_mpa
    return yield_mpa / modulus_mpa + (stress_mpa - yield_mpa) / tangent_mpa


def analyze_micromechanics(
    result: CorrectionResult, config: MicromechanicalConfig
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compare measured response with bilinear Voigt, Reuss and Hill bounds."""

    config.validate()
    curve = result.corrected_curve
    measured_strain = curve["corrected_engineering_strain"].to_numpy(dtype=float)
    measured_stress = curve["engineering_stress_MPa"].to_numpy(dtype=float)
    strain = np.linspace(0.0, float(measured_strain[-1]), min(500, len(curve)))
    measured = np.interp(strain, measured_strain, measured_stress)
    fraction = config.tungsten_volume_fraction
    matrix_fraction = 1.0 - fraction
    ew = config.tungsten_modulus_gpa * 1000.0
    em = config.matrix_modulus_gpa * 1000.0
    stress_w = _phase_stress(
        strain, ew, config.tungsten_yield_mpa, config.tungsten_hardening_mpa
    )
    stress_m = _phase_stress(
        strain, em, config.matrix_yield_mpa, config.matrix_hardening_mpa
    )
    voigt = fraction * stress_w + matrix_fraction * stress_m

    def composite_strain(stress: float) -> float:
        return fraction * _phase_strain(
            stress, ew, config.tungsten_yield_mpa, config.tungsten_hardening_mpa
        ) + matrix_fraction * _phase_strain(
            stress, em, config.matrix_yield_mpa, config.matrix_hardening_mpa
        )

    reuss = np.empty_like(strain)
    for index, target in enumerate(strain):
        low = 0.0
        high = max(float(voigt[index]) * 2.0, 1.0)
        while composite_strain(high) < target:
            high *= 2.0
        for _ in range(70):
            middle = 0.5 * (low + high)
            if composite_strain(middle) < target:
                low = middle
            else:
                high = middle
        reuss[index] = 0.5 * (low + high)
    hill = 0.5 * (voigt + reuss)
    modulus_voigt = fraction * ew + matrix_fraction * em
    modulus_reuss = 1.0 / (fraction / ew + matrix_fraction / em)
    modulus_hill = 0.5 * (modulus_voigt + modulus_reuss)

    def rmse(prediction: np.ndarray) -> float:
        return float(np.sqrt(np.mean((measured - prediction) ** 2)))

    data = pd.DataFrame(
        {
            "engineering_strain": strain,
            "measured_engineering_stress_MPa": measured,
            "W_phase_iso_strain_stress_MPa": stress_w,
            "matrix_phase_iso_strain_stress_MPa": stress_m,
            "Voigt_stress_MPa": voigt,
            "Reuss_stress_MPa": reuss,
            "Hill_stress_MPa": hill,
        }
    )
    summary: dict[str, object] = {
        "status": "ok",
        "method": "bilinear two-phase Voigt-Reuss-Hill load-sharing bounds",
        "Voigt_modulus_GPa": float(modulus_voigt / 1000.0),
        "Reuss_modulus_GPa": float(modulus_reuss / 1000.0),
        "Hill_modulus_GPa": float(modulus_hill / 1000.0),
        "target_corrected_modulus_GPa": result.config.target_modulus_mpa / 1000.0,
        "Voigt_RMSE_MPa": rmse(voigt),
        "Reuss_RMSE_MPa": rmse(reuss),
        "Hill_RMSE_MPa": rmse(hill),
        "reference": "https://doi.org/10.1016/j.msea.2013.11.007",
        "inputs": asdict(config),
        "caveat": (
            "These are one-dimensional bilinear load-sharing bounds, not an "
            "interface-resolved or crystal-plasticity solution. Phase parameters "
            "must be independently justified before physical interpretation."
        ),
    }
    return data, summary


def _isotropic_bulk_shear(modulus_mpa: float, poisson: float) -> tuple[float, float]:
    bulk = modulus_mpa / (3.0 * (1.0 - 2.0 * poisson))
    shear = modulus_mpa / (2.0 * (1.0 + poisson))
    return bulk, shear


def _mori_tanaka_modulus(
    micromechanical: MicromechanicalConfig, advanced: AdvancedWHAConfig
) -> float:
    """Isotropic spherical-inclusion Mori-Tanaka elastic modulus (MPa)."""

    ew = micromechanical.tungsten_modulus_gpa * 1000.0
    em = micromechanical.matrix_modulus_gpa * 1000.0
    kw, gw = _isotropic_bulk_shear(ew, advanced.tungsten_poisson_ratio)
    km, gm = _isotropic_bulk_shear(em, advanced.matrix_poisson_ratio)
    fraction = micromechanical.tungsten_volume_fraction
    bulk = km + fraction * (kw - km) / (
        1.0 + (1.0 - fraction) * (kw - km) / (km + 4.0 * gm / 3.0)
    )
    zeta = gm * (9.0 * km + 8.0 * gm) / (6.0 * (km + 2.0 * gm))
    shear = gm + fraction * (gw - gm) / (
        1.0 + (1.0 - fraction) * (gw - gm) / (gm + zeta)
    )
    return 9.0 * bulk * shear / (3.0 * bulk + shear)


def analyze_advanced_wha(
    result: CorrectionResult,
    micromechanical: MicromechanicalConfig,
    advanced: AdvancedWHAConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Build requested WHA homogenization/sensitivity views from stated inputs."""

    micromechanical.validate()
    advanced.validate()
    if result.micromechanical is None or result.micromechanical.empty:
        result.micromechanical, _ = analyze_micromechanics(result, micromechanical)
    base = result.micromechanical.copy()
    fraction = micromechanical.tungsten_volume_fraction
    matrix_fraction = 1.0 - fraction
    mt_modulus = _mori_tanaka_modulus(micromechanical, advanced)
    elastic_limit = min(
        micromechanical.tungsten_yield_mpa / mt_modulus,
        micromechanical.matrix_yield_mpa / mt_modulus,
    )
    base["Mori_Tanaka_elastic_stress_MPa"] = np.where(
        base["engineering_strain"] <= elastic_limit,
        mt_modulus * base["engineering_strain"],
        np.nan,
    )
    macro = base["Voigt_stress_MPa"].to_numpy(dtype=float)
    w_stress = base["W_phase_iso_strain_stress_MPa"].to_numpy(dtype=float)
    m_stress = base["matrix_phase_iso_strain_stress_MPa"].to_numpy(dtype=float)
    load_partition = pd.DataFrame(
        {
            "engineering_strain": base["engineering_strain"],
            "W_phase_stress_MPa": w_stress,
            "matrix_phase_stress_MPa": m_stress,
            "W_load_share_fraction": fraction * w_stress / np.maximum(macro, 1.0e-12),
            "matrix_load_share_fraction": matrix_fraction
            * m_stress
            / np.maximum(macro, 1.0e-12),
        }
    )
    interface_factor = 4.0 * fraction * matrix_fraction
    interface = pd.DataFrame(
        {
            "interface_strength_input_MPa": np.linspace(
                0.0, 2.0 * advanced.interface_strength_mpa, 160
            ),
        }
    )
    interface["load_transfer_increment_MPa"] = (
        interface_factor * interface["interface_strength_input_MPa"]
    )
    contiguity = pd.DataFrame({"W_W_contiguity": np.linspace(0.0, 1.0, 160)})
    contiguity["empirical_strength_correction_MPa"] = -(
        advanced.contiguity_coefficient_mpa * contiguity["W_W_contiguity"]
    )
    porosity_factor = (
        1.0 - advanced.porosity_fraction
    ) ** advanced.porosity_strength_exponent
    porosity = pd.DataFrame(
        {
            "engineering_strain": base["engineering_strain"],
            "Hill_dense_stress_MPa": base["Hill_stress_MPa"],
            "porosity_corrected_Hill_stress_MPa": porosity_factor
            * base["Hill_stress_MPa"],
        }
    )
    phase_flow = base[
        [
            "engineering_strain",
            "W_phase_iso_strain_stress_MPa",
            "matrix_phase_iso_strain_stress_MPa",
        ]
    ].copy()
    if result.dislocation_density is None or result.dislocation_density.empty:
        density = pd.DataFrame()
    else:
        density = result.dislocation_density
    two_phase_density = pd.DataFrame(
        {
            "true_plastic_strain": density.get(
                "true_plastic_strain", pd.Series(dtype=float)
            ),
            "effective_apparent_density_m-2": density.get(
                "apparent_dislocation_density_m-2", pd.Series(dtype=float)
            ),
        }
    )
    if not two_phase_density.empty:
        two_phase_density["W_phase_scenario_density_m-2"] = (
            advanced.tungsten_density_multiplier
            * two_phase_density["effective_apparent_density_m-2"]
        )
        two_phase_density["matrix_phase_scenario_density_m-2"] = (
            advanced.matrix_density_multiplier
            * two_phase_density["effective_apparent_density_m-2"]
        )
    data = {
        "rule_mixtures": base[
            [
                "engineering_strain",
                "measured_engineering_stress_MPa",
                "Voigt_stress_MPa",
                "Reuss_stress_MPa",
                "Hill_stress_MPa",
            ]
        ].copy(),
        "iso_responses": base[
            [
                "engineering_strain",
                "W_phase_iso_strain_stress_MPa",
                "matrix_phase_iso_strain_stress_MPa",
                "Voigt_stress_MPa",
                "Reuss_stress_MPa",
            ]
        ].copy(),
        "mori_tanaka": base[
            [
                "engineering_strain",
                "measured_engineering_stress_MPa",
                "Mori_Tanaka_elastic_stress_MPa",
            ]
        ].copy(),
        "load_partition": load_partition,
        "interface": interface,
        "contiguity": contiguity,
        "porosity": porosity,
        "phase_flow": phase_flow,
        "two_phase_dislocation": two_phase_density,
    }
    summary: dict[str, object] = {
        "status": "ok",
        "Mori_Tanaka_elastic_modulus_GPa": mt_modulus / 1000.0,
        "Mori_Tanaka_elastic_strain_limit": elastic_limit,
        "Voigt_elastic_modulus_GPa": (
            fraction * micromechanical.tungsten_modulus_gpa
            + matrix_fraction * micromechanical.matrix_modulus_gpa
        ),
        "Reuss_elastic_modulus_GPa": 1.0
        / (
            fraction / micromechanical.tungsten_modulus_gpa
            + matrix_fraction / micromechanical.matrix_modulus_gpa
        ),
        "current_interface_load_transfer_increment_MPa": (
            interface_factor * advanced.interface_strength_mpa
        ),
        "current_W_W_contiguity_correction_MPa": -(
            advanced.contiguity_coefficient_mpa * advanced.ww_contiguity
        ),
        "porosity_strength_factor": porosity_factor,
        "references": [
            "https://doi.org/10.1016/j.msea.2013.11.007",
            "https://doi.org/10.1016/j.msea.2010.08.071",
            "https://doi.org/10.1179/pom.1979.22.4.175",
        ],
        "micromechanical_inputs": asdict(micromechanical),
        "advanced_inputs": asdict(advanced),
        "caveat": (
            "Mori-Tanaka is a linear-elastic spherical-inclusion estimate. Interface, "
            "contiguity, porosity, and two-phase density views are transparent "
            "parameter sensitivities, not independently calibrated WHA failure or "
            "phase-resolved dislocation models."
        ),
    }
    return data, summary
