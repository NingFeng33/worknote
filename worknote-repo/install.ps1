# WorkNote installer for Windows PowerShell / PowerShell 7.
# Run from the unzipped folder:
#   Set-ExecutionPolicy -Scope Process Bypass -Force; .\install.ps1

$ErrorActionPreference = 'Stop'
$src  = $PSScriptRoot
$dest = Join-Path $HOME 'bin\worknote'

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $src 'note.py'), (Join-Path $src 'note.ps1') -Destination $dest -Force
Get-ChildItem $dest | Unblock-File
Write-Host "Installed to $dest"

# Load it from your profile
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Force -Path $PROFILE | Out-Null }
if (-not (Select-String -Path $PROFILE -SimpleMatch 'worknote\note.ps1' -Quiet)) {
    Add-Content -Path $PROFILE -Value "`n. `"`$HOME\bin\worknote\note.ps1`""
    Write-Host "Added to profile: $PROFILE"
}

# Profiles don't load under the default 'Restricted' policy
$cu = Get-ExecutionPolicy -Scope CurrentUser
$lm = Get-ExecutionPolicy -Scope LocalMachine
if ($cu -in 'Undefined', 'Restricted' -and $lm -notin 'RemoteSigned', 'Unrestricted', 'Bypass') {
    try {
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
        Write-Host "Execution policy for your user set to RemoteSigned (needed to load the profile)."
    } catch {
        Write-Warning "Could not change execution policy (maybe set by your company). The profile may not load."
    }
}

. (Join-Path $dest 'note.ps1')
Write-Host ""
Write-Host "Done. 'note' works in this window now and in every new one." -ForegroundColor Green
Write-Host "Try:  note -l      then connect sync:  note --init USER@SERVER:worknotes.git"
