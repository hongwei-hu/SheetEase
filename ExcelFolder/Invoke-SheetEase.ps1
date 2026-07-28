[CmdletBinding()]
param(
    [ValidateSet('Check', 'Export')]
    [string]$Mode = 'Check',
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'sheet_config.json'),
    [string]$ReportPath = (Join-Path $PSScriptRoot '.sheetease\agent-export-report.json'),
    [string]$ToolRoot = (Split-Path $PSScriptRoot -Parent),
    [switch]$UseExecutable,
    [switch]$AllowCleanup,
    [switch]$NoDiff
)

$ErrorActionPreference = 'Stop'
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$ReportPath = [System.IO.Path]::GetFullPath($ReportPath)
$ToolRoot = [System.IO.Path]::GetFullPath($ToolRoot)
$runStartedAt = [System.DateTimeOffset]::UtcNow

$exportArguments = @(
    '--headless'
    '--config', $ConfigPath
    '--report', $ReportPath
)
if ($Mode -eq 'Check') {
    $exportArguments += '--dry-run'
}
if (-not $AllowCleanup) {
    $exportArguments += '--no-cleanup'
}
if ($NoDiff) {
    $exportArguments += '--no-diff'
}

if ($UseExecutable) {
    $executable = Join-Path $PSScriptRoot 'SheetEase.exe'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "未找到 SheetEase.exe: $executable"
    }
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $executable
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $exportArguments) {
        $startInfo.ArgumentList.Add($argument)
    }
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.WaitForExit()
    $exitCode = $process.ExitCode
}
else {
    if (-not (Test-Path -LiteralPath (Join-Path $ToolRoot 'ExcelExportTool') -PathType Container)) {
        throw "未找到 Excel2JsonTool 源码目录: $ToolRoot"
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    $python = Get-Command python -ErrorAction SilentlyContinue
    Push-Location $ToolRoot
    try {
        if ($pyLauncher) {
            & $pyLauncher.Source -3 -m ExcelExportTool.export_all @exportArguments
        }
        elseif ($python) {
            & $python.Source -m ExcelExportTool.export_all @exportArguments
        }
        else {
            throw '未找到 py 或 python 命令。'
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) {
    throw "导出进程未生成报告: $ReportPath"
}

$report = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
$reportedFinishedAt = [System.DateTimeOffset]::Parse($report.finished_at)
if ($reportedFinishedAt -lt $runStartedAt.AddSeconds(-1)) {
    throw "导出报告不是本次运行生成的，拒绝使用旧报告: $ReportPath"
}
if ([int]$report.exit_code -ne [int]$exitCode) {
    throw "进程退出码与报告不一致: process=$exitCode, report=$($report.exit_code)"
}
Write-Output "SHEETEASE_STATUS=$($report.status)"
Write-Output "SHEETEASE_EXIT_CODE=$exitCode"
Write-Output "SHEETEASE_REPORT=$ReportPath"
exit $exitCode
