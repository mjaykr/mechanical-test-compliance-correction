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

from .analysis import fit_flow_models
from .cli import write_outputs
from .correction import correct_curve
from .high_rate import SHPBConfig, analyze_shpb, prepare_shpb_waves
from .io import numeric_column_names, read_data_table
from .models import CorrectionConfig, CorrectionResult
from .plot_registry import get_plot_spec, plot_data, plots_for_panel
from .plotting import (
    ADVANCED_WHA_VIEW_LABELS,
    configure_plot_style,
    draw_advanced_wha_view,
    draw_constitutive_assessment,
    draw_dislocation_panel,
    draw_hall_petch_panel,
    draw_macroscopic_response,
    draw_micromechanical_panel,
    draw_shpb_view,
    draw_work_hardening,
)
from .publication import export_ieee_panel, export_ieee_plot, panel_data
from .wha_models import (
    AdvancedWHAConfig,
    DislocationConfig,
    MicromechanicalConfig,
    MicrostructureConfig,
    analyze_advanced_wha,
    analyze_dislocation_density,
    analyze_hall_petch,
    analyze_micromechanics,
)
from .work_hardening import analyze_work_hardening


def config_from_values(values: Mapping[str, str]) -> CorrectionConfig:
    """Build and validate a correction configuration from GUI text fields."""

    if "yield_offset_percent" in values:
        offset_strain = float(values["yield_offset_percent"]) / 100.0
    else:
        offset_strain = float(values["offset_strain"])
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
        offset_strain=offset_strain,
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
    """Ten-stage workflow from import through WHA micromechanics."""

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
        "yield_offset_percent",
        "flow_fit_end",
        "smoothing_window",
        "w_volume_fraction",
        "w_grain_size_um",
        "matrix_grain_size_um",
        "hp_base_stress_mpa",
        "hp_w_k",
        "hp_matrix_k",
        "taylor_factor",
        "dislocation_alpha",
        "shear_modulus_gpa",
        "burgers_vector_nm",
        "friction_stress_mpa",
        "w_modulus_gpa",
        "matrix_modulus_gpa",
        "w_yield_mpa",
        "matrix_yield_mpa",
        "w_hardening_mpa",
        "matrix_hardening_mpa",
        "advanced_view",
        "w_poisson_ratio",
        "matrix_poisson_ratio",
        "ww_contiguity",
        "porosity_fraction",
        "interface_strength_mpa",
        "contiguity_coefficient_mpa",
        "porosity_strength_exponent",
        "w_density_multiplier",
        "matrix_density_multiplier",
        "shpb_file",
        "shpb_time_column",
        "shpb_incident_column",
        "shpb_reflected_column",
        "shpb_transmitted_column",
        "shpb_time_unit",
        "shpb_bar_modulus_gpa",
        "shpb_bar_density_kg_m3",
        "shpb_bar_diameter_mm",
        "shpb_specimen_diameter_mm",
        "shpb_specimen_length_mm",
        "shpb_static_proof_mpa",
        "shpb_reference_rate_s",
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
        configure_plot_style()
        self.root = root
        self.root.title("Mechanical Test Compliance Correction")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 720)
        self.table: pd.DataFrame | None = None
        self.curve: pd.DataFrame | None = None
        self.result: CorrectionResult | None = None
        self.shpb_table: pd.DataFrame | None = None
        self.values = self._initial_values()
        self.plot_selections: dict[str, StringVar] = {}
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
            "yield_offset_percent": StringVar(value="0.2"),
            "flow_fit_end": StringVar(value="peak"),
            "smoothing_window": StringVar(value="51"),
            "w_volume_fraction": StringVar(value="0.90"),
            "w_grain_size_um": StringVar(value="30"),
            "matrix_grain_size_um": StringVar(value="8"),
            "hp_base_stress_mpa": StringVar(value="300"),
            "hp_w_k": StringVar(value="810"),
            "hp_matrix_k": StringVar(value="350"),
            "taylor_factor": StringVar(value="2.75"),
            "dislocation_alpha": StringVar(value="0.30"),
            "shear_modulus_gpa": StringVar(value="161"),
            "burgers_vector_nm": StringVar(value="0.274"),
            "friction_stress_mpa": StringVar(value="300"),
            "w_modulus_gpa": StringVar(value="411"),
            "matrix_modulus_gpa": StringVar(value="200"),
            "w_yield_mpa": StringVar(value="750"),
            "matrix_yield_mpa": StringVar(value="350"),
            "w_hardening_mpa": StringVar(value="1500"),
            "matrix_hardening_mpa": StringVar(value="900"),
            "advanced_view": StringVar(value="Rule-of-mixtures bounds"),
            "w_poisson_ratio": StringVar(value="0.28"),
            "matrix_poisson_ratio": StringVar(value="0.31"),
            "ww_contiguity": StringVar(value="0.45"),
            "porosity_fraction": StringVar(value="0.00"),
            "interface_strength_mpa": StringVar(value="150"),
            "contiguity_coefficient_mpa": StringVar(value="100"),
            "porosity_strength_exponent": StringVar(value="1.5"),
            "w_density_multiplier": StringVar(value="1.30"),
            "matrix_density_multiplier": StringVar(value="0.50"),
            "shpb_file": StringVar(),
            "shpb_time_column": StringVar(value="time"),
            "shpb_incident_column": StringVar(value="incident"),
            "shpb_reflected_column": StringVar(value="reflected"),
            "shpb_transmitted_column": StringVar(value="transmitted"),
            "shpb_time_unit": StringVar(value="us"),
            "shpb_bar_modulus_gpa": StringVar(value="210"),
            "shpb_bar_density_kg_m3": StringVar(value="7850"),
            "shpb_bar_diameter_mm": StringVar(value="20"),
            "shpb_specimen_diameter_mm": StringVar(value="8"),
            "shpb_specimen_length_mm": StringVar(value="4"),
            "shpb_static_proof_mpa": StringVar(value="0"),
            "shpb_reference_rate_s": StringVar(value="0.001"),
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
        self.corrected_analysis_tab = ttk.Frame(self.notebook, padding=8)
        self.constitutive_tab = ttk.Frame(self.notebook, padding=8)
        self.work_hardening_tab = ttk.Frame(self.notebook, padding=8)
        self.microstructure_tab = ttk.Frame(self.notebook, padding=8)
        self.dislocation_tab = ttk.Frame(self.notebook, padding=8)
        self.micromechanical_tab = ttk.Frame(self.notebook, padding=8)
        self.advanced_wha_tab = ttk.Frame(self.notebook, padding=8)
        self.shpb_tab = ttk.Frame(self.notebook, padding=8)
        self.export_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.import_tab, text="1  Import")
        self.notebook.add(self.setup_tab, text="2  Test setup")
        self.notebook.add(self.analyze_tab, text="3  Correct & review")
        self.notebook.add(self.corrected_analysis_tab, text="4  Macroscopic response")
        self.notebook.add(self.constitutive_tab, text="5  Constitutive assessment")
        self.notebook.add(self.work_hardening_tab, text="6  Work hardening")
        self.notebook.add(
            self.microstructure_tab, text="7  Microstructure & Hall-Petch"
        )
        self.notebook.add(self.dislocation_tab, text="8  Dislocation density")
        self.notebook.add(self.micromechanical_tab, text="9  WHA two-phase model")
        self.notebook.add(self.advanced_wha_tab, text="10  Advanced WHA models")
        self.notebook.add(self.shpb_tab, text="11  High strain rate / SHPB")
        self.notebook.add(self.export_tab, text="12  Export")
        self._build_import_tab()
        self._build_setup_tab()
        self._build_analyze_tab()
        self._build_corrected_analysis_tab()
        self._build_constitutive_tab()
        self._build_work_hardening_tab()
        self._build_microstructure_tab()
        self._build_dislocation_tab()
        self._build_micromechanical_tab()
        self._build_advanced_wha_tab()
        self._build_shpb_tab()
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
            ]
        ):
            ttk.Label(controls, text=label).grid(row=0, column=2 * index, sticky="w")
            ttk.Entry(controls, textvariable=self.values[name], width=11).grid(
                row=0, column=2 * index + 1, padx=(3, 10)
            )
        ttk.Label(controls, text="Yield offset (%)").grid(row=0, column=6, sticky="w")
        offset_combo = ttk.Combobox(
            controls,
            textvariable=self.values["yield_offset_percent"],
            values=["0.2", "0.02"],
            state="readonly",
            width=8,
        )
        offset_combo.grid(row=0, column=7, padx=(3, 10))
        offset_combo.bind("<<ComboboxSelected>>", self._analysis_settings_changed)
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

    def _build_corrected_analysis_tab(self) -> None:
        tab = self.corrected_analysis_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(controls, text="Yield offset convention").pack(side="left")
        offset_combo = ttk.Combobox(
            controls,
            textvariable=self.values["yield_offset_percent"],
            values=["0.2", "0.02"],
            state="readonly",
            width=8,
        )
        offset_combo.pack(side="left", padx=(5, 14))
        offset_combo.bind("<<ComboboxSelected>>", self._analysis_settings_changed)
        self._panel_export_buttons(controls, "macroscopic", "macroscopic_response")
        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=1, column=0, sticky="nsew")
        plot_frame = ttk.Frame(content)
        table_frame = ttk.Frame(content)
        content.add(plot_frame, weight=3)
        content.add(table_frame, weight=2)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.macro_figure = Figure(figsize=(10, 5), dpi=100, constrained_layout=True)
        self.macro_axes = (
            self.macro_figure.add_subplot(121),
            self.macro_figure.add_subplot(122),
        )
        self.macro_canvas = FigureCanvasTkAgg(self.macro_figure, master=plot_frame)
        self.macro_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(
            self.macro_canvas, toolbar_frame, pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(side="left")
        self.macro_canvas.draw_idle()
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.macro_property_table = ttk.Treeview(
            table_frame, columns=("value", "unit"), show="tree headings", height=8
        )
        self.macro_property_table.heading("#0", text="Property")
        self.macro_property_table.heading("value", text="Value")
        self.macro_property_table.heading("unit", text="Unit")
        self.macro_property_table.column("#0", width=440)
        self.macro_property_table.column("value", width=150, anchor="e")
        self.macro_property_table.column("unit", width=100)
        self.macro_property_table.grid(row=0, column=0, sticky="nsew")

    def _build_constitutive_tab(self) -> None:
        tab = self.constitutive_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(controls, text="Fit end").pack(side="left")
        end_combo = ttk.Combobox(
            controls,
            textvariable=self.values["flow_fit_end"],
            values=["peak", "terminal"],
            state="readonly",
            width=10,
        )
        end_combo.pack(side="left", padx=(5, 14))
        end_combo.bind("<<ComboboxSelected>>", self._analysis_settings_changed)
        self._panel_export_buttons(controls, "constitutive", "constitutive_models")
        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=1, column=0, sticky="nsew")
        plot_frame = ttk.Frame(content)
        table_frame = ttk.Frame(content)
        content.add(plot_frame, weight=3)
        content.add(table_frame, weight=2)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.constitutive_figure = Figure(
            figsize=(10, 5), dpi=100, constrained_layout=True
        )
        self.constitutive_ax = self.constitutive_figure.add_subplot(111)
        self.constitutive_canvas = FigureCanvasTkAgg(
            self.constitutive_figure, master=plot_frame
        )
        self.constitutive_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(
            self.constitutive_canvas, toolbar_frame, pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(side="left")
        self.constitutive_canvas.draw_idle()
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("equation", "r_squared", "rmse", "parameters")
        self.model_table = ttk.Treeview(
            table_frame, columns=columns, show="tree headings", height=6
        )
        self.model_table.heading("#0", text="Model")
        self.model_table.heading("equation", text="Equation")
        self.model_table.heading("r_squared", text="R²")
        self.model_table.heading("rmse", text="RMSE (MPa)")
        self.model_table.heading("parameters", text="Parameters")
        self.model_table.column("#0", width=90)
        self.model_table.column("equation", width=275)
        self.model_table.column("r_squared", width=75, anchor="e")
        self.model_table.column("rmse", width=90, anchor="e")
        self.model_table.column("parameters", width=430)
        self.model_table.grid(row=0, column=0, sticky="nsew")

    def _build_work_hardening_tab(self) -> None:
        tab = self.work_hardening_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(controls, text="Savitzky-Golay window").pack(side="left")
        smoothing = ttk.Entry(
            controls, textvariable=self.values["smoothing_window"], width=7
        )
        smoothing.pack(side="left", padx=(5, 4))
        ttk.Button(
            controls, text="Recalculate", command=self._recalculate_work_hardening
        ).pack(side="left", padx=(0, 14))
        self._panel_export_buttons(controls, "work_hardening", "work_hardening")
        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=1, column=0, sticky="nsew")
        plot_frame = ttk.Frame(content)
        summary_frame = ttk.Frame(content)
        content.add(plot_frame, weight=4)
        content.add(summary_frame, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.hardening_figure = Figure(
            figsize=(10, 5), dpi=100, constrained_layout=True
        )
        self.hardening_axes = (
            self.hardening_figure.add_subplot(121),
            self.hardening_figure.add_subplot(122),
        )
        self.hardening_canvas = FigureCanvasTkAgg(
            self.hardening_figure, master=plot_frame
        )
        self.hardening_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(
            self.hardening_canvas, toolbar_frame, pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(side="left")
        self.hardening_canvas.draw_idle()
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.hardening_summary = ttk.Treeview(
            summary_frame, columns=("value",), show="tree headings", height=6
        )
        self.hardening_summary.heading("#0", text="Metric")
        self.hardening_summary.heading("value", text="Value")
        self.hardening_summary.column("#0", width=410)
        self.hardening_summary.column("value", width=480)
        self.hardening_summary.grid(row=0, column=0, sticky="nsew")

    def _build_dual_model_panel(
        self,
        tab: ttk.Frame,
        *,
        fields: tuple[tuple[str, str], ...],
        recalculate,
        panel: str,
        default_stem: str,
    ):
        """Build a compact parameter area, dual plot, and summary table."""

        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        top = ttk.Frame(tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        inputs = ttk.Frame(top)
        inputs.pack(side="left", fill="x", expand=True)
        for index, (label, name) in enumerate(fields):
            row, group = divmod(index, 4)
            column = 2 * group
            ttk.Label(inputs, text=label).grid(row=row, column=column, sticky="w")
            ttk.Entry(inputs, textvariable=self.values[name], width=9).grid(
                row=row, column=column + 1, padx=(3, 10), pady=2
            )
        actions = ttk.Frame(top)
        actions.pack(side="right")
        ttk.Button(actions, text="Recalculate", command=recalculate).pack(
            side="left", padx=4
        )
        self._panel_export_buttons(actions, panel, default_stem)

        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=1, column=0, sticky="nsew")
        plot_frame = ttk.Frame(content)
        summary_frame = ttk.Frame(content)
        content.add(plot_frame, weight=4)
        content.add(summary_frame, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        figure = Figure(figsize=(10, 5), dpi=100, constrained_layout=True)
        axes = (figure.add_subplot(121), figure.add_subplot(122))
        canvas = FigureCanvasTkAgg(figure, master=plot_frame)
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(canvas, toolbar_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="left")
        canvas.draw_idle()
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        summary = ttk.Treeview(
            summary_frame, columns=("value",), show="tree headings", height=6
        )
        summary.heading("#0", text="Metric")
        summary.heading("value", text="Value")
        summary.column("#0", width=390)
        summary.column("value", width=510)
        summary.grid(row=0, column=0, sticky="nsew")
        return figure, axes, canvas, summary

    def _build_microstructure_tab(self) -> None:
        (
            self.hp_figure,
            self.hp_axes,
            self.hp_canvas,
            self.hp_summary,
        ) = self._build_dual_model_panel(
            self.microstructure_tab,
            fields=(
                ("W volume fraction", "w_volume_fraction"),
                ("W grain (µm)", "w_grain_size_um"),
                ("Matrix grain (µm)", "matrix_grain_size_um"),
                ("Base stress (MPa)", "hp_base_stress_mpa"),
                ("W k (MPa√µm)", "hp_w_k"),
                ("Matrix k", "hp_matrix_k"),
            ),
            recalculate=self._recalculate_microstructure,
            panel="microstructure",
            default_stem="microstructure_hall_petch",
        )

    def _build_dislocation_tab(self) -> None:
        (
            self.dislocation_figure,
            self.dislocation_axes,
            self.dislocation_canvas,
            self.dislocation_summary,
        ) = self._build_dual_model_panel(
            self.dislocation_tab,
            fields=(
                ("Taylor factor M", "taylor_factor"),
                ("Interaction α", "dislocation_alpha"),
                ("Shear modulus (GPa)", "shear_modulus_gpa"),
                ("Burgers vector (nm)", "burgers_vector_nm"),
                ("Friction stress (MPa)", "friction_stress_mpa"),
            ),
            recalculate=self._recalculate_dislocation,
            panel="dislocation",
            default_stem="dislocation_density",
        )

    def _build_micromechanical_tab(self) -> None:
        (
            self.micromechanical_figure,
            self.micromechanical_axes,
            self.micromechanical_canvas,
            self.micromechanical_summary,
        ) = self._build_dual_model_panel(
            self.micromechanical_tab,
            fields=(
                ("W volume fraction", "w_volume_fraction"),
                ("W modulus (GPa)", "w_modulus_gpa"),
                ("Matrix modulus (GPa)", "matrix_modulus_gpa"),
                ("W yield (MPa)", "w_yield_mpa"),
                ("Matrix yield (MPa)", "matrix_yield_mpa"),
                ("W tangent (MPa)", "w_hardening_mpa"),
                ("Matrix tangent (MPa)", "matrix_hardening_mpa"),
            ),
            recalculate=self._recalculate_micromechanics,
            panel="micromechanical",
            default_stem="wha_two_phase",
        )

    def _build_advanced_wha_tab(self) -> None:
        """Build one dropdown-driven panel for advanced WHA sensitivities."""

        tab = self.advanced_wha_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(controls, text="View").grid(row=0, column=0, sticky="w")
        view = ttk.Combobox(
            controls,
            textvariable=self.values["advanced_view"],
            values=[spec.label for spec in plots_for_panel("advanced_wha")],
            state="readonly",
            width=32,
        )
        view.grid(row=0, column=1, sticky="w", padx=(4, 12))
        view.bind("<<ComboboxSelected>>", self._advanced_view_changed)
        for index, (label, name) in enumerate(
            (
                ("W ν", "w_poisson_ratio"),
                ("Matrix ν", "matrix_poisson_ratio"),
                ("W-W contiguity", "ww_contiguity"),
                ("Porosity", "porosity_fraction"),
                ("Interface (MPa)", "interface_strength_mpa"),
                ("Contiguity k (MPa)", "contiguity_coefficient_mpa"),
                ("Porosity exponent", "porosity_strength_exponent"),
                ("W rho multiplier", "w_density_multiplier"),
                ("Matrix rho multiplier", "matrix_density_multiplier"),
            )
        ):
            column = 2 * (index % 4) + 2
            row = 0 if index < 4 else 1
            ttk.Label(controls, text=label).grid(row=row, column=column, sticky="w")
            ttk.Entry(controls, textvariable=self.values[name], width=7).grid(
                row=row, column=column + 1, padx=(3, 7), pady=2
            )
        actions = ttk.Frame(controls)
        actions.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(
            actions, text="Recalculate", command=self._recalculate_advanced_wha
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Export selected data…",
            command=lambda: self._export_individual_data("advanced_wha"),
        ).pack(side="left", padx=5)
        ttk.Button(
            actions,
            text="Export selected IEEE…",
            command=lambda: self._export_individual_ieee("advanced_wha"),
        ).pack(side="left", padx=2)
        self.plot_selections["advanced_wha"] = self.values["advanced_view"]
        ttk.Label(
            tab,
            text=(
                "Mori-Tanaka is elastic. Interface, contiguity, porosity, and "
                "phase-density views are parameter sensitivities—not calibrated "
                "failure models."
            ),
            wraplength=1180,
        ).grid(row=1, column=0, sticky="w", pady=(0, 4))
        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=2, column=0, sticky="nsew")
        plot_frame = ttk.Frame(content)
        summary_frame = ttk.Frame(content)
        content.add(plot_frame, weight=4)
        content.add(summary_frame, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.advanced_wha_figure = Figure(
            figsize=(10, 5), dpi=100, constrained_layout=True
        )
        self.advanced_wha_ax = self.advanced_wha_figure.add_subplot(111)
        self.advanced_wha_canvas = FigureCanvasTkAgg(
            self.advanced_wha_figure, master=plot_frame
        )
        self.advanced_wha_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(
            self.advanced_wha_canvas, toolbar_frame, pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(side="left")
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.advanced_wha_summary = ttk.Treeview(
            summary_frame, columns=("value",), show="tree headings", height=6
        )
        self.advanced_wha_summary.heading("#0", text="Metric")
        self.advanced_wha_summary.heading("value", text="Value")
        self.advanced_wha_summary.column("#0", width=450)
        self.advanced_wha_summary.column("value", width=500)
        self.advanced_wha_summary.grid(row=0, column=0, sticky="nsew")

    def _build_shpb_tab(self) -> None:
        """Build the separate pulse-file workflow for compression SHPB data."""

        tab = self.shpb_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)
        source = ttk.LabelFrame(tab, text="SHPB pulse file", padding=6)
        source.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="File").grid(row=0, column=0, sticky="w")
        ttk.Entry(source, textvariable=self.values["shpb_file"]).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(source, text="Browse…", command=self._browse_shpb_file).grid(
            row=0, column=2
        )
        for column, (label, name) in enumerate(
            (
                ("Time", "shpb_time_column"),
                ("Incident", "shpb_incident_column"),
                ("Reflected", "shpb_reflected_column"),
                ("Transmitted", "shpb_transmitted_column"),
                ("Time unit", "shpb_time_unit"),
            )
        ):
            ttk.Label(source, text=label).grid(row=1, column=2 * column, sticky="w")
            if name == "shpb_time_unit":
                ttk.Combobox(
                    source,
                    textvariable=self.values[name],
                    values=("s", "ms", "us"),
                    state="readonly",
                    width=7,
                ).grid(row=1, column=2 * column + 1, padx=(3, 7), pady=3)
            else:
                ttk.Entry(source, textvariable=self.values[name], width=13).grid(
                    row=1, column=2 * column + 1, padx=(3, 7), pady=3
                )
        parameters = ttk.LabelFrame(tab, text="Bar and specimen inputs", padding=6)
        parameters.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        for index, (label, name) in enumerate(
            (
                ("Bar E (GPa)", "shpb_bar_modulus_gpa"),
                ("Bar density (kg/m³)", "shpb_bar_density_kg_m3"),
                ("Bar diameter (mm)", "shpb_bar_diameter_mm"),
                ("Specimen diameter (mm)", "shpb_specimen_diameter_mm"),
                ("Specimen length (mm)", "shpb_specimen_length_mm"),
                ("Static 0.2% proof (MPa; optional)", "shpb_static_proof_mpa"),
                ("Reference rate (s⁻¹)", "shpb_reference_rate_s"),
            )
        ):
            ttk.Label(parameters, text=label).grid(
                row=index // 4, column=2 * (index % 4), sticky="w"
            )
            ttk.Entry(parameters, textvariable=self.values[name], width=12).grid(
                row=index // 4, column=2 * (index % 4) + 1, padx=(3, 10), pady=2
            )
        actions = ttk.Frame(tab)
        actions.grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Button(
            actions, text="Load and reduce SHPB", command=self._recalculate_shpb
        ).pack(side="left")
        self.plot_selections["shpb"] = StringVar(value=plots_for_panel("shpb")[0].label)
        picker = ttk.Combobox(
            actions,
            textvariable=self.plot_selections["shpb"],
            values=[item.label for item in plots_for_panel("shpb")],
            state="readonly",
            width=28,
        )
        picker.pack(side="left", padx=(10, 4))
        picker.bind("<<ComboboxSelected>>", self._shpb_view_changed)
        ttk.Button(
            actions,
            text="Export selected data…",
            command=lambda: self._export_individual_data("shpb"),
        ).pack(side="left", padx=3)
        ttk.Button(
            actions,
            text="Export selected IEEE…",
            command=lambda: self._export_individual_ieee("shpb"),
        ).pack(side="left", padx=3)
        content = ttk.PanedWindow(tab, orient="vertical")
        content.grid(row=3, column=0, sticky="nsew")
        plot_frame, summary_frame = ttk.Frame(content), ttk.Frame(content)
        content.add(plot_frame, weight=4)
        content.add(summary_frame, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.shpb_figure = Figure(figsize=(10, 5), dpi=100, constrained_layout=True)
        self.shpb_ax = self.shpb_figure.add_subplot(111)
        self.shpb_canvas = FigureCanvasTkAgg(self.shpb_figure, master=plot_frame)
        self.shpb_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(
            self.shpb_canvas, ttk.Frame(plot_frame), pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(side="left")
        self.shpb_summary = ttk.Treeview(
            summary_frame, columns=("value",), show="tree headings", height=6
        )
        self.shpb_summary.heading("#0", text="SHPB metric")
        self.shpb_summary.heading("value", text="Value")
        self.shpb_summary.column("#0", width=450)
        self.shpb_summary.column("value", width=500)
        self.shpb_summary.pack(fill="both", expand=True)

    def _panel_export_buttons(
        self, parent: ttk.Frame, panel: str, default_stem: str
    ) -> None:
        specs = plots_for_panel(panel)
        selection = StringVar(value=specs[0].label)
        self.plot_selections[panel] = selection
        ttk.Combobox(
            parent,
            textvariable=selection,
            values=[spec.label for spec in specs],
            state="readonly",
            width=25,
        ).pack(side="right", padx=(8, 2))
        ttk.Button(
            parent,
            text="Plot data…",
            command=lambda: self._export_individual_data(panel),
        ).pack(side="right", padx=2)
        ttk.Button(
            parent,
            text="Plot IEEE…",
            command=lambda: self._export_individual_ieee(panel),
        ).pack(side="right", padx=2)
        ttk.Button(
            parent,
            text="Panel data…",
            command=lambda: self._export_panel_data(panel, default_stem),
        ).pack(side="right", padx=4)
        ttk.Button(
            parent,
            text="Panel IEEE…",
            command=lambda: self._export_ieee(panel, default_stem),
        ).pack(side="right", padx=4)

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

    def _microstructure_config(self) -> MicrostructureConfig:
        return MicrostructureConfig(
            tungsten_grain_size_um=float(self.values["w_grain_size_um"].get()),
            matrix_grain_size_um=float(self.values["matrix_grain_size_um"].get()),
            tungsten_volume_fraction=float(self.values["w_volume_fraction"].get()),
            base_stress_mpa=float(self.values["hp_base_stress_mpa"].get()),
            tungsten_k_mpa_sqrt_um=float(self.values["hp_w_k"].get()),
            matrix_k_mpa_sqrt_um=float(self.values["hp_matrix_k"].get()),
        )

    def _dislocation_config(self) -> DislocationConfig:
        return DislocationConfig(
            taylor_factor=float(self.values["taylor_factor"].get()),
            alpha=float(self.values["dislocation_alpha"].get()),
            shear_modulus_gpa=float(self.values["shear_modulus_gpa"].get()),
            burgers_vector_nm=float(self.values["burgers_vector_nm"].get()),
            friction_stress_mpa=float(self.values["friction_stress_mpa"].get()),
        )

    def _micromechanical_config(self) -> MicromechanicalConfig:
        return MicromechanicalConfig(
            tungsten_volume_fraction=float(self.values["w_volume_fraction"].get()),
            tungsten_modulus_gpa=float(self.values["w_modulus_gpa"].get()),
            matrix_modulus_gpa=float(self.values["matrix_modulus_gpa"].get()),
            tungsten_yield_mpa=float(self.values["w_yield_mpa"].get()),
            matrix_yield_mpa=float(self.values["matrix_yield_mpa"].get()),
            tungsten_hardening_mpa=float(self.values["w_hardening_mpa"].get()),
            matrix_hardening_mpa=float(self.values["matrix_hardening_mpa"].get()),
        )

    def _advanced_wha_config(self) -> AdvancedWHAConfig:
        return AdvancedWHAConfig(
            tungsten_poisson_ratio=float(self.values["w_poisson_ratio"].get()),
            matrix_poisson_ratio=float(self.values["matrix_poisson_ratio"].get()),
            ww_contiguity=float(self.values["ww_contiguity"].get()),
            porosity_fraction=float(self.values["porosity_fraction"].get()),
            interface_strength_mpa=float(self.values["interface_strength_mpa"].get()),
            contiguity_coefficient_mpa=float(
                self.values["contiguity_coefficient_mpa"].get()
            ),
            porosity_strength_exponent=float(
                self.values["porosity_strength_exponent"].get()
            ),
            tungsten_density_multiplier=float(
                self.values["w_density_multiplier"].get()
            ),
            matrix_density_multiplier=float(
                self.values["matrix_density_multiplier"].get()
            ),
        )

    def _shpb_config(self) -> SHPBConfig:
        return SHPBConfig(
            bar_modulus_gpa=float(self.values["shpb_bar_modulus_gpa"].get()),
            bar_density_kg_m3=float(self.values["shpb_bar_density_kg_m3"].get()),
            bar_diameter_mm=float(self.values["shpb_bar_diameter_mm"].get()),
            specimen_diameter_mm=float(self.values["shpb_specimen_diameter_mm"].get()),
            specimen_length_mm=float(self.values["shpb_specimen_length_mm"].get()),
            static_proof_stress_mpa=float(self.values["shpb_static_proof_mpa"].get()),
            reference_strain_rate_s=float(self.values["shpb_reference_rate_s"].get()),
        )

    def _calculate_wha_models(self) -> None:
        if self.result is None:
            return
        self.result.hall_petch, hp_summary = analyze_hall_petch(
            self.result, self._microstructure_config()
        )
        self.result.dislocation_density, density_summary = analyze_dislocation_density(
            self.result, self._dislocation_config()
        )
        self.result.micromechanical, micro_summary = analyze_micromechanics(
            self.result, self._micromechanical_config()
        )
        self.result.advanced_wha, advanced_summary = analyze_advanced_wha(
            self.result, self._micromechanical_config(), self._advanced_wha_config()
        )
        self.result.summary["hall_petch_analysis"] = hp_summary
        self.result.summary["dislocation_density_analysis"] = density_summary
        self.result.summary["micromechanical_analysis"] = micro_summary
        self.result.summary["advanced_wha_analysis"] = advanced_summary

    def _preview_result(self, *, show_errors: bool = True) -> None:
        try:
            if self.table is None:
                raise ValueError("Import data before applying a correction")
            self.curve = prepare_curve(self.table, self._plain_values())
            config = config_from_values(self._plain_values())
            self.result = correct_curve(self.curve, config)
            self.result.summary["flow_model_fits"] = fit_flow_models(
                self.result.corrected_curve,
                modulus_mpa=config.target_modulus_mpa,
                yield_offset=config.offset_strain,
                end_criterion=self.values["flow_fit_end"].get(),
            )
            self.result.work_hardening, work_summary = analyze_work_hardening(
                self.result.corrected_curve,
                self.result.summary["flow_model_fits"],
                modulus_mpa=config.target_modulus_mpa,
                smoothing_window=int(self.values["smoothing_window"].get()),
            )
            self.result.summary["work_hardening_analysis"] = work_summary
            self._calculate_wha_models()
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
        self._update_analysis_panels()

    def _analysis_settings_changed(self, _event=None) -> None:
        if self.table is not None:
            self._preview_result(show_errors=False)

    def _update_analysis_panels(self) -> None:
        if self.result is None:
            return
        draw_macroscopic_response(self.macro_axes, self.result)
        self.macro_canvas.draw_idle()
        draw_constitutive_assessment(self.constitutive_ax, self.result)
        self.constitutive_canvas.draw_idle()
        draw_work_hardening(self.hardening_axes, self.result)
        self.hardening_canvas.draw_idle()
        draw_hall_petch_panel(self.hp_axes, self.result)
        self.hp_canvas.draw_idle()
        draw_dislocation_panel(self.dislocation_axes, self.result)
        self.dislocation_canvas.draw_idle()
        draw_micromechanical_panel(self.micromechanical_axes, self.result)
        self.micromechanical_canvas.draw_idle()
        self._draw_advanced_wha()
        self._show_macroscopic_properties()
        self._show_model_table()
        self._show_hardening_summary()
        self._show_science_summaries()

    def _show_macroscopic_properties(self) -> None:
        self.macro_property_table.delete(*self.macro_property_table.get_children())
        if self.result is None:
            return
        for item in self.result.summary["mechanical_properties"].values():
            value = (
                "not available"
                if item["value"] is None
                else f"{float(item['value']):.7g}"
            )
            self.macro_property_table.insert(
                "",
                "end",
                text=str(item["label"]),
                values=(value, item["unit"]),
            )

    def _show_model_table(self) -> None:
        self.model_table.delete(*self.model_table.get_children())
        if self.result is None:
            return
        fits = self.result.summary["flow_model_fits"]
        for name, model in fits.get("models", {}).items():
            if "parameters" in model:
                parameters = ", ".join(
                    f"{key}={float(value):.5g}"
                    for key, value in model["parameters"].items()
                )
                r_squared = f"{float(model['R_squared']):.6f}"
                rmse = f"{float(model['RMSE_MPa']):.4g}"
            else:
                parameters = str(model.get("error", "Fit unavailable"))
                r_squared = "—"
                rmse = "—"
            self.model_table.insert(
                "",
                "end",
                text=name,
                values=(model["equation"], r_squared, rmse, parameters),
            )

    def _show_hardening_summary(self) -> None:
        self.hardening_summary.delete(*self.hardening_summary.get_children())
        if self.result is None:
            return
        for key, value in self.result.summary["work_hardening_analysis"].items():
            self.hardening_summary.insert(
                "", "end", text=key.replace("_", " "), values=(value,)
            )

    @staticmethod
    def _fill_summary_table(table: ttk.Treeview, summary: dict[str, object]) -> None:
        table.delete(*table.get_children())
        for key, value in summary.items():
            if isinstance(value, dict):
                parent = table.insert(
                    "", "end", text=key.replace("_", " "), values=("",)
                )
                for input_key, input_value in value.items():
                    table.insert(
                        parent,
                        "end",
                        text=input_key.replace("_", " "),
                        values=(input_value,),
                    )
            else:
                table.insert("", "end", text=key.replace("_", " "), values=(value,))

    def _show_science_summaries(self) -> None:
        if self.result is None:
            return
        self._fill_summary_table(
            self.hp_summary, self.result.summary.get("hall_petch_analysis", {})
        )
        self._fill_summary_table(
            self.dislocation_summary,
            self.result.summary.get("dislocation_density_analysis", {}),
        )
        self._fill_summary_table(
            self.micromechanical_summary,
            self.result.summary.get("micromechanical_analysis", {}),
        )
        self._fill_summary_table(
            self.advanced_wha_summary,
            self.result.summary.get("advanced_wha_analysis", {}),
        )

    def _recalculate_work_hardening(self) -> None:
        if self.result is None:
            messagebox.showwarning(
                "No corrected data", "Apply the compliance correction first."
            )
            return
        try:
            self.result.work_hardening, summary = analyze_work_hardening(
                self.result.corrected_curve,
                self.result.summary["flow_model_fits"],
                modulus_mpa=self.result.config.target_modulus_mpa,
                smoothing_window=int(self.values["smoothing_window"].get()),
            )
        except ValueError as exc:
            messagebox.showerror("Work-hardening analysis failed", str(exc))
            return
        self.result.summary["work_hardening_analysis"] = summary
        draw_work_hardening(self.hardening_axes, self.result)
        self.hardening_canvas.draw_idle()
        self._show_hardening_summary()

    def _require_result(self) -> bool:
        if self.result is not None:
            return True
        messagebox.showwarning(
            "No corrected data", "Apply the compliance correction first."
        )
        return False

    def _recalculate_microstructure(self) -> None:
        if not self._require_result():
            return
        try:
            assert self.result is not None
            self.result.hall_petch, summary = analyze_hall_petch(
                self.result, self._microstructure_config()
            )
        except ValueError as exc:
            messagebox.showerror("Hall-Petch analysis failed", str(exc))
            return
        self.result.summary["hall_petch_analysis"] = summary
        draw_hall_petch_panel(self.hp_axes, self.result)
        self.hp_canvas.draw_idle()
        self._fill_summary_table(self.hp_summary, summary)

    def _recalculate_dislocation(self) -> None:
        if not self._require_result():
            return
        try:
            assert self.result is not None
            self.result.dislocation_density, summary = analyze_dislocation_density(
                self.result, self._dislocation_config()
            )
        except ValueError as exc:
            messagebox.showerror("Dislocation analysis failed", str(exc))
            return
        self.result.summary["dislocation_density_analysis"] = summary
        draw_dislocation_panel(self.dislocation_axes, self.result)
        self.dislocation_canvas.draw_idle()
        self._fill_summary_table(self.dislocation_summary, summary)

    def _recalculate_micromechanics(self) -> None:
        if not self._require_result():
            return
        try:
            assert self.result is not None
            self.result.micromechanical, summary = analyze_micromechanics(
                self.result, self._micromechanical_config()
            )
        except ValueError as exc:
            messagebox.showerror("Micromechanical analysis failed", str(exc))
            return
        self.result.summary["micromechanical_analysis"] = summary
        draw_micromechanical_panel(self.micromechanical_axes, self.result)
        self.micromechanical_canvas.draw_idle()
        self._fill_summary_table(self.micromechanical_summary, summary)

    def _draw_advanced_wha(self) -> None:
        if self.result is None:
            return
        view = self._selected_plot_id("advanced_wha").split(".", 1)[1]
        draw_advanced_wha_view(self.advanced_wha_ax, self.result, view=view)
        self.advanced_wha_canvas.draw_idle()

    def _advanced_view_changed(self, _event=None) -> None:
        if self.result is not None:
            self._draw_advanced_wha()
            view = self._selected_plot_id("advanced_wha").split(".", 1)[1]
            self.status.set(f"Advanced WHA view: {ADVANCED_WHA_VIEW_LABELS[view]}")

    def _recalculate_advanced_wha(self) -> None:
        if not self._require_result():
            return
        try:
            assert self.result is not None
            self.result.advanced_wha, summary = analyze_advanced_wha(
                self.result,
                self._micromechanical_config(),
                self._advanced_wha_config(),
            )
        except ValueError as exc:
            messagebox.showerror("Advanced WHA analysis failed", str(exc))
            return
        self.result.summary["advanced_wha_analysis"] = summary
        self._draw_advanced_wha()
        self._fill_summary_table(self.advanced_wha_summary, summary)
        self.status.set("Advanced WHA sensitivity views recalculated.")

    def _browse_shpb_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose SHPB pulse file",
            filetypes=[
                ("Data files", "*.csv *.tsv *.txt *.dat *.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.values["shpb_file"].set(path)

    def _draw_shpb(self) -> None:
        if self.result is None:
            return
        view = self._selected_plot_id("shpb").split(".", 1)[1]
        draw_shpb_view(self.shpb_ax, self.result, view=view)
        self.shpb_canvas.draw_idle()

    def _shpb_view_changed(self, _event=None) -> None:
        if self.result is not None and self.result.high_rate:
            self._draw_shpb()

    def _recalculate_shpb(self) -> None:
        path = self.values["shpb_file"].get().strip()
        if not path:
            messagebox.showwarning(
                "No SHPB file",
                "Choose a pulse file containing time, incident, reflected, and "
                "transmitted histories.",
            )
            return
        try:
            self.shpb_table = read_data_table(path)
            waves = prepare_shpb_waves(
                self.shpb_table,
                time_column=self.values["shpb_time_column"].get(),
                incident_column=self.values["shpb_incident_column"].get(),
                reflected_column=self.values["shpb_reflected_column"].get(),
                transmitted_column=self.values["shpb_transmitted_column"].get(),
                time_unit=self.values["shpb_time_unit"].get(),
            )
            high_rate, summary = analyze_shpb(waves, self._shpb_config())
        except (OSError, ValueError) as exc:
            messagebox.showerror("SHPB analysis failed", str(exc))
            return
        if self.result is None:
            self.result = CorrectionResult(
                config=CorrectionConfig(
                    "compression", 310_000.0, "strain", 0.0005, 0.0025
                ),
                audit=pd.DataFrame(),
                corrected_curve=pd.DataFrame(),
                summary={},
            )
        self.result.high_rate = high_rate
        self.result.summary["shpb_analysis"] = summary
        self._draw_shpb()
        self._fill_summary_table(self.shpb_summary, summary)
        self.status.set(
            "SHPB waves reduced. Check force equilibrium before interpreting "
            "the response."
        )

    def _selected_plot_id(self, panel: str) -> str:
        selected = self.plot_selections[panel].get()
        return next(
            spec.plot_id for spec in plots_for_panel(panel) if spec.label == selected
        )

    def _export_individual_data(self, panel: str) -> None:
        if not self._require_result():
            return
        assert self.result is not None
        plot_id = self._selected_plot_id(panel)
        spec = get_plot_spec(plot_id)
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"{spec.default_stem}_data.csv",
            filetypes=[("CSV data", "*.csv")],
        )
        if not path:
            return
        data = plot_data(self.result, plot_id)
        if data.empty:
            messagebox.showerror(
                "No plot data", f"No data are available for {spec.label}."
            )
            return
        data.to_csv(path, index=False)
        self.status.set(f"Individual plot data exported to {path}")

    def _export_individual_ieee(self, panel: str) -> None:
        if not self._require_result():
            return
        assert self.result is not None
        plot_id = self._selected_plot_id(panel)
        spec = get_plot_spec(plot_id)
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"{spec.default_stem}.pdf",
            filetypes=[("PDF base name", "*.pdf")],
        )
        if not path:
            return
        try:
            outputs = export_ieee_plot(
                self.result, plot_id, Path(path).with_suffix(""), use_latex=True
            )
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("IEEE export failed", str(exc))
            return
        self.status.set(f"Individual IEEE plot and CSV exported beside {outputs[0]}")

    def _export_panel_data(self, panel: str, default_stem: str) -> None:
        if self.result is None:
            messagebox.showwarning(
                "No corrected data", "Apply the compliance correction first."
            )
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"{default_stem}_data.csv",
            filetypes=[("CSV data", "*.csv")],
        )
        if not path:
            return
        data = panel_data(self.result, panel)
        if data.empty:
            messagebox.showerror("No plot data", "This analysis panel has no data.")
            return
        data.to_csv(path, index=False)
        self.status.set(f"Plot data exported to {path}")

    def _export_ieee(self, panel: str, default_stem: str) -> None:
        if self.result is None:
            messagebox.showwarning(
                "No corrected data", "Apply the compliance correction first."
            )
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"{default_stem}_ieee.pdf",
            filetypes=[("PDF base name", "*.pdf")],
        )
        if not path:
            return
        stem = Path(path).with_suffix("")
        try:
            outputs = export_ieee_panel(self.result, panel, stem, use_latex=True)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("IEEE export failed", str(exc))
            return
        self.status.set(f"IEEE PDF, PNG, TIFF, and CSV exported beside {outputs[0]}")

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
            elif key not in {
                "mechanical_properties",
                "flow_model_fits",
                "work_hardening_analysis",
                "hall_petch_analysis",
                "dislocation_density_analysis",
                "micromechanical_analysis",
            }:
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
