@echo off
rem ============================================================
rem CorrectNote -> exe build script
rem
rem Usage: double-click this file (or run in cmd)
rem Output: dist\CorrectNote.exe
rem
rem Python is needed only on the PC that builds.
rem The resulting CorrectNote.exe runs on PCs without Python.
rem
rem [3/4] prints WHAT WENT INTO the exe (build\bundle_report.txt).
rem The list of bundled files lives in bundle_manifest.py (one place).
rem ============================================================

cd /d "%~dp0"

rem --- use this workspace's Python 3.9 unless explicitly overridden ---
set "PY=%CORRECTNOTE_PYTHON%"
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    ) else (
        set "PY=python"
    )
)
"%PY%" -X utf8 -c "import sys; assert sys.version_info >= (3, 9)"
if errorlevel 1 (
    echo Python 3.9 or newer was not found. Set CORRECTNOTE_PYTHON to python.exe.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

if not exist "bundle_manifest.py" (
    echo bundle_manifest.py was not found in this folder.
    echo The bundle manifest is required to build the executable.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo [1/4] Checking required packages...
"%PY%" -X utf8 -c "import PyInstaller, janome"
if errorlevel 1 (
    echo.
    echo PyInstaller or janome is missing from this Python environment.
    echo Install them into "%PY%" and run build_exe.bat again.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

rem Remove the prior bundle report so an old result cannot be mistaken for this build.
if exist "build\bundle_report.txt" del /q "build\bundle_report.txt"

echo.
echo [2/4] Building the executable...
"%PY%" -X utf8 -m PyInstaller correctnote.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo Build failed. See the error above.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [3/4] Checking bundled files...
echo.
if not exist "build\bundle_report.txt" (
    echo !! build\bundle_report.txt was not created.
    echo !! Check whether correctnote.spec loaded bundle_manifest.py.
    echo !! See the build output above.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)
type "build\bundle_report.txt"

findstr /b /c:"RESULT=NG" "build\bundle_report.txt" >nul
if not errorlevel 1 (
    echo.
    echo ============================================================
    echo !! Some required files were not bundled. See the [NG] lines above.
    echo !! The executable may start with features missing.
    echo !! This is not a complete distribution.
    echo !! Restore the missing files in this folder, then build again.
    echo.
    echo ============================================================
    echo.
    echo dist\CorrectNote.exe exists but failed the bundle check.
    echo.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [4/4] Verifying the executable against current source and data...
"%PY%" -X utf8 "verify_built_exe.py" "dist\CorrectNote.exe"
if errorlevel 1 (
    echo The EXE did not match the current source. Build failed verification.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [4/4] Complete.
echo   dist\CorrectNote.exe
echo The executable can run on a PC without Python.
echo.
echo Data folder:
echo   The executable uses the folder where it is placed.
echo   Vocabulary, notes and settings are stored beside it.
echo   Running it inside dist starts with empty local data.
echo   The first dictionary import may take some time.
echo   To use existing data, place the executable in that data folder
echo   before starting it.
echo.
if not defined CORRECTNOTE_NO_PAUSE pause
