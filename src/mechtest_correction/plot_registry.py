"""Stable registry for GUI plots, their data, and individual exports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import matplotlib.pyplot as plt
import pandas as pd

from .advanced_constitutive import MODEL_LABELS
from .analysis import flow_fit_data_frame
from .models import CorrectionResult
from .plotting import (
    draw_advanced_constitutive_view,
    draw_advanced_wha_view,
    draw_constitutive_assessment,
    draw_dislocation_density,
    draw_dislocation_stress_fit,
    draw_engineering_response,
    draw_hall_petch_projection,
    draw_hardening_evolution,
    draw_kocks_mecking,
    draw_micromechanical_response,
    draw_phase_response,
    draw_shpb_view,
    draw_strengthening_contributions,
    draw_true_response,
)
from .wha_models import hall_petch_contributions

DataFunction = Callable[[CorrectionResult], pd.DataFrame]
DrawFunction = Callable[[plt.Axes, CorrectionResult], None]


@dataclass(frozen=True)
class PlotSpec:
    """One registered plot and the exact data required to reproduce it."""

    plot_id: str
    panel: str
    label: str
    default_stem: str
    draw: DrawFunction
    data: DataFunction
    latex_xlabel: str
    latex_ylabel: str


def _engineering_data(result: CorrectionResult) -> pd.DataFrame:
    return result.corrected_curve[
        [
            "corrected_engineering_strain",
            "engineering_stress_MPa",
            "target_elastic_line_MPa",
            "offset_line_MPa",
        ]
    ].copy()


def _true_data(result: CorrectionResult) -> pd.DataFrame:
    return result.corrected_curve[["true_strain", "true_stress_MPa"]].copy()


def _constitutive_data(result: CorrectionResult) -> pd.DataFrame:
    return flow_fit_data_frame(
        result.corrected_curve,
        result.summary["flow_model_fits"],
        result.config.target_modulus_mpa,
    )


def _hardening_data(result: CorrectionResult) -> pd.DataFrame:
    return (
        pd.DataFrame()
        if result.work_hardening is None
        else result.work_hardening.copy()
    )


def _hall_petch_data(result: CorrectionResult) -> pd.DataFrame:
    return pd.DataFrame() if result.hall_petch is None else result.hall_petch.copy()


def _strengthening_data(result: CorrectionResult) -> pd.DataFrame:
    return hall_petch_contributions(result.summary.get("hall_petch_analysis", {}))


def _dislocation_data(result: CorrectionResult) -> pd.DataFrame:
    return (
        pd.DataFrame()
        if result.dislocation_density is None
        else result.dislocation_density.copy()
    )


def _micromechanical_data(result: CorrectionResult) -> pd.DataFrame:
    return (
        pd.DataFrame()
        if result.micromechanical is None
        else result.micromechanical.copy()
    )


def _advanced_data(result: CorrectionResult, view: str) -> pd.DataFrame:
    return (result.advanced_wha or {}).get(view, pd.DataFrame()).copy()


def _shpb_data(result: CorrectionResult, view: str) -> pd.DataFrame:
    return (result.high_rate or {}).get(view, pd.DataFrame()).copy()


def _advanced_constitutive_data(result: CorrectionResult, model: str) -> pd.DataFrame:
    return (result.advanced_constitutive or {}).get(model, pd.DataFrame()).copy()


PLOT_SPECS = (
    PlotSpec(
        "macroscopic.engineering",
        "macroscopic",
        "Engineering stress-strain",
        "engineering_response_ieee",
        draw_engineering_response,
        _engineering_data,
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Engineering stress, $\sigma_{\mathrm{eng}}$ (MPa)",
    ),
    PlotSpec(
        "macroscopic.true",
        "macroscopic",
        "True stress-strain",
        "true_response_ieee",
        draw_true_response,
        _true_data,
        r"True strain, $\varepsilon_{\mathrm{true}}$ (\%)",
        r"True stress, $\sigma_{\mathrm{true}}$ (MPa)",
    ),
    PlotSpec(
        "constitutive.flow_models",
        "constitutive",
        "Constitutive models",
        "constitutive_models_ieee",
        draw_constitutive_assessment,
        _constitutive_data,
        r"True plastic strain, $\varepsilon_p$ (\%)",
        r"True stress, $\sigma_{\mathrm{true}}$ (MPa)",
    ),
    PlotSpec(
        "work_hardening.kocks_mecking",
        "work_hardening",
        "Kocks-Mecking theta-sigma",
        "kocks_mecking_ieee",
        draw_kocks_mecking,
        _hardening_data,
        r"True stress, $\sigma_{\mathrm{true}}$ (MPa)",
        r"Hardening rate, $\theta$ (MPa)",
    ),
    PlotSpec(
        "work_hardening.theta_evolution",
        "work_hardening",
        "Hardening-rate evolution",
        "theta_evolution_ieee",
        draw_hardening_evolution,
        _hardening_data,
        r"True plastic strain, $\varepsilon_p$ (\%)",
        r"Hardening rate, $\theta$ (MPa)",
    ),
    PlotSpec(
        "microstructure.hall_petch",
        "microstructure",
        "Hall-Petch projection",
        "hall_petch_projection_ieee",
        draw_hall_petch_projection,
        _hall_petch_data,
        r"Grain size, $d$ ($\mathrm{\mu m}$)",
        r"Predicted proof stress, $\sigma_{0.2}$ (MPa)",
    ),
    PlotSpec(
        "microstructure.strengthening",
        "microstructure",
        "Strengthening contributions",
        "strengthening_contributions_ieee",
        draw_strengthening_contributions,
        _strengthening_data,
        "Strengthening mechanism",
        r"Stress contribution (MPa)",
    ),
    PlotSpec(
        "dislocation.density",
        "dislocation",
        "Dislocation-density evolution",
        "dislocation_density_ieee",
        draw_dislocation_density,
        _dislocation_data,
        r"True plastic strain, $\varepsilon_p$ (\%)",
        r"Apparent density, $\rho$ ($\mathrm{m}^{-2}$)",
    ),
    PlotSpec(
        "dislocation.stress_fit",
        "dislocation",
        "Density-model stress fit",
        "dislocation_stress_fit_ieee",
        draw_dislocation_stress_fit,
        _dislocation_data,
        r"True plastic strain, $\varepsilon_p$ (\%)",
        r"True stress, $\sigma_{\mathrm{true}}$ (MPa)",
    ),
    PlotSpec(
        "micromechanical.bounds",
        "micromechanical",
        "Two-phase response bounds",
        "wha_two_phase_bounds_ieee",
        draw_micromechanical_response,
        _micromechanical_data,
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Engineering stress, $\sigma_{\mathrm{eng}}$ (MPa)",
    ),
    PlotSpec(
        "micromechanical.phases",
        "micromechanical",
        "Assumed phase responses",
        "wha_phase_responses_ieee",
        draw_phase_response,
        _micromechanical_data,
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Phase stress, $\sigma$ (MPa)",
    ),
    PlotSpec(
        "advanced_wha.rule_mixtures",
        "advanced_wha",
        "Rule-of-mixtures bounds",
        "rule_mixtures_ieee",
        partial(draw_advanced_wha_view, view="rule_mixtures"),
        partial(_advanced_data, view="rule_mixtures"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Engineering stress (MPa)",
    ),
    PlotSpec(
        "advanced_wha.iso_responses",
        "advanced_wha",
        "Iso-strain / iso-stress response",
        "iso_responses_ieee",
        partial(draw_advanced_wha_view, view="iso_responses"),
        partial(_advanced_data, view="iso_responses"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Stress (MPa)",
    ),
    PlotSpec(
        "advanced_wha.mori_tanaka",
        "advanced_wha",
        "Mori-Tanaka / Eshelby",
        "mori_tanaka_ieee",
        partial(draw_advanced_wha_view, view="mori_tanaka"),
        partial(_advanced_data, view="mori_tanaka"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Engineering stress (MPa)",
    ),
    PlotSpec(
        "advanced_wha.load_partition",
        "advanced_wha",
        "Phase load partition",
        "phase_load_partition_ieee",
        partial(draw_advanced_wha_view, view="load_partition"),
        partial(_advanced_data, view="load_partition"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        "Load-share fraction",
    ),
    PlotSpec(
        "advanced_wha.interface",
        "advanced_wha",
        "Interface-strength contribution",
        "interface_strength_ieee",
        partial(draw_advanced_wha_view, view="interface"),
        partial(_advanced_data, view="interface"),
        "Interface-strength input (MPa)",
        "Load-transfer increment (MPa)",
    ),
    PlotSpec(
        "advanced_wha.contiguity",
        "advanced_wha",
        "W-W contiguity correction",
        "ww_contiguity_ieee",
        partial(draw_advanced_wha_view, view="contiguity"),
        partial(_advanced_data, view="contiguity"),
        "W-W contiguity",
        "Empirical strength correction (MPa)",
    ),
    PlotSpec(
        "advanced_wha.porosity",
        "advanced_wha",
        "Porosity correction",
        "porosity_correction_ieee",
        partial(draw_advanced_wha_view, view="porosity"),
        partial(_advanced_data, view="porosity"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        r"Engineering stress (MPa)",
    ),
    PlotSpec(
        "advanced_wha.phase_flow",
        "advanced_wha",
        "Separate BCC-W / FCC-matrix flows",
        "phase_flow_ieee",
        partial(draw_advanced_wha_view, view="phase_flow"),
        partial(_advanced_data, view="phase_flow"),
        r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)",
        "Phase stress (MPa)",
    ),
    PlotSpec(
        "advanced_wha.two_phase_dislocation",
        "advanced_wha",
        "Two-phase dislocation evolution",
        "two_phase_dislocation_ieee",
        partial(draw_advanced_wha_view, view="two_phase_dislocation"),
        partial(_advanced_data, view="two_phase_dislocation"),
        r"True plastic strain, $\varepsilon_p$ (\%)",
        r"Density, $\rho$ ($\mathrm{m}^{-2}$)",
    ),
    PlotSpec(
        "shpb.waves",
        "shpb",
        "SHPB wave histories",
        "shpb_waves_ieee",
        partial(draw_shpb_view, view="waves"),
        partial(_shpb_data, view="waves"),
        r"Time, $t$ (µs)",
        r"Bar strain ($\mathrm{\mu\varepsilon}$)",
    ),
    PlotSpec(
        "shpb.response",
        "shpb",
        "SHPB dynamic response",
        "shpb_response_ieee",
        partial(draw_shpb_view, view="response"),
        partial(_shpb_data, view="response"),
        r"Specimen strain, $\varepsilon$ (\%)",
        r"Compression stress, $\sigma$ (MPa)",
    ),
    PlotSpec(
        "shpb.rate_equilibrium",
        "shpb",
        "SHPB rate and equilibrium",
        "shpb_rate_equilibrium_ieee",
        partial(draw_shpb_view, view="rate_equilibrium"),
        partial(_shpb_data, view="response"),
        r"Time, $t$ (µs)",
        r"Strain rate, $\dot{\varepsilon}$ ($\mathrm{s}^{-1}$)",
    ),
    *(
        PlotSpec(
            f"advanced_constitutive.{model}",
            "advanced_constitutive",
            label,
            f"{model}_fit_ieee",
            partial(draw_advanced_constitutive_view, model=model),
            partial(_advanced_constitutive_data, model=model),
            r"True plastic strain, $\varepsilon_p$ (\%)",
            r"True flow stress, $\sigma$ (MPa)",
        )
        for model, label in MODEL_LABELS.items()
    ),
)

REGISTRY = {spec.plot_id: spec for spec in PLOT_SPECS}


def plots_for_panel(panel: str) -> tuple[PlotSpec, ...]:
    """Return registered plots in their GUI order for one panel."""

    return tuple(spec for spec in PLOT_SPECS if spec.panel == panel)


def get_plot_spec(plot_id: str) -> PlotSpec:
    try:
        return REGISTRY[plot_id]
    except KeyError as exc:
        raise ValueError(f"Unknown plot id: {plot_id}") from exc


def plot_data(result: CorrectionResult, plot_id: str) -> pd.DataFrame:
    """Return a copy of the exact data associated with one registered plot."""

    return get_plot_spec(plot_id).data(result).copy()


def draw_registered_plot(
    axis: plt.Axes, result: CorrectionResult, plot_id: str
) -> None:
    """Draw one registry item onto an existing axis."""

    get_plot_spec(plot_id).draw(axis, result)
