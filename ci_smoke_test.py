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

# **同梱の表が読めているか**（項目48-DK・2026-08-15）。
#
# `familiarity.json`（書籍での使われぶり・UniDic 由来）と
# `kanji_onkun.json`（漢字の音訓）は **`.py` ではない同梱物**。
# どちらの読み込み側も「無くても動く」造りにしてあるので、
# **落ちても何も起きない**。実際、
#
#   - `correctnote.spec` の `datas` に入っておらず、
#     **exe には最初から入っていなかった**
#   - `freshstate.py` は `*.py` だけを写すので、
#     **初期状態の測定でも毎回落ちていた**
#
# という取りこぼしを2026-08-15に見つけた。
# **静かに落ちるものは、声を出させる。**
# **在るのに読めていないときだけ赤くする。**
# ファイルそのものが無いのは、うにさん待ちの持ち越し
# （README_SNAPSHOT の「うにさん待ちのもの 3」）であって、
# こちらが CI を止めてよい話ではない。**声は出す。**
#
# **見張る相手の名簿は `bundle_manifest.py` ただ1つ**（項目48-GS）。
# ここに書き写すと、spec に足したものをこちらに足し忘れる
# ——実際、spec と ci と freshstate で3つに分かれていた。
import os as _os

import bundle_manifest as _bm

_here = _os.path.dirname(_os.path.abspath(__file__))

for _item in _bm.ITEMS:
    _there = _os.path.exists(_os.path.join(_here, _item.name)) \
        or _os.path.exists(_item.name)
    if not _item.module:
        # 読み込み側のいない同梱物（説明書・NOTICE）は、在るかだけ見る
        print(f'[OK] 同梱物 {_item.name} が在る' if _there
              else f'!! {_item.name} が**入っていない**。{_item.why}')
        continue
    try:
        _ok = __import__(_item.module).available()
    except Exception as _e:
        print(f'[NG] {_item.name} の読み込みで落ちた: {_e}')
        sys.exit(1)
    if _ok:
        print(f'[OK] 同梱の表 {_item.name} が読めている')
    elif _there:
        print(f'[NG] **{_item.name} は在るのに読めていない**'
              f'（中身が壊れている）')
        sys.exit(1)
    else:
        print(f'!! {_item.name} が**入っていない**。'
              f'この表に頼る機能は静かに効かなくなる')
        print(f'!! （{_item.why}）')

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
