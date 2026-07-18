# ============================================================
#  make_delco_signage.ps1 (pixelcoat v0.10.0) - build the DELCO
#  signage pack library: six retro sign faces (deli, pawn, auto,
#  open-24, cold beer, checks cashed) crushed to 128x64 PS1 packs
#  with emissive letterform maps, landed in the exact layout Zoo's
#  sign-pack resolver (v0.31+) consumes:
#
#      _runs\skins\delco_signage\signs_delco\<asset_id>\*.pack.json
#
#  Point zoo --skins at _runs\skins\delco_signage (the dress runner
#  does this automatically when the folder exists).
#
#  Home: pixelcoat\tools\. Sources ship with the recipes
#  (recipes\sources\) - the generator is included for variants.
#  Run:
#  powershell -ExecutionPolicy Bypass -File C:\Projects\gabagool_studios\gabagool_factory\pixelcoat\tools\make_delco_signage.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$PxRepo  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Factory = (Resolve-Path (Join-Path $PxRepo "..")).Path
$Runs    = Join-Path $Factory "_runs"
$Lib     = Join-Path $Runs "skins\delco_signage\signs_delco"
New-Item -ItemType Directory -Path $Lib -Force | Out-Null

$Sources = Join-Path $PxRepo "recipes\sources"
if (-not (Test-Path (Join-Path $Sources "sign_deli.png"))) {
    Write-Host "== generating sign sources"
    python (Join-Path $PSScriptRoot "gen_sign_sources.py") $Sources
}

Write-Host "== building 6 sign packs"
Push-Location $PxRepo
$fail = 0
Get-ChildItem (Join-Path $PxRepo "recipes\delco_signage") -Filter "sign_*.json" | ForEach-Object {
    python -m pixelcoat.cli.main build $_.FullName --output $Lib --json --force 2>&1 | Select-Object -Last 1 | ForEach-Object { Write-Host ("  " + $_.Substring(0, [Math]::Min(110, $_.Length))) }
    if ($LASTEXITCODE -ne 0) { $fail++ }
}
Pop-Location
if ($fail -gt 0) { Write-Host ("FAILED: " + $fail + " pack build(s)"); exit 1 }

Write-Host "== library"
Get-ChildItem $Lib -Directory | ForEach-Object {
    $manifest = Get-ChildItem $_.FullName -Filter "*.pack.json" | Select-Object -First 1
    $maps = if ($manifest) { ((Get-Content $manifest.FullName -Raw | ConvertFrom-Json).maps.PSObject.Properties.Name) -join "," } else { "NO MANIFEST" }
    Write-Host ("  " + $_.Name + "  [" + $maps + "]")
}
Write-Host ""
Write-Host ("SKINS LIBRARY -> " + (Split-Path $Lib -Parent))
Write-Host "Next: lot\tools\night_strip_dress.ps1 picks this up automatically."
