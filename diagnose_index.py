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
候補が出ない原因を突き止めるための診断。

    py diagnose_index.py > index.txt

「ひらがな」をドラッグしても「平仮名」が出ない、
「時ッ層」に「実装」が出ない、という症状は
辞書索引（dict_index.py）が空であることが原因の可能性が高い。
この診断は、索引が作れているか・どこで失敗しているかを段階的に見る。
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'dict_index.json')

print('=' * 60)
print('辞書索引の診断')
print('=' * 60)

# --- 1. janome があるか ---
try:
    from janome_import import HAS_JANOME, iter_janome_entries
    print(f'janome: {"あり" if HAS_JANOME else "なし"}')
except Exception as e:
    print(f'janome_import の読み込みに失敗: {e}')
    raise SystemExit(1)

# --- 2. 既存のキャッシュの状態 ---
print()
print('--- キャッシュファイル ---')
if os.path.exists(CACHE):
    size = os.path.getsize(CACHE)
    print(f'{CACHE}')
    print(f'サイズ: {size:,} バイト')
    if size < 100000:
        print('※ 小さすぎます。中身が空の可能性が高いです。')
    import json
    try:
        with open(CACHE, encoding='utf-8') as f:
            data = json.load(f)
        print(f'version: {data.get("version")}')
        print(f'読みの数: {len(data.get("by_reading", {})):,}')
        print(f'表記の数: {len(data.get("by_surface", {})):,}')
    except Exception as e:
        print(f'読み込み失敗: {e}')
else:
    print('（まだありません）')

# --- 3. 辞書の生データが取れるか ---
print()
print('--- janome 辞書の走査（先頭20件） ---')
n = 0
sample = []
pos_count = {}
try:
    for surface, reading, pos, sub_pos, _ss, cost in \
            iter_janome_entries(min_len=1, max_len=8):
        n += 1
        if len(sample) < 20:
            sample.append((surface, reading, pos, sub_pos, cost))
        pos_count[pos] = pos_count.get(pos, 0) + 1
        if n >= 200000:
            break
except Exception as e:
    print(f'走査に失敗: {e}')

print(f'取得できた語数: {n:,}')
for s, r, p, sp, c in sample:
    print(f'  {s!r:12s} 読み={r!r:12s} 品詞={p}:{sp} コスト={c}')
print()
print('品詞ごとの件数:')
for p, c in sorted(pos_count.items(), key=lambda x: -x[1])[:10]:
    print(f'  {p or "(空)":12s} {c:,}')

# --- 4. 索引を実際に作ってみる ---
print()
print('--- 索引の構築 ---')
from dict_index import DictIndex

idx = DictIndex(None)      # キャッシュを使わずその場で作る
idx.ensure_built()
st = idx.stats()
print(f'読みの数: {st["readings"]:,}')
print(f'表記の数: {st["surfaces"]:,}')

# --- 5. 実際に問題になった語を引く ---
print()
print('--- 問題の語を引けるか ---')
for reading in ['ひらがな', 'じっそう', 'まちがい', 'いと', 'うった', 'うっ',
                'たんご', 'せいかく', 'さまよう']:
    got = idx.surfaces_for_reading(reading)
    print(f'  読み {reading:10s} -> {got if got else "(引けない)"}')

print()
for surface in ['時', '層', 'タン', '具', '売っ', '打っ', '平仮名', '実装']:
    got = idx.readings_for_surface(surface)
    print(f'  表記 {surface:6s} -> {got if got else "(引けない)"}')

print()
print('診断終了')
print()
print('※ 4 の件数が 0 に近い場合、辞書の走査ができていません。')
print('※ 4 は多いのに 5 で引けない語がある場合、絞り込みが原因です。')
print('　（地名・人名・難語の除外は _should_prune で行っている）')
