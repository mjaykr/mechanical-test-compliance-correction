import pytest

from mechtest_correction import CorrectionConfig, correct_curve, publication
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


def test_ieee_export_automatically_uses_labelled_no_latex_fallback(
    tmp_path, synthetic_curve, monkeypatch
):
    frame, _, _ = synthetic_curve
    result = correct_curve(
        frame,
        CorrectionConfig(
            mode="compression",
            target_modulus_mpa=400_000.0,
            fit_axis="stress",
            fit_min=100.0,
            fit_max=300.0,
        ),
    )
    monkeypatch.setattr(publication.shutil, "which", lambda _: None)

    outputs = export_ieee_panel(result, "macroscopic", tmp_path / "auto_ieee")

    assert all(path.is_file() for path in outputs)
    assert all("_draft_no_latex" in path.name for path in outputs)


def test_explicit_latex_request_reports_missing_latex(monkeypatch):
    monkeypatch.setattr(publication.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="LaTeX was requested"):
        publication._resolve_latex_mode(True)


def test_auto_export_prioritises_latex_when_it_is_available(monkeypatch):
    monkeypatch.setattr(publication.shutil, "which", lambda _: "C:/tex/latex.exe")

    assert publication._resolve_latex_mode(None) is True
