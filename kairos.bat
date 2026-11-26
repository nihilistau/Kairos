@echo off
rem THE LAUNCHER (harness/launcher.py): choose the companion, who is talking to her and how she
rem runs, then start, stop, back up or open the room. No arguments = the menu.
cd /d "%~dp0"
python -m harness.launcher %*
