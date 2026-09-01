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
形態素解析による文の区切り判定。

誤補正の主な原因は、語の境界が分からないことだった。
「思うことは」を「思う/こと/は」と区切れないため、
「ことは」をひとかたまりと見て「今年」に誤って直してしまう。

janome があれば正確に区切れる。無い場合も動くよう、
簡易的な判定にフォールバックする。

    pip install janome
"""

import threading

try:
    from janome.tokenizer import Tokenizer
    _TOKENIZER = Tokenizer()
    HAS_JANOME = True
except Exception:
    _TOKENIZER = None
    HAS_JANOME = False

# janome の Tokenizer は**1つだけ**作って使い回している。
# この1つを複数のスレッドから同時に呼んではいけない
# （2026-08-10・「起動読み込み中にタブ移動ショートカットを入れると
# クラッシュする」の正体）。
#
# 理由: janome の辞書は mmap で読む（MMapSystemDictionary）。
# 同時に読むと読み出しが崩れることがあり、崩れたときに janome は
#     except Exception: ... sys.exit(1)
# を実行する（janome/dic.py の lookup。RAM 版も同じ）。
# **sys.exit は SystemExit を投げる。SystemExit は Exception の
# 子ではないので、こちらの try/except では捕まらず、tkinter の
# コールバックから外へ抜けて mainloop ごと終わる**＝アプリが
# 黙って消える。エラーも出ないので原因が分かりにくい。
#
# 対策は2段構え:
#   1. この錠前で、tokenize を同時に走らせない（根本）。
#      錠前を取るのは1行ぶんの解析の間だけなので、待たされても
#      ごく短い。画面が固まる心配はない。
#   2. それでも SystemExit が出たときは、簡易分割に落として
#      アプリだけは生かす（保険）。
_TOKENIZE_LOCK = threading.Lock()


def janome_lock():
    """
    janome の辞書を読む処理を囲むための錠前（with 文で使う）。

    janome_import.py のように**別の Tokenizer を作る**場所からも、
    同じ錠前を使うこと。Tokenizer を作り直しても、辞書の実体
    （mmap で開いたファイル）は janome の中で共有されているため、
    別インスタンスなら安全、ということにはならない。
    """
    return _TOKENIZE_LOCK


# 補正の対象にしない品詞。
# 助詞・助動詞・記号は、誤字ではなく文法上必要な要素なので触らない。
SKIP_POS = ('助詞', '助動詞', '記号', 'フィラー', '感動詞')

# 補正対象にしたい品詞。
# 名詞・動詞・形容詞など、意味を持つ語だけを見る。
TARGET_POS = ('名詞', '動詞', '形容詞', '副詞', '連体詞', '接頭詞')

# 品詞判定ができないとき（janome 非導入時）に、文法要素として守りたい語。
# これらを別の語に直してしまうと文が壊れる。
FUNCTION_WORDS = {
    'です', 'ます', 'でした', 'ました', 'ません', 'ましょう', 'でしょう',
    'ください', 'いる', 'ある', 'する', 'なる', 'れる', 'られる',
    'せる', 'させる', 'ない', 'たい', 'そう', 'よう', 'らしい',
    'こと', 'もの', 'とき', 'ところ', 'ため', 'ほう', 'わけ', 'はず',
    'から', 'ので', 'のに', 'けど', 'けれど', 'しかし', 'また',
    'そして', 'でも', 'ただ', 'なお', 'つまり', 'ように', 'ような',
    'について', 'として', 'による', 'により', 'における',
    'なく', 'なくて', 'ていない', 'ている', 'ていた', 'しました',
    'はなく', 'ではなく', 'となる', 'となり',
}

# 助詞。これで始まるひらがな列は、語ではなく文法的な繋がりの可能性が高い。
PARTICLES = ('は', 'が', 'を', 'に', 'で', 'と', 'も', 'の', 'へ',
             'や', 'か', 'ば', 'て', 'ど')

# 簡易分割（janome 非導入時）で区切りに使う助詞。
# 語の内部に現れにくいものだけに絞る。
# 「に」「で」「と」などは語中によく出るので使わない。
SPLIT_PARTICLES = ('の', 'を', 'が', 'は', 'へ')

# 活用語尾・助動詞的な終わり方。
FUNCTION_TAILS = ('ない', 'ます', 'ました', 'ません', 'です', 'でした',
                  'ている', 'ていた', 'ていない', 'なく', 'なら', 'たら',
                  'れば', 'ので', 'から', 'けど',
                  'たり', 'だり', 'つつ', 'ながら')


def looks_grammatical(text):
    """
    ひらがなだけの文字列が、語ではなく文法的な繋がりに見えるか。

    「はなく」（は＋なく）、「ていない」（て＋い＋ない）のように、
    助詞や助動詞が連なったものを1つの語として補正すると文が壊れる。
    janome があればこの判定は不要だが、無い場合の保険として使う。

    ただし判定を広げすぎると「もば」（もじの誤字）のような
    正当な補正対象まで弾いてしまうため、
    「助詞＋文法要素」の形になっているものだけを対象にする。
    """
    if not text:
        return False
    if text in FUNCTION_WORDS:
        return True

    # 助詞1文字 + 文法要素、の形（「は」+「なく」→「はなく」）
    if len(text) >= 3 and text[0] in PARTICLES:
        rest = text[1:]
        if rest in FUNCTION_WORDS or rest in ('なく', 'ない', 'ある', 'いる',
                                              'する', 'なる', 'あり', 'なり'):
            return True

    # 助動詞的な終わり方をする短い語
    for tail in FUNCTION_TAILS:
        if text.endswith(tail) and len(text) <= len(tail) + 1:
            return True

    return False


def is_function_word(text):
    """文法要素として守るべき語か（janome 非導入時の保険）"""
    return text in FUNCTION_WORDS or looks_grammatical(text)


def strip_function_tail(text):
    """
    ひらがな文字列の末尾から、文法的な活用語尾・助動詞をできるだけ長く切り離す。

    「にします」を「します」（文法要素）と「に」（助詞）に分けず、
    そのまま「にします」を1語として補正にかけると、
    「します」の部分まで巻き込んで無関係な語に化けることがある
    （例: 「にします」→「に字ます」）。

    ここでは末尾が既知の活用語尾・助動詞であれば機械的に切り離し、
    残った「内容部分（stem）」だけを補正対象として返す。
    stem が短すぎる／空になる場合は切り離さない
    （「です」単体などはそもそも is_function_word 側で弾かれる）。

    戻り値: (stem, tail) 。切り離せなければ (text, '')。
    """
    if not text:
        return text, ''

    # 長い語尾から先にマッチさせる（「ていない」を「ない」より優先）
    candidates = sorted(set(FUNCTION_TAILS) | set(FUNCTION_WORDS),
                        key=len, reverse=True)
    for tail in candidates:
        if not tail or tail == text:
            continue
        if text.endswith(tail) and len(text) > len(tail):
            stem = text[:-len(tail)]
            if len(stem) >= 2:
                return stem, tail
    return text, ''


class Token:
    """形態素1つ分。janome の有無にかかわらず同じ形で扱えるようにする。"""

    __slots__ = ('surface', 'pos', 'base_form', 'reading', 'start', 'end',
                 'has_reading', 'pos_sub', 'infl_form')

    def __init__(self, surface, pos, base_form, reading, start, end,
                 has_reading=True, pos_sub='', infl_form=''):
        self.surface = surface        # 表記
        self.pos = pos                # 品詞（大分類）
        self.pos_sub = pos_sub        # 品詞（細分類）。接尾・非自立の判定に使う
        self.base_form = base_form    # 原形（活用する語の場合）
        self.reading = reading        # 読み（ひらがなに直したもの）
        self.start = start            # 行内の開始位置
        self.end = end                # 行内の終了位置
        # **活用形**（連用形・連用タ接続…。2026-08-31・うにさんの指定
        # 「活用変化しているものはその形で書く」）。**画面の説明に
        # しか使わない**——補正の判断はここを見ない（見はじめると、
        # janome の有無で答えが変わる）。janome が無いときは ''。
        self.infl_form = infl_form
        # janome が辞書から読みを引けたか。
        # 引けなかった語は辞書に無い＝誤字の可能性がある。
        self.has_reading = has_reading

    @property
    def is_skippable(self):
        """助詞など、補正対象にすべきでない語か"""
        return self.pos in SKIP_POS

    @property
    def is_target(self):
        """補正対象にしてよい語か"""
        return self.pos in TARGET_POS

    def __repr__(self):
        return f'<{self.surface}({self.pos}) {self.start}:{self.end}>'


def katakana_to_hiragana(text):
    out = []
    for ch in text:
        if '\u30a1' <= ch <= '\u30f6':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


# 単独の濁点・半濁点（かな入力で「゛」キーだけが確定してしまった状態）
def _is_kana_char(ch):
    """ひらがな・カタカナか（濁点を落としてよい根拠になる文字）。"""
    return bool(ch) and (
        '\u3041' <= ch <= '\u3096' or '\u30a1' <= ch <= '\u30fa'
        or ch == 'ー')


DAKUTEN_MARKS = ('\u309b', '\u3099', '゛')      # 濁点
HANDAKUTEN_MARKS = ('\u309c', '\u309a', '゜')   # 半濁点

_DAKUTEN_COMPOSE = {
    'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
    'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
    'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
    'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    'う': 'ゔ',
}
_HANDAKUTEN_COMPOSE = {
    'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ',
}


def _with_katakana(table):
    """
    ひらがなの合成表に、同じ内容のカタカナの組を足す。

    検証レポート 2-D: 表がひらがなの鍵しか持っていなかったため、
    分解済み（NFD）のカタカナでは合成先が見つからず、
    **濁点そのものを捨てていた**（バックアップ → ハックアッフ）。
    macOS 由来のファイル名やクリップボードを貼ると行ごと壊れる。

    ひらがなとカタカナはコード上 0x60 ずれているだけなので、
    表を二重に持たず、ここで機械的に作る（片方だけ直す事故を防ぐ）。
    """
    out = dict(table)
    for src, dst in table.items():
        out[chr(ord(src) + 0x60)] = chr(ord(dst) + 0x60)
    return out


_DAKUTEN_COMPOSE = _with_katakana(_DAKUTEN_COMPOSE)
_HANDAKUTEN_COMPOSE = _with_katakana(_HANDAKUTEN_COMPOSE)


def _compose_across_one(out, table):
    """
    **1つ前のかなを跨いで合成する（順序の入れ替え）**。

    うにさんの指定（2026-08-11・項目48-AO）:

        「ふ・半濁点・あ」の3つの順番が入れ替わって
        「ふ・あ・半濁点」になっただけなので、
        **他の順序間違いと同じ扱い**でよい。

    直前の1文字がその印を受け取れず（＝合成に失敗し）、
    **その1つ前なら受け取れる**ときだけ、印をそちらへ渡す。
    **間に入った1打は消さずにそのまま残す**（本文の文字を
    落とさないため。項目48-AO の道(b)を採らなかった理由）。

        フア゜ラネタリウム → プアラネタリウム
                            → プラネタリウム（外来語の経路が1手で届く）

    表の鍵はかなだけなので、引けた時点で out[-2] はかな。
    間の1打がかなでないとき（記号・英字）は呼ばれない
    （そこは 48-AA の「わざと書いた印」として残す側）。
    """
    if len(out) < 2:
        return False
    composed = table.get(out[-2])
    if not composed:
        return False
    out[-2] = composed
    return True


def normalize_marks(text, swap_across=False, dropped=None):
    """
    分離した濁点・半濁点を前の文字と合成する。

    swap_across: 直前の1文字が印を受け取れないとき、**1つ前の
        かなを跨いで**合成してみる（打つ順番の入れ替え・項目48-AO）。
        既定は False。**落としたほうで補正が届かなかったときだけ**
        呼び出し側が True で呼び直す（学び38: 許可は、候補を絞る
        前ではなく、決まってから掛ける）。
    dropped: 名簿を渡すと、**落とした印の位置**（元の text での
        添字）をそこへ入れる。設計39（場違いな濁点・項目48-JP）が
        入口の判定に使う。**「落とす」の決まりはこの関数だけが
        持つ**——同じ判定を別の場所で書き直すと、片方だけ直して
        素通りする（学び22）。

    かな入力では濁点が独立したキーなので、
    「たんこ゛」のように濁点だけが残ることがある。
    これを「たんご」に直してから照合できるようにする。

    「こ゜」のように合成できない組み合わせは、
    濁点キーの誤打なので取り除く。

    **ただし、かなの後ろでなければ落とさない**（2026-08-11）。
    落とす根拠は「かなを打った直後に濁点キーを叩いた」ことなので、
    **前がかなでなければその根拠が無い**。
    うにさんのメモには `@ ⇒ ゛` `[ ⇒ ゜` のように、記号の説明として
    **わざと単体で書いた濁点**がある（JISかな配列の対応表）。
    これを落とすのは、**正しく書いたものを消している**。

    うにさんは「゛゜は単体で書くことはないのでスルーします」と
    言っているが、それは「直せるようにしなくてよい」であって
    「消してよい」ではない。**何もしないほうが、消すよりよい。**
    """
    if not text:
        return text
    out = []
    for i, ch in enumerate(text):
        if ch in DAKUTEN_MARKS:
            if out:
                composed = _DAKUTEN_COMPOSE.get(out[-1])
                if composed:
                    out[-1] = composed
                    continue
                if not _is_kana_char(out[-1]):
                    out.append(ch)      # わざと書かれた濁点。残す
                    continue
                # 打つ順番が入れ替わっただけかもしれない（項目48-AO）
                if swap_across and _compose_across_one(out,
                                                       _DAKUTEN_COMPOSE):
                    continue
                if dropped is not None:
                    dropped.append(i)
                continue    # かなの後ろの合成できない濁点は誤打
            out.append(ch)              # 行頭の濁点。残す
            continue
        if ch in HANDAKUTEN_MARKS:
            if out:
                composed = _HANDAKUTEN_COMPOSE.get(out[-1])
                if composed:
                    out[-1] = composed
                    continue
                # 半濁点が付かない字なら、濁点の打ち間違いかもしれない
                composed = _DAKUTEN_COMPOSE.get(out[-1])
                if composed:
                    out[-1] = composed
                    continue
                if not _is_kana_char(out[-1]):
                    out.append(ch)      # わざと書かれた半濁点。残す
                    continue
                # 打つ順番が入れ替わっただけかもしれない（項目48-AO）。
                # ここでは**同じ印**でしか跨がない。半濁点→濁点の
                # 読み替えまで重ねると、推測が3段になる。
                if swap_across and _compose_across_one(
                        out, _HANDAKUTEN_COMPOSE):
                    continue
                if dropped is not None:
                    dropped.append(i)
                continue
            out.append(ch)              # 行頭の半濁点。残す
            continue
        out.append(ch)
    return ''.join(out)


def tokenize(line):
    """
    1行を形態素に分割する。

    戻り値: [Token, ...]
    janome が無い場合は、文字種の切れ目で区切る簡易版を使う。
    """
    if not line:
        return []

    if HAS_JANOME:
        return _tokenize_janome(line)
    return _tokenize_fallback(line)


def _tokenize_janome(line):
    # 分割そのものは錠前の中で済ませ、結果を控えてから外で組み立てる
    # （錠前を握っている時間を最短にするため）。
    # tokenize() は生成器なので、**錠前の中で全部取り出す**こと。
    # list() を外でやると、実際の読み出しが錠前の外で走ってしまう。
    try:
        with _TOKENIZE_LOCK:
            raw = list(_TOKENIZER.tokenize(line))
    except SystemExit:
        # janome が辞書の読み出しに失敗して sys.exit(1) を呼んだ。
        # ここで受け止めないとアプリごと終わる（上の説明を参照）。
        return _tokenize_fallback(line)
    except Exception:
        return _tokenize_fallback(line)

    tokens = []
    pos = 0
    for t in raw:
        surface = t.surface
        # janome は元の文字列の位置を返さないので、順に数えていく
        start = line.find(surface, pos)
        if start < 0:
            start = pos
        end = start + len(surface)
        pos = end

        parts = t.part_of_speech.split(',')
        pos_major = parts[0] if parts else '*'
        # 細分類は3段まで運ぶ（項目48-JL・2026-08-25）。
        # 「固有名詞」だけでは**姓か名か**が分からず、うにさんの指定
        # 「苗字を登録することで、続く後ろを名前と保護するべき」が
        # 組めない（janome は未知語も固有名詞と推測するので、
        # 大分類だけを頼ると本物の異様まで黙る・項目48-JG）。
        # `固有名詞:人名:姓` の形。既存の読み手は `in` と
        # `split(':')[1]` なのでそのまま通る。
        pos_sub = ':'.join(p for p in parts[1:4] if p and p != '*')

        reading = getattr(t, 'reading', '*')
        has_reading = (reading != '*' and reading != '')
        if not has_reading:
            reading = surface

        infl = getattr(t, 'infl_form', '') or ''
        if infl == '*':
            infl = ''

        tokens.append(Token(
            surface=surface,
            pos=pos_major,
            base_form=t.base_form if t.base_form != '*' else surface,
            reading=katakana_to_hiragana(reading),
            start=start,
            end=end,
            has_reading=has_reading,
            pos_sub=pos_sub,
            infl_form=infl,
        ))
    return tokens


# 「その並びを、いちばん自然に読んだときの不自然さ」の控え。
# 同じ文字列を何度も測るので（候補ごとに1回ずつ呼ばれる）、
# 覚えておかないと重い。上限を切っておく。
_COST_CACHE = {}
_COST_CACHE_LIMIT = 20000


def path_cost(line):
    """
    その並びを**いちばん自然に読んだとき**の不自然さの合計。

    うにさんの指摘（2026-08-11）:
    「正しく読めるとは、**辞書と一致する**ではなく、
    **単語と単語の結びつきに違和感がない**こと」

    janome（IPAdic）は形態素の**並びやすさ**（連接コスト）を
    持っている。Viterbi の最小コスト（`node.min_cost`）は
    「その文をいちばん自然に読んだときの不自然さの合計」そのもので、
    **辞書に載っているかではなく、繋がりが自然かを直接測る**。

    しかも**初期状態から使える**（IPAdic は janome に同梱。
    学習も、メモも要らない）。

    **絶対値では使えない**（実測・項目48-AD）。語の長さや珍しさに
    引きずられるので、`7文字の名詞`（正しい）のほうが、たいていの
    壊れた並びより高く出る。**必ず比べて使うこと**
    （`naturalness.py` を参照）。

    戻り値: 不自然さの合計。janome が無い・測れないときは **None**
        （＝「意見なし」。呼ぶ側は今までどおりの判断をすること）。

    **錠前の中で測る。** janome の Tokenizer は1つしか無く、
    同時に呼ぶとアプリごと落ちる（学び16）。ここも tokenize と
    同じ構えにしてある。
    """
    if not line or not HAS_JANOME:
        return None
    got = _COST_CACHE.get(line)
    if got is not None:
        return got
    try:
        with _TOKENIZE_LOCK:
            raw = list(_TOKENIZER.tokenize(line))
    except SystemExit:
        return None
    except Exception:
        return None
    if not raw:
        return None
    try:
        cost = raw[-1].node.min_cost
    except Exception:
        # janome の作りが変わって min_cost が取れない。
        # **黙って 0 を返さないこと**（0 は「完全に自然」の意味に
        # なってしまい、あらゆる直しが通る）。意見なしにする。
        return None
    if len(_COST_CACHE) >= _COST_CACHE_LIMIT:
        _COST_CACHE.clear()
    _COST_CACHE[line] = cost
    return cost


def path_words(line):
    """
    その並びを**いちばん自然に読んだとき**の語の並び。

    馴染みの薄さ（`familiarity`）を測るのに使う。
    janome が無い・測れないときは空。
    """
    if not line or not HAS_JANOME:
        return []
    try:
        with _TOKENIZE_LOCK:
            raw = list(_TOKENIZER.tokenize(line))
    except SystemExit:
        return []
    except Exception:
        return []
    return [t.surface for t in raw]


def _char_kind(ch):
    if '\u3041' <= ch <= '\u3096':
        return 'hiragana'
    if '\u30a1' <= ch <= '\u30f6' or ch == 'ー':
        return 'katakana'
    if '\u4e00' <= ch <= '\u9fff':
        return 'kanji'
    if ch.isascii() and ch.isalnum():
        return 'alnum'
    return 'other'


def _tokenize_fallback(line):
    """
    janome が無いときの簡易分割。

    文字種が変わるところで区切り、さらにひらがなの塊は
    助詞になりやすい1文字でも区切る。
    「もばのにゅうりょく」を「もば」「の」「にゅうりょく」に分けて、
    それぞれを個別に補正できるようにするため。
    """
    tokens = []
    if not line:
        return tokens

    # まず文字種で大まかに区切る
    rough = []
    start = 0
    prev_kind = _char_kind(line[0])
    for i in range(1, len(line) + 1):
        kind = _char_kind(line[i]) if i < len(line) else None
        if kind != prev_kind:
            rough.append((start, i, line[start:i], prev_kind))
            start = i
            prev_kind = kind

    # ひらがなの塊を、助詞らしき1文字でさらに区切る
    for s, e, text, kind in rough:
        if kind != 'hiragana' or len(text) < 4:
            pos = '名詞' if kind in ('kanji', 'katakana', 'alnum') else '*'
            tokens.append(Token(text, pos, text, text, s, e, has_reading=False))
            continue

        sub_start = 0
        i = 0
        while i < len(text):
            ch = text[i]
            # 前後に十分な長さがある位置の助詞で区切る
            if (ch in SPLIT_PARTICLES
                    and i - sub_start >= 2
                    and len(text) - i - 1 >= 2):
                tokens.append(Token(text[sub_start:i], '*', '', '',
                                    s + sub_start, s + i, has_reading=False))
                tokens.append(Token(ch, '助詞', ch, ch,
                                    s + i, s + i + 1, has_reading=True))
                sub_start = i + 1
            i += 1
        if sub_start < len(text):
            tokens.append(Token(text[sub_start:], '*', '', '',
                                s + sub_start, e, has_reading=False))

    return tokens


def is_unknown_word(token):
    """
    その形態素が「辞書に無い語」かどうか。

    janome は未知語にも品詞を付けてしまう（多くは名詞扱い）ため、
    品詞の有無では判定できない。
    辞書に載っている語は読みが取れるので、それを手がかりにする。

    「かな」「うち」「いる」のような実在する語は読みが取れる。
    「もぱなゃうりゅき」のような打ち間違いは読みが取れない。
    """
    if not HAS_JANOME:
        return True     # 判定できないので、従来どおり補正対象にする
    # 読みが取れない = 辞書に無い = 誤字の可能性が高い
    return not token.has_reading


def _has_non_japanese(text):
    """
    数字・英字・記号を含むか。

    「3つ」「2つ」のような数詞や、コード片、記号混じりの文字列は
    補正の対象にすると文脈を壊すので触らない。
    """
    for ch in text:
        if ch.isascii():
            return True
        if ch.isdigit():
            return True
        # 全角英数字
        if '\uff01' <= ch <= '\uff5e':
            return True
    return False


def find_correctable_spans(line):
    """
    行の中から、補正の対象にしてよい範囲を返す。

    janomeは誤字を含むひらがな文字列を細かく分割してしまい、
    「もばのにゅうりょく」→「も/ば/のに/ゅうりょく」のように
    補正不能な断片にしてしまう。

    そのため、ひらがなだけの連続部分はjanomeを使わず
    独自の助詞分割で処理する。
    janomeは漢字・カタカナを含む語の境界判定にだけ使う。
    """
    if not line:
        return []

    spans = []
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]

        # ひらがなの連続部分はフォールバック処理で扱う
        if '\u3041' <= ch <= '\u3096':
            j = i
            while j < n and '\u3041' <= line[j] <= '\u3096':
                j += 1
            kana_run = line[i:j]
            kana_len = j - i

            # 漢字・カタカナの直後に続く短いひらがな（3文字以下）は、
            # 送り仮名・活用語尾として前の語の一部である可能性が高い。
            # 「繋がり」の「がり」や「綱切り」の「り」を単独で補正すると
            # 誤補正の原因になるため、スパンに含めない。
            prev_is_word = (i > 0 and not ('\u3041' <= line[i-1] <= '\u3096')
                           and not _has_non_japanese(line[i-1]))
            if prev_is_word and kana_len <= 3:
                i = j
                continue

            # 助詞(の・を・が・は・へ)で区切ってスパンを作る
            for s, e, text, is_unk in _split_kana_run(kana_run, i):
                spans.append((s, e, text, is_unk))
            i = j
            continue

        # 記号・数字・ASCII は補正対象外
        if _has_non_japanese(ch):
            i += 1
            continue

        # 漢字・カタカナ部分はjanomeで処理
        if HAS_JANOME:
            j = i
            while j < n:
                c = line[j]
                if '\u3041' <= c <= '\u3096':
                    break
                if _has_non_japanese(c):
                    break
                j += 1
            chunk = line[i:j]
            if chunk:
                for s, e, text, is_unk in _tokenize_kanji_chunk(chunk, i):
                    spans.append((s, e, text, is_unk))
            i = j
        else:
            i += 1

    return spans


def _split_kana_run(run_text, offset):
    """
    ひらがなの連続部分を助詞で区切ってスパンを返す。

    「もばのにゅうりょく」→ [(もば, True), (の, True-particle), (にゅうりょく, True)]
    全て unknown=True として返す（誤字かどうかは補正エンジンが判断）。
    """
    out = []
    n = len(run_text)
    sub_start = 0
    i = 0
    while i < n:
        ch = run_text[i]
        # 助詞になりやすい1文字で、前後に十分な長さがある位置で区切る
        if (ch in SPLIT_PARTICLES
                and i - sub_start >= 2
                and n - i - 1 >= 2):
            if sub_start < i:
                out.append((offset + sub_start, offset + i,
                             run_text[sub_start:i], True))
            # 助詞自体も含める（結合に必要な場合があるため）
            out.append((offset + i, offset + i + 1, ch, True))
            sub_start = i + 1
        i += 1
    if sub_start < n:
        out.append((offset + sub_start, offset + n,
                    run_text[sub_start:], True))
    return out


def _tokenize_kanji_chunk(chunk, offset):
    """
    漢字・カタカナを含む部分をjanomeで分割してスパンを返す。
    記号・数字を含む語と短すぎる語はスキップする。
    """
    if not HAS_JANOME or not chunk:
        return [(offset, offset + len(chunk), chunk, True)]

    out = []
    tokens = tokenize(chunk)
    for t in tokens:
        if t.is_skippable:
            continue
        if _has_non_japanese(t.surface):
            continue
        if len(t.surface) < 2:
            continue
        out.append((offset + t.start, offset + t.end,
                    t.surface, is_unknown_word(t)))
    return out


def describe():
    """現在の解析方式を説明する文字列を返す（UI表示用）"""
    if HAS_JANOME:
        return '形態素解析: janome'
    return '形態素解析: 簡易版（janome を入れると精度が上がります）'


if __name__ == '__main__':
    print(describe())
    print()
    samples = [
        '思うことは',
        '入れるのではなく、',
        '今やっている',
        'ファイル保存',
        '入れていないPC',
        'メモ帳',
        'もぱなゃうりゅきがはやくなる',
    ]
    for s in samples:
        print(f'--- {s} ---')
        for t in tokenize(s):
            mark = 'skip' if t.is_skippable else ('target' if t.is_target else '-')
            print(f'   {t.surface:8s} {t.pos:6s} {mark}')
        print('   補正対象:', find_correctable_spans(s))
        print()
