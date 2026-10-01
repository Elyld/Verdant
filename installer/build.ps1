#Requires -Version 5.1
<#
  Builds the Verdant Windows installer (.msi).

  Run from anywhere on Windows:
      powershell -ExecutionPolicy Bypass -File installer/build.ps1

  Needs: Python 3.12 with the repo's requirements.txt plus pyinstaller,
  and WiX Toolset v3 (install with: choco install wixtoolset).

  Steps: PyInstaller bundles the app into dist/verdant, heat harvests that
  folder into WiX components, then candle + light produce
  installer/dist/Verdant-<version>-x64.msi.
#>
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $version = ((Select-String -Path 'app/version.py' `
        -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value)
    Write-Host "Building Verdant $version"

    # 1. PyInstaller bundle (dist/verdant)
    pyinstaller --noconfirm installer/verdant.spec

    # 2. Locate WiX Toolset v3
    $wixBin = 'C:\Program Files (x86)\WiX Toolset v3.14\bin'
    if (-not (Test-Path "$wixBin\candle.exe")) {
        $wixBin = 'C:\Program Files (x86)\WiX Toolset v3.11\bin'
    }
    if (-not (Test-Path "$wixBin\candle.exe")) {
        throw 'WiX Toolset v3 not found. Install it with: choco install wixtoolset'
    }

    # 3. Harvest the bundle into WiX components
    New-Item -ItemType Directory -Force -Path installer/obj | Out-Null
    New-Item -ItemType Directory -Force -Path installer/dist | Out-Null
    & "$wixBin\heat.exe" dir 'dist\verdant' -gg -scom -sreg -sfrag -srd `
        -cg VerdantFiles -dr INSTALLFOLDER -var var.SourceDir `
        -out installer/files.wxs

    # 4. Find the File Id heat assigned to verdant.exe (Start menu target)
    $filesWxs = Get-Content installer/files.wxs -Raw
    $m = [regex]::Match($filesWxs,
        '<File Id="(fil[^"]+)"[^>]*Source="[^"]*verdant\.exe"')
    if (-not $m.Success) { throw 'Could not find verdant.exe in heat output' }
    $exeId = $m.Groups[1].Value
    Write-Host "verdant.exe File Id: $exeId"

    # 5. Compile and link the .msi
    & "$wixBin\candle.exe" -arch x64 `
        -dProductVersion=$version `
        "-dSourceDir=$repoRoot\dist\verdant" `
        -dVerdantExeFileId=$exeId `
        installer/verdant.wxs installer/files.wxs -out installer/obj/
    $msiName = "Verdant-$version-x64.msi"
    & "$wixBin\light.exe" installer/obj/verdant.wixobj installer/obj/files.wixobj `
        -out "installer/dist/$msiName"
    Write-Host "Built installer/dist/$msiName"
}
finally {
    Pop-Location
}
