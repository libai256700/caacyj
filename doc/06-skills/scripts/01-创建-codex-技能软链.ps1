param(
    [string]$ProjectRoot = (Get-Location).Path,
    [switch]$Force
)

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$projectSkillsRoot = Join-Path $resolvedProjectRoot 'doc\06-skills'
$codexRoot = Join-Path $resolvedProjectRoot '.codex'
$codexSkillsRoot = Join-Path $codexRoot 'skills'

if (-not (Test-Path -LiteralPath $projectSkillsRoot)) {
    throw "未找到项目级 skills 根目录：$projectSkillsRoot"
}

$skillDirs = Get-ChildItem -LiteralPath $projectSkillsRoot -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md')
}

if (-not $skillDirs) {
    throw "在 $projectSkillsRoot 下没有找到直接包含 SKILL.md 的技能目录。"
}

New-Item -ItemType Directory -Path $codexRoot -Force | Out-Null
New-Item -ItemType Directory -Path $codexSkillsRoot -Force | Out-Null

foreach ($skillDir in $skillDirs) {
    $targetPath = Join-Path $codexSkillsRoot $skillDir.Name

    if (Test-Path -LiteralPath $targetPath) {
        $existingItem = Get-Item -LiteralPath $targetPath -Force
        $resolvedExisting = $null

        try {
            $resolvedExisting = (Resolve-Path -LiteralPath $targetPath).Path
        } catch {
            $resolvedExisting = $null
        }

        if ($resolvedExisting -eq $skillDir.FullName) {
            Write-Host "已存在同名正确链接：$targetPath"
            continue
        }

        if (-not $Force) {
            throw "目标已存在且不指向当前技能目录：$targetPath。请先人工确认，或带 -Force 重新执行。"
        }

        Remove-Item -LiteralPath $targetPath -Force -Recurse
    }

    try {
        New-Item -ItemType SymbolicLink -Path $targetPath -Target $skillDir.FullName | Out-Null
        Write-Host "已创建符号链接：$targetPath -> $($skillDir.FullName)"
    } catch {
        New-Item -ItemType Junction -Path $targetPath -Target $skillDir.FullName | Out-Null
        Write-Host "已创建目录联接：$targetPath -> $($skillDir.FullName)"
    }
}
