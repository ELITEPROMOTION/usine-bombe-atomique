<#
.SYNOPSIS
  UBA Local-Prod : arrete la stack local-prod (10 containers).
#>
param([switch]$Volumes)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $root

Write-Host ""
Write-Host "  > Arret stack local-prod..." -ForegroundColor Cyan

if ($Volumes) {
    docker compose -f docker-compose.local-prod.yml down -v
    Write-Host "  OK Stack arretee + volumes supprimes." -ForegroundColor Yellow
} else {
    docker compose -f docker-compose.local-prod.yml down
    Write-Host "  OK Stack arretee (volumes preserves)." -ForegroundColor Green
}

Write-Host ""
