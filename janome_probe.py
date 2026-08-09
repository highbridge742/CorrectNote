# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
janome の辞書データ構造を詳しく調べる診断スクリプト。

    py janome_probe.py > probe.txt

出力をファイルに落として、その中身を見せてください。
（画面だと長すぎて見切れるため）
"""

import importlib

print('=' * 60)
print('janome 辞書データ構造の診断')
print('=' * 60)

try:
    import janome
    print(f'バージョン: {getattr(janome, "__version__", "不明")}')
except Exception as e:
    print(f'import に失敗: {e}')
    raise SystemExit(1)


def describe(obj, name, depth=0, max_show=3):
    """オブジェクトの構造を簡潔に説明する。"""
    pad = '  ' * depth
    t = type(obj).__name__
    try:
        n = len(obj)
        print(f'{pad}{name}: {t} (件数 {n})')
    except Exception:
        print(f'{pad}{name}: {t}')
        return

    if isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            if i >= max_show:
                break
            print(f'{pad}  キー {k!r} ({type(k).__name__})')
            preview = repr(v)
            if len(preview) > 300:
                preview = preview[:300] + ' ...'
            print(f'{pad}    値: {preview}')
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj[:max_show]):
            preview = repr(v)
            if len(preview) > 300:
                preview = preview[:300] + ' ...'
            print(f'{pad}  [{i}]: {preview}')


print()
print('--- entries_compact0 の中身 ---')
try:
    m = importlib.import_module('janome.sysdic.entries_compact0')
    names = [a for a in dir(m) if not a.startswith('__')]
    print(f'属性: {names}')
    for name in names:
        val = getattr(m, name)
        if isinstance(val, (dict, list, tuple)):
            describe(val, name, depth=1)
except Exception as e:
    print(f'読み込み失敗: {e}')

print()
print('--- entries_extra0 の中身 ---')
try:
    m = importlib.import_module('janome.sysdic.entries_extra0')
    names = [a for a in dir(m) if not a.startswith('__')]
    print(f'属性: {names}')
    for name in names:
        val = getattr(m, name)
        if isinstance(val, (dict, list, tuple)):
            describe(val, name, depth=1)
except Exception as e:
    print(f'読み込み失敗: {e}')

print()
print('--- entries_compact0_idx の中身 ---')
try:
    m = importlib.import_module('janome.sysdic.entries_compact0_idx')
    names = [a for a in dir(m) if not a.startswith('__')]
    print(f'属性: {names}')
    for name in names:
        val = getattr(m, name)
        if isinstance(val, (dict, list, tuple)):
            describe(val, name, depth=1)
except Exception as e:
    print(f'読み込み失敗: {e}')

print()
print('--- janome.sysdic 本体 ---')
try:
    sysdic = importlib.import_module('janome.sysdic')
    names = [a for a in dir(sysdic) if not a.startswith('__')]
    print(f'属性: {names}')
    for name in names[:15]:
        val = getattr(sysdic, name, None)
        if isinstance(val, (dict, list, tuple)):
            describe(val, name, depth=1)
        elif callable(val):
            print(f'  {name}: 関数/メソッド')
except Exception as e:
    print(f'読み込み失敗: {e}')

print()
print('診断終了')
