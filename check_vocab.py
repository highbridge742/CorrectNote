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
語彙ストアの状態を確認するスクリプト。

    py check_vocab.py

vocabulary.json の件数と内容のサンプルを表示します。
"""

import json
import os

VOCAB_FILE = 'vocabulary.json'

if not os.path.exists(VOCAB_FILE):
    print('vocabulary.json が見つかりません。')
    print('アプリを起動して少し待つと作成されます。')
    raise SystemExit()

with open(VOCAB_FILE, encoding='utf-8') as f:
    data = json.load(f)

print(f'語彙の総数: {len(data)} 件')
print()

# カテゴリ別に集計
from collections import Counter
cats = Counter(e.get('category', '?') for e in data)
print('カテゴリ別件数:')
for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
    print(f'  {cat:20s} {n:6d} 件')

print()
# **回数は持たない**（項目48-QG・2026-09-05）。うにさんの指定で
# 使用回数と最終使用時刻の記録をやめたので、「上位20件」は無い。
# 代わりに **立っている語（solid）** を数えて、先頭を並べる。
_solid = [e for e in data
          if (e.get('solid') if 'solid' in e
              else (e.get('count', 0) >= 2))]
print(f'立っている語（solid）: {len(_solid)} 件 '
      f'／ 辞書から取り込んだだけ: {len(data) - len(_solid)} 件')
print('サンプル（立っている語の先頭20件）:')
for e in _solid[:20]:
    print(f'  {e["surface"]:12s}  読み:{e["reading"]:14s}  '
          f'world:{e.get("world", 0):3d}  {e.get("category","?")}')

print()
# 特定の読みを引けるか確認
checks = [
    ('たんご', '単語'),
    ('つながり', 'つながり'),
    ('もじ', '文字'),
    ('にゅうりょく', '入力'),
    ('きーぼーど', 'キーボード'),
    ('かんじ', '漢字'),
]
print('語彙の引き当て確認:')
by_reading = {}
for e in data:
    r = e['reading']
    by_reading.setdefault(r, []).append(e['surface'])

for reading, expected in checks:
    surfaces = by_reading.get(reading, [])
    found = expected in surfaces
    print(f'  {reading:16s} -> {", ".join(surfaces[:5]) or "(なし)":20s}'
          f'  {"OK" if found else "未登録"}')
