# Сборка и прогон VBA-порта PAPPA (Excel/VBA 7, Office 2016 и новее).
# Компиляции нет: модули .bas импортируются в книгу Excel и вызываются через COM
# (Application.Run). Excel ищется по стандартным путям Office16, PROGID
# Excel.Application берётся как запасной вариант.
#
#   powershell -File vba/build_vba.ps1            проверить, что модули грузятся
#   powershell -File vba/build_vba.ps1 -Test      + самопроверка (векторы, юниты, round-trip)
#   powershell -File vba/build_vba.ps1 -Vectors   + конформанс-векторы
#   powershell -File vba/build_vba.ps1 -Pipeline  + пайплайн и подсказка со сверкой
#
# ВАЖНО ПРО ОБЪЕКТНУЮ МОДЕЛЬ: импорт .bas через VBProject требует «доверенного
# доступа к объектной модели проекта VBA» (Excel: Параметры -> Центр управления
# безопасностью -> Параметры макросов). Флаг живёт в реестре,
# HKCU\Software\Microsoft\Office\<версия>\Excel\Security\AccessVBOM (DWord = 1);
# скрипт его ВЫСТАВЛЯЕТ, если он не выставлен (одноразово, ДО старта Excel), и
# сообщает об этом. Отключить это поведение: -NoSetViolationModel (тогда при
# отсутствии флага скрипт падает с инструкцией).
#
# ВАЖНО ПРО КОДИРОВКУ: файл сохранён как UTF-8 БЕЗ BOM (как остальные .ps1 в
# репозитории). Windows PowerShell 5.1 читает такой файл в ANSI, поэтому весь
# ИСПОЛНЯЕМЫЙ текст здесь ASCII, а кириллица — только в комментариях.
# Исходники .bas тоже UTF-8 (кириллица в комментариях), но редактор VBA читает
# импортируемый .bas как ANSI (cp1251), поэтому перед импортом скрипт делает
# копии в cp1251 в vba/build/modules (иначе в редакторе виден мусор).
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Pipeline,
    [switch]$Clean,
    [switch]$NoSetViolationModel,
    [string]$Input,
    [string]$OutDir,
    [string]$Name = 'synthetic_sphere',
    [int]$TimeoutSec = 900
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$src = Join-Path $here 'src'
$build = Join-Path $here 'build'
$work = Join-Path $build 'modules'
$runLog = Join-Path $build 'run.log'

if ($Clean -and (Test-Path $build)) { Remove-Item -Recurse -Force $build }
foreach ($d in @($build, $work)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# --- Excel: есть ли установка (чтобы ошибка была понятной, а не от COM) ---
$excelPath = @("$env:ProgramFiles\Microsoft Office\root\Office16\EXCEL.EXE",
               "${env:ProgramFiles(x86)}\Microsoft Office\root\Office16\EXCEL.EXE",
               "$env:ProgramFiles\Microsoft Office\Office16\EXCEL.EXE",
               "${env:ProgramFiles(x86)}\Microsoft Office\Office16\EXCEL.EXE",
               "$env:ProgramFiles\Microsoft Office\root\Office15\EXCEL.EXE") |
             Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $excelPath) {
    throw 'EXCEL.EXE not found: the VBA port needs Microsoft Excel (Office 2016 or newer, x86 or x64).'
}
Write-Host "excel: $excelPath"

# --- модули: UTF-8 -> cp1251 (VBE читает .bas как ANSI) ---
$modules = @(Get-ChildItem (Join-Path $src '*.bas') -ErrorAction SilentlyContinue | Sort-Object Name)
if ($modules.Count -eq 0) { throw "no .bas modules in $src" }
$enc1251 = [System.Text.Encoding]::GetEncoding(1251)
foreach ($m in $modules) {
    $text = [System.IO.File]::ReadAllText($m.FullName, [System.Text.Encoding]::UTF8)
    [System.IO.File]::WriteAllText((Join-Path $work $m.Name), $text, $enc1251)
}
Write-Host ("modules: " + (($modules | ForEach-Object { $_.BaseName }) -join ', '))

# VBA держит стандартные модули в ОДНОМ пространстве имён: два Public-имени с
# одинаковым названием ломают компиляцию проекта, а Excel отдаёт только
# RPC_E_SERVERFAULT без текста. Поэтому дубли ловим до старта Excel.
$publics = @{}
foreach ($m in $modules) {
    $text = [System.IO.File]::ReadAllText($m.FullName, [System.Text.Encoding]::UTF8)
    foreach ($mm in [regex]::Matches($text, '(?m)^Public\s+(?:Function|Sub)\s+(\w+)')) {
        $pname = $mm.Groups[1].Value
        if ($publics.ContainsKey($pname)) {
            throw ("duplicate Public name '" + $pname + "' in " + $publics[$pname] + " and " +
                   $m.Name + ": VBA modules share one global namespace")
        }
        $publics[$pname] = $m.Name
    }
}
Write-Host ("public procedures: " + $publics.Count)

# Ещё одна ловушка VBA: массивы передаются только по ссылке, "ByVal x() As T"
# не компилируется (текст ошибки -- "Ожидается массив"), поэтому проверяем заранее.
foreach ($m in $modules) {
    $text = [System.IO.File]::ReadAllLines($m.FullName, [System.Text.Encoding]::UTF8)
    for ($i = 0; $i -lt $text.Count; $i++) {
        if ($text[$i].TrimStart().StartsWith("'")) { continue }
        if ($text[$i] -match 'ByVal\s+\w+\s*\(\s*\)') {
            throw ($m.Name + ':' + ($i + 1) + ": 'ByVal' перед параметром-массивом не компилируется: " + $text[$i].Trim())
        }
    }
}

# --- версия Office (ветка реестра) и флаг доверия к объектной модели ---
$officeVer = $null
foreach ($v in @('16.0', '15.0', '14.0')) {
    if (Test-Path "HKCU:\Software\Microsoft\Office\$v\Excel") { $officeVer = $v; break }
}
if (-not $officeVer) { $officeVer = '16.0' }
$secKey = "HKCU:\Software\Microsoft\Office\$officeVer\Excel\Security"
$vbom = $null
if (Test-Path $secKey) { $vbom = (Get-ItemProperty -Path $secKey -ErrorAction SilentlyContinue).AccessVBOM }
if ($vbom -ne 1) {
    if ($NoSetViolationModel) {
        throw ("VBA project object model is not accessible. Enable it once (Excel > Options > " +
               "Trust Center > Trust Center Settings > Macro Settings > 'Trust access to the VBA " +
               "project object model'), or drop -NoSetViolationModel so that the script sets " +
               "HKCU:\Software\Microsoft\Office\$officeVer\Excel\Security\AccessVBOM = 1 itself.")
    }
    if (-not (Test-Path $secKey)) { New-Item -Path $secKey -Force | Out-Null }
    Set-ItemProperty -Path $secKey -Name AccessVBOM -Value 1 -Type DWord
    Write-Host "note: AccessVBOM was off; set HKCU:\Software\Microsoft\Office\$officeVer\Excel\Security\AccessVBOM = 1"
}

# --- точка входа и аргументы ---
if ($Vectors) {
    $entry = 'PappaConformance.pappa_conformance_run'
    $entryArgs = @((Join-Path $repo 'spec\conformance\vectors'))
} elseif ($Test) {
    $entry = 'PappaSelftest.pappa_selftest_run'
    $entryArgs = @((Join-Path $repo 'spec\conformance\vectors'))
} elseif ($Pipeline) {
    if (-not $Input) { $Input = Join-Path $repo 'python\synthetic_data.csv' }
    # Папка порта как у остальных портов: samples/synthetic_sphere_vba.
    # -Name -- это имя образца ВНУТРИ sample.json (оно сверяется с референсом),
    # поэтому в путь оно не подставляется.
    if (-not $OutDir) { $OutDir = Join-Path $repo 'samples\synthetic_sphere_vba' }
    $entry = 'PappaPipeline.pappa_pipeline_run'
    $entryArgs = @($Input, $OutDir, $Name)
} else {
    $entry = 'PappaMain.Smoke'
    $entryArgs = @()
}
Write-Host "entry: $entry"

# Прогон идёт в отдельном процессе PowerShell (Start-Job) с таймаутом: если Excel
# зависнет на модальном диалоге (ошибка VBA, компиляция модуля), COM-вызов из
# основного процесса висел бы бесконечно, а ворота должны падать, а не ждать.
$trace = Join-Path $build 'trace.log'
Remove-Item $trace -ErrorAction SilentlyContinue
$env:PAPPA_VBA_TRACE = $trace

$runner = {
    param($moduleList, $entryName, $argCount, $arg1, $arg2, $arg3)
    $ErrorActionPreference = 'Stop'
    $excel = $null
    $book = $null
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $excel.ScreenUpdating = $false
        $excel.EnableEvents = $false
        $excel.AskToUpdateLinks = $false
        # msoAutomationSecurityLow: макросы, добавленные программно, не блокируются.
        $excel.AutomationSecurity = 1
        # Interactive = False: ошибка VBA приходит исключением в вызывающий код,
        # а не модальным окном (иначе прогон зависает).
        $excel.Interactive = $false
        Write-Host "excel version: $($excel.Version)"
        $book = $excel.Workbooks.Add()
        foreach ($m in ($moduleList -split "`n")) {
            if ($m.Trim().Length -gt 0) { $null = $book.VBProject.VBComponents.Import($m) }
        }
        switch ($argCount) {
            0 { $report = $excel.Run($entryName) }
            1 { $report = $excel.Run($entryName, $arg1) }
            3 { $report = $excel.Run($entryName, $arg1, $arg2, $arg3) }
            default { throw "unsupported entry argument count: $argCount" }
        }
        return "$report"
    } finally {
        if ($book) { try { $book.Close($false) } catch { } }
        if ($excel) {
            try { $excel.Quit() } catch { }
            try { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) } catch { }
            [GC]::Collect()
            [GC]::WaitForPendingFinalizers()
        }
    }
}

$moduleList = (@($modules | ForEach-Object { Join-Path $work $_.Name }) -join "`n")
$a1 = ''
$a2 = ''
$a3 = ''
if ($entryArgs.Count -gt 0) { $a1 = [string]$entryArgs[0] }
if ($entryArgs.Count -gt 1) { $a2 = [string]$entryArgs[1] }
if ($entryArgs.Count -gt 2) { $a3 = [string]$entryArgs[2] }
$job = Start-Job -ScriptBlock $runner -ArgumentList $moduleList, $entry, $entryArgs.Count, $a1, $a2, $a3
$finished = Wait-Job $job -Timeout $TimeoutSec
if (-not $finished) {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Get-Process EXCEL -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "VBA run TIMED OUT after $TimeoutSec s (Excel killed)"
    if (Test-Path $trace) { Write-Host '--- trace (tail)'; Get-Content $trace -Tail 25 | Write-Host }
    exit 1
}

$out = Receive-Job $job
$jobError = $job.ChildJobs[0].Error
Remove-Job $job -Force

$report = ($out | Out-String).Trim()
if ($jobError -and $jobError.Count -gt 0) {
    Write-Host "VBA FAILED: $($jobError[0].ToString())"
    if (Test-Path $trace) { Write-Host '--- trace (tail)'; Get-Content $trace -Tail 25 | Write-Host }
    exit 1
}
if ($report.Length -gt 0) { Write-Host $report }
Set-Content -Path $runLog -Value $report -Encoding UTF8

# Точки входа заканчивают отчёт строкой "RESULT: OK" или "RESULT: FAIL n": так
# отчёт не теряется при ошибке (COM показал бы только текст исключения), а код
# возврата всё равно отражает результат проверки.
if ($report -match 'RESULT:\s*FAIL') {
    Write-Host 'VBA checks reported failures'
    exit 1
}

if ($Pipeline) {
    Write-Host 'compare: python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_vba'
    Write-Host 'schema:  python spec/check_schema.py samples/synthetic_sphere_vba'
}
exit 0
