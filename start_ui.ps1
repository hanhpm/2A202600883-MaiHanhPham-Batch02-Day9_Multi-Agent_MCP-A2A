param(
    [string]$PythonPath = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not $PythonPath) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $PythonPath = $VenvPython
    } else {
        $PythonPath = "python"
    }
}

Write-Host "Starting Day 9 UI on http://localhost:$Port"
Write-Host "Start agents in another terminal with: .\start_all.ps1"

$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    $ProcessId = ($Existing | Select-Object -First 1).OwningProcess
    Write-Host "UI is already running on http://localhost:$Port (PID: $ProcessId)"
    Write-Host "Open http://localhost:$Port in your browser, or use another port:"
    Write-Host "  .\start_ui.ps1 -Port 8001"
    Write-Host "If you use another UI port, start agents with:"
    Write-Host "  .\start_all.ps1 -TraceEventUrl http://localhost:8001/api/trace"
    exit 0
}

& $PythonPath -m uvicorn ui_app:app --host 0.0.0.0 --port $Port
