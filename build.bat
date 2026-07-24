@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Build payslip-downloader.exe  (single file)
REM
REM  build.bat        — single exe build (for sharing)
REM  build.bat --dev  — fast folder build (for testing)
REM
REM  First run installs dependencies automatically.
REM  Subsequent runs reuse the build\ cache.
REM ─────────────────────────────────────────────────────────────────────────────

if exist build\ goto :skip_setup

echo [1/2] First-time setup: installing build dependencies...
pip install pyinstaller playwright customtkinter python-dotenv python-dateutil requests
if errorlevel 1 goto :error
echo.
echo [2/2] Building...
goto :build

:skip_setup
echo Building...

:build
if /i "%1"=="--dev" (
    echo Mode: DEV ^(folder build — fast^)
    pyinstaller ^
        --onedir ^
        --windowed ^
        --splash splash.png ^
        --name payslip-downloader ^
        --collect-all playwright ^
        --collect-all customtkinter ^
        --exclude-module numpy ^
        --exclude-module matplotlib ^
        --exclude-module pandas ^
        --exclude-module scipy ^
        --exclude-module PIL ^
        --exclude-module setuptools ^
        --exclude-module distutils ^
        --exclude-module unittest ^
        --exclude-module xmlrpc ^
        gui.py
    if errorlevel 1 goto :error
    echo.
    if exist dist\payslip-downloader\payslip-downloader.exe (
        echo  SUCCESS: dist\payslip-downloader\payslip-downloader.exe
    ) else (
        goto :error
    )
) else (
    echo Mode: RELEASE ^(single exe — this takes a few minutes^)
    pyinstaller ^
        --onefile ^
        --windowed ^
        --splash splash.png ^
        --name payslip-downloader ^
        --collect-all playwright ^
        --collect-all customtkinter ^
        --exclude-module numpy ^
        --exclude-module matplotlib ^
        --exclude-module pandas ^
        --exclude-module scipy ^
        --exclude-module PIL ^
        --exclude-module setuptools ^
        --exclude-module distutils ^
        --exclude-module unittest ^
        --exclude-module xmlrpc ^
        gui.py
    if errorlevel 1 goto :error
    echo.
    if exist dist\payslip-downloader.exe (
        echo  SUCCESS: dist\payslip-downloader.exe
    ) else (
        goto :error
    )
)
goto :end

:error
echo.
echo  BUILD FAILED — check output above.

:end
pause
