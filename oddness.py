# -*- coding: utf-8 -*-
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
**語と語が、その順でくっつけるか**（項目48-HO）。

うにさんの指定（2026-08-21）:

    「アプリにAIは入れませんが、**開発しているのはAI**です。
      異様さがわかるのですから、**その基準を落とし込んで**ください」
    「**局所的な対応とならないよう留意して。** ピックアップした
      一部の単語だけ対応しては、大量の対応漏れが出ます」
    「さらに、**野外文章の異様さも、AIなら分かります**。踏み込んで」

### `野外文章` は、なぜ異様か

`野外` も `文章` も実在語で、**形だけ見れば `誤字補正` と同じ**
（項目48-FC が「殺意代価 と 誤字補正 は形として同じ」と書いたところ）。
違うのは**くっつき方**である。

    誤字補正   誤字**を**補正する      ← 目的語＋動作（動詞的名詞）
    文字入力   文字**を**入力する      ← 同じ
    野外活動   野外**で**行う活動      ← 場所が修飾できる相手
    **野外文章**  文章は場所の属性を持たない。
               `野外を文章する` とも `野外の文章` とも言えない

つまり **「後ろに立つ語が、そもそも後ろに立てる語か」**。
これは**手で並べる話ではなく、表から数えられる**。

### 手で並べた表は捨てた（局所的だったため）

前の版は接頭・接尾の漢字をこちらが書き下していた。**それは局所的**で、
挙げ漏らせばそのまま漏れになる。**全部やめて、次の3つに置き換えた**:

  1. **表の全部の語を割って、どの語がどの位置に立てるかを数える**
     （`seed_japanese.txt.gz` 778,340語 → 割れた組 50,944・
       前に立つ語 15,866・後ろに立つ語 18,392）
  2. **品詞**（接頭詞・接尾・サ変接続・数詞）は**解析から取る**
  3. くっつき方の規則（下の `is_odd_run`）

**数えた例**（後ろに立った回数）:

    活動 42 ／ 文字 39 ／ 変換 13 ／ 確認 9 ／ 戦争 9 ／ 入力 7
    **文章 1** ／ 仮名 1 ／ **代価 0** ／ **家事 0** ／ **帰任 0** ／ **流力 0**

### 何を「異様」と呼ぶか

助詞をはさまずに直接くっついた2語 (A, B) について、
**次のどれにも当てはまらないなら異様**:

    (1) A＋B を**表の語の中で見たことがある**（野外活動・文字入力）
    (2) B が**動詞的名詞（サ変接続）**   誤字補正・挙動確認・全文走査
    (3) B が**接尾**、A が**接頭詞**      効率化・必要性・再変換
    (4) どちらかが**数詞**               3日以内
    (5) B に**後ろに立った実績がある**    半角文字（文字 39回）
    (6) A が名詞で B が動詞なら、**複合動詞として表に在る**
        （見切れる ○ ／ 差釣れる ×）

**材料は増えない。** 表はすべて同梱の `seed_japanese.txt.gz` から
その場で作る。

### 実測（2026-08-21・うにさんの材料）—— **単独の門には使えない**

    うにさんの誤変換 30件       印 **13件**
      （野外文章・殺意代価・最大家事・差釣・雛仮名・簡易流力・
        田部井号・かな地軌・単語の触長利・奥悠久子帝・夕後…）
    正しい語・文・直し先 54件   印 **2件**（今書いた・今思うと）
    **実機メモ 全タブ 1,226行    印 102行（8%）**

**実機メモの8%は多すぎる。** 中身は `補正欄` `説明欄` `漢字塊`
`添付画像` `語彙読込` `選択切り替え` `辞書取り込み` `大陸選手権`
——**どれも正しく書けた生産的な複合語**で、778,340語の表に
入っていないだけ。

**「後ろに立った回数」で分けようとしても分かれない**（実測）:

    誤爆側  欄 0 ／ 塊 0 ／ 画像 1 ／ 指 0 ／ 余白 0 ／ 切り替え 0
    異様側  文章 1 ／ 代価 0 ／ 家事 0 ／ 帰任 0 ／ 仮名 1

**同じ値である。** 表が生産的な複合語を持っていないため、
「見たことがない」は「日本語に無い」を意味しない。

### **だから、これは門ではない。比べるときの材料である。**

**絶対の異様さは、同梱の材料からは出ない**（項目48-HP に5軸の実測）。
出るのは**直し先と比べたとき**だけ。この道具の使い道は:

  - **直し先を作るときの歯止め**（`can_join` が False の複合語を
    新しく作らない）——**refuse する向き**にだけ使う。安全側。
  - 診断（`probe_*` から呼んで、材料の性質を見る）

**印だけで直してはいけない。** うにさんの決まり
「**正しく書いたものを壊さない**」に反する。
"""

import gzip
import os
import collections

MIN_WORDS = 100000

_WORDS = None
_LEFT = None
_RIGHT = None
_PAIR = None
_LOADED = False

# 後ろに立った実績が**これ以上**あれば、ふつうに後ろへ立つ語とみなす。
# 2 にしたのは、`文章`(1) `仮名`(1) と `補正`(2) `全体`(3) のあいだに
# 線が引けたため（2026-08-21 に実測。うにさんの材料）。
RIGHT_MIN = 2

# **位置・方向を表す1字の名詞**（項目48-HT）。
# 接頭辞と同じく「何にでも付く」ので、後ろとの相性を問わない。
# **閉じた類**である（新しく増えない）。解析の品詞は
# `名詞:一般` としか言わないため、ここで補う。
_POSITION_KANJI = set('上下左右前後内外中表裏奥端横縦先元底頭尾')

# **否定の接頭辞**（項目48-IP）。`不一致` `非対応` `未確定` `無関係` の
# 頭。後ろに付く相手を選ばないので、前の語との相性を問わない。
# 閉じた類（4字）。
_NEG_PREFIX = set('不非未無')

# **位置・順序の2字の名詞**（項目48-LJ・2026-08-30）。`文節最後`
# `画面中央` のように、どんな名詞の後ろにも「Aの最後」の略記として
# 付く。(6-3) の位置の1字と同じ**閉じた文法の類**。
# AI の判断で書き下した名簿（Fable 5・2026-08-30）。
_POSITION_TAIL2 = frozenset((
    '最後', '最初', '最終', '先頭', '末尾', '冒頭', '直前', '直後',
    '前後', '途中', '中央', '上部', '下部', '内部', '外部', '左右',
    '上下', '手前', '周辺', '付近', '前半', '後半', '全体', '両端',
    '末端', '中間'))

# **形・集合を表す1字の名詞**（項目48-IS）。`漢字塊` `文字列` `語群`
# `上層` `光束` `断片` `集団` のように、どんな名詞の後ろにも付く。
# 位置名詞と同じ閉じた類。表には1字の語が無いので、これを書かないと
# `漢字塊` が異様に見え、門を外したあと `漢字会議` に直された（実測）。
_AGGREGATE_KANJI = set('塊群層列束片団帯')

# **画面・文書の区画の1字**（項目48-JG・2026-08-25）。名詞の後ろに
# 自由に付く（空白行・補正欄・候補列・入力枠・4桁・2段・3頁）。
# 位置名詞と同じ閉じた類。`空白行` の印が誤りで、設計27 が
# `空白くい`（読み替え）へ引っぱっていた（うにさんの「補正の誤検知」）。
_LAYOUT_KANJI = set('行欄列枠桁段頁')


def _load():
    """表を作る（**必要になってから1回だけ**）。"""
    global _WORDS, _LEFT, _RIGHT, _PAIR, _LOADED
    if _LOADED:
        return _WORDS
    _LOADED = True
    path = None
    for base in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        p = os.path.join(base, 'seed_japanese.txt.gz')
        if os.path.exists(p):
            path = p
            break
    if path is None:
        return None                       # 表が無ければ**意見なし**
    try:
        words = set()
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for raw in f:
                w = raw.rstrip('\n')
                if not w:
                    continue
                if w[0] == '*':           # 狭い側の印（`seed_japanese`）
                    w = w[1:]
                words.add(w)
        if len(words) < MIN_WORDS:
            return None
        left = collections.Counter()
        right = collections.Counter()
        pair = set()
        kanji = lambda c: '一' <= c <= '鿿'
        for w in words:
            if not (2 <= len(w) <= 6) or not all(kanji(c) for c in w):
                continue
            for i in range(1, len(w)):
                a, b = w[:i], w[i:]
                if a in words and b in words:
                    left[a] += 1
                    right[b] += 1
                    pair.add((a, b))
        _WORDS, _LEFT, _RIGHT, _PAIR = words, left, right, pair
    except Exception:
        _WORDS = None
    return _WORDS


def available():
    return _load() is not None


def stats():
    if _load() is None:
        return {}
    return {'語': len(_WORDS), '割れた組': len(_PAIR),
            '前に立つ語': len(_LEFT), '後ろに立つ語': len(_RIGHT)}


def right_count(word):
    """その語が**複合語の後ろに立った回数**（診断用）。"""
    _load()
    return _RIGHT.get(word, 0) if _RIGHT is not None else 0


def _adverbial(pos):
    """
    **その品詞は「副詞として前を修飾する」側か**（項目48-KE・2026-08-27）。

    解析は副詞性を**2通りの書き方**で返す:

        `副詞:一般`         本物の副詞      一度・既に・すぐ・もっと
        `名詞:副詞可能`     名詞だが副詞にもなる  全部・今回・半分

    **見ていたのは後者だけだった。** そのため `一度無効にする` の
    (一度, 無効) が門を全部素通りして異様に立ち、設計27 が
    `一度向かうにして` に化けさせた（うにさん自身の文・実機メモ
    tab4:50。CLAUDE.md ★★③ に引く「一度無効にしたりして」そのもの）。

    **学び22 の型**——副詞性の門を片方の書き方にだけ掛けたので、
    もう片方がそこを迂回して素通りした。**決めているのはこの1か所**。
    """
    p = pos or ''
    return p.startswith('副詞') or '副詞可能' in p


def can_join(a, ap, b, bp):
    """
    **A の後ろに B がその順でくっつけるか**。

    a/b は表記、ap/bp は品詞（解析が返す文字列。`名詞,サ変接続,...`）。
    戻り値は True（くっつける）／False（**くっつけない＝異様**）／
    **None（意見なし）**。**None と False を混ぜないこと。**
    """
    words = _load()
    if words is None or not a or not b:
        return None
    ap, bp = ap or '', bp or ''
    # **品詞は解析の書き方（`名詞:接尾` のように `:` 区切り）に
    # 合わせて、部分一致で見る**（項目48-HO。`,接尾` で見ていて
    # 接尾辞が全部素通りし、`起動時` `変換中` `解決済み` が
    # 立ってしまった。2026-08-21 に実測して直した）。
    # (4) 数詞は数え方の話（3日以内・1本指）
    if '数' in ap or '数' in bp:
        return True
    # (3) 接頭詞・接尾・非自立は、くっつくのが仕事
    #     **前が接尾**の形も入れる（`1本指` の `本`＝助数詞は
    #     前の数に付いた語尾で、そこは語の境目）
    if '接頭' in ap or '接尾' in ap or '接尾' in bp or '非自立' in bp:
        return True
    # (1) 表の語の中で、その並びを見たことがある
    if (a, b) in _PAIR or (a + b) in words:
        return True
    # (1') **否定の接頭辞**（不・非・未・無）を頭に持つ語は、
    #      「A の 不一致」のように何にでも付く（型不一致・色不一致・
    #      数未確定）。否定の接頭辞は**閉じた文法の類**（4字）であって
    #      語の一覧ではない（項目48-IP。`型不一致` が正しいのに
    #      立っていた）。
    if len(b) >= 2 and b[0] in _NEG_PREFIX and b[1:] in words:
        return True
    # (1'') **かな交じりの形容動詞語幹に、名詞が直付き**は異様
    #       （項目48-KW・2026-08-29。うにさんの一覧 `好き任`）。
    #       ナ形容詞は**「な」を経て**名詞に付く（好き**な**任務）——
    #       うにさんの文法「「な」だからナ形容詞」そのもの。語幹が
    #       直接付けるのは接尾（好き放題・静かさ＝上の (3) が先に
    #       通す）だけ。漢語の語幹（安全・簡易・重要）は自由に複合語を
    #       作る（安全確認）ので、**かなを含む語幹**（和語）に限る。
    #       `好き嫌い` `きれい事` は解析が1語に切るのでここへ来ない。
    if ('形容動詞語幹' in ap and any('ぁ' <= c <= 'ゖ' for c in a)
            and bp.startswith('名詞')):
        return False
    # (6) **名詞＋動詞**。
    #     `順序入れ替え` `直接呼ぶ` は目的語・副詞＋動作でふつうの形。
    #     `差釣れ` が異様なのは、**1字の名詞が動詞に直付き**だから
    #     （差を釣れる とは言えない）。**長さと副詞性で分ける。**
    if bp.startswith('動詞') or bp.startswith('形容詞'):
        if len(a) >= 2 or _adverbial(ap):
            return True
        return (a + b) in words
    # --- ここから **くっつき方の型** で見る（項目48-HT）---------
    # うにさんの問い（2026-08-21）:
    #   「**添付とは言葉として何の分類で、画像は何の分類ですか？**」
    #
    #     添付 ＝ **名詞・サ変接続**（動作性名詞。「添付する」と言える）
    #     画像 ＝ **名詞・一般**（具体物）
    #     関係 ＝ **動作＋その対象／結果物**（＝添付された画像）
    #
    # **単語を並べるのではなく、関係の型で見る。** 型は6つだけ。
    #
    # (2) **後ろが動作性名詞** ＝ 目的語＋動作
    #       誤字補正・文字入力・挙動確認・全文走査
    #     **前は2字以上**であること。1字では目的語にならない
    #     （`素を帰任する` `経を補正する` とは言えない。
    #       接頭辞なら上の (3) で先に通っている）。
    if 'サ変接続' in bp and len(a) >= 2:
        return True
    # (2') **前が動作性名詞** ＝ 動作＋対象／結果物／場所
    #       **添付画像**・補正欄・選択切り替え・変換候補
    #       ——ここが抜けていて `添付画像` が異様に見えていた
    if 'サ変接続' in ap and len(a) >= 2:
        return True
    # (2'') **後ろが送り仮名を持つ**＝動詞・形容詞の名詞化。
    #       目的語＋動作の形になる。
    #       辞書取り込み・語彙読み込み・行の組み合わせ
    if len(b) >= 2 and not ('一' <= b[-1] <= '鿿'):
        return True
    # (6-3) **位置・方向を表す1字の名詞**は、何にでも自由に付く。
    #       右余白・上半分・内側面・奥行き。
    #       **閉じた文法の類**（接頭辞と同じ扱い）であって、
    #       語を拾い集めた表ではない。解析はこれらを
    #       `名詞:一般` としか言わないので、ここで補う。
    if len(a) == 1 and a in _POSITION_KANJI:
        return True
    # (6-3') **後ろが位置・方向の1字名詞**も同じ（項目48-JG・2026-08-25）。
    #        用紙縦・画面上・枠外・行頭 のような「名詞＋向き」の略記は
    #        メモではふつうの形。うにさんの「異様さの誤検知」——
    #        `A4用紙縦1枚` の `用紙縦` に紫が付いていた。
    if len(b) == 1 and b in _POSITION_KANJI and len(a) >= 2:
        return True
    # (6-3'') **後ろが画面・文書の区画の1字**（行・欄・列・枠・桁・段・頁）
    #         も何にでも付く（項目48-JG）。空白行・補正欄・候補列・2段。
    #         `空白行` の印が誤りで、設計27 が `空白くい`（読み替え）へ
    #         引っぱっていた（うにさんの「補正の誤検知」）。
    if len(b) == 1 and b in _LAYOUT_KANJI and len(a) >= 2:
        return True
    # (6-4) **形・集合の1字名詞**は何の後ろにも付く（漢字塊・文字列）
    if len(b) == 1 and b in _AGGREGATE_KANJI and len(a) >= 2:
        return True
    # (6-4') **位置・順序の2字の名詞**（最後・最初・先頭・直後…）も
    #        何の後ろにも付く（項目48-LJ・2026-08-30。うにさんの
    #        「補正の誤検知」——`文節最後の文字` の 文節最後 に印が
    #        立ち、設計27 が別読み（もんせつさいご）経由で `隣接最後`
    #        へ、そこを塞ぐと `文節正誤` へ引っぱった。「Aの最後」の
    #        略記はメモではふつうの形。閉じた文法の類として名簿にする)
    if len(a) >= 2 and b in _POSITION_TAIL2:
        return True
    # (6') **前が副詞になれる語**＝後ろを修飾する
    #       一番大切・最高品質・**一度無効**（項目48-KE で本物の副詞まで）
    #       副詞は**閉じた文法の類**（接頭辞・位置名詞と同じ扱い）で、
    #       後ろに立つ相手を選ばない——`一度` は `無効` と複合語を作って
    #       いるのではなく、`無効にする` という述語ごと修飾している。
    if _adverbial(ap):
        return True
    # (6'') **後ろが副詞にもなれる語**＝量・部分を表し、何にでも付く
    #       右半分・横幅全体・作業全部
    if _adverbial(bp):
        return True
    # (7) **切り方のずれ**。後ろが1字で、**前の最後の字＋後ろ**が
    #     語になるなら、`誤判定` を `誤判|定` と割っただけ。
    if len(b) == 1 and len(a) >= 2 and (a[-1] + b) in words:
        return True
    # (5) 後ろに立った実績があるか
    if _RIGHT.get(b, 0) >= RIGHT_MIN:
        return True
    return False


# 「する」の活用形（解析が動詞:自立として切る表記）。項目48-IX
_SURU_FORMS = frozenset(('し', 'する', 'した', 'して', 'します', 'しよう',
                         'しな', 'すれ', 'しろ', 'せ'))

# 連用形の尻尾（五段のい段・一段の語幹末）。項目48-JC・2026-08-25。
# 連用形は**い段**で終わる（買い・取り・押し・起き）。連体形は
# う段（閉じる・使う・付く）なので、この集合で連用形だけを選る。
_RENYOU_TAIL = frozenset('いきしちにひみりぎじびぴ')

# 単独では立てない小書きのかな（項目48-JG）
_SMALL_KANA = frozenset('ゃゅょぁぃぅぇぉっゎ')

# 行頭に裸で立てない1字の助詞（項目48-KX）。は・と・で・や は
# 文頭の言い回しがある（は？・と言えば・では・やはり の切れ端）ので
# 入れない。**閉じた類**。
_HEAD_PARTICLES = frozenset('もをへにが')

# 動詞の言い切りの尾（ウ段）。項目48-KZ (B)
_U_DAN_KZ = frozenset('うくぐすずつづぬふぶぷむゆる')


def _is_unknown_fragment(surf, known):
    """
    **辞書に無い断片**か（項目48-JG・2026-08-25）。

    解析が読みを立てられなかったトークンのうち、
      ・小書きのかな1字（`ゅ`——単独では音にならない字）
      ・ひらがな2字以上（擬態語の形 `〜と` は除く。ぱちりと）
      ・カタカナ2〜4字で、**一般的な語の表に無い**もの
        （`アプリ` `アイコン` は辞書（IPAdic・2007年ごろ）に無いだけの
          普通の語。`general_words.py`＝AI が焼いた表・版つき が守る）
    を断片とみなす。戻り値: '' か 断片の種類。
    """
    if known or not surf:
        return ''
    if len(surf) == 1 and surf in _SMALL_KANA:
        return '小書き1字'
    hira = all('ぁ' <= c <= 'ゖ' for c in surf)
    if len(surf) >= 2 and hira:
        if surf.endswith('と'):
            return ''                     # 擬態語（ぱちりと・ぱたんと）
        return 'かな断片'
    kata = all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf)
    if 2 <= len(surf) <= 4 and kata:
        try:
            from general_words import is_general
            if is_general(surf):
                return ''
        except Exception:
            pass
        return 'カタカナ断片'
    return ''


def is_odd_run(text, tokenize_fn, with_spans=False):
    """
    **その塊に「その順ではくっつけない語の並び」があるか**。

    with_spans=True なら (A, B, 始まり, 終わり) を返す（画面で色を
    付けるため・項目48-IR）。

    `tokenize_fn` は `corrector.make_tokenizer` が返す形
    （(表記, 品詞, 読み, 開始, 終了, 読みが確定か) の並び）。
    解析できない・表が無いときは **[]**（意見なし）。

    戻り値: くっつけない並びの一覧（例 `[('野外', '文章')]`）。
    **空でも「正しい」という意味ではない。**
    """
    if _load() is None or not text or tokenize_fn is None:
        return []
    try:
        toks = list(tokenize_fn(text))
    except Exception:
        return []
    # 位置は**解析が言う始まり・終わり**（t[3], t[4]）を使う。表記を
    # 足し上げると、解析が落とす空白・記号のぶんだけずれて、画面の
    # 色が隣の字に付く（項目48-IR で実測: 行頭の空白で `素帰任` が
    # `す／素` に）。無いときだけ足し上げる。
    spans, pos = [], 0
    for t in toks:
        surf = t[0] or ''
        try:
            s0, e0 = int(t[3]), int(t[4])
            if not (0 <= s0 <= e0 <= len(text)):
                raise ValueError
        except Exception:
            s0, e0 = pos, pos + len(surf)
        spans.append((s0, e0, t))
        pos = e0
    kanji = lambda c: '一' <= c <= '鿿'
    out = []
    for i in range(len(spans) - 1):
        a_s, a_e, a = spans[i]
        b_s, b_e, b = spans[i + 1]
        if a_e != b_s:
            continue
        a_sf, b_sf = a[0] or '', b[0] or ''
        ap, bp = a[1] or '', b[1] or ''
        # **助詞の「ん」に、漢字始まりの名詞が直付き**は異様
        # （項目48-KW・2026-08-29。うにさんの一覧 `平ん仮名`）。
        # 解析は ん を話し言葉の の（おれんち）と読むが、その形で
        # 漢字の名詞に続くのは「ん家（んち）」だけ。撥音 ん は
        # 語の途中の音であって、名詞と名詞の間には立てない。
        if (a_sf == 'ん' and ap.startswith('助詞')
                and bp.startswith('名詞')
                and b_sf and kanji(b_sf[0]) and b_sf[0] != '家'):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # **行頭の1字助詞に、漢字始まりの名詞が直付き**は異様
        # （項目48-KX・2026-08-29。うにさんの一覧 `も水戸に戻ります`
        # 〔もとにもどります〕・`に有力ミス`〔にゅうりょくみす〕）。
        # 係助詞・格助詞は**前の句が要る**——うにさんの文法
        # 「文の頭だから接続詞。文の間だから助詞」の裏返しで、
        # 文の頭に裸の助詞は立てない。**本当の行頭だけ**を見る
        # （読点や閉じ括弧のあとの助詞は、その前の句を受ける正しい形。
        # 実測: 「」を付与・（〜）に単語 まで見ると実機メモで36行が
        # 誤爆した。行頭だけなら立つのは的の4行だけ・誤爆0）。
        if (len(a_sf) == 1 and a_sf in _HEAD_PARTICLES
                and ap.startswith('助詞')
                and bp.startswith('名詞')
                and b_sf and kanji(b_sf[0])
                and not text[:a_s].strip(' \t　・')):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # **「を」の直後の助詞**は異様（項目48-KY・2026-08-29。
        # うにさんの指定「助詞が連続していたり」。を に続けてよい
        # 助詞は をも・をば だけ（閉じた類）。実機メモの実測:
        # 立つのは `判断をとくい`・`再起動をなどを` の誤りだけで、
        # 正しい助詞連続（ても・での・には・てから…）は
        # を を含まないので無傷）。
        if (a_sf == 'を' and ap.startswith('助詞')
                and bp.startswith('助詞') and b_sf not in ('も', 'ば')):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # === 項目48-KZ: 品詞対の規則の束（2026-08-29・うにさんの指定を
        # 実機メモ1,494行＋中立文8,400文で測って締めた形。的の見本は
        # tools_local/cases/cases_pos_rules_20260829.tsv）================
        _kz = False
        # (A) **イ形容詞の言い切りに「だ」は付かない**（赤いだ）。
        #     です は付く——丁寧形（よいです が実機に20か所超・実測）
        if (ap.startswith('形容詞') and a_sf.endswith('い')
                and bp.startswith('助動詞') and b_sf == 'だ'):
            _kz = True
        # (C) **感動詞に助詞は付かない**（はいを）。括弧ごしは
        #     位置が切れるのでここへ来ない
        elif ap.startswith('感動詞') and bp.startswith('助詞'):
            _kz = True
        # (D) **格助詞は連続しない**（をに・がを）。から・へ だけは
        #     2つ目を取れる（ここ**からが**本番・駅**へと**向かう）
        elif ('格助詞' in ap and '格助詞' in bp
                and a_sf not in ('から', 'へ')):
            _kz = True
        # (E) **名詞の読みを持たない接続詞に格助詞は付かない**
        #     （しかしを）。それゆえ・そのうえ・だから は名詞や
        #     言い回しに化けるので、閉じた名簿だけ
        elif (ap.startswith('接続詞') and '格助詞' in bp
                and a_sf in ('しかし', 'そして', 'つまり', 'ただし',
                             'なお', 'または', 'および', 'ちなみに')):
            _kz = True
        # (F) **同一の助動詞は2度続かない**（強調ぬぬ・実機の的）。
        #     ますます は副詞の1語なのでここへ来ない
        elif (ap.startswith('助動詞') and bp.startswith('助動詞')
                and a_sf == b_sf):
            _kz = True
        # (R2) **連体詞に助詞は付かない**（そのが）。ある だけは
        #      慣用（あるがまま）で除く
        elif (ap.startswith('連体詞') and bp.startswith('助詞')
                and a_sf != 'ある'):
            _kz = True
        # (S2) **イ形容詞の語幹だけ（送り仮名なし）に「て」が直付き**は
        #      異様（うにさんの案「文節最後の文字を隣接キーと疑ったら
        #      イ形容詞として自然に繋がったり」の①。`重て` ＝ 重い の
        #      い（Eキー）を て（Wキー・隣）と打った形。正しくは
        #      重い／重くて。動詞の て形（書いて・取って）は品詞が
        #      違うのでここへ来ない）
        if (ap.startswith('形容詞') and a_sf
                and all(kanji(c) for c in a_sf)
                and b_sf == 'て' and '接続助詞' in bp):
            _kz = True
        if _kz:
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # (R3) **名詞＋終助詞1字＋名詞**（平ね仮名——48-KW の ん の
        #      一般化。両側とも漢字に接する形だけ。元気だね君 は
        #      前が助動詞なのでここへ来ない）
        if (ap.startswith('名詞') and a_sf and kanji(a_sf[-1])
                and len(b_sf) == 1 and b_sf in 'ねよわさぞぜ'
                and bp.startswith('助詞') and i + 2 < len(spans)):
            _n_s, _n_e, _nt = spans[i + 2]
            if (_n_s == b_e and (_nt[1] or '').startswith('名詞')
                    and _nt[0] and kanji(_nt[0][0])):
                out.append((a_sf + b_sf, _nt[0], a_s, _n_e) if with_spans
                           else (a_sf + b_sf, _nt[0]))
                continue
        # 助詞・助動詞・記号をはさむ形は「くっついて」いない
        if any(x in ap for x in ('助詞', '助動詞', '記号')):
            continue
        if any(x in bp for x in ('助詞', '助動詞', '記号')):
            continue
        # **辞書に無い断片が、漢字始まりの内容語に直付き**（項目48-JG・
        # 2026-08-25。うにさんの指定「異様であると認識しているのかが
        # 重要です。紫の表示がなければその判定が必要です」）。
        # `にゅ力ミス`（ゅ｜力）・`きょじえかく乱`（ょじえかく｜乱）・
        # `乳リュク`（乳｜リュク）・`背中セク` の型。相手が**漢字始まり**で
        # あることが誤爆の壁——擬音・かな崩し（ぴよピヨ・きゅいー）は
        # 相手がかな・カタカナ・長音なので立たない（2026-08-25 に
        # 実機メモ1,317行で測った。`tools_local/probe_odd_fragments.py`。
        # 誤爆は辞書に無いだけの一般語（アプリ 19件）で、それは
        # `general_words.py` の表が守る）。
        a_known = bool(a[5]) if len(a) > 5 else True
        b_known = bool(b[5]) if len(b) > 5 else True
        _frag_hit = False
        for _fk, _other, _op, _o_known in (
                (_is_unknown_fragment(a_sf, a_known), b_sf, bp, b_known),
                (_is_unknown_fragment(b_sf, b_known), a_sf, ap, a_known)):
            if not _fk:
                continue
            if not _o_known:
                continue        # 相手は**辞書に載っている語**であること。
                                # janome の無い環境の簡易分割は全トークンが
                                # 「読み立たず」になるので、これが無いと
                                # 普通のかなにまで印が立つ（tests_mock で踏んだ）
            if not (_other and kanji(_other[0])):
                continue        # 相手は漢字始まり（擬音・かな崩しの壁）
            if not (_op.startswith('名詞') or _op.startswith('動詞')):
                continue
            if _op.startswith('動詞') and _fk == 'カタカナ断片':
                continue        # 付けるオンオフ の形は見ない（実測）
            _frag_hit = True
            break
        # **小書きで終わる かなの断片に、未知のカタカナ断片が直付き**
        # （項目48-KS・2026-08-29。`にゅカミス` の型——にゅ｜カミス は
        # **両方とも**辞書に無いので、上の「相手は辞書に載っている語」の
        # 条件では拾えなかった。小書きで終わって切れる音（にゅ・きょ）は
        # 語の頭が千切れた印であって、擬音・かな崩し（ぴよピヨ）は
        # 小書きで終わらないので立たない）。
        if not _frag_hit:
            _a_fk = _is_unknown_fragment(a_sf, a_known)
            _b_fk = _is_unknown_fragment(b_sf, b_known)
            if (_a_fk and a_sf and a_sf[-1] in _SMALL_KANA
                    and _b_fk == 'カタカナ断片'):
                _frag_hit = True
        if _frag_hit:
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # **漢字の名詞＋「し／する」の直付き**は異様（項目48-IX・2026-08-23・
        # うにさんの指定「`田部井号して` が異様と判定できれば」）。
        # 「N する」と言えるのは動作性名詞（サ変接続）だけ。`号して`
        # `誤字して` は、号・誤字 が動作ではないのに動詞が直付きしている。
        # **文法の類で除くもの**: 形容動詞語幹（`安定して`）、`〜化`
        # （化 がサ変を作る・`無効化して`）、`お／ご＋連用形＋する`
        # （敬語・`お渡しする`）、副詞にもなる語、数詞。カタカナ語は
        # 見ない（IPAdic は `ドラッグ` `クリック` を一般名詞と言うが
        # 外来語は自由にサ変化する。実機メモで 66 行が正しい文だった）。
        prev_sf = spans[i - 1][2][0] if i > 0 else ''
        # **1字の漢字の動詞に「し」が直付き**は異様（項目48-KX・
        # 2026-08-29。うにさんの一覧 `設計の見して`＝せっけいのみして）。
        # 連用形1字＋する は現代語に無い（`見し` は古語で、表には
        # 在るが**現代のメモに出たら打ち間違い**）。門は2つ:
        # **前に漢字が付くなら見ない**（`自走して` が 自|走|し と割れて
        # 誤爆した・実測）・**次の字まで含めて語になるなら見ない**
        # （`来し方`）。
        if (ap.startswith('動詞') and len(a_sf) == 1 and kanji(a_sf)
                and b_sf == 'し' and bp.startswith('動詞')
                and not (prev_sf and kanji(prev_sf[-1])
                         and i > 0 and spans[i - 1][1] == a_s)
                and text[a_s:b_e + 1] not in (_WORDS or ())
                and text[a_s:b_e + 2] not in (_WORDS or ())):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # (B) **動詞の言い切り（ウ段）に動詞は直接つながらない**
        # （項目48-KZ・うにさんの指定「動詞が連続しているときは、
        # 複合動詞の形になっているか見る」）。複合動詞は**連用形**から
        # 作る（読み始める）ので、ウ段のままの直付き（戻すすると・
        # ゆすかりた）は異様。**同じ語の繰り返し**（やるやる）は
        # 話し言葉なので見ない。
        if (ap == '動詞:自立' and a_sf and a_sf[-1] in _U_DAN_KZ
                and bp == '動詞:自立' and a_sf != b_sf):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        if (a_sf and all(kanji(c) for c in a_sf)
                and ap.startswith('名詞')
                and not any(x in ap for x in ('サ変', '形容動詞', '副詞可能',
                                              '数', '非自立'))
                and not a_sf.endswith('化')
                and bp.startswith('動詞')
                and b_sf in _SURU_FORMS
                and prev_sf not in ('お', 'ご')
                # 送り仮名まで含めて表の語（`見做|し`＝見做す）なら語の
                # 中の切れ目。`号し` だけが表に在っても `田部井号し` は
                # 無いので、漢字の連続ごと見る（48-IP と同じ `_run_is_word`）
                and not _run_is_word(text, a_s, b_e)):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans else (a_sf, b_sf))
            continue
        # 右は漢字始まりであること（かなへ続く形は送り仮名・活用で
        # 別の話・項目48-HN）。
        if not (a_sf and b_sf and kanji(b_sf[0])):
            continue
        if kanji(a_sf[-1]):
            # **前が、辞書に載っている姓なら意見しない**（項目48-JL・
            # うにさんの指定「**苗字を登録することで、続く後ろを名前と
            # 保護するべき**」）。名は1字でも2字でも辞書に無くて当然
            # （高橋佑・高橋ゆうた）。**読みが立っていること**（known）が
            # 条件——janome は未知語も固有名詞と推測する（48-JG で踏んだ）。
            # `奥悠久子帝` は姓が居ない（奥=固有名詞:一般・悠/久子=名）
            # ので印が立ち続ける。
            if '姓' in ap and a_known:
                continue
            # **両側とも、辞書に載っている固有名詞なら意見しない**
            # （項目48-JG・姓＋名の形）。`高橋佑`＝高橋（姓）＋佑（名）は
            # 表に無くて当然。ここを見ないと設計27 が名を読み替える
            # （高橋佑 → 高橋よう／高橋優雅・うにさんの「補正の誤検知」）。
            # 条件は2つとも要る:
            #   ・**読みが立っていること**（known）——janome は未知語も
            #     固有名詞と推測するので、品詞だけでは `子帝` まで黙る
            #   ・**両側**であること——`奥悠久子帝` は 久子（固有）＋帝
            #     （一般）の境で印が立ち続ける（片側だけで黙らせると
            #     本物の異様まで消えた。2026-08-25 に両方踏んだ）
            if '固有名詞' in ap and a_known \
                    and '固有名詞' in bp and b_known:
                continue
            # **漢字が境目で隣り合っている形**（元からの道・48-HN）
            if can_join(a_sf, ap, b_sf, bp) is not False:
                continue
        else:
            # **動詞の連用形＋名詞**（項目48-JC・2026-08-25。うにさんの指定
            # 「`買い脊柱` が異様という判定が要ります。異様ならさらに
            # 次の変換候補を追ってもらいます」・2026-08-24）。
            # `閉じる機能` と `買い脊柱` は品詞の組が同じなので品詞では
            # 割れない。分ける鍵は**活用形**——連用形は**い段**で終わる
            # （買い・取り・押し）、連体形は**う段**（閉じる・使う）。
            # 右だけ漢字始まりを要求すると実機メモ1,306行で**126行**が
            # 立つ（`正しい単語` `既に前`＝連体修飾と副詞。日本語の背骨）
            # ので、**A が動詞・B が名詞・A の尾がい段・A の頭が漢字**の
            # ときだけ見る → 誤爆は `伸ばし棒`（話し言葉の複合）の1行
            # （`tools_local/probe_odd_renyou.py`・2026-08-24 に測った）。
            if not bp.startswith('名詞'):
                continue                    # 動詞なら複合動詞（起き続け）
            if a_sf[-1] not in _RENYOU_TAIL:
                continue                    # 連体形（う段）は見ない
            if not kanji(a_sf[0]):
                continue
            if ap.startswith('動詞'):
                pass                        # 48-JC の道（買い脊柱）
            elif ap.startswith('名詞') and len(a_sf) >= 2:
                # **動詞の名詞化が前に立つ形**（項目48-KF・2026-08-27）。
                # うにさんの正解メモ `引き月資料` ＝ **`引き継ぎ資料` の
                # タイプミス**（ひきつぎ を ひきつき と打った＝濁点の脱け）。
                # 解析は `引き` を **`名詞:一般`** と言う（`引き受け` の
                # ような名詞が辞書に在るため）ので、48-JC の枝
                # （`動詞` だけ）では落ちていた。**材料は在ったのに
                # 道が無かった**——`can_join('引き','名詞:一般','月',
                # '名詞:一般')` は元から **False** と言っている。
                #
                # **門は can_join そのもの。** 実機メモ全タブで測ると
                # （`tools_local/diag_stem_run.py`・2026-08-27）:
                #     can_join を要求しない形   12組（読み込み中・打ち補正・
                #                               押し間違い・付き入力…全部正しい）
                #     can_join が False だけ    **1組＝的そのものだけ・誤爆0**
                # 育ち・初期とも同じ数字。**動詞の枝と違って直に立てない**
                # のは、名詞のほうが正しい複合語をずっと多く作るため。
                if can_join(a_sf, ap, b_sf, bp) is not False:
                    continue
            else:
                continue                    # 形容詞・副詞・連体詞は見ない
        # **塊まるごとが表の語なら、その中の並びは異様ではない**
        # （項目48-IP）。解析は `同音異義語` を `同音|異義|語` と
        # 割るので (同音, 異義) の対だけを見ると表に無いが、
        # 塊 `同音異義語` そのものは表に在る。送り仮名まで含めて
        # 語になる形（`見做|す`）も同じ。見るのは漢字の連続と、
        # その直後のかな2字まで。
        if _run_is_word(text, a_s, b_e):
            continue
        out.append((a_sf, b_sf, a_s, b_e) if with_spans else (a_sf, b_sf))
    return out


#: 正の判定で見る「自立語の名詞」の細分類（項目48-KH）
_SELF_NOUN = ('一般', 'サ変接続', '形容動詞語幹')


def is_sound_run(text, tokenize_fn):
    """
    **【いまは誰も呼んでいない】**（2026-08-28・うにさんの指示
    「外しましょう。ただし、まだ消しません。無効にして、読まれない
    ようにします。**意図的にその状態にしてることがわかるように**する」）。

    唯一の呼び元だった `corrector._chunk_is_intact` が
    `_USE_48KH_SOUND_RUN = False` で切っている。**戻すならあの旗
    1つ。** 判定そのものは壊れていないので、そのまま残してある。
    理由は `corrector.py` の `_USE_48KH_SOUND_RUN` の上の説明
    （項目48-KP で根が直り、この迂回が要らなくなった）。

    ----------------------------------------------------------------

    **その塊は、品詞の並びとして日本語ができあがっているか**——
    **正の判定**（項目48-KH・2026-08-27）。

    うにさんの指定（2026-08-27）:

        「**切り替え時、が自然な文字列と判定されないことが問題です。
          これを正しいとする分析をします。詞の組み合わせは何ですか？**」

    答えは:

        切り替え時 ＝ `切り替え`（**名詞:一般**）＋ `時`（**名詞:接尾:副詞可能**）
        起動時・保存時・入力時・変換中 と**まったく同じ組み**

    `is_odd_run` は「異様か」を見る**負の判定**しか持っていなかった。
    異様ではないことと、**日本語としてできあがっていること**は別で、
    後者が無いと「読めない解釈」のほうが勝ってしまう:

        `切り替え時` の読みは、逆算で `きりかええじ` も作られる
        （`替` の音訓に **かえ** が在り、本文の送り仮名 `え` と
          繋ぐと **え が二重**になる）。これは「読めない」ので、
        芯の再構築が費用1.0で `きりかえし`（切り返し）へ寄せた。
        **正しい読み `きりかえじ` の側は自分で断れている**
        （「読める並びを覆すほど自然にならない・差5044」）。

    **だから、塊そのものを正しいと言える判定を持つ。**
    これはうにさんの実装方針6・点2「**『でした は正常』を正の判定で
    持つ**」と同じ形。

    ### 見るもの（**閉じた形**。語の一覧ではない）

        1. 最後が **`名詞:接尾` かつ `副詞可能`**——時・中・後・前・
           時点。**時や状態を表す言い回しを作る接尾**であって、
           これが付いた形は日本語として完成している
        2. その前が**自立語の名詞**（一般・サ変接続・形容動詞語幹）で
           **2字以上**・読みが立っている
        3. 隣り合う組が全部 `can_join` を通る（異様な並びは対象外）

    ### **副詞可能に限る**（実測で締めた・2026-08-27）

        `接尾:一般` まで広げると **`待ち外`**（うにさんの的
        `待ち外 ⇒ 間違い`）まで守ってしまう。`解決済み` も
        `接尾:一般` だが、いま壊れていないので広げる理由が無い。

    守らないことを確かめたもの（実測）: 二階席・切り替え時二階席・
    引き月資料・野外文章・空白行・漢字塊・素帰任・非欄仮名・
    殺意代価・最大家事・奥悠久子帝・簡易流力・補正欄・添付画像。

    戻り値: True（できあがっている＝触らない）／False（意見なし）。
    """
    try:
        toks = [t for t in (tokenize_fn(text) or ()) if t and t[0].strip()]
    except Exception:
        return False
    if len(toks) < 2:
        return False
    a, b = toks[-2], toks[-1]
    ap = a[1] or ''
    bp = b[1] or ''
    # 1. 最後は「副詞可能の接尾」
    if not (bp.startswith('名詞') and '接尾' in bp and '副詞可能' in bp):
        return False
    # 2. その前は自立語の名詞で2字以上、読みが立っていること
    if not ap.startswith('名詞'):
        return False
    if not any(k in ap for k in _SELF_NOUN):
        return False
    if len(a[0]) < 2:
        return False
    if len(a) > 5 and not (a[5] and b[5]):
        return False
    # 3. 並び全体が、くっつける形であること
    for i in range(len(toks) - 1):
        x, y = toks[i], toks[i + 1]
        if can_join(x[0], x[1] or '', y[0], y[1] or '') is False:
            return False
    return True


def odd_spans(text, tokenize_fn):
    """
    **異様と見た範囲**（項目48-IR・画面で紫にする）。

    `is_odd_run` の対を、重なる・隣り合うものはつないで (始まり, 終わり)
    の並びにする。表が無い・解析できないときは []（意見なし）。
    """
    spans = []
    for _a, _b, s, e in is_odd_run(text, tokenize_fn, with_spans=True):
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    return spans


def _run_is_word(text, start, end):
    """位置 start〜end を含む漢字の連続（＋直後のかな2字まで）が表の語か。"""
    words = _WORDS
    if not words:
        return False
    kanji = lambda c: '一' <= c <= '鿿'
    rs, re_ = start, end
    while rs > 0 and kanji(text[rs - 1]):
        rs -= 1
    while re_ < len(text) and kanji(text[re_]):
        re_ += 1
    run = text[rs:re_]
    if run in words:
        return True
    tail = ''
    for ch in text[re_:re_ + 2]:
        if not ('ぁ' <= ch <= 'ん'):
            break
        tail += ch
        if (run + tail) in words:
            return True
    return False


if __name__ == '__main__':
    print(__doc__)
    print(stats())
