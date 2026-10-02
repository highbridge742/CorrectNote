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
    echo bundle_manifest.py がこのフォルダにありません。
    echo exe に何を入れるかの名簿なので、これが無いとビルドできません。
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo [1/4] 必要なパッケージを確認しています...
"%PY%" -X utf8 -c "import PyInstaller, janome"
if errorlevel 1 (
    echo.
    echo PyInstaller or janome is missing from this Python environment.
    echo Install them into "%PY%" and run build_exe.bat again.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

rem 前のビルドの報告を消しておく（残っていると古い結果を読んでしまう）
if exist "build\bundle_report.txt" del /q "build\bundle_report.txt"

echo.
echo [2/4] exe をビルドしています（数分かかります）...
"%PY%" -X utf8 -m PyInstaller correctnote.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo ビルドに失敗しました。上のエラーを確認してください。
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [3/4] 何が exe に入ったかを確かめています...
echo.
if not exist "build\bundle_report.txt" (
    echo !! 同梱物の報告 build\bundle_report.txt が作られませんでした。
    echo !! correctnote.spec が bundle_manifest.py を読めていない可能性が
    echo !! あります。上のビルドの出力を確認してください。
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)
type "build\bundle_report.txt"

findstr /b /c:"RESULT=NG" "build\bundle_report.txt" >nul
if not errorlevel 1 (
    echo.
    echo ============================================================
    echo !! exe に入らなかったものがあります（上の [NG] の行）。
    echo !! どれも「無ければ黙って効かない」造りなので、exe は動きますが、
    echo !! その機能だけが静かに効きません。
    echo !! 足りないファイルをこのフォルダに置いて、もう一度ビルドして
    echo !! ください。
    echo ============================================================
    echo.
    echo dist\CorrectNote.exe は出来ています（そのままでも動きます）。
    echo.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [4/4] exe 内の版と補正エンジンを確かめています...
"%PY%" -X utf8 "verify_built_exe.py" "dist\CorrectNote.exe"
if errorlevel 1 (
    echo The EXE did not match the current source. Build failed verification.
    if not defined CORRECTNOTE_NO_PAUSE pause
    exit /b 1
)

echo.
echo [4/4] 完了しました。
echo   dist\CorrectNote.exe
echo が出来ています。Python の無いPCへコピーして使えます。
echo.
echo 【どのフォルダで動かすか】
echo   exe は「置いたフォルダ」を見ます。語彙・メモ・設定は
echo   その隣に作られます（vocabulary.json / session.json など）。
echo   dist の中でそのまま動かすと、語彙もメモも空の「初期状態」から
echo   始まります（初回は辞書の取り込みに時間がかかります）。
echo   いまの語彙・メモのまま試すときは、exe をそのデータの在る
echo   フォルダへ写してから動かしてください。
echo.
if not defined CORRECTNOTE_NO_PAUSE pause
