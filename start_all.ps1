param(
    [string]$PythonPath = "",
    [string]$TraceEventUrl = "http://localhost:8000/api/trace"
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

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:TRACE_EVENT_URL = $TraceEventUrl

$Processes = New-Object System.Collections.Generic.List[object]

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Start-AgentService {
    param(
        [string]$Name,
        [string]$Module,
        [int]$Port,
        [int]$DelaySeconds = 2
    )

    $OutLogFile = Join-Path $LogDir "$Name.out.log"
    $ErrLogFile = Join-Path $LogDir "$Name.err.log"

    if (Test-PortListening -Port $Port) {
        Write-Host "$Name already appears to be running on port $Port. Skipping start."
        return
    }

    Write-Host "Starting $Name on port $Port..."
    $Process = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @("-m", $Module) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $OutLogFile `
        -RedirectStandardError $ErrLogFile `
        -WindowStyle Hidden `
        -PassThru
    $Processes.Add([pscustomobject]@{
        Name = $Name
        Port = $Port
        Process = $Process
    })
    Start-Sleep -Seconds $DelaySeconds
}

try {
    Start-AgentService -Name "registry" -Module "registry" -Port 10000 -DelaySeconds 2
    Start-AgentService -Name "tax_agent" -Module "tax_agent" -Port 10102 -DelaySeconds 1
    Start-AgentService -Name "compliance_agent" -Module "compliance_agent" -Port 10103 -DelaySeconds 3
    Start-AgentService -Name "law_agent" -Module "law_agent" -Port 10101 -DelaySeconds 3
    Start-AgentService -Name "customer_agent" -Module "customer_agent" -Port 10100 -DelaySeconds 1

    Write-Host ""
    Write-Host "All services started:"
    Write-Host "  Registry:         http://localhost:10000"
    Write-Host "  Customer Agent:   http://localhost:10100"
    Write-Host "  Law Agent:        http://localhost:10101"
    Write-Host "  Tax Agent:        http://localhost:10102"
    Write-Host "  Compliance Agent: http://localhost:10103"
    Write-Host ""
    Write-Host "Logs are in: $LogDir"
    Write-Host "Trace events are sent to: $TraceEventUrl"
    Write-Host "Run a test query with:"
    Write-Host "  & `"$PythonPath`" test_client.py"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all services."

    while ($true) {
        Start-Sleep -Seconds 2
        foreach ($Record in @($Processes)) {
            $Process = $Record.Process
            if ($Process -and $Process.HasExited) {
                Write-Warning "$($Record.Name) on port $($Record.Port) exited with code $($Process.ExitCode). Check logs in $LogDir."
                [void]$Processes.Remove($Record)
            }
        }
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping services..."
    foreach ($Record in $Processes) {
        $Process = $Record.Process
        if ($Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
        }
    }
}
