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
                 'has_reading', 'pos_sub')

    def __init__(self, surface, pos, base_form, reading, start, end,
                 has_reading=True, pos_sub=''):
        self.surface = surface        # 表記
        self.pos = pos                # 品詞（大分類）
        self.pos_sub = pos_sub        # 品詞（細分類）。接尾・非自立の判定に使う
        self.base_form = base_form    # 原形（活用する語の場合）
        self.reading = reading        # 読み（ひらがなに直したもの）
        self.start = start            # 行内の開始位置
        self.end = end                # 行内の終了位置
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


def normalize_marks(text):
    """
    分離した濁点・半濁点を前の文字と合成する。

    かな入力では濁点が独立したキーなので、
    「たんこ゛」のように濁点だけが残ることがある。
    これを「たんご」に直してから照合できるようにする。

    「こ゜」のように合成できない組み合わせは、
    濁点キーの誤打なので取り除く。
    """
    if not text:
        return text
    out = []
    for ch in text:
        if ch in DAKUTEN_MARKS:
            if out:
                composed = _DAKUTEN_COMPOSE.get(out[-1])
                if composed:
                    out[-1] = composed
                    continue
            continue    # 合成できない濁点は誤打なので落とす
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
        pos_sub = parts[1] if len(parts) > 1 else ''

        reading = getattr(t, 'reading', '*')
        has_reading = (reading != '*' and reading != '')
        if not has_reading:
            reading = surface

        tokens.append(Token(
            surface=surface,
            pos=pos_major,
            base_form=t.base_form if t.base_form != '*' else surface,
            reading=katakana_to_hiragana(reading),
            start=start,
            end=end,
            has_reading=has_reading,
            pos_sub=pos_sub,
        ))
    return tokens


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
