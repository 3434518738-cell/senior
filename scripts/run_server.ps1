param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Project virtual environment not found: $python. Create .venv and install requirements.txt first."
    exit 1
}

Set-Location -LiteralPath $projectRoot
& $python -m uvicorn app.api:app --host $BindHost --port $Port
exit $LASTEXITCODE
