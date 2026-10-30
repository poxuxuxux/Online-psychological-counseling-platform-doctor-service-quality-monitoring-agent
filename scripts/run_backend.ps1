# 环节：开发运维辅助层；用途：协助本地服务启动或受控样本准备。
param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [string]$PythonPath = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project

# Prefer a working project environment, then the shorter workspace environment.
# A partially installed .venv must not hide a working .venv-quality.
$candidates = if ($PythonPath) {
    @($PythonPath)
} else {
    @(
        (Join-Path $project '.venv\Scripts\python.exe'),
        (Join-Path (Split-Path -Parent $project) '.venv-quality\Scripts\python.exe'),
        (Join-Path $project 'venv\Scripts\python.exe')
    )
}
$selectedPython = $null
foreach ($candidate in $candidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    try {
        & $candidate -c "import sys; assert sys.version_info >= (3, 11); import uvicorn, dotenv; from app.main import app" *> $null
        if ($LASTEXITCODE -eq 0) {
            $selectedPython = (Resolve-Path -LiteralPath $candidate).Path
            break
        }
    } catch {
        # Try the next environment without printing import failures from stale installs.
    }
}
if (-not $selectedPython) {
    throw 'No working Python 3.11+ environment found. Install project dependencies with: python -m pip install -e ".[dev]"; or pass -PythonPath <venv-python.exe>.'
}

if (-not (Test-Path -LiteralPath '.env' -PathType Leaf)) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env from .env.example. Add your model API key before evaluating.' -ForegroundColor Yellow
}
if (-not (Test-Path -LiteralPath 'app\web\index.html' -PathType Leaf)) {
    throw 'Frontend build missing. Run: pnpm --dir frontend build:backend'
}

Write-Host "Python: $selectedPython"
Write-Host "Project: $project"
$entryHtml = [System.IO.File]::ReadAllText((Join-Path $project 'app\web\index.html'))
$entryMatch = [regex]::Match($entryHtml, '/assets/index-[^" ]+\.js')
Write-Host "Frontend entry: $($entryMatch.Value)"
Write-Host 'Expected page label: 后台任务版 · 2026-10-29'
& $selectedPython -c "from dotenv import load_dotenv; load_dotenv('.env'); from app.config import Settings; from app.infrastructure.model import JsonModelGateway; s=Settings.from_env(); print('Protocol:', s.team_protocol); print('Model configured:', JsonModelGateway().configured)"
if ($LASTEXITCODE -ne 0) { throw 'Configuration check failed. Check .env and retry.' }
if ($CheckOnly) {
    Write-Host 'Startup checks passed. No server was started.'
    return
}

Write-Host "Website: http://127.0.0.1:$Port"
Write-Host "API docs: http://127.0.0.1:$Port/docs"
Write-Host 'Backend also serves the built website; no separate frontend server is needed.'
Write-Host 'Keep this terminal open. Press Ctrl+C to stop. Restart after changing .env.'
& $selectedPython -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE. See the error above." }
