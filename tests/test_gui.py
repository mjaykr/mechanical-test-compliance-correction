import pandas as pd
import pytest

from mechtest_correction.gui import config_from_values, prepare_curve


def test_gui_values_create_valid_config():
    config = config_from_values(
        {
            "mode": "compression",
            "target_modulus_gpa": "310",
            "fit_axis": "strain",
            "fit_min": "0.0005",
            "fit_max": "0.0025",
            "offset_strain": "0.002",
            "strain_unit": "fraction",
            "stress_unit": "MPa",
            "strain_sign": "auto",
            "stress_sign": "auto",
        }
    )
    config.validate()
    assert config.target_modulus_mpa == 310_000.0


def test_gui_supports_point_zero_two_percent_offset():
    values = {
        "mode": "tension",
        "target_modulus_gpa": "200",
        "fit_axis": "strain",
        "fit_min": "0.0005",
        "fit_max": "0.0025",
        "yield_offset_percent": "0.02",
        "strain_unit": "fraction",
        "stress_unit": "MPa",
        "strain_sign": "auto",
        "stress_sign": "auto",
    }
    assert config_from_values(values).offset_strain == pytest.approx(0.0002)


def test_gui_derives_curve_from_load_extension():
    table = pd.DataFrame(
        {"extension": [0.0, 0.1, 0.2, 0.3, 0.4], "load": [0, 10, 20, 30, 40]}
    )
    curve = prepare_curve(
        table,
        {
            "strain_column": "extension",
            "stress_column": "load",
            "data_basis": "load-extension",
            "gauge_length_mm": "10",
            "area_mm2": "2",
            "extension_unit": "mm",
            "load_unit": "kN",
        },
    )
    assert curve.iloc[-1].tolist() == pytest.approx([0.04, 20_000.0])
