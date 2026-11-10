# Creates "Alfred" shortcuts so you never need a terminal:
#   - Desktop + Start menu: one click toggles Alfred on/off (no console window)
#   - Keyboard shortcut Ctrl+Alt+A toggles him too
#   - Optional: start Alfred automatically when you log in to Windows
# Run from the repo:   powershell -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1 [-Startup] [-NoStartup]
param([switch]$Startup, [switch]$NoStartup, [string]$Hotkey = "Ctrl+Alt+A")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pyw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { throw "No virtualenv at $repo\.venv - run scripts\setup_windows.ps1 first." }

$stateDir = Join-Path $env:USERPROFILE ".alfred"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$icon = Join-Path $stateDir "alfred.ico"
& (Join-Path $repo ".venv\Scripts\python.exe") -m alfred.icon $icon | Out-Null

$shell = New-Object -ComObject WScript.Shell
function New-AlfredShortcut($path, $arguments, $desc, $hotkey) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $pyw              # pythonw = no console window pops up
    $lnk.Arguments = $arguments
    $lnk.WorkingDirectory = $repo
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = $desc
    $lnk.WindowStyle = 7                # minimized
    if ($hotkey) { $lnk.Hotkey = $hotkey }
    $lnk.Save()
}

$desktop = [Environment]::GetFolderPath("Desktop")
$programs = [Environment]::GetFolderPath("Programs")
New-AlfredShortcut (Join-Path $desktop "Alfred.lnk") "-m alfred toggle" "Wake Alfred up / put him to sleep" $Hotkey
New-AlfredShortcut (Join-Path $programs "Alfred.lnk") "-m alfred toggle" "Wake Alfred up / put him to sleep" $null
Write-Host "[ok] 'Alfred' on your Desktop and in the Start menu - click to wake him up, click again to stop him"
Write-Host "[ok] keyboard shortcut: $Hotkey (toggles him on/off)"

$startupLnk = Join-Path ([Environment]::GetFolderPath("Startup")) "Alfred.lnk"
if (-not $Startup -and -not $NoStartup) {
    $answer = Read-Host "Start Alfred automatically when you log in to Windows? (y/N)"
    $Startup = $answer -match "^(y|yes)$"
}
if ($Startup) {
    New-AlfredShortcut $startupLnk "-m alfred wakeup" "Start Alfred at login" $null
    Write-Host "[ok] Alfred starts automatically at login (remove: delete Alfred in shell:startup, or re-run with -NoStartup)"
} elseif (Test-Path $startupLnk) {
    Remove-Item $startupLnk
    Write-Host "[ok] auto-start at login turned off"
}
