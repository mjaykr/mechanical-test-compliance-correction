"""Export-only SciencePlots IEEE figures and their underlying data."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .analysis import flow_fit_data_frame
from .models import CorrectionResult
from .plot_registry import get_plot_spec, plot_data, plots_for_panel
from .plotting import (
    draw_constitutive_assessment,
    draw_dislocation_panel,
    draw_hall_petch_panel,
    draw_macroscopic_response,
    draw_micromechanical_panel,
    draw_work_hardening,
)

IEEE_SINGLE_COLUMN = 3.5
IEEE_DOUBLE_COLUMN = 7.16
GOLDEN_RATIO = 0.618


def _configure_ieee(*, use_latex: bool) -> None:
    try:
        import scienceplots  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "SciencePlots is required for IEEE export. Run install.ps1 again."
        ) from exc
    if use_latex and shutil.which("latex") is None:
        raise RuntimeError(
            "LaTeX was not found. Install MiKTeX, TeX Live, or MacTeX before "
            "exporting a final IEEE figure."
        )
    styles = ["science", "ieee"] if use_latex else ["science", "ieee", "no-latex"]
    plt.style.use(styles)
    mpl.rcParams.update(
        {
            "text.usetex": use_latex,
            "font.family": "serif",
            "font.serif": ["Times", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.labelsize": 8,
            "axes.titlesize": 8,
            "font.size": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.linewidth": 0.6,
            "lines.linewidth": 1.0,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "legend.frameon": False,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.unicode_minus": False,
            "text.latex.preamble": (
                r"\usepackage{amsmath}\usepackage{amssymb}\usepackage{siunitx}"
                if use_latex
                else ""
            ),
        }
    )


def macroscopic_plot_data(result: CorrectionResult) -> pd.DataFrame:
    """Return the data displayed in the macroscopic-response panel."""

    curve = result.corrected_curve
    return curve[
        [
            "corrected_engineering_strain",
            "engineering_stress_MPa",
            "true_strain",
            "true_stress_MPa",
            "target_elastic_line_MPa",
            "offset_line_MPa",
        ]
    ].copy()


def constitutive_plot_data(result: CorrectionResult) -> pd.DataFrame:
    """Return the experimental flow curve and every model prediction."""

    return flow_fit_data_frame(
        result.corrected_curve,
        result.summary["flow_model_fits"],
        result.config.target_modulus_mpa,
    )


def work_hardening_plot_data(result: CorrectionResult) -> pd.DataFrame:
    """Return the theta(sigma) and theta(epsilon_p) data."""

    if result.work_hardening is None:
        return pd.DataFrame()
    return result.work_hardening.copy()


def panel_data(result: CorrectionResult, panel: str) -> pd.DataFrame:
    functions = {
        "macroscopic": macroscopic_plot_data,
        "constitutive": constitutive_plot_data,
        "work_hardening": work_hardening_plot_data,
        "microstructure": lambda item: _combined_panel_data(item, panel),
        "dislocation": lambda item: _combined_panel_data(item, panel),
        "micromechanical": lambda item: _combined_panel_data(item, panel),
        "advanced_wha": lambda item: _combined_panel_data(item, panel),
        "shpb": lambda item: _combined_panel_data(item, panel),
        "advanced_constitutive": lambda item: _combined_panel_data(item, panel),
    }
    if panel not in functions:
        raise ValueError(f"Unknown export panel: {panel}")
    return functions[panel](result)


def _combined_panel_data(result: CorrectionResult, panel: str) -> pd.DataFrame:
    """Combine differently shaped subplot data with stable column prefixes."""

    frames = []
    for spec in plots_for_panel(panel):
        frame = plot_data(result, spec.plot_id).reset_index(drop=True)
        prefix = spec.plot_id.split(".", 1)[1]
        frames.append(frame.add_prefix(f"{prefix}__"))
    return pd.concat(frames, axis=1) if frames else pd.DataFrame()


def _save_figure(fig: plt.Figure, output_stem: Path) -> tuple[Path, Path, Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    pdf = output_stem.with_suffix(".pdf")
    png = output_stem.with_suffix(".png")
    tiff = output_stem.with_suffix(".tiff")
    metadata = {
        "Creator": "Mechanical Test Compliance Correction + SciencePlots IEEE",
        "Producer": "Matplotlib",
    }
    fig.savefig(pdf, metadata=metadata)
    fig.savefig(png, dpi=600)
    try:
        fig.savefig(tiff, dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    except TypeError:
        warnings.warn(
            "TIFF LZW compression unavailable; saving an uncompressed TIFF.",
            RuntimeWarning,
            stacklevel=2,
        )
        fig.savefig(tiff, dpi=600)
    return pdf, png, tiff


def _agg_subplots(*, ncols: int = 1, figsize: tuple[float, float]):
    """Create export axes without invoking an interactive GUI backend."""

    fig = Figure(figsize=figsize)
    FigureCanvasAgg(fig)
    axes = fig.subplots(nrows=1, ncols=ncols, squeeze=True)
    return fig, axes


def export_ieee_panel(
    result: CorrectionResult,
    panel: str,
    output_stem: str | Path,
    *,
    use_latex: bool = True,
) -> tuple[Path, Path, Path, Path]:
    """Export one panel as IEEE PDF/PNG/TIFF plus its source-data CSV."""

    stem = Path(output_stem)
    with plt.rc_context():
        _configure_ieee(use_latex=use_latex)
        if panel == "macroscopic":
            fig, axes = _agg_subplots(
                ncols=2,
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.62),
            )
            draw_macroscopic_response((axes[0], axes[1]), result)
            for axis in axes:
                axis.set_title("")
            axes[0].set_xlabel(r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)")
            axes[1].set_xlabel(r"True strain, $\varepsilon_{\mathrm{true}}$ (\%)")
        elif panel == "constitutive":
            fig, axis = _agg_subplots(
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.72)
            )
            draw_constitutive_assessment(axis, result)
            axis.set_title("")
            axis.set_xlabel(r"True plastic strain, $\varepsilon_{p}$ (\%)")
        elif panel == "work_hardening":
            fig, axes = _agg_subplots(
                ncols=2,
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.62),
            )
            draw_work_hardening((axes[0], axes[1]), result)
            for axis in axes:
                axis.set_title("")
            axes[1].set_xlabel(r"True plastic strain, $\varepsilon_{p}$ (\%)")
        elif panel == "microstructure":
            fig, axes = _agg_subplots(
                ncols=2,
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.62),
            )
            draw_hall_petch_panel((axes[0], axes[1]), result)
            for axis in axes:
                axis.set_title("")
            axes[0].set_xlabel(r"Grain size, $d$ ($\mathrm{\mu m}$)")
        elif panel == "dislocation":
            fig, axes = _agg_subplots(
                ncols=2,
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.62),
            )
            draw_dislocation_panel((axes[0], axes[1]), result)
            for axis in axes:
                axis.set_title("")
                axis.set_xlabel(r"True plastic strain, $\varepsilon_p$ (\%)")
        elif panel == "micromechanical":
            fig, axes = _agg_subplots(
                ncols=2,
                figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.62),
            )
            draw_micromechanical_panel((axes[0], axes[1]), result)
            for axis in axes:
                axis.set_title("")
                axis.set_xlabel(
                    r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)"
                )
        else:
            raise ValueError(f"Unknown export panel: {panel}")
        fig.tight_layout(pad=0.25)
        pdf, png, tiff = _save_figure(fig, stem)
        fig.clear()
    csv = stem.with_name(stem.name + "_data").with_suffix(".csv")
    panel_data(result, panel).to_csv(csv, index=False)
    return pdf, png, tiff, csv


def export_ieee_plot(
    result: CorrectionResult,
    plot_id: str,
    output_stem: str | Path,
    *,
    use_latex: bool = True,
) -> tuple[Path, Path, Path, Path]:
    """Export one registered subplot at IEEE single-column size plus CSV data."""

    spec = get_plot_spec(plot_id)
    data = plot_data(result, plot_id)
    if data.empty:
        raise ValueError(f"No data are available for {spec.label}")
    stem = Path(output_stem)
    with plt.rc_context():
        _configure_ieee(use_latex=use_latex)
        fig, axis = _agg_subplots(
            figsize=(IEEE_SINGLE_COLUMN, IEEE_SINGLE_COLUMN * GOLDEN_RATIO)
        )
        spec.draw(axis, result)
        axis.set_title("")
        axis.set_xlabel(spec.latex_xlabel)
        axis.set_ylabel(spec.latex_ylabel)
        fig.tight_layout(pad=0.2)
        pdf, png, tiff = _save_figure(fig, stem)
        fig.clear()
    csv = stem.with_name(stem.name + "_data").with_suffix(".csv")
    data.to_csv(csv, index=False)
    return pdf, png, tiff, csv
