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
    # **助詞のトークンで区切る**（項目48-PI・2026-09-03・うにさんの問い
    # 「`かいすせき` は解析に正しく補正されます。`かいすせきがおわった` は
    #   補正されません。**`がおわった` の品詞判定は正しいです**」）。
    # 解析（janome）が要るので、ここ（ci_smoke）で見張る。
    # **ここは初期語彙だけ**（索引も文脈も差していない）ので、
    # 直る先は**読みまで**（`かいせき`）。実機と初期状態の写しでは
    # そこから `解析` まで進む。切る前は `かいすせきがおわった` の
    # まま動かない（`CN_PSPLIT=0` で確かめられる）。
    ('かいすせきがおわった', 'かいせきがおわった',
     '助詞のトークンで区切る（48-PI）'),
    ('かいすせきにいく', 'かいせきにいく', '同上（に・格助詞）'),
    # **余分な隣のキーは①が立つ塊だけ**（項目48-PL(b')・2026-09-04・
    # うにさんの正し「正しい文が異様と判定されているのが問題」）。
    # `解す咳` は動詞基本形＋名詞の直付き＝品詞のつながりが異様（①）
    # なので、`かいすせき` の `す`（い の隣のキー）を落とす手まで開く。
    # ①が立たない塊（下の `糸を察して`）には、この手は走らない。
    ("解す咳が終わった", "解析が終わった",
     "余分な隣のキーは①が立つ塊だけ（48-PL(b')）"),
    # `糸を察して` は名詞＋を＋て形＝正しい品詞の並び（①が立たない）。
    # 直るのは同音の `糸 → 意図` だけで、`察して` が `さして` に
    # 壊れないこと（2026-09-03 に無条件の extra_key が壊した形）。
    ('糸を察して', '意図を察して',
     "①が立たない塊に余分な隣のキーの手は走らない（48-PL(b')の守り）"),
    # **カタカナのサ変名詞に接尾 語 は付かない**（項目48-PQ・2026-09-04）。
    # 同じ読みで動作の名詞に付く接尾は 後（スクロール後・保存後）。
    ('スクロール語の見えた', 'スクロール後の見えた',
     'カタカナのサ変名詞＋語 → 後（48-PQ）'),
    # **異様の対の範囲だけを読みで置き換える受け皿**（項目48-PO）。
    # 行頭の係助詞に地名が直付き（①）→ 開いた読みに手（み を落とす）
    # → 表記には組めないが読みが文法で説明が付く → 対の範囲だけ読みで
    ('も水戸に戻ります', 'もとに戻ります',
     '異様の対の範囲だけを読みで置き換える（48-PO）'),
    # **読みの立たないカタカナ断片は塊に含める**（項目48-PT）。
    # 48-HU の守りを「読みが立つカタカナ語に接しているとき」に絞ったら、
    # 48-HU の説明にあった反例そのものが直るようになった
    ('文字乳リュク', '文字入力',
     '読みの立たないカタカナ断片は塊に含める（48-PT）'),
    # **壊れた形の見本の並記に引きずられない**（項目48-PX・2026-09-04）。
    # うにさんが不具合を `X → Y` と書き残した行では、壊れた側 Y が
    # 「文字通りの並記」になる。`察して`（連用形＋接続助詞）は
    # できあがった活用列なので触らず、直るのは 糸→意図 だけ。
    ('糸を察して → 意図をさして', '意図を察して → 意図をさして',
     '見本の並記があっても、できあがった活用列は壊さない（48-PX）'),
    # ★★ **回数を廃したあとも `すきにん` は `確認` へ**
    # （項目48-QG'・2026-09-05）。`確認` と `新任` は同梱の費用表で
    # **どちらも 101 で同点**なので、費用だけで裁くと表記の字コード順で
    # `新任` に倒れる（移行したあとの実機メモで実際に出た）。
    # 費用が同点のときは**段**（`kango_tier`・確認=1／新任=2）で決める。
    # **ここは初期語彙だけ**（索引も文脈も差していない）ので、
    # かなの側は**読みまで**（`かくにん`）。大事なのは `しんにん`
    # （＝新任）に倒れないこと。
    ('すきにん', 'かくにん', '同点は段で決める（確認 段1 ／ 新任 段2）'),
    ('好き任', '確認', '開いた読みから、段のいちばん高い語へ'),
    # 48-SC（2026-09-06）: 語の列として組み直す道。余分な隣のキー（す は
    # い の隣）を落とし、解析（solid）＋でした
    ('かいすせきでした', '解析でした', '語の列として組み直す（48-SC）'),
]

# 正しく打てているので、触ってはいけない例。
KEEP_CASES = [
    'もじにゅうりょく',
    'せいかくせい',
    # **48-PI で切ってはいけない形**（2026-09-03）:
    'ほせいがきかない',      # 左が3字（`ほせい`）＝連続の最短より短い
    'ちゅうがくにいく',      # `ちゅうがく` は1トークン＝`が`は助詞にならない
    'これはたんほです',      # 右が完結していない（紫のまま・直さない）
    # `かいすせきでした` は 48-PI の「切らない」を見る例だったが、
    # 48-SC（語の列として組み直す道を起こした・2026-09-06）で
    # `解析でした` に**正しく直る**ようになったので、FIX_CASES へ移した
    # **48-PL(b') で触ってはいけない形**（2026-09-04）:
    '書く本が多い',          # 動詞基本形＋名詞だが、直し先が無い＝動かない
    'ひとつ前より前も…',    # 名詞の列＝①が立たない（extra_key を開かない）
    # **48-PQ で触ってはいけない形**（2026-09-04）:
    'カタカナ語の補正',      # 頭がサ変でない（カタカナ＝名詞:一般）
    'ドイツ語を話す',        # 言語名（頭は固有名詞）
    '検索語を入れる',        # 漢語のサ変＋語は正しい語（表では守れない）
    # **48-PK の的の形**（直し先 かなで に吸い込まれない。初期は紫だけ）:
    'かなちでのほせい',
    # **48-PO で触ってはいけない形**（係助詞・地名の正しい文）:
    '私も東京に行きます',
    'これも水戸の名物です',
    # **48-PT で触ってはいけない形**（読みが立つカタカナ語に接している）:
    'ソフトウエアの更新',
    # **48-PY で触ってはいけない形**（真ん中の より は働いている格助詞。
    # 見本の並記 `人前より前も…` があっても より→よ に書き換えない）:
    'ひとつ前より前も… → 人前より前も…',
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
        _mod, _, _fn = _item.module.partition(':')
        _ok = getattr(__import__(_mod), _fn or 'available')()
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
