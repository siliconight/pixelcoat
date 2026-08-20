# ============================================================
#  rebuild_theme_libraries.ps1  (pixelcoat 0.12.0)
#
#  WHAT THIS FIXES
#  ---------------
#  zoo core/skins.py load_pack() does:
#        manifests = sorted(glob("*.pack.json")); use manifests[0]
#  and pixelcoat build_material_pack() does makedirs(exist_ok=True)
#  WITHOUT removing what is already in the directory. So re-running
#  "theme-library" over an existing library LAYERS a second pack into
#  the same <kind>_<theme>/ folder, and the ALPHABETICALLY FIRST one
#  keeps winning.
#
#  Live proof, right now, in build\skins_rockay\metal_rockay\:
#        on disk : metal_brass_casino.pack.json     (built 1785930270)
#        profile : metal_galvanized_stadium         (edited  1785934005)
#  A plain rebuild would leave BOTH and brass would STILL win
#  ("metal_brass..." < "metal_galvanized..."). Hence: delete, then build.
#
#  Run:
#    pwsh -ExecutionPolicy Bypass -File C:\Projects\gabagool_studios\gabagool_factory\pixelcoat\tools\rebuild_theme_libraries.ps1
#  Audit only, write nothing:
#    pwsh -ExecutionPolicy Bypass -File ...\rebuild_theme_libraries.ps1 -Check
# ============================================================
param([switch]$Check)

$ErrorActionPreference = "Stop"
$Factory = "C:\Projects\gabagool_studios\gabagool_factory"
$Px      = Join-Path $Factory "pixelcoat"
$Build   = Join-Path $Px "build"
$Probe   = Join-Path $env:TEMP "pc_theme_probe.py"

$Themes = @("rockay","rockay_civic","rockay_retail","rockay_service","street")

if (-not (Test-Path $Px)) { Write-Host "no pixelcoat repo at $Px"; exit 1 }

# ---- the probe: compares every built pack dir against its theme profile ----
$py = @'
import glob, json, os, sys

px    = sys.argv[1]
build = os.path.join(px, "build")
prof  = os.path.join(px, "profiles")
themes_wanted = sys.argv[2:]

KNOWN = ("laminate","wood","metal","plastic","leather","rubber","canvas","carbon",
         "glass","glass_facade","paper","concrete","plaster","brick","tile","drywall",
         "ceiling_tile","carpet","dirt","tar","gravel","vegetation")

mats = {}
for p in sorted(glob.glob(os.path.join(prof, "materials", "*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    mats[d["id"]] = d["kind"]

bad = 0
print("")
print("  %-22s %-14s %-28s %s" % ("LIBRARY", "KIND", "PROFILE SAYS", "ON DISK"))
print("  " + "-" * 88)
for theme in themes_wanted:
    tp = os.path.join(prof, "themes", theme + ".json")
    if not os.path.isfile(tp):
        print("  %-22s  NO THEME PROFILE" % theme); bad += 1; continue
    want = json.load(open(tp, encoding="utf-8"))["materials"]
    lib  = os.path.join(build, "skins_" + theme)
    if not os.path.isdir(lib):
        print("  %-22s  NOT BUILT (%d kinds pending)" % ("skins_" + theme, len(want)))
        bad += 1
        continue
    for kind in sorted(want):
        d = os.path.join(lib, kind + "_" + theme)
        ms = sorted(glob.glob(os.path.join(d, "*.pack.json")))
        if not ms:
            got = "MISSING"
        elif len(ms) > 1:
            got = "AMBIGUOUS: " + ",".join(os.path.basename(m)[:-10] for m in ms)
        else:
            got = json.load(open(ms[0], encoding="utf-8")).get("material_profile", "?")
        ok = (got == want[kind])
        if not ok: bad += 1
        print("  %-22s %-14s %-28s %s %s"
              % ("skins_" + theme, kind, want[kind], got, "" if ok else "  <-- MISMATCH"))

# ---- the coverage table: which kinds no theme can dress at all -------------
allthemes = {}
for p in sorted(glob.glob(os.path.join(prof, "themes", "*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    allthemes[d["theme"]] = d["materials"]
slots = set()
for m in allthemes.values(): slots |= set(m)

print("")
print("  KIND COVERAGE  (%d material profiles, %d themes)" % (len(mats), len(allthemes)))
print("  %-14s %-9s %-8s %s" % ("KIND", "PROFILES", "THEMED", ""))
print("  " + "-" * 60)
for k in KNOWN:
    n = sum(1 for v in mats.values() if v == k)
    t = sum(1 for m in allthemes.values() if k in m)
    note = ""
    if t == 0 and n > 0: note = "profile exists, NO theme maps it"
    if t == 0 and n == 0: note = "no profile at all"
    print("  %-14s %-9d %-8d %s" % (k, n, t, note))

print("")
print("MISMATCHES=%d" % bad)
sys.exit(0)
'@

Set-Content -Path $Probe -Value $py -Encoding utf8

function Invoke-Probe {
    Push-Location $Px
    & python $Probe $Px @Themes
    Pop-Location
}

Write-Host ""
Write-Host "== BEFORE"
Invoke-Probe

if ($Check) {
    Write-Host ""
    Write-Host "-Check: nothing written."
    exit 0
}

Write-Host ""
Write-Host "== REBUILD (delete, then build -- see header for why delete)"
Push-Location $Px
$fail = 0
foreach ($t in $Themes) {
    $out = Join-Path $Build ("skins_" + $t)
    if (Test-Path $out) {
        Write-Host ("  rm  " + $out)
        Remove-Item -Recurse -Force $out
    }
    & python -m pixelcoat.cli.main theme-library --theme $t --out $out
    if ($LASTEXITCODE -ne 0) { $fail++; Write-Host ("  FAILED: " + $t) }
}
Pop-Location

Write-Host ""
Write-Host "== AFTER"
Invoke-Probe

if ($fail -gt 0) { Write-Host ""; Write-Host ("FAILED: " + $fail + " theme build(s)"); exit 1 }
Write-Host ""
Write-Host "Libraries are under pixelcoat\build\. Point Zoo at one with:"
Write-Host "  --skins pixelcoat\build\skins_rockay --theme rockay"
