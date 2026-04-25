#Requires -RunAsAdministrator
<#
.SYNOPSIS
  UBA Local-Prod : ajoute uba.localhost et api.uba.localhost dans hosts file.

.NOTES
  Doit etre execute en tant qu'administrateur.
  Idempotent : ne fait rien si les entrees sont deja presentes.
#>
param()

$ErrorActionPreference = "Stop"
$hostsPath = "$env:WINDIR\System32\drivers\etc\hosts"

$entries = @(
    "127.0.0.1 uba.localhost",
    "127.0.0.1 api.uba.localhost"
)

$content = Get-Content -Path $hostsPath -Raw
$added = 0

foreach ($entry in $entries) {
    if ($content -notmatch [regex]::Escape($entry)) {
        Add-Content -Path $hostsPath -Value $entry
        Write-Host "  + $entry" -ForegroundColor Green
        $added++
    } else {
        Write-Host "  = $entry (deja present)" -ForegroundColor Gray
    }
}

if ($added -gt 0) {
    Write-Host ""
    Write-Host "$added entree(s) ajoutee(s) au fichier hosts." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Aucune modification necessaire." -ForegroundColor Cyan
}
