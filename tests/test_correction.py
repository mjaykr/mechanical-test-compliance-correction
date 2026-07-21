from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mechtest_correction import CorrectionConfig, correct_curve


def make_config(mode: str = "tension") -> CorrectionConfig:
    return CorrectionConfig(
        mode=mode,
        target_modulus_mpa=200_000.0,
        fit_axis="stress",
        fit_min=100.0,
        fit_max=300.0,
    )


def test_recovers_known_modulus_and_specimen_strain(synthetic_curve):
    frame, specimen_strain, _ = synthetic_curve
    result = correct_curve(frame, make_config())

    assert result.summary["apparent_modulus_GPa"] == pytest.approx(
        1.0 / (1.0 / 200.0 + 0.008), rel=1e-10
    )
    assert result.summary["recovered_output_modulus_GPa"] == pytest.approx(
        200.0, rel=1e-10
    )
    source_rows = result.corrected_curve["source_row"].to_numpy(dtype=int)
    corrected = result.corrected_curve["corrected_engineering_strain"].to_numpy()
    measured_rows = source_rows > 0
    assert corrected[measured_rows] == pytest.approx(
        specimen_strain[source_rows[measured_rows] - 1], abs=1e-12
    )


def test_offset_proof_stress_is_recovered(synthetic_curve):
    frame, _, _ = synthetic_curve
    result = correct_curve(frame, make_config())
    assert result.summary["proof_strain"] == pytest.approx(0.00404, rel=2e-3)
    assert result.summary["proof_stress_MPa"] == pytest.approx(408.0, abs=0.2)


def test_tensile_properties_are_reported(synthetic_curve):
    frame, _, _ = synthetic_curve
    result = correct_curve(frame, make_config("tension"))
    properties = result.summary["mechanical_properties"]
    assert properties["proof_stress_0_2pct"]["value"] == pytest.approx(408.0, abs=0.2)
    assert properties["ultimate_tensile_strength"]["value"] == 1000.0
    assert properties["toughness_to_end"]["value"] > 0.0


def test_compression_properties_include_specified_strains(synthetic_curve):
    frame, _, _ = synthetic_curve
    result = correct_curve(frame, make_config("compression"))
    properties = result.summary["mechanical_properties"]
    assert properties["stress_at_1pct_strain"]["value"] is not None
    assert properties["maximum_compressive_stress"]["value"] == 1000.0


@pytest.mark.parametrize("mode", ["tension", "compression"])
def test_true_conversion(mode, synthetic_curve):
    frame, _, _ = synthetic_curve
    result = correct_curve(frame, make_config(mode))
    curve = result.corrected_curve
    e = curve["corrected_engineering_strain"].to_numpy()
    s = curve["engineering_stress_MPa"].to_numpy()
    if mode == "tension":
        assert curve["true_strain"].to_numpy() == pytest.approx(np.log1p(e))
        assert curve["true_stress_MPa"].to_numpy() == pytest.approx(s * (1 + e))
    else:
        assert curve["true_strain"].to_numpy() == pytest.approx(-np.log1p(-e))
        assert curve["true_stress_MPa"].to_numpy() == pytest.approx(s * (1 - e))


def test_auto_sign_normalizes_negative_compression_export(synthetic_curve):
    frame, _, _ = synthetic_curve
    negative = pd.DataFrame(
        {
            "engineering_strain": -frame["engineering_strain"],
            "engineering_stress": -frame["engineering_stress"],
        }
    )
    result = correct_curve(negative, make_config("compression"))
    assert result.summary["strain_sign_multiplier"] == -1.0
    assert result.summary["stress_sign_multiplier"] == -1.0
    assert result.corrected_curve["engineering_stress_MPa"].iloc[-1] == 1000.0


def test_target_must_exceed_apparent_modulus(synthetic_curve):
    frame, _, _ = synthetic_curve
    config = CorrectionConfig(
        mode="tension",
        target_modulus_mpa=50_000.0,
        fit_axis="stress",
        fit_min=100.0,
        fit_max=300.0,
    )
    with pytest.raises(ValueError, match="does not exceed"):
        correct_curve(frame, config)
