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
for text in ('言っちゃわない', '読んじゃいます', '食べちゃおう', '飲んじゃって'):
    result = run(text)
    if result['corrected'] != text or result.get('unsure_spans') or result.get('odd_spans'):
        failed += 1
        print('[NG] 口語縮約', text, result)

for text in ('寒ぃ日だ', '可愛ぃ猫がいる', '小さいぁを書く', 'ぃを入力する', 'ゅを削除する'):
    result = run(text)
    assert result['corrected'] == text, (text, result)
    assert not result.get('odd_spans'), (text, result)
    assert not result.get('unsure_spans'), (text, result)

for text in KEEP_CASES:
    got = run(text)['corrected']
    if got == text:
        print(f'[OK] {text!r} はそのまま')
    else:
        failed += 1
        print(f'[NG] {text!r} が {got!r} に変えられた')

# 48-VK/VL: seedだけでは見えない、初回辞書取り込み後の挙動も測る。
from janome_import import import_from_janome
initial_store = VocabularyStore()
load_seed(initial_store)
import_from_janome(initial_store)
initial_tok = C.make_tokenizer(initial_store)
from vocabulary import dup_repair_enabled
review_keep = [
    '初めでした。', 'これが初めでした。', '新しい生活の初めでした。',
    '初めでしたが、楽しめました。', '眺めでした。', '控えでした。',
    '初めてでした。', '強めでした。', '見ていませんでした。',
]
if not dup_repair_enabled():
    review_keep += ['クリッック', 'ファイイル', 'プラネタリウウム', 'keybooard']
for method in ('kana', 'romaji'):
    for text in review_keep:
        got = C.correct_line(text, initial_store, initial_tok,
                             find_known_readings_flex, input_method=method)['corrected']
        if got != text:
            failed += 1
            print(f'[NG] 48-VK/VL {method}: {text!r} -> {got!r}')
print('[確認] 初期状態の文法と重複設定を両入力方式で検査')

# 48-VO: 品詞・単位の読み直しを実際の Janome と補正結果の両方で検査。
import morphology as _mpos
_pos_clean = ('電動爪切り', '自動爪切り', '超軽量爪切り', '十六個',
              'お湯よりに感じました', '東京よりに住む', '爪切りを使う',
              '爪を切り、手を洗う', 'お湯より熱い', '見つかるようになる')
for method in ('kana', 'romaji'):
    for text in _pos_clean:
        result = C.correct_line(text, initial_store, initial_tok,
                                find_known_readings_flex, input_method=method)
        if result['corrected'] != text or result.get('odd_spans'):
            failed += 1
            print('[NG] 48-VO', method, text, result['corrected'], result.get('odd_spans'))
for text, surface, expected in (
        ('お湯よりに感じました','より','名詞'),
        ('お湯より熱い','より','助詞'),
        ('東京よりの便り','より','助詞'),
        ('電動爪切り','爪切り','名詞'),
        ('爪を切り、手を洗う','切り','動詞'),
        ('十六個','十六','名詞')):
    matches = [t for t in _mpos.tokenize(text) if t.surface == surface]
    if len(matches) != 1 or matches[0].pos != expected:
        failed += 1
        print('[NG] 48-VO POS', text, surface, expected)
print('[確認] 48-VO 文脈の品詞・単位と自然文の印を検査')

# 48-VQ: 未然形＋接尾動詞の受身・使役を、本文の補正まで通す。
for method in ('kana', 'romaji'):
    for text in ('名詞で示されるものが存在しないことを表す限定詞である。構文で表される。',
                 '示される', '書かせられる', '読まされる', '食べさせる',
                 '文書に示されていないことを確認します。'):
        result = C.correct_line(text, initial_store, initial_tok,
                                find_known_readings_flex, input_method=method)
        if result['corrected'] != text or result.get('odd_spans'):
            failed += 1
            print('[NG] 48-VQ', method, text, result['corrected'], result.get('odd_spans'))
for text, expected in (('示される',True), ('書かせられる',True),
                       ('示すれる',False), ('示されるない',False),
                       ('書かれるます',False), ('書かせるられる',False)):
    if C._chunk_is_intact(text, initial_tok) != expected:
        failed += 1
        print('[NG] 48-VQ 活用の入口', text)
print('[確認] 48-VQ 受身・使役と不正な活用の反例を検査')

# 48-VR: 普通名詞＋派生接尾辞と、記号付きの既知英語を実データで検証。
for method in ('kana','romaji'):
    for text in ('規則性','周期性','規則的','共通化','name:example','type:integer','status:unknown'):
        result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method=method)
        if result['corrected']!=text or result.get('odd_spans'):
            failed+=1
            print('[NG] 48-VR',method,text,result['corrected'],result.get('odd_spans'))
for text in ('規則性','周期性','規則的'):
    if not C._chunk_is_intact(text,initial_tok):
        failed+=1
        print('[NG] 48-VR 派生語の入口',text)
print('[確認] 48-VR 派生語と英字の構造を検査')




# 48-VS: 述語用法と連体用法を実解析・全補正経路で確認する。
for method in ('kana', 'romaji'):
    for text in ('同じだけの', '同じくらいの量', '同じぐらい食べる',
                 '同じにする', '同じです', '同じなのに', '同じ本', '同じようにする'):
        result = C.correct_line(text, initial_store, initial_tok,
                                find_known_readings_flex, input_method=method)
        if result['corrected'] != text or result.get('odd_spans'):
            failed += 1
            print('[NG] 48-VS', method, text, result['corrected'], result.get('odd_spans'))
print('[確認] 48-VS 述語用法と連体用法を検査')

# 48-VU: 形容動詞をイ形容詞として活用させない。実辞書の全品詞を使う。
import pos_grammar as _pg_vu
for word, expected in (('きれい',False), ('嫌い',False), ('よい',True), ('すい',True)):
    if _pg_vu._possible_i_adjective(word) != expected:
        failed += 1
        print('[NG] 48-VU 形容詞の種類',word)
for text, expected in (('きれくない',False), ('きれいだった',True),
                       ('あつかった',True), ('よかった',True)):
    if _pg_vu.explain_kana_run(text) != expected:
        failed += 1
        print('[NG] 48-VU 活用の接続',text)
for text in ('きれいだった','嫌いだった','美しかった','読みづらかった'):
    for method in ('kana','romaji'):
        result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method=method)
        if result['corrected'] != text or result.get('odd_spans') or result.get('unsure_spans'):
            failed += 1
            print('[NG] 48-VU 正常な活用',method,text,result)
print('[確認] 48-VU 形容動詞とイ形容詞の活用を検査')

# 48-VY: 辞書の形容動詞語幹から名詞化し、助詞へ接続する。
for stem, run, expected in (('異様','さについて',True), ('便利','さの',True),
                            ('静','かさの',True), ('作業','さの',False),
                            ('便利','さをに',False)):
    if _pg_vu.explain_kana_run(run, after_kanji=True, kanji_stem=stem,
                             no_words=True) != expected:
        failed += 1
        print('[NG] 48-VY 名詞化',stem,run)
for text in ('異様さについて考える','便利さについて考える','不自然さについて考える'):
    for method in ('kana','romaji'):
        result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method=method)
        if result['corrected'] != text or result.get('odd_spans') or result.get('unsure_spans'):
            failed += 1
            print('[NG] 48-VY 正常な名詞化',method,text,result)
print('[確認] 48-VY 名詞化と助詞の接続を検査')

# 48-VZ: 画面の未補正・誤補正を初期状態で直接検証する。
from dict_index import DictIndex
idx = DictIndex(cache_path=None)
idx.ensure_built()
for text, expected in (('さいたいか','最大化'), ('さいでいか','最大化'),
                       ('きょでいか','巨大化'), ('追い焚き可能','追い焚き可能')):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=expected or r.get('odd_spans') or r.get('unsure_spans'):
            failed+=1;print('[NG] 48-VZ',method,text,r)
for text in ('こうりつか','じどうか','さいかいか','しょうせい'):
    if C._kana_run_hand_fixes(text,initial_store,idx):
        failed+=1;print('[NG] 48-VZ 正常な語を読み替えた',text)
for text, expected in (('こうりさか','効率化'),
       ('小売り坂\tこうりさか ⇒ こうりつか\t効率化','効率化'),
       ('居で以下\tきょでいか ⇒ きょだいか\t巨大化','巨大化')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected'].split('\t')[0] != expected:
        failed+=1;print('[NG] 48-VZ 再解析が補正を覆した',text,r['corrected'])
if not C._arrow_respell('映します ⇒ 移します', initial_tok, idx):
    failed+=1;print('[NG] 48-VZ 元からある同音の指定を失った')
_source_token = C._CORRECTION_SOURCE.set('こうりさか ⇒ こうりつか')
try:
    if C._arrow_respell('効率化 ⇒ 効率か', initial_tok, idx):
        failed+=1;print('[NG] 48-VZ 補正が作った矢印を指定にした')
finally:
    C._CORRECTION_SOURCE.reset(_source_token)
if C._CORRECTION_SOURCE.get() is not None:
    failed+=1;print('[NG] 48-VZ 最初の本文が残っている')
# 接尾辞付きの候補だけが普通の一語を押しのけない。
for text, expected in (('いゅうせい','修正'),('こょうじ','表示'),
                       ('けんさか','検索'),('しゃしか','写真'),('だんだか','段々')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected'] != expected:
        failed+=1;print('[NG] 48-VZ 普通の一語との比較',text,r['corrected'])
print('[確認] 48-VZ 画面の実例と再解析を検査')

# 記号の連続と、数量＋括弧内の換算表記は完成した入力。
for text in ('使用・・・', '（検討・・）', '長さ12cm（120mm）です',
             '容量１Ｌ（１０００ｍｌ）です', '150mg（300IU）'):
    for method in ('kana', 'romaji'):
        r = C.correct_line(text, initial_store, initial_tok, find_known_readings_flex,
                           input_method=method, dict_index=idx)
        if r['corrected'] != text:
            failed += 1
            print('[NG] 記号・数量の保持', method, text, r['corrected'])
print('[確認] 中黒の連続・単位つき数量を両入力方式で検査')


# 直前の活用状態から助動詞へ接続する。文節頭への戻りで不正な接続を許さない。
for state, text, expected in (('R','ましたら',True), ('R','ませんでした',True),
                               ('MZ','ましたら',False), ('R','のました',False)):
    if _pg_vu.explain_kana_run(text, no_words=True, initial_state=state) != expected:
        failed += 1
        print('[NG] 直前の活用状態', state, text)
for text, expected in (('修正しらた','修正したら'), ('保存たしら','保存したら'),
                       ('読みましらた','読みましたら'), ('泳ぎましらた','泳ぎましたら')):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected'] != expected:
            failed+=1;print('[NG] 活用の順序違い',method,text,r['corrected'])
for text, expected in (('検査さらた','検査された'), ('変更さーた','変更された')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected'] != expected:
        failed+=1;print('[NG] 活用の隣接キー',text,r['corrected'])
for text in ('対象例','計算例','安全かどうか','読みましたら',
             '泳ぎの速さ','連鎖させていく','ひなた'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected'] != text or r.get('odd_spans') or r.get('unsure_spans'):
            failed+=1;print('[NG] 正常な接続と一語の保持',method,text,r)
# 従来のかな窓はこの2つに unsure を出す。今回の新判定で odd を増やさない。
for text in ('泳ぎましたら','けいたいそ'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected'] != text or r.get('odd_spans'):
            failed+=1;print('[NG] 活用と読みを壊した',method,text,r)
print('[確認] 活用・名詞接尾・機能語の保持を検査')


# 連体形の後ろの形式名詞は、品詞解析と機能語の境界をそろえて復元する。
for text, expected in (('見つかるよわぅになる','見つかるようになる'),
                       ('分かるゆうになる','分かるようになる'),
                       ('読むようらなる','読むようになる')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected'] != expected:
        failed+=1;print('[NG] 形式名詞の復元',text,r['corrected'])
for text in ('泳ぎましたら','ひなたを確認','これはひなたです',
             '/た',
             '読むようになる','動くことになる','見るはずだった'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected'] != text or r.get('odd_spans'):
            failed+=1;print('[NG] 一語と機能語の正常例',method,text,r)
        if text=='泳ぎましたら' and r.get('unsure_spans'):
            failed+=1;print('[NG] 動詞の途中からの窓',method,text,r)
# 連用形から音便を推測しない。機能語の反証は入口から直接検査する。
for text in ('昨日したゃを見ました。','たでなおさをみます。','やみづきがありました。'):
    if C._inflection_tail_fixes(text,initial_tok,'romaji',idx,initial_store):
        failed+=1;print('[NG] 連用形の過剰推定',text)
from decisions import DecisionStore
_grammar_decisions=DecisionStore()
_grammar_decisions.protect('確認しらた')
_grammar_decisions.reject('わぅ','う')
for text, expected in (('確認しらた、保存しらた','確認しらた、保存したら'),
                       ('見つかるよわぅになる','見つかるよわぅになる')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx,decisions=_grammar_decisions)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 再解析前のユーザー判断',text,r['corrected'])
print('[確認] 形式名詞の境界・送り仮名の窓・ユーザー判断を検査')

# 再解析が前の本文へ戻ったとき、深い再帰でアプリを落とさない。
@C._with_correction_source
def _cycle_probe(text):
    return _cycle_probe('b' if text == 'a' else 'a')
_cycle_result = _cycle_probe('a')
if (_cycle_result['corrected'] != 'a' or not _cycle_result.get('diagnostic_cycle')
        or C._CORRECTION_PATH.get() or C._CORRECTION_SOURCE.get() is not None):
    failed += 1
    print('[NG] 循環の検出・呼び出し状態の破棄')
for text in ('やみづきがありました。','これはじわじじわです。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r.get('diagnostic_cycle'):
        failed += 1
        print('[NG] 活用の判定で再解析が循環した',text)
print('[確認] 再解析の循環を防止')

# 活用経路は全かなの一語の途中を横取りしない。
for text in ('昨日てれくすを見ました。','昨日ふれこすを見ました。','とるこまだを確認しました。'):
    if C._inflection_tail_fixes(text,initial_tok,'kana',idx,initial_store):
        failed+=1;print('[NG] 一語の途中を活用と誤認',text)
for text, expected in (('けいじきがありました。','形式がありました。'),
                       ('そぞろるき、それから相談します。','そぞろあるき、それから相談します。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 窓の途中の語で探索を止めた',text,r['corrected'])
print('[確認] かなの単語と活用末尾の境界を検査')

# 連用形と丁寧語の間の余字。名詞や引用の境界まで切り取らない。
for text, expected in (('入れの真下','入れました'), ('泳ぎのました','泳ぎました'),
                       ('読みのません','読みません'), ('食べのましょう','食べましょう')):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=expected:
            failed+=1;print('[NG] 連用形と丁寧語の余字',method,text,r['corrected'])
for text in ('読みの真下','名入れの真下','「入れ」の真下','読みのます目',
             '読みのまま','飲みの真下にある','話しの真下から見える','起きの真下は暗い'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=text:
            failed+=1;print('[NG] 名詞句の境界を壊した',method,text,r['corrected'])
# 部分文字列を渡す判定は、元の文の後半を知っていると仮定しない。
import oddness as _odd_complete
if _odd_complete.renyou_no_polite_spans('飲みの真下にある',initial_tok('飲みの真下にある'),initial_tok):
    failed+=1;print('[NG] 後ろの助詞を無視した')
if _odd_complete.is_odd_run('飲みの真下',initial_tok,dict_index=idx):
    failed+=1;print('[NG] 断片を行全体として判定した')
print('[確認] 丁寧語の余字と元の文脈の保持')

# 助詞として誤分割された名詞は、文全体の異様を確かめて読みから復元する。
for text, expected in (('もみとに戻ります','もとに戻ります'),
                       ('かもとに戻ります','もとに戻ります'),
                       ('あかとに続きます','あとに続きます'),
                       ('みそとに出ます','外に出ます')):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=expected:
            failed+=1;print('[NG] 名詞と助詞の境界',method,text,r['corrected'])
for text in ('いぬとねことに分けます。','あか、あおとに分けます。',
             'みそとしょうゆとを混ぜます。','名詞と副詞の関係',
             '動詞と側置詞の','2個以下、操作性','2倍以下、操作性','2年以下、操作性'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=text:
            failed+=1;print('[NG] 並列・数量の文脈',method,text,r['corrected'])
for text, expected in (('タブ最大家事に','タブ最大化時に'),
                       ('画面最大家事に','画面最大化時に')):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=expected:
            failed+=1;print('[NG] 名詞直後の複合語',method,text,r['corrected'])
_boundary_decisions=DecisionStore()
_boundary_decisions.protect('もみと')
r=C.correct_line('もみとに戻ります',initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx,decisions=_boundary_decisions)
if r['corrected']!='もみとに戻ります':
    failed+=1;print('[NG] 助詞境界のユーザー保護',r['corrected'])
print('[確認] 名詞と助詞・並列・数量・複合語の境界')

# 使役の短縮形「す」の接続。未然形という名前だけでは一段と五段を区別できない。
for text in ('書かす','読ます','見さす','食べさす','書かせる','食べさせる'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 正しい使役を壊した',text,r['corrected'])
for text in ('食べす','変えす'):
    if C._chunk_is_intact(text,initial_tok):
        failed+=1;print('[NG] 使役の接続を過剰に許した',text)
r=C.correct_line('かげすをみます。',initial_store,initial_tok,find_known_readings_flex,dict_index=idx)
if r['corrected']!='かけすをみます。':
    failed+=1;print('[NG] 不正な活用を完成形として止めた',r['corrected'])
print('[確認] 使役と読点の列挙を検査')

# 読点の列挙は、本文の保護と異様判定が同じ判断を使う。
for text in ('赤、くろとに分けます。','あか、あおとに分けます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,dict_index=idx)
    if r['corrected']!=text or r.get('odd_spans') or r.get('unsure_spans'):
        failed+=1;print('[NG] 列挙の判定と補正が食い違う',text,r)
for text, start in (('昨日、あおとに会いました。',3),('そこ、あおとに会いました。',3)):
    if C._comma_nominal_context(text,start,'あおとに',initial_tok):
        failed+=1;print('[NG] 時間・指示を名詞の列挙とみなした',text)

# 名詞直後でも接尾辞から始まる範囲を、独立した複合語として開かない。
for text in ('原初的構成部分','基本的構成要素','機能的構成単位','一般的構造変化'):
    for method in ('kana','romaji'):
        r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                         input_method=method,dict_index=idx)
        if r['corrected']!=text:
            failed+=1;print('[NG] 接尾辞から語を切り直した',method,text,r['corrected'])

# 異様な長い読みは、正解見本なしで左右を独立に直し、普通名詞2語の
# 自然さで先頭を決める。元から2語として読めるかなは保持する。
for text,expected in (
        ('きょじえかくらん','挙動確認'),
        ('きょじえかくらんを調べます','挙動確認を調べます'),
        ('ログで、きょじえかくらんを行います','ログで、挙動確認を行います'),
        ('きょじえかく乱','挙動確認'),
        ('きょじえかく乱を行います','挙動確認を行います'),
        ('きょどうかくにん','挙動確認'),
        ('きょじんかくにん','巨人確認'),
        ('そうさかくにん','操作確認')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 普通名詞2語の読み直し',text,r['corrected'])
import kango_tier as _kt_split
if (_kt_split.affinity('挙動','確認') != 2
        or _kt_split.affinity('書道','確認') != 0
        or _kt_split.affinity('挙動','撹乱') != 0):
    failed+=1;print('[NG] AIの複合語意味関係')
print('[確認] 正解見本なしで異様な複合語を左右別々に直す')
for text in ('挙動確認を行います','書道撹乱を調べます'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 成立済みの複合語を読み直した',text,r['corrected'])

# 48-WU: 本物の辞書索引を渡した行は、実際に使用可能と報告する。
resource_result=C.correct_line('文章を読みます',initial_store,initial_tok,
    find_known_readings_flex,input_method='kana',dict_index=idx)
resource_diagnosis=resource_result.get('diagnosis',{})
if (resource_result.get('analysis_status')!='complete'
        or resource_diagnosis.get('missing_resources')
        or resource_diagnosis.get('resource_status',{}).get('dictionary_index',{}).get('state')!='available'):
    failed+=1;print('[NG] 実辞書索引の資源状態',resource_diagnosis)
print('[確認] 実辞書索引の資源状態')

# 原文の既知のかな名詞を保持し、異様な後半だけを復元する。
for text,expected in (('かな流力','かな入力'),('カナ流力','カナ入力'),
                      ('かな入力','かな入力'),('かなり有力','かなり有力'),
                      ('カナダ旅行','カナダ旅行')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 既知のかな名詞と後半の復元',text,r['corrected'])
print('[確認] 原文のかな表記を保つ複合語補正')
for text,expected in (('Alt+Tab出ウィンドウ','Alt+Tabでウィンドウ'),
                      ('Ctrl+S出保存','Ctrl+Sで保存'),('Ctrl+S出力','Ctrl+S出力'),
                      ('動詞と側置詞の','動詞と側置詞の'),
                      ('移動フワーと軽快','移動フワーと軽快')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 文脈と格助詞の判定',text,r['corrected'],r['odd_spans'])
print('[確認] 擬音・名詞並列・キー操作の格助詞')
for text,expected in (('しゅどうちょうせい','手動調整'),
                      ('しゅどうにゅうりゅく','手動入力'),
                      ('主導性','主導性'),('非同期性','非同期性'),
                      ('主導権を握る','主導権を握る')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 複合語の意味関係',text,r['corrected'])
print('[確認] 一般語の保持と複合語の意味関係')
for text,expected in (('主同調性','手動調整'),
                      ('主同調性を変更する','手動調整を変更する'),
                      ('副交感性','副交感性'),('主作用性','主作用性'),
                      ('主従属性','主従属性'),('主導性','主導性')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 順位接頭辞と派生元の照合',text,r['corrected'],r['odd_spans'])
print('[確認] 接辞の付加先・複合語の別解')





# 48-XP/XQ: 語尾の機能語と、濁点隣接誤打を名詞句の文脈で復元する。
for text,expected in (
        ('タフ背','タブ'),('タフ背を開く','タブを開く'),
        ('タフ毛','タブ'),('タフ瀬','タブ'),('ラフ背','ラブ'),
        ('いけなかった李','いけなかったり'),
        ('行けなかった李','行けなかったり'),
        ('いけなかった李、できなかった李','いけなかったり、できなかったり'),
        ('できたりできなかった李','できたりできなかったり')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 名詞句と過去語尾の復元',text,r['corrected'],r['odd_spans'])
for text in ('タフな背中','ハード面','ソフト面','ソフト毛','クール便',
             'ラフ絵','ラフ画','ラフ図','ラフ線','いけなかった李さん','いけなかった李が来た',
             'いけなかった李の話','食べた李','読んだ李','李を食べた',
             '「タフ背」という誤入力','「いけなかった李」という誤入力'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 自然な名詞句と名前の保持',text,r['corrected'])
for text in ('タフ背','いけなかった李'):
    protected=DecisionStore();protected.protect(text)
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx,decisions=protected)
    if r['corrected']!=text:
        failed+=1;print('[NG] 文脈補正のユーザー保護',text,r['corrected'])
print('[確認] 名詞句の順位・過去語尾・人名と引用の保持')


# 48-XR/XS: 小書き口語の解析と、サ変の文脈で同音名詞を選ぶ。
for text,expected in (
        ('有線して補正','優先して補正'),('有線しない','優先しない'),
        ('有線すれば','優先すれば'),('有線しました','優先しました'),
        ('よいでしょぅか。有線して補正','よいでしょぅか。優先して補正'),
        ('よいでしょぅか。','よいでしょぅか。'),('そうでしょぅ。','そうでしょぅ。'),
        ('行きましょぅ。','行きましょぅ。'),('行くだろぅ。','行くだろぅ。'),
        ('確認しましょぅか。','確認しましょぅか。'),('食べましょぅね。','食べましょぅね。'),
        ('よいでしょうか。','よいでしょうか。'),('有線を使う','有線を使う'),
        ('優先して補正','優先して補正'),('用船して補正','用船して補正'),
        ('起床して待つ','起床して待つ'),('無効化して','無効化して'),
        ('誤字していた','誤字していた'),('脱字する','脱字する'),
        ('衍字した','衍字した'),('脱文していた','脱文していた'),
        ('誤字を直す','誤字を直す'),('誤字の確認','誤字の確認'),
        ('A列末尾','A列末尾'),('行先頭','行先頭'),('欄末尾','欄末尾'),('欄下部','欄下部'),
        ('お渡しする','お渡しする'),('同梱して送る','同梱して送る')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 助動詞表記とサ変同音',text,r['corrected'],r['odd_spans'])
import explain as _ex_polite
_polite_pos=_ex_polite.pos_lines('よいでしょぅか。',store=initial_store,dict_index=idx)
if any('判定できません' in part for part in _polite_pos):
    failed+=1;print('[NG] 小書き助動詞の品詞説明',_polite_pos)
for text in ('有線して補正',):
    protected=DecisionStore();protected.protect(text)
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx,decisions=protected)
    if r['corrected']!=text:
        failed+=1;print('[NG] サ変同音のユーザー保護',text,r['corrected'])
print('[確認] 口語表記の品詞・サ変の同音選択')

# 48-XV: 実IMEの巻き込み結果も、読みを渡さず単独入力で直す。
for text, expected in (
        ('素画像を保存します。', '画像を保存します。'),
        ('この場所に乗荷物を置きます。', 'この場所に荷物を置きます。'),
        ('画像を保存します。', '画像を保存します。'),
        ('この場所に荷物を置きます。', 'この場所に荷物を置きます。'),
        ('図像を保存します。', '図像を保存します。'),
        ('技発動', '技発動'), ('強炭酸', '強炭酸'),
        ('炭酸湯', '炭酸湯'), ('温泉湯', '温泉湯'),
        ('薬草湯', '薬草湯'), ('火山灰', '火山灰'),
        ('清涼炭酸湯', '清涼炭酸湯')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 漢字変換後の隣接巻き込み',text,r['corrected'])
protected=DecisionStore();protected.protect('乗荷物')
r=C.correct_line('この場所に乗荷物を置きます。',initial_store,initial_tok,
                 find_known_readings_flex,input_method='kana',dict_index=idx,decisions=protected)
if r['corrected']!='この場所に乗荷物を置きます。':
    failed+=1;print('[NG] 巻き込み修復のユーザー保護',r['corrected'])
print('[確認] IME変換後の巻き込みと自然な語・ユーザー保護')

# 48-XW: 元の文脈を保持する補正。正解の並記もIME読みの注入も無し。
for text,expected in (
        ('予定を聞く人しました。','予定を確認しました。'),
        ('予定を書くな認しました。','予定を確認しました。'),
        ('画素背うを保存します。','画像を保存します。'),
        ('画添えウを保存します。','画像を保存します。'),
        ('説明を読み納屋押して理解しました。','説明を読み直して理解しました。'),
        ('この場所にに見持つを置きます。','この場所に荷物を置きます。'),
        ('も水戸に戻ります','もとに戻ります'),
        ('きょじえかく乱','挙動確認'),
        ('Alt+Tab出ウインドウ','Alt+Tabでウインドウ'),
        ('悪けれではないでしょうか。','悪けれではないでしょうか。'),
        ('部屋を静かにします。','部屋を静かにします。'),
        ('説明ぶん　差釣れません。','説明文　されません。'),
        ('窓を言閉めてから電気を消します。','窓を閉めてから電気を消します。'),
        ('ちゅうりくょを確認しました。','ちゅうりょくを確認しました。'),
        ('昨日ぴっぐるすを見ました。','昨日ぴっくるすを見ました。'),
        ('予定を聞く人して画素背うを保存します。','予定を確認して画像を保存します。'),
        ('書く人も読む人もいます。','書く人も読む人もいます。'),
        ('読み直して確認する','読み直して確認する'),
        ('荷物を受け取って住所を確かめます。','荷物を受け取って住所を確かめます。'),
        ('窓を閉めてから電気を消します。','窓を閉めてから電気を消します。'),
        ('資料は読んでも読まなくてもよい。','資料は読んでも読まなくてもよい。'),
        ('「画素背う」という誤入力','「画素背う」という誤入力')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の範囲と接続の共有',text,r['corrected'])
for text in ('予定を聞く人しました。','画添えウを保存します。'):
    protected=DecisionStore();protected.protect(text)
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx,decisions=protected)
    if r['corrected']!=text:
        failed+=1;print('[NG] 文脈再構築の明示保護',text,r['corrected'])
print('[確認] 原文の文脈・読み・活用形・ユーザー保護')

# 48-XX: 読みの3連と名詞句の接続を合わせる。確率単独では書き換えない。
for text,expected in (
        ('思慮合うを整理してください。','資料を整理してください。'),
        ('この場所に名持つを置きます。','この場所に荷物を置きます。'),
        ('名持つをここに置きます。','荷物をここに置きます。'),
        ('資料に合う図を選びます。','資料に合う図を選びます。'),
        ('名を持つ人を呼びます。','名を持つ人を呼びます。'),
        ('本を読む人を見ました。','本を読む人を見ました。'),
        ('続けます。','続けます。'),('並べました。','並べました。'),
        ('風起こるを知る。','風起こるを知る。'),
        ('風起こるを知りました。','風起こるを知りました。'),
        ('風起こるを静かに待っていました。','風起こるを静かに待っていました。'),
        ('予備画像を保存します。','予備画像を保存します。'),
        ('「名持つ」という誤入力','「名持つ」という誤入力')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 読みの双方向3連と名詞句接続',text,r['corrected'])
protected=DecisionStore();protected.protect('名持つ')
r=C.correct_line('この場所に名持つを置きます。',initial_store,initial_tok,
                 find_known_readings_flex,input_method='kana',dict_index=idx,decisions=protected)
if r['corrected']!='この場所に名持つを置きます。':
    failed+=1;print('[NG] 読みの異様に対するユーザー保護',r['corrected'])
print('[確認] 双方向の読みと品詞接続・正常文の保持')


# 48-XY: 名詞・基本形の後ろに誤って付いた丁寧語尾と、その範囲を共有する。
for text,expected in (
        ('予約まして','予約して'),('記録まして','記録して'),
        ('結果を記録まして資料を閉じます。','結果を記録して資料を閉じます。'),
        ('机の上に書類をなラボました。','机の上に書類を並べました。'),
        ('机の上に書類を並べ背ました。','机の上に書類を並べました。'),
        ('書くました','書きました'),
        ('予約しまして、','予約しまして、'),('記録します','記録します'),
        ('楽しみます','楽しみます'),('食べられます','食べられます'),
        ('読ませました','読ませました'),('お待ちくださいませ','お待ちくださいませ'),
        ('少々お待ち願います','少々お待ち願います'),
        ('ありがとうございます','ありがとうございます'),
        ('大人にも難しい。まして子どもには無理だ。','大人にも難しい。まして子どもには無理だ。'),
        ('「記録まして」という誤入力例','「記録まして」という誤入力例')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 丁寧語の接続と原文範囲',text,r['corrected'])
protected=DecisionStore();protected.protect('記録まして')
r=C.correct_line('記録まして',initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx,decisions=protected)
if r['corrected']!='記録まして':
    failed+=1;print('[NG] 丁寧語範囲のユーザー保護',r['corrected'])
print('[確認] 丁寧語の接続・語尾までの読み直し・動作名詞の保持')

# 48-XZ: 内容語＋丁寧語を巻き込み削除の対象にせず、語尾の再構築を検算する。
for text,expected in (
        ('履歴をっ買いますが','履歴を使いますが'),
        ('この道具をっ買いました。','この道具を使いました。'),
        ('履歴を買いますが','履歴を買いますが'),
        ('小さいっを書きます。','小さいっを書きます。'),
        ('あっ買いました。','あっ買いました。'),
        ('君をっ！','君をっ！'),
        ('うかがいます。','うかがいます。'),
        ('うかがいました。','うかがいました。'),
        ('うかがいません。','うかがいません。'),
        ('うかがいませんでした。','うかがいませんでした。'),
        ('オンマウスすねると','オンマウスすると'),
        ('いいですよわね','いいですよね'),
        ('結果を切ろまして資料を閉じます。','結果を記録して資料を閉じます。'),
        ('机の上に書類を並べ背ました。','机の上に書類を並べました。'),
        ('並べさせました。','並べさせました。'),
        ('読ませました。','読ませました。'),
        ('来させました。','来させました。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 完成した活用と語尾の再構築',text,r['corrected'])
print('[確認] 自然な丁寧形の保持・語尾の比較・使役の活用型')

for text in ('透明度が高く','透明度を測ります。','樹脂性の材料','金利率の計算',
             '技発動','本確認','水補給','卵購入','原子力学の本'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 名詞の語幹・接尾辞・動作名詞',text,r['corrected'],r['odd_spans'])
print('[確認] 名詞の区切り直しと一字名詞の目的語')

for text,expected in (
        ('道具を片付けいて部屋を掃除します。','道具を片付けて部屋を掃除します。'),
        ('資料を調べいて結果を記録します。','資料を調べて結果を記録します。'),
        ('荷物を並べいてから写真を撮ります。','荷物を並べてから写真を撮ります。'),
        ('道具を片付けて部屋を掃除します。','道具を片付けて部屋を掃除します。'),
        ('論ぜられました。','論ぜられました。'),
        ('食べれます。','食べれます。'),
        ('食べられます。','食べられます。'),
        ('書かれました。','書かれました。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 範囲外の隣接打鍵と受身の接続',text,r['corrected'])
print('[確認] 語の端の巻き込み・受身と口語の可能形')

# 48-YB〜YD: 未知語に飲まれた述語・誤った境界・目的語の役割を原文で検算。
for text,expected in (
        ('どうぐをかたづけいてへやをそうじします。','どうぐをかたづけてへやをそうじします。'),
        ('このしりょうをしらべいてけっかをきろくします。','このしりょうをしらべてけっかをきろくします。'),
        ('あたらしいしょるいをあつめいてかぞえます。','あたらしいしょるいをあつめてかぞえます。'),
        ('「しりょうをしらべいて」と入力しました。','「しりょうをしらべいて」と入力しました。'),
        ('きせいせん（規制線、紀勢線、棋聖戦）','きせいせん（規制線、紀勢線、棋聖戦）'),
        ('机の上に書類を奈良へ背ました。','机の上に書類を並べました。'),
        ('机の上に書類を奈良へ是ました。','机の上に書類を並べました。'),
        ('机の上に書類を奈良へ蹴ました。','机の上に書類を並べました。'),
        ('机の上に書類を奈良へ下ました。','机の上に書類を並べました。'),
        ('東京へ来ます。','東京へ来ます。'),('奈良へ行きました。','奈良へ行きました。'),
        ('かけいをしらべます。','かけいをしらべます。'),
        ('失敗した理由を切飯します。','失敗した理由を説明します。'),
        ('結果を機論して資料を閉じます。','結果を記録して資料を閉じます。'),
        ('手順を切飯します。','手順を説明します。'),
        ('数値を機論します。','数値を記録します。'),
        ('思い出を運びます。','思い出を運びます。'),
        ('沈黙を食べる詩を書きました。','沈黙を食べる詩を書きました。'),
        ('新しい小説を再版します。','新しい小説を再版します。'),
        ('お金を寄付します。','お金を寄付します。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の述語境界と目的語の役割',text,r['corrected'])
print('[確認] 長いかなの部分解析・境界の誤分割・一般語の意味的役割・引用の保持')

# 48-YD〜YF: 同じ異様の編集・文中の読み・音便・正常な口語を検算する。
for text,expected in (
        ('資料を並ぼてください。','資料を並べてください。'),
        ('本を貸さって帰ります。','本を買って帰ります。'),
        ('本を友人に歌詞なました。','本を友人に貸しました。'),
        ('あちらへ行けい。','あちらへ行けい。'),
        ('にじますを食べました。','にじますを食べました。'),
        ('本を読んじまった。','本を読んじまった。'),
        ('部屋にしまう。','部屋にしまう。'),
        ('食べてみ','食べてみ'),
        ('持って行き','持って行き')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 文中の読みと完成した語尾',text,r['corrected'])
print('[確認] 文中の読み・音便・編集合成・口語の保持')

print()
if failed:
    print(f'[NG] {failed} 件が期待どおりではありませんでした')
    sys.exit(1)

print('[OK] 補正エンジンは正しく動作しています')
