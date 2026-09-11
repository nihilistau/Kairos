<#
Deploys the Home Assistant logon autostart, and refuses to leave it broken.

    powershell -NoProfile -ExecutionPolicy Bypass -File harness\homeassistant\stack\deploy-autostart.ps1

WHY THIS IS A SCRIPT AND NOT TWO Copy-Item LINES IN A DOC (2026-09-09). I deployed the new
launcher by hand, ran it, and it did nothing at all -- no error, no log, no stack. The cause
was ENCODING, and it is a trap anyone repeating this by hand will fall into:

  * this repo writes UTF-8 without a BOM, and the reasoning in these files uses em dashes;
  * the Startup entry invokes `powershell.exe`, which is Windows PowerShell 5.1;
  * 5.1 reads a BOM-LESS file as cp1252, so every em dash arrives as three bytes of
    mojibake and the file does not PARSE:

        Write-Log ("host network NOT ready after {0}s â€” no {1} ...
        Unexpected token 'no' in expression or statement.

  * a parse failure under `-File` with a hidden window produces no output anywhere. The
    logon entry ran, powershell started, died before its first line, and the log this whole
    fix exists to write was never created. Silent, and identical from the outside to the
    bug it was meant to fix.

So the copy is done ONCE, here, with an explicit BOM, and then the deployed copy is PARSED
BY THE INTERPRETER THAT WILL ACTUALLY RUN IT before this script will call the job done.
Testing it under pwsh 7 -- which reads BOM-less UTF-8 correctly -- is what let the fault
through in the first place: the check has to use the same reader as the caller.

AND IT OWNS THE SCHEDULED TASK, BECAUSE THAT IS WHAT ACTUALLY RUNS (2026-09-11). The
2026-09-09 fix was correct and never fired once: it went into the Startup FOLDER, and the
real autostart on this machine is a scheduled task, `Home Assistant WSL autostart`, created
2026-08-29 with a logon trigger and a 15-second delay, pointing at
`C:\Users\Sam\.wsl-ha\start-ha.vbs` -- a one-liner that starts the distro and pins it with
`sleep infinity`, nothing more. After the next reboot the log written for exactly this
moment was EMPTY, while the distro was up with `wslinfo --networking-mode = none` and every
container healthy and unreachable: the identical failure, because the launcher I fixed is
not the launcher that runs.

I had the evidence on 09-09 and read it wrong. "The distro is up at logon in mode none" is
explained just as well by that task as by the Startup entry, and I never checked which. So
this script now OWNS the whole path -- files, task, and the removal of the other entry --
because two launchers where one is believed is the shape of the original bug, and this time
it was in my own fix.

    powershell -NoProfile -ExecutionPolicy Bypass -File ...\deploy-autostart.ps1 -Verify
#>
[CmdletBinding()]
param(
    [switch] $NoRun,         # deploy and verify parsing, but do not start the stack
    [switch] $Verify,        # after deploying, RUN THE TASK -- the only end-to-end proof
    [string] $TaskName = "Home Assistant WSL autostart"
)

$ErrorActionPreference = "Stop"

$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
# ~/.wsl-ha AND NOT %LOCALAPPDATA%. The scheduled task cannot see AppData -- see the
# header, and ha-autostart.ps1's $LogPath note, which carries the proof.
$dstDir  = "$env:USERPROFILE\.wsl-ha"
$dstPs1  = "$dstDir\ha-autostart.ps1"
# THE LAUNCHER LIVES WITH THE WORKER NOW, not in the Startup folder. One directory, one
# path, and the scheduled task is the only thing that points at it.
$dstVbs  = "$dstDir\home-assistant-wsl.vbs"
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$oldVbs  = "$startup\home-assistant-wsl.vbs"
$ps51    = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }

# ── 1. the worker, written WITH a BOM so 5.1 reads it as UTF-8 ──────────────────────
# `Set-Content -Encoding UTF8` emits a BOM on 5.1 and NOT on 7+, which is exactly the kind
# of difference that produced this bug -- so the bytes are written explicitly instead.
$text = [IO.File]::ReadAllText("$here\ha-autostart.ps1", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($dstPs1, $text, [Text.UTF8Encoding]::new($true))
$bom = [IO.File]::ReadAllBytes($dstPs1)[0..2]
if ($bom[0] -ne 0xEF -or $bom[1] -ne 0xBB -or $bom[2] -ne 0xBF) {
    throw "deployed $dstPs1 has no UTF-8 BOM -- Windows PowerShell 5.1 will mis-read it"
}
Write-Host "deployed  $dstPs1  (UTF-8 with BOM)"

# ── 2. the launcher, WITHOUT a BOM, which is the exact opposite rule ───────────────
# AND THIS IS THE TRAP UNDERNEATH THE TRAP. Having learned that 5.1 needs the BOM, I wrote
# both files the same way and the launcher stopped compiling at all:
#
#     home-assistant-wsl.vbs(1, 1) Microsoft VBScript compilation error: Invalid character
#
# VBScript rejects a BOM outright, at the first character. So these two files that ship
# together have OPPOSITE encoding requirements -- the worker must have a BOM or PowerShell
# 5.1 mangles it, the launcher must not have one or the script host refuses it -- and that
# is precisely why this is a script with assertions instead of a sentence in a doc.
$vbsText = [IO.File]::ReadAllText("$here\home-assistant-wsl.vbs", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($dstVbs, $vbsText, [Text.UTF8Encoding]::new($false))
$vbsBytes = [IO.File]::ReadAllBytes($dstVbs)
if ($vbsBytes[0] -eq 0xEF -and $vbsBytes[1] -eq 0xBB -and $vbsBytes[2] -eq 0xBF) {
    throw "deployed $dstVbs starts with a UTF-8 BOM -- VBScript will refuse it at (1,1)"
}
$nonAscii = @($vbsText.ToCharArray() | Where-Object { [int]$_ -gt 127 })
if ($nonAscii.Count -gt 0) {
    $codes = ($nonAscii | Select-Object -Unique | ForEach-Object { "U+{0:X4} ({1})" -f [int]$_, $_ }) -join ", "
    throw ("the launcher contains {0} non-ASCII character(s) [{1}] and cannot carry a BOM to " -f
           $nonAscii.Count, $codes) +
          "declare its encoding, because VBScript refuses a BOM at (1,1) -- keep it ASCII"
}
Write-Host "deployed  $dstVbs  (no BOM, ASCII)"

# NO SEPARATE "DOES IT COMPILE" CHECK, AND THAT IS A CORRECTION. This had a
# `cscript //nologo //Job:nonexistent` here to compile without running -- but `//Job`
# selects a job inside a .wsf, means nothing to a plain .vbs, and cscript simply EXECUTED
# the launcher. The log then showed two `autostart begin` lines two seconds apart on every
# deploy, and stray `sleep infinity` processes accumulating in the distro: a check that
# performs the action it is checking. The two byte assertions above cover both encoding
# faults actually observed, and step 4 runs the launcher for real exactly once, which is
# the only proof that matters anyway.

# ── 3. THE LEG THAT WOULD HAVE CAUGHT IT: parse with the real interpreter ──────────
$probe = @"
`$errs = `$null
[void][System.Management.Automation.Language.Parser]::ParseFile('$dstPs1', [ref]`$null, [ref]`$errs)
if (`$errs) { `$errs | ForEach-Object { 'PARSE: ' + `$_.Message }; exit 3 }
'parses clean under ' + `$PSVersionTable.PSVersion.ToString()
"@
$probeFile = Join-Path $env:TEMP "ha-deploy-parse-probe.ps1"
[IO.File]::WriteAllText($probeFile, $probe, [Text.UTF8Encoding]::new($true))
$out = & $ps51 -NoProfile -ExecutionPolicy Bypass -File $probeFile 2>&1
$rc = $LASTEXITCODE
Remove-Item $probeFile -ErrorAction SilentlyContinue
$out | ForEach-Object { Write-Host "  $_" }
if ($rc -ne 0) { throw "the deployed autostart does not parse under Windows PowerShell 5.1" }

# ── 4. THE SCHEDULED TASK IS THE AUTOSTART, so this owns it ───────────────────────
# Only the ACTION is rewritten. The principal and trigger are left exactly as they are --
# interactive, as the logged-on user, 15 s after logon -- because those are what make it
# fire at all, and the race they create is handled inside ha-autostart.ps1 by waiting for
# the network rather than by arguing with the delay.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$dstVbs`""
if ($existing) {
    $wasPointingAt = ($existing.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join "; "
    Set-ScheduledTask -TaskName $TaskName -Action $action | Out-Null
    Write-Host "task '$TaskName' repointed"
    Write-Host "   was: $wasPointingAt"
    Write-Host "   now: wscript.exe `"$dstVbs`""
} else {
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT15S"
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                                        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $set.ExecutionTimeLimit = "PT0S"
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                           -Settings $set -Description "Brings Home Assistant up with Windows." | Out-Null
    Write-Host "task '$TaskName' created"
}
$now = (Get-ScheduledTask -TaskName $TaskName).Actions |
       ForEach-Object { "$($_.Execute) $($_.Arguments)" }
if ($now -notmatch [regex]::Escape($dstVbs)) {
    throw "the task still does not point at $dstVbs -- it points at: $now"
}

# ── 5. ONE LAUNCHER. Anything else that could start this stack is a path nobody reads ──
if (Test-Path $oldVbs) {
    Remove-Item $oldVbs -Force
    Write-Host "removed the Startup-folder copy (it never ran, and a second path is the bug)"
}
$legacy = "$dstDir\start-ha.vbs"
if (Test-Path $legacy) {
    Write-Warning ("$legacy still exists. Nothing points at it now, but it is the launcher " +
                   "that actually ran until 2026-09-11 and it starts the distro with no " +
                   "network wait. Delete it once you are happy, or it will mislead the next reader.")
}

# ── 6. and prove it end to end THROUGH THE TASK, which is the only thing that runs ──
if ($NoRun) { Write-Host "-NoRun: deployed and verified, not started"; exit 0 }

$logPath = "$dstDir\autostart.log"
$before  = if (Test-Path $logPath) { (Get-Item $logPath).LastWriteTime } else { [datetime]::MinValue }
if ($Verify) {
    # THE PROOF THE 09-09 PASS DID NOT HAVE. Running the launcher by hand only ever showed
    # that the launcher works; it could not show that anything CALLS it. Start-ScheduledTask
    # exercises the real mechanism -- task -> wscript -> VBS -> powershell 5.1 -> worker.
    Write-Host "starting the TASK (not the file) -- the mechanism, end to end..."
    Start-ScheduledTask -TaskName $TaskName
} else {
    Write-Host "running the launcher directly (pass -Verify to exercise the task instead)..."
    Start-Process wscript.exe -ArgumentList @("`"$dstVbs`"") -Wait
}
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 5
    if ((Test-Path $logPath) -and (Get-Item $logPath).LastWriteTime -gt $before) {
        if ((Get-Content $logPath -Tail 12) -match "autostart end") { break }
    }
}
if (-not (Test-Path $logPath) -or (Get-Item $logPath).LastWriteTime -le $before) {
    throw ("nothing reached $logPath -- the chain is broken. If -Verify was used, the TASK " +
           "did not run the launcher; otherwise the VBS -> PowerShell hop failed.")
}
Write-Host "--- $logPath ---"
Get-Content $logPath -Tail 12 | ForEach-Object { Write-Host "  $_" }
