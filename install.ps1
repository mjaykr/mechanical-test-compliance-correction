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
$shortcutName = "Mechanical Test Compliance Correction.lnk"

function New-ApplicationIcon {
    param([Parameter(Mandatory)] [string]$Path)

    if (Test-Path $Path) {
        return
    }

    Add-Type -AssemblyName System.Drawing
    $folder = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $bitmap = [System.Drawing.Bitmap]::new(256, 256)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::FromArgb(18, 42, 66))
    $blue = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(0, 114, 178))
    $orange = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(230, 159, 0), 12)
    $white = [System.Drawing.Pen]::new([System.Drawing.Color]::WhiteSmoke, 8)
    $graphics.FillEllipse($blue, 26, 26, 204, 204)
    $points = [System.Drawing.Point[]]@(
        [System.Drawing.Point]::new(52, 165),
        [System.Drawing.Point]::new(92, 118),
        [System.Drawing.Point]::new(126, 142),
        [System.Drawing.Point]::new(196, 76)
    )
    $graphics.DrawLines($white, $points)
    $graphics.DrawLine($orange, 50, 204, 207, 204)
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create)
    try {
        $icon.Save($stream)
    }
    finally {
        $stream.Dispose()
        $icon.Dispose()
        $orange.Dispose()
        $white.Dispose()
        $blue.Dispose()
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Get-UserDesktopDirectory {
    # User Shell Folders preserves Desktop redirection such as OneDrive\Desktop.
    $desktop = $null
    try {
        $shellFolders = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" -Name Desktop -ErrorAction Stop
        $desktop = [Environment]::ExpandEnvironmentVariables([string]$shellFolders.Desktop)
    }
    catch {
        $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    }

    if ([string]::IsNullOrWhiteSpace($desktop)) {
        throw "Windows did not provide a Desktop folder for the current user."
    }

    New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    return (Resolve-Path -LiteralPath $desktop).Path
}

function New-ShortcutAtDesktop {
    param(
        [Parameter(Mandatory)] [string]$ProjectRoot,
        [Parameter(Mandatory)] [string]$DesktopDirectory
    )

    $shortcutPath = Join-Path $DesktopDirectory $shortcutName
    $iconPath = Join-Path $ProjectRoot "assets\mechtest.ico"
    New-ApplicationIcon -Path $iconPath
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $ProjectRoot 'start-gui.ps1')`""
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Description = "Launch Mechanical Test Compliance Correction"
    $shortcut.Save()
    if (-not (Test-Path -LiteralPath $shortcutPath)) {
        throw "The Desktop shortcut could not be created at: $shortcutPath"
    }
    return $shortcutPath
}

function New-DesktopShortcuts {
    param([Parameter(Mandatory)] [string]$ProjectRoot)

    $shortcutPaths = @(
        New-ShortcutAtDesktop -ProjectRoot $ProjectRoot -DesktopDirectory (Get-UserDesktopDirectory)
    )

    # An elevated installation may be run under a different account. In that
    # case a shared shortcut is visible on the signed-in user's desktop too.
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdministrator) {
        $commonDesktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonDesktopDirectory)
        if ($commonDesktop -and $commonDesktop -ne (Get-UserDesktopDirectory)) {
            $shortcutPaths += New-ShortcutAtDesktop -ProjectRoot $ProjectRoot -DesktopDirectory $commonDesktop
        }
    }

    return $shortcutPaths
}

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

$shortcutPaths = New-DesktopShortcuts -ProjectRoot $projectRoot

Write-Host ""
Write-Host "Installation completed."
Write-Host "To start the graphical interface later, run: .\start-gui.ps1"
foreach ($shortcutPath in $shortcutPaths) {
    Write-Host "Desktop shortcut created: $shortcutPath"
}

if ($Launch) {
    & (Join-Path $venvDirectory "Scripts\mechtest-gui.exe")
}
