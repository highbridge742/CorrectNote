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
- **育つデータ**（vocabulary.json 等）は同梱しない。
  実行時に exe と同じフォルダへ作られる（app.py の app_dir()）。
  初期語彙は seed_vocabulary.py がコードとして持っているので
  初回起動時に自動投入される。
- **`.py` ではない同梱物の名簿は `bundle_manifest.py` ただ1つ**
  （項目48-DK・48-GS）。ここには**書かない**。
  この spec・`kana_memo.spec`・`ci_smoke_test.py`・`freshstate.py` は
  すべてその1つを読む。**同じものを指す一覧を2つ持たない。**
- **在るものだけ挙げる**（PyInstaller は datas に挙げた実物が無いと
  ビルドごと止まる）。無いものは**報告に出して、止めない**。
  報告は画面と `build/bundle_report.txt` の両方に出る。
  `build_exe.bat` が最後にそれを読み直して、足りないものがあれば
  **はっきり知らせる**。
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

# janome 本体＋辞書モジュール＋データを全て集める
janome_datas, janome_binaries, janome_hidden = collect_all('janome')

# 名簿（`bundle_manifest.py`）を読む。spec は exec されるだけなので、
# 自分の居場所を一時的に sys.path へ入れて import し、すぐ戻す。
_here = os.path.abspath(globals().get('SPECPATH') or os.getcwd())
sys.path.insert(0, _here)
try:
    import bundle_manifest
finally:
    if sys.path and sys.path[0] == _here:
        sys.path.pop(0)

bundle_datas, _report, _missing_required = bundle_manifest.collect(
    _here, 'correctnote.spec')
bundle_manifest.print_report(_report, 'correctnote.spec')
bundle_manifest.write_report(_report, _here)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=janome_binaries,
    datas=janome_datas + bundle_datas,
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
