$ErrorActionPreference = "Stop"

# 1. Setup controlled temp directory to avoid OneDrive sync issues
$TestTemp = "$env:LOCALAPPDATA\Temp\reflex_s3_tests"
if (Test-Path $TestTemp) {
    # Attempt cleanup but ignore ACL/locked file noise
    Remove-Item -Path "$TestTemp\*" -Recurse -Force -ErrorAction SilentlyContinue
} else {
    New-Item -Path $TestTemp -ItemType Directory -Force | Out-Null
}

$env:TMPDIR = $TestTemp
$env:TEMP = $TestTemp
$env:TMP = $TestTemp
$env:ENTORHINAL_ENABLED = "0"

Write-Host "Temp directory set to: $env:TMPDIR"
Write-Host "Running full suite (Entorhinal disabled)..."

# 2. Run full suite
$FullSuiteResult = "PASS"
uv run pytest -v > "full_suite_run.log"
if ($LASTEXITCODE -ne 0) {
    $FullSuiteResult = "FAIL"
}

# 3. Repeat sensitive tests for determinism (run 3 times)
Write-Host "Running sensitive tests 3 times for determinism..."
$TargetTests = "tests/test_mock_native_adapters.py tests/test_entorhinal_bridge.py tests/test_circuit_breaker.py"
$DeterminismResult = "PASS"

for ($i = 1; $i -le 3; $i++) {
    Write-Host " Iteration $i..."
    uv run pytest $TargetTests.Split(" ") -v >> "sensitive_tests_run.log"
    if ($LASTEXITCODE -ne 0) {
        $DeterminismResult = "FAIL"
    }
}

# 4. Generate Template C Manifest
$Timestamp = (Get-Date).ToString("o")
$Manifest = @"
{
  "identity": {
    "run_id": "S3-Reflex-Standalone",
    "evidence_class": "Integration and Unit Regression",
    "gate": "G1R Input",
    "timestamp": "$Timestamp"
  },
  "environment": {
    "os": "Windows",
    "python": "3.12",
    "temp_path_strategy": "Controlled non-OneDrive directory at $TestTemp",
    "entorhinal_installed": false
  },
  "execution": {
    "commands": ["uv run pytest", "uv run pytest <sensitive_tests> x3"],
    "process_topology": "In-process tests, no network"
  },
  "outputs": {
    "full_suite_log": "full_suite_run.log",
    "sensitive_tests_log": "sensitive_tests_run.log"
  },
  "verdict": {
    "full_suite": "$FullSuiteResult",
    "determinism": "$DeterminismResult",
    "overall": "$(if ($FullSuiteResult -eq 'PASS' -and $DeterminismResult -eq 'PASS') { 'PASS' } else { 'FAIL' })"
  }
}
"@

$Manifest | Out-File -FilePath "S3_MANIFEST.json" -Encoding UTF8
Write-Host "Manifest saved to S3_MANIFEST.json"
