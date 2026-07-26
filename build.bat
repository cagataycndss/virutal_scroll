@echo off
echo ============================================
echo   VirtualScroll - Building Executable...
echo ============================================
echo.

REM Calisan VirtualScroll sureclerini kapat
echo [1/4] Checking running instances of VirtualScroll...
taskkill /F /IM VirtualScroll.exe >nul 2>&1
taskkill /F /IM VirtualScroll_App.exe >nul 2>&1

REM Sanal ortam kontrolu
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment found. Activating...
    call venv\Scripts\activate.bat
) else (
    echo [WARN] No virtual environment found. Using system Python.
)

REM Bagimlilik kontrolu
echo [2/4] Checking dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

REM PyInstaller ile exe olusturma
echo [3/4] Building executable with PyInstaller...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name VirtualScroll_App ^
    --clean ^
    --noconfirm ^
    virtual_scroll.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    echo.
    echo [NEDEN] Eger "PermissionError: Erişim engellendi" hatasi aliyorsaniz:
    echo   1. Sag alttaki sistem tepsisinden VirtualScroll simgesine sag tiklayip "Cikis" deyin.
    echo   2. Veya Gorev Yöneticisi'ni (Ctrl+Shift+Esc) acip "VirtualScroll.exe" / "VirtualScroll_App.exe" gorevini sonlandirin.
    echo   3. Ardindan build.bat dosyasini tekrar calistirabilirsiniz.
    echo.
    pause
    exit /b 1
)

echo.
echo [4/4] Build complete!
echo.
echo ============================================
echo   Output: dist\VirtualScroll_App.exe
echo ============================================
echo.
echo You can now:
echo   1. Run dist\VirtualScroll_App.exe directly
echo   2. Copy it to your Windows Startup folder:
echo      Press Win+R, type "shell:startup", and paste the exe there.
echo.
pause
