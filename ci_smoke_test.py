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

# SP: native analysis still preserves source token positions; output repairs the spelling.
for text,expected in (('寒ぃ日だ','寒い日だ'),('可愛ぃ猫がいる','可愛い猫がいる'),
                      ('小さいぁを書く','小さいぁを書く'),('ぃを入力する','ぃを入力する'),('ゅを削除する','ゅを削除する')):
    result = run(text)
    assert result['corrected'] == expected, (text, result)
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
# JIS long-vowel and れ keys are remote; the former reference 変更された
# used an incorrect physical map and is now a forbidden-adjacency control.
for text, expected in (('検査さらた','検査された'), ('変更さーた','変更さーた')):
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
        # The former kana references for these three inputs delete a key
        # physically remote from both original neighbors. Keep the old
        # references for romaji, but never count that forbidden deletion as
        # a kana success. もみと retains its genuinely adjacent deletion.
        wanted=text if method=='kana' and text!='もみとに戻ります' else expected
        if r['corrected']!=wanted:
            failed+=1;print('[NG] 名詞と助詞の境界',method,text,r['corrected'],wanted)
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
        # 48-AGV: 巨人（person）＋確認は実在名詞と動作の結び付き。
        # 旧48-WAの巨人確認は、別の読みへ変えない意図の参考期待。
        ('きょじんかくにん','きょじんかくにん'),
        # 48-AIR/AIV: 操作(process)＋確認 is now independently proved.
        # The old 48-WA kanji conversion is historical intent only;
        # a natural, unchanged kana compound retains its spelling.
        ('そうさかくにん','そうさかくにん')):
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
        ('よいでしょぅか。有線して補正','よいでしょうか。優先して補正'),
        ('よいでしょぅか。','よいでしょうか。'),('そうでしょぅ。','そうでしょう。'),
        ('行きましょぅ。','行きましょう。'),('行くだろぅ。','行くだろう。'),
        ('確認しましょぅか。','確認しましょうか。'),('食べましょぅね。','食べましょうね。'),
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
        # 48-AIS: old 48-XV intent was 画像. A productive nominal prefix
        # and attested technical use make 素画像 a natural source; preserve it.
        ('素画像を保存します。', '素画像を保存します。'),
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
        # Both native spellings preserve the same reading and meaning; the old
        # single-kanji reference remains accepted alongside its natural kana form.
        ('説明を読み納屋押して理解しました。',('説明を読み直して理解しました。','説明を読みなおして理解しました。')),
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
    if r['corrected'] not in (expected if isinstance(expected,tuple) else (expected,)):
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

# 48-YI: 説明対象の実在する活用形を、未完の通常本文と取り違えない。
for text in ('走らという語形を示します。', '次は泳がという未然形を確認します。',
             '「書か」という活用形を比べます。', '美しけれという仮定形です。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 活用形の説明',text,r['corrected'],r['odd_spans'])
print('[確認] 活用形を説明する文脈と原文範囲')

# 48-YJ: 意味の役割と、正常な活用・後ろの述語への係り先を区別する。
for text,expected in (
        ('事故の原因を絶命しました。','事故の原因を説明しました。'),
        ('方法を絶命します。','方法を説明します。'),
        ('資料を死亡した人物が残しました。','資料を死亡した人物が残しました。'),
        ('人を死亡させる危険があります。','人を死亡させる危険があります。'),
        ('母が亡くなりました。','母が亡くなりました。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 述語の項構造',text,r['corrected'])
print('[確認] 主体を述べる述語と目的語・連体節・使役')

# 48-YK: 記号の説明と声を写した綴りを合成・補正で変えない。
for text in ('記号は゛です。','記号は゜です。','あ゛ーと叫びました。',
             'ン゛ーと唸りました。','う゛う゛と唸りました。',
             'は゜は半濁点を付けた形です。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 記号・声の表記',text,r['corrected'],r['odd_spans'])
print('[確認] 記号の説明と短い声の表記')

# 48-YL: 語内の孤立した印を残したまま読み・打鍵へ渡す。
for text,expected in (
        ('ン゛像を保存します。','画像を保存します。'),
        ('科゜像を保存します。','画像を保存します。'),
        ('画゜像を保存します。','画像を保存します。'),
        ('モジ゛ツを選びます。','文字列を選びます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 孤立した印の打鍵',text,r['corrected'],r['odd_spans'])
print('[確認] 語内の孤立した印・読み・物理打鍵・補正後の色')

# 48-YN/YO: preserve genuine modifiers; recover IME boundaries and nominative roles.
for text,expected in (
        ('保存したがぞ゜ウを確認します。','保存した画像を確認します。'),
        ('保存した画素゜ウを確認します。','保存した画像を確認します。'),
        ('問題が買い゛つ下ので作業を続けます。','問題が解決したので作業を続けます。'),
        ('明日のじゅんぴ゛を済ませます。','明日の準備を済ませます。'),
        ('調査した内容を報告島七た。','調査した内容を報告しました。'),
        ('読んだ本を友人に鹿島七た。','読んだ本を友人に貸しました。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 修飾節・誤分割・主語の意味',text,r['corrected'],r['odd_spans'])
print('[確認] 修飾節を残す範囲・広い範囲の再検査・元の活用・主語と動作')

# Quoted predicates and formal nouns retain their own native boundary roles.
for text,expected in (
        ('問題が買い゛つ下と考えています。','問題が解決したと考えています。'),
        ('問題が買い゛つ下ため予定どおり進めます。','問題が解決したため予定どおり進めます。'),
        ('ふている','ファイル'),('ふいいる','ファイル'),
        ('使用した道具をか経つぜ蹴ます。','使用した道具を片付けます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 引用・形式名詞・終助詞・生成候補の順位',text,r['corrected'],r['odd_spans'])
print('[確認] 引用のと・形式名詞の辞書別解・終助詞の境界・活用候補の共有順位')

# 48-YP/YQ: dictionary roles and explicit word mentions share the normal-text gate.
for text in ('予定どおり進めます。','指示通り進めます。','本日作業します。',
             'すねるという言葉を使います。','ややという言葉を使います。',
             'じょうせきという言葉を使います。','こんばんはという言葉を使います。',
             'エイという言葉を使います。','ウンウンという言葉を使います。',
             '次にかじという単語を説明します。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 副詞可能の別解・語の明示的な説明',text,r['corrected'],r['odd_spans'])
print('[確認] 同じ読みの辞書別解と説明対象の既知語')

# 48-YR/YS: quoted utterances and location suffixes are grammatical constructions.
for text,expected in (
        ('ありがとうと言いました。','ありがとうと言いました。'),
        ('エイという魚です。','エイという魚です。'),
        ('問題が買い゛つ下という説明です。','問題が解決したという説明です。'),
        ('名詞句内の語順を確認します。','名詞句内の語順を確認します。'),
        ('前置詞句外の要素を確認します。','前置詞句外の要素を確認します。'),
        ('説明書内の図を確認します。','説明書内の図を確認します。'),
        ('簡易流力を使います。','簡易入力を使います。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 引用の格・接尾に付く位置',text,r['corrected'],r['odd_spans'])
print('[確認] 感動詞の引用・述語のという・位置接尾と旧異様の区別')

# 48-YT/YU/YV: source word boundaries and productive adjective nominalization.
for text,expected in (
        ('じょうせきについて書きます。','じょうせきについて書きます。'),
        ('説明のじょうせきについて書きます。','説明のじょうせきについて書きます。'),
        ('こんにちはという声がしました。','こんにちはという声がしました。'),
        ('こんばんは。','こんばんは。'),
        ('小ささについて書きます。','小ささについて書きます。'),
        ('ささやかな幸せです。','ささやかな幸せです。'),
        ('表示さされるので確認します。','表示さされるので確認します。'),
        ('こうりつを上げます。','こうりつを上げます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 原文の語境界・かなの名詞・形容詞の名詞化',text,r['corrected'],r['odd_spans'])
print('[確認] nativeの語と接続・原文の連体化・漢語変換の語境界・小ささの名詞化')

# 48-YW/YX: conditional euphony and complete literal word boundaries.
for text,expected in (
        ('仕事の割り振らを決めます。','仕事の割り振りを決めます。'),
        ('割り振らがありました。','割り振りがありました。'),
        ('書いたら教えてください。','書いたら教えてください。'),
        ('泳いだら教えてください。','泳いだら教えてください。'),
        ('焼きたらを食べます。','焼きたらを食べます。'),
        ('書き足らないところがあります。','書き足らないところがあります。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 条件形の音便・活用と名詞の区別',text,r['corrected'],r['odd_spans'])
import literal_examples as literal_boundary
for text in ('未知甲くという言葉','ヌォけれという活用形'):
    if literal_boundary.protected_ranges(text):
        failed+=1;print('[NG] 未知の塊の語尾だけを説明対象にしない',text)
print('[確認] たら/だらの生成と検算・未知の塊を途中で凍結しない')

# 48-YY/YZ: actual display spans and native noun senses share source grammar.
for text in ('おみやげについて書きます。','おはらいを受けます。',
             'かけっこについて話します。','説明のへんざいについて書きます。',
             '引っ張りだこについて書きます。','ややがありました。',
             'やや寒いです。','やや大きい箱です。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の名詞と機能語・同じ読みの名詞用法',text,r['corrected'],r['odd_spans'])
print('[確認] 普通名詞の原文範囲と後続の機能語・副詞と同表記の名詞用法')

# 48-ZA/ZB: original word fragments and nominal-case proof stay distinct.
for text,expected in (
        ('これはどんでん返しのことです。','これはどんでん返しのことです。'),
        ('説明のわざわざについて書きます。','説明のわざわざについて書きます。'),
        ('おみやげについては話します。','おみやげについては話します。'),
        ('ここからが本番です。','ここからが本番です。'),
        ('ひとりよりがをみます。','ひとりよがりをみます。'),
        ('まちがし','まちがい')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の語内部・名詞後の機能語の品詞',text,r['corrected'])
print('[確認] 芯も原文の共通入口へ渡す・既存の格助詞の接続を確認')

# 48-ZC/ZD: native repeated nouns and finite functional continuations.
for text in ('ももがありました。','ももだけにします。','これはややのことです。',
             'これはささやかのことです。','おみやげがありました。',
             'おみやげがあります。','かけっこがありました。','おはらいだけがある。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 語の中の反復・機能語の述語の完成',text,r['corrected'],r['odd_spans'])
print('[確認] 名詞の反復を消さず、原文の機能語の述語は活用まで照合する')

# 48-ZE/ZF: mixed-script original words and native nominal homographs.
for text in ('きちょう面を確認しました。','きちょう面がありました。',
             'これはきちょう面のことです。','同じを選びます。',
             'これと同じを選びます。','同じにします。','同じ字です。','同じものを買います。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] かな漢字交じりの語・連体詞と同形の名詞',text,r['corrected'],r['odd_spans'])
print('[確認] 変換する頭も原文の語境界を守る・連体詞と同表記の名詞用法')

# 48-ZG: a noun boundary needs the original left context too.
for text,expected in (('これはわかかんです','これはわかかんです'),
                      ('これはかかんです。','これはかかんです。'),
                      ('私はねももが好きです。','私はねももが好きです。'),
                      ('そうだねももがいいね。','そうだねももがいいね。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の終助詞と名詞の境界',text,r['corrected'],expected)
print('[確認] 原文の名詞は左の接続も確認・完成した会話文は保持')

# 48-ZH: original known-word fragments have the same meaning for purple.
for text in ('これはちゃぶ台のことです。','説明のどしゃ降りについて書きます。',
             'しゃっちょこ立ちがありました。','ひっくり返す。',
             'これはひっくり返した箱です。','説明のてんこ盛りについて書きます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の一語の断片を異様としない',text,r['corrected'],r['odd_spans'])
r=C.correct_line('ひっくり返ます。',initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx)
if not r['odd_spans'] and r['corrected']=='ひっくり返ます。':
    failed+=1;print('[NG] 語の断片を守っても原文の活用不一致を消さない')
print('[確認] かな窓の終点が既知語の内部・紫と補正の共通判定')

# 48-ZI/ZJ/ZK/ZL: spelling conversion shares native suffix validation.
for text,allowed in (
        ('せんたくします。',('せんたくします。',)),
        ('せんたくしました。',('せんたくしました。',)),
        ('せんたくしません。',('せんたくしません。',)),
        ('せんたくし直します。',('せんたくし直します。',)),
        ('せんたくし続けます。',('せんたくし続けます。',)),
        ('読み直します。',('読み直します。',)),
        ('かくにんしません。',('かくにんしません。','確認しません。')),
        ('選択肢を増やします。',('選択肢を増やします。',))):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected'] not in allowed or r['odd_spans']:
        failed+=1;print('[NG] 変換と補正の活用・原文の複合動詞',text,r['corrected'],r['odd_spans'])
import reading_segments as native_sahen
for text,expected in (('せんたくします',True),('せんたくしませんでした',True),
                      ('かくにんしました',True),('せんたくし',False),
                      ('せんたくしたます',False),('ぬぉします',False)):
    if native_sahen.completed_sahen_reading(text)!=expected:
        failed+=1;print('[NG] 同じ読みのnativeサ変名詞と完成した活用',text)
import oddness as native_bound
for original,end,changed,new_end,expected in (
        ('せんたくし直します。',5,'選択肢直します。',3,False),
        ('せんたくし直します。',5,'選択し直します。',3,True),
        ('よみ直します。',2,'読み直します。',2,True)):
    if native_bound.preserves_bound_verb(original,end,changed,new_end,initial_tok)!=expected:
        failed+=1;print('[NG] 原文の非自立動詞・一語になる正当な複合動詞',original,changed)
print('[確認] かなの活用を名詞の組に壊さない・変換前後で動詞の接続を共有')

# 48-ZM/ZN: a proven whole reading precedes an accidental token split.
for text in ('がぞうをほぞんします。','よていをかくにんしました。',
             'しりょうをほぞんします。','ぶんしょうをほぞんします。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の読みで完成した句を部分の解析で壊さない',text,r['corrected'],r['odd_spans'])
for text in ('がぞうのほぞんします。','がぞうがをほぞんします。',
             'がぞうをほぞんしたます。','ぬぉをほぞんします。',
             'へんししん','じっししょう','さいししょう'):
    if native_sahen.completed_native_reading_clause(text):
        failed+=1;print('[NG] 辞書の別用法や縮約形だけで新しい語境界を確定しない',text)
print('[確認] 全かなの名詞の読み・原文の格・丁寧なサ変活用を共有')

# 48-ZO/ZP: mark deletion may itself resolve the detected intrusion.
for original,expected in (
        ('手順を゛説明します。','手順を説明します。'),
        ('資料を゜保存します。','資料を保存します。'),
        ('予定を゛整理し、内容を゛説明します。','予定を整理し、内容を説明します。'),
        ('予定を\u3099整理します。','予定を整理します。'),
        ('「予定を゛整理します」は誤入力です。','「予定を゛整理します」は誤入力です。'),
        ('「手順を゛説明します」は誤字ではない。','「手順を゛説明します」は誤字ではない。'),
        ('あ゛ー！','あ゛ー！'),('記号は゛です。','記号は゛です。')):
    r=C.correct_line(original,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 余分な印の打鍵証拠と明示的な引用',original,r['corrected'],r['odd_spans'])
import mark_usage as mark_proof
for original in ('硬い゛に取り掛かる','資料を゛未知ぬぉします。','文字を゛選択肢ます。'):
    dropped=[]
    normalized=_mpos.normalize_marks(original,dropped=dropped)
    if mark_proof.normalized_intrusions(original,normalized,dropped,initial_tok,initial_store,idx):
        failed+=1;print('[NG] 物理証拠・既知の接続が足りない印を削除しない',original)
print('[確認] 原文の異様・前後の読み・隣接打鍵・削除後の接続・引用を共有')

# 48-ZQ: a modifier and ordinary noun can be written entirely in kana.
for text in ('ひつようなしょるい','ちいさなはこ','あたらしいしりょう',
             'ひつようなしょるいをそうしんしました。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 同じ読みの修飾語と名詞の完成形',text,r['corrected'],r['odd_spans'])
for text in ('ひつようなします。','ひつようながしょるい。',
             'ひつようなしょるいがをほぞんします。','ひつようなしょるいのほぞんします。',
             'ひつようなしょるいをほぞんしたます。','ぬぉなしょるいをほぞんします。',
             'ひつようなぬぉをほぞんします。'):
    if native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 原文の修飾語・名詞・接続が証明できない読み',text)
print('[確認] 全かなの修飾語と名詞を同じnative辞書の読みで確認')


# 48-ZR: the original nominative/topic can attach to a native basic predicate.
for text in ('ひつようなしょるいがありました。','おおきなはこがありました。',
             'ちいさなはこがありました。','ひつようなしりょうはあります。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の主格・主題とnative基本動詞の完成形',text,r['corrected'],r['odd_spans'])
for text in ('ひつようなしょるいがありた。','ひつようなしょるいがあったます。',
             'ひつようなしょるいがをあります。','ひつようなしょるいがあれば。',
             'ひつようなしょるいをありました。','ひつようなしょるいのあります。',
             'ぬぉがありました。','ひつようなしょるいがぬぉます。'):
    if native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 原文の格・完成したnative活用が足りない並び',text)
print('[確認] 主格・主題の後ろの基本動詞は既存の同じ活用判定を使用')


# 48-ZS: punctuation and the proven nominal reading preserve the literal tail.
for text in ('ひつようなしょるいがあった。','ひつようなしょるいがあった',
             'ひつようなしょるいはあります。','ひつようなしょるいはあります'):
    if not native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 原文またはnative名詞後の同じ格・活用を保持',text)
for text in ('ひつようなしょるいがあったます。','ひつようなしょるいがあれば。',
             'ひつようなしょるいがありた。','ひつようなしょるいがのあります。'):
    if native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 未完・活用違いは名詞の読みで完成させない',text)
print('[確認] 元の句点を含む解析と、未知語内の格に続く同じ活用を検算')


# Source-only unfinished native predicates share their actual attachment.
# They never serve as positive completed candidates, even with valid cases.
for text in ('よていをてちょうにかき','よていをてちょうにかか',
             'よていをてちょうにかけ','よていをてちょうにかきまし',
             'てがみをかぞくにおくら','もじをにゅうりょくし',
             'もじをにゅうりょくしまし'):
    if not native_sahen.intact_native_reading(text):
        failed+=1;print('[NG] native open predicate not retained:',text)
    if native_sahen.completed_native_reading_clause(text,require_nominal=True,require_object_fit=True):
        failed+=1;print('[NG] native open predicate certified complete:',text)
for text in ('もじをにゅうりょくしせまし','ほんをよままし',
             'もじをにゅうりょくしましです','よていをてちょうにかくます'):
    if native_sahen.completed_native_reading_clause(text,require_nominal=True,
            require_object_fit=True,allow_open_tail=True):
        failed+=1;print('[NG] bad attachment retained as open predicate:',text)

# Native object ranges retain short nouns, adverbs and written verb roles.
for text in ('てをあらいます','てをあらい','てをあらってからりょうりをはじめます',
             'まいにちこうえんをさんぽしています',
             'そとであそんだあとにくつをあらいます'):
    if not native_sahen.intact_native_reading(text):
        failed+=1;print('[NG] native object/adverb reading lost:',text)
for text in ('そとであそぶあとにくつをあらいます',
             'そとであそんだまえにくつをあらいます',
             'こうえんであそびそうだあとにかえります'):
    if native_sahen.completed_native_temporal_clause(text):
        failed+=1;print('[NG] temporal phase borrowed a different auxiliary:',text)
for text,expected in (('こうえんをさんぽして凍てます',False),
                      ('こうえんを散歩しています',True),
                      ('こうえんをさんぽしています',True)):
    if native_sahen.native_object_predicate_proof(text,5,('公園',))!=expected:
        failed+=1;print('[NG] written predicate borrowed auxiliary role:',text)
if not any(start==4 and cut==9 for start,cut,faces in
           native_sahen.native_object_predicate_contexts('まいにちこうえんをとんぽしています')):
    failed+=1;print('[NG] native adverb hides original object')
if native_sahen.native_adverbial_reading_cuts('またたびをたべます'):
    failed+=1;print('[NG] native adverb cuts a known lexical noun')

# 48-ZT: a classical alternative does not prove an irregular modern past.
for text in ('ちいさなはこがありた。','ちいさなはこがありた',
             'ちいさなはこがなりた。','ちいさなはこがしたます。'):
    if native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 現代語の音便が証明できない過去形',text)
for text in ('ちいさなはこがあった。','ひつようなしょるいがあった。'):
    if not native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 正しい音便の基本動詞は完成を維持',text)
print('[確認] 現代語の音便の肯定証拠と、辞書項目順に依存しない判定')


# 48-ZU/ZV: native positive evidence cannot invent an independent adjective
# or cut the first original connective. Keep ordinary demonstratives and
# the whole na-adjective when a later accidental token crosses its edge.
for text in ('くいぎょう','ないししん','あるちんざ','ぽいはこ'):
    if native_sahen.native_adnominal_reading_parts(text):
        failed+=1;print('[NG] 不確かな語義・従属語・原文の語内切断を完成の証拠にしない',text)
for text in ('このしょるい','ひつようなぶぶん','ひつようなしりょう',
             'たいせつなしょるい','べんりなきのう','みじかいてじゅん'):
    if not native_sahen.native_adnominal_reading_parts(text):
        failed+=1;print('[NG] 原文の修飾語全体と普通名詞の読みを維持',text)
print('[確認] 自立した形容詞・原文の最初の語・連体詞と動詞の同形を区別')

# 48-ZW: inspect the unchanged ending as well as the candidate itself.
for text,expected in (
    ('みちがこん゛ていたためすこしおくれました。','みちがこんでいたためすこしおくれました。'),
    ('せつめいをきいてからじぶん゛てためしてみます。','せつめいをきいてからじぶんでためしてみます。'),
    ('しごとをおえおたらえきでともだちをまちます。','しごとをおえたらえきでともだちをまちます。'),
    ('仕事を終えたら駅で待ちます。','仕事を終えたら駅で待ちます。'),
    ('本を読んだら返してください。','本を読んだら返してください。'),
    ('雨なら休みます。','雨なら休みます。'),
    ('泳いでから休みました。','泳いでから休みました。'),
    ('書いてから送りました。','書いてから送りました。'),
    ('高くて買えません。','高くて買えません。'),
    ('必要なくて外しました。','必要なくて外しました。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の語尾との接続と完成した条件形',text,r['corrected'],expected)
print('[確認] 候補の外に残したて/た接続と、たら/ならの完結を検算')

# 48-ZX: a narrower candidate must fit its retained original modifier.
for text,expected in (
    ('こどもにえほんをよんであうげます。','こどもにえほんをよんであげます。'),
    ('とうろくしたたんごをいちらんあ゛かくにんできます。','とうろくしたたんごをいちらんでかくにんできます。'),
    ('とうろくしたたんごをいちらんてあ゛かくにんできます。','とうろくしたたんごをいちらんでかくにんできます。'),
    ('とうろくしたたんごをいちらんてい゛かくにんできます。','とうろくしたたんごをいちらんでかくにんできます。'),
    ('小さい動くおもちゃがあります。','小さい動くおもちゃがあります。'),
    ('かわいいしゃべる人形を買いました。','かわいいしゃべる人形を買いました。'),
    ('見たことのない動く模型でした。','見たことのない動く模型でした。'),
    ('保存した画像を確認します。','保存した画像を確認します。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 原文の修飾境界と候補の文中品詞',text,r['corrected'],expected)
print('[確認] 複数の修飾語が共有する名詞を保ち、完成形の後の候補を検算')

# 48-ZY/ZZ/AAA: preserve original whole anomaly and actual grammatical roles.
for text,expected in (
    ('がばうをほぞんします。','画像を保存します。'),
    ('がそうをほぞんします。','画像を保存します。'),
    ('がぞいをほぞんします。','画像を保存します。'),
    ('がぞいうをほぞんします。','画像を保存します。'),
    ('がぞうをほぞかします。',('画像を保存します。','がぞうをほぞんします。')),
    ('がぞうをほぞんします。','がぞうをほぞんします。'),
    ('よていをかくにんします。','よていをかくにんします。'),
    ('電車の時刻を言調べて駅へ向かいます。','電車の時刻を調べて駅へ向かいます。'),
    ('道具をん片付けて部屋を掃除します。','道具を片付けて部屋を掃除します。'),
    ('子どもに絵本を読んであうげます。','子どもに絵本を読んであげます。'),
    ('おはようございます。','おはようございます。'),
    ('あ、影が動きました。','あ、影が動きました。'),
    ('読んで、あ、思い出しました。','読んで、あ、思い出しました。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    # 48-ACQ: keep the old kanji reference, also accept literal kana
    # restoration with the same reading. Purple is not a successful repair.
    accepted=expected if isinstance(expected,tuple) else (expected,)
    if r['corrected'] not in accepted or (isinstance(expected,tuple) and r['odd_spans']):
        failed+=1;print('[NG] 元の異様範囲と文中の品詞',text,r['corrected'],expected)
print('[確認] 分割前の異様範囲と、元の述語・候補の語尾の文中接続を保つ')

# 48-AAB: native common-noun readings keep their original actual case.
for text in ('こぶんをみます。','こうぼうをみます。','じしょうを確認しました。',
             'こしつをみます。','こぶんをみない。','そのじしょうを確認しました。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r.get('odd_spans'):
        failed+=1;print('[NG] 自然な名詞の読みと実際の助詞',text,r['corrected'],r.get('odd_spans'))
for text in ('しりょうをあります','ひとをいます','こぶんがをみます','こぶんのをみます'):
    if native_sahen.completed_native_reading_clause(text):
        failed+=1;print('[NG] 不適切な格の列を新たに完成とみなした',text)
print('[確認] 名詞の読みを保ち、格の連続と基本動詞の目的語の有無を区別')

print()
# 48-AAI/AAJ: ordinary usage supplies missing candidates and original grammar.
for text,expected in (('あんじんして眠れます。','安心して眠れます。'),
                      ('あんじんしました。','安心しました。'),
                      ('こじつを予約しました。','こしつを予約しました。'),
                      ('じしょうの原因を調べます。','じしょうの原因を調べます。'),
                      ('こうぼうの話を聞きました。','こうぼうの話を聞きました。'),
                      ('こぶんの話を聞きました。','こぶんの話を聞きました。'),
                      ('三浦按針について調べます。','三浦按針について調べます。'),
                      ('故実の研究を続けます。','故実の研究を続けます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r.get('odd_spans'):
        failed+=1;print('[NG] AIの使用判断・原文の連体化',text,r['corrected'],r.get('odd_spans'))
print('[確認] 日常の入力可能性と、実際に書かれた語の接続を共有')

# 48-AAK/AAL/AAM: normal written categories and item identifiers stay whole.
for text in ('性数格による変化を確認します。','文法上の人称性数格について説明します。',
             'このじしょうの内容を確認します。','このしょるいの内容を確認します。',
             '資料DDを確認します。','資料ＤＤを確認します。','ファイルDDを確認します。',
             '図面XXを確認します。','仕様書ＣＤを確認します。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r.get('odd_spans'):
        failed+=1;print('[NG] 完成した属性列・名詞句・識別子',text,r['corrected'],r.get('odd_spans'))


# 48-AAP/AAS: no new optional choice among ordinary homophones; single
# character daily nouns remain ordinary in their original written reading.
for word in ('いっけん','こうえん','こうそく','こしょう','しちょう','しんちょう','せんじょう',
             'あぶら','いわ','やま'):
    text=word+'を確認しました。'
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r.get('odd_spans'):
        failed+=1;print('[NG] 未判定の同音選択と普通語の読み',text,r['corrected'],r.get('odd_spans'))
for text,expected in (
    ('せっていをへんこうしてかれ゛めんをひらきます。','せっていをへんこうして画面をひらきます。'),
    ('せつめいをきいてからしれ゛ぶんでためしてみます。','せつめいをきいてから自分でためしてみます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r.get('odd_spans'):
        failed+=1;print('[NG] 原文の節と孤立した印の補正',text,r['corrected'],r.get('odd_spans'))



# 48-AAY/ABA/ABE: real compound case, same-reading predicate grammar,
# and an explicit matching reading of an authored fictitious kana name.
for text,expected in (
    ('しゅうふくについて確認しました。','しゅうふくについて確認しました。'),
    ('しりょうをせありしてください。',('資料を整理してください。','しりょうをせいりしてください。')),
    ('しりょうをせいるしてください。',('資料を整理してください。','しりょうをせいりしてください。')),
    ('ミップの規則（みっぷのきそく、rule）について説明します。',
     'ミップの規則（みっぷのきそく、rule）について説明します。'),
    ('三浦按針（みうらあんじん）について調べます。','三浦按針（みうらあんじん）について調べます。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    # 48-ACQ: keep the old kanji reference, also accept literal kana
    # restoration with the same reading. Purple is not a successful repair.
    accepted=expected if isinstance(expected,tuple) else (expected,)
    if r['corrected'] not in accepted or (isinstance(expected,tuple) and r['odd_spans']):
        failed+=1;print('[NG] 読みの注記・複合格・候補の述語接続',text,r['corrected'],expected)



# 48-ABG/ABJ/ABL: exact native auxiliary chains, including their
# counterexamples, supply the same evidence to candidates and mark seams.
from contextual_repair import _allows_grammatical_tail, _productive_predicate
from morphology import dictionary_inflections as native_forms, tokenize as native_tokens
for text in ('確認できます','確認できませんでした','整理してください',
             'とどけられそうです','届くそうです','わすれずに',
             '食べられます','見られそうです','食べないです'):
    head=native_tokens(text)[0]
    if not (_allows_grammatical_tail(native_forms(head.surface) or (),
            text[head.end:],head.reading,head.surface) and _productive_predicate(text,head.surface)):
        failed+=1;print('[NG] nativeで完成した補助語の列',text)
for text in ('確認あります','生理できます','泳がられます','確認できますです',
             '確認しますです','かれめん','てれためし'):
    head=native_tokens(text)[0]
    if (_allows_grammatical_tail(native_forms(head.surface) or (),
            text[head.end:],head.reading,head.surface) and _productive_predicate(text,head.surface)):
        failed+=1;print('[NG] 不完全な列を完成したnative述語と扱った',text)
for text,expected in (
    ('みちがこんでいたためすこしおくれ゛ました。','みちがこんでいたためすこしおくれました。'),
    ('あめのひにはかさをわすれず゜にもっていきます。','あめのひにはかさをわすれずにもっていきます。'),
    ('ゆうがたまでににもつをとどけられ゛そうです。','ゆうがたまでににもつをとどけられそうです。'),
    ('せつめいをきいてからじぶんてれ゛ためしてみます。','せつめいをきいてからじぶんてれ゛ためしてみます。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 補助語の列と印を消した後の語境界',text,r['corrected'],expected)



# 48-ABN: preserve a completed original case/predicate and search the
# entire anomalous word before it, without inventing a noun boundary.
for text,expected_cuts in (
    ('うぃんとうがありました',(5,)),
    ('うぃんとうがありた',()),
    ('うぃんとうがをあります',()),
    ('うぃんとうが',()),
    ('うぃんとうをあります',()),
):
    got=native_sahen.native_functional_case_cuts(text)
    if got!=expected_cuts:
        failed+=1;print('[NG] 既存の格と完成した基本述語だけを切り口にする',text,got,expected_cuts)
text='うぃんとうがありました。'
r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx)
if r['corrected']!='ウィンドウがありました。':
    failed+=1;print('[NG] 語全体を残した補正',text,r['corrected'])


# 48-ABS: a remote-key deletion cannot hide a legitimate insertion.
for text,expected in (
    ('ふっらを確認しました。','ふっくらを確認しました。'),
    ('せつめをよみなおしてりかいしました。','説明をよみなおしてりかいしました。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] 1打鍵削除の物理的な根拠',text,r['corrected'],expected)


# 48-ABS: the prohibited remote-key deletion must not be adopted.
# Native parsing has a separate pre-existing partial repair; this contract
# does not authorize arbitrary deletion just to recover a whole word.
r=C.correct_line('もんじにゅうりょく',initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx)
if r['corrected'] in ('もじにゅうりょく','文字入力'):
    failed+=1;print('[NG] 非隣接のんを削除した',r['corrected'])


# 48-ABT: recursive Shift preparation must not conceal disabled duplication.
for text in ('ひとりよよがりをみます。','ひとりよよがりを確認しました。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']==text.replace('よよ','よ'):
        failed+=1;print('[NG] 再解析が原文の重複削除を迂回した',text,r['corrected'])


# 48-ABU: compose unchanged, independently proven native readings.
for text in (
    'ぶんしょうをにゅうりょくしてないようをかくにんします。',
    'ほぞんしたがぞうをかくにんします。',
    'しりょうをせいりしてよていをかくにんします。',
    'がぞうをほぞんしたのでないようをかくにんします。',
    'がぞうをほぞんするからないようをかくにんします。',
    'そうしんしたしょるいをかくにんします。',
    'がぞうをほぞんしてしりょうをせいりしてよていをかくにんします。',
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の読みを保持した接続・連体修飾',text,r['corrected'],r['odd_spans'])
for text in (
    'がぞうのほぞんしてないようをかくにんします。',
    'がぞうをほぞんしてないようがをかくにんします。',
    'がぞうをほぞんしてないようをかくにんしたます。',
    'がぞうをほぞんしてぬぉをかくにんします。',
    'がぞうをほぞんてないようをかくにんします。',
    'がぞうをほぞんしますないようをかくにんします。',
    'ほぞんしたかくにんします。','ほぞんするせつめいします。',
    'ほぞんしたがぞうがをかくにんします。',
    'ほぞんしたがぞうをかくにんし。',
    'ほぞんしたますがぞうをかくにんします。',
    'ほぞんしてのでかくにんします。',
    'ほぞんしたのでがぞうをありました。',
    'ほぞんしたのでがぞうがありた。',
    'ぶんしょうをにゅうりょくしてないようをかんにんします。',
    'しりょうをけいりしてよていをかくにんします。',
    'ぞうしんしたしょるいをかくにんします。',
):
    if native_sahen.completed_native_reading(text):
        failed+=1;print('[NG] 接続の前後にそれぞれ文法の肯定証拠が必要',text)


# 48-ABV: native final-question context and range selection share one analysis.
import morphology as selected_morph,units as selected_units,explain as selected_explain
for text in ('よいでしょうか。','どうでしょうか。','これでよいですか。',
             'このままでよいのか。','行きますか。','帰るか。'):
    parts=selected_morph.tokenize(text)
    question=[t for t in parts if t.surface=='か']
    if not question or question[-1].pos_sub!='終助詞':
        failed+=1;print('[NG] 元の完成した述語に続く文末の疑問',text,question)
for text in ('何か。','行くかどうか。','行くか帰るか決めます。'):
    if any(t.surface=='か' and t.pos_sub=='終助詞' for t in selected_morph.tokenize(text)):
        failed+=1;print('[NG] 不定・選択のかを文末疑問に断定しない',text)
text='よいでしょうか。'
r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx)
line,items=selected_units.build_line_units(r,initial_tok)
for start,end in ((2,6),(6,7),(2,7)):
    unit=selected_units.make_range_unit(line,items,start,end)
    if not unit.get('functional'):
        failed+=1;print('[NG] 選択範囲にも元の機能語判定を保持',unit)
unit=selected_units.make_range_unit(line,items,6,7)
if selected_explain.pos_lines('か',source_context=unit['analysis_context'])!=['助詞（終助詞）']:
    failed+=1;print('[NG] かを単独で解析し直さず元の文末の用法を表示')
unit=selected_units.make_range_unit(line,items,3,6)
if unit.get('functional') or '原文の語の区切り' not in str(selected_explain.pos_lines('しょう',source_context=unit['analysis_context'])):
    failed+=1;print('[NG] 語の途中の範囲から別の原形を作らない')



# 48-ABW: attested spellings use lexical facts in initial state only.
for text in ('産地アソート','紅茶アソート','マイバッグを買いました。',
             '爽健美茶','爽健美茶を飲みます。','特茶について調べます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 完全一致する一般語・固有名詞の初期認識',text,r['corrected'],r['odd_spans'])
for text,expected_span in (('爽健美茶がを買います。',(4,6)),
                           ('爽健美茶を買いたます。',(7,10)),
                           ('産地アソートがを買います。',(6,8))):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if not any(start<=expected_span[0] and end>=expected_span[1] for start,end in r['odd_spans']):
        failed+=1;print('[NG] 既知語の外にある文法違反も判定する',text,r['odd_spans'])
for word,reading in (('爽健美茶','そうけんびちゃ'),('綾鷹','あやたか'),
                     ('伊右衛門','いえもん'),('特茶','とくちゃ')):
    tokens=selected_morph.tokenize(word)
    if len(tokens)!=1 or tokens[0].reading!=reading or tokens[0].pos_sub!='固有名詞:一般':
        failed+=1;print('[NG] 版付き固有名詞の表記と読みを共有',word,tokens)
if selected_morph.dictionary_inflections('爽健美茶'):
    failed+=1;print('[NG] 補足語彙をIPAdic原典の辞書項として偽装しない')



# 48-ABX/ABY: all usage judgments share native readings; abbreviated action
# notes keep every original kana and reuse actual clause/object evidence.
import reading_segments as note_readings
if '優先' not in note_readings._native_nominal_reading_faces('ゆうせん'):
    failed+=1;print('[NG] 既存の日常語の判断も読みの証拠に共有する')
for text in ('ゆうせんしてほせい','かくにんしてほぞん','せんたくしてさくじょ',
             'ぶんしょうをせんたくしてさくじょ','しりょうをかくにんしてそうしん',
             'ぶんしょうをにゅうりょくしてかくにんしてほぞん',
             'かどうしてかくにん','くどうしてかくにん','しゅうけいしてほぞん'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 操作メモの未編集の読みと意味の接続',text,r['corrected'],r['odd_spans'])
for text in ('かんにんしてほぞん','しゅうわいしてほぞん',
             'ぶんしょうをにゅうりょくしてかんにんしてほぞん',
             'ゆうせんしてほせいしたます','がぞうがをほぞんしてしゅうりょう'):
    if note_readings.completed_native_action_note(text):
        failed+=1;print('[NG] 動作が並ぶだけでは自然な操作メモと認定しない',text)



# 48-ABZ: native content-verb inflection and positive case roles share evidence.
for text in ('もんだいがかいけつしたのでさぎょうをつづけます。',
             'もんだいがかいけつしました。','しごとをつづけます。',
             'さぎょうをつづけます。','かいぎをつづけます。',
             'しごとをつづけまい。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 元の読みと格・内容動詞の活用を保持',text,r['corrected'],r['odd_spans'])
for text in ('もんだいのかいけつしました。','もんだいがをかいけつしました。',
             'もんだいがしゅっせきしました。','つくえがかいけつしました。',
             'さぎょうをつづくます。','さぎょうをつづけたます。',
             'さぎょうがをつづけます。','さぎょうをあきます。'):
    if note_readings.completed_native_reading(text):
        failed+=1;print('[NG] 格と内容動詞を原文のまま肯定できることが必要',text)


# 48-ACA: 意味の異様を先に判定し、表示の面を元の文脈に残す。
for text,expected in (
        ('画面繁栄','画面反映'),('画面繁栄します。','画面反映します。'),
        ('表示面繁栄を確認します。','表示面反映を確認します。'),
        ('経済繁栄','経済繁栄'),('商売繁昌','商売繁昌'),
        ('社会の繁栄を画面に表示します。','社会の繁栄を画面に表示します。'),
        ('「画面繁栄」という誤変換が出ます。','「画面繁栄」という誤変換が出ます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 表示の意味と発展を表す名詞・引用の保持',text,r['corrected'],r['odd_spans'])

# 48-ACB: カテゴリーと名称、および旧切り直し経路も同じ語彙の知識を使う。
for text in ('新商品爽健美茶を紹介します。','飲料綾鷹を紹介します。',
             '銘柄伊右衛門を紹介します。','製品特茶を紹介します。',
             '味別アソート','色別アソート'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 名称の同格と既知語の切り直しを共有',text,r['corrected'],r['odd_spans'])

# 48-ACC: 紫の既存判定から、元のして＋動作を残してかなの打鍵を探す。
for text,expected in (('ようせんしてほせい','ゆうせんしてほせい'),
                      ('かんにんしてほぞん','かくにんしてほぞん'),
                      ('かすくにんしてほぞん','かくにんしてほぞん'),
                      ('ゆうぜんしてほせい','ゆうせんしてほせい'),
                      ('ゆうせんしてほせい','ゆうせんしてほせい'),
                      ('ちょうりしてほぞん','ちょうりしてほぞん')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] かな操作メモの元の異様と打鍵・完成形',text,r['corrected'],r['odd_spans'])

# 48-ACD: 言葉を論じている引用はその綴りを残し、別の出現だけ直す。
for text,expected in (
        ('「画面繁栄」は、成立しているが説明が必要です。','「画面繁栄」は、成立しているが説明が必要です。'),
        ('「画面繁栄」は正しいですか。','「画面繁栄」は正しいですか。'),
        ('「画面繁栄」は自然だが、画面繁栄を確認します。','「画面繁栄」は自然だが、画面反映を確認します。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 表現を論じる引用の範囲と外側の補正',text,r['corrected'],r['odd_spans'])

# 48-ACE: 新しい候補探索にも正常な日常動作と接続語を渡す。
for text in ('そしてほぞん','どうしてほぞん','うんどうしてほきゅう',
             'かんそうしてほかん','くんれんしてじょうたつ','きろくしてぶんせき',
             'ろくおんしてほぞん','しゅうかくしてほぞん','ほきゅうしてきゅうそく','りかいしてきおく'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 日常動作の意味と元の接続語',text,r['corrected'],r['odd_spans'])


# 48-ACF: 生成標本の攪乱を確認の誤打扱いから撤回。原文の意味を先に読む。
for text in ('かくらんしてほぞん','かくらんしてほぞんしてしゅうりょう',
             'じょうほうをかくらんしてほぞん','あっしゅくしてほぞん',
             'がぞうはほぞんしてしゅうりょう','はこにほかんしてしゅうりょう'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 自然な別の動作と格の関係を保持',text,r['corrected'],r['odd_spans'])
for text in ('かくにんしかほぞんしてしゅうりょう','がぞうにほぞんしてしゅうりょう'):
    if note_readings.completed_native_action_note(text):
        failed+=1;print('[NG] 助詞と述語の関係にも肯定証拠を要求',text)
r=C.correct_line('かくにんしうほぞんしてしゅうりょう',initial_store,initial_tok,
                 find_known_readings_flex,input_method='kana',dict_index=idx)
if r['corrected']!='かくにんしてほぞんしてしゅうりょう':
    failed+=1;print('[NG] しかを作る副作用を解消',r['corrected'])


# 48-ACG: 長音と実際の「の」、結果/履歴の中心語を名詞句として共有。
for text in ('ぺーじをひらきます','もくてきのぺーじをひらきます',
             'けんさくけっかをかくにんします','けんさくけっかのぺーじをひらきます',
             'へんこうりれきをかくにんします','あしたのかいぎをかくにんします'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 原文の名詞句・格・動詞を保持',text,r['corrected'],r['odd_spans'])
for text in ('ぺーじがをひらきます','もくてきのをぺーじをひらきます',
             'しごとのよていをかんにんします','けんさくけっかをかくにんしたます'):
    if note_readings.completed_native_reading(text):
        failed+=1;print('[NG] 名詞句の外の異様は完成証拠にしない',text)


# 48-ACH: 肯定した動作の一般性で比較し、単独解析の断片で採点しない。
for text in ('かくゆんしてほぞん','かくよんしてほぞん','かくわんしてほぞん',
             'かくのんしてほぞん','かくりんしてほぞん'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!='かくにんしてほぞん':
        failed+=1;print('[NG] 同じ打鍵費用なら日常的な動作を優先',text,r['corrected'])


# 48-ACI: 時刻と出所も同じ読み・格・活用の肯定証拠で扱う。
for text in ('あしたのかいぎはごぜんじゅうじからはじまります',
             'かいぎはごごさんじにおわります','かいぎはごぜんくじはんからはじまります',
             'じっけんはごごよじからかいしします','かいぎはごごさんじまでにおわります',
             'けんさくけっかからもくてきのぺーじをひらきます'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 元の時刻/出所と完成した文を保持',text,r['corrected'],r['odd_spans'])
for text in ('かいぎはごごさんじまではじまります','かいぎはごごさんじからおわります',
             'かいぎはごごにじゅうごじからはじまります','かいぎはごごさんじからはじまりたます',
             'けんさくけっかからもくてきのぺーじがをひらきます',
             'おちゃからもくてきのぺーじをひらきます'):
    if note_readings.completed_native_adjunct_clause(text):
        failed+=1;print('[NG] 新しい副詞句の各部分にも肯定証拠が必要',text)


# 48-ACJ: 「しか」の否定と、原文の未知塊にある実際の出所を共通に確認。
for text in ('がぞうをほぞんしない','がぞうしかほぞんしない','がぞうはほぞんしない',
             'がぞうをほぞんする','よていをへんこうしない','もくてきのぺーじをよみます',
             'しょるいからひつようなぶんしょうをよみます'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 明示された名詞・格・通常形の活用を保持',text,r['corrected'],r['odd_spans'])
for text in ('がぞうしかほぞんする','がぞうしかほぞんした','がぞうをかんにんしない',
             'がぞうがをほぞんしない','がぞうのほぞんしない','がぞうをほぞんしたない'):
    if note_readings.completed_native_reading(text):
        failed+=1;print('[NG] 否定・通常形も格と元の活用を検査する',text)


# 48-ACK: native negative-volition attachment, including retained source context.
for text in ('ぺーじをひらくまい','ぺーじをとじまい','しごとをつづけまい',
             'ぶんしょうをよむまい','がぞうをひらきますまい',
             'がぞうをほぞんするまい','がぞうをほぞんしまい','がぞうをほぞんすまい'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 正常なまい接続を文脈ごと保持',text,r['corrected'],r['odd_spans'])
for text in ('ぺーじをひらきまい','ぶんしょうをよみまい','ぶんしょうをかきまい',
             'かいぎはごごさんじからはじまりまい','かいぎはごごさんじにおわりまい'):
    if note_readings.completed_native_reading(text):
        failed+=1;print('[NG] 五段の連用形からまいを正常と認定しない',text)
r=C.correct_line('ぶんしょうをよみまい',initial_store,initial_tok,find_known_readings_flex,
                 input_method='kana',dict_index=idx)
if 'セミ' in r['corrected'] or (r['corrected']=='ぶんしょうをよみまい' and not r['odd_spans']):
    failed+=1;print('[NG] まいを名詞の候補で迂回しない・候補なしでも異様を知らせる',r['corrected'],r['odd_spans'])

# 48-ACL: actual POS excludes a homographic verb inside a kana counter;
# explicit linguistic assertions retain the expression under discussion.
for text in ('かみをさんまいよういします','「読みまい」は不自然な表現です。',
             '「読みまい」は不自然な文です。','「読みまい」は不自然な言い方です。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 同形の別品詞と語形の説明を誤検知しない',text,r['corrected'],r['odd_spans'])
import literal_examples as assertion_literals
for text in ('「画面繁栄」は不自然な動きです。','「画面繁栄」は自然な文法の例です。'):
    if assertion_literals.protected_ranges(text):
        failed+=1;print('[NG] 表現の判定以外の引用へ広げない',text)

# 48-ACM: a meaning-anomalous source needs meaningful candidate context.
for text,expected in (('画面繁栄','画面反映'),('表示面繁栄','表示面反映'),
                      ('描画面繁栄を確認します。','描画面反映を確認します。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 画面の文脈を候補の意味の検算まで保持',text,r['corrected'],r['odd_spans'])
for text in ('画面繁盛','画面繁盛を確認します。','表示面繁昌','描画面興隆','プレビュー繁盛'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if any(bad in r['corrected'] for bad in ('根性','判じよう','交流')) or (r['corrected']==text and not r['odd_spans']):
        failed+=1;print('[NG] 無関係な名詞への補正を成功にしない・候補なしは紫',text,r['corrected'],r['odd_spans'])

# 48-ACP-ACT: source anomaly, complete predicate, and retained kana.
for text,expected in (
    ('手順を紹介したます。','手順を紹介してます。'),
    ('しゃしんをえらんてともだちにおくります。','しゃしんをえらんでともだちにおくります。'),
    ('ないようをかくにんしたます。','ないようをかくにんしてます。'),
    ('ぶんしょうをにゅうりょきします。','ぶんしょうをにゅうりょくします。'),
    ('がめんのひょうじをきすりかえます。','がめんのひょうじをきりかえます。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 原文の格と完成した述語で復元',text,r['corrected'],r['odd_spans'])
for text in ('しりょうをほぞんしてからないようをかくにんします。',
             'ないようをかくにんしてください。','それは違うのではあるまいか。',
             'ぶんしょうをにゅうりょくしますか。','がめんのひょうじをきりかえますか。',
             '紹介しますまい。','確認しましょうか。','入力させられます。',
             '「わかりましてます」という誤入力例です。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 正常な活用と接続を保持',text,r['corrected'],r['odd_spans'])
for text in ('わかりましたます。','紹介しましてます。','読みましたまい。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']==text and not r['odd_spans']:
        failed+=1;print('[NG] 直し先がなくても活用の異様を知らせる',text)
    if any(bad in r['corrected'] for bad in ('たまず','ましてます')) and r['corrected']!=text:
        failed+=1;print('[NG] 別の不適切な活用へ変更しない',text,r['corrected'])

# 48-ACU: native inflected cues and the actual instrumental predicate.
for text,expected in (('図を視覚で囲みます。','図を四角で囲みます。'),
                      ('図を視覚で囲めば分かります。','図を四角で囲めば分かります。'),
                      ('視覚実験の装置を囲みます。','視覚実験の装置を囲みます。'),
                      ('視覚を図形化します。','視覚を図形化します。'),
                      ('枠に囲まれた図を視覚で捉えます。','枠に囲まれた図を視覚で捉えます。'),
                      ('「わかりましてます」と書いてありました。','「わかりましてます」と書いてありました。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 同音の手がかりと引用の範囲',text,r['corrected'],r['odd_spans'])

# A native open connective is not a reason to delete its final particle.
for text in ('ぶんしょうをにゅうりょくしますし。','ぶんしょうをにゅうりょくしねます。','ぶんしょうをにゅうりょくしみます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 文の途中の接続を保持',text,r['corrected'])

# A completed desire plus final particle is valid; candidate zero preserves source and mark.
for text,alternative in (('がぞうをほぞんしたない','がぞうをほぞんしたいな'),
                         ('がぞうをほぞんしただない',None)):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    valid=(r['corrected']==text and bool(r['odd_spans'])) or (
        alternative is not None and r['corrected']==alternative and not r['odd_spans'])
    if not valid:
        failed+=1;print('[NG] 成立候補を採るか原文と紫を保持',text,r['corrected'],r['odd_spans'])

# A generated negative-volitional chain needs positive native attachment.
import contextual_repair as native_repair
for text,head in (('入力しんまい','入力'),('紹介しんまい','紹介'),('確認したまい','確認'),('せます','せ')):
    if native_repair._productive_predicate(text,head):
        failed+=1;print('[NG] 未判定の接続を候補の肯定証拠にしない',text)

# 2026-09-14: completed native clauses, exact object cues, and resolved marks.
for text,expected in (
    ('よやくしたじかんをかくにんしてください。','よやくしたじかんをかくにんしてください。'),
    ('まちがえたもじをけしてかきなおします。','まちがえたもじをけしてかきなおします。'),
    ('おりょうりをつくります。','おりょうりをつくります。'),
    ('おこめをあらいます。','おこめをあらいます。'),
    ('文字を読んでから、風景を描きます。','文字を読んでから、風景を描きます。'),
    ('文章を読んだ人を描きます。','文章を読んだ人を描きます。'),
    ('病気を治してから、誤字を治します。','病気を治してから、誤字を直します。'),
    ('絵を、書きます。','絵を、描きます。'),
    ('文章を乳力します。','文章を入力します。'),
    ('まどをしめてからほんをよまみます。','まどをしめてからほんをよみます。'),
    ('ゆうしょくをつくってかぞくとたべのます。','ゆうしょくをつくってかぞくとたべます。'),
    ('まどをしめてからほんをよんでみます。','まどをしめてからほんをよんでみます。'),
    ('ほんをよま','ほんをよま'),
    ('かくにんせんか。','かくにんせんか。'),
    ('ぶんしょうをにゅうりょくしんか。','ぶんしょうをにゅうりょくしんか。'),
    ('ぶんしょうをにゅうりょくしんす。','ぶんしょうをにゅうりょくします。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 元の活用・目的語・解決済み接続を共有',text,r['corrected'],r['odd_spans'])
for text in ('もんせだいがかいけつしたのでさぎょうをつづけます。',
             'もんだいがかいけつしたのでさわぎょうをつづけます。',
             'かいぎでつかうしりょうをじゅんわびします。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 非隣接の1打鍵を旧経路でも削除しない',text,r['corrected'])

# Native adverbs, alternate homophone readings, and source-retained connectives.
for text in ('なくしたかぎをもういちどさがします。','もういちどかくにんします。',
             'へんこうするないようをかくにんします。','りれきをつかいますし',
             'りれきをつかいますけれど','ほんをよめば'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 読み全体と原文の接続を保護',text,r['corrected'],r['odd_spans'])
for text,expected in (('いますとーる','インストール'),
                      ('りれきをっかいますが','りれきをつかいますが')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 語と原文の接続で修復',text,r['corrected'],r['odd_spans'])
if native_repair._productive_predicate('干せしまし','干せ'):
    failed+=1;print('[NG] 単独の候補だけで原文の助動詞列を正当化しない')
for suffix in ('て','ば','ながら','つつ'):
    text='読みます'+suffix
    if native_repair._unchanged_finite_connective(text,text) is not None:
        failed+=1;print('[NG] 有限形以外の接続を残存接続の証明にしない',text)

# A later predicate and a repaired object retain the completed first clause.
for text,expected in (
    ('まどをしめてからほんをよみんす。','まどをしめてからほんをよみます。'),
    ('まどをしめてからほんをよみまもす。','まどをしめてからほんをよみます。'),
    ('まどをしめてから゛んをよみます。','まどをしめてからほんをよみます。'),
    ('てがみをかいてから゛んをよみます。','てがみをかいてからほんをよみます。'),
    ('せつめいをよんでからそうちをうごかします。','せつめいをよんでからそうちをうごかします。'),
    ('ほんをよんでからまどをしめます。','ほんをよんでからまどをしめます。'),
    ('まどをしめてからいものをたべます。','まどをしめてからいものをたべます。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 前節と後節の目的語を保持',text,r['corrected'],r['odd_spans'])
if native_sahen.native_object_predicate_frames('せつめいをよんでからそうちをうごかします'):
    failed+=1;print('[NG] からの誤分割で複文を単一述語の探索へ渡さない')
if not native_repair._productive_predicate('しめて','しめ',before='を'):
    failed+=1;print('[NG] 実際の格を除いて動詞を副詞へ戻さない')
if native_repair.preserves_completed_reading_link('まどをしめてから゛んをよみます',6,10,'苅られん'):
    failed+=1;print('[NG] 共通の最終検算が完成した原文の接続を保護')
from semantic_roles import candidate_object_evidence as noun_candidate_evidence
for noun,following,expected in (('本','をよみます',True),('ほん','をよみます',True),
                               ('県','をよみます',False),('水','を読みます',False),
                               ('本','のよみかた',False)):
    evidence=noun_candidate_evidence(noun,following,before='まどをしめてから')
    if bool(evidence and evidence['shared_roles'])!=expected:
        failed+=1;print('[NG] 候補名詞の意味と原文の格を共有',noun,following,evidence)

# The actual written object and original particle remain shared context.
for text,expected in (
    ('本をもねどします。','本をもどします。'),
    ('本をもどしつます。','本をもどします。'),
    ('本をももどします。','本をももどします。'),
    ('荷物をはこびます。','荷物をはこびます。'),
    ('きろくをかんにんしてほぞんします。','きろくをかくにんしてほぞんします。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 原文の目的語と係助詞の語頭を検算',text,r['corrected'],r['odd_spans'])
if native_repair.object_predicate_candidate_allowed('荷物をはくこびます',4,7,'くび'):
    failed+=1;print('[NG] 旧経路の部分再構築にも述語全体の検算を適用')

# Native counter nouns retain their complete dictionary readings.
for text in ('これはみっつです。','これはよっつです。','これはむっつです。','これはやっつです。','これはここのつです。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native counter noun was not preserved:',text,result['corrected'],result['odd_spans'])

# Literal native nouns, counters and final particles retain the user's text.
for text in ('おなじことばをくらべます。','ことばをじしょでさがします。',
             'ことばをじしょでひきます。','わからないことばをじしょでしらべますか。',
             'ことばをじしょでしらべますかね。','りんごをみっつください。',
             'りんごをむっつください。','りんごをここのつください。','みっつのはこをならべます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] native noun/counter/particle context:',text,r['corrected'],r['odd_spans'])
# The same final check applies when a bad past tail lies outside an edit.
for before,a,b,after in (('あねがつくっつたおかし。',3,6,'つくし'),
                         ('これはしんつた。',3,5,'しき')):
    accepted,reason=C._check_replacement(before,(a,b,after,'かな入力'),initial_store,initial_tok,idx)
    if accepted is not None:
        failed+=1;print('[NG] finite auxiliary accepted a past tail:',before,after)

# Counter boundaries and short clauses retain literal source readings.
for text in ('これはとおです。','とおのはこをならべます。','とおくのはこをみます。',
             'かいてちしきをえます。','かいでちしきをえます。',
             'かおりをかいでちしきをえます。','みていみをかんがえます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] source counter/short clause:',text,r['corrected'],r['odd_spans'])
for text,expected in (('かいてちしきをえにす。','かいてちしきをえます。'),
                     ('かいてじょうほうをほぞかします。','かいてじょうほうをほぞんします。'),
                     ('あさごはんをたべてからしごとわいきます。','あさごはんをたべてからしごとにいきます。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                     input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] repair retained an earlier complete clause:',text,r['corrected'],r['odd_spans'])
# Kana homographs admit either native euphony; written kanji retain identity.
for head,reading,tail,expected in (('かい','かい','て',True),('かい','かい','で',True),
        ('書い','かい','て',True),('書い','かい','で',False),
        ('嗅い','かい','で',True),('嗅い','かい','て',False),
        ('泳い','およい','で',True),('泳い','およい','て',False)):
    if bool(_allows_grammatical_tail(native_forms(head) or (),tail,reading,head))!=expected:
        failed+=1;print('[NG] native euphonic paradigm was lost or mixed:',head,tail,expected)
for text,head in (('してえます','し'),('してうる','し')):
    if _productive_predicate(text,head):
        failed+=1;print('[NG] bound possibility verb attached without a continuative stem:',text)

# Syntactic compounds and direct reanalysis use the same source contract.
for text in ('てがみをかきおえてからふうとうにいれます。',
             'ほんをよみはじめます。','ほんをよみつづけます。','ほんをよみおえます。',
             'ふいてはこをしまいます。','ひらがなをにゅうりょくします。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] phase verb or original noun/case was lost:',text,r['corrected'],r['odd_spans'])
for text in ('ほんをよむおえます','ほんをよんおえます','ほんをよみたはじめます'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] phase verb without its continuative stem:',text)
for text,forbidden in (('てがみをかきおえてかにふうとうにいれます。','かきかえて'),
                        ('もうすこつしゆっくりはなしてください。','ゅっくり'),
                        ('もうすこつしよくかんがえてください。','ょく')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if forbidden in r['corrected']:
        failed+=1;print('[NG] unrelated source boundary changed through another route:',text,r['corrected'])

# A noun's own argument/genitive relation precedes nearby homophone cues.
for text in ('開業の日付を文末に書きます。','開業を知らせる行を削除しました。',
             '開業の案内に空白を挿入します。','糸を理解するには材質も調べます。',
             '糸を汲むという誤変換の例を示します。','ふうとうにてがみをいれます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] original noun context/literal example:',text,r['corrected'],r['odd_spans'])
for text,expected in (('保存の官僚を確認します。','保存の完了を確認します。'),
        ('保存が官僚しました。糸を汲むという誤変換の例を示します。',
         '保存が完了しました。糸を汲むという誤変換の例を示します。')):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected:
        failed+=1;print('[NG] noun context/literal boundary hid another error:',text,r['corrected'],expected)

# Native particles retain question/confirmation meaning after finite verbs.
for text in ('しらべますか','しらべますね','しらべますよ','しらべますよね','しらべますかね','しらべますで'):
    if not native_sahen.completed_native_verb_reading(text):
        failed+=1;print('[NG] native final particles lost:',text)
for text in ('しらべまか','しらべまね','しらべますを'):
    if native_sahen.completed_native_verb_reading(text):
        failed+=1;print('[NG] malformed finite predicate accepted:',text)
# Nominal reconstruction and full clauses share the same relative ending.
for text in ('わかったことば','とどいたほん','よまないほん'):
    if not native_sahen.native_adnominal_reading_parts(text,True):
        failed+=1;print('[NG] native relative head was lost:',text)
for text in ('わかりますことば','とどきますほん','よみますほん','よむまいほん'):
    if native_sahen.native_adnominal_reading_parts(text,True):
        failed+=1;print('[NG] a finite polite/volitional clause became a relative head:',text)

# A changed verb retains its full auxiliary chain in the actual clause.
for text in ('これはしんつです。','箱は三つです。','これはみっつです。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text:
        failed+=1;print('[NG] unproved perfective/count-noun conversion:',text,result['corrected'])
if not native_sahen.native_adverbial_reading_cuts('はやくのみます'):
    failed+=1;print('[NG] native continuative adverb was lost')

# Bound particles do not become free adverbs via homophonic kanji rows.
for text in ('ほどかします','だけよみます','くらいのみます'):
    if native_sahen.native_adverbial_reading_cuts(text):
        failed+=1;print('[NG] bound particle became a standalone adverb:',text)

# Relative subjects and lookup instruments keep their distinct case roles.
for text in ('わからないことばをじしょでしらべます。','じしょでことばをしらべます。',
             'とどいたほんをよみます。','おなじもじをつづけてにゅうりょくします。',
             'おちゃをゆっくりのみます。','てをよくあらいます。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] relative/case/adverb source not preserved:',text,result['corrected'],result['odd_spans'])
for text in ('おちゃをゆっくりのまます','てをよくあらいでます','じしょでゆっくりしらべでます'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] adverb borrowed malformed predicate:',text)

# Native adjective nominalization supplies the existing attribute relation.
for text in ('糸の長さを読み取ります。','糸の重さを理解しました。',
             '糸の太さを読み取ります。','官僚の忙しさを理解しました。',
             '文字の美しさを描きます。','開業の難しさを段落に分けて説明します。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text:
        failed+=1;print('[NG] written nominalized attribute changed:',text,result['corrected'])

# Existing one-kanji semantic cues follow native verb inflections.
import homophone_pairs as _hp_native
for word,cue in (('汲み','汲'),('汲ん','汲'),('縫っ','縫'),('切っ','切'),('伸ばし','伸'),('磨き','磨')):
    if not _hp_native._hits((cue,),(word,)):
        failed+=1;print('[NG] native inflected semantic cue:',word,cue)
for word,cue in (('切手','切'),('針金','針'),('縫製','縫'),('汲み出し','汲')):
    if _hp_native._hits((cue,),(word,)):
        failed+=1;print('[NG] a noun/compound prefix became a verb cue:',word,cue)

# A proven source reading also gates the legacy kana-to-kanji path.
for text in ('しつもんをします','ゆしゅつします','もじれつです','もじれつだ',
             'ひつようなしょるいです','思いのほか処理が速いです。',
             '操作を官僚に説明します。','官僚と処理を確認します。',
             '官僚から操作方法を教わりました。','官僚への報告を保存します。',
             '開業の日に段落の書き方を説明します。','この糸の構造を理解しました。',
             '鏡に次の文字を映します。','誤変換の例として「保存が官僚した」を示します。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] proven source reading/role not preserved:',text,result['corrected'],result['odd_spans'])
for text in ('もじれつですます','しつもんだます','もじれつなら','もじれつな'):
    if native_sahen.completed_native_nominal_predicate(text):
        failed+=1;print('[NG] nominal predicate has no native finite tail:',text)

# Native roles retain valid homophones and complete relative clauses.
for text,expected in (
    ('古いキーボードを売った。','古いキーボードを売った。'),
    ('官僚が資料を解析します。','官僚が資料を解析します。'),
    ('画面のタブを映した動画を見ます。','画面のタブを映した動画を見ます。'),
    ('文字の輪郭を描きます。','文字の輪郭を描きます。'),
    ('誤変換の例は「文末で開業する」です。','誤変換の例は「文末で開業する」です。'),
    ('×「文字を売った」→○「文字を打った」と比較します。','×「文字を売った」→○「文字を打った」と比較します。'),
    ('がぞうをほぞんしたないようをかくにんします。','がぞうをほぞんしたないようをかくにんします。'),
    ('しりょうをへんこうしたりゆうをせつめいします。','しりょうをへんこうしたりゆうをせつめいします。'),
    ('花を摘みつ。','花を摘みつ。'),('文を書きつ。','文を書きつ。'),
    ('これをひとつ買います。','これをひとつ買います。'),
    ('この処理は思いです。','この処理は重いです。'),
    ('キーを売つ。','キーを打つ。'),
    ('キーボードで文字を売ちます。','キーボードで文字を打ちます。'),
):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=expected or r['odd_spans']:
        failed+=1;print('[NG] 原文の項・修飾節・助動詞接続を検算',text,r['corrected'],r['odd_spans'])
for text,head,expected in (('売りてます','売り',False),('読みてます','読み',False),
                           ('売ってます','売っ',True),('読んでます','読ん',True),
                           ('書いてます','書い',True)):
    if native_repair._productive_predicate(text,head)!=expected:
        failed+=1;print('[NG] 非自立動詞の縮約形も音便接続で検算',text)
if C._compound_verb_backed('思い','おもい','この処理は思いです。'):
    failed+=1;print('[NG] 名詞の綴りだけでは複合動詞を証明しない')
if not C._compound_verb_backed('換わり','かわり','補正の文字列に書き換わりました。'):
    failed+=1;print('[NG] 辞書で分割された複合動詞の連用接続を保持')
import morphology as native_morphology, oddness as native_oddness
for text,expected in (('売つ',True),('書くつ',True),('見るつ',True),
                       ('書きつ',False),('見つ',False),('行きつ',False)):
    parts=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
            t.start,t.end,t.has_reading,t.infl_form) for t in native_morphology.tokenize(text)]
    actual=any(native_oddness.completed_tsu_aux_mismatch(a,b) for a,b in zip(parts,parts[1:]))
    if actual!=expected:
        failed+=1;print('[NG] 完了のつは原文の連用形別解で検算',text,actual)

# Recipient/content cases and physical repeated-key policy use original input.
for text in ('ないようをかくにんしたひとにききます。',
             'ともだちにてがみをおくります。','たんとうしゃにたずねます。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text or r['odd_spans']:
        failed+=1;print('[NG] 受け手と内容を同じ述語へ接続',text,r['corrected'],r['odd_spans'])
for text in ('ひらがなのままぶんしょうをほそぞんします。',
             'きっふぷをかってからでんしゃにのります。',
             'てをあらってからりょうりをはしじめます。',
             'まだとちゅうですがここまでをほそぞんします。'):
    r=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if r['corrected']!=text:
        failed+=1;print('[NG] 濁点を含む重複打鍵を原文で保護',text,r['corrected'])

# Shared state adjunct, personal plural, progressive tail and insertion contracts.
for text in ('ひらがなのままぶんしょうをほぞんします。',
             'ひらがなのままぶんしょうをほぞんしますか。',
             'かなのままでてがみをかきます。',
             'こどもたちはにわであそんでいます。','こどもたちがほんをよみます。',
             'がくせいたちはとしょかんでべんきょうします。',
             'わたしたちはほんをよみます。','せんせいたちがしりょうをよみます。',
             '静かに歩く','入力欄がアクティブになっていません。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native nominal/functional composition:',text,result['corrected'],result['odd_spans'])
for text in ('にわであそびています','にわであそんています','ほんをよむています',
             'はこたちがほんをよみます'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] unproved native functional composition:',text)
for text,expected in (
    ('静か歩く','静かに歩く'),
    ('入力欄がアクティブなっていません。','入力欄がアクティブになっていません。'),
    ('せつめいをよぇでからそうちをぁごかします。','せつめいをよんでからそうちをうごかします。'),
    ('せつめいをよんあでからそうちをあうごかします。','せつめいをよんでからそうちをうごかします。'),
    ('おなじもじをさづけてにゅうせょくします。','おなじもじをつづけてにゅうりょくします。'),
    ('おなじもじをつさづけてにゅうありょくします。','おなじもじをつづけてにゅうりょくします。')):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=expected or result['odd_spans']:
        failed+=1;print('[NG] independent key slips / native particle insertion:',text,result['corrected'],result['odd_spans'])

# Finite reason/contrast, unchanged prerequisite and demonstrative extent.
for text in ('はやくついたのでしばらくまちました。',
             'まだとちゅうですがここまでをほぞんします。',
             'ぶんしょうをほぞんしましたがまだとちゅうです。',
             'ないようはあっていますがひづけがちがいます。',
             'かくにんしてからでないとほぞんできません。',
             'かくにんしてからじゃないとほぞんできません。',
             'しりょうをよんでからでなければせつめいできません。',
             'そこまでをかくにんします。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] finite link / prerequisite / extent:',text,result['corrected'],result['odd_spans'])
for text in ('まだとちゅうですかが','ぶんしょうをほぞんしますかが',
             'はやくついなので','ほんをよんて','まだとちゅうですますが'):
    if native_sahen.completed_native_reading_link(text):
        failed+=1;print('[NG] unproved finite connective:',text)

# Nested nominal heads and focus particles must survive unchanged.
for text in ('おわったしごとのないようをほうこくします。',
             'あたらしいほんのないようをせつめいします。',
             'かいたてがみのないようをかくにんします。',
             'あたらしいやりかたをためしてもみます。',
             'あたらしいやりかたをためしてはみます。',
             'ほんをよんではいます。','かみにかいてはおきます。',
             'あとでよみますがいまはほぞんします。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] nested nominal / auxiliary focus:',text,result['corrected'],result['odd_spans'])
for text in ('ほぞんしましたしごと','よんてほん','おわったりんご'):
    if native_sahen.native_nominal_phrase_faces(text):
        failed+=1;print('[NG] unproved relative noun:',text)
for text in ('ほんをよんてはみます','もじをかいでもみます'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] focused auxiliary keeps native euphony:',text)

# The same native verb owns semantic roles, euphony and auxiliary potential.
for text in ('このぶんしょうをよんでいただけますか。',
             'しりょうをかくにんしてもらえますか。','かみにかいておけます。',
             'ここからあるいていけます。','においをかいでもみます。',
             'せつめいをせんでそうちをうごかします。',
             'つくえのうえをかたづけておきます。','たなのなかをせいりします。',
             '一緒に行きましょう。','昨日は読みけり。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native lemma / auxiliary potential / spatial cleanup:',text,result['corrected'],result['odd_spans'])
for text,expected in (
    ('このぶんしょうをよんでいただけますう。','このぶんしょうをよんでいただけますか。'),
    ('このぶんしょうをよんでいただけますき。','このぶんしょうをよんでいただけますか。'),
    ('つくえのうえをかたづめておきます。','つくえのうえをかたづけておきます。')):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=expected or result['odd_spans']:
        failed+=1;print('[NG] contextual auxiliary / cleanup repair:',text,result['corrected'],result['odd_spans'])
for text in ('もじをかいでもみます','もじをよんていただけますか'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] one native lemma must own meaning and inflection:',text)

# Native volition keeps the written reading through the shared Shift gate.
for text in ('もういちどかくにんしよう。','かくにんしよう。',
             'しりょうをかくにんしよう。','いっしょにべんきょうしよう。',
             'もういちどためしてみよう。','ひとやすみしよう。',
             'しりょうをしらべまい。','つくえのうえをかたづけておくまい。',
             'あかいさらをしろいたなにおきます。',
             'えらんだことばをべつのことばにかえます。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native volition / resultative / placement:',text,result['corrected'],result['odd_spans'])
for text,expected in (
    ('おわったしごとのないようをほうこくしすます。','おわったしごとのないようをほうこくします。'),
    ('つくえのうえをかたづけておくます。','つくえのうえをかたづけておきます。'),
    ('えらんだことばをべつのことばにゆかえます。','えらんだことばをべつのことばにかえます。'),
    ('あかいさらをしろれいたなにおきます。','あかいさらをしろいたなにおきます。')):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=expected or result['odd_spans']:
        failed+=1;print('[NG] shared rank / resultative / placement:',text,result['corrected'],result['odd_spans'])
for text in ('かくにんしたう','かくにんしるう'):
    if native_sahen.completed_sahen_reading(text,allow_nonpolite=True):
        failed+=1;print('[NG] native volition requires actual mizen attachment:',text)

# Ordinary lettering and projection remain valid original meanings.
for text in ('文字を描きます。','文字を大きく描きます。','文字を丁寧に描きます。',
             '文字をゆっくり描きます。','漢字を描きます。','看板に文字を描きます。',
             'タブに映ります。','別のタブに映ります。','画面に鮮明に映ります。',
             '文字を読んでから絵を描きます。','文字を大きくしてから説明を書きます。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native glyph / projection / adverbial argument:',text,result['corrected'],result['odd_spans'])

# Held-out ordinary words and predicates keep their original kana onset.
for text in ('かいたぶんしょうをよみなおしてからほぞんします。',
             'でんわばんごう','でんわばんごうをかくにんします。',
             'でんわばんごうをかくにんしてからでんわをかけます。',
             'かみにかいたもじをゆっくりよみます。',
             'もじをかぞえなおしてからほぞんします。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,input_method='kana',dict_index=idx)
    if result['corrected']!=text:
        failed+=1;print('[NG] held-out native source spelling:',text,result['corrected'])
# Unknown clause relations may still carry purple; a proved lexical word
# itself must be clean, and an invalid continuative is not positive proof.
for text in ('でんわばんごう','でんわばんごうをかくにんします。'):
    if not native_sahen.intact_native_reading(text):
        failed+=1;print('[NG] native relational compound is an intact reading:',text)
for text in ('しりょうをよむなおします','しりょうをよみたなおします'):
    if native_sahen.completed_native_reading_clause(text,require_object_fit=True):
        failed+=1;print('[NG] redo compound requires continuative attachment:',text)

# JIS physical keys and native phase roles are independent of source spelling.
import kana_layout as native_keys
if not (native_keys._base_distance('ー','へ')==1.0
        and native_keys._base_distance('ー','ろ')>1.0
        and not native_keys.same_physical_key('ー','ろ')
        and native_keys.same_physical_key('わ','を')
        and native_keys.kana_key_distance('わ','を')==0.3):
    failed+=1;print('[NG] JIS long-vowel / shifted-wa key identity')
import semantic_roles as native_semantics
for word in ('読み直し','読みなおし','書き直し','書きなおし'):
    if not native_semantics.predicate_roles(word,'て','説明を') & {'text'}:
        failed+=1;print('[NG] native phase compound keeps lexical argument:',word)

# Native loanword readings, calling and material compounds share the source gate.
for text in ('すくろーる','すくろーるをかくにんします。','ぷらねたりうむ',
             'ぷらねたりうむにいきます。','でんわをかけます。',
             'でんわばんごうをかくにんしてからでんわをかけます。',
             'せんたくものをほしてからまどをあけます。','ものをはこにいれます。',
             '電話を掛けます。','時間をかけます。','音楽をかけます。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native source word / compound:',text,result['corrected'],result['odd_spans'])
for text in ('ふれろむ','ぷぷらねたりうむ'):
    if native_sahen.native_katakana_nominal_face(text):
        failed+=1;print('[NG] absent loanword is not native proof:',text)
if native_sahen.native_relational_compound_heads('せんたくもの')!=('物',):
    failed+=1;print('[NG] native suffix alternate reading must retain the material head')
for text in ('せんたくも','せんたくにん'):
    if native_sahen.native_relational_compound_heads(text):
        failed+=1;print('[NG] unrelated suffix is not the material compound:',text)

# A native focus particle retains a proved noun phrase even after kana misparsing.
for text in ('ひつようなものだけをはこにいれておきます。',
             'ものだけをはこにいれます。','たいせつなものだけをもちます。',
             'あかいはなだけをかざります。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native focused noun phrase:',text,result['corrected'],result['odd_spans'])
for text in ('ひつようなものだせ','ひつようなものしか','だけ'):
    if native_sahen.native_nominal_phrase_faces(text):
        failed+=1;print('[NG] absent or conditional focus is not nominal proof:',text)

# Candidate identity is checked inside an independently validated kana predicate.
# ぶ -> び is remote; す -> い is adjacent. These cases exercise native まい,
# not an assumed polite answer produced by a nonadjacent key substitution.
for source,expected in (('しりょうだけをえらぶます。','しりょうだけをえらぶまい。'),
                        ('ものだけをおくます。','ものだけをおきます。'),
                        ('このほんだけをよむます。','このほんだけをよむまい。')):
    result=C.correct_line(source,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!=expected or result['odd_spans']:
        failed+=1;print('[NG] native predicate identity through kana segmentation:',source,result['corrected'],result['odd_spans'])

# Native genitive boundaries and complete case-bearing relative clauses.
for text in ('まどのそと','まどのそとをみます。',
             'かみにかいたもじをゆっくりよみます。',
             'はこにいれたものをとりだします。',
             'ほんをよんだひとにたずねます。','ひとがよんだほんをさがします。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!=text or result['odd_spans']:
        failed+=1;print('[NG] native genitive / case-bearing relative:',text,result['corrected'],result['odd_spans'])
if (native_semantics.relative_action_support('文書','よんだ',('を',))
        or native_semantics.relative_action_support('人','よんだ',('が',))):
    failed+=1;print('[NG] relative head cannot reuse an occupied argument case')
if not (native_semantics.relative_action_support('人','よんだ',('を',))
        and native_semantics.relative_action_support('文書','よんだ',('が',))):
    failed+=1;print('[NG] relative head keeps the remaining native argument case')

# Original literal neighbors and proved noun meanings survive unknown kana parsing.
for text in ('ふれーむのいろをせかえます。','ふれーむのいろをよかえます。',
             'ふれーむのいろをらかえます。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!='ふれーむのいろをかえます。' or result['odd_spans']:
        failed+=1;print('[NG] original neighbor and object frame:',text,result['corrected'],result['odd_spans'])
from reading_likelihood import adjacent_readings as native_adjacent_readings
if native_adjacent_readings('ろをせか',[],2,3)!=('ろを','か'):
    failed+=1;print('[NG] literal kana keys remain available across unknown segmentation')
for text,edge in (('漢せ',1),('xせ',1),('を せ',2)):
    if native_adjacent_readings(text,[],edge,len(text))[0]:
        failed+=1;print('[NG] literal-neighbor fallback crossed an unreadable character or gap:',text)

# Kana suru actions retain the same positive meaning as their native spelling.
for text in ('でーたをせほぞんします。','でーたをにほぞんします。',
             'でーたをよほぞんします。','でーたをらほぞんします。'):
    result=C.correct_line(text,initial_store,initial_tok,find_known_readings_flex,
                          input_method='kana',dict_index=idx)
    if result['corrected']!='でーたをほぞんします。' or result['odd_spans']:
        failed+=1;print('[NG] native suru meaning preserves kana:',text,result['corrected'],result['odd_spans'])

# SP/SR: actual native grammar, empty seed store, and shared engine contracts.
import unittest
from tests_spec_contracts import SpellingEngineContracts
_sp_contract=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SpellingEngineContracts))
if not _sp_contract.wasSuccessful():failed+=1

from tests_tab_analysis import CompletedTabTests
from tests_background_ownership import BackgroundOwnershipTests
from tests_application_cache import ApplicationCacheTests
from tests_initial_setup import InitialSetupTests
from tests_reading_rows import ReadingRowsTests
from tests_native_reading_extensions import NativeReadingExtensionsTests
from tests_negative_degree_context import NegativeDegreeContextTests
from tests_action_nominal_context import ActionNominalContextTests
from tests_focused_request_context import FocusedRequestContextTests
from tests_counter_readings import CounterReadingTests
from tests_nominal_source_ranges import NominalSourceRangeTests
from tests_short_causative import ShortCausativeTests
from tests_floating_quantity import FloatingQuantityTests, OrdinaryQuantityMeaningTests
from tests_prolonged_clause import ProlongedClauseTests
from tests_focused_sequence import FocusedSequenceTests
from tests_original_case_style import OriginalCaseStyleTests
from tests_unclassified_native import UnclassifiedNativeTests
from tests_finite_copula import FiniteCopulaTests
from tests_source_sequence_ranges import SourceSequenceRangeTests
from tests_avoidance_roles import AvoidanceRoleTests
from tests_quantity_object_validation import QuantityObjectValidationTests
from tests_counted_nominal_repairs import CountedNominalRepairTests
from tests_attested_nominal_candidates import AttestedNominalCandidateTests
from tests_device_arrangement import DeviceArrangementTests
from tests_conjunctive_case import ConjunctiveCaseTests
from tests_classified_nominal_readings import ClassifiedNominalReadingTests
from tests_candidate_case_roles import CandidateCaseRoleTests
from tests_consultation_roles import ConsultationRoleTests
from tests_conflict_explanation import ConflictExplanationTests
from tests_changed_nominal_case import ChangedNominalCaseTests
from tests_independent_object_clause import IndependentObjectClauseTests
from tests_release_roles import ReleaseRoleTests
from tests_processing_roles import ProcessingRoleTests
from tests_unadorned_prefix import UnadornedPrefixTests
from tests_suru_paradigm import SuruParadigmTests
from tests_nominal_temporal import NominalTemporalTests
from tests_adjective_manner import AdjectiveMannerTests, AdjectiveHostBoundaryTests
from tests_sahen_particle_context import SahenParticleContextTests
from tests_rhetorical_adverb import RhetoricalAdverbTests
from tests_source_manner import SourceMannerTests
from tests_moved_word_evidence import MovedWordEvidenceTests
from tests_action_attachment import ActionAttachmentTests
from tests_genitive_object_repairs import GenitiveObjectRepairTests
from tests_nominalized_reading import NominalizedReadingTests
from tests_ime_native_stems import ImeNativeStemTests
from tests_collection_roles import CollectionRoleTests
from tests_conflict_repair_fit import ConflictRepairFitTests
from tests_multiple_key_deletion import MultipleKeyDeletionTests
from tests_event_argument_roles import EventArgumentRoleTests
from tests_genitive_case_repairs import GenitiveCaseRepairTests
from tests_writing_system_conversion import WritingSystemConversionTests
from tests_representation_formats import RepresentationFormatTests
from tests_comitative_activity import ComitativeActivityTests
from tests_communication_case import CommunicationCaseTests
from tests_cooking_roles import CookingRoleTests
from tests_native_relative_repairs import NativeRelativeRepairTests
from tests_comma_kana_context import CommaKanaContextTests
from tests_biological_case import BiologicalCaseTests
from tests_adverbial_host import AdverbialHostTests
from tests_counted_nominals import CountedNominalTests
from tests_native_verb_prefix import NativeVerbPrefixTests
from tests_legacy_coverage import LegacyCoverageTests, NativeLegacyCoverageTests
from tests_search_boundaries import SearchBoundaryTests
from tests_file_format import FileFormatTests
from tests_spatial_nominal_context import SpatialNominalContextTests
from tests_prepare_reuse import PrepareReuseTests
from tests_native_nominals import NativeNominalTests
from tests_particle_candidates import ParticleCandidateTests, ParticleChoiceTkTests
from tests_particle_auto import AutomaticParticleTests
from tests_kana_request import KanaRequestTests
from tests_question_particles import QuestionParticleTests
from tests_native_reading_data import NativeReadingDataTests
_cache_suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
    for case in (NominalTemporalTests,AdjectiveMannerTests,AdjectiveHostBoundaryTests,SahenParticleContextTests,RhetoricalAdverbTests,SourceMannerTests,MovedWordEvidenceTests,ActionAttachmentTests,GenitiveObjectRepairTests,NominalizedReadingTests,ImeNativeStemTests,CollectionRoleTests,ConflictRepairFitTests,MultipleKeyDeletionTests,EventArgumentRoleTests,GenitiveCaseRepairTests,WritingSystemConversionTests,RepresentationFormatTests,ComitativeActivityTests,CommunicationCaseTests,CookingRoleTests,NativeRelativeRepairTests,CommaKanaContextTests,IndependentObjectClauseTests,ReleaseRoleTests,ProcessingRoleTests,UnadornedPrefixTests,SuruParadigmTests,ConsultationRoleTests,ConflictExplanationTests,ChangedNominalCaseTests,CandidateCaseRoleTests,ClassifiedNominalReadingTests,CountedNominalRepairTests,AttestedNominalCandidateTests,DeviceArrangementTests,ConjunctiveCaseTests,UnclassifiedNativeTests,FiniteCopulaTests,SourceSequenceRangeTests,AvoidanceRoleTests,QuantityObjectValidationTests,FileFormatTests,NativeVerbPrefixTests,CountedNominalTests,AdverbialHostTests,BiologicalCaseTests,LegacyCoverageTests,NativeLegacyCoverageTests,FocusedSequenceTests,OriginalCaseStyleTests,CounterReadingTests,NominalSourceRangeTests,ShortCausativeTests,FloatingQuantityTests,OrdinaryQuantityMeaningTests,ProlongedClauseTests,SearchBoundaryTests,FocusedRequestContextTests,SpatialNominalContextTests,NegativeDegreeContextTests,ActionNominalContextTests,CompletedTabTests,BackgroundOwnershipTests,ApplicationCacheTests,InitialSetupTests,ReadingRowsTests,NativeReadingExtensionsTests,PrepareReuseTests,NativeNominalTests,ParticleCandidateTests,ParticleChoiceTkTests,AutomaticParticleTests,KanaRequestTests,QuestionParticleTests,NativeReadingDataTests))
if not unittest.TextTestRunner().run(_cache_suite).wasSuccessful():failed+=1

# 48-ACO: the engine contracts do not exercise Tk's actual startup boundary.
# Windows is the shipped desktop target; use synthetic stores in child copies.
if sys.platform == 'win32':
    from tests_gui_startup import TextObserverTkTests, FixtureCollectionTkTests, StartupTkTests
    from tests_gui_editing import EditingTkTests, HalfwidthAutofixTkTests, CrossTabQuoteTests
    from tests_gui_fonts import FontSettingsTests, FontTkTests
    from tests_gui_gutter import GutterTkTests
    from tests_typing_pointer import TypingPointerTests
    from tests_gui_all_tabs_search import AllTabsSearchTkTests
    from tests_gui_file_format import FileFormatApplicationTests
    from tests_gui_features import FeaturesApplicationTests
    from tests_unicode_undo import UnicodeUndoTkTests
    from tests_gui_analysis import AnalysisGuiTests
    from tests_gui_interaction import InteractionTkTests
    from tests_text_navigation import BlockNavigationTests, NavigationTkTests
    from tests_window_icons import WindowIconTests
    from tests_result_selection import ResultSelectionTkTests
    from tests_gui_tab_lifecycle import TabLifecycleTkTests
    from tests_gui_initial_setup import InitialSetupTkTests
    from tests_gui_refresh import PendingColorTkTests, RefreshApplicationTkTests
    _startup_suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(case)
        for case in (FontSettingsTests,FontTkTests,GutterTkTests,TypingPointerTests,AllTabsSearchTkTests,FileFormatApplicationTests,FeaturesApplicationTests,CrossTabQuoteTests,TextObserverTkTests, FixtureCollectionTkTests, StartupTkTests, EditingTkTests, HalfwidthAutofixTkTests, UnicodeUndoTkTests, AnalysisGuiTests,
                     InteractionTkTests, BlockNavigationTests, NavigationTkTests, WindowIconTests, ResultSelectionTkTests, TabLifecycleTkTests, InitialSetupTkTests, PendingColorTkTests, RefreshApplicationTkTests))
    _startup_result = unittest.TextTestRunner().run(_startup_suite)
    if not _startup_result.wasSuccessful():
        failed += 1
else:
    print('[SKIP] Windows GUI startup: this host is not Windows')

if failed:
    print(f'[NG] {failed} 件が期待どおりではありませんでした')
    sys.exit(1)

print('[OK] 補正エンジンは正しく動作しています')
