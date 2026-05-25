# webnovel-director Coworker Automation
# Auto-pick GitHub Issues -> Claude Code fix -> PR
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$RepoDir = "C:\Users\ThinkPad\webnovel-director"
Set-Location $RepoDir
$env:GH_PAGER = ""

git checkout master 2>&1 | Out-Null
git pull origin master 2>&1 | Out-Null

# Get first open issue number (simple output, no JSON parsing)
$issueNum = gh issue list --limit 1 --state open --json number --jq ".[0].number" 2>$null
if (-not $issueNum) {
    Write-Host "[coworker] No open issues."
    exit 0
}

# Get issue details individually
$title = gh issue view $issueNum --json title --jq ".title" 2>$null
$branch = "fix/issue-$issueNum"

Write-Host "[coworker] Issue #${issueNum} - ${title}"

# Check existing PR
$prCheck = gh pr list --head $branch --state open --json number --jq ".[0].number" 2>$null
if ($prCheck) {
    Write-Host "  -> Skipped: PR already exists"
    exit 0
}

# Check existing branch
$branchCheck = git ls-remote --heads origin $branch 2>$null
if ($branchCheck) {
    Write-Host "  -> Skipped: branch already exists on remote"
    exit 0
}

if ($DryRun) {
    Write-Host "  [DRY RUN] Would launch Claude Code to fix and create PR"
    exit 0
}

# Save issue body to temp file to avoid encoding issues
$bodyFile = "$env:TEMP\coworker-body-${issueNum}.txt"
gh issue view $issueNum --json body --jq ".body" 2>$null | Out-File -FilePath $bodyFile -Encoding UTF8
$bodyContent = Get-Content $bodyFile -Raw -Encoding UTF8

# Build prompt for Claude Code
$prompt = @"
You are a coding coworker on the webnovel-director project.
Fix this GitHub issue, then open a PR.

ISSUE NUMBER: ${issueNum}
ISSUE TITLE: ${title}
ISSUE BODY: ${bodyContent}

STEPS:
1. Read relevant files to understand the codebase
2. Create branch: git checkout -b ${branch}
3. Make the minimal changes needed to fix this issue
4. Run smoke test if available: python scripts/test_smoke.py
5. Commit: git add -A && git commit -m "fix: #${issueNum} - ${title}"
6. Push: git push origin ${branch}
7. Create PR: gh pr create --title "fix: #${issueNum} - ${title}" --body "Closes #${issueNum}" --base master

RULES:
- Only change files related to this issue
- Do NOT refactor unrelated code
- Keep changes minimal and focused
"@

$promptFile = "$env:TEMP\coworker-prompt-${issueNum}.txt"
[System.IO.File]::WriteAllText($promptFile, $prompt, [System.Text.Encoding]::UTF8)
Write-Host "  -> Launching Claude Code to fix #${issueNum}..."

claude -p "$(Get-Content $promptFile -Raw -Encoding UTF8)" --add-dir $RepoDir 2>&1

git checkout master 2>&1 | Out-Null
Write-Host "[coworker] Done."
