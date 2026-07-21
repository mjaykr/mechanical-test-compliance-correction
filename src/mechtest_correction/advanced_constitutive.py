"""Multi-condition strain-rate and temperature constitutive fitting."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

MODEL_LABELS = {
    "johnson_cook": "Johnson-Cook",
    "zerilli_armstrong_bcc": "Zerilli-Armstrong (BCC)",
    "khan_huang_liang": "Khan-Huang-Liang",
    "extended_voce": "Rate-temperature Voce",
    "modified_arrhenius": "Modified Arrhenius",
}

MODEL_EQUATIONS = {
    "johnson_cook": "(A+B eps^n)(1+C ln(rate/rate0))(1-T*^m)",
    "zerilli_armstrong_bcc": "C0+C1 exp[(-C3+C4 ln(rate/rate0))T]+C5 eps^n",
    "khan_huang_liang": "[A+B(1-ln(rate/rate0)/ln(D0))^n1 eps^n0] rate*^C (1-T*^m)",
    "extended_voce": (
        "[sigma_sat-(sigma_sat-sigma0)exp(-beta eps)] rate-temperature factors"
    ),
    "modified_arrhenius": "asinh{[rate exp(Q/RT)/A(eps)]^(1/n)}/alpha",
}


@dataclass(frozen=True)
class AdvancedConstitutiveConfig:
    """Reference values used by multi-condition flow-law fits."""

    reference_strain_rate_s: float = 1.0e-3
    reference_temperature_k: float = 293.15
    melting_temperature_k: float = 3_695.0
    khl_upper_rate_s: float = 1.0e6

    def validate(self) -> None:
        if self.reference_strain_rate_s <= 0.0 or self.khl_upper_rate_s <= 0.0:
            raise ValueError("Reference and KHL upper strain rates must be positive")
        if self.reference_temperature_k <= 0.0:
            raise ValueError("Reference temperature must be positive")
        if self.melting_temperature_k <= self.reference_temperature_k:
            raise ValueError("Melting temperature must exceed reference temperature")
        if self.khl_upper_rate_s <= self.reference_strain_rate_s:
            raise ValueError("KHL upper strain rate must exceed the reference rate")


def prepare_multicondition_data(
    frame: pd.DataFrame,
    *,
    strain_column: str,
    stress_column: str,
    strain_rate_column: str,
    temperature_column: str,
    condition_column: str = "",
) -> pd.DataFrame:
    """Map a tidy multi-test table to the canonical fit columns."""

    required = (strain_column, stress_column, strain_rate_column, temperature_column)
    missing = [name for name in required if not name or name not in frame.columns]
    if missing:
        raise ValueError(f"Missing constitutive-data columns: {missing}")
    selected = frame.loc[:, list(required)].apply(pd.to_numeric, errors="coerce")
    selected.columns = (
        "plastic_strain",
        "flow_stress_MPa",
        "strain_rate_s-1",
        "temperature_K",
    )
    if condition_column and condition_column in frame.columns:
        selected["condition"] = frame.loc[selected.index, condition_column].astype(str)
    else:
        selected["condition"] = (
            selected["strain_rate_s-1"].map(lambda value: f"{value:g} s^-1")
            + ", "
            + selected["temperature_K"].map(lambda value: f"{value:g} K")
        )
    selected = (
        selected.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    )
    selected = selected[
        (selected["plastic_strain"] >= 0.0)
        & (selected["flow_stress_MPa"] > 0.0)
        & (selected["strain_rate_s-1"] > 0.0)
        & (selected["temperature_K"] > 0.0)
    ].reset_index(drop=True)
    if len(selected) < 20:
        raise ValueError(
            "At least 20 valid multi-condition flow observations are required"
        )
    return selected


def _normalized_inputs(data: pd.DataFrame, config: AdvancedConstitutiveConfig):
    strain = data["plastic_strain"].to_numpy(dtype=float)
    stress = data["flow_stress_MPa"].to_numpy(dtype=float)
    rate = data["strain_rate_s-1"].to_numpy(dtype=float)
    temperature = data["temperature_K"].to_numpy(dtype=float)
    rate_star = np.maximum(rate / config.reference_strain_rate_s, 1.0e-12)
    homologous = np.clip(
        (temperature - config.reference_temperature_k)
        / (config.melting_temperature_k - config.reference_temperature_k),
        0.0,
        0.999999,
    )
    return strain, stress, rate, temperature, rate_star, homologous


def _predict(
    model: str,
    values: np.ndarray,
    data: pd.DataFrame,
    config: AdvancedConstitutiveConfig,
) -> np.ndarray:
    strain, _, rate, temperature, rate_star, homologous = _normalized_inputs(
        data, config
    )
    eps = np.maximum(strain, 1.0e-10)
    if model == "johnson_cook":
        a, b, n, c, m = values
        return (
            (a + b * eps**n)
            * np.maximum(1.0 + c * np.log(rate_star), 0.01)
            * (1.0 - homologous**m)
        )
    if model == "zerilli_armstrong_bcc":
        c0, c1, c3, c4, c5, n = values
        exponent = np.clip((-c3 + c4 * np.log(rate_star)) * temperature, -50.0, 30.0)
        return c0 + c1 * np.exp(exponent) + c5 * eps**n
    if model == "khan_huang_liang":
        a, b, n0, n1, c, m = values
        coupling = np.maximum(
            1.0
            - np.log(rate_star)
            / np.log(config.khl_upper_rate_s / config.reference_strain_rate_s),
            1.0e-6,
        )
        return (a + b * coupling**n1 * eps**n0) * rate_star**c * (1.0 - homologous**m)
    if model == "extended_voce":
        sigma_sat, sigma0, beta, c, m = values
        hardening = sigma_sat - (sigma_sat - sigma0) * np.exp(-beta * eps)
        return (
            hardening
            * np.maximum(1.0 + c * np.log(rate_star), 0.01)
            * (1.0 - homologous**m)
        )
    if model == "modified_arrhenius":
        log_a0, log_a1, alpha, n, q_kj_mol = values
        gas_constant = 8.314462618
        log_z_over_a = (
            np.log(rate)
            + q_kj_mol * 1_000.0 / (gas_constant * temperature)
            - (log_a0 + log_a1 * eps)
        )
        return np.arcsinh(np.exp(np.clip(log_z_over_a / n, -40.0, 40.0))) / alpha
    raise ValueError(f"Unknown advanced constitutive model: {model}")


def _setup(model: str, data: pd.DataFrame):
    stress = data["flow_stress_MPa"].to_numpy(dtype=float)
    low, high = float(np.percentile(stress, 10)), float(np.percentile(stress, 95))
    span = max(high - low, 10.0)
    if model == "johnson_cook":
        return (
            [low, span, 0.25, 0.01, 1.0],
            [0, 0, 0.01, -0.2, 0.05],
            [5 * high, 20 * high, 2, 0.5, 5],
        )
    if model == "zerilli_armstrong_bcc":
        return (
            [low * 0.5, low, 0.002, 1e-5, span, 0.3],
            [0, 0, 0, -0.002, 0, 0.01],
            [5 * high, 10 * high, 0.05, 0.002, 20 * high, 2],
        )
    if model == "khan_huang_liang":
        return (
            [low, span, 0.25, 0.5, 0.01, 1.0],
            [0, -20 * high, 0.01, 0.01, -0.2, 0.05],
            [5 * high, 20 * high, 2, 5, 0.5, 5],
        )
    if model == "extended_voce":
        return (
            [high * 1.1, low, 15.0, 0.01, 1.0],
            [0, 0, 1e-4, -0.2, 0.05],
            [20 * high, 10 * high, 1e4, 0.5, 5],
        )
    if model == "modified_arrhenius":
        return (
            [20.0, 1.0, 0.005, 5.0, 250.0],
            [-50, -100, 1e-5, 0.2, 1],
            [100, 100, 0.2, 50, 2_000],
        )
    raise ValueError(model)


PARAMETER_NAMES = {
    "johnson_cook": ("A_MPa", "B_MPa", "n", "C", "m"),
    "zerilli_armstrong_bcc": ("C0_MPa", "C1_MPa", "C3_K-1", "C4_K-1", "C5_MPa", "n"),
    "khan_huang_liang": ("A_MPa", "B_MPa", "n0", "n1", "C", "m"),
    "extended_voce": ("sigma_sat_MPa", "sigma0_MPa", "beta", "C", "m"),
    "modified_arrhenius": ("lnA0", "lnA_strain", "alpha_MPa-1", "n", "Q_kJ_mol"),
}


def fit_advanced_constitutive(
    data: pd.DataFrame, config: AdvancedConstitutiveConfig
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Fit all supported laws to a multi-rate, multi-temperature flow dataset."""

    config.validate()
    rate_count = data["strain_rate_s-1"].nunique()
    temperature_count = data["temperature_K"].nunique()
    if rate_count < 2 or temperature_count < 2:
        raise ValueError(
            "Rate-temperature fitting requires at least two strain rates and "
            "two temperatures"
        )
    observed = data["flow_stress_MPa"].to_numpy(dtype=float)
    scale = max(float(np.std(observed)), 1.0)
    outputs: dict[str, pd.DataFrame] = {}
    summaries: dict[str, object] = {}
    for model in MODEL_LABELS:
        initial, lower, upper = _setup(model, data)
        fit = least_squares(
            lambda values, current_model=model: (
                (_predict(current_model, values, data, config) - observed) / scale
            ),
            x0=initial,
            bounds=(lower, upper),
            max_nfev=50_000,
        )
        predicted = _predict(model, fit.x, data, config)
        residual = observed - predicted
        ss_res = float(np.sum(residual**2))
        ss_total = float(np.sum((observed - np.mean(observed)) ** 2))
        rmse = float(np.sqrt(np.mean(residual**2)))
        parameter_count = len(fit.x)
        aic = float(
            len(data) * np.log(max(ss_res / len(data), 1e-30)) + 2 * parameter_count
        )
        frame = data.copy()
        frame["predicted_flow_stress_MPa"] = predicted
        frame["residual_MPa"] = residual
        outputs[model] = frame.sort_values(["condition", "plastic_strain"]).reset_index(
            drop=True
        )
        summaries[model] = {
            "label": MODEL_LABELS[model],
            "equation": MODEL_EQUATIONS[model],
            "parameters": dict(
                zip(PARAMETER_NAMES[model], map(float, fit.x), strict=True)
            ),
            "R_squared": None if ss_total == 0 else 1.0 - ss_res / ss_total,
            "RMSE_MPa": rmse,
            "AIC": aic,
            "converged": bool(fit.success),
        }
    best = min(summaries, key=lambda name: float(summaries[name]["AIC"]))
    summary: dict[str, object] = {
        "status": "ok",
        "observation_count": len(data),
        "condition_count": data["condition"].nunique(),
        "strain_rate_count": rate_count,
        "temperature_count": temperature_count,
        "best_model_by_AIC": MODEL_LABELS[best],
        "models": summaries,
        "inputs": asdict(config),
        "references": [
            "https://doi.org/10.1093/jom/ufad020",
            "https://doi.org/10.3390/ma18092061",
            "https://doi.org/10.1007/s12598-015-0620-4",
        ],
        "caveat": (
            "These are phenomenological global fits. Validate outside-sample "
            "predictions and avoid extrapolation beyond the supplied strain, "
            "strain-rate, and temperature domain. Modified Arrhenius uses a "
            "linear strain compensation for ln(A)."
        ),
    }
    return outputs, summary
