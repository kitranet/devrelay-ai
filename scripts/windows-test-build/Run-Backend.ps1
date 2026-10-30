$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Install-DevRelayTestBuild.ps1 first.' }
Set-Location $repoRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
