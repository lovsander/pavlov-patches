# Сборка Rust-порта PAPPA. cargo обычно лежит в %USERPROFILE%\.cargo\bin (rustup),
# и в уже открытом терминале его может не быть в PATH — скрипт это чинит сам.
#
#   powershell -File rust/build.ps1             собрать (release)
#   powershell -File rust/build.ps1 -Test       собрать и прогнать cargo test
#   powershell -File rust/build.ps1 -Vectors    собрать и проверить конформанс-векторы
param(
    [switch]$Test,
    [switch]$Vectors
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

# --- поиск cargo ---
$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
if (Test-Path (Join-Path $cargoBin 'cargo.exe')) {
    if ($env:Path -notlike "*$cargoBin*") { $env:Path = "$cargoBin;$env:Path" }
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo не найден. Установите Rust (rustup) или добавьте %USERPROFILE%\.cargo\bin в PATH."
}
Write-Host ("cargo: " + (Get-Command cargo).Source)

Push-Location $here
try {
    & cargo build --release --offline
    if ($LASTEXITCODE -ne 0) { throw "cargo build вернул код $LASTEXITCODE" }

    if ($Test) {
        & cargo test --release --offline
        if ($LASTEXITCODE -ne 0) { throw "cargo test вернул код $LASTEXITCODE" }
        exit 0
    }
    if ($Vectors) {
        & (Join-Path $here 'target\release\conformance.exe') (Join-Path $repo 'spec\conformance\vectors')
        if ($LASTEXITCODE -ne 0) { throw "векторы: код $LASTEXITCODE" }
        exit 0
    }
} finally {
    Pop-Location
}

Write-Host "векторы:  .\rust\target\release\conformance.exe spec\conformance\vectors"
Write-Host "тесты:    cd rust; cargo test --release --offline"
Write-Host "пайплайн: .\rust\target\release\pappa.exe --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_rust"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_rust"
