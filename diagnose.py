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
実機（janome あり）での補正動作を診断する。

補正が効かない／誤補正される原因を特定するために、
janome が実際にどう分割しているかと、
補正エンジンが各段階で何を判断しているかを表示する。

    py diagnose.py > shindan.txt

出力されたファイルの内容を共有してください。
（画面だと長すぎて見切れるため、ファイルに落とすことを推奨します）
"""

import os

VOCAB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'vocabulary.json')

# ここに、うまくいかない入力を書いてください
TEST_CASES = [
    'もじにゅうりょく',
    'もじなゅうりょく',
    'もじにうりょく',
    'もじにゅうのりょく',
    'もじにゅりうょく',
    'ネイルも髪も推し仕様にした',
    'ヤバい',
    'サクッと焼かれて',
    'MTGスタン率直に言って',
    '歌とオケ',
    '耳コピ',
    'ないです',
    # --- 実機で報告された「直らない」ケース ---
    '新規チャットに映るので',
    '時ッ層',
    '待ち外の補正',
    '売った文字',
    '糸を察して',
    'タン具の繋がり',
    '高後の綱切り',
    'タン子の繋がり',
    '単語の綱刷り',
    '単語ま繋がり',
    # --- 実機で報告された「正しい文が壊れる」ケース ---
    # モック環境では再現しないため、janome の実分割を見る必要がある
    'チェックがうまく動いてない',
    '「文字の入力」にします。',
    '判断をします。',
    '単語のつながりのほうが文脈が合う',
    '漢字を平仮名にひらいたり、ひらがなを漢字にしたり、',
    '一回り小さくします',
    'Pythonを入れていないPC',
]

print('=' * 70)
print('かな入力メモ帳 診断')
print('=' * 70)

try:
    from janome.tokenizer import Tokenizer
    _t = Tokenizer()
    print('janome: あり')
except Exception as e:
    _t = None
    print(f'janome: なし ({e})')

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex

store = VocabularyStore(VOCAB_FILE)
print(f'語彙の総数: {len(store.to_list())} 件')
print()

print('=' * 70)
print('1. janome の実際の分割（品詞の細分類と読みの有無）')
print('=' * 70)
if _t:
    for text in TEST_CASES:
        print(f'[{text}]')
        for tok in _t.tokenize(text):
            reading = getattr(tok, 'reading', '*')
            known = (reading != '*' and reading != '')
            print(f'  {tok.surface!r:14s} {tok.part_of_speech:28s} '
                  f'reading={reading!r:12s} 辞書にある={known}')
        print()
else:
    print('janome が無いため省略')
    print()

print('=' * 70)
print('2. 補正エンジンが受け取るトークン')
print('=' * 70)
tokenize_fn = C.make_tokenizer(store)
for text in TEST_CASES:
    print(f'[{text}]')
    for surface, pos, reading, start, end, has_reading in tokenize_fn(text):
        print(f'  {surface!r:14s} pos={pos:20s} reading={reading!r:12s} '
              f'辞書にある={has_reading}')
    print()

print('=' * 70)
print('3. 補正対象として選ばれた範囲')
print('=' * 70)
for text in TEST_CASES:
    toks = tokenize_fn(text)
    spans = C.find_editable_spans(text, toks)
    runs = C.find_hiragana_runs(text)
    print(f'[{text}]')
    print(f'  ひらがな連続: {runs}')
    print(f'  補正対象の語: {[(s, e, sf) for s, e, sf, r, k in spans]}')
    print()

print('=' * 70)
print('4. 誤打の候補探索（読みから既知語に届くか）')
print('=' * 70)
for text in TEST_CASES:
    for start, end, run in C.find_hiragana_runs(text):
        found = find_known_readings_flex(run, store, max_dist=1.6, max_edits=2)
        print(f'[{run}] -> {found[:3]}')
print()

print('=' * 70)
print('5. 最終的な補正結果')
print('=' * 70)
for text in TEST_CASES:
    r = C.correct_line(text, store, tokenize_fn, find_known_readings_flex)
    mark = '変化' if r['changed'] else '    '
    print(f'{mark} {text}')
    if r['changed']:
        print(f'     => {r["corrected"]}')
        print(f'     詳細: {r["details"]}')
print()

print('=' * 70)
print('6. 語彙に誤字が混ざっていないかの確認')
print('=' * 70)
print('（自動学習で誤変換語を覚えてしまうと、その誤りが直せなくなります）')
checks = ['もじ', 'にゅうりょく', 'もじにゅうりょく', 'ねいる', 'すたん',
          'なおす', 'おし', 'やばい']
for reading in checks:
    entries = store.lookup(reading)
    if entries:
        desc = ', '.join(f'{e["surface"]}(count={e["count"]})' for e in entries)
    else:
        desc = '(未登録)'
    print(f'  {reading:16s} -> {desc}')
print()
print('診断終了')
