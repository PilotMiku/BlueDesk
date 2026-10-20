$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (Test-Path ".venv\Scripts\python.exe") {
    $Python = ".venv\Scripts\python.exe"
} else {
    $Python = "python"
}

& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "BlueDesk requires Python 3.11 or newer; recreate .venv with a supported Python.")'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:PYTHONPATH = "$Root\src"
& $Python -m bluedesk @args
