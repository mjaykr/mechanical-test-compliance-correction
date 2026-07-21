from __future__ import annotations

import json

from mechtest_correction.cli import main


def test_cli_creates_expected_outputs(tmp_path, synthetic_curve):
    frame, _, _ = synthetic_curve
    input_path = tmp_path / "curve.csv"
    output_dir = tmp_path / "results"
    frame.to_csv(input_path, index=False)

    return_code = main(
        [
            str(input_path),
            "--mode",
            "tension",
            "--target-modulus-gpa",
            "200",
            "--fit-axis",
            "stress",
            "--fit-min",
            "100",
            "--fit-max",
            "300",
            "--strain-column",
            "engineering_strain",
            "--stress-column",
            "engineering_stress",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert return_code == 0
    expected = {
        "correction_audit.csv",
        "corrected_curve.csv",
        "mechanical_properties.csv",
        "flow_model_fits.csv",
        "flow_fit_data.csv",
        "summary.json",
        "stress_strain_comparison.png",
        "stress_strain_comparison.pdf",
        "corrected_data_analysis.png",
        "corrected_data_analysis.pdf",
    }
    assert expected == {path.name for path in output_dir.iterdir()}
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["target_modulus_GPa"] == 200.0
