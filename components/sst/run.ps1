<#
.SYNOPSIS
    Cross-platform developer automation script for Project SST.
.DESCRIPTION
    Provides commands for installing dependencies, linting, formatting,
    type checking, test execution, and quality gates using Astral UV.
.EXAMPLE
    .\run.ps1 -Install
    .\run.ps1 -Test
    .\run.ps1 -Gate
#>

param(
    [switch]$Install,
    [switch]$Lint,
    [switch]$Format,
    [switch]$FormatCheck,
    [switch]$Typecheck,
    [switch]$Test,
    [switch]$Coverage,
    [switch]$Gate,
    [switch]$Clean,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "Project SST Developer Automation Runner" -ForegroundColor Cyan
    Write-Host "Usage: .\run.ps1 [Option]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Install      Sync dependencies with Astral UV"
    Write-Host "  -Lint         Run ruff check"
    Write-Host "  -Format       Format code with ruff format"
    Write-Host "  -FormatCheck  Check formatting with ruff format --check"
    Write-Host "  -Typecheck    Run strict mypy type analysis"
    Write-Host "  -Test         Run pytest suite"
    Write-Host "  -Coverage     Run pytest with coverage analysis"
    Write-Host "  -Gate         Run complete CI quality gates"
    Write-Host "  -Clean        Remove caches and temp artifacts"
    Write-Host "  -Help         Display this help message"
}

if ($Help -or ($PSBoundParameters.Count -eq 0)) {
    Show-Help
    exit 0
}

if ($Install) {
    Write-Host "==> Syncing dependencies with UV..." -ForegroundColor Green
    uv sync --all-extras
}

if ($Lint) {
    Write-Host "==> Running ruff lint check..." -ForegroundColor Green
    uv run ruff check .
}

if ($Format) {
    Write-Host "==> Formatting code with ruff..." -ForegroundColor Green
    uv run ruff format .
}

if ($FormatCheck) {
    Write-Host "==> Checking code format..." -ForegroundColor Green
    uv run ruff format --check .
}

if ($Typecheck) {
    Write-Host "==> Running mypy strict type analysis..." -ForegroundColor Green
    uv run mypy --strict src/ tests/
}

if ($Test) {
    Write-Host "==> Running pytest test suite..." -ForegroundColor Green
    uv run pytest -v
}

if ($Coverage) {
    Write-Host "==> Running pytest with coverage..." -ForegroundColor Green
    uv run pytest -v --cov=sst
}

if ($Gate) {
    Write-Host "==> Executing all SST quality gates..." -ForegroundColor Cyan
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy --strict src/ tests/
    uv run pytest -v
    Write-Host "==> All SST quality gates PASSED successfully!" -ForegroundColor Green
}

if ($Clean) {
    Write-Host "==> Cleaning caches and temp artifacts..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .pytest_cache, .mypy_cache, .ruff_cache, htmlcov, dist, build
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -File -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
}
