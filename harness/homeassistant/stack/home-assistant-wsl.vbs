' Starts Home Assistant with Windows. Deployed BESIDE its worker:
'   %USERPROFILE%\.wsl-ha\home-assistant-wsl.vbs
'
' and called by the scheduled task "Home Assistant WSL autostart" (logon trigger, 15 s
' delay). A VBS only so nothing flashes a console window at logon; the work is in
' ha-autostart.ps1 next to it, because the work is more than one command.
'
' NOT UNDER %LOCALAPPDATA%, and that is not a preference. The task cannot SEE that
' directory: made to run "dir" itself, as beast\sam, it lists C:\Users\Sam\AppData\Local
' and answers "File Not Found" for the folder every shell of mine lists happily. Put here,
' wscript found it on the first try. Deployed there, wscript popped an invisible modal
' "Can not find script file" and hung forever, which is what a scheduled task does with an
' error dialog and no desktop to show it on.
'
' IT USED TO LIVE IN THE STARTUP FOLDER, AND THAT IS WHY IT NEVER RAN (2026-09-11). The
' 2026-09-09 fix was correct and fired exactly zero times: the autostart on this machine is
' the scheduled task above, created 2026-08-29, and it pointed at a different file
' entirely -- C:\Users\Sam\.wsl-ha\start-ha.vbs, a one-liner that starts the distro and
' pins it with "sleep infinity" and waits for nothing. After the next reboot the log
' written for exactly that moment was empty while the distro sat in networking mode "none"
' with every container healthy and unreachable. Two launchers, one believed, and the wrong
' one fixed. deploy-autostart.ps1 owns the task now, and removes the Startup-folder copy.
'
' THIS FILE IS ASCII ONLY, DELIBERATELY. VBScript refuses a UTF-8 BOM at the first
' character ("Invalid character" at 1,1), so this file cannot declare its own encoding --
' which means it must not contain anything that needs declaring. Its sibling
' ha-autostart.ps1 has the OPPOSITE requirement: Windows PowerShell 5.1 reads a BOM-less
' file as cp1252, so without a BOM its em dashes become mojibake and it will not parse.
' deploy-autostart.ps1 asserts both rules; do not deploy these by hand.
'
' WHAT THIS USED TO BE, AND WHY IT WAS NOT ENOUGH (2026-09-09). One line:
'
'   Run "wsl.exe -d homeassistant -u root --exec /usr/local/bin/ha-keepalive", 0, False
'
' correct, and fired TOO EARLY. At logon, Windows networking and the Hyper-V switches are
' still settling, so networkingMode=mirrored has nothing to mirror. WSL then comes up with
' networking mode "none", and there is no fallback to NAT and no error anywhere. Measured:
' the distro had lo and a linkdown docker0 and no eth at all, could not reach the router,
' and Home Assistant was serving 8123 into a namespace nothing could route to. Every
' container reported healthy. Started by hand ten minutes later the same distro came up
' mirrored, holding the host's own 10.0.0.150. Same config; a different moment.
'
' So the launcher now waits for the host to really hold its LAN address, verifies what the
' distro actually got, recycles the VM if it got nothing, and writes a log either way.
'
' Delete this file to stop Home Assistant starting with Windows.
Dim shell, script
Set shell = CreateObject("WScript.Shell")
script = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.wsl-ha\ha-autostart.ps1"
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & script & """", 0, False
