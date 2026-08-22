@echo off
rem ============================================================
rem seed_japanese_build.py を走らせるバッチ（ダブルクリック用）
rem
rem 「日本語で1語として在る表記」の表を作り直します。
rem   ネットから SudachiDict の生の CSV を取ってきて、
rem   seed_japanese.txt.gz / seed_japanese_cost.txt.gz /
rem   NOTICE_sudachi.txt の3つを **上書き** します。
rem
rem 開発時に1回だけの作業です。アプリ本体はネットに繋ぎません。
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

if not exist "seed_japanese_build.py" (
    echo seed_japanese_build.py がこのフォルダにありません。
    pause
    exit /b 1
)

echo ============================================================
echo  これから行うこと
echo ============================================================
echo   1. ネットから SudachiDict の語彙 CSV を3つ取ってきます
echo      （small / core / notcore。数十MBあります）
echo   2. 「1語として在る表記」の表を作り直します
echo   3. 次の3つを **上書き** します
echo        seed_japanese.txt.gz
echo        seed_japanese_cost.txt.gz
echo        NOTICE_sudachi.txt
echo.
echo   ネットに繋がる必要があります。数分かかります。
echo   終わったら「残した見本」「落とした見本」が並びます。
echo   **その出力をそのままコピーして渡してください。**
echo.
echo 中止するときは、この窓を閉じてください。
pause

echo.
%PY% seed_japanese_build.py
if errorlevel 1 (
    echo.
    echo 失敗しました。上のエラーを確認してください。
    echo （版が古いと言われたら、seed_japanese_build.bat ではなく
    echo   cmd で  py seed_japanese_build.py 20260723  のように
    echo   版を指定して走らせてください）
    pause
    exit /b 1
)

echo.
echo 終わりました。上の出力をコピーして渡してください。
pause
