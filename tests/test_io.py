from __future__ import annotations

import pandas as pd
import pytest

from mechtest_correction.io import normalize_units, read_curve


def test_reads_text_with_non_numeric_header(tmp_path):
    path = tmp_path / "curve.txt"
    path.write_text(
        "Eng_strain Eng_stress\n,MPa\n0 0.5\n0.001 10\n0.002 20\n",
        encoding="utf-8",
    )
    frame = read_curve(path)
    assert frame.columns.tolist() == ["engineering_strain", "engineering_stress"]
    assert frame.shape == (3, 2)
    assert frame.iloc[-1].tolist() == pytest.approx([0.002, 20.0])


def test_reads_named_csv_columns(tmp_path):
    path = tmp_path / "curve.csv"
    pd.DataFrame(
        {"time": [0, 1, 2], "eps": [0.0, 0.01, 0.02], "sig": [0, 50, 80]}
    ).to_csv(path, index=False)
    frame = read_curve(path, strain_column="eps", stress_column="sig")
    assert frame["engineering_stress"].tolist() == [0, 50, 80]


def test_unit_normalization():
    frame = pd.DataFrame(
        {"engineering_strain": [0.0, 1.0], "engineering_stress": [0.0, 0.2]}
    )
    normalized = normalize_units(frame, strain_unit="percent", stress_unit="GPa")
    assert normalized.iloc[-1].tolist() == pytest.approx([0.01, 200.0])
