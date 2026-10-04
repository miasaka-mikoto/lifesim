@echo off
setlocal
cd /d "%~dp0"
python -m lifesim run --days 30 --agents 10 --progress --output reports\demo
endlocal

