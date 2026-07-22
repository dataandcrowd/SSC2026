# Re-run the full sensitivity suite on the CALIBRATED model (scale-factor 160 +
# suburban destinations) on Windows. PowerShell equivalent of
# run_calibrated_suite.sh.
#
# Concurrency is capped at 3 (not NUMBER_OF_PROCESSORS): on an 8 GB machine
# BehaviorSpace shares one ~4 GB JVM heap across an experiment's parallel runs,
# and 6-way concurrency thrashes GC (~4.5 h/experiment) while 3-way runs
# near-linearly (~2.2 h/experiment, ~11 h total). See LOS_IMPLEMENTATION.md.
# On a machine with >=16 GB RAM you can raise it: $env:THREADS = 6.
#
# The script keeps Windows awake for its duration (SetThreadExecutionState) so
# you do not need a caffeinate equivalent; sleep resumes when it exits.
#
# Usage (PowerShell):
#   $env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"
#   .\run_calibrated_suite.ps1

$ErrorActionPreference = "Stop"

if (-not $env:NETLOGO) {
    throw 'Set NETLOGO to your NetLogo install dir, e.g. $env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"'
}
$HEADLESS = Join-Path $env:NETLOGO "netlogo-headless.bat"
if (-not (Test-Path $HEADLESS)) {
    throw "netlogo-headless.bat not found at $HEADLESS. Check the NETLOGO path."
}

# netlogo-headless.bat falls back to a bare "java.exe" (PATH) when JAVA_HOME is
# unset. NetLogo 6.x bundles a JRE under <install>\runtime; point JAVA_HOME at it
# so the run does not depend on a system-wide Java being on PATH.
if (-not $env:JAVA_HOME) {
    $bundled = Join-Path $env:NETLOGO "runtime"
    if (Test-Path (Join-Path $bundled "bin\java.exe")) {
        $env:JAVA_HOME = $bundled
        Write-Host "Using NetLogo's bundled Java: $bundled"
    } else {
        throw "Java not found: JAVA_HOME is unset and no bundled JRE at $bundled. Install Java or set JAVA_HOME to a JDK/JRE."
    }
}

$HERE        = $PSScriptRoot
$NETLOGO_DIR = Split-Path $HERE -Parent
$MODEL       = Join-Path $NETLOGO_DIR "akl_traffic.nlogo"
$XML         = Join-Path $HERE "sensitivity_experiment.xml"
$OUT         = Join-Path $NETLOGO_DIR "..\output\tables"
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
$OUT = (Resolve-Path $OUT).Path

$THREADS = if ($env:THREADS) { $env:THREADS } else { 3 }
$LOG = Join-Path $env:TEMP "suite_calibrated.log"
"" | Set-Content $LOG

# --- keep the machine awake for the run (released when the process exits) ---
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Sleepless {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
}
'@
[void][Sleepless]::SetThreadExecutionState([Sleepless]::ES_CONTINUOUS -bor [Sleepless]::ES_SYSTEM_REQUIRED)

Push-Location $NETLOGO_DIR   # so Data\... resolves
try {
    "[{0}] calibrated suite start (threads=$THREADS)" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
    foreach ($EXP in @("sensitivity-pay", "sensitivity-elfarol", "sensitivity-ql-alpha", "sensitivity-ql-epsilon", "sensitivity-kfactor")) {
        "[{0}] >>> $EXP" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
        $table = Join-Path $OUT "$EXP.csv"
        & $HEADLESS --model $MODEL `
            --setup-file $XML --experiment $EXP `
            --table $table --threads $THREADS *>> $LOG
        "[{0}] <<< $EXP exit $LASTEXITCODE" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
    }
    "[{0}] aggregating" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
    Push-Location $HERE
    try {
        python aggregate_sensitivity.py *>> $LOG
        python plot_sensitivity.py      *>> $LOG
    } finally { Pop-Location }
    "[{0}] ALL DONE" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
}
finally {
    Pop-Location
    # release the sleep lock
    [void][Sleepless]::SetThreadExecutionState([Sleepless]::ES_CONTINUOUS)
}
