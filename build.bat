@echo off
echo === MLMS Windows Widget Build ===
echo.

echo [1/2] Installing dependencies...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo [2/2] Building MLMS.exe...
python -m PyInstaller --onefile --windowed --name MLMS ^
    --add-data "*.py;." ^
    --hidden-import PyQt6.QtWebEngineWidgets ^
    --hidden-import PyQt6.QtWebEngineCore ^
    --hidden-import keyring.backends.Windows ^
    main.py
if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo === Build complete! ===
echo Output: dist\MLMS.exe
pause
