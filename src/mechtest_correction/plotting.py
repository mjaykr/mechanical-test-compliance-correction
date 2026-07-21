"""SciencePlots IEEE figures for corrected mechanical-test data."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import scienceplots  # noqa: F401  # registers the SciencePlots styles
from matplotlib.ticker import AutoMinorLocator, MaxNLocator

from .models import CorrectionResult

IEEE_DOUBLE_COLUMN = 7.16
GOLDEN_RATIO = 0.618


def configure_ieee_style(*, use_latex: bool = True) -> bool:
    """Apply SciencePlots IEEE styling and report whether LaTeX is active."""

    latex_available = shutil.which("latex") is not None
    final_latex = use_latex and latex_available
    if use_latex and not latex_available:
        warnings.warn(
            "LaTeX was not found. Exporting a draft IEEE-style figure with the "
            "SciencePlots no-latex fallback; install MiKTeX or TeX Live for final use.",
            RuntimeWarning,
            stacklevel=2,
        )
    styles = ["science", "ieee"] if final_latex else ["science", "ieee", "no-latex"]
    plt.style.use(styles)
    mpl.rcParams.update(
        {
            "text.usetex": final_latex,
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
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.unicode_minus": False,
            "text.latex.preamble": r"\usepackage{amsmath}\usepackage{amssymb}",
        }
    )
    return final_latex


def _polish(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(which="major", length=3.0)
    ax.tick_params(which="minor", length=1.5)


def _annotate_mode_property(ax: plt.Axes, result: CorrectionResult) -> None:
    properties = result.summary["mechanical_properties"]
    key = (
        "ultimate_tensile_strength"
        if result.config.mode == "tension"
        else "maximum_compressive_stress"
    )
    peak = properties[key]
    peak_value = peak["value"]
    if peak_value is None:
        return
    curve = result.corrected_curve
    index = int(np.argmax(curve["engineering_stress_MPa"].to_numpy()))
    x_value = 100.0 * float(curve["corrected_engineering_strain"].iloc[index])
    label = "UTS" if result.config.mode == "tension" else r"$\sigma_{\mathrm{c,max}}$"
    ax.plot(x_value, peak_value, marker="s", mfc="none", color="#D55E00")
    ax.annotate(
        f"{label} = {float(peak_value):.1f} MPa",
        xy=(x_value, float(peak_value)),
        xytext=(5, -12),
        textcoords="offset points",
    )


def plot_comparison(
    result: CorrectionResult,
    output_dir: str | Path,
    *,
    publication_style: bool = True,
) -> tuple[Path, Path, Path]:
    """Save an IEEE double-column comparison as PDF, PNG, and TIFF."""

    latex_active = configure_ieee_style(use_latex=True) if publication_style else False
    if not publication_style:
        plt.style.use("default")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = result.audit
    curve = result.corrected_curve
    config = result.config

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(IEEE_DOUBLE_COLUMN, IEEE_DOUBLE_COLUMN * GOLDEN_RATIO * 0.78),
    )
    ax1.plot(
        100.0 * audit["normalized_engineering_strain"],
        audit["normalized_engineering_stress_MPa"],
        color="#7A7A7A",
        linestyle="--",
        label="Raw normalized",
    )
    ax1.plot(
        100.0 * curve["corrected_engineering_strain"],
        curve["engineering_stress_MPa"],
        color="#0072B2",
        label=rf"Corrected, $E={config.target_modulus_mpa / 1000:g}$ GPa",
    )
    _annotate_mode_property(ax1, result)
    ax1.set_xlabel(r"Engineering strain, $\varepsilon_{\mathrm{eng}}$ (\%)")
    ax1.set_ylabel(r"Engineering stress, $\sigma_{\mathrm{eng}}$ (MPa)")
    ax1.set_xlim(left=0.0)
    ax1.set_ylim(bottom=0.0)
    ax1.legend(loc="best")
    _polish(ax1)

    proof_strain = result.summary["proof_strain"]
    low_limit = (
        max(0.006, 3.0 * config.offset_strain)
        if proof_strain is None
        else max(0.006, 1.6 * float(proof_strain))
    )
    low_limit = min(low_limit, float(curve["corrected_engineering_strain"].max()))
    low = curve["corrected_engineering_strain"] <= low_limit
    ax2.plot(
        100.0 * curve.loc[low, "corrected_engineering_strain"],
        curve.loc[low, "engineering_stress_MPa"],
        color="#0072B2",
        label="Corrected curve",
    )
    line_strain = np.linspace(0.0, low_limit, 300)
    ax2.plot(
        100.0 * line_strain,
        config.target_modulus_mpa * line_strain,
        color="#000000",
        linestyle=":",
        label="Target elastic line",
    )
    ax2.plot(
        100.0 * line_strain,
        config.target_modulus_mpa * (line_strain - config.offset_strain),
        color="#009E73",
        linestyle="--",
        label=rf"{100 * config.offset_strain:g}\% offset",
    )
    proof_stress = result.summary["proof_stress_MPa"]
    if proof_strain is not None and proof_stress is not None:
        ax2.plot(
            100.0 * float(proof_strain),
            float(proof_stress),
            marker="o",
            markerfacecolor="none",
            markeredgecolor="#009E73",
            linestyle="none",
            label=rf"$\sigma_{{0.2}}={float(proof_stress):.1f}$ MPa",
        )
    ax2.set_xlabel(r"Corrected strain, $\varepsilon_{\mathrm{eng,corr}}$ (\%)")
    ax2.set_ylabel(r"Engineering stress, $\sigma_{\mathrm{eng}}$ (MPa)")
    ax2.set_xlim(0.0, 100.0 * low_limit)
    ax2.set_ylim(bottom=0.0)
    ax2.legend(loc="best")
    _polish(ax2)
    if publication_style and not latex_active:
        fig.text(0.5, 0.01, "DRAFT — LaTeX unavailable", ha="center", color="0.4")

    fig.tight_layout(pad=0.3)
    png = out / "stress_strain_comparison.png"
    pdf = out / "stress_strain_comparison.pdf"
    tiff = out / "stress_strain_comparison.tiff"
    metadata = {"Creator": "Matplotlib + SciencePlots IEEE style"}
    fig.savefig(pdf, metadata=metadata)
    fig.savefig(png, dpi=600)
    try:
        fig.savefig(tiff, dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    except TypeError:
        warnings.warn(
            "TIFF LZW compression is unavailable; saving an uncompressed TIFF.",
            RuntimeWarning,
            stacklevel=2,
        )
        fig.savefig(tiff, dpi=600)
    plt.close(fig)
    return png, pdf, tiff
