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
かなの打ち間違いが「なぜ直らないか」を、補正エンジン自身に語らせる診断。

    py diagnose_rebuild.py > rebuild.txt

出力されたファイルの内容を渡してください。

--------------------------------------------------------------------
 前の版との違い（大事な点）
--------------------------------------------------------------------
 前の版は、診断スクリプトの中で関門を **書き写して** 再現していた。
 そのため、書き写し漏れた関門（edge_word）が診断に現れず、
 実機で直らない本当の原因が見えなかった。

 この版は corrector.py 本体に記録を仕込み（corrector.trace_on）、
 **実際に通った道筋をそのまま出す**。書き写しによる食い違いは
 原理的に起きない。
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB_FILE = os.path.join(HERE, 'vocabulary.json')
CONTEXT_VEC_FILE = os.path.join(HERE, 'context_vec.json')
DECISIONS_FILE = os.path.join(HERE, 'decisions.json')
CHOICES_FILE = os.path.join(HERE, 'choices.json')

# (行, 上下の行) の組。上下の行は実機の nearby_words を再現するために
# 渡す（並記の関門・文脈の裁定は周りの語で決まるため、これを省くと
# 実機と食い違う）。
TEST_CASES = [
    ('非アクティブ時のキー', ['隣接キーや脱字、', '文字が元のカーソル位置に挿入されます。']),
    ('文字が元のカール位置に挿入されます。　※カーソル位置、の誤入力',
     ['「素帰任」はありえない。', '非アクティブ時のキー']),
    ('隣接キーや脱字、', ['非アクティブ時のキー', '文字コードを選べるようにします。']),
    ('文字コードを選べるようにします。', ['隣接キーや脱字、', '最大化ボタンを消して']),
    ('最大化ボタンを消して', ['文字コードを選べるようにします。']),
    ('「素帰任」はありえない。', ['折り返しがある行を途中までスクロール']),
]

print('=' * 70)
print('かなの再構築 診断（実際に通った道筋を出す版）')
print('=' * 70)

import corrector as C
from vocabulary import (VocabularyStore, find_known_readings_flex,
                        find_similar_readings)
from seed_vocabulary import load_seed

try:
    from janome_import import HAS_JANOME
except Exception:
    HAS_JANOME = False
print(f'janome: {"あり" if HAS_JANOME else "なし"}')
if not HAS_JANOME:
    print('  ※ janome が無いと、誤補正を防ぐ守り'
          '（正しい日本語として読めるかの判定）が働きません。')
    print('     配布する exe には janome が同梱されるので、'
          'この状態は実機の姿ではありません。')

print(f'corrector.py の場所: {C.__file__}')
print(f'記録の仕組み（trace_on）: '
      f'{"あり" if hasattr(C, "trace_on") else "**無い（古いファイル）**"}')
for name in ('rebuild_window_core', 'window_cores', '_is_all_functional',
             '_break_tie_by_usage'):
    print(f'  corrector.{name}: '
          f'{"あり" if hasattr(C, name) else "**無い（古いファイル）**"}')
print(f'  vocabulary.find_similar_readings: '
      f'{"あり" if find_similar_readings else "無い"}')
if not hasattr(C, 'trace_on'):
    raise SystemExit('corrector.py が古いままです。差し替えてください。')

store = VocabularyStore(VOCAB_FILE)
print(f'語彙の総数: {len(store.to_list())} 件')
added = load_seed(store)
print(f'初期語彙の追加: {added} 件')
tokenize_fn = C.make_tokenizer(store)

# 実機と同じ材料を揃える。ここを省くと、決め手（周りの語・
# ユーザーの判断）が無い状態で測ることになり、実機と食い違う。
try:
    from context_vec import ContextVectorStore
    context_vec = ContextVectorStore(CONTEXT_VEC_FILE)
    print(f'文脈ベクトル: {len(context_vec)} 語')
except Exception as e:
    context_vec = None
    print(f'文脈ベクトル: 読み込めず ({e})')

try:
    from decisions import DecisionStore
    decisions = DecisionStore(DECISIONS_FILE)
    print(f'ユーザーの判断: {len(decisions)} 件')
except Exception as e:
    decisions = None
    print(f'ユーザーの判断: 読み込めず ({e})')

# 実機と同じ辞書索引（読みの候補が索引の有無で変わる）
dict_index = None
try:
    from dict_index import DictIndex
    DICT_INDEX_FILE = os.path.join(HERE, 'dict_index.json')
    dict_index = DictIndex(DICT_INDEX_FILE)
    if not dict_index.ensure_built():
        dict_index = None
    print(f'辞書索引: {"あり" if dict_index else "無し"}')
except Exception as e:
    print(f'辞書索引: 読み込めず ({e})')

try:
    from choices import ChoiceStore
    choices = ChoiceStore(CHOICES_FILE)
    print(f'選び直しの記憶: {len(choices)} 件')
    print('  ※ ここに記録があると、補正エンジンとは別に'
          '表示側で語が置き換わります。')
except Exception as e:
    print(f'選び直しの記憶: 読み込めず ({e})')

print()
print('=' * 70)
print('実際に通った道筋')
print('=' * 70)

for text, neighbor_lines in TEST_CASES:
    print()
    print(f'[{text}]')
    nearby = []
    for nl in neighbor_lines:
        for tok in tokenize_fn(nl):
            if len(tok[0]) >= 2:
                nearby.append(tok[0])
    log = C.trace_on()
    try:
        result = C.correct_line(text, store, tokenize_fn,
                                find_known_readings_flex,
                                decisions=decisions,
                                context_vec=context_vec,
                                dict_index=dict_index,
                                nearby_words=nearby)
    except Exception:
        import traceback
        C.trace_off()
        print('  補正でエラー:')
        traceback.print_exc()
        continue
    C.trace_off()
    if not log:
        print('  （かな連続の切り出しに掛からず、'
              'この経路には入っていません）')
    for stage, detail in log:
        print(f'  [{stage}] {detail}')
    mark = '変化' if result['changed'] else '無変化'
    print(f'  => [{mark}] {result["corrected"]!r}')
    if result['details']:
        print(f'     内訳: {result["details"]}')
    if result['unsure_spans']:
        print(f'     色だけ付けた範囲: {result["unsure_spans"]}')

print()
print('=' * 70)
print('語彙の状態（判断材料）')
print('=' * 70)
for reading in ['ていじ', 'せっそう', 'すぴーど', 'かいだん', 'あんない',
                'はいち', 'かーそる', 'いち', 'こーど', 'ぼたん',
                'ありえない', 'てぃぶじ']:
    entries = store.lookup(reading)
    if entries:
        desc = ', '.join(f'{e["surface"]}({e["count"]}回)' for e in entries)
    else:
        desc = '(語彙に無い)'
    print(f'  {reading:10s} -> {desc}')

print()
print('診断終了')
