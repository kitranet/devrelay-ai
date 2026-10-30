$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$frontendRoot = Join-Path $repoRoot 'frontend'
$next = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
if (-not (Test-Path -LiteralPath $next)) { throw 'Run Install-DevRelayTestBuild.ps1 first.' }
Set-Location $frontendRoot
& node $next start --hostname 127.0.0.1 --port 3000
