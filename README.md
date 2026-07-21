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
- Corrected CSV, property/model/audit CSVs, JSON summary, and Matplotlib figures.
- Synthetic tests and GitHub Actions continuous integration.

## Installation

### Windows: one-command installer

Clone or download this repository, open PowerShell in the project folder, and
run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

This creates a local `.venv` environment and installs the GUI. Start the
application at any later time with:

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

The interactive workflow is arranged in four tabs:

1. **Import** previews up to 100 rows, identifies numeric columns, proposes a
   strain/stress or extension/load mapping, and lets you correct that mapping.
2. **Test setup** defines tension or compression, input units and signs, or the
   gauge length and initial area needed to convert load–extension data.
3. **Correct & review** embeds the raw and corrected curves. Drag horizontally
   over the raw graph to select the elastic fitting interval, then inspect the
   apparent and recovered moduli, fit R-squared, toe strain, and compliance.
4. **Corrected-data analysis** plots corrected engineering and true responses,
   identifies proof yield, and compares post-yield flow-law fits.
5. **Export** saves the complete audit outputs and an `analysis_settings.json`
   file. Settings can also be saved and reloaded independently.

The graph selection is an analysis aid: use a visibly linear, pre-yield region
after initial platen seating or grip take-up. The software still treats the
target modulus as an external assumption, not as a measured result.

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

SciencePlots is no longer used or required. Figures use standard Matplotlib so
the GUI and exports do not depend on a LaTeX installation or journal-specific
style package.

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
- `correction_audit.csv`: original rows, normalized data, removed compliance,
  toe correction, inclusion status, and monotonic adjustment.
- `summary.json`: assumptions, fitted values, proof stress, terminal values,
  work density, and warnings.
- `stress_strain_comparison.png`: high-resolution review figure.
- `stress_strain_comparison.pdf`: vector figure.
- `corrected_data_analysis.png`: engineering, true, and flow-model panels.
- `corrected_data_analysis.pdf`: vector version of the analysis panels.

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
