// 环节：开发运维辅助层；用途：协助本地服务启动或受控样本准备。
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port $Port
