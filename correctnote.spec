# -*- mode: python ; coding: utf-8 -*-
"""
CorrectNote の PyInstaller ビルド定義。

    py -m PyInstaller correctnote.spec

で dist/CorrectNote.exe ができる（build_exe.bat 参照）。

要点:
- janome の辞書は janome/sysdic/ 以下の Python モジュール
  （entries_compact0〜9, entries_extra0〜9 など）に入っており、
  本体コード（janome_import.py / janome 自身）はこれらを
  importlib で動的に読み込む。PyInstaller の静的解析では
  動的 import を追えないため、collect_all('janome') で
  パッケージ全体を明示的に同梱する。これを忘れると
  「exe では janome が見つからない」状態になる。
- console=False で黒いコンソール窓を出さない。
- データファイル（vocabulary.json 等）は同梱しない。
  実行時に exe と同じフォルダへ作られる（app.py の app_dir()）。
  初期語彙は seed_vocabulary.py がコードとして持っているので
  初回起動時に自動投入される。
- **説明書（CorrectNote_説明書v4.html）は exe に同梱する**
  （うにさんの指定・2026-08-10。exe と html を zip にまとめた
  配布にはせず、exe 1つを置けば説明書も手に入る形にする）。
  同梱したものは実行時の一時フォルダ（sys._MEIPASS）に展開され、
  終了時に消えるため、**app.py が初回起動時に app_dir() へ
  書き出す**（`_extract_manual`）。メニューの
  「このアプリについて → 説明書をHTMLで展開」からも書き出せる。
  ファイル名は app.py の MANUAL_FILENAME と揃えること。
  **このファイルが無いとビルドが失敗する**（PyInstaller は
  datas に挙げた実物が無いとエラーで止まる）。リポジトリで
  CI ビルドする場合は、html も一緒にコミットしておくこと。
"""

from PyInstaller.utils.hooks import collect_all

# janome 本体＋辞書モジュール＋データを全て集める
janome_datas, janome_binaries, janome_hidden = collect_all('janome')

# 説明書（exe の中に入れて持ち歩き、初回起動時に書き出す）。
# ('元のファイル', '展開先のフォルダ') の形。'.' は _MEIPASS 直下。
manual_datas = [('CorrectNote_説明書v4.html', '.')]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=janome_binaries,
    datas=janome_datas + manual_datas,
    hiddenimports=janome_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 使っていない大物を外してサイズと起動時間を抑える
        'numpy', 'pandas', 'matplotlib', 'scipy', 'PIL',
        'test', 'unittest', 'pydoc_data',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CorrectNote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX はウイルス誤検知の原因になるので使わない
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # コンソール窓を出さない（GUIアプリ）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
