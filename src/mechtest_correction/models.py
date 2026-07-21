from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

TestMode = Literal["tension", "compression"]
FitAxis = Literal["strain", "stress"]
StrainUnit = Literal["fraction", "percent"]
StressUnit = Literal["Pa", "kPa", "MPa", "GPa"]
SignPolicy = Literal["auto", "keep", "invert"]


@dataclass(frozen=True)
class CorrectionConfig:
    """Configuration for a modulus-targeted compliance correction.

    Fit limits use normalized units: fractional engineering strain when
    ``fit_axis='strain'`` and MPa when ``fit_axis='stress'``.
    """

    mode: TestMode
    target_modulus_mpa: float
    fit_axis: FitAxis
    fit_min: float
    fit_max: float
    strain_unit: StrainUnit = "fraction"
    stress_unit: StressUnit = "MPa"
    strain_sign: SignPolicy = "auto"
    stress_sign: SignPolicy = "auto"
    offset_strain: float = 0.002
    exclude_before_fit: bool = True
    monotonic: bool = True
    add_origin: bool = True
    strict_increment: float = 1.0e-10

    def validate(self) -> None:
        if self.mode not in {"tension", "compression"}:
            raise ValueError("mode must be 'tension' or 'compression'")
        if self.target_modulus_mpa <= 0:
            raise ValueError("target_modulus_mpa must be positive")
        if self.fit_axis not in {"strain", "stress"}:
            raise ValueError("fit_axis must be 'strain' or 'stress'")
        if self.fit_min >= self.fit_max:
            raise ValueError("fit_min must be less than fit_max")
        if self.offset_strain < 0:
            raise ValueError("offset_strain cannot be negative")
        if self.strict_increment <= 0:
            raise ValueError("strict_increment must be positive")


@dataclass
class CorrectionResult:
    """Correction outputs and their audit trail."""

    config: CorrectionConfig
    audit: pd.DataFrame
    corrected_curve: pd.DataFrame
    summary: dict[str, object]
    work_hardening: pd.DataFrame | None = None
    hall_petch: pd.DataFrame | None = None
    dislocation_density: pd.DataFrame | None = None
    micromechanical: pd.DataFrame | None = None
