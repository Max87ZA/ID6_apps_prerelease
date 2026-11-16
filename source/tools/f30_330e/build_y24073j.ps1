# Builds BoostDeck, ShiftDeck and EngineCodes for NBTevo_Y24073J with the same
# compiler flags as source/native/build.sh, using the Windows-hosted QNX SDP 6.5.
$ErrorActionPreference = "Stop"
$env:QNX_HOST = "C:/QNX650/host/win32/x86"
$env:QNX_TARGET = "C:/QNX650/target/qnx6"
$env:QNX_CONFIGURATION = "C:\Program Files (x86)\QNX Software Systems"
$env:PATH = "C:\QNX650\host\win32\x86\usr\bin;$env:PATH"
Set-Location (Join-Path $PSScriptRoot "..\..\native")
New-Item -ItemType Directory -Force out | Out-Null
$fw = @("frameworks/libAppFramework.A.so", "frameworks/libCoreFramework.A.so")
$C = @("-V4.4.2,gcc_ntoarmv7le", "-Wc,-std=c99", "-Wall", "-Wextra", "-Werror")
$X = @("-V4.4.2,gcc_ntoarmv7le_gpp", "-lang-c++", "-Wc,-std=gnu++98", "-Wall", "-Wextra", "-Werror")
$L = @("-Lout", "-lm", "-lsocket")
function Run($label, $list) {
    Write-Host "== $label"
    & qcc @list
    if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
Run "core.o" ($C + @("-DPERF_LAB", "-Isrc", "-O2", "-fPIC", "-c", "src/gauge_core.c", "-o", "out/core.o"))
Run "libBoostDeck.so" ($X + @("-DPERF_LAB", "-DHV_SOC_BAR", "-DHYBRID_PAGE", "-Isrc", "-Isdk", "-O2", "-fno-strict-aliasing", "-fno-exceptions", "-fPIC", "-shared", "src/plugin.cpp", "out/core.o") + $fw + $L + @("-Wl,--allow-shlib-undefined", "-Wl,-soname,libBoostDeck.so", "-o", "out/libBoostDeck.so"))
Run "boostdeck-collector-qnx" ($C + @("-DNATIVE_FAST", "-DPERF_LAB", "-DHYBRID_PAGE","-Isrc", "-O2", "src/collector.c", "out/core.o") + $L + @("-o", "out/boostdeck-collector-qnx"))
Run "libShiftDeck.so" ($X + @("-DPERF_LAB", "-Isrc", "-Isdk", "-O2", "-fno-strict-aliasing", "-fno-exceptions", "-fPIC", "-shared", "-DNATIVE_SHIFT_SMOOTH", "src/shift_deck.cpp", "out/core.o") + $fw + $L + @("-Wl,--allow-shlib-undefined", "-Wl,-soname,libShiftDeck.so", "-o", "out/libShiftDeck.so"))
Run "shift-deck-qnx" ($C + @("-DNATIVE_FAST", "-Isrc", "-O2", "-DSHIFT_DECK_ONLY", "src/collector.c", "out/core.o") + $L + @("-o", "out/shift-deck-qnx"))
Run "libEngineCodes.so" ($X + @("-DPERF_LAB", "-Isrc", "-Isdk", "-O2", "-fno-strict-aliasing", "-fno-exceptions", "-fPIC", "-shared", "src/engine_codes.cpp", "out/core.o") + $fw + $L + @("-Wl,--allow-shlib-undefined", "-Wl,-soname,libEngineCodes.so", "-o", "out/libEngineCodes.so"))
Run "engine-codes-qnx" ($C + @("-Isrc", "-O2", "-DENGINE_CODES_ONLY", "src/collector.c", "out/core.o") + $L + @("-o", "out/engine-codes-qnx"))
Write-Host "BUILD OK"
Get-ChildItem out | Select-Object Name, Length
