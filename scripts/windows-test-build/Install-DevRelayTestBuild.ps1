$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Get-Command python -ErrorAction Stop
$node = Get-Command node -ErrorAction Stop
$npm = Get-Command npm.cmd -ErrorAction Stop

$pythonVersionText = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersionText -lt [version]'3.12.0') {
    throw 'Install Python 3.12 or newer, then run this installer again.'
}

$nodeVersionText = (& $node.Source --version).Trim().TrimStart('v')
if ([version]$nodeVersionText -lt [version]'20.9.0') {
    throw 'Install Node.js 20.9 or newer, then run this installer again.'
}

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python.Source -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment setup failed.' }
}

& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

$frontendRoot = Join-Path $repoRoot 'frontend'
Push-Location $frontendRoot
try {
    & $npm.Source ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }

    $environmentNames = @(
        'AUTHORIZED_REPOSITORIES', 'INFERENCE_PROVIDER', 'NEBIUS_API_KEY',
        'NEBIUS_LIVE_INFERENCE_ENABLED', 'NEBIUS_TOTAL_INFERENCE_QUOTA',
        'NEBIUS_QUOTA_DB_PATH', 'INFERENCE_TELEMETRY_DB_PATH',
        'INFERENCE_TELEMETRY_RETENTION_DAYS', 'ENABLE_LOCAL_REVIEWS',
        'ENABLE_ISOLATED_RUNTIME_VALIDATION', 'BACKEND_API_URL',
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
        $authorized = @{ 'continuity-pipeline-fixture' = $fixturePath } | ConvertTo-Json -Compress
        $stateRoot = Join-Path $repoRoot '.devrelay-state'
        $env:AUTHORIZED_REPOSITORIES = $authorized
        $env:INFERENCE_PROVIDER = 'mock'
        $env:NEBIUS_API_KEY = ''
        $env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
        $env:NEBIUS_TOTAL_INFERENCE_QUOTA = '0'
        $env:NEBIUS_QUOTA_DB_PATH = Join-Path $stateRoot 'nebius-quota.sqlite3'
        $env:INFERENCE_TELEMETRY_DB_PATH = Join-Path $stateRoot 'inference-attempts.sqlite3'
        $env:INFERENCE_TELEMETRY_RETENTION_DAYS = '90'
        $env:ENABLE_LOCAL_REVIEWS = 'false'
        $env:ENABLE_ISOLATED_RUNTIME_VALIDATION = 'false'
        $env:BACKEND_API_URL = 'http://127.0.0.1:8001'
        $env:NEXT_PUBLIC_REPOSITORY_IDS = 'continuity-pipeline-fixture'
        $env:NEXT_PUBLIC_LOCAL_REVIEWER_ID = 'demo_reviewer'
        $env:NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID = 'local_authorizer'
        $env:NEXT_TELEMETRY_DISABLED = '1'

        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { throw 'The Next.js production build failed.' }
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
    Pop-Location
}

Write-Host 'Test build installed. No model request was made.'
Write-Host 'Next: run Start-DevRelayTestBuild.ps1 and use the two server windows it opens.'
