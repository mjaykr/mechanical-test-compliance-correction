from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mechtest_correction.advanced_constitutive import (
    AdvancedConstitutiveConfig,
    fit_advanced_constitutive,
    prepare_multicondition_data,
)


def multicondition_frame() -> pd.DataFrame:
    rows = []
    config = AdvancedConstitutiveConfig()
    for rate in (1.0e-3, 1.0, 1.0e3):
        for temperature in (293.15, 773.15):
            for strain in np.linspace(0.002, 0.20, 28):
                homologous = (temperature - config.reference_temperature_k) / (
                    config.melting_temperature_k - config.reference_temperature_k
                )
                stress = (
                    (650.0 + 1_100.0 * strain**0.32)
                    * (1.0 + 0.018 * np.log(rate / config.reference_strain_rate_s))
                    * (1.0 - homologous**1.1)
                )
                rows.append(
                    {
                        "epsp": strain,
                        "sigma": stress,
                        "rate": rate,
                        "temp": temperature,
                        "test": f"{rate:g} s^-1, {temperature:g} K",
                    }
                )
    return pd.DataFrame(rows)


def test_multicondition_models_fit_and_rank_synthetic_johnson_cook_data():
    data = prepare_multicondition_data(
        multicondition_frame(),
        strain_column="epsp",
        stress_column="sigma",
        strain_rate_column="rate",
        temperature_column="temp",
        condition_column="test",
    )
    outputs, summary = fit_advanced_constitutive(data, AdvancedConstitutiveConfig())
    assert len(outputs) == 5
    assert summary["best_model_by_AIC"] == "Johnson-Cook"
    assert summary["models"]["johnson_cook"]["RMSE_MPa"] < 1.0
    assert outputs["johnson_cook"]["predicted_flow_stress_MPa"].notna().all()


def test_rate_temperature_fit_rejects_unidentifiable_single_condition():
    frame = multicondition_frame()
    frame = frame[(frame["rate"] == 1.0e-3) & (frame["temp"] == 293.15)]
    data = prepare_multicondition_data(
        frame,
        strain_column="epsp",
        stress_column="sigma",
        strain_rate_column="rate",
        temperature_column="temp",
    )
    with pytest.raises(ValueError, match="at least two strain rates"):
        fit_advanced_constitutive(data, AdvancedConstitutiveConfig())
