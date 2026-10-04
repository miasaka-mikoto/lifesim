@echo off
setlocal
cd /d "%~dp0"
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --name LifeSim --paths . --exclude-module matplotlib --exclude-module PIL lifesim_entry.py
echo Built dist\LifeSim.exe
endlocal
