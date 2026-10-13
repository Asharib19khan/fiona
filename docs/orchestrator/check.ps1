# Orchestrator sweep check. Run: powershell -File docs/orchestrator/check.ps1
# Prints only problems and test results; exit code 1 if any rule is broken.
$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..\..')
$problems = @()

function Find($pattern, $path, $include) {
    if (-not (Test-Path $path)) { return @() }
    Get-ChildItem $path -Recurse -File -Include $include -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\(node_modules|\.venv|__pycache__|\.next|\.turbo)\\' } |
        Select-String -Pattern $pattern -ErrorAction SilentlyContinue
}

# Rule 5.1: the engine never calls Claude.
foreach ($m in Find '(import anthropic|from anthropic|api\.anthropic\.com|claude-(opus|sonnet|haiku))' 'services\engine' '*.py') {
    $problems += "ENGINE CALLS CLAUDE: $($m.Path):$($m.LineNumber)"
}
# Rule 5.2: no float money at module boundaries (heuristic: float-typed *_minor fields).
# Only model/class fields (a declaration at the start of a line), not function parameters that get rounded.
foreach ($m in Find '^\s+\w*_minor\s*:\s*(float|Optional\[float\]|float\s*\|)' 'services' '*.py') {
    $problems += "FLOAT MONEY FIELD: $($m.Path):$($m.LineNumber)"
}
foreach ($m in Find '_minor\??\s*:\s*number\s*;?\s*//\s*float' 'packages' '*.ts') {
    $problems += "FLOAT MONEY FIELD: $($m.Path):$($m.LineNumber)"
}
# Secrets must never be committed.
$tracked = git ls-files 2>$null
foreach ($f in $tracked) { if ($f -match '(^|/)\.env(\.|$)' -and $f -notmatch '\.env\.example$') { $problems += "SECRET FILE TRACKED: $f" } }
foreach ($m in (git grep -n -E 'sk-ant-[A-Za-z0-9_-]{20,}' 2>$null)) { $problems += "API KEY IN REPO: $m" }
# Kaggle datasets must not be committed (licensing).
foreach ($f in $tracked) { if ($f -match '(?i)(m5|favorita|sales_train_validation|store-sales)') { $problems += "KAGGLE DATA TRACKED: $f" } }

if ($problems.Count) { "RULE PROBLEMS:"; $problems | ForEach-Object { "  $_" } } else { "rules: clean" }

# Tests, where the scaffolding exists.
if (Test-Path 'services\engine\pyproject.toml') {
    "--- engine tests"
    uv run --directory services/engine pytest -q -x --no-header -p no:cacheprovider 2>&1 | Select-Object -Last 8
}
if ((Test-Path 'package.json') -and (Test-Path 'node_modules')) {
    "--- workspace tests"
    pnpm -s test 2>&1 | Select-Object -Last 12
}
if ($problems.Count) { exit 1 }
