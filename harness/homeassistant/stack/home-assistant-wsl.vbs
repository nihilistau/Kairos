' Starts Home Assistant with Windows. Deployed to the per-user Startup folder:
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\home-assistant-wsl.vbs
'
' A VBS only so nothing flashes a console window at logon. The work is in
' ha-autostart.ps1 (deployed to %LOCALAPPDATA%\HomeAssistant\), because the work is now
' more than one command and needs to be readable.
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
script = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\HomeAssistant\ha-autostart.ps1"
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & script & """", 0, False
