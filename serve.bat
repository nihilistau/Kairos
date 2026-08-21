@echo off
REM kairos serve — profile-driven stack launcher. Usage: serve.bat [profile]
cd /d %~dp0
python serve.py %*
