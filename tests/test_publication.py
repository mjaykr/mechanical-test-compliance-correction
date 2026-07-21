from mechtest_correction import CorrectionConfig, correct_curve
from mechtest_correction.publication import export_ieee_panel, panel_data


def test_each_analysis_panel_has_exportable_data(synthetic_curve):
    frame, _, _ = synthetic_curve
    config = CorrectionConfig(
        mode="tension",
        target_modulus_mpa=200_000.0,
        fit_axis="stress",
        fit_min=100.0,
        fit_max=300.0,
    )
    result = correct_curve(frame, config)
    for panel in ("macroscopic", "constitutive", "work_hardening"):
        assert not panel_data(result, panel).empty


def test_ieee_export_can_render_without_latex_for_ci(tmp_path, synthetic_curve):
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
    outputs = export_ieee_panel(
        result, "macroscopic", tmp_path / "macro_ieee", use_latex=False
    )
    assert all(path.is_file() for path in outputs)
