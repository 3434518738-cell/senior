param(
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual-environment Python was not found: $Python"
}

# 只清空当前 PowerShell 进程的代理变量，不修改用户或系统环境变量。
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:all_proxy = ""

& $Python -m pip install --index-url https://pypi.org/simple -r requirements-workflow.txt
if ($LASTEXITCODE -ne 0) {
    throw "LangGraph installation failed. Check network access or start the configured proxy."
}

& $Python -c "from langgraph.graph import StateGraph, START, END; import importlib.metadata as m; print('LangGraph OK', m.version('langgraph'))"
if ($LASTEXITCODE -ne 0) {
    throw "LangGraph installation completed but import verification failed."
}
