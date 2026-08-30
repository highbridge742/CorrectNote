# -*- mode: python ; coding: utf-8 -*-
"""
かな入力メモ帳 の PyInstaller ビルド定義（**CI が使うほう**・build.yml）。

    py -m PyInstaller kana_memo.spec

で dist/KanaMemo.exe ができる。

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
- **同梱物の名簿は `bundle_manifest.py` ただ1つ**（項目48-GS）。
  ここに一覧を書き写さない。**書き写した瞬間に、いつかずれる。**
  実際、このファイルには**説明書（CorrectNote_説明書v5.html）が
  入っておらず**、CI が作った exe だけ説明書を持っていなかった。
  名簿を1つにして、その取りこぼしごと直した。
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

# **在るものだけ挙げる**（PyInstaller は実物が無いと止まる）。
# CI のリポジトリに大きい表が入っていなくても、ビルドは赤くしない。
# 足りないものは報告に出す（`ci_smoke_test.py` が同じ名簿で見張る）。
bundle_datas, _report, _missing_required = bundle_manifest.collect(
    _here, 'kana_memo.spec')
bundle_manifest.print_report(_report, 'kana_memo.spec')
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
    name='KanaMemo',
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
    # exe そのものの絵（項目48-JR）。**Windows は `.ico` だけ**。
    # 窓のアイコンは別（app.py の `_apply_window_icon`）——
    # 片方だけだと、そちらを迂回して羽根に戻る（学び22）。
    icon='correctnote.ico',
)
