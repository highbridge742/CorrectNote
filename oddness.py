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

# **形容詞の語幹として名詞の頭に立つ1字**（項目48-SN・2026-09-06）。
# 強炭酸・厚爪・高濃度・低価格・長時間・軽自動車・大容量・新機能。
# 解析は `強` を 形容詞:自立（つよ）と切り、`厚` を 地域（あつ）と切る
# ——品詞では拾えない字を、**閉じた名簿**で補う。
# AI の判断で書き下した（Fable 5.1・2026-09-06）。語の一覧ではなく
# 「語幹1字＋名詞」という**文法の型**の側の名簿。
_ADJ_STEM_KANJI_1 = frozenset(
    '強弱高低厚薄長短軽重大小新古多少早遅速広狭深浅細太濃淡'
    '冷温熱寒暑安甘辛苦若近遠固硬柔軟良悪鋭鈍粗密')

# **何にでも付く接尾**（項目48-SN・2026-09-06）。`説明書付き` の
# （書, 付き）のように、接尾どうしの並びでも後ろがこれなら異様ではない。
_SUFFIX_TAIL_FREE = frozenset((
    '付き', '付', '入り', '済み', '済', '向け', '込み', '無し', '有り',
    '用', '別', '同士', '同然', '同様', '以外', '以来'))

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

#: **要素・単位をつくる1字の名詞**（項目48-NB・2026-08-31）。
#: 学術の文で「〜素」のように、何にでも付いて「その要素」を作る
#: （形態素・音素・語彙素・水素・酸素・元素・色素・要素／接頭辞・
#: 接尾辞／第一項）。解析はこれらを **名詞:接尾 とは言わず
#: 名詞:一般**と言う——形態素・音素・水素 は1語として辞書に在るので
#: ふだんは露わにならず、**辞書に無い組み合わせ（語彙素）だけが
#: 割れて異様に見えていた**。
#: `_POSITION_KANJI`・`_LAYOUT_KANJI`・`_AGGREGATE_KANJI` と同じ
#: **閉じた文法の類**（語を拾い集めた表ではない）。
_ELEMENT_KANJI = set('素辞項')

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


#: **ナ形容詞の語幹が、裸のままでは用言の前に立てない語**
#: （項目48-NM'・2026-09-01・うにさんの指定）:
#:
#:     「**元気**の2つの顔
#:       ・**ナ形容詞（形容動詞）の語幹**としての顔——「元気な人」
#:         「元気に遊ぶ」「元気だ」のように「な・に・だ」を連れる
#:       ・**名詞**としての顔——「元気を出す」「元気がある」
#:         「元気の源」のように**格助詞（を・が・の）を連れて**
#:         そのものを指す
#:       『元気出して』は『元気**を**出して』から格助詞が省略された形。
#:       **AIならここまで行けるはずです。アプリの判定がすべてと
#:       思わないで。**」
#:
#: **格助詞は落とせる。活用語尾は落とせない。** `静か歩く` は
#: `静かが/静かを歩く` がどちらも成り立たないので、落ちたのは
#: 語尾「に」しかない＝**異様**。`元気出して` は「を」が落ちた形＝**自然**。
#:
#: 解析では分けられない（実測——`元気/静か/有力` は `〜がある`
#: `〜を出す` `〜の源` `〜な人` の**どの形でも** `名詞:形容動詞語幹`）。
#: **ここは AI の判断を焼いた表で分ける。**
#:
#: **掛ける側に持つ**（除外名簿にしない）——載っていない語は**黙る**。
#: 未知語が漏れたときに壊す側へ落ちないため（壊さない ＞ 直る）。
#:
#: **落としたのは2種類の「顔」**:
#:   名詞の顔  元気・自由・安全・無理・無駄・必要・便利・品薄…
#:   **副詞の顔**  大変助かる・十分足りる・散々言われた・突然消えた
#:                （「に」を入れると壊れる／意味が変わる。**IPAdic に
#:                  副詞の項が無く、全部 `名詞:形容動詞語幹` になる**）
#: **カタカナ語は1語も入れない**（`ラフ描く` `ムリある` `ダメ出す`
#: `クール入る` はどれも正しい日本語で、解析は全部 形容動詞語幹）。
#:
#: **出どころ**: 語の選別は **この AI（Claude Opus 4.6・2026-09-01）が
#: 日本語として判断した**もの。9人がかりで3通りに書き下し、
#: それぞれに反例を当てて叩いてから残した。**迷った語は載せない**
#: （確か・明らか・柔らか・大丈夫・見事・丁寧 は降りた）。
_NAADJ_STEM_ONLY = frozenset("""
静か 賑やか 穏やか 和やか 健やか 爽やか 鮮やか 細やか 軽やか 華やか
緩やか 冷ややか 滑らか 清らか 安らか 朗らか 速やか 平ら 愚か 密か
微か 厳か 豊か
綺麗 奇麗 きれい 素直 素敵 立派 健気 惨め 呑気 気楽 気軽 手軽
身近 不憫 大雑把 大切 新た
有力 有名 有能 優秀 良好 順調 適切 妥当 的確 明確 正当 厳密
精密 精巧 巧妙 絶妙 微妙 曖昧 重大 深刻 悲惨 凄惨 残念 素朴
高潔 温厚 謙虚 寛大 傲慢 冷酷 残酷 卑劣 陰険 快適 爽快 軽快
迅速 急速 頻繁 簡単 容易 単純 複雑 多彩 莫大 巨大 広大 壮大
偉大 強力 強大 強引 強硬 高価 安価 上品 下品 熱心 勤勉 怠惰
大胆 律儀 几帳面 敏感 鈍感 主要 丈夫 頑丈 清楚 質素 安易 無難
地道 露骨 唐突 悠長 円滑 良質 潤沢 頑固 柔軟
""".split())

#: **現代語の「なる」**。語幹の直後に来たら、**語が何であれ**
#: 「に」が落ちている（アクティブ**に**なっていない・品薄**に**
#: なっている・無効**に**なった）。ここだけ**名簿が要らない**——
#: うにさんの的の片方 `アクティブなっていない` はこの門で拾う
#: （カタカナ語を名簿に入れるのは族ごと危ない）。
_NAADJ_NARU = frozenset(('なっ', 'なり', 'なる'))

#: **語幹に直に付いてよい動詞**（ここでは何も言わない）。
#:   なら・なれ  文語（容易**ならぬ** 事態／静か**なれば**）
#:   ぶる・ぶっ  「〜のように振る舞う」（上品**ぶる**／謙虚**ぶって**）
_NAADJ_BARE_OK = frozenset(('なら', 'なれ', 'ぶる', 'ぶっ', 'ぶら', 'ぶれ'))


def naadj_stem_bare(a, ap, b, bp):
    """
    **ナ形容詞の語幹が裸のまま用言の前に立っている**か（項目48-NM'）。

        静か|歩く      → 静か**に**歩く    異様（表に在る）
        アクティブ|なっ → アクティブ**に**なって  異様（門α）
        元気|出し      → 元気**を**出して   **自然**（表に無い）
        大変|助かる    → 副詞の顔          **自然**（表に無い）
    """
    if '形容動詞語幹' not in ap:
        return False
    if not (bp.startswith('動詞') or bp.startswith('形容詞')):
        return False
    if b in _NAADJ_BARE_OK and bp.startswith('動詞'):
        return False
    if b in _NAADJ_NARU and bp.startswith('動詞'):
        return True
    return a in _NAADJ_STEM_ONLY


#: **疑問の代名詞**（項目48-OX・2026-09-03）。閉じた表。
#: 名詞の直後に置けるのは「は・を・が が落ちた形」だから
_QUESTION_PRONOUNS = frozenset((
    '何', 'なに', 'なん', '誰', 'だれ', 'どこ', 'いつ', 'どれ',
    'どっち', 'どちら', 'どなた', 'いくつ', 'いくら',
))


def _hira(text):
    """カタカナの読みを ひらがな に（項目48-OV）。読めなければ空。"""
    if not text:
        return ''
    try:
        from morphology import katakana_to_hiragana
        return katakana_to_hiragana(text)
    except Exception:
        return text


def _kun_noun_1(a, ap, a_reading):
    """
    **1字の名詞で、解析が訓読みで読んでいる**か（項目48-OV・2026-09-03）。

    水（みず）・手（て）・目（め）・家（いえ）・車（くるま）・
    力（ちから）・技（わざ）——**それだけで立つ和語の名詞**。
    こういう1字の名詞は `水飲む`・`手洗う` のように**格助詞が落ちた
    口語**でふつうに動詞に直付きする（うにさんの検討・2026-09-03）。

    **音読みの1字は入れない**（本＝ほん・駅＝えき・差＝さ）。
    `差釣れ`（48-HT の的）が異様のまま残ることが要る。
    音読みの1字を通すかは**別に測る**（引き継ぎの次の段）。

    読みが取れない・表が読めないときは False（今までどおり）。
    """
    if len(a) != 1 or not ('一' <= a <= '鿿'):
        return False
    if not ap.startswith('名詞:一般'):
        return False
    if not a_reading:
        return False
    try:
        import kanji_onkun as _ok
        if not _ok.available():
            return False
        return _ok.kind_of(a, a_reading) == 'kun'
    except Exception:
        return False


#: **接尾どうしでも並べる組**（項目48-KZ(G)・2026-09-03）。
#: 実機メモ2,144行を走査して残った誤爆は `語系`（セム語系）だけ
#: ——ほかの3つ（次号・語派・強勢）は `a+b` が表の語なので自動で外れる。
_SUFFIX_PAIR_OK = frozenset((
    ('語', '系'),
))


def _nominal_action_head(surface,pos,reading):
    """一字の名詞＋動作名詞を、訓読みだけで完成形と決めない。

    形容動詞語幹の別解を持つ字は、名詞の目的語と修飾語幹を
    この二語だけでは区別できない。既知の複合語や別の接続根拠に委ねる。
    口語の名詞＋動詞の既存規則は変更しない。
    """
    if not _kun_noun_1(surface,pos,reading):
        return False
    from morphology import dictionary_base_pos
    positions=dictionary_base_pos(surface)
    if positions is None:
        return False
    return not any(p.startswith('名詞,形容動詞語幹,') for p in positions)


def layout_position_pair(a, ap, b):
    """48-XT: 区画名1字に位置名が付く名詞句。判定と完成形で共有。"""
    return a in _LAYOUT_KANJI and _plain_noun(ap) and b in _POSITION_TAIL2


def can_join(a, ap, b, bp, a_reading=''):
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
    # (3-1) **何にでも付く尾**（項目48-SN・`_SUFFIX_TAIL_FREE`。解析が接尾と
    #       言わない `同士`〔語彙素同士・友達同士〕もここで通す）
    if b in _SUFFIX_TAIL_FREE:
        return True
    # (3') **形容詞の語幹1字は名詞の頭に付く**（項目48-SN・2026-09-06。
    #      強風・高濃度・低価格・長時間）。解析は `強` を
    #      形容詞:自立（つよ）と切る。語幹1字＋名詞は複合名詞の**型**。
    #      解析が形容詞と言わない字（厚＝地域・薄・濃…）は閉じた名簿
    #      `_ADJ_STEM_KANJI_1` で補い、自然な複合語の分断を防ぐ。
    #      **動詞の連用形にも付く**（48-TE・2026-09-06。浅煎り・早起き・
    #      遅咲き・深煎り——形容詞語幹＋連用形の複合名詞。`浅煎りブレンド`
    #      に紫が立っていた）
    if (len(a) == 1 and '一' <= a <= '鿿' and bp.startswith(('名詞', '動詞'))
            and (ap.startswith('形容詞') or a in _ADJ_STEM_KANJI_1)):
        return True
    # (3'') **地名は何にでも付く**（項目48-SN。九州方言・東京在住・
    #       北海道産・現代九州）。固有名詞は 48-NG で `_plain_noun` から
    #       外してある（人名は誤変換の常連）が、**地域**は「Aの」の略記で
    #       どんな名詞にも付くし、名詞の後ろにも立つ
    if (('地域' in ap and len(b) >= 2 and _plain_noun(bp))
            or ('地域' in bp and len(a) >= 2 and _plain_noun(ap))):
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
    # (1''') **ナ形容詞の語幹に、動詞・形容詞が直付き**は異様
    #        （項目48-NM・2026-09-01。うにさんの列挙）:
    #
    #     有力な／有力に／有力で／有力だ／有力なら／有力ならば／
    #     有力です／有力だった／有力だした／有力ではない／
    #     有力じゃない／有力でしょう／有力だろう／有力。／有力！
    #
    #   「だ」＝断定の助動詞。「な」＝その連体形。「に」「で」＝
    #   格助詞・接続助詞、または「だ」の連用形。
    #   ——**後ろに来られるのは「だ」の活用形と、助詞・記号だけ。**
    #
    #   **名詞は入れない。** うにさんの整理（2026-09-01）:
    #     「『重要ポイント』はナ形容詞ではなく、**複合名詞**。
    #       『重要』は…**基本は名詞**です」
    #   解析は 重要・自由・自然・安全・特殊 を全部 `形容動詞語幹` と
    #   言うが、**どれも名詞でもある**ので、名詞が続けば複合名詞
    #   （48-NA が既に「名詞どうしは作れる」と裁いている）。
    #   実測でも、名詞まで広げると **8件増えて全部が誤検知**だった
    #   （自由形態素・自然発生・単純計算・特殊動詞）。
    #
    #   **動詞・形容詞は複合名詞になりようがない**ので、ここだけ採る
    #   （静か**に**歩く の「に」が要る）。実機メモでは増減0——
    #   **いまの材料に当たりは無いが、判定としては正しい守り**。
    #   **一律に False にすると誤爆する**（項目48-NM'・2026-09-01）。
    #   `元気出して`（＝元気**を**出して・格助詞落ち）・`品薄続く`・
    #   `大変助かる`（副詞の顔）は全部正しい日本語。**表に載っている
    #   語だけ**が立つ（`naadj_stem_bare`）。
    if naadj_stem_bare(a, ap, b, bp):
        return False
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
        # **1字の訓読みの名詞＋動詞は、格助詞の落ちた口語**
        # （項目48-OV・2026-09-03）。`水飲む`＝水**を**飲む・
        # `家帰る`＝家**に**帰る。`差釣れ`（音読み）は残る
        if _kun_noun_1(a, ap, a_reading):
            return True
        return (a + b) in words
    # (6') **名詞＋疑問の代名詞**（項目48-OX・2026-09-03）。
    #      `昼ご飯**何**にする` は「昼ご飯**は** 何にする」の
    #      **は が落ちた形**（助詞の省略の族・うにさんの検討）。
    #      **閉じた表**——人称の代名詞（彼・私・それ）は入れない
    #      （`ご飯彼` は異様のまま）
    if '代名詞' in bp and b in _QUESTION_PRONOUNS:
        return True
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
    #     訓読みの一字名詞も目的語になる（本確認・水補給・技発動）。
    #     名詞＋動詞の口語接続と同じ判定を使い、文字数だけで退けない。
    #     音だけの一字断片は従来どおり別の根拠を必要とする。
    if 'サ変接続' in bp and (len(a) >= 2 or _nominal_action_head(a, ap, a_reading)):
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
    # (6-4'') **要素・単位の1字名詞**も同じ（項目48-NB）。語彙素・
    #         形態素・接尾辞。**1字の尻尾を「後ろに立った実績」で
    #         数える形は測って落とした**——表の1字の尻尾は地名の接尾
    #         （町7399・駅2942・村1583）が桁違いに多く、床をどこに
    #         置いても `月`(72) が通って `引き月資料` の的が消えた。
    if len(b) == 1 and b in _ELEMENT_KANJI and len(a) >= 2:
        return True
    # 名詞に付く『例』は、その事柄の具体例を作る生産的な接尾用法。
    # 要素の単位（素・辞・項）とは分け、前が名詞の場合に限る。
    if b == '例' and _plain_noun(ap):
        return True
    # (6-4') **位置・順序の2字の名詞**（最後・最初・先頭・直後…）も
    #        何の後ろにも付く（項目48-LJ・2026-08-30。うにさんの
    #        「補正の誤検知」——`文節最後の文字` の 文節最後 に印が
    #        立ち、設計27 が別読み（もんせつさいご）経由で `隣接最後`
    #        へ、そこを塞ぐと `文節正誤` へ引っぱった。「Aの最後」の
    #        略記はメモではふつうの形。閉じた文法の類として名簿にする)
    # 48-XT: 行・列・欄などの区画名は1字でも位置の付加先になる。
    # A列末尾の「列」を長さだけで断らない。一般の1字名詞や
    # 人名へは広げず、既存の区画名と位置名の分類を共有する。
    if b in _POSITION_TAIL2 and (len(a) >= 2
            or layout_position_pair(a, ap, b)):
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
    # (8) **名詞どうしの複合は、日本語では既定で作れる**（試し・48-NA）
    if (_plain_noun(ap) and _plain_noun(bp)
            and len(a) >= 2 and len(b) >= 2):
        return True
    # (5) 後ろに立った実績があるか
    if _RIGHT.get(b, 0) >= RIGHT_MIN:
        return True
    return False


_NOUN_NG = ('固有名詞', '接尾', '接頭', '非自立', '代名詞', '数', '副詞可能')


def _plain_noun(pos):
    return (pos or '').startswith('名詞') and not any(
        x in (pos or '') for x in _NOUN_NG)


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


def _is_unknown_fragment(surf, known, dict_index=None, kata_split=False):
    """
    **辞書に無い断片**か（項目48-JG・2026-08-25）。

    解析が読みを立てられなかったトークンのうち、
      ・小書きのかな1字（`ゅ`——単独では音にならない字）
      ・ひらがな2字以上（擬態語の形 `〜と` は除く。ぱちりと）
      ・カタカナ2〜4字で、**世の中の語ではない**もの
        （`アプリ` `アイコン` は辞書（IPAdic・2007年ごろ）に無いだけの
          普通の語。判定は `_katakana_word_known` ただ1つ・項目48-OY——
          AI の表・外来語の表・**同梱の費用の表**・**索引の読み**の4つ）
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
        # **世の中の語かどうかは1か所で決める**（項目48-OY・48-GN）。
        # ただし**カタカナの連なりの途中で切れている**なら、
        # 世の中の語でも「1語を割った跡」（項目48-OY'）
        if not kata_split and _katakana_word_known(surf, dict_index):
            return ''
        return 'カタカナ断片'
    return ''


def in_reading_gloss(text, p):
    """
    位置 p が「**読みの注記**」の括弧の中か（項目48-NW・2026-09-01）。

        同音異義語（どうおん**い**ぎご）
        精肉（**せい**にく）

    注記の中は**書きたくて書いたかな**なので、解析はほぼ必ず壊れる
    （`せいにく` → せい(命令ｉ)＋にく(形容詞:非自立)）。**そこの
    活用形の接続を見てはいけない。**

    判定そのものは `corrector.is_reading_gloss`（項目48-LN・
    うにさんの規則「直前に漢字があり、括弧に入った平仮名は、
    平仮名として書きたい意図がある」）を**借りる**
    ——同じ判定をもう一度書かない（項目48-GN）。
    ここが足すのは「**注記の頭か**」を「**注記の中か**」に
    広げるところだけ。
    """
    if not text or p <= 0:
        return False
    j = max(text.rfind('（', 0, p), text.rfind('(', 0, p))
    if j < 0:
        return False
    # あいだに閉じ括弧があれば、その括弧はもう閉じている
    for c in ('）', ')'):
        k = text.find(c, j)
        if 0 <= k <= p:
            return False
    try:
        from corrector import is_reading_gloss
    except Exception:
        return False
    return bool(is_reading_gloss(text, j + 1))


def _katakana_word_known(surf, dict_index=None, spelling=False):
    """
    その**カタカナ語が、世の中に在る**か（項目48-OR・2026-09-03／
    **出どころを増やした 48-OY・同日**）。

    ★★ `spelling=True` は「**その綴りが在るか**」を聞く形
    （項目48-TY・2026-09-07）。**費用表だけは外す。**理由は下の
    48-RO の注記のとおり——費用表は読みごとにカタカナ綴りを
    **作って**持っているので、**綴りの証拠にならない**。
    聞き分けが要るのは、**この判定が向きの違う2つに使われている**から:

        異様か（紫を立てるか）  読めなければ「意見なし＝守る側」。
                                 広く採るのが安全（48-OY で足した）
        **生やしてよいか**       採ると**書いていないカタカナを画面に
        （48-SU の門）           出す**。広く採るのは危険な側

    同じ問いに見えて、**間違えたときに壊れる向きが逆**。だから
    出どころの数を引数1つで分ける（判定を2つ書かない・48-GN）。

    `クリック` `ドラッグ` `スクロール` は在る。`リュク` `カミス` は無い。

    ★★ **まず `katakana_frag` の断片の表を引く**（項目48-RO）——
    載っていれば **False**（＝印を立ててよい）。理由は下の本文。

    **出どころは4つ**（どれか1つでも在れば「世の中の語」。名簿は
    増やすだけで、消さない）:

        `general_words.is_general`            AI が焼いた表・版つき
        `loanword._katakana_seed_all`         同梱の外来語 9,094 語
        **`corrector._table_cost`**           同梱の費用の表（SudachiDict 由来）
        **`dict_index.is_world_reading`**     刈り込む前の読み

    **48-OY で後ろの2つを足した**（2026-09-03）。外来語の表は
    9,094 語しか無く、**短い日常語が抜けていた**——`ブレ`・`プレイ`・
    `タブ`・`ミス`・`メモ`・`ズレ`・`ブレイク` は載っていないのに、
    `出力ブレ`・`プレイ動画` に紫が立っていた。
    費用の表は `リュク`・`カミス` を持たないので、**断片は断片のまま**。

    どれも読めなければ **True**（意見なし＝守る側）。
    """
    if not surf or len(surf) < 2:
        return False
    if not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf):
        return False
    # ★★ **断片の表を、いちばん先に引く**（項目48-RO・2026-09-05・
    # うにさんの報告「`解析課背中セク、`——まず `背中セク` が異様な
    # のでそう判定しないといけない。**セクが組織名である判定が変**」）。
    #
    # 下の4つのうち**費用表と世の読みは、カタカナに対しては
    # 読みの証拠であって綴りの証拠ではない**——費用表は読みごとに
    # そのカタカナ綴りを表記として持つ（`せく → セク:35 咳く:145`）。
    # 2字の読み 3,036 のうち 1,838（60%）にカタカナ形が在り、
    # たいてい最安。つまり `_table_cost('セク')` が返すのは
    # 「**せく と読む語が在る**」でしかなく、`セク` という綴りが
    # 語かどうかを1つも言っていない。**だから表で割る**
    # （`katakana_frag`・AI の判定・版と出どころつき）。
    # 表に無ければ何も言わない＝今までどおり下の4つで決める。
    try:
        import katakana_frag as _kf
        if _kf.is_fragment(surf):
            return False
    except Exception:
        pass
    try:
        from general_words import is_general
        if is_general(surf):
            return True
    except Exception:
        pass
    if not spelling:
        # ★★ **綴りを聞かれているときは、費用表を証拠にしない**
        # （項目48-TY）。この表だけが認めるカタカナ形は、
        # 語の綴りが実在する証拠にはならない。
        try:
            import corrector as _C
            if _C._table_cost(surf) is not None:
                return True
        except Exception:
            pass
    if dict_index is not None:
        try:
            from morphology import katakana_to_hiragana as _h
            if dict_index.is_world_reading(_h(surf)):
                return True
        except Exception:
            pass
    try:
        from loanword import _katakana_seed_all
        from morphology import katakana_to_hiragana
        return katakana_to_hiragana(surf) in (_katakana_seed_all() or {})
    except Exception:
        return True             # 表が読めない＝意見なし（守る側）


def _proper_noun_is_trusted(t, store, dict_index):
    """
    **その固有名詞は信用してよいか**（項目48-OR・2026-09-03・
    うにさんの指定「**人名や地名判定になるとそこから先に進まない。
    それらの判定はもっと後の段階で処理するべき**」）。

    ①（異様か判定する）では、固有名詞を**特別扱いしない**。
    解析が「これは人名／地名です」と言っただけで黙るから、
    `右田でブルクリック` に印が立たなかった（`右田`＝地域・
    `ブル`＝人名:姓 と読まれる）。**守るのは「本人の語」と
    「登録した姓」**で、そこは④（決める）で今までどおり守る
    （`_is_whole_proper_noun`・48-JL）。

    信用してよいのは4つ（**どれか1つでも当たれば今までどおり**）:

        (1) **本人の語彙に実績2以上**（育ちの 高橋・柚須）
        (2) **漢字だけで書かれた姓**——48-JL「苗字を登録することで、
            続く後ろを名前と保護する」の持ち場。**カタカナの姓は
            数えない**（`ブル` を人名:姓 と読むのは解析の当て推量で、
            日本語の姓としては書かれていない）
        (3) **カタカナは、人名でなければ信用する**（ドイツ＝地域:国・
            トヨタ＝組織。表記が固定していて当てずっぽうにならない）。
            **人名は、世の中のカタカナ語の表に在るときだけ**
            （IPAdic の人名は数が多く、`ブル`＝ダブル の千切れ まで
              「人名:姓」に化ける）
        (4) **読みが世の中に在る**（同音の普通語が在る）——
            索引は固有名詞を外して作ってあるので、ここが立つのは
            「その読みで書かれる普通の語が別に在る」ときだけ

    `store` も `dict_index` も無ければ **True**（意見なし＝今までどおり）。
    **そもそも落としてよい形か**は `_proper_noun_downgradable` が
    先に見る（ひらがなだけ／カタカナの連なりの端）。
    """
    if store is None and dict_index is None:
        return True
    surf = t[0] or ''
    if not surf:
        return True
    kata = all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf)
    rd = ''
    try:
        from morphology import katakana_to_hiragana
        rd = katakana_to_hiragana(t[2] or '') if len(t) > 2 else ''
    except Exception:
        rd = ''
    if not rd or not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in rd):
        return True             # 読みが取れない＝意見なし
    # (1) 本人の語彙に実績2以上
    if store is not None:
        try:
            if any(e.get('surface') == surf
                   and (e.get('count', 0) or 0) >= 2
                   for e in store.lookup(rd)):
                return True
        except Exception:
            return True
    pos = (t[1] or '') if len(t) > 1 else ''
    if kata:
        # (3) カタカナの固有名詞
        #   ・**人名以外**（地域・国・組織）は今までどおり信用する。
        #     `ドイツ`（地域:国）・`トヨタ`（組織）は表記が固定して
        #     いて、解析の当てずっぽうにならない。
        #     **測って受け止めた門**——ここを外したら
        #     `ドイツ語 → 同一かたり` を作った（実機メモ1行・2026-09-03）
        #   ・**人名**は、世の中のカタカナ語の表に在るときだけ信用する。
        #     IPAdic の人名は数が多く、`ブル`（＝ダブル の千切れ）の
        #     ような断片まで「人名:姓」に化ける
        # **人名は信用しない**（`_proper_noun_downgradable` が
        # 「カタカナの連なりの途中」に絞ってあるので、そこに立つ
        # 人名は**1つのカタカナ語を割った跡**）。
        # **48-OY で世の中の表を広げたので、`ブル` も「在る語」に
        # なった**——`_katakana_word_known` で裁くと
        # `右田でブルクリック` が届かなくなる。**門1つに任せる**
        return '人名' not in pos
    # (2) 漢字だけの姓
    if '姓' in pos and all('一' <= c <= '鿿' for c in surf):
        return True
    # (4) 同音の普通語が在る
    if dict_index is not None:
        try:
            if dict_index.is_world_reading(rd):
                return True
        except Exception:
            return True
    return False


def _kata_run_continues(toks, i):
    """
    位置 i のトークンの**隣にもカタカナが続いているか**（項目48-OR）。

    カタカナの連なりの**途中**で `固有名詞:人名` が現れるのは、
    **解析が1つのカタカナ語を割った跡**（`ブル|クリック`）。
    連なりの端に立つカタカナ語（`縦|シュー|という`）は、
    書いた人がそう書いた語なので触らない。
    """
    def _kata(c):
        return 'ァ' <= c <= 'ヶ' or c == 'ー'
    prev = (toks[i - 1][0] or '') if i > 0 else ''
    nxt = (toks[i + 1][0] or '') if i + 1 < len(toks) else ''
    return bool((prev and _kata(prev[-1])) or (nxt and _kata(nxt[0])))


def downgraded_tokens(toks, store=None, dict_index=None):
    """
    **信用できない固有名詞の「読みが立った」を落とした並び**を返す
    （項目48-OR・2026-09-03）。**判定はここ1つ**——`is_odd_run` と、
    印を受け取って開く側（`corrector._reopen_mixed_run_fixes` の
    断片の見立て）が**同じ並びを見る**ようにするため（学び22——
    片方だけに置くと、印は立つのに断片と数えられない、が起きる）。

    `store` も `dict_index` も無ければ**そのまま返す**（意見なし）。
    t[6]（活用形・48-NT）は落とさない。
    """
    if store is None and dict_index is None:
        return list(toks)
    out = []
    for i, t in enumerate(toks):
        if (len(t) > 5 and t[5] and '固有名詞' in (t[1] or '')
                and _proper_noun_downgradable(toks, i)
                and not _proper_noun_is_trusted(t, store, dict_index)):
            t = tuple(t[:5]) + (False,) + tuple(t[6:])
        out.append(t)
    return out


def _proper_noun_downgradable(toks, i):
    """
    **その固有名詞は、そもそも落としてよい形か**（項目48-OR・
    2026-09-03。**測って足した門**——紫の全行検品で出た誤検知2種を
    そのまま外す形にした）。

        ・**ひらがなだけの固有名詞は落とさない**
          `ひらがなを漢字にしたり` を janome は
          `ひ|ら|が|**なを**(人名:名)|漢字` と割る。ここを断片に
          数えると、**正しい文に紫が立つ**（実機メモ2行）。
          ひらがなは助詞・送り仮名が混ざる字種なので、断片として
          数えない（48-MV「ひらがなを含む印は開かない」と同じ理由）
        ・**カタカナは、連なりの途中に立つときだけ**落とす
          `ブル|クリック` は**1つのカタカナ語を割った跡**だが、
          `縦|シュー|という` の `シュー` は書いた人がそう書いた語
          （実機メモ1行）
    """
    surf = (toks[i][0] or '') if i < len(toks) else ''
    if not surf:
        return False
    if all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in surf):
        return False
    if all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surf):
        return _kata_run_continues(toks, i)
    return True


def _fragment_has_parallel_noun_context(text, start, end, tokenize_fn):
    """辞書未収録という証拠だけを、既存の名詞並列の正の証拠と照合する。"""
    if not all('一' <= c <= '鿿' for c in text[start:end]):
        return False
    while start > 0 and '一' <= text[start-1] <= '鿿':
        start -= 1
    while end < len(text) and '一' <= text[end] <= '鿿':
        end += 1
    from corrector import _parallel_noun_context
    return _parallel_noun_context(text, start, end, tokenize_fn)


def shortcut_case_spans(text, tokens):
    """キーの組合せ＋出＋名詞を、操作手段の格助詞の誤変換として検出。

    GPT-6による構造規則（2026-09-10）。出力/出口の語中や出身表現は対象外。
    """
    if '出' not in text or '+' not in text:
        return []
    import re
    chord = re.compile(r'(?<![A-Za-z0-9_])(?:(?:Ctrl|Control|Alt|Shift|Win|Cmd|Command|Option|Meta)\+)+'
                       r'(?:[A-Za-z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|Tab|Enter|Return|Esc|Escape|Space|Delete|Backspace|Home|End|PageUp|PageDown|Up|Down|Left|Right)$', re.I)
    out = []
    for a,b in zip(tokens,tokens[1:]):
        if not (a[0] == '出' and a[2] == 'で' and a[5]
                and (a[1] or '').startswith('名詞:接尾')
                and a[4] == b[3] and b[5]
                and (b[1] or '').startswith('名詞')
                and not any(x in (b[1] or '') for x in ('接尾','非自立','固有名詞'))):
            continue
        if chord.search(text[max(0,a[3]-96):a[3]]):
            out.append((a[3],a[4]))
    return out


_PROPERTY_BASE_SOURCE = None
_PROPERTY_BASES = set()


def ranked_property_prefix_spans(text, tokens, store=None):
    """順位接頭辞＋動作名詞＋性の、裏付けのない付加を検出する（48-XB）。

    GPT-6・2026-09-10。主/副は対象の順位を表すが、性が作る抽象的性質に
    自由には付かない。文法上の絶対禁止ではなく、狭い語構成の異様判定。
    既知の派生元・複合語に現れる派生元・別の既知語分割を先に照合する。
    """
    global _PROPERTY_BASE_SOURCE, _PROPERTY_BASES
    words = _load()
    if not words:
        return []
    out = []
    for a,b,c in zip(tokens,tokens[1:],tokens[2:]):
        if any(len(t)<6 for t in (a,b,c)):
            continue
        if not (a[0] in ('主','副') and '接頭' in (a[1] or '')
                and len(b[0])==2 and 'サ変' in (b[1] or '') and b[5]
                and c[0]=='性' and '接尾' in (c[1] or '')
                and a[4]==b[3] and b[4]==c[3]):
            continue
        start,end=a[3],c[4]
        whole=a[0]+b[0]+c[0];base=a[0]+b[0]
        counterpart=('副' if a[0]=='主' else '主')+b[0]
        if text[start:end]!=whole or not all('一'<=ch<='鿿' for ch in whole):
            continue
        # 大きな未知複合語の内部へ、この4文字だけの判断を広げない。
        if ((start and '一'<=text[start-1]<='鿿')
                or (end<len(text) and '一'<=text[end]<='鿿')):
            continue
        if whole in words or base in words or counterpart in words:
            continue
        if whole[:2] in words and whole[2:] in words:
            continue
        if _PROPERTY_BASE_SOURCE is not words:
            _PROPERTY_BASES={w[:3] for w in words if len(w)>3 and w[0] in ('主','副')}
            _PROPERTY_BASE_SOURCE=words
        if base in _PROPERTY_BASES or counterpart in _PROPERTY_BASES:
            continue
        if store is not None:
            try:
                from vocabulary import entry_is_solid
                reading=''.join(t[2] or '' for t in (a,b,c))
                base_reading=''.join(t[2] or '' for t in (a,b))
                if any(e.get('surface')==sf and entry_is_solid(e)
                       for rd,sf in ((reading,whole),(base_reading,base))
                       for e in store.lookup(rd)):
                    continue
            except Exception:
                continue
        out.append((a[0],b[0]+c[0],start,end))
    return out


def past_tail_kanji_spans(text, tokens):
    """48-XP: 過去助動詞に直続する漢字1字を、語尾の文脈として判定。

    裸の姓より機能語の接続を優先する限定的な推定。姓＋敬称や格助詞、
    後続の名前を含む名詞句は対象外。設計/反証: GPT-6、2026-09-10。
    """
    import re
    from pos_grammar import _PIECES
    extensions={piece for piece,state in _PIECES['TA'] if len(piece)==1}
    out=[]
    for i in range(1,len(tokens)):
        a,b=tokens[i-1],tokens[i]
        if (len(a)<6 or len(b)<6 or a[4]!=b[3] or not a[5] or not b[5]
                or a[0] not in ('た','だ') or not (a[1] or '').startswith('助動詞')
                or len(b[0])!=1 or not ('一'<=b[0]<='鿿')
                or not (b[1] or '').startswith('名詞') or b[2] not in extensions):
            continue
        # 「た」という引用や文字名には適用しない。活用する前項が必要。
        if i<2 or tokens[i-2][4]!=a[3] or not (tokens[i-2][1] or '').startswith(('動詞','形容詞','助動詞')):
            continue
        # 肯定過去＋名詞は普通の連体修飾にもなる。まず否定過去と、
        # 既にたり/だりがある並列だけで、機能語としての完結を優先する。
        negative=tokens[i-2][0]=='なかっ' and (tokens[i-2][1] or '').startswith(('助動詞','形容詞'))
        # 別の文・別欄の列挙を、現在の句の証拠にしない。
        boundaries=list(re.finditer(r'[。！？!?\n\t]| {2,}|　',text[:a[3]]))
        clause_start=boundaries[-1].end() if boundaries else 0
        parallel=any(t[3]>=clause_start and t[0] in ('たり','だり')
                     and (t[1] or '').startswith('助詞') for t in tokens[:i-1])
        if not (negative or parallel):continue
        right=text[b[4]:]
        # 別欄の読み/正解は使わず、そこで現在の句の文脈を閉じる。
        right=re.split(r'\t| {2,}|　',right,maxsplit=1)[0].lstrip()
        if right and right[0] not in '、。，．!?！？;；)]）］」』':
            continue
        if in_reading_gloss(text,b[3]):
            continue
        out.append((a[3],b[3],b[4],b[2]))
    return out


def bare_katakana_modifier_spans(text,tokens):
    """48-XQ: カタカナ2字のナ形容詞語幹＋独立した1拍の名詞の未接続。

    既知の複合語・接尾辞は保持。誤打候補の有無を判定根拠にしない。
    """
    from morphology import dictionary_base_pos
    out=[]
    for a,b in zip(tokens,tokens[1:]):
        if (len(a)<6 or len(b)<6 or not a[5] or not b[5] or a[4]!=b[3]
                or len(a[0])!=2 or not all('ァ'<=c<='ヶ' or c=='ー' for c in a[0])
                or len(b[0])!=1 or not ('一'<=b[0]<='鿿')
                or (b[1] or '')!='名詞:一般' or len(b[2] or '')!=1):
            continue
        if not any(p.startswith('名詞,形容動詞語幹,') for p in (dictionary_base_pos(a[0]) or ())):
            continue
        if _run_is_word(text,a[3],b[4]) or can_join(a[0],a[1],b[0],b[1],a[2]) is not False:
            continue
        out.append((a[0],b[0],a[3],b[4]))
    return out


def is_odd_run(text, tokenize_fn, with_spans=False,
               store=None, dict_index=None, skip_join=False, complete_line=False,
               reading_reasons_out=None):
    """
    **その塊に「その順ではくっつけない語の並び」があるか**。

    with_spans=True なら (A, B, 始まり, 終わり) を返す（画面で色を
    付けるため・項目48-IR）。

    `tokenize_fn` は `corrector.make_tokenizer` が返す形
    （(表記, 品詞, 読み, 開始, 終了, 読みが確定か) の並び）。
    解析できない・表が無いときは **[]**（意見なし）。

    `store` / `dict_index` を渡すと、**信用できない固有名詞**の
    「読みが立った」を落とす（項目48-OR）。渡さなければ今までどおり
    （検査のモックや janome の無い環境は落とさない）。
    `skip_join=True` は **「表で見たことのない並び」（`can_join` が
    False）の判定だけを使わない**読み（項目48-SM・2026-09-06）。
    呼び手はこれと通常の読みを比べて、「印が立った理由は見たことのない
    並びだけか」を知る。

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
    # **信用できない固有名詞は「読みの立たない語」として扱う**
    # （項目48-OR・2026-09-03）。**落とすのは `downgraded_tokens`
    # ただ1つ**——`_plain_noun` の `_NOUN_NG` から固有名詞を外すのでは
    # ない（外すと 48-NA が 高橋佑 を「名詞どうし」と見て黙る。
    # 判定の順を変えるのではなく、**信じてよい固有名詞かどうか**を
    # 1か所で決める）。
    source_tokens = list(toks)
    toks = downgraded_tokens(toks, store, dict_index)
    #: 対のループで**隣を見る**ために、並びをそのまま持っておく
    #: （項目48-OY'。カタカナの連なりの途中かどうか）
    _tok_list = list(toks)
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
    from reading_likelihood import nominal_slot_spans
    for a,b,start,end in nominal_slot_spans(text,source_tokens):
        if not in_reading_gloss(text,start):
            out.append((a,b,start,end) if with_spans else (a,b))
            if reading_reasons_out is not None:
                reading_reasons_out[start,end] = '読みの並びと後続の「を」への接続から、語の区切りが不自然だと判定しました'
    for a,b,start,end in bare_katakana_modifier_spans(text,source_tokens):
        out.append((a,b,start,end) if with_spans else (a,b))
    if complete_line:
        for start,tail_start,end,reading in past_tail_kanji_spans(text,source_tokens):
            a,b=text[start:tail_start],text[tail_start:end]
            out.append((a,b,start,end) if with_spans else (a,b))
    for a,b,start,end in ranked_property_prefix_spans(text,toks,store):
        out.append((a,b,start,end) if with_spans else (a,b))
    for a,b in shortcut_case_spans(text, toks):
        out.append(('キー操作', '出（格助詞の位置）', a, b) if with_spans
                   else ('キー操作', '出（格助詞の位置）'))
    # 「の」の後ろが丁寧語か名詞句かは、切り出す前の文脈で決める。
    # 部分文字列の末尾を、元の行の終わりと取り違えない。
    if complete_line:
        for root_start, tail_start, end, body in renyou_no_polite_spans(text,toks,tokenize_fn):
            first=text[root_start:tail_start];last=text[tail_start:end]
            out.append((first,last,root_start,end) if with_spans else (first,last))
    # **副詞＋に の後ろに用言が1つも無い**（項目48-NR）。対ではなく
    # 3語ぶんの並びを見るので、下の対のループとは別に置く。
    for i in range(1, len(spans) - 1):
        if adverb_ni_dangling(spans, i):
            _a = spans[i][2][0]
            _b = spans[i + 1][2][0]
            out.append((_a, _b, spans[i][0], spans[i + 1][1])
                       if with_spans else (_a, _b))
    # **活用形の接続が合わない**（項目48-NT）。品詞の対だけでは
    # 見きれないので、対のループとは別に置く。
    for i in range(len(spans) - 1):
        a_s, a_e, a = spans[i]
        b_s, b_e, b = spans[i + 1]
        if a_e != b_s:
            continue
        # **読みの注記の中では見ない**（項目48-NW）。括弧の中の
        # かなは書きたくて書いたもので、解析はほぼ必ず壊れる。
        if in_reading_gloss(text, a_s):
            continue
        _prev = spans[i - 1][2] if i > 0 else None
        if (infl_mismatch(a, b, _prev) or suffix_then_yougen(spans, i)
                or noun_past_aux_mismatch(a, b, text, dict_index)
                or polite_aux_mismatch(a, b)
                or causative_aux_mismatch(a, b)
                or passive_aux_mismatch(a, b)
                or orphan_sokuon_mismatch(a, b, _prev)
                or auxiliary_te_mismatch(a, b)
                or contracted_aux_mismatch(a, b)):
            _one = (a[0], b[0], a_s, b_e) if with_spans else (a[0], b[0])
            # **同じ対を二重に出さない**（項目48-NY）。語の対の表
            # （`_PAIR`）と構造の判定が同じ所を指すことがある
            # ——`号|し` は両方が言う。印は1つでよい。
            if _one not in out:
                out.append(_one)
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
        # (C) **感動詞に付けないのは「格助詞」だけ**（はい**を**・
        #     ありがとう**に**）。括弧ごしは位置が切れるのでここへ来ない。
        #
        #     **2026-09-03 に絞った**（項目48-OW）。「助詞は付かない」と
        #     一律に書いていたので、**接続助詞まで止めていた**——
        #     `すみません**が**…`（janome は接続助詞と読む・実測）・
        #     `ごめん**けど**` は正しい日本語。
        #     置けないのは**格を示す助詞**（感動詞は文の成分にならない）で、
        #     接続助詞・終助詞・係助詞は置ける
        #     （すみませんが・はい**は**？・いや**ね**）
        elif ap.startswith('感動詞') and '格助詞' in bp:
            _kz = True
        # (D) **格助詞は連続しない**（をに・がを）。から・へ だけは
        #     2つ目を取れる（ここ**からが**本番・駅**へと**向かう）。
        #     **並立助詞の と は数えない**（項目48-RZ・2026-09-06 に
        #     一度足して**測って外した**——解析が と を並立助詞と読むのは
        #     まさに `AとBとが`・`〜とのことですが` の並立・引用の形で、
        #     実機メモの正しい5行に紫が立った。`もみとにもどります` の
        #     ①は、かな連続の側の `pos_grammar`（K/Bk・行頭の裸の助詞）が
        #     立てる）
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
                and a_sf != 'ある'
                # **この／その／あの／どの＋くらい・ぐらい・ほど** は程度の言い方
                # （項目48-TE・2026-09-06。`どのくらい日持ちしますか` に紫）
                and not (a_sf in ('この', 'その', 'あの', 'どの')
                         and b_sf in ('くらい', 'ぐらい', 'ほど'))):
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
        # (G) **接尾に接尾は付かない**（項目48-KZ(G)・2026-09-03・
        #     うにさんの画面 `簡易**流力**`）。接尾は**語に付く**もので、
        #     接尾どうしが並ぶ形は語ではない。
        #
        #     実機メモ2,144行で「名詞:接尾 が2つ続く」組は **23種**あるが、
        #     **`名詞:接尾:一般` どうし**に絞ると **5種**に落ち、さらに
        #     **`a+b` が表の語でない**を足すと **2種**（`流力`＝的 と
        #     `語系`）だけになる（実測）。**閉じた表に書くのは `語系` 1語**。
        #     fpcheck の材料（1,500文）では 0件。
        #
        #     `流力` は**行の中でだけ**この形になる（塊単体で解析すると
        #     `流` が動詞になる）ので、測るときは必ず行で測ること。
        if ('名詞:接尾:一般' in ap and '名詞:接尾:一般' in bp
                and (a_sf, b_sf) not in _SUFFIX_PAIR_OK
                and b_sf not in _SUFFIX_TAIL_FREE       # 説明書付き（48-SN）
                and (a_sf + b_sf) not in (_load() or ())
                and not _run_is_word(text, a_s, b_e)):
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
        # **カタカナの連なりの途中で切れているトークンは、世の中の語
        # でも「1語を割った跡」**（項目48-OY'・2026-09-03）。
        # 48-OY で世の中の表を広げたら `ブル` も「在る語」になり、
        # `右田で**ブル|クリック**` の印が消えた。**カタカナの連なりは
        # ふつう1語**なので、途中で切れていること自体が跡になる。
        # `出力|ブレ`・`プレイ|動画`・`縦|シュー` は**連なりの端**
        # （相手が漢字）なので、ここには当たらない
        _a_split = _kata_run_continues(_tok_list, i)
        _b_split = _kata_run_continues(_tok_list, i + 1)
        _frag_hit = False
        for _fk, _other, _op, _o_known in (
                (None if ap == "副詞:擬音文脈" else _is_unknown_fragment(a_sf, a_known, dict_index, _a_split),
                 b_sf, bp, b_known),
                (None if bp == "副詞:擬音文脈" else _is_unknown_fragment(b_sf, b_known, dict_index, _b_split),
                 a_sf, ap, a_known)):
            if not _fk:
                continue
            if not _o_known:
                continue        # 相手は**辞書に載っている語**であること。
                                # janome の無い環境の簡易分割は全トークンが
                                # 「読み立たず」になるので、これが無いと
                                # 普通のかなにまで印が立つ（tests_mock で踏んだ）
            if not (_other and (kanji(_other[0])
                                or _katakana_word_known(_other,
                                                        dict_index))):
                continue        # 相手は漢字始まり（擬音・かな崩しの壁）
                                # **または、世の中のカタカナ語**
                                # （項目48-OR・2026-09-03）。この壁は
                                # 擬音・かな崩し（ぴよピヨ・きゅいー）を
                                # 止めるためのもので、**相手が表に在る
                                # カタカナ語なら崩れではなく内容語**
                                # ——漢字始まりの語と同じ資格。
                                # `ブル｜クリック` が立つのはこの枝
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
            _a_fk = _is_unknown_fragment(a_sf, a_known, dict_index)
            _b_fk = _is_unknown_fragment(b_sf, b_known, dict_index)
            if (_a_fk and a_sf and a_sf[-1] in _SMALL_KANA
                    and _b_fk == 'カタカナ断片'):
                _frag_hit = True
        if _frag_hit and _fragment_has_parallel_noun_context(text, a_s, b_e, tokenize_fn):
            # 未知の漢字名詞について、未知断片/未知の名詞結合を重ねて異様としない。
            # 活用・助詞接続の規則はこの分岐より前で検査済み。
            continue
        if _frag_hit:
            out.append((a_sf, b_sf, a_s, b_e) if with_spans
                       else (a_sf, b_sf))
            continue
        # **漢字の名詞＋「し／する」の直付き**は異様（項目48-IX・2026-08-23・
        # うにさんの指定「`田部井号して` が異様と判定できれば」）。
        # 動作名詞の解釈が無いままの「Nする」を検出する。辞書の一般名詞でも
        # 口語の動作用法はあるため、morphologyの文脈判定を先に反映する。
        # 旧説明の「誤字しては動作でない」は不適切（48-XSで訂正）。
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
                # **接頭詞が直前に付いているなら、接頭詞＋この字が1語**
                # （項目48-SN・2026-09-06。同梱し・再送し・未着し）。
                # 解析は `同梱` を 同(接頭詞)|梱 と切るので、`梱し` が
                # 名詞1字＋する に見えていた（うにさんの実機・紫）
                and not (i > 0 and spans[i - 1][1] == a_s
                         and '接頭' in (spans[i - 1][2][1] or ''))
                # 送り仮名まで含めて表の語（`見做|し`＝見做す）なら語の
                # 中の切れ目。`号し` だけが表に在っても `田部井号し` は
                # 無いので、漢字の連続ごと見る（48-IP と同じ `_run_is_word`）
                and not _run_is_word(text, a_s, b_e)):
            out.append((a_sf, b_sf, a_s, b_e) if with_spans else (a_sf, b_sf))
            continue
        # **ナ形容詞の語幹＋用言は、下の2枚の壁に当たって
        # `can_join` まで届いていなかった**（項目48-NM'・2026-09-01）:
        #     「右は漢字始まり」  → `アクティブ|なっ` が落ちる
        #     「左が漢字終わりで右が名詞」 → `静か|歩く` が落ちる
        # **うにさんの的が2つとも印になっていなかった**（実測）。
        # 48-NM の注記の「実機メモでは増減0」は、判定が無いのでは
        # なく**判定まで道が通っていなかった**からだった。
        # **判定は `can_join` に置いたまま**（同じ判定を2度書かない・
        # 項目48-GN）、この形だけ先に聞きに行く。
        if naadj_stem_bare(a_sf, ap, b_sf, bp):
            if not _run_is_word(text, a_s, b_e):
                out.append((a_sf, b_sf, a_s, b_e) if with_spans
                           else (a_sf, b_sf))
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
            # **漢字が境目で隣り合っている形**（元からの道・48-HN）。
            # **A の読みも渡す**（項目48-OV。1字の名詞が訓読みかを見る）
            if skip_join:
                continue                    # 見たことのない並びは見ない（48-SM）
            if can_join(a_sf, ap, b_sf, bp,
                        _hira(a[2] if len(a) > 2 else '')) is not False:
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
            # **後ろが副詞にもなれる語なら、複合語ではなく修飾**
            # （項目48-MR・2026-08-31。うにさんの画面の誤検知
            # `通常の文と異なり**全て**ひらがなであり、`——`全て` は
            # 述語を修飾していて、`異なり全て` という複合語ではない）。
            # `can_join` の (6'')「後ろが副詞にもなれる語＝何にでも
            # 付く」と**同じ判定**。48-JC の枝は `can_join` を通らない
            # ので、ここにも掛ける（学び22——片方だけに置くと、
            # そちらを迂回して素通りする）。
            if _adverbial(bp):
                continue
            if a_sf[-1] not in _RENYOU_TAIL:
                continue                    # 連体形（う段）は見ない
            if not kanji(a_sf[0]):
                continue
            if ap.startswith('動詞'):
                # **後ろが1字の名詞なら見ない**（項目48-NC・2026-08-31）。
                # 連用形＋1字の名詞は、日本語でいちばん作りやすい
                # 複合名詞（伸ばし**棒**・押し**ピン**・引き**戸**・
                # 巻き**尺**・差し**歯**・貼り**紙**）。48-JC を入れた
                # ときの記録に「**誤爆は `伸ばし棒` の1行**」とある——
                # **その形が、後ろ1字**だった。的の `買い脊柱` は
                # 後ろが2字なので残る。
                #
                # **`can_join` にも聞く形（48-KF の枝と同じ門）は、
                # 測って落とした。** 紫の誤検知は2つ消える
                # （`繰り返し文字`・`繰り返し傾向`）が、育ちの
                # readcheck で**化けが1つ増えた**（157 → 158）。
                # 上の1字の門だけなら **直った +2・化け 据え置き**。
                if len(b_sf) == 1:
                    continue
                # **連用形＋動作性名詞は複合の型**（項目48-SN・2026-09-06。
                # 飛び散り防止・立ち入り禁止・吹き出し防止・書き込み禁止・
                # 取り扱い注意）。うにさんの実機で `飛び散り防止 →
                # 飛び入り防止` と化けた
                if 'サ変接続' in bp:
                    continue
            elif ap.startswith('名詞') and len(a_sf) >= 2:
                if skip_join:
                    continue                # 見たことのない並びは見ない（48-SM）
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
        if ((not a_known or not b_known) and ap.startswith('名詞') and bp.startswith('名詞')
                and _fragment_has_parallel_noun_context(text, a_s, b_e, tokenize_fn)):
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
    # **位置の順にそろえて返す**（項目48-NT・2026-09-01）。
    # `odd_spans` は「印は位置順に来る」前提で隣り合う印を繋いでいる:
    #
    #     if spans and s <= spans[-1][1]: spans[-1] = ...（繋ぐ）
    #
    # 上のループ（対で見る道）と、別に置いた道（活用形・副詞＋に）を
    # 足したので**順序が崩れ**、うしろの印が前の印を飲み込んだ
    # ——`解析課背中セク、` の `背中|セク`(3-7) が、読みの欄の
    # `かいせ|きか`(9-14) に吸われて**画面から消えた**（実測）。
    # **道を足すたびに崩れる**ので、出口でそろえる（学び22）。
    if with_spans:
        out.sort(key=lambda t: (t[2], t[3]))
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


#: **活用形 → 後ろに来られる品詞の頭**（項目48-NT・2026-09-01・
#: うにさんの指定「**異様さとは、品詞の文法が間違っていることが
#: 大半だと思われます**」）。
#:
#: 品詞だけでは足りない——`書け`（仮定形）と `食べ`（連用形）は
#: どちらも `動詞:自立` で、後ろに来られるものが違う。
#: `corrector.make_tokenizer` の**7つ目に活用形**を通した（48-NT）。
#:
#: **厳密に決まるものだけ**を入れる（連用形・基本形は後ろが広すぎて
#: 使えない）。
#:
#: **出どころ**: 活用形の名前は janome（IPAdic）。後ろに来られる
#: ものは **この AI（Claude Opus 4.6・2026-09-01）が日本語文法として
#: 書き下した**もので、辞書から採ったのではない。CLAUDE.md の
#: 「AI の判断を材料にしてよい。ただし版と出どころを書く」に従う。
#:
#: **測って2度直した**（実機メモ全タブ 1,791行）:
#:   ・未然形の後ろの `れる`/`せる` を解析は **助動詞ではなく
#:     `動詞:接尾`** と言う（`さ|れ` が137件出た）→ 足した
#:   ・**助動詞の仮定形**（たら・なら）は後ろが自由
#:     （`〜したら多重起動`）→ **用言の仮定形だけ**に絞った
#:   ・**命令形は入れない**——理由は**2026-09-01 に変わった**。
#:     もとは「`とはいえ存在` で誤爆する」だったが、その誤爆は
#:     **項目48-NV（複合辞を1語にする）で消えた**（`とはいえ` は
#:     いま1語の接続詞で、`いえ`＝命令ｅ は出てこない）。
#:     残っていた `精肉（**せい**にく）` も **48-NW（読みの注記の中は
#:     見ない）** で消えた。**いまは誤爆0**。
#:     それでも入れないのは、**当たりも0**だから——実機メモ1,800行・
#:     readcheck 3,481語・fpcheck 1,500文の**すべてで差0**だった
#:     （2026-09-01 に測った）。「効果のあるものだけ入れる」。
#:     **入れても安全にはなったので、証拠が出たら足せる。**
_AFTER_INFL = {
    '未然形': ('助動詞', '動詞:接尾', '記号'),
    '未然ウ接続': ('助動詞', '動詞:接尾', '記号'),
    '未然ヌ接続': ('助動詞', '動詞:接尾', '記号'),
    '未然レル接続': ('助動詞', '動詞:接尾', '記号'),
    '未然特殊': ('助動詞', '動詞:接尾', '記号'),
    '仮定形': ('助詞:接続助詞', '記号'),
    # **命令形は入れない**（項目48-NX → **48-NZ(a) で撤去**）。
    #
    # 一度は入れた（2026-09-01・うにさんの「論理的に正しいものを
    # 重ねる」を受けて）。**入れた理由が間違っていた**——
    # 「命令形の後ろに自立語は来ない」は**論理的に正しくない**:
    #
    #     頑張れ**日本**       ← **呼びかけ**（呼格）。名詞が来る
    #     遅かれ**早かれ**壊れます ← 形容詞の命令形の慣用
    #     やめろ**ー**         ← 引き伸ばし
    #     宙に浮け**ない**     ← `浮け` は可能動詞。解析の取り違え
    #
    # うにさんの決まりは「**論理的に正しいもの**を重ねる」であって
    # 「誤爆が測れなければ入れる」ではない。**私の書いた文法が
    # 間違っていた**ので撤去する（実機メモでは当たりも誤爆も0
    # だった——**標本に無かっただけ**で、正しさの裏付けにならない）。
}

#: 上の表を**用言のときだけ**当てる活用形（助動詞は別の接続をする）
#: **未然形系も「用言のときだけ」**（項目48-NZ(b)）。
#: 助動詞の未然形は後ろが自由:
#:     そう**だろ**ー。   `だろ`(助動詞・未然形) ＋ `ー`(名詞)
#:     そう**でしょ**が。 `でしょ`(助動詞・未然形) ＋ `が`(接続助詞)
#: 的（`ほせ|い`・`こ|て`・`かいせ|きか`）は**全部 動詞**なので損は無い。
_INFL_YOUGEN_ONLY = ('仮定形', '未然形', '未然ウ接続', '未然ヌ接続',
                     '未然レル接続', '未然特殊')

#: **口語・叫び声の側は見ない**。`はわわー`・`知らなーい`・
#: `おもしれえ` は活用の形を崩して書くのがふつうで、打ち間違いでは
#: ない（SPEC の「叫び声・合図」と同じ向き）。
_INFL_SKIP_AFTER = ('助詞:終助詞', '感動詞', 'フィラー', '助詞:間投助詞')


#: **接尾辞のうち、直後に用言が来てよいもの**（項目48-NY）。
#:
#:   サ変接続      速度**化**する・重要**視**する
#:   助数詞        3**回**行く・二**度**見る・5**分**待つ
#:                 （数量詞は**副詞のように使える**——ここが要注意）
#:   副詞可能      少し**ずつ**進める・10分**ごと**確認する
#:   形容動詞語幹  積極**的**に…（「に」を挟むが、外しておく）
#:   助動詞語幹    面白**そう**…（同上）
#:   特殊          暑**さ**増す・寒**さ**和らぐ・高**さ**増す
#:                 ——**見出しの書き方では自然**（新聞の見出しに
#:                 そのまま出る形）。うにさんのメモも箇条書き・
#:                 体言止めが多い。**測って外した**（項目48-NZ(e)）
_SUFFIX_YOUGEN_OK = ('サ変接続', '助数詞', '副詞可能',
                     '形容動詞語幹', '助動詞語幹', '特殊')


def suffix_then_yougen(spans, i):
    """
    **接尾辞の直後に、自立の用言が来ていないか**（項目48-NY・
    2026-09-01・うにさんの指定）:

        「『田部井号して』に焦点を当てます。「号」は……
          **ここでは接尾辞と判定されています。
          接尾辞の次が接続助詞なのが異様です。**」

        田部井 / **号**(名詞:接尾:一般) / **し**(動詞:自立) / て
          → 接尾辞のうしろに助詞が無く、いきなり用言

    接尾辞は**前の語にくっついて名詞句を作る**ので、その名詞句は
    助詞を伴って文に入る。**助詞を飛ばして用言に繋がることはない**:

        田中**さん**行く   → 田中さん**が**行く
        子供**たち**走る   → 子供たち**が**走る
        東京**都**行く     → 東京都**へ**行く
        高**さ**増す       → 高さ**が**増す
        確認**済み**送る   → 確認済み**を**送る

    **外すもの**は2つ:

    (あ) `_SUFFIX_YOUGEN_OK` の細分類——サ変接続（速度**化**する）・
         助数詞（3**回**行く）・副詞可能（少し**ずつ**進める）ほか。

    (い) **数量表現の末尾**——接尾辞の並びを左へ辿って **名詞:数** に
         行き着くなら、そのまとまりは**副詞のように使える**:

             1行**分**開いていて   分←行(助数詞)←**1(数)**
             3日**分**残る         二人**分**作る

         `分` は IPAdic では `名詞:接尾:一般` で助数詞ではないので、
         (あ) では外れない。**測って見つけた**（実機メモで1件だけ
         誤爆した・2026-09-01）。(あ) と同じ理屈——数量詞は副詞的。
    """
    if i < 0 or i + 1 >= len(spans):
        return False
    a = spans[i][2]
    b = spans[i + 1][2]
    ap = a[1] or ''
    if not ap.startswith('名詞:接尾'):
        return False
    if any(x in ap for x in _SUFFIX_YOUGEN_OK):
        return False
    bp = b[1] or ''
    if not (bp.startswith('動詞:自立') or bp.startswith('形容詞:自立')):
        return False
    # (う) **サ変の「する」は 48-JC が見ている**（同じ判定を2度
    #      書かない・項目48-GN）。あちらは**接尾辞の前**まで見て
    #      `無効**化**して` を通し、`田部井**号**して` を止める。
    #      ここで重ねると `無効化して` を壊す（**測って踏んだ**）。
    if (b[0] or '') in _SURU_FORMS:
        return False
    # (い) 左へ辿って **数** に行き着けば数量表現
    j = i
    while j > 0:
        pp = spans[j - 1][2][1] or ''
        if pp.startswith('名詞:数'):
            return False
        if not pp.startswith('名詞:接尾'):
            break
        j -= 1
    return True


def renyou_no_polite_spans(text, toks, tokenize_fn=None):
    """連用形の後ろに『の』が紛れ、丁寧語が途切れている形を調べる。"""
    if 'の' not in text:
        return []
    import re
    import pos_grammar as pg
    from morphology import dictionary_base_pos
    out=[]
    for i,a in enumerate(toks):
        verbal=(len(a)>6 and (a[1] or '').startswith('動詞:自立') and a[6]=='連用形')
        nominal=(len(a)>6 and (a[1] or '').startswith('名詞:一般'))
        if not (len(a)>6 and a[5] and (verbal or nominal) and text[a[4]:a[4]+1]=='の'):
            continue
        start=a[4]
        m=re.match(r'の([ぁ-ゖー]{2,12})',text[start:])
        body=m.group(1) if m else ''
        end=start+len(m.group(0)) if m else start
        if not body.startswith('ま'):
            if not verbal:continue
            # 変換で名詞になった尾は、その読みが丁寧語として成立する場合だけ。
            if i+2>=len(toks):continue
            n,b=toks[i+1],toks[i+2]
            if not (n[0]=='の' and n[3]==start and n[4]==b[3]
                    and (b[1] or '').startswith('名詞') and b[5]):continue
            if any(p.startswith('名詞,') and not p.startswith(('名詞,接尾,','名詞,固有名詞,'))
                   for p in (dictionary_base_pos(a[0]) or ())):continue
            if i and toks[i-1][4]==a[3] and (toks[i-1][1] or '').startswith(('名詞','接頭詞')):
                continue
            body=b[2] or '';end=b[4]
            if end<len(text) and ('ぁ'<=text[end]<='ゖ' or '一'<=text[end]<='鿿'):
                continue
        if not body.startswith('ま'):continue
        # 丁寧語に見える部分が、元の既知名詞の途中なら切り取らない。
        if any(t[5] and (t[1] or '').startswith('名詞') and t[3]<=start+1<end<t[4]
               for t in toks):continue
        if not pg.explain_kana_run(body,no_words=True,initial_state='R',
                                   before_kanji=(end<len(text) and '一'<=text[end]<='鿿')):continue
        if nominal:
            if tokenize_fn is None:continue
            candidate=text[:start]+body+text[end:]
            if not any(len(t)>6 and t[5] and t[0]==a[0] and t[3]==a[3] and t[4]==a[4]
                       and (t[1] or '').startswith('動詞:自立') and t[6]=='連用形'
                       for t in tokenize_fn(candidate)):continue
        if text[a[3]:end] in (_load() or ()):continue
        out.append((a[3],start,end,body))
    return out



# 継続・結果状態の補助動詞。移動・方向・授受の動詞は、連用形に
# 直結して複合動詞や敬語にもなるため、この規則には含めない。
_TE_AUXILIARY_BASES = frozenset(('いる','居る','おる'))


from functools import lru_cache


@lru_cache(maxsize=4096)
def _kana_nominal_alternative(text):
    """同じ読み全体に名詞があるなら、かな内部の動詞分割だけで禁止しない。"""
    if not (2<=len(text)<=16 and all('ぁ'<=c<='ゖ' or c=='ー' for c in text)):
        return False
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_base_pos
    return any(any(p.startswith('名詞,') and '接尾' not in p
                   for p in (dictionary_base_pos(sf) or ()))
               for sf in table_surfaces_for_reading(text,limit=8))


def auxiliary_te_mismatch(a,b):
    """連用形を、て/でを介さず継続の補助動詞に直接つながない。"""
    if len(a)<7 or not a[6].startswith('連用'):
        return False
    # 自立した語の名詞別解は残す。使役/受身の接尾動詞まで、同音の
    # 短い名詞へ置き換えて接続を正当化しない。
    if a[1].startswith('動詞:自立') and _kana_nominal_alternative(a[0]+b[0]):
        return False
    return aspect_auxiliary_needs_te(a,b)


def aspect_auxiliary_needs_te(a,b):
    """継続の補助動詞へ動詞を直結していないか。生成の検算とも共有する。"""
    if (len(a)<7 or len(b)<7 or not a[5] or not b[5] or a[4]!=b[3]
            or not a[1].startswith('動詞')
            or not b[1].startswith('動詞:非自立')):
        return False
    from morphology import dictionary_inflections
    entries=dictionary_inflections(b[0])
    if not entries:
        return False
    bases={base for pos,form,base,rd in entries if pos.startswith('動詞,非自立,')}
    if not bases or not bases.issubset(_TE_AUXILIARY_BASES):
        return False
    # 書き置く・飛び行く等が辞書に一語としてあれば、その複合動詞を残す。
    compound=dictionary_inflections(a[0]+b[0])
    if compound and any(pos.startswith('動詞,') for pos,form,base,rd in compound):
        return False
    return True


def contracted_aux_mismatch(a,b):
    """完了の口語縮約は格助詞の直後で自立した述語にならない。"""
    if (len(a)<7 or len(b)<7 or a[4]!=b[3] or not a[5] or not b[5]
            or not a[1].startswith('助詞:格助詞')
            or a[0] not in ('を','に','へ','で','から','より','まで')
            or not b[1].startswith('動詞:非自立')):
        return False
    from morphology import dictionary_inflections
    entries=dictionary_inflections(b[0]) or ()
    if any(pos.startswith(('名詞,','動詞,自立,')) for pos,form,base,rd in entries):
        return False
    bases={base for pos,form,base,rd in entries if pos.startswith('動詞,非自立,')}
    return bool(bases and bases.issubset({'ちゃう','じゃう','ちまう','じまう'}))


def orphan_sokuon_mismatch(a,b,previous):
    """格助詞＋単独の促音＋自立動詞は、動詞の正しい活用として扱わない。"""
    return bool(previous is not None and len(a)>=6 and len(b)>=6
        and a[0]=='っ' and previous[4]==a[3] and a[4]==b[3]
        and previous[1].startswith('助詞:格助詞')
        and b[5] and b[1].startswith('動詞:自立'))


def causative_aux_mismatch(a,b):
    """使役の せる/させる は直前の動詞の活用型にも従う。"""
    return _derivational_aux_mismatch(a,b,'causative')


def passive_aux_mismatch(a,b):
    """受身・可能の接続。口語のら抜きは成立する別解として残す。"""
    return _derivational_aux_mismatch(a,b,'passive')


def _derivational_aux_mismatch(a,b,auxiliary):
    if (len(a)<7 or len(b)<7 or not a[5] or not b[5] or a[4]!=b[3]
            or not b[1].startswith(('動詞:接尾','助動詞'))
            or not a[1].startswith(('動詞','助動詞'))):
        return False
    from morphology import dictionary_paradigms
    right=dictionary_paradigms(b[0])
    left=dictionary_paradigms(a[0])
    if not right or not left:
        return False
    allowed=('せる','させる') if auxiliary=='causative' else ('れる','られる')
    bases={base for pos,kind,form,base,rd in right
           if base in allowed and pos.startswith(('動詞,接尾,','助動詞,'))}
    if not bases:
        return False
    considered=False
    for pos,kind,form,base,rd in left:
        # 表記が同じだけの別品詞を、文中の動詞の接続根拠にしない。
        if pos.split(',')[0]!=a[1].split(':')[0]:
            continue
        group=('godan' if kind.startswith('五段') else
               'ichidan' if kind.startswith('一段') else
               'zahen' if kind.endswith('ズル') else
               'sahen' if kind.startswith('サ変') else
               'kahen' if kind.startswith('カ変') else None)
        if group is None or (group=='zahen' and auxiliary=='causative'):
            return False  # 文語等を現代語の禁止条件で決めない。
        considered=True
        if not form.startswith('未然') or form=='未然ウ接続':
            continue
        if auxiliary=='causative':
            if 'せる' in bases and group=='godan':
                return False
            if 'せる' in bases and group=='sahen' and form=='未然レル接続':
                return False
            if 'させる' in bases and group in ('ichidan','kahen'):
                return False
        else:
            if 'れる' in bases and group in ('godan','ichidan','kahen'):
                return False
            if 'れる' in bases and group=='sahen' and form=='未然レル接続':
                return False
            if 'られる' in bases and group in ('ichidan','kahen','zahen'):
                return False
            if 'られる' in bases and group=='sahen' and form=='未然ヌ接続':
                return False
    return considered



def polite_aux_mismatch(a, b):
    """48-XY: 丁寧のますは動詞の連用形に接続する。

    活用した表記の辞書別解まで確かめる。名詞のまま直結した形や
    基本形/音便形の接続を、候補の有無とは独立に調べる。
    設計/反証: GPT-6、2026-09-11。
    """
    if (min(len(a),len(b))<7 or not a[5] or not b[5] or a[4]!=b[3]
            or not b[1].startswith('助動詞') or b[0] not in ('ます','まし','ませ','ましょ')
            or not a[1].startswith(('名詞','動詞','形容詞','助動詞'))):
        return False
    if a[1].startswith('動詞') and a[6]=='連用形':
        return False
    # かなで書いた一つの名詞を、語中のますだけで丁寧語と断定しない。
    # 活用の途中に現れる接尾動詞までこの別解で守ることはしない。
    if a[1].startswith(('名詞','助動詞','動詞:自立')) and _kana_nominal_alternative(a[0]+b[0]):
        return False
    from morphology import dictionary_inflections
    forms=dictionary_inflections(a[0])
    if forms is None:
        return False
    # サ変の「し」は未然形と連用形が同形。辞書の一部に未然形の項
    # しかなくても、原形がするで対応する既知語なら連用形を失わない。
    if any(pos.startswith('動詞,') and form=='未然形'
           and base.endswith('する') and a[0]==base[:-2]+'し'
           for pos,form,base,reading in forms):
        return False
    if any(form=='連用形' and (pos.startswith('動詞,') or
            (pos.startswith('助動詞,') and base in ('れる','られる','せる','させる')))
           for pos,form,base,reading in forms):
        return False
    return True


def noun_past_aux_mismatch(a, b, text, dict_index=None):
    """名詞に過去の「た」が直結する誤解析。語の途中・記号の注記は除く。"""
    if len(a) < 5 or len(b) < 5:
        return False
    if not ((a[1] or '').startswith('名詞')
            and (b[1] or '').startswith('助動詞') and b[0] == 'た'):
        return False
    if not (any('ぁ' <= c <= 'ゖ' or '一' <= c <= '鿿' for c in a[0])
            or (a[0] and all(c == 'ー' for c in a[0]))):
        return False
    start, end = a[3], b[4]
    while start > 0 and ('ぁ' <= text[start - 1] <= 'ゖ' or text[start - 1] == 'ー'):
        start -= 1
    while end < len(text) and ('ぁ' <= text[end] <= 'ゖ' or text[end] == 'ー'):
        end += 1
    whole = text[start:end]
    # 長音だけのトークンは直前のかなと合わせて見る。記号単独の注記は除く。
    if not any('ぁ' <= c <= 'ゖ' or '一' <= c <= '鿿' for c in text[start:b[3]]):
        return False
    # 助詞が続いても、名詞＋たに誤分割された一語の境界を保つ。
    if whole in (_load() or ()) or text[a[3]:b[4]] in (_load() or ()):
        return False
    # 漢字の直後は送り仮名・活用末尾かもしれない。一語の読みとして
    # 保護するのは独立したかな列だけ（語の一部を人名の読みなどで守らない）。
    if (dict_index is not None and not (start > 0 and '一' <= text[start - 1] <= '鿿')
            and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in whole)):
        try:
            if dict_index.is_world_reading(whole):
                return False
        except Exception:
            pass
    return True


def infl_mismatch(a, b, prev=None):
    """
    **前の語の活用形に、後ろの品詞が続けない**か（項目48-NT）。

    a, b は解析の語（7つ目に活用形が入っている形）。活用形が
    分からない環境（janome 無し・古い形）では**必ず False**。

        ほせ（未然レル接続）| い   ← `ほせい`（補正）が割れている
        こ（未然形）| て           ← `おくゆくこてい`
        かいせ（未然レル接続）| きか ← `かいせきかせなかせく`
        そも（未然ウ接続）| もそ    ← `そももそ`
    """
    if len(a) < 7:
        return False
    form = a[6] or ''
    # **(d) 直前が「数」なら見送る**（項目48-NZ(d)）。
    # 数の直後は助数詞なので、そこを用言と読んだ解析は壊れている:
    #     **1**つも動いていない  `つも` を 動詞:自立・未然ウ接続 と読む
    #     **2**つも残っている    （`一つも` は正しく 名詞:一般 になる
    #                             ので、**半角数字のときだけ**起きる）
    # 同じ事実は 48-NO（`_preceded_by_digit`）でも使っている。
    if prev is not None and (prev[1] or '').startswith('名詞:数'):
        return False
    ok = _AFTER_INFL.get(form)
    if not ok:
        return False
    ap = a[1] or ''
    if form in _INFL_YOUGEN_ONLY and not (ap.startswith('動詞')
                                          or ap.startswith('形容詞')):
        return False
    bp = b[1] or ''
    if any(bp.startswith(x) for x in ok):
        return False
    if any(bp.startswith(x) for x in _INFL_SKIP_AFTER):
        return False
    # **(c) 文語の 未然形＋ば**（項目48-NZ(c)）。
    #     **急が**ば回れ ／ **思わ**ば通ず ／ **death**ば…
    # いまの日本語でも諺・言い回しとして生きている。
    if form.startswith('未然') and (b[0] or '') == 'ば':
        return False
    return True


#: 副詞＋に のあとが名詞のとき、**その名詞が動詞句になれる**印
#: （項目48-NR）。`すぐに**確認**`（サ変）・`非常に**困難**`
#: （形容動詞語幹）は述語になるので自然。
_ADV_NI_OK_TAIL = ('サ変接続', '形容動詞語幹', '接尾', '非自立', '数')


def adverb_ni_dangling(spans, i):
    """
    **副詞＋に の後ろに用言が1つも無い**か（項目48-NR・2026-09-01・
    うにさんの指定）:

        「『そのままに市内』に焦点を当てます。**そのまま：副詞。
          に：格助詞。後ろに来るべき品詞は、主に動詞（または
          動詞句）**。『そのままに』全体が文中で副詞（連用修飾語）
          として機能するため、原則として後ろには動詞（用言）が
          配置されます。」

        そのままに**市内** → そのままに**しない**

    **素直に「に の後ろは用言」とすると反例が多い**（実機メモで実測）:

        完全に別物 ／ 非常に困難 ／ 急に雨が降る ／ すぐに確認

    3つ重ねると、うにさんの的だけが残る（1,791行で **2件・誤爆0**）:

        (a) 前が**もともとの副詞**（副詞:一般／副詞:助詞類接続）。
            `完全``非常``急` は 名詞:形容動詞語幹 なので外れる
        (b) 後ろの名詞が**動詞句になれない**
            （`確認``完了` はサ変＝述語になる。`市内` はならない）
        (c) **その先に用言が1つも無い**＝修飾する相手が居ない
            （`実際に横**に並んで**`・`すぐに元**に戻す**` は自然）

    `spans` は `[(始まり, 終わり, 語), ...]`、`i` は「に」の位置。
    """
    if i < 1 or i + 1 >= len(spans):
        return False
    a = spans[i - 1][2]
    n = spans[i][2]
    b = spans[i + 1][2]
    if n[0] != 'に' or not (n[1] or '').startswith('助詞'):
        return False
    if not (a[1] or '').startswith('副詞'):
        return False
    bp = b[1] or ''
    if not bp.startswith('名詞'):
        return False
    if any(k in bp for k in _ADV_NI_OK_TAIL):
        return False
    for _, _, u in spans[i + 1:]:
        if u[0] and u[0][0] in '、。，．\t':
            break
        q = u[1] or ''
        if (q.startswith('動詞') or q.startswith('形容詞')
                or q.startswith('助動詞')):
            return False
    return True


def odd_spans(text, tokenize_fn, reasons_out=None,
              store=None, dict_index=None):
    """
    **異様と見た範囲**（項目48-IR・画面で紫にする）。

    `is_odd_run` の対を、重なる・隣り合うものはつないで (始まり, 終わり)
    の並びにする。表が無い・解析できないときは []（意見なし）。

    `reasons_out` を渡すと、**どの対でその印が立ったか**を
    `(始まり, 終わり, 理由の言葉)` で積む（項目48-MD・2026-08-31。
    候補一覧の「－ 補正根拠 －」の1行目）。**繋ぐ前の対ごと**に積む
    ——繋いだあとの範囲では「何と何が続けて置けないのか」が消える。
    渡さなければ何もしない（**答えは1文字も変わらない**）。
    """
    spans = []
    reading_reasons = {}
    for _a, _b, s, e in is_odd_run(text, tokenize_fn, with_spans=True, complete_line=True,
                                   store=store, dict_index=dict_index,
                                   reading_reasons_out=reading_reasons):
        if reasons_out is not None:
            reasons_out.append((s, e, reading_reasons.get((s,e), f'「{_a}」と「{_b}」は続けて置けない')))
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
