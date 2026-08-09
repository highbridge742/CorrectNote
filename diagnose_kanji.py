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
「素帰任」「分割時」のような、漢字列の推測パス（kanji_guess.py）が
実機で正しく動いているかを段階的に診断する。

    py diagnose_kanji.py > kanji_shindan.txt

出力されたファイルの内容を共有してください。
どの段階で期待どおりの結果が出ていないかが分かれば、
原因を特定できます。
"""

import os

VOCAB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'vocabulary.json')

TEST_CASES = [
    '素帰任',
    '分割時',
    '分割',
    'タン子',
    '見切れ魔訶',
    '乳リュク',
]

print('=' * 70)
print('漢字列の推測パス（kanji_guess.py）診断')
print('=' * 70)

# --- 0. モジュール自体が読み込めるか ---
print()
print('--- 0. モジュールの読み込み ---')
try:
    import kanji_guess
    print('[OK] kanji_guess のインポートに成功')
    print(f'     ファイルの場所: {kanji_guess.__file__}')
    has_strangeness = hasattr(kanji_guess, 'strangeness')
    print(f'     strangeness 関数がある: {has_strangeness}')
    if not has_strangeness:
        print('[NG] strangeness が無い＝古いバージョンの'
              'kanji_guess.py が読み込まれています。')
except Exception as e:
    print(f'[NG] kanji_guess の読み込みに失敗: {e}')
    raise SystemExit(1)

try:
    import kanji_readings
    print(f'[OK] kanji_readings のインポートに成功 '
          f'(登録漢字数: {len(kanji_readings.KANJI_READINGS)})')
    print(f'     ファイルの場所: {kanji_readings.__file__}')
except Exception as e:
    print(f'[NG] kanji_readings の読み込みに失敗: {e}')

try:
    import corrector as C
    print('[OK] corrector のインポートに成功')
    print(f'     ファイルの場所: {C.__file__}')
    import inspect
    sig = inspect.signature(C.correct_line)
    print(f'     correct_line の引数: {list(sig.parameters.keys())}')
    has_dict_index = 'dict_index' in sig.parameters
    print(f'     dict_index 引数がある: {has_dict_index}')
except Exception as e:
    print(f'[NG] corrector の読み込みに失敗: {e}')
    raise SystemExit(1)

try:
    from janome_import import HAS_JANOME
    print(f'[情報] janome: {"あり" if HAS_JANOME else "なし"}')
except Exception as e:
    print(f'[情報] janome_import の読み込みに失敗（janome 無しとして続行）: {e}')
    HAS_JANOME = False

from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

store = VocabularyStore(VOCAB_FILE)
print(f'[情報] 読み込み直後の語彙数: {len(store.to_list())} 件')

added = load_seed(store)
print(f'[情報] load_seed() で追加された件数: {added} 件')
print(f'[情報] 最終的な語彙の総数: {len(store.to_list())} 件')
has_bunkatsu = bool(store.lookup('ぶんかつ'))
print(f'     「分割」が語彙にある: {has_bunkatsu}')
has_mikire = bool(store.lookup('みきれます'))
print(f'     「見切れます」が語彙にある: {has_mikire}')
if added > 0:
    store.save()
    print(f'[情報] vocabulary.json に保存しました'
          f'（次回このスクリプトを実行すると追加0件になるのが正常）')

tokenize_fn = C.make_tokenizer(store)

# --- 1. 塊の切り出し ---
print()
print('--- 1. 塊の切り出し（find_kanji_runs） ---')
for text in TEST_CASES:
    runs = kanji_guess.find_kanji_runs(text)
    print(f'[{text}] -> {[r[2] for r in runs]}')

# --- 2. 異様さの判定 ---
print()
print('--- 2. 異様さの判定（strangeness） ---')
if hasattr(kanji_guess, 'strangeness'):
    for text in TEST_CASES:
        try:
            s = kanji_guess.strangeness(text, store)
            print(f'[{text}] 異様さ={s}')
        except Exception as e:
            print(f'[{text}] エラー: {e}')
else:
    print('（strangeness が無いため省略。古いバージョンの可能性）')

# --- 2.5 異様さが低く出る場合、どの部分文字列が「既知語」と
#     見なされているのかを名指しする。
print()
print('--- 2.5 なぜ異様と判定されないか（既知語とみなされた部分） ---')
if hasattr(kanji_guess, '_is_solid_known_word'):
    for text in TEST_CASES:
        n = len(text)
        hits = []
        if n == 2:
            if kanji_guess._is_solid_known_word(text, store):
                hits.append(text)
        else:
            for size in range(n - 1, 1, -1):
                for i in range(0, n - size + 1):
                    part = text[i:i + size]
                    if part == text:
                        continue
                    if kanji_guess._is_solid_known_word(part, store):
                        hits.append(part)
        if hits:
            detail = []
            for h in hits:
                reading = None
                try:
                    reading = store.reading_of(h)
                except Exception:
                    pass
                count = None
                if reading:
                    for e in store.lookup(reading):
                        if e.get('surface') == h:
                            count = e.get('count')
                detail.append(f'{h}(読み={reading}, count={count})')
            print(f'[{text}] 既知語とみなされた部分: {", ".join(detail)}')
        else:
            print(f'[{text}] 既知語とみなされた部分: なし')
else:
    print('（_is_solid_known_word が無いため省略。古いバージョンの可能性）')

# --- 3. 読みへの復元 ---
print()
print('--- 3. 読みへの復元（reading_combos） ---')
for text in TEST_CASES:
    combos = kanji_guess.reading_combos(text)
    print(f'[{text}] -> {combos[:6]}')

# --- 4. 推測（suggest_for_run） ---
print()
print('--- 4. 推測（suggest_for_run） ---')
for text in TEST_CASES:
    try:
        got = kanji_guess.suggest_for_run(
            text, store, find_known_readings_flex,
            tokenize_fn=tokenize_fn, at_sentence_end=True)
        print(f'[{text}] -> {got}')
    except Exception as e:
        import traceback
        print(f'[{text}] エラー:')
        traceback.print_exc()

# --- 5. 補正エンジン全体を通して ---
print()
print('--- 5. 補正エンジン全体（correct_line） ---')
for text in TEST_CASES:
    try:
        r = C.correct_line(text, store, tokenize_fn, find_known_readings_flex)
        mark = '変化' if r['changed'] else '無変化'
        print(f'[{mark}] {text!r} -> {r["corrected"]!r}')
    except Exception as e:
        import traceback
        print(f'[{text}] correct_line でエラー:')
        traceback.print_exc()

print()
print('診断終了')
