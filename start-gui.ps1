<#
.SYNOPSIS
Starts the Mechanical Test Compliance Correction desktop application.
#>

$ErrorActionPreference = "Stop"
$guiExecutable = Join-Path $PSScriptRoot ".venv\Scripts\mechtest-gui.exe"

if (-not (Test-Path $guiExecutable)) {
    throw "The application is not installed yet. Run .\install.ps1 first."
}

& $guiExecutable
