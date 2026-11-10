# Makes `alfred` work from any terminal on Windows (PowerShell, cmd, Windows Terminal).
# Run once from the repo:   powershell -ExecutionPolicy Bypass -File scripts\install_command.ps1
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No virtualenv at $py - create it first (see README setup)." }

$bin = Join-Path $env:USERPROFILE ".alfred\bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null
$shim = Join-Path $bin "alfred.cmd"
Set-Content -Path $shim -Encoding ASCII -Value "@echo off`r`n`"$py`" -m alfred %*"
Write-Host "[ok] created $shim"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" | Where-Object { $_ -eq $bin })) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$bin", "User")
    Write-Host "[ok] added $bin to your PATH - open a NEW terminal for it to take effect"
}
Write-Host "`nTry:  alfred wakeup   |   alfred status   |   alfred sleep"
