# webnovel-director Coworker Automation
# 自动领 GitHub Issue → Claude Code 修 → 提 PR
param(
    [string]$Label = "",           # 按标签过滤（空=不过滤）
    [int]$Limit = 1,               # 每次最多处理几个 Issue
    [switch]$DryRun                # 只看不执行
)

$ErrorActionPreference = "Stop"
$RepoDir = "C:\Users\ThinkPad\webnovel-director"
Set-Location $RepoDir

# 确保在 master 且干净
git checkout master 2>&1 | Out-Null
git pull origin master 2>&1 | Out-Null

# 获取 Issue 列表
$labelFilter = if ($Label) { "--label `"$Label`"" } else { "" }
$issuesJson = Invoke-Expression "gh issue list --limit $Limit --state open --json number,title,body,labels $labelFilter" | ConvertFrom-Json

if (-not $issuesJson -or $issuesJson.Count -eq 0) {
    Write-Host "[coworker] No open issues found." 
    exit 0
}

foreach ($issue in $issuesJson) {
    $num = $issue.number
    $title = $issue.title
    $body = $issue.body
    $branch = "fix/issue-$num"

    Write-Host "[coworker] Processing #$num: $title"

    # 跳过已有 PR 的
    $prCheck = gh pr list --head $branch --state open --json number 2>$null | ConvertFrom-Json
    if ($prCheck -and $prCheck.Count -gt 0) {
        Write-Host "  → Skipped: PR already exists for branch $branch"
        continue
    }

    # 跳过已有分支的（可能在处理中）
    $branchExists = git ls-remote --heads origin $branch 2>$null
    if ($branchExists) {
        Write-Host "  → Skipped: remote branch $branch already exists"
        continue
    }

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would create branch, fix with Claude Code, and open PR"
        continue
    }

    # 创建修复分支
    git checkout -b $branch 2>&1 | Out-Null

    # 构造 Claude Code coworker prompt
    $claudePrompt = @"
You are a coding coworker on the webnovel-director project. Fix this GitHub issue.

<issue>
Number: #$num
Title: $title
Body: $body
</issue>

<instructions>
1. Understand the issue and what needs to change
2. Read relevant files in the project to understand the current code
3. Make the necessary changes
4. Run any available tests (scripts/test_smoke.py) to verify
5. If tests pass: commit all changes with message "fix: #$num - $title"
6. Push to origin/$branch
7. Create a PR using: gh pr create --title "fix: #$num - $title" --body "Closes #$num`n`n$body" --base master

IMPORTANT: Do NOT modify files unrelated to this issue.
Do NOT refactor code that isn't broken.
Keep changes minimal and focused.
</instructions>
"@

    Write-Host "  → Spawning Claude Code..."
    
    # 临时写入 prompt 文件（避免 PowerShell 中文 JSON 编码问题）
    $promptFile = "$env:TEMP\claude-coworker-prompt.txt"
    [System.IO.File]::WriteAllText($promptFile, $claudePrompt, [System.Text.Encoding]::UTF8)
    
    $result = claude -p "$(Get-Content $promptFile -Raw -Encoding UTF8)" --add-dir $RepoDir 2>&1
    Write-Host $result

    # 回到 master 准备下一个
    git checkout master 2>&1 | Out-Null
}

Write-Host "[coworker] Done."
