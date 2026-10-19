$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (Test-Path ".venv\Scripts\python.exe") {
    $Python = ".venv\Scripts\python.exe"
} elseif (Test-Path ".venv39\Scripts\python.exe") {
    $Python = ".venv39\Scripts\python.exe"
} else {
    $Python = "python"
}

$env:PYTHONPATH = "$Root\src"
& $Python -m bluedeck @args
