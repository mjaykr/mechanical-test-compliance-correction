"""Interactive desktop workflow for mechanical-test compliance correction."""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

from .cli import write_outputs
from .correction import correct_curve
from .io import numeric_column_names, read_data_table
from .models import CorrectionConfig, CorrectionResult
from .plotting import configure_ieee_style


def config_from_values(values: Mapping[str, str]) -> CorrectionConfig:
    """Build and validate a correction configuration from GUI text fields."""

    config = CorrectionConfig(
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
    config.validate()
    return config


def prepare_curve(table: pd.DataFrame, values: Mapping[str, str]) -> pd.DataFrame:
    """Map raw columns or derive engineering stress-strain from load-extension."""

    x_name = values["strain_column"]
    y_name = values["stress_column"]
    if not x_name or not y_name:
        raise ValueError("Choose both data columns on the Import tab")
    missing = [name for name in (x_name, y_name) if name not in table.columns]
    if missing:
        raise ValueError(f"Missing selected columns: {missing}")
    x = pd.to_numeric(table[x_name], errors="coerce")
    y = pd.to_numeric(table[y_name], errors="coerce")
    clean = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(clean) < 5:
        raise ValueError("The selected columns contain fewer than five numeric rows")

    if values["data_basis"] == "load-extension":
        gauge_length = float(values["gauge_length_mm"])
        area = float(values["area_mm2"])
        if gauge_length <= 0 or area <= 0:
            raise ValueError("Gauge length and initial area must be positive")
        extension_scale = {"mm": 1.0, "um": 0.001}[values["extension_unit"]]
        load_scale = {"N": 1.0, "kN": 1000.0}[values["load_unit"]]
        strain = clean["x"] * extension_scale / gauge_length
        stress = clean["y"] * load_scale / area
    else:
        strain = clean["x"]
        stress = clean["y"]
    return pd.DataFrame(
        {"engineering_strain": strain, "engineering_stress": stress}
    ).reset_index(drop=True)


class CorrectionApp:
    """Four-stage Tkinter workflow with preview and interactive fit selection."""

    SETTINGS_KEYS = (
        "data_basis",
        "strain_column",
        "stress_column",
        "mode",
        "target_modulus_gpa",
        "fit_axis",
        "fit_min",
        "fit_max",
        "offset_strain",
        "strain_unit",
        "stress_unit",
        "strain_sign",
        "stress_sign",
        "gauge_length_mm",
        "area_mm2",
        "extension_unit",
        "load_unit",
        "output_dir",
    )

    def __init__(self, root: Tk) -> None:
        configure_ieee_style(use_latex=False)
        self.root = root
        self.root.title("Mechanical Test Compliance Correction")
        self.root.geometry("1050x720")
        self.root.minsize(900, 620)
        self.table: pd.DataFrame | None = None
        self.curve: pd.DataFrame | None = None
        self.result: CorrectionResult | None = None
        self.values = self._initial_values()
        self.auto_preview = BooleanVar(value=True)
        self.status = StringVar(value="Import a test-data file to begin.")
        self.metric_text = StringVar(value="No correction preview available.")
        self._build()

    def _initial_values(self) -> dict[str, StringVar]:
        return {
            "input_file": StringVar(),
            "output_dir": StringVar(value=str(Path.cwd() / "results")),
            "data_basis": StringVar(value="stress-strain"),
            "strain_column": StringVar(),
            "stress_column": StringVar(),
            "mode": StringVar(value="compression"),
            "target_modulus_gpa": StringVar(value="310"),
            "fit_axis": StringVar(value="strain"),
            "fit_min": StringVar(value="0.0005"),
            "fit_max": StringVar(value="0.0025"),
            "offset_strain": StringVar(value="0.002"),
            "strain_unit": StringVar(value="fraction"),
            "stress_unit": StringVar(value="MPa"),
            "strain_sign": StringVar(value="auto"),
            "stress_sign": StringVar(value="auto"),
            "gauge_length_mm": StringVar(value="10"),
            "area_mm2": StringVar(value="10"),
            "extension_unit": StringVar(value="mm"),
            "load_unit": StringVar(value="N"),
        }

    def _build(self) -> None:
        shell = ttk.Frame(self.root, padding=10)
        shell.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True)
        self.import_tab = ttk.Frame(self.notebook, padding=10)
        self.setup_tab = ttk.Frame(self.notebook, padding=10)
        self.analyze_tab = ttk.Frame(self.notebook, padding=8)
        self.export_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.import_tab, text="1  Import")
        self.notebook.add(self.setup_tab, text="2  Test setup")
        self.notebook.add(self.analyze_tab, text="3  Correct & review")
        self.notebook.add(self.export_tab, text="4  Export")
        self._build_import_tab()
        self._build_setup_tab()
        self._build_analyze_tab()
        self._build_export_tab()
        ttk.Label(shell, textvariable=self.status).pack(fill="x", pady=(7, 0))

    def _build_import_tab(self) -> None:
        tab = self.import_tab
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(5, weight=1)
        ttk.Label(tab, text="Input data file").grid(row=0, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.values["input_file"]).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(tab, text="Browse and load…", command=self._choose_input).grid(
            row=0, column=2
        )
        self._combo(
            tab,
            1,
            "Input basis",
            "data_basis",
            ["stress-strain", "load-extension"],
            callback=self._basis_changed,
        )
        ttk.Label(tab, text="Strain / extension column").grid(
            row=2, column=0, sticky="w", pady=3
        )
        self.strain_combo = ttk.Combobox(
            tab, textvariable=self.values["strain_column"], state="readonly"
        )
        self.strain_combo.grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(tab, text="Stress / load column").grid(
            row=3, column=0, sticky="w", pady=3
        )
        self.stress_combo = ttk.Combobox(
            tab, textvariable=self.values["stress_column"], state="readonly"
        )
        self.stress_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(tab, text="Refresh mapping", command=self._mapping_changed).grid(
            row=4, column=2, sticky="e", pady=6
        )
        preview_frame = ttk.LabelFrame(tab, text="Data preview", padding=5)
        preview_frame.grid(row=5, columnspan=3, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview = ttk.Treeview(preview_frame, show="headings", height=16)
        scroll_y = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.preview.yview
        )
        scroll_x = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.preview.xview
        )
        self.preview.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _build_setup_tab(self) -> None:
        tab = self.setup_tab
        tab.columnconfigure(1, weight=1)
        self._combo(tab, 0, "Test mode", "mode", ["compression", "tension"])
        self._combo(tab, 1, "Strain unit", "strain_unit", ["fraction", "percent"])
        self._combo(tab, 2, "Stress unit", "stress_unit", ["MPa", "Pa", "kPa", "GPa"])
        self._combo(tab, 3, "Strain sign", "strain_sign", ["auto", "keep", "invert"])
        self._combo(tab, 4, "Stress sign", "stress_sign", ["auto", "keep", "invert"])
        ttk.Separator(tab).grid(row=5, columnspan=3, sticky="ew", pady=10)
        self._entry(tab, 6, "Gauge length (mm)", "gauge_length_mm")
        self._entry(tab, 7, "Initial area (mm²)", "area_mm2")
        self._combo(tab, 8, "Extension unit", "extension_unit", ["mm", "um"])
        self._combo(tab, 9, "Load unit", "load_unit", ["N", "kN"])
        ttk.Label(
            tab,
            text=(
                "Geometry is used only for load–extension input. Engineering strain "
                "is extension/gauge length and stress in MPa is load/area."
            ),
            wraplength=760,
        ).grid(row=10, columnspan=3, sticky="w", pady=12)

    def _build_analyze_tab(self) -> None:
        tab = self.analyze_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew")
        for index, (label, name) in enumerate(
            [
                ("Target E (GPa)", "target_modulus_gpa"),
                ("Fit min", "fit_min"),
                ("Fit max", "fit_max"),
                ("Offset", "offset_strain"),
            ]
        ):
            ttk.Label(controls, text=label).grid(row=0, column=2 * index, sticky="w")
            ttk.Entry(controls, textvariable=self.values[name], width=11).grid(
                row=0, column=2 * index + 1, padx=(3, 10)
            )
        ttk.Button(
            controls, text="Apply correction", command=self._preview_result
        ).grid(row=0, column=8, padx=4)
        ttk.Button(controls, text="Reset fit", command=self._reset_fit).grid(
            row=0, column=9, padx=4
        )
        ttk.Checkbutton(
            controls, text="Update after selection", variable=self.auto_preview
        ).grid(row=0, column=10, padx=4)
        ttk.Label(tab, textvariable=self.metric_text).grid(
            row=1, column=0, sticky="w", pady=(7, 3)
        )
        self.figure = Figure(figsize=(9, 5), dpi=100, constrained_layout=True)
        self.raw_ax = self.figure.add_subplot(121)
        self.corrected_ax = self.figure.add_subplot(122)
        self.canvas = FigureCanvasTkAgg(self.figure, master=tab)
        self.canvas.get_tk_widget().grid(row=2, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(tab)
        toolbar_frame.grid(row=3, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(
            self.canvas, toolbar_frame, pack_toolbar=False
        )
        self.toolbar.update()
        self.toolbar.pack(side="left")
        self.span = SpanSelector(
            self.raw_ax,
            self._fit_selected,
            "horizontal",
            useblit=True,
            props={"alpha": 0.25, "facecolor": "tab:blue"},
            interactive=True,
            drag_from_anywhere=True,
        )
        self._empty_plot()

    def _build_export_tab(self) -> None:
        tab = self.export_tab
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)
        ttk.Label(tab, text="Output folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.values["output_dir"]).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(tab, text="Browse…", command=self._choose_output).grid(
            row=0, column=2
        )
        actions = ttk.Frame(tab)
        actions.grid(row=1, columnspan=3, sticky="w", pady=10)
        ttk.Button(actions, text="Export results", command=self._export).pack(
            side="left"
        )
        ttk.Button(actions, text="Open outputs", command=self._open_outputs).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Save settings…", command=self._save_settings).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Load settings…", command=self._load_settings).pack(
            side="left", padx=6
        )
        ttk.Label(tab, text="Analysis summary").grid(
            row=2, columnspan=3, sticky="w", pady=(5, 2)
        )
        self.summary = ttk.Treeview(tab, columns=("value",), show="tree headings")
        self.summary.heading("#0", text="Property")
        self.summary.heading("value", text="Value")
        self.summary.column("#0", width=310)
        self.summary.column("value", width=420)
        self.summary.grid(row=3, columnspan=3, sticky="nsew")

    def _entry(self, parent: ttk.Frame, row: int, label: str, name: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=self.values[name]).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=3
        )

    def _combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        name: str,
        options: list[str],
        callback=None,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        widget = ttk.Combobox(
            parent, textvariable=self.values[name], values=options, state="readonly"
        )
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        if callback is not None:
            widget.bind("<<ComboboxSelected>>", callback)

    def _choose_input(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Test data", "*.csv *.tsv *.txt *.dat *.xlsx *.xls"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.values["input_file"].set(path)
            self._load_data()

    def _load_data(self) -> None:
        try:
            path = Path(self.values["input_file"].get()).expanduser()
            self.table = read_data_table(path)
            columns = numeric_column_names(self.table)
            if len(columns) < 2:
                raise ValueError("Fewer than two usable numeric columns were found")
            self.strain_combo.configure(values=columns)
            self.stress_combo.configure(values=columns)
            strain_guess = self._guess_column(columns, ("strain", "extension", "disp"))
            stress_guess = self._guess_column(columns, ("stress", "load", "force"))
            selected_strain = self.values["strain_column"].get()
            selected_stress = self.values["stress_column"].get()
            if selected_strain not in columns:
                self.values["strain_column"].set(strain_guess or columns[0])
            if selected_stress not in columns:
                self.values["stress_column"].set(stress_guess or columns[1])
            self._show_table(self.table)
            self._mapping_changed()
            self.status.set(
                f"Loaded {len(self.table):,} rows and {len(columns)} numeric columns."
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not load data", str(exc))

    @staticmethod
    def _guess_column(columns: list[str], terms: tuple[str, ...]) -> str | None:
        return next(
            (name for name in columns if any(term in name.lower() for term in terms)),
            None,
        )

    def _show_table(self, table: pd.DataFrame) -> None:
        self.preview.delete(*self.preview.get_children())
        columns = [str(column) for column in table.columns]
        self.preview.configure(columns=columns)
        for column in columns:
            self.preview.heading(column, text=column)
            self.preview.column(column, width=125, anchor="e")
        for _, row in table.head(100).iterrows():
            self.preview.insert("", "end", values=[str(value) for value in row])

    def _basis_changed(self, _event=None) -> None:
        basis = self.values["data_basis"].get()
        if basis == "load-extension":
            self.values["strain_unit"].set("fraction")
            self.values["stress_unit"].set("MPa")
        self._mapping_changed()

    def _mapping_changed(self) -> None:
        if self.table is None:
            return
        try:
            self.curve = prepare_curve(self.table, self._plain_values())
            self.result = None
            self._plot_raw()
        except ValueError as exc:
            self.status.set(str(exc))

    def _plain_values(self) -> dict[str, str]:
        return {name: variable.get() for name, variable in self.values.items()}

    def _plot_raw(self) -> None:
        if self.curve is None:
            return
        self.raw_ax.clear()
        strain = self.curve["engineering_strain"]
        if self.values["strain_unit"].get() == "fraction":
            x = 100.0 * strain
        else:
            x = strain
        self.raw_ax.plot(x, self.curve["engineering_stress"], color="0.35", lw=1.2)
        self.raw_ax.set_title("Raw curve — drag to select elastic region")
        self.raw_ax.set_xlabel("Engineering strain (%)")
        self.raw_ax.set_ylabel(f"Stress ({self.values['stress_unit'].get()})")
        self.raw_ax.grid(alpha=0.2)
        self.corrected_ax.clear()
        self.corrected_ax.set_title("Corrected preview")
        self.corrected_ax.set_xlabel("Corrected engineering strain (%)")
        self.corrected_ax.set_ylabel("Stress (MPa)")
        self.corrected_ax.grid(alpha=0.2)
        self.canvas.draw_idle()

    def _empty_plot(self) -> None:
        self.raw_ax.set_title("Raw curve")
        self.corrected_ax.set_title("Corrected preview")
        self.canvas.draw_idle()

    def _fit_selected(self, xmin: float, xmax: float) -> None:
        if xmax <= xmin:
            return
        self.values["fit_axis"].set("strain")
        self.values["fit_min"].set(f"{xmin / 100.0:.7g}")
        self.values["fit_max"].set(f"{xmax / 100.0:.7g}")
        self.status.set(
            f"Selected elastic interval: {xmin:.4g}% to {xmax:.4g}% strain."
        )
        if self.auto_preview.get():
            self._preview_result(show_errors=False)

    def _preview_result(self, *, show_errors: bool = True) -> None:
        try:
            if self.table is None:
                raise ValueError("Import data before applying a correction")
            self.curve = prepare_curve(self.table, self._plain_values())
            config = config_from_values(self._plain_values())
            self.result = correct_curve(self.curve, config)
            self._plot_result()
            self._show_summary()
        except (RuntimeError, ValueError) as exc:
            self.result = None
            self.status.set(f"Correction preview unavailable: {exc}")
            if show_errors:
                messagebox.showerror("Correction could not be previewed", str(exc))

    def _plot_result(self) -> None:
        if self.result is None:
            return
        result = self.result
        self._plot_raw()
        fit_min = 100.0 * result.config.fit_min
        fit_max = 100.0 * result.config.fit_max
        self.raw_ax.axvspan(fit_min, fit_max, alpha=0.18, color="tab:blue")
        audit = result.audit
        fit = (audit["normalized_engineering_strain"] >= result.config.fit_min) & (
            audit["normalized_engineering_strain"] <= result.config.fit_max
        )
        fit_x = 100.0 * audit.loc[fit, "normalized_engineering_strain"]
        fit_y = audit.loc[fit, "normalized_engineering_stress_MPa"]
        self.raw_ax.plot(fit_x, fit_y, "o", ms=3, color="tab:blue", label="Fit points")
        self.raw_ax.legend(frameon=False)
        curve = result.corrected_curve
        self.corrected_ax.clear()
        self.corrected_ax.plot(
            100.0 * audit["normalized_engineering_strain"],
            audit["normalized_engineering_stress_MPa"],
            "--",
            color="0.55",
            label="Raw",
        )
        self.corrected_ax.plot(
            100.0 * curve["corrected_engineering_strain"],
            curve["engineering_stress_MPa"],
            color="tab:blue",
            label="Corrected",
        )
        self.corrected_ax.set_title("Raw versus corrected")
        self.corrected_ax.set_xlabel("Engineering strain (%)")
        self.corrected_ax.set_ylabel("Engineering stress (MPa)")
        self.corrected_ax.set_xlim(left=0)
        self.corrected_ax.set_ylim(bottom=0)
        self.corrected_ax.grid(alpha=0.2)
        self.corrected_ax.legend(frameon=False)
        summary = result.summary
        recovered = summary["recovered_output_modulus_GPa"]
        recovered_text = "n/a" if recovered is None else f"{float(recovered):.2f} GPa"
        self.metric_text.set(
            f"Apparent E: {float(summary['apparent_modulus_GPa']):.2f} GPa   |   "
            f"Corrected E: {recovered_text}   |   "
            f"R²: {float(summary['fit_R_squared_strain_on_stress']):.6f}   |   "
            f"Toe: {100 * float(summary['toe_strain_removed']):.4g}%   |   "
            f"Compliance: {float(summary['system_compliance_strain_per_MPa']):.4g} /MPa"
        )
        self.status.set("Correction preview updated. Review the fit before exporting.")
        self.canvas.draw_idle()

    def _reset_fit(self) -> None:
        self.values["fit_min"].set("0.0005")
        self.values["fit_max"].set("0.0025")
        self.result = None
        self.metric_text.set(
            "Fit interval reset; apply correction to update the preview."
        )
        self._plot_raw()

    def _show_summary(self) -> None:
        self.summary.delete(*self.summary.get_children())
        if self.result is None:
            return
        for key, value in self.result.summary.items():
            if key == "mechanical_properties":
                parent = self.summary.insert(
                    "", "end", text=f"{self.result.config.mode.title()} analysis"
                )
                for item in value.values():
                    display = (
                        "not available"
                        if item["value"] is None
                        else f"{float(item['value']):.6g} {item['unit']}"
                    )
                    self.summary.insert(
                        parent, "end", text=str(item["label"]), values=(display,)
                    )
            if key == "caveats":
                for index, caveat in enumerate(value, start=1):
                    self.summary.insert(
                        "", "end", text=f"Caveat {index}", values=(caveat,)
                    )
            elif key != "mechanical_properties":
                self.summary.insert(
                    "", "end", text=key.replace("_", " "), values=(value,)
                )

    def _choose_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.values["output_dir"].set(path)

    def _export(self) -> None:
        if self.result is None:
            self._preview_result()
        if self.result is None:
            return
        input_file = Path(self.values["input_file"].get()).expanduser()
        output_dir = Path(self.values["output_dir"].get()).expanduser()
        try:
            write_outputs(self.result, output_dir, input_file=input_file)
            settings_path = output_dir / "analysis_settings.json"
            settings_path.write_text(
                json.dumps(self._settings_payload(), indent=2), encoding="utf-8"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Results could not be exported", str(exc))
            return
        self.status.set(f"Results exported to {output_dir}")
        messagebox.showinfo("Export completed", f"Results saved to:\n{output_dir}")

    def _settings_payload(self) -> dict[str, str]:
        payload = {name: self.values[name].get() for name in self.SETTINGS_KEYS}
        payload["input_file"] = self.values["input_file"].get()
        return payload

    def _save_settings(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Analysis settings", "*.json")],
        )
        if path:
            Path(path).write_text(
                json.dumps(self._settings_payload(), indent=2), encoding="utf-8"
            )
            self.status.set(f"Settings saved to {path}")

    def _load_settings(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Analysis settings", "*.json")])
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            for name, value in payload.items():
                if name in self.values:
                    self.values[name].set(str(value))
            if self.values["input_file"].get():
                self._load_data()
            self.status.set(f"Settings loaded from {path}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Settings could not be loaded", str(exc))

    def _open_outputs(self) -> None:
        path = Path(self.values["output_dir"].get()).expanduser()
        if not path.is_dir():
            messagebox.showwarning(
                "No output folder",
                "Export results first, or choose an existing output folder.",
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
