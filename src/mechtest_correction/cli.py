from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import tomllib

from .analysis import flow_fit_data_frame, flow_models_frame, properties_frame
from .correction import correct_curve
from .io import read_curve
from .models import CorrectionConfig
from .plotting import plot_comparison, plot_corrected_analysis, plot_work_hardening


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mechtest-correct",
        description=(
            "Apply an auditable target-modulus compliance correction to a "
            "monotonic tensile or compression engineering stress-strain curve."
        ),
    )
    parser.add_argument("input", type=Path, help="CSV, TSV, TXT, DAT, XLSX, or XLS")
    parser.add_argument("--config", type=Path, help="TOML configuration file")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--mode", choices=["tension", "compression"])
    parser.add_argument("--target-modulus-gpa", type=float)
    parser.add_argument("--fit-axis", choices=["strain", "stress"])
    parser.add_argument("--fit-min", type=float)
    parser.add_argument("--fit-max", type=float)
    parser.add_argument("--offset-strain", type=float)
    parser.add_argument("--strain-column")
    parser.add_argument("--stress-column")
    parser.add_argument("--strain-unit", choices=["fraction", "percent"])
    parser.add_argument("--stress-unit", choices=["Pa", "kPa", "MPa", "GPa"])
    parser.add_argument("--strain-sign", choices=["auto", "keep", "invert"])
    parser.add_argument("--stress-sign", choices=["auto", "keep", "invert"])
    parser.add_argument(
        "--sheet", default=None, help="Excel sheet name or zero-based index"
    )
    parser.add_argument(
        "--exclude-before-fit",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--monotonic",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--add-origin",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    return parser


def _load_toml(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    flattened: dict[str, object] = {}
    for section in ("test", "correction", "output"):
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"TOML section [{section}] must be a table")
        flattened.update(values)
    return flattened


def _value(
    args: argparse.Namespace, config: dict[str, object], name: str, default=None
):
    command_value = getattr(args, name, None)
    if command_value is not None:
        return command_value
    return config.get(name, default)


def _sheet_value(value: object) -> str | int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text) if text.isdigit() else text


def _build_config(
    args: argparse.Namespace, toml: dict[str, object]
) -> CorrectionConfig:
    required = {
        "target_modulus_gpa": _value(args, toml, "target_modulus_gpa"),
        "fit_min": _value(args, toml, "fit_min"),
        "fit_max": _value(args, toml, "fit_max"),
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise ValueError("Missing required correction settings: " + ", ".join(missing))
    return CorrectionConfig(
        mode=str(_value(args, toml, "mode", "compression")),
        target_modulus_mpa=float(required["target_modulus_gpa"]) * 1000.0,
        fit_axis=str(_value(args, toml, "fit_axis", "strain")),
        fit_min=float(required["fit_min"]),
        fit_max=float(required["fit_max"]),
        strain_unit=str(_value(args, toml, "strain_unit", "fraction")),
        stress_unit=str(_value(args, toml, "stress_unit", "MPa")),
        strain_sign=str(_value(args, toml, "strain_sign", "auto")),
        stress_sign=str(_value(args, toml, "stress_sign", "auto")),
        offset_strain=float(_value(args, toml, "offset_strain", 0.002)),
        exclude_before_fit=bool(_value(args, toml, "exclude_before_fit", True)),
        monotonic=bool(_value(args, toml, "monotonic", True)),
        add_origin=bool(_value(args, toml, "add_origin", True)),
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    toml = _load_toml(args.config)
    config = _build_config(args, toml)
    strain_column = _value(args, toml, "strain_column")
    stress_column = _value(args, toml, "stress_column")
    sheet = _sheet_value(_value(args, toml, "sheet", 0))
    output_dir = Path(_value(args, toml, "output_dir", args.output_dir))

    frame = read_curve(
        args.input,
        strain_column=None if strain_column is None else str(strain_column),
        stress_column=None if stress_column is None else str(stress_column),
        sheet_name=sheet,
    )
    result = correct_curve(frame, config)
    return write_outputs(
        result,
        output_dir,
        input_file=args.input,
    )


def write_outputs(result, output_dir: Path, *, input_file: Path) -> dict[str, object]:
    """Write standard correction artifacts and return the run summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result.audit.to_csv(output_dir / "correction_audit.csv", index=False)
    result.corrected_curve.to_csv(output_dir / "corrected_curve.csv", index=False)
    properties_frame(result.summary["mechanical_properties"]).to_csv(
        output_dir / "mechanical_properties.csv", index=False
    )
    flow_fits = result.summary["flow_model_fits"]
    flow_models_frame(flow_fits).to_csv(output_dir / "flow_model_fits.csv", index=False)
    flow_fit_data_frame(
        result.corrected_curve, flow_fits, result.config.target_modulus_mpa
    ).to_csv(output_dir / "flow_fit_data.csv", index=False)
    if result.work_hardening is not None:
        result.work_hardening.to_csv(
            output_dir / "work_hardening_data.csv", index=False
        )
    pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in result.summary["work_hardening_analysis"].items()
            if not isinstance(value, (dict, list))
        ]
    ).to_csv(output_dir / "work_hardening_summary.csv", index=False)
    summary = dict(result.summary)
    summary["input_file"] = str(input_file.resolve())
    summary["correction_equation"] = (
        "epsilon_corrected = epsilon_raw - C_system * sigma - epsilon_toe"
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )
    plot_comparison(result, output_dir)
    plot_corrected_analysis(result, output_dir)
    plot_work_hardening(result, output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
