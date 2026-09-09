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
#>
[CmdletBinding()]
param(
    [switch] $NoRun          # deploy and verify parsing, but do not start the stack
)

$ErrorActionPreference = "Stop"

$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$dstDir  = "$env:LOCALAPPDATA\HomeAssistant"
$dstPs1  = "$dstDir\ha-autostart.ps1"
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$dstVbs  = "$startup\home-assistant-wsl.vbs"
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

# ── 4. and prove the chain end to end, through the launcher Windows will use ───────
if ($NoRun) { Write-Host "-NoRun: deployed and verified, not started"; exit 0 }

$logPath = "$dstDir\autostart.log"
$before  = if (Test-Path $logPath) { (Get-Item $logPath).LastWriteTime } else { [datetime]::MinValue }
Write-Host "running the Startup entry via wscript, as Explorer does..."
Start-Process wscript.exe -ArgumentList @("`"$dstVbs`"") -Wait
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 5
    if ((Test-Path $logPath) -and (Get-Item $logPath).LastWriteTime -gt $before) {
        $tail = Get-Content $logPath -Tail 12
        if ($tail -match "autostart end") { break }
    }
}
if (-not (Test-Path $logPath) -or (Get-Item $logPath).LastWriteTime -le $before) {
    throw "the launcher wrote nothing to $logPath -- the VBS -> PowerShell chain is broken"
}
Write-Host "--- $logPath ---"
Get-Content $logPath -Tail 12 | ForEach-Object { Write-Host "  $_" }
