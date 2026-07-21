from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mechtest_correction import CorrectionConfig, correct_curve
from mechtest_correction.advanced_constitutive import (
    AdvancedConstitutiveConfig,
    fit_advanced_constitutive,
    prepare_multicondition_data,
)
from mechtest_correction.cli import write_outputs
from mechtest_correction.high_rate import SHPBConfig, analyze_shpb, prepare_shpb_waves
from mechtest_correction.plot_registry import PLOT_SPECS, plot_data
from mechtest_correction.publication import export_ieee_plot, panel_data
from mechtest_correction.wha_models import (
    AdvancedWHAConfig,
    DislocationConfig,
    MicromechanicalConfig,
    MicrostructureConfig,
    analyze_advanced_wha,
    analyze_dislocation_density,
    analyze_hall_petch,
    analyze_micromechanics,
)


@pytest.fixture
def wha_result(synthetic_curve):
    frame, _, _ = synthetic_curve
    result = correct_curve(
        frame,
        CorrectionConfig(
            mode="tension",
            target_modulus_mpa=200_000.0,
            fit_axis="stress",
            fit_min=100.0,
            fit_max=300.0,
        ),
    )
    result.hall_petch, hp = analyze_hall_petch(result, MicrostructureConfig())
    result.dislocation_density, density = analyze_dislocation_density(
        result, DislocationConfig()
    )
    result.micromechanical, micromechanical = analyze_micromechanics(
        result, MicromechanicalConfig()
    )
    result.summary["hall_petch_analysis"] = hp
    result.summary["dislocation_density_analysis"] = density
    result.summary["micromechanical_analysis"] = micromechanical
    result.advanced_wha, advanced = analyze_advanced_wha(
        result, MicromechanicalConfig(), AdvancedWHAConfig()
    )
    result.summary["advanced_wha_analysis"] = advanced
    time_us = np.linspace(0.0, 200.0, 401)
    pulse = np.sin(np.pi * time_us / time_us.max())
    waves = prepare_shpb_waves(
        pd.DataFrame(
            {
                "time": time_us,
                "incident": 1.0e-3 * pulse,
                "reflected": -2.5e-4 * pulse,
                "transmitted": 6.0e-4 * pulse,
            }
        ),
        time_column="time",
        incident_column="incident",
        reflected_column="reflected",
        transmitted_column="transmitted",
    )
    result.high_rate, shpb = analyze_shpb(waves, SHPBConfig())
    result.summary["shpb_analysis"] = shpb
    constitutive_rows = []
    for rate in (1.0e-3, 1.0e3):
        for temperature in (293.15, 773.15):
            for strain in np.linspace(0.002, 0.2, 20):
                homologous = (temperature - 293.15) / (3695.0 - 293.15)
                stress = (
                    (650.0 + 1100.0 * strain**0.32)
                    * (1.0 + 0.018 * np.log(rate / 1.0e-3))
                    * (1.0 - homologous**1.1)
                )
                constitutive_rows.append(
                    {
                        "plastic_strain": strain,
                        "flow_stress_MPa": stress,
                        "strain_rate_s-1": rate,
                        "temperature_K": temperature,
                    }
                )
    constitutive_data = prepare_multicondition_data(
        pd.DataFrame(constitutive_rows),
        strain_column="plastic_strain",
        stress_column="flow_stress_MPa",
        strain_rate_column="strain_rate_s-1",
        temperature_column="temperature_K",
    )
    result.advanced_constitutive, constitutive_summary = fit_advanced_constitutive(
        constitutive_data, AdvancedConstitutiveConfig()
    )
    result.summary["advanced_constitutive_analysis"] = constitutive_summary
    return result


def test_hall_petch_is_a_traceable_projection(wha_result):
    summary = wha_result.summary["hall_petch_analysis"]
    total = (
        summary["base_stress_MPa"]
        + summary["W_Hall_Petch_contribution_MPa"]
        + summary["matrix_Hall_Petch_contribution_MPa"]
    )
    assert summary["predicted_yield_stress_MPa"] == pytest.approx(total)
    assert "not a Hall-Petch regression" in summary["caveat"]
    assert len(wha_result.hall_petch) == 240


def test_dislocation_model_reports_positive_apparent_density(wha_result):
    data = wha_result.dislocation_density
    summary = wha_result.summary["dislocation_density_analysis"]
    assert summary["status"] == "ok"
    assert (data["apparent_dislocation_density_m-2"] > 0.0).all()
    assert np.isfinite(data["KM_fitted_true_stress_MPa"]).all()
    assert summary["KM_storage_k1_m-1"] > 0.0
    assert "effective apparent composite density" in summary["caveat"]


def test_micromechanical_bounds_and_moduli_are_ordered(wha_result):
    data = wha_result.micromechanical
    summary = wha_result.summary["micromechanical_analysis"]
    assert summary["Reuss_modulus_GPa"] < summary["Hill_modulus_GPa"]
    assert summary["Hill_modulus_GPa"] < summary["Voigt_modulus_GPa"]
    assert (data["Reuss_stress_MPa"] <= data["Voigt_stress_MPa"] + 1.0e-9).all()


def test_advanced_wha_homogenization_and_sensitivities(wha_result):
    data = wha_result.advanced_wha
    summary = wha_result.summary["advanced_wha_analysis"]
    assert set(data) == {
        "rule_mixtures",
        "iso_responses",
        "mori_tanaka",
        "load_partition",
        "interface",
        "contiguity",
        "porosity",
        "phase_flow",
        "two_phase_dislocation",
    }
    assert (
        summary["Reuss_elastic_modulus_GPa"]
        < summary["Mori_Tanaka_elastic_modulus_GPa"]
    )
    assert (
        summary["Mori_Tanaka_elastic_modulus_GPa"]
        < summary["Voigt_elastic_modulus_GPa"]
    )
    shares = data["load_partition"]
    nonzero_shares = shares.loc[shares["W_phase_stress_MPa"] > 0.0]
    assert np.allclose(
        nonzero_shares["W_load_share_fraction"]
        + nonzero_shares["matrix_load_share_fraction"],
        1.0,
    )
    porosity = data["porosity"]
    assert (
        porosity["porosity_corrected_Hill_stress_MPa"]
        <= porosity["Hill_dense_stress_MPa"]
    ).all()


def test_registry_exposes_every_plot_and_new_panel_data(wha_result):
    assert len(PLOT_SPECS) == 28
    for spec in PLOT_SPECS:
        assert not plot_data(wha_result, spec.plot_id).empty
    for panel in (
        "microstructure",
        "dislocation",
        "micromechanical",
        "advanced_wha",
        "shpb",
        "advanced_constitutive",
    ):
        assert not panel_data(wha_result, panel).empty


def test_individual_plot_ieee_export(tmp_path, wha_result):
    outputs = export_ieee_plot(
        wha_result,
        "dislocation.density",
        tmp_path / "density_ieee",
        use_latex=False,
    )
    assert all(path.is_file() for path in outputs)


def test_complete_export_includes_wha_analysis_artifacts(tmp_path, wha_result):
    source = tmp_path / "source.csv"
    source.write_text("strain,stress\n0,0\n", encoding="utf-8")
    output = tmp_path / "results"
    write_outputs(wha_result, output, input_file=source)
    expected = {
        "hall_petch_data.csv",
        "hall_petch_summary.csv",
        "dislocation_density_data.csv",
        "dislocation_density_summary.csv",
        "micromechanical_data.csv",
        "micromechanical_summary.csv",
        "microstructure_hall_petch.png",
        "microstructure_hall_petch.pdf",
        "dislocation_density.png",
        "dislocation_density.pdf",
        "wha_two_phase.png",
        "wha_two_phase.pdf",
        "advanced_wha_summary.csv",
        "advanced_wha_mori_tanaka_data.csv",
        "advanced_wha_two_phase_dislocation_data.csv",
        "shpb_waves_data.csv",
        "shpb_response_data.csv",
        "shpb_summary.csv",
        "advanced_constitutive_johnson_cook_data.csv",
        "advanced_constitutive_summary.csv",
    }
    assert expected <= {path.name for path in output.iterdir()}
