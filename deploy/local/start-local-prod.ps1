<#
.SYNOPSIS
  UBA Local-Prod : demarre la stack complete (10 containers) avec reverse-proxy nginx + SSL.

.DESCRIPTION
  1. Stoppe la stack dev si elle tourne
  2. Verifie/ajoute les entrees hosts (eleve en admin si besoin)
  3. Demarre docker-compose.local-prod.yml
  4. Attend que tous les containers soient healthy
  5. Trust le certificat SSL self-signed dans le store Windows
  6. Ouvre https://uba.localhost dans le navigateur
#>
param(
    [switch]$SkipHosts,
    [switch]$SkipTrust,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $root

function Info($msg)  { Write-Host "  > $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "  OK $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  !! $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "  XX $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host "  UBA Local-Prod : demarrage" -ForegroundColor Magenta
Write-Host "==============================================" -ForegroundColor Magenta
Write-Host ""

# 1. Stop dev stack
Info "Stop dev stack si elle tourne..."
docker compose -f docker-compose.yml down 2>&1 | Out-Null
Ok "dev stack arretee."

# 2. Hosts
if (-not $SkipHosts) {
    Info "Verification du fichier hosts..."
    $hostsContent = Get-Content "$env:WINDIR\System32\drivers\etc\hosts" -Raw
    if ($hostsContent -notmatch "uba\.localhost") {
        Warn "Entree manquante. Lancement du script en admin pour modifier hosts..."
        $hostsScript = "$PSScriptRoot\setup-hosts.ps1"
        Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$hostsScript`"" -Wait
    } else {
        Ok "uba.localhost mappe a 127.0.0.1."
    }
}

# 3. Verify SSL cert exists
$certPath = "$root\deploy\local\ssl\cert.pem"
$keyPath  = "$root\deploy\local\ssl\key.pem"
if (-not (Test-Path $certPath) -or -not (Test-Path $keyPath)) {
    Fail "Certificat SSL absent. Generer avec : openssl req ... (voir deploy/local/ssl/openssl.cnf)"
}
Ok "Certificat SSL present."

# 4. Verify .env.local-prod exists
if (-not (Test-Path "$root\.env.local-prod")) {
    Fail ".env.local-prod manquant a la racine."
}
Ok ".env.local-prod present."

# 5. Start stack
Info "Demarrage de la stack (10 containers)..."
docker compose -f docker-compose.local-prod.yml up -d
if ($LASTEXITCODE -ne 0) { Fail "docker compose up a echoue." }

# 6. Wait healthchecks
Info "Attente healthchecks (max 120s)..."
$deadline = (Get-Date).AddSeconds(120)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $statusJson = docker compose -f docker-compose.local-prod.yml ps --format json 2>$null
    if ($statusJson) {
        $services = @($statusJson -split "`n" | Where-Object { $_ } | ForEach-Object { try { $_ | ConvertFrom-Json } catch {} })
        $unhealthy = @($services | Where-Object { $_.Health -and $_.Health -ne 'healthy' -and $_.Health -ne 'starting' })
        $starting  = @($services | Where-Object { $_.Health -eq 'starting' })
        if ($unhealthy.Count -eq 0 -and $starting.Count -eq 0) {
            $ready = $true
            break
        }
    }
    Start-Sleep -Seconds 3
}

if ($ready) {
    Ok "Tous les containers healthy."
} else {
    Warn "Certains containers ne sont pas healthy apres 120s. Continuer quand meme."
    docker compose -f docker-compose.local-prod.yml ps
}

# 7. Trust SSL cert
if (-not $SkipTrust) {
    Info "Trust du certificat dans le store Windows (Root CA)..."
    try {
        certutil -addstore -f Root $certPath 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Ok "Certificat trust dans Root."
        } else {
            Warn "Trust automatique echoue (code $LASTEXITCODE). Vous pouvez accepter le warning navigateur manuellement."
        }
    } catch {
        Warn "certutil indisponible. Le navigateur affichera un warning SSL : c'est normal en local."
    }
}

# 8. Smoke test
Info "Smoke test https://uba.localhost/healthz..."
try {
    $resp = Invoke-WebRequest -Uri "https://uba.localhost/healthz" -SkipCertificateCheck -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -eq 200) {
        Ok "https://uba.localhost OK ($($resp.StatusCode))"
    } else {
        Warn "Code HTTP $($resp.StatusCode)"
    }
} catch {
    Warn "Smoke test echoue : $_"
}

# 9. Open browser
if (-not $NoOpen) {
    Info "Ouverture du navigateur..."
    Start-Process "https://uba.localhost"
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  UBA Local-Prod : pret" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  URL principale : https://uba.localhost" -ForegroundColor White
Write-Host "  API directe    : https://uba.localhost/api/v1/health" -ForegroundColor White
Write-Host "  Docs OpenAPI   : https://uba.localhost/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Stop : .\deploy\local\stop-local-prod.ps1" -ForegroundColor Gray
Write-Host ""
