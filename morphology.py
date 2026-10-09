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
import re
from functools import lru_cache
from contextlib import contextmanager
from contextvars import ContextVar

# Tabs, arrows and column spacing end the native grammatical context.
# Padding adjacent to an explicit boundary belongs to that boundary.
COLUMN_SEPARATOR = re.compile(r'[ \u3000]*(?:[\t\r\n⇒→]|\s{2,})[ \u3000]*')

def source_column_bounds(text,start,end):
    """The original tab/arrow column containing the whole requested span."""
    if not 0<=start<end<=len(text):return None
    lo,hi=0,len(text)
    for match in COLUMN_SEPARATOR.finditer(text):
        if match.end()<=start:lo=match.end()
        elif match.start()>=end:
            hi=match.start();break
        else:return None
    return lo,hi


def detached_symbol_separators(text):
    """Whitespace-detached symbols keep the following source grammar separate.

    Unicode So/Sk identifies symbols, not arbitrary unknown words. ZWJ and
    presentation selectors may remain inside the same symbol run (UTS #51).
    This is not an emoji recognizer and does not split symbols used inside
    a word/argument. Return original Python positions including padding.
    """
    import unicodedata
    out=[]
    for match in re.finditer(r'(?<!\S)\S+(?!\S)',text):
        word=match.group()
        if (unicodedata.category(word[0])!='So' or
                any(unicodedata.category(ch) not in ('So','Sk')
                    and ch not in '\u200d\ufe0e\ufe0f' for ch in word)):
            continue
        a,b=match.span()
        while a and text[a-1].isspace():a-=1
        while b<len(text) and text[b].isspace():b+=1
        out.append((a,b))
    return tuple(out)


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
        # 活用形（連用形・連用タ接続等）。品詞説明と文脈の接続判定で使う。
        # 辞書がないときは空文字。未確認の活用形を推測で埋めない。
        self.infl_form = infl_form
        # 同梱の解析辞書、または版付きの語彙表から読みを引けたか。
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


def compound_voiced_reading(reading):
    voiced=dict(zip('かきくけこさしすせそたちつてとはひふへほ',
                    'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))
    return voiced[reading[0]]+reading[1:] if reading and reading[0] in voiced else None


from kana_text import katakana_to_hiragana


# 単独の濁点・半濁点（かな入力で「゛」キーだけが確定してしまった状態）
def _is_kana_char(ch):
    """ひらがな・カタカナか（濁点を落としてよい根拠になる文字）。"""
    return bool(ch) and (
        '\u3041' <= ch <= '\u3096' or '\u30a1' <= ch <= '\u30fa'
        or ch == 'ー')


DAKUTEN_MARKS = ('\u309b', '\u3099', '\uff9e')      # 濁点
HANDAKUTEN_MARKS = ('\u309c', '\u309a', '\uff9f')   # 半濁点

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


def normalize_marks(text, swap_across=False, dropped=None, miskeyed=None):
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

    miskeyed: 半濁点を濁点として読み替えた元の印の位置を返す。
        通常の合成とは異なる、既存処理の誤打判断を共有する。

    かな入力では濁点が独立したキーなので、
    「たんこ゛」のように濁点だけが残ることがある。
    これを「たんご」に直してから照合できるようにする。

    半濁点が付かないかなでは濁点としての合成も試す。
    どちらでも合成できない印は、かなの直後に限り取り除く。

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
                    if miskeyed is not None:miskeyed.append(i)
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


@lru_cache(maxsize=4096)
def colloquial_adjective_forms(line):
    """48-WM: 終止・連体の「い」を小さく書いた、辞書で確かめられる形容詞。

    文字数と原文位置は変えない。小書き母音一般を正しい語とする判定ではない。
    仮の通常表記は解析だけに使い、原文へ書き戻さない。
    """
    if not HAS_JANOME or 'ぃ' not in line:
        return ()
    normal = line.replace('ぃ', 'い')
    forms = []
    for t in _tokenize_janome(normal):
        original = line[t.start:t.end]
        if (t.pos == '形容詞' and t.has_reading and t.infl_form == '基本形'
                and len(original) >= 2 and original.endswith('ぃ')
                and original[:-1] == t.surface[:-1]
                and t.surface.endswith('い')):
            forms.append((t.start, t.end, t.base_form, t.reading,
                          t.pos_sub, t.infl_form))
    return tuple(forms)


def _restore_colloquial_adjectives(line, tokens):
    if 'ぃ' not in line:
        return tokens
    forms = colloquial_adjective_forms(line)
    if not forms:
        return tokens
    out = list(tokens)
    for start, end, base, reading, sub, infl in reversed(forms):
        indexes = [i for i, t in enumerate(out) if start <= t.start and t.end <= end]
        if not indexes:
            continue
        first, last = indexes[0], indexes[-1]
        if out[first].start != start or out[last].end != end:
            continue
        out[first:last + 1] = [Token(line[start:end], '形容詞', base, reading,
                                    start, end, True, sub, infl)]
    return out


@lru_cache(maxsize=4096)
def colloquial_auxiliary_forms(line):
    """48-XR: 助動詞の未然形＋小書きぅを、本文を保って推量のうと読む。

    GPT-6、2026-09-10。辞書で確かめた助動詞2個の境界だけを戻す。
    擬音や未知語の中の小書き母音全体を正規化するものではない。
    """
    if not HAS_JANOME or 'ぅ' not in line:
        return ()
    normal = line.replace('ぅ', 'う')
    tokens = _tokenize_janome(normal)
    forms = []
    for i, (a, b) in enumerate(zip(tokens, tokens[1:])):
        following = tokens[i+2] if i+2 < len(tokens) else None
        if (following is not None and b.end == following.start
                and not (following.pos == '助詞' and following.has_reading)
                and following.pos != '記号'):
            continue
        if (a.pos == b.pos == '助動詞' and a.has_reading and b.has_reading
                and a.infl_form in ('未然形','未然ウ接続') and b.base_form == 'う'
                and b.surface == 'う' and b.infl_form == '基本形'
                and a.end == b.start and line[a.start:a.end] == a.surface
                and line[b.start:b.end] == 'ぅ'):
            forms.append(tuple((t.start,t.end,t.pos,t.base_form,t.reading,
                                t.pos_sub,t.infl_form) for t in (a,b)))
    return tuple(forms)


def colloquial_auxiliary_normal_form(line):
    """解析用の表記のみを返す。文字数・原文位置は維持する。"""
    forms = colloquial_auxiliary_forms(line)
    if not forms:
        return line
    chars = list(line)
    for _a,b in forms:
        chars[b[0]] = 'う'
    return ''.join(chars)



# SP-2026-09-13-1 / GPT-6: spelling evidence is distinct from readable tokens.
# Keep the original positions; the existing native inflection routines are the
# sole grammatical source. These are not word-to-answer lookup entries.
from dataclasses import dataclass


@dataclass(frozen=True)
class SpellingFact:
    start: int
    end: int
    change_start: int
    original: str
    normal: str
    reading: str
    rule: str
    pos: str
    inflection: str

    @property
    def reason(self):
        return '読み・活用は説明できますが、通常の語尾が小書きになっています'


def _spelling_adjective_boundary(line,start,end):
    """A hypothetical adjective must not take a loanword's prefix or suffix.

    SP / GPT-6, 2026-09-13. Written boundaries, an original preceding functional
    unit, or a complete grammatical suffix establish the source word boundary.
    Parsing a guessed normalized prefix alone cannot establish it.
    """
    import re
    if start and ('ぁ'<=line[start-1]<='ゖ' or line[start-1]=='ー'):
        before=_tokenize_janome(line[:start])
        if (not before or not all(t.has_reading for t in before)
                or before[-1].pos not in ('助詞','助動詞','連体詞','記号')):
            return False
    if end<len(line) and 'ぁ'<=line[end]<='ゖ':
        suffix=re.match(r'[ぁ-ゖー]+',line[end:]).group()
        parts=_tokenize_janome(suffix)
        if not parts or not all(t.has_reading and t.pos in ('助詞','助動詞') for t in parts):
            return False
        from pos_grammar import explain_kana_run
        if not explain_kana_run(suffix,no_words=True,initial_state='END',before_kanji=False):
            return False
    return True


@lru_cache(maxsize=4096)
def original_spelling_facts(line):
    """Confirmed source spelling anomalies, without generating lexical guesses."""
    if not HAS_JANOME or not any(c in line for c in 'ぃぅ'):
        return ()
    from literal_examples import protected_ranges, overlaps
    protected=protected_ranges(line)
    out=[]
    for a,b in colloquial_auxiliary_forms(line):
        if a[3] not in ('です','ます','だ'):continue
        start,end=a[0],b[1]
        if overlaps(start,end,protected) or (end<len(line) and line[end] in 'ー〜～'):
            continue
        original=line[start:end]
        out.append(SpellingFact(start,end,b[0],original,original[:-1]+'う',
            a[4]+b[4],'SP-AUX-U','助動詞',a[6]+'+基本形'))
    for start,end,base,reading,sub,infl in colloquial_adjective_forms(line):
        if not _spelling_adjective_boundary(line,start,end):continue
        if overlaps(start,end,protected) or (end<len(line) and line[end] in 'ー〜～'):
            continue
        original=line[start:end]
        out.append(SpellingFact(start,end,end-1,original,original[:-1]+'い',
            reading,'SP-ADJ-I','形容詞',infl))
    return tuple(sorted(out,key=lambda f:(f.start,f.end,f.rule)))


_YOON_BASES = frozenset('きぎしじちぢにひびぴみりふゔてでとど')


@lru_cache(maxsize=2048)
def kana_syllable_ranges(text):
    # A written kana syllable cannot supply an internal word boundary.
    # This proves a source range, never the existence of a dictionary word.
    out=[]
    for i,c in enumerate(text):
        normalized=katakana_to_hiragana(c)
        if not i or normalized not in 'ゃゅょぁぃぅぇぉ':continue
        previous=text[i-1];base=katakana_to_hiragana(previous)
        if not ('ぁ'<=base<='ゖ'):continue
        if normalized in 'ゃゅょ' and base not in _YOON_BASES:continue
        end=i+1
        while end<len(text) and text[end]=='ー':end+=1
        out.append((i-1,end))
    return tuple(out)


@lru_cache(maxsize=2048)
def mixed_kana_syllable_ranges(text):
    return tuple((start,end) for start,end in kana_syllable_ranges(text)
                 if ('ぁ'<=text[start]<='ゖ')!=('ぁ'<=text[start+1]<='ゖ'))


def kana_syllable_boundary(text,cut):
    return not any(start<cut<end for start,end in kana_syllable_ranges(text))

def mixed_kana_syllable_scope(line,start,end):
    return not any(lo<end and start<hi and not (start<=lo and hi<=end)
                   for lo,hi in mixed_kana_syllable_ranges(line))


@lru_cache(maxsize=4096)
def preserves_native_adverbial_word(original,changed):
    """A native temporal/adverbial noun keeps its word boundary and sense.

    Match unchanged readings, so repairs elsewhere do not freeze the whole
    clause. A homophonic nominal needs its own original case relation.
    """
    if original==changed:return True
    old_parts=tokenize(original)
    protected=[t for t in old_parts if t.has_reading and t.pos=='名詞'
        and t.pos_sub=='副詞可能' and any(p.startswith('名詞,副詞可能,')
        and r==t.reading for p,f,b,r in dictionary_inflections(t.surface) or ())]
    if not protected:return True
    # A source-proved malformed numeric unit owns the inner homographic
    # adverb. Require the actual replacement to complete that same native
    # counter; an unrelated noun or a normal approximation is not exempt.
    from numeric_mark_repair import candidate_evidence
    lo=0
    while lo<min(len(original),len(changed)) and original[lo]==changed[lo]:lo+=1
    tail=0
    while (tail<len(original)-lo and tail<len(changed)-lo
            and original[len(original)-tail-1]==changed[len(changed)-tail-1]):tail+=1
    hi=len(original)-tail;face=changed[lo:len(changed)-tail]
    if candidate_evidence(original,lo,hi,face):
        protected=[t for t in protected if not (lo<=t.start and t.end<=hi)]
        if not protected:return True
    # Prove the original longest action before protecting a shorter token
    # inside it. A kana parse of a native sahen word can invent an adverb.
    from reading_segments import (native_bare_action_faces,completed_sahen_reading,
                                   native_predicate_link_boundaries)
    # A proved original te/de seam can introduce a bare action note.
    # The word ending exactly at the clause edge owns its whole range,
    # including any shorter temporal noun found by the best-path split.
    action_edges=native_predicate_link_boundaries(original,0)
    from pos_grammar import unexplained_shifted_predicate_tails
    from pos_grammar import native_object_functional_tail_frames
    original_predicates=(unexplained_shifted_predicate_tails(original)
                         +native_object_functional_tail_frames(original))
    def inside_original_action(token):
        # A native original continuative plus its intact functional prefix
        # owns an inner best-parse adverb. The final broken small vowel is
        # excluded; no repaired candidate supplies this source boundary.
        if any(start<token.start and token.end<=end-1
               for start,end,cut,reading in original_predicates):return True
        bare=original.rstrip('。！？.!?')
        if any(edge<=token.start and token.end<=len(bare)
               and native_bare_action_faces(bare[edge:]) for edge in action_edges):return True
        for start in range(max(0,token.start-24),token.start+1):
            if start and original[start-1] not in '、。！？!?\t\r\nをにがでもとは':continue
            for end in range(token.end+1,min(len(original),start+24)+1):
                heads=native_bare_action_faces(original[start:end])
                if not heads:continue
                for cut in range(end+1,min(len(original),end+10)+1):
                    if completed_sahen_reading(original[start:cut],allow_nonpolite=True,
                            return_action=True,finite_only=True) in heads:return True
        return False
    from oddness import case_particle_mismatch
    def broken_case_attachment(token):
        following=[part for part in old_parts if part.start>=token.end]
        return bool(len(following)>=2 and following[0].start==token.end
            and following[0].end==following[1].start
            and all(part.has_reading and part.pos=='助詞' for part in following[:2])
            and case_particle_mismatch(following[0].surface,
                                       following[0].pos+':'+following[0].pos_sub,
                                       following[1].surface,
                                       following[1].pos+':'+following[1].pos_sub))
    def broken_past_attachment(token):
        from oddness import noun_past_aux_mismatch
        following=next((part for part in old_parts if part.start==token.end),None)
        if following is None:return False
        def legacy(part):
            return (part.surface,part.pos+':'+part.pos_sub,part.reading,
                    part.start,part.end,part.has_reading,part.infl_form)
        return noun_past_aux_mismatch(legacy(token),legacy(following),original)
    from semantic_roles import adverbial_reading_needs_host
    def missing_adverbial_host(token):
        if not adverbial_reading_needs_host(token.surface,token.reading):return False
        preceding=next((p for p in old_parts if p.end==token.start),None)
        return preceding is None or (preceding.pos=='助詞'
            and preceding.pos_sub.startswith('格助詞'))
    protected=[token for token in protected if not inside_original_action(token)
               and not broken_case_attachment(token) and not missing_adverbial_host(token)
               and not broken_past_attachment(token)]
    if not protected:return True
    from difflib import SequenceMatcher
    def reading_positions(parts):
        result=[];reading=''
        for t in parts:
            word=t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface) else t.reading if t.has_reading else t.surface
            result.append((t,len(reading),len(reading)+len(word)));reading+=word
        return reading,result
    old_reading,old_positions=reading_positions(old_parts)
    new_reading,new_positions=reading_positions(tokenize(changed))
    blocks=SequenceMatcher(None,old_reading,new_reading,autojunk=False).get_matching_blocks()
    def keeps_particle(source,target):
        following=next((t for t in old_parts if t.start==source.end and t.has_reading and t.pos=='助詞'),None)
        if following is None:return True
        return any(t.start==target.end and t.surface==following.surface and t.pos=='助詞'
                   and (t.pos_sub==following.pos_sub or
                        # The same written nominal and identical particle
                        # retain their boundary across a repaired comparison.
                        # Native POS ambiguity of to is not a word edit.
                        following.surface=='と'
                        and {t.pos_sub,following.pos_sub}=={'並立助詞','格助詞:一般'}
                        or following.surface=='の'
                        and {t.pos_sub,following.pos_sub}=={'連体化','格助詞:一般'})
                   for t,c,d in new_positions)
    for source,lo,hi in old_positions:
        if source not in protected:continue
        match=next((b for b in blocks if b.a<=lo and hi<=b.a+b.size),None)
        if match is None:
            # An IME-only/unknown compound supplies no readable inner edge.
            # Accept another actual reading of the same adverbial word only
            # after aligning its unchanged source prefix.
            if any(any(p.startswith('名詞,副詞可能,') and r==source.reading
                       for p,f,base,r in dictionary_inflections(t.surface) or ())
                   and (original[:source.start]==changed[:t.start]
                        or native_spelling_only(original[:source.start],changed[:t.start]))
                   for t,c,d in new_positions if keeps_particle(source,t)):continue
            return False
        a=match.b+lo-match.a;b=a+hi-lo
        target=next((t for t,c,d in new_positions if c==a and d==b),None)
        if target and (target.surface==source.surface or any(
                p.startswith('名詞,副詞可能,') and r==source.reading
                for p,f,base,r in dictionary_inflections(target.surface) or ())) and keeps_particle(source,target):continue
        if target:
            from semantic_roles import candidate_nominal_spelling_evidence
            following=original[source.end:]
            if following.startswith(('を','が','に','で','の')) and candidate_nominal_spelling_evidence(
                    original[:source.start],target.surface,following):continue
        return False
    return True


def spelling_edit_allowed(line,start,end,replacement):
    if line[start:end]!=replacement and not mixed_kana_syllable_scope(line,start,end):return False
    """None: unrelated; False: loses a proven stem; True: exact scoped size edit."""
    facts=[f for f in original_spelling_facts(line) if f.start<end and start<f.end]
    if not facts:
        return None
    if len(replacement)!=end-start:
        return False
    for f in facts:
        a,b=max(start,f.start),min(end,f.end)
        expected=f.normal[a-f.start:b-f.start]
        if replacement[a-start:b-start]!=expected:
            return False
    return True


def _restore_colloquial_auxiliaries(line, tokens):
    normal = colloquial_particle_normal_form(colloquial_auxiliary_normal_form(line))
    if normal == line:
        return tokens
    # 証明した助動詞・終助詞の通常の読みで境界を取り直す。
    # 未知語が後続の「か」まで巻き込んでいる場合も同じ。
    # 全トークンの表記は原文へ戻し、本文は変更しない。
    return [Token(line[t.start:t.end],t.pos,t.base_form,t.reading,
                  t.start,t.end,t.has_reading,t.pos_sub,t.infl_form)
            for t in _tokenize_janome(normal)]


@lru_cache(maxsize=4096)
def _nominal_reading_evidence(reading):
    from corrector import table_surfaces_for_reading
    for sf in table_surfaces_for_reading(reading, limit=8):
        ps=dictionary_base_pos(sf)
        if ps and any(p.startswith(('名詞,一般,','名詞,サ変接続,')) for p in ps):
            # 読みの境界だけを戻す。名詞の表記や同音語は選ばない。
            return True
    return False


def _nominal_reading_tokens(text):
    if _nominal_reading_evidence(text):
        return [Token(text,'名詞',text,text,0,len(text),True,'一般')]
    # 既知の連体詞・形容詞は名詞に混ぜない。後ろの名詞の読みが
    # 辞書で確認できる位置だけで区切り、修飾語の品詞と原文位置を保つ。
    prefix=[]
    for t in _tokenize_janome(text)[:4]:
        if not t.has_reading or not (t.pos=='連体詞' or
                (t.pos=='形容詞' and t.infl_form=='基本形')):
            break
        if t.start!=(prefix[-1].end if prefix else 0):
            break
        prefix.append(t)
        tail=text[t.end:]
        if len(tail)>=2 and _nominal_reading_evidence(tail):
            return prefix+[Token(tail,'名詞',tail,tail,t.end,len(text),True,'一般')]
    return []


def _restore_unknown_predicates(line, tokens):
    """未知語に飲まれた格助詞と既知の述語を、原文のまま取り出す。"""
    if not any(not t.has_reading and len(t.surface)>=4 for t in tokens):
        return tokens
    import re
    out=list(tokens)
    for match in re.finditer(r'[ぁ-ゖー]{8,}',line):
        start,end=match.span();run=match.group()
        if len(run)>80:
            continue
        ids=[i for i,t in enumerate(out) if start<=t.start and t.end<=end]
        if not ids:
            continue
        lo,hi=ids[0],ids[-1]+1
        old=out[lo:hi]
        if old[0].start!=start or old[-1].end!=end or not any(not t.has_reading for t in old):
            continue
        for cut in range(2,len(run)-3):
            if run[cut]!='を':
                continue
            head_tokens=_nominal_reading_tokens(run[:cut])
            if not head_tokens:
                continue
            tail=_tokenize_janome(run[cut+1:])
            if (not tail or not all(t.has_reading for t in tail)
                    or tail[0].start!=0 or tail[-1].end!=len(run)-cut-1
                    or tail[0].pos!='動詞' or tail[0].pos_sub!='自立'
                    or len(tail[0].surface)<2):
                continue
            # 語尾に助動詞/接続助詞があり、述語として読める部分だけ。
            if not any(t.pos=='助動詞' or (t.pos=='助詞' and t.pos_sub.startswith('接続助詞')) for t in tail[1:]):
                continue
            offset=start+cut+1
            replacement=[Token(t.surface,t.pos,t.base_form,t.reading,t.start+start,t.end+start,
                                t.has_reading,t.pos_sub,t.infl_form) for t in head_tokens]
            replacement.append(Token('を','助詞','を','を',start+cut,offset,True,'格助詞:一般'))
            replacement += [Token(t.surface,t.pos,t.base_form,t.reading,t.start+offset,t.end+offset,
                                  t.has_reading,t.pos_sub,t.infl_form) for t in tail]
            out[lo:hi]=replacement
            break
    return out


def _restore_attested_nouns(line, tokens):
    """48-ABW: restore attested written nouns at existing exact boundaries.

    The versioned general_words roster and exact native Katakana noun entries
    supply lexical facts, not generated repair answers. Never split an unknown token to extract a known substring,
    join across a gap, or absorb a particle/predicate into a noun. The remaining
    tokens retain their original evidence and still undergo anomaly judgment.
    Native dictionary_inflections remains native-only; no fact is forged there.
    """
    from general_words import (EXACT_NOUNS,SOURCED_COMMON_NOUNS,sourced_common_noun_evidence,
                               GENERAL_WORDS,general_katakana_noun_reading)
    attested=EXACT_NOUNS.keys() | SOURCED_COMMON_NOUNS.keys() | GENERAL_WORDS
    if not tokens:
        return tokens
    katakana=lambda text:bool(text) and all('ァ'<=c<='ヶ' or c=='ー' for c in text)
    if not any(w in line for w in attested) and not any(katakana(t.surface) and not t.has_reading for t in tokens) and not any(
            katakana(a.surface) and katakana(b.surface) and a.end==b.start
            for a,b in zip(tokens,tokens[1:])):
        return tokens
    out=[];i=0
    while i<len(tokens):
        first=tokens[i];best=None;word='';end=first.start
        for j in range(i,min(len(tokens),i+8)):
            part=tokens[j]
            # A source-attested written noun can be split into archaic
            # bound verb stems by the old native dictionary. These fragments
            # supply no lexical reading; only the exact external whole word
            # below may restore it. Existing names/finite verbs stay native.
            nominal_fragment=(part.pos=='動詞' and part.infl_form.startswith('体言接続')
                and all('一'<=c<='鿿' for c in part.surface)
                and any(w.startswith(word+part.surface) for w in SOURCED_COMMON_NOUNS))
            if part.start!=end or part.pos not in ('名詞','接頭詞') and not nominal_fragment:
                break
            word+=part.surface;end=part.end
            if line[first.start:end]!=word:
                break
            entry=EXACT_NOUNS.get(word)
            if (entry is None and word in SOURCED_COMMON_NOUNS
                    and (any(not item.has_reading for item in tokens[i:j+1])
                        or all('一'<=c<='鿿' for c in word)
                        and any(item.pos=='動詞' and item.infl_form.startswith('体言接続')
                            for item in tokens[i:j+1]))
                    and not dictionary_inflections(word)):
                # External facts restore only a whole unread nominal range.
                # Known native homographs and ambiguous readings stay native.
                readings={(item['reading'],item['pos'].split(',')[1])
                          for item in sourced_common_noun_evidence(word)}
                if len(readings)==1:entry=next(iter(readings))
            # The existing reviewed ordinary Katakana roster already proves
            # this exact script reading. Share it only with a whole unread
            # nominal range; native words and proper-name readings stay native.
            if (entry is None and any(not item.has_reading for item in tokens[i:j+1])
                    and not dictionary_inflections(word)
                    and general_katakana_noun_reading(word,katakana_to_hiragana(word))):
                entry=(katakana_to_hiragana(word),'一般')
            # Whole, unchanged dictionary nouns may be split into names by
            # the surrounding text. A cost-table spelling is not this proof.
            native=katakana(word) and len(word)<=32
            if entry is None and native and (j>i or not first.has_reading):
                rows=[(rd,pos.split(',')[1]) for pos,form,base,rd in dictionary_inflections(word) or ()
                      if pos.startswith(('名詞,一般,','名詞,サ変接続,','名詞,形容動詞語幹,'))
                      and base==word and rd==katakana_to_hiragana(word)]
                if rows:entry=rows[0]
            if entry:
                best=(j+1,Token(word,'名詞',word,entry[0],first.start,end,
                               True,entry[1],''))
            if not native and not any(w.startswith(word) for w in attested):
                break
        if best:
            i,merged=best;out.append(merged)
        else:
            out.append(first);i+=1
    return out



def _restore_orthographic_nouns(line, tokens):
    """48-AGP: interpret an attested variant word without changing its text.

    A verified character variant AND a complete native noun entry are both
    required. Do not infer a word from a per-character reading or extract a
    substring from an unknown token. Native dictionary APIs remain exact.
    """
    from kanji_onkun import orthographic_variants, _ORTHOGRAPHIC_VARIANTS
    if not any(ch in _ORTHOGRAPHIC_VARIANTS for ch in line):
        return tokens
    out=[];i=0
    while i<len(tokens):
        first=tokens[i];best=None;word='';edge=first.start
        for j in range(i,min(len(tokens),i+8)):
            part=tokens[j]
            if part.start!=edge or part.pos not in ('名詞','接頭詞'):
                break
            word+=part.surface;edge=part.end
            if len(word)>32 or line[first.start:edge]!=word:break
            if dictionary_inflections(word):continue
            rows=[]
            for alternate in orthographic_variants(word):
                for pos,form,base,reading in dictionary_inflections(alternate) or ():
                    if (pos.startswith(('名詞,一般,','名詞,サ変接続,','名詞,形容動詞語幹,'))
                            and base==alternate and reading):
                        rows.append((pos.split(',')[1],reading))
            # Conflicting native interpretations need context we do not have.
            rows=set(rows)
            if len(rows)==1:
                sub,reading=next(iter(rows))
                best=(j+1,Token(word,'名詞',word,reading,first.start,edge,True,sub,''))
        if best:
            i,merged=best;out.append(merged)
        else:
            out.append(first);i+=1
    return out


def _restore_counter_readings(line,tokens):
    """Preserve native counting nouns at exact original token boundaries.

    Known verbs spanning the counter's end (やっつける) stay intact.
    The native dictionary supplies the full counting reading; no substring
    inside an unknown token or corrected candidate supplies this evidence.
    """
    from reading_segments import (native_counted_surface_readings,native_counted_surface_prefixes,
                                  native_counter_readings,native_numeric_quantity_spans)
    quantities=native_numeric_quantity_spans(line)
    counters=native_counted_surface_readings()
    prefixes=native_counted_surface_prefixes()
    kana_counters=native_counter_readings()
    out=[];i=0
    while i<len(tokens):
        first=tokens[i];best=None;word='';edge=first.start
        # 48-AHJ: an existing noun owns its following native case.
        # Do not turn 子供 + に + 本 into a new 二本 counter token.
        # Quantity proof after a case (本を二冊) remains independent.
        previous=tokens[i-1] if i else None
        # A suffix of a larger written number is not a separate count.
        # In １２３冊, the known ２３冊 reading cannot consume only that tail.
        if (first.start and first.surface[:1] in '0123456789０１２３４５６７８９'
                and (line[first.start-1] in '0123456789０１２３４５６７８９'
                     or any(start<first.start<end for start,end in quantities))):
            out.append(first);i+=1;continue
        if (previous and previous.has_reading and previous.end==first.start
                and previous.pos=='名詞' and first.has_reading
                and first.pos=='助詞' and first.pos_sub.startswith('格助詞')):
            out.append(first);i+=1;continue
        for j in range(i,min(len(tokens),i+5)):
            part=tokens[j]
            numeral=(part.pos=='名詞' and part.pos_sub=='数' and part.surface
                     and all(c in '0123456789０１２３４５６７８９' for c in part.surface))
            if part.start!=edge or not (part.has_reading or numeral):break
            word+=part.surface;edge=part.end
            if word not in prefixes:break
            # Keep existing kanji token POS. Only the established kana
            # restoration and exact digit-counter spellings need merging.
            if (word in counters and line[first.start:edge]==word
                    and (word in kana_counters or word[0] in '0123456789０１２３４５６７８９')):
                reading=word if word in kana_counters else counters[word][0]
                best=(j+1,Token(surface=word,pos='名詞',base_form=word,reading=reading,
                               start=first.start,end=edge,has_reading=True,pos_sub='一般'))
        if best:
            i,merged=best;out.append(merged)
        else:
            out.append(first);i+=1
    return out


_TOKENIZATION_CACHE=ContextVar('correctnote_native_tokenization_cache',default=None)
_TOKENIZATION_CACHE_LIMIT=2048
_NATIVE_TOKENIZATION_CACHE=ContextVar('correctnote_raw_tokenization_cache',default=None)


@contextmanager
def tokenization_scope():
    """Reuse native parsing during one analysis, then release all source text."""
    if _TOKENIZATION_CACHE.get() is not None:
        yield
        return
    token=_TOKENIZATION_CACHE.set({})
    native_token=_NATIVE_TOKENIZATION_CACHE.set({})
    try:yield
    finally:
        _NATIVE_TOKENIZATION_CACHE.reset(native_token)
        _TOKENIZATION_CACHE.reset(token)


def tokenize(line):
    cache=_TOKENIZATION_CACHE.get()
    if cache is None or not HAS_JANOME:return _tokenize_uncached(line)
    rows=cache.get(line)
    if rows is None:
        result=_tokenize_uncached(line)
        rows=tuple((t.surface,t.pos,t.base_form,t.reading,t.start,t.end,
                    t.has_reading,t.pos_sub,t.infl_form) for t in result)
        if len(cache)>=_TOKENIZATION_CACHE_LIMIT:cache.pop(next(iter(cache)))
        cache[line]=rows
    # Token is mutable. Neither a returned list nor one changed token may
    # corrupt a later grammar/reading caller's view of the same source.
    return [Token(*row) for row in rows]


def _tokenize_uncached(line):
    if not line:return []
    if not HAS_JANOME:return _tokenize_fallback(line)
    separators=list(COLUMN_SEPARATOR.finditer(line))
    if not separators:return _tokenize_field(line)
    out=[];cursor=0
    for match in separators+[None]:
        end=match.start() if match is not None else len(line)
        if cursor<end:
            for token in _tokenize_field(line[cursor:end]):
                out.append(Token(token.surface,token.pos,token.base_form,token.reading,
                    cursor+token.start,cursor+token.end,token.has_reading,
                    token.pos_sub,token.infl_form))
        if match is not None:
            surface=match.group()
            out.append(Token(surface,'記号',surface,surface,match.start(),match.end(),
                             False,'空白' if surface.isspace() else '一般'))
            cursor=match.end()
    return out


def _tokenize_field(line):
    """
    1行を形態素に分割する。

    戻り値: [Token, ...]
    janome が無い場合は、文字種の切れ目で区切る簡易版を使う。
    """
    if not line:
        return []

    if HAS_JANOME:
        tokens = _restore_orthographic_nouns(line, _tokenize_janome(line))
        tokens = _restore_attested_nouns(line, tokens)
        tokens = _restore_counter_readings(line, tokens)
        tokens = _restore_colloquial_auxiliaries(line, tokens)
        tokens = _restore_colloquial_adjectives(line, tokens)
        tokens = _restore_nominal_readings(line, tokens)
        tokens = _restore_unknown_predicates(line, tokens)
        return contextualize_tokens(tokens)
    return _tokenize_fallback(line)


@lru_cache(maxsize=8192)
def dictionary_base_pos(surface):
    """48-VU: 同梱辞書の完全一致から、基本形として可能な品詞の詳細をすべて返す。

    単独解析の最上位だけでは同形語を落とすため、全エントリを読む。
    未登録・辞書なし・読み出し失敗は None（判定材料なし）。
    空集合は、登録はあるがこの表記を基本形とする品詞がない、という意味。
    """
    if not HAS_JANOME or not surface:
        return None
    try:
        with _TOKENIZE_LOCK:
            entries = [e for e in _TOKENIZER.sys_dic.lookup(
                surface.encode('utf-8'), _TOKENIZER.matcher) if e[1] == surface]
            if not entries:
                return None
            extras = [_TOKENIZER.sys_dic.lookup_extra(e[0]) for e in entries]
        return frozenset(e[0] for e in extras if e[3] == surface)
    except (Exception, SystemExit):
        return None



@lru_cache(maxsize=8192)
def dictionary_paradigms(surface):
    """完全一致する辞書項の品詞・活用型・活用形・原形・読み。"""
    if not HAS_JANOME or not surface:
        return None
    try:
        with _TOKENIZE_LOCK:
            entries=[e for e in _TOKENIZER.sys_dic.lookup(
                surface.encode('utf-8'), _TOKENIZER.matcher) if e[1]==surface]
            extras=[_TOKENIZER.sys_dic.lookup_extra(e[0]) for e in entries]
        return tuple(dict.fromkeys((e[0], e[1], e[2], e[3], katakana_to_hiragana(e[4]))
                                   for e in extras))
    except (Exception, SystemExit):
        return None


@lru_cache(maxsize=4096)
def dictionary_prefix_paradigms(text):
    """Actual native entries at the unchanged start, from one trie lookup.

    None means unavailable/failed, so callers can retain an exhaustive
    fallback. These entries locate spans; they are not grammatical proof.
    """
    if not HAS_JANOME or not text:return None
    try:
        with _TOKENIZE_LOCK:
            entries=[e for e in _TOKENIZER.sys_dic.lookup(
                text.encode('utf-8'),_TOKENIZER.matcher) if text.startswith(e[1])]
            rows=[(e[1],_TOKENIZER.sys_dic.lookup_extra(e[0])) for e in entries]
        return tuple(dict.fromkeys((surface,row[0],row[1],row[2],row[3],
            katakana_to_hiragana(row[4])) for surface,row in rows))
    except (Exception,SystemExit):return None


@lru_cache(maxsize=8192)
def dictionary_inflections(surface):
    """表記の全辞書項。未登録は空tuple、辞書なし/失敗はNone。"""
    forms=dictionary_paradigms(surface)
    if forms is None:
        return None
    return tuple(dict.fromkeys((pos,form,base,reading)
                 for pos,kind,form,base,reading in forms))


@lru_cache(maxsize=8192)
def native_suru_form(surface,form,reading,allow_potential=True):
    """48-AIT: the grammatical suru is native サ変, not a godan homograph.

    IPAdic also gives すり (rubbing/printing) the base spelling する.
    The complete native paradigm, surface, form and reading bind this
    grammatical role. The existing potential できる remains ichidan.
    """
    return any(pos.startswith('動詞,自立,') and inflection==form and rd==reading
               and ((base=='する' and kind.startswith('サ変'))
                    or allow_potential and base in ('できる','出来る') and kind=='一段')
               for pos,kind,inflection,base,rd in dictionary_paradigms(surface) or ())


@lru_cache(maxsize=4096)
def native_potential_origins(surface,form,reading,pos_prefix='動詞,自立,'):
    """Native ichidan/godan pairs with the same spelling stem and reading.

    Both complete lemmas and the observed inflection must be dictionary
    entries. The godan paradigm supplies only their potential relation,
    never a replacement, guessed reading, or a new vocabulary entry.
    """
    from pos_grammar import _GODAN_ROW
    found=[]
    for pos,kind,inflection,base,rd in dictionary_paradigms(surface) or ():
        if (not pos.startswith('動詞,') or kind!='一段' or inflection!=form
                or rd!=reading or len(base)<2 or not base.endswith('る')):continue
        for terminal,row in _GODAN_ROW.items():
            if base[-2]!=row[2]:continue
            origin=base[:-2]+terminal
            for p,k,f,b,r in dictionary_paradigms(origin) or ():
                if not (p.startswith(pos_prefix) and k.startswith('五段')
                        and f=='基本形' and b==origin):continue
                expected=r[:-1]+row[2]+'る'
                if any(p2.startswith('動詞,') and k2=='一段' and f2=='基本形'
                       and b2==base and r2==expected
                       for p2,k2,f2,b2,r2 in dictionary_paradigms(base) or ()):
                    found.append((origin,r))
    return tuple(dict.fromkeys(found))


# Te/de auxiliaries have their own attachment, distinct from continuative
# compounds and contracted auxiliaries which already include te/de.
# TUFS: https://www.tufs.ac.jp/blog/icjs/activityreports/pdf/project_report_02.pdf
# JPF: https://www.jpf.go.jp/j/project/japanese/teach/tsushin/grammar/201409.html
TE_AUXILIARY_BASES=frozenset(('いる','居る','おる','居る','ある','有る','在る',
    'おく','置く','しまう','仕舞う','いく','行く','ゆく','くる','来る',
    'みる','見る','みせる','見せる','もらう','貰う','いただく','頂く',
    'あげる','上げる','さしあげる','差し上げる','やる','くれる','呉れる',
    'くださる','下さる'))


def native_te_auxiliary_attachment_mismatch(previous,auxiliary):
    """Share the existing native bound-verb connection at its source span.

    A te/de auxiliary cannot attach directly to another verb. The same
    independently attested compound spelling, form, and reading retains
    its lexical connection. Unknown tokens and other attachment types
    supply no negative evidence here.
    """
    a,b=previous,auxiliary
    return bool(a.has_reading and b.has_reading and a.end==b.start
        and a.pos=='動詞' and b.pos=='動詞' and b.pos_sub.startswith('非自立')
        and b.base_form in TE_AUXILIARY_BASES
        and not any(p.startswith('動詞,') and f==b.infl_form
                    and r==a.reading+b.reading for p,f,base,r in
                    dictionary_inflections(a.surface+b.surface) or ()))


@lru_cache(maxsize=8192)
def native_potential_auxiliary(surface,form,reading):
    """An attested potential of a native non-independent godan auxiliary."""
    origins=tuple(row for row in native_potential_origins(surface,form,reading,'動詞,非自立,')
                  if row[0] in TE_AUXILIARY_BASES)
    return origins[0][0] if origins else None


# 48-ZU / GPT-6 / 2026-09-11. Inspection of all 1,821 native basic
# adjective entries, including all 24 entries with at most two kana.
# IPAdic's くい adjective has no established independent meaning here.
# Its entry cannot supply positive evidence for a new adjective/noun split.
# This does not reclassify original text, noun/verb senses, or dialects.
_UNVERIFIED_INDEPENDENT_ADJECTIVES = frozenset(('くい',))


def native_independent_adjective(pos, form, lemma):
    """Native classification supplies positive lexical evidence only."""
    return (pos.startswith('形容詞,自立,') and form=='基本形'
            and lemma not in _UNVERIFIED_INDEPENDENT_ADJECTIVES)


# 48-WM: 文字を対象に取る用言。文字の説明という局所文脈に限って使う。
# GPT-6による構造規則（2026-09-10）。商品名や誤字の置換表ではない。
_TEXT_ACTION_BASES = frozenset(('書く', '読む', '打つ', '消す', '並べる',
                                '入力', '表示', '削除', '挿入', '選択'))


def _split_literal_character_objects(tokens):
    """小書き文字＋を＋文字操作を、名詞（文字そのもの）と格助詞に分ける。"""
    out = []
    for i, t in enumerate(tokens):
        b = tokens[i + 1] if i + 1 < len(tokens) else None
        if (len(t.surface) == 2 and t.surface[0] in 'ぁぃぅぇぉゃゅょっゎ'
                and t.surface[1] == 'を' and not t.has_reading
                and b is not None and t.end == b.start and b.has_reading
                and b.base_form in _TEXT_ACTION_BASES
                and (b.pos == '動詞' or (b.pos == '名詞' and b.pos_sub == 'サ変接続'))):
            char = t.surface[0]
            out.append(Token(char, '名詞', char, char, t.start, t.start + 1, True, '一般'))
            out.append(Token('を', '助詞', 'を', 'を', t.start + 1, t.end, True, '格助詞:一般'))
        else:
            out.append(t)
    return out


def native_prolonged_adverb_token_ranges(tokens):
    """Exact native adverbs behind same-vowel expressive source spellings.

    GPT-6 Astra / 2026-09-24. The dictionary proves the unprolonged
    adverb, not a new lexical entry or the following sentence. Keep
    original token edges and require the same vowel before と/っと.
    """
    if not any(c in t.surface for t in tokens for c in 'ぁぃぅぇぉ'):return ()
    import re
    from pos_grammar import prolonged_small_vowel
    out=[]
    for i,first in enumerate(tokens):
        source='';edge=first.start
        for part in tokens[i:]:
            if part.start!=edge:break
            source+=part.surface;edge=part.end
            if len(source)>18 or not all('ぁ'<=c<='ゖ' or c=='ー' for c in source):break
            match=re.search('[ぁぃぅぇぉ]ー?っ?と$',source)
            if not match or not prolonged_small_vowel(source[:match.start()+1]):continue
            compact=source[:match.start()]+source[match.start()+1:].lstrip('ー')
            if any(pos.startswith('副詞,') and rd==compact
                   for pos,form,base,rd in dictionary_inflections(compact) or ()):
                out.append((first.start,part.end));break
    return tuple(sorted(set(out)))


def _contextualize_expressive_adverbs(tokens):
    """未知の短い伸ばし音＋と＋用言を、副詞の用法として読む。

    GPT-6による構造規則、2026-09-10。既知名詞の再分類はしない。
    綴りの実在性ではなく、発音を写す形と明示された係り先を証拠にする。
    """
    ranges=dict(native_prolonged_adverb_token_ranges(tokens))
    out=[];index=0
    while index<len(tokens):
        token=tokens[index];end=ranges.get(token.start)
        if end is None:
            out.append(token);index+=1;continue
        parts=[]
        while index<len(tokens) and tokens[index].end<=end:
            parts.append(tokens[index]);index+=1
        surface=''.join(t.surface for t in parts)
        out.append(Token(surface,'副詞',surface,katakana_to_hiragana(surface),
                         token.start,end,False,'擬音文脈'))
    for i in range(len(out) - 2):
        t, particle, predicate = out[i:i + 3]
        sf = t.surface
        if (t.has_reading or t.pos != '名詞' or not sf.endswith(('ー', 'ッ'))
                or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in sf)):
            continue
        stem = sf[:-1]
        morae = sum(c not in 'ァィゥェォャュョ' for c in stem)
        if not (1 <= morae <= 2) or not stem or stem[0] in 'ァィゥェォャュョッー':
            continue
        if (particle.surface != 'と' or particle.pos != '助詞'
                or t.end != particle.start or particle.end != predicate.start
                or not predicate.has_reading):
            continue
        adjectival = predicate.pos == '名詞' and predicate.pos_sub == '形容動詞語幹'
        if predicate.pos == '名詞' and not adjectival:
            adjectival = any(p.startswith('名詞,形容動詞語幹,')
                             for p in (dictionary_base_pos(predicate.surface) or ()))
        if predicate.pos not in ('動詞', '形容詞') and not adjectival:
            continue
        out[i] = Token(sf, '副詞', sf, katakana_to_hiragana(sf),
                       t.start, t.end, False, '擬音文脈')
        out[i+1] = Token('と', '助詞', 'と', 'と', particle.start,
                         particle.end, True, '格助詞:一般')
        if adjectival:
            out[i+2] = Token(predicate.surface, '名詞', predicate.base_form,
                             predicate.reading, predicate.start, predicate.end,
                             True, '形容動詞語幹')
    return out


def _restore_nominal_readings(line, tokens):
    """48-XH: 未知語に割れた名詞の読みを辞書の境界へ戻す。本文は保持。"""
    if not any(not t.has_reading for t in tokens):
        return tokens
    import re
    from reading_segments import short_nominal_reading
    out = list(tokens)
    for match in re.finditer(r'[ぁ-ゖー]+', line):
        a, b = match.span()
        selected = [i for i,t in enumerate(out) if a <= t.start and t.end <= b]
        if not selected:
            continue
        lo, hi = selected[0], selected[-1] + 1
        pieces = out[lo:hi]
        if (pieces[0].start != a or pieces[-1].end != b
                or not any(not t.has_reading for t in pieces)):
            continue
        evidence = short_nominal_reading(match.group())
        if not evidence:
            continue
        head, tail, suffix, face = evidence
        cut = a + len(head)
        end = cut + len(tail)
        suffix_tokens = _tokenize_janome(suffix) if suffix else []
        if suffix and (not suffix_tokens or any(not t.has_reading for t in suffix_tokens)):
            continue
        positions = dictionary_base_pos(face) or ()
        sub = 'サ変接続' if any(p.startswith('名詞,サ変接続,') for p in positions) else '一般'
        first = pieces[0]
        if first.surface == head and first.end == cut:
            head_token = first
        else:
            head_token = Token(head, '名詞', head, head, a, cut, True, '一般')
        restored = [head_token, Token(tail, '名詞', tail, tail, cut, end, True, sub)]
        for t in suffix_tokens:
            restored.append(Token(t.surface,t.pos,t.base_form,t.reading,
                                  end+t.start,end+t.end,t.has_reading,t.pos_sub,t.infl_form))
        out[lo:hi] = restored
    return out


def _restore_polite_aux_boundaries(tokens):
    """48-XY: 動作句の途中で副詞になった丁寧語尾の区切りを戻す。

    「を＋サ変名詞＋まして」では、後続の名詞のために「まして」が
    副詞へ変わっても、直前の動作句の述語が欠けている。連用形の形容詞
    に直結する場合も同じ助動詞接続として調べる。読点・空白や、
    独立した節を始める「まして」はこの範囲に含まない。本文は変えない。
    設計/反証: GPT-6、2026-09-11。
    """
    out=[]
    for i,t in enumerate(tokens):
        a=tokens[i-1] if i else None
        before=tokens[i-2] if i>=2 else None
        attached=bool(a and a.has_reading and a.end==t.start)
        noun_action=bool(attached and a.pos=='名詞' and a.pos_sub=='サ変接続'
            and before and before.end==a.start and before.pos=='助詞'
            and before.pos_sub.startswith('格助詞'))
        adjective=bool(attached and a.pos=='形容詞' and a.infl_form=='連用テ接続')
        if (t.has_reading and t.pos=='副詞' and t.surface=='まして'
                and (noun_action or adjective)):
            out.extend((Token('まし','助動詞','ます','まし',t.start,t.start+2,True,'','連用形'),
                        Token('て','助詞','て','て',t.start+2,t.end,True,'接続助詞','')))
        else:
            out.append(t)
    return out


@lru_cache(maxsize=4096)
def native_sahen_compound_reading(surface):
    """An independently classified action with a native sahen suffix.

    GPT-6 Astra / 2026-09-24: the whole action already has meaning evidence;
    contiguous native nouns and its actual suffix supply the reading/POS.
    This does not add a dictionary entry or allow arbitrary noun+suffix words.
    """
    if not HAS_JANOME or not surface or not 2<=len(surface)<=24:return ''
    parts=_tokenize_janome(surface)
    # A native nominal prefix keeps an independently attested sahen host.
    # This is productive source morphology, not a new dictionary entry or
    # a requirement that the compound already have a semantic roster row.
    if parts and parts[0].has_reading and parts[0].pos=='接頭詞' and parts[0].pos_sub=='名詞接続':
        first=parts[0];host=surface[first.end:]
        # Repetition applies to the action itself. Merely distributive
        # nominal prefixes (each N, etc.) do not turn N into a verb.
        # Other compounds keep their independent whole-word POS evidence.
        if first.surface=='再' and any(pos.startswith('接頭詞,名詞接続,') and rd==first.reading
               for pos,form,base,rd in dictionary_inflections(first.surface) or ()):
            readings={rd for pos,form,base,rd in dictionary_inflections(host) or ()
                      if pos.startswith('名詞,サ変接続,') and base==host}
            if len(readings)==1:return first.reading+next(iter(readings))
    from semantic_roles import VERB_ROLES
    if surface not in VERB_ROLES:return ''
    if (len(parts)<2 or ''.join(t.surface for t in parts)!=surface
            or parts[0].start!=0 or parts[-1].end!=len(surface)
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))
            or not all(t.has_reading and t.pos=='名詞' for t in parts)):
        return ''
    suffix=parts[-1]
    if not any(p.startswith('名詞,接尾,サ変接続,') and b==suffix.surface and r==suffix.reading
               for p,f,b,r in dictionary_inflections(suffix.surface) or ()):return ''
    if not all(any(p.startswith(('名詞,一般,','名詞,サ変接続,','名詞,形容動詞語幹,'))
                   and b==t.surface and r==t.reading
                   for p,f,b,r in dictionary_inflections(t.surface) or ()) for t in parts[:-1]):
        return ''
    return ''.join(t.reading for t in parts)


def _contextualize_sahen_compounds(tokens):
    out=[];i=0
    while i<len(tokens):
        head=tokens[i];merged=False
        if head.has_reading and (head.pos=='名詞' or head.pos=='接頭詞' and head.pos_sub=='名詞接続'):
            for j in range(i+1,min(len(tokens),i+8)):
                tail=tokens[j]
                if (tokens[j-1].end!=tail.start or tail.end-head.start>24
                        or tail.pos!='名詞' or not tail.has_reading):break
                if tail.pos_sub!='接尾:サ変接続' and not (head.pos=='接頭詞' and tail.pos_sub=='サ変接続'):continue
                word=''.join(t.surface for t in tokens[i:j+1])
                reading=native_sahen_compound_reading(word)
                if reading and reading==''.join(t.reading for t in tokens[i:j+1]):
                    out.append(Token(word,'名詞',word,reading,head.start,tail.end,True,'サ変接続',''))
                    i=j+1;merged=True;break
        if not merged:out.append(head);i+=1
    return out


def _contextualize_nominal_actions(tokens):
    """48-XS・AGH: 実辞書の一般名詞にある動作用法を、するの文脈で読む。

    GPT-6の設計・反証（2026-09-10）。誤/脱/衍＋字/語/句/文は
    書かれた結果と、その結果を生む行為の両方を指せる。辞書で一般名詞に
    分類されても、直後がするの活用なら動作名詞として解釈する。
    接頭要素だけで造語を認めず、全体が実辞書の普通名詞であることを要求。
    既存の意味役割表が持つ動作用法も同じ口で共有する。
    """
    out=_contextualize_sahen_compounds(tokens)
    for i,(a,b) in enumerate(zip(out,out[1:])):
        if (a.pos == '名詞' and a.pos_sub == '一般' and a.has_reading
                and b.pos == '動詞' and b.base_form == 'する' and b.has_reading
                and native_suru_form(b.surface,b.infl_form,b.reading,False)
                and a.end == b.start
                and any(p.startswith('名詞,一般,')
                        for p in (dictionary_base_pos(a.surface) or ()))):
            from semantic_roles import classified_nominal_action
            written_error=(len(a.surface)==2 and a.surface[0] in '誤脱衍'
                           and a.surface[1] in '字語句文')
            # An exact native sahen homograph is the same action evidence
            # used by completed readings and omissions. Keep the actual
            # suru attachment and the noun's whole original reading.
            from reading_segments import native_action_noun_reading
            if (written_error or native_action_noun_reading(a.surface,a.reading)
                    or classified_nominal_action(a.surface,a.reading)):
                out[i]=Token(a.surface,a.pos,a.base_form,a.reading,a.start,a.end,
                             a.has_reading,'サ変接続',a.infl_form)
    return out


@lru_cache(maxsize=8192)
def _nominal_suffix_parts(surface):
    """一般名詞＋一般接尾辞の辞書上の区切りを返す。語の名簿は増やさない。"""
    if len(surface)<3 or not all('一'<=c<='鿿' for c in surface):
        return None
    head,suffix=surface[:-1],surface[-1]
    readings={rd for pos,form,base,rd in dictionary_inflections(suffix) or ()
              if pos.startswith('名詞,接尾,一般,') and base==suffix}
    if len(readings)!=1:
        return None
    # 語幹は、辞書がその表記を一語として読める場合だけ採用する。
    parts=_tokenize_janome(head) if HAS_JANOME else []
    if (len(parts)!=1 or parts[0].surface!=head or not parts[0].has_reading
            or parts[0].pos!='名詞' or parts[0].pos_sub not in ('一般','サ変接続','形容動詞語幹')):
        return None
    a=parts[0]
    return (head,a.reading,a.pos_sub,a.infl_form,suffix,next(iter(readings)))


def _restore_nominal_affixes(tokens):
    """48-AGH: retain nominal prefix/suffix attachment across a noun boundary.

    This interprets unchanged native parts; it neither creates dictionary
    entries nor searches for a correction. A person-name suffix keeps the
    personal-name parse. The preceding noun must itself remain unchanged.
    """
    out=[];i=0
    plain=('一般','サ変接続','形容動詞語幹','副詞可能')
    while i<len(tokens):
        t=tokens[i];prev=out[-1] if out else None
        nxt=tokens[i+1] if i+1<len(tokens) else None
        nominal_left=(prev is not None and prev.end==t.start and prev.has_reading
                      and prev.pos=='名詞' and prev.pos_sub in plain)
        if (nominal_left and t.has_reading and t.pos=='接頭詞'
                and t.pos_sub=='名詞接続' and nxt is not None
                and t.end==nxt.start and nxt.has_reading
                and nxt.pos=='名詞' and nxt.pos_sub in plain
                and any(p.startswith('接頭詞,名詞接続,') and rd==t.reading
                        for p,f,b,rd in dictionary_inflections(t.surface) or ())):
            word=t.surface+nxt.surface
            out.append(Token(word,'名詞',word,t.reading+nxt.reading,t.start,nxt.end,
                             True,nxt.pos_sub,nxt.infl_form))
            i+=2;continue
        if (nominal_left and t.has_reading and t.pos=='名詞'
                and t.pos_sub=='固有名詞:人名:名' and 2<=len(t.surface)<=4
                and not (nxt is not None and nxt.start==t.end
                         and nxt.pos=='名詞' and nxt.pos_sub=='接尾:人名')):
            suffix,head=t.surface[0],t.surface[1:]
            left=_tokenize_janome(prev.surface+suffix)
            right=_tokenize_janome(head)
            if (len(left)==2 and left[0].surface==prev.surface
                    and left[0].reading==prev.reading and left[0].has_reading
                    and left[1].surface==suffix and left[1].has_reading
                    and left[1].pos=='名詞' and left[1].pos_sub=='接尾:一般'
                    and len(right)==1 and right[0].surface==head
                    and right[0].has_reading and right[0].pos=='名詞'
                    and right[0].pos_sub in plain):
                a,b=left[1],right[0];edge=t.start+len(suffix)
                out.append(Token(suffix,'名詞',suffix,a.reading,t.start,edge,True,a.pos_sub,a.infl_form))
                out.append(Token(head,'名詞',b.base_form,b.reading,edge,t.end,True,b.pos_sub,b.infl_form))
                i+=1;continue
        out.append(t);i+=1
    return out


def _restore_nominal_suffix_boundaries(tokens):
    """一字＋複数字へ誤分割された名詞を、既知の語幹＋接尾辞で読み直す。"""
    out=[]
    for b in tokens:
        if out:
            a=out[-1]
            if (a.end==b.start and len(a.surface)==1 and len(b.surface)>=2
                    and a.has_reading and b.has_reading and a.pos==b.pos=='名詞'
                    and a.pos_sub=='一般' and b.pos_sub in ('一般','サ変接続','形容動詞語幹')):
                parts=_nominal_suffix_parts(a.surface+b.surface)
                if parts is not None:
                    head,rd,sub,form,suffix,suffix_rd=parts
                    split=b.end-1
                    out[-1]=Token(head,'名詞',head,rd,a.start,split,True,sub,form)
                    out.append(Token(suffix,'名詞',suffix,suffix_rd,split,b.end,True,'接尾:一般'))
                    continue
        out.append(b)
    return out


def _restore_imperative_emphasis(tokens):
    """命令形の終わりを伸ばす「い」を、継続の「いる」に取り違えない。"""
    out=list(tokens)
    for i in range(1,len(out)):
        a,b=out[i-1:i+1]
        if (a.pos!='動詞' or a.pos_sub!='自立' or not a.has_reading
                or b.surface not in ('い','ぃ') or a.end!=b.start):
            continue
        nxt=out[i+1] if i+1<len(out) else None
        if nxt is not None and not (nxt.pos=='記号' and nxt.surface in '。！？!?、」』'):
            continue
        entries=dictionary_inflections(a.surface) or ()
        imperative=next(((form,base) for pos,form,base,rd in entries
                        if pos.startswith('動詞,自立,') and form.startswith('命令')
                        and rd==a.reading),None)
        if imperative is None:
            continue
        form,base=imperative
        out[i-1]=Token(a.surface,a.pos,base,a.reading,a.start,a.end,True,a.pos_sub,form)
        out[i]=Token(b.surface,'助詞',b.surface,b.surface,b.start,b.end,True,'終助詞')
    return out


@lru_cache(maxsize=4096)
def _native_adverbial_noun(surface,reading,voiced_suffix=False):
    """Same spelling/reading has a native adverbial nominal use."""
    readings={reading}
    if voiced_suffix and reading:
        import unicodedata
        unvoiced=unicodedata.normalize('NFD',reading[0]).replace('\u3099','')
        if len(unvoiced)==1:readings.add(unvoiced+reading[1:])
    return any(pos.startswith('名詞,') and '副詞可能' in pos and rd in readings
               for pos,form,base,rd in dictionary_inflections(surface) or ())


@lru_cache(maxsize=4096)
def _native_nominal_case_entry(surface, reading):
    """Same spelling and reading may have a noun sense as well as an adverb sense."""
    entries=[(pos,base) for pos,form,base,rd in dictionary_inflections(surface) or ()
             if rd==reading and pos.startswith('名詞,')
             and not any(x in pos for x in ('固有名詞','接尾','非自立'))]
    return min(entries) if entries else None


def _contextualize_nominal_cases(tokens):
    """Use a native nominal homograph when an explicit nominal case follows.

    GPT-6 / 2026-09-11 / 48-YZ/ZF. Adverbs and adnominals may have a native noun sense.
    This changes the grammatical interpretation,
    keeping the original characters, reading and positions. An adverb before
    a predicate, an unknown word, or another reading supplies no noun evidence.
    """
    out=list(tokens)
    for i,(a,b) in enumerate(zip(out,out[1:])):
        if (a.pos not in ('副詞','連体詞') or not a.has_reading or not b.has_reading or a.end!=b.start
                or b.pos!='助詞' or not b.pos_sub.startswith(('格助詞','係助詞','連体化'))):
            continue
        entry=_native_nominal_case_entry(a.surface,a.reading)
        if entry is not None:
            pos,lemma=entry
            out[i]=Token(a.surface,'名詞',lemma,a.reading,a.start,a.end,True,
                         ':'.join(p for p in pos.split(',')[1:] if p!='*'))
    return out


def _contextualize_adverbial_nominals(tokens):
    """Retain native adverbial evidence before a predicate, including nominal suffixes.

    GPT-6, 2026-09-11. Surface, reading, offsets and the original subtype remain.
    Only the same dictionary spelling/reading supplies the additional role.
    """
    out=list(tokens)
    for i,(a,b) in enumerate(zip(out,out[1:])):
        if (a.pos!='名詞' or '副詞可能' in a.pos_sub or '固有名詞' in a.pos_sub
                or not a.has_reading or not b.has_reading or a.end!=b.start
                or b.pos not in ('動詞','形容詞')):
            continue
        suffix=(a.pos_sub.startswith('接尾') and i>0 and out[i-1].pos=='名詞'
                and out[i-1].has_reading and out[i-1].end==a.start)
        if _native_adverbial_noun(a.surface,a.reading,suffix):
            out[i]=Token(a.surface,a.pos,a.base_form,a.reading,a.start,a.end,
                         a.has_reading,a.pos_sub+':副詞可能',a.infl_form)
    return out



def _contextualize_terminal_questions(tokens):
    """48-ABV / GPT-6 / 2026-09-13: a finite predicate followed by final か.

    Retain the native ambiguous label in indefinite or alternative uses.
    Only original, contiguous, known tokens and a completed predicate give
    positive evidence for the sentence-final question particle.
    """
    out=list(tokens)
    for i,t in enumerate(out):
        if (i==0 or t.surface!='か' or t.pos!='助詞' or not t.has_reading
                or '終助詞' not in t.pos_sub):
            continue
        tail=out[i+1:]
        if any(x.pos!='記号' or x.surface not in ('。','！','？','!','?','」','』') for x in tail):
            continue
        head=out[i-1]
        if head.end!=t.start:
            continue
        if head.surface=='の' and head.pos in ('助詞','名詞') and i>=2:
            previous=out[i-2]
            if previous.end!=head.start or not head.has_reading:
                continue
            head=previous
        if (not head.has_reading or head.pos not in ('動詞','形容詞','助動詞')
                or head.infl_form!='基本形'):
            continue
        out[i]=Token(t.surface,t.pos,t.base_form,t.reading,t.start,t.end,
                     t.has_reading,'終助詞',t.infl_form)
    return out


def native_tokens_in_span(text,start,end):
    """Use exact original token boundaries, never a standalone fragment parse."""
    if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(text):
        return ()
    parts=tuple(t for t in tokenize(text) if start<=t.start and t.end<=end)
    if (not parts or parts[0].start!=start or parts[-1].end!=end
            or ''.join(t.surface for t in parts)!=text[start:end]
            or any(a.end!=b.start for a,b in zip(parts,parts[1:]))):
        return ()
    return parts


def contextualize_tokens(tokens):
    """48-VO: 前後の接続と既知の複合語から、品詞と単位を確かめる。

    文字列は変更しない。助詞の同形語は接続の証拠がある場合だけ選び直す。
    名詞＋名詞化の接尾辞（爪＋切り等）は、同梱辞書が認めるまとまりだけを採る。
    漢字だけの接尾辞や複数の「ら」まで一律に普通名詞へ変えることはしない。
    解析不能時に語尾だけから品詞を決めることはしない。
    """
    tokens = _restore_imperative_emphasis(tokens)
    out = _restore_nominal_suffix_boundaries(_contextualize_nominal_actions(
        _contextualize_expressive_adverbs(_restore_polite_aux_boundaries(
            _split_literal_character_objects(list(tokens))))))
    out = _contextualize_nominal_cases(_restore_nominal_affixes(out))
    out = _contextualize_terminal_questions(_contextualize_adverbial_nominals(out))
    # 48-VS: 「同じ」は連体用法とナ形容詞の述語用法を兼ねる不規則語。
    # 辞書の連体詞分類だけで「同じだけ／同じに／同じです」を拒まない。
    # 名詞に直結する連体用法（同じ本・同じように）は元の分類を保つ。
    for i in range(len(out) - 1):
        a, b = out[i:i + 2]
        if (a.pos == '連体詞' and a.base_form in ('同じ', 'おなじ')
                and a.has_reading and b.has_reading and a.end == b.start
                and ((b.pos == '助詞' and
                      (b.pos_sub == '副助詞' or
                       (b.pos_sub.startswith('格助詞') and b.surface == 'に')))
                     or (b.pos == '助動詞' and b.base_form in ('だ', 'です')))):
            out[i] = Token(a.surface, '名詞', a.base_form, a.reading,
                           a.start, a.end, True, '形容動詞語幹')
    for i in range(1, len(out) - 1):
        a, t, b = out[i - 1:i + 2]
        # 48-VQ: 五段の未然形＋さ＋れる（読まされる・待たされる）。
        # IPAdicが「さ」を独立した「する」と読む場合は、使役の「す」へ。
        # 一段の「食べされる」や、空白を挟む別の語には適用しない。
        if (a.pos == '動詞' and a.pos_sub == '自立'
                and a.infl_form == '未然形' and a.has_reading
                and a.reading and a.reading[-1] in 'あかがただなばまらわ'
                and not a.base_form.endswith('す')
                and t.surface == 'さ' and t.pos == '動詞'
                and t.pos_sub == '自立' and t.base_form == 'する'
                and t.infl_form == '未然レル接続'
                and b.pos == '動詞' and b.pos_sub == '接尾'
                and b.base_form == 'れる' and t.has_reading and b.has_reading
                and a.end == t.start and t.end == b.start):
            out[i] = Token(t.surface, '動詞', 'す', t.reading,
                           t.start, t.end, True, '接尾', '未然形')
        if (t.surface == 'より' and t.pos == '助詞'
                and a.pos == '名詞' and a.has_reading
                and a.end == t.start and t.end == b.start
                and ((b.pos == '助詞' and b.surface == 'に')
                     or (b.pos == '助動詞' and b.surface in ('だ', 'です')))):
            # 「東京よりに」は寄り（接尾辞）。比較の「東京より遠い」は別。
            # 「東京よりの便り」は起点の格助詞とも読めるので決め直さない。
            out[i] = Token(t.surface, '名詞', '寄り', t.reading,
                           t.start, t.end, t.has_reading, '接尾:一般')
    # 48-VZ: 連用形の列が既知の複合語を作り、ナ形容詞の述語に続くなら名詞用法。
    # 語の途中（追い／焚き等）の境界を異様判定へ渡さない。
    i = 0
    while i < len(out):
        j = i
        while (j < len(out) and out[j].pos == '動詞'
               and out[j].pos_sub == '自立' and out[j].infl_form == '連用形'
               and out[j].has_reading and (j == i or out[j-1].end == out[j].start)):
            j += 1
        if (j - i >= 2 and j < len(out) and out[j].pos == '名詞'
                and out[j].pos_sub == '形容動詞語幹' and out[j].has_reading
                and out[j-1].end == out[j].start):
            surface = ''.join(t.surface for t in out[i:j])
            from seed_japanese import is_unit
            if is_unit(surface) is True:
                first, last = out[i], out[j-1]
                token = Token(surface, '名詞', surface, ''.join(t.reading for t in out[i:j]),
                              first.start, last.end, True, '一般')
                out[i:j] = [token]
                j = i + 1
        i = max(i + 1, j)
    merged = []
    for t in out:
        if merged and merged[-1].end == t.start:
            a = merged[-1]
            numeric = (a.pos == t.pos == '名詞'
                       and a.pos_sub == t.pos_sub == '数')
            compound = False
            if (a.pos == t.pos == '名詞' and t.pos_sub.startswith('接尾')
                    and a.has_reading and t.has_reading and not numeric
                    and a.pos_sub in ('一般', 'サ変接続')
                    and any('一' <= ch <= '鿿' for ch in t.surface)
                    and any('ぁ' <= ch <= 'ゖ' for ch in t.surface)):
                try:
                    from seed_japanese import is_unit
                    compound = is_unit(a.surface + t.surface) is True
                except Exception:
                    pass
            if numeric or compound:
                word = a.surface + t.surface
                merged[-1] = Token(word, '名詞', word, a.reading + t.reading,
                                   a.start, t.end, a.has_reading and t.has_reading,
                                   '数' if numeric else '一般')
                continue
        merged.append(t)
    return merged


def _tokenize_janome(line):
    # Restoration and native spelling validation also call the raw parser.
    # Share only its immutable rows within the same analysis; restored POS
    # and lexical boundaries remain a separate result.
    cache=_NATIVE_TOKENIZATION_CACHE.get()
    if cache is None:return _tokenize_janome_uncached(line)
    rows=cache.get(line)
    if rows is None:
        result=_tokenize_janome_uncached(line)
        rows=tuple((t.surface,t.pos,t.base_form,t.reading,t.start,t.end,
                    t.has_reading,t.pos_sub,t.infl_form) for t in result)
        if len(cache)>=_TOKENIZATION_CACHE_LIMIT:cache.pop(next(iter(cache)))
        cache[line]=rows
    return [Token(*row) for row in rows]


def _tokenize_janome_uncached(line):
    from analysis_context import check_current_request
    check_current_request(frequent=True)
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


# 48-XX: 文語の準体法で、述語を含む節そのものを「を」で受けられる
# 知覚・認識・期待・感情の述語。語の直し先ではなく項の取り方の分類。
# GPT-6による設計/反証、2026-09-11。原形で共有し、活用形を列挙しない。
# これは十分条件の小集合であり、全ての準体法を判定する表ではない。
_CLAUSAL_OBJECT_BASES = frozenset("""
知る しる 悟る さとる 認める みとめる 覚える おぼえる 思う おもう
信じる しんじる 見る みる 聞く きく 感じる かんじる 感ずる かんずる
待つ まつ 望む のぞむ 願う ねがう 喜ぶ よろこぶ 恐れる おそれる
憂う うれう 惜しむ おしむ 悲しむ かなしむ 嫌う きらう
""".split())


@lru_cache(maxsize=4096)
def allows_bare_clause_object(following):
    """「風起こるを知る」のような、名詞化した節を受ける述語か。

    低頻度の名詞/動詞連接を誤分割とする前に、この用法を残す。
    未知語や別の文の知覚動詞を拾って保護範囲を広げない。
    """
    for part in tokenize(following):
        if not part.has_reading or part.pos == '記号':
            return False
        if part.pos == '動詞':
            return part.base_form in _CLAUSAL_OBJECT_BASES
        # 心から・静かに等の修飾を越えて最初の述語を見る。別の述語や
        # 文を越えて後方の知覚動詞まで探し続けることはしない。
        if part.pos not in ('名詞', '助詞', '副詞', '連体詞', '接頭詞'):
            return False
    return False


@lru_cache(maxsize=4096)
def native_excess_head(surface, reading):
    """48-AGP: native V-continuative / adjective stem before bound sugiru.

    Unknown/nominal interpretations remain undecided. A native adjective
    stem + nominalizing sa supplies another unchanged degree expression;
    its occurrence as a verb's irrealis homograph must not create an error.
    Source: https://www2.ninjal.ac.jp/vvlexicon/about.html
    Grammar review and counterexamples: GPT-6 Astra / 2026-09-15.
    """
    rows=[row for row in dictionary_inflections(surface) or () if row[3]==reading]
    if any((p.startswith('動詞,') and f=='連用形')
           or (p.startswith(('形容詞,','助動詞,')) and f=='ガル接続')
           or p.startswith('名詞,形容動詞語幹,') for p,f,b,rd in rows):return True
    if surface.endswith('さ') and reading.endswith('さ'):
        if any(p.startswith(('形容詞,','助動詞,')) and f=='ガル接続' and rd==reading[:-1]
               for p,f,b,rd in dictionary_inflections(surface[:-1]) or ()):return True
    if any(p.startswith(('名詞,','副詞,','感動詞,')) for p,f,b,rd in rows):return None
    if any(p.startswith(('動詞,','形容詞,','助動詞,')) for p,f,b,rd in rows):return False
    return None


@lru_cache(maxsize=1024)
def native_final_particle_tail(reading):
    """The entire reading is an attested sequence of sentence particles."""
    if not reading:return True
    reachable={0}
    for start in range(len(reading)):
        if start not in reachable:continue
        for end in range(start+1,len(reading)+1):
            piece=reading[start:end]
            if any(pos.startswith('助詞,終助詞,') and rd==piece
                   for pos,form,base,rd in dictionary_inflections(piece) or ()):
                reachable.add(end)
    return len(reading) in reachable


def _native_small_particle_tail(word,index,parts):
    # The source's actual native forms can explain a colloquial small よ.
    # A competing first POS label is not the only possible native reading.
    if katakana_to_hiragana(word[index])!='ょ':return False
    from pos_grammar import continuation_state,explain_kana_run
    # A final particle must explain its complete unchanged kana tail.
    # Proving only the left verb + よ would protect an interior typo while
    # silently discarding the remaining い (or another lexical fragment).
    tail_end=index+1
    while tail_end<len(word) and ('ぁ'<=word[tail_end]<='ゖ' or 'ァ'<=word[tail_end]<='ヶ' or word[tail_end]=='ー'):
        tail_end+=1
    # A final particle ends at an actual textual boundary. Stopping the
    # kana scan before a kanji/Latin word does not complete the utterance.
    if (tail_end<len(word) and not word[tail_end].isspace()
            and word[tail_end] not in '、。，,！？!?;；:：…‥()（）[]［］【】「」『』〈〉《》⇒→'):
        return False
    after=katakana_to_hiragana(word[index+1:tail_end])
    if not native_final_particle_tail(after):return False
    for j,t in enumerate(parts):
        if not (t.has_reading and t.start<=index-1<t.end==index):continue
        native=[row for row in dictionary_inflections(t.surface) or () if row[3]==t.reading]
        for pos,form,base,reading in native:
            if not pos.startswith(('動詞,自立,','形容詞,自立,')):continue
            state=continuation_state(form)
            if state is not None and explain_kana_run('よ',no_words=True,initial_state=state):return True
        if t.pos not in ('助詞','助動詞'):continue
        tail=katakana_to_hiragana(word[t.start:index]+'よ')
        if not j:
            if t.pos=='助動詞' and explain_kana_run(tail,no_words=True,initial_state='Bw'):return True
            continue
        previous=parts[j-1]
        if previous.end!=t.start:continue
        states={'Bw'} if previous.pos=='名詞' else set()
        for pos,form,base,reading in dictionary_inflections(previous.surface) or ():
            if reading!=previous.reading:continue
            state='Bw' if pos.startswith('名詞,') else continuation_state(form)
            if state is not None:states.add(state)
        if any(explain_kana_run(tail,no_words=True,initial_state=state) for state in states):return True
    return False


@lru_cache(maxsize=2048)
def colloquial_particle_normal_form(line):
    """Read a proved casual final よ without changing text or positions."""
    if not HAS_JANOME or 'ょ' not in line:return line
    parts=_tokenize_janome(line)
    changes=[i for i,c in enumerate(line) if c=='ょ'
             and _native_small_particle_tail(line,i,parts)]
    if not changes:return line
    chars=list(line)
    for i in changes:chars[i]='よ'
    return ''.join(chars)


@lru_cache(maxsize=2048)
def source_yoon_spans(text):
    """Malformed palatalized syllables in the original kana sequence.

    Ordinary/foreign yoon bases and native grammatical tails are retained.
    Neither an unknown word nor script mixing alone supplies this evidence.
    """
    import re
    from literal_examples import protected_ranges,overlaps
    protected=protected_ranges(text)
    out=[]
    for i,char in enumerate(text):
        if char not in 'ゃゅょ' or not i:continue
        prev=text[i-1]
        if ('ぁ'<=prev<='ゖ' or prev=='ー' or prev in '「『（(［[｛{【〔・　 \t'):continue
        if 'ァ'<=prev<='ヶ':
            normalized=chr(ord(prev)-0x60)
            if normalized in _YOON_BASES:continue
            if char=='ょ' and i+1<len(text) and text[i+1]=='ー':continue
        if not overlaps(i-1,i+1,protected):out.append((i-1,i+1))
    native_parts=None
    for m in re.finditer('[ぁ-ゖァ-ヶー]+',text):
        word=m.group()
        if not 2<=len(word)<=40:continue
        normalized=''.join(chr(ord(c)-0x60) if 'ァ'<=c<='ヶ' else c for c in word)
        if not any(c in 'ゃゅょ' for c in normalized):continue
        if overlaps(m.start(),m.end(),protected):continue
        if dictionary_inflections(word):continue
        for i,char in enumerate(normalized):
            if char not in 'ゃゅょ' or not 0<i<len(word):continue
            if normalized[i-1] in _YOON_BASES:continue
            if (normalized[i-1] in 'ゃゅょぁぃぅぇぉっー'
                    or char=='ょ' and i+1<len(word) and normalized[i+1]=='ー'):continue
            # Colloquial small よ after an actual auxiliary/final particle
            # is a grammatical tail, not a broken interior loanword syllable.
            if native_parts is None:native_parts=_tokenize_janome(text)
            if _native_small_particle_tail(text,m.start()+i,native_parts):continue
            out.append((m.start()+i-1,m.start()+i+1))
    return tuple(out)


def native_spelling_only(original,changed):
    """Prove literal kana-to-written projection, with no key or written-word edit."""
    if not original or not changed:return False
    parts=tokenize(changed)
    # The native tokenizer may read the first kanji of an attested noun as an
    # unrelated verb. Use the whole shipped noun and its attested reading.
    if (original and 'ぁ'<=original[0]<='ゖ' and len(parts)>1
            and parts[0].start==0 and parts[0].end==parts[1].start):
        from reading_segments import native_attested_prefix_noun_readings
        face=parts[0].surface+parts[1].surface
        for reading in native_attested_prefix_noun_readings(face):
            if original.startswith(reading) and (len(reading)==len(original)
                    and len(face)==len(changed) or len(reading)<len(original)
                    and len(face)<len(changed)
                    and native_spelling_only(original[len(reading):],changed[len(face):])):
                return True
    cursors={0}
    for token in parts:
        following=set()
        readings={rd for pos,form,base,rd in dictionary_inflections(token.surface) or ()
                  if pos.startswith(token.pos+',') and rd and all('ぁ'<=c<='ゖ' or c=='ー' for c in rd)} if token.has_reading else set()
        # The tokenizer already restores independently proved sahen
        # compounds as one noun. Preserve that same whole reading here;
        # dictionary_inflections deliberately remains native-only.
        if token.has_reading and token.pos=='名詞' and token.pos_sub=='サ変接続':
            compound_reading=native_sahen_compound_reading(token.surface)
            if compound_reading:readings.add(compound_reading)
        # Exact externally sourced nouns share the same reading proof;
        # the native dictionary API remains unchanged. No substring proof.
        from general_words import sourced_common_noun_evidence
        readings.update(entry['reading'] for entry in sourced_common_noun_evidence(token.surface)
                        if entry['pos'].startswith(token.pos+','+token.pos_sub.replace(':',',')+','))
        for cursor in cursors:
            if original.startswith(token.surface,cursor):following.add(cursor+len(token.surface))
            if any(not ('ぁ'<=c<='ゖ' or c=='ー') for c in token.surface):
                following.update(cursor+len(rd) for rd in readings if original.startswith(rd,cursor))
        if not following:return False
        cursors=following
    return len(original) in cursors
