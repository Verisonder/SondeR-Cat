<#
    build_msix.ps1  —  build the SondeR cat Microsoft Store package (MSIX)

    Produces a self-contained MSIX that bundles its own Python runtime, so the
    Store build never needs Python installed (unlike the GitHub installer).

    It uses the SAME sondercat.py / sprites.py / libs as the GitHub build —
    one source, two packages — and drops a STORE_BUILD marker so the app
    disables its self-updater and lets the Store handle updates.

    Run on Windows with the Windows SDK on PATH (for makeappx.exe) and a C
    compiler (MSVC 'cl' or MinGW gcc) for the launcher.

    Usage:
        pwsh ./msix/build_msix.ps1 `
             -IdentityName  "1234ABCD.SondeRcat" `
             -Publisher     "CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX" `
             -PublisherName "Your Name"

    Output: msix/out/SondeRcat.msix   (unsigned — the Store re-signs it)
#>

param(
    [Parameter(Mandatory=$true)][string]$IdentityName,
    [Parameter(Mandatory=$true)][string]$Publisher,
    [Parameter(Mandatory=$true)][string]$PublisherName,
    [string]$PythonVersion = "3.12.7",
    [string]$Arch = "amd64"
)

$ErrorActionPreference = "Stop"
$repo   = Split-Path -Parent $PSScriptRoot          # repo root
$msix   = $PSScriptRoot
$stage  = Join-Path $msix "stage"
$app    = Join-Path $stage "app"
$out    = Join-Path $msix "out"

Write-Host "== SondeR cat MSIX build ==" -ForegroundColor Cyan

# --- 0. read APP_VERSION from the single source of truth -----------------
$verLine = Select-String -Path (Join-Path $repo "sondercat.py") `
                         -Pattern '^APP_VERSION = "([^"]+)"' | Select-Object -First 1
$appVer  = $verLine.Matches[0].Groups[1].Value
$pkgVer  = "$appVer.0"                              # 4-part, last part 0
Write-Host "app version : $appVer  (package $pkgVer)"

# --- 1. clean staging ----------------------------------------------------
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $app, $out, (Join-Path $stage "Assets") | Out-Null

# --- 2. embeddable Python runtime ---------------------------------------
$pyZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-$Arch.zip"
$pyZip    = Join-Path $env:TEMP "python-embed.zip"
Write-Host "downloading $pyZipUrl"
Invoke-WebRequest -Uri $pyZipUrl -OutFile $pyZip
$pyDir = Join-Path $app "python"
Expand-Archive -Path $pyZip -DestinationPath $pyDir -Force

# make the embeddable runtime see the app dir + libs even with a ._pth file
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
if ($pth) {
    Add-Content -Path $pth.FullName -Value "..`r`n..\libs"
}

# --- 3. app payload (shared source) -------------------------------------
Copy-Item (Join-Path $repo "sondercat.py")       $app
Copy-Item (Join-Path $repo "sprites.py")         $app
Copy-Item (Join-Path $repo "meow.wav")           $app -ErrorAction SilentlyContinue
Copy-Item (Join-Path $repo "sondercat_gray.ico") $app -ErrorAction SilentlyContinue
Copy-Item (Join-Path $repo "assets") $app -Recurse -ErrorAction SilentlyContinue
Copy-Item (Join-Path $repo "libs")   $app -Recurse

# the marker that flips APP_CHANNEL -> "store" (disables self-update)
New-Item -ItemType File -Force -Path (Join-Path $app "STORE_BUILD") | Out-Null

# --- 4. compile the launcher --------------------------------------------
$launcherOut = Join-Path $app "SondeRCat.exe"
$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if ($cl) {
    Push-Location $app
    $clOut = & cl /nologo /O2 (Join-Path $msix "launcher.c") /Fe:$launcherOut `
        /link user32.lib shell32.lib shlwapi.lib 2>&1
    $clRc = $LASTEXITCODE
    Get-ChildItem $app -Filter *.obj | Remove-Item -Force -ErrorAction SilentlyContinue
    Pop-Location
    if ($clRc -ne 0 -or -not (Test-Path $launcherOut)) {
        throw "cl failed (rc=$clRc): $($clOut -join ' // ')"
    }
} else {
    $gcc = Get-Command x86_64-w64-mingw32-gcc -ErrorAction SilentlyContinue
    if (-not $gcc) { throw "Need MSVC 'cl' or mingw gcc to build the launcher." }
    & x86_64-w64-mingw32-gcc (Join-Path $msix "launcher.c") `
        -o $launcherOut -mwindows -lshlwapi
    if ($LASTEXITCODE -ne 0) { throw "mingw gcc failed to build the launcher." }
}

# --- 5. Store assets (logos) --------------------------------------------
# The manifest references these PNGs; makeappx fails if any are missing.
# Use real logos from msix/store-assets when present, else generate simple
# placeholders so a test build always succeeds.
$srcAssets = Join-Path $msix "store-assets"
$dstAssets = Join-Path $stage "Assets"
$required = @{
    "StoreLogo.png"          = 50
    "Square44x44Logo.png"    = 44
    "Square71x71Logo.png"    = 71
    "Square150x150Logo.png"  = 150
    "Square310x310Logo.png"  = 310
    "Wide310x150Logo.png"    = @(310, 150)
}
Add-Type -AssemblyName System.Drawing
foreach ($name in $required.Keys) {
    $dst = Join-Path $dstAssets $name
    $src = Join-Path $srcAssets $name
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        continue
    }
    $dim = $required[$name]
    $w = if ($dim -is [array]) { $dim[0] } else { $dim }
    $h = if ($dim -is [array]) { $dim[1] } else { $dim }
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g   = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::FromArgb(255, 232, 150, 74))   # cat orange
    $g.Dispose()
    $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Warning "placeholder logo generated: $name ($w x $h) — replace before real submission"
}

# --- 6. manifest with real identity + version ---------------------------
$manifest = Get-Content (Join-Path $msix "AppxManifest.xml") -Raw
$manifest = $manifest -replace 'Name="PUBLISHER.SondeRcat"', "Name=`"$IdentityName`""
$manifest = $manifest -replace 'Publisher="CN=REPLACE-WITH-PARTNER-CENTER-PUBLISHER-ID"', "Publisher=`"$Publisher`""
$manifest = $manifest -replace 'REPLACE-WITH-PUBLISHER-DISPLAY-NAME', $PublisherName
$manifest = $manifest -replace 'Version="0.0.0.0"', "Version=`"$pkgVer`""
Set-Content -Path (Join-Path $stage "AppxManifest.xml") -Value $manifest -Encoding UTF8

# --- 7. pack -------------------------------------------------------------
$makeappx = Get-Command makeappx.exe -ErrorAction SilentlyContinue
if (-not $makeappx) { throw "makeappx.exe not found — install the Windows SDK." }
$msixOut = Join-Path $out "SondeRcat.msix"
$maOut = & makeappx pack /d $stage /p $msixOut /o 2>&1
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $msixOut)) {
    throw "makeappx failed (rc=$LASTEXITCODE): $($maOut -join ' // ')"
}

Write-Host "`nBuilt: $msixOut" -ForegroundColor Green
Write-Host "Unsigned by design — the Microsoft Store re-signs it on submission."
