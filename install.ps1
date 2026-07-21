<#
.SYNOPSIS
Installs the Mechanical Test Compliance Correction desktop tool locally.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\install.ps1

.EXAMPLE
.\install.ps1 -Launch
#>

[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"

function Get-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @($pyLauncher.Source, "-3")
    }

    throw "Python 3.10 or later was not found. Install it from https://www.python.org/downloads/windows/ and run this script again."
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    $pythonCommand = Get-PythonCommand
    $pythonArguments = @($pythonCommand | Select-Object -Skip 1)
    & $pythonCommand[0] @pythonArguments -m venv $venvDirectory
}

Write-Host "Updating pip..."
& $venvPython -m pip install --upgrade pip

$installTarget = if ($Dev) { "${projectRoot}[dev]" } else { $projectRoot }
Write-Host "Installing Mechanical Test Compliance Correction..."
& $venvPython -m pip install --editable $installTarget

Write-Host ""
Write-Host "Installation completed."
Write-Host "To start the graphical interface later, run: .\start-gui.ps1"

if ($Launch) {
    & (Join-Path $venvDirectory "Scripts\mechtest-gui.exe")
}
