# PAPPA: one command to check EVERY port in this repository.
#
#   powershell -File verify_all.ps1                 build + conformance vectors + unit tests
#   powershell -File verify_all.ps1 -Full           + pipeline of every port + numeric compare
#   powershell -File verify_all.ps1 -VectorsOnly    only build + conformance vectors
#   powershell -File verify_all.ps1 -Only r,julia   only the listed ports
#   powershell -File verify_all.ps1 -List           show the table of ports and commands
#
# Exit code: 0 = every executed gate passed (skips are allowed), 1 = something failed,
# 2 = nothing could be executed on this machine.
#
# A port whose toolchain is absent is reported as SKIP with the reason and does NOT fail
# the run: the repository is meant to be readable on a machine that has only a few of the
# toolchains installed.
#
# ENCODING NOTE: this file is UTF-8 without BOM, like every other .ps1 here. Windows
# PowerShell 5.1 reads such a file in the ANSI code page, so the EXECUTABLE text below is
# ASCII only (English messages); Cyrillic lives in comments, where mangling is harmless
# (details in julia/build_julia.ps1).
param(
    [switch]$Full,
    [switch]$VectorsOnly,
    [switch]$List,
    [switch]$NoBuild,
    [string]$Only = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$PS = 'powershell.exe'
$PSARGS = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File')

# ============================== helper layer ==============================

function New-Step([string]$Dir, [string[]]$Argv) {
    return @{ Dir = $Dir; Argv = $Argv }
}

function New-PsStep([string]$Script, [string[]]$Flags) {
    # A port build script runs in its own process: they call exit(n), which would
    # otherwise terminate this script halfway through the port list.
    $flags = @($Flags | Where-Object { $_ })
    $argv = @($PS) + $PSARGS + @($Script) + $flags
    return @{ Dir = '.'; Argv = $argv }
}

function Invoke-Step($Step, [hashtable]$Subst) {
    # Runs one external command, captures every stream, returns exit code + text.
    $argv = @()
    foreach ($a in $Step.Argv) {
        $s = [string]$a
        foreach ($k in $Subst.Keys) { $s = $s.Replace($k, $Subst[$k]) }
        $argv += $s
    }
    $dir = Join-Path $repo $Step.Dir
    $log = Join-Path $env:TEMP ('pappa_verify_' + [guid]::NewGuid().ToString('N') + '.log')

    Push-Location $dir
    # Native programs write warnings (e.g. "Finished `release` profile") to stderr;
    # PowerShell 5.1 turns that into a NativeCommandError and, with
    # ErrorActionPreference = 'Stop', would abort the whole run. The exit code is
    # the gate here, so stderr is captured, not fatal.
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $argv[0] @($argv[1..($argv.Count - 1)]) *> $log
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } finally {
        $ErrorActionPreference = $eap
        Pop-Location
    }

    $text = ''
    if (Test-Path $log) {
        $text = ((Get-Content $log -ErrorAction SilentlyContinue) | Out-String).Trim()
        Remove-Item $log -Force -ErrorAction SilentlyContinue
    }
    return @{ Code = [int]$code; Text = $text }
}

function Show-Tail([string]$Text, [int]$Lines = 3) {
    $arr = @($Text -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
    if ($arr.Count -eq 0) { return '(no output)' }
    return (($arr | Select-Object -Last $Lines) -join ' | ')
}

function Test-Tool([string[]]$Probes) {
    foreach ($p in $Probes) {
        if ($p -like '*:*') {
            if (Test-Path $p) { return $true }
        } elseif (Get-Command $p -ErrorAction SilentlyContinue) {
            return $true
        }
    }
    return $false
}

# --- Python with numpy: the reference sample and every numeric checker need it ---
$script:PyExe = $null
function Resolve-NumpyPython {
    if ($script:PyExe) { return $script:PyExe }
    $candidates = @()
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    $candidates += @(
        'C:\Users\maxan\miniconda3\envs\geom-toolkit\python.exe',
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
    )
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        try {
            & $c -c 'import numpy' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $script:PyExe = $c; return $c }
        } catch { }
    }
    return $null
}

# ============================== port table ==============================
# Every entry: Name, Title, Tool (probe list), Build, Vectors, Tests, Pipeline, Sample.
# Sample = folder under samples/ written by that port's pipeline (used by -Full).

$ports = @(
    @{
        Name = 'spec'; Title = 'Spec: JSON Schema of documents and manifests (no dependencies)'
        Tool = @('python')
        Build = $null
        Vectors = (New-Step '.' @('python', 'spec/check_schema.py'))
        Tests = $null
        Pipeline = $null
        Sample = ''
        Note = 'checks samples/**/sample.json and sections/*.pappa.json against spec/*.schema.json'
    },
    @{
        Name = 'python'; Title = 'Python (reference implementation, needs numpy)'
        Tool = @('python')
        Build = $null
        Vectors = $null
        Tests = $null
        Pipeline = (New-Step '.' @('%PY%', 'python/studies/build_sample.py', '--name', 'synthetic_sphere'))
        Sample = 'synthetic_sphere'
        Note = 'reference: builds the reference sample; other ports are compared against it'
    },
    @{
        Name = 'cpp'; Title = 'C++17 (CMake preset msvc-release + ctest)'
        Tool = @('cmake', 'ctest')
        Build = (New-Step 'cpp' @('cmake', '--build', '--preset', 'msvc-release'))
        Vectors = (New-Step 'cpp' @('ctest', '--preset', 'msvc-release', '-R', 'conformance_vectors', '--output-on-failure'))
        Tests = (New-Step 'cpp' @('ctest', '--preset', 'msvc-release', '--output-on-failure'))
        Pipeline = (New-Step '.' @('cpp/build-cmake/msvc-release/Release/pappa_pipeline.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_cpp', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_cpp'
    },
    @{
        Name = 'c'; Title = 'C99 (MSYS2 gcc; the Python checkers build the core themselves)'
        Tool = @('C:\msys64\mingw64\bin\gcc.exe')
        Build = $null
        Vectors = (New-Step '.' @('%PY%', 'python/studies/check_c_port.py'))
        Tests = (New-Step '.' @('%PY%', 'python/studies/check_c_pipeline.py'))
        Pipeline = (New-Step '.' @('c/pappa_c.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_c', '--name', 'synthetic_sphere'))
        Sample = 'synthetic_sphere_c'
    },
    @{
        Name = 'go'; Title = 'Go (go test + conformance runner)'
        Tool = @('go')
        Build = $null
        Vectors = (New-Step 'go' @('go', 'run', './cmd/conformance', '../spec/conformance/vectors'))
        Tests = (New-Step 'go' @('go', 'test', './...'))
        Pipeline = (New-Step 'go' @('go', 'run', './cmd/pappa', '-input', '../python/synthetic_data.csv', '-out-dir', '../samples/synthetic_sphere_go', '-name', 'synthetic_sphere', '-quiet'))
        Sample = 'synthetic_sphere_go'
    },
    @{
        Name = 'js'; Title = 'JavaScript (Node, ESM, node --test)'
        Tool = @('node')
        Build = $null
        Vectors = (New-Step 'js' @('node', 'cmd/conformance.js', '..'))
        Tests = (New-Step 'js' @('node', '--test'))
        Pipeline = (New-Step 'js' @('node', 'cmd/pappa.js', '--input', '../python/synthetic_data.csv', '--out-dir', '../samples/synthetic_sphere_js', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_js'
    },
    @{
        Name = 'fortran'; Title = 'Fortran 2018 (gfortran 10.3; no external libraries)'
        Tool = @('gfortran', 'C:\TDM-GCC-64\bin\gfortran.exe',
                 'C:\msys64\mingw64\bin\gfortran.exe', 'C:\msys64\ucrt64\bin\gfortran.exe')
        Build = $null
        Vectors = (New-PsStep 'fortran/build_fortran.ps1' @('-Vectors'))
        Tests = (New-PsStep 'fortran/build_fortran.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('fortran/bin/pappa.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_fortran', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_fortran'
        Note = 'one build script compiles modules, conformance and selftest; -Test = vectors + JSON round-trip + smoke fit'
    },
    @{
        Name = 'java'; Title = 'Java (plain javac; SelfTest = vectors + smoke fit)'
        Tool = @('javac', 'java')
        Build = $null
        Vectors = (New-PsStep 'java/build.ps1' @('-Test'))
        Tests = (New-PsStep 'java/build.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('java', '-cp', 'java/out', 'pappa.cli.PappaMain', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_java', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_java'
        Note = 'one SelfTest run covers both the vectors and the smoke fit'
    },
    @{
        Name = 'kotlin'; Title = 'Kotlin (kotlinc from Android Studio; SelfTest)'
        Tool = @('kotlinc', 'C:\Program Files\Android\Android Studio\plugins\Kotlin\kotlinc\bin\kotlinc.bat')
        Build = $null
        Vectors = (New-PsStep 'kotlin/build.ps1' @('-Test'))
        Tests = (New-PsStep 'kotlin/build.ps1' @('-Test'))
        Pipeline = $null
        Sample = 'synthetic_sphere_kotlin'
        Note = 'pipeline by hand: java -cp kotlin/out pappa.cli.PappaMain ... (kotlin-stdlib on the classpath)'
    },
    @{
        Name = 'rust'; Title = 'Rust (cargo --offline, zero crates)'
        Tool = @((Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'), 'cargo')
        Build = $null
        Vectors = (New-PsStep 'rust/build.ps1' @('-Vectors'))
        Tests = (New-PsStep 'rust/build.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('rust/target/release/pappa.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_rust', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_rust'
    },
    @{
        Name = 'pascal'; Title = 'Free Pascal (FPC 3.2, nothing beyond the RTL)'
        Tool = @('fpc', 'C:\FPC\3.2.2\bin\i386-Win32\fpc.exe')
        Build = $null
        Vectors = (New-PsStep 'pascal/build_fpc.ps1' @('-Vectors'))
        Tests = (New-PsStep 'pascal/build_fpc.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('pascal/bin/pappa.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_pascal', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_pascal'
    },
    @{
        Name = 'swift'; Title = 'Swift (SwiftPM; needs SDKROOT on Windows)'
        Tool = @('swift', (Join-Path $env:LOCALAPPDATA 'Programs\Swift'))
        Build = $null
        Vectors = (New-PsStep 'swift/build_swift.ps1' @('-Vectors'))
        Tests = (New-PsStep 'swift/build_swift.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('swift/.build/release/PappaCLI.exe', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_swift', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_swift'
    },
    @{
        Name = 'julia'; Title = 'Julia (package Pappa, stdlib only, works offline)'
        Tool = @((Join-Path $env:USERPROFILE '.julia\juliaup'), 'julia', 'C:\Julia')
        Build = $null
        Vectors = (New-PsStep 'julia/build_julia.ps1' @('-Vectors'))
        Tests = (New-PsStep 'julia/build_julia.ps1' @('-Test'))
        Pipeline = (New-PsStep 'julia/build_julia.ps1' @('-Pipeline'))
        Sample = 'synthetic_sphere_julia'
    },
    @{
        Name = 'r'; Title = 'R (base R only: own JSON, CSV, statistics)'
        Tool = @('Rscript', (Join-Path $env:ProgramFiles 'R'))
        Build = $null
        Vectors = (New-PsStep 'r/build_r.ps1' @('-Vectors'))
        Tests = (New-PsStep 'r/build_r.ps1' @('-Test'))
        Pipeline = (New-PsStep 'r/build_r.ps1' @('-Pipeline'))
        Sample = 'synthetic_sphere_r'
    }
    @{
        Name = 'csharp'; Title = 'C# (.NET 10, zero NuGet packages; SelfTest = vectors + smoke + round-trip)'
        Tool = @('dotnet', (Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'))
        Build = (New-PsStep 'csharp/build.ps1' @())
        Vectors = (New-PsStep 'csharp/build.ps1' @('-Vectors'))
        Tests = (New-PsStep 'csharp/build.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('csharp/bin/Release/net10.0/pappa.exe', 'pipeline', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_csharp', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_csharp'
        Note = 'one exe, three subcommands: conformance | selftest | pipeline'
    }
    @{
        Name = 'octave'; Title = 'GNU Octave (core only: own JSON, CSV, statistics)'
        Tool = @('octave-cli', 'octave', (Join-Path $env:LOCALAPPDATA 'Programs\GNU Octave'), (Join-Path $env:ProgramFiles 'GNU Octave'))
        Build = $null
        Vectors = (New-PsStep 'octave/build_octave.ps1' @('-Vectors'))
        Tests = (New-PsStep 'octave/build_octave.ps1' @('-Test'))
        Pipeline = (New-PsStep 'octave/build_octave.ps1' @('-Pipeline'))
        Sample = 'synthetic_sphere_octave'
        Note = 'bin/*.m scripts; the self-test covers vectors + smoke fit + document round-trip'
    }
    @{
        Name = 'vba'; Title = 'VBA 7 in Microsoft Excel (modules imported through COM)'
        Tool = @("$env:ProgramFiles\Microsoft Office\root\Office16\EXCEL.EXE",
                 "$env:ProgramFiles\Microsoft Office\Office16\EXCEL.EXE",
                 "${env:ProgramFiles(x86)}\Microsoft Office\root\Office16\EXCEL.EXE",
                 "${env:ProgramFiles(x86)}\Microsoft Office\Office16\EXCEL.EXE")
        Build = (New-PsStep 'vba/build_vba.ps1' @())
        Vectors = (New-PsStep 'vba/build_vba.ps1' @('-Vectors'))
        Tests = (New-PsStep 'vba/build_vba.ps1' @('-Test'))
        Pipeline = (New-PsStep 'vba/build_vba.ps1' @('-Pipeline'))
        Sample = 'synthetic_sphere_vba'
        Note = 'needs Excel 2016+ and a one-time AccessVBOM; every run goes through a job with a timeout'
    }
    @{
        Name = 'fsharp'; Title = 'F# (.NET 10, zero NuGet packages; SelfTest = vectors + smoke + round-trip)'
        Tool = @('dotnet', (Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'))
        Build = (New-PsStep 'fsharp/build_fsharp.ps1' @())
        Vectors = (New-PsStep 'fsharp/build_fsharp.ps1' @('-Vectors'))
        Tests = (New-PsStep 'fsharp/build_fsharp.ps1' @('-Test'))
        Pipeline = (New-Step '.' @('fsharp/bin/Release/net10.0/pappa.exe', 'pipeline', '--input', 'python/synthetic_data.csv', '--out-dir', 'samples/synthetic_sphere_fsharp', '--name', 'synthetic_sphere', '--quiet'))
        Sample = 'synthetic_sphere_fsharp'
        Note = 'one exe, three subcommands like csharp; POSIX twin: bash fsharp/build_fsharp.sh --vectors (no PowerShell)'
    }

)

# ============================== driver ==============================

$selected = $ports
if ($Only -ne '') {
    $wanted = @($Only -split ',' | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ -ne '' })
    $selected = @($ports | Where-Object { $wanted -contains $_.Name })
    if ($selected.Count -eq 0) { throw "No port matches -Only '$Only' (see -List)." }
}

if ($List) {
    Write-Host 'PAPPA ports and their gates:'
    foreach ($p in $selected) {
        Write-Host ('  {0,-7} {1}' -f $p.Name, $p.Title)
        foreach ($k in @('Build', 'Vectors', 'Tests', 'Pipeline')) {
            if ($p.$k) { Write-Host ('          {0,-9} {1}' -f $k, ($p.$k.Argv -join ' ')) }
        }
        if ($p.Note) { Write-Host ('          note      {0}' -f $p.Note) }
    }
    exit 0
}

# --- Python with numpy: reference sample + every numeric checker need it ---
$needPython = $false
foreach ($p in $selected) {
    foreach ($step in @($p.Vectors, $p.Tests)) {
        if ($step -and (($step.Argv -join ' ') -like '*%PY%*')) { $needPython = $true }
    }
    if ($Full -and $p.Sample -ne '') { $needPython = $true }
}
$py = Resolve-NumpyPython
if ($needPython -and -not $py) {
    Write-Warning 'Python with numpy not found: the Python/C checkers and the numeric comparison will be skipped.'
}
$subst = @{ '%PY%' = $py }

if ($Full) {
    $refManifest = Join-Path $repo 'samples/synthetic_sphere/sample.json'
    if ($py -and -not (Test-Path $refManifest)) {
        Write-Host '[reference] building samples/synthetic_sphere with Python'
        $r = Invoke-Step (New-Step '.' @('%PY%', 'python/studies/build_sample.py', '--name', 'synthetic_sphere')) $subst
        if ($r.Code -ne 0) { Write-Host ('  FAILED (exit {0}): {1}' -f $r.Code, (Show-Tail $r.Text)) }
    }
}

$rows = @()
foreach ($p in $selected) {
    $status = 'OK'
    $col = @{ vectors = '-'; tests = '-'; pipeline = '-'; verify = '-' }
    $note = $p.Note

    $toolOk = $true
    if ($p.Name -eq 'python') { $toolOk = [bool]$py } elseif ($p.Tool.Count -gt 0) { $toolOk = Test-Tool $p.Tool }
    if (-not $toolOk) {
        Write-Host ('[skip]      {0,-7} toolchain not found on this machine' -f $p.Name)
        $rows += [pscustomobject]@{ Port = $p.Name; Vectors = 'SKIP'; Tests = 'SKIP'; Pipeline = 'SKIP'; Verify = 'SKIP'; Status = 'SKIP'; Note = 'toolchain not found' }
        continue
    }

    if ($p.Build -and -not $NoBuild) {
        $b = Invoke-Step $p.Build $subst
        if ($b.Code -ne 0) {
            Write-Host ('[fail]      {0,-7} build exit {1}: {2}' -f $p.Name, $b.Code, (Show-Tail $b.Text))
            $rows += [pscustomobject]@{ Port = $p.Name; Vectors = 'FAIL'; Tests = '-'; Pipeline = '-'; Verify = '-'; Status = 'FAIL'; Note = ('build exit ' + $b.Code) }
            continue
        }
    }

    $gates = @()
    if ($p.Vectors) { $gates += , @('Vectors', $p.Vectors) }
    if ($p.Tests -and -not $VectorsOnly) { $gates += , @('Tests', $p.Tests) }
    if ($Full -and -not $VectorsOnly -and $p.Pipeline) { $gates += , @('Pipeline', $p.Pipeline) }

    foreach ($g in $gates) {
        $label = $g[0]; $step = $g[1]
        $key = $label.ToLower()
        $res = Invoke-Step $step $subst
        if ($res.Code -eq 0) {
            $col[$key] = 'OK'
            Write-Host ('[ok]        {0,-7} {1}' -f $p.Name, $label)
        } else {
            $col[$key] = 'FAIL'
            $status = 'FAIL'
            Write-Host ('[fail]      {0,-7} {1} exit {2}: {3}' -f $p.Name, $label, $res.Code, (Show-Tail $res.Text))
        }
    }

    # --- -Full: numeric comparison of the port's sample against the reference ---
    if ($Full -and -not $VectorsOnly) {
        $sampleDir = Join-Path $repo ('samples/' + $p.Sample)
        $portManifest = Join-Path $sampleDir 'sample.json'
        $refDir = Join-Path $repo 'samples/synthetic_sphere'
        if ($p.Name -ne 'python' -and $p.Sample -ne '' -and $py -and (Test-Path $portManifest) -and (Test-Path (Join-Path $refDir 'sample.json'))) {
            $v = Invoke-Step (New-Step '.' @('%PY%', 'python/studies/verify_port.py', '--py-dir', $refDir, '--cpp-dir', $sampleDir)) $subst
            if ($v.Code -eq 0) {
                $col['verify'] = 'OK'
                Write-Host ('[ok]        {0,-7} verify_port: {1}' -f $p.Name, (Show-Tail $v.Text 1))
            } else {
                $col['verify'] = 'FAIL'
                $status = 'FAIL'
                Write-Host ('[fail]      {0,-7} verify_port exit {1}: {2}' -f $p.Name, $v.Code, (Show-Tail $v.Text))
            }
        } elseif ($p.Name -ne 'python' -and $p.Sample -ne '') {
            $col['verify'] = 'SKIP'
            if (-not $note) { $note = 'no sample folder for the numeric compare' }
            Write-Host ('[skip]      {0,-7} numeric compare: no sample folder' -f $p.Name)
        }
    }

    if ($p.Name -eq 'python') { $col['vectors'] = 'n/a'; $col['tests'] = 'n/a' }
    $rows += [pscustomobject]@{ Port = $p.Name; Vectors = $col['vectors']; Tests = $col['tests']; Pipeline = $col['pipeline']; Verify = $col['verify']; Status = $status; Note = $note }
}

Write-Host ''
$rows | Format-Table -AutoSize Port, Vectors, Tests, Pipeline, Verify, Status | Out-String | Write-Host

$ok = @($rows | Where-Object { $_.Status -eq 'OK' }).Count
$skip = @($rows | Where-Object { $_.Status -eq 'SKIP' }).Count
$fail = @($rows | Where-Object { $_.Status -eq 'FAIL' }).Count
Write-Host ('summary: {0} OK, {1} SKIP, {2} FAIL (of {3} ports)' -f $ok, $skip, $fail, $rows.Count)
if ($fail -gt 0) { exit 1 }
if ($ok -eq 0) { exit 2 }
exit 0

