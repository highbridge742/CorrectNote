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
CI（GitHub Actions）用の動作確認スクリプト。

画面（tkinter）は CI 環境に無いので確認できないが、
実際の janome を使って補正エンジンが動くことは確認できる。
tests_mock.py はモックの分割器を使うため、これとは別に、
本物の janome を使った経路が壊れていないかをここで見る。

    python ci_smoke_test.py

代表的な誤打が直ること、および正しく打てた行を
壊さないことの両方を確認する。
"""

import sys

# CI の Windows ランナーでは、標準出力が端末ではなくパイプに
# つながるため、Python が出力の文字コードを cp1252 などの
# 「日本語を表せない符号化」と判断することがある。その状態で
# 日本語を print すると UnicodeEncodeError で異常終了し、
# 補正エンジンには何の問題も無いのに CI が赤くなる。
# ここで UTF-8 に固定しておく（他のモジュールを読み込む前に行う）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

# (入力, 期待する補正結果, 説明)
# 直ってほしい代表例。誤打の種類ごとに1件ずつ。
FIX_CASES = [
    ('もじにゆうりょく', 'もじにゅうりょく', '小書き（ゅ）の打ち忘れ'),
    ('もじにゅうりよく', 'もじにゅうりょく', '小書き（ょ）の打ち忘れ'),
    ('たんこ゛のつながり', 'たんごのつながり', '濁点が離れて入力された'),
    ('md@i(4l)h', '文字入力', '日本語入力オフのままのかな打ち'),
    ('mojinyuuryoku', '文字入力', '日本語入力オフのままのローマ字打ち'),
]

# 正しく打てているので、触ってはいけない例。
KEEP_CASES = [
    'もじにゅうりょく',
    'せいかくせい',
]

print('janome を使った補正エンジンの動作確認')

try:
    from janome.tokenizer import Tokenizer
    Tokenizer()
    print('[OK] janome の読み込みに成功')
except Exception as e:
    print(f'[NG] janome の読み込みに失敗: {e}')
    sys.exit(1)

store = VocabularyStore()
added = load_seed(store)
print(f'[OK] 初期語彙を投入: {added} 件')

tokenize_fn = C.make_tokenizer(store)
failed = 0


def run(text):
    return C.correct_line(text, store, tokenize_fn, find_known_readings_flex)


print('\n--- 直ってほしい誤打 ---')
for text, expected, why in FIX_CASES:
    got = run(text)['corrected']
    if got == expected:
        print(f'[OK] {text!r} -> {got!r}（{why}）')
    else:
        failed += 1
        print(f'[NG] {text!r} -> {got!r} / 期待 {expected!r}（{why}）')

print('\n--- 触ってはいけない行 ---')
for text in KEEP_CASES:
    got = run(text)['corrected']
    if got == text:
        print(f'[OK] {text!r} はそのまま')
    else:
        failed += 1
        print(f'[NG] {text!r} が {got!r} に変えられた')

print()
if failed:
    print(f'[NG] {failed} 件が期待どおりではありませんでした')
    sys.exit(1)

print('[OK] 補正エンジンは正しく動作しています')
