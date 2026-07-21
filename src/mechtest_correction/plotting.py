from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import AutoMinorLocator, MaxNLocator

from .models import CorrectionResult


def _polish(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(direction="in", top=True, right=True, which="both")


def plot_comparison(
    result: CorrectionResult,
    output_dir: str | Path,
    *,
    publication_style: bool = False,
) -> tuple[Path, Path]:
    """Save raw-versus-corrected and offset-construction panels."""

    if publication_style:
        try:
            import scienceplots  # noqa: F401

            plt.style.use(["science", "ieee"])
        except ImportError as exc:
            raise RuntimeError(
                "Install the 'publication' extra to use publication style"
            ) from exc
    else:
        plt.style.use("default")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = result.audit
    curve = result.corrected_curve
    config = result.config

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.0))
    ax1.plot(
        100.0 * audit["normalized_engineering_strain"],
        audit["normalized_engineering_stress_MPa"],
        color="#7A7A7A",
        linestyle="--",
        label="Raw normalized curve",
    )
    ax1.plot(
        100.0 * curve["corrected_engineering_strain"],
        curve["engineering_stress_MPa"],
        color="#0072B2",
        label=f"Corrected to E = {config.target_modulus_mpa / 1000:g} GPa",
    )
    ax1.set_xlabel("Engineering strain (%)")
    ax1.set_ylabel("Engineering stress (MPa)")
    ax1.set_xlim(left=0.0)
    ax1.set_ylim(bottom=0.0)
    ax1.legend(frameon=False)
    _polish(ax1)

    proof_strain = result.summary["proof_strain"]
    if proof_strain is None:
        low_limit = max(0.006, 3.0 * config.offset_strain)
    else:
        low_limit = max(0.006, 1.6 * float(proof_strain))
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
        label=f"{100 * config.offset_strain:g}% offset",
    )
    proof_stress = result.summary["proof_stress_MPa"]
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
    ax2.legend(frameon=False)
    _polish(ax2)

    fig.tight_layout()
    png = out / "stress_strain_comparison.png"
    pdf = out / "stress_strain_comparison.pdf"
    fig.savefig(png, dpi=400, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf
