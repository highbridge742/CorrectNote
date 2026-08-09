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
かな入力の誤字補正エンジン（再設計版）。

これまでの実装は補正を適用する経路が複数並列に存在し、
片方に安全策を入れても別の経路が同じ誤りを通してしまう構造だった。
その結果、正しい日本語（特に助詞・活用語尾）を壊す誤補正が頻発した。

この再設計版では次の原則を貫く:

  1. 入力をまず「触ってよい区間」と「絶対に触らない区間」に分ける。
     助詞・助動詞・活用語尾・数字・英字・記号は、
     一切の補正対象から機械的に除外する。

  2. 補正の判断経路は1つだけにする。
     複数の方法で候補を出して寄せ集めることをしない。

  3. 「直せるかもしれない」ではなく
     「明確に誤りだと言えるか」で採否を決める。
     判断がつかないものは直さない（取りこぼしを許容する）。

設計の詳細は SPEC.md を参照。
"""

import re

# ============================================================
# 文字種の判定
# ============================================================

def is_hiragana(ch):
    return '\u3041' <= ch <= '\u3096'


def is_katakana(ch):
    return '\u30a1' <= ch <= '\u30f6' or ch == 'ー'


def is_kanji(ch):
    return '\u4e00' <= ch <= '\u9fff'


def is_japanese_word_char(ch):
    """語を構成しうる文字か（かな・カタカナ・漢字）"""
    return is_hiragana(ch) or is_katakana(ch) or is_kanji(ch)


# ============================================================
# 絶対に触らない語
# ============================================================

# 助詞。1文字のものは特に誤補正の温床になるため、
# 単独で現れた場合は必ず保護する。
PARTICLES_1CHAR = set('はがをにでとものへやかばねよさなぞぜわ')

# 語の先頭に立てないかな。窓がこれで始まるのは、形態素解析が
# 語の途中で切った印（「にゅうりょく」→ に/ゅうりょく）。
_SMALL_KANA_HEADS = set('ぁぃぅぇぉゃゅょっゎー')

# 語の末尾に立てないかな。読みがこれで終わるのは活用の断片
# （つよかっ・打っ 等）で、独立した語として当ててはいけない。
_FRAGMENT_TAILS = set('っゃゅょぁぃぅぇぉ')

# 2文字以上の助詞・複合助詞
PARTICLES_MULTI = {
    'から', 'まで', 'より', 'ほど', 'など', 'なり', 'だけ', 'しか',
    'こそ', 'さえ', 'でも', 'ても', 'とも', 'のに', 'ので', 'けど',
    'けれど', 'けれども', 'ながら', 'つつ', 'たり', 'だり',
    'として', 'について', 'によって', 'により', 'における', 'に対して',
    'という', 'といった', 'のような', 'ように', 'ため', 'ゆえ',
    # 話し言葉の終助詞の組（させないわよ！ が させまいよ に
    # 化けた。2026-08-08）
    'わよ', 'わね', 'かしら',
    # 「だよねえ」のような言い回しの末尾（釣れないねえ が
    # 釣れないりえ に化けた。ねえ・ねぇ・よねえ が末尾で
    # 区切られる部分は対象外に、というユーザーの指示。2026-08-08）
    'ねえ', 'ねぇ', 'よね', 'よねえ',
}

# 助動詞・活用語尾。これで終わる語は語尾部分を保護する。
AUXILIARY_TAILS = (
    'です', 'ます', 'ました', 'ません', 'ませんでした', 'でした',
    'でしょう', 'ましょう', 'ください', 'ておく', 'ている', 'ていた',
    'ていない', 'てある', 'てしまう', 'ちゃう', 'られる', 'させる',
    'せる', 'れる', 'たい', 'たがる', 'そうだ', 'らしい', 'ようだ',
    'ない', 'なかった', 'なく', 'なくて', 'ず', 'ぬ',
    # サ変動詞・一段動詞の活用語尾。
    # これが無いと「にします」（に＋し＋ます）のような
    # 助詞と助動詞だけの並びを1語と誤認してしまう。
    'し', 'する', 'した', 'して', 'しない', 'します', 'しました',
    'すれ', 'せず', 'さ', 'き', 'け', 'こ',
    # 「〜てしまう」の活用形。「てしまう」だけでは
    # 「してしまいます」（し＋て＋しまいます）を説明できず、
    # 芯「してしま」が語彙の「ハテ島（はてじま）」に化けた（実機）。
    'しまう', 'しまい', 'しまいます', 'しまいました', 'しまった',
    'しまって',
    # 受身・可能・使役の助動詞の連用形。
    # 「れる」「られる」「せる」は原形が入っているが、
    # 「されません」「読まれません」のように **連用形＋ません** で
    # 現れることが多く、その形を取りこぼしていた。
    # これが無いと「されません」が「さ」＋「れません」に分かれた
    # とき、「れません」が助動詞だけの並びと判定されず、
    # 内容語とみなされて補正の対象になってしまう
    # （実機で「されません」に色が付くと報告された）。
    'れ', 'られ', 'せ', 'させ',
    # 「ある」「得る」の連用形。「ありえない」（あり＋え＋ない）が
    # 機能語の並びと判定されず、語彙の「あんない（案内）」に
    # 化けていた（実機で「ありえない」→「あんない」と壊れた）。
    'あり', 'ありえ',
    # 授受の補助動詞（〜てもらう・〜てくれる）。
    # 「消してもらっては」の らっては が芯に見えて けってい に
    # 化けた（実機・2026-08-08）。
    'もらう', 'もらっ', 'もらい', 'もらえ', 'てもらう', 'てもらっ',
    'くれ', 'くれる', 'くださっ',
    # 逆接の「ども」「ねど（も）」（劣らねども・行けども）。
    # 古い形だが日常でも見る。「劣らねども」の芯 らねど が
    # らんど に化けた（実機・2026-08-09）。
    'ども', 'ねど', 'ねども',
    # 丁寧の「まし（て/た）」。「おきまして」が机の分解で
    # おき＋ま＋して になり、芯 おきま が おやま に化けた
    # （実機・2026-08-09）。
    'まし', 'まして',
    # 意向形の「よう」（はじめよう・やめよう）。
    # 「はじめようか」の はじめよう が誤検知になった（2026-08-08）。
    'よう',
    # 仮定の「なら（ば）」（時ならば・弁当ならいい）。
    # 「ならばお土産」の芯 らばお が らじお に化けた（2026-08-09）。
    'なら', 'ならば',
    # 「のだ」の縮約（〜んだ・〜んです）。「でもいいんだ」の
    # いいんだ が説明できず いんじ に化けた（2026-08-08）。
    # ※単独の「ん」は加えない。「たん」（た＋ん）が機能語扱いに
    #   なると、たん子→単語 の修正が止まってしまう。
    'んだ', 'んです', 'んで',
    # 接尾の「〜がち」。ガチ過ぎ（俗語）の頭が機能語として
    # 説明できず 勝ち過ぎ に化けた（2026-08-08）。
    'がち',
    # 形容詞化の接尾（〜しやすい・〜しにくい）。これが無いと
    # 「起こりやすい語」の「すい語」が語の途中として認識されず、
    # 「英語」に化けた（実機・2026-08-08）。
    'やすい', 'やすく', 'にくい', 'にくく', 'づらい', 'がたい',
    # 「〜てみる」の活用形。「してみました」（し＋てみ＋ました）が
    # 機能語の並びと判定されず、「しくみ（仕組み）」に化けていた
    # （実機で 追記してみました→追記しくみました と壊れた）。
    'てみ', 'てみる', 'てみて', 'てみた', 'てみない', 'てみよう',
    'た', 'て', 'だ', 'で', 'に', 'く', 'き', 'い', 'う', 'る',
)

# 形式名詞・機能語。内容語のように見えるが、
# 補正対象にすると文の意味を壊すもの。
FUNCTION_NOUNS = {
    'こと', 'もの', 'とき', 'ところ', 'ほう', 'わけ', 'はず', 'つもり',
    'ため', 'うえ', 'うち', 'あいだ', 'かぎり', 'とおり', 'まま',
    # 「〜どころではない」の どころ（ところ の連濁）
    'どころ',
    'ひと', '人', '方', '事', '物', '時', '所',
}

# 指示語・代名詞
DEMONSTRATIVES = {
    # 連体詞「ある」（ある行・ある日）。この/その と同じ働きの
    # 機能語であり、「ある＋語」の並びに単語は無い
    # （実機で「ある行を」が、自動学習で紛れ込んだ「歩い」
    #   （歩く の連用形・count 4）に化けた。2026-08-08）。
    'ある',
    'これ', 'それ', 'あれ', 'どれ', 'この', 'その', 'あの', 'どの',
    'ここ', 'そこ', 'あそこ', 'どこ', 'こう', 'そう', 'ああ', 'どう',
    'こんな', 'そんな', 'あんな', 'どんな',
    'わたし', '私', 'あなた', 'かれ', '彼', 'かのじょ', '彼女',
    'われわれ', '私たち', 'みんな', 'みなさん',
    # 話し言葉の代名詞・疑問詞（セリフの検証で追加・2026-08-08。
    # わしらの縄張り→わからの、どうなんだ→どうおん と壊れた）。
    'わし', 'わしら', 'あたし', 'おまえ', 'なに', 'なん',
    # 疑問詞「いつ」「だれ」。「いつ得られましょうか」の いつ得 が
    # 塊として拾われ、いえ に化けた（実機・2026-08-09）。
    'いつ', 'だれ',
}

# 接続詞・副詞のうち、よく使われるもの
CONNECTIVES = {
    'そして', 'しかし', 'でも', 'また', 'さらに', 'つまり', 'ただし',
    'なお', 'ただ', 'もし', 'もしも', 'たとえ', 'なぜ', 'なぜなら',
    'だから', 'ですから', 'それで', 'すると', 'ところが', 'ちなみに',
    'とても', 'すごく', 'かなり', 'ぜんぜん', 'あまり', 'すこし',
    # 「すぐ上」が スコア に、「ちょっとした」が ちょっとと に
    # 化けた（実機・2026-08-08）。副詞＋語 の並びに単語は無い。
    'すぐ', 'ちょっと', 'もう',
    # 「まだ外に」が 間違いに、「まだ今の世」が 巻き込んの世 に
    # 化けた（実機・2026-08-09）。「ちょうどお粥」の ちょうど も
    # 同じ働きの副詞。
    'まだ', 'ちょうど', 'なおさら',
    # 「ついて来な」の「ついて」（つい＋て）が語の頭として拾われ、
    # 最適 に化けた（実機・2026-08-08）
    'つい',
    'もっと', 'ずっと', 'やはり', 'やっぱり', 'きっと', 'たぶん',
    'ぜひ', 'まったく', 'ほとんど', 'すべて', 'いつも', 'ときどき',
}

# 挨拶・慣用表現。ひらがなで書かれることが多く、
# 語彙に登録されていないと「未知の読み＝誤字」と誤判定されやすい。
SET_PHRASES = {
    'おはよう', 'おはようございます', 'こんにちは', 'こんばんは',
    'ありがとう', 'ありがとうございます', 'すみません', 'ごめんなさい',
    'おつかれ', 'おつかれさま', 'よろしく', 'おねがい', 'おねがいします',
    'いただきます', 'ごちそうさま', 'おやすみ', 'さようなら',
    'そのため', 'そのほか', 'そのうえ', 'そのまま', 'そのとき',
    'あるいは', 'および', 'ならびに', 'したがって', 'ただし',
    'いっぽう', 'たとえば', 'つまり', 'なぜなら', 'ちなみに',
    'とりあえず', 'いちおう', 'そもそも', 'もちろん', 'たしかに',
    'なるほど', 'ところで', 'それでは', 'それから', 'それとも',
    'いずれ', 'いつか', 'いくつ', 'いくら', 'どれくらい',
}

# 上記すべてをまとめた「触らない語」集合
PROTECTED_WORDS = (
    PARTICLES_MULTI | FUNCTION_NOUNS | DEMONSTRATIVES | CONNECTIVES
    | SET_PHRASES
)


def is_protected_word(text):
    """
    この語は補正対象から完全に除外すべきか。

    助詞・助動詞・形式名詞・指示語・接続詞など、
    文の骨組みを作る語は、たとえ語彙ストアに
    似た読みの語があっても絶対に書き換えない。
    """
    if not text:
        return True
    if text in PROTECTED_WORDS:
        return True
    if len(text) == 1 and text in PARTICLES_1CHAR:
        return True
    return False


def has_protected_tail(text):
    """
    末尾が助動詞・活用語尾かどうか。

    「引き下げました」の「ました」、「見えにくいです」の「です」など、
    語尾を巻き込んだ補正は文を壊すため、
    語尾を持つ語は語幹だけを補正対象にする（あるいは触らない）。
    """
    for tail in AUXILIARY_TAILS:
        if len(text) > len(tail) and text.endswith(tail):
            return True
    return False


def split_protected_tail(text):
    """
    語を (語幹, 保護すべき語尾) に分ける。

    最も長い語尾を優先して切り出す。
    切り出せない場合は (text, '') を返す。
    """
    if not text:
        return text, ''
    for tail in sorted(AUXILIARY_TAILS, key=len, reverse=True):
        if len(text) > len(tail) and text.endswith(tail):
            return text[:-len(tail)], tail
    return text, ''


# ============================================================
# 触ってよい区間の抽出
# ============================================================

def contains_non_japanese(text):
    """数字・英字・記号を含むか。含む語は補正対象外にする。"""
    for ch in text:
        if not is_japanese_word_char(ch):
            return True
    return False


def find_hiragana_runs(line, min_len=4, allow_adjacent_kanji=False):
    """
    ひらがなだけが連続する部分を、区切らずにまとまりとして返す。

    かな入力の誤字は、まさにこのひらがな連続部分に現れる。
    ところが形態素解析は、誤字を含むひらがな列を正しく区切れない
    （「もじにうりょく」を「も/じ/に/うりょく」のように壊してしまう）。
    そのため、ひらがな連続部分については形態素解析の結果を使わず、
    まとまり全体をそのまま補正の候補にする。

    min_len: これより短い連続は対象にしない（助詞の連なりと区別できない）

    allow_adjacent_kanji:
        False のときは、前後に漢字・カタカナが隣接する連続を
        対象から外す（送り仮名・複合語の一部を壊さないため）。

        True のときは、それらも対象にする。実際の日本語は
        漢字とひらがなが交互に現れるのが普通なので、隣接を理由に
        一律で外すと「単語のつあがり」「かな打ちでのほらい」の
        ように、**大半の誤字が補正対象にすらならない**
        （実機で多数報告された）。
        ただし送り仮名を巻き込む危険があるため、
        呼び出し側で探索を厳しくすること。

    戻り値: [(開始, 終了, 文字列), ...]
    """
    def _is_run_char(ch):
        # 長音符「ー」はひらがな語の一部として使われる
        # （「きーぼーど」「こーひー」など）。
        # これを区切りとして扱うと語が分断され、
        # 「きーぼーそ」のような誤字を直せなくなる。
        return is_hiragana(ch) or ch == 'ー'

    runs = []
    n = len(line)
    i = 0
    while i < n:
        # 長音符だけで始まる範囲は語ではないので飛ばす
        if not is_hiragana(line[i]):
            i += 1
            continue
        j = i
        while j < n and _is_run_char(line[j]):
            j += 1
        run = line[i:j]
        if allow_adjacent_kanji:
            # 送り仮名の保護は explain_cores（窓の切り出し）側で行う
            prev_ok = next_ok = True
        else:
            # 前後に漢字・カタカナが隣接している場合は、
            # 送り仮名や複合語の一部の可能性が高いので対象外
            prev_ok = (i == 0) or not is_japanese_word_char(line[i - 1])
            next_ok = (j >= n) or not is_japanese_word_char(line[j])
        if len(run) >= min_len and prev_ok and next_ok:
            runs.append((i, j, run))
        i = j
    return runs


# 直前の漢字に付く送り仮名になりやすい1文字（動詞の連用形語尾）。
# 「打ち」「切り」「読み」「選び」のように、漢字＋この1文字で
# 連用形になる。AUXILIARY_TAILS に混ぜると、末尾の機能語判定
# （_trailing_functional_len）や「機能語だけの並び」の判定まで
# 広がって効きすぎるので、**先頭の送り仮名を剥がすときだけ**
# 使う専用の集合として分けておく。
# 「す」は五段動詞の終止形の送り（話す・出す・渡す）。これが無いと
# 「話す＋たびに」の たびに が「すたび」を芯にされ、すみび に化けた
# （実機・2026-08-09）。「む」も同じ（包む・読む・飲む。
# 「包むどころ」の むどころ が みどころ に化けた）。
OKURIGANA_HEADS = set('ちりみにびぎじひえめねべげせてれすむ')

# 古い言い回しだが日常でも時折見る表現。janome のビルドによっては
# 読みが取れず（以・往 の単漢字読みが無い）「読める」判定に乗らない
# ため、表記そのもので守る（実機で 以て→足音り・往って→応じて と
# 壊れた・2026-08-09。方針: 古語はほとんど対応しないが、日常の中で
# 時折見るものだけは壊さない）。
PROTECTED_CLASSICAL = (
    '以て', '以って', '往って', '往った', '往く', '曰く', '即ち',
    '故に', '依って', '拠って',
)


def _skip_leading_okurigana(run):
    """
    ひらがな連続の先頭から、送り仮名・助詞・助動詞にあたる部分の
    長さを返す（そこまでは補正の対象にしない）。

    直前の漢字と一体になっている活用語尾を守るための処理。
    前から順に、既知の活用語尾・助詞を最長一致で取り除いていき、
    取り除けなくなった位置を返す。

    ただし全部を取り除いてしまう場合（＝助詞・助動詞だけの並び）は
    0 を返す。その場合は _is_all_auxiliary 側で対象外と判定される。
    """
    tails = sorted(set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
                   | set(PARTICLES_1CHAR) | OKURIGANA_HEADS,
                   key=len, reverse=True)
    pos = 0
    while pos < len(run):
        for tail in tails:
            if run.startswith(tail, pos):
                pos += len(tail)
                break
        else:
            break
    if pos >= len(run):
        return 0
    return pos


def token_windows(run, tokenize_fn, min_len=3, max_len=8):
    """
    形態素解析の分割から、誤字が潜んでいそうな窓を切り出す。

    誤字を含むひらがな列を janome に掛けると、
    **1〜2文字の短い断片がぱらぱらと連続する**形に割れる
    （「たんほ」→ たん/ほ、「ちでのほらい」→ ち/で/の/ほ/らい 等。
      実機の観察から得られた知見）。
    正しい文は「まま（名詞）＋で（助詞）＋よい（形容詞）」のように、
    読みの確定したまとまった語に割れる。

    そこで「短い断片（2文字以下）または読みの取れないトークン」が
    連続し、その中に**読みの取れないトークンが1つ以上含まれる**
    範囲を窓とする。全部が読める短断片だけ（で＋よい 等）の並びは
    正しい文なので対象にしない。

    語彙ストアに依存しない（explain_cores と違い、実機の巨大な
    辞書語彙で2文字断片が既知語にヒットして窓が消える、という
    問題が起きない）。

    戻り値: [(窓の開始, 窓の終了), ...]  runの中の相対位置
    """
    try:
        toks = tokenize_fn(run)
    except Exception:
        return []
    if not toks:
        return []

    def _fragile(tok):
        surface, _pos, _reading, _s, _e, known = tok
        if not all(is_hiragana(c) or c == 'ー' for c in surface):
            return False
        if not known:
            return True        # 読みが取れない＝壊れている可能性
        return len(surface) <= 2   # 読めても短い断片は連結して見る

    windows = []
    i = 0
    n = len(toks)
    while i < n:
        if not _fragile(toks[i]):
            i += 1
            continue
        j = i
        has_unknown = False
        while j < n and _fragile(toks[j]):
            if not toks[j][5]:
                has_unknown = True
            j += 1
        if has_unknown:
            w_start = toks[i][3]
            w_end = toks[j - 1][4]
            # 両端の、読みが確定している1文字の助詞は窓から外す
            # （「のつあがり」の「の」等。次の語との境界であって
            #   壊れた部分ではない）
            while (i < j and toks[i][5] and len(toks[i][0]) == 1
                   and toks[i][0] in PARTICLES_1CHAR):
                i += 1
                if i < j:
                    w_start = toks[i][3]
            while (j - 1 > i and toks[j - 1][5]
                   and len(toks[j - 1][0]) == 1
                   and toks[j - 1][0] in PARTICLES_1CHAR):
                j -= 1
                w_end = toks[j - 1][4]
            if min_len <= w_end - w_start <= max_len:
                windows.append((w_start, w_end))
        i = j
    return windows


def explain_cores(run, store, min_len=3, max_len=8, after_kanji=False):
    """
    ひらがな連続の中から、誤字が潜んでいそうな「窓」を切り出す。

    連続を「語彙にある語（count>=2）」「機能語（助詞・助動詞・
    活用語尾・指示語）」「どちらでも説明できない文字（スキップ）」に
    分解し、**両端の機能語を取り除いた内部にスキップが残る場合**、
    その内部全体をひとつの窓として返す。

    「単語のつあがり」の「のつあがり」なら、先頭の「の」（助詞）を
    除いた「つあがり」が窓になる（「つ」「あ」が説明できず、間の
    「が」だけでは分断しない）。
    「知っている」の「っている」は全部が機能語なので窓は無い
    （＝触ってはいけない）。

    前回、連続全体をまるごと探索して「知っている→知せってい」の
    ような送り仮名破壊を起こした反省から、探索対象をこの窓だけに
    絞り、しかも窓の補正は「既知の語に確実に一致した場合だけ」に
    制限する（呼び出し側）。

    戻り値: [(窓の開始, 窓の終了), ...]  runの中の相対位置
    """
    n = len(run)
    # 位置 i から始められる説明の候補: [(長さ, 種別)] 種別: 'word'/'func'
    starts = {}
    for i in range(n):
        opts = []
        for ln in range(2, min(13, n - i + 1)):
            frag = run[i:i + ln]
            try:
                if any(e['count'] >= 2 for e in store.lookup(frag)):
                    opts.append((ln, 'word'))
            except Exception:
                pass
        for tail in AUXILIARY_TAILS:
            if run.startswith(tail, i):
                opts.append((len(tail), 'func'))
        for prt in PARTICLES_MULTI:
            if run.startswith(prt, i):
                opts.append((len(prt), 'func'))
        if run[i] in PARTICLES_1CHAR:
            opts.append((1, 'func'))
        for dem in DEMONSTRATIVES:
            if run.startswith(dem, i):
                opts.append((len(dem), 'func'))
        # 形式名詞（まま・ほう・こと 等）。
        # 「色付きのままでよい」の「まま」が説明できず、正しい文に
        # 色が付いてしまった（実機で報告された誤検知）。
        for fnoun in FUNCTION_NOUNS:
            if run.startswith(fnoun, i):
                opts.append((len(fnoun), 'func'))
        # ごく基本的な形容詞。「したほうがよい」の「よい」が
        # 説明できず、同じく誤検知になっていた。
        for adj in ('よい', 'いい', 'ない'):
            if run.startswith(adj, i):
                opts.append((len(adj), 'func'))
        starts[i] = opts

    # DP: スキップ文字数が最小になる分解を選ぶ
    INF = 10 ** 9
    best = [INF] * (n + 1)
    best[0] = 0
    choice = [None] * (n + 1)   # (前の位置, 種別)
    for i in range(n):
        if best[i] == INF:
            continue
        for ln, kind in starts[i]:
            if best[i] < best[i + ln]:
                best[i + ln] = best[i]
                choice[i + ln] = (i, kind)
        if best[i] + 1 < best[i + 1]:
            best[i + 1] = best[i] + 1
            choice[i + 1] = (i, 'skip')

    # 経路を戻して分解を得る
    segs = []
    pos = n
    while pos > 0 and choice[pos] is not None:
        prev, kind = choice[pos]
        segs.append((prev, pos, kind))
        pos = prev
    segs.reverse()

    if not any(k == 'skip' for _s, _e, k in segs):
        return []

    _trace('分解', f'{run!r} → '
                   f'{[(run[a2:b2], k) for a2, b2, k in segs]}')

    # 両端の機能語を取り除いた内部を窓にする。
    #
    # ただし **先頭を剥がすのは、直前が漢字のときだけ** にする。
    # 先頭の機能語は「直前の漢字に付く送り仮名」を想定した処理で、
    # 直前に漢字が無ければ、そこは語の先頭である。
    # 「たああんごの」の「た」は活用語尾として説明が付いてしまうが、
    # 実際には「たんご」の頭であり、剥がすと窓が「ああんご」になる。
    # そのまま直すと「た」が取り残されて **たたんごの** という
    # 壊れ方をする（実機で発生）。
    lo, hi = 0, len(segs)
    if after_kanji:
        while lo < hi and segs[lo][2] == 'func':
            lo += 1
    while hi > lo and segs[hi - 1][2] == 'func':
        hi -= 1
    if lo >= hi:
        return []
    inner = segs[lo:hi]
    if not any(k == 'skip' for _s, _e, k in inner):
        return []
    w_start, w_end = inner[0][0], inner[-1][1]

    # 窓が短すぎるときは、隣の機能語を取り込んで広げる。
    #
    # 「たんほの」は「た」が活用語尾、「の」が助詞として説明できる
    # ため、スキップは「んほ」の2文字だけになる。しかし実際の誤字は
    # 「たんご」の「ご」を「ほ」と打ったもので、「た」は語の一部。
    # 説明できてしまった機能語が、実は壊れた語の一部だったという
    # このケースを拾うため、窓が min_len に届かないときは
    # 前（送り仮名・語頭は前に付くので前を優先）→後ろの順で
    # 隣の機能語を1つずつ取り込む。
    # 拡張するのは、説明できない文字が2文字以上あるときだけ。
    # 1文字だけなら、それは「っ」（促音）や動詞の活用の一部である
    # 可能性が高く、窓にすると正しい文（知っている・やらない）に
    # まで色が付いてしまう。
    total_skips = sum(e2 - s2 for s2, e2, k in segs if k == 'skip')
    if (w_end - w_start) < min_len and total_skips < 2:
        return []
    lo2, hi2 = lo, hi
    while (w_end - w_start) < min_len and (lo2 > 0 or hi2 < len(segs)):
        if lo2 > 0:
            lo2 -= 1
            w_start = segs[lo2][0]
        else:
            hi2 += 1
            w_end = segs[hi2 - 1][1]
    if not (min_len <= w_end - w_start <= max_len):
        return []
    return [(w_start, w_end)]


# --- ローマ字入力者向けの照合 ---
# ローマ字で打つ人の打ち間違いは、かなではなく**ローマ字の文字単位**で
# 起きる（h の隣の g を押して「ほ」が「ご」になる等）。
# かなキー配列の隣接では捉えられないため、かなをローマ字に開き、
# QWERTY の隣接で照合し直す。

_KANA_TO_ROMAJI = {
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'si', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'ti', 'つ': 'tu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'hu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
    'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'を': 'wo', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'zi', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'di', 'づ': 'du', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ゃ': 'ya', 'ゅ': 'yu', 'ょ': 'yo', 'ぁ': 'a', 'ぃ': 'i',
    'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o', 'っ': 't', 'ー': '-',
}

_QWERTY_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')


def _qwerty_adjacent(a, b):
    """QWERTY 配列で a と b が隣り合うキーか。"""
    pos = {}
    for row_i, row in enumerate(_QWERTY_ROWS):
        for col_i, ch in enumerate(row):
            pos[ch] = (row_i, col_i)
    pa, pb = pos.get(a), pos.get(b)
    if pa is None or pb is None:
        return False
    return abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1 and a != b


def kana_to_romaji(kana):
    return ''.join(_KANA_TO_ROMAJI.get(c, '?') for c in kana)


def _romaji_distance(a, b):
    """ローマ字列どうしの重み付き編集距離（QWERTY隣接の置換を安く）。"""
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 99.0
    dp = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        dp[i][0] = i * 0.9
    for j in range(lb + 1):
        dp[0][j] = j * 0.9
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                sub = 0.0
            elif _qwerty_adjacent(a[i - 1], b[j - 1]):
                sub = 0.5
            else:
                sub = 1.2
            dp[i][j] = min(dp[i - 1][j - 1] + sub,
                           dp[i - 1][j] + 0.9,
                           dp[i][j - 1] + 0.9)
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 0.6)
    return dp[la][lb]


def romaji_window_match(window, store, max_dist=0.6, min_reading_len=3):
    """
    窓のかな列を、ローマ字の打ち間違いとして語彙の読みと照合する。

    QWERTY で隣のキーを押した誤り（h→g で「ほ」→「ご」等）を、
    かな1文字の置換として捉え直す。確実な一致（唯一で距離が小さい）
    のときだけ読みを返し、曖昧なら None。
    """
    w_rom = kana_to_romaji(window)
    if '?' in w_rom:
        return None
    hits = []
    for reading in store.all_readings():
        if not (min_reading_len <= len(reading) <= len(window) + 1):
            continue
        if abs(len(reading) - len(window)) > 1:
            continue
        if not any(e['count'] >= 2 for e in store.lookup(reading)):
            continue
        r_rom = kana_to_romaji(reading)
        if '?' in r_rom:
            continue
        d = _romaji_distance(w_rom, r_rom)
        if d <= max_dist + 0.4:
            hits.append((d, reading))
    hits.sort()
    if not hits:
        return None
    best_d, best_r = hits[0]
    if best_d > max_dist or best_r == window:
        return None
    if len(hits) > 1 and hits[1][0] - best_d < 0.4:
        return None    # 曖昧なら選ばない
    return best_r


# 人名につく敬称・接尾語。これらの直前にある語は人名の可能性が高く、
# 語彙に無くて当然なので補正対象から外す。
HONORIFICS = ('さん', 'さま', '様', 'くん', '君', 'ちゃん', '氏', '先生',
              'せんせい', 'せんぱい', '先輩', 'こうはい', '後輩')


def _is_before_honorific(line, end):
    """
    この位置の直後に敬称が続くか。

    「イブキさん」の「イブキ」のように、敬称の前にある語は
    人名である可能性が高い。人名は辞書に無くて当然なので、
    「知らない語＝誤字」と判断して別の語に変えてしまうと
    必ず誤りになる（「イブキさん」→「自分さん」）。
    """
    rest = line[end:]
    return rest.startswith(HONORIFICS)


def _is_fragment_of_protected(line, start, end):
    """
    この区間が、保護すべき語の一部を切り出しただけではないかを調べる。

    形態素解析が不正確だと「もしそのことなら」を
    「もし/そ/の/こと/なら」ではなく
    「も/しそ/の/こ/と/なら」のように誤って区切ることがある。
    そのまま断片を補正すると「しそ」→「外」のような破壊が起きる。

    区間の前後に文字を足した形が保護語に一致するなら、
    それは分割の失敗とみなして補正対象から外す。
    """
    for pad_left in range(0, 3):
        for pad_right in range(0, 3):
            s = max(0, start - pad_left)
            e = min(len(line), end + pad_right)
            if s == start and e == end:
                continue
            piece = line[s:e]
            if piece in PROTECTED_WORDS:
                return True
    return False


def find_editable_spans(line, tokens):
    """
    1行のテキストから「補正してよい区間」だけを抽出する。

    tokens は形態素解析の結果。各要素は
    (表記, 品詞, 読み, 開始位置, 終了位置, 読みが確定しているか)。

    次の条件をすべて満たす区間だけを対象にする:
      - 助詞・助動詞・記号ではない
      - 保護対象の語（形式名詞・指示語・接続詞等）ではない
      - 数字・英字・記号を含まない
      - 2文字以上ある（1文字の語は情報が少なすぎて誤爆しやすい）
      - 保護語を分割してできた断片ではない

    戻り値: [(開始, 終了, 表記, 読み), ...]
    """
    spans = []
    for surface, pos, reading, start, end, has_reading in tokens:
        if not surface:
            continue
        # 品詞（大分類）による除外
        pos_major = pos.split(':')[0] if pos else ''
        pos_sub = pos.split(':')[1] if ':' in pos else ''
        if pos_major in ('助詞', '助動詞', '記号', '接続詞', '感動詞',
                         'フィラー', '連体詞'):
            continue
        # 品詞（細分類）による除外。
        # 「〜向け」「〜寄り」「〜か月」「〜済み」のように、
        # 単独では意味を成さず前の語にくっついて使う語は、
        # 独立した語として補正すると必ず文を壊す。
        # 大分類だけを見ているとこれらが「名詞」として
        # 補正対象に入ってしまうため、細分類で確実に除外する。
        if pos_sub in ('接尾', '非自立', '接続詞的', '代名詞', '数',
                       '特殊', '副詞可能', 'ナイ形容詞語幹'):
            continue
        # 保護対象の語
        if is_protected_word(surface):
            continue
        # 数字・英字・記号を含む
        if contains_non_japanese(surface):
            continue
        # 短すぎる語
        if len(surface) < 2:
            continue
        # カタカナ語は原則として触らない。
        # 固有名詞（人名・作品名・キャラクター名）、俗語、専門用語、
        # 略語が大半を占めており、辞書に無くて当然の語ばかりなので、
        # 「辞書に無い＝誤字」と判断すると必ず誤る
        # （「ネイル」→「直る」、「ナルト」→「習い」、
        #   「スタン」→「破綻」のような破壊が起きていた）。
        # カタカナの打ち間違いは、かな入力では
        # ひらがなで打ってから変換するため、この経路には現れない。
        if any(is_katakana(c) for c in surface):
            continue
        # 読みが全く取れないものは判断材料が無いので触らない
        if not reading:
            continue
        # 保護語を切り損ねた断片
        if _is_fragment_of_protected(line, start, end):
            continue
        # 敬称の直前＝人名の可能性が高いので触らない
        if _is_before_honorific(line, end):
            continue
        # has_reading は「形態素解析が辞書から読みを引けたか」。
        # 引けた語は実在する語として正しく書けている可能性が高く、
        # 引けなかった語は辞書に無い＝誤字の可能性がある。
        # この違いは補正の判断で使うので、そのまま持ち回す。
        spans.append((start, end, surface, reading, bool(has_reading)))
    return spans


# ============================================================
# 補正の判断（唯一の経路）
# ============================================================

# 補正を採用する条件の強さ。数字が小さいほど強い証拠。
EVIDENCE_CONTEXT = 0      # 同じメモ内に正しい表記がある（最強）
EVIDENCE_VECTOR = 1       # 同音の複数候補から、文脈ベクトルで明確に選べた
EVIDENCE_EXACT = 2        # 読みが完全一致し、使用実績のある語がある
EVIDENCE_NEAR = 3         # 読みが1文字違いで、使用実績のある語がある
EVIDENCE_NONE = 99        # 証拠なし（採用しない）


def is_plausible_typo(typed, cost, edits):
    """
    その訂正が「打ち間違いとして自然か」を判定する。

    判断材料は2つ:
      - 訂正1文字あたりのコスト（隣接キーなら約1.0）
        遠いキーへの置き換えは打ち間違いとして不自然。
      - 語の長さに対する訂正の割合
        長い語なら3箇所間違えることもあるが、
        短い語で何箇所も違うなら、それは別の語である可能性が高い。

    「もじにゅうりょく」（8文字）の3箇所訂正は許容するが、
    「ぱそこん」（4文字）の3箇所訂正は認めない、という具合。
    """
    if edits <= 0:
        return True
    avg_cost = cost / edits
    # 遠いキーへの置き換えは、何箇所であっても打ち間違いとみなさない。
    # ただし1箇所だけの訂正なら、濁点・半濁点の有無の違い
    # （「そ」と「ど」は同じキーで濁点だけが違う）も含めて
    # 自然な打ち間違いなので、やや緩めに見る。
    limit_cost = 1.5 if edits == 1 else 1.35
    if avg_cost > limit_cost:
        return False
    n = len(typed)
    if n <= 0:
        return False
    # 訂正できる箇所数の上限を語の長さから決める。
    # 3文字以下: 1箇所 / 4〜5文字: 2箇所 / 6文字以上: 3箇所まで
    if n <= 3:
        limit = 1
    elif n <= 5:
        limit = 2
    else:
        limit = 3
    if edits > limit:
        return False
    # 訂正箇所が多いときは、1箇所あたりのコストにも厳しくする。
    # 隣接キーの押し間違いが重なった場合だけを通す。
    if edits >= 3 and avg_cost > 1.1:
        return False
    return True


def _is_all_functional(run):
    """
    その並びが、助詞・活用語尾・指示語だけで説明が付くか。

    「かったのかな」は かった＋の＋かな と、全部が機能語で説明できる。
    こういう並びは「単語として成立していない」のではなく、
    **単語がそもそも無い**（前の漢字に付く送り仮名と助詞）だけなので、
    語彙と突き合わせて似た語に置き換えてはいけない
    （実機で「言えば良かったのかな」→「言えば良かたかな」という
      破壊が出た。芯の切り出しがこれを素通ししていた）。

    前から最長一致で食べる方式だと、短い断片を先に取ったせいで
    その先が説明できなくなることがある（「か」を取ってしまって
    「ったのかな」で行き詰まる）。どの区切り方でもよいので
    最後まで説明が付くかを見る、という形にする。

    促音「っ」は単独では機能語ではないが、活用語尾の中に現れる
    （かった・行った）。語尾の一覧に個々の活用形を全部並べる
    代わりに、ここでだけ繋ぎとして許す。
    """
    # 形式名詞（まま・こと・ほう…）も機能語として数える。
    # 「のままでよい」は まま＋で＋よい と説明が付く。これを
    # 単語として扱うと「うまでよい」のように壊れる（実際に壊れた）。
    # 副詞（すぐ・ちょっと・とても…）も機能語として数える
    # （「すぐ上」「ちょっとした」の保護。2026-08-08）。
    tails = (set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
             | set(PARTICLES_1CHAR) | set(DEMONSTRATIVES)
             | set(CONNECTIVES) | set(FUNCTION_NOUNS)
             # ごく基本的な形容詞（explain_cores と同じ扱い。
             # 「でもいいんだ」の いい が説明できず でもいんじ に
             # 化けた。2026-08-08）と、敬語の接頭「お」
             # （お前・お願い。「なんだお」＝なん＋だ＋お が
             # 説明できず ねんだい に化けた。2026-08-08）
             | {'っ', 'よい', 'いい', 'お'})
    n = len(run)
    # reach[i] = 先頭から i 文字目までを機能語だけで説明できるか
    reach = [False] * (n + 1)
    reach[0] = True
    for i in range(n):
        if not reach[i]:
            continue
        for tail in tails:
            if run.startswith(tail, i):
                reach[i + len(tail)] = True
    return reach[n]


# 接尾の形容詞・様態。単独の内容語ではなく、動詞の連用形に付く。
# 「こりやすい」（起こりやすい の断片）を守るのに要る。
_SUFFIX_TAILS = ('やすい', 'やすく', 'にくい', 'にくく',
                 'がち', 'すぎる', 'すぎ', 'そう')


def _okurigana_functional_only(run, any_head=False):
    """
    「送り仮名＋機能語」だけで最後まで説明が付くか。

    「見えません」の「えません」、「取り違えてました」の
    「えてました」は、え（送り仮名）＋ません／て＋ました であり、
    そこに独立した単語は無い。これを語彙と突き合わせると
    「えません」→「えびせん」のような破壊が起きる（実機で発生）。

    _is_all_functional との違いは、**先頭だけ** 送り仮名を許すこと。
    先頭以外で許すと「ほらい」（補正の一部）のような壊れた列まで
    説明が付いてしまうので、位置に限る。判定は _is_all_functional と
    同じ経路探索（最長一致で行き詰まる並びを取りこぼさない）。

    any_head: 直前が漢字だと分かっている窓に使う。送り仮名は
        どのかなにもなりうる（づかれず＝気づく、すときに＝足す、
        んでいた＝死んでいた、こりやすい＝起こりやすい）ので、
        OKURIGANA_HEADS に限らず先頭の1〜2文字を送り仮名として
        許す。実機ではこの形の破壊（→つかれた／いっきに／
        えでぃった）が最も多かった。
        独立した連続には使わない（「たああんご」の語頭まで
        送り仮名扱いになってしまうため）。
    """
    n = len(run)
    if n == 0:
        return False
    tails = (set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
             | set(PARTICLES_1CHAR) | set(DEMONSTRATIVES)
             | set(CONNECTIVES)
             | set(FUNCTION_NOUNS) | set(_SUFFIX_TAILS) | {'っ'})
    reach = [False] * (n + 1)
    reach[0] = True
    if run[0] in OKURIGANA_HEADS or (any_head and is_hiragana(run[0])):
        reach[1] = True
    if any_head and n >= 2 and is_hiragana(run[0]) and is_hiragana(run[1]):
        reach[2] = True
    for i in range(n):
        if not reach[i]:
            continue
        for tail in tails:
            if run.startswith(tail, i):
                reach[i + len(tail)] = True
    return reach[n]


def _leading_particle_len(run):
    """
    ひらがな連続の先頭にある助詞の長さを返す。

    剥がすのは **助詞だけ** にする。_skip_leading_okurigana は
    活用語尾も剥がすが、それを窓の先頭に当てはめると
    「たああんご」の「た」まで削れてしまう（語の先頭に来る
    かなと、直前の漢字に付く送り仮名は、字面では区別が付かない）。
    助詞（の・を・が…）なら語の先頭に単独で立つことはまず無い。
    """
    tails = sorted(set(PARTICLES_MULTI) | set(PARTICLES_1CHAR),
                   key=len, reverse=True)
    pos = 0
    while pos < len(run):
        for tail in tails:
            if run.startswith(tail, pos):
                pos += len(tail)
                break
        else:
            break
    if pos >= len(run):
        return 0
    return pos


# ============================================================
# 補正の判断を記録する仕組み（診断用）
# ============================================================
# 「なぜ直らないのか」を調べるとき、診断スクリプトの中で関門を
# 書き写して再現すると、**書き写し漏れた関門が見えない**。
# 実機で直らない原因が edge_word の関門だったのに、診断が
# その関門を持っていなかったために特定が1往復遅れた
# （SPEC.md「過去の失敗と学び」参照）。
#
# 同じ失敗を繰り返さないよう、判断そのものに記録を仕込む。
# TRACE が None のときは何もしない（通常の動作に影響しない）。
TRACE = None


def trace_on():
    """記録を始める。診断スクリプトから呼ぶ。"""
    global TRACE
    TRACE = []
    return TRACE


def trace_off():
    global TRACE
    TRACE = None


# 叫び声・合図の直後に付く記号。
# 短いかなの並びがこの記号で終わるなら、それは掛け声
# （おたから！・ねこだまし！・きゅっ♡）であって、
# 語彙と突き合わせて直す対象ではない。
# ※行ごと・セリフごと対象外にはしない。セリフではない括弧書きも
#   あるし、セリフの中の普通の言い回し・文章は補正対象、という
#   方針（2026-08-08 に修正合意）。対象外にするのは
#   叫び声に近い合図のような語だけ。
_SHOUT_MARKS = '！!？?♡…‥'


def _followed_by_shout_mark(line, end):
    """かなの連続の直後が ！？♡ か。"""
    return end < len(line) and line[end] in _SHOUT_MARKS


def _is_expressive_kana_run(run):
    """
    伸ばし言葉・擬音の形をした、かなの連続か。

    - 長音「ー」を含むひらがなの並びは、伸ばして書いた話し言葉
      （うれしー・きゅーん・みかーん）。末尾がーの語の誤検知が
      多い、というユーザーの指摘（2026-08-08）に基づく。
      辞書の語と一致しないのは当然で、直す対象ではない。
    - 小書きのかな（ぁぃぅぇぉ）で終わるのも感嘆の書き方
      （あいたぁ・おいでぇ）。
    - 同じ並びの繰り返し（はわはわ・わうわう・うほうほ）は擬音。
    """
    if not run:
        return False
    # 長音「ー」が1つだけの並びは、伸ばして書いた話し言葉
    # （うれしー・みかーん・もしもーし・すりーぷ）。
    # ーが2つ以上の並びは、カタカナ語をひらがなで打った可能性が
    # 高い（きーぼーそ→きーぼーど）ので対象に残す。そちらは
    # 読みの照合側の「ーの位置が変わる訂正はしない」が守る。
    if run.count('ー') == 1:
        return True
    if run.endswith('ー') or run.endswith('ーん') or run.endswith('ーっ'):
        return True
    # 末尾の促音（かくごっ・きゃーっ）も掛け声の書き方
    if run[-1] in 'ぁぃぅぇぉっ':
        return True
    # 小書きの母音（ぁぃぅぇぉ）はどの位置にあっても感嘆・擬音
    # （ふぇぇん・あいたぁ）。拗音（ゃゅょ）は普通の語にも
    # 現れるので対象にしない。
    if any(c in 'ぁぃぅぇぉ' for c in run):
        return True
    # え段＋え の終わり（おもしれえ・すげえ）。おもしろい を
    # くだけて書いたよくあるセリフで、意図した表記（2026-08-08）。
    if (len(run) >= 3 and run[-1] == 'え'
            and run[-2] in 'えけせてねへめれげぜでべぺ'):
        return True
    n = len(run)
    if n >= 4 and n % 2 == 0 and run[:n // 2] == run[n // 2:]:
        return True
    return False


def _preceded_by_digit(line, start):
    """
    塊の直前（空白を飛ばして）が数字か。

    助数詞・単位の並び（7日以内・4コマ目・30 日間無料・第3章）は
    数字が「意図した表記」の強い証拠になる。janome の分割が
    環境で揺れても、形で守れる（項目41・42）。
    """
    j = start
    while j > 0 and line[j - 1] in (' ', '\u3000'):
        j -= 1
    return j > 0 and (line[j - 1].isdigit()
                      or '０' <= line[j - 1] <= '９')


def _trace(stage, detail):
    """関門の通過・不通過を1件記録する。"""
    if TRACE is not None:
        TRACE.append((stage, detail))


def _trailing_particle_len(run):
    """
    末尾にある助詞（だけ）の長さを返す。

    _trailing_functional_len と違い、活用語尾（い・た 等）は数えない。
    「既知語＋助詞」の判定に使う（たんごの → たんご＋の）。
    活用語尾まで見ると「ほらい」（補正の打ち間違い）が
    「ほら＋い」に見えてしまう。
    """
    tails = sorted(set(PARTICLES_MULTI) | set(PARTICLES_1CHAR),
                   key=len, reverse=True)
    pos = len(run)
    while pos > 0:
        for tail in tails:
            if pos - len(tail) >= 0 and run.endswith(tail, 0, pos):
                pos -= len(tail)
                break
        else:
            break
    if pos <= 0:
        return 0
    return len(run) - pos


def _trailing_functional_len(run):
    """
    ひらがな連続の末尾にある助詞・活用語尾の長さを返す。

    _leading_particle_len の末尾版。「たああんごの」の「の」を
    剥がして「たああんご」を取り出すために要る。
    末尾は活用語尾も剥がしてよい（語の末尾に付くものだから）。
    全部が機能語なら 0 を返す（剥がしようがない）。
    """
    tails = sorted(set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
                   | set(PARTICLES_1CHAR), key=len, reverse=True)
    pos = len(run)
    while pos > 0:
        for tail in tails:
            if pos - len(tail) >= 0 and run.endswith(tail, 0, pos):
                pos -= len(tail)
                break
        else:
            break
    if pos <= 0:
        return 0
    return len(run) - pos


def window_cores(window, store, min_len=3, after_kanji=False):
    """
    窓の中から、実際に語彙と照合する「芯」の候補を切り出す。

    窓には助詞や活用語尾がくっついたまま入ってくることが多い
    （「のつあがり」「たああんごの」「たんごのちながり」）。
    そのまま語彙と突き合わせても助詞のぶんだけ形が違うので、
    何にも一致しない。**機能語を剥がしてから照合する**必要がある。

    絞り込みの強い順に返す。呼び出し側は前から試し、
    最初に確信の持てた芯だけを直す。

      1. 先頭の助詞・末尾の機能語を剥がしたもの
         （after_kanji のときは、先頭の活用語尾も剥がす）
      2. 末尾だけ剥がしたもの
      3. 既知語＋助詞 で説明が付く部分を切り離した残り
         （「たんご＋の＋ちながり」の「ちながり」）
      4. 窓そのもの

    戻り値: [(開始, 終了), ...]  window の中の相対位置
    """
    n = len(window)
    # 窓全体が「送り仮名＋機能語」で説明し尽くせるなら、
    # そこに単語は無い（見えません の「えません」等）。芯を出さない。
    # 直前が漢字かどうかは条件にしない（引用で切り離された
    # 「えません」も同じ並びであるため）。直前が漢字なら、
    # 送り仮名はどのかなでもありうるとして広めに守る。
    if _okurigana_functional_only(window, any_head=after_kanji):
        return []
    out = []
    seen = set()

    def push(s, e):
        if e - s < min_len or s < 0 or e > n or (s, e) in seen:
            return
        frag = window[s:e]
        if _is_all_auxiliary(frag) or _is_all_functional(frag):
            return      # 助詞・語尾だけの並びは直す対象ではない
        seen.add((s, e))
        out.append((s, e))

    def _known(frag):
        try:
            return any(en['count'] >= 2 for en in store.lookup(frag))
        except Exception:
            return False

    # 直前が漢字なら、先頭は送り仮名である可能性が高い。
    # その場合に限り、活用語尾まで剥がす。
    #
    # 剥がす条件を「直前が漢字か」で切り分けるのが要点。
    # 常に剥がすと「たああんご」の語頭の「た」まで削れてしまい、
    # 逆に剥がさないと「色付き|のままでよい」の送り仮名「き」が
    # 芯に混ざって「きのま」→「きのう」と化ける（どちらも実際に壊れた）。
    # 字面だけでは語頭のかなと送り仮名は区別できないので、
    # 直前に何があるかで決めるしかない。
    if after_kanji:
        lead = _skip_leading_okurigana(window)
    else:
        lead = _leading_particle_len(window)
    tail = _trailing_functional_len(window)
    # 送り仮名を剥がすと決めたときは、剥がさない形は候補にしない。
    # 「きのままでよい」で末尾だけ剥がした「きのま」が残ると、
    # そこから「きのう」に化ける（実際に壊れた）。
    base = lead if after_kanji else 0
    push(lead, n - tail)
    # 末尾を剥がさない形も候補にする。壊れた語の最後の1文字が
    # たまたま活用語尾と同じ字のことがある（「ほらい」の「い」は
    # 「補正（ほせい）」の一部であって語尾ではない）。
    push(lead, n)
    push(base, n - tail)

    # 既知語と助詞で説明が付く部分は切り離す。
    # 「たんご」「の」まで説明できるなら、直すべきは残りの
    # 「ちながり」のほうだと分かる。
    # 切り離すのは **既知語＋助詞 の後ろ** だけにする。
    # 逆向き（後ろが既知語だから前を芯にする）もやっていたが、
    # 「きのままでよい」（色付き の まま で よい）で
    # 後ろの「よい」が既知語だからと前の「きのま」を芯にしてしまい、
    # 「きのう」に化けた。前側は語の途中から始まっていることが多く
    # （直前の漢字の送り仮名）、芯として信用できない。
    for i in range(2, n - 1):
        if window[i] in PARTICLES_1CHAR and _known(window[:i]):
            push(i + 1, n)

    push(base, n)
    return out


def _best_surface_for(reading, store):
    """その読みで、いちばんよく使われている表記。"""
    try:
        entries = store.lookup(reading)
    except Exception:
        return None
    if not entries:
        return None
    return max(entries, key=lambda e: e.get('count', 0)).get('surface')


def _usage_count(reading, store):
    """その読みで最もよく使われている表記の使用回数。"""
    try:
        entries = store.lookup(reading)
    except Exception:
        return 0
    if not entries:
        return 0
    return max(e.get('count', 0) for e in entries)


# 使用実績で決め打ちするための条件。
# 「よく使う語だから」というだけで選ぶのは危ういので、
# 他を圧倒しているときに限る。
_USAGE_DOMINANCE = 4        # 二番手の何倍あれば決め手とみなすか
_USAGE_MIN = 20             # 最低これだけ使われていること


def _break_tie_by_usage(candidates, store):
    """
    費用が拮抗している候補を、本人の使用実績で選ぶ。

    文脈ベクトルは、その語の共起がまだ育っていないと 0 のままで
    何も決められない（使い始めの時期や、話題が変わった直後）。
    そのとき残る手がかりが「本人がその語をどれだけ使ってきたか」。
    「たんほ」に対する「単語(696回)」と「単に(数回)」なら、
    打ち間違いの元として前者のほうがずっとありそうである。

    文脈と違って周りを見ないので、こちらは **圧倒的な差** が
    あるときだけ使う。僅差では選ばない。

    戻り値: 選ばれた読み、または None
    """
    scored = sorted(((_usage_count(r, store), r) for r, _c, _e in candidates),
                    reverse=True)
    if len(scored) < 2:
        return None
    top_count, top_reading = scored[0]
    second_count = scored[1][0]
    if top_count < _USAGE_MIN:
        return None
    if top_count < max(1, second_count) * _USAGE_DOMINANCE:
        return None
    return top_reading


def _break_tie_by_context(candidates, store, context_vec, surrounding_words):
    """
    費用が拮抗している候補のうち、文脈に馴染むものを1つ選ぶ。

    「たんほ」に対して「たんに（単に）」と「たんご（単語）」は、
    キーの距離だけ見るとほとんど差が付かない。どちらも実在する語で、
    打ち間違いとしてもっともらしいからである。
    決め手になるのは周りに何が書かれているか
    （「〜の繋がり」と続くなら「単語」）で、これは
    キー配列からは絶対に出てこない情報である。

    ここで見るのは前の回で用意した文脈の材料
    （同じ行の前後 → 直前の変換履歴 → 上下の行）。

    決め手が無ければ None を返す。その場合は直さない
    （「判断がつかないものは直さない」という設計方針のとおり）。

    candidates: [(読み, 費用, 訂正回数), ...]
    戻り値: 選ばれた読み、または None
    """
    if context_vec is None or not surrounding_words:
        return None
    surface_to_reading = {}
    surfaces = []
    for reading, _cost, _edits in candidates:
        surface = _best_surface_for(reading, store)
        if not surface or surface in surface_to_reading:
            continue
        surface_to_reading[surface] = reading
        surfaces.append(surface)
    if len(surfaces) < 2:
        return None
    try:
        picked = context_vec.pick_best_by_context(surfaces, surrounding_words)
    except Exception:
        return None
    if not picked:
        return None
    return surface_to_reading.get(picked)


def _reading_intact(reading, store, tokenize_fn):
    """
    その読みが「正しい日本語として通る」か。

    混合塊の読みの候補列は、同じ書かれた文字への別の解釈である。
    どれか1つでも正しい日本語として通るなら、書かれたものは
    意図した表記である可能性が高く、**通らない別の解釈**を
    打ち間違いとみなして直してはいけない。

    実機（2026-08-09）: パン屋 の読み ぱんや は「既知語＋助詞」で
    通るのに、別の読み ぱんおく（屋=おく）が はんかく に訂正され
    「パン屋の」→「半角の」と壊れた。上野（うえの が通るのに
    じょうや→じょうか で 浄化）、大正（たいしょう が通るのに
    おおせい→おんせい で 音声）も同じ構図。

    判定は語彙に根拠のある基準（読みが語彙にある・既知語＋助詞）
    だけを使う。janome で「読める」ことは根拠にしない: 壊れた塊の
    読みも、短い語の寄せ集めとして読めてしまうことが多く
    （流力＝りゅうりょく が 竜＋力 と読める）、それを根拠にすると
    直せる塊まで止まってしまう（学び12と同じ構図）。
    """
    try:
        if store.lookup(reading):
            return True
    except Exception:
        pass
    tail = _trailing_particle_len(reading)
    if 0 < tail < len(reading):
        try:
            if any(e['count'] >= 2
                   for e in store.lookup(reading[:-tail])):
                return True
        except Exception:
            pass
    return False


def _kanji_starts_verb(kanji, follow, tokenize_fn):
    """
    漢字1文字が直後のかなと繋がって動詞（の活用）になるか。

    ソラ来＋た＝来た、アハハ分＋からんかね＝分から のように、
    カタカナ語と動詞の境目を塊が跨いだ形を見分ける。
    「実在する並びかどうか」だけで見ると 子＋の（タン子の）まで
    実在扱いになり、タン子→単語 が直らなくなる（2026-08-09）。
    先頭のトークンが動詞であることまで求める。
    """
    for m in range(1, len(follow) + 1):
        try:
            toks = tokenize_fn(kanji + follow[:m])
        except Exception:
            continue
        if not toks or not all(t[5] for t in toks):
            continue
        if (toks[0][1] or '').split(':')[0] == '動詞' \
                and len(toks[0][0]) >= 1:
            return True
    return False


def _resolve_reading_list(chunk, readings, store, tokenize_fn,
                          context_vec=None, surrounding=(),
                          short_ok=(), allow_exact=True):
    """
    混合塊（漢字・カタカナ・混入英字を含む塊）の読みの候補列から、
    置き換え先の表記を決める（1-B / 1-C の共通部）。

      1. 読みそのものが語彙にある（変換し損ねただけ）→ その表記
      2. 芯の再構築（rebuild_window_core）が塊全体を直せる → その表記

    判断はどちらも既存の関門（使用実績・拮抗の裁定・切り詰め禁止）に
    委ね、ここでは増やさない。

    short_ok: 2文字でも引き当てを許す読みの集合（英字2連の ん 読み替え）。
    戻り値: (表記, 分類) または None。
        塊がそのまま正しい表記だった場合も None（触らない）。

    読みは確からしい順に並んでいる前提で、**1つの読みごとに
    完全一致→再構築の順で**試す。読みをまたいで完全一致を先に
    探すと、最有力の読み（たんこ）の再構築（→単語）より先に、
    次点の読み（たんし）の完全一致（→端子）が採られてしまう
    （実機相当の検証で「たん子」→「端子」と出た）。
    """
    for reading in readings:
        if len(reading) < (2 if reading in short_ok else 3):
            continue
        entries = [e for e in store.lookup(reading) if e['count'] >= 2]
        if entries:
            if not allow_exact:
                # 分割解決では完全一致を使わない。読みが語彙にある＝
                # その部分は正しい語かもしれない、ということであり、
                # 同音の別表記へすり替える危険がある（機能→昨日）。
                return None
            best = max(entries, key=lambda e: e.get('count', 0))
            if best['surface'] == chunk:
                return None        # いまの表記で正しい
            return best['surface'], best.get('category', 'その他')
        if len(reading) < 3:
            continue
        # この読みが正しい日本語として通るなら、塊は意図した表記。
        # ここで止めずに次の読みへ進むと、通らない別の解釈の側が
        # 訂正されてしまう（パン屋→半角・上野→浄化。詳しくは
        # _reading_intact の説明を参照）。
        if _reading_intact(reading, store, tokenize_fn):
            _trace('混合塊', f'{reading!r} は正しい読みとして通るので'
                             f'塊ごと触らない')
            return None
        fix = rebuild_window_core(reading, store, tokenize_fn,
                                  context_vec=context_vec,
                                  surrounding_words=surrounding,
                                  whole_only=True)
        if fix is None:
            continue
        surface = _best_surface_for(fix[2], store)
        if not surface or surface == chunk:
            continue
        entries = store.lookup(fix[2])
        category = entries[0].get('category', 'その他') if entries \
            else 'その他'
        return surface, category
    return None


def _resolve_kanji_split(chunk, store, tokenize_fn, dict_index=None,
                         context_vec=None, surrounding=()):
    """
    塊の片側が実在語なら、それを残してもう片側だけを組み直す（1-C）。

      野外文章 → 野外＋文章（実在）→ やがい→ながい → 長い文章
      簡易流力 → 簡易（実在）＋流力 → りゅうりょく→にゅうりょく → 簡易入力

    実在の判定は、確実な情報源（janome で読み切れる・辞書・語彙）
    だけを使う。組み直す側は _resolve_reading_list（既存の関門）。
    """
    from kanji_guess import (reading_combos_with_rank, looks_like_real_word)

    def _is_solid(part):
        if len(part) < 2:
            return False
        if looks_like_real_word(part, store, tokenize_fn):
            return True
        # 片側がまるごと1つの固有名詞（上野・高千穂・山手）。
        # looks_like_real_word は固有名詞を実在の根拠にしない
        # （田安吾＝田＋安吾 のような、固有名詞を**含む**寄せ集めを
        # 守らないため）が、切った片側が**ちょうど1語**の固有名詞で
        # あることは、正しい複合語（上野＋小学校）の切れ目の証拠に
        # なる。ここを実在扱いにしないと、反対側だけが読みに戻されて
        # 上野小学校→浄化小学校・高千穂大学→対戦穂大学 と壊れる
        # （実機・2026-08-09）。
        if tokenize_fn is not None:
            try:
                toks = tokenize_fn(part)
            except Exception:
                toks = []
            if (len(toks) == 1 and toks[0][0] == part
                    and '固有名詞' in (toks[0][1] or '')):
                return True
        if dict_index is not None:
            try:
                if dict_index.readings_for_surface(part):
                    return True
            except Exception:
                pass
        return False

    n = len(chunk)
    for cut in range(2, n - 1):
        # カタカナの連続の途中では割らない。「非アク|ティブ時」
        # 「カー|ル位置」のように、カタカナ語を断ち切った片側が
        # 「実在語」に見えてしまい、残り半分が別の語に化ける
        # （実機診断で 非アク提示・カー配置 の正体と確定した）。
        if ('ァ' <= chunk[cut - 1] <= 'ヶ' or chunk[cut - 1] == 'ー') \
                and ('ァ' <= chunk[cut] <= 'ヶ' or chunk[cut] == 'ー'):
            continue
        head, tail = chunk[:cut], chunk[cut:]
        for solid, broken, head_side in ((tail, head, True),
                                         (head, tail, False)):
            if not _is_solid(solid):
                continue
            # 壊れている側も実在語なら、塊は正しい複合語
            # （タブ＋機能）。触ると「機能」→「昨日」のように
            # 同音の別表記へすり替えてしまう。
            if _is_solid(broken):
                continue
            # 壊れている側の中に2文字以上の固有名詞が丸ごと
            # 入っているなら、切る位置がずれている（上野小|学校 の
            # 上野小）。この切り方では組み直さない。正しい切り方
            # （上野|小学校）は上の固有名詞の実在判定が守る
            # （実機で 上野小学校→相性学校 と壊れた・2026-08-09）。
            if tokenize_fn is not None:
                try:
                    _b_toks = tokenize_fn(broken)
                except Exception:
                    _b_toks = []
                if any(len(t[0]) >= 2 and '固有名詞' in (t[1] or '')
                       for t in _b_toks):
                    continue
            # 壊れている側に漢字が無い（カタカナ・かなだけ）なら
            # 触らない。カタカナ語は固有名詞・俗語が大半で、
            # 「スタン率直」の スタン を ボタン に変えるような
            # 破壊になる（カタカナ語は原則対象外、の方針どおり）。
            if not any(is_kanji(c) for c in broken):
                continue
            combos = reading_combos_with_rank(broken, dict_index)
            got = _resolve_reading_list(
                broken, [r for r, _k in combos[:4]], store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                allow_exact=False)
            if got is None:
                continue
            surface, category = got
            whole = (surface + solid) if head_side else (solid + surface)
            if whole != chunk:
                return whole, category
    return None


def _resolve_reading_seq(chunk, readings, store, tokenize_fn,
                         context_vec=None, surrounding=(),
                         require_context=False, attest_text='',
                         only_whole=False):
    """
    混合塊の読みを「語＋語（＋助詞）」の組として解決する（方針1-D/1-F）。

    1-F で加えた材料（すべて既存の基準の組み合わせ）:
      - 1文字削除の変種（挿入打鍵の訂正）。ただし証拠として弱いので、
        塊全体の完全一致（さつれません→されません）と
        真ん中助詞の3分割にしか使わない（2分割の組には使わない）
      - 塊全体が1つの語彙語に完全一致（説明ぶん＝せつめいぶん→説明文。
        「読みが語彙にあればそれ」の適用）
      - 真ん中助詞の3分割: [語][助詞1字][語] で、語の表記が塊の
        先頭・末尾に文字通り一致する場合だけ（クリック化ドラッグ→
        クリックかドラッグ、がいとうのはんい→該当の範囲）。
        直る箇所が真ん中だけに限定されるため証拠が強い
      - attest_text: 塊の外の同じ行の文字列。直した結果がそこに
        文字通り書かれていれば並記とみなす（⇒で正解を並べたメモや、
        同じ語を書き直している行で効く）
      - only_whole: 機能語尾の塊（差釣れません）では、組の探索を
        塊全体の完全一致だけに絞る（〜する・〜します のような
        ありふれた並びで余計な候補を作らないため）

    1-B/1-C の解決（_resolve_reading_list）は塊全体が1つの語である
    ことを前提にする。しかし報告された カタカナ・かな混じりの誤変換は
    複数の語にまたがる:

      カニ打ち   → かにうち   → かに＋うち → かな＋打ち（かに→かな）
      かな地腕   → かなちうで → かな＋ちう＋で → かな＋打ち＋で
      叶う父     → かなうちち → かなうち（連打畳み）→ かな＋打ち

    使う材料は既存の基準だけ:
      - 各部分は語彙の完全一致（count>=2。「読みが語彙にあればそれ」）
      - 2文字の部分に限り「強い形」の訂正を1箇所だけ許す
        （入れ替え: ちう→うち／隣接キー1置換: かに→かな。
          2文字は偶然似やすいため、形の証拠が強いものに限る）
      - 連打の畳み込み（_is_repeat_collapse と同じ考え方）
      - 訂正は塊全体で1箇所まで。少なくとも片側は無傷の完全一致
        （錨。両側とも直すのは「打ち間違い」ではなく別の語）

    正しい文章（カニ料理）も同じ形で読めるため、直すかどうかは
    拮抗の裁定に委ねる（rebuild_window_core と同じ順序:
    周りの語 → 使用実績の優位 → 決め手が無ければ直さない）。
    いまの表記どおりの解釈（カニ＋打ち）が語彙から組めるなら、
    それも候補として並べ、負かした場合だけ直す。

    require_context: 塊が実在語の並びとして読める場合に True。
        読める並びを直すのは「読める≠意図した語」（35-f と同じ
        構図）だが、その分、周りの語の裏付けを必須にする。

    戻り値: (表記, 分類) または None。
    """
    try:
        from kana_layout import nearby_candidates
    except Exception:
        return None

    # いまの表記そのものが語彙にあるなら補正しない（判断の順序1と
    # 同じ。「入力欄」「違和感」のような正しい語を、読みの分割から
    # 別の語の組（入力＋にん）に組み替えてしまわないための最初の関門。
    # 実機の総点検で 入力欄→入力にん・違和感→言わかな の誤爆を
    # 確認して足した）。
    try:
        if store.reading_of(chunk):
            return None
    except Exception:
        pass

    def _exact(part):
        entries = [e for e in store.lookup(part) if e['count'] >= 2]
        if not entries:
            return None
        best = max(entries, key=lambda e: e.get('count', 0))
        return (best['surface'], best.get('count', 0),
                best.get('category', 'その他'), False)


    def _strong_fix(part):
        # 2文字限定の「強い形」: 入れ替え、または隣接キー1置換。
        # 完全一致した語の中で最も使用実績の多いものを採る。
        if len(part) != 2:
            return None
        tries = set()
        if part[1] != part[0]:
            tries.add(part[1] + part[0])
        for pos in (0, 1):
            for alt, dist in nearby_candidates(part[pos]):
                if alt == part[pos] or dist > 1.0:
                    continue
                tries.add(part[:pos] + alt + part[pos + 1:])
        tries.discard(part)
        best = None
        for cand in tries:
            got = _exact(cand)
            if got and (best is None or got[1] > best[1]):
                best = got
        if best is None:
            return None
        return (best[0], best[1], best[2], True)

    as_is = None                # いまの表記どおりの解釈（部分の列）
    cands = []
    seen = set()
    for reading in readings:
        if len(reading) < 4:
            continue
        peels = [(reading, '')]
        if reading[-1] in PARTICLES_1CHAR and len(reading) - 1 >= 4:
            peels.append((reading[:-1], reading[-1]))
        for base, tail in peels:
            variants = [(base, 0, 'base')]
            for k in range(1, len(base)):
                if base[k] == base[k - 1]:
                    v = base[:k] + base[k + 1:]
                    if all(v != w for w, _c, _k2 in variants):
                        variants.append((v, 1, 'collapse'))
            # 1文字削除の変種（挿入打鍵の訂正。1-F）。連打の畳み込み
            # より証拠が弱いため、使い先は塊全体の完全一致と
            # 真ん中助詞の3分割に限る（下の kind 判定を参照）。
            if not tail:
                for k in range(len(base)):
                    v = base[:k] + base[k + 1:]
                    if all(v != w for w, _c, _k2 in variants):
                        variants.append((v, 1, 'delete'))
            for w, collapsed, kind in variants:
                if len(w) < 3:
                    continue
                # --- 塊全体が1つの語彙語（変換し損ね・挿入の訂正） ---
                # 説明ぶん＝せつめいぶん→説明文／
                # 差釣れません＝さつれません−つ→されません。
                # 読みそのままの完全一致は、ひらがなを含む塊
                # （変換し損ねの形）か、削除で届いた読みに限る
                # （漢字だけの塊の同音すり替えを防ぐ）。
                if kind == 'base':
                    # 変換し損ね（説明ぶん→説明文）: 塊にひらがなが
                    # あり、表記に漢字が入る（漢字→ひらがなへの
                    # 格下げはしない。押しても→おしても を防ぐ）。
                    whole_ok = (any(is_hiragana(c) for c in chunk))
                else:
                    # 削除・畳み込みで届く完全一致（差釣れません→
                    # されません）: 塊がひらがなだけの列に**解ける**
                    # 形に限る。漢字を含む語に化けるのは、頭の漢字の
                    # 読みを丸ごと捨てる形（誤入力→入力・入力後→
                    # 入力）で、削除の訂正ではなく語の切り落とし。
                    whole_ok = True
                if whole_ok:
                    got_w = _exact(w)
                    if got_w and kind == 'base' \
                            and not any(is_kanji(c) for c in got_w[0]):
                        got_w = None
                    if got_w and kind != 'base' \
                            and not (all(is_hiragana(c) for c in got_w[0])
                                     and _is_all_functional(got_w[0])):
                        # 削除の訂正で認めるのは「機能語列に解ける」
                        # 形だけ（されません）。内容語のかな
                        # （おうして−う→おして）まで許すと、
                        # 押して→おして のような格下げが起きる。
                        got_w = None
                    if got_w and got_w[0] + tail != chunk \
                            and got_w[0] + tail not in seen \
                            and len(got_w[0] + tail) * 2 >= len(chunk):
                        seen.add(got_w[0] + tail)
                        cands.append({'surface': got_w[0] + tail,
                                      'category': got_w[2] or 'その他',
                                      'parts': [got_w],
                                      'whole': True,
                                      'needs': True})
                # --- 真ん中助詞の3分割（1-F） ---
                # [語][助詞1字][語] で、語の表記が塊の先頭・末尾に
                # 文字通り一致する場合だけ。直る箇所が真ん中に限定
                # されるため、削除の変種にも許す。
                #   くりっくかどらっぐ → クリック＋か＋ドラッグ
                #   がいとうのはんい（あ を削除）→ 該当＋の＋範囲
                if not only_whole and len(w) >= 5:
                    for mid in range(2, len(w) - 2):
                        p1 = w[mid]
                        if p1 not in PARTICLES_1CHAR:
                            continue
                        mx, my = _exact(w[:mid]), _exact(w[mid + 1:])
                        if not (mx and my):
                            continue
                        if not (chunk.startswith(mx[0])
                                and chunk.endswith(my[0])):
                            continue
                        middle = chunk[len(mx[0]):len(chunk) - len(my[0])]
                        if middle == p1:
                            continue        # いまの表記で正しい
                        surface = mx[0] + p1 + my[0] + tail
                        if surface == chunk or surface in seen:
                            continue
                        seen.add(surface)
                        cands.append({'surface': surface,
                                      'category': mx[2] or 'その他',
                                      'parts': [mx, my],
                                      'whole': False,
                                      'needs': True})
                if only_whole or kind == 'delete' or len(w) < 4:
                    continue
                for cut in range(2, len(w) - 1):
                    x, y = w[:cut], w[cut:]
                    px, py = _exact(x), _exact(y)
                    # as-is 判定は「最多の表記」ではなく、その読みで
                    # 実績のある全表記の組み合わせで行う（タブ機能:
                    # きのう の最多が 昨日 でも タブ＋機能 は as-is）。
                    if as_is is None and collapsed == 0:
                        for e_x in store.lookup(x):
                            if e_x['count'] < 2:
                                continue
                            sx = e_x['surface']
                            if not chunk.startswith(sx):
                                continue
                            for e_y in store.lookup(y):
                                if e_y['count'] < 2:
                                    continue
                                if sx + e_y['surface'] + tail == chunk:
                                    as_is = (
                                        (sx, e_x.get('count', 0),
                                         e_x.get('category', 'その他'),
                                         False),
                                        (e_y['surface'],
                                         e_y.get('count', 0),
                                         e_y.get('category', 'その他'),
                                         False))
                                    break
                            if as_is is not None:
                                break
                    pairs = []
                    if px and py:
                        pairs.append((px, py))
                    if collapsed == 0:
                        # 訂正は塊全体で1箇所まで。畳み込みを使った
                        # 読みでは、部分の訂正はもう許さない。
                        # 両側が完全一致する場合（かに＋うち＝カニ打ち）
                        # でも強い形の訂正（かに→かな）は候補に並べる。
                        # いまの表記どおりの解釈（as_is）と拮抗させ、
                        # 周りの語・使用実績が決めたときだけ勝たせる。
                        if px:
                            fy = _strong_fix(y)
                            if fy:
                                pairs.append((px, fy))
                        if py:
                            fx = _strong_fix(x)
                            if fx:
                                pairs.append((fx, py))
                    for pa, pb in pairs:
                        changed = collapsed + int(pa[3]) + int(pb[3])
                        surface = pa[0] + pb[0] + tail
                        if changed == 0:
                            if surface == chunk and as_is is None:
                                as_is = (pa, pb)
                            # 表記が違うのに無傷で組める＝同音の
                            # 別表記へのすり替え（機能→昨日）。採らない
                            continue
                        if surface == chunk or surface in seen:
                            continue
                        if len(surface) * 2 < len(chunk):
                            continue
                        seen.add(surface)
                        part_cat = (pa[2] if pa[3] else pb[2]) or 'その他'
                        cands.append({'surface': surface,
                                      'category': part_cat,
                                      'parts': [pa, pb],
                                      'whole': False})
    if not cands:
        return None

    win = cands[0]
    if as_is is not None:
        # いまの表記どおりの解釈（カニ＋打ち）が語彙から組める。
        # 挑戦者は「as_is の部分を1つだけ入れ替えた組」に限り、
        # 入れ替えた部分（かな）対 元の部分（カニ）を、無傷の相方
        # （打ち）との共起で1対1で裁く。
        #   カニ打ち: 打ち と共起が強いのは かな ＞ カニ → 直す
        #   カニ料理: 料理 は かな とも カニ とも共起しない → 触らない
        #   カニ位置（うち→いち の挑戦）: 相方が カニ になるが、
        #     位置 は カニ と共起しない → 落ちる
        # 周りの語まで混ぜると、貼り付けの多いメモでは周りが常に
        # 「補正」等で埋まっており、無関係な カニ料理 まで かな側に
        # 引きずられる（実装中の検証で誤爆を確認して絞った）。
        asis_surfaces = set(p[0] for p in as_is)
        survivors = []
        for c in cands:
            if c.get('whole'):
                # 塊全体の完全一致（説明文）対 語＋かな片（説明＋ぶん）。
                # 同じ読みでの表記選びなので、「同じメモ内に同じ読みの
                # 語が別の表記で書かれているならそれに合わせる」
                # （判断の順序2）をそのまま適用する: 同じ行に文字通り
                # 書かれているときだけ勝たせる。
                if attest_text and c['surface'] in attest_text:
                    survivors.append(c)
                continue
            changed = [p for p in c['parts'] if p[0] not in asis_surfaces]
            if len(changed) != 1:
                continue        # 2箇所違うのは挑戦の形ではない
            challenger = changed[0]
            partners = [p[0] for p in c['parts']
                        if p[0] in asis_surfaces]
            incumbent = next(
                (q for q in as_is
                 if q[0] not in set(p[0] for p in c['parts'])), None)
            if incumbent is None or not partners:
                continue
            # 決めるのは相方との共起だけ。使用実績の優位まで許すと、
            # 語彙で育った無関係な語（英単語 の えい に対する いえ）が
            # 数の力で正しい表記を倒してしまう（実機相当の総点検で
            # 英単語→いえ単語 の誤爆を確認して外した）。
            beat = None
            if context_vec is not None:
                try:
                    beat = context_vec.pick_best_by_context(
                        [challenger[0], incumbent[0]], partners)
                except Exception:
                    beat = None
            if beat == challenger[0]:
                survivors.append(c)
        if len(survivors) != 1:
            _trace('語の組', f'{chunk!r} → いまの表記の解釈に'
                             f'勝てる組が{len(survivors)}件で決め手が無い')
            return None
        win = survivors[0]
    elif len(cands) > 1:
        # いまの表記は語彙から組めない。候補どうしの拮抗を、
        # 異なっている部分の 周りの語 → 使用実績 で決める
        # （順序は rebuild_window_core の裁定と同じ）。
        # 語の部分が全候補で同じ（真ん中の助詞だけが違う。
        # クリックかドラッグ／クリックばドラッグ）なら、読みの
        # 確からしさの順（cands は読みの順に並ぶ）で最初を採る。
        first_parts = tuple(p[0] for p in cands[0]['parts'])
        if all(tuple(p[0] for p in c['parts']) == first_parts
               for c in cands):
            pass        # win = cands[0] のまま（読みの順が決め手）
        else:
            common = set(p[0] for p in cands[0]['parts'])
            for c in cands[1:]:
                common &= set(p[0] for p in c['parts'])
            reps = []
            for c in cands:
                rest = [p for p in c['parts'] if p[0] not in common]
                if not rest:
                    return None        # 区別が付かない
                rep = next((p for p in rest if p[3]), rest[0])
                reps.append((rep[0], rep[1], c))
            picked = None
            if context_vec is not None and surrounding:
                try:
                    sel = context_vec.pick_best_by_context(
                        [r[0] for r in reps], list(surrounding))
                except Exception:
                    sel = None
                if sel:
                    picked = next((r for r in reps if r[0] == sel), None)
            if picked is None:
                ordered = sorted(reps, key=lambda r: -r[1])
                if ordered[0][1] >= max(1, ordered[1][1]) \
                        * _USAGE_DOMINANCE:
                    picked = ordered[0]
            if picked is None:
                _trace('語の組', f'{chunk!r} → 拮抗 '
                                 f'{[r[0] for r in reps]} の決め手が無い')
                return None
            win = picked[2]

    if require_context or win.get('needs'):
        # 塊全体の完全一致・真ん中助詞の3分割（1-F）は、読みの削除や
        # 表記の組み替えを含む分、塊が読めるかどうかに関係なく
        # 並記の裏付けを必須にする（刺されません→されません のような
        # 「読めない環境でだけ起きる」壊れ方も塞ぐ）。
        # 実在語の並びとして読める塊を直すのは、**直した後の語の組が
        # 近くに実際に書かれているときだけ**（判断の順序2「同じメモ内に
        # 同じ読みの語が別の表記で書かれているならそれに合わせる」の
        # 語の組への適用）。共起スコアの裏付けでは足りない:
        # 貼り付けの多いメモでは 補正↔意図 のような共起が常に強く、
        # 「補正後」→「補正意図」のような正しい語の組み替えが
        # 起きてしまう（実機相当の総点検で確認して絞った）。
        #   カニ打ち → かな＋打ち: 近くの行に「かな打ちでの補正」が
        #     あり、かな と 打ち が並んで現れる → 直す
        #   補正後 → 補正＋意図: 補正 意図 が並ぶ行は無い → 触らない
        # 周りの語（surrounding）は 同じ行 → 直前の履歴 → 上下の行 の
        # 順の語の列。当初は「隣り合って現れる」ことまで求めたが、
        # 周りの語は行をまたいで平坦化・重複除去されるため、並びが
        # 崩れる（実機で「かな地腕」だけ直らなかった正体。上の行の
        # 打ち が先に登録され、かな打ち の並びが壊れていた）。
        # 「組の両方の語が周りに現れる」まで緩める。緩めても
        # 補正後→補正意図 は 意図 が近傍に無い限り起きない
        # （メモ全文の総点検で誤爆が戻らないことを確認済み）。
        if not surrounding and not attest_text:
            return None
        names = [p[0] for p in win['parts']]
        # 文字通りの並記（同じ行に直した結果そのものが書かれている。
        # ⇒で正解を並べたメモや、書き直しの行で効く）か、
        # 組の全ての語が周りの語に現れることを求める。
        literal = bool(attest_text) and win['surface'] in attest_text
        support = literal or (
            bool(surrounding) and all(w in surrounding for w in names))
        if not support:
            _trace('語の組', f'{chunk!r} → {win["surface"]!r} は'
                             f'近くに書かれていないので直さない')
            return None

    return win['surface'], win['category']


_KATAKANA_MELT_MIN_COUNT = 100


def _katakana_melt_ok(chunk, new_surface, store):
    """
    カタカナ2文字以上を含む塊を、カタカナの無い表記へ置き換えて
    よいか（タン子→単語、乳リュク→入力）。

    カタカナ語は固有名詞・俗語・略語が多く、辞書に無くて当然。
    その塊を丸ごと漢字の語に溶かすのは強い判断なので、置き換え先に
    十分な使用実績を求める。語彙が育つと、検証の貼り付けから学習した
    使用実績の小さい語（大衆3・日常20・事項61）が誤変換先として
    引き当てられてしまう（実機で 縦シュー→大衆・ブチ上→日常・
    耳コピ→事項 と壊れた）。単語(968)・入力(871) のような
    使い込まれた語だけが、カタカナを溶かす置き換え先になれる。

    シード語彙（最初から正しいと分かっている語）は count に
    関係なく認める（項目27の原則: 判断根拠を汚れうる count ではなく
    確実な語の集合に置く）。
    """
    kata = 0
    longest = 0
    for c in chunk:
        if 'ァ' <= c <= 'ヶ' or c == 'ー':
            kata += 1
            longest = max(longest, kata)
        else:
            kata = 0
    if longest < 2:
        return True        # カタカナの塊を含まない。従来どおり
    if any('ァ' <= c <= 'ヶ' or c == 'ー' for c in new_surface):
        return True        # カタカナが残る置き換えは対象外
    try:
        from kanji_guess import _seed_surfaces
        if new_surface in _seed_surfaces():
            return True
    except Exception:
        pass
    try:
        r = store.reading_of(new_surface)
        if not r:
            return False
        count = max((e['count'] for e in store.lookup(r)
                     if e['surface'] == new_surface), default=0)
    except Exception:
        return False
    return count >= _KATAKANA_MELT_MIN_COUNT


def _is_repeat_collapse(core, cand):
    """
    core から「隣と同じ文字」だけを削っていくと cand になるか。

    「たたんご」→「たんご」（先頭の た の連打を1つ削る）が該当する。
    連打の訂正で短くなった候補は、部分文字列の形をしていても
    「切り詰め」（語の切り落とし）ではないので、除外してはいけない。
    """
    # 「隣と同じ文字を削る」を1文字ずつ判定すると、「みみ」の
    # 両方を削って「みみこぴー」→「こぴー」まで許してしまう
    # （どちらの み も「隣と同じ」だから）。これは連打の訂正ではなく
    # 語の頭の切り落とし（実機で 耳コピー→コピー と壊れた）。
    # 同じ文字の連続（run）ごとに比べ、**各連続から最低1文字は残る**
    # 形だけを連打の畳み込みとみなす。
    def _runs(s):
        out = []
        for ch in s:
            if out and out[-1][0] == ch:
                out[-1][1] += 1
            else:
                out.append([ch, 1])
        return out

    rc, rd = _runs(core), _runs(cand)
    if len(rc) != len(rd):
        return False
    for (c1, n1), (c2, n2) in zip(rc, rd):
        if c1 != c2 or not (1 <= n2 <= n1):
            return False
    return core != cand


def rebuild_window_core(window, store, tokenize_fn, max_cost=3.0,
                        min_margin=0.6, tie_band=1.0,
                        context_vec=None, surrounding_words=(),
                        after_kanji=False, whole_only=False):
    """
    単語として成立していない窓を、語彙にある読みへ組み直す。

    方針「ひらがなに直し、隣接キーや脱字などを考慮して再構築する」
    に対応する経路。窓から機能語を剥がした「芯」を取り出し、
    語彙の読みと重み付き編集距離で総当たりする。

    隣接キーの誤打だけを見る従来の探索（find_known_readings_flex）
    では、配列上で遠い取り違え（たんほ→たんご）に届かない。
    こちらは取り違えの費用を高くしたうえで許す。

    **直すかどうかの判断はこの関数の中だけで行う。**
    補正エンジンの判断経路を増やさないという設計方針のため、
    呼び出し側は「戻ってきたらその範囲を置き換える」だけにする。

    受け入れる条件（どれか1つでも欠けたら直さない）:
      - 芯が3文字以上（短い語は偶然似やすい）
      - 芯が機能語だけの並びでない
      - 芯が形態素解析で正しい日本語として読めない
        （読める＝壊れていないので触らない）
      - 芯そのものが語彙に無い（あるなら打ち間違いではない）
      - 最有力の費用が max_cost 未満
      - 訂正する箇所が芯の長さの半分まで
      - 二番手と差が付いている。付いていなければ文脈で決める。
        文脈でも決まらなければ直さない。

    tie_band: この幅に収まる候補は「拮抗している」とみなし、
        費用の差ではなく文脈で選ぶ。語彙が育つと、実在する語同士が
        僅差で並ぶことが増える（実機の7379語で「たんに」「たんご」
        「たんし」が同じ訂正1箇所で並んだ）。差が小さいからと
        いって諦めると、語彙が育つほど直せなくなってしまう。

    戻り値: (芯の開始, 芯の終了, 直した読み) または None
    """
    try:
        from vocabulary import find_similar_readings
    except Exception:
        return None
    if whole_only:
        # 混合塊（漢字を読みに戻した列）の解決では、塊全体が
        # 1つの語であることが分かっているので、部分の芯は作らない
        # （末尾の「う」等が活用語尾として剥がれ、届く語に
        #   届かなくなるため。めもちちょう → めもちちょ 等）。
        cores = []
        if not _okurigana_functional_only(window):
            cores = [(0, len(window))]
    else:
        # 窓全体が正しい日本語として読めるなら、そこから芯を
        # 削り出してはいけない。芯だけを見ると「うっかり」の
        # っかり が しっかり に、「たびに」の たび が別の語に
        # 化ける（実機・2026-08-09）。個々の芯にも同じ検査はあるが、
        # 剥がした後の断片では「窓が元々正しかった」ことが
        # 分からない。
        if _looks_like_valid_japanese(window, tokenize_fn):
            _trace('芯', f'{window!r} → 窓全体が正しい日本語として'
                         f'読めるので触らない')
            return None
        cores = window_cores(window, store, after_kanji=after_kanji)
    _trace('芯', f'{window!r}（直前が漢字={after_kanji}）→ '
                 f'{[window[x:y] for x, y in cores] or "芯なし"}')
    for c_s, c_e in cores:
        core = window[c_s:c_e]
        if len(core) < 3:
            _trace('芯', f'{core!r} → 3文字未満なので対象外')
            continue
        if is_protected_word(core) or _is_all_auxiliary(core):
            _trace('芯', f'{core!r} → 守る語／助詞だけなので対象外')
            continue
        # 芯の終わりの文字が、窓に残した直後の部分と繋がって
        # 機能語（活用語尾）になるなら、芯は機能語の途中で切れている
        # （「おきまして」の芯 おきま は ま＋して＝まして の途中。
        # 実機で おやま に化けた・2026-08-09）。
        _rest_after = window[c_e:]
        if _rest_after:
            _joined = False
            for _k in range(1, min(3, len(core)) + 1):
                _frag = core[-_k:] + _rest_after
                if any(len(t) > _k and _frag.startswith(t)
                       for t in AUXILIARY_TAILS):
                    _joined = True
                    break
            if _joined:
                _trace('芯', f'{core!r} → 終わりが機能語の途中で'
                             f'切れているので対象外')
                continue
        # 「〜りと」（ぱちりと・ぐるりと・ぴたりと）は擬態語の副詞。
        # 語彙と突き合わせて似た語に直す対象ではない
        # （実機で ぱちり が ぱせり（パセリ）に化けた・2026-08-09）。
        if (_rest_after[:1] == 'と' and core.endswith('り')
                and len(core) <= 4):
            _trace('芯', f'{core!r} → 擬態語（〜りと）なので対象外')
            continue
        # 直前が漢字の窓で、芯の頭が送り仮名の1文字、残りが
        # それだけで正しい語なら、芯は「送り仮名＋別の語」を
        # またいで拾っている（話す＋たびに の すたび。実機で
        # すみび に化けた・2026-08-09）。
        if (after_kanji and c_s == 0 and len(core) >= 3
                and core[0] in OKURIGANA_HEADS):
            _rest = core[1:]
            _rest_ok = False
            try:
                if any(e['count'] >= 2 for e in store.lookup(_rest)):
                    _rest_ok = True
            except Exception:
                pass
            if not _rest_ok and _looks_like_valid_japanese(_rest,
                                                           tokenize_fn):
                _rest_ok = True
            if _rest_ok:
                _trace('芯', f'{core!r} → 送り仮名＋正しい語'
                             f'（{_rest!r}）なので対象外')
                continue
        # 日本語の語は っ・ん・ー・小書きかな では始まらない。
        # 芯がこれらで始まっているのは、剥がし方がずれて語の途中を
        # 拾っている（「かんむり」の んむり、「いったら」の ったら、
        # 「うっかり」の っかり。実機・2026-08-09）。この芯は直さない。
        if core[0] in 'っんーゃゅょぁぃぅぇぉ':
            _trace('芯', f'{core!r} → 語頭に立たない文字で始まるので'
                         f'芯の切り出しがずれている。対象外')
            continue
        # 促音・長音で終わる芯も同じ（「往って」の おうっ 等。
        # 語は っ・ー では終わらない＝促音の途中で切れている）。
        if core[-1] in 'っー':
            _trace('芯', f'{core!r} → 語末に立たない文字で終わるので'
                         f'芯の切り出しがずれている。対象外')
            continue
        # 芯の頭が、窓の中の既知語（使用実績つき）の途中を
        # 切っていないか。「あらかじめお」から芯「じめお」を取ると、
        # 「あらかじめ」という語の腹を切っている。その芯を直すと
        # 語の後半だけが別の語に化ける（じめお→じめん。実機・
        # 2026-08-09）。
        if c_s > 0:
            _crossed = None
            for _x in range(max(0, c_s - 6), c_s):
                for _y in range(c_s + 1,
                                min(len(window), _x + 8) + 1):
                    _seg = window[_x:_y]
                    if len(_seg) < 3:
                        continue
                    try:
                        if any(e['count'] >= 2
                               for e in store.lookup(_seg)):
                            _crossed = _seg
                            break
                    except Exception:
                        pass
                if _crossed:
                    break
            if _crossed:
                _trace('芯', f'{core!r} → 既知語 {_crossed!r} の途中を'
                             f'切っているので対象外')
                continue
        # 正しく読める芯は壊れていない。触らない。
        if _looks_like_valid_japanese(core, tokenize_fn):
            _trace('芯', f'{core!r} → 正しい日本語として読めるので触らない')
            continue
        # 既に語彙にある読みそのものなら、打ち間違いではない
        try:
            if store.lookup(core):
                _trace('芯', f'{core!r} → この読みが語彙にあるので触らない')
                continue
        except Exception:
            pass
        # 「既知語＋助詞」の形の芯も、打ち間違いではない。
        # 窓全体が芯になったとき（たんごの）、末尾の助詞を含んだ
        # まま語彙と突き合わせると、「たんごの」→「たんこう」
        # （ご→こ は濁点の差で安く、の→う で1語に化ける）のような
        # 破壊が起きる（実機で「たんこ゛の繋がり」→「たんこう繋がり」。
        # 濁点を合成した たんごの が正しい語＋助詞なのに直された）。
        # 剥がすのは **助詞だけ** にする。活用語尾（い 等）まで見ると
        # 「ほらい」が「ほら＋い」に見えて、補正（ほせい）に届く道が
        # 塞がる（語彙が育つと「ほら」のような短い語が必ず現れる。
        # 学び12と同じ構図）。
        tail_len = _trailing_particle_len(core)
        if 0 < tail_len < len(core):
            try:
                if any(e['count'] >= 2
                       for e in store.lookup(core[:-tail_len])):
                    _trace('芯', f'{core!r} → 既知語＋助詞なので触らない')
                    continue
            except Exception:
                pass
        found = find_similar_readings(core, store, max_cost=max_cost + 1.5)
        _trace('芯', f'{core!r} 似た読み='
                     f'{[(r, round(c, 2), e) for r, c, e in found[:5]]}')
        # 訂正2箇所以上の候補は、打ち間違いの形をしているものだけ許す。
        #   - 長さが変わらないまま2文字以上を置き換えるのは、
        #     別の語への乗り換えである（まごころ→まきこむ・
        #     ひどいく→ひといき・あやこう→たんこう。実機 2026-08-09）。
        #   - 長さが変わる場合も、1箇所あたりの費用が安い訂正
        #     （連打の畳み・削除中心。たああんご→たんご は 0.6/箇所）
        #     だけを通す。高くつく2箇所訂正で届く語は偶然の一致
        #     （あおいえき→あいえん 1.8/箇所）。
        found = [f for f in found
                 if f[2] < 2 or (len(f[0]) != len(core)
                                 and f[1] / f[2] <= 1.4)]
        # 「助詞を1文字消しただけ」の候補は採らない。
        # 「二つばかり」の つばかり から ば を消すと つかり（浸かり）に
        # 届いてしまうが、助詞は打ち間違いで紛れ込む文字ではなく、
        # 意図して打たれた区切りである（実機・2026-08-09）。
        def _is_particle_drop(cand):
            if len(cand) != len(core) - 1:
                return False
            for _i, _ch in enumerate(core):
                if _ch in PARTICLES_1CHAR                         and core[:_i] + core[_i + 1:] == cand:
                    return True
            return False
        found = [f for f in found if not _is_particle_drop(f[0])]
        if not found:
            continue
        # 芯の一部でしかない候補（切り詰め）は採らない。
        # 「よろしくお」を「よろしく」に、「たんほ」を「たん」に
        # 縮めるのは、打ち間違いの訂正ではなく語の切り落としである。
        # 打ち間違いで壊れた語は、元の語と **別の形** になるのが普通で、
        # きれいに短くなることはまず無い。
        #
        # ただし **連打の重複を取り除いただけ** の候補は切り詰めではない。
        # 「たたんご」→「たんご」は、隣り合う同じ文字を削る訂正であり、
        # 部分文字列の形になるのは当然の帰結。これまで一律に除外して
        # いたため、本命「たんご」（連打・費用0.6）が消えて次点の
        # 「たんし」（2箇所訂正）が採られていた（実機で
        # 「たたんごの繋がり」→「たんしの繋がり」と壊れた）。
        cut = [f[0] for f in found
               if len(f[0]) < len(core) and f[0] in core
               and not _is_repeat_collapse(core, f[0])]
        if cut:
            _trace('芯', f'{core!r} → 切り詰め候補 {cut} を除外')
        found = [f for f in found
                 if not (len(f[0]) < len(core) and f[0] in core
                         and not _is_repeat_collapse(core, f[0]))]
        # 芯の後ろに活用語尾が残っている場合（「あらゆる」から
        # 「る」を剥がして芯が「あらゆ」になった等）、芯は語幹の
        # 途中で切れている。語幹の終わりの文字を別の字に変えると、
        # 残した語尾と繋がらない語になる
        # （「あらゆ」→「あらい」＋「る」＝ あらいる。実機で発生）。
        # 方針の「文節・単語ごとに頭の文字と終わりの文字を重視する」を
        # ここに適用し、終わりの文字を保つ候補だけに絞る。
        # 剥がしたのが助詞（たんほ「の」）なら芯は語の終わりまで
        # 揃っているので、この制限は掛けない（たんほ→たんご は
        # 終わりの文字が変わるが正しい訂正）。
        rest = window[c_e:]
        if rest and rest[0] not in PARTICLES_1CHAR:
            found = [f for f in found if f[0][-1] == core[-1]]
        if not found:
            continue
        best, cost, edits = found[0]
        if cost >= max_cost or best == core:
            _trace('芯', f'{core!r} → 最有力 {best!r} の費用 {cost:.2f} が'
                         f'高すぎる（{max_cost} 未満が必要）')
            continue
        # 訂正する箇所は、芯の長さの半分までに収める。
        # それ以上直すのは「打ち間違い」ではなく別の語であり、
        # 直した結果が元と似ても似つかないものになる。
        if edits * 2 > len(core):
            _trace('芯', f'{core!r} → 訂正 {edits}箇所は'
                         f'{len(core)}文字には多すぎる')
            continue
        # 拮抗している候補（同じ訂正回数で、費用が僅差のもの）
        close = [f for f in found
                 if f[2] == edits and f[1] - cost < tie_band
                 and f[1] < max_cost]
        if len(close) > 1:
            second_cost = close[1][1]
            if second_cost - cost >= min_margin and len(close) == 2:
                pass        # 二番手と十分な差がある。最有力でよい
            else:
                # 周りの語で決める。決まらなければ使用実績で決める。
                # どちらでも決まらなければ直さない。
                picked = _break_tie_by_context(close, store, context_vec,
                                               surrounding_words)
                how = '周りの語'
                if picked is None:
                    picked = _break_tie_by_usage(close, store)
                    how = '使用実績'
                if picked is None:
                    _trace('芯', f'{core!r} → 拮抗 '
                                 f'{[f[0] for f in close]} の決め手が無い'
                                 f'（周りの語={list(surrounding_words)[:5]}）')
                    continue    # 決め手が無い。直さない
                _trace('芯', f'{core!r} → 拮抗 {[f[0] for f in close]} を'
                             f'{how}で {picked!r} に決めた')
                best = picked
        _trace('芯', f'{core!r} → {best!r} に直す')
        return (c_s, c_e, best)
    return None


def _surrounding_content_words(tokens, start, end, window=3,
                               nearby_words=(), recent_words=()):
    """
    対象範囲 [start, end) の周りにある内容語の表記を、
    手がかりとして強い順に並べて返す（文脈スコアの material）。

    並べる順序がそのまま優先順位になる（context_score は
    先頭に近いものほど重く数える）。方針に沿って3段階にする:

      1. 同じ行の前後      いちばん確かな手がかり
      2. 直前の変換履歴    いま書いている話題の流れ
      3. 上下の行の語      同じ段落・同じ話題のまとまり

    nearby_words: 上下の行から集めた語（近い行の順）
    recent_words: 直前に確定した語（新しい順）

    助詞・記号・短すぎる語は除く。同じ語は最初に出た位置だけ残す
    （重複すると、その語だけが何重にも効いてしまう）。
    """
    before = []
    after = []
    for tok in tokens:
        surface, _pos, _reading, ts, te = tok[0], tok[1], tok[2], tok[3], tok[4]
        if te <= start:
            if len(surface) >= 2 and not is_protected_word(surface):
                before.append(surface)
        elif ts >= end:
            if len(surface) >= 2 and not is_protected_word(surface):
                after.append(surface)
    # 対象に近い語を先頭にする: 直前語は末尾から、直後語は先頭から
    near = list(reversed(before[-window:])) + after[:window]

    out = []
    seen = set()
    for group in (near, recent_words or (), nearby_words or ()):
        for w in group:
            if not w or w in seen:
                continue
            seen.add(w)
            out.append(w)
    return out


def evaluate_candidate(surface, reading, store, context_vocab,
                       find_readings, max_dist, is_known_word=False,
                       context_vec=None, surrounding_words=None):
    """
    ある語（表記・読み）について、補正すべきかを判断する。

    これがこのエンジンで唯一の補正判断の場所。
    複数の方法で候補を出して寄せ集めることはしない。

    is_known_word: 形態素解析がこの表記を実在する語として
        認識できたか。認識できている語は、たとえ語彙ストアに
        未登録でも正しく書けている可能性が高いので、
        文脈の裏付けが無い限り書き換えない。

    判断の順序:
      1. 今の表記のまま語彙にあり、使用実績があるなら補正しない
         （正しく書けているものを壊さないことが最優先）
      2. 同じメモ内に、同じ読みの語が別の表記で書かれているなら
         それに合わせる（文脈が最も確実な手がかり）
      3. 読みが誤っている場合、訂正して既知語に届き、
         かつその語に使用実績があるなら補正する

    戻り値: (補正後の表記, カテゴリ, 証拠の強さ) または None
    """
    # --- 1. 既に正しく書けているなら触らない ---
    entries = store.lookup(reading)
    for e in entries:
        if e['surface'] == surface and e['count'] >= 2:
            return None

    # 形態素解析が実在する語として認識できている表記は、
    # 語彙ストアに無くても正しく書けている可能性が高い。
    # 「以下」「か所」「しゃ」などを、同じ読みの別語
    # （「異化」「箇所」）に置き換えてしまうのを防ぐ。
    #
    # この判定は文脈による置換よりも先に行う。
    # 「性格」と「正確」、「彷徨」と「方向」のように
    # 両方とも実在する同音語の場合、同じメモ内に片方があるだけで
    # もう片方を書き換えてしまうため（実機で報告された誤検知）。
    # どちらが正しいかは文脈だけでは決められないので、
    # 実在語として書けているものは触らない。
    # 誤変換を直したい場合は、ユーザーが語をクリックして
    # 候補から選び直す（choices.py）。
    if is_known_word:
        return None

    # --- 2. 文脈による裏付け ---
    if context_vocab and reading in context_vocab:
        ctx_surface, ctx_category = context_vocab[reading]
        if ctx_surface != surface:
            return (ctx_surface, ctx_category, EVIDENCE_CONTEXT)
        return None

    # --- 3. 読みが完全一致する既知語（表記だけが違う） ---
    strong = [e for e in entries if e['count'] >= 2]
    if strong:
        # 同じ読みに有力な表記が複数ある場合（「すぎ」に対する
        # 「過ぎ」と「好き」など）、どちらが正しいかは
        # 文脈が無い限り決められない。
        # 使用実績だけを頼りに選ぶと「10時過ぎ」を「10時好き」に
        # 変えてしまうので、原則は判断がつかないものとして触らない。
        #
        # ただし文脈ベクトル（周辺の語との意味的な近さ）があれば、
        # それを追加の手がかりにする。完全一致の文脈語彙
        # （EVIDENCE_CONTEXT）ほど強い証拠ではないため、
        # 僅差での決め打ちは避ける（pick_best_by_context の
        # margin による足切り）。それでも選べない場合は、
        # これまでどおり何もしない。
        if len(strong) >= 2:
            if context_vec is not None and surrounding_words:
                cand_surfaces = [e['surface'] for e in strong]
                picked = context_vec.pick_best_by_context(
                    cand_surfaces, surrounding_words)
                if picked and picked != surface:
                    picked_entry = next(e for e in strong
                                        if e['surface'] == picked)
                    return (picked, picked_entry['category'],
                           EVIDENCE_VECTOR)
            return None
        best = strong[0]
        if best['surface'] != surface:
            return (best['surface'], best['category'], EVIDENCE_EXACT)
        return None

    # --- 4. 読みの誤りを訂正して既知語に届くか ---
    # ここが「誤打の補正」の本体。
    # 訂正後の読みが元より短くなる場合は採用しない
    # （「めもらん」→「めも」のように語を削る補正を防ぐ）。
    found = find_readings(reading, store, max_dist=max_dist, max_edits=3)
    for cand_reading, cost, edits in found:
        if edits == 0:
            continue
        if len(cand_reading) < len(reading):
            continue
        # 訂正1文字あたりのコストが高い（遠いキー）ものは
        # 打ち間違いとして不自然なので採用しない
        if not is_plausible_typo(reading, cost, edits):
            continue
        cand_entries = [e for e in store.lookup(cand_reading)
                        if e['count'] >= 2]
        if not cand_entries:
            continue
        if context_vocab and cand_reading in context_vocab:
            cs, cc = context_vocab[cand_reading]
            return (cs, cc, EVIDENCE_CONTEXT)
        # 訂正先の読みに有力な表記が複数ある場合、
        # どれを選ぶべきか決められないので、原則は触らない。
        # ここでも文脈ベクトルがあれば追加の手がかりにする
        # （3.の分岐と同じ考え方）。
        if len(cand_entries) >= 2:
            if context_vec is not None and surrounding_words:
                cand_surfaces = [e['surface'] for e in cand_entries]
                picked = context_vec.pick_best_by_context(
                    cand_surfaces, surrounding_words)
                if picked and picked != surface:
                    picked_entry = next(e for e in cand_entries
                                        if e['surface'] == picked)
                    return (picked, picked_entry['category'],
                           EVIDENCE_VECTOR)
            break
        best = cand_entries[0]
        if best['surface'] != surface:
            return (best['surface'], best['category'], EVIDENCE_NEAR)
        break

    return None


def _is_all_auxiliary(run):
    """
    このひらがな列は、助動詞・活用語尾だけで組み立てられているか。

    「ないです」（ない＋です）、「ませんでした」のような並びは
    内容語ではないので補正対象にしてはいけない。
    前から順に助動詞・活用語尾を取り除いていき、
    最後まで取り除けたなら文法要素だけの並びだと判断する。
    """
    tails = sorted(AUXILIARY_TAILS, key=len, reverse=True)
    # この判定は「ないです」「にします」のような短い文法的な並びを
    # 守るためのもの。長い列は、たまたま活用語尾に分解できたとしても
    # 内容語＋誤字である可能性のほうが高いので対象にしない。
    # （「もじにゅうのりょく」を「に＋ゅ＋う＋の＋り＋ょ＋く」のように
    #   分解して「文法要素の並び」と誤認するのを防ぐ）
    if len(run) > 6:
        return False
    rest = run
    consumed = False
    while rest:
        for tail in tails:
            if rest.startswith(tail):
                rest = rest[len(tail):]
                consumed = True
                break
        else:
            return False
    return consumed


def _looks_like_valid_japanese(run, tokenize_fn):
    """
    このひらがな列は、既に正しい日本語として成立しているか。

    語彙ストアに載っていない語でも、正しい日本語であることは多い
    （「そのため」「おはよう」「あるいは」など）。
    これらを「未知の読み＝誤字かもしれない」と扱うと、
    正しい文を壊してしまう。

    判定は「列全体が、辞書の語と機能語だけで説明しつくせるか」で行う。

    一部に既知語が含まれるだけでは根拠にならない。
    「もじなゅうりょく」は先頭の「もじ」が辞書にあるが、
    残りの「なゅうりょく」は説明できないので誤字である。
    逆に「そのため」は全体が機能語として説明でき、
    「おはよう」は全体が1つの既知語として説明できる。

    助詞の有無でも判定できない。かな入力の誤字列は
    形態素解析にかけると必ず助詞混じりに誤分割されるため
    （「もじにうりょく」の「も」「に」を助詞と誤認する）、
    助詞があることを根拠にすると誤字が一切直せなくなる。
    """
    try:
        toks = tokenize_fn(run)
    except Exception:
        return False
    if not toks:
        return False

    # 列を構成する各トークンが「説明できる」かを順に確かめる。
    # 説明できないトークンが1つでもあれば、誤字を含むとみなす。
    for surface, pos, reading, start, end, has_reading in toks:
        if is_protected_word(surface):
            continue          # 機能語・慣用表現
        if len(surface) == 1:
            # 1文字の助詞・助動詞は文法的な繋がりとして許容する。
            # ただし内容語の一部が偶然1文字に切られた場合もあるため、
            # これ単独では「正しい」の根拠にはしない。
            pos_major = pos.split(':')[0] if pos else ''
            if pos_major == '助詞':
                continue
            if pos_major == '助動詞' and start > 0:
                continue
            # **先頭の1文字助動詞は根拠にしない。**
            # 助動詞は用言の後ろに付くものなので、並びの先頭には
            # 立たない。それでも先頭に来ているのは、壊れた語の
            # 一部がたまたま助動詞と同じ字だったからである。
            # 「つあがり」は「つ（文語の助動詞）＋あがり」と読めて
            # しまい、正しい日本語として素通りしていた
            # （実機で「つながり」に直らない原因）。
            return False
        if has_reading:
            continue          # 辞書が読みを引けた語
        return False          # 説明できない断片がある＝誤字の可能性
    return True


from halfwidth import (correct_halfwidth, correct_romaji,
                       correct_zenkaku_input, has_zenkaku_ascii,
                       correct_kana_typed_as_romaji)


def find_halfwidth_runs(line, min_len=4):
    """
    半角文字だけが続く部分を取り出す。

    半角モードのまま打ってしまった箇所は、
    かなではなく半角の英数字・記号の並びとして現れる。
    その候補範囲をまとめて返す。

    実際に「打ち間違いなのか、意図した英単語なのか」の判断は
    correct_halfwidth() が、かなに戻した結果で行う。

    戻り値: [(開始, 終了, 文字列), ...]
    """
    def _is_run_char(ch):
        # 半角の英数字・記号に加えて、全角の英数字・記号も対象にする。
        # かな入力モードで変換をオンのまま打つと全角で入るため
        # （「md@i(4l)h」が「ｍｄ＠い（４ｌ）ｈ」になる）。
        if ch.isspace():
            return False
        if ch.isascii():
            return True
        return 0xFF01 <= ord(ch) <= 0xFF5E

    runs = []
    n = len(line)
    i = 0
    while i < n:
        if not _is_run_char(line[i]):
            i += 1
            continue
        j = i
        # 全角入力の中にはかなが混ざることがある（「い」など）ので、
        # 範囲の途中に現れるかなも取り込む
        while j < n and (_is_run_char(line[j])
                         or ('\u3041' <= line[j] <= '\u3096'
                             and j + 1 < n and _is_run_char(line[j + 1]))):
            j += 1
        run = line[i:j]
        if len(run) >= min_len and not _looks_like_address(run):
            runs.append((i, j, run))
        i = j
    return runs


# メールアドレスの形（名前@ドメイン.TLD）
_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
# URL の始まり
_URL_RE = re.compile(r'^(https?://|ftp://|www\.)', re.IGNORECASE)
# Windows のパス（C:\... ）
_WINPATH_RE = re.compile(r'^[A-Za-z]:[\\/]')
# よくあるトップレベルドメイン。これで終わる語はアドレスとみなす。
_TLD_TAIL = ('.com', '.net', '.org', '.jp', '.co.jp', '.io', '.dev',
             '.gov', '.edu', '.info', '.me', '.tv', '.app', '.xyz')
# URL のクエリや設定値の形（&sort=releasedate、key=value）。
# 英字の名前の直後に = が来る形は意図した入力とみなす。
# かな打ちの「=」（ほ のキー）を含む誤入力（Shift+= や 単=）は
# = の前が英字の並びではないので、この形には一致しない。
_QUERY_RE = re.compile(r'^[&?]?[A-Za-z_][A-Za-z0-9_\-]*=[A-Za-z0-9]')


def _looks_like_address(run):
    """
    メールアドレス・URL・ファイルパスのように見えるか。

    これらは意図して半角で書かれたものなので、
    かなに戻してはいけない（実機で someone742@example.com が
    ひらがなに変換される問題が報告された）。

    判定は厳しめにする。かな入力では「@」は濁点キー、
    「.」は「る」キーなので、これらが含まれるだけでは
    アドレスとは言えない（「md@i(4l)h」は「文字入力」の半角打ち）。
    ドメインの形（名前.TLD）まで揃っている場合だけ除外する。
    """
    low = run.lower()
    if _EMAIL_RE.search(run):
        return True
    if _URL_RE.match(run):
        return True
    if _WINPATH_RE.match(run):
        return True
    if any(low.endswith(t) for t in _TLD_TAIL):
        return True
    # クエリパラメータの形（実機で &sort=releasedate が
    # 日本語に化けた。2026-08-08）
    if _QUERY_RE.match(run):
        return True
    return False


def _has_new_repetition(original, replacement):
    """
    置換によって、元には無かった同じ文字の連続が生まれたか。

    範囲の取り方を誤ると、切り離したはずの助詞が残って
    「ももじにゅうりょく」のように文字が二重になることがある。
    こうした破綻を最後に検出して弾くための確認。
    """
    def _max_run(s):
        best = cur = 1
        for i in range(1, len(s)):
            cur = cur + 1 if s[i] == s[i - 1] else 1
            best = max(best, cur)
        return best if s else 0

    return _max_run(replacement) > _max_run(original)


def _match_score(a, b):
    """
    同じ長さの2つのかな列が、何文字違うかを返す。
    長さが違う場合は大きな値を返す（比較の対象外）。
    """
    if len(a) != len(b):
        return 99
    return sum(1 for x, y in zip(a, b) if x != y)


def _roughly_same(a, b, max_diff=1):
    """
    2つの同じ長さのかな列が、おおむね一致しているか。

    「語＋助詞」を巻き込んで探索したのか、
    それとも語の途中に余分な文字があるのかを見分けるために使う。
    前者なら、助詞を除いた部分は候補とほぼ一致するはず。
    """
    if len(a) != len(b):
        return False
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return diff <= max_diff


def correct_line(line, store, tokenize_fn, find_readings, max_dist=1.6,
                 context_vocab=None, decisions=None, input_method='kana',
                 context_vec=None, dict_index=None,
                 nearby_words=(), recent_words=()):
    """
    1行を補正する。このエンジンの入口。

    tokenize_fn: 行を受け取り
        [(表記, 品詞, 読み, 開始, 終了, 読みが確定か), ...] を返す関数。
        janome の有無はこの関数の中で吸収する。
    find_readings: 誤打された読みから既知の読みを探す関数。
    decisions: ユーザーが明示した判断（decisions.DecisionStore）。
        「この補正は不要」と言われた置換を最終検査で取り下げる。
        None なら判断なしとして扱う。
    context_vec: 語の共起から作った軽量な文脈ベクトル
        （context_vec.ContextVectorStore）。同じ読みに複数の
        有力な表記がある場合（「過ぎ」と「好き」等）に、
        周辺の語と意味的に馴染む方を選ぶ追加の手がかりとして使う。
        None なら、これまでどおり「判断がつかない」として触らない
        （新しい判断経路を増やすのではなく、既存の判断の中で
        使う追加の材料という位置づけ）。
    dict_index: janome 辞書の読み索引（dict_index.DictIndex）。
        誤変換された漢字列を読みに戻すとき、漢字1文字の読みを
        引くのに使う（「素帰任」→ す・き・にん）。
        None でも動く（自前の単漢字読み表だけで補う）。
    nearby_words: この行の上下の行にある内容語（近い行の順）。
        同音異義語の選択は同じ行の中だけでは決められないことが多い
        ため、段落としてのまとまりを手がかりに加える。
    recent_words: 直前に確定した語（新しい順）。
        いま書いている話題の流れ。ひとつ前だけでなく複数を見る。
        どちらも「材料」であって、これ自体が新しい判断経路に
        なるわけではない（渡さなければ従来どおりの動きになる）。

    戻り値: {'original', 'corrected', 'changed', 'details', 'spans'}
    """
    empty = {'original': line, 'corrected': line, 'changed': False,
             'details': [], 'spans': [], 'original_spans': [],
             'unsure_spans': []}
    if not line or not line.strip():
        return empty

    # かな入力では濁点・半濁点が独立したキーなので、
    # 「たんこ゛」のように濁点だけが分離して残ることがある。
    # これを「たんご」に合成してから補正にかける。
    # 合成できない組み合わせ（「こ゜」など）は濁点キーの誤打なので
    # normalize_marks 側で取り除かれる。
    try:
        from morphology import normalize_marks
        normalized = normalize_marks(line)
    except Exception:
        normalized = line
    if normalized != line:
        inner = correct_line(normalized, store, tokenize_fn, find_readings,
                             max_dist=max_dist, context_vocab=context_vocab,
                             decisions=decisions, context_vec=context_vec,
                             dict_index=dict_index,
                             nearby_words=nearby_words,
                             recent_words=recent_words)
        corrected = inner['corrected']
        changed = corrected != line
        # 濁点の合成で文字数が変わるため、内側の補正が持つ位置は
        # 元のテキストとずれる。以前はここで位置を諦めて空にして
        # いたため、**濁点合成だけの補正（たんこ゛の→たんごの）に
        # 色が一切付かなかった**（実機で「補正の色が付かないが
        # 補正はできている」と報告された）。
        # 元の行と最終結果の差分を取り直し、変わった範囲を
        # そのまま色と詳細にする（合成と内側の補正の両方を含む）。
        spans = []
        original_spans = []
        details = []
        if changed:
            import difflib
            sm = difflib.SequenceMatcher(None, line, corrected,
                                         autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == 'equal':
                    continue
                original_spans.append((i1, i2))
                spans.append((j1, j2))
                details.append((line[i1:i2], corrected[j1:j2], 'かな入力'))
        return {
            'original': line,
            'corrected': corrected,
            'changed': changed,
            'details': details,
            'spans': spans,
            'original_spans': original_spans,
            'unsure_spans': inner.get('unsure_spans', []),
        }

    tokens = tokenize_fn(line)
    if not tokens:
        return empty

    replacements = []

    # 文頭の「?」は、箇条書きの「・」を打とうとして、
    # 変換前の記号のまま確定してしまったものである可能性が高い。
    # かな入力の配列では「・」は無変換のキーにあり、
    # 半角/全角の状態を誤ると「?」相当の記号が入ることがある
    # （実機で「文頭に?と出た」と報告された）。
    # 文中の「?」は疑問符として使われている可能性が高いので触らず、
    # **行頭に限って**「・」への置き換えを提案する。
    if line[0] == '?':
        replacements.append((0, 1, '・', '記号'))

    # --- ひらがなだけの連続部分（かな入力の誤字が現れる主戦場） ---
    # 形態素解析は誤字を含むひらがな列を正しく区切れないため、
    # まとまり全体を1つの語として扱い、既知の読みに届くかを見る。
    # --- 半角モードのまま打ってしまった部分 ---
    # 日本語入力をオフのまま打つと、かなではなく半角文字が入る。
    # 「もじにゅうりょく」と打ったつもりが「md@i(4l)h」になる。
    # かなに戻して意味が通るものだけを補正する。
    halfwidth_taken = []
    for start, end, chunk in find_halfwidth_runs(line):
        # 全角で入ってしまった場合は、まず半角に戻して解釈する
        # （ｍｄ＠い（４ｌ）ｈ → md@i(4l)h → もじにゅうりょく）
        fixed = None
        if has_zenkaku_ascii(chunk):
            fixed = correct_zenkaku_input(chunk, store, find_readings,
                                          max_dist)
        if not fixed:
            # かな入力配列として解釈する（md@i(4l)h → もじにゅうりょく）
            fixed = correct_halfwidth(chunk, store, find_readings, max_dist)
        if not fixed:
            # ローマ字として解釈する（mojinyuuryoku → もじにゅうりょく）
            fixed = correct_romaji(chunk, store, find_readings, max_dist)
        if fixed:
            replacements.append((start, end, fixed, 'IT・PC操作'))
            halfwidth_taken.append((start, end))

    # --- 語として成立しない漢字の連続部分 ---
    # かな入力の誤打はIMEを通って漢字になるため、画面に出るのは
    # 「かなの誤り」ではなく漢字の誤変換になる。
    #   「かくにん」のつもりが「すきにん」→ IMEが「素帰任」を作る
    # 「素帰任」は語として存在しない。この判断に文脈は要らず、
    # 漢字を読みに戻せば機械的に「確認」まで導ける
    # （素=す 帰=き 任=にん → すきにん → 隣接キー訂正 → かくにん）。
    # 実機で「素帰任」「時ッ層」が直らないと報告された経路。
    #
    # 判断の物差しは増やさない: ここで使う「打ち間違いとして自然か」
    # 「使用実績があるか」は、いずれも既存の基準をそのまま借りる。
    kanji_taken = []
    try:
        from kanji_guess import (find_kanji_runs, suggest_for_run,
                                 looks_like_real_word, _looks_sentence_end,
                                 find_trailing_kanji_runs,
                                 find_leading_kanji_runs,
                                 reading_combos_with_rank)

        # --- かな2〜3文字＋漢字1文字の塊（方針1-C） ---
        # かなの並びの最後の1音だけが漢字に化けた形
        # （たん子＝たんこ→単語、やん後＝やんご、タン子）。
        # janome はこの並びを「たん＋子」のように読めてしまうため、
        # looks_like_real_word の守りが効かない。塊全体を読みに
        # 戻して、既存の関門（語彙の完全一致→芯の再構築）に委ねる。
        for t_start, t_end, chunk in (find_trailing_kanji_runs(line)
                                      + find_leading_kanji_runs(line)):
            if any(not (t_end <= s or t_start >= e)
                   for s, e in halfwidth_taken + kanji_taken):
                continue
            if _is_before_honorific(line, t_end):
                continue
            # 地名の接尾で終わる塊は固有名詞の可能性が高い。
            # find_kanji_runs 側と同じ形の守り（実機で「つく駅」が
            # 「使えん」に化けた・2026-08-09。つく＋えき の読みが
            # 訂正2箇所で つかえん に届いてしまう）。
            if len(chunk) >= 2 and chunk[-1] in '駅県市区町村港':
                continue
            # カタカナ頭＋末尾漢字1字で、その漢字が直後のかなと
            # 繋がって実在の語（動詞の活用）になるなら、カタカナ語と
            # 動詞の境目を跨いでいるだけ（アハハ分からんかね の
            # アハハ分。find_kanji_runs 側と同じ守り・2026-08-09）。
            if (len(chunk) >= 3 and is_kanji(chunk[-1])
                    and all('ァ' <= c <= 'ヶ' or c == 'ー'
                            for c in chunk[:-1])):
                _fw = ''
                _fj = t_end
                while (_fj < len(line) and is_hiragana(line[_fj])
                       and len(_fw) < 3):
                    _fw += line[_fj]
                    _fj += 1
                if _fw and _kanji_starts_verb(chunk[-1], _fw,
                                              tokenize_fn):
                    continue
            # 数字の直後の塊は意図した表記（4コマ目・第3章）。
            # 実機で 4コマ目 が 4項目 に化けた（2026-08-08）。
            if _preceded_by_digit(line, t_start):
                continue
            # 頭のかなが機能語だけ（その辺・いい子）なら正しい並び
            head = ''.join(chr(ord(c) - 0x60)
                           if 'ァ' <= c <= 'ヶ' and c != 'ー' else c
                           for c in chunk[:-1])
            if _is_all_functional(head) or _okurigana_functional_only(head):
                continue
            # 頭のかなが、直前のかなと合わせると機能語・送り仮名の
            # 断片になるなら、語の途中を拾っている
            # （「起こりやすい語」の「すい語」。頭の「すい」だけでは
            #   分からないが、前の「や」と合わせた「やすい」で
            #   分かる。実機で「や英語」に化けた。2026-08-08）。
            _prev = ''
            _pj = t_start
            while (_pj > 0 and is_hiragana(line[_pj - 1])
                   and len(_prev) < 3):
                _prev = line[_pj - 1] + _prev
                _pj -= 1
            if _prev and head and any(
                    _is_all_functional(_prev[m:] + head)
                    or _okurigana_functional_only(_prev[m:] + head)
                    for m in range(len(_prev))):
                continue
            # 漢字1＋カタカナの塊（leading）は、頭の漢字が **直前の
            # 漢字と繋がって実在語になり**、かつカタカナ側も単体で
            # 実在する語なら、正しい複合語の切れ目をまたいで拾って
            # いる（隣接キーの 接キー、文字コードの 字コード、
            # 最大化ボタンの 化ボタン。実機で 隣節操・文スピード・
            # 最大会談 と壊れた）。文字乳リュク の 乳リュク は
            # リュク が実在しないので引き続き対象。
            if is_kanji(chunk[0]) and t_start > 0 \
                    and is_kanji(line[t_start - 1]):
                kata_part = chunk[1:]
                prev2 = line[max(0, t_start - 2):t_start]
                joins_prev = any(
                    looks_like_real_word(prev2[-m:] + chunk[0], store,
                                         tokenize_fn)
                    for m in range(1, len(prev2) + 1))
                if joins_prev and looks_like_real_word(kata_part, store,
                                                       tokenize_fn):
                    continue
            # カタカナ語＋場所・位置の接尾の漢字1字（ソフト上・
            # アプリ内）は正しい複合。カタカナ側が実在する語なら
            # 触らない（実機で ソフト上→ソフトウエア と壊れた。
            # 2026-08-08）。子・目 のような接尾は対象にしない
            # （タン子→単語 は誤変換なので直し続ける）。
            if (len(chunk) >= 3 and is_kanji(chunk[-1])
                    and chunk[-1] in '上中下内外前後間側'):
                _kata = chunk[:-1]
                if (all('ァ' <= c <= 'ヶ' or c == 'ー' for c in _kata)
                        and looks_like_real_word(_kata, store,
                                                 tokenize_fn)):
                    continue
            surrounding = _surrounding_content_words(
                tokens, t_start, t_end,
                nearby_words=nearby_words, recent_words=recent_words)
            combos = reading_combos_with_rank(chunk, dict_index)
            # 実在する語の並びとして読める塊（うどん粉＝うどん＋粉）は、
            # 読みの完全一致による表記の差し替えを許さない。読みが
            # 同じ別表記（饂飩粉）へのすり替えは誤字の訂正ではなく
            # 表記変換であり、方針1に反する（実機・2026-08-09）。
            # 芯の再構築（壊れた読みを直す）は引き続き試す。
            got = _resolve_reading_list(
                chunk, [r for r, _k in combos[:6]], store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                allow_exact=not looks_like_real_word(chunk, store,
                                                     tokenize_fn))
            if got is None:
                continue
            new_surface, category = got
            if len(new_surface) * 2 < len(chunk):
                continue
            if not _katakana_melt_ok(chunk, new_surface, store):
                _trace('混合塊', f'{chunk!r} → {new_surface!r} は'
                                 f'使用実績が足りないので溶かさない')
                continue
            _trace('混合塊', f'{chunk!r} → {new_surface!r}')
            replacements.append((t_start, t_end, new_surface, category))
            kanji_taken.append((t_start, t_end))

        # --- カタカナ・かなの混じった塊（方針1-D） ---
        # かなの一部がカタカナや漢字2文字に化けて確定した形
        # （カニ打ち＝かな打ち、かな地腕＝かな打ちで）。
        # 塊全体を読みの列に戻し、語の組として解決する。
        # 正しい文章（カニ料理）も同じ形に一致するため、
        # いまの表記どおりの解釈と拮抗させ、周りの語・使用実績が
        # 決めたときだけ直す（_resolve_reading_seq）。
        from kanji_guess import find_mixed_kana_runs
        for m_start, m_end, chunk in find_mixed_kana_runs(line):
            # 数字の直後の塊は意図した表記（30 日間無料・7日以内）。
            # 実機で 日間無料 が 日夜無料 に化けた（2026-08-08）。
            if _preceded_by_digit(line, m_start):
                continue
            # 頭のかな（カタカナ含む）が、それ自体で接尾・助詞の語
            # （〜がち 等）なら、俗語の強調書き（ガチ過ぎ）の可能性が
            # 高い。語の組に分解しない（実機で ガチ過ぎないか が
            # 勝ち過ぎないか に化けた。2026-08-08）。
            # ※機能語の「組み合わせで説明できる」判定（かな＝か＋な）
            #   まで広げると、カニ打ち・かな地腕 の修正が止まるため、
            #   一覧への直接の一致だけを見る。
            _mh = ''
            for _c in chunk:
                if 'ァ' <= _c <= 'ヶ' and _c != 'ー':
                    _mh += chr(ord(_c) - 0x60)
                elif is_hiragana(_c):
                    _mh += _c
                else:
                    break
            if _mh and (_mh in AUXILIARY_TAILS or _mh in PARTICLES_MULTI):
                continue
            if any(not (m_end <= s or m_start >= e)
                   for s, e in halfwidth_taken + kanji_taken):
                continue
            if _is_before_honorific(line, m_end):
                continue
            # ひらがな頭＋漢字2文字の形（かな地腕）は、直す先が
            # 漢字側になる。漢字側が単体で実在する語（ここの機能・
            # ここ数年）なら、それは正しい語に かなの頭が付いた
            # だけの並びなので触らない（実機相当の総点検で
            # ここの機能→この昨日 の誤爆を確認して足した）。
            # カタカナ頭（カニ打ち）は直す先がカタカナ側なので、
            # 漢字側（打ち）が実在していても対象のまま。
            # 「地腕」（地＋腕、単漢字の寄せ集め）は読めても実在の
            # 根拠にしない（田安吾と同じ構図）。1語で読める場合だけ守る。
            if is_hiragana(chunk[0]):
                kanji_part = chunk[-2:]        # この形の漢字は末尾2文字
                one_word = False
                try:
                    toks_k = tokenize_fn(kanji_part)
                    one_word = (len(toks_k) == 1 and bool(toks_k[0][5]))
                except Exception:
                    pass
                if one_word or store.reading_of(kanji_part):
                    continue
            # 漢字頭＋かな尾（説明ぶん・差釣れません）の塊は、
            # 〜する・〜します・〜ため のようなありふれた活用の並びと
            # 同じ形なので、解決を「塊全体の完全一致」だけに絞る
            # （only_whole。組の探索まで許すと 止まるため→止まる詰め、
            #   変わります→変わりまず のような強い形の誤爆が出る。
            #   実機相当の総点検で確認して絞った）。
            m_only_whole = is_kanji(chunk[0])
            surrounding = _surrounding_content_words(
                tokens, m_start, m_end,
                nearby_words=nearby_words, recent_words=recent_words)
            combos = reading_combos_with_rank(chunk, dict_index)
            got = _resolve_reading_seq(
                chunk, [r for r, _k in combos[:6]], store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                require_context=looks_like_real_word(chunk, store,
                                                     tokenize_fn),
                attest_text=line[:m_start] + ' ' + line[m_end:],
                only_whole=m_only_whole)
            if got is None:
                continue
            new_surface, category = got
            if len(new_surface) * 2 < len(chunk):
                continue
            # 「直した結果」が塊の読みそのもの（漢字をかなに開いた
            # だけ）なら、それは訂正ではない。同じ語をかなでも
            # 書いている行（F9おして…エンターを押しても）で、
            # 並記の関門を逆手に 押して→おして と開いてしまった
            # （2026-08-08）。
            if new_surface in (r for r, _k in combos):
                _trace('語の組', f'{chunk!r} → {new_surface!r} は'
                                 f'読みに開くだけなので直さない')
                continue
            _trace('語の組', f'{chunk!r} → {new_surface!r}')
            replacements.append((m_start, m_end, new_surface, category))
            kanji_taken.append((m_start, m_end))

        for k_start, k_end, chunk in find_kanji_runs(line):
            if any(not (k_end <= s or k_start >= e)
                   for s, e in halfwidth_taken):
                continue
            # 敬称の直前＝人名の可能性が高いので触らない
            if _is_before_honorific(line, k_end):
                continue
            # 地名の接尾で終わる塊は固有名詞（田無駅）の可能性が
            # 高い。janome は固有名詞を実在の根拠にしない方針
            # のため「読める」判定に乗らず、当てずっぽうの探索で
            # タメ息 に化けた（実機・2026-08-08）。形で守る。
            if len(chunk) >= 2 and chunk[-1] in '駅県市区町村港':
                continue
            # 古い言い回しだが日常で見る表現（以て・往って 等）を
            # 含む塊は触らない（PROTECTED_CLASSICAL 参照）。
            if any(p in line[max(0, k_start - 1):k_end + 2]
                   for p in PROTECTED_CLASSICAL):
                _trace('漢字塊', f'{chunk!r} → 日常で見る古い言い回し'
                                 f'なので触らない')
                continue
            # 漢数字＋助数詞を含む塊（五十個入・第三章）は意図した
            # 表記。「数字・記号を含む範囲は触らない」の漢数字版
            # （実機で 玉子五十個入 が 五十記入 に化けた・2026-08-09）。
            try:
                _c_toks = tokenize_fn(chunk)
            except Exception:
                _c_toks = []
            if any('名詞:数' in (t[1] or '') for t in _c_toks):
                _trace('漢字塊', f'{chunk!r} → 漢数字を含むので触らない')
                continue
            # 塊の直後の送り仮名まで含めると実在する語になるなら触らない。
            # 塊の切り出しは最後の漢字で止まるため、「取り違えて」から
            # 「取り違」だけが塊になる。「取り違」単体は辞書に無いので
            # 異様と誤判定され、「種類」に化けた（実機で発生）。
            # 後ろに続くひらがなを1〜3文字足して実在語になるかを見る。
            follow = ''
            j = k_end
            while (j < len(line) and is_hiragana(line[j])
                   and len(follow) < 3):
                follow += line[j]
                j += 1
            if follow and any(
                    looks_like_real_word(chunk + follow[:m], store,
                                         tokenize_fn)
                    for m in range(1, len(follow) + 1)):
                # 塊そのものが実在語の並びとして読める場合は、
                # ここで捨てずに先へ進める（「叶う父」＋「で」も
                # 実在の並びとして読めるが、それは塊単体が読める
                # ことの言い換えでしかない）。読める塊の扱いは
                # 後段の 1-D（語の組＋文脈の裏付け）が決める。
                if not looks_like_real_word(chunk, store, tokenize_fn):
                    continue
            # カタカナ語＋漢字語の複合（バフ効果・カール位置・
            # ドラッグ変換）。カタカナ側が辞書に無い語（バフ）でも、
            # 漢字側が2文字以上の実在語なら、正しい複合の可能性が
            # 高い（カタカナ語は固有名詞・俗語が多く辞書に無くて
            # 当然）。触らない。タン子（漢字1文字）は対象のまま。
            _kata_head_len = 0
            while (_kata_head_len < len(chunk)
                   and ('ァ' <= chunk[_kata_head_len] <= 'ヶ'
                        or chunk[_kata_head_len] == 'ー')):
                _kata_head_len += 1
            if _kata_head_len >= 2:
                _kanji_rest = chunk[_kata_head_len:]
                # 末尾の漢字が1文字でも、直後のかなと繋がって実在の
                # 語（動詞の活用）になるなら、カタカナ語と動詞の
                # 境目を塊が跨いでいるだけ（ソラ来た の ソラ来、
                # アハハ分からんかね の アハハ分。実機・2026-08-09）。
                if len(_kanji_rest) == 1 and follow \
                        and _kanji_starts_verb(_kanji_rest, follow,
                                               tokenize_fn):
                    _trace('漢字塊', f'{chunk!r} → カタカナ語＋動詞の'
                                     f'境目なので触らない')
                    continue
                if (len(_kanji_rest) >= 2
                        and all(is_kanji(c) for c in _kanji_rest)
                        and looks_like_real_word(_kanji_rest, store,
                                                 tokenize_fn)):
                    continue
                # カタカナ頭が、それ自体で接尾・助詞の語（がち等）
                # なら、俗語の強調書き（ガチ過ぎ）。触らない
                # （実機で ガチ過 が ガラス に化けた。2026-08-08）。
                _kh = ''.join(chr(ord(c) - 0x60)
                              for c in chunk[:_kata_head_len]
                              if c != 'ー')
                if _kh in AUXILIARY_TAILS or _kh in PARTICLES_MULTI:
                    continue
            # 実在語の並びとして読める塊は、当てずっぽうの探索
            # （suggest_for_run）に掛けない。「日以内」（日＋以内）が
            # 汚染された語彙の「行内」に化けた（実機）。読める塊を
            # 直せるのは、並記の裏付けを要求する 1-D の経路だけ。
            # 数字の直後の塊（過去7日以内・約2倍・第3章）も同じ扱い:
            # 助数詞・単位の並びは janome の分割が環境で揺れるため、
            # 「読める」判定に頼らず形で守る（実機で 7日以内 が
            # 行内 に化けたままだった）。
            # 数字と塊の間に空白が挟まっていても（過去 7 日以内）、
            # 数字が意図の証拠であることは変わらない。空白を
            # 飛ばして直前の文字を見る（実機で「過去 7 日以内」の
            # 日以内 だけが 行内 に化けたままだった。2026-08-08）。
            # 「読める扱いにして並記つきの経路へ送る」のではなく、
            # 塊ごと対象外にする。読めない塊（日間無料）だと
            # 並記なしのフォールバックに落ちて 日夜無料 に化けた。
            if _preceded_by_digit(line, k_start):
                _trace('漢字塊', f'{chunk!r} → 数字の直後なので触らない')
                continue
            _readable = looks_like_real_word(chunk, store, tokenize_fn)
            surrounding = None
            if context_vec is not None:
                surrounding = _surrounding_content_words(
                    tokens, k_start, k_end,
                    nearby_words=nearby_words, recent_words=recent_words)
            guess = None
            if not _readable:
                guess = suggest_for_run(chunk, store, find_readings,
                                        dict_index=dict_index,
                                        tokenize_fn=tokenize_fn,
                                        max_dist=max_dist,
                                        at_sentence_end=_looks_sentence_end(
                                            line, k_end),
                                        context_vec=context_vec,
                                        surrounding_words=surrounding)
            if not guess:
                # --- 方針1-C: 読みを芯の再構築に載せるフォールバック ---
                # suggest_for_run の打ち間違い探索は「読みの長さが
                # 変わらない」誤りしか扱えない。脱字・挿入を含む誤変換
                # （田安吾＝たあんご→たんご、目もち長＝めもちちょう→
                # めもちょう）はここで拾う。実在する語（janome で
                # 読み切れる並び）はこれまでどおり触らない。
                if looks_like_real_word(chunk, store, tokenize_fn):
                    # --- 方針1-D: 読める並びでも語の組で解決を試す ---
                    # 「叶う父」は 叶う＋父 と読めてしまうが、読みの列
                    # かなうちち は連打を畳むと かな＋打ち に届く。
                    # 「読める」ことは「意図した語」を意味しない
                    # （35-f と同じ構図）。ただし読める並びを直すのは
                    # 周りの語の裏付けがあるときだけ（require_context）。
                    surrounding_d = _surrounding_content_words(
                        tokens, k_start, k_end,
                        nearby_words=nearby_words,
                        recent_words=recent_words)
                    combos_d = reading_combos_with_rank(chunk, dict_index)
                    got_d = _resolve_reading_seq(
                        chunk, [r for r, _k in combos_d[:6]], store,
                        tokenize_fn, context_vec=context_vec,
                        surrounding=surrounding_d, require_context=True,
                        attest_text=line[:k_start] + ' ' + line[k_end:])
                    if got_d is None:
                        continue
                    new_surface, category = got_d
                    if len(new_surface) * 2 < len(chunk):
                        continue
                    # 漢字をかなに開くだけの置き換えは訂正ではない
                    # （押して→おして。上の混合塊と同じ関門）
                    if new_surface in (r for r, _k in combos_d):
                        _trace('語の組', f'{chunk!r} → {new_surface!r} は'
                                         f'読みに開くだけなので直さない')
                        continue
                    # 読みが変わらない置き換え（料理屋料理→料理や料理。
                    # 屋 を や に開いただけ）も表記変換であって訂正では
                    # ない（実機・2026-08-09）。置き換え先の読みが、
                    # 塊の読みの候補と同じなら採らない。
                    try:
                        _ns_toks = tokenize_fn(new_surface)
                    except Exception:
                        _ns_toks = []
                    if _ns_toks and all(t[5] for t in _ns_toks):
                        _ns_reading = ''.join(
                            chr(ord(c) - 0x60)
                            if 'ァ' <= c <= 'ヶ' and c != 'ー' else c
                            for c in ''.join(t[2] for t in _ns_toks))
                        if _ns_reading in {r for r, _k in combos_d}:
                            _trace('語の組', f'{chunk!r} → {new_surface!r}'
                                             f' は読みが同じ表記変換なので'
                                             f'直さない')
                            continue
                    _trace('語の組', f'{chunk!r} → {new_surface!r}')
                    replacements.append((k_start, k_end, new_surface,
                                         category))
                    kanji_taken.append((k_start, k_end))
                    continue
                surrounding2 = _surrounding_content_words(
                    tokens, k_start, k_end,
                    nearby_words=nearby_words, recent_words=recent_words)
                combos_k = reading_combos_with_rank(chunk, dict_index)
                got = _resolve_reading_list(
                    chunk, [r for r, _k in combos_k[:6]], store,
                    tokenize_fn, context_vec=context_vec,
                    surrounding=surrounding2)
                if got is None:
                    # 片側が実在語なら、残りだけを組み直す
                    # （野外文章→長い文章、簡易流力→簡易入力）
                    got = _resolve_kanji_split(
                        chunk, store, tokenize_fn, dict_index=dict_index,
                        context_vec=context_vec, surrounding=surrounding2)
                if got is None:
                    continue
                new_surface, category = got
                if len(new_surface) * 2 < len(chunk):
                    continue
                if not _katakana_melt_ok(chunk, new_surface, store):
                    _trace('混合塊', f'{chunk!r} → {new_surface!r} は'
                                     f'使用実績が足りないので溶かさない')
                    continue
                _trace('混合塊', f'{chunk!r} → {new_surface!r}')
                replacements.append((k_start, k_end, new_surface, category))
                kanji_taken.append((k_start, k_end))
                continue
            new_surface, category, _reading = guess
            if not _katakana_melt_ok(chunk, new_surface, store):
                _trace('漢字塊', f'{chunk!r} → {new_surface!r} は'
                                 f'使用実績が足りないので溶かさない')
                continue
            _trace('漢字塊', f'{chunk!r} → {new_surface!r}'
                             f'（suggest_for_run・読み {_reading!r}）')
            replacements.append((k_start, k_end, new_surface, category))
            kanji_taken.append((k_start, k_end))

        # --- 半角英字・記号が1文字だけ混入した塊（方針1-B） ---
        # かな入力の途中で一瞬だけ半角モードに落ちると、
        #   たｂごの繋がり／他b後の繋がり／単=の繋がり
        # のように、日本語の並びに英字・記号が1文字だけ混入する。
        # 混入した文字を JIS かな配列でかなに読み替え
        # （b→こ、j→ま、=→ほ）、漢字・カタカナは読みに戻して、
        # 塊全体を読みの列として組み立て直す。
        #   単=  → たん+ほ → たんほ → （再構築）→ たんご → 単語
        #   他b後 → た+こ+ご → たこご → （再構築）→ たんご → 単語
        # **判断はここでは増やさない**: 読みが語彙にそのままあるか
        # （既存の使用実績の基準）、無ければ芯の再構築
        # （rebuild_window_core。拮抗の裁定・切り詰めの禁止まで
        # 含めた既存の唯一の関門）に委ねる。
        from kanji_guess import find_ascii_mixed_runs, \
            reading_combos_with_rank
        for a_start, a_end, chunk in find_ascii_mixed_runs(line):
            if any(not (a_end <= s or a_start >= e)
                   for s, e in halfwidth_taken + kanji_taken):
                continue
            if _is_before_honorific(line, a_end):
                continue
            # 同じ英字の2連（たｂｂご）は、次の2通りに読み替えて試す:
            #   1. 「ん」……ローマ字打ちの「Nを2回押して ん」の習慣。
            #      たｂｂご → たんご が読みそのものとして語彙に届く
            #   2. 1打に畳む……かな入力の連打。たｂｂご → たｂご と
            #      同じ扱いになり、こ→ん の再構築で届く
            _jp_ok = lambda c: (is_hiragana(c) or is_kanji(c)
                                or ('ァ' <= c <= 'ヶ') or c == 'ー')
            stray_idx = [k for k, c in enumerate(chunk) if not _jp_ok(c)]
            chunk_variants = [chunk]
            n_variant_readings = set()
            if (len(stray_idx) == 2
                    and stray_idx[1] == stray_idx[0] + 1
                    and chunk[stray_idx[0]] == chunk[stray_idx[1]]):
                p = stray_idx[0]
                chunk_n = chunk[:p] + 'ん' + chunk[p + 2:]
                chunk_one = chunk[:p] + chunk[p:p + 1] + chunk[p + 2:]
                chunk_variants = [chunk_n, chunk_one]
                for r, _k in reading_combos_with_rank(chunk_n, dict_index):
                    n_variant_readings.add(r)
            combos = []
            for cv_chunk in chunk_variants:
                combos.extend(reading_combos_with_rank(cv_chunk, dict_index))
            # 混入した文字は「押し間違い」ではなく「余計な打鍵」の
            # こともある（たんb後 ＝ たんご に b が挟まっただけ）。
            # 混入文字を取り除いた読みも、後ろに並べて試す
            # （優先は残した側。取り除いた側が上だと「単=」が
            #   「たん」に痩せる方向に倒れるが、そちらは読み3文字
            #   未満の除外で止まる）。
            chunk_wo = ''.join(c for c in chunk
                               if is_hiragana(c) or is_kanji(c)
                               or ('ァ' <= c <= 'ヶ') or c == 'ー')
            drop_combos = []
            stray = next((c for c in chunk
                          if not (is_hiragana(c) or is_kanji(c)
                                  or ('ァ' <= c <= 'ヶ') or c == 'ー')), '')
            if 0xFF01 <= ord(stray or ' ') <= 0xFF5E:
                stray = chr(ord(stray) - 0xFEE0)
            # 数字は「第1章」「その2」のように意図して打つことが
            # 圧倒的に多い。取り除いた読み（第章＝だいしょう→対象）が
            # 偶然の語に化けるため、数字では取り除く変種を作らない。
            if chunk_wo and chunk_wo != chunk and not stray.isdigit():
                drop_combos = reading_combos_with_rank(chunk_wo, dict_index)
            try_readings = ([r for r, _k in combos[:6]]
                            + [r for r, _k in drop_combos[:3]])
            # 判断は共通の解決器（語彙の完全一致 → 芯の再構築）へ。
            # 「ん」読み替え（たｈｈ→たん）だけは、2連打という強い形の
            # 証拠があるので2文字の読みでも引き当てを許す
            # （1打の「単=」→「たん」は従来どおり3文字未満を見ない）。
            surrounding = _surrounding_content_words(
                tokens, a_start, a_end,
                nearby_words=nearby_words, recent_words=recent_words)
            got = _resolve_reading_list(
                chunk, try_readings, store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                short_ok=n_variant_readings)
            if got is None:
                continue
            fixed_surface, fixed_category = got
            # 置き換えで塊が痩せすぎるものは別の語への化けとみなす
            if len(fixed_surface) * 2 < len(chunk):
                continue
            _trace('半角混入', f'{chunk!r} → {fixed_surface!r}')
            replacements.append((a_start, a_end, fixed_surface,
                                 fixed_category))
            kanji_taken.append((a_start, a_end))
    except Exception:
        pass

    hiragana_taken = []
    for run_start, run_end, run in find_hiragana_runs(line):
        # 半角入力として既に補正した範囲とは重ねない
        if any(not (run_end <= s or run_start >= e) for s, e in halfwidth_taken):
            continue

        # ローマ字入力のつもりで、かな入力モードのまま打った場合。
        # かなをキー配列で半角に戻し、ローマ字として読み直す。
        # 「もらまにみらみんななすんらのな」→「もじにゅうりょく」
        as_romaji = correct_kana_typed_as_romaji(
            run, store, find_readings, max_dist)
        if as_romaji:
            replacements.append((run_start, run_end, as_romaji, 'IT・PC操作'))
            hiragana_taken.append((run_start, run_end))
            halfwidth_taken.append((run_start, run_end))
            continue
        # 敬称の直前＝人名の可能性が高いので触らない
        if _is_before_honorific(line, run_end):
            continue
        # 伸ばし言葉・擬音の形（ー入り・小書き終わり・繰り返し）は
        # 話し言葉なので触らない（2026-08-08）
        if _is_expressive_kana_run(run):
            _trace('窓', f'{run!r} → 伸ばし・擬音の形なので触らない')
            continue
        # 直後に！？♡が付く短いかなの並びは叫び声・合図
        # （おたから！・ねこだまし！）。語彙と突き合わせない
        if (run_end - run_start) <= 5 \
                and _followed_by_shout_mark(line, run_end):
            _trace('窓', f'{run!r} → 叫び声・合図なので触らない')
            continue

        # 連続部分そのものが正しい語なら、切り分けずにそのまま残す。
        # 「どうしても」を「どうして」＋「も」と切って探索すると、
        # 「どうしても」に一致して「も」が二重になってしまう。
        if [e for e in store.lookup(run) if e['count'] >= 2]:
            continue
        if is_protected_word(run) or _is_all_auxiliary(run):
            continue
        # 既知語＋機能語の並び（はじめ＋ようか）は正しい形。
        # 全体が語彙に無くても壊れているとは言えない
        # （実機で はじめようか → はじめてか と壊れた。2026-08-08）。
        # 語尾が1文字だけの分け方では判定しない（「ほらい」が
        # ほら＋い に見えてしまう。_trailing_particle_len と同じ構図）。
        _kg = False
        for _k in range(2, len(run) - 1):
            _rest = run[_k:]
            if len(_rest) < 2 or not _is_all_functional(_rest):
                continue
            if [e for e in store.lookup(run[:_k]) if e['count'] >= 2]:
                _kg = True
                break
        if _kg:
            continue

        # 探索する範囲の候補を作る。
        #
        # ひらがなの連続には、語だけでなく前後の助詞も含まれている
        # ことが多い（「ぱそみんは」＝「ぱそこん」＋「は」）。
        # そこで「そのまま」「先頭の助詞を除く」「末尾の助詞を除く」
        # 「両端の助詞を除く」の4通りを、それぞれ独立した範囲として試す。
        #
        # 範囲を決めてから探索するので、置き換える文字列と
        # 置き換える位置が必ず対応する。
        # （以前は探索してから範囲を後追いで調整していたため、
        #   助詞が消えたり文字が二重になったりしていた）
        candidates = []
        for cut_head in (0, 1):
            for cut_tail in (0, 1):
                s = run_start + cut_head
                e = run_end - cut_tail
                if e - s < 4:
                    continue
                if cut_head and run[0] not in PARTICLES_1CHAR:
                    continue
                if cut_tail and run[-1] not in PARTICLES_1CHAR:
                    continue
                candidates.append((s, e, line[s:e]))
        # 長い範囲から順に試す（語全体として捉えられるほうを優先）
        candidates.sort(key=lambda c: -(c[1] - c[0]))

        # 各範囲について最良の候補を集め、最後に一番確からしいものを選ぶ。
        # 範囲ごとに独立して探索するので、置き換える位置と文字列は
        # 必ず対応する。
        scored = []
        for start, end, target in candidates:
            if is_protected_word(target):
                continue
            # 助動詞・活用語尾だけで構成された並びは、
            # 内容語ではなく文法的な繋がりなので触らない。
            if _is_all_auxiliary(target):
                continue
            # 助詞・活用語尾・形式名詞だけで説明が付く並びにも
            # 単語は無い（「やっていた」＝や＋っ＋ていた）。
            # _is_all_auxiliary は6文字までの制限があり、かつ
            # 助詞を含む並びを見ないため、「やっていた」が素通りして
            # 「にってい（日程）」に化けた（実機で発生）。
            if _is_all_functional(target):
                continue
            # 「送り仮名1字＋機能語」も同様（「えません」＝え＋ません。
            #   引用などで前の漢字から切り離されて単独の連続になった
            #   場合、直前が漢字という手がかりが使えないため、
            #   並びの形そのもので守る。実機で「えません」→「え欄」）。
            if _okurigana_functional_only(target):
                continue
            # 助詞・機能語の連なりでないことを確かめる。
            if any(w in target for w in PROTECTED_WORDS if len(w) >= 3):
                continue
            # そのまま正しい読みなら触らない
            if [e for e in store.lookup(target) if e['count'] >= 2]:
                continue
            # 語彙に無くても、正しい日本語として読めるなら触らない
            if _looks_like_valid_japanese(target, tokenize_fn):
                continue

            found = find_readings(target, store, max_dist=max_dist,
                                  max_edits=3)
            best = None
            for cand_reading, cost, edits in found:
                if edits == 0:
                    continue
                # 重複打鍵の訂正では1文字短くなるのが正常。
                # それ以上短くなる場合は、語を削って別の短い語に
                # すり替える誤補正の可能性が高い。
                if len(cand_reading) < len(target) - 1:
                    continue
                if len(cand_reading) > len(target) + 1:
                    continue
                if not is_plausible_typo(target, cost, edits):
                    continue
                # 促音・小書きで終わる読みは活用の断片
                # （つよかっ 等。自動学習が拾ってしまった語幹）。
                # これを当てると「つよかった」→「つよかっ」のように
                # 正しい語まで断片に化ける（実機で発生）。
                if cand_reading[-1] in _FRAGMENT_TAILS:
                    continue
                # 範囲の一部でしかない候補（切り詰め）は採らない。
                # 「たんほ」→「たん」は訂正ではなく切り落とし。
                # 連打の重複を削っただけの形（ととまる→とまる）は除く。
                if (len(cand_reading) < len(target)
                        and cand_reading in target
                        and not _is_repeat_collapse(target, cand_reading)):
                    continue
                # 長さの変わる訂正では、頭の文字が保たれていることを
                # 求める（方針:「文節・単語ごとに頭の文字と終わりの
                # 文字を重視する」）。頭が違ううえに長さも違うのは、
                # 別の語に飛んでいる可能性が高い
                # （「つわかった」→「よかった」で頭の つ が
                #   飲み込まれた。実機で発生）。
                if (len(cand_reading) != len(target)
                        and cand_reading[0] != target[0]):
                    continue
                # 末尾が助詞の範囲を、別の字で終わる読みに置き換えない。
                # 「たんほの」→「たんに」（の を丸ごと飲み込む）、
                # 「ひらがなを」→「ひらがな」（を が消える）のような、
                # 助詞ごとすり替える誤補正が実機で起きた。
                # 助詞を除いた範囲は別の候補として既に試しているので、
                # ここで断っても取りこぼしにはならない。
                if (target[-1] in PARTICLES_1CHAR
                        and cand_reading[-1] != target[-1]):
                    continue
                cand_entries = [e for e in store.lookup(cand_reading)
                                if e['count'] >= 2]
                if cand_entries:
                    best = (cand_reading, cand_entries[0], cost, edits)
                    break
            if best is None:
                continue

            cand_reading, entry, cost, edits = best
            # 読みの長さが範囲と一致するものを最優先する。
            # 長さが違うのは脱字・重複打鍵の訂正だが、
            # 「範囲の切り方（助詞を含めるか）を間違えている」
            # 場合も長さが変わるため、同じ長さで一致する範囲が
            # あるならそちらを信頼する。
            # どの範囲の切り方が正しいかは、訂正の少なさで判断する。
            # 助詞まで巻き込んだ範囲だと、助詞の分だけ余計な訂正が
            # 必要になるので、正しく切り出せた範囲のほうが
            # 訂正数もコストも小さくなる。
            scored.append((edits, cost, -(end - start), start, end,
                           cand_reading, entry['category']))

        if not scored:
            continue
        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        _, _, _, start, end, cand_reading, category = scored[0]
        # 補正結果はひらがなのまま返す（表記変換はしない）。
        replacements.append((start, end, cand_reading, category))
        hiragana_taken.append((start, end))

    # --- 漢字に隣接するひらがな連続（前回まで対象外だった領域） ---
    #
    # 実際の日本語は漢字とひらがなが交互に現れるのが普通で、
    # 「独立した連続だけを見る」従来の制限では
    # 「単語のつあがり」のような普通の形の誤字が対象にすらならなかった。
    #
    # ただし、連続全体をまるごと探索すると送り仮名を壊す
    # （「知っている」→「知せってい」。一度実装して撤回した）。
    # そこで explain_cores で「語彙・機能語で説明できない窓」だけを
    # 切り出し、その窓に限って厳格な条件で照合する:
    #   - 訂正1回・コスト小・2位との差が大きい（唯一の答え）とき
    #     だけ置き換える
    #   - 条件を満たさなければ**置き換えず**、unsure（色だけ付ける）
    #     として返す。単語として成立していないことは分かるが、
    #     何に直すべきか確信が持てない、という状態の表現。
    unsure_spans = []
    taken_all = halfwidth_taken + hiragana_taken
    for run_start, run_end, run in find_hiragana_runs(
            line, allow_adjacent_kanji=True):
        if any(not (run_end <= s0 or run_start >= e0)
               for s0, e0 in taken_all):
            continue
        if _is_before_honorific(line, run_end):
            continue
        # 伸ばし言葉・擬音の形は話し言葉なので触らない（2026-08-08）
        if _is_expressive_kana_run(run):
            _trace('窓', f'{run!r} → 伸ばし・擬音の形なので触らない')
            continue
        # 直後に！？♡が付く短いかなの並びは叫び声・合図
        if (run_end - run_start) <= 5 \
                and _followed_by_shout_mark(line, run_end):
            _trace('窓', f'{run!r} → 叫び声・合図なので触らない')
            continue
        # 窓の切り出しは、形態素解析の分割から見る token_windows を
        # 第一候補にする（実機の janome の「短い断片が連続する」
        # 振る舞いに基づく。語彙の規模に左右されない）。
        # 解析が窓を出さないときだけ、語彙ベースの explain_cores を
        # 控えとして使う。
        run_after_kanji = (run_start > 0 and is_kanji(line[run_start - 1]))
        windows = token_windows(run, tokenize_fn)
        source = 'token_windows'
        if not windows:
            windows = explain_cores(run, store,
                                    after_kanji=run_after_kanji)
            source = 'explain_cores'
        if not windows:
            # どちらの切り出しも窓を出さなかった。
            #
            # explain_cores は「短い既知語と機能語だけで全部説明が
            # 付いた」ときに窓を出さない。語彙が7000語を超えると、
            # 壊れた列でも短い語の寄せ集めで説明が付いてしまう
            # （「ちながり」が「な」「がり」等で埋まる。実機で確認）。
            # 説明が付いたことを「正しい」の根拠にできない以上、
            # かな連続そのものを窓として最後にもう一度見る。
            #
            # 直すかどうかは、これまでどおり芯の再構築
            # （rebuild_window_core）の関門が決める。そこは
            # 「語彙にある読みは触らない」「正しく読める芯は
            # 触らない」を通すので、正しい文が素通りする。
            windows = [(0, len(run))]
            source = 'かな連続そのもの'
        _trace('かな連続', f'{run!r} 窓({source})='
               f'{[run[x:y] for x, y in windows]}')
        for w_s, w_e in windows:
            # 窓の頭が小書きかな・促音・長音で始まるのは、形態素解析が
            # 語の途中で切った印（「にゅうりょく」→ に/ゅうりょく）。
            # そのまま照合すると、正しい語の断片を「直して」しまう
            # （実機で「にゅうりょく」が壊れた）。前の文字を取り込んで
            # 窓を語の頭まで広げる。
            while (w_s > 0 and line[run_start + w_s] in _SMALL_KANA_HEADS
                   and is_hiragana(line[run_start + w_s - 1])):
                w_s -= 1
            a, b = run_start + w_s, run_start + w_e
            window = line[a:b]
            if is_protected_word(window) or _is_all_auxiliary(window):
                _trace('窓', f'{window!r} → 守る語／助詞だけなので対象外')
                continue
            # 窓そのものが語彙にある読みなら、打ち間違いではない。
            # （芯の再構築には同じ関門があるが、従来の探索の側には
            #   無かった。窓を広げた結果ここに来る「にゅうりょく」の
            #   ような正しい語を、1文字違いの別語に化けさせない。）
            try:
                if any(e['count'] >= 2 for e in store.lookup(window)):
                    _trace('窓', f'{window!r} → この読みが語彙にあるので'
                                 f'触らない')
                    continue
            except Exception:
                pass
            # 機能語だけで説明が付く窓は、そもそも単語が無い。
            # 「ではなく」を「できなく」に直すような破壊が起きる
            # （janome の無い環境では、読める窓かどうかの判定
            #   （_looks_like_valid_japanese）が働かないため、
            #   ここで明示的に守る必要がある）。
            if _is_all_functional(window):
                _trace('窓', f'{window!r} → 機能語だけで説明が付くので対象外')
                continue
            # 「送り仮名＋機能語」だけの窓にも単語は無い
            # （見えません の「えません」→「えびせん」を防ぐ。
            #   芯の再構築側にも同じ関門があるが、従来の探索が先に
            #   走るので、窓の段階でも止める必要がある）。
            # 直前が漢字かどうかは条件にしない。引用（「えません」）の
            # ように前の漢字から切り離された形でも並び自体は同じで、
            # 実機で「えません」→「え欄」と壊れた。
            # 直前が漢字の窓は、先頭の送り仮名をどのかなでも許す
            # （づかれず・すときに・んでいた・こりやすい。実機で
            #   つかれた／いっきに／えでぃった 等に壊れた）。
            window_after_kanji = (a > 0 and is_kanji(line[a - 1]))
            if _okurigana_functional_only(window,
                                          any_head=window_after_kanji):
                _trace('窓', f'{window!r} → 送り仮名＋機能語なので対象外')
                continue
            # 窓を右に1〜2文字延ばすと「送り仮名＋機能語」で説明が
            # 付くなら、窓の切り出しが次の語の途中で止まっただけで、
            # そこに直すべき単語は無い。
            # 「押すとそのホットキー」で窓が「すとそ」になり
            # （「その」が形態素の途中で切れた）、「すとあ(ストア)」に
            # 化ける誤補正が実機で起きた。すとそ＋の＝す＋と＋その で
            # 説明が付くので、切り出し不良と分かる。
            ext_functional = False
            for ext in (1, 2):
                if b + ext <= len(line) and all(
                        is_hiragana(c) for c in line[b:b + ext]):
                    if _okurigana_functional_only(
                            line[a:b + ext], any_head=window_after_kanji):
                        ext_functional = True
                        break
            if ext_functional:
                _trace('窓', f'{window!r} → 右に延ばすと送り仮名＋機能語に'
                             f'なる（切り出し不良）ので対象外')
                continue
            # 窓が「既知語＋短い残り」の形なら触らない。
            # 「よろしくお（ねがいします）」の窓で「お」を削って
            # 「よろしく」に一致してしまう、という切り詰め型の
            # 誤補正が起きた。残りの1〜2文字は次の語の頭
            # （お＝おねがい の頭）である可能性が高い。
            # 補正も色付けもせず、そのまま残す。
            def _known(frag):
                try:
                    return any(e['count'] >= 2 for e in store.lookup(frag))
                except Exception:
                    return False
            edge_word = False
            for ln in range(len(window) - 1, 1, -1):
                if len(window) - ln > 2:
                    break
                if _known(window[:ln]) or _known(window[len(window) - ln:]):
                    edge_word = True
                    break
            # edge_word のときは、従来の探索（find_readings）だけを
            # 見送る。切り詰め型の誤補正はそちらで起きたものであり、
            # 芯を切り出して組み直す経路（rebuild_window_core）は
            # 「元の語の一部でしかない候補」を別途はじくので、
            # ここで窓ごと捨てる必要は無い。
            #
            # 窓ごと捨てていたために、**語彙が育つほど直せなくなる**
            # という逆転が起きていた。7379語の実機では
            # 「たんほの」の先頭「たん」が語彙にあるというだけで
            # 窓が捨てられ、この経路が丸ごと働いていなかった
            # （実機の診断で判明）。
            # 形態素解析で正しい日本語として読める窓は触らない
            # （補正もせず、色も付けない）。
            # janome のある実機では、これが誤検知（ままでよい・
            # したほうがよい 等の正しい表現への色）を防ぐ主力になる。
            # 逆に「たんほ」「ほらい」のような壊れた列は読めないので、
            # 色や補正の対象として残る。
            if _looks_like_valid_japanese(window, tokenize_fn):
                _trace('窓', f'{window!r} → 正しい日本語として読めるので触らない')
                continue
            chosen = None
            found = [] if edge_word else find_readings(
                window, store, max_dist=max_dist, max_edits=2)
            found = [(r, c, e2) for r, c, e2 in found if r != window]
            if found:
                r0, c0, e0 = found[0]
                second = found[1][1] if len(found) > 1 else 99.0
                if (e0 == 1 and c0 <= 1.5 and second - c0 >= 0.4
                        and len(r0) >= 3
                        and abs(len(r0) - len(window)) <= 1
                        and any(en['count'] >= 2
                                for en in store.lookup(r0))):
                    chosen = r0
            if chosen is None and input_method == 'romaji':
                # ローマ字入力者なら、QWERTY の隣接キーとして照合し直す
                chosen = romaji_window_match(window, store)
            if chosen and chosen != window and not (
                    a > 0 and chosen == line[a - 1] + window):
                # ひらがなで打たれたものはひらがなのまま直す（方針どおり）。
                # ただし「直前の文字を足しただけ」の候補は、窓の切り出しが
                # 語の途中から始まっただけで、文字はもう書かれている
                # （「通常のひらがな」の窓「らがな」に「ひらがな」を
                #   当てると ひひらがな になる。実機で発生）。
                _trace('窓', f'{window!r} → 従来の探索で {chosen!r} に直す')
                replacements.append((a, b, chosen, 'かな入力'))
                continue
            # ここまでで直せなかった窓を、機能語を剥がした「芯」に
            # 絞ってもう一度照合する（rebuild_window_core）。
            # 隣接キーで説明の付かない取り違え（たんほ→たんご）や、
            # 助詞がくっついたままの窓（のつあがり）は、この経路で
            # ようやく届く。判断はこの関数ひとつに閉じてあり、
            # 満たさなければこれまでどおり unsure（色だけ）に落ちる。
            # 芯を探すときは、窓の末尾を **かな連続の終わりまで**
            # 伸ばして渡す。窓の切り出し（explain_cores）は末尾の
            # 機能語を落とすが、壊れた語の最後の1文字がたまたま
            # 活用語尾と同じ字のことがある（「ほらい」の「い」は
            # 「補正（ほせい）」の一部であって語尾ではない）。
            # 落としたままだと芯が「ほら」になり、直す先に届かない。
            # どこを芯にするかは window_cores が改めて決める。
            window_ext = line[a:max(b, run_end)]
            fixed = rebuild_window_core(
                window_ext, store, tokenize_fn, context_vec=context_vec,
                surrounding_words=_surrounding_content_words(
                    tokens, a, b, nearby_words=nearby_words,
                    recent_words=recent_words),
                after_kanji=(a > 0 and is_kanji(line[a - 1])))
            if fixed is not None and (
                    a + fixed[0] == 0
                    or fixed[2] != line[a + fixed[0] - 1]
                    + window_ext[fixed[0]:fixed[1]]):
                c_s, c_e, core_fix = fixed
                _trace('窓', f'{window_ext!r} → 芯の再構築で '
                             f'{window_ext[c_s:c_e]!r} を {core_fix!r} に直す')
                replacements.append((a + c_s, a + c_e, core_fix, 'かな入力'))
            elif not edge_word:
                _trace('窓', f'{window!r} → 直せないので色だけ付ける')
                # edge_word（既知語＋短い残り）の窓は、直せなかった
                # ときに色も付けない。「よろしくお（ねがいします）」の
                # ように、残りが次の語の頭であるだけで壊れていない
                # 可能性が高いため（実機からの指定）。
                unsure_spans.append((a, b))
            else:
                _trace('窓', f'{window!r} → 直せず、既知語＋短い残りの形'
                             f'なので色も付けない')

    spans = find_editable_spans(line, tokens)

    for start, end, surface, reading, is_known_word in spans:
        # 既に補正した範囲（ひらがな連続・半角入力）とは重複させない
        if any(not (end <= s or start >= e)
               for s, e in hiragana_taken + halfwidth_taken + kanji_taken):
            continue
        # 語尾に助動詞・活用語尾が付いている場合は、
        # 語幹だけを判断対象にして語尾はそのまま残す。
        stem_surface, tail_surface = split_protected_tail(surface)
        if tail_surface:
            # 語尾を切り離した結果、語幹が短すぎるなら触らない。
            # 断片は偶然どれかの語に一致しやすく誤爆の元になる。
            if len(stem_surface) < 2:
                continue
            # 語尾を切り離した場合、読みの側も対応させる必要があるが、
            # 表記と読みの対応を正確に取るのは難しいため、
            # 語尾を持つ語はこのエンジンでは補正対象にしない。
            # （「引き下げました」→「引き下また」のような破壊を防ぐ）
            continue

        # この語の周りにある内容語（文脈スコアの材料）。
        # 同じ行の前後を最優先し、直前の変換履歴・上下の行と続ける
        # （_surrounding_content_words が並び順で優先度を表す）。
        surrounding = None
        if context_vec is not None:
            surrounding = _surrounding_content_words(
                tokens, start, end,
                nearby_words=nearby_words, recent_words=recent_words)

        result = evaluate_candidate(surface, reading, store, context_vocab,
                                    find_readings, max_dist,
                                    is_known_word=is_known_word,
                                    context_vec=context_vec,
                                    surrounding_words=surrounding)
        if result is None:
            continue
        new_surface, category, evidence = result
        if evidence >= EVIDENCE_NONE:
            continue

        # ひらがなだけで書かれた語は、文法的な語や慣用表現である
        # 可能性が高い（「そのため」「おはよう」「あるいは」など）。
        # 内容語であれば通常は漢字・カタカナで書かれるため、
        # ひらがなだけの語は文脈の裏付けが無い限り補正しない。
        # 機能語をすべて列挙して守るのは現実的でないので、
        # 「表記の種類」という構造的な条件で判断する。
        if all(is_hiragana(c) for c in surface):
            if evidence != EVIDENCE_CONTEXT:
                continue

        # 漢字・カタカナで書かれていたものを、ひらがなだけの表記に
        # 置き換えない（「理論寄り」→「理論より」、
        # 「人向け」→「人見る」のような改悪を防ぐ）。
        # 漢字で書いたということは、書き手がその表記を選んだ
        # ということなので、その判断を尊重する。
        has_kanji_before = any(is_kanji(c) or is_katakana(c) for c in surface)
        all_kana_after = all(is_hiragana(c) for c in new_surface)
        if has_kanji_before and all_kana_after:
            continue

        # 逆に、ひらがなで書かれていたものを漢字・カタカナに
        # 変換することもしない（「もじ」→「文字」）。
        # このアプリは誤字を直すためのものであり、
        # 変換の仕事はIMEに任せる。ひらがなで入力されたものは
        # ひらがなのまま、誤字だけを直して返す。
        all_kana_before = all(is_hiragana(c) for c in surface)
        has_kanji_after = any(is_kanji(c) or is_katakana(c)
                              for c in new_surface)
        if all_kana_before and has_kanji_after:
            continue

        # 補正の結果、文字数が大きく減る場合は採用しない。
        # 語を削る方向の補正は、正しい文を壊す典型的なパターン。
        if len(new_surface) < len(surface) - 1:
            continue
        replacements.append((start, end, new_surface, category))

    if not replacements:
        if unsure_spans:
            out = dict(empty)
            out['unsure_spans'] = unsure_spans
            return out
        return empty

    # 最終確認: 置換後の長さが元と大きく食い違うものは採用しない。
    # 誤打の訂正は1〜2文字の違いに収まるはずで、
    # それ以上ずれる場合は範囲の取り方か候補選びが誤っている。
    # 文字が二重になる・消えるといった破綻を構造的に防ぐための砦。
    checked = []
    for start, end, new_surface, category in replacements:
        original = line[start:end]
        # ユーザーが「この補正は不要」と判断した置換は行わない。
        # 統計や辞書より、本人が明示した判断を優先する。
        # 補正経路は複数あるが、ここは全ての置換が必ず通る最終検査なので、
        # ここで見ることで判断経路を増やさずに済む（SPEC.md の設計方針）。
        if decisions is not None and decisions.blocks(original, new_surface):
            continue
        # 半角・ローマ字をかなに直した箇所は、文字数が大きく変わるのが
        # 正常なので長さの検査から外す（mojinyuuryoku → もじにゅうりょく）。
        is_halfwidth = any(not (end <= s or start >= e)
                           for s, e in halfwidth_taken)
        if not is_halfwidth and abs(len(new_surface) - len(original)) > 2:
            continue
        # 置換によって、元には無かった同じ文字の連続が生まれた場合は
        # 範囲の取り方が誤っている（助詞の切り離しに失敗して
        # 文字が二重になった等）。採用しない。
        if _has_new_repetition(original, new_surface):
            continue
        checked.append((start, end, new_surface, category))
    replacements = checked
    if not replacements:
        if unsure_spans:
            out = dict(empty)
            out['unsure_spans'] = unsure_spans
            return out
        return empty

    replacements.sort(key=lambda r: r[0])
    out = []
    details = []
    result_spans = []
    original_spans = []
    cursor = 0
    out_len = 0
    for start, end, new_surface, category in replacements:
        if start < cursor:
            continue
        if start > cursor:
            out.append(line[cursor:start])
            out_len += start - cursor
        original = line[start:end]
        details.append((original, new_surface, category))
        result_spans.append((out_len, out_len + len(new_surface)))
        original_spans.append((start, end))
        out.append(new_surface)
        out_len += len(new_surface)
        cursor = end
    out.append(line[cursor:])
    corrected = ''.join(out)

    # 置き換えが確定した範囲と重なる unsure は取り下げる
    final_unsure = [
        (a, b) for a, b in unsure_spans
        if not any(not (b <= s0 or a >= e0) for s0, e0 in original_spans)]

    return {
        'original': line,
        'corrected': corrected,
        'changed': corrected != line,
        'details': details,
        'unsure_spans': final_unsure,
        'spans': result_spans,
        # 'details' と同じ順番で、元のテキスト上での置換範囲。
        # 通常の表示（補正後のテキストを見せる）では使わないが、
        # 「自動では直さず、疑わしい箇所に色をつけるだけ」の表示
        # （統合レイアウト・簡易入力ウィンドウ向け）で使う。
        # spans が補正後テキスト上の位置なのに対し、
        # こちらは常に元のテキスト（line）上の位置になる。
        'original_spans': original_spans,
    }


# ============================================================
# 形態素解析との接続（アダプタ）
# ============================================================

def make_tokenizer(store):
    """
    このエンジンが使うトークナイザを作る。

    janome があればそれを使い、無ければ文字種による簡易分割で代替する。
    どちらの場合も
      [(表記, 品詞, 読み, 開始, 終了, 読みが確定か), ...]
    の形式で返す。
    """
    try:
        from morphology import tokenize as _mtok, HAS_JANOME
    except Exception:
        HAS_JANOME = False
        _mtok = None

    def _from_janome(line):
        out = []
        for t in _mtok(line):
            # 品詞は「大分類:細分類」の形で渡す。
            # 「接尾」「非自立」などの細分類を落とすと、
            # 「〜向け」「〜寄り」「〜か月」「〜済み」のような
            # 単独では意味を成さない語まで補正対象になってしまう。
            pos = t.pos
            sub = getattr(t, 'pos_sub', '')
            if sub:
                pos = f'{pos}:{sub}'
            out.append((t.surface, pos, t.reading or '',
                        t.start, t.end, bool(t.has_reading and t.reading)))
        return out

    def _fallback(line):
        """
        janome が無い場合の簡易分割。

        ひらがな連続は correct_line 側が別途まとめて扱うので、
        ここでは文字種の切れ目だけで区切る。
        助詞での細かい分割はしない（語を壊す原因になるため）。
        """
        out = []
        i, n = 0, len(line)
        while i < n:
            ch = line[i]
            if not is_japanese_word_char(ch):
                out.append((ch, '記号', ch, i, i + 1, False))
                i += 1
                continue
            if is_hiragana(ch):
                j = i
                while j < n and is_hiragana(line[j]):
                    j += 1
                w = line[i:j]
                pos = '助詞' if is_protected_word(w) else '名詞'
                # 「辞書にあるか」は、語彙ストアに登録されているか、
                # あるいは保護対象の機能語であるかで判断する。
                # ひらがなというだけで「辞書にある」と答えてしまうと、
                # 誤字も正しい語とみなされ、補正が一切効かなくなる。
                known = bool(store.lookup(w)) or is_protected_word(w)
                out.append((w, pos, w, i, j, known))
                i = j
                continue
            j = i
            while j < n and (is_kanji(line[j]) or is_katakana(line[j])):
                j += 1
            w = line[i:j]
            rd = store.reading_of(w) or ''
            out.append((w, '名詞', rd, i, j, bool(rd)))
            i = j
        return out

    return _from_janome if HAS_JANOME else _fallback
