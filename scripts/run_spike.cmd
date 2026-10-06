@echo off
rem Runs Spike (web + worker + watcher) forever, restarting 30 s after any exit.
rem Started by the "Spike" scheduled task (scripts\install_autostart.ps1). All output goes to data\spike.log.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
:loop
echo [%date% %time%] starting spike >> data\spike.log
py spike.py web >> data\spike.log 2>&1
echo [%date% %time%] spike exited with code %errorlevel%, restarting in 30 s >> data\spike.log
ping -n 31 127.0.0.1 > nul
goto loop
