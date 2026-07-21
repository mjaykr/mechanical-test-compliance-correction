# Mechanical test compliance correction

An auditable Python workflow for reconstructing tensile and compression
stress-strain curves when crosshead or load-train compliance makes the measured
elastic slope much lower than an independently justified specimen modulus.

The package corrects the **strain axis only**. It does not rescale force or
stress to make a curve agree with a preferred strength.

## Correction model

Within a user-selected elastic fitting interval, measured engineering strain is
modelled as

```text
epsilon_raw = a * sigma + epsilon_toe
```

where `a` is measured strain per unit stress. Given an independently justified
target modulus `E_target`, the excess system compliance is

```text
C_system = a - 1 / E_target
```

and the reconstructed specimen strain is

```text
epsilon_corrected = epsilon_raw - C_system * sigma - epsilon_toe
```

This approach assumes that the excess displacement is linear with load. It is
not a substitute for a calibrated extensometer, DIC, clip gauge, or independent
load-frame compliance test.

## Features

- Tensile and compression modes.
- CSV, TSV, whitespace text, and Excel input.
- Positive- or negative-sign machine exports normalized automatically.
- Fit intervals defined using engineering strain or engineering stress.
- Complete audit table showing every correction component.
- Optional toe exclusion and minimum monotonic reconstruction.
- 0.2% offset proof stress or another user-defined offset.
- Mode-specific tensile and compression property analysis.
- Engineering-to-true conversion using mode-appropriate equations.
- Volumetric work integration.
- Stable registry for 28 independently exportable scientific plots.
- Two-phase Hall-Petch projection with explicit W and matrix contributions.
- Effective Taylor dislocation density and Kocks-Mecking density evolution.
- WHA Voigt-Reuss-Hill load-sharing bounds with separate phase properties.
- Advanced WHA homogenization and sensitivity views in one selectable panel.
- Dedicated compression Split-Hopkinson pressure bar (SHPB) pulse reduction.
- Multi-rate and multi-temperature constitutive fitting with five model families.
- Corrected CSV, property/model/audit CSVs, JSON summary, and Matplotlib figures.
- Synthetic tests and GitHub Actions continuous integration.

## Installation

### Windows: one-command installer

Clone or download this repository, open PowerShell in the project folder, and
run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

This creates a local `.venv` environment, installs the GUI, and creates a
**Mechanical Test Compliance Correction** shortcut with an application icon on
your Windows Desktop. Start the application at any later time using that shortcut
or with:

```powershell
.\start-gui.ps1
```

To install the development tools as well, use `-Dev`; use `-Launch` to open the
GUI as soon as installation finishes.

### Manual installation

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quick start

### Desktop GUI

After installation, start the desktop tool with:

```bash
mechtest-gui
```

Choose the raw data file and output folder, select tension or compression, and
enter a justified target modulus plus an elastic fitting interval. The GUI saves
the same audit CSV, corrected curve, JSON summary, and figures as the command-
line tool. It proposes column mappings automatically and lets you select a
different pair when the machine export contains additional channels.

The interactive workflow is arranged in thirteen tabs:

1. **Import** previews up to 100 rows, identifies numeric columns, proposes a
   strain/stress or extension/load mapping, and lets you correct that mapping.
2. **Test setup** defines tension or compression, input units and signs, or the
   gauge length and initial area needed to convert load–extension data.
3. **Correct & review** embeds the raw and corrected curves. Drag horizontally
   over the raw graph to select the elastic fitting interval, then inspect the
   apparent and recovered moduli, fit R-squared, toe strain, and compliance.
4. **Macroscopic response** plots corrected engineering and true responses,
   identifies proof yield, and tabulates tensile or compression properties.
5. **Constitutive assessment** compares post-yield flow-law fits and parameters.
6. **Rate-temperature models** imports a tidy multi-condition flow dataset and
   fits Johnson-Cook, BCC Zerilli-Armstrong, Khan-Huang-Liang, extended Voce,
   and strain-compensated modified Arrhenius models from one dropdown panel.
7. **Work hardening** plots Kocks–Mecking `theta(sigma)` and `theta(epsilon_p)`,
   with derivative smoothing and data-driven stage segmentation.
8. **Microstructure & Hall-Petch** projects separate W-grain and matrix-grain
   strengthening contributions from user-supplied microstructural parameters.
9. **Dislocation density** converts the post-yield curve to an effective Taylor
   density and fits a Kocks-Mecking storage-recovery evolution law.
10. **WHA two-phase model** compares the measured response with bilinear
   Voigt, Reuss, and Hill load-sharing estimates using separate BCC W and FCC
   matrix properties.
11. **Advanced WHA models** is one dropdown-driven panel for rule-of-mixtures
    bounds; iso-strain and iso-stress response; Mori-Tanaka/Eshelby elasticity;
    phase load partition; interface strength, W-W contiguity, and porosity
    sensitivities; separate BCC-W/FCC-matrix flow laws; and two-phase
    dislocation-density scenarios. Every selected view has its own data and
    IEEE export buttons.
12. **High strain rate / SHPB** imports a separate pulse file, reduces incident,
    reflected, and transmitted bar-strain histories using the 1-D SHPB equations,
    and plots pulse histories, dynamic compression response, strain rate, and
    force-equilibrium mismatch.
13. **Export** saves the complete audit outputs and an `analysis_settings.json`
   file. Settings can also be saved and reloaded independently.

The graph selection is an analysis aid: use a visibly linear, pre-yield region
after initial platen seating or grip take-up. The software still treats the
target modulus as an external assumption, not as a measured result.

## Multi-rate and temperature constitutive modelling

The advanced constitutive panel expects one tidy table with at least these four
numeric columns: `plastic_strain`, `flow_stress_MPa`, `strain_rate_s-1`, and
`temperature_K`. An optional `condition` column controls curve labels. At least
two distinct strain rates and two distinct temperatures are required for fitting.
The panel fits all five model families, reports parameters, R-squared, RMSE and
AIC, and identifies the lowest-AIC model. The dropdown switches the live plot
without refitting, while each selection has its own CSV and IEEE export.

These are global phenomenological correlations; predictions must be validated
against held-out conditions and should not be extrapolated beyond the calibrated
domain. The implemented forms follow published descriptions of
[Johnson-Cook](https://doi.org/10.1093/jom/ufad020),
[Khan-Huang-Liang](https://doi.org/10.3390/ma18092061), and
[strain-compensated Arrhenius modelling](https://doi.org/10.1007/s12598-015-0620-4).

## Corrected-data analysis

For **tensile tests**, the property table reports 0.1% and 0.2% proof stress,
ultimate tensile strength, engineering strain at UTS, terminal stress and
strain, modulus of resilience, and toughness to the end of the recorded curve.
The terminal strain is not labelled fracture strain unless the supplied record
is known to end at fracture. True tensile stress remains valid only before
necking unless instantaneous area is measured.

For **compression tests**, the property table reports 0.2% proof stress,
stress at 1%, 2%, 5%, 10%, and 20% corrected strain when those strains are
present, maximum and terminal compressive stress, strain at maximum stress, and
energy absorbed to the end of the record. These values do not correct for
barreling, friction, or specimen instability.

The exported `mechanical_properties.csv` provides a compact property table for
further statistical analysis.

## Yield-offset convention

The default is a **0.2% offset**, equivalent to `0.002` engineering strain. This
is the conventional proof-yield definition for metals without a distinct yield
point and is used in both tensile and ASTM E9 compression reporting. A **0.02%
offset** (`0.0002`) is available when explicitly required by a material
specification or reporting convention; it is not treated as interchangeable
with 0.2%.

Supporting sources include the
[NIST tensile-property report](https://doi.org/10.6028/NIST.TN.2165) and the
[NIST ASTM E9 compression reproducibility study](https://doi.org/10.6028/NIST.TN.1679).

## Post-yield flow-law fitting

The analysis tab fits **Hollomon, Ludwik, Swift, Voce, and linear hardening**
models to true stress versus true plastic strain. True plastic strain is
calculated as `true strain - true stress / E`. Fitting starts at the selected
offset proof point and ends at peak engineering stress by default. For tension,
this is the UTS and avoids treating the simple area conversion as valid after
necking. The terminal-point option is available for monotonic compression or a
record whose maximum occurs at its final point.

Every model reports its equation, fitted parameters, R-squared, and RMSE. No
model is automatically declared physically correct merely because it has the
largest R-squared. The model set follows commonly evaluated metallic flow laws;
see this [comparative model study](https://doi.org/10.1007/s00170-025-16068-8)
and this [experimental compression application](https://pmc.ncbi.nlm.nih.gov/articles/PMC10057155/).

## Work-hardening and Kocks–Mecking analysis

The instantaneous hardening rate is calculated as
`theta = d(true stress) / d(true plastic strain)` after uniform resampling and
Savitzky–Golay smoothing. The smoothing window is adjustable in the GUI. The
tool plots both `theta` versus true stress (the Kocks–Mecking representation)
and `theta` versus true plastic strain. A three-piece linear least-squares
segmentation labels early/Stage II, dynamic-recovery/Stage III, and late/Stage
IV regions. The Stage III `theta–sigma` line, its R-squared, and extrapolated
saturation stress are reported when defined.

These stage labels are data-driven curve descriptions, not standalone evidence
for a specific dislocation mechanism. Numerical derivatives are sensitive to
noise, smoothing, machine oscillation, adiabatic heating, friction, barreling,
and localization. The implementation follows the classic
[Mecking–Kocks formulation](https://doi.org/10.1016/0001-6160(81)90112-7) and
the experimental definition used in this
[Kocks–Mecking steel study](https://doi.org/10.1016/j.msea.2013.03.044).

## Microstructure and Hall-Petch projection

The microstructure panel evaluates the supplied relation

```text
sigma_y = sigma_base + f_W k_W / sqrt(d_W) + (1 - f_W) k_matrix / sqrt(d_matrix)
```

and displays the W and matrix contributions separately. Grain sizes are entered
in micrometres, phase fraction is volumetric, and both Hall-Petch coefficients
remain editable. The result is deliberately called a **projection**, not a fit:
one stress-strain curve cannot identify Hall-Petch intercepts or coefficients.
A regression requires multiple independently characterized specimens spanning
grain size while controlling composition, porosity, contiguity, and processing.

WHA strength and ductility depend on W content, interfaces, contiguity, and
manufacturing condition as well as grain size; see the experimental
[W-Ni-Fe structural study](https://doi.org/10.1016/S0921-5093(00)01369-1).
The starting values in the GUI are editable analysis assumptions, not certified
constants for a particular alloy batch.

## Dislocation-density model

The density panel applies the effective Taylor relation

```text
sigma = sigma_0 + M alpha mu b sqrt(rho)
```

to the corrected post-yield flow curve. It then fits the Kocks-Mecking evolution
law `d rho / d epsilon_p = k1 sqrt(rho) - k2 rho`, reporting storage, recovery,
saturation density, and stress-reconstruction error. The result is labelled
**effective apparent composite density** because a macroscopic WHA curve cannot
separate dislocations in BCC W from those in the FCC Ni-Fe-W matrix. Absolute
interpretation requires independently supported `M`, `alpha`, `mu`, `b`, and
`sigma_0`, preferably with XRD, EBSD, or TEM calibration. The model direction is
consistent with experimentally validated dislocation-mediated modelling of
[polycrystalline tungsten](https://doi.org/10.1016/j.jmps.2015.08.015).

## WHA two-phase micromechanics

The WHA panel treats tungsten grains and the matrix as separate bilinear phases.
It plots their assumed responses and compares measured engineering stress with
Voigt (iso-strain), Reuss (iso-stress), and Hill-average load-sharing estimates.
It also reports the corresponding elastic moduli and curve RMSE values.

These are transparent one-dimensional bounds, not interface-resolved crystal
plasticity. They are useful for sensitivity analysis and detecting inconsistent
phase assumptions. Physical calibration should use measured phase properties;
more advanced two-phase WHA formulations are described by
[Lu, Gao, and Ke](https://doi.org/10.1016/j.msea.2013.11.007) and recent
[W/matrix interface modelling](https://doi.org/10.1016/j.ijplas.2024.104156).

## Advanced WHA homogenization and sensitivities

The advanced panel keeps the requested WHA extensions together in one dropdown,
so its plot and exported CSV always describe one model view at a time. The
Mori-Tanaka response is a linear-elastic, isotropic, spherical-inclusion
estimate. The interface, W-W contiguity, porosity, and phase-density views are
explicit parameter sensitivities—not fitted phase-resolved measurements. This
keeps their assumptions inspectable and prevents a macroscopic curve from being
overinterpreted as a calibrated microstructural solution. The chosen structure
is consistent with published WHA analyses that identify matrix/interface,
contiguity, and porosity as key response variables
([WHA microstructure study](https://doi.org/10.1016/j.msea.2010.08.071);
[porosity study](https://doi.org/10.1179/pom.1979.22.4.175)).

## High strain rate / Split-Hopkinson pressure bar

The SHPB panel is a separate compression-pulse workflow. Provide a CSV, text, or
Excel file with time, incident, reflected, and transmitted **bar-strain** columns,
then set the bar and specimen dimensions. The program uses a one-dimensional
elastic-wave reduction: transmitted pulse for stress and reflected pulse for
strain rate and integrated strain. It normalizes a global gauge-polarity reversal,
but it does not perform dispersion or gauge-to-interface pulse-shift corrections.
Inspect force-equilibrium mismatch and pulse alignment before reporting response.
The assumptions follow modern SHPB guidance
([Yokoyama, 2025](https://doi.org/10.11395/aem.25-0008)).

## Plot-data and IEEE export

Every analysis panel now uses a stable plot registry. Select any individual
subplot and use **Plot data** or **Plot IEEE**, or export the complete panel with
**Panel data** or **Panel IEEE**. Live GUI plots use standard Matplotlib. IEEE
export alone loads SciencePlots' `science` and `ieee` styles, keeps LaTeX
enabled, and creates a vector PDF plus 600 dpi PNG and TIFF files. The exact
registered plot data are saved beside the figure as CSV. MiKTeX, TeX Live, or
MacTeX is required for final IEEE export; the application reports an error
rather than silently substituting a non-LaTeX final figure.

### Command line

Compression using a TOML configuration:

```bash
mechtest-correct data/compression.txt \
  --config examples/compression_90w7ni3fe.toml \
  --output-dir results/compression
```

Tension using command-line options:

```bash
mechtest-correct data/tensile.csv \
  --mode tension \
  --target-modulus-gpa 210 \
  --fit-axis stress \
  --fit-min 50 \
  --fit-max 250 \
  --strain-column strain \
  --stress-column stress_MPa \
  --output-dir results/tension
```

Run `mechtest-correct --help` for all options.

## Outputs

Each run creates:

- `corrected_curve.csv`: usable corrected engineering and true curve.
- `mechanical_properties.csv`: mode-specific corrected-data properties.
- `flow_model_fits.csv`: equations, parameters, R-squared, and RMSE.
- `flow_fit_data.csv`: experimental true flow curve and model predictions.
- `work_hardening_data.csv`: true stress, plastic strain, theta, and stage.
- `work_hardening_summary.csv`: smoothing, stage boundaries, and Stage III fit.
- `hall_petch_data.csv` and `hall_petch_summary.csv`: grain-size projection and
  strengthening decomposition when the GUI analysis has been calculated.
- `dislocation_density_data.csv` and `dislocation_density_summary.csv`:
  apparent density, Kocks-Mecking prediction, parameters, and caveats.
- `micromechanical_data.csv` and `micromechanical_summary.csv`: phase responses,
  load-sharing bounds, effective moduli, and RMSE.
- `advanced_wha_*_data.csv` and `advanced_wha_summary.csv`: all selectable
  advanced-WHA model data and the stated sensitivity assumptions.
- `shpb_waves_data.csv`, `shpb_response_data.csv`, and `shpb_summary.csv`:
  pulse histories, dynamic response, equilibrium diagnostic, and SHPB inputs.
- `advanced_constitutive_*_data.csv` and
  `advanced_constitutive_summary.csv`: observations, model predictions,
  residuals, fitted parameters, and comparison metrics.
- `correction_audit.csv`: original rows, normalized data, removed compliance,
  toe correction, inclusion status, and monotonic adjustment.
- `summary.json`: assumptions, fitted values, proof stress, terminal values,
  work density, and warnings.
- `stress_strain_comparison.png`: high-resolution review figure.
- `stress_strain_comparison.pdf`: vector figure.
- `corrected_data_analysis.png`: engineering, true, and flow-model panels.
- `corrected_data_analysis.pdf`: vector version of the analysis panels.
- `work_hardening_analysis.png`: Kocks–Mecking and theta-evolution panels.
- `work_hardening_analysis.pdf`: vector work-hardening figure.
- `microstructure_hall_petch.*`, `dislocation_density.*`, and
  `wha_two_phase.*`: normal GUI/batch review figures when those analyses exist.

## Sign and unit conventions

The internal representation uses positive magnitudes for engineering strain and
engineering stress in both tension and compression. `sign = "auto"` reverses a
column when the median of its final observations is negative. Strain can be
provided as a fraction or percent. Stress is currently expected in MPa.

True quantities are calculated as follows:

| Mode | True strain | True stress |
|---|---|---|
| Tension | `ln(1 + e)` | `sigma * (1 + e)` |
| Compression | `-ln(1 - e)` | `sigma * (1 - e)` |

The tensile conversion is valid only while deformation remains uniform, before
necking. The compression conversion assumes homogeneous, constant-volume
deformation and becomes uncertain when barreling, friction, damage, or
localization is important.

## Choosing a target modulus

Use a modulus supported by specimen-level measurement, an applicable standard,
or closely matched literature for composition, density, porosity, heat
treatment, and processing route. Manufacturing route alone does not uniquely
determine elastic modulus. The software records the target as an assumption and
does not claim to have measured it.

## Choosing the fitting interval

Use a visually linear, pre-yield interval after initial seating. The package
reports the inverse strain-on-stress regression slope because compliance is a
deformation-per-load quantity. Check the reported fit R-squared and inspect the
low-strain panel. A high R-squared does not prove that the selected interval is
truly elastic.

## Scientific cautions

- A target-modulus correction is a model-based reconstruction.
- Do not use it to alter stress values or force agreement with a desired yield
  strength.
- Report raw and corrected curves together.
- Preserve specimen geometry, load, displacement, extensometer channel, strain
  rate, temperature, and lubrication metadata whenever available.
- Use replicate specimens to quantify uncertainty.
- Do not apply true-stress conversion after tensile necking without measuring
  the instantaneous area.

## Development

```bash
pytest
ruff check .
```

Contributions are welcome. See `CONTRIBUTING.md`.

## Publish to GitHub

Create an empty GitHub repository, then run:

```bash
git add .
git commit -m "Initial release"
git remote add origin https://github.com/YOUR_USERNAME/mechanical-test-compliance-correction.git
git push -u origin main
```
