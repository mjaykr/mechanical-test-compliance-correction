from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_curve() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Return a curve with a known 200 GPa specimen modulus and system compliance."""

    stress = np.linspace(0.0, 1000.0, 1001)
    target_mpa = 200_000.0
    plastic_strain = np.maximum(stress - 400.0, 0.0) / 4000.0
    specimen_strain = stress / target_mpa + plastic_strain
    system_compliance = 8.0e-6
    toe = 3.0e-4
    measured_strain = specimen_strain + system_compliance * stress + toe
    frame = pd.DataFrame(
        {
            "engineering_strain": measured_strain,
            "engineering_stress": stress,
        }
    )
    return frame, specimen_strain, stress
