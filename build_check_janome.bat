@echo off
rem ============================================================
rem janome 同梱チェック用の exe を作るスクリプト
rem
rem できた dist\check_janome.exe を、janome を入れていない
rem 別のPCへコピーして実行すると、同梱がうまくいっているか
rem 確認できます（本体アプリとは別の、確認専用のexeです）。
rem ============================================================

cd /d "%~dp0"

set PY=py
where py >nul 2>nul
if errorlevel 1 set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
    echo Python が見つかりません。Python をインストールしてください。
    pause
    exit /b 1
)

echo 必要なパッケージを確認しています...
%PY% -m pip install --upgrade pyinstaller janome
if errorlevel 1 (
    echo pip の実行に失敗しました。
    pause
    exit /b 1
)

echo.
echo ビルドしています...
%PY% -m PyInstaller --onefile --console --collect-all janome check_janome.py --noconfirm
if errorlevel 1 (
    echo ビルドに失敗しました。
    pause
    exit /b 1
)

echo.
echo 完了しました。 dist\check_janome.exe を
echo janome を入れていない別のPCにコピーして実行してください。
pause
