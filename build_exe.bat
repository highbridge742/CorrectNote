@echo off
rem ============================================================
rem kana memo -> exe build script
rem
rem Usage: double-click this file (or run in cmd)
rem Output: dist\KanaMemo.exe
rem
rem Python is needed only on the PC that builds.
rem The resulting KanaMemo.exe runs on PCs without Python.
rem ============================================================

cd /d "%~dp0"

rem --- find Python launcher (py or python) ---
set PY=py
where py >nul 2>nul
if errorlevel 1 set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
    echo Python が見つかりません。Python をインストールしてください。
    pause
    exit /b 1
)

echo [1/3] 必要なパッケージを確認しています...
%PY% -m pip install --upgrade pyinstaller janome
if errorlevel 1 (
    echo.
    echo pip の実行に失敗しました。上のエラーを確認してください。
    pause
    exit /b 1
)

echo.
echo [2/3] exe をビルドしています（数分かかります）...
%PY% -m PyInstaller kana_memo.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ビルドに失敗しました。上のエラーを確認してください。
    pause
    exit /b 1
)

echo.
echo [3/3] 完了しました。
echo   dist\KanaMemo.exe
echo が出来ています。Python の無いPCへコピーして使えます。
echo （語彙などのデータは exe と同じフォルダに自動で作られます）
echo.
pause
