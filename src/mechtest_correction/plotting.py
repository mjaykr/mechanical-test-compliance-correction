"""Matplotlib figures for corrected mechanical-test data."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import AutoMinorLocator, MaxNLocator

from .analysis import evaluate_flow_model, flow_fit_data_frame
from .models import CorrectionResult


def configure_plot_style() -> None:
    """Apply a dependency-free, readable Matplotlib style."""

    plt.style.use("default")
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.4,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "legend.frameon": False,
            "figure.dpi": 120,
            "savefig.dpi": 400,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _polish(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(which="major", length=3.5)
    ax.tick_params(which="minor", length=2.0)


def _yield_values(result: CorrectionResult) -> tuple[float | None, float | None]:
    return result.summary["proof_strain"], result.summary["proof_stress_MPa"]


def _percent_text(value: float) -> str:
    marker = r"\%" if mpl.rcParams["text.usetex"] else "%"
    return f"{value:g}{marker} offset"


def plot_comparison(
    result: CorrectionResult,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Save the raw/corrected and proof-offset comparison."""

    configure_plot_style()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = result.audit
    curve = result.corrected_curve
    config = result.config
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.0))
    ax1.plot(
        100.0 * audit["normalized_engineering_strain"],
        audit["normalized_engineering_stress_MPa"],
        color="#777777",
        linestyle="--",
        label="Raw normalized",
    )
    ax1.plot(
        100.0 * curve["corrected_engineering_strain"],
        curve["engineering_stress_MPa"],
        color="#0072B2",
        label=f"Corrected, E = {config.target_modulus_mpa / 1000:g} GPa",
    )
    ax1.set_xlabel("Engineering strain (%)")
    ax1.set_ylabel("Engineering stress (MPa)")
    ax1.set_xlim(left=0.0)
    ax1.set_ylim(bottom=0.0)
    ax1.legend(loc="best")
    _polish(ax1)

    proof_strain, proof_stress = _yield_values(result)
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
        color="#222222",
        linestyle=":",
        label="Target elastic line",
    )
    ax2.plot(
        100.0 * line_strain,
        config.target_modulus_mpa * (line_strain - config.offset_strain),
        color="#009E73",
        linestyle="--",
        label=_percent_text(100 * config.offset_strain),
    )
    if proof_strain is not None and proof_stress is not None:
        ax2.plot(
            100.0 * float(proof_strain),
            float(proof_stress),
            marker="o",
            markerfacecolor="white",
            markeredgecolor="#009E73",
            linestyle="none",
            label=f"Proof stress = {float(proof_stress):.1f} MPa",
        )
    ax2.set_xlabel("Corrected engineering strain (%)")
    ax2.set_ylabel("Engineering stress (MPa)")
    ax2.set_xlim(0.0, 100.0 * low_limit)
    ax2.set_ylim(bottom=0.0)
    ax2.legend(loc="best")
    _polish(ax2)
    fig.tight_layout()
    png = out / "stress_strain_comparison.png"
    pdf = out / "stress_strain_comparison.pdf"
    fig.savefig(png)
    fig.savefig(pdf, metadata={"Creator": "Mechanical Test Compliance Correction"})
    plt.close(fig)
    return png, pdf


def draw_macroscopic_response(
    axes: tuple[plt.Axes, plt.Axes], result: CorrectionResult
) -> None:
    """Draw corrected engineering and true macroscopic response panels."""

    engineering_ax, true_ax = axes
    for axis in axes:
        axis.clear()
    curve = result.corrected_curve
    config = result.config
    engineering_strain = curve["corrected_engineering_strain"].to_numpy(dtype=float)
    engineering_stress = curve["engineering_stress_MPa"].to_numpy(dtype=float)
    true_strain = curve["true_strain"].to_numpy(dtype=float)
    true_stress = curve["true_stress_MPa"].to_numpy(dtype=float)
    proof_strain, proof_stress = _yield_values(result)

    engineering_ax.plot(
        100.0 * engineering_strain,
        engineering_stress,
        color="#0072B2",
        label="Corrected engineering curve",
    )
    offset_line = config.target_modulus_mpa * (
        engineering_strain - config.offset_strain
    )
    engineering_ymax = 1.08 * float(np.max(engineering_stress))
    valid_offset = (offset_line >= 0.0) & (offset_line <= engineering_ymax)
    engineering_ax.plot(
        100.0 * engineering_strain[valid_offset],
        offset_line[valid_offset],
        "--",
        color="#009E73",
        label=_percent_text(100 * config.offset_strain),
    )
    if proof_strain is not None and proof_stress is not None:
        engineering_ax.plot(
            100.0 * float(proof_strain),
            float(proof_stress),
            "o",
            mfc="white",
            color="#D55E00",
            label=f"Proof = {float(proof_stress):.1f} MPa",
        )
    engineering_ax.set_title("Corrected engineering response")
    engineering_ax.set_xlabel("Engineering strain (%)")
    engineering_ax.set_ylabel("Engineering stress (MPa)")
    engineering_ax.set_xlim(left=0.0)
    engineering_ax.set_ylim(0.0, engineering_ymax)
    engineering_ax.legend(loc="best")
    _polish(engineering_ax)

    true_ax.plot(100.0 * true_strain, true_stress, color="#0072B2")
    peak_index = int(np.argmax(engineering_stress))
    point_label = "UTS" if config.mode == "tension" else "Maximum"
    true_ax.plot(
        100.0 * true_strain[peak_index],
        true_stress[peak_index],
        "s",
        mfc="white",
        color="#D55E00",
        label=f"{point_label} engineering-stress point",
    )
    true_ax.set_title("True response")
    true_ax.set_xlabel("True strain (%)")
    true_ax.set_ylabel("True stress (MPa)")
    true_ax.set_xlim(left=0.0)
    true_ax.set_ylim(bottom=0.0)
    true_ax.legend(loc="best")
    _polish(true_ax)


def draw_constitutive_assessment(flow_ax: plt.Axes, result: CorrectionResult) -> None:
    """Draw corrected flow stress with all constitutive-model predictions."""

    flow_ax.clear()
    curve = result.corrected_curve
    config = result.config
    fits = result.summary["flow_model_fits"]
    fit_data = flow_fit_data_frame(curve, fits, config.target_modulus_mpa)
    if fit_data.empty:
        flow_ax.text(
            0.5,
            0.5,
            str(fits.get("reason", "Flow-law fits are unavailable")),
            transform=flow_ax.transAxes,
            ha="center",
            va="center",
        )
    else:
        x = fit_data["true_plastic_strain"].to_numpy(dtype=float)
        flow_ax.plot(
            100.0 * x,
            fit_data["experimental_true_stress_MPa"],
            color="#222222",
            linewidth=2.0,
            label="Corrected data",
        )
        styles = {
            "Hollomon": ("#0072B2", "--"),
            "Ludwik": ("#D55E00", "-."),
            "Swift": ("#009E73", ":"),
            "Voce": ("#CC79A7", "--"),
            "Linear": ("#7A7A7A", ":"),
        }
        for name, model in fits["models"].items():
            if "parameters" not in model:
                continue
            prediction = evaluate_flow_model(name, x, model["parameters"])
            color, linestyle = styles[name]
            flow_ax.plot(
                100.0 * x,
                prediction,
                color=color,
                linestyle=linestyle,
                label=f"{name} (R²={float(model['R_squared']):.4f})",
            )
    flow_ax.set_title("Post-yield true flow stress models")
    flow_ax.set_xlabel("True plastic strain (%)")
    flow_ax.set_ylabel("True stress (MPa)")
    flow_ax.set_xlim(left=0.0)
    if not fit_data.empty:
        flow_ax.set_ylim(
            bottom=0.9 * float(fit_data["experimental_true_stress_MPa"].min())
        )
    flow_ax.legend(loc="best", ncol=2)
    _polish(flow_ax)


def draw_corrected_analysis(
    axes: tuple[plt.Axes, plt.Axes, plt.Axes], result: CorrectionResult
) -> None:
    """Draw engineering, true, and flow-law panels on existing axes."""

    draw_macroscopic_response((axes[0], axes[1]), result)
    draw_constitutive_assessment(axes[2], result)


def draw_work_hardening(
    axes: tuple[plt.Axes, plt.Axes], result: CorrectionResult
) -> None:
    """Draw Kocks-Mecking theta(sigma) and theta(epsilon_p) panels."""

    km_ax, evolution_ax = axes
    km_ax.clear()
    evolution_ax.clear()
    data = result.work_hardening
    summary = result.summary.get("work_hardening_analysis", {})
    if data is None or data.empty:
        reason = str(summary.get("reason", "Work-hardening analysis unavailable"))
        for axis in axes:
            axis.text(
                0.5, 0.5, reason, transform=axis.transAxes, ha="center", va="center"
            )
        return
    stage_styles = {
        "Stage II / early": ("#0072B2", "Stage II / early"),
        "Stage III / dynamic recovery": ("#D55E00", "Stage III / recovery"),
        "Stage IV / late": ("#009E73", "Stage IV / late"),
    }
    for stage, (color, label) in stage_styles.items():
        selected = data["stage"] == stage
        km_ax.plot(
            data.loc[selected, "true_stress_MPa"],
            data.loc[selected, "hardening_rate_theta_MPa"],
            color=color,
            label=label,
        )
        evolution_ax.plot(
            100.0 * data.loc[selected, "true_plastic_strain"],
            data.loc[selected, "hardening_rate_theta_MPa"],
            color=color,
            label=label,
        )
    stage_three = data["stage"] == "Stage III / dynamic recovery"
    if stage_three.any() and summary.get("stage_III_KM_slope") is not None:
        stress = data.loc[stage_three, "true_stress_MPa"].to_numpy(dtype=float)
        theta_fit = (
            float(summary["stage_III_KM_intercept_MPa"])
            + float(summary["stage_III_KM_slope"]) * stress
        )
        km_ax.plot(
            stress, theta_fit, "--", color="#222222", label="Stage III linear fit"
        )
    km_ax.axhline(0.0, color="0.5", linewidth=0.8)
    km_ax.set_title("Kocks-Mecking plot")
    km_ax.set_xlabel("True stress (MPa)")
    km_ax.set_ylabel(r"Hardening rate, $\theta$ (MPa)")
    km_ax.legend(loc="best")
    _polish(km_ax)
    evolution_ax.axhline(0.0, color="0.5", linewidth=0.8)
    evolution_ax.set_title("Hardening-rate evolution")
    evolution_ax.set_xlabel("True plastic strain (%)")
    evolution_ax.set_ylabel(r"Hardening rate, $\theta$ (MPa)")
    evolution_ax.legend(loc="best")
    _polish(evolution_ax)


def plot_corrected_analysis(
    result: CorrectionResult, output_dir: str | Path
) -> tuple[Path, Path]:
    """Save the dedicated corrected-data analysis figure."""

    configure_plot_style()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(10.0, 7.2))
    grid = fig.add_gridspec(2, 2)
    axes = (
        fig.add_subplot(grid[0, 0]),
        fig.add_subplot(grid[0, 1]),
        fig.add_subplot(grid[1, :]),
    )
    draw_corrected_analysis(axes, result)
    fig.tight_layout()
    png = out / "corrected_data_analysis.png"
    pdf = out / "corrected_data_analysis.pdf"
    fig.savefig(png)
    fig.savefig(pdf, metadata={"Creator": "Mechanical Test Compliance Correction"})
    plt.close(fig)
    return png, pdf


def plot_work_hardening(
    result: CorrectionResult, output_dir: str | Path
) -> tuple[Path, Path]:
    """Save Kocks-Mecking and hardening-rate evolution panels."""

    configure_plot_style()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.2))
    draw_work_hardening((axes[0], axes[1]), result)
    fig.tight_layout()
    png = out / "work_hardening_analysis.png"
    pdf = out / "work_hardening_analysis.pdf"
    fig.savefig(png)
    fig.savefig(pdf, metadata={"Creator": "Mechanical Test Compliance Correction"})
    plt.close(fig)
    return png, pdf
