$ErrorActionPreference = 'Stop'

$taskDir = $PSScriptRoot
$runDir = 'D:\ProjPort\Work\feixingxueyuan\tmp\task008-direct-import-run'

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Export-MysqlSafeTsv {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $rows = Import-Csv -LiteralPath $SourcePath
    $safeRows = foreach ($row in $rows) {
        $ordered = [ordered]@{}
        foreach ($property in $row.PSObject.Properties) {
            $value = [string]$property.Value
            $ordered[$property.Name] = $value `
                -replace "\\", "\\\\" `
                -replace "`t", "\t" `
                -replace "`r`n|`n|`r", "\n"
        }
        [pscustomobject]$ordered
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $headers = @($safeRows[0].PSObject.Properties.Name)
    $lines.Add(($headers -join "`t"))
    foreach ($row in $safeRows) {
        $values = foreach ($header in $headers) {
            [string]$row.$header
        }
        $lines.Add(($values -join "`t"))
    }
    [System.IO.File]::WriteAllLines($TargetPath, $lines, [System.Text.UTF8Encoding]::new($false))
    return $safeRows.Count
}

$questionCount = Export-MysqlSafeTsv `
    -SourcePath (Join-Path $taskDir '20260513233500-question-import-staging-real.csv') `
    -TargetPath (Join-Path $runDir 'question-import-staging-real.tsv')

$optionCount = Export-MysqlSafeTsv `
    -SourcePath (Join-Path $taskDir '20260513233600-question-import-option-staging-real.csv') `
    -TargetPath (Join-Path $runDir 'question-import-option-staging-real.tsv')

Copy-Item -LiteralPath (Join-Path $taskDir '20260514014000-dml-question-direct-import-final-tables-fixed.sql') `
    -Destination (Join-Path $runDir 'direct-import-fixed.sql') `
    -Force

[pscustomobject]@{
    runtime_dir = $runDir
    question_runtime_rows = $questionCount
    option_runtime_rows = $optionCount
    question_runtime_file = Join-Path $runDir 'question-import-staging-real.tsv'
    option_runtime_file = Join-Path $runDir 'question-import-option-staging-real.tsv'
    sql_runtime_file = Join-Path $runDir 'direct-import-fixed.sql'
}
