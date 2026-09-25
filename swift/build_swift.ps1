# Сборка Swift-порта PAPPA. Тулчейн ищется в %LOCALAPPDATA%\Programs\Swift (как ставит
# установщик swift.org) или в PATH. КРИТИЧНО: Swift на Windows требует SDKROOT ->
# <Platforms>\<ver>\Windows.platform\Developer\SDKs\Windows.sdk, иначе «unable to load
# standard library for target 'x86_64-unknown-windows-msvc'».
#
#   powershell -File swift/build_swift.ps1            собрать (release)
#   powershell -File swift/build_swift.ps1 -Test      собрать и прогнать swift test
#   powershell -File swift/build_swift.ps1 -Vectors   собрать и проверить векторы
#   powershell -File swift/build_swift.ps1 -Clean     пересобрать с нуля
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$swiftRoot = Join-Path $env:LOCALAPPDATA 'Programs\Swift'

# --- PATH: компилятор + рантайм (swiftCore.dll и т.п.) ---
$toolchain = Get-ChildItem (Join-Path $swiftRoot 'Toolchains') -Directory -ErrorAction SilentlyContinue |
    Select-Object -First 1
$runtime = Get-ChildItem (Join-Path $swiftRoot 'Runtimes') -Directory -ErrorAction SilentlyContinue |
    Select-Object -First 1
$platform = Get-ChildItem (Join-Path $swiftRoot 'Platforms') -Directory -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($toolchain) { $env:Path = "$($toolchain.FullName)\usr\bin;$env:Path" }
if ($runtime) { $env:Path = "$($runtime.FullName)\usr\bin;$env:Path" }

# --- SDKROOT: без него swiftc не находит стандартную библиотеку ---
if ($platform) {
    $sdk = Join-Path $platform.FullName 'Windows.platform\Developer\SDKs\Windows.sdk'
    if (Test-Path $sdk) { $env:SDKROOT = $sdk }
}
if (-not (Get-Command swift -ErrorAction SilentlyContinue)) {
    throw "swift не найден. Установите Swift for Windows (swift.org) или добавьте его bin в PATH."
}
Write-Host ("swift: " + (Get-Command swift).Source)
if ($env:SDKROOT) { Write-Host ("SDKROOT: " + $env:SDKROOT) }

Push-Location $here
try {
    if ($Clean -and (Test-Path (Join-Path $here '.build'))) {
        Remove-Item -Recurse -Force (Join-Path $here '.build')
    }
    & swift build -c release
    if ($LASTEXITCODE -ne 0) { throw "swift build вернул код $LASTEXITCODE" }

    if ($Test) {
        & swift test
        if ($LASTEXITCODE -ne 0) { throw "swift test вернул код $LASTEXITCODE" }
        exit 0
    }
    if ($Vectors) {
        & (Join-Path $here '.build\release\ConformanceCLI.exe') (Join-Path $repo 'spec\conformance\vectors')
        if ($LASTEXITCODE -ne 0) { throw "векторы: код $LASTEXITCODE" }
        exit 0
    }
} finally {
    Pop-Location
}

Write-Host "векторы:  .\swift\.build\release\ConformanceCLI.exe spec\conformance\vectors"
Write-Host "тесты:    cd swift; swift test"
Write-Host "пайплайн: .\swift\.build\release\PappaCLI.exe --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_swift"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_swift"
