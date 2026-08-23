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

# **形・集合を表す1字の名詞**（項目48-IS）。`漢字塊` `文字列` `語群`
# `上層` `光束` `断片` `集団` のように、どんな名詞の後ろにも付く。
# 位置名詞と同じ閉じた類。表には1字の語が無いので、これを書かないと
# `漢字塊` が異様に見え、門を外したあと `漢字会議` に直された（実測）。
_AGGREGATE_KANJI = set('塊群層列束片団帯')


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
    # (6) **名詞＋動詞**。
    #     `順序入れ替え` `直接呼ぶ` は目的語・副詞＋動作でふつうの形。
    #     `差釣れ` が異様なのは、**1字の名詞が動詞に直付き**だから
    #     （差を釣れる とは言えない）。**長さと副詞性で分ける。**
    if bp.startswith('動詞') or bp.startswith('形容詞'):
        if len(a) >= 2 or '副詞可能' in ap:
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
    # (6-4) **形・集合の1字名詞**は何の後ろにも付く（漢字塊・文字列）
    if len(b) == 1 and b in _AGGREGATE_KANJI and len(a) >= 2:
        return True
    # (6') **前が副詞になれる語**＝後ろを修飾する
    #       一番大切・最高品質
    if '副詞可能' in ap:
        return True
    # (6'') **後ろが副詞にもなれる語**＝量・部分を表し、何にでも付く
    #       右半分・横幅全体・作業全部
    if '副詞可能' in bp:
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
        # 助詞・助動詞・記号をはさむ形は「くっついて」いない
        if any(x in ap for x in ('助詞', '助動詞', '記号')):
            continue
        if any(x in bp for x in ('助詞', '助動詞', '記号')):
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
        # **漢字が境目で隣り合っているときだけ見る**。
        # かなが挟まる形は送り仮名・活用で、別の話（項目48-HN）。
        if not (a_sf and b_sf and kanji(a_sf[-1]) and kanji(b_sf[0])):
            continue
        if can_join(a_sf, ap, b_sf, bp) is not False:
            continue
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
