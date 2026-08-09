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
"""

import sys

import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

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
r = C.correct_line('もじにゅうりょく', store, tokenize_fn,
                   find_known_readings_flex)
print(f'補正結果: {r["corrected"]!r}')

if not r['corrected']:
    print('[NG] 補正結果が空でした')
    sys.exit(1)
if not r['changed']:
    print('[NG] 誤打が補正されませんでした（期待: もじにゅうりょく）')
    sys.exit(1)

print('[OK] 補正エンジンは正しく動作しています')
