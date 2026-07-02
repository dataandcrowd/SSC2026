# Run the behavioural-parameter sensitivity analysis for the SSC2026 model.
#
# Usage (PowerShell):
#   $env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"
#   .\run_sensitivity.ps1
#
# Requires NetLogo 6.x (tested with 6.4.0 headless). The gis, nw, csv and table
# extensions ship with NetLogo. The script runs from the netlogo\ folder so the
# model's relative "Data\..." paths resolve.

$ErrorActionPreference = "Stop"

# --- NETLOGO must point at the install dir, e.g. "C:\Program Files\NetLogo 6.4.0"
if (-not $env:NETLOGO) {
    throw 'Set NETLOGO to your NetLogo install dir, e.g. $env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"'
}

$HEADLESS = Join-Path $env:NETLOGO "netlogo-headless.bat"
if (-not (Test-Path $HEADLESS)) {
    throw "netlogo-headless.bat not found at $HEADLESS. Check the NETLOGO path."
}

$HERE        = $PSScriptRoot                       # sensitivity_experiment\
$NETLOGO_DIR = Split-Path $HERE -Parent            # the netlogo\ folder (model + Data live here)
$MODEL       = Join-Path $NETLOGO_DIR "akl_traffic.nlogo"
$XML         = Join-Path $HERE "sensitivity_experiment.xml"
$OUT         = Join-Path $NETLOGO_DIR "..\output\tables"

New-Item -ItemType Directory -Force -Path $OUT | Out-Null
$OUT = (Resolve-Path $OUT).Path

# thread count = number of logical processors
$THREADS = $env:NUMBER_OF_PROCESSORS
if (-not $THREADS) { $THREADS = 2 }

Push-Location $NETLOGO_DIR   # so Data\... resolves
try {
    foreach ($EXP in @("sensitivity-pay", "sensitivity-elfarol", "sensitivity-ql-alpha", "sensitivity-ql-epsilon")) {
        Write-Host ">>> running $EXP"
        $table = Join-Path $OUT "$EXP.csv"
        & $HEADLESS --model $MODEL `
            --setup-file $XML --experiment $EXP `
            --table $table --threads $THREADS
        if ($LASTEXITCODE -ne 0) { throw "$EXP failed with exit code $LASTEXITCODE" }
    }
}
finally {
    Pop-Location
}

Write-Host "Done. Tables in $OUT. Now run: python $HERE\aggregate_sensitivity.py"