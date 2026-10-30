$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$backendScript = Join-Path $PSScriptRoot 'Run-Backend.ps1'
$frontendScript = Join-Path $PSScriptRoot 'Run-Frontend.ps1'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$node = Get-Command node -ErrorAction Stop
$next = Join-Path $repoRoot 'frontend\node_modules\next\dist\bin\next'

if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $next)) {
    throw 'Run Install-DevRelayTestBuild.ps1 first.'
}
foreach ($port in @(8001, 3000)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { throw "Port $port is already in use. No process was stopped; close the existing service or choose another machine." }
}

$securePassword = Read-Host 'Choose a temporary local dashboard password (16+ characters)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($plainPassword.Length -lt 16) { throw 'Use a password with at least 16 characters and run this script again.' }

    $environmentNames = @(
        'AUTHORIZED_REPOSITORIES', 'INFERENCE_PROVIDER', 'NEBIUS_API_KEY',
        'NEBIUS_LIVE_INFERENCE_ENABLED', 'NEBIUS_TOTAL_INFERENCE_QUOTA',
        'NEBIUS_QUOTA_DB_PATH', 'INFERENCE_TELEMETRY_DB_PATH',
        'INFERENCE_TELEMETRY_RETENTION_DAYS', 'ENABLE_LOCAL_REVIEWS',
        'ENABLE_ISOLATED_RUNTIME_VALIDATION', 'BACKEND_API_URL',
        'DEMO_AUTH_USERNAME', 'DEMO_AUTH_PASSWORD', 'DEMO_AUTH_ORIGIN',
        'NEXT_PUBLIC_REPOSITORY_IDS', 'NEXT_PUBLIC_LOCAL_REVIEWER_ID',
        'NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID', 'NEXT_TELEMETRY_DISABLED'
    )
    $previousEnvironment = @{}
    foreach ($name in $environmentNames) {
        $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        $previousEnvironment[$name] = if ($item) { $item.Value } else { $null }
    }

    try {
        $fixturePath = (Join-Path $repoRoot 'tests\fixtures\continuity_pipeline').Replace('\', '/')
        $env:AUTHORIZED_REPOSITORIES = (@{ 'continuity-pipeline-fixture' = $fixturePath } | ConvertTo-Json -Compress)
        $env:INFERENCE_PROVIDER = 'mock'
        $env:NEBIUS_API_KEY = ''
        $env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
        $env:NEBIUS_TOTAL_INFERENCE_QUOTA = '0'
        $env:NEBIUS_QUOTA_DB_PATH = Join-Path $repoRoot '.devrelay-state\nebius-quota.sqlite3'
        $env:INFERENCE_TELEMETRY_DB_PATH = Join-Path $repoRoot '.devrelay-state\inference-attempts.sqlite3'
        $env:INFERENCE_TELEMETRY_RETENTION_DAYS = '90'
        $env:ENABLE_LOCAL_REVIEWS = 'false'
        $env:ENABLE_ISOLATED_RUNTIME_VALIDATION = 'false'
        $env:BACKEND_API_URL = 'http://127.0.0.1:8001'
        $env:DEMO_AUTH_USERNAME = 'local-demo'
        $env:DEMO_AUTH_PASSWORD = $plainPassword
        $env:DEMO_AUTH_ORIGIN = 'http://127.0.0.1:3000'
        $env:NEXT_PUBLIC_REPOSITORY_IDS = 'continuity-pipeline-fixture'
        $env:NEXT_PUBLIC_LOCAL_REVIEWER_ID = 'demo_reviewer'
        $env:NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID = 'local_authorizer'
        $env:NEXT_TELEMETRY_DISABLED = '1'

        $powerShell = (Get-Process -Id $PID).Path
        $argumentLineBackend = '-NoExit -ExecutionPolicy Bypass -File "' + $backendScript + '"'
        $argumentLineFrontend = '-NoExit -ExecutionPolicy Bypass -File "' + $frontendScript + '"'
        Start-Process -FilePath $powerShell -ArgumentList $argumentLineBackend -WorkingDirectory $repoRoot | Out-Null
        Start-Process -FilePath $powerShell -ArgumentList $argumentLineFrontend -WorkingDirectory $repoRoot | Out-Null
    }
    finally {
        foreach ($name in $environmentNames) {
            $value = $previousEnvironment[$name]
            if ($null -eq $value) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
            else { Set-Item -LiteralPath "Env:$name" -Value $value }
        }
    }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $securePassword.Dispose()
    Remove-Variable plainPassword -ErrorAction SilentlyContinue
}

function Wait-ForLocalPort([int]$port) {
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $connect = $client.BeginConnect('127.0.0.1', $port, $null, $null)
            if ($connect.AsyncWaitHandle.WaitOne(500)) {
                $client.EndConnect($connect)
                return
            }
        }
        catch { }
        finally { $client.Dispose() }
        Start-Sleep -Milliseconds 500
    }
    throw "Local service on port $port did not start within 60 seconds. Check its server window; no additional process was started."
}

Wait-ForLocalPort 8001
Wait-ForLocalPort 3000
Start-Process 'http://127.0.0.1:3000'
Write-Host 'Two local server windows were opened. Sign in with username local-demo and the password you just chose.'
Write-Host 'Both services bind only to 127.0.0.1. Inference is deterministic mock; no Nebius request was made.'
Write-Host 'To stop: press Ctrl+C in each server window.'
