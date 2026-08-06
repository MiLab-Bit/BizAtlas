# BizAtlas local helpers (project-embedded Python)
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".tools\python\python.exe"
$env:PYTHONPATH = "$(Join-Path $Root 'packages');$(Join-Path $Root 'apps')"

if (-not (Test-Path $Py)) {
  Write-Error "Missing $Py — extract Python into .tools first (see README)"
  exit 1
}

$cmd = if ($args.Count -gt 0) { $args[0] } else { "help" }
switch ($cmd) {
  "smoke" { & $Py (Join-Path $Root "scripts\smoke_analyze.py") }
  "smoke-upload" { & $Py (Join-Path $Root "scripts\smoke_upload_report.py") }
  "smoke-workflow" { & $Py (Join-Path $Root "scripts\smoke_workflow.py") }
  "test"  { & $Py -m pytest -q }
  "api"   {
    & $Py -m uvicorn api.app.main:app --app-dir (Join-Path $Root "apps") --host 127.0.0.1 --port 8000 --reload
  }
  default {
    Write-Host "Usage: .\scripts\dev.ps1 [smoke|smoke-upload|smoke-workflow|test|api]"
  }
}
