from __future__ import annotations

import numpy as np
import pandas as pd

from mechtest_correction.high_rate import SHPBConfig, analyze_shpb, prepare_shpb_waves


def test_shpb_reduction_returns_response_and_equilibrium_metrics():
    time_us = np.linspace(0.0, 200.0, 401)
    pulse = np.sin(np.pi * time_us / time_us.max())
    source = pd.DataFrame(
        {
            "time": time_us,
            "incident": 1.0e-3 * pulse,
            "reflected": -2.5e-4 * pulse,
            "transmitted": 6.0e-4 * pulse,
        }
    )
    waves = prepare_shpb_waves(
        source,
        time_column="time",
        incident_column="incident",
        reflected_column="reflected",
        transmitted_column="transmitted",
    )
    outputs, summary = analyze_shpb(waves, SHPBConfig(static_proof_stress_mpa=400.0))
    assert {"waves", "response"} == set(outputs)
    assert outputs["response"]["specimen_engineering_strain"].iloc[-1] > 0.0
    assert outputs["response"]["transmitted_stress_MPa"].max() > 0.0
    assert summary["mean_strain_rate_s-1"] > 0.0
    assert summary["wave_speed_m_s"] > 0.0
