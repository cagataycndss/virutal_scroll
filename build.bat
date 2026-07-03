@echo off
echo ============================================
echo   VirtualScroll - Building Executable...
echo ============================================
echo.

REM Sanal ortam kontrolu
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment found. Activating...
    call venv\Scripts\activate.bat
) else (
    echo [WARN] No virtual environment found. Using system Python.
)

REM Bagimlilik kontrolu
echo [1/3] Checking dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

REM PyInstaller ile exe olusturma
echo [2/3] Building executable with PyInstaller...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name VirtualScroll ^
    --clean ^
    --noconfirm ^
    virtual_scroll.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo.
echo ============================================
echo   Output: dist\VirtualScroll.exe
echo ============================================
echo.
echo You can now:
echo   1. Run dist\VirtualScroll.exe directly
echo   2. Copy it to your Windows Startup folder:
echo      Press Win+R, type "shell:startup", and paste the exe there.
echo.
pause
