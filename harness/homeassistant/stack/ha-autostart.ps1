<#
Brings the Home Assistant WSL distro up AT LOGON, and does not trust that it worked.

THE BUG THIS EXISTS FOR (2026-09-09, reported as "home assistant on wsl is not loading on
start"). The stack started perfectly and was unreachable, which is a worse failure than not
starting: every container reported healthy, Home Assistant listened on 8123, and nothing
could talk to it in either direction.

Measured at the boundary rather than guessed:

    wslinfo --networking-mode      -> none          <- started by the logon script
    ip -4 -o addr show             -> lo, docker0(linkdown)   ... and no eth at all
    ip route                       -> 172.17.0.0/16 dev docker0 linkdown
    ping 10.0.0.1               -> Network is unreachable
    http://localhost:8123          -> actively refused

then, restarted by hand minutes later with nothing else changed:

    wslinfo --networking-mode      -> mirrored
    ip -4 -o addr show             -> eth1 10.0.0.150/24    <- the host's own LAN address
    http://10.0.0.150:8123      -> HTTP 200

So it is a RACE. The logon entry fired while Windows networking and the Hyper-V switches
were still settling (its own event log shows a switch being created at 15:34:18, and the
distro's init started ~15:34:30), and `networkingMode=mirrored` had nothing to mirror.
There is no fallback to NAT and no error: WSL simply comes up with networking mode `none`,
which is silent, total, and looks exactly like a working stack from the inside.

WHY A CONDITION AND NOT A SLEEP. "Wait 60 seconds" is a guess that is wrong on a slow boot
and wasteful on a fast one, and when it fails it fails the same silent way. This waits for
the fact it actually needs (a real LAN address on the host, and the gateway answering),
then VERIFIES the distro came up with networking and RETRIES if it did not.

WHY THE RETRY IS `--shutdown` AND NOT `--terminate`. WSL2 runs ONE VM for every distro and
`networkingMode` is a property of that VM (`[wsl2]` in .wslconfig), so terminating this
distro alone leaves the broken network in place and restarting it changes nothing. The VM
has to be recycled. Guarded: if any OTHER distro is running, this refuses to pull it down
and logs instead — at logon nothing else is up, and outside logon that is not this script's
call to make.

AND IT WRITES A LOG, because the original failure was invisible. Whatever happens next
time, `%LOCALAPPDATA%\HomeAssistant\autostart.log` says which layer it got to.

Deployed from this file — the copy that runs is
`%LOCALAPPDATA%\HomeAssistant\ha-autostart.ps1`, launched by the Startup entry
`home-assistant-wsl.vbs` (a VBS only so there is no console flash). See
docs/HOME-ASSISTANT.md.
#>
[CmdletBinding()]
param(
    [string] $Distro       = "homeassistant",
    [string] $Keepalive    = "/usr/local/bin/ha-keepalive",
    # The address the stack should end up holding. Its presence on an interface INSIDE the
    # distro is the real proof that mirrored mode worked — `wslinfo` reporting "mirrored"
    # is necessary and not sufficient.
    [string] $HostAddress  = "10.0.0.150",
    [string] $Gateway      = "10.0.0.1",
    [int]    $NetWaitSec   = 180,
    [int]    $Attempts     = 4,
    # ── NOT UNDER %LOCALAPPDATA% (2026-09-11) ────────────────────────────────────
    # The scheduled task that actually launches this CANNOT SEE that directory. Proven by
    # making the task run `dir` itself: as beast\sam it lists C:\Users\Sam\AppData\Local
    # and answers "File Not Found" for the HomeAssistant folder, while every shell I have --
    # sandboxed or not -- lists the files happily. My tooling's writes under AppData are
    # container-virtualised: real to me, absent to the system. That is why the 2026-09-09
    # deployment verified green and then fired exactly zero times, and why the log written
    # for precisely that failure was empty after the reboot. ~/.wsl-ha is his own directory,
    # created outside all of that, and the task reads it -- which is how the bisect ended.
    [string] $LogPath      = "$env:USERPROFILE\.wsl-ha\autostart.log",
    # TESTABILITY, and it is the only reason this switch exists: the failure mode is a boot
    # race that cannot be reproduced on demand, so the retry path would otherwise ship
    # having never run. With this set the first verification is forced to fail, which
    # exercises the detect -> recycle -> re-verify path end to end.
    [switch] $ForceFirstCheckFail
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string] $Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        $dir = Split-Path -Parent $LogPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -Path $LogPath -Value $line -Encoding UTF8
    } catch { }
    Write-Output $line
}

function Test-HostNetworkReady {
    <# The precondition mirrored mode needs: a real routable address on this machine, and
       something answering at the far end of it. A link-local 169.254.* address is Windows
       saying "I have an adapter and no network", which is exactly the state that produces
       the silent failure. #>
    $addr = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $HostAddress }
    if (-not $addr) { return $false }
    return [bool] (Test-Connection -ComputerName $Gateway -Count 1 -Quiet -ErrorAction SilentlyContinue)
}

function Get-WslNetworkState {
    <# Asks the distro what it actually got. Returns the mode and whether the host address
       is really on an interface — both, because "mirrored" with no eth is a state this has
       already been seen in. #>
    $mode = (& wsl.exe -d $Distro -u root -- sh -c "wslinfo --networking-mode 2>/dev/null || echo unknown" 2>$null |
             Out-String).Trim()
    $addrs = (& wsl.exe -d $Distro -u root -- sh -c "ip -4 -o addr show 2>/dev/null" 2>$null | Out-String)
    return [pscustomobject]@{
        Mode    = $mode
        HasAddr = $addrs -match [regex]::Escape($HostAddress)
        Addrs   = ($addrs -replace "\s+", " ").Trim()
    }
}

function Get-OtherRunningDistros {
    $out = (& wsl.exe --list --running --quiet 2>$null | Out-String) -replace "`0", ""
    $out -split "`r?`n" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and $_ -ne $Distro }
}

Write-Log "=== autostart begin (distro=$Distro) ==="

# ── 1. wait for the fact, not for a duration ──────────────────────────────────────────
$sw = [Diagnostics.Stopwatch]::StartNew()
$ready = $false
while ($sw.Elapsed.TotalSeconds -lt $NetWaitSec) {
    if (Test-HostNetworkReady) { $ready = $true; break }
    Start-Sleep -Seconds 3
}
if ($ready) {
    Write-Log ("host network ready after {0:N0}s ({1} up, {2} answering)" -f
               $sw.Elapsed.TotalSeconds, $HostAddress, $Gateway)
} else {
    # NOT A REASON TO GIVE UP. He may be off that network entirely (travelling, a different
    # LAN); Home Assistant should still come up locally. Recorded, then continue.
    Write-Log ("host network NOT ready after {0}s — no {1} or no answer from {2}. " -f
               $NetWaitSec, $HostAddress, $Gateway)
    Write-Log "continuing anyway: a wrong network is not a reason to leave the house offline"
}

# ── 2. start it, then check what it got, and recycle the VM if the answer is 'none' ───
$good = $false
for ($i = 1; $i -le $Attempts; $i++) {
    & wsl.exe -d $Distro -u root -- /bin/true 2>$null | Out-Null
    $state = Get-WslNetworkState
    if ($ForceFirstCheckFail -and $i -eq 1) {
        Write-Log "attempt ${i}: FORCED failure (-ForceFirstCheckFail) — exercising the retry path"
        $state = [pscustomobject]@{ Mode = "none"; HasAddr = $false; Addrs = "(forced)" }
    }
    Write-Log ("attempt {0}: mode={1} hostAddrPresent={2} | {3}" -f
               $i, $state.Mode, $state.HasAddr, $state.Addrs)

    if ($state.Mode -ne "none" -and $state.HasAddr) { $good = $true; break }

    if ($i -eq $Attempts) {
        Write-Log "out of attempts — leaving it up so the stack at least runs locally"
        break
    }
    $others = @(Get-OtherRunningDistros)
    if ($others.Count -gt 0) {
        Write-Log ("NOT recycling the VM: other distro(s) running [{0}]. Networking mode is " -f ($others -join ", "))
        Write-Log "a VM-wide property, so fixing it means --shutdown, and that is not mine to do here"
        break
    }
    Write-Log "recycling the WSL VM (mode is VM-wide; --terminate would not clear it)"
    & wsl.exe --shutdown 2>$null | Out-Null
    Start-Sleep -Seconds (5 * $i)
}

# ── 3. pin the distro open and bring the stack up ─────────────────────────────────────
# The keepalive holds one process open forever; WSL2 tears a distro down seconds after the
# last attached process exits, and systemd being PID 1 is not enough. Launched detached so
# this script can exit while that wsl.exe relay stays alive.
Write-Log "starting the keepalive ($Keepalive)"
Start-Process -FilePath "wsl.exe" `
              -ArgumentList @("-d", $Distro, "-u", "root", "--exec", $Keepalive) `
              -WindowStyle Hidden | Out-Null

# ── 4. say whether it actually worked ─────────────────────────────────────────────────
$url = "http://{0}:8123" -f $HostAddress
$answered = $false
for ($t = 0; $t -lt 24; $t++) {          # up to ~2 min: a cold HA takes a while to listen
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 5 -UseBasicParsing
        Write-Log ("{0} -> HTTP {1}" -f $url, $r.StatusCode)
        $answered = $true
        break
    } catch { }
}
if (-not $answered) { Write-Log "$url never answered — see the log above for which layer" }

Write-Log ("=== autostart end (network={0}, reachable={1}) ===" -f $good, $answered)
if ($good -and $answered) { exit 0 } else { exit 1 }
