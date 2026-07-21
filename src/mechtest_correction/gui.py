"""Desktop interface for compliance correction of stress-strain curves."""

from __future__ import annotations

import os
import sys
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, messagebox, ttk

from .cli import write_outputs
from .correction import correct_curve
from .io import read_curve
from .models import CorrectionConfig


def config_from_values(values: Mapping[str, str]) -> CorrectionConfig:
    """Build and validate a correction configuration from GUI text fields."""

    return CorrectionConfig(
        mode=values["mode"],  # type: ignore[arg-type]
        target_modulus_mpa=float(values["target_modulus_gpa"]) * 1000.0,
        fit_axis=values["fit_axis"],  # type: ignore[arg-type]
        fit_min=float(values["fit_min"]),
        fit_max=float(values["fit_max"]),
        strain_unit=values["strain_unit"],  # type: ignore[arg-type]
        stress_unit=values["stress_unit"],  # type: ignore[arg-type]
        strain_sign=values["strain_sign"],  # type: ignore[arg-type]
        stress_sign=values["stress_sign"],  # type: ignore[arg-type]
        offset_strain=float(values["offset_strain"]),
    )


class CorrectionApp:
    """Tkinter front end for a single correction run."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("Mechanical Test Compliance Correction")
        root.minsize(760, 500)
        self.values = {
            "input_file": StringVar(),
            "output_dir": StringVar(value=str(Path.cwd() / "results")),
            "mode": StringVar(value="compression"),
            "target_modulus_gpa": StringVar(value="310"),
            "fit_axis": StringVar(value="strain"),
            "fit_min": StringVar(value="0.0005"),
            "fit_max": StringVar(value="0.0025"),
            "offset_strain": StringVar(value="0.002"),
            "strain_column": StringVar(),
            "stress_column": StringVar(),
            "strain_unit": StringVar(value="fraction"),
            "stress_unit": StringVar(value="MPa"),
            "strain_sign": StringVar(value="auto"),
            "stress_sign": StringVar(value="auto"),
        }
        self.status = StringVar(value="Choose a test-data file to begin.")
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Input data").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.values["input_file"]).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(frame, text="Browse…", command=self._choose_input).grid(
            row=0, column=2
        )
        ttk.Label(frame, text="Output folder").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.values["output_dir"]).grid(
            row=1, column=1, sticky="ew", padx=6
        )
        ttk.Button(frame, text="Browse…", command=self._choose_output).grid(
            row=1, column=2
        )

        ttk.Separator(frame).grid(row=2, columnspan=3, sticky="ew", pady=10)
        self._combo(frame, 3, "Test mode", "mode", ["compression", "tension"])
        self._entry(frame, 4, "Target modulus (GPa)", "target_modulus_gpa")
        self._combo(frame, 5, "Fit interval axis", "fit_axis", ["strain", "stress"])
        self._entry(frame, 6, "Fit interval minimum", "fit_min")
        self._entry(frame, 7, "Fit interval maximum", "fit_max")
        self._entry(frame, 8, "Offset strain", "offset_strain")

        ttk.Separator(frame).grid(row=9, columnspan=3, sticky="ew", pady=10)
        self._entry(frame, 10, "Strain column (optional)", "strain_column")
        self._entry(frame, 11, "Stress column (optional)", "stress_column")
        self._combo(frame, 12, "Strain unit", "strain_unit", ["fraction", "percent"])
        self._combo(
            frame, 13, "Stress unit", "stress_unit", ["MPa", "Pa", "kPa", "GPa"]
        )
        self._combo(frame, 14, "Strain sign", "strain_sign", ["auto", "keep", "invert"])
        self._combo(frame, 15, "Stress sign", "stress_sign", ["auto", "keep", "invert"])

        buttons = ttk.Frame(frame)
        buttons.grid(row=16, columnspan=3, sticky="ew", pady=(14, 4))
        ttk.Button(buttons, text="Run correction", command=self._run).pack(side="left")
        ttk.Button(buttons, text="Open outputs", command=self._open_outputs).pack(
            side="left", padx=8
        )
        ttk.Label(frame, textvariable=self.status, wraplength=710).grid(
            row=17, columnspan=3, sticky="w", pady=(5, 0)
        )

    def _entry(self, parent: ttk.Frame, row: int, label: str, name: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=self.values[name]).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=2
        )

    def _combo(
        self, parent: ttk.Frame, row: int, label: str, name: str, options: list[str]
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(
            parent, textvariable=self.values[name], values=options, state="readonly"
        ).grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=2)

    def _choose_input(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Test data", "*.csv *.tsv *.txt *.dat *.xlsx *.xls"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.values["input_file"].set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.values["output_dir"].set(path)

    def _run(self) -> None:
        try:
            input_file = Path(self.values["input_file"].get()).expanduser()
            if not input_file.is_file():
                raise ValueError(
                    "Select an existing CSV, TXT, TSV, or Excel data file."
                )
            output_dir = Path(self.values["output_dir"].get()).expanduser()
            config = config_from_values(
                {key: item.get() for key, item in self.values.items()}
            )
            config.validate()
            frame = read_curve(
                input_file,
                strain_column=self.values["strain_column"].get() or None,
                stress_column=self.values["stress_column"].get() or None,
            )
            result = correct_curve(frame, config)
            summary = write_outputs(result, output_dir, input_file=input_file)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Correction could not be completed", str(exc))
            self.status.set(
                "Correction failed. Review the inputs and fitting interval."
            )
            return
        proof = summary["proof_stress_MPa"]
        proof_text = "not found" if proof is None else f"{float(proof):.1f} MPa"
        corrected_modulus = float(summary["corrected_modulus_GPa"])
        self.status.set(
            "Completed. "
            f"Corrected modulus: {corrected_modulus:.2f} GPa; "
            f"proof stress: {proof_text}"
        )
        messagebox.showinfo("Correction completed", f"Results saved to:\n{output_dir}")

    def _open_outputs(self) -> None:
        path = Path(self.values["output_dir"].get()).expanduser()
        if not path.is_dir():
            messagebox.showwarning(
                "No output folder",
                "Run a correction first, or choose an existing output folder.",
            )
            return
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.resolve().as_uri())


def main() -> int:
    root = Tk()
    CorrectionApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
