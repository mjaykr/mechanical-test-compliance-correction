from mechtest_correction.gui import config_from_values


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
