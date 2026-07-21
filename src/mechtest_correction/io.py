from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def read_data_table(path: str | Path, *, sheet_name: str | int = 0) -> pd.DataFrame:
    """Read an input file while preserving columns for GUI mapping and preview."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(source, sheet_name=sheet_name)
    elif suffix in {".csv", ".tsv", ".txt", ".dat"}:
        lines = [
            line.strip()
            for line in source.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not lines:
            raise ValueError(f"No data found in {source}")
        first_fields = [field for field in re.split(r"[\s,;]+", lines[0]) if field]
        header = (
            None if first_fields and all(_NUMBER.match(x) for x in first_fields) else 0
        )
        if suffix in {".csv", ".tsv"}:
            frame = pd.read_csv(
                source, sep=None, engine="python", header=header, on_bad_lines="skip"
            )
        else:
            frame = pd.read_csv(
                source,
                sep=r"[\s,;]+",
                engine="python",
                header=header,
                on_bad_lines="skip",
            )
        if header is None:
            frame.columns = [f"column_{index + 1}" for index in range(frame.shape[1])]
    else:
        raise ValueError(
            f"Unsupported input type {suffix!r}; use CSV, TSV, TXT, DAT, XLSX, or XLS"
        )
    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.empty or frame.shape[1] < 2:
        raise ValueError("The input must contain at least two columns")
    return frame


def numeric_column_names(frame: pd.DataFrame, *, minimum_values: int = 3) -> list[str]:
    """Return columns containing enough numeric values for test-data mapping."""

    return [
        str(column)
        for column in frame.columns
        if pd.to_numeric(frame[column], errors="coerce").notna().sum() >= minimum_values
    ]


def _first_two_numeric_columns(
    frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    usable = [column for column in numeric if numeric[column].notna().sum() >= 3]
    if len(usable) < 2:
        raise ValueError("Could not identify two numeric columns")
    clean = numeric[usable[:2]].dropna()
    return clean.iloc[:, 0], clean.iloc[:, 1]


def _read_text_numeric_pairs(path: Path) -> pd.DataFrame:
    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fields = [field for field in re.split(r"[\s,;]+", line.strip()) if field]
        if (
            len(fields) < 2
            or not _NUMBER.match(fields[0])
            or not _NUMBER.match(fields[1])
        ):
            continue
        rows.append((float(fields[0]), float(fields[1])))
    if len(rows) < 3:
        raise ValueError(f"No usable numeric stress-strain rows found in {path}")
    return pd.DataFrame(rows, columns=["engineering_strain", "engineering_stress"])


def read_curve(
    path: str | Path,
    *,
    strain_column: str | None = None,
    stress_column: str | None = None,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """Read a two-column engineering stress-strain curve.

    The returned frame always has ``engineering_strain`` and
    ``engineering_stress`` columns. Text files tolerate non-numeric header lines.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    suffix = source.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(source, sheet_name=sheet_name)
    elif suffix == ".csv":
        frame = pd.read_csv(source)
    elif suffix == ".tsv":
        frame = pd.read_csv(source, sep="\t")
    elif suffix in {".txt", ".dat"}:
        if strain_column is None and stress_column is None:
            return _read_text_numeric_pairs(source)
        frame = pd.read_csv(source, sep=None, engine="python")
    else:
        raise ValueError(
            f"Unsupported input type {suffix!r}; use CSV, TSV, TXT, DAT, XLSX, or XLS"
        )

    if (strain_column is None) != (stress_column is None):
        raise ValueError("strain_column and stress_column must be supplied together")

    if strain_column is not None and stress_column is not None:
        missing = [
            name for name in (strain_column, stress_column) if name not in frame.columns
        ]
        if missing:
            raise ValueError(f"Missing requested columns: {missing}")
        strain = pd.to_numeric(frame[strain_column], errors="coerce")
        stress = pd.to_numeric(frame[stress_column], errors="coerce")
        clean = pd.DataFrame(
            {"engineering_strain": strain, "engineering_stress": stress}
        ).dropna()
    else:
        strain, stress = _first_two_numeric_columns(frame)
        clean = pd.DataFrame(
            {
                "engineering_strain": strain.to_numpy(dtype=float),
                "engineering_stress": stress.to_numpy(dtype=float),
            }
        )

    if len(clean) < 3:
        raise ValueError("At least three numeric stress-strain rows are required")
    return clean.reset_index(drop=True)


def normalize_units(
    frame: pd.DataFrame, *, strain_unit: str, stress_unit: str
) -> pd.DataFrame:
    result = frame.copy()
    strain_scale = {"fraction": 1.0, "percent": 0.01}
    stress_scale = {"Pa": 1.0e-6, "kPa": 1.0e-3, "MPa": 1.0, "GPa": 1.0e3}
    if strain_unit not in strain_scale:
        raise ValueError(f"Unsupported strain unit: {strain_unit}")
    if stress_unit not in stress_scale:
        raise ValueError(f"Unsupported stress unit: {stress_unit}")
    result["engineering_strain"] = (
        result["engineering_strain"].to_numpy(dtype=float) * strain_scale[strain_unit]
    )
    result["engineering_stress_mpa"] = (
        result["engineering_stress"].to_numpy(dtype=float) * stress_scale[stress_unit]
    )
    return result[["engineering_strain", "engineering_stress_mpa"]]


def sign_factor(values: np.ndarray, policy: str) -> float:
    if policy == "keep":
        return 1.0
    if policy == "invert":
        return -1.0
    if policy != "auto":
        raise ValueError(f"Unsupported sign policy: {policy}")
    tail_count = max(3, len(values) // 10)
    return -1.0 if float(np.nanmedian(values[-tail_count:])) < 0.0 else 1.0
