# Re-run the full sensitivity suite on the CALIBRATED model (scale-factor 160 +
# suburban destinations) on Windows. PowerShell equivalent of
# run_calibrated_suite.sh.
#
# Concurrency defaults to 8. IMPORTANT: BehaviorSpace shares ONE JVM heap
# (~50 % of system RAM) across an experiment's parallel runs, so the safe
# thread count scales with RAM, not cores. On the 8 GB dev laptop 8-way
# concurrency thrashes GC badly - use $env:THREADS = 3 there (measured
# ~2.2 h/experiment at 3-way vs ~4.5 h at 6-way). 8-way needs >=16 GB.
# See LOS_IMPLEMENTATION.md.
#
# n-sim-days is 14 for the sensitivity experiments (5 for calibration-demand),
# set in sensitivity_experiment.xml. At 14 days expect roughly 0.7x the
# 20-day runtimes quoted above.
#
# The script keeps Windows awake for its duration (SetThreadExecutionState) so
# you do not need a caffeinate equivalent; sleep resumes when it exits.
#
# Usage (PowerShell):
#   $env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"
#   .\run_calibrated_suite.ps1
#
# Low-RAM machine, or to run only the El Farol seed replication:
#   $env:THREADS = 3
#   $env:EXPERIMENTS = "elfarol-seeds"

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

$THREADS = if ($env:THREADS) { $env:THREADS } else { 8 }
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
    $EXPERIMENTS = if ($env:EXPERIMENTS) {
        $env:EXPERIMENTS -split '[,\s]+' | Where-Object { $_ }
    } else {
        @("sensitivity-pay", "sensitivity-elfarol", "sensitivity-ql-alpha",
          "sensitivity-ql-epsilon", "sensitivity-kfactor", "elfarol-seeds")
    }
    foreach ($EXP in $EXPERIMENTS) {
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
        # Figures need matplotlib; a missing module must not fail the whole run
        # (the Windows host lacked it on 2026-07-25 and the tables were fine).
        python -c "import matplotlib" 2>$null
        if ($LASTEXITCODE -eq 0) {
            python plot_sensitivity.py *>> $LOG
        } else {
            "[{0}] matplotlib not installed - skipping figures. Run 'python plot_sensitivity.py' on a host that has it (or: pip install matplotlib)." -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
        }
    } finally { Pop-Location }
    "[{0}] ALL DONE" -f (Get-Date -Format 's') | Tee-Object -FilePath $LOG -Append
}
finally {
    Pop-Location
    # release the sleep lock
    [void][Sleepless]::SetThreadExecutionState([Sleepless]::ES_CONTINUOUS)
}
