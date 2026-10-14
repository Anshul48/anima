<#
.SYNOPSIS
    Automation Script for STC (Spec-To-Code) on Windows.

.EXAMPLE
    .\run.ps1 -Install
    .\run.ps1 -Test
    .\run.ps1 -Lint
    .\run.ps1 -Format
    .\run.ps1 -Typecheck
    .\run.ps1 -All
    .\run.ps1 -Clean
#>

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Sync,
    [switch]$Lint,
    [switch]$Format,
    [switch]$Typecheck,
    [switch]$Test,
    [switch]$Coverage,
    [switch]$Mutmut,
    [switch]$All,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Header([string]$Title) {
    Write-Host "`n=== $Title ===" -ForegroundColor Cyan
}

if ($Install) {
    Show-Header "Installing Dependencies with uv"
    uv sync --all-groups
}

if ($Sync) {
    Show-Header "Syncing Frozen Dependencies"
    uv sync --frozen --all-groups
}

if ($Lint) {
    Show-Header "Running Ruff Linter"
    uv run ruff check src tests
}

if ($Format) {
    Show-Header "Formatting Code with Ruff"
    uv run ruff check --fix src tests
    uv run ruff format src tests
}

if ($Typecheck) {
    Show-Header "Running Mypy Strict Type Check"
    uv run mypy src tests
}

if ($Test) {
    Show-Header "Running Automated Pytest Suite"
    uv run pytest -v
}

if ($Coverage) {
    Show-Header "Running Pytest with Coverage"
    uv run pytest --cov=stc --cov-report=term-missing --cov-report=html
}

if ($Mutmut) {
    Show-Header "Running Mutation Robustness Testing"
    uv run mutmut run
}

if ($Clean) {
    Show-Header "Cleaning Caches and Ephemeral Worktrees"
    Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Force | Remove-Item -Recurse -Force
    Get-ChildItem -Path . -Filter "*.pyc" -Recurse -Force | Remove-Item -Force
    if (Test-Path ".pytest_cache") { Remove-Item -Recurse -Force ".pytest_cache" }
    if (Test-Path ".mypy_cache") { Remove-Item -Recurse -Force ".mypy_cache" }
    if (Test-Path ".ruff_cache") { Remove-Item -Recurse -Force ".ruff_cache" }
    if (Test-Path "htmlcov") { Remove-Item -Recurse -Force "htmlcov" }
    if (Test-Path ".coverage") { Remove-Item -Force ".coverage" }
    Write-Host "Cleanup completed successfully." -ForegroundColor Green
}

if ($All) {
    Show-Header "Executing Zero-Defect Quality Gates"
    uv run ruff check src tests
    uv run ruff format --check src tests
    uv run mypy src tests
    uv run pytest -v
    Write-Host "`n[+] All Quality Gates Passed Successfully!" -ForegroundColor Green
}
