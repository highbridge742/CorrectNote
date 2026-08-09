# CorrectNote — かな入力誤字補正メモ帳
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
print('サンプル（使用回数が多い上位20件）:')
top = sorted(data, key=lambda e: e.get('count', 0), reverse=True)[:20]
for e in top:
    print(f'  {e["surface"]:12s}  読み:{e["reading"]:14s}  '
          f'count:{e["count"]:4d}  {e.get("category","?")}')

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
