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

import os
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

# そのうち、**前の字と合わせて1つの音になる**もの（項目48-DM）。
# 促音「っ」は入れない（単独で1拍ある）。
_MORA_TAIL_KANA = _SMALL_KANA_HEADS - {'っ'}

# 語の末尾に立てないかな。読みがこれで終わるのは活用の断片
# （つよかっ・打っ 等）で、独立した語として当ててはいけない。
#
# **拗音（ゃゅょ）は外した**（項目48-GK・2026-08-19）。
# `っ` は確かに活用の断片の印だが（`やっ` `間違っ` `拾っ`
# ——語彙に 432 件、どれも自動学習が拾った語幹）、
# **拗音で終わる読みは、ほとんどが普通の語**だった:
#
#     ょ 160件  辞書1189 ／ 解除1136 ／ 削除988 ／ 場所928 ／ 箇所723
#     ゃ 250件  後者62 ／ 自動車39 ／ 前者34 ／ 忍者33 ／ 神社32
#     ゅ 124件  クラッシュ545 ／ キャッシュ541 ／ 着手71 ／ 特殊39
#
# **534件が、直し先としてまるごと見えていなかった。**
#
#     「いはしょ」と書きました。（正解 いばしょ＝居場所・37回）
#       → `いばしょ` は `ょ` で終わるので候補から外れ、
#         **`いしょく`（移植・2回）**に化けていた
#
# 小書き母音（ぁぃぅぇぉ）は残す。`ボディ` `カフェ` のような
# 外来語はあるが 136件と少なく、そちらは外来語の道が持っている。
_FRAGMENT_TAILS = set('っぁぃぅぇぉ')

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
    # **未然形・命令形・意向形が抜けていた**（項目48-CC・2026-08-13）。
    # 「〜してしまわない」「〜してしまえば」「〜してしまおう」。
    # 芯「してしま」が語彙の「親しま（したしま・7回）」に化けた
    # （散文の材料 357行目「けん にしてしまわないため）」）。
    # 上の「ハテ島に化けた」と**同じ型で、活用形が1つ足りなかった**
    # だけ。回数の敷居で止めようとしたが、**初期状態は全語が
    # count<=3 なので敷居は成り立たない**（実測: count>=20 は0語）。
    # 学び12。**規模に依らない「形」で止めるのが正しい。**
    'しまわ', 'しまえ', 'しまお', 'しまえる', 'しまおう',
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
    # **剥がした先頭を、1つだけ戻す**（項目48-GH）。
    #
    # 直前が漢字なら先頭の機能語を剥がす（送り仮名とみなす）。
    # だが**語の頭が、たまたま活用語尾と同じ字**のことがある:
    #
    #     昨日こもれひを見ました。（正解 こもれび）
    #       分解 [('こ','func'), ('もれ','word'), ('ひ','skip'), ('を','func')]
    #       → 窓は `もれひ`（`こ` は活用語尾として剥がされた）
    #       → 芯 `もれひ` → **`もひ`** に化ける
    #
    #     窓が `こもれひ` なら:
    #       find_known_readings_flex('こもれひ') → **こもれび 0.40**
    #
    # **剥がした形は失われない。** 窓を広げても、`window_cores` が
    # `after_kanji` のときに先頭を剥がした芯も一緒に出す
    # （項目48-DY）。**窓を広げるほうが、持っている手が増える。**
    #
    # 戻すのは**2文字まで。ただし戻すなら全部戻す**。
    #
    # 最初は「1つの塊だけ」戻したが、先頭に機能語が**2つ**並ぶと
    # 片方だけ戻って**語の途中から始まる窓**ができ、壊した:
    #
    #     昨日ばたふいらを見ました。（正解 ばたふらい）
    #       分解 [('ば','func'), ('た','func'), ('ふい','word'), …]
    #       1つ戻す → 窓 `たふいら`  ← ば が無い。直せなくなった
    #       全部戻す → 窓 `ばたふいら` ← これなら届く
    #
    # **中途半端に戻すのがいちばん悪い。**
    #
    # **本物の助詞は戻さない。** 剥がした頭が助詞なら、それは
    # 直前の漢字語に付いた助詞であって、語の一部ではない:
    #
    #     単語のつあがり（正解 つながり）
    #       `の` を戻すと窓が `のつあがり` になり、**直らなくなる**
    #       （`tests_mock` の「直前が漢字なら窓の先頭を剥がす」が
    #         これを見張っていた。**janome の無い経路**なので
    #         readcheck・実機メモでは1件も動かず、危うく通した）
    #
    # 戻すのは**活用語尾としてだけ説明が付いた頭**に限る
    # （`こ` は `AUXILIARY_TAILS` に在るが助詞ではない）。
    if after_kanji and 0 < w_start <= 2 \
            and min_len <= w_end <= max_len:
        _head = run[:w_start]
        if not (_head in PARTICLES_MULTI
                or any(c in PARTICLES_1CHAR for c in _head)):
            w_start = 0
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

# キーの位置は**一度だけ作る**（項目48-BO）。
# 以前は `_qwerty_adjacent` の中で毎回26件の表を作り直していた。
# ローマ字入力の人のメモ120行を測ったら、この関数が **451,910回**
# 呼ばれていて、表づくりだけで解析時間の **31%** を使っていた。
# 中身は変えていないので、答えは1つも変わらない。
_QWERTY_POS = {ch: (row_i, col_i)
               for row_i, row in enumerate(_QWERTY_ROWS)
               for col_i, ch in enumerate(row)}

# 隣り合うかどうかも一度だけ数えておく（26×26＝676通り）。
# 上の表を引いて引き算するより、組で引いたほうが速い。
_QWERTY_NEAR = frozenset(
    (a, b)
    for a, pa in _QWERTY_POS.items()
    for b, pb in _QWERTY_POS.items()
    if a != b and abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1)


def _qwerty_adjacent(a, b):
    """QWERTY 配列で a と b が隣り合うキーか。"""
    return (a, b) in _QWERTY_NEAR


# --- 項目48-FX: 「1文字違い」を採ってよいか（隣接キーか）---
#
# うにさんの指定（2026-08-19）:
#
# > 「1文字違うだけでは補正しません、その違いが隣接キーかどうか。
# >   隣接判定はかな入力とローマ字入力で変わる。」
#
# **かな入力とローマ字入力では、隣が違う。** 同じ1文字違いでも:
#
#     ご ↔ ほ   かな入力  こ(B) と ほ(-) は遠い    → 採らない
#               ローマ字  go と ho は g と h が隣  → 採ってよい
#     ざ ↔ は   かな入力  ざ＝さ＋゛ の2打鍵。遠い → 採らない
#               ローマ字  za と ha は z と h が遠い → 採らない
#
# `find_similar_readings` は今までどちらの人にも**かな配列の
# 隣接だけ**で答えていた（`_sub_cost` → `kana_key_distance`）。
# 入力方式は `correct_line` まで届いていたのに、探索には
# 渡っていなかった。
#
# **ただし、次の2つは配列と関係なく「1回の誤り」として通す**:
#   - 小書き ⇔ 大書き（同じキーの Shift）
#   - 濁点・半濁点の付け外し（SPEC の「誤打の種類」その4）
# どちらも SPEC が最初から誤打の型として挙げているもので、
# 配列の話ではない。
_ADJ_KANA_MAX = 1.6      # `nearby_candidates` の既定と同じ「隣」の広さ


def adjacent_slip(a, b, input_method='kana'):
    """
    その1文字の違いは、**隣のキーを押した1回の誤り**で説明が付くか。

    付かないなら、それは打ち間違いではなく別の語である。
    """
    if a == b:
        return True
    # **かな以外は塞がない。** 語彙には `en:claude` のような英語の
    # 読みも入っている（42件）。英字の打ち間違いは別の道
    # （`loanword` / `seed_english`）が見るので、ここでは判断しない。
    if not (is_hiragana(a) or a == 'ー') \
            or not (is_hiragana(b) or b == 'ー'):
        return True
    try:
        from kana_layout import (SMALL_KANA_PAIR, DAKUTEN_BASE,
                                 kana_key_distance)
    except Exception:
        return True          # 判定できないなら塞がない
    # 小書き ⇔ 大書き（同じキー・Shift の押し忘れ）
    if SMALL_KANA_PAIR.get(a) == b:
        return True
    # 濁点・半濁点の付け外し（同じキー・印キーの押し忘れ）
    if DAKUTEN_BASE.get(a, a) == DAKUTEN_BASE.get(b, b):
        return True
    if input_method == 'romaji':
        ra = _KANA_TO_ROMAJI.get(a)
        rb = _KANA_TO_ROMAJI.get(b)
        if not ra or not rb:
            return False
        if ra == rb:
            return True
        if len(ra) == len(rb):
            diff = [(x, y) for x, y in zip(ra, rb) if x != y]
            return (len(diff) == 1
                    and _qwerty_adjacent(diff[0][0], diff[0][1]))
        # **ローマ字では「かな1文字の違い」が脱字のことがある**
        # （項目48-FY・うにさんの指定・2026-08-19
        #   「つあがり、これはローマ字限定補正です。
        #     かな入力では対象外です」）。
        #
        #     つあがり ／ つながり   かな   あ(3) と な(U) は遠い → 対象外
        #                            ローマ字 tu**a**gari ／ tu**na**gari
        #                                     ＝ `n` の**脱字**（1打の押し忘れ）
        #
        # 置き換えではないので、「隣接キーか」を問う話ではない。
        # SPEC の「誤打の種類」の**別の型**（脱字・余分な打鍵）であり、
        # そちらは1回の誤りとして最初から通してよい。
        # かな入力ではかな1文字＝1打なので、この道は無い。**それが
        # 「ローマ字限定」の意味。**
        if abs(len(ra) - len(rb)) != 1:
            return False
        short, long_ = (ra, rb) if len(ra) < len(rb) else (rb, ra)
        return any(long_[:i] + long_[i + 1:] == short
                   for i in range(len(long_)))
    return kana_key_distance(a, b) <= _ADJ_KANA_MAX


_ADJ_GATE = (os.environ.get('CN_ADJ_GATE', '1') != '0')


def _adj_ok_one_char(typed, chosen, input_method):
    """
    **決まった直しが「1文字違うだけ」なら、隣のキーかを見る**
    （項目48-FX）。

    1文字違いでないもの（脱字・重複・入れ替え・2箇所以上）は
    ここでは何も言わない（True）。入れ替え（順序違い）は
    同じ長さだが**2箇所**違うので、これも当たらない。
    """
    if not _ADJ_GATE:
        return True
    if len(typed) != len(chosen):
        return True
    diff = [(a, b) for a, b in zip(typed, chosen) if a != b]
    if len(diff) != 1:
        return True
    return adjacent_slip(diff[0][0], diff[0][1], input_method)


def kana_to_romaji(kana):
    return ''.join(_KANA_TO_ROMAJI.get(c, '?') for c in kana)


# ローマ字列の距離で使う値。**下界の見積もりと必ず揃えること**
# （項目48-BR。ばらばらに書くと、下界が下界でなくなる）。
_ROM_GAP = 0.9          # 1文字ぶんの挿入・削除
_ROM_SUB_NEAR = 0.5     # 隣のキーへの置き換え（いちばん安い置換）
_ROM_SUB_FAR = 1.2      # 離れたキーへの置き換え
_ROM_SWAP = 0.6         # 隣り合う2文字の入れ替え


def romaji_distance_floor(a, b):
    """
    `_romaji_distance` の**下界**を、表を作らずに見積もる（項目48-BR）。

    本物の距離は必ずこれ以上になる（＝これを超えるものは、
    DP を掛けるまでもなく届かない）。使うのは2つだけ:

      長さの差    1文字ずれるたびに、必ず挿入か削除が要る（0.9）
      文字の個数  相手に無い文字は、置き換えか消すかのどちらか。
                  いちばん安いのは隣のキーへの置き換え（0.5）

    入れ替え（0.6）は**文字の顔ぶれを変えない**ので、この下界は
    入れ替えを取りこぼさない。

    実測（うにさんのメモ300行・ローマ字入力）:

        DP を掛けていた相手   180,882
        長さの下界で          92,708
        **文字の個数まで見て   1,775（99%減）**

    `romaji_window_match` は語彙の**全部**に DP を掛けていた。
    ローマ字入力の解析時間の **72%** がここだった。
    """
    la, lb = len(a), len(b)
    floor = abs(la - lb) * _ROM_GAP
    avail = {}
    for ch in a:
        avail[ch] = avail.get(ch, 0) + 1
    extra_b = 0
    for ch in b:
        k = avail.get(ch, 0)
        if k:
            avail[ch] = k - 1
        else:
            extra_b += 1
    extra_a = 0
    for k in avail.values():
        extra_a += k
    unmatched = extra_a if extra_a > extra_b else extra_b
    by_chars = unmatched * _ROM_SUB_NEAR
    return floor if floor > by_chars else by_chars


def _romaji_distance(a, b):
    """ローマ字列どうしの重み付き編集距離（QWERTY隣接の置換を安く）。"""
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 99.0
    dp = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        dp[i][0] = i * _ROM_GAP
    for j in range(lb + 1):
        dp[0][j] = j * _ROM_GAP
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                sub = 0.0
            elif _qwerty_adjacent(a[i - 1], b[j - 1]):
                sub = _ROM_SUB_NEAR
            else:
                sub = _ROM_SUB_FAR
            dp[i][j] = min(dp[i - 1][j - 1] + sub,
                           dp[i - 1][j] + _ROM_GAP,
                           dp[i][j - 1] + _ROM_GAP)
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + _ROM_SWAP)
    return dp[la][lb]


# 読み → ローマ字綴り の控え（項目48-GD）。
# **語の顔ぶれが変わったときだけ作り直す**（`shape_revision`。
# 使用回数が増えただけでは作り直さない）。
_ROM_TABLE_CACHE = {}


def _romaji_reading_table(store):
    """
    語彙の読みを、**あらかじめローマ字に直して**並べたもの。

        [(読み, 読みの長さ, ローマ字綴り), ...]

    `romaji_window_match` は1回の呼び出しで語彙の全部を見る。
    そこで毎回 `kana_to_romaji` を掛け直していた（1回の照合で
    5,346 回・実測）。**読みからローマ字は純粋な計算**なので、
    語の顔ぶれが変わったときに1度だけ作れば足りる。

    ローマ字に直せない読み（`?` が混じる）はここで落とす。
    元は輪の中で落としていたが、**どの門も「かつ」で繋がって
    いる**ので、先に落としても後で落としても結果は同じ。
    """
    key = store.shape_revision()
    got = _ROM_TABLE_CACHE.get(id(store))
    if got is not None and got[0] == key:
        return got[1]
    out = []
    try:
        readings = store.all_readings()
    except Exception:
        readings = ()
    for reading in readings:
        r_rom = kana_to_romaji(reading)
        if '?' in r_rom:
            continue
        out.append((reading, len(reading), r_rom))
    _ROM_TABLE_CACHE.clear()
    _ROM_TABLE_CACHE[id(store)] = (key, out)
    return out


def _romaji_floor_prepared(w_count, la, b):
    """`romaji_distance_floor` と**同じ額**を、打った側を数え直さずに出す。

    打った側（`a`）の文字の個数は1回の照合の中で変わらないので、
    輪の外で1度だけ数えておく（項目48-GD）。
    **式は `romaji_distance_floor` と1文字も変えないこと**
    （項目48-BR。下界がずれると取りこぼす）。
    """
    lb = len(b)
    floor = (la - lb if la > lb else lb - la) * _ROM_GAP
    avail = dict(w_count)
    extra_b = 0
    for ch in b:
        k = avail.get(ch, 0)
        if k:
            avail[ch] = k - 1
        else:
            extra_b += 1
    extra_a = 0
    for k in avail.values():
        extra_a += k
    unmatched = extra_a if extra_a > extra_b else extra_b
    by_chars = unmatched * _ROM_SUB_NEAR
    return floor if floor > by_chars else by_chars


def romaji_window_match(window, store, max_dist=0.6, min_reading_len=3):
    """
    窓のかな列を、ローマ字の打ち間違いとして語彙の読みと照合する。

    QWERTY で隣のキーを押した誤り（h→g で「ほ」→「ご」等）を、
    かな1文字の置換として捉え直す。確実な一致（唯一で距離が小さい）
    のときだけ読みを返し、曖昧なら None。

    **安い門から順に置くこと**（項目48-GD。48-GA と同じ話）。
    以前は「使用実績（`store.lookup`）」を下界より**先**に見ていて、
    1回の照合で 11,569 回引いていた。下界は 99% を落とすので、
    後ろに回すと引く回数が 57 回になる。**どの門も「かつ」で
    繋がっているので、順番を変えても結果は1つも変わらない。**
    """
    w_rom = kana_to_romaji(window)
    if '?' in w_rom:
        return None
    # 拾う範囲（曖昧さを見るために本命より少し広く取る）
    limit = max_dist + 0.4
    w_len = len(window)
    w_rom_len = len(w_rom)
    # 打った側の文字の個数は**輪の外で1回だけ**数える
    w_count = {}
    for ch in w_rom:
        w_count[ch] = w_count.get(ch, 0) + 1
    hits = []
    for reading, r_len, r_rom in _romaji_reading_table(store):
        if r_len < min_reading_len or r_len > w_len + 1:
            continue
        if r_len - w_len > 1 or w_len - r_len > 1:
            continue
        # **表を作る前に、届かない相手を落とす**（項目48-BR）。
        # 取りこぼしの無い下界なので、答えは1つも変わらない。
        if _romaji_floor_prepared(w_count, w_rom_len, r_rom) > limit:
            continue
        if not any(e['count'] >= 2 for e in store.lookup(reading)):
            continue
        d = _romaji_distance(w_rom, r_rom)
        if d <= limit:
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


# --- 項目48-EL: 長音の書き分けのゆれ（2026-08-17・実機の持ち越し）---
#
# 第38回からの持ち越し「`メニューとめにゅう → つにゅう`（既存の
# 不具合）」を追ったら、**長音の書き分け**だった。
#
#     store.reading_of('メニュー')  →  'めにゅー'   ← しまってある形
#     人が打つ                      →  'めにゅう'   ← 打てる形
#
# この2つが**別の並び**に見えていたので、`めにゅう` は
# 「どこにも無い並び＝誤字」と読まれ、似た読みを探しに行って
#
#     めにゅう            → **にゅうひ**（入費）
#     メニューとめにゅう   → メニューと**つにゅう**（突入）
#
# と正しい語を壊していた。項目48-DX の「**打った文字と、しまって
# ある文字が同じ形か**を確かめる」と同じ型の見落としである。
#
# カタカナ語をひらがなで書くと、長音符は**直前の字の母音の字**になる:
#
#     メニュー     めにゅー ／ **めにゅう**
#     ニュース     にゅーす ／ **にゅうす**
#     コンピュータ  こんぴゅーた ／ **こんぴゅうた**
#     セーター     せーたー ／ せえたあ ／ **せいたあ**
#
# え段は「い」（せんせい）、お段は「う」（とうきょう）も普通なので、
# その2つは別に持つ。**触らない側に倒すためだけに使う**こと。
_VOWEL_ROWS = (
    ('あ', 'あかさたなはまやらわがざだばぱぁゃゎ'),
    ('い', 'いきしちにひみりぎじぢびぴぃ'),
    # 促音「っ」は入れない（単独で1拍あり、母音を持たない）。
    ('う', 'うくすつぬふむゆるぐずづぶぷぅゅ'),
    ('え', 'えけせてねへめれげぜでべぺぇ'),
    ('お', 'おこそとのほもよろをごぞどぼぽぉょ'),
)
_VOWEL_OF = {c: v for v, _row in _VOWEL_ROWS for c in _row}
# その母音を「ー」の代わりに書きうる字（え段は い、お段は う も）。
_LONG_WRITTEN_AS = {'あ': 'あ', 'い': 'い', 'う': 'う',
                    'え': 'えい', 'お': 'おう'}
_MAX_LONG_FOLD = 3          # 「ー」に畳む箇所の上限（組み合わせが増えるため）


def long_vowel_folds(reading, limit=8):
    """
    母音の字で書かれた長音を「ー」に畳んだ形の一覧（項目48-EL）。

        めにゅう   → ['めにゅう', 'めにゅー']
        にゅうす   → ['にゅうす', 'にゅーす']
        せいたあ   → ['せいたあ', 'せーたあ', 'せいたー', 'せーたー']

    畳める箇所が多いときは上限で切る（**触らない側に倒すため
    だけ**の道具なので、取りこぼしても壊れない）。
    """
    if not reading or 'ー' in reading:
        return [reading]
    spots = []
    for i in range(1, len(reading)):
        v = _VOWEL_OF.get(reading[i - 1])
        if v and reading[i] in _LONG_WRITTEN_AS.get(v, ''):
            spots.append(i)
        if len(spots) >= _MAX_LONG_FOLD:
            break
    if not spots:
        return [reading]
    out = [reading]
    for i in spots:
        for base in list(out):
            cand = base[:i] + 'ー' + base[i + 1:]
            if cand not in out:
                out.append(cand)
            if len(out) >= limit:
                return out
    return out


def long_vowel_variant_of_known(reading, store, dict_index=None):
    """
    その並びは、**既知の読みの「長音の書き分け違い」でしかない**か
    （項目48-EL）。そうなら誤字ではないので触らない。

    `めにゅう` は語彙の `めにゅー`（メニュー）と同じ語である。
    **元の並びそのものが既知なら False**（ここで見るまでもなく、
    ほかの門が守る）。
    """
    if not reading or 'ー' in reading:
        return None
    folds = long_vowel_folds(reading)
    if len(folds) < 2:
        return None
    for cand in folds[1:]:
        try:
            if store.has_reading(cand):
                return cand
        except Exception:
            pass
        if dict_index is not None:
            try:
                if dict_index.surfaces_for_reading(cand):
                    return cand
            except Exception:
                pass
    return None


# 長音のゆれで守る並びの長さ（`めにゅう` の3文字から `こんぴゅうた` 級まで）
_LV_MIN = 3
_LV_MAX = 12


def long_vowel_protected_span(line, start, end, new_surface, store,
                              dict_index=None):
    """
    その置換は、**長音の書き分けが違うだけの正しい語**を壊していないか
    （項目48-EL）。壊しているなら、その語（の畳んだ形）を返す。

    置換の**実際に変わる部分**を求め、それを含む短い並びのどれかが
    「既知の読みの長音の書き分け違い」なら、そこは誤字ではない。

        メニューと**め**にゅう → メニューと**つ**にゅう
          変わるのは `め` の1文字。それを含む `めにゅう` が
          `めにゅー`（メニュー・1,227回）の書き分け違い。→ 触らない

    置換は経路がいくつもあるが、**ここは全ての置換が必ず通る
    最終検査**なので、1箇所で塞げる（SPEC.md の設計方針）。
    """
    original = line[start:end]
    if not original or original == new_surface:
        return None
    # 変わる部分（前後の一致を削る）
    h = 0
    while (h < len(original) and h < len(new_surface)
           and original[h] == new_surface[h]):
        h += 1
    t = 0
    while (t < len(original) - h and t < len(new_surface) - h
           and original[-1 - t] == new_surface[-1 - t]):
        t += 1
    lo, hi = start + h, end - t          # 行の中で変わる範囲
    if lo >= hi:
        lo, hi = start, end
    n = len(line)
    for s in range(max(0, hi - _LV_MAX), min(lo, n - _LV_MIN) + 1):
        for e in range(max(hi, s + _LV_MIN), min(n, s + _LV_MAX) + 1):
            sub = line[s:e]
            if not all(is_hiragana(c) for c in sub):
                continue
            try:
                if store.has_reading(sub):
                    return None      # 元のままで既知＝ほかの門の仕事
            except Exception:
                pass
            got = long_vowel_variant_of_known(sub, store, dict_index)
            if not got:
                continue
            # **その語が、かなの連続のほとんどを占めていること。**
            # 残ってよいのは助詞・機能語だけ（項目48-EL）。
            #
            # これが無いと、**途中の切れ端がたまたま短い外来語に
            # 見える**だけで手を引いてしまう。実測（readcheck 型8種）:
            #
            #     ぼつににゅう → ぼつにゅう   `にゅう`＝ニュー で止まった
            #     どぶうつ     → どうぶつ     `ぶうつ`＝ブーツ で止まった
            #
            # 長さの下限で切りたくなるが、うにさんの指定 (c)
            # 「**長さの下限は理由にならない**」。守っているものを
            # 名指しすると「その語が並びの本体であること」だった。
            #
            #     メニューと|めにゅう|      残り `と`（助詞）    → 守る
            #     ぼつに|にゅう|            残り `ぼつに`        → 守らない
            #     ど|ぶうつ|                残り `ど`            → 守らない
            rs = s
            while rs > 0 and is_hiragana(line[rs - 1]):
                rs -= 1
            re_ = e
            while re_ < n and is_hiragana(line[re_]):
                re_ += 1
            head, tail = line[rs:s], line[e:re_]
            if head and not is_protected_word(head):
                continue
            if tail and not is_protected_word(tail):
                continue
            return f'{sub}（＝{got}）'
    return None


# **かな連続の最後で「助詞だ」と読み切ってよいかな**（項目48-DJ）。
# `PARTICLES_1CHAR` 全部ではなく、格助詞・係助詞だけに絞る。
# 除いたもの（や・か・ば・ね・よ・さ・な・ぞ・ぜ・わ）は
# **語の末尾にも普通に立つ**（はな・さかな・ちから・ことば・
# おかね・いね）ので、助詞と決めつけられない。
_RUN_TAIL_PARTICLES = set('をにへとでがはもの')


def run_tail_particle(line, run_start, run_end):
    """
    **かな連続の最後にある助詞**を返す（無ければ ''）。

    かな連続のすぐ後ろに**漢字かカタカナが続くときだけ**返す。
    そこで文が続いている、ということは、末尾のかなは
    「語の一部」ではなく**助詞**だと読める。

    なぜ要るか（項目48-DJ）
    ------------------------
    `probe_particle_eat.py` で見つけた:

        もじにゅうりょに行きます。 → もじにゅうりょ**く**行きます。

    `もじにゅうりょ`（`もじにゅうりょく` の脱字）に助詞 `に` が
    付いた形。かな連続は `もじにゅうりょに` で、これを丸ごと
    `もじにゅうりょく` に置き換えると **`に` が消える**。
    直った語は1文字伸びているのに文の長さが変わらない、という
    形で気づける。

    **これは「直らない」より悪い。** 文の意味が変わるうえ、
    利用者から見れば余計なことをされている。

    同じ考えの門は `を` にだけ既にある（項目48-CL）。
    ここはそれを**他の格助詞まで広げ、しかも両方の経路に置く**
    （従来の探索と芯の再構築。片方だけだと迂回される・学び22）。
    """
    if run_end >= len(line) or run_end <= run_start:
        return ''
    nxt = line[run_end]
    if not (is_kanji(nxt) or is_katakana(nxt)):
        return ''
    run = line[run_start:run_end]
    for p in sorted(PARTICLES_MULTI, key=len, reverse=True):
        # 助詞を剥がした残りが3文字以上あること
        # （短い残りは偶然どれかの語に似る）。
        if run.endswith(p) and len(run) - len(p) >= 3:
            return p
    if len(run) >= 4 and run[-1] in _RUN_TAIL_PARTICLES:
        return run[-1]
    return ''


def _rest_is_ordinary_japanese(rest, tokenize_fn):
    """
    **切り落とした残りが、ふつうの日本語の続きに見えるか**
    （項目48-DL）。

    ひらがなの並びの**頭だけ**をカタカナに寄せるとき、残りが
    「語の途中」だと**語を真っ二つにする**。

        ぷらねたりうむをみます  残り `をみます` → 続きに見える。よい
        こんぱくととかめら      残り `とかめら` → `かめら` の途中。だめ
        ちゃんぴおんしぷっ      残り `しぷっ`   → 語の途中。だめ

    見分けかた（2026-08-15 に実測して決めた）:

      1. 残り全部が**送り仮名・機能語だけ**（しました・です・に）
      2. または、**先頭の助詞を剥がした残りが2文字以上**で、
         それが送り仮名だけ、または形態素解析で読める
         （を＋みます・が＋ほしい・を＋つかう）

    「先頭の文字が助詞なら通す」では緩すぎた。`と` も `か` も
    助詞なので、`とかめら` `からめ` が素通りしていた
    （初期状態の readcheck で化けが2件出た）。
    **助詞の**次**まで見るのが要る。**
    """
    if not rest:
        return True
    if _okurigana_functional_only(rest):
        return True
    n = _leading_particle_len(rest)
    if not n or n >= len(rest):
        return False
    after = rest[n:]
    if len(after) < 2:
        return False
    return bool(_okurigana_functional_only(after)
                or _looks_like_valid_japanese(after, tokenize_fn))


def _looks_like_broken_katakana(run, store):
    """
    **この並び全体が、既知のカタカナ語を1つ壊した形に見えるか**
    （項目48-DL）。

    見えるなら、**頭だけをカタカナに寄せてはいけない**。
    壊れているのは語のうしろ側で、頭を寄せると

        こんぱくとかめら（コンパクトカメラ）を打ち損ねた
            こんぱくととかめら → **コンパクトとかめら**
            こんぱくとからめ   → **コンパクトからめ**

    のように、**壊れた尻尾を残したまま**半分だけカタカナになる。
    直っていないのに直った顔をするので、いちばん困る形。

    「1回の打ち間違いで説明が付く」＝訂正1箇所で届くこと、を
    条件にする。2箇所以上なら別の語であって、この語の壊れた形とは
    言えない。
    """
    try:
        from vocabulary import find_similar_readings
        import loanword as _LW
    except Exception:
        return False
    body = run
    n = _trailing_particle_len(body)
    if n and len(body) - n >= 4:
        body = body[:len(body) - n]
    if len(body) < 5:
        return False
    try:
        found = find_similar_readings(body, store, max_cost=2.8, limit=8)
    except Exception:
        return False
    for rd, _c, edits in found:
        if edits <= 1 and rd != body \
                and _LW.katakana_for_hiragana(rd, store, min_length=4):
            _trace('外来語', f'{run!r} → 全体が {rd!r} を1つ壊した形に'
                             f'見えるので、頭だけ寄せない')
            return True
    return False


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
        # **語頭に立てない文字まで剥がしたら、剥がしすぎ**
        # （項目48-DM）。送り仮名を剥がす仕掛けは最長一致で進むので、
        # 語の途中で止まることがある:
        #
        #     昨日もじにゅうりょに行った
        #       窓 `もじにゅうりょに` → `もじに` を剥がして `ゅうりょに`
        #       → 語頭に立たない `ゅ` で始まるので**芯が全部消える**
        #       → この文だけ直らない（単体なら直る）
        #
        # 窓の切り出し側には**既に同じ守りがある**
        #   （`while w_s > 0 and line[...] in _SMALL_KANA_HEADS: w_s -= 1`）
        # のに、**芯の切り出し側に無かった**（学び22）。
        # 語の頭になれる文字まで戻す。
        # **戻すのは「前の字と1拍になる字」だけ**。拗音（ゃゅょ）・
        # 小書き母音・長音は、前の字と合わせて1つの音なので、
        # そこで切れているのは明らかに切りすぎ。
        #
        # **促音（っ）は戻さない。** あれは単独で1拍あり、語の頭に
        # 立てないだけで「前の字と1つの音」ではない。戻すと
        #
        #     進めていったら → 進めていった**い**
        #     （`ったら` が `いったら` になり、`いったい` に化けた。
        #       janome の無い経路で実測・2026-08-15）
        #
        # のように、**正しい日本語を掘り起こして壊す**。
        while 0 < lead < n and window[lead] in _MORA_TAIL_KANA:
            lead -= 1
    else:
        lead = _leading_particle_len(window)
    tail = _trailing_functional_len(window)
    # 送り仮名を剥がすと決めたときは、剥がさない形は候補にしない。
    # 「きのままでよい」で末尾だけ剥がした「きのま」が残ると、
    # そこから「きのう」に化ける（実際に壊れた）。
    base = lead if after_kanji else 0
    # **剥がさない形も候補にする**（項目48-DY・2026-08-16）。
    #
    # 直前が漢字のとき、先頭のかなは送り仮名とみなして剥がす。
    # そのせいで**語の1文字目にある誤字に手が届かない**うえ、
    # 残りだけを直して**日本語ですらない並び**を作っていた:
    #
    #     昨日ひどまえを見ました。（正解 ひとまえ）
    #       芯は `どまえ` → `じまえ` → **昨日ひじまえを**
    #
    # 8種の型で測った化けの**40%**がこの形だった（項目48-DT）。
    #
    # 2026-08-16 に一度試して**戻した**。`竹かんむり` が
    # `竹うかんむり` に化けたため。`かんむり` は正しい語なのに
    # うにさんの語彙にも刈り込んだ索引にも無く、
    # 「壊れている」と「知らないだけ」を分けられなかった。
    # **項目48-DY で分けられるようになった**（刈り込む前の辞書）。
    # 実際に落とすのは `rebuild_window_core` の側。
    if after_kanji and lead:
        push(0, n - tail)
        push(0, n)
    push(lead, n - tail)
    # **助詞だけを剥がした形**も候補にする（項目48-DV・2026-08-16）。
    #
    # `_trailing_functional_len` は活用語尾まで貪欲に剥がすので、
    # **語の中身まで食う**ことがある:
    #
    #     てんまんくうに → 剥がすと `てんまん`（`くうに` を食った）
    #       → `てんかん` に化ける（正解 てんまんぐう）
    #     「てんまんくう」と書きました。 → **こちらは直る**
    #       （助詞が付かないので窓がそのまま `てんまんくう`）
    #
    # 同じ語が、うしろに助詞が付くかどうかで直ったり化けたり
    # していた。**助詞だけ剥がした形**（`_trailing_particle_len`）を
    # 足せば、`てんまんくう` が芯になって1文字違いで届く。
    #
    # 活用語尾まで剥がす形も残す（「たああんごの」等はそちらが要る）。
    _p_tail = _trailing_particle_len(window)
    if _p_tail and _p_tail != tail:
        push(lead, n - _p_tail)
        push(base, n - _p_tail)
    # 末尾を剥がさない形も候補にする。壊れた語の最後の1文字が
    # たまたま活用語尾と同じ字のことがある（「ほらい」の「い」は
    # 「補正（ほせい）」の一部であって語尾ではない）。
    push(lead, n)
    push(base, n - tail)
    # **末尾を「途中まで」剥がした形**も候補にする（項目48-GG）。
    #
    # 剥がす仕掛けは**貪欲**（いちばん長く剥がせるところまで剥がす）
    # なので、**語尾が助詞と同じ字の語**が丸ごと食われる:
    #
    #     あぎらかを（正解 あきらか）
    #       機能語で剥がすと `あぎら` ／ 助詞で剥がしても `あぎら`
    #       （`か` も `を` も助詞なので、2文字とも食われる）
    #       → 芯は `あぎら` だけ → `あら` に化ける
    #
    #     切らない形なら圧倒的に安い:
    #       find_known_readings_flex('あぎらか') → **あきらか 0.40**
    #
    # `あきらか` `きよらか` のように **語尾が「か」**の語は、
    # 誤字で語彙に当たらなくなると必ずこれを踏む。
    # **1文字ずつ戻した形**を足せば、長い芯から見る決まり
    # （項目48-CR）でそちらが先に当たる。
    #
    # 実測（`probe_core.py`・600語×6型）: 化け78件のうち
    # **57件は打たれた形そのものが芯になっていない**。
    # そのうち **45件は、切らない形なら狙いが1番**（費用 0.40〜1.10）。
    # 崩れうるのは 3件。
    #
    # **戻すのは1文字だけ。** 途中まで全部戻す形も試したが、
    # **機能語の並びの途中で切った芯**ができて壊した:
    #
    #     したゃがありました（正解 たしゃ）
    #       末尾 `がありました` を途中まで戻すと芯 `したゃが` が
    #       でき、`しゃが` に化けた（`たしゃ` に直っていたのに）
    #
    # 1文字だけなら、`したゃがありまし` になって
    # 「終わりが機能語の途中」の門で落ちる。**`あぎらか` は救えて、
    # `したゃが` は作らない。**
    if tail >= 2:
        push(lead, n - 1)
        push(base, n - 1)

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
            # **末尾の機能語も落とした形**も出す（項目48-DP）。
            # 切り離した残りをそのまま渡していたので、
            # `これはたんほです` から出る芯は `たんほです` だけで、
            # **`たんほ` が出てこなかった**。`です` が付いたままでは
            # どの語にも似ない。
            push(i + 1, n - tail)

    # **内側の助詞の手前も芯にする**（項目48-DM）。
    #
    #     もじにゅうりょをみます。 → 直らなかった
    #       芯の候補は `もじにゅうりょをみ`（助詞を跨いだ形）ばかりで、
    #       **`もじにゅうりょ` が一度も出てこない**。
    #
    # 上の切り離しは「**既知語**＋助詞」の**後ろ**しか見ない。
    # 打ち間違えた語は既知語ではないので、前側は永遠に芯にならない。
    # 文の途中に置かれた誤字が、そこだけ直らないことになる。
    #
    # 始まりは `lead`（送り仮名を剥がした位置）から数える。
    # 0 から数えると「色付き|のままでよい」の窓 `きのままでよい` で
    # `きのまま` が芯になり、`このまま` に化ける。
    # **`base` の側も出す。** 直前が漢字でなければ窓の頭は語の頭
    # なので、そこから数える（`push(base, n)` と同じ考え）。
    # `lead` だけだと、語頭がたまたま助詞と同じ字のときに削れる:
    #     もじにゅうりょをみます → `も` を助詞とみて `じにゅうりょ`
    # **切るのは `を` の手前だけ**にする。`PARTICLES_1CHAR` 全部で
    # 切ると、語の中にふつうに現れる字で真っ二つになる（実測）:
    #
    #     ちゅうがくを → 芯 `ちゅう`（`が` で切った）→ **しちゅうがく**
    #     まぐねねっとを → 芯 `まぐね`（`ね` で切った）→ **まねねっと**
    #
    # `を` は現代語ではほぼ必ず助詞で、語の中に現れない
    # （項目48-CL と同じ根拠）。まずここだけ開ける。
    for i in range(min(lead, base) + min_len, n - 1):
        if window[i] == 'を':
            push(lead, i)
            push(base, i)

    push(base, n)
    return out


# --- 項目48-EU（設計12）: 語＋接尾の合成で表記を立てる ---
#
# `最大化` は**語彙にも索引にも世の中にも無い**（2026-08-18 に
# Opus と Fable 5 の両方で確かめた。`最大` は count 1,107 で在る）。
# **派生語だから**で、辞書の刈り込みが悪いわけではない。
# 刈り込みをゆるめる方向は大きくて危ないので取らない。
#
# 代わりに、**読みから表記を出す最後の段にだけ**合成を許す。
# 接尾の表はごく小さく始める（増やすのは測ってから）。
_SUFFIX_SURFACE = {
    'か': '化', 'じ': '時', 'ちゅう': '中', 'てき': '的',
    'せい': '性', 'しゃ': '者', 'すう': '数', 'りつ': '率',
    'べつ': '別', 'がわ': '側',
}
_SUFFIX_MAX_PEEL = 2        # 2段まで（さいだいかじ → さいだい＋か＋じ）


def compose_suffix_surface(reading, store, dict_index=None,
                           want_parts=False):
    """
    **読みを「語幹＋接尾」に分けて表記を組み立てる**
    （項目48-EU・設計12・2026-08-18）。

        さいだいか   → さいだい（最大・実績1,107）＋ か → **最大化**
        さいだいかじ → さいだい ＋ か ＋ じ           → **最大化時**

    条件:
      - 剥がせる接尾は `_SUFFIX_SURFACE` の10個だけ・**2段まで**
      - 残った語幹が**漢字の実績語**として立つこと
        （語彙か索引。ひらがな・カタカナの表記は使わない）

    **表記の解決にだけ使うこと。** 読みの探索や「正しいかどうか」の
    判断には使わない（判断経路を増やさない・SPEC の設計方針）。
    """
    if not reading or len(reading) < 3:
        return None
    tail = []
    stem = reading
    for _ in range(_SUFFIX_MAX_PEEL):
        for suf, kanji in _SUFFIX_SURFACE.items():
            if len(stem) > len(suf) + 1 and stem.endswith(suf):
                stem = stem[:-len(suf)]
                tail.append(kanji)
                break
        else:
            break
    if not tail:
        return None
    # 語幹が漢字の実績語として立つこと
    head = None
    try:
        for e in sorted(store.lookup(stem),
                        key=lambda x: -x.get('count', 0)):
            s = e.get('surface') or ''
            if s and all(is_kanji(c) for c in s) and e.get('count', 0) >= 2:
                head = s
                break
    except Exception:
        pass
    if head is None and dict_index is not None:
        try:
            for s in dict_index.surfaces_for_reading(stem):
                if s and all(is_kanji(c) for c in s):
                    head = s
                    break
        except Exception:
            pass
    if not head:
        return None
    full = head + ''.join(reversed(tail))
    return (head, full, stem, len(tail)) if want_parts else full


def _best_surface_for(reading, store):
    """その読みで、いちばんよく使われている表記。"""
    try:
        entries = store.lookup(reading)
    except Exception:
        return None
    if not entries:
        return None
    return max(entries, key=lambda e: e.get('count', 0)).get('surface')


# 使用実績の頭打ちと、使わなくなった語の弱まり方。
#
# うにさんの指摘（2026-08-10）:
# 「1000以上の回数があると、次に普段使う単語が変わるような
# 　環境変化の時、補正が逆効果で不便になるはず」。
#
# そのとおりで、回数が青天井だと**昔たくさん使った語が永久に勝ち
# 続ける**。実機では「単語」が1312回まで育っていた。
# 仕事や話題が変われば、その語はもう普段の語ではない。
#
#   - 頭打ち: ここを超えたら「よく使う語」として横並びに扱う。
#     1312回と300回の差に意味は無い（どちらも「よく使う」）。
#   - 弱まり: 最後に使った日から離れるほど効きを落とす。
#     半減期は14日。しばらく使わなければ自然に譲る。
#     語彙そのものは消さない（また使い始めれば戻る）。
_USAGE_CAP = 300
_USAGE_HALFLIFE_DAYS = 14.0


def _now_for_usage():
    """
    使われぶりの弱まりを測る「いま」。**測るときだけ固定できる**
    （項目48-DQ・2026-08-15）。

    `_break_tie_by_generality` は

        if _usage_count(...) < _USAGE_MIN:   # 20

    と、**減り続ける値を固定の敷居と比べている**。減りかたは
    **1日で4.83%**。うにさんの語彙では、敷居20のきわ（15〜25）に
    **717の読み**が居る。つまり**時計が進むだけで、同じ版・同じ
    入力の答えが変わる**（2026-08-15 に実測。1分の間に変わった）。

    これは造りとしては意図どおり（最近使っているかを効かせたい）。
    だが**測るときには嘘の差分になる**。前後の版を比べていて
    「1件だけ違う」が出るたびに、それが自分の直したせいなのか
    時計のせいなのか分からなくなる（実際に3回振り回された）。

    そこで `CORRECTNOTE_NOW`（秒）が置いてあれば、その時刻で測る。
    **アプリの動きは変わらない**（置かなければ今までどおり）。
    `runprobe.sh` / `sweepcmp.sh` が固定値を置く。
    """
    import os
    import time
    v = os.environ.get('CORRECTNOTE_NOW')
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    return time.time()


def _usage_count(reading, store):
    """
    その読みの「いまの使われぶり」。

    生の回数ではなく、頭打ちと日数による弱まりを掛けた値を返す
    （`_USAGE_CAP` / `_USAGE_HALFLIFE_DAYS` の説明を参照）。
    """
    try:
        entries = store.lookup(reading)
    except Exception:
        return 0
    if not entries:
        return 0
    now = _now_for_usage()
    best = 0.0
    for e in entries:
        n = min(e.get('count', 0), _USAGE_CAP)
        if not n:
            continue
        last = e.get('last_seen') or 0
        days = max(0.0, (now - last) / 86400.0)
        n *= 0.5 ** (days / _USAGE_HALFLIFE_DAYS)
        if n > best:
            best = n
    return best


# 使用実績で決め打ちするための条件。
# 「よく使う語だから」というだけで選ぶのは危ういので、
# 他を圧倒しているときに限る。
_USAGE_DOMINANCE = 4        # 二番手の何倍あれば決め手とみなすか
_USAGE_MIN = 20             # 最低これだけ使われていること

# 「一般的さ」で決めるときの差（項目48-BZ・2026-08-13）
_GENERALITY_MIN_RATIO = 1.2   # 二番手のこの倍を超えていること


def _general_count(reading, store):
    """
    その読みの **一般的さ**。生の回数の最大値を返す。

    `_usage_count` との違い（**使い分けること**）:

        _usage_count    「いまの使われぶり」。頭打ち(300)と
                        日数による弱まりが掛かる。最近使ったか。
        _general_count  「一般的さ」。**生の回数**。よく使う語か。

    **なぜ分けたか**（項目48-BZ）。`_break_tie_by_generality` は
    `_usage_count` を使っていたが、**頭打ちと減衰が、まさに
    一般的さを測るのに要る情報を捨てていた**:

        単語 1315回 / 端子 632回 / 単位 537回   ← 生の回数（2倍以上の差）
             300         300        300         ← 頭打ちで区別が消える
        256.0444    237.4148   237.4148         ← 残るのは last_seen の差

    さらに**解析中に語彙が育って last_seen が動く**ので、
    飽和した候補どうしの差は **0.000002** まで縮み、
    「どちらを直前に学習したか」で勝者が変わっていた。
    同じ行が、解析の順番で `たんごの` にも `たんしの` にもなる
    （`probes/probe_order_learn.py` が 11回中3〜5回落ちていた原因）。

    `scored[0][0] == scored[1][0]` で同点を弾く関門は**書いてあった**
    が、小数の誤差で**一度も成立しなかった**。
    学び43「刈り込んだ索引を、別の目的に使い回さない」。
    """
    try:
        entries = store.lookup(reading)
    except Exception:
        return 0
    if not entries:
        return 0
    # **世の中での使われぶりも見る**（項目48-DA）。
    # 辞書から取り込んだだけの語は `count` が1のままなので、
    # 回数だけで見ると**初期状態では全部が同点**になり、
    # うにさんの指定「補正候補はより一般的なほうを優先」が
    # 初期状態では一度も働かない。
    return max(max(e.get('count', 0) or 0, e.get('world', 0) or 0)
               for e in entries)


# 地名の接尾（項目48-CJ）。**地形だけに絞る。**
# 「原・野・池・森・林・城・橋」は普通の語にも出るので入れない
# （データ林・エラー原 のような並びは無いが、狭く保つほうが安全）。
_PLACE_SUFFIX = '山島川岳湖峠岬'


_ADVERBIAL_POS = ('副詞', '接続詞', '連体詞', '感動詞')


def _leading_hiragana(text):
    """先頭に続くひらがなを返す（無ければ空文字）。"""
    i = 0
    while i < len(text) and 'ぁ' <= text[i] <= 'ん':
        i += 1
    return text[:i]


def _is_adverbial_word(text, tokenize_fn):
    """
    その並びが、**それだけで1語の副詞・接続詞・連体詞・感動詞**か
    （項目48-CI）。

    後ろの名詞と複合語を作らない品詞なので、塊に含めてはいけない。
    **1語に割れることを条件にする**——2語以上に割れる並びは
    「たまたま副詞で始まっている語の一部」かもしれない。
    """
    if not text or tokenize_fn is None:
        return False
    try:
        parts = [(t[0] if isinstance(t, (tuple, list))
                  else getattr(t, 'surface', ''),
                  t[1] if isinstance(t, (tuple, list))
                  else (getattr(t, 'part_of_speech', '') or ''))
                 for t in tokenize_fn(text)]
    except Exception:
        return False
    if len(parts) != 1:
        return False
    pos = parts[0][1] or ''
    return pos.split(':')[0].split(',')[0] in _ADVERBIAL_POS


def _linked_by_okurigana(chunk, tokenize_fn):
    """
    その塊が、**送り仮名で繋がっただけの複数語**か（項目48-CB）。

    形態素に割って、**真ん中のどれかが活用語尾・助詞だけの語**なら
    True。先頭と末尾は数えない（「打ち」「並び」のように、送り仮名を
    含んで1語になるものを巻き込まないため）。

        作った行 → 作っ / **た** / 行   → True（触らない）
        時ッ層   → 時 / ッ / 層         → False（ッ は活用語尾ではない）
        田安吾   → 田安 / 吾            → False（2語しかない）
        カニ打ち → カニ / 打ち          → False
    """
    if not chunk or tokenize_fn is None:
        return False
    try:
        parts = [t[0] if isinstance(t, (tuple, list)) else
                 getattr(t, 'surface', '') for t in tokenize_fn(chunk)]
    except Exception:
        return False
    if len(parts) < 3:
        return False
    return any(p and _is_all_functional(p) for p in parts[1:-1])


def _break_tie_by_generality(candidates, store):
    """
    拮抗が最後まで解けないとき、**より一般的なほう**を選ぶ。

    うにさんの指定（2026-08-10）:
    「原文が不自然な文字列であれば、何かしら自動補正してしまって
    　ください。補正候補はより一般的なほうを優先。」

    `_break_tie_by_usage` は「他を圧倒しているときだけ」という
    厳しい条件（二番手の4倍以上）を課しているため、
    自動学習で妙な語が育っていると決め手を失って**何もしない**に
    倒れていた（実機の例: 「たんほ」に対して
    単語1312回 と たんと426回 が並び、4倍に届かず直せなかった）。

    **これは「元の並びがそもそも語として成立していない」ときだけの
    最後の手** で、呼び出し側でその確認をしてから使う。
    正しく書けている語はここへ来ない（来る前に `best == core` で
    弾かれる）。

    戻り値: 選ばれた読み、または None（差が無くて選べない）
    """
    # **並べるのは生の回数**（項目48-BZ・2026-08-13）。
    # 使う場所が違うので `_usage_count` は使わない（下の説明）。
    scored = sorted(((_general_count(r, store), r)
                     for r, _c, _e in candidates), reverse=True)
    if len(scored) < 2:
        return None
    # **選ぶほうが本当に「一般的」でなければならない。**
    # ここを外すと、正しく書いた珍しい並び（駅名の読みがな等）まで
    # 巻き添えにする。実測: 「相川駅（あいかわえき…）」が
    # 「あいかひえき」に化けた（2026-08-10）。
    #
    # **この関門だけは「いまの使われぶり」で見る**（減衰つき）。
    # 「そもそも使われている語か」を見たいので、最近使っているか
    # どうかが効く。生の回数にすると、何年も前に一度だけ育った語が
    # 通ってしまう。
    if _usage_count(scored[0][1], store) < _USAGE_MIN:
        return None
    # **一番手が二番手を、はっきり上回っていること。**
    # 前は `scored[0][0] == scored[1][0]` で同点を弾いていたが、
    # 頭打ち後の小数を比べていたので**一度も成立しなかった**
    # （項目48-BZ。差が 0.000002 でも「同点ではない」になる）。
    if scored[1][0] * _GENERALITY_MIN_RATIO > scored[0][0]:
        return None
    return scored[0][1]


# 「より一般的なほうを優先」する条件。
# 打鍵の近さで負けていても、本人の使用実績が桁違いなら覆す。
_GENERAL_DOMINANCE = 10     # 最有力の何倍あれば覆してよいか（頭打ち後の値で比べる）
_GENERAL_COST_BAND = 1.5    # 最有力との費用差がこれ以内の候補だけ見る


def _prefer_general(found, store, top_cost, edits, max_cost):
    """
    打鍵の近さでは二番手でも、**桁違いによく使う語**があればそちらを選ぶ。

    うにさんの指定（2026-08-10）:「補正候補はより一般的なほうを優先」。

    実機の例:「他b後の繋がり」の芯 'たこご' に対して
      たまご（費用1.0・玉子22回）／たんご（費用2.2・単語1312回）
    となり、かな配列の隣接の近さだけで「玉子」が選ばれていた。
    費用差は 1.2 しかないのに使用実績は約60倍あり、
    「単語」のほうが明らかに一般的。

    覆すのは**桁違いのとき（20倍以上）だけ**にする。僅差で
    ひっくり返すと、打鍵の近さという確かな手がかりを捨てて
    「よく使う語」に引きずられる（学び12・項目27の轍）。

    戻り値: 選び直した読み、または None
    """
    top_usage = None
    best_reading = None
    best_usage = 0
    for reading, cost, ed in found:
        if ed > edits or cost >= max_cost:
            continue
        if cost - top_cost > _GENERAL_COST_BAND:
            break               # found は費用の昇順。ここから先は遠すぎる
        usage = _usage_count(reading, store)
        if top_usage is None:
            top_usage = usage
            continue            # 最有力そのもの
        if usage > best_usage:
            best_usage, best_reading = usage, reading
    if best_reading is None or top_usage is None:
        return None
    if best_usage < _USAGE_MIN:
        return None
    if best_usage < max(1, top_usage) * _GENERAL_DOMINANCE:
        return None
    return best_reading


def _core_is_unnatural(core, store, find_readings=None):
    """
    その並びが「そもそも語として成立していない」か。

    成立していない＝語彙にその読みが無く、読みの探索でも
    説明が付かない。ここが True のときだけ、拮抗を
    `_break_tie_by_generality` で押し切ってよい。
    """
    if not core:
        return False
    try:
        if store.has_reading(core):
            return False
    except Exception:
        return False
    if find_readings is not None:
        try:
            if find_readings(core, store):
                return False
        except Exception:
            pass
    return True


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
                          short_ok=(), allow_exact=True,
                          exact_only=(), dict_index=None,
                          input_method=None):
    """
    混合塊（漢字・カタカナ・混入英字を含む塊）の読みの候補列から、
    置き換え先の表記を決める（1-B / 1-C の共通部）。

      1. 読みそのものが語彙にある（変換し損ねただけ）→ その表記
      2. 芯の再構築（rebuild_window_core）が塊全体を直せる → その表記

    判断はどちらも既存の関門（使用実績・拮抗の裁定・切り詰め禁止）に
    委ね、ここでは増やさない。

    short_ok: 2文字でも引き当てを許す読みの集合（英字2連の ん 読み替え）。
    exact_only: **完全一致でしか使わない**読みの集合。
        「ん」の打ち損ね（QWERTY で n の隣の英字）の読み替えは
        推測が1段深いので、語彙にそのままある（使用実績のある）
        ときだけ採り、正しさの確認（_reading_intact）や
        芯の再構築へは渡さない（2026-08-16・タマゴの繋がり）。
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
        if reading in exact_only:
            continue    # この読みは完全一致でしか使わない（上の説明）
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
                                  whole_only=True,
                                  # **隣接の判定は入力方式で変わる**
                                  # （項目48-FX/FZ）。混合塊の経路にも
                                  # 同じ門を掛ける。
                                  input_method=input_method)
        if fix is None:
            continue
        surface = _best_surface_for(fix[2], store)
        if not surface or surface == chunk:
            continue
        entries = store.lookup(fix[2])
        category = entries[0].get('category', 'その他') if entries \
            else 'その他'
        return surface, category
    # --- 項目48-EX: 造語めいた複合を、開いて直して組む ---
    # （うにさん指示・2026-08-18。第43回で候補には出るように
    #   なったものを、**初期状態で自動補正される**ところまで）
    # どの道でも決まらなかったときの、いちばん最後の手。
    if dict_index is not None:
        _cg = compose_from_intruded(chunk, readings, store, dict_index,
                                    tokenize_fn)
        if _cg:
            return _cg, 'その他'
    return None


# 前の語にぶら下がる品詞。これで始まる位置は「語の頭」ではない。
# 助動詞（た・ます・です）・助詞（を・が・に）・接尾（性・的・さ）・
# 非自立（こと・もの・いる）。設計方針2の
# 「助詞・助動詞・接尾語・非自立語は補正対象外」と同じ並び。
_LEFT_ATTACHING_POS = ('助動詞', '助詞')
_LEFT_ATTACHING_SUB = ('接尾', '非自立')


def _left_attaching_cuts(chunk, tokenize_fn):
    """
    塊の中で「前の語に付く語」が始まる位置の集合。

    `打った行` なら {2}（`た` が助動詞なので、その手前では割れない）。

    **形態素の切れ目ちょうどの位置だけ**を返す。切れ目でない位置
    （語の途中）は、誤変換で解析が乱れている可能性があるので
    ここでは触らない。狭く効かせて、既にできている分割
    （野外|文章・簡易|流力・上野|小学校）を邪魔しない。

    解析できなければ空集合（何も禁じない）。
    """
    if tokenize_fn is None or not chunk:
        return frozenset()
    try:
        toks = tokenize_fn(chunk)
    except Exception:
        return frozenset()
    out = set()
    pos = 0
    for i, t in enumerate(toks):
        surface = t[0] or ''
        if i > 0:
            main = t[1] or ''
            head = main.split(':')[0]
            if head in _LEFT_ATTACHING_POS or any(
                    s in main for s in _LEFT_ATTACHING_SUB):
                out.add(pos)
        pos += len(surface)
    return frozenset(out)


def _resolve_kanji_split(chunk, store, tokenize_fn, dict_index=None,
                         context_vec=None, surrounding=(),
                         input_method=None):
    """
    塊の片側が実在語なら、それを残してもう片側だけを組み直す（1-C）。

      野外文章 → 野外＋文章（実在）→ やがい→ながい → 長い文章
      簡易流力 → 簡易（実在）＋流力 → りゅうりょく→にゅうりょく → 簡易入力

    実在の判定は、確実な情報源（janome で読み切れる・辞書・語彙）
    だけを使う。組み直す側は _resolve_reading_list（既存の関門）。

    **物差しは片側ごとに違う**（2026-08-11・項目48-AL(1)）。
    同じ `_is_solid` を両側に使っていたのが間違いだった。

      残す側（solid）  … 「ここは触らない」と決める根拠。
                         **強い証拠が要る**。ゆるいと、語ですら
                         ない並び（流力・素帰・簡易流・野外文）を
                         足場にして、反対側だけを別の語に化けさせる。
      壊れている側（broken）… 「正しい複合語だから触らない」と
                         決める根拠。**疑わしきは実在に倒す**のが
                         安全側なので、今までどおりゆるく見る。
    """
    from kanji_guess import (reading_combos_with_rank, looks_like_real_word,
                             _is_solid_known_word)

    def _is_real_ish(part):
        """**壊れている側**の判定（ゆるい＝守りに倒す）。"""
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

    def _is_solid(part):
        """
        **残す側**の判定（きびしい＝「語として実在する」の証拠）。

        `looks_like_real_word` は「**形態素に切れる**」ことを
        実在の根拠にしている。大きな辞書では壊れた並びも切れて
        しまうので、足場にするには弱すぎた（学び12 の罠）:

            流力  → 流[動詞:自立] / 力[名詞:接尾]      → 実在扱い
            素帰  → 素[名詞:一般] / 帰[名詞:サ変接続]  → 実在扱い
            簡易流 → 簡易 / 流[接尾]                    → 実在扱い
            野外文 → 野外 / 文                          → 実在扱い

        そこで、残す側には次のどれかを求める:

          1. janome が**ちょうど1語**として読み切る（読みが確定）
          2. 語彙に使用実績つきで載っている（count>=2）
          3. 辞書索引（読み→表記）に載っている

        1 は「上野」「小学校」のような、切れ目の証拠になる語を
        そのまま通す（固有名詞もここで通る）。
        2・3 は「文字入力」のような、2語に切れるが実在が
        確かめられている複合語のための逃げ道。
        """
        if len(part) < 2:
            return False
        if tokenize_fn is not None:
            try:
                toks = tokenize_fn(part)
            except Exception:
                toks = []
            # ちょうど1語。読みが確定している（＝辞書にある）ことまで
            # 求める。未知語も1トークンになるため、これが無いと
            # 「読めない並び」をそのまま足場にしてしまう。
            if len(toks) == 1 and toks[0][0] == part and toks[0][5]:
                return True
        return _is_solid_known_word(part, store, dict_index)

    # 左に付く語（助動詞・助詞・接尾・非自立）が始まる位置。
    # そこで割ると、前の語から活用語尾や助詞をもぎ取ることになる。
    _left_bound = _left_attaching_cuts(chunk, tokenize_fn)

    n = len(chunk)
    for cut in range(2, n - 1):
        # カタカナの連続の途中では割らない。「非アク|ティブ時」
        # 「カー|ル位置」のように、カタカナ語を断ち切った片側が
        # 「実在語」に見えてしまい、残り半分が別の語に化ける
        # （実機診断で 非アク提示・カー配置 の正体と確定した）。
        if ('ァ' <= chunk[cut - 1] <= 'ヶ' or chunk[cut - 1] == 'ー') \
                and ('ァ' <= chunk[cut] <= 'ヶ' or chunk[cut] == 'ー'):
            continue
        # **前の語に付く語の手前では割らない**（2026-08-11）。
        # 「打った行」を 打っ|た行 と割ると、`た`（打つの助動詞）が
        # 次の語の頭になり、たぎょう → さぎょう → **打っ作業**に
        # 化ける。README.md の「打った行」で実際に壊れていた。
        # 助動詞・助詞・接尾・非自立は前の語にぶら下がるものなので、
        # **それが語の頭になることはありえない**。
        if cut in _left_bound:
            _trace('分割', f'{chunk!r} を {cut} で割らない'
                           f'（{chunk[cut:]!r} が前の語に付く語で始まる）')
            continue
        head, tail = chunk[:cut], chunk[cut:]
        for solid, broken, head_side in ((tail, head, True),
                                         (head, tail, False)):
            if not _is_solid(solid):
                continue
            # 壊れている側も実在語なら、塊は正しい複合語
            # （タブ＋機能）。触ると「機能」→「昨日」のように
            # 同音の別表記へすり替えてしまう。
            # **ここはゆるいほうの物差しを使う**（守りに倒すため）。
            # きびしい物差しに替えると、日清|戦争 の 日清 のような
            # 「1文字の固有名詞2つ」が実在扱いを外れ、
            # 日清戦争→実在戦争 の再発になる（実機・2026-08-09）。
            if _is_real_ish(broken):
                # **設計26（項目48-HQ）は、測って外した。**
                # 「両方とも実在語でも、その順でくっつけないなら
                #   壊れている」——`oddness.can_join` でこの守りを
                # 開けると、`野外文章` は確かに先へ進む。だが
                # **実機メモ・fpcheck とも差0**（何も変わらない）。
                # 先に `やがい` の芯が取れず（`window_cores` が空）、
                # 取れても `ながい`/`にがい`/`やがて` が**3つ拮抗**
                # するため。**効果が無いものは入れない**（決まり）。
                # 開け方と鎖の全部は項目48-HQ に書いてある。
                continue            # 壊れている側の中に2文字以上の固有名詞が丸ごと
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
            # 壊れている側が**前半**なら、そのすぐ後ろは残す側の
            # 1文字目（漢字）＝送り仮名は付いていない。
            # 後半なら塊の外なので分からない（None のまま）。
            combos = reading_combos_with_rank(
                broken, dict_index,
                next_char=(chunk[len(broken)] if head_side else None))
            got = _resolve_reading_list(
                broken, [r for r, _k in combos[:4]], store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                allow_exact=False, input_method=input_method)
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
                         only_whole=False, line_span=None):
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
        # **並べてから回す**（項目48-DR・2026-08-15）。
        # `tries` は集合なので、**回る順が python の起動ごとに変わる**
        # （文字列のハッシュに種が入る）。下は `>` で比べるので
        # **同点のときは先に来たほうが残る**。つまり
        #
        #     絵字文を確認しました。
        #       → **かじぶん**（ある起動）
        #       → **あじぶん**（別の起動）
        #       → **絵字文**（また別の起動。関門に引っかかる）
        #
        # と、**同じ版・同じ入力・同じデータで答えが変わっていた**。
        # 使う人から見れば「直るときと直らないときがある」。
        # 測る側から見れば、前後の版を比べるたびに1件ずつ嘘の差分が出る。
        for cand in sorted(tries):
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
        # **近くに書かれていなくても、明らかに自然になるなら通す**
        # （項目48-AE・2026-08-11）。
        #
        # うにさん:「正しく読めるとは、辞書と一致するではなく、
        # 単語と単語の結びつきに違和感がないこと」。
        # 「近くに同じ語が書いてあるか」は**書いた人の都合**であって、
        # 日本語として自然かどうかとは関係が無い。
        # `目もち長 → メモ帳` はここで止まっていた（差 +7314）。
        #
        # 敷居は高いほう（MIN_GAIN_READABLE）を使う。この道は
        # 「読める並びを別の語に置き換える」ので、慎重側に倒す。
        if not support and _naturalness.worth_touching_readable(
                chunk, win['surface'], default=False):
            support = True
            _trace('語の組', f'{chunk!r} → {win["surface"]!r} は'
                             f'近くに無いが、明らかに自然になるので通す'
                             f'（差 {_naturalness.gain(chunk, win["surface"])}）')
        # **単位の表を並べる**（設計23・項目48-HM）。
        # 近接条件と同じ「語ごと」の形で、表が言えることだけを足す。
        if not support:
            _why = _unit_table_support(chunk, win['surface'], names)
            if _why:
                support = True
                _trace('語の組', f'{chunk!r} → {win["surface"]!r} は'
                                 f'近くに無いが、{_why}ので通す'
                                 f'（設計23）')
        if not support:
            _trace('語の組', f'{chunk!r} → {win["surface"]!r} は'
                             f'近くに書かれていないので直さない')
            return None

    return win['surface'], win['category']


# **設計27 の自然さの拒否権**（項目48-HS）。
# 自然さは「より自然になること」を求めない（`野外文章 →
# 長い文章` は -1080 になる）。**大きく悪くなるときだけ断る。**
_ODD_REOPEN_DROP = 4000

_KATAKANA_MELT_MIN_COUNT = 100


# 溶かしてはいけないカタカナ語の最短の長さ（2026-08-11）。
# 3文字未満（カニ・タン）は偶然そう読めるだけのことが多く、
# ここを2にすると カニ打ち→かな打ち・タン子→単語 が通らなくなる。
# 「3文字未満は偶然似やすい」という、芯の切り出しと同じ線引き。
_KATAKANA_KEEP_MIN = 3


def _has_solid_katakana_word(chunk, tokenize_fn):
    """
    塊の中に、**辞書が1語として読み切れているカタカナ語**が
    あるか（`左ペイン` の `ペイン`）。

    あるなら、その塊は壊れていない部分を含んでいる。
    カタカナ語は固有名詞・略語が多く、そもそも補正対象外の方針
    なので、丸ごと別の語へ溶かしてはいけない。

    条件:
      - トークンがまるごとカタカナ（長音を含む）
      - 3文字以上（`_KATAKANA_KEEP_MIN`）
      - 辞書が読みを引けている（t[5]）

    読めていないカタカナ（`リュク` `コピ` `ブチ`）は誤変換の断片
    なので、ここでは守らない。
    """
    if tokenize_fn is None or not chunk:
        return False
    try:
        toks = tokenize_fn(chunk)
    except Exception:
        return False
    for surface, _pos, _reading, _s, _e, has_reading in toks:
        if not has_reading or len(surface) < _KATAKANA_KEEP_MIN:
            continue
        if all('ァ' <= c <= 'ヶ' or c == 'ー' for c in surface):
            return True
    return False


def _katakana_melt_ok(chunk, new_surface, store, tokenize_fn=None):
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
    # **辞書が1語として読めているカタカナ語は溶かさない**
    # （2026-08-11）。`左ペイン` が `索引` に化けていた
    # （左 の別読み さ を当てて さぺいん → さくいん）。
    # `ペイン` は辞書にも語彙にもある、壊れていない語で、
    # 「カタカナ語は原則補正対象外」の方針そのものに反する。
    #
    # 3文字以上に限る。2文字（カニ・タン）は偶然そう読めるだけの
    # ことが多く、ここを2にすると カニ打ち→かな打ち・タン子→単語
    # という当たりが通らなくなる（実測）。
    if _has_solid_katakana_word(chunk, tokenize_fn):
        return False
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


def _is_whole_proper_noun(surface, tokenize_fn):
    """
    その表記は、**まるごと1語の固有名詞**か（項目48-CS）。

    うにさんの語彙には、地名・人名のような固有名詞も混ざる
    （辞書からの取り込み・文章からの学習で入る）。それが
    **直し先**になると、普通の日本語を固有名詞へ引きずり込む:

        ぼたんのはな → **ぼんのはな**（ボンノ鼻・使用3回）
        「ぼたん」は 1,213回 使っている語なのに、
        「ぼんのはな」という読みが語彙にあるだけで負ける。

    seedcheck の「壊してはいけない」33件のうち、これが1件。

    **まるごと1語であることを見る。** 「団子鼻」は
    団子(一般)＋鼻(一般) の2語に割れるので固有名詞ではない。
    「ボンノ鼻」は1語で 名詞,固有名詞,一般 になる。

    これは関門（後付けで引くだけ・学び38）。直し先を減らすので、
    正しく書いたものを壊す側にしか効かない。
    """
    if not surface:
        return False
    try:
        toks = tokenize_fn(surface)
    except Exception:
        return False
    if len(toks) != 1:
        return False
    pos = toks[0][1] or ''
    return '固有名詞' in pos


def short_pile_overturn_ok(core, best, store, dict_index, tokenize_fn):
    """
    **元の解釈が「短い語の寄せ集め」でしかないなら覆してよい**
    （項目48-ES・設計11・2026-08-18）。

    `たんあごの繋がり → たんごの繋がり` が止まっている理由は、
    芯 `たんあご` が `たん`＋`あご`（どちらも実在語）と読めてしまい、
    「読める並びは覆さない」（項目48-AE）に落ちるから。

    かな同士の自然さ比較は符号が逆に出る（第38回の学び4）が、
    **比べる相手を漢字にする道は第41回に測って駄目だった**
    （設計5。実機メモを11箇所壊した）。残る形は
    **元の解釈の質そのものを見る**こと:

        たんあご = たん(2) ＋ あご(2)    … 2文字以下の寄せ集め
        たんご   = 1語として立つ（語彙にある）

    条件（**全部**）:
      1. 元の解釈の内容語が**全部3文字未満**（助詞・助動詞は数えない）
      2. その内容語が**2つ以上**（＝「寄せ集め」と言える）
      3. 直し先が**1語**として語彙か索引に在り、3文字以上
      4. 直し先が元の解釈の**語のどれかと同じではない**
         （`たん`→`たん` のような置き換えでない）

    敷居も費用の上限も動かさない。**この門は「覆してよい」を
    足すだけ**で、直すかどうかは今までどおり他の門が決める。
    """
    if not core or not best or len(best) < 3:
        return False
    try:
        ts = tokenize_fn(core)
    except Exception:
        return False
    if not ts or ''.join(t[0] for t in ts) != core:
        return False
    content = [t for t in ts
               if not (t[1] or '').startswith(('助詞', '助動詞', '記号'))]
    if len(content) < 2:
        return False
    if any(len(t[0]) >= 3 for t in content):
        return False
    if any(t[0] == best for t in ts):
        return False
    # **1文字の断片は「語」と数えない**（2026-08-18 に実測して足した）。
    #
    # これが無いと、語の途中から切り出した芯が「短い語の寄せ集め」に
    # 見えてしまう。実機のメモを壊した:
    #
    #     変え|たあ|と  芯 `えたあ` ＝ え(1) ＋ た ＋ あ(1)
    #     → **えりあ（エリア）** → `変えりあと`
    #
    # `え` も `あ` も語ではなく、`変え` と `あと` を切った断片。
    # 設計11 の言う「**2文字以下の実在語**の寄せ集め」の
    # 「実在語」を、ちゃんと確かめる:
    #   1文字でないこと ＋ 語彙か索引に在ること。
    for t in content:
        if len(t[0]) < 2:
            return False
        if not known_or_bundled(t[0], store, dict_index):
            try:
                if not store.reading_of(t[0]):
                    return False
            except Exception:
                return False
    # 直し先が1語として立つこと
    try:
        if any(e.get('count', 0) >= 2 for e in store.lookup(best)):
            return True
    except Exception:
        pass
    if dict_index is not None:
        try:
            if dict_index.surfaces_for_reading(best):
                return True
        except Exception:
            pass
    return False


def _covered_by_known(run, store, after_kanji=False, max_len=10,
                      free_from=None, world=None):
    """
    その並びを、**語彙にある読み**と**助詞・機能語**だけで
    端から端まで敷き詰められるか（項目48-CT）。

    芯の再構築が出す「化けた」を見分けるための物差し。
    2026-08-13 に、化けた150件の**85%が芯の再構築**から出ていて、
    その**51%はどこにも無い並び**だと分かった。

    見分けに何を使うかを実測で選んだ（正しい側15例・化けた側13例）:

        `_looks_like_valid_japanese`  正しい側の 5/15 が偽、
                                      化けた側の 9/13 が真。**逆に効く**
        **語彙にある読みか**          正しい側 13/15 が真、
                                      **化けた側は 0/13**

    残る2例（`たんごのつながり` `たんごの`）は「語＋助詞＋語」で、
    1語としては語彙に無い。だから**敷き詰め**で見る。

        たんごのつながり = たんご ＋ の ＋ つながり  → 通る
        のりん           = ？                      → 通らない

    **これは関門ではない。** 通らなければ `continue` して
    次の芯を見るだけで、どれも通らなければ直さない（＝そのまま）。
    「直らない」は失敗ではない、という方針どおり。

    `after_kanji`: 窓の直前が漢字なら、**先頭の数文字は送り仮名**
        なので説明できなくてよい（「かな打ちでのほらい」の窓
        `ちでのほせい` の先頭 `ち` は「打ち」の送り仮名）。
        ここを見落とすと tests_mock の
        「ほらい→ほせい」が落ちる（2026-08-13 に踏んだ）。

    `free_from`: **この位置から先は、その人が元から書いていた文字**
        （直した範囲の外）。そこは「送り仮名・機能語だけで説明が
        付く」並びも通す。項目48-DM。

        直した結果が日本語かどうかを見るのがこの物差しなので、
        **咎めるべきは直した部分**であって、元からあった続きでは
        ない。文の途中の誤字を直すとき、続きの `をみます` のような
        ふつうの日本語が「語彙に無い」というだけで足を引っ張って
        いた:

            もじにゅうりょをみます。
              芯 `もじにゅうりょ` → `もじにゅうりょく` は費用0.5で
              当たっているのに、`もじにゅうりょくをみます` を
              敷き詰められず捨てていた（`みます` が語彙に無い）。

        直した部分そのものは今までどおり**語彙にある読み**でしか
        説明させない。`になうう` のような化けは、そこが直した
        部分なので**変わらず捕まる**。

    `world`: **世の中の集合を部品として使う**（項目48-EJ・設計1）。
        `dict_index.is_world_reading` を渡すと、刈り込む前の辞書に
        在る読みも「説明の付く部品」として数える。**既定は None＝
        今までどおり**なので、これまでの経路の答えは1件も動かない。

        うにさんの指定 (d) のとおり、初期状態の判断は
        「辞書・世の中の集合・書籍の頻度」という**同梱の材料**で
        立てるべきで、学習（count）に頼ってはいけない。
        `すごいね` の `すごい` は初期の語彙に読みとして無いが、
        世の中には在る。渡すかどうかは**実測で決める**こと。
    """
    n = len(run)
    if not n:
        return False
    ok = [False] * (n + 1)
    ok[0] = True
    if after_kanji:
        for _k in range(1, min(3, n) + 1):
            ok[_k] = True
    for i in range(n):
        if not ok[i]:
            continue
        _free = free_from is not None and i >= free_from
        for j in range(i + 2, min(n, i + max_len) + 1):
            if not ok[j]:
                try:
                    if store.has_reading(run[i:j]):
                        ok[j] = True
                except Exception:
                    pass
                if not ok[j] and world is not None:
                    try:
                        if world(run[i:j]):
                            ok[j] = True
                    except Exception:
                        pass
                if not ok[j] and _free \
                        and _okurigana_functional_only(run[i:j]):
                    ok[j] = True
        for j in (i + 1, i + 2, i + 3):
            if j <= n and not ok[j] and is_protected_word(run[i:j]):
                ok[j] = True
    return ok[n]


# 誤打の種類から作る候補に使うかな（項目48-DD）。
# 拗音・促音・小書きも入れる（打ち忘れがいちばん多いのはここ）。
_TYPO_KANA = ('あいうえおかきくけこさしすせそたちつてとなにぬねの'
              'はひふへほまみむめもやゆよらりるれろわをん'
              'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ'
              'ぁぃぅぇぉゃゅょっー')

_TYPO_DAKUTEN = {}
for _a, _b in zip('かきくけこさしすせそたちつてとはひふへほ',
                  'がぎぐげござじずぜぞだぢづでどばびぶべぼ'):
    _TYPO_DAKUTEN[_a] = _b
    _TYPO_DAKUTEN[_b] = _a
for _a, _b in zip('はひふへほ', 'ぱぴぷぺぽ'):
    _TYPO_DAKUTEN.setdefault(_a, _b)
    _TYPO_DAKUTEN[_b] = _a


# --- 項目48-FX: 濁点・半濁点のキーを、隣のキーで打った ---
#
# うにさんの指定（2026-08-19）:
#
# > 「かな入力において、濁音、半濁音は2打鍵であることを考慮します。
# >   ざいりょう、はいりょうはそのため遠く、隣接キーでもありません。
# >   補正対象外です。
# >   さへいりょう、これは濁音の隣接キー判定です。」
#
#     ざいりょう = さ(X) ＋ ゛(@) ＋ いりょう
#     2打鍵めで `@` の隣の `^`(へ) を叩くと **さへいりょう**
#
# かな1文字ずつの編集距離では、これは
# 「さ→ざ の置換(0.4)」＋「へ の削除(2.6)」＝ **3.0** に見える。
# **打鍵で見れば1回の誤り**なので、その値では届かない
# （実測: `さへいりょう` から `ざいりょう` は 3.0 で、
#   敷居 3.0 にわずかに届かず落ちていた）。
#
# `_typo_repairs`（誤打の形を巻き戻す候補づくり）に足す。
# ここで作った候補は**語彙にある読みだけを採る**ので、
# どこにも無い並びには決してならない。
_MARK_SLIP = (os.environ.get('CN_MARK_SLIP', '1') != '0')
# 巻き戻した先の最短の長さ。**短い断片を作らせない。**
# 3文字まで許すと `もこれび`（＝こもれび の順序違い）が
# `もごび` に化けた（2026-08-19 に実測）。語彙には自動学習が拾った
# 3文字の断片が多く、0.5 という安い費用で正解を押しのける。
_MARK_SLIP_MIN_LEN = 4


def _mark_slip_repairs(core):
    """
    「印のキーの隣を叩いた」形を巻き戻した候補を返す。

        さへいりょう → **ざいりょう**（へ は ゛ のつもり）
        さほい…      → ざい…        （ほ も ゛ の隣）

    条件:
      - 直前の字に、その印が**付けられる**こと（さ→ざ）
      - 叩いた字が、その印のキーの**隣**であること
      - 直前の字に**まだ印が付いていない**こと
        （`が` の後ろの `へ` は、印を2度打った話にならない）
      - 出来上がりが `_MARK_SLIP_MIN_LEN` 以上であること
    """
    if not _MARK_SLIP:
        return ()
    try:
        from kana_layout import mark_key_neighbors
    except Exception:
        return ()
    out = []
    n = len(core)
    if n - 1 < _MARK_SLIP_MIN_LEN:
        return ()
    for i in range(1, n):
        prev = core[i - 1]
        for mark, table in (('゛', _MARK_COMPOSE_DAKUTEN),
                            ('゜', _MARK_COMPOSE_HANDAKUTEN)):
            marked = table.get(prev)
            if not marked:
                continue
            if core[i] not in mark_key_neighbors(mark):
                continue
            out.append(core[:i - 1] + marked + core[i + 1:])
    return out


# 清音 → 濁音／半濁音（印を1つ足した形）。
_MARK_COMPOSE_DAKUTEN = {}
for _a, _b in zip('かきくけこさしすせそたちつてとはひふへほう',
                  'がぎぐげございずぜぞだぢづでどばびぶべぼゔ'):
    _MARK_COMPOSE_DAKUTEN[_a] = _b
_MARK_COMPOSE_HANDAKUTEN = dict(zip('はひふへほ', 'ぱぴぷぺぽ'))


def _typo_repairs(core):
    """
    **SPEC の「誤打の種類」を、そのまま巻き戻した候補**（項目48-DD）。

    うにさんの SPEC は誤打を4つに分けている。どれも
    **直し方が形で決まっている**:

        重複打鍵  同じ字が2度  → 1つ消す
        脱字      1字足りない  → 1字入れる
        順序違い  隣が入れ替わり → 入れ替え戻す
        濁点      濁点の付け外し → 付け外しを戻す

    ふつうの編集距離に混ぜると、**別の語のほうが安く見える**ことが
    ある。実測（初期状態・2026-08-14）:

        えととす   → **えとわす**（正解 えとす）
        ふわふふわ → **ふわふわわ**（正解 ふわふわ）
        かづおぶし → **かにおぶし**（正解 かつおぶし）

    ここで作った候補は**語彙にある読みだけを採る**ので、
    「どこにも無い並び」には決してならない。

    戻り値: 巻き戻した読みの一覧（重複なし・元と同じものは除く）。
    """
    out = []
    seen = {core}

    def push(x):
        if x and len(x) >= 2 and x not in seen:
            seen.add(x)
            out.append(x)

    n = len(core)
    # 重複打鍵: 同じ字の連続を1つ減らす
    for i in range(1, n):
        if core[i] == core[i - 1]:
            push(core[:i] + core[i + 1:])
    # --- 項目48-EV（設計13）: **入り込んだ1打を落とす** ---
    #
    # うにさんのメモの誤打の種類に「同じキーが2度入り込んだ」
    # 「隣接キーが入り込んだ」は**最初からある**（プラネタリウムの
    # 見本）。カタカナ語の経路は巻き戻しを持っているのに、
    # **かな経路の `_typo_repairs` に無いのは適用漏れ**だった
    # （項目48-EL「同じ不具合の型は、別の文字種にも及んでいないか
    #   確かめる」と同じ型。Fable 5 の判断・2026-08-18）。
    #
    #     さついだいか → **さいだいか**（＝最大化。`つ` が入り込んだ）
    #
    # **無条件では落とさない。** 落とす字が、**隣の字と同じキーか
    # 隣接キーのときだけ**（それが「入り込み」の定義そのもので、
    # 候補の爆発も防ぐ）。`さ`と`つ` は JISかなで距離 1.0（実測）。
    # 上の重複打鍵（同じ字が2度）はすぐ上で既に見ているので、
    # ここは**違う字**の入り込みだけを見る。
    # **自動補正には入れない**（2026-08-18 に測って決めた）。
    # ここに混ぜたら readcheck 型8種で **直った −16／化けた +6**。
    # 動いた17件のうち**16件が順序違いの型**で、落とした短い形が
    # 正しい入れ替えの答えを**同じ費用（0.5）で押しのけて**いた:
    #
    #     ひきら（正解 ひらき）→ **ひら**（き を落とした）
    #     せんくご（正解 せんごく）→ **せんご**
    #
    # うにさんの指示 (g) は「**まず候補に出す**。自動補正に
    # 上げるのは候補で様子を見てから」なので、**候補一覧の側
    # （`_typo_repairs_intruded`）にだけ置く**。
    # 順序違い: 隣どうしを入れ替え戻す
    for i in range(n - 1):
        if core[i] != core[i + 1]:
            push(core[:i] + core[i + 1] + core[i] + core[i + 2:])
    # 濁点・半濁点の付け外し
    for i in range(n):
        alt = _TYPO_DAKUTEN.get(core[i])
        if alt:
            push(core[:i] + alt + core[i + 1:])
    # 脱字: 1字入れる（**いちばん数が多いので最後**）
    for i in range(n + 1):
        head, tail = core[:i], core[i:]
        for ch in _TYPO_KANA:
            push(head + ch + tail)
    return out


# **もう出来上がっている形を作り直すのに要る「字の並びの良さ」**
# （項目48-EY）。`probe_cmp.py` で測った隙間（+0.94 と +2.91 の
# あいだ・初期状態では +0.88 と +2.9x のあいだ）の真ん中。
_COMPOSE_MIN_NGRAM_GAIN = 1.5


def _typo_repairs_cheap(core):
    """
    **誤打の種類のうち、安いものだけ**（項目48-FG）。

    重複打鍵・順序違い・濁点。**脱字（1字入れる）は入れない。**

    脱字は「かな全部 × 位置全部」を作るので、6字の読みで約500通り。
    複合語の組み直しでは1つずつ `compose_suffix_surface` に掛ける
    ので、**1行 5.5ms → 99.6ms（18倍）**になった（実測・2026-08-18）。
    うにさんの的で脱字が要るものは1つも無い。

    **`_typo_repairs` はそのまま**（かな経路はこれまでどおり脱字も
    使う。あちらは語彙にある読みだけを採るので候補が爆発しない）。
    """
    out = []
    seen = {core}

    def push(x):
        if x and len(x) >= 2 and x not in seen:
            seen.add(x)
            out.append(x)

    n = len(core)
    # 重複打鍵: 同じ字の連続を1つ減らす
    for i in range(1, n):
        if core[i] == core[i - 1]:
            push(core[:i] + core[i + 1:])
    # 順序違い: 隣どうしを入れ替え戻す
    for i in range(n - 1):
        if core[i] != core[i + 1]:
            push(core[:i] + core[i + 1] + core[i] + core[i + 2:])
    # 濁点・半濁点の付け外し
    for i in range(n):
        alt = _TYPO_DAKUTEN.get(core[i])
        if alt:
            push(core[:i] + alt + core[i + 1:])
    return out


def _wide_repairs_enabled():
    """
    **誤打の種類を全部使うか**（項目48-FC で入れた広げ方）。

    既定は使う。`CORRECTNOTE_NO_B=1` のときだけ「入り込んだ1打を
    落とす」だけに戻す。**測るための切り替え**で、設計18 の壊れが
    入口(a) と入口(b) のどちらから来ているかを分けるのに使う。
    """
    import os as _os
    return _os.environ.get('CORRECTNOTE_NO_B') != '1'


def _d18_enabled():
    """
    **設計18（かな混じりの語連続を入口にする）を動かすか**
    （項目48-FF）。

    **既定は動かさない。** `CORRECTNOTE_D18=1` のときだけ。
    Fable 5 の指示「まず測るだけ。火入れはこちらの判断まで待つ」
    に従い、測るための入口を切り替えで持っておく。
    """
    import os as _os
    return _os.environ.get('CORRECTNOTE_D18') == '1'


def _content_word_spans(line, tokenize_fn, max_len=8):
    """
    **自立語が2つ以上つながった範囲**を返す（項目48-FF・設計18）。

    かなを含んでよい。ただし:

      - **漢字を1字は含む**こと（かなだけの並びは既存の経路が持つ）
      - 助詞・助動詞・記号は**切れ目**（またがない）
      - **読みを言い切れる**トークンだけ（項目48-DE
        「推測の上に推測を重ねない」）
      - 長さは 3〜`max_len` 字

        誘い消化  → 誘い（動詞）＋消化（名詞）＝ 自立語2つ・漢字あり ○
        歳で以下  → 歳／で／以下 の `で` が切れ目なので、
                    自立語2つの連続にはならない ✕

    戻り値: [(始まり, 終わり, 文字列), ...]（長いものから）
    """
    try:
        toks = tokenize_fn(line)
    except Exception:
        return []
    if not toks:
        return []
    out = []
    runs = []
    cur = []
    for t in toks:
        pos = t[1] or ''
        if pos.startswith(('助詞', '助動詞', '記号')) or not t[5]:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
            continue
        cur.append(t)
    if len(cur) >= 2:
        runs.append(cur)
    for run in runs:
        # 連続する2語以上のすべての組を見る（長いものから）
        n = len(run)
        for i in range(n):
            for j in range(n, i + 1, -1):
                s, e = run[i][3], run[j - 1][4]
                if not (3 <= e - s <= max_len):
                    continue
                chunk = line[s:e]
                if not any(is_kanji(c) for c in chunk):
                    continue
                out.append((s, e, chunk))
    out.sort(key=lambda x: -(x[1] - x[0]))
    return out


def _unit_table_ready():
    """
    **「1語として在るか」の表が読めているか**（項目48-FC）。

    読めているときだけ、誤打の種類を全部使って組み直す
    （表が守ってくれる前提の上に立つ広げ方なので、
      **表が無いなら広げない**）。
    """
    try:
        import seed_japanese
        return bool(seed_japanese.available())
    except Exception:
        return False


def _charngram_available():
    """文字3連の表が読めているか（読めないときは門を閉じる）。"""
    try:
        import charngram
        return bool(charngram.available())
    except Exception:
        return False


def _charngram_gain(before, after):
    """
    **直した先のほうが、日本語の文字の並びとしてどれだけ良いか**
    （項目48-EY）。

    `charngram.score` は1文字あたりの対数確率（0に近いほど
    日本語らしい）。その**差**を返す。正なら良くなっている。
    表が無ければ None（＝判断しない＝採らない）。
    """
    try:
        import charngram
        if not charngram.available():
            return None
        return charngram.score(after) - charngram.score(before)
    except Exception:
        return None


def compose_from_intruded(chunk, readings, store, dict_index,
                          tokenize_fn=None):
    """
    **造語めいた複合語を、開いた読みから直して表記を組む**
    （項目48-EX・うにさん指示 (g) の自動補正ぶん・2026-08-18）。

    第43回で**候補には出る**ようになった道を、自動補正にも通す。
    うにさんの指示（2026-08-18・実機の画面を見て）:

        「Shift+左右で4文字を選択したら候補が出ましたが、
          これを**初期状態で自動補正される**ところを目指します」

        殺意代価 → 開いて さついだいか → `つ` を落として さいだいか
                 → 最大（実績語）＋ 化 → **最大化**
        最大家事 → 開いて さいだいかじ → 最大 ＋ 化 ＋ 時 → **最大化時**

    **自動補正なので、門は候補一覧より厳しくする**（設計10 の 5
    「自動補正に上げるのは『候補が1つだけ・明らかに自然』のとき」）:

      1. **元の複合が「単位として」どこにも無いこと**
         （語彙・索引。在るなら正しく書けている＝項目48-CF/CG）。
      2. 開いた読み、または**入り込んだ1打を落とした読み**から、
         **語＋接尾**で表記が組めること（`compose_suffix_surface`）。
         語幹は漢字の実績語であることが要る。
      3. **組めた表記がただ1つ**であること。2つ以上に割れたら
         決め手が無いので触らない（候補一覧には両方出てよい）。
      4. 組めた表記が元の塊と違うこと（`重要性`→`重要性` は無視）。

    **初期状態でも動く**: `最大` は初期の索引に在る（実測）。
    学習には依らない＝うにさんの指定 (d) に沿う。
    """
    if not chunk or not readings:
        return None
    # (0) **もう「語＋接尾」の形の塊は、直した先が
    #     「字の並び」として明らかに良くなるときだけ作り直す**
    #     （項目48-EY・2026-08-18）。
    #
    #     もとは「**末尾が接尾の字なら触らない**」という打ち切り
    #     だった。`開発者` を `会派者` にしてしまったのを塞ぐため
    #     に置いた門で、`操作性` `一時的` `実行時` `実体化` も
    #     同じ形で守れていた。
    #
    #     **うにさんの指摘（2026-08-18）:**
    #
    #         「補正はされていますが**局所的すぎます**。汎用的な、
    #           違和感を感じる文字列判定がないと**際限のない修正が
    #           続きます**」
    #
    #     そのとおりで、この打ち切りは**うにさんの的そのもの**も
    #     塞いでいた（`再退化 → 最大化`・`誘い消化 → 最小化` は
    #     直せる読みも組める表記も在るのに、末尾が `化` という
    #     だけで捨てていた。`diag_odd.py` で実測）。
    #
    #     **「この並びは変だ」という絶対の物差しは、同梱の材料には
    #     無い**（`probe_odd.py` で8つの軸を実測。語彙・索引・
    #     世の中の集合・敷き詰め・共起・連接コスト・文字3連・接尾の
    #     品詞、どれも違和感のある並びとふつうの複合語が重なる）。
    #     語幹だけ見る案はふつうに書く語の **30%** が通り抜け
    #     （`probe_stem2.py`: 使用回数 86回・初回起動時 20回…）、
    #     アプリの文書から複合語の表を作る案はうにさんが実際に書く
    #     語の **66%** を取りこぼした（`probe_wordset.py`）。
    #
    #     **だが「比べる」形なら分かれる。** 同じ読みの2つの表記の
    #     どちらが日本語の並びらしいかは、文字3連（項目48-BN・
    #     アプリ自身の文書から作った表）が言える（`probe_cmp.py`）:
    #
    #         採ってほしい組み直し  -0.04 〜 **+3.20**
    #         捨ててほしい組み直し  -3.38 〜 **+0.94**
    #
    #     **+0.94 と +2.91 のあいだが空いている。** 当てはめでは
    #     なく隙間なので、真ん中の **+1.5** を余裕にする（初期状態
    #     でも同じ隙間があることを確かめてある: -0.31〜+4.01 と
    #     -2.74〜+0.88）。数はいつでも `probe_cmp.py` で引き直せる。
    #
    #     表が読めないときは、**もとの打ち切りに戻る**（知らない
    #     ものを勝手に通さない）。
    _suffix_tail = chunk[-1] in set(_SUFFIX_SURFACE.values())
    if _suffix_tail and not _charngram_available():
        return None
    # (1) 単位として在るなら触らない
    try:
        if store.lookup(chunk) or store.reading_of(chunk):
            return None
    except Exception:
        return None
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(chunk):
                return None
        except Exception:
            return None
    # (1'') **世の中で1語として在る表記なら触らない**
    #       （項目48-FC・設計16・うにさんの問い (h) への答え）。
    #
    #       門(1) と**同じ考えを、もっと大きな辞書で**やる。
    #       語彙も刈り込み索引も「このアプリが提案しうる語」に
    #       絞ってあるので、**正しく書けているのに載っていない語**が
    #       たくさんある（第45回の実測: ふつうの複合語 36件のうち、
    #       同梱の材料で守れるのは 11件だけ）。
    #
    #       これが第44回の宿題そのものを片づける。文字3連
    #       （項目48-EY）は**ゴミへの化け**は止めるが、
    #       **もっともらしい別語への化け**は止められなかった:
    #
    #           投機的 → 同期的   文字3連 +2.56（止まらない）
    #           符号化 → 複合化   文字3連 +2.08（止まらない）
    #
    #       どちらも `投機的`・`符号化` が**1語として在る**ので、
    #       ここで止まる。実測（15組）: **捨ててほしい 14/15**。
    #
    #       **「直し先が1語であること」は要求しない。** それを
    #       要求すると `最大家事 → 最大化時` が落ちる（`最大化時` は
    #       辞書に無い派生語。第45回に実測）。**元を守る側だけ**に使う。
    #
    #       表が無ければ **None** が返り、これまでどおりになる。
    try:
        import seed_japanese as _sj
        if _sj.is_unit(chunk):
            _trace('造語', f'{chunk!r} は1語として在る（項目48-FC）ので'
                           f'触らない')
            return None
    except Exception:
        pass
    # (1') **読みは「解析が言い切っているもの」だけを使う**
    #      （項目48-DE「推測の上に推測を重ねない」・2026-08-18 に
    #        実機メモで痛い目を見て足した）。
    #
    #      漢字の読みの推測（`reading_combos_with_rank`）を全部
    #      渡していたら、**珍しい読みの上に接尾の合成を重ねて**
    #      うにさんのメモを26行も壊した:
    #
    #          説明書 → **説明化**  （書 を `か` と読んだ）
    #          再変換 → **再編化**  ／ 仕様書 → **使用化**
    #          操作性 → **捜索性**  ／ 実行時 → **実業時**
    #          一時的 → **位置時的** ／ 経補正 → **今日性**
    #
    #      解析が `説明書 = せつめいしょ` と言い切っているなら、
    #      `せつめいか` は**そもそも読みではない**。
    #      `殺意代価` は解析が `さついだいか` と言い切るので通る。
    _ar = _analyzer_reading(chunk, tokenize_fn) if tokenize_fn else None
    if not _ar:
        return None
    # (2)(3) 組める表記を集める
    found = set()
    for rd in (_ar,):
        if not rd:
            continue
        drops = _typo_repairs_intruded(rd)
        # **誤打の種類を全部使う**（項目48-FC・設計16 の効き目）。
        #
        # 第44回は「入り込んだ1打を落とす」だけだった。広げると
        # `再退化 → 最大化`（濁点）・`誘い消化 → 最小化` が自動でも
        # 直るが、同時に**もっともらしい別語への化け**が起きて、
        # 文字3連（項目48-EY）では止められなかった:
        #
        #     投機的 → 同期的 +2.56 ／ 符号化 → 複合化 +2.08
        #
        # **上の門(1'') がこれを止める**（`投機的`・`符号化` は
        # 1語として在るので、そもそもここへ来ない）。だから
        # いま初めて広げられる。**表が無ければ広げない**
        # （＝第45回までと同じ振る舞いに戻る）。
        if _unit_table_ready() and _wide_repairs_enabled():
            # **脱字（1字入れる）はここでは使わない**（項目48-FG）。
            #
            # `_typo_repairs` の脱字は「かな全部 × 位置全部」を作る
            # ので、6字の読みなら **約500通り**。その1つずつに
            # `compose_suffix_surface` を掛けると、**1行あたり
            # 5.5ms → 99.6ms（18倍）**になった（2026-08-18 に実測。
            # うにさんから「解析が長く、待たされる」と報告された）。
            #
            # しかも**買えるものが無い**: `再退化` は濁点、
            # `殺意代価`・`誘い消化` は入り込み、`差す代価` は
            # 隣接キーで届く。脱字で届く的は1つも無い。
            for _extra in (typo_repairs_nearby_key(rd),
                           _typo_repairs_cheap(rd)):
                for _x in _extra:
                    if _x not in drops:
                        drops.append(_x)
        for cand in [rd] + drops:
            got = compose_suffix_surface(cand, store, dict_index,
                                         want_parts=True)
            if not got:
                continue
            head, full, stem_rd, n_suf = got
            if full == chunk:
                continue
            # (2'') **正しい語を「別の字で書き直す」だけなら採らない**
            #       （2026-08-18 に実測して足した）。
            #
            #       塊の頭が、語幹と**同じ読み**なのに**別の表記**に
            #       なるなら、それは訂正ではなく書き直しである:
            #
            #           一時的 → **位置時的**（いち を 位置 と書いた）
            #           実体化 → **実態化**  （じったい を 実態 と）
            #
            #       `最大家事` は頭 `最大` が語幹 `さいだい` の表記
            #       そのものなので通る（直しているのは `家事`→`化時`）。
            _pre = chunk[:len(chunk) - n_suf] if n_suf < len(chunk) else ''
            if _pre and _pre != head:
                _pre_rd = (_analyzer_reading(_pre, tokenize_fn)
                           if tokenize_fn else None)
                if _pre_rd and _pre_rd == stem_rd:
                    _trace('造語', f'{chunk!r} → {full!r} は頭を別の字で'
                                   f'書き直すだけなので採らない')
                    continue
            # (2') **1打を落として直したと言うなら、その部分の
            #      読み方が変わっていなければならない**
            #      （2026-08-18 に実測して足した）。
            #
            #      落としただけで頭がそのままなら、それは訂正では
            #      なく**ただの削除**である。これが無いと、
            #      うにさんがいつも書く語を壊した:
            #
            #          誤字補正 → **誤字性**（`ほ` を落として 補正 を消した）
            #          自動補正 → **自動性**（同じ形）
            #
            #      `殺意代価 → 最大化` は頭が `殺意` → `最大` と
            #      **変わっている**ので通る。既存の「読みに開くだけの
            #      置き換えは訂正ではない」と同じ考え方。
            if cand in drops and chunk.startswith(head):
                _trace('造語', f'{chunk!r} → {full!r} は頭が変わって'
                               f'いないので、訂正ではなく削除'
                               f'（採らない）')
                continue
            # (0) の続き — **もう出来上がっている形を作り直すなら、
            #     直した先が字の並びとして明らかに良くなること**
            if _suffix_tail:
                _g = _charngram_gain(chunk, full)
                if _g is None or _g < _COMPOSE_MIN_NGRAM_GAIN:
                    _trace('造語', f'{chunk!r} → {full!r} は字の並びが'
                                   f'良くならない（{_g}）ので採らない')
                    continue
            found.add(full)
    if len(found) != 1:
        if found:
            _trace('造語', f'{chunk!r} → {sorted(found)} は'
                           f'決め手が無いので自動では直さない')
        return None
    surface = found.pop()
    _trace('造語', f'{chunk!r} → {surface!r}（開いて誤打を戻し、'
                   f'語＋接尾で組んだ）')
    return surface


def _typo_repairs_intruded(core):
    """
    **入り込んだ1打を落とした形**（項目48-EV・設計13）。

    うにさんのメモの誤打の種類に「同じキーが2度入り込んだ」
    「隣接キーが入り込んだ」は最初からあり（プラネタリウムの見本）、
    カタカナ語の経路は巻き戻しを持っている。**かな経路に無いのは
    適用漏れ**だった（項目48-EL と同じ型）。

        さついだいか → **さいだいか**（＝最大化。`つ` が入り込んだ）

    **無条件では落とさない。** 落とす字が、**隣の字と同じキーか
    隣接キーのときだけ**（それが「入り込み」の定義そのもので、
    候補の爆発も防ぐ）。`さ`と`つ` は JISかなで距離 1.0（実測）。

    **`_typo_repairs` とは別にしてある。** あちらは自動補正が使う
    ので、落とした短い形を混ぜると**正しい入れ替えの答えを
    押しのける**（実測: readcheck で 直った −16／化けた +6・
    うち16件が順序違いの型）。うにさんの指示 (g)
    「**まず候補に出す**」のとおり、**候補一覧だけで使う**。
    """
    n = len(core)
    if n < 3:
        return []
    out = []
    for i in range(1, n - 1):
        c = core[i]
        if c == core[i - 1] or c == core[i + 1]:
            continue            # 重複打鍵は `_typo_repairs` が見る
        if _intruded_keystroke(c, core[i - 1], core[i + 1]):
            cand = core[:i] + core[i + 1:]
            if cand not in out:
                out.append(cand)
    return out


# 「入り込み」とみなす鍵の近さ（JISかな配列の距離）。
# `さ`-`つ` が 1.0（隣）。1.0 までを「隣接キー」とする。
_INTRUDE_MAX_DIST = 1.0


def _intruded_keystroke(ch, left, right):
    """
    その1字は「隣の字を打つついでに入り込んだ1打」か
    （項目48-EV・設計13）。

    左右どちらかの字と**同じキー**（濁点・小書きの取り違え）か、
    **隣接キー**（配列の上で距離 1.0 以内）なら、入り込みとみなす。
    かな以外は見ない（ローマ字側は別の経路が持っている）。
    """
    if not ch or not is_hiragana(ch):
        return False
    try:
        import kana_layout as _kl
    except Exception:
        return False
    for other in (left, right):
        if not other or not is_hiragana(other):
            continue
        try:
            if ch in (_kl.SMALL_KANA_PAIR.get(other, ''),
                      _kl.DAKUTEN_BASE.get(other, '')):
                return True
            if _kl.kana_key_distance(ch, other) <= _INTRUDE_MAX_DIST:
                return True
        except Exception:
            pass
    return False


# **隣接キーの打ち間違いとみなす距離**（項目48-FA）。
# `_INTRUDE_MAX_DIST` と同じ 1.0。JISかなで `さ`–`つ` が 1.0。
_NEARBY_KEY_MAX_DIST = 1.0


def typo_repairs_nearby_key(core, max_dist=_NEARBY_KEY_MAX_DIST):
    """
    **1打だけ隣のキーに打ち間違えた形**（項目48-FA・設計15）。

    SPEC の「誤打の種類」4種（重複打鍵・脱字・順序違い・濁点）は
    `_typo_repairs` が持っているが、**置換（隣のキーを押した）だけ
    別扱い**だった。かな経路では `find_similar_readings` が
    距離つきで探すので要らなかったが、あちらは
    **「置き換えた先が既知の読みであること」**を要求する。

        こうりざか → こうりつか（＝効率化）

    `こうりつか` は派生語なので**読みとしてはどこにも無い**。
    だから既知の読みしか返さない道では届かない。ここは
    **読みの形だけ**を返し、表記が組めるかは呼ぶ側が決める。

    **候補一覧でだけ使うこと。** 自動補正に入れると、
    `投機的 → 同期的`・`符号化 → 複合化` のような
    **もっともらしい別語への化け**が起きる（第44回に実測。
    48-EY の比べる門でも止まらない）。

    戻り値: 置き換えた読みの一覧（元と同じもの・重複は除く）。
    """
    if not core or len(core) < 2:
        return []
    try:
        import kana_layout as _kl
    except Exception:
        return []
    out = []
    seen = {core}
    for i, ch in enumerate(core):
        if not is_hiragana(ch):
            continue
        for alt in getattr(_kl, 'ALL_KANA', ()):
            if alt == ch or not is_hiragana(alt):
                continue
            try:
                if _kl.kana_key_distance(ch, alt) > max_dist:
                    continue
            except Exception:
                continue
            cand = core[:i] + alt + core[i + 1:]
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


def _drop_one_repeat(core):
    """
    **同じ字の連続を1つ減らした形**を、ぜんぶ返す（項目48-DC）。

        えととす   → ['えとす']
        ふわふふわ → ['ふわふわ']
        もぐぐら   → ['もぐら']

    「重複打鍵」は SPEC の誤打の種類のひとつで、**直しは
    「1つ消す」以外にありえない**。にもかかわらず、いまは
    ふつうの編集距離に混ぜているので、別の語に飛んでいた:

        えととす   → **えとわす**（正解 えとす）
        ふわふふわ → **ふわふわわ**（正解 ふわふわ）
        もぐぐら   → **ももぐら**（正解 もぐら）

    長さが同じまま並べ替わっているものまである。
    """
    out = []
    for i in range(1, len(core)):
        if core[i] == core[i - 1]:
            cut = core[:i] + core[i + 1:]
            if cut and cut not in out:
                out.append(cut)
    return out


def rebuild_window_core(window, store, tokenize_fn, max_cost=3.0,
                        min_margin=0.6, tie_band=1.0,
                        context_vec=None, surrounding_words=(),
                        after_kanji=False, whole_only=False,
                        readable_hint=False, keep_tail='',
                        dict_index=None, attest_text='',
                        input_method=None):
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
        from vocabulary import find_similar_readings, store_is_young
    except Exception:
        return None
    if whole_only:
        # 混合塊（漢字を読みに戻した列）の解決では、塊全体が
        # 1つの語であることが分かっているので、部分の芯は作らない
        # （末尾の「う」等が活用語尾として剥がれ、届く語に
        #   届かなくなるため。めもちちょう → めもちちょ 等）。
        cores = []
        readable = bool(readable_hint)
        if not _okurigana_functional_only(window):
            cores = [(0, len(window))]
    else:
        # 窓全体が正しい日本語として読めるなら、そこから芯を
        # 削り出してはいけない。芯だけを見ると「うっかり」の
        # っかり が しっかり に、「たびに」の たび が別の語に
        # 化ける（実機・2026-08-09）。個々の芯にも同じ検査はあるが、
        # 剥がした後の断片では「窓が元々正しかった」ことが
        # 分からない。
        # **閉じる門ではなく、高い敷居にする**（項目48-AE・2026-08-11）。
        #
        # うにさん:「正しく読めるとは、辞書と一致するではなく、
        # 単語と単語の結びつきに違和感がないこと」。
        # ここは「辞書で読める＝触らない」で門を閉じていたので、
        # `たんあご` のように**短い既知語に分解できてしまう壊れた
        # 並び**が全部素通りしていた。
        #
        # 読める並びは正しいことのほうが多いので、門は残す。
        # ただし**明らかに自然になる直しなら通す**（下で判定）。
        # --- 項目48-EN（設計7）: 芯の再構築にも「世の中の語は
        #     触らない」を（2026-08-17・Fable 5 の設計）---
        #
        # うにさんの指定 (d) のとおり、初期状態の判断は同梱の材料で
        # 立てる。**「語彙に無い」は「壊れている」ではない** ——
        # 世の中に在るなら、**知らないだけで壊れてはいない**。
        # 同じキーの読み替えには門(2')（世の中の集合）があるのに、
        # かな連続の芯の再構築には同じ門が無かった。
        # 項目48-DY で入れたのは「剥がさない形」の芯だけ（すぐ下）。
        #
        # **測り方でつまずいた話**（学びとして残す・2026-08-17）:
        # うにさんの育った語彙で測ったら **1件も動かなかった**ので、
        # 一度「効かない」と判断して外した。**外したのが間違い**で、
        # 初期状態で測り直したら `もちごめ → もこごめ`
        # （芯 `ちごめ` → `こごめ`）がここで止まった。
        # 育った語彙では `もちごめ` が別の経路（ひらがな連続の
        # `count>=2` の門・項目48-EO）で先に壊れていたので、
        # **この門まで届いていなかっただけ**だった。
        # **「効かない」と言う前に、初期状態でも測る。**
        #
        # **窓まるごとにだけ掛ける。** 部分芯（送り仮名を剥いだ形や
        # 切り離した芯）には掛けない —— `かんむり` の教訓の逆で、
        # 直せるものまで止まる恐れがあるため。
        # **ひらがなだけの並びに限る**（世の中の集合は読みしか
        # 持たないので、漢字まじりは常に「無い」になる）。
        if dict_index is not None and window \
                and all(is_hiragana(c) or c == 'ー' for c in window):
            try:
                if dict_index.is_world_reading(window):
                    _trace('芯', f'{window!r} → 世の中に在る語なので'
                                 f'触らない（知らないだけで'
                                 f'壊れていない・項目48-EN）')
                    return None
            except Exception:
                pass
        readable = bool(readable_hint) or _looks_like_valid_japanese(
            window, tokenize_fn)
        if readable:
            _trace('芯', f'{window!r} → 辞書としては読める。'
                         f'明らかに自然になる直しだけ通す')
        cores = window_cores(window, store, after_kanji=after_kanji)
    _trace('芯', f'{window!r}（直前が漢字={after_kanji}）→ '
                 f'{[window[x:y] for x, y in cores] or "芯なし"}')
    # **長い芯から見る**（項目48-CR）。短いほうから見ると、短い芯で
    # 当たった時点で決まってしまい、長いほうにある正解へ届かない:
    #     のりごんを → 芯'りごん'→'りん' → **のりん**
    #                  （芯'のりごん' なら 'のりこん' で正解）
    #     かまぐらを → 芯'まぐら'→'かぐら' → **かかぐら**
    #                  （芯'かまぐら' なら 'かまくら' で正解）
    # 出来上がりは語彙にも辞書にも無い並びになる。
    cores = sorted(cores, key=lambda p: p[1] - p[0], reverse=True)
    for c_s, c_e in cores:
        core = window[c_s:c_e]
        if len(core) < 3:
            _trace('芯', f'{core!r} → 3文字未満なので対象外')
            continue
        # **送り仮名を剥がさない形は、世の中に在る語なら触らない**
        # （項目48-DY）。直前が漢字のとき、窓の頭から始まる芯は
        # `window_cores` が足した「剥がさない形」。そこは
        # 「剥がす」という判断を通していない余分な候補なので、
        # **世の中に在る語なら壊れていない**とみなす。
        #
        #     竹かんむり → 芯 `かんむり` は刈り込んだ索引に無いが、
        #                  **刈り込む前の辞書には在る** → 触らない
        #     昨日ひどまえ → 芯 `ひどまえ` はどこにも無い → 直す
        if after_kanji and c_s == 0 and dict_index is not None:
            try:
                if dict_index.is_world_reading(core):
                    _trace('芯', f'{core!r} → 送り仮名を剥がさない形だが、'
                                 f'世の中に在る語なので触らない')
                    continue
            except Exception:
                pass
        if is_protected_word(core) or _is_all_auxiliary(core):
            _trace('芯', f'{core!r} → 守る語／助詞だけなので対象外')
            continue
        # **末尾の機能語を剥がした残りが1文字なら触らない**
        # （項目48-DI）。断片は偶然どれかの語に一致しやすい。
        #
        #     これをみます。 → これを**みなす**。
        #     芯 `みます` ＝ `み`（1文字）＋ `ます`（機能語）。
        #     `みます` は語彙に無いので「知らない並び」に見えるが、
        #     ふつうの日本語である。`みなす`（537回）が費用1.0で
        #     当たって勝っていた（第36回にもあった古い誤検知）。
        #
        # 同じ考えの門は `find_editable_spans` の側には**既にある**
        # （「語尾を切り離した結果、語幹が短すぎるなら触らない。
        #   断片は偶然どれかの語に一致しやすく誤爆の元になる」）。
        # **芯の再構築の側に無かった**ので、片方だけ素通りしていた
        # （学び22「片方にしか置かないと、そちらを迂回される」）。
        _tail_len = _trailing_functional_len(core)
        if _tail_len and len(core) - _tail_len <= 1:
            _trace('芯', f'{core!r} → 機能語を剥がすと1文字しか'
                         f'残らないので対象外')
            continue
        # **頭の側にも同じ門を掛ける**（項目48-GZ・門の掛け忘れ6例目）。
        #
        #     ああつにする。 → **あいつにする。**
        #     芯 `ああつ` ＝ `ああ`（指示語・守る語）＋ `つ`（1文字）。
        #     `あいつ` が費用1.0・訂正1で当たって勝っていた。
        #     かな入力では あ(3) と い(E) が隣なので、隣のキーの門も
        #     通ってしまう（ローマ字入力では隣ではないので止まる。
        #     **同じ文字列が入力方式しだいで化けていた**）。
        #
        # 末尾側は項目48-DI で塞いだが、**頭側は空いていた**。
        # 断片が偶然どれかの語に一致しやすいのは、どちらの端でも
        # 同じ話（学び22「片方にしか置かないと、そちらを迂回される」）。
        #
        # **見るのは「守る語」だけ。** 末尾側と同じように機能語を
        # 貪欲に剥がす形も試したが、**頭では効きすぎた**:
        #
        #     はなづ（正解 はなつ）  は＋な で2文字剥がれる
        #     けいやぐ（正解 けいやく）けいや が機能語で説明が付く
        #
        # 実測（型8種・600語）: 貪欲版は **直る 48件を落として**
        # 化けを7件しか減らさなかった（初期状態では 49件落として3件）。
        # 頭のかなは語の一部であることが多く、末尾とは事情が違う
        # （`window_cores` が頭を助詞しか剥がさないのと同じ理由）。
        # **守る語まるごと＋1文字**だけに絞れば、上の巻き添えは
        # どれも `is_protected_word` が False なので当たらない。
        if is_protected_word(core[:-1]):
            _trace('芯', f'{core!r} → 守る語 {core[:-1]!r} に1文字'
                         f'足しただけなので対象外')
            continue
        # **芯の終わりが「を」なら触らない**（項目48-CL）。
        # `を` は現代語ではほぼ必ず助詞で、語の末尾にならない。
        #
        #     がぶぶを確認しました。 → がぶぶん確認しました。
        #     （芯が `ぶぶを` になり、`ぶぶん` に直して**助詞を食った**）
        #
        # 「既知語＋助詞なので触らない」という関門は既にあるが、
        # **前の部分が既知語のときしか効かない**（`あんじょうを` は
        # 守られるが `がぶぶを` は素通り）。ここは語彙に頼らず、
        # **形だけ**で切る。
        #
        # 項目48-CH（漢字塊が `を` を跨ぐ）と同じ話が、
        # **かな連続の経路にも残っていた**。
        # 実測: 実機のメモ＋正しい日本語＋散文＋SPEC で、
        # 末尾が `を` の芯を直していたものは**0件**。失う直しは無い。
        if 'を' in core:
            # **終わりだけでなく、途中の `を` も**（項目48-DO）。
            # 現代語で `を` は助詞にしかならず、**語の読みの中に
            # 現れない**。芯が `を` を跨いでいるなら、それは
            # 1語ではなく句を跨いでいる。
            #
            #     読みをみます。 → **読みこみます。**
            #     （窓 `みをみます` の芯 `みをみ` が `みこみ` に。
            #       助詞 `を` が `こ` に化けた・2026-08-15 実測）
            #
            # 項目48-CL は終わりの `を` だけを見ていたので、
            # **内側の `を` は素通り**していた。
            _trace('芯', f'{core!r} → 助詞「を」を含むので対象外')
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
        # **直前が「既知語＋助詞」なら、そこは本物の切れ目**
        # （項目48-DP）。下の「既知語の途中を切っている」検査は、
        # たまたま跨いで出来た並びまで既知語とみなす:
        #
        #     これはたんほです。 → 芯 `たんほ` が
        #       **`はたん`（破綻）の途中を切っている**として捨てられる
        #       （`は` は助詞、`たん` は `たんほ` の頭にすぎない）
        #
        # 実測（型を8種に増やした readcheck・2026-08-15）:
        #     `これは{w}です。` の型だけ **直った 0 / 419**
        #     他の型は 42〜164 直る。**この形だけ丸ごと死んでいた。**
        def _known_here(frag):
            try:
                return any(e['count'] >= 2 for e in store.lookup(frag))
            except Exception:
                return False

        _boundary_ok = (c_s >= 2 and window[c_s - 1] in PARTICLES_1CHAR
                        and _known_here(window[:c_s - 1]))
        if _boundary_ok:
            _trace('芯', f'{core!r} → 直前が「既知語＋助詞」'
                         f'（{window[:c_s]!r}）なので本物の切れ目')
        if c_s > 0:
            _crossed = None
            for _x in range(max(0, c_s - 6), c_s):
                # **助詞から始まる並びは、既知語の証拠にしない**
                # （項目48-DP）。助詞を次の語に貼り付けただけの
                # 偶然の一致だから:
                #
                #     これはたんほです → `はたん`（破綻）が
                #       芯 `たんほ` を塞いでいた
                #
                # 助詞より**前**から始まる並びは今までどおり見る。
                # そちらは本当に語を跨いでいる:
                #
                #     あらかじめお渡しする → `あらかじめ` が
                #       芯 `じめお` を塞ぐ（塞いで正しい）
                if _boundary_ok and _x >= c_s - 1:
                    continue
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
        # 正しく読める芯は壊れていないことが多い。**ただし門は
        # 閉じない**（項目48-AE）。ここも敷居にして、明らかに
        # 自然になる直しだけ通す。判定は下の `readable` でまとめて
        # 行う（同じ判定を2か所に書かない）。
        if _looks_like_valid_japanese(core, tokenize_fn):
            _trace('芯', f'{core!r} → 芯だけでも読める。'
                         f'明らかに自然になる直しだけ通す')
            readable = True
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
        # **連打を1つ消した形が語彙にあるなら、それが答え**
        # （項目48-DC）。重複打鍵の直しは「1つ消す」以外に無いので、
        # ふつうの編集距離に混ぜて別の語と競わせない。
        # 結果は必ず**語彙にある語**なので、どこにも無い並びには
        # ならない。
        # **誤打の種類を巻き戻した候補を、ふつうの探索に混ぜる**
        # （項目48-DD）。**即決はしない。**
        #
        # 最初は「巻き戻して語彙にあれば、それが答え」と決め打ちに
        # したが、**ふつうの探索が見つける本命と比べないまま返す**
        # ので、うにさんの realcheck が1件落ちた:
        #
        #     たんほの繋がり → **たんぼ**の繋がり（狙い たんごの）
        #     濁点を戻した「たんぼ」（田んぼ）は確かに語だが、
        #     「たんご」（単語・1,315回）と比べていなかった。
        #
        # 候補として**安い費用で差し出す**だけにして、どれを採るかは
        # いままでの仕組み（費用・訂正回数・一般的さ）に任せる。
        # 判断経路は増えない（設計方針）。
        # **漢字から推した読みには、巻き戻しを使わない**（項目48-DE）。
        # 混合塊の経路は「漢字の読みを組み合わせた推測」を渡してくる
        # （`whole_only=True` がその印）。推測が外れていると、
        # そこへ巻き戻しを掛けて**でたらめな読みが実在の語になる**:
        #
        #     使う形 → 読みの推測 `しうぎょう` → 「ょ」を入れて
        #              `しょうぎょう` → **商業**
        #     （janome の無い経路で実測・2026-08-14）
        #
        # 打った文字そのもの（かなの並び）には巻き戻しを使う。
        # **推測の上に推測を重ねない。**
        # **長音の書き分けが違うだけなら、誤字ではない**（項目48-EL）。
        # `めにゅう` は語彙の `めにゅー`（メニュー）と同じ語。
        # ここを通さないと、似た読みを探しに行って
        # `にゅうひ`（入費）`とつにゅう`（突入）に化ける（実機）。
        _lv = long_vowel_variant_of_known(core, store)
        if _lv:
            _trace('芯', f'{core!r} は {_lv!r} の長音の書き分け違いなので'
                         f'触らない')
            continue
        _repairs = []
        for _c in (() if whole_only else _typo_repairs(core)):
            try:
                if store.has_reading(_c):
                    # 費用 0.5・訂正1回。**連打の削除(0.6)より少し安い**。
                    # 「誤打の形そのもの」なので、ふつうの置換より
                    # ありそうだが、桁違いに安くはしない。
                    _repairs.append((_c, 0.5, 1))
            except Exception:
                pass
        # **印のキーの隣を叩いた形は、少し高く置く**（項目48-FX）。
        # 「どのキーを押すつもりだったか」を1段よけいに推している
        # ので、上の巻き戻し（誤打の型そのもの）と同点にしない。
        # 同点にしたら `せいけけん`（＝せいけん の重複打鍵）が
        # `せいげん` と拮抗して、直っていたものが直らなくなった
        # （2026-08-19 に実測）。
        _seen_rep = {_r for _r, _c2, _e in _repairs}
        for _c in (() if whole_only else _mark_slip_repairs(core)):
            if _c in _seen_rep:
                continue
            try:
                if store.has_reading(_c):
                    _repairs.append((_c, 0.7, 1))
                    _seen_rep.add(_c)
            except Exception:
                pass
        found = find_similar_readings(core, store, max_cost=max_cost + 1.5)
        if _repairs:
            _seen_r = {r for r, _c, _e in found}
            found = _repairs + [x for x in found if x[0] not in
                                {r for r, _c, _e in _repairs}]
            found.sort(key=lambda rce: (rce[2], rce[1], -len(rce[0]), rce[0]))
            _trace('芯', f'{core!r} 誤打を巻き戻した候補='
                         f'{[r for r, _c, _e in _repairs][:4]}')
        if not found and store_is_young(store):
            # **育っていない語彙のときだけ、
            #   「辞書から取り込んだだけの語」も見る**（項目48-CX）。
            #
            # `find_similar_readings` の既定は `min_count=2`＝
            # 「実際に使われた語だけ」。育った語彙ではこれが正しい
            # （珍しい語に引き寄せられない）。だが**ダウンロード
            # しただけの初期状態では、使用回数が全部1**なので、
            # 14,551 読みのうち **373（2.6%）しか候補にならない**。
            # 残り 14,178 は辞書から取り込んだ普通の語なのに、
            # 芯の再構築から**まるごと見えていなかった**。
            #
            #   実測（初期状態・400語×6種・2026-08-14）:
            #       いまのまま  直った **9** / 化けた 25
            #                   ← **直らないのに、たまに化ける**
            #       ここを緩める 直った **433** / 化けた 70
            #
            #   実測（うにさんの育った語彙）:
            #       常に緩める  直った 599→595 ／ 化けた 131→**145**
            #                   realcheck 6→5   ← **育った側は悪くなる**
            #
            # だから**育っていない語彙のときだけ**緩める。
            # 「使われた読みの割合」で見分ける（`store_is_young`）:
            #     初期状態 2.6%  対  うにさんの語彙 77.9%
            # **空振りしたときだけ**という後詰めも重ねる。
            #
            # 育った語彙にも掛けたら、うにさんのメモの
            #     かな入力用 → **かな食用**
            # という化けが出た（janome の無い経路・実測）。
            # だから**育った側は1文字も変えない**形にする。
            found = find_similar_readings(core, store,
                                          max_cost=max_cost + 1.5,
                                          min_count=1)
            if found:
                _trace('芯', f'{core!r} → 使った語では当たらないので、'
                             f'辞書から取り込んだだけの語も見る')
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
        # **かな連続の最後の助詞は動かさない**（項目48-DJ）。
        # 芯が窓の終わりまで届いているとき、その末尾は
        # 「文が続く直前の助詞」なので、置き換えで消してはいけない。
        #
        #     もじにゅうりょに行きます。
        #       芯 `もじにゅうりょに` → `もじにゅうりょく`
        #       → **に が消える**
        #
        # ここで落とすと、次の（1文字短い）芯 `もじにゅうりょ` に
        # 順番が回り、`もじにゅうりょく` が助詞を残したまま入る。
        # **門を閉じるのではなく、正しい芯に譲らせる。**
        if keep_tail and c_e >= len(window):
            _kept = [f for f in found if f[0].endswith(keep_tail)]
            if len(_kept) != len(found):
                _ate = [f[0] for f in found
                        if not f[0].endswith(keep_tail)][:3]
                _trace('芯', f'{core!r} → 末尾の助詞 {keep_tail!r} を'
                             f'食う候補を外した（{_ate}）')
            found = _kept
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
        # **より一般的なほうを優先**（うにさんの指定・2026-08-10）。
        # 打鍵の近さでは最有力でも、桁違いによく使う語が同じ
        # 訂正回数で届くなら、そちらを採る。
        _general = _prefer_general(found, store, cost, edits, max_cost)
        if _general is not None and _general != best:
            _trace('芯', f'{core!r} → {best!r} より一般的な '
                         f'{_general!r} を採る')
            best = _general
            cost = next(f[1] for f in found if f[0] == _general)
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
                if picked is None and _core_is_unnatural(core, store):
                    # **元の並びが語として成立していない**なら、
                    # 決め手が無くても直す（うにさんの指定・
                    # 2026-08-10「元が不自然なら自動補正する。
                    # 補正候補はより一般的なほうを優先」）。
                    # 正しく書けている語はここへ来ないので、
                    # 「正しい文を壊さない」とは両立する。
                    picked = _break_tie_by_generality(close, store)
                    how = '一般的さ'
                if picked is None:
                    _trace('芯', f'{core!r} → 拮抗 '
                                 f'{[f[0] for f in close]} の決め手が無い'
                                 f'（周りの語={list(surrounding_words)[:5]}）')
                    continue    # 決め手が無い。直さない
                _trace('芯', f'{core!r} → 拮抗 {[f[0] for f in close]} を'
                             f'{how}で {picked!r} に決めた')
                best = picked
        # **辞書として読める並びは、明らかに自然になるときだけ直す**
        # （項目48-AE）。読める並びは正しいことのほうが多いので、
        # 敷居を高くする（`MIN_GAIN_READABLE`）。
        # janome が無い環境では「意見なし」になるので、
        # **今までどおり触らない**（default=False）。
        if readable:
            _after = window[:c_s] + best + window[c_e:]
            # --- 項目48-EP（設計5）: **かな同士で比べない**
            #     （2026-08-17・Fable 5 の設計。第38回の学び4の適用）
            #
            # `たんあごの繋がり → 単語の繋がり` は、芯 `たんあご` が
            # `たんご`（費用2.6）に**届いているのに**、ここで
            # 「読める並びを覆すほど自然にならない（差 −5823）」と
            # 落ちていた（第40回の診断）。
            #
            # 理由は第38回の学び4のとおり: **かな同士の自然さ比較は
            # 符号が逆に出る**。janome は裸のかな `たんごの` を
            # 短く割るので、元の `たんあごの`（＝`たん`＋`あご`＋`の`
            # と、実在語に割れてしまう）より高くついてしまう。
            # 項目48-EA は「比べる相手を漢字にして」これを通した。
            # 同じ置き換えを、芯の再構築の判定にもする。
            #
            # **直し先に最有力の表記が在るときだけ**置き換える。
            # 無ければ今までどおり。敷居（48-AE）は動かさない。
            # **測って戻した**（2026-08-17）。`_best_surface_for(best)`
            # で漢字にして比べると、`たんあごの繋がり → たんごの繋がり`
            # は通るようになったが、**うにさんのメモを11箇所壊した**:
            #
            #     塊の直後のひらがな  → 塊の直後**て**のひらがな
            #     通常のひらがな探索  → 通常**て**のひらがな探索
            #     手のひらから溢れ出す → 手**て**のひらから溢れ出す
            #     変えたあと          → 変え**りあ**と
            #     秋田駅（あたえき）   → （あた**える**）
            #
            # readcheck 型8種でも **直った +304 / 化けた +67**。
            # 漢字は自然さを上げる向きに強く働くので、**この門が
            # 事実上効かなくなる**（門を外したのと同じ）。
            # 設計5 の但し書き「それでも増えるなら戻す」に従った。
            # 詳しくは SPEC の「試して入れなかったもの（第41回）」。
            if not _naturalness.worth_touching_readable(
                    window, _after, default=False):
                # --- 項目48-EW（設計14）: **並記なら覆してよい** ---
                #
                # 自然さの軸は3度測って駄目だった（かな同士＝符号が
                # 逆・漢字化＝効きすぎ・寄せ集め判定＝他の経路の
                # 正解を先取り）。
                #
                # **4度目も駄目だった（項目48-HV・2026-08-21）。**
                # 設計23（項目48-HM）が 48-EA の近接条件に単位の表を
                # 並べたので、**同じ置き換えをここにも**と考えて測った
                # ——「元が非単位（`rebuild_is_suspicious`）かつ直し先が
                # よく使う1語」なら覆す、という形。
                # 的（`たんあごの繋がり → たんごの繋がり`）は通り、
                # 初期の readcheck は **直った +145／化け +8**、
                # **fpcheck は 0 のまま**、実機材料の的148 は 55→**56**。
                # だが**初期＋実機メモで正しい文を3行壊した**:
                #
                #     隣接キーを取ります  → 隣接キーを**リトマス**
                #     済んだらまず補正を  → 済んだら**んず**補正を
                #     「やがいぶんしょう」→ 「やがい**んしょう**」
                #     たんb後の繋がり     → **単行**の繋がり（先取り再発）
                #
                # 理由は項目48-HM/48-HN が書いたとおり:
                # **単位の表は活用について何も言えない**ので、
                # `とります` `まず` のような正しい形まで「非単位」に
                # 見える。**かなの芯に表を当ててはいけない。**
                # 48-HM が `_no_kana` で線を引いたのと同じ線が、
                # ここでは**芯そのものがかな**なので引けない。
                #
                # 残っているいちばん強い証拠は
                # **並記**（判断の順序2「同じメモ内に同じ読みの語が
                # 別の表記で書かれているならそれに合わせる」）。
                #
                #     たんあごの繋がり  芯 `たんあご → たんご`
                #     表記 `単語` は、すぐ近くの行に何度も書いてある
                #     → 覆してよい
                #
                # この形は**設計11 の失敗を構造的に避ける**:
                # `たんここう → たんこう` の表記（炭鉱・単行）は
                # 近くに書かれていないので、先取りが起きない。
                # 並記の無い単独行では動かないが、それは正しい
                # （**証拠が無いのだから触らない**）。
                _att_surf = _best_surface_for(best, store)
                if attest_text and _att_surf and _att_surf != best \
                        and len(_att_surf) >= 2 \
                        and _att_surf in attest_text:
                    _trace('芯', f'{core!r} → {best!r}（表記 {_att_surf!r}）'
                                 f'は近くに文字どおり書かれているので覆す')
                else:
                    _trace('芯', f'{core!r} → {best!r} は、読める並びを'
                                 f'覆すほど自然にならないので直さない'
                                 f'（差 {_naturalness.gain(window, _after)}）')
                    continue
                # *（設計11「短い語の寄せ集めなら覆してよい」は
                #   第42回に測って戻した。readcheck の化け +20 と、
                #   実機メモの `たんb後の繋がり` が `単語` → `単行` に
                #   なる先取りが起きたため。上の並記の門は、
                #   その失敗を構造的に避ける形になっている。
                #   詳しくは SPEC の「試して入れなかったもの（第42回）」）*
        # **直した先が、語彙と助詞だけで敷き詰められること**（項目48-CT）。
        # 敷き詰められない並び（のりん・かかぐら・になうう）は、
        # 語彙にも辞書にも無い＝日本語ですらない。
        _after3 = window[:c_s] + best + window[c_e:]
        # **続きが助詞から始まるときだけ**、そこから先を大目に見る
        # （項目48-DM）。助詞は語の切れ目なので、そこまでで直しは
        # 閉じている。切れ目でない位置から先を大目に見ると、
        # 語の途中で直しを止めたものまで通ってしまう:
        #
        #     しどめるを → **しずめるを**（芯 `しどめ`→`しずめ`。
        #                    残り `るを` が「送り仮名＋助詞」に
        #                    見えるので通っていた）
        _tail_free = window[c_e:]
        _free_from = (c_s + len(best)
                      if _tail_free and _leading_particle_len(_tail_free)
                      else None)
        if not _covered_by_known(_after3, store, after_kanji,
                                 free_from=_free_from):
            _trace('芯', f'{core!r} → {best!r} にすると {_after3!r} になり、'
                         f'語彙と助詞で説明できないので採らない')
            continue
        # **1文字違いは、隣のキーで説明が付くときだけ**（項目48-FX・
        # うにさんの指定・2026-08-19「1文字違うだけでは補正しません、
        # その違いが隣接キーかどうか。隣接判定はかな入力と
        # ローマ字入力で変わる」）。
        #
        # **決まった答えに掛ける**のが要点。候補の段階で落とすと、
        # 拮抗の裁定に使う相手まで消えて、それまで拮抗で止まって
        # いた別の直しが独り勝ちする（実機メモで `たんほの` が
        # `たんぼの` に化けた。2026-08-19 に実測）。
        # ここで `continue` すれば、**何も直さない**に落ち着く。
        if input_method and not _adj_ok_one_char(core, best, input_method):
            _trace('芯', f'{core!r} → {best!r} は1文字違うだけで、'
                         f'その違いは隣のキーでは説明が付かない'
                         f'（{input_method}）ので採らない')
            continue
        _trace('芯', f'{core!r} → {best!r} に直す')
        return (c_s, c_e, best)
    return None


def _next_char(line, end):
    """
    塊のすぐ後ろの1文字（行の終わりなら None）。

    **送り仮名が付いているかの判断だけに使う**（項目48-AP）。
    塊の最後の字は、塊の中だけを見ても送り仮名の有無が分からない
    （`見` と `見せる` の見分けが付かない）。行を持っている側から
    1文字だけ渡す。
    """
    if not line or end is None:
        return None
    return line[end] if 0 <= end < len(line) else None


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


# --- 方針2（同音異義語の文脈置換）の条件 -------------------------------
#
# 「正しく書けている実在語を、文脈だけを根拠に別の表記へ置き換える」
# のは、このエンジンで唯一「明確な誤りだと言えないもの」を直す経路。
# 正しく書いた文を壊す危険がいちばん大きいので、実機のメモ全文で
# 測った上で、誤爆がゼロになる範囲まで条件を絞ってある。
#
# 実測（2026-08-10・実機の session.json 全6タブ・387箇所が候補）:
#   閾値 0.12 未満には、直してはいけないものが並ぶ。
#     階層→回想 +0.024 / 性格→正確 +0.018 / 移し→映し +0.090
#   閾値 0.12 以上に残る漢字だけの語は、すべて直すべきものだった。
#     洗濯→選択 +0.275 / 開業→改行 +0.181 / 名刺→名詞 +0.128
#     賀古→過去 +0.301
#   0.12 以上でも、送り仮名を含む語には誤爆がある（換わり→変わり
#   +0.211。「書き換わりました」は正しい）。だから**漢字だけの語**に
#   限る。かな・カタカナを含む語は、字面が近い別語と共起が混ざり、
#   共起だけでは裁けない。
_HOMOPHONE_MIN_MARGIN = 0.12    # 既定の 0.08 より厳しい。上の実測から
_HOMOPHONE_MIN_USAGE = 10       # 置き換え先の使用実績（回）

# **証拠の太さ**（項目48-BY・2026-08-13）。
#
# `判断の精度に依存しない` が `判断の制度に依存しない` に化けていた。
# 差は 0.1335 で、敷居 0.12 を超えていた。**敷居では止められない**:
#
#     精度 → 制度（誤爆）  差 0.1335  決め手の共通相手 **1語**
#     開業 → 改行（正）    差 0.1806  決め手の共通相手 15語
#     洗濯 → 選択（正）    差 0.2750  決め手の共通相手 19語
#
# 0.1335 と 0.1806 は近すぎて、敷居を上げると `開業→改行`
# （うにさん指定・実機メモ tab0 153行）が巻き添えになる。
# **分かれるのは差ではなく「共通の相手の数」のほう**。
# 学び19「しきい値は『上げ下げ』ではなく『別の軸』で切る」。
#
# 中身: `制度` の共起は11件しか無く、`ない`(15) がベクトルの
# 72%を占めていた。相手の `置き換え` も `ない`(102) が64%。
# **共通の相手はこの1語だけ**でコサインが 0.4627 出ていた。
# 「似ている」のではなく「たまたま同じ1語の隣にいた」。
#
# 実機のメモ全6タブ＋正しい日本語＋散文だけで方針2が通ったのは
# **3件だけ**で、共通の相手が1語なのは**誤爆のその1件のみ**。
# 数え直す道具は `homocheck.py`。
_HOMOPHONE_MIN_SHARED = 2       # 共通の共起相手が何語以上あれば信じるか

# 案A（項目48-DZ）の入り／切り。**既定は切**（2026-08-16・保留）。
#
# うにさんの判断:
#
# > 売って、打って、撃っては**併用して使われる語**であり、
# > 付近の用語に合わせるのは適していないようです。周囲の字に
# > 合わせる処理をどこまで使うかは検討しますが、入ったとしても
# > これらの単語に関しては**周囲に合わせるレベルを下げる**
# > 必要があります。
#
# 実測では 実機メモ +4行／化け0／誤検知0／readcheck 変化なしだったが、
# 増えた4行のうち1行が `「に」と売って` → `「に」と撃って` で、
# まさにこの「併用される同音の一族」に当たっていた。
# **並記だけでは、一族の中のどれかを選ぶ根拠にならない。**
#
# 次にやるなら「同じ読みに実在語が何語あるか」で強さを変える
# （一族が厚い読みでは並記を証拠にしない）。それまで既定は切。
# 環境変数 `CN_CONJ_HOMOPHONE=1` で測定用に入れられる。
_CONJ_HOMOPHONE = (os.environ.get('CN_CONJ_HOMOPHONE', '0') != '0')


def _is_all_kanji(text):
    """漢字だけで書かれているか（送り仮名・カタカナを含まない）。"""
    return bool(text) and all(is_kanji(c) for c in text)


# --- 案A: 活用形を「補正のときだけ」作る（項目48-DZ・2026-08-16）---
#
# **なぜ要るか。** うにさんの語彙では、活用する語が
# **基本形でしか入っていない**（`janome_import.py` の設計判断・
# 2026-08-09。活用の断片が語彙を汚す誤爆を避けるため）。
# 一方、**メモから学んだ語は活用形のまま入る**。この非対称が
# 「直す先が語彙に無いので原理的に直せない」形を生んでいる:
#
#     なおり → 語彙は `治り`(563) だけ。`直り` は無い。
#              ただし **`直る`(539) は在る**
#     うっ   → 語彙に無し。ただし **`打つ`(939) は在る**
#     うつる → 語彙は `移る`(1210)。書かれた `映る` は無い
#
# 右クリックの候補側は `candidates.align_okurigana()` で
# 「`打つ` ＋ 元の送り仮名 `っ` → `打っ`」を作っているので、
# **候補には出るのに自動では直らない**というずれになっていた
# （うにさんのメモ16行目「※『治り』を右クリックすると…」）。
#
# ここでは**語彙を1行も増やさない**。比べるときだけ活用形を作る。
# 駄目なら、この経路を切るだけで完全に元へ戻る。
#
# **危ないことは分かっている**: 送り仮名を含む語は
# `換わり→変わり`(+0.211) のように共起だけでは裁けない
# （上の `_HOMOPHONE_MIN_MARGIN` の但し書き）。だから
# **測ってから採否を決める**。案B（語彙に活用形を入れる）と
# 同じ物差しに並べること。

# 連用形・音便形の語尾から、辞書に載る形（基本形）の語尾へ。
# 五段は行ごとに決まる。一段は語尾に `る` が付いた形が基本形。
_CONJ_TO_BASE = {
    'い': ('う', 'いる'),
    'き': ('く', 'きる'),
    'ぎ': ('ぐ',),
    'し': ('す', 'しる'),
    'ち': ('つ',),
    'に': ('ぬ',),
    'び': ('ぶ',),
    'み': ('む',),
    'り': ('る',),                 # 直り → 直る
    'っ': ('つ', 'る', 'う'),      # 打っ(た) → 打つ／直っ → 直る
    'え': ('える', 'う'),
    'け': ('ける', 'く'),
    'せ': ('せる', 'す'),
    'て': ('てる', 'つ'),
    'ね': ('ねる', 'ぬ'),
    'べ': ('べる', 'ぶ'),
    'め': ('める', 'む'),
    'れ': ('れる', 'る'),
}


def _split_stem_tail_local(word):
    """語を「漢字・カタカナの部分」と「後ろのひらがな」に分ける。

    `candidates._split_stem_tail` と同じもの。補正エンジンから
    候補作りのモジュールを呼びたくないので、ここに置いてある。
    """
    i = len(word)
    while i > 0 and is_hiragana(word[i - 1]):
        i -= 1
    return word[:i], word[i:]


def _conjugated_alts(surface, reading, store):
    """
    書かれている活用形（漢字＋送り仮名）に対して、
    **基本形が語彙に在る**同音の別表記を、元の送り仮名に合わせて作る。

    例: `治り`(なおり) → `なおる` を引く → `直る`(539) →
        送り仮名を合わせて **`直り`**

    語彙には何も足さない。作った形はこの判断のあいだだけ使う。
    戻り値: [{'surface', 'count', 'category'}, ...]
    """
    stem, tail = _split_stem_tail_local(surface)
    if not stem or not tail:
        return []
    if not _is_all_kanji(stem):
        return []
    if len(tail) > 2:
        return []
    if not reading or not reading.endswith(tail):
        # 読みの末尾が送り仮名と一致しない形は、語幹の読みを
        # 切り出せない（`行った`(いった) のような音便）。
        # ここでは確かな形だけを扱う。
        return []
    rstem = reading[:-len(tail)]
    if not rstem:
        return []

    wanted = {reading}                      # 基本形そのものが書かれている形
    for base_tail in _CONJ_TO_BASE.get(tail[-1], ()):
        wanted.add(rstem + tail[:-1] + base_tail)

    out = []
    seen = {surface}
    for r in sorted(wanted):
        for e in store.lookup(r):
            if e['count'] < _HOMOPHONE_MIN_USAGE:
                continue
            e_stem, e_tail = _split_stem_tail_local(e['surface'])
            if not e_stem or not e_tail:
                continue
            if not _is_all_kanji(e_stem):
                continue
            if e_stem == stem:
                # **書かれている語そのものが語彙に裏打ちされている**
                # （`直り` に対する `直る`・539回）。正しく書けて
                # いるので、この語は動かさない。
                #
                # これが無いと、`A ⇒ B` と並べた行で**向きが逆に
                # なる**。並記は左右どちらから見ても成り立つので、
                # 並記だけでは向きを決められない:
                #
                #     半角が治りました。⇒ 半角が**直り**ました。
                #       → 右の `直り` を見て `治り`(563) へ書き換えた
                #
                # 向きを決めるのは「語彙の裏打ちがある側は動かさない」
                # のほう（判断の順序1と同じ考え方）。
                return []
            if len(e_stem) != len(stem):
                continue
            made = e_stem + tail            # = align_okurigana(surface, e)
            if made in seen:
                continue
            seen.add(made)
            # `vec` は**共起を測るときに使う表記**。
            # 作った活用形（`直り`）はメモに一度も出ていないので
            # 共起ベクトルを持たない。持っているのは語彙に在る
            # 基本形（`直る`・539回）のほう。ここを分けておかないと、
            # 置き換え先の点がいつも 0 になって必ず負ける。
            out.append({'surface': made, 'vec': e['surface'],
                        'count': e['count'],
                        'category': e.get('category')})
    return out


# --- 項目48-EA: かなのまま残った語を漢字へ ---

# **誤字の見本が載っている行**（矢印・引用符・記号・英数）。
# `charngram._NOT_PROSE` と同じ考え方で、そちらに区切りの記号を足した。
#
# **これが無いと、うにさん自身の説明を壊す。** 実機メモで測ったら
# 当たった14件のうち9件がこの形だった:
#
#     「『たんこ』に直せば『**たんご**』に補正できます」
#       → 「…『**単語**』に補正できます」（説明が意味をなさなくなる）
#     「『やがいぶんしょう』という誤入力」→「『野外ぶんしょう』…」
#
# 学び45（材料が自己言及だと数字が化ける）と同じ罠。
_LOOKS_LIKE_EXAMPLE = re.compile(
    r'[→⇒⇔←↔`「」『』"“”\'‘’|*#\[\]{}<>=+\\_~^$%&／・（）]|[0-9A-Za-z]')

# ひらがなで書いた外来語を、何文字から見るか（項目48-EC）。
#
# **長さは原理ではない。** うにさんの指摘（2026-08-16）:
#
# > しかしそうすると、カタカナ3文字はどうなんだ、
# > カタカナ2文字はどうなんだと、同じ問題は出てきます。
#
# そのとおりだった。5→4 に下げただけでは同じ問いが 3・2 で出る。
# 何を守っているのかを測り直した。**危ない形**（同じ行にカタカナ語が
# あり、そこから距離1の**正しいかな語**も書かれている）を語彙から
# 全部作って数えた:
#
#     最短    危ない組    通してしまう（＝誤検知）
#      2      2,911         131
#      3        991         110
#      4        113          31   ← 下限だけ下げた時点のこの道
#      5          8           5   ← 第37回
#
# 中身を見ると、**全部が「語彙に漢字・ひらがなの表記を持つ語」**
# だった（かめい＝仮名564／きろく＝記録114／はんたい＝反対17）。
# `katakana_for_hiragana`（そのまま変換する道）はこの門を持っていて、
# **打ち間違いの道だけが持っていなかった**。門を揃えたら:
#
#     最短 1・2・3・4・5 のどれでも **誤検知 0件**
#
# つまり守っているのは長さではなく、次の4つ:
#   - 書かれているかなが**正しく書けている語ではない**
#     （`_has_non_katakana_surface`）
#   - **語の頭が動かない**（`とどらっぐ → ドラッグ` の助詞食いを塞ぐ）
#   - **並記**（直した結果が同じ行にある）
#   - **明らかに自然になる**（項目48-AE の敷居）
#
# 残す下限は「カタカナ語として立つ最短」＝2文字（メモ・キー・バー）。
# 実機メモ・fpcheck・readcheck は 2 と 4 で**完全に同じ**だった。
_LOAN_KANA_MIN = int(os.environ.get('CN_LOAN_KANA_MIN', '2'))

# この道の入り／切り（測定用）と、見る連続の最短の長さ。
_KANA_TO_KANJI = (os.environ.get('CN_KANA_TO_KANJI', '1') != '0')
_K2K_MIN_LEN = 3

# 置き換え先として認める使用実績。方針2と同じ 10 回。
_K2K_MIN_USAGE = 10


def _kanji_surface_for_reading(reading, store):
    """
    この読みに対して「**漢字でしか書かない語**」が語彙にあるなら返す。

    かな・カタカナの表記が実績つきで登録されている読みは、
    **かなも正しい書き方**なので触らない:

        つながり → 繋がり(1235) と つながり(1211) の両方 → 触らない
        たんご   → 単語(1317) だけ                      → 直してよい
        かよわい → かよわい(218) だけ（漢字が無い）      → 触らない
    """
    try:
        entries = store.lookup(reading)
    except Exception:
        return None
    if not entries:
        return None
    best = None
    for e in entries:
        surf = e.get('surface') or ''
        if not any(is_kanji(c) for c in surf):
            if e.get('count', 0) >= 2:
                return None        # かなでも書く語
            continue
        if best is None or e['count'] > best['count']:
            best = e
    if best is None or best['count'] < _K2K_MIN_USAGE:
        return None
    return best['surface']


# --- 項目48-FU: シフトを押し損ねた拗音を、漢字にして戻す ---
#
# うにさんの指定（2026-08-19）:
#
# > 「シフトキーを押していないものを補正するときは、漢字変換させる。
# >   （きようちよう ⇒ 強調）」
#
# **なぜ「かなを直す」で止めずに漢字まで行けるのか。**
#
# 項目48-EA のかな→漢字の道は、`並記`（その漢字が近くに
# 書いてある）を関門にしている。**打ち間違いでたまたま別の語の
# 読みになった並びを、漢字にして固めてしまう**のを防ぐためだった
# （かふん → 花粉。正解は ふかん）。
#
# ここは**証拠の種類が違う**。
#
#     きようちよう … 語ではない。しかも `きょうちょう`（語彙に
#                    21回）と **小書き／大書きの違いだけ**で一致する。
#                    ＝**シフトを押し損ねた形そのもの**
#     かふん       … それ自体が正しく書ける語（花粉）。
#                    小書きの話ではない
#
# 打ち損ねが**字の形として証明できている**ので、並記は要らない。
# 代わりに、証明が崩れる形を全部塞ぐ:
#
#   (1) **打たれた並びそれ自体が語なら触らない**（`known_or_bundled`）。
#       `もつ`(持つ) `かつ` `いつか` `かつて` `してい`(指定)
#       `おもう`(思う) `ういんどう`(ウインドウ) …
#       語彙の読み 22,714 のうち、大書きに開くと語彙の別の読みに
#       ぶつかるものが **111件**ある。その全部がこの門で止まる。
#   (2) **直せる位置は「い段＋やゆよ」だけ**。拗音はシフトを
#       押さないと出ない字で、かつ前の字が決まっている。
#       小書き母音（ぁぃぅぇぉ）は外来語の書き方で、漢字にならない
#       （`_kanji_surface_for_reading` が None を返す）ので入れない。
#       促音「っ」も入れない —— ぶつかる 111件のうち大半が
#       `もつ／かつ／まさつ` の形で、得るものより危ない。
#   (3) **答えが1つに定まらないなら触らない**。組み合わせが複数の
#       読みに当たり、漢字表記が食い違うなら判断がつかない。
#   (4) 漢字にする条件は項目48-EA と**同じ関数**を使う
#       （`_kanji_surface_for_reading`＝かなでも書く語は触らない・
#       使用実績 10回以上）。新しい物差しを増やさない。
#   (5) **明らかに自然になること**（項目48-AE の敷居）。
#
# 拗音の頭に立てる字（い段）。`ぢ` `ゐ` は現代の入力では出ない。
_YOUON_HEADS = frozenset('きぎしじちにひびぴみり')
# 大書きで打たれた拗音 → 本来の小書き。
_YOUON_SMALL = {'や': 'ゃ', 'ゆ': 'ゅ', 'よ': 'ょ'}
# この道で見る並びの最短の長さ。`ちよう` `きよう` のような3字は
# それ自体が語になりやすいので見ない（`きよう`＝器用）。
_SHIFT_MIN_LEN = 4
# 直す位置の上限。組み合わせは 2^n 通り見るので、天井を置く。
# 実機のメモで n が 3 を超える並びは 1つも無かった。
_SHIFT_MAX_POS = 6


def _youon_small_positions(text):
    """小書きの拗音（ゃゅょ）が立っている位置の集合。"""
    return frozenset(i for i, c in enumerate(text) if c in 'ゃゅょ')


def _shift_lost_positions(typed):
    """
    **シフトを押し損ねた拗音になりうる位置**を返す。

    「い段の字＋や/ゆ/よ」の並びだけ。ここが空なら、この道は
    そもそも関係が無い（ほとんどの並びはここで抜ける）。
    """
    return [i for i in range(1, len(typed))
            if typed[i] in _YOUON_SMALL and typed[i - 1] in _YOUON_HEADS]


def _shift_lost_kanji(typed, store, dict_index=None):
    """
    打たれた並びが「シフトを押し損ねた拗音」に見えるなら、
    **本来の読みと、その漢字表記**を返す。違えば (None, None)。

    戻り値: (読み, 漢字表記)
    """
    n = len(typed)
    if n < _SHIFT_MIN_LEN:
        return None, None
    if not all(is_hiragana(c) or c == 'ー' for c in typed):
        return None, None
    pos = _shift_lost_positions(typed)
    if not pos or len(pos) > _SHIFT_MAX_POS:
        return None, None
    # 直せる位置の組み合わせを全部見る。**並べ直してから**扱う
    # （集合を経由しても順序が動かないように。項目48-DR）。
    #
    # **安い判定から順に置く**（項目48-FT と同じ考え）。ここは
    # 1行の中の窓ごとに何十回も呼ばれるので、`known_or_bundled`
    # （語彙・索引・世の中の集合の3つを引く）を先に置くと効く。
    # 当たりが出てから1回だけ引く。
    found = {}
    for mask in range(1, 1 << len(pos)):
        chars = list(typed)
        for b, i in enumerate(pos):
            if (mask >> b) & 1:
                chars[i] = _YOUON_SMALL[typed[i]]
        cand = ''.join(chars)
        try:
            if not store.has_reading(cand):
                continue
        except Exception:
            continue
        kanji = _kanji_surface_for_reading(cand, store)
        if kanji:
            found[cand] = kanji
    if not found:
        return None, None
    # (1) 打たれた並びそれ自体が語なら、打ち損ねではない。
    if known_or_bundled(typed, store, dict_index):
        _trace('シフト', f'{typed!r} はそれ自体が語なので触らない')
        return None, None
    # (3) 漢字表記が食い違うなら、判断がつかないので触らない。
    if len(set(found.values())) > 1:
        _trace('シフト', f'{typed!r} → {sorted(set(found.values()))} は'
                         f'どれとも決められないので触らない')
        return None, None
    # 同じ漢字に行き着くなら、読みは**使われている回数の多いほう**。
    # 同点は読みの字並び順で決める（起動ごとに答えが変わらないため）。
    best = sorted(found, key=lambda r: (-_usage_count(r, store), r))[0]
    return best, found[best]


# --- 項目48-EG: 記号のつもりで打った、同じキーのかな ---
#
# うにさんの指定（2026-08-16）:
#
#     おおごえぬ       ⇒ おおごえ！      （かな入力。1 のキー）
#     しつもんめ       ⇒ しつもん？      （かな入力。/ のキー）
#     おわりのくてんる   ⇒ おわりのくてん。 （かな入力。. のキー）
#     おおごえ１       ⇒ おおごえ！      （ローマ字入力。Shift の押し忘れ）
#     しつもん・       ⇒ しつもん？      （ローマ字入力）
#
# `（→ゆ` の**逆向き**。同じ物理キーの上での取り違えなので、
# 表は `kana_layout.same_key_characters` がすでに持っている。
#
# **危ないのは「る」と「め」。** 正しい語の末尾によく出る
# （おしえ**る**・うまれ**る**・むす**め**・する**め**）。
# 語彙＋辞書の 22,705 語で、どれだけ巻き込むかを数えて門を決めた:
#
#     門                                      巻き込む正しい語
#     前が既知語（それだけ）                        90件
#     ＋末尾が独立した語として切れる                  16件
#     ＋全体が辞書に載っていない                      1件
#     ＋前は末尾の既知語でもよい（ゆるめた）             4件
#       （もちごめ・はちぶんめ・きりめ・ひとりじめ。全部「め」）
#     ＋行の終わりに限る                        ← いま入れている形
#
# **半角の `. / 1` は入れない。** URL・パス・版番号の末尾を
# 句点に変えてしまう。うにさんが挙げた かな と全角だけにする。
_SAMEKEY_PUNCT = {
    'ぬ': '！', '１': '！',
    'め': '？', '・': '？',
    'る': '。',
}

# 直す先の手前に要る「語」の最短の長さ（`くてん` のような2文字を拾う）。
_SAMEKEY_MIN_WORD = 2

# **世の中の集合を、敷き詰めの部品としても使うか**（項目48-EJ・設計1）。
# 入れると `すごいね` `きれいだね` のように、初期の語彙に読みが
# 無い形容詞も説明が付くようになる（そのぶん通りやすくなる）。
# **実測で決める切り替え**。数字は SPEC の項目48-EJ を見ること。
_SAMEKEY_TILE_WORLD = False

# --- 項目48-EI: 記号の連続への違和感（うにさん指定 (f)・2026-08-17）---
#
# うにさんの指定:
#
#     「『する。』が『す。。』になっていた。
#       **『。。』に違和感を感じる必要がある**」
#
# 起きたこと: `補正る。` の `る` に**行中の**同じキーの読み替え
# （項目48-EG）が乗り、`補正。。` を作った。第38回までは
# 「行末の語連続だけ」を見ていたので、`る` の右に `。` が
# 在る形はそもそも対象にならなかった。**行中まで広げたときに、
# その安全が黙って外れていた。**
#
# 2段で塞ぐ:
#
#   (a) 語連続の**直後に文の記号が既に在るなら、その末尾は
#       読み替えの対象外**。文の記号はもう打てているのだから、
#       同じキーを打ち損ねた話ではない。
#       **閉じ括弧の前は対象のまま**（`（強調ぬ）` を守る）。
#   (b) 全置換の最終検査で、**元に無かった句読点の連続**が
#       生まれたら採らない（`_new_punct_run`）。
#
# 文の記号（`。、．，！？`）。ここに `）」』】` は入れない。
_SENTENCE_PUNCT = '。、．，！？'
# そのうち「句読点」。**連続したら必ずおかしい**もの。
# `！！` `！？` は同じキーの連続の正しい出力なので、この集合から
# 外してある（項目48-EG の `ぬぬ → ！！` を通すため）。
_HARD_PUNCT = '。、．，'


def _samekey_word_run(line):
    """行の末尾から、語として続いている部分を切り出す。

    かな・漢字・カタカナ・全角数字・`・` を語の一部とみなす。
    戻り値: (開始位置, 中身)。無ければ (None, '')。
    """
    i = len(line)
    while i > 0:
        c = line[i - 1]
        if (is_hiragana(c) or is_katakana(c) or is_kanji(c)
                or c == 'ー' or c == '・' or '０' <= c <= '９'):
            i -= 1
            continue
        break
    return (i, line[i:]) if i < len(line) else (None, '')


def known_or_bundled(reading, store, dict_index=None, min_count=2):
    """
    その読みは「知っている語」か —— **学習だけに頼らずに見る**
    （項目48-EO・設計6・うにさん指定 (d)）。

    第40回の棚卸し（項目48-EK）で数えたこと:

        初期状態の語彙 16,263件のうち **count>=2 は 375件（2.3%）**。
        しかもその375件は **seed の語とちょうど同じ**。
        つまり `count >= 2` は初期状態では「seed か」の意味しか
        持たず、**辞書から取り込んだ 15,888語は全部「知らない」**
        と答えていた。

    うにさんの指定 (d):

        「使っているうちに変わるというのは、同音異義語の候補先を
          決め打ちするためのもので、**短期的な参照に留めるもの**」

    そこで、同じ問いに**同梱の材料**でも答えられるようにする:

      1. 使用実績がある（seed か、実際に使われた）      … 今までどおり
      2. **刈り込んだ索引に在る**（このアプリが提案してよい語）
      3. **世の中の集合に在る**（ひらがなの読みのみ。項目48-DY）

    3 は「日本語として在る」だけを言うので、**触らない側に倒す
    判断にだけ使う**こと（提案の材料にはしない）。

    **`familiarity` は使わない**（設計6 の案にはあったが、
    `bias()` は「表に無ければ 0」を返すので、0 が「馴染みが深い」と
    「表に無い」の両方を意味してしまい、在る／無いの判定に使えない。
    2026-08-17 に確かめた）。
    """
    if not reading:
        return False
    try:
        if any(e.get('count', 0) >= min_count
               for e in store.lookup(reading)):
            return True
    except Exception:
        pass
    if dict_index is None:
        return False
    try:
        if dict_index.surfaces_for_reading(reading):
            return True
    except Exception:
        pass
    try:
        if all(is_hiragana(c) or c == 'ー' for c in reading) \
                and dict_index.is_world_reading(reading):
            return True
    except Exception:
        pass
    return False


# 位置・場所を表す接尾の漢字1字（ソフト上・アプリ内）。
# 混合塊の経路が持っていた守りと同じ字を使う。
_PLACE_SUFFIX_KANJI = '上中下内外前後間側'


# --- 項目48-ID（設計31）: **接尾が引数に要求する「場」** -----------
#
# うにさんの指定（2026-08-21）:
#
#   「背景食が異様、違和感のある言葉、考えれば背景色が正しいと
#     分かる、その思考の理由を分析して」
#   「型はやります。正しいならそのまま。**補正せずに違和感のない
#     文章は補正しなくてよい**」
#
# ### なぜ表が要るのか（4通り測って、どれも割れなかった）
#
# `背景食` と `電気料` は、形の上では同じである。どちらも
# 「実在する2字語＋1字の接尾」で、どちらも同梱の表に**載っていない**。
# それでも前者だけが異様なのは、**接尾が左に要求する意味の場**が
# 違うからである:
#
#     色 : 〈面・領域・物・立場〉を取る    背景は面        → **合う**
#     食 : 〈食事の時・様式・場面〉を取る  背景は面ではない → **合わない**
#     料 : 〈代金を払う対象〉を取る        電気は払う対象   → **合う**
#
# この「引数の場」を、同梱の材料から出せるかを2026-08-21に測った:
#
#   (1) 読み→表記の表（266,950読み）の在/不在
#       → 読み1つに表記1つしか無く、**不在は不在証明にならない**
#          （学び43）。作った複合語1,360語で
#          `電気料→電気量` `選択率→選択律` など**6件以上壊した**
#   (2) 表のコスト   当たり106〜205／壊し153〜233で**重なる**
#   (3) 接尾の自由さ（2字以上の頭を何種類取るか）
#       背景食○ 食44→色117（比2.66）／保存量× 量86→料173（比2.01）
#       **重なる**
#   (4) 話題のまとまり（`seed_context`・39話題1,014語）
#       → `背景` `色` `食` `料` `量` が**1語も入っていない**
#   (5) 本人の語彙 → `背景色` すら入っておらず、**当たりも全部止まる**
#
# **どれも割れない。** 表が記録しているのは「どの語が出来上がったか」
# であって、「どの形態素が何を要求するか」ではない。だから
# **ここだけは、閉じた文法の類として書き下す**（項目48-HT で
# 位置名詞を書き下したのと同じ扱い）。
#
# ### この表の安全のしかた——**載せ漏れは無害、載せ過ぎだけが危ない**
#
# ここに在る字のときだけ型を疑う。だから
#
#     載せ忘れた字 → 何も起きない（今までどおり）
#     載せ過ぎた字 → **正しい語を疑ってしまう**
#
# **迷ったら載せない。** 「何にでも付く」側（化・性・的・者・料・量・
# 率・時・目・後・内・分・用・先・側・色・音・数・費・形・力・語…）は
# **1字も入れない**。入れるのは、頭が**特定の分野の語でなければ
# 意味を成さない**ものだけである。
_SCOPED_SUFFIX = {
    # 飲食（朝食・和食・給食。頭は食事の時・様式・場面）
    '食', '飯', '膳', '汁', '麺', '酒', '茶',
    # 地形（上り坂・七曲坂。頭は地形か地名）
    '坂', '峠', '岬', '谷', '峰', '岳', '崎', '浜', '浦', '洲', '沼',
    '湖', '池', '滝', '淵', '磯', '崖', '窪', '洞',
    # 施設・建物（田無駅・一乗寺。頭は場所か固有名）
    '駅', '寺', '院', '堂', '塔', '橋', '港', '城', '邸', '荘', '庵',
    '宮', '廟', '閣', '舎', '楼',
    # 行政の区画（頭は地名）
    '省', '庁', '藩', '郡', '県', '市', '町', '村', '区', '郷',
    # 生き物（頭はその種類）
    '菌', '虫', '貝', '藻', '蝶', '蜂', '鮫', '鯨',
    # 病い（頭は部位か原因）
    '症', '炎', '疹', '癌', '痘',
    # 天と海（頭はその現象）
    '雲', '霧', '雷', '霜', '潮', '嵐',
}


def _scoped_tail_fix(chunk, tokenize_fn):
    """
    **接尾の要求する場に頭が合っていない複合を、末尾1字で直す**
    （設計31・項目48-ID）。

    直すのは、うにさんの `背景食 ⇒ 背景色` の形だけ:

        背景食（はいけいしょく）
          頭 `背景` はそのまま、**末尾の1字だけ**が別の同音字
          → `しょく` と読める字のうち、`背景X` が1語として在るのは
            **`色` だけ** → `背景色`

    門は5つ。どれも「決め手が無ければ触らない」側に働く:

      (1) 漢字だけ・3字以上（かなが混じるものには表を使わない・48-HM）
      (2) **末尾が `_SCOPED_SUFFIX`**（場の決まった接尾）
      (3) **いまの表記が1語として在るなら触らない**（`is_unit`。
          `相川駅` `兼六園` はここで守られる。正しいならそのまま）
      (4) 頭が1語として在る（`背景` は在る）
      (5) 直し先は**よく使う1語**（`is_common_unit`＝固有名詞を除く）で、
          **ただ1つに決まる**

    読みは**解析が言い切っているものだけ**を使う（当て推量の読みは
    使わない・項目48-DE）。

    戻り値: 直した表記、または None
    """
    if not chunk or len(chunk) < 3 or not all(is_kanji(c) for c in chunk):
        return None
    tail = chunk[-1]
    if tail not in _SCOPED_SUFFIX:
        return None
    head = chunk[:-1]
    try:
        import seed_japanese as _sj
        import kanji_onkun as _ok
    except Exception:
        return None
    if not _sj.available() or not _ok.available():
        return None
    # (3) 正しく書けているなら、そのまま
    if _sj.is_unit(chunk) is not False:
        return None
    # (4) 頭は1語として在ること
    if _sj.is_unit(head) is not True:
        return None
    # 末尾の読み（解析が言い切っている読みから、頭のぶんを引く）
    rd = _analyzer_reading(chunk, tokenize_fn)
    rd_head = _analyzer_reading(head, tokenize_fn)
    if not rd or not rd_head or not rd.startswith(rd_head):
        return None
    rd_tail = rd[len(rd_head):]
    if not rd_tail:
        return None
    if rd_tail not in (_ok.readings_of(tail) or ()):
        return None          # 解析と音訓表が食い違う＝読みが確かでない
    # (5) 同じ読みの字に差し替えて、**よく使う1語**になるものを集める
    got = []
    table = _ok._load() or {}
    for ch, rds in table.items():
        if ch == tail or rd_tail not in rds:
            continue
        cand = head + ch
        try:
            if _sj.is_common_unit(cand) is True:
                got.append(cand)
        except Exception:
            continue
    if len(got) != 1:
        if got:
            _trace('型', f'{chunk!r} → 末尾を替えた語が {got} と並んだ。'
                         f'決め手が無いので触らない（設計31）')
        return None
    _trace('型', f'{chunk!r} → 接尾 {tail!r} は場の決まった接尾で、'
                 f'頭 {head!r} はその場の語ではない。'
                 f'同じ読み {rd_tail!r} で 1語になるのは {got[0]!r} '
                 f'だけ（設計31・項目48-ID）')
    return got[0]


def _analyzer_reading(text, tokenize_fn):
    """解析が言い切っている読み（言い切れないなら None）。"""
    try:
        ts = tokenize_fn(text)
    except Exception:
        return None
    if not ts or not all(t[5] for t in ts):
        return None
    if ''.join(t[0] for t in ts) != text:
        return None
    return ''.join(
        chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' and c != 'ー' else c
        for c in ''.join(t[2] for t in ts))


def fallthrough_rebuild_ok(chunk, surface, readings, store, dict_index,
                           tokenize_fn=None):
    """
    **組の経路が駄目だったとき、芯の再構築へ譲ってよいか**
    （項目48-EQ・設計8・2026-08-18）。

    設計8 の但し書き「化けが出たら、fallthrough の入口を絞る」に
    従って足した門。実測で出た化けは3件で、**どれも既にどこかに
    ある守り**だった:

        ジリ高  → **実行**       （48-CG: 辞書に載っている塊）
        ソフト上 → **ソフトウエア** （混合塊の「カタカナ＋位置の接尾」）
        叶う父  → **強化**       （誤打の種類で説明が付かない）

    だから**新しい判断は作らず、既にある3つを並べ直すだけ**にする:

      1. **辞書に表記が載っている塊は読み直さない**（項目48-CG）。
      2. **カタカナ語＋位置の接尾の漢字1字**は正しい複合
         （混合塊の経路が持っている守りと同じ）。
      3. **直した先が、うにさんの「誤打の種類」で説明が付く**こと。
         SPEC の4種（重複打鍵・脱字・順序違い・濁点）を巻き戻した
         形（`_typo_repairs`）に、直し先の読みが在ること。

         めもちちょう → **めもちょう**（`ち` の重複打鍵）→ メモ帳 ○
         きょううちち → きょうか（説明が付かない）              ×
         じりたか     → じっこう（説明が付かない）              ×

    3 が肝で、**譲る先を「打ち間違いとして説明が付く直し」だけに
    絞る**。組の経路が抱えていた塊を再構築に晒すのだから、
    再構築の側の門はゆるめず、**入口をこれだけ狭くする**。
    """
    if not surface or surface == chunk:
        return False
    # (0) **「変換に一部だけ失敗した形」だけを譲る**
    #     （項目48-EA の印・2026-08-18 に実測して足した）。
    #
    #     IME は文節ごとに変換するので、一部だけ失敗した形は
    #     **漢字とひらがなが隣り合う**（`目もち長` の `もち`）。
    #     この印が無い塊は、たいてい**正しい生産的な複合**である:
    #
    #         選択時 → **選択肢**   （選択＋時。正しい語を壊した）
    #
    #     `選択時` は辞書の表記索引に無いので (1) では守れず、
    #     `せんたくじ → せんたくし` は濁点1つで説明も付くので
    #     (3) も通ってしまう。**譲る入口をこの形に限る。**
    if not (any(is_kanji(c) for c in chunk)
            and any(is_hiragana(c) for c in chunk)):
        _trace('語の組', f'{chunk!r} は漢字とかなが隣り合う形ではないので'
                         f'譲らない')
        return False
    # (1) 辞書に載っている塊は読み直さない（項目48-CG）
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(chunk):
                _trace('語の組', f'{chunk!r} は辞書にある塊なので譲らない')
                return False
        except Exception:
            pass
    # (2) カタカナ語＋位置の接尾の漢字1字は正しい複合
    if len(chunk) >= 3 and is_kanji(chunk[-1]) \
            and chunk[-1] in _PLACE_SUFFIX_KANJI:
        _kata = chunk[:-1]
        if all('ァ' <= c <= 'ヶ' or c == 'ー' for c in _kata):
            _trace('語の組',
                   f'{chunk!r} はカタカナ語＋位置の接尾なので譲らない')
            return False
    # (3) 直し先が「誤打の種類」で説明が付くこと。
    #     **比べる元は「解析が言い切っている読み」だけ**にする
    #     （項目48-DE「推測の上に推測を重ねない」）。
    #
    #     実測で必要だった（2026-08-18・readcheck）:
    #       `昨日ひんとを見ました。` → **`作品とを見ました。`**
    #     塊 `昨日ひん` の推した読みは `さくひひん` で、そこから
    #     `さくひん`（＝作品）は確かに重複打鍵1つで説明が付く。
    #     **だが解析は `昨日` を `きのう` と読んでいる。**
    #     推した読みが解析と食い違っているなら、その推しは
    #     信用できない —— **食い違った推しの上に誤打の巻き戻しを
    #     重ねると、でたらめな読みが実在の語になる。**
    _ar = _analyzer_reading(chunk, tokenize_fn) if tokenize_fn else None
    if not _ar:
        _trace('語の組', f'{chunk!r} は解析が読みを言い切らないので'
                         f'譲らない')
        return False
    try:
        rd = store.reading_of(surface) or ''
    except Exception:
        rd = ''
    if not rd:
        return False
    # **読みが同じ置き換えは採らない**（2026-08-18 に実測して足した）。
    # 読みが変わらないなら、それは誤字の訂正ではなく**表記変換**で、
    # 方針1に反する（既存の門と同じ考え方）。実機のメモで
    #     短期的な参照に**留める** → **止める**
    # と、うにさんの文章の表記を勝手に変えていた。
    if rd == _ar:
        _trace('語の組', f'{chunk!r} → {surface!r} は読みが同じ'
                         f'（表記変換）なので譲らない')
        return False
    try:
        if rd in _typo_repairs(_ar):
            return True
    except Exception:
        pass
    _trace('語の組', f'{chunk!r}（解析の読み {_ar!r}）→ {surface!r} は'
                     f'誤打の種類で説明が付かないので譲らない')
    return False


def _known_word(text, store, dict_index):
    """
    その並びを「知っている語」とみなせるか（読みでも表記でも）。

    **設計6の3（読み側にも索引を足す）は、測って入れなかった**
    （項目48-EO・2026-08-17）。初期状態の `おおごえぬ`
    `おおごえぬめ` の3件は通るようになるが、readcheck 型8種で
    **化けが2件生まれた**:

        ふかる   → **ふか。**   （`ふか` が索引に在る）
        しべらる → **しべら。** （末尾2文字 `べら` が索引に在る）

    門(4)は「手前が**語として立っている**」を求める場所で、
    しかも**末尾2文字まで**を順に試す。刈り込んだ索引には
    2〜3文字の語がいくらでも在るので、ここに索引を足すと
    **ほぼ何でも通る**ようになる。`おおごえぬ` の3件は
    「直らない」であって「化けた」ではないので、
    **2件の化けと引き換えにはできない**（うにさんの決まり:
    「化けただけが本当の失敗」）。

    長さの下限で切る手もあるが、うにさんの指定 (c)
    「長さの下限は理由にならない」。門(4)そのものの証拠を
    別の形で立て直すのが筋で、それは第42回の設計に回す。
    """
    try:
        if any(e.get('count', 0) >= 2 for e in store.lookup(text)):
            return True
    except Exception:
        pass
    try:
        if store.reading_of(text):
            return True
    except Exception:
        pass
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(text):
                return True
        except Exception:
            pass
    return False


def _samekey_index_empty(dict_index):
    """
    (0) **索引を渡されたのに空か**（2026-08-16・実機）。
        門(2)「辞書に載っている語は正しく書けている」は
        この補正のいちばん大事な守りで、索引が空だと黙って消える。
        実際に、アプリが索引を読み込む前に解析が走った回があり
        （控えの見分けに dict_index=[0,0] が残っていた）、
        `むすめ → むす？` `するめ → する？` と正しい語を壊した。
        門が立てられないなら、直さないほうを選ぶ。
        None（明示的に無し。janome の無いテスト・道具の呼び方）は
        従来どおり語彙の門(1)だけで動く。アプリは必ず DictIndex を
        渡すので、実機ではこの区別が「読み込み前」を捕まえる。
    """
    if dict_index is None:
        return False
    try:
        return not dict_index.stats().get('readings')
    except Exception:
        return True


# --- 項目48-EM: サ変動詞の「する」の す抜け（2026-08-17）---
#
# うにさんの (f) の実機の例は `する。` が `す。。` になっていた形で、
# その手前に **`補正る。`**（＝`補正する。` の `す` 抜け）があった。
# 項目48-EI で「同じキー」は手を引いたが、**本来の直し**は
# `補正る。→ 補正する。` である（設計2 の 3）。
#
# **既存の芯再構築は拾えなかった**（実測）。芯は `る` の1文字で、
# 手前が漢字なので、かな連続の経路にそもそも乗らない。
#
# 形が決まっているので、名指しで直せる。**解析がそのまま証拠になる**:
#
#     補正る  →  補正(名詞:サ変接続) ＋ る(助動詞)   … 2つに切れる
#     反る    →  反る(動詞:自立)                      … 1つ。切れない
#     参る・解る・困る・至る                          … 同じく1つ
#
# **危なさを数えた**（2026-08-17・うにさんの語彙 7,551語）:
#
#     漢字だけの語で「＋る」がサ変接続に切れるもの   3,064語
#     そのうち「漢字＋る」自体が辞書に在るもの       **0語**
#
# つまり `反る` `参る` のような正しい語は、**解析が1語にまとめる**
# ので、この経路にそもそも来ない。カタカナのサ変（`メモる`
# `ググる` `サボる`）を巻き込まないよう、**漢字だけに限る**。
_SAHEN_MAX_KANJI = 4


def _fix_sahen_suru(line, tokenize_fn, dict_index):
    """
    「漢字（サ変接続の名詞）＋ る」の `る` を `する` に直す
    （項目48-EM）。戻り値: [(開始, 終了, 直した文字), ...]。
    """
    out = []
    if not line or 'る' not in line:
        return out
    try:
        toks = tokenize_fn(line)
    except Exception:
        return out
    for i, t in enumerate(toks):
        if t[0] != 'る' or i == 0:
            continue
        pos = t[1] or ''
        if not (pos.startswith('助動詞') or pos.startswith('動詞')):
            continue
        prev = toks[i - 1]
        if not (prev[1] or '').startswith('名詞:サ変接続'):
            continue
        word = prev[0]
        if not word or len(word) > _SAHEN_MAX_KANJI \
                or not all(is_kanji(c) for c in word):
            continue
        # 「漢字＋る」自体が辞書に在るなら、正しく書けている
        # （門(2) と同じ「載っていることだけを根拠にする」使い方）。
        if dict_index is not None:
            try:
                if dict_index.readings_for_surface(word + 'る'):
                    continue
            except Exception:
                pass
        # 直後が `る` の連なりなら触らない（`〜るる` のような形）。
        if t[4] < len(line) and line[t[4]] == 'る':
            continue
        _trace('サ変', f'{word!r}＋る → {word!r}＋する（す抜け）')
        out.append((t[3], t[4], 'する'))
    return out


def _fix_samekey_punctuation_all(line, store, tokenize_fn, dict_index):
    """
    **行の中のすべての語連続**の末尾で、同じキーのかなを直す
    （2026-08-16・実機。`（強調ぬ）` `いいよねぬ ⇒ …` のように、
    行末でない位置の対象が全部素通りしていた）。

    戻り値: [(開始, 終了, 直した文字), ...]。
    """
    out = []
    if not line or _samekey_index_empty(dict_index):
        return out
    n = len(line)

    def _wc(c):
        return (is_hiragana(c) or is_katakana(c) or is_kanji(c)
                or c == 'ー' or c == '・' or '０' <= c <= '９')

    i = 0
    while i < n:
        if not _wc(line[i]):
            i += 1
            continue
        j = i
        while j < n and _wc(line[j]):
            j += 1
        got = _fix_samekey_in_run(line, i, j, store, tokenize_fn,
                                  dict_index)
        if got is not None:
            out.append(got)
        i = j
    return out


def _fix_samekey_punctuation(line, store, tokenize_fn, dict_index):
    """
    行末の1文字（〜3連）が「記号のつもりで打った同じキーのかな」
    なら直す。行末の語連続だけを見る（行の途中も見る側は
    `_fix_samekey_punctuation_all`）。

    戻り値: (開始, 終了, 直した文字) または None。
    """
    if not line:
        return None
    if _samekey_index_empty(dict_index):
        return None
    start, core = _samekey_word_run(line)
    if start is None:
        return None
    return _fix_samekey_in_run(line, start, len(line), store,
                               tokenize_fn, dict_index)


def _new_punct_run(line, start, end, new_surface):
    """
    その置換で、**元には無かった句読点の連続**が生まれるか
    （項目48-EI・うにさん指定 (f)）。

    `_has_new_repetition` は「同じ文字の連続」しか見ず、しかも
    項目48-EG のために「記号」分類を対象外にした。その穴を
    **句読点の連続に限って**塞ぎ直す。

        補正る。 → 補正。。   採らない（`。。` が生まれる）
        す。 → す。。         採らない
        おおごえぬぬ → おおごえ！！   採る（`！！` は正しい出力）
        おおごえぬめ → おおごえ！？   採る

    見分けは「連続の中に句読点（`。、．，`）が混じるか」。
    `！！` `！？` は混じらないので通り、`！。` `？、` は落ちる。
    """
    def _runs(s):
        out = []
        i = 0
        n = len(s)
        while i < n:
            if s[i] in _SENTENCE_PUNCT:
                j = i
                while j < n and s[j] in _SENTENCE_PUNCT:
                    j += 1
                if j - i >= 2 and any(c in _HARD_PUNCT for c in s[i:j]):
                    out.append(s[i:j])
                i = j
            else:
                i += 1
        return out

    was = _runs(line)
    now = _runs(line[:start] + new_surface + line[end:])
    if len(now) <= len(was):
        # 数が増えていないなら、伸びていないかだけ見る
        return sorted(now, key=len, reverse=True)[:1] \
            > sorted(was, key=len, reverse=True)[:1]
    return True


def _fix_samekey_in_run(line, start, end, store, tokenize_fn,
                        dict_index):
    """1つの語連続 line[start:end] に対する本体。"""
    core = line[start:end]
    if len(core) < 3:
        return None

    # (0') **直後に文の記号が既に在るなら触らない**（項目48-EI・
    #      うにさん指定 (f)）。`補正る。` の `る` は「`。` を
    #      打ち損ねた `る`」ではない —— `。` はもう打ててある。
    #      第38回までの「行末限定」が持っていた安全の復元。
    #      **閉じ括弧の前は対象のまま**（`（強調ぬ）` を守る）。
    if end < len(line) and line[end] in _SENTENCE_PUNCT:
        _trace('同じキー',
               f'{core!r} の直後に {line[end]!r} が既に在るので触らない')
        return None

    # (0'') **サ変接続の名詞＋`る` は、句点の打ち損ねではない**
    #      （項目48-EM・2026-08-17）。`設定る` は `設定。` ではなく
    #      **`設定する` の `す` 抜け**と読むほうが自然で、
    #      **解析が「サ変接続」だと言っている**のがその証拠。
    #      実機の基準の版では `設定る → 設定。` `保存る → 保存。`
    #      `確認る → 確認。` `メモる → メモ。` と壊していた
    #      （`メモる` は俗語だが正しい語で、直す必要が無い）。
    #      漢字のサ変は項目48-EM が `する` を補い、カタカナのサ変
    #      （`メモる`）は**そのまま残す**のが正しい。
    if core.endswith('る'):
        try:
            _t = tokenize_fn(core)
        except Exception:
            _t = None
        if _t and len(_t) >= 2 and _t[-1][0] == 'る' \
                and (_t[-2][1] or '').startswith('名詞:サ変接続'):
            _trace('同じキー',
                   f'{core!r} はサ変接続の名詞＋る なので触らない'
                   f'（`する` の す抜け）')
            return None

    # (1) **全体が語彙にあるなら正しく書けている**（かんがえる・
    #     たべる・しぬ・だめ）。
    try:
        if any(e.get('count', 0) >= 2 for e in store.lookup(core)):
            _trace('同じキー', f'{core!r} は語彙にあるので触らない')
            return None
    except Exception:
        return None
    # (2) **辞書に載っているなら正しく書けている**（むすめ・するめ・
    #     しばいぬ・ばーる。項目48-CF と同じ「載っていることだけを
    #     根拠にする」使い方）。
    #     末尾が表の文字の2連・3連でも、正しい語はここで守られる:
    #     語彙＋辞書の全語で数えたら、末尾が表の文字2連以上の語は
    #     99語（あきらめる・まとめる・するめ・ぐるめ…）で、
    #     **全部が語彙か辞書に載っていた**（2026-08-16 に数えた）。
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(core)                     or dict_index.surfaces_for_reading(core):
                _trace('同じキー', f'{core!r} は辞書にあるので触らない')
                return None
        except Exception:
            pass
        # (2') **刈り込む前の辞書（世の中の語）に在るなら触らない**
        #     （2026-08-16・項目48-DY の物差し）。刈り込んだ索引は
        #     「あることは確かだが、無いことは何も言わない」。
        #     `ひとめ`（人目）は刈り込みで索引から落ちていて、
        #     行の途中まで見るようにした途端 `ひと？` と壊した。
        #     世の中の集合は読み（かな）しか持たないので、
        #     ひらがなだけの並びに限って引く。
        try:
            if all(is_hiragana(c) or c == 'ー' for c in core) \
                    and dict_index.is_world_reading(core):
                _trace('同じキー',
                       f'{core!r} は世の中に在る語なので触らない')
                return None
        except Exception:
            pass
    try:
        toks = tokenize_fn(core)
    except Exception:
        return None

    # **末尾の連続にも対応する**（2026-08-16・うにさん指定）。
    #     大声ぬめ → 大声！？   ふつうのこえぬぬ → ふつうのこえ！！
    # `！？` を打とうとして両方とも押し損なう形。表の文字が
    # 連続している長さぶんを1度に直す。**長い連続から順に試し、
    # 門を通らなければ短くして試す**（3連まで。うにさんの例の上限）。
    run_max = 0
    while (run_max < 3 and run_max < len(core) - 1
           and core[-1 - run_max] in _SAMEKEY_PUNCT):
        run_max += 1

    def _known(text):
        return _known_word(text, store, dict_index)

    # --- 項目48-EJ（設計1）: 証拠を「学習」から「並びの異様さ」へ ---
    #
    # うにさんの指定 (d)（2026-08-17）:
    #
    #   「初期状態で必要となる認識が甘い。**使っているうちに変わる
    #     というのは、同音異義語の候補先を決め打ちするためのもので、
    #     短期的な参照に留めるもの**」
    #
    # 第39回の `いいよねめ → いいよね？` は、迂回条件が
    # 「手前 `いいよね` が**まるごと語彙にある**（count>=2）」で、
    # **初期状態では通らない**（実測: 通らなかった）。これは (d) に反する。
    #
    # うにさんの指定 (e):
    #
    #   「『いいよねめ』『よかったねめ』という文字列は**ありえない
    #     もので異様なもの**。この違和感を感じ取れる判定が必要」
    #
    # そこで証拠の軸を変える。**異様さ**＝語連続まるごとが
    #
    #   (i) 語彙に無い   … 門(1) で確かめ済み（在れば return している）
    #   (ii) 刈り込んだ索引に無い … 門(2) で確かめ済み
    #   (iii) **世の中の集合に無い**（項目48-DY）  ← ここで見る
    #
    # の3つとも無いこと。3つとも無い並びは「日本語として在りえない」。
    # 実測（初期状態・2026-08-17）:
    #
    #     通したい  いいよねめ・よかったねめ・そうだねめ
    #               たのしいよねめ … **4つとも世の中に無い**
    #     守りたい  ひとめ・むすめ・するめ・もちごめ・ひとりじめ・
    #               はちぶんめ・きりめ・つかれる・にえる・くわせる・
    #               かんむり・おしえる・たべる … **13語とも世の中に在る**
    #
    # **ひらがなだけの並びに限る。** 世の中の集合は読み（かな）しか
    # 持たないので、漢字まじりを通すと常に「無い」ことになる
    # （第39回に `教える → 教え。` で踏んだ）。分からないときは
    # 「異様ではない」＝触らない側に倒す。
    _weird = False
    if dict_index is not None \
            and all(is_hiragana(c) or c == 'ー' for c in core):
        try:
            _weird = not dict_index.is_world_reading(core)
        except Exception:
            _weird = False

    # **説明可能性**（設計1 の 2）。末尾の表の文字を除いた手前が、
    # **初期状態の材料だけで**端から端まで敷き詰められること。
    #
    #     いいよね   ＝ いい ＋ よ ＋ ね
    #     よかったね ＝ よかっ ＋ た ＋ ね
    #     そうだね   ＝ そう ＋ だ ＋ ね
    #
    # 終助詞（ね・よ・な・か）は `PARTICLES_1CHAR` に既に在り、
    # 活用語尾（た・だ）は `AUXILIARY_TAILS`。**48-DJ の学びのとおり、
    # 終助詞は語の末尾にも立つ字なので、敷き詰めの部品としてだけ
    # 使い、単独の証拠にはしない**（異様さが立っていなければ、
    # ここを通っても直さない）。
    #
    # **敷き詰めだけでは足りなかった**（2026-08-17・readcheck 型8種で
    # 実測）。異様さは「日本語として在りえない並び」を指すが、
    # **打ち間違えた語そのものも在りえない並び**なので、
    # 異様さ＋敷き詰めだけだと、ふつうの誤字を同じキーの仕事だと
    # 思い込んで末尾を記号にしてしまう。実際に7件出た（型
    # 「{w}」と書きました。 に集中）:
    #
    #     しらへる（正解 しらべる）  → しらへ。
    #     しらる  （正解 しらべる）  → しら。
    #     ふかる  （正解 ふかめる）  → ふか。
    #     やじしる（正解 やじるし）  → やじし。
    #     ばしりあげる（正解 しばりあげる）→ ばしりあげ。
    #     しばりああげる            → しばりああげ。
    #     はじよめ（正解 はじめよ）  → はじよ？
    #
    # 通したい側と並べると、**形がはっきり分かれた**（解析の結果）:
    #
    #     いいよね     いい(形容詞) ＋ よ(終助詞) ＋ ね(終助詞)
    #     よかったね   よかっ(形容詞) ＋ た(助動詞) ＋ ね(終助詞)
    #     そうだね     そう(副詞) ＋ だ(助動詞) ＋ ね(終助詞)
    #     たのしいよね たのしい(形容詞) ＋ よ(終助詞) ＋ ね(終助詞)
    #     ------------------------------------------------ 機能語 2つ
    #     しらへ       しら(名詞) ＋ へ(**格助詞**)            1つ
    #     はじよ       はじ(名詞) ＋ よ(終助詞)               1つ
    #     しら・ふか・やじし・ばしりあげ・しばりああげ            0
    #
    # **文がそこで言い切られている形**かどうか、である。話し言葉の
    # 文末は機能語が重なる（よ＋ね／た＋ね／だ＋ね）。だからその
    # 直後に来た `る` `め` `ぬ` は語の一部ではありえず、記号の
    # 打ち損ねだと言える。名詞＋助詞1つ（`しらへ` `はじよ`）は
    # 文末とは限らず、**語の途中**でありうる。
    #
    # 3つ目の条件として足す:
    #   (c) 手前の解析が **自立語 ＋ 助詞/助動詞が2つ以上**で終わり、
    #       **いちばん後ろが終助詞**であること。
    #
    # janome の無い環境では品詞が取れないので、この道は開かない
    # （＝第39回までの動きのまま。tests_mock の答えが動かない）。
    _world_parts = (dict_index.is_world_reading
                    if (dict_index is not None and _SAMEKEY_TILE_WORLD)
                    else None)

    def _ends_utterance(text):
        """その並びは「文がそこで言い切られている形」か（項目48-EJ）。"""
        try:
            ts = tokenize_fn(text)
        except Exception:
            return False
        if not ts or ''.join(t[0] for t in ts) != text:
            return False
        tail = 0
        for t in reversed(ts):
            pos = t[1] or ''
            if pos.startswith('助詞') or pos.startswith('助動詞'):
                tail += 1
            else:
                break
        if tail < 2:
            return False                 # 機能語1つでは文末と言えない
        if not (ts[-1][1] or '').startswith('助詞:終助'):
            return False                 # いちばん後ろは終助詞
        return len(ts) > tail            # 手前に自立語が在る

    def _explained(text):
        if not text or len(text) < 2:
            return False
        if not _ends_utterance(text):
            return False
        try:
            return _covered_by_known(text, store, world=_world_parts)
        except Exception:
            return False

    for rl in range(run_max, 0, -1):
        run = core[-rl:]
        pre = core[:-rl]
        if not pre:
            continue
        # (3) **末尾の連続が、独立した語として切れること。**
        #     `おしえる` は `おしえる` で1語に切れるので落ちる。
        #
        #     1文字のとき: 最後の1語がその文字そのもの。
        #     **ここはゆるめない**（2026-08-16 に測って決めた）。
        #     `終わりの句点る` は `['終わり','の','句','点る']` と
        #     切れる（`点る`＝ともる が実在語）ので、この門で落ちる。
        #     拾おうとして「塊が2語以上に切れていればよい」まで
        #     ゆるめると、巻き込む正しい語が **1件 → 14件** に増えた
        #     （つかれる・にえる・くわせる・ひとりじめ・もちごめ…）。
        #     1つの例のためによく使う動詞を13語壊す取り引きは
        #     割に合わない。`終わりの句点る` は直らないままにする。
        #
        #     2連以上のとき: **連続の始まる位置で語が切れている**こと
        #     （どれかの語がその位置から始まる）。`つかめぬ`（文語の
        #     否定）は `つかめ`＋`ぬ` と切れて `つかめ` が境目を
        #     跨ぐので落ちる。辞書に無い活用形はここで守る。
        if rl == 1:
            # --- 項目48-ER（設計9）: 文語の否定を巻き込まない ---
            #
            # `つかめぬ → つかめ！` は育った語彙で出る化け
            # （`つかめ` が門(4)を通ってしまう）。`ぬ` は
            # **文語の打ち消しの助動詞**でもあるので、
            # 「記号のつもりで打った `ぬ`」と区別が要る。
            #
            # Fable 5 が測った材料（2026-08-18）:
            #
            #     つかめぬ       つかめ(動詞) ＋ ぬ        ← 触らない
            #     よめぬ         よめ(動詞) ＋ ぬ          ← 触らない
            #     ふつうのこえぬ の(格助詞) ＋ こえ(動詞) ＋ ぬ ← **直したい**
            #
            # **品詞だけでは分けられない**（janome は `こえ` を
            # 動詞＝越え と読む）。分けるのは**直前の「の」**で、
            # 連体の「の」の直後は**名詞の位置**だから、動詞という
            # 読みのほうが誤り。
            #
            # そこにもう1つ足した（実測で必要だった）: **終助詞の
            # 直後**も同じ。`いいよねぬ` の `ね` を janome は
            # 動詞:自立 と読むが、`よ`（終助詞）の後で文は閉じて
            # いるので、動詞が始まるはずがない。足さないと
            # **項目48-EJ（設計1）の的をこの門が塞いでしまう**。
            #
            # `を` のような他の格助詞は入れない（`ペンをとれぬ` の
            # `とれ` は本物の動詞。を の後は動詞が来てよい）。
            if core[-1] == 'ぬ' and toks and len(toks) >= 2 \
                    and toks[-1][0] == 'ぬ' \
                    and (toks[-2][1] or '').startswith('動詞'):
                _before = toks[-3] if len(toks) >= 3 else None
                _pos = (_before[1] or '') if _before else ''
                _opens_noun = bool(_before) and (
                    _pos.startswith('助詞:連体化')
                    or _pos.startswith('助詞:終助')
                    or (_pos.startswith('助詞') and _before[0] == 'の'))
                if not _opens_noun:
                    _trace('同じキー',
                           f'{core!r} は動詞＋ぬ（文語の打ち消し）'
                           f'なので触らない')
                    return None

            # **前の語と合わせると世の中の語になる形**は、手前が
            # まるごと既知語のときだけ通す（2026-08-16・実測）。
            # 行の途中まで見るようにした途端、`…漢字にひとめ、` の
            # `ひと`＋`め`（＝人目。刈り込みで索引から落ちている）を
            # `ひと？` と壊した。解析は `ひと|め` と切るので門(3)は
            # すり抜ける。**世の中の集合（項目48-DY）**で「合わせて
            # 1語」を見張り、そのときは手前の**全体一致**を求める
            # （`よかったね`＋`め` は `ねめ`＝睨め が世の中に在るが、
            #   `よかったね` がまるごと語彙にあるので通ってよい）。
            #
            # **設計1 で、ここの「手前の全体一致」を「説明が付く」に
            # ゆるめた**（項目48-EJ）。`よかったねめ` は解析が
            # `よかっ|た|ね|め` と切るのでこの門に来るが、`よかったね`
            # は初期状態では**まるごとの語ではない**（学習しないと
            # 通らない＝(d) に反する）。異様さ (iii) が立っていて、
            # かつ手前が初期状態の材料で敷き詰められるなら通す。
            # `ひとめ` は門(2')（世の中に在る）で先に守られる。
            if toks and len(toks) >= 2 and toks[-1][0] == core[-1] \
                    and dict_index is not None:
                _pair = toks[-2][0] + core[-1]
                try:
                    if all(is_hiragana(c) or c == 'ー' for c in _pair) \
                            and dict_index.is_world_reading(_pair) \
                            and not (_known(pre)
                                     or (_weird and _explained(pre))):
                        _trace('同じキー',
                               f'{_pair!r} が世の中の語で、手前'
                               f'{pre!r} も説明の付く並びではないので'
                               f'触らない')
                        continue
                except Exception:
                    pass
            if not toks or toks[-1][0] != core[-1]:
                # **世の中に無い並びで、手前まるごとが既知語なら通す**
                # （2026-08-16・項目48-DY の物差しの適用）。
                # `いいよねめ` は janome が `ねめ` を動詞（睨め）と
                # 読むのでこの門で落ちていた。だが `いいよねめ` は
                # 刈り込む前の辞書にも無い並びで、`いいよね` は
                # まるごと語彙にある。以前この門をゆるめて壊した
                # 13語（つかれる・にえる・ひとりじめ…）は**全部
                # 世の中の語**なので、世の中の物差しで守れる
                # （実際は門(1)(2)が先に守る）。
                # **ひらがなだけの並びに限る。** 世の中の集合は
                # 読み（かな）しか持たないので、漢字まじりを通すと
                # 常に「無い」ことになり、刈り込みで落ちた
                # `教える` を `教え。` と壊した（実測）。
                #
                # **設計1（項目48-EJ）でここの証拠を差し替えた。**
                # 旧: 世の中に無い ＋ 手前が**まるごと既知語**
                # 新: 世の中に無い（＝異様） ＋ 手前が
                #     **初期状態の材料で説明が付く**
                # 学習（`_known`）は**追加の近道**として残す
                # （(d)「学習は短期的な参照に留める」）。
                if not _weird:
                    _trace('同じキー',
                           f'{core!r} の末尾は語の一部で、'
                           f'異様な並びでもないので触らない')
                    continue
                if not (_explained(pre) or _known(pre)):
                    _trace('同じキー',
                           f'{core!r} は異様な並びだが、手前 {pre!r} が'
                           f'説明の付く並びではないので触らない')
                    continue
                _trace('同じキー',
                       f'{core!r} は世の中に無い異様な並びで、'
                       f'{pre!r} は説明が付くので通す')
        else:
            if not toks or not any(t[3] == len(pre) for t in toks):
                _trace('同じキー', f'{core!r} は {pre!r}|{run!r} の'
                                   f'境目で語が切れないので触らない')
                continue
        # (4) 手前が既知語であること。まるごとでも、末尾だけでもよい
        #     （`おわりのくてん` は `くてん`(4回) で通る）。
        #
        #     **漢字に変換したあとの形が本命**（2026-08-16 に気付いた）。
        #     実際の打ち方は「おおごえ→変換して**大声**→Shift+1 を
        #     押し損なって ぬ」なので、手前は `大声` になっていることが
        #     多い。読みで引くだけだと `大声ぬ` が拾えなかった。
        #     表記でも引き、辞書に載っている表記も既知語とみなす。
        ok = _known(pre)
        if not ok:
            for L in range(len(pre) - 1, _SAMEKEY_MIN_WORD - 1, -1):
                if _known(pre[-L:]):
                    ok = True
                    break
        if not ok and _weird and _explained(pre):
            # **異様さが立っているときは、説明が付くことを証拠にする**
            # （項目48-EJ・設計1）。`いいよね` は初期状態では
            # まるごとの語ではないが、`いい`＋`よ`＋`ね` と
            # 同梱の材料だけで敷き詰められる。
            # **異様さ抜きでは通さない**（終助詞を単独の証拠に
            # しないため。48-DJ の学び）。
            ok = True
            _trace('同じキー',
                   f'{pre!r} はまるごとの語ではないが、'
                   f'同梱の材料で説明が付くので通す')
        if not ok:
            _trace('同じキー', f'{pre!r} が既知語でないので触らない')
            continue
        fixed = ''.join(_SAMEKEY_PUNCT[c] for c in run)
        _trace('同じキー',
               f'{run!r} → {fixed!r}（{pre!r} のあと・同じキー）')
        return (end - rl, end, fixed)
    return None


# --- 括弧のつもりで打った、同じキーのかな（2026-08-16・うにさん指定）---
#
#     ゜かぎかっこむ   ⇒ 「かぎかっこ」   （[ ] のキー。かな入力）
#     ゆまるいかっこよ ⇒ （まるいかっこ） （8 9 のキー。かな入力）
#
# 記号1文字（項目48-EG）と違い、**開きと閉じが対で在ること**が証拠。
# 片方だけでは絶対に触らない（`むすめ` の `む`・終助詞の `よ` を守る）。
_KANA_BRACKET_PAIRS = (
    # (開きのかな, 閉じのかな（IMEでカタカナになった形も）, 直す開き, 直す閉じ)
    ('゜', 'むム', '「', '」'),
    ('ゆ', 'よヨ', '（', '）'),
)


# 8…9 の対の中身に許す**ごく短い英単語**。英単語の種（SCOWL）は
# 6文字以上しか持たず、学習からも `ok` は拾えないため、ここだけ
# 小さな表で受ける。増やすときは「対の中身として書く語か」で選ぶ。
_ASCII_BRACKET_SHORT_WORDS = frozenset(
    ('ok', 'ng', 'no', 'yes', 'on', 'off'))


def _fix_ascii_brackets(line, store):
    """
    `8ok9 → (ok)`（2026-08-16・うにさん指定）。

    ローマ字入力で `（）` を打とうとして Shift を押し損なうと、
    `8` `9` がそのまま入る。開き 8・閉じ 9 が**対で**英字の並びを
    挟んでいるときだけ直す。

    門:
      - 8 の前と 9 の後ろが、行端か英数字以外（`0x8ab9` を守る）
      - 中身が英字だけで2文字以上（`8x9` の掛け算を守る）
      - 中身が知っている英単語（種・学習・上の短い表のどれか）

    戻り値: [(開始, 終了, 直した文字), ...]。
    """
    out = []
    if not line or '8' not in line:
        return out
    n = len(line)
    i = 0
    while i < n:
        if line[i] != '8' or (i > 0 and line[i - 1].isalnum()):
            i += 1
            continue
        j = i + 1
        while j < n and line[j].isascii() and line[j].isalpha():
            j += 1
        if j >= n or line[j] != '9' \
                or (j + 1 < n and line[j + 1].isalnum()):
            i += 1
            continue
        word = line[i + 1:j]
        if len(word) < 2:
            i += 1
            continue
        key = word.lower()
        known = key in _ASCII_BRACKET_SHORT_WORDS
        if not known:
            try:
                import loanword as _lw
                known = bool(_lw.known_english_spelling(word, store))
            except Exception:
                known = False
        if not known:
            i += 1
            continue
        _trace('同じキー', f'8…9 → (…)（中身 {word!r}）')
        out.append((i, i + 1, '('))
        out.append((j, j + 1, ')'))
        i = j + 1
    return out


def _fix_kana_brackets(line, store, tokenize_fn, dict_index):
    """
    「開きのかな ＋ 中身 ＋ 閉じのかな」の形を括弧に直す。

    **括弧を先に判定して、中身の補正はそのあとで考える**
    （2026-08-16・うにさんの指定）。この関数は判定だけを行い、
    直した行は correct_line の入口で丸ごと補正し直される
    （濁点の合成と同じ形）。だから中身の中の誤字はここでは見ない。

    門:

      (0) 索引を渡されたのに空なら触らない（項目48-EG と同じ）。
      (1) **開きが立っていて、閉じが語連続の末尾に在ること。**
          閉じは語に溶ける（`かっこむ`＝動詞・`かっこよ`＝形容詞に
          janome が読む）ので、解析では見ない。閉じは IME が
          カタカナにした形（ム・ヨ）も受ける（`゜カギカッコム`）。
      (2) `゜` の対: **単体の゜は本文に立てない文字**なので、
          それ自体が証拠（かなに付く゜は normalize_marks が合成
          する）。中身は1文字でよく、敷き詰めも求めない
          （`゜はむ → 「は」`）。
      (3) `ゆ` の対: ゆ・よ はふつうのかななので、証拠は対の形だけ。
          - 開きが語連続の頭にあること
          - **開き・閉じ込みで日本語として敷き詰まるなら触らない**
            （`ゆめをみたよ`＝ゆめ＋を＋みた、`ゆっくりするよ`）
          - 中身（2文字以上）が語彙と助詞で敷き詰まるか既知語
            （`まるいかっこ`・`いい`）
          - 中身が格助詞で始まらない（`ゆをわかすよ`＝湯を沸かす）

    戻り値: [(開始, 終了, 直した文字), ...]（開き・閉じで2件ずつ）。
    """
    out = []
    if not line:
        return out
    if dict_index is not None:
        try:
            if not dict_index.stats().get('readings'):
                return out
        except Exception:
            return out

    def _wc(c):
        return (is_hiragana(c) or is_katakana(c) or is_kanji(c)
                or c == 'ー')

    n = len(line)
    i = 0
    while i < n:
        matched = False
        for op, cls, r_op, r_cl in _KANA_BRACKET_PAIRS:
            if line[i] != op:
                continue
            # 開きの立ち位置（`ゆ` は語連続の頭にあること）
            if op != '゜':
                if i > 0 and _wc(line[i - 1]):
                    continue        # 語のつづきの中にある
            # 語連続の終わりを探す
            j = i + 1
            while j < n and _wc(line[j]):
                j += 1
            # 閉じが連続の末尾に在ること
            min_len = 3 if op == '゜' else 4   # 開き＋中身＋閉じ
            if j - i < min_len or line[j - 1] not in cls:
                continue
            inner = line[i + 1:j - 1]
            if op != '゜':
                # 中身が格助詞で始まらない。`PARTICLES_1CHAR` 全部
                # ではなく格助詞・係助詞だけ（項目48-DJ と同じ
                # 絞り方。`か` まで助詞扱いすると落ちる）。
                if inner[0] in _RUN_TAIL_PARTICLES:
                    continue
                # **開き・閉じ込みで敷き詰まるなら、ふつうの文**。
                whole = line[i:j]
                try:
                    if _covered_by_known(whole, store) \
                            or _known_word(whole, store, dict_index):
                        _trace('同じキー', f'{whole!r} は語で敷き詰まる'
                                           f'ふつうの文なので触らない')
                        continue
                except Exception:
                    continue
                # 中身が語彙で敷き詰められる／まるごと既知語
                tiled = False
                try:
                    tiled = _covered_by_known(inner, store)
                except Exception:
                    tiled = False
                if not tiled and not _known_word(inner, store,
                                                 dict_index):
                    continue
            _trace('同じキー', f'{op!r}…{line[j-1]!r} → '
                               f'{r_op!r}…{r_cl!r}（中身 {inner!r}）')
            out.append((i, i + 1, r_op))
            out.append((j - 1, j, r_cl))
            i = j               # この対の先から続きを見る
            matched = True
            break
        if not matched:
            i += 1
    return out


def _homophone_by_context(surface, reading, store, context_vec,
                          surrounding_words, dict_index=None,
                          attest_text=''):
    """
    方針2: 正しく書けている漢字語を、同じ読みの別の表記へ、
    周りの語との共起だけを根拠に置き換えてよいか。

    「明確に誤りだと言えるか」で採否を決めるという原則の、唯一の
    例外にあたる経路なので、次をすべて満たすときだけ通す。

      - 書かれている表記が**漢字だけ**（送り仮名を含む語は、
        換わる／変わる のような近い意味の語と共起が混ざる）
      - 置き換え先も漢字だけで、**字数が同じ**
      - 置き換え先に使用実績がある（_HOMOPHONE_MIN_USAGE 以上）
      - 周りの語が、書かれている表記より置き換え先を
        **はっきり支持している**（_HOMOPHONE_MIN_MARGIN 以上の差）
      - **選び終わったあと**、置き換え先の側だけを「共通の共起相手が
        _HOMOPHONE_MIN_SHARED 語以上」の証拠に限って測り直しても、
        まだ差が保つ（項目48-BY。**落とすことしかしない関門**）

    判断そのものは既存の pick_best_by_context に委ねる
    （補正の判断経路を増やさない、という設計原則のため）。
    書かれている表記を候補に混ぜて比べるので、差は
    「今の表記に対してどれだけ勝っているか」になる。

    戻り値: (置き換え先の表記, カテゴリ, 証拠の強さ) または None
    """
    if context_vec is None or not surrounding_words:
        return None
    # 案A（項目48-DZ）: 漢字だけでない語でも、**漢字＋送り仮名**なら
    # 活用形を作って比べる経路に入る。`_CONJ_HOMOPHONE` を False に
    # すれば、この経路は丸ごと消えて第37回までと同じ動きに戻る。
    conjugated = not _is_all_kanji(surface)
    if conjugated and not _CONJ_HOMOPHONE:
        return None

    # **書かれている語が、刈り込んだ辞書に載っているなら触らない**
    # （項目48-CF・2026-08-13）。
    #
    # 中立な文6,077（辞書の語を普通の文型に入れただけ・`fpcheck.py`）で
    # 方針2 が発動したのは6件。**6件とも誤検知**で、
    # **6件とも「書かれている語が dict_index に載っている」**だった:
    #
    #     一掃 → 一層 ／ 敬意 → 経緯 ／ 信仰 → 進行
    #     書記 → 初期 ／ 機動 → 起動 ／ 画定 → 確定
    #
    # 一方、直ってよい側（実機のメモ＋材料で発動した47件）で
    # 載っているのは **`機能 → 昨日` の2件だけ**——これも誤爆なので、
    # 止まって困らない。`開業→改行` `洗濯→選択` `名刺→名詞`
    # `意向→以降` は**どれも載っていない**ので通る。
    #
    # **「証拠の太さ」より効く。** 共通の相手を10語以上にすると
    # 誤検知は6件とも止まるが、`意向→以降` `核心→確信` `修整→修正`
    # を巻き添えにする（うにさんが「対比の行は直す」と言った形）。
    #
    # **48-AR・学び43 との違い（大事）**: あちらは
    # 「dict_index に**無い**＝IMEで作れない」と読んで失敗した
    # （うにさんの語の23.3%を誤判定）。ここは逆で、
    # **「載っている」ことだけを根拠にする**。
    # 刈り込んだ索引は**あることは確かだが、無いことは何も言わない**。
    # 使ってよいのは確かな側だけ。
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(surface):
                _trace('同音',
                       f'{surface!r} は辞書にある語なので置き換えない')
                return None
        except Exception:
            pass

    if conjugated:
        # **並記の関門**（項目48-DZ・2026-08-16）。
        #
        # 活用形の経路は、共起だけでは裁けない。実機のメモで測ったら
        # 直った3行（`売った文字 ⇒ 打った文字`）と引き換えに、
        # SPEC が名指しで予告していた誤爆がそのまま出た:
        #
        #     書き換わりました → 書き**変**わりました（tab1 56行目）
        #
        # `換わり` 対 `変わり` は +0.211 で敷居 0.12 を超える
        # （`_HOMOPHONE_MIN_MARGIN` の但し書き）。**敷居では分けられない。**
        # 逆側も測った: `治り` 0.1485 対 `直る` 0.0309、
        # `映る` 0.0357 対 `移る` 0.0133 で、**直すべき側のほうが
        # 点が低い**。共起の符号そのものが逆なので、この軸は使えない。
        #
        # そこで別の軸に切り替える（学び19）。**直した結果が同じ行に
        # 文字通り書かれているときだけ通す。** 項目38（助詞）と
        # 1-F（`attest_text`）で既に使っている「並記の関門」と同じ形で、
        # このアプリのよりどころ（「メモのどこかに正しく書いてある語」）
        # そのものでもある。
        #
        #     売った文字 ⇒ **打った**文字        → 同じ行に在る → 直す
        #     半角が治りました。⇒ 半角が**直り**ました。 → 在る → 直す
        #     新規チャットに映るので ⇒ …**移る**ので  → 在る → 直す
        #     書き換わりました                    → `変わり` は無い → 触らない
        #
        # 並記が無いときは何もしない。共起に落とさないこと
        # （落とすと上の誤爆がそのまま戻る）。
        alts = [a for a in _conjugated_alts(surface, reading, store)
                if attest_text and a['surface'] in attest_text]
        if not alts:
            return None
        # 並記そのものが証拠なので、共起の差は求めない
        # （判断の順序2「同じメモ内に同じ読みの語が別の表記で
        #   書かれているならそれに合わせる」の活用形への適用）。
        best = max(alts, key=lambda a: a['count'])
        _trace('同音', f'{surface!r} → {best["surface"]!r}'
                       f'（同じ行に並記あり）')
        return (best['surface'], best.get('category'), EVIDENCE_CONTEXT)
    else:
        alts = [e for e in store.lookup(reading)
                if e['surface'] != surface
                and e['count'] >= _HOMOPHONE_MIN_USAGE
                and len(e['surface']) == len(surface)
                and _is_all_kanji(e['surface'])]
    if not alts:
        return None

    # **候補が近くに書いてあることも、証拠として使う**
    # （2026-08-12・項目48-AY。**48-AV を取り消した**）。
    #
    # 48-AV では逆にしていた（候補を材料から落としていた）。
    # うにさんの指示で取り消した:「直します。対比を書いたのは
    # **開発として**です」。
    #
    # 落としていたせいで、こういう行が直らなくなっていた:
    #
    #     開業と行の削除 ⇒ 改行と行の削除   （実機メモ tab0 153行）
    #
    # **48-AV が守っていた行と、この行は形が同じ**。どちらも
    # 「誤 ⇒ 正」を1行に並べた対比で、片方だけ残すことはできない。
    # 測ったら、48-AV が減らしていた11行は**全部** .py のコメントに
    # 書いた `誤字→正しい語` の対比だった。**正しい日本語だけ**でも
    # **散文だけ**でも件数は1件も動かない（3→3・19→19）。
    #
    # → 学び45。あの 370→360 は被害ではなく、**材料が自己言及
    #   だったせいで出た数字**。SPEC.md で同じ罠を踏んだのと同じ形。
    material = tuple(surrounding_words)
    if not material:
        return None

    # 共起を測るときの表記。活用形を作った経路では、作った形
    # （`直り`）はメモに一度も出ていないので共起を持たない。
    # **作った形が共起を持っているならそれを使い、持っていない
    # ときだけ**語彙に在る基本形（`直る`）で測る。
    # 初めからいつも基本形にすると、`売っ → 打っ` のように
    # 活用形のほうが実データを持っている形で点が変わってしまう。
    def _vec_surface(e):
        made = e['surface']
        base = e.get('vec', made)
        if made == base:
            return made
        try:
            if context_vec.context_score(made, material):
                return made
        except Exception:
            pass
        return base

    vec_of = {e['surface']: _vec_surface(e) for e in alts}
    try:
        picked_vec = context_vec.pick_best_by_context(
            [surface] + [vec_of[e['surface']] for e in alts], material,
            min_margin=_HOMOPHONE_MIN_MARGIN)
    except Exception:
        return None
    if not picked_vec or picked_vec == surface:
        return None
    picked = next((e['surface'] for e in alts
                   if vec_of[e['surface']] == picked_vec), None)
    if not picked or picked == surface:
        return None

    # **証拠の太さは「決まってから」掛ける**（学び38・項目48-BY）。
    #
    # 最初は `pick_best_by_context` の点の付け方そのものに
    # min_shared を渡した。**それは駄目だった**。細い証拠を
    # 両側から等しく削るので、**書かれている側の点が先に消えて、
    # 置き換え先が勝ちやすくなる**ことがある。実際、
    # `全文走査が行数に比例して重くなる` が `全文操作` に化けた
    # （散文だけ:309・**直す前には無かった誤爆**）。
    #
    # そこで、**選び終わったあとに、置き換え先の側だけ**を
    # 細い証拠抜きで測り直し、それでも差が保つかを見る。
    # こうすると、この関門は**落とすことしかできない**
    # （新しい書き換えを生まない）。
    # 学び33「罰は『持ち込むもの』にだけ与える」も同じ形。
    try:
        thick = context_vec.context_score(
            picked_vec, material, min_shared=_HOMOPHONE_MIN_SHARED)
        held = context_vec.context_score(surface, material)
    except Exception:
        return None
    if thick - held < _HOMOPHONE_MIN_MARGIN:
        _trace('同音', f'{surface!r} → {picked!r} は証拠が細い（棄却）')
        return None

    entry = next((e for e in alts if e['surface'] == picked), None)
    if entry is None:
        return None
    _trace('同音', f'{surface!r} → 周りの語が {picked!r} を強く支持')
    return (picked, entry['category'], EVIDENCE_VECTOR)


def evaluate_candidate(surface, reading, store, context_vocab,
                       find_readings, max_dist, is_known_word=False,
                       context_vec=None, surrounding_words=None,
                       dict_index=None, attest_text=''):
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
    #
    # 例外は「方針2（同音異義語の文脈置換）」だけ。
    # 周りの語が圧倒的に別の表記を支持しているときに限り、
    # 実在語であっても置き換える（_homophone_by_context）。
    if is_known_word:
        return _homophone_by_context(surface, reading, store,
                                     context_vec, surrounding_words,
                                     dict_index=dict_index,
                                     attest_text=attest_text)

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


import naturalness as _naturalness      # 連接コストでの判断（48-AE）


def _tokens_all_known_in_span(tokens, start, end,
                              after_kanji=False, partial_start=False,
                              partial_end=False):
    """
    **文全体**の形態素解析で、この範囲がまるごと
    「辞書にある語」の並びとして読めているか。

    窓の判定（_looks_like_valid_japanese）は、窓の文字だけを
    取り出して解析し直す。前後を失うため、文の中では正しく
    切れていた並びが、断片にすると別の切り方になることがある。

    実機の例（2026-08-10）:
        「確定したのち」→ janome は 確定/し/た/のち と正しく切る。
        ところが窓は「したのち」だけを渡され、断片としての判定は
        先頭の1文字動詞「し」を根拠にできず不合格。結果、
        「したまち（下町）」という**実在するが無関係な語**に
        1文字違いで引き寄せられ、正しい文が壊れた。

    そこで、**文全体を見た解析の結果**をそのまま使う。
    その範囲が、切れ目もぴったり合ったうえで、すべて辞書が
    読みを引けた語で埋まっているなら、それは壊れていない。
    誤字を含む列は、文全体で見ても必ずどこかに
    「辞書が読みを引けない断片」が出る（それが誤字の定義）。

    ただし「すべて辞書が読みを引けた」だけでは足りない。
    **壊れた列も、短い語の寄せ集めなら全部引けてしまう**
    （学び12と同じ罠）。実際、直したい列はどれもそうなっている:

        たんほの繋がり  → たん(名詞)/ほ(動詞!)/の/繋がり
        単語のつあがり  → 単語/の/つ(助動詞!)/あがり
        たんごのちながり → たん/ご(接頭詞!)/のち/な/がり
        たああんごの…  → た(助動詞!)/あ(フィラー!)/あん/ご/の

    共通しているのは **1文字の中身のあるトークン**（1文字の
    動詞・接頭詞・フィラー・感動詞、並びの頭に立つ助動詞）で、
    どれも解析が崩れた印。正しい「したのち」にはこれが無い
    （し は直前の漢字「確定」の送り仮名なので例外扱いする）。

    条件（すべて満たすときだけ True）:
      - 範囲の両端がトークンの切れ目と一致している
      - 隙間なく覆っている
      - どのトークンも辞書が読みを引けている（または守る語）
      - フィラー・感動詞が混じっていない（解析が崩れた印）
      - 1文字のトークンは次のどれかだけ
          * 助詞（どこでもよい）
          * 助動詞（ただし並びの先頭は不可＝つあがりの「つ」）
          * 動詞で、並びの先頭かつ**直前が漢字**
            （＝その漢字の送り仮名。確定+し）
      - 2文字以上の内容語が1つ以上ある
        （助詞・助動詞だけの並びは、そもそも別の関門が見ている。
          ここで「正しい」と言い切る根拠にはしない）

    after_kanji: 範囲の直前の文字が漢字か。送り仮名の判定に使う。

    partial_start=True: **範囲の頭が語の途中でもよい**とする
        （2026-08-11）。頭を切れ目に合わせろという条件のせいで、
        **語の途中から始まる窓がこの守りを素通りしていた**:

            変わらない  → 窓 `らない`   （動詞 `変わら` の途中から）
            届くたびに  → 窓 `くたび`   （動詞 `届く` の途中から）
            下ごしらえ  → 窓 `ごしらえ` （名詞 `下ごしらえ` の途中から）

        それぞれ `きない` `くたびれ` `こしらえ` に化けていた
        （実機のメモにも、自分たちのコメントにも大量に出ていた）。

        頭を緩めても守りは弱くならない。**覆っているトークンが
        すべて辞書で読み切れていること**という中心の条件は
        そのままで、そこに「ほらい」のような読めない断片が
        1つでもあれば False になるため
        （`かな打ちでのほらい` の窓 `ちでのほらい` は、
          `ほらい` が読めないので今までどおり調べに行く）。

    partial_end=True: **範囲のお尻が語の途中でもよい**とする
        （2026-08-11・項目48-AH）。

        もともとここは「お尻は緩めない。語の途中で終わる窓は、
        誤字がその先に続いている可能性がある」としていた。
        **それが裏目に出ていた。** お尻が語の途中で終わる窓は
        「読めない」と返るので、**アプリはそれを直しに行っていた**:

            できる/ほか/、    窓 `できるほ`  → `できれ`
            広く/使える       窓 `広く使`    → `こう消し`
            誤っ/て/消さ/れる  窓 `誤って消`  → `誤っでき`
            取り/に/行く      窓 `取りに行`  → `とりない`
            作れる/こと       窓 `作れるこ`  → `される`
            選択/し/直す      窓 `選択し直`  → `選択肢ない`

        **これは「読めない文字列」ではなく「窓の取り方が悪い」。**
        正しい答えは「直す」ではなく「触らない」。
        誤爆385件を型で数えたところ、**語の途中で切れているもの
        45件（11%）**がこの形だった（2026-08-11 に実測）。

        頭と同じ条件で緩める。**その語が2文字以上で読み切れて
        いるときだけ。** 読み切れない断片がお尻に掛かっている
        ときは、もとの心配（誤字がその先に続いている）が
        当たるので、今までどおり調べに行く。
    """
    if not tokens or end <= start:
        return False

    def _head_ok(t):
        # 頭が語の途中でもよい。ただし**その語が2文字以上で
        # 読み切れている**ときだけ（1文字の語は解析が崩れた印の
        # ことが多く、上の説明のとおり信用しない）。
        return (t[3] >= start
                or (partial_start and t[3] < start < t[4]
                    and t[5] and (t[4] - t[3]) >= 2))

    def _tail_ok(t):
        return (t[4] <= end
                or (partial_end and t[3] < end < t[4]
                    and t[5] and (t[4] - t[3]) >= 2))

    covered = [t for t in tokens if _head_ok(t) and _tail_ok(t)]
    if not covered:
        return False
    if covered[-1][4] != end and not (
            partial_end and covered[-1][3] < end < covered[-1][4]):
        return False
    if covered[0][3] != start and not (
            partial_start and covered[0][3] < start < covered[0][4]):
        return False
    at = covered[0][3]
    has_content = False
    prev_surface = ''
    for surface, pos, _reading, s, e, has_reading in covered:
        if s != at:
            return False      # 隙間がある（＝端が語の途中）
        at = e
        if not has_reading and not is_protected_word(surface):
            return False      # 辞書が読みを引けない断片がある
        major = (pos or '').split(':')[0]
        if major in ('フィラー', '感動詞'):
            return False      # 解析が崩れた印
        if len(surface) == 1:
            if major == '助詞':
                continue
            if major == '助動詞' and s > start:
                continue
            # **1文字の漢字は、崩れた印にしない**（2026-08-11・48-AU）。
            #
            # 「1文字の内容語は解析が崩れた印」という規則は、
            # 崩れた例がどれも**かな1文字**だったところから来ている:
            #
            #     たん/**ほ**/の      単語/の/**つ**/あがり
            #     たん/**ご**/のち    **た**/**あ**/あん/ご
            #
            # ところが**漢字1文字の語は、普通の日本語に山ほど出る**
            # （間・行・誤・打・時・点・語・件）。それを崩れた印に
            # したせいで、**この守り自体が働かず**、正しい文が
            # 直しに掛けられていた（散文だけの材料で実測）:
            #
            #     わずかな**間しか働**いていない → もし稼働いていない
            #     にし**てしま**わないため       → にしたしまわないため
            #     表を**作った行**               → 表を実態
            #     **誤打補正**のみ               → 語彙補正のみ
            #
            # かな1文字は今までどおり崩れた印のまま。
            # **見分けは字種でつく。**
            if is_kanji(surface):
                has_content = True
                prev_surface = surface
                continue
            if major == '動詞' and s == start and after_kanji:
                continue      # 直前の漢字の送り仮名（確定＋し）
            if (major == '動詞' and s > start and prev_surface
                    and is_kanji(prev_surface[-1])):
                # 範囲の途中の「し」も送り仮名・サ変（選択＋し＋直す）。
                # 頭だけを認めていたので `選択し直` が「読めない」と
                # 出て、直しに行っていた（項目48-AH）。
                continue
            return False
        if major not in ('助詞', '助動詞'):
            has_content = True
        prev_surface = surface
    reached = (at == end
               or (partial_end and covered[-1][3] < end < covered[-1][4]
                   and at == covered[-1][4]))
    return reached and has_content


def _span_reads_in_sentence(tokens, line, start, end):
    """
    **文全体の解析で、この範囲が読めているか**（項目48-AH）。

    範囲だけを取り出して解析し直す `_looks_like_valid_japanese` は
    **前後を失う**ので、「範囲が語を途中で切っている」ことに
    気付けない。実測でこうなっていた（2026-08-11）:

        できる/ほか/、   範囲 `できるほ`  → `できれ`
        広く/使える      範囲 `広く使`    → `こう消し`
        取り/に/行く     範囲 `取りに行`  → `とりない`
        選択/し/直す     範囲 `選択し直`  → `選択肢ない`
        作れる/こと      範囲 `作れるこ`  → `される`
        誤っ/て/消さ/れる 範囲 `誤って消`  → `誤っでき`

    末尾の `か` `に` `こ` は助詞や形式名詞の頭にも見えるので、
    範囲を作る側は「助詞を落とした」つもりで**語の途中**を切る。
    **これは読めない文字列ではなく、範囲の取り方が悪い。**
    正しい答えは「直す」ではなく「触らない」。

    窓の道にはこの守りが `_tokens_all_known_in_span` として
    既にあった。**残りの道には無かったので素通りしていた**
    （学び22:「片方だけに置くと、そちらを迂回して素通りする」）。

    誤爆385件を型で数えたところ、**語の途中で切れているもの
    45件（11%）**がこの形だった。

    **門ではなく敷居として使うこと**（項目48-AE）。読める範囲でも
    「明らかに自然になる」直しなら通す。呼ぶ側で
    `_naturalness.worth_touching_readable` と組にすること。
    """
    if not tokens:
        return False
    try:
        ok = _tokens_all_known_in_span(
            tokens, start, end, partial_start=True, partial_end=True,
            after_kanji=(start > 0 and is_kanji(line[start - 1])))
    except Exception:
        return False
    if not ok:
        return False
    # **語を途中で切っているか**を返し分ける。
    # 切っているなら「範囲の取り方が悪い」ので慎重に。
    # 語の区切りに揃っているなら、今までどおりの判断に任せる
    # （`カニ打ち → かな打ち` のような、区切りは正しいが
    #   語を取り違えている直しを落とさないため）。
    for t in tokens:
        if t[3] < start < t[4] or t[3] < end < t[4]:
            return 'partial'
    return 'whole'


def _span_is_known_single_word(tokens, start, end):
    """
    この範囲が、形態素解析で**1語**として切られ、かつ辞書に
    載っている語か。載っているなら正しく書けているので触らない。
    """
    for surface, pos, reading, s, e, has_reading in tokens or ():
        if s == start and e == end:
            return bool(has_reading)
    return False


# 濁点「゛」のキーの、**すぐ隣**のキーが出すかな。
# JIS かな配列の並びは  P(せ) @(゛) [(゜) ](む)  で、
# 「ど」と打つつもりで と を打ってから ゛ の隣を叩くと、
# 「とせ」「と゜」のような形になる（実機からの指摘・2026-08-10:
# 「とせ」は「と゛」の隣接扱いとなります）。
#
# 隣の隣までは広げない。け・れ のようなよく使うかなまで
# 「濁点の打ち間違いかもしれない」と見なすと、正しい文が
# 壊れる余地が増えるため。
#
# ここに '゜' '゛' そのものを入れても**到達しない**。この経路の入力は
# find_hiragana_runs が切り出したひらがなの並びで、`is_hiragana('゛')`
# は False なので並びに入らないため（検証レポート 3-D）。
# 単独の濁点・半濁点は、この手前の normalize_marks が先に処理する。
_DAKUTEN_TYPO_CHARS = ('せ',)
_HANDAKUTEN_TYPO_CHARS = ('む',)

# この直しを試す最短の長さ。短い並びは偶然当たりやすい。
_DAKUTEN_TYPO_MIN_RUN = 5
_DAKUTEN_TYPO_MIN_RESULT = 4


def dakuten_typo_variants(run):
    """
    「濁点のキーの隣を押した」と読み替えた別案を並べる。

    「とせらっぐ」→「どらっぐ」。1か所だけ読み替える
    （2か所も間違えたと考えるより、他の説明のほうが確からしい）。

    戻り値: [読み替えた並び, ...]
    """
    try:
        from kana_layout import DAKUTEN_BASE
    except Exception:
        return []
    voiced = {}
    for v, base in DAKUTEN_BASE.items():
        voiced.setdefault(base, v)
    # 半濁点（ぱ行）は DAKUTEN_BASE に無いので自前で持つ
    handaku = {'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ',
               'へ': 'ぺ', 'ほ': 'ぽ'}
    out = []
    for i in range(1, len(run)):
        prev = run[i - 1]
        ch = run[i]
        if ch in _DAKUTEN_TYPO_CHARS and prev in voiced:
            out.append(run[:i - 1] + voiced[prev] + run[i + 1:])
        elif ch in _HANDAKUTEN_TYPO_CHARS and prev in handaku:
            out.append(run[:i - 1] + handaku[prev] + run[i + 1:])
    return out


def dakuten_typo_fix(run, store):
    """
    かなの並びが「濁点のキーの隣を押した形」なら、正しい語に直す。

    **語彙にそのままある読みに一致したときだけ**直す。似ている、
    ではなく完全一致に限るのは、この読み替えが（せ・む という
    よく使うかなを消す）大胆な操作だから。判断はこの関数の中で
    完結させる（判断経路を増やさない、という設計方針）。

    外来語（表記がカタカナだけの語）なら、カタカナの表記を返す
    （ドラッグ。うにさんの指定でカタカナに直す方針・項目48-r）。

    戻り値: 直した文字列。直さないなら None。
    """
    if len(run) < _DAKUTEN_TYPO_MIN_RUN:
        return None
    try:
        if store.lookup(run):
            return None      # そのままで語彙にある＝打ち間違いではない
    except Exception:
        return None
    for cand in dakuten_typo_variants(run):
        if len(cand) < _DAKUTEN_TYPO_MIN_RESULT:
            continue
        try:
            entries = [e for e in store.lookup(cand)
                       if e.get('count', 0) >= 2]
        except Exception:
            entries = []
        if not entries:
            # **覚えていなくても、辞書が実在すると言うなら認める**
            # （2026-08-12・項目48-BH）。ここは「完全一致」を求めて
            # いる場所で、緩めているのは**何を実在の語と認めるか**
            # だけ（似ている、に広げてはいない）。
            # これが無いと、うにさん指定の `とせらっぐ → ドラッグ`
            # が**初期状態では一度も効かない**（ドラッグ を自分で
            # 2回書くまで直らない）。
            try:
                from loanword import _katakana_seed_kana_only
                if cand not in _katakana_seed_kana_only():
                    continue
            except Exception:
                continue
        try:
            from loanword import katakana_for_hiragana
            # ここまで来た時点で「濁点のキーの隣を押した形」として
            # 語彙に完全一致している。根拠が揃っているので、
            # カタカナに直す長さの下限を4文字まで下げてよい。
            kata = katakana_for_hiragana(cand, store, min_length=4)
        except Exception:
            kata = None
        return kata or cand
    return None


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


def _insert_makes(old, ch, new):
    """`old` のどこかに `ch` を1文字入れると `new` になるか。"""
    if len(new) != len(old) + 1:
        return False
    for i in range(len(old) + 1):
        if old[:i] + ch + old[i:] == new:
            return True
    return False


def absorb_stray_char(line, start, end, new):
    """
    **窓が1文字ずれていたせいで残る「余りの1文字」を吸収する**
    （項目48-DS・2026-08-16）。

    窓の切り出し（`explain_cores`）は、かな連続の端の1文字を
    「助詞・送り仮名として説明が付く」と見て窓から外すことがある。
    その1文字が実は語の一部だったとき、残りだけを直すと
    **正しい語＋余りの1文字**という、見るからに壊れた形になる:

        とひまえ   → **とひとまえ** （正解 ひとまえ。窓は `ひまえ`）
        かあちゃん → **かあかちゃん**（正解 あかちゃん。窓は `あちゃん`）
        おきえか   → **おきかえか** （正解 おきかえ。窓は `おきえ`）
        じょおうちば → **じょおうばちば**
        かでゅせうも → **かでゅせもうも**

    どれも「直し先の語」は当たっている。**置く場所だけが1文字
    ずれている。** 直した結果が、外した1文字を**そのまま作り直して
    いる**なら、その1文字は窓に含めるべきだった。範囲を広げる。

    範囲を広げた結果、`new` が元と同じになるなら（＝直前の文字を
    足しただけ）、それは直しではないので呼び出し側が落とす。

    戻り値: (新しい開始, 新しい終了)
    """
    old = line[start:end]

    # **連打を1つ残したまま直した形**も拾う（項目48-DU）。
    # 窓が1文字ずれていて、外した1文字が「連打の片割れ」だった形:
    #
    #     ばりばばり → **ばバリバリ**（正解 ばりばり。窓は `りばばり`）
    #
    # 直し先（かなに戻した形）に隣の1文字を足すと、
    # **ちょうど連打を1つ増やした形**になるなら、
    # その1文字は窓に含めるべきだった。
    _hira = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
                    for c in new)
    for _s2, _e2 in ((start - 1, end), (start, end + 1)):
        if _s2 < 0 or _e2 > len(line):
            continue
        ch = line[_s2] if _s2 < start else line[end]
        if not (is_hiragana(ch) or is_katakana(ch)):
            continue
        ext = line[_s2:_e2]
        if len(ext) != len(_hira) + 1:
            continue
        # ext が _hira のどこか1文字を二重にした形か
        for i in range(len(_hira)):
            if _hira[:i + 1] + _hira[i:] == ext:
                return _s2, _e2

    if len(new) != len(old) + 1:
        return start, end
    if start > 0:
        ch = line[start - 1]
        if (is_hiragana(ch) or is_katakana(ch)) \
                and _insert_makes(old, ch, new):
            return start - 1, end
    if end < len(line):
        ch = line[end]
        if (is_hiragana(ch) or is_katakana(ch)) \
                and _insert_makes(old, ch, new):
            return start, end + 1
    return start, end


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


def _mark_swap_is_better(dropped, swapped, store):
    """
    **印を跨いで合成したほうが、落としたほうより語らしいか**
    （項目48-CW）。

    うにさんの指定（2026-08-13）:
    「濁点か半濁点のキーよりも前に2文字めが割り込むケースはあります。
      プラネタリウムでもその例はありました。」

    項目48-AO で跨いで合成する道は入れたが、採るかどうかの条件が
    **「跨いだ文をさらに補正できたか」**だった。そのため
    **跨いだだけで正解になる場合に、答えを捨てていた**:

        たんこの゛繋がり
          落とす → たんこの繋がり → 補正なし（changed=False）
          跨ぐ   → たんごの繋がり → **もう直すところが無い**
                                     （changed=False なので捨てられた）
        かっ゛こう
          落とす → かっこう（そのまま）
          跨ぐ   → がっこう（捨てられた）

    プラネタリウムだけ通っていたのは、跨いだ `ぷあらねたりうむ` に
    まだ直すところが残っていたから（たまたま条件を満たしていた）。

    ここでは**語らしさ**で決める。印を受け取った文字を含むかなの
    並びを両方から取り出し、末尾の助詞を剥がして、
    **使用実績の多いほうを採る**（48-BZ と同じ考え方）。

        たんご(実績あり) 対 たんこ(実績なし)  → 跨ぐ
        かね(実績あり)   対 がね(実績なし)    → 跨がない
    """
    if not dropped or not swapped or dropped == swapped:
        return False
    i = 0
    while i < len(dropped) and i < len(swapped) and dropped[i] == swapped[i]:
        i += 1
    if i >= len(dropped) or i >= len(swapped):
        return False

    def _kana(c):
        return 'ぁ' <= c <= 'ん' or 'ァ' <= c <= 'ヶ' or c == 'ー'

    def run_at(text, pos):
        a = pos
        while a > 0 and _kana(text[a - 1]):
            a -= 1
        b = pos
        while b < len(text) and _kana(text[b]):
            b += 1
        run = text[a:b]
        return run[:len(run) - _trailing_particle_len(run)]

    d_core = run_at(dropped, i)
    s_core = run_at(swapped, i)
    if not s_core:
        return False

    def best_count(word):
        if not word:
            return 0
        try:
            return max((e.get('count', 0) or 0)
                       for e in store.lookup(word)) if store.lookup(word) else 0
        except Exception:
            return 0

    return best_count(s_core) > best_count(d_core)


def _known_head_plus_functional(run, store):
    """
    **既知語＋機能語の並び**（はじめ＋ようか・それ＋から）は正しい形
    （A道の _kg と同じ判定を、48-HI/48-HJ の入口でも使えるよう
    関数にしたもの）。壊れているとは言えないので触らない。
    """
    for _k in range(2, len(run) - 1):
        _rest = run[_k:]
        if len(_rest) < 2 or not _is_all_functional(_rest):
            continue
        try:
            if [e for e in store.lookup(run[:_k]) if e['count'] >= 2]:
                return True
        except Exception:
            pass
    return False



def _fold_repeat_to_word(run, store):
    """
    **畳むと在る語になる連打**（設計22・項目48-HI・狭い形）。

    隣り合う同じ文字を1つ畳んでみて、畳んだ結果（末尾の助詞を
    除いた本体・3文字以上）が語彙に在る語なら、その畳んだ並びを
    返す。**ただ1通りに畳めるときだけ**（2通り以上は決め手なし）。
    連続そのものが在る語（ここ・たたみ・すすむ）は、呼び元の
    known_or_bundled / 順序1 が先に守る。count の縛りは 48-HH と
    同じ若さ分岐。畳んで**機能語の並び**にしかならない形
    （的 `ににして`）はここでは当たらない——別の証拠が要る。
    """
    from vocabulary import store_is_young as _sy
    _mc = 1 if _sy(store) else 2
    got = []
    for i in range(len(run) - 1):
        if run[i] != run[i + 1] or run[i] == 'ー':
            continue
        # **頭の助詞の二重は畳まない。** 連続の1文字目が助詞なら、
        # それは前の語に付く字で、二重に見えるのは語の頭と重なった
        # だけのことがある（`壁に` ＋ `にげる` ＝ ににげる、
        # `特に` ＋ `について`）。畳むと正しい文が壊れる
        # （fpcheck の型の境目で実測・2026-08-20）。
        if i == 0 and run[0] in PARTICLES_1CHAR:
            continue
        fold = run[:i] + run[i + 1:]
        # 末尾の助詞は0〜2文字まで剥がしてよい。**長いほうから**
        # 試す（`にじゅうか` の末尾 `か` は語の一部——剥がし切って
        # から見ると `にじゅう` しか見えず、取りこぼす）。
        bodies = [fold]
        b = fold
        for _ in range(1):
            if b and b[-1] in PARTICLES_1CHAR and len(b) > 3:
                b = b[:-1]
                bodies.append(b)
        hit = None
        for body in bodies:
            if len(body) < 3:
                continue
            try:
                if [e for e in store.lookup(body) if e['count'] >= _mc]:
                    hit = body
                    break
            except Exception:
                pass
        if hit is not None and fold not in [f for f, _b in got]:
            got.append((fold, hit))
    if len(got) != 1:
        return None
    # **入れ替え（順序違い）でも説明が付くなら畳まない**（決め手なし）。
    # 順序違いの写し間違いは、隣り合う2文字の入れ替えで**同じ文字の
    # 並び**を作ることがある（あどれすばす → あどれす**すば**）。
    # これを畳むと、別の語の切り落としに化ける（あどれすば・
    # おもしろか・てんか・できない——2026-08-20 に readcheck で5件実測）。
    # 入れ替えを1回戻して在る語に届くなら、そちらの解釈と拮抗して
    # いるので触らない（拮抗は直さない、の既存の考えかた）。
    # 入れ替え側の解釈で剥がしてよい助詞は、**元の連続の末尾に
    # もともと在った助詞だけ**（最大2文字）。入れ替えが作った字を
    # 助詞として剥がすと、`はちががつを` の入れ替え `はちがつがを`
    # から `はちがつ`（八月）が見えてしまい、正しい畳みまで
    # 「拮抗」で止まる（2026-08-20 に実測）。
    _tails = ['']
    _b0 = run
    for _ in range(2):
        if _b0 and _b0[-1] in PARTICLES_1CHAR and len(_b0) > 3:
            _tails.append(_b0[-1] + (_tails[-1] if len(_tails) > 1 else ''))
            _b0 = _b0[:-1]
        else:
            break
    for i in range(len(run) - 1):
        if run[i] == run[i + 1]:
            continue
        swp = run[:i] + run[i + 1] + run[i] + run[i + 2:]
        cands = [swp[:-len(t)] if t else swp
                 for t in _tails if not t or swp.endswith(t)]
        for b in cands:
            if len(b) < 3:
                continue
            try:
                if [e for e in store.lookup(b) if e['count'] >= _mc]:
                    return None
            except Exception:
                pass
    # **1字足して在る語に届くなら畳まない**（脱字との拮抗・同上）。
    # `できなない` は なな の連打にも、`できなくない` の く の
    # 脱字にも見える。決め手が無いものは触らない。
    # 足すのは、連続に**もう出ている文字**だけでよい——脱字と
    # 連打が見分けにくいのは、同じ字が近くに並ぶときだから
    # （く は `できなくない` の中に…無い。いや、任意の1字を試す）。
    _chars = [chr(c) for c in range(ord('ぁ'), ord('ん') + 1)]
    for pos in range(len(run) + 1):
        for ch in _chars:
            ins = run[:pos] + ch + run[pos:]
            for t in _tails:
                b = ins[:-len(t)] if t and ins.endswith(t) else (ins if not t else None)
                if not b or len(b) < 3:
                    continue
                try:
                    if [e for e in store.lookup(b)
                            if e['count'] >= _mc]:
                        return None
                except Exception:
                    pass
    return got[0]



def _swap_to_word(run, store, after_kanji=False):
    """
    **入れ替えを戻すと在る語になる順序違い**（項目48-HJ・48-HI と対称）。

    隣り合う2文字を入れ替えてみて、戻した結果（末尾の助詞1文字を
    除いた本体・3文字以上）が語彙に在る語なら、その並びを返す。
    入れ替えは**文字の顔ぶれを変えない**強い形の証拠（既存の
    強い形の並びと同じ考え）。門は 48-HI と同じ構え:

      - **ただ1通り**のときだけ（2通り以上は決め手なし）
      - **連打の畳みでも説明が付くなら触らない**（`てんんか` は
        てんかん の入れ替えにも 転化 の連打にも見える）
      - count は 48-HH と同じ若さ分岐
      - 連続そのものが在る語は呼び元の known_or_bundled が先に守る
    """
    from vocabulary import store_is_young as _sy
    _mc = 1 if _sy(store) else 2
    def _bodies(t):
        out = [t]
        if t and t[-1] in PARTICLES_1CHAR and len(t) > 3:
            out.append(t[:-1])
        return out
    def _known(t):
        try:
            return bool([e for e in store.lookup(t)
                         if e['count'] >= _mc])
        except Exception:
            return False
    # **本体（末尾の助詞を除いた連続）が在る語なら触らない。**
    # `きかんに` は known_or_bundled（連続まるごと）では守れない——
    # `きかん`（機関）＋`に` の形。ここを見ずに入れ替えると
    # 正しい語＋助詞が `きんかに` に壊れる（2026-08-20 実測）。
    for b in _bodies(run):
        if len(b) >= 2 and _known(b):
            return None
    got = []
    # **漢字の直後の連続では、頭の2文字に掛かる入れ替えを見ない。**
    # 頭は前の漢字の送り仮名のことが多く、`要らないと` の頭を
    # 入れ替えると `要ならいと`（習い に吸われる）と壊れる（実機
    # メモで実測）。1文字ずらしでも `深きゃから → 深きゃらか`
    # （きゃら に吸われる）が出た（fpcheck の型の境目で実測）ので、
    # 2文字目までは動かさない。
    _i0 = 2 if after_kanji else 0
    for i in range(_i0, len(run) - 1):
        if run[i] == run[i + 1]:
            continue
        swp = run[:i] + run[i + 1] + run[i] + run[i + 2:]
        hit = None
        for b in _bodies(swp):
            # 戻し側は**4文字以上**の語だけ。3文字の語は偶然
            # 引き寄せやすく、`深きゃから` の `から` を入れ替えて
            # `きゃら`＋`か` に吸われた（fpcheck の型の境目で実測。
            # 畳み側の3文字とは危なさが違う——畳みは文字を減らす
            # だけだが、戻しは並びを作り替える）。
            if len(b) < 4:
                continue
            if _known(b):
                hit = b
                break
        if hit is not None and swp not in [f for f, _b in got]:
            got.append((swp, hit))
    if len(got) != 1:
        return None
    # 連打の畳みでも説明が付くなら触らない（拮抗）
    for i in range(len(run) - 1):
        if run[i] != run[i + 1] or run[i] == 'ー':
            continue
        fold = run[:i] + run[i + 1:]
        for b in _bodies(fold):
            if len(b) >= 3 and _known(b):
                return None
    # **1字足して在る語に届くなら戻さない**（脱字との拮抗。
    # `いちん` は いんち の入れ替えにも `いちだん`・`いちえん` の
    # 脱字にも見える——12件の新化けの大半がこの形だった）。
    _chars = [chr(c) for c in range(ord('ぁ'), ord('ん') + 1)]
    for pos in range(len(run) + 1):
        for ch in _chars:
            ins = run[:pos] + ch + run[pos:]
            for b in _bodies(ins):
                if len(b) >= 3 and _known(b):
                    return None
    # **濁点・半濁点の付け外しで在る語に届くなら戻さない**
    # （`さんか` は さかん の入れ替えにも `さんが` の濁点にも
    # 見える）。
    _DK = {'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご',
           'さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ',
           'た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど',
           'は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ'}
    _DKR = {v: k for k, v in _DK.items()}
    _HP = {'は':'ぱ','ひ':'ぴ','ふ':'ぷ','へ':'ぺ','ほ':'ぽ'}
    _HPR = {v: k for k, v in _HP.items()}
    for i2, ch in enumerate(run):
        for alt in (_DK.get(ch), _DKR.get(ch), _HP.get(ch),
                    _HPR.get(ch)):
            if not alt:
                continue
            var = run[:i2] + alt + run[i2 + 1:]
            for b in _bodies(var):
                if len(b) >= 3 and _known(b):
                    return None
    return got[0]



def _unit_table_support(chunk, surface, names):
    """
    **単位の表（`seed_japanese`）を、48-EA の近接条件に並べる**
    （設計23・項目48-HM）。

    「近くに書いてあるか」は**書いた人の都合**であって、日本語として
    正しいかどうかとは関係が無い（項目48-AE と同じ考え）。そこで
    **表が言えることだけ**を、同じ形（語ごと）で並べる。
    **新しい判断は作らない。** 使うのは既にある2つだけ:

      (1) `rebuild_is_suspicious` が **True**
          ＝ **元は非単位で、直し先が1語として在る**（項目48-FC）。
            説明ぶん → **説明文** ／ 待ち外 → **間違い**
          この関数は「元が1語として在る」なら False を返すので、
          **正しく書けた塊は自分で断る**（土俵が広がりにくい）。

      (2) 組の語が**全部 1語として在り、かつ元の塊に文字通り
          入っている**（＝直しは**混入した字を落とすだけ**で、
          語の入れ替えではない）。
            該当あの範囲 → **該当の範囲**（該当・範囲 はどちらも
            元の塊にそのまま在り、落ちるのは `あ` だけ）

    **(2) に「文字通り入っている」が要る理由。** これが無いと
    `補正後 → 補正意図` が通る（補正・意図 はどちらも1語として
    在るので、語が在るだけでは分けられない）。**それはこの門が
    もともと止めていた誤爆そのもの**なので、必ず残すこと。
    `意図` は `補正後` に入っていないので、この形なら止まる。

    表が無ければ **None**（意見なし）＝これまでどおり。

    戻り値: 通してよい理由の文字列、または None
    """
    try:
        import seed_japanese as _sj
    except Exception:
        return None
    if not _sj.available():
        return None

    def _no_kana(w):
        """
        **表が意見を持てる形か——活用が絡む語には使わない**
        （項目48-HM／根拠は項目48-HN）。

        `in_scope` と同じ考えで、**表の守備範囲を守る**ための線。
        「異様さの判定をあきらめた」のではない。

        **単位の表は活用について何も言えない。** 載っているのは
        言い切りの形なので、`追加する` `察して` `出ました` `適した`
        はどれも**正しい日本語なのに「非単位」**と出る。そこを
        突かれて、実機メモでこう壊した（2026-08-20 に実測）:

            追加すると通常モードに戻ります → **かすると**通常モードに…
            糸を察して                    → 糸を**さして**
            候補が出ましたが              → 候補が**だましが**
            カタカナが適した単語          → カタカナが**適し**単語

        **「活用を戻してから聞けばよい」とはならない**（項目48-HN で
        実測）。言い切りに戻すと `差釣れません`（釣れる）も
        `該当あの範囲`（該当・あの・範囲）も**全部「在る」**になり、
        **表は何も言わなくなる**。分解すれば、どんな誤変換も
        「在る語の並び」になるからである。

        だから線は**形**で引く。かなを含まない語＝活用の絡まない
        語についてだけ、表の答えを使う。4件とも止まり、的
        （該当の範囲・説明文・クリックかドラッグ）は残った。
        **fpcheck では1件も見えなかった**（実機メモでだけ出た）。

        **異様さそのものは、ここでは決まらない。** このアプリの
        異様さの判定は**比べる形**（自然さ・項目48-AE、単位の表の
        `rebuild_is_suspicious`・項目48-FC）でできている。
        `差釣れません → されません` は自然さの差 7839 で通っている。
        """
        return bool(w) and all(
            ('一' <= c <= '鿿') or ('ァ' <= c <= 'ヶ') or c in 'ー々'
            for c in w)

    # (1) 直し先が1語として在る（元は非単位）。**直し先は漢字・
    #     カタカナだけ**（かなを含む直し先は活用形と見分けられない）
    try:
        if _no_kana(surface) and _sj.rebuild_is_suspicious(
                chunk, surface) is True:
            return f'{surface!r} は1語として在る（元は非単位）'
    except Exception:
        pass
    # (2) 組の語が全部1語として在り、元の塊に文字通り入っている。
    #     **語はどれも漢字・カタカナだけ**（同上）
    try:
        if _sj.is_unit(chunk):
            return None            # 元が1語＝正しく書けている
        solid = [w for w in names
                 if len(w) >= 2 and not _is_all_functional(w)]
        if len(solid) < 2:
            return None
        if not all(_no_kana(w) for w in solid):
            return None
        if not all(_sj.is_common_unit(w) for w in solid):
            return None
        if not all(w in chunk for w in solid):
            return None
        return (f'組の語 {solid} はどれも1語として在り、'
                f'元の塊にそのまま入っている')
    except Exception:
        pass
    return None



def _odd_chunk_edges_are_real(line, start, end):
    """
    漢字の並びの**両端が、本当の語の切れ目か**を見る（項目48-HU）。

    設計27 は「漢字の並び」を一つの塊として扱う。だが並びの
    すぐ隣にカタカナが立っているとき、その境目は語の切れ目では
    なく、**一つの塊を漢字とカタカナで切った跡**でしかない:

        文字乳リュク   漢字の並び = `文字乳`
                       本当の切れ目 = `文字` ＋ `乳リュク`
                       （`にゅうりょく` → 入力）

    このとき `文字乳` だけを開いて直すと `文字立ち` になり、
    **後ろの経路（混合塊）から塊を奪う**（実機メモ・2026-08-21）。

    ひらがなが隣に立つのは送り仮名・助詞なので**切れ目として
    正しい**。見るのはカタカナ（と長音符）だけ。

    True = 端が本当の端。False = 途中で切れている。
    """
    for c in (line[start - 1] if start > 0 else '',
              line[end] if end < len(line) else ''):
        if not c:
            continue
        if ('ァ' <= c <= 'ヶ') or c == 'ー' or c == 'ヽ' or c == 'ヾ':
            return False
    return True


def _reopen_odd_chunk(chunk, store, tokenize_fn, dict_index=None,
                      input_method=None):
    """
    **異様と判定した塊を、ひらがなに開いて直す**（設計27・項目48-HS）。

    うにさんの指定（2026-08-21）:

        「**異様だと判定されたら、ひらがなに開きます。** 今は IME 変換
          確定前文字列もあります。そこから、隣接キーなどの補正を試し、
          **異様さがなくなったもの、より自然な文字列に補正します**」

    流れはその言葉のまま:

        1. 異様と判定        `oddness.is_odd_run`（項目48-HP）
        2. **ひらがなに開く**  **IME が確定した読み**（設計25(甲)の対）
                             ＋**解析が言い切っている読み**だけ。
                             **当て推量の読みは使わない**（項目48-DE）
        3. **隣接キーなどを試す** 隣接キー1置換＋誤打4種
                             （重複打鍵・脱字・順序違い・濁点）
        4. 直した読みから表記を組む（丸ごと／2語の組。
                             **部分はどれも使用実績2以上**）
        5. **受け入れ**       **異様さが消えた** ∧ 語の並びとして読める
                             ∧ 長さ ±1 ∧ 自然さが**大きく悪くならない**

    **`より自然` は受け入れに使えない**（項目48-HR で実測）:

        naturalness.gain(**野外文章 → 長い文章**) = **-1080**

    自然さの表は「野外文章のほうが自然だ」と言う。だから自然さには
    **拒否権だけ**を持たせ、採る決め手は
    **「異様さが消えた」＋「使用実績」**にする。
    `長い`(実績2) が `ニガい`(実績1) に勝つ。

    **印（`oddness`）の誤爆は、ここで吸収される。** `補正欄` `漢字塊`
    `添付画像` は印が立つが、開いて直しても「異様さが消えて実績のある
    語」に届かないので何も返らない（実測・18件とも無傷）。

    戻り値: (表記, 分類) または None。
    """
    try:
        import oddness as _odd
        from kana_layout import nearby_candidates as _near
    except Exception:
        return None
    if not chunk or len(chunk) < 3 or not _odd.available():
        return None
    _odd_pairs = _odd.is_odd_run(chunk, tokenize_fn)
    if not _odd_pairs:
        return None                     # 印が立たない＝入口に入らない
    # **1字を根拠にしては動かない**（項目48-HU）。
    #
    # 印は「差＋釣れ」「型＋不一致」のような1字がらみの並びにも
    # 立つ。**印が見えること自体は正しい。** だが表
    # （`seed_japanese.txt.gz`）には**1字の語が1つも入っていない**
    # ので、1字の側については**数えた証拠が何も無い**。
    # 証拠が無いまま開いて直すと、育った語彙では
    #
    #     型不一致（正しい）→ 片手一致    ← 壊した
    #     一度止まる（正しい）→ 一度とりまる
    #
    # になった（2026-08-21 に実測）。**印は見える。動くのは
    # 決め手があるときだけ**——うにさんの決まり
    # 「判断がつかないものは触らない」。
    # 2字以上どうしの並びが1つも無いなら、ここでは決めない。
    if not any(len(a) >= 2 and len(b) >= 2 for a, b in _odd_pairs):
        _trace('異様', f'{chunk!r} → 印は立つが {_odd_pairs} は'
                       f'**1字がらみ**（表に1字の語は無い＝数えた'
                       f'証拠が無い）。決めない（設計27・項目48-HU）')
        return None
    _trace('異様', f'{chunk!r} → 印が立った（{_odd_pairs}・設計27の入口）')

    # --- 2. ひらがなに開く（**当て推量の読みは使わない**）---
    readings = []
    try:
        from kanji_guess import _IME_READINGS_PROVIDER as _prov
        if _prov is not None:
            for r in (_prov(chunk) or ()):
                if r and r not in readings:
                    readings.append(r)
    except Exception:
        pass
    _ar = _analyzer_reading(chunk, tokenize_fn)
    if _ar and _ar not in readings:
        readings.append(_ar)
    if not readings:
        _trace('異様', f'{chunk!r} → **ひらがなに開けない**'
                       f'（IMEの読みも解析の読みも無い）。決めない')
        return None
    _trace('異様', f'{chunk!r} → 開いた読み {readings}')

    # --- 3. 隣接キーなどを試す ---
    def _fixes(rd):
        got = {}
        for i, ch in enumerate(rd):
            try:
                for alt, d in _near(ch):
                    if alt != ch and d <= 1.0:
                        got[rd[:i] + alt + rd[i + 1:]] = '隣接キー'
            except Exception:
                pass
        try:
            for r in _typo_repairs(rd):
                got.setdefault(r, '誤打の型')
        except Exception:
            pass
        got.pop(rd, None)
        return got

    # --- 4. 直した読みから表記を組む（部分は使用実績2以上）---
    def _surfaces(rd):
        out = {}
        try:
            for e in store.lookup(rd):
                if e.get('count', 0) >= 2:
                    out[e['surface']] = max(out.get(e['surface'], 0),
                                            e['count'])
        except Exception:
            pass
        for i in range(2, len(rd) - 1):
            a, b = rd[:i], rd[i:]
            try:
                sa = [(e['surface'], e['count']) for e in store.lookup(a)
                      if e.get('count', 0) >= 2]
                sb = [(e['surface'], e['count']) for e in store.lookup(b)
                      if e.get('count', 0) >= 2]
            except Exception:
                continue
            for x, cx in sa[:3]:
                for y, cy in sb[:3]:
                    out[x + y] = max(out.get(x + y, 0), min(cx, cy))
        return out

    from kanji_guess import looks_like_real_word as _real
    import collections as _collections
    best = None
    cands = {}
    _why = _collections.Counter()
    _seen_any = False
    for rd in readings:
        for fixed, how in _fixes(rd).items():
            for surf, cnt in _surfaces(fixed).items():
                if surf == chunk or abs(len(surf) - len(chunk)) > 1:
                    continue
                _seen_any = True
                # 5-a: **異様さが消えたか**
                if _odd.is_odd_run(surf, tokenize_fn):
                    _why['異様さが消えない'] += 1
                    continue
                # 5-b: 語の並びとして読めるか
                try:
                    if not _real(surf, store, tokenize_fn):
                        _why['語の並びとして読めない'] += 1
                        continue
                except Exception:
                    _why['語の並びとして読めない'] += 1
                    continue
                # 5-c: **自然さは拒否権だけ**（大きく悪くなるなら採らない）
                try:
                    if _naturalness.gain(chunk, surf) < -_ODD_REOPEN_DROP:
                        _why['自然さが大きく落ちる'] += 1
                        continue
                except Exception:
                    pass
                # 5-d: 直し先が固有名詞だけなら採らない（既存の門と同じ）
                try:
                    if _is_whole_proper_noun(surf, tokenize_fn):
                        _why['固有名詞だけ'] += 1
                        continue
                except Exception:
                    pass
                key = (-cnt, len(surf), surf)
                cands[surf] = min(cands.get(surf, key), key)
                if best is None or key < best[0]:
                    best = (key, surf, how, rd, fixed, cnt)
    # **異様と判定したら、実績のいちばん高い候補に直す**
    # （うにさんの指定・2026-08-21・項目48-IE）:
    #
    #   「**ただ1つのときだけ採るのは望ましくない。異様なものは
    #     変える。まず何かの候補に補正してしまいたい**」
    #
    # 項目48-HU では「ただ1つのときだけ採る」を置いていた。動機は
    # `素帰任 → もし帰任`・`鍵括弧 → かぎ各国` だったが、**同じ48-HU で
    # 入れた「1字がらみでは動かない」が、いまその2つを先に止めている**
    # （どちらも (素,帰任) (鍵,括弧) と1字がらみ）。
    # **3つ一度に入れたので、どれが効いているかを分けて測っていなかった。**
    #
    # 外して実測（2026-08-21）:
    #
    #     野外文章  候補 やがて(実績23) / ニガい(3) / **長い(679)**
    #               → 実績で選べば `長い文章`。**育った語彙のほうが
    #                 初期状態(2対1)よりずっと強く正解を指している**
    #
    #     見本行63組・育った語彙  直った **17 → 18**・化け0
    #     初期状態                **1行も動かない**
    #     実機メモ                差は `野外文章 → 長い文章` だけ・壊し0
    #
    # 残っている断りは、**触ってはいけないものを守る門だけ**にする。
    if best is None:
        if best is None and not _seen_any:
            _trace('異様', f'{chunk!r} → 直し先の**表記が一つも組めない**'
                           f'（実績2以上の語に届かない）。決めない')
        elif best is None:
            _trace('異様', f'{chunk!r} → 直し先は出たが全部落ちた: '
                           f'{dict(_why)}。決めない')
        else:
            _trace('異様', f'{chunk!r} → 直し先が {len(cands)}個'
                           f'（{sorted(cands)[:4]}）並んだ。'
                           f'**決め手が無いので触らない**')
        return None
    _, surf, how, rd, fixed, cnt = best
    _trace('異様', f'{chunk!r} → 異様なので {rd!r} に開き、'
                   f'{how}で {fixed!r} に直して {surf!r}'
                   f'（実績{cnt}・設計27）')
    return surf, 'その他'



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
        # input_method を渡し忘れると既定の 'kana' に落ちるため、
        # **ローマ字入力の人だけ**、濁点が分離した文字を1つ含む行の
        # 補正が効かなくなる（検証レポート 3-A。
        # '。゛しじとう' が 'しじょう' に届かない）。
        inner = correct_line(normalized, store, tokenize_fn, find_readings,
                             max_dist=max_dist, context_vocab=context_vocab,
                             decisions=decisions, context_vec=context_vec,
                             dict_index=dict_index,
                             input_method=input_method,
                             nearby_words=nearby_words,
                             recent_words=recent_words)
        # **印を落としただけで、その先が語にならなかったとき**は、
        # 打つ順番が入れ替わっただけかもしれない（項目48-AO）。
        #
        #     プ ＝ フ → ゜（JISかな・2打）
        #     打たれたのは フ → ア → ゜ ＝ 3つの順番が入れ替わった
        #
        # うにさんの指定:「ふ、半濁点、あ の3つの順番が入れ替わり、
        # ふ、あ、半濁点となったので、**他の順序入れ替えと同等の
        # 扱い**です」。
        #
        # **落としたほうが補正に届いたなら、そちらを採る**。
        # 先に跨いで合成すると `たん゛子の繋がり` が
        # `だん子→担子` に化けて `単語` に届かなくなる（実測）。
        # 学び38「許可は、候補を絞る前ではなく、決まってから掛ける」。
        if not inner['changed']:
            try:
                swapped = normalize_marks(line, swap_across=True)
            except Exception:
                swapped = normalized
            if swapped != normalized:
                alt = correct_line(swapped, store, tokenize_fn, find_readings,
                                   max_dist=max_dist,
                                   context_vocab=context_vocab,
                                   decisions=decisions, context_vec=context_vec,
                                   dict_index=dict_index,
                                   input_method=input_method,
                                   nearby_words=nearby_words,
                                   recent_words=recent_words)
                # **跨いだだけで正解になる場合を捨てない**（48-CW）。
                # `alt['changed']` は「跨いだ文をさらに直せたか」で、
                # 跨ぎ自体が答えのときは False になる。
                if alt['changed'] or _mark_swap_is_better(
                        normalized, swapped, store):
                    inner = alt
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

    # --- 括弧のつもりで打った、同じキーのかな（゜…む／ゆ…よ）---
    # **括弧を先に判定して、中身の補正はそのあとで考える**
    # （2026-08-16・うにさんの指定）。括弧に直した行を丸ごと
    # 補正し直せば、中身は普段の道で直る（上の濁点合成と同じ形）。
    # ただし **normalize_marks（印の合成）よりは後**。先に見ると
    # `フア゜ラネタリウム`（順序入れ替わりの゜）の ゜ を括弧の
    # 開きと取り違えて `フア「ラネタリウ」` と壊した（実測）。
    # 印の合成で説明が付く行はそちらが先、というだけで、
    # 「括弧が中身の補正より先」の順序は変わらない。
    _brk = _fix_kana_brackets(line, store, tokenize_fn, dict_index)
    _brk += _fix_ascii_brackets(line, store)   # 8ok9 → (ok)
    if _brk:
        _b_chars = list(line)
        for _b_s, _b_e, _b_r in _brk:
            _b_chars[_b_s] = _b_r
        _b_line = ''.join(_b_chars)
        inner = correct_line(_b_line, store, tokenize_fn, find_readings,
                             max_dist=max_dist, context_vocab=context_vocab,
                             decisions=decisions, context_vec=context_vec,
                             dict_index=dict_index,
                             input_method=input_method,
                             nearby_words=nearby_words,
                             recent_words=recent_words)
        corrected = inner['corrected']
        spans = []
        original_spans = []
        details = []
        import difflib
        sm = difflib.SequenceMatcher(None, line, corrected,
                                     autojunk=False)
        _brk_pos = {s for s, _e, _r in _brk}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            original_spans.append((i1, i2))
            spans.append((j1, j2))
            details.append((line[i1:i2], corrected[j1:j2],
                            '記号' if i1 in _brk_pos else 'かな入力'))
        return {
            'original': line,
            'corrected': corrected,
            'changed': corrected != line,
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
            # **語の途中から塊を始めない**（項目48-DQ）。
            #
            #     昨日ブラクを見ました。 → **昨開くを見ました。**
            #     （塊 `日ブラク` の `日` は `昨日` の一部。
            #       読みを `ひぶらく` と推して `開く` に化け、
            #       **正しく書けている `昨日` まで消えた**）
            #
            # `find_leading_kanji_runs` は「前が漢字でも拾う」
            # （`文字乳リュク` の `乳リュク` を拾うため）。そこは
            # 「重なり処理と分割解決が守る」つもりだったが、
            # **守れていなかった**。
            #
            # 文全体の解析で**2文字以上の語が塊の頭を跨いでいる**なら、
            # そこは語の途中である。`文字乳リュク` は 文字/乳/リュク と
            # 切れるので跨がず、今までどおり拾える。
            if any(tk[3] < t_start < tk[4] and tk[5]
                   and (tk[4] - tk[3]) >= 2 for tk in tokens):
                _trace('混合塊', f'{chunk!r} → 語の途中から始まって'
                                 f'いるので1塊にしない')
                continue
            # 地名の接尾で終わる塊は固有名詞の可能性が高い。
            # find_kanji_runs 側と同じ形の守り（実機で「つく駅」が
            # 「使えん」に化けた・2026-08-09。つく＋えき の読みが
            # 訂正2箇所で つかえん に届いてしまう）。
            if len(chunk) >= 2 and chunk[-1] in '駅県市区町村港':
                continue
            # **副詞・接続詞は、後ろの語と1塊にしない**（項目48-CI）。
            #
            #     まず上を見ます。          → まずいを見ます。
            #     まず色とりどりから始めます。 → 水色とりどりから始めます。
            #     まず下がりから始めます。    → また下がりから始めます。
            #
            # `find_trailing_kanji_runs` は「かな＋漢字」を1塊にする
            # （`たん子`＝たんこ→単語 を拾うために要る）。ところが
            # **副詞「まず」＋名詞「上」**まで1塊にしてしまい、
            # 読みが `まずあ` になって `まずい` に化けていた。
            #
            # 副詞・接続詞は**後ろの名詞と複合語を作らない**ので、
            # ここで切ってよい。`たん子` の `たん` は名詞なので残る。
            #
            # 実測: 実機のメモ全6タブ＋正しい日本語＋散文で
            # **変わった行51件・答えも1件も動かない**。
            # 材料全体でこの形の塊は 副詞14件・接続詞3件だけだった。
            _head = _leading_hiragana(chunk)
            if _head and _is_adverbial_word(_head, tokenize_fn):
                _trace('混合塊',
                       f'{chunk!r} → 先頭が副詞・接続詞なので1塊にしない')
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
            # **辞書に載っている塊は、読み直さない**（項目48-CG）。
            #
            # 48-CF と同じ形。中立な文6,077で残っていた誤検知2件は
            # どちらもこれだった:
            #
            #     ジリ高 → 実行   （じりこう → じっこう と読み直した）
            #     ジリ安 → ジリ貧
            #
            # どちらも janome が**1語の名詞として知っている株の用語**
            # なのに、混合塊の経路が読みに戻して直していた。
            #
            # 直したい側は**全部 辞書に載っていない**:
            #     タン子 ／ カニ打 ／ 時ッ層 ／ 田安吾
            #     ププラネタリウム ／ プニラネタリウム
            #
            # ここでも根拠にするのは**「載っている」ことだけ**。
            # 載っていないときは何も言わない（48-AR の轍を踏まない）。
            if dict_index is not None:
                try:
                    if dict_index.readings_for_surface(chunk):
                        _trace('混合塊',
                               f'{chunk!r} は辞書にある語なので読み直さない')
                        continue
                except Exception:
                    pass
            surrounding = _surrounding_content_words(
                tokens, t_start, t_end,
                nearby_words=nearby_words, recent_words=recent_words)
            combos = reading_combos_with_rank(
                chunk, dict_index, next_char=_next_char(line, t_end))
            # 実在する語の並びとして読める塊（うどん粉＝うどん＋粉）は、
            # 読みの完全一致による表記の差し替えを許さない。読みが
            # 同じ別表記（饂飩粉）へのすり替えは誤字の訂正ではなく
            # 表記変換であり、方針1に反する（実機・2026-08-09）。
            # 芯の再構築（壊れた読みを直す）は引き続き試す。
            got = _resolve_reading_list(
                chunk, [r for r, _k in combos[:6]], store, tokenize_fn,
                context_vec=context_vec, surrounding=surrounding,
                allow_exact=not looks_like_real_word(chunk, store,
                                                     tokenize_fn),
                dict_index=dict_index, input_method=input_method)
            if got is None:
                continue
            new_surface, category = got
            if len(new_surface) * 2 < len(chunk):
                continue
            if not _katakana_melt_ok(chunk, new_surface, store,
                                    tokenize_fn):
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
            combos = reading_combos_with_rank(
                chunk, dict_index, next_char=_next_char(line, m_end))
            got = _resolve_reading_seq(
                chunk, [r for r, _k in combos[:6]], store, tokenize_fn,
                line_span=(line, m_start, m_end),
                context_vec=context_vec, surrounding=surrounding,
                require_context=looks_like_real_word(chunk, store,
                                                     tokenize_fn),
                attest_text=line[:m_start] + ' ' + line[m_end:],
                only_whole=m_only_whole)
            if got is None:
                # --- 項目48-EQ（設計8）: 駄目なら他の経路へ譲る ---
                #
                # 第41回の測定で分かったこと: `目もち長 → メモ帳` が
                # 止まっているのは**並記の門ではなく、その手前の
                # 「組の作り方」**だった。組の経路は `メモちょが` を
                # 作って落とし、**そこで塊を抱えたまま終わる**ので、
                # 「漢字塊→読み→芯の再構築」の道（1-C）へ**順番が
                # 回らなかった**。実際、`rebuild_window_core` に
                # 読み `めもちちょう` を直に渡すと `めもちょう`
                # （＝メモ帳）を返す。**直す力はあった。**
                #
                # だから「入口を増やす」だけにする。**判断は増やさない**
                # （SPEC の設計方針）。落とした判断はそのまま正しく、
                # それを覆すのではなく、**別の解釈に順番を回す**。
                # 再構築側の門（敷き詰め・自然さ・切り詰め禁止・
                # 項目48-EN の世の中の門）は1つもゆるめていない。
                _rl = [r for r, _k in combos[:6]]
                got = _resolve_reading_list(
                    chunk, _rl, store,
                    tokenize_fn, context_vec=context_vec,
                    surrounding=surrounding,
                    allow_exact=not looks_like_real_word(
                        chunk, store, tokenize_fn),
                    dict_index=dict_index, input_method=input_method)
                if got is None or not fallthrough_rebuild_ok(
                        chunk, got[0], _rl, store, dict_index,
                        tokenize_fn):
                    continue
                _trace('語の組', f'{chunk!r} → 組では決まらなかったので'
                                 f'芯の再構築へ譲った → {got[0]!r}')
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
            # 文全体では読めている塊（＝範囲が語を途中で切っている）は、
            # 明らかに自然になるときだけ直す（項目48-AH）。
            #   作れる/こと の `作れるこ` → `される`
            #   1行が/重い/こと の `重いこ` → `おもい`
            if _span_reads_in_sentence(
                    tokens, line, m_start, m_end) == 'partial' \
                    and not _naturalness.line_not_worse(
                        line, m_start, m_end, new_surface, default=False):
                _trace('語の組', f'{chunk!r} → {new_surface!r} は'
                                 f'文全体では読める並びなので直さない')
                continue
            _trace('語の組', f'{chunk!r} → {new_surface!r}')
            replacements.append((m_start, m_end, new_surface, category))
            kanji_taken.append((m_start, m_end))

        # --- 設計18（項目48-FF）: 入口(a) を「かな混じりの語連続」へ ---
        #
        # 第44回で測った「入口の三重の狭さ」の (a)。いまの造語の
        # 入口は **漢字だけが3字以上つながっている塊**しか見ない。
        # うにさんの的13件のうち**7件**がここで落ちている:
        #
        #     歳で以下 ／ 差す代価 ／ 誘い消化 ／ 小売り坂 ／
        #     居で以下 ／ 時ッ層 ／ 目もち長
        #
        # ここでは**自立語が2つ以上つながった範囲**（かなを含んで
        # よい・漢字を1字は含むこと）を塊として、同じ
        # `compose_from_intruded` に通す。**門は1つも足さない**
        # （Fable 5 の指示どおり。新しい門は作らない）。
        #
        # **既定で動くのは「かな1字だけ混じる」形だけ**（項目48-HD・
        # 2026-08-20 に Fable が測って火入れ）。
        #
        # 全部を通すと（`CORRECTNOTE_D18=1` の測定で実測・初期状態）:
        #     直る +2（差す代価→最大化・誘い消化→最小化）
        #     壊す  5（よう修正→優秀性・指示します→獅子時ます・
        #             そのあと補正欄→その後性欄・移行でき→以降的・
        #             タブ管→多分化）＋見本行で 解析課→回線化
        # 壊れた5件は**どれも、かな2字以上かカタカナを含む範囲**。
        # 直った2件は**どちらも、かな1字だけが漢字に挟まる形**。
        #
        # `compose_from_intruded` の造りは「**入り込んだ1打**を
        # 落とした読みから組む」（項目48-EX）。かな1字＝その形。
        # かな2字以上は「入り込んだ1打」ではなく**語の一部**
        # （よう・し・でき）なので、開いて組み直すと別の語になる。
        # カタカナ語は原則対象外（既存の方針のまま）。
        # かなが無い範囲は従来の造語の入口（下の 48-EX）が持って
        # いるので、ここでは見ない（`解析課 → 回線化` の化けを
        # 作らないため）。
        #
        # **門は足していない。入口をこの形に絞っただけ**（48-EQ と
        # 同じやり方）。広い入口は `CORRECTNOTE_D18=1` の測定用に残す。
        if True:
            for m_start, m_end, chunk in _content_word_spans(
                    line, tokenize_fn):
                if not _d18_enabled():
                    _hira = sum(1 for c in chunk if is_hiragana(c))
                    _kata = sum(1 for c in chunk
                                if ('ァ' <= c <= 'ヶ') or c == 'ー')
                    if _hira != 1 or _kata:
                        continue
                    # かなは**漢字に挟まれている**こと。端のかなは
                    # 「入り込んだ1打」ではなく語の一部（`指示し` の
                    # `し`）で、育った語彙では 指示し → 獅子時 と
                    # 正しい文を壊した（2026-08-20 に実測）。
                    if not (is_kanji(chunk[0]) and is_kanji(chunk[-1])):
                        continue
                if any(not (m_end <= s or m_start >= e)
                       for s, e in halfwidth_taken + kanji_taken):
                    continue
                if _is_before_honorific(line, m_end):
                    continue
                if any(p in line[max(0, m_start - 1):m_end + 2]
                       for p in PROTECTED_CLASSICAL):
                    continue
                try:
                    _s_toks = tokenize_fn(chunk)
                except Exception:
                    continue
                if any('名詞:数' in (t[1] or '') for t in _s_toks):
                    continue
                # **読みは解析が言い切るものを渡す**（項目48-DE）。
                # `reading_combos_with_rank` は漢字だけの塊向けで、
                # かな混じりでは**空を返す**（`誘い消化` → `[]`）。
                # 空だと `compose_from_intruded` が入口で止まるので、
                # ここは解析の読みをそのまま渡す。
                _sr = _analyzer_reading(chunk, tokenize_fn)
                if not _sr:
                    continue
                _cg = compose_from_intruded(
                    chunk, [_sr], store, dict_index, tokenize_fn)
                if _cg and _cg != chunk:
                    _trace('造語', f'{chunk!r} → {_cg!r}'
                                   f'（設計18・かな混じりの語連続）')
                    replacements.append((m_start, m_end, _cg, 'その他'))
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
            # --- 項目48-EX: 造語めいた複合語（うにさん指示・2026-08-18）---
            #
            #     「Shift+左右で4文字を選択したら候補が出ましたが、
            #       これを**初期状態で自動補正される**ところを目指します」
            #
            # `殺意代価` は `殺意`＋`代価` と**どちらも実在語**なので、
            # ここまでのどの門も「壊れている」と言わない。だから
            # 第43回までは**どの経路にも乗っていなかった**。
            # うにさんの言う「文字列として違和感を感じるもの」＝
            # **単位としてどこにも無い複合**を、ここで見る。
            #
            # 門は `compose_from_intruded` に全部書いてある
            # （単位で無い ∧ 開いた読みから組める ∧ ただ1つ ∧
            #   頭が変わっている）。**自動補正なので厳しくしてある。**
            if all(is_kanji(c) for c in chunk) and len(chunk) >= 3 \
                    and len([t for t in _c_toks
                             if not (t[1] or '').startswith(
                                 ('助詞', '助動詞', '記号'))]) >= 2:
                _cg = compose_from_intruded(
                    chunk, [r for r, _k in reading_combos_with_rank(
                        chunk, dict_index)[:6]],
                    store, dict_index, tokenize_fn)
                if _cg:
                    _trace('漢字塊', f'{chunk!r} → {_cg!r}（造語めいた'
                                     f'複合を開いて組み直した）')
                    replacements.append((k_start, k_end, _cg, 'その他'))
                    kanji_taken.append((k_start, k_end))
                    continue
            # --- 項目48-ID（設計31）: **接尾の場に頭が合わない複合** ---
            # `背景食` は、ここまでのどの門も「壊れている」と言わない
            # （背景も食も実在語で、切り方も正しい）。**接尾が要求する
            # 意味の場**だけが合っていない。上の造語（48-EX）と同じ
            # 家族なので、隣に置く。
            _tf = _scoped_tail_fix(chunk, tokenize_fn)
            if _tf:
                replacements.append((k_start, k_end, _tf, 'その他'))
                kanji_taken.append((k_start, k_end))
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
            # **項目48-CB は測って、入れなかった**（2026-08-13）。
            #
            # `作った行 → 実態` を止めるため、「形態素に割って
            # 真ん中が活用語尾なら1語ではない」という関門を書いて
            # 測った。狙いどおり誤爆1件は消え、漢字塊の経路で
            # 書き換わる残り9件（時ッ層→実装・田安吾→単語など）も
            # そのまま通った。**しかし tests_mock が3件落ちた**:
            #
            #     該当あの範囲を  →  該当の範囲を   （混入かなの削除）
            #     見切れ魔訶。    →  見切れます。
            #
            # どちらも**混じり込んだかな自体が誤字**で、真ん中に
            # 活用語尾が立つ。`作った行`（正しい送り仮名）と
            # **字面では区別が付かない**——学び13
            # 「語頭のかなと送り仮名は字面では区別できない」そのもの。
            #
            # 誤爆1件と引き換えに直る力を3件失うので入れない。
            # `okurigana.py` の表で分けられないかも測った（同日）。
            # **これも駄目**。`該当あの範囲` の直前の漢字「当」は
            # `NEEDS_OKURIGANA['当'] = ('あ','あた')` を持つので、
            # 「送り仮名として正しい」と読めてしまう。
            # さらに形態素で見ても、
            #     作った行     → 作っ(動詞)/た(助動詞)/行(名詞)
            #     該当あの範囲 → 該当(名詞)/あの(連体詞)/範囲(名詞)
            # **どちらも文法的には通る**。学び13 のとおり、
            # 字面でも品詞でも送り仮名と混入かなは区別できない。
            # **次に試すなら、塊の外側（前後の文）を見る道**しかない。
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
            # --- 漢字塊のフォールバック（方針1-C / 1-D）---
            # 以前はここが `if not guess:` の中にあり、
            # `suggest_for_run` が当たると**一度も走らなかった**。
            # 実機では「田安吾」が 沢庵（実績2.8）に化けていたが、
            # この道を通せば たあんご → たんご → 単語（実績299）に
            # 届く（コメントに名指しで書いてあったのに、到達して
            # いなかった・2026-08-10）。
            # `continue` を戻り値に置き換えて、外から呼べるようにした。
            def _kanji_chunk_fallback():
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
                    combos_d = reading_combos_with_rank(
                        chunk, dict_index,
                        next_char=_next_char(line, k_end))
                    got_d = _resolve_reading_seq(
                        chunk, [r for r, _k in combos_d[:6]], store,
                        tokenize_fn, context_vec=context_vec,
                        surrounding=surrounding_d, require_context=True,
                        attest_text=line[:k_start] + ' ' + line[k_end:],
                        line_span=(line, k_start, k_end))
                    if got_d is None:
                        # --- 項目48-EQ（設計8）: 駄目なら譲る ---
                        # `目もち長` はここで終わっていた。組は
                        # `メモちょが` を作って門で落とし、塊を
                        # 抱えたまま `return None`。芯の再構築の道へ
                        # 順番が回らない。**入口を増やすだけ**にして
                        # 譲る（判断は増やさない）。
                        # `allow_exact=False`＝読みに開くだけの
                        # 置き換えは通さない（読める塊なので）。
                        _rl_d = [r for r, _k in combos_d[:6]]
                        got_d = _resolve_reading_list(
                            chunk, _rl_d, store,
                            tokenize_fn, context_vec=context_vec,
                            surrounding=surrounding_d, allow_exact=False,
                            dict_index=dict_index,
                            input_method=input_method)
                        if got_d is None or not fallthrough_rebuild_ok(
                                chunk, got_d[0], _rl_d, store, dict_index,
                                tokenize_fn):
                            return None
                        _trace('語の組',
                               f'{chunk!r} → 組では決まらなかったので'
                               f'芯の再構築へ譲った → {got_d[0]!r}')
                    new_surface, category = got_d
                    if len(new_surface) * 2 < len(chunk):
                        return None
                    # 漢字をかなに開くだけの置き換えは訂正ではない
                    # （押して→おして。上の混合塊と同じ関門）
                    if new_surface in (r for r, _k in combos_d):
                        _trace('語の組', f'{chunk!r} → {new_surface!r} は'
                                         f'読みに開くだけなので直さない')
                        return None
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
                            return None
                    _trace('語の組', f'{chunk!r} → {new_surface!r}')
                    return (new_surface, category)
                surrounding2 = _surrounding_content_words(
                    tokens, k_start, k_end,
                    nearby_words=nearby_words, recent_words=recent_words)
                combos_k = reading_combos_with_rank(
                    chunk, dict_index,
                    next_char=_next_char(line, k_end))
                got = _resolve_reading_list(
                    chunk, [r for r, _k in combos_k[:6]], store,
                    tokenize_fn, context_vec=context_vec,
                    surrounding=surrounding2, input_method=input_method)
                if got is None:
                    # 片側が実在語なら、残りだけを組み直す
                    # （野外文章→長い文章、簡易流力→簡易入力）
                    got = _resolve_kanji_split(
                        chunk, store, tokenize_fn, dict_index=dict_index,
                        context_vec=context_vec, surrounding=surrounding2,
                        input_method=input_method)
                if got is None:
                    return None
                new_surface, category = got
                if len(new_surface) * 2 < len(chunk):
                    return None
                if not _katakana_melt_ok(chunk, new_surface, store,
                                    tokenize_fn):
                    _trace('混合塊', f'{chunk!r} → {new_surface!r} は'
                                     f'使用実績が足りないので溶かさない')
                    return None
                _trace('混合塊', f'{chunk!r} → {new_surface!r}')
                return (new_surface, category)

            # `suggest_for_run` が当てた語が**一般的でない**なら、
            # そこで確定せずフォールバックとも比べる
            # （うにさんの指定「補正候補はより一般的なほうを優先」）。
            # フォールバックが何も出さなければ、元の結果を使う
            # （メモ帳・見切れます等、この道が拾っていた補正を守る）。
            _weak_guess = (guess is not None
                           and _usage_count(guess[2], store) < _USAGE_MIN)
            if not guess or _weak_guess:
                _got_fb = _kanji_chunk_fallback()
                if _got_fb is not None and _span_reads_in_sentence(
                        tokens, line, k_start, k_end) == 'partial' \
                        and not _naturalness.line_not_worse(
                            line, k_start, k_end, _got_fb[0], default=False):
                    # 文全体では読める塊（範囲が語を途中で切っている）。
                    #   取り/に/行く の `取りに行` → `とりない`
                    #   選択/し/直す の `選択し直` → `選択肢ない`
                    _trace('漢字塊', f'{chunk!r} → {_got_fb[0]!r} は'
                                     f'文全体では読める並びなので直さない')
                    _got_fb = None
                if _got_fb is not None:
                    new_surface, category = _got_fb
                    if _weak_guess:
                        _trace('漢字塊',
                               f'{chunk!r} → {guess[1]!r}(実績乏しい) より '
                               f'{new_surface!r} を採る')
                    replacements.append((k_start, k_end, new_surface,
                                         category))
                    kanji_taken.append((k_start, k_end))
                    continue
                if not guess:
                    # **設計27**（うにさんの指定・項目48-HS/48-HT）:
                    # どの道も決まらなかった塊が**異様**なら、
                    # ひらがなに開いて直しを試す。
                    #
                    # ただし**塊の端が本当の端でないなら決めない**
                    # （項目48-HU）。漢字の並びのすぐ隣にカタカナが
                    # 立っているとき、その境目は語の切れ目ではなく
                    # **一つの塊を途中で切った跡**である:
                    #
                    #   文字乳リュク  漢字の並びは `文字乳`
                    #                 本当の切れ目は `文字`＋`乳リュク`
                    #                 （にゅうりょく＝入力）
                    #
                    # ここで `文字乳` だけを開いて直すと `文字立ち`
                    # になり、**後ろの経路（混合塊）から塊を奪う**。
                    # 端がカタカナに接している塊は、設計27の持ち場
                    # ではない。
                    # **語を途中で切った範囲では決めない**（項目48-HU）。
                    # 既にある `_span_reads_in_sentence` と同じ話——
                    # `一度止まる` の漢字の並びは `一度止` で、
                    # `止まる` を送り仮名の手前で切っている。ここで
                    # 開いて直すと `一度とり|まると` になる
                    # （育った語彙で実測・2026-08-21）。
                    if _span_reads_in_sentence(
                            tokens, line, k_start, k_end) == 'partial':
                        _trace('異様', f'{chunk!r} → 範囲が語を途中で'
                                       f'切っている（文全体では読める）。'
                                       f'決めない（設計27・項目48-HU）')
                        continue
                    _odd_edge = _odd_chunk_edges_are_real(
                        line, k_start, k_end)
                    if not _odd_edge:
                        _trace('異様', f'{chunk!r} → 端がカタカナに'
                                       f'接しているので、この塊は'
                                       f'途中で切れている。決めない'
                                       f'（設計27・項目48-HU）')
                        continue
                    _odd_got = _reopen_odd_chunk(
                        chunk, store, tokenize_fn,
                        dict_index=dict_index, input_method=input_method)
                    if _odd_got is not None:
                        replacements.append((k_start, k_end,
                                             _odd_got[0], _odd_got[1]))
                        kanji_taken.append((k_start, k_end))
                    continue
            new_surface, category, _reading = guess
            if not _katakana_melt_ok(chunk, new_surface, store,
                                    tokenize_fn):
                _trace('漢字塊', f'{chunk!r} → {new_surface!r} は'
                                 f'使用実績が足りないので溶かさない')
                continue
            # 文全体では読める塊は、明らかに自然になるときだけ
            # （項目48-AH）。
            if _span_reads_in_sentence(
                    tokens, line, k_start, k_end) == 'partial' \
                    and not _naturalness.line_not_worse(
                        line, k_start, k_end, new_surface, default=False):
                _trace('漢字塊', f'{chunk!r} → {new_surface!r} は'
                                 f'文全体では読める並びなので直さない')
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
                for r, _k in reading_combos_with_rank(
                        chunk_n, dict_index,
                        next_char=_next_char(line, a_end)):
                    n_variant_readings.add(r)
            combos = []
            for cv_chunk in chunk_variants:
                combos.extend(reading_combos_with_rank(
                    cv_chunk, dict_index,
                    next_char=_next_char(line, a_end)))
            # 混入した英字が **QWERTY で n の隣**（b・m・h・j）なら、
            # ローマ字打ちで「ん」を打ち損ねた形も試す
            # （tango の n を b と押して 他b後。→ 他ん後 → たんご）。
            # かな配列の読み替え（b→こ → たこご）だけだと、初期状態
            # では再構築が距離だけで裁いて `タマゴ` に倒れた
            # （2026-08-16・実機の初期状態）。この読み替えは推測が
            # 1段深いので **exact_only**: 語彙にそのままある
            # （count>=2＝seed か使用実績）ときだけ採り、
            # 再構築へは渡さない。先頭に置くのは、確実な引き当てを
            # 距離頼みの再構築より上に置くため。
            n_slip_readings = []
            if len(stray_idx) == 1:
                _sc = chunk[stray_idx[0]]
                if 0xFF01 <= ord(_sc) <= 0xFF5E:
                    _sc = chr(ord(_sc) - 0xFEE0)
                _sc = _sc.lower()
                if _sc == 'n' or ('a' <= _sc <= 'z'
                                  and _qwerty_adjacent(_sc, 'n')):
                    _p = stray_idx[0]
                    _chunk_nn = chunk[:_p] + 'ん' + chunk[_p + 1:]
                    n_slip_readings = [
                        r for r, _k in reading_combos_with_rank(
                            _chunk_nn, dict_index,
                            next_char=_next_char(line, a_end))[:3]]
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
                drop_combos = reading_combos_with_rank(
                    chunk_wo, dict_index,
                    next_char=_next_char(line, a_end))
            try_readings = (n_slip_readings
                            + [r for r, _k in combos[:6]]
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
                short_ok=n_variant_readings,
                exact_only=frozenset(n_slip_readings),
                input_method=input_method)
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
        #
        # **ここも「使ったことがあるか」ではなく「在る語か」で見る**
        # （項目48-EO・設計6）。`はちぶんめ`（八分目・count 1）は
        # ここを素通りしたあと、**切れ端の `ちぶんめ` が `ちんみ`
        # （珍味）に化けていた**。連続まるごとが在る語なら、
        # その中を切り分けて探すこと自体が要らない。
        if known_or_bundled(run, store, dict_index):
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

        # --- 設計22: **畳むと在る語になる連打だけ**を先に畳む
        #     （項目48-HI・2026-08-20・Fable）。
        #
        # 初期状態の化け32件のうち**10件が「重複打鍵の畳み方の
        # 選び違い」**だった（probe_bake で実測）:
        #     もぐぐらに → 窓が「ぐぐらに」に切られ、芯 ぐぐら が
        #     ぐらぐら に化ける（正解 もぐら は窓の外の も ごと
        #     見ないと出ない）。
        # 窓に切る**前**の連続全体で、隣り合う同じ文字を1つ畳んで
        # みて、**畳んだ結果（末尾の助詞を除く）が在る語**なら、
        # それを採る。証拠は連打（0.6）そのもので、探索より強い。
        #
        # 門（狭く保つこと）:
        #   - 連続そのものが在る語なら上の known_or_bundled で
        #     既に触らない（ここ・たたみ・すすむ は来ない）
        #   - **畳んだ語がただ1つ**のときだけ（2つ以上は決め手なし）
        #   - 語は3文字以上・count は 48-HH と同じ若さ分岐
        #   - 的 `ににして` のような「畳むと機能語の並びになる」形は
        #     **対象外のまま**（語にならないので当たらない。あれは
        #     別の証拠が要る——記録 48-HI に書いた）
        _c22 = _fold_repeat_to_word(run, store)
        if _c22 is not None:
            _fold, _body = _c22
            _trace('かな連続', f'{run!r} → {_fold!r} に畳む'
                             f'（連打・畳むと {_body!r} が在る語・'
                             f'項目48-HI）')
            replacements.append((run_start, run_end, _fold, 'かな入力'))
            hiragana_taken.append((run_start, run_end))
            continue
        _c23 = None
        if not _known_head_plus_functional(run, store):
            _c23 = _swap_to_word(run, store)
        if _c23 is not None:
            _swp, _body = _c23
            _trace('かな連続', f'{run!r} → {_swp!r} に戻す'
                             f'（入れ替え・戻すと {_body!r} が在る語・'
                             f'項目48-HJ）')
            replacements.append((run_start, run_end, _swp, 'かな入力'))
            hiragana_taken.append((run_start, run_end))
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
        # **先頭を助詞と見なして切るのは、直前に「語」があるときだけ**
        # （項目48-GJ）。助詞は前の語にくっつくものなので、
        # **文の頭・括弧の中・読点の直後**には立てない。
        #
        #     でんせせつ、それから…（正解 でんせつ）
        #       `で` を助詞と見て切ると 範囲は `んせせつ`
        #       → `しんせつ` に直り、**でしんせつ** になる
        #     「でんせせつ」と書きました。 も同じ（直前は `「`）
        #     でんせせつを確認しました。   は連続が長いので通っていた
        #
        # 同じ語が**文の形しだいで**化けていた。項目48-GH（窓の頭）・
        # 項目48-DY（芯の頭）と同じ話が、この道にもあった。
        _head_cuttable = (run_start > 0
                          and is_japanese_word_char(line[run_start - 1]))
        candidates = []
        for cut_head in (0, 1):
            for cut_tail in (0, 1):
                s = run_start + cut_head
                e = run_end - cut_tail
                if e - s < 4:
                    continue
                if cut_head and not _head_cuttable:
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

            # --- ここから、**芯の再構築に既にある門**を同じに掛ける
            #     （項目48-GZ・門の掛け忘れ5例目）---
            #
            # `1つにする。` → **`1つくる。`** が化けていた。
            # 記録はたった2行で、分解も窓も芯も走っていない。
            #
            #     行頭 ／ 半角英数の直後 ／ 記号（、。）の直後 ／
            #     空白の直後 → かな連続が `つにする` そのものになり、
            #     **この道（独立したひらがな連続）に入る**
            #     ひらがな・漢字・全角数字の直後 → 連続がそれを含む形に
            #     なり、**分解の道**へ行って門で止まる
            #
            # 同じ `つにする` が、直前の1文字で通ったり止まったり
            # していた。**項目48-GI・48-FZ とまったく同じ話**
            # （門は経路ごとに掛け直す・学び22）。
            #
            # 新しい考えは足さない。`rebuild_window_core` が芯に
            # 掛けている門を、そのままの順で並べる。
            # 範囲の後ろに残っている部分（`_rest_after`）は、
            # 芯の側の `window[c_e:]` にあたる。
            _rest_after = line[end:run_end]

            # **末尾の機能語を剥がした残りが1文字なら触らない**
            # （項目48-DI と同じ門）。`つにする` ＝ `つ`（1文字）＋
            # `にする`（機能語）。断片は偶然どれかの語に一致しやすい。
            _tail_len = _trailing_functional_len(target)
            if _tail_len and len(target) - _tail_len <= 1:
                _trace('かな連続', f'{target!r} → 機能語を剥がすと1文字しか'
                                 f'残らないので対象外')
                continue
            # **`を` を含む範囲は触らない**（項目48-CL・48-DO と同じ門）。
            # `を` は現代語では助詞にしかならず、語の読みに現れない。
            if 'を' in target:
                _trace('かな連続', f'{target!r} → 助詞「を」を含むので対象外')
                continue
            # **終わりが機能語の途中で切れている**（同じ門）。
            if _rest_after:
                _joined = False
                for _k in range(1, min(3, len(target)) + 1):
                    _frag = target[-_k:] + _rest_after
                    if any(len(t) > _k and _frag.startswith(t)
                           for t in AUXILIARY_TAILS):
                        _joined = True
                        break
                if _joined:
                    _trace('かな連続', f'{target!r} → 終わりが機能語の'
                                     f'途中で切れているので対象外')
                    continue
            # **擬態語（〜りと）**（同じ門）。
            if (_rest_after[:1] == 'と' and target.endswith('り')
                    and len(target) <= 4):
                _trace('かな連続', f'{target!r} → 擬態語（〜りと）なので対象外')
                continue
            # **語頭・語末に立たない文字**（同じ門）。ただし
            # **切った側にだけ掛ける**。
            #
            # 芯の側でこの門が言っているのは「語は っ・ん・ー・小書き
            # かな では始まらないのだから、そこで始まる芯は
            # **切り出しがずれている**」ということ。**切っていない端に
            # は、その前提が立たない。** この道の範囲は多くの場合
            # 連続そのもので、頭の `っ` `ん` `ゃ` は切り損ねではなく
            # **語頭の入れ替え（打ち間違いそのもの）**である:
            #
            #     っぴたり（正解 ぴったり）  んかどう（正解 かんどう）
            #     ゃしでん（正解 しゃでん）  ょきうき（正解 きょうき）
            #
            # 実測（うにさんの語彙・型8種・600語）: 端を見ずに掛けると
            # **順序違い(語頭) が 13件 直らなくなった**（化けは1件減）。
            # **門の言い分が立つのは、実際に切った端だけ。**
            if start > run_start and target[0] in 'っんーゃゅょぁぃぅぇぉ':
                _trace('かな連続', f'{target!r} → 頭を切った結果、語頭に'
                                 f'立たない文字で始まるので対象外')
                continue
            if end < run_end and target[-1] in 'っー':
                _trace('かな連続', f'{target!r} → 終わりを切った結果、語末に'
                                 f'立たない文字で終わるので対象外')
                continue
            # --- 掛け直しはここまで ---

            # そのまま正しい読みなら触らない
            #
            # **ここは「使ったことがあるか」ではなく「在る語か」で
            # 見る**（項目48-EO・設計6・うにさん指定 (d)）。
            # `count >= 2` だけだと、辞書から取り込んだだけの語
            # （初期状態では 15,888語＝97.7%）が全部「知らない」に
            # なり、使われている語へ引きずり込まれる。実測:
            #
            #     もちごめ（糯米・count 1）  → **もちこむ**（持ち込む・7）
            #     ひとりじめ（一人占め・1）  → **ひともじ**（一文字・11）
            #     はちぶんめ（八分目・1）    → **はちんみ**
            #     かんむり（語彙に無い）      → **かんり**（管理・1,181）
            #
            # どれも**世の中に在る正しい語**で、壊れてはいない。
            if known_or_bundled(target, store, dict_index):
                continue
            # 語彙に無くても、正しい日本語として読めるなら触らない
            if _looks_like_valid_japanese(target, tokenize_fn):
                continue

            # **文全体の解析でも見る**（項目48-AH・学び22）。
            # 範囲が語を途中で切っていないか。説明は
            # `_span_reads_in_sentence` に書いた。
            _span_cuts_word = _span_reads_in_sentence(
                tokens, line, start, end) == 'partial'

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
                # 文全体では読めている範囲は、明らかに自然になる
                # ときだけ直す（項目48-AH）。
                if _span_cuts_word and not \
                        _naturalness.line_not_worse(
                            line, start, end, cand_reading, default=False):
                    continue
                # **育っていない語彙のときだけ、「辞書から取り込んだ
                # だけの語」（count 1）も直し先にする**（項目48-HH・
                # 項目48-CX と同じ緩め。芯の再構築には掛かっていたのに
                # この道には無く、初期状態では**直し先が種の375語しか
                # 無かった**。たままご→たんご（正解 たまご）のように、
                # 空いた席へ**種の語が吸い込む**化けの型を作っていた）。
                # 育った語彙では今までどおり count>=2（48-CX の実測:
                # 育った側に掛けると悪くなる）。
                from vocabulary import store_is_young as _sy
                _min_c = 1 if _sy(store) else 2
                cand_entries = [e for e in store.lookup(cand_reading)
                                if e['count'] >= _min_c]
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
        # **この道にも、隣のキーの門を通す**（項目48-GI）。
        #
        # 項目48-FX で入れた「1文字違いは隣のキーのときだけ」は
        # `rebuild_window_core`（芯の再構築）にしか掛かって
        # いなかった。**ひらがな連続を直すこの道は素通り**で、
        # 同じ語が文の形しだいで通ったり止まったりしていた:
        #
        #     こかかんがありました。   → 直さない（芯の門で止まる）
        #     こかかん、それから…     → **こうかん**（ここが通した）
        #     「こかかん」と書きました。 → **こうかん**（同上）
        #
        # `か → う` はローマ字でも `ka → u` で隣ではない。
        # **項目48-FZ とまったく同じ話**（門は経路ごとに掛け直す）。
        if input_method and not _adj_ok_one_char(line[start:end],
                                                 cand_reading,
                                                 input_method):
            _trace('かな連続', f'{line[start:end]!r} → {cand_reading!r} は'
                             f'1文字違うだけで、その違いは隣のキーでは'
                             f'説明が付かない（{input_method}）ので採らない')
            continue
        _trace('かな連続', f'{line[start:end]!r} → {cand_reading!r} に'
                         f'直す（ひらがな連続の道）')
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
        # **畳むと在る語になる連打**（設計22・項目48-HI）。
        # 窓に切る前に連続全体で見る——窓が「ぐぐらに」に切られると
        # 正解 もぐら は窓の外の「も」ごと見ないと出ない。
        # 連続そのものが在る語は下の known_or_bundled 系の守りの
        # 前に来るので、ここで**先に**同じ確認をする。
        # 守る語（それから 等）だけは入口で外す。機能語だけ・
        # 助動詞だけ・既知語＋機能語の門は**ここには掛けない**——
        # よかかっ・わるくくない・おばばけ のような的まで塞ぎ、
        # 初期40件・育ち80件の直りを失った（2026-08-20 実測）。
        # 畳み・戻しは「結果が在る語」を要求するので、それで足りる。
        if (not known_or_bundled(run, store, dict_index)
                and not is_protected_word(run)):
            _c22 = _fold_repeat_to_word(run, store)
            if _c22 is not None:
                _fold, _body = _c22
                _trace('かな連続', f'{run!r} → {_fold!r} に畳む'
                                 f'（連打・畳むと {_body!r} が在る語・'
                                 f'項目48-HI）')
                replacements.append((run_start, run_end, _fold,
                                     'かな入力'))
                taken_all.append((run_start, run_end))
                continue
            # **戻し（入れ替え）には機能語の門を掛ける**（畳みには
            # 掛けない）。機能語の連なりは入れ替えても機能語の並びに
            # 見えることが多く、実機メモで `ではない → ではいな`・
            # `がなければ → ながければ` と壊れた（2026-08-20 実測）。
            # 畳みは同じ門で よかかっ・わるくくない の的まで塞いだ
            # ので、掛けるのは戻し側だけ。
            _c23 = None
            if (not _is_all_functional(run)
                    and not _is_all_auxiliary(run)
                    and not _known_head_plus_functional(run, store)):
                _c23 = _swap_to_word(
                    run, store,
                    after_kanji=(run_start > 0
                                 and is_kanji(line[run_start - 1])))
            if _c23 is not None:
                _swp, _body = _c23
                _trace('かな連続', f'{run!r} → {_swp!r} に戻す'
                                 f'（入れ替え・戻すと {_body!r} が在る語・'
                                 f'項目48-HJ）')
                replacements.append((run_start, run_end, _swp,
                                     'かな入力'))
                taken_all.append((run_start, run_end))
                continue
        # 濁点のキーの隣を押した形（とせらっぐ → ドラッグ）。
        # **並び全体**を読み替えるので、窓に切り分ける前に見る。
        # 切り分けたあとでは「せらっぐ」だけが直り、頭の「と」が
        # 余ってしまう（実機で「とどらっぐ」・2026-08-10）。
        _dak = dakuten_typo_fix(run, store)
        if _dak:
            _trace('かな連続', f'{run!r} → 濁点のキーの隣を押した形'
                               f'として {_dak!r} に直す')
            replacements.append((run_start, run_end, _dak, 'かな入力'))
            taken_all.append((run_start, run_end))
            continue
        # 窓の切り出しは、形態素解析の分割から見る token_windows を
        # 第一候補にする（実機の janome の「短い断片が連続する」
        # 振る舞いに基づく。語彙の規模に左右されない）。
        # 解析が窓を出さないときだけ、語彙ベースの explain_cores を
        # 控えとして使う。
        run_after_kanji = (run_start > 0 and is_kanji(line[run_start - 1]))
        # **かな連続の最後にある助詞は動かさない**（項目48-DJ）。
        # この経路は2本（従来の探索・芯の再構築）あるので、
        # **両方に同じ印を渡す**（片方だけだと迂回される・学び22）。
        run_keep_tail = run_tail_particle(line, run_start, run_end)
        if run_keep_tail:
            _trace('かな連続', f'{run!r} → 末尾の {run_keep_tail!r} は'
                             f'助詞なので動かさない')
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
            # 文全体の解析で、この範囲がすべて辞書の語として
            # 読めているなら壊れていない（_tokens_all_known_in_span）。
            # 窓だけを取り出して解析し直すと前後を失い、
            # 「確定したのち」の「したのち」が「したまち」に
            # 化けるような事故が起きる（実機・2026-08-10）。
            #
            # **窓の頭が語の途中でもよい**（partial_start・2026-08-11）。
            # 頭を切れ目に合わせろという条件のせいで、`変わらない`の
            # `らない`・`届くたびに`の`くたび`・`下ごしらえ`の
            # `ごしらえ` がこの守りを素通りし、それぞれ `きない`
            # `くたびれ` `こしらえ` に化けていた。
            # **閉じる門ではなく、高い敷居にする**（項目48-AE）。
            # 「辞書で読める＝触らない」だと、`たんあご` のように
            # **短い既知語に分解できてしまう壊れた並び**が
            # 全部素通りする。読める並びは正しいことのほうが
            # 多いので門は残すが、**明らかに自然になる直しなら通す**
            # （判定は rebuild_window_core の中）。
            # **お尻も緩める**（partial_end・項目48-AH）。
            # 語の途中で終わる窓を「読めない」と返していたため、
            # `できるほ`（できる/ほか の途中）を直しに行っていた。
            window_readable = _tokens_all_known_in_span(
                tokens, a, b, partial_start=True, partial_end=True,
                after_kanji=(a > 0 and is_kanji(line[a - 1])))
            if window_readable:
                _trace('窓', f'{window!r} → 文全体の解析では読める。'
                             f'明らかに自然になる直しだけ通す')
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
                # ここも敷居にする（項目48-AE）。
                window_readable = True
                _trace('窓', f'{window!r} → 単体でも読める。'
                             f'明らかに自然になる直しだけ通す')
            chosen = None
            # **窓が `を` を跨いでいるなら、従来の探索も掛けない**
            # （項目48-DO）。芯の再構築側と同じ理由。片方だけに
            # 置くと、そちらを迂回される（学び22）。
            if 'を' in window:
                _trace('窓', f'{window!r} → 助詞「を」を含むので'
                             f'従来の探索は掛けない')
            found = [] if (edge_word or 'を' in window) else find_readings(
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
                    # **隣のキーの門は、ここには掛けない**（項目48-HK・
                    # 48-HF を取り消した）。48-HF で掛けたら、実機の的
                    #     つあがり → つながり（あ→な・隣ではない）
                    # を失った（probe_fresh の的148行で 54→53・
                    # 2026-08-20 実測）。この道は 2位との差 0.4・
                    # 使用実績 count>=2・読める窓の敷居が既に立って
                    # いて、隣のキー以外の1文字置換（脱字がかなに
                    # 化けた形）を拾うのが役目。48-GZ-表の※4は
                    # 「掛けない」に根拠がついた。
                    chosen = r0
            if chosen is None and input_method == 'romaji':
                # ローマ字入力者なら、QWERTY の隣接キーとして照合し直す
                chosen = romaji_window_match(window, store)
            # **直し先が固有名詞なら使わない**（項目48-CS）。
            # 語彙に紛れ込んだ地名・人名へ引きずり込まれるのを塞ぐ。
            # **末尾の助詞を食う直しは採らない**（項目48-DJ）。
            # 窓がかな連続の終わりまで届いているとき、その末尾は
            # 「文が続く直前の助詞」である。
            #
            #     もじにゅうりょが必要です。
            #       窓 `もじにゅうりょが` → `もじにゅうりょく`
            #       → **が が消える**
            #
            # ここで見送ると、下の芯の再構築が助詞を残したまま
            # 直す（芯 `もじにゅうりょ` → `もじにゅうりょく`）。
            if (chosen and run_keep_tail and b >= run_end
                    and not chosen.endswith(run_keep_tail)):
                _trace('窓', f'{window!r} → {chosen!r} は末尾の助詞 '
                             f'{run_keep_tail!r} を食うので採らない')
                chosen = None
            if chosen and chosen != window:
                _surfs = [e.get('surface') for e in store.lookup(chosen)]
                if _surfs and all(_is_whole_proper_noun(x, tokenize_fn)
                                  for x in _surfs if x):
                    _trace('窓', f'{window!r} → {chosen!r}（{_surfs}）は'
                                 f'固有名詞なので直し先にしない')
                    chosen = None
            if chosen and chosen != window and not (
                    a > 0 and chosen == line[a - 1] + window):
                # ひらがなで打たれたものはひらがなのまま直す（方針どおり）。
                # ただし「直前の文字を足しただけ」の候補は、窓の切り出しが
                # 語の途中から始まっただけで、文字はもう書かれている
                # （「通常のひらがな」の窓「らがな」に「ひらがな」を
                #   当てると ひひらがな になる。実機で発生）。
                #
                # 読める窓は、明らかに自然になるときだけ（項目48-AE）。
                # **この道にも同じ敷居を置くこと。** 片方だけに
                # 置くと、そちらを迂回して素通りする（学び22）。
                if window_readable and not \
                        _naturalness.worth_touching_readable(
                            window, chosen, default=False):
                    _trace('窓', f'{window!r} → {chosen!r} は読める並びを'
                                 f'覆すほど自然にならないので直さない')
                else:
                    _trace('窓', f'{window!r} → 従来の探索で '
                                 f'{chosen!r} に直す')
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
                after_kanji=(a > 0 and is_kanji(line[a - 1])),
                readable_hint=window_readable,
                # **窓はこの直前で連続の終わりまで伸ばしてある**
                # （window_ext = line[a:max(b, run_end)]）。伸ばした
                # 窓は必ず連続の末尾（助詞）を含むので、`b` が
                # 連続の終わりに届いているかで場合分けしてはいけない。
                # 場合分けしていたせいで、元の窓が短いときだけ
                # 48-DJ の門（末尾の助詞を食う候補を外す）が外れ、
                #     じんしに行きます。 → **じんしゅ行きます。**
                # と助詞ごと食っていた（項目48-HG・2026-08-20 実測。
                # 初期状態の readcheck で同型の化けが4件）。
                keep_tail=run_keep_tail,
                dict_index=dict_index,
                # **隣接の判定は入力方式で変わる**（項目48-FX）。
                input_method=input_method,
                # **並記**（項目48-EW・設計14）。窓の外の同じ行と、
                # 近くの行に**文字どおり書かれている**もの。
                attest_text=(line[:a] + ' ' + line[b:] + ' '
                             + ' '.join(nearby_words or ())))
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
                                    surrounding_words=surrounding,
                                    dict_index=dict_index,
                                    attest_text=line)
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

    # ------------------------------------------------------------
    # カタカナ語・英単語の誤字（loanword.py・2026-08-10）
    # ------------------------------------------------------------
    # これまでカタカナ語は原則として触らず、英単語には経路すら
    # 無かった。うにさんの指定で、長い外来語・英単語の打ち間違いも
    # 直すことになった。判断は loanword.py の中だけで行い、
    # ここは「返ってきたら置き換える」だけにする（判断経路を
    # 増やさないという設計方針）。
    #
    # 既に他の経路が直すと決めた範囲には手を出さない。
    _loan_taken = [(_s, _e) for _s, _e, _n, _c in replacements]
    # **かなを漢字に直した範囲**（項目48-FU）。
    # 最終検査の「長さが2文字以上ずれたら採らない」から外す。
    # `きょうちょう`(6) → `強調`(2) は**縮むのが正しい形**で、
    # 半角をかなに戻した箇所（`halfwidth_taken`）と同じ理由。
    _shift_taken = []

    def _loan_overlaps(a, b):
        return any(not (b <= s0 or a >= e0) for s0, e0 in _loan_taken)

    try:
        import loanword as _LW
    except Exception:
        _LW = None
    if _LW is not None:
        # --- カタカナの並び（プセネタリウム → プラネタリウム）---
        for k_s, k_e, k_run in _LW.find_katakana_runs(line):
            if _loan_overlaps(k_s, k_e):
                continue
            # 形態素解析が「辞書にある語」だけで説明できる並びは、
            # 正しく書けている。1語として読めた場合はもちろん、
            # **複合語として複数の既知語に割れた場合も**触らない。
            # これが無いと、実機のメモで
            #   ショートカットキー → ショートカット
            #   タブショートカット → ショートカット
            # のように、正しい複合語が縮められた（2026-08-10）。
            if _span_is_known_single_word(tokens, k_s, k_e):
                continue
            _parts = [t[0] for t in (tokens or ())
                      if t[3] >= k_s and t[4] <= k_e]
            if (''.join(_parts) == k_run
                    and _LW.is_known_compound(_parts, store)):
                continue
            span_e = k_e
            fixed = None
            # 末尾に1文字紛れた形（プラネタリウ［）を先に試す。
            # ただし、その1文字を除いた部分が既に正しい語なら
            # 触らない（「（東京上野キャンパス）」の閉じ括弧を
            # 消してしまった件・2026-08-10）。
            if (k_e < len(line) and _LW.is_stray(line[k_e])
                    and not _LW.is_known_katakana(k_run, store)):
                fixed = _LW.fix_katakana_word(k_run + line[k_e], store)
                if fixed:
                    span_e = k_e + 1
            if not fixed:
                span_e = k_e
                fixed = _LW.fix_katakana_word(k_run, store)
            # 直すと決めたあとで、いちばん重い関門を通す。
            # 形態素解析の辞書だけで元の並びの説明が付くなら、
            # 利用者は実在する語を書いたということなので手を引く
            # （検証レポート 2-C。コールバック→オールバック 等）。
            # ここに置くのは、字句解析を1〜2回余分に呼ぶため。
            # 直す候補が出た並びは稀なので、1000行のタブでも
            # 切り替えの速さ（項目48-m）に響かない。
            # **直後が地名の接尾なら、固有名詞なので触らない**
            # （項目48-CJ）。漢字の塊には同じ守り（駅県市区町村港）が
            # あったが、カタカナ語の経路には無かった。
            #
            #     オダッシュ山  → ダッシュ山
            #     マジョルカ島  → マジョリカ島
            #
            # どちらも実在の地名で、たまたま語彙の別語（ダッシュ・
            # マジョリカ）と距離が近いだけだった。よく知られた地名
            # （エベレスト山・ハワイ島・ミシシッピ川）は元から
            # 直らないので、**穴は「珍しい地名」にだけ空いていた**。
            #
            # うにさんのジャンル（ゲーム・実況）では
            # **カタカナ＋山／島**の地名がよく出るので塞ぐ。
            # 実測: 材料10,044行のカタカナの並び2,328件のうち、
            # 直後がこの接尾のものは**0件**。失う直しは無い。
            if fixed and span_e < len(line) \
                    and line[span_e] in _PLACE_SUFFIX:
                _trace('外来語', f'{line[k_s:span_e]!r} → '
                                 f'直後が地名の接尾なので触らない')
                fixed = None
            if fixed and _LW.dictionary_explains(line[k_s:span_e],
                                                 tokenize_fn):
                _trace('外来語', f'{line[k_s:span_e]!r} → '
                                 f'辞書で説明が付くので触らない')
                fixed = None
            if fixed:
                _trace('外来語', f'{line[k_s:span_e]!r} → {fixed!r}')
                replacements.append((k_s, span_e, fixed, '外来語'))
                _loan_taken.append((k_s, span_e))

        # --- ひらがなで書かれた外来語（ぷらねたりうむ → カタカナ）---
        # 「ひらがなで打たれたものはひらがなのまま」の例外。
        # 助詞が後ろに付いた形（ぷらねたりうむに）でも拾えるよう、
        # 末尾の助詞を1〜2文字まで剥がして試す。
        _tail_particles = set('はがをにでともへやかねのよねなら、。')
        # **前後に漢字があっても拾う**（項目48-DG）。
        # 既定の `find_hiragana_runs` は「前後に漢字・カタカナが
        # 隣接する連続」を外す（送り仮名を壊さないため）。だが
        # ここは**ひらがなで書いた外来語をカタカナに直す**道なので、
        # その門に掛かると
        #
        #     ぷらねたりうむ          → プラネタリウム  （直る）
        #     ぷらねたりうむに行きます → **直らない**
        #
        # という食い違いになる。**単体でしか直らない。**
        # うにさんが書くのは後者のほうなので、実質ほとんど効いて
        # いなかった（2026-08-14 に実測）。
        #
        # 送り仮名を巻き込む危険は、この道では小さい:
        #   - 5文字以上の連続だけを見る
        #   - 末尾の助詞を1〜2文字剥がして試す
        #   - `katakana_for_hiragana` は**カタカナ語として知って
        #     いる読み**にしか直さない（送り仮名の並びは通らない）
        for h_s, h_e, h_run in find_hiragana_runs(line, min_len=5,
                                                  allow_adjacent_kanji=True):
            if _loan_overlaps(h_s, h_e):
                continue
            # **後ろに何が続いていても、頭から探す**（項目48-DL）。
            #
            # 末尾を1〜2文字だけ剥がす形にしていたので、
            # 助詞のあとに言葉が続くと届かなかった:
            #
            #     ぷらねたりうむに行きます。 → 直る（に を1文字剥がす）
            #     ぷらねたりうむをみます。   → **直らない**
            #                                  （をみます が4文字）
            #
            # うにさんが書くのは文なので、後ろに何か続くほうが
            # 普通である。**長いほうから順に、頭の何文字が
            # カタカナ語かを見る。**
            #
            # 勝手に切らない造りになっている:
            #   - `katakana_for_hiragana` は**カタカナでしか
            #     書かない語**にしか直さない（5文字以上・
            #     使用2回以上・漢字やひらがなの表記があれば断る）
            #   - 頭から数えるので、文の途中の語は拾わない
            # **末尾の助詞を剥がしたところまでは「中身」**。
            # そこまでの切り方はいままでどおりで、壊れた形かどうかを
            # 疑う必要はない。**それより内側を切るときだけ**疑う。
            #
            # ここを分けないと `こんぴゅーたに` が
            # 「`こんぴゅーたー`（コンピューター）を1つ壊した形」に
            # 見えて、ふつうの直しまで止まる（2026-08-15 に踏んだ）。
            _tail_n = _trailing_particle_len(h_run)
            _inner = len(h_run) - (_tail_n if len(h_run) - _tail_n >= 4
                                   else 0)
            _broken_whole = None      # 遅らせて調べる（内側を切るときだけ）
            for _len in range(len(h_run), _LW.MIN_LENGTH - 1, -1):
                _body = h_run[:_len]
                kata = _LW.katakana_for_hiragana(_body, store)
                if not kata:
                    continue
                _rest = h_run[_len:]
                if _rest and _len < _inner:
                    if _broken_whole is None:
                        _broken_whole = _looks_like_broken_katakana(
                            h_run, store)
                    if _broken_whole:
                        break
                # **切れ目が語の途中でないこと。** 残りが
                # 「助詞・送り仮名だけ」で説明が付くなら、そこは
                # 語の切れ目である。全部使い切るなら文句なし。
                if _rest and not _rest_is_ordinary_japanese(
                        _rest, tokenize_fn):
                    _trace('外来語', f'{_body!r} → {kata!r} にしたいが、'
                                     f'残り {_rest!r} が語の途中に見える')
                    continue
                _trace('外来語', f'{_body!r} → {kata!r}（カタカナへ）')
                replacements.append((h_s, h_s + _len, kata, '外来語'))
                _loan_taken.append((h_s, h_s + _len))
                break

        # --- 漢字にしたかったのに、かなのまま残った語（項目48-EA）---
        #
        # うにさんの指定（2026-08-16）:
        #
        # > **漢字変換したかったかどうかの意図を察します。**
        # > 誤入力によって IME が一部を漢字変換できずに平仮名のまま
        # > 通すケースがあります。その場合は**漢字が一部入っていたり
        # > する**ので、それを判定して**漢字変換したかったが平仮名に
        # > なったもの**を見分けます。
        #
        # 見分ける印は「**ひらがなの連続が漢字と地続きである**」こと。
        # IME は文節ごとに変換するので、一部だけ変換に失敗した形は
        # 漢字とかなが隣り合う:
        #
        #     たんごの繋がり     `たんごの` の直後が 繋 → 変換の途中
        #     かな打ちでのほせい  `ちでのほせい` の直前が 打 → 同上
        #     かくごっ           前後に漢字が無い → **本人がかなで
        #                        書いた**ので触らない
        #
        # 「ひらがなで打たれたものはひらがなのまま直す」の例外。
        # 外来語（ぷらねたりうむ→プラネタリウム・項目48-DL）に
        # 続く2つめの例外で、守りの形も同じにしてある。
        #
        # **なぜ自然さで測るのか。** かな同士で比べると符号が逆に出る
        # （2026-08-16 の実測）:
        #
        #     たんあごの繋がり → たんごの繋がり   **−10,528**（棄却）
        #     たんあごの繋がり → 単語の繋がり     **+5,640**（通る）
        #     たんごの繋がり   → 単語の繋がり     **+13,831**
        #
        # janome は裸のかな `たんご` を「たん＋ご（接頭詞）」と読んで
        # 元より高くつくと判定する。**比べる相手を漢字にして初めて
        # 正しい向きになる。**
        #
        # 守り（実機メモ1,457行で測って決めた・下の数字は当たった数）:
        #   守り無し ....................... 14件（うち9件は引用を壊す）
        #   ＋漢字と地続き .................. 4件（うち3件は引用を壊す）
        #   ＋誤字の見本らしい行を外す ...... **1件**（望みどおりの1件）
        if _KANA_TO_KANJI and not _LOOKS_LIKE_EXAMPLE.search(line):
            for h_s, h_e, h_run in find_hiragana_runs(
                    line, min_len=_K2K_MIN_LEN, allow_adjacent_kanji=True):
                if _loan_overlaps(h_s, h_e):
                    continue
                # **漢字と地続きか。** ここが「変換したかった」の印。
                if not ((h_s > 0 and is_kanji(line[h_s - 1]))
                        or (h_e < len(line) and is_kanji(line[h_e]))):
                    continue
                for _len in range(len(h_run), _K2K_MIN_LEN - 1, -1):
                    _body = h_run[:_len]
                    _kanji = _kanji_surface_for_reading(_body, store)
                    if not _kanji:
                        continue
                    _after = line[:h_s] + _kanji + line[h_s + _len:]
                    # **その漢字表記が、近くに実際に書かれていること**
                    # （2026-08-16。下の実測から。並記の関門）。
                    #
                    # 自然さだけで通すと、**打ち間違いでたまたま別の語の
                    # 読みになった並びを、漢字にして固めてしまう**。
                    # readcheck（型8種600語×4）で化けが 114 → **142**:
                    #
                    #     かふん → 花粉 （正解 ふかん）
                    #     じょし → 助詞 （正解 じしょ）
                    #     ごういせ → 合意せ（正解 ごうせい・語ですらない）
                    #
                    # **直った数は1件も増えていない**（1013 のまま）。
                    # かなのままなら「変だ」と目で分かるが、漢字にすると
                    # **書いたつもりの形**に見える。「直らない」を
                    # 「自信のある誤り」に変えるのはいちばん悪い。
                    #
                    # 実績の回数では分けられない（花粉681・単語1317・
                    # 補正1399・作動60）。**5点で敷居を決めない**（学び50）。
                    # 共起の支持でも分けられなかった（142→140 どまり。
                    # 共起はメモ全体から育つので、測定用の型の語とも
                    # 薄く繋がってしまう）。
                    #
                    # 分かれるのは「**その漢字が近くに書いてあるか**」。
                    # `単語` はすぐ上の行に書いてある。`花粉` は測定用の
                    # 型のどこにも無い。項目38・1-F と同じ関門で、
                    # このアプリのよりどころ（「メモのどこかに正しく
                    # 書いてある語」）そのもの。
                    if (_kanji not in line
                            and _kanji not in (nearby_words or ())
                            and _kanji not in (recent_words or ())):
                        _trace('かな→漢字',
                               f'{_body!r} → {_kanji!r} は近くに'
                               f'書かれていないので触らない')
                        break
                    # 読める並びと同じ敷居（項目48-AE）。
                    # janome が無ければ「意見なし」→触らない。
                    if not _naturalness.worth_touching_readable(
                            line, _after, default=False):
                        _trace('かな→漢字',
                               f'{_body!r} → {_kanji!r} は自然にならない'
                               f'（差 {_naturalness.gain(line, _after)}）')
                        break
                    _trace('かな→漢字', f'{_body!r} → {_kanji!r}'
                                        f'（漢字と地続き）')
                    replacements.append(
                        (h_s, h_s + _len, _kanji, 'かな入力'))
                    _loan_taken.append((h_s, h_s + _len))
                    break

        # --- シフトを押し損ねた拗音を、漢字にして戻す（項目48-FU）---
        #
        # うにさんの指定: `きようちよう ⇒ 強調`
        #
        # 見分けかたと門は `_shift_lost_kanji` に全部書いてある。
        # ここは「切り出す範囲を決めて、返ってきたら置き換える」だけ。
        #
        # **範囲の取りかた**は、外来語・かな→漢字の道と同じ形にする:
        # ひらがなの連続の中から、
        #   - 前は**機能語だけ**で説明が付く（`これは` `そのあと`）
        #   - 後ろは**ふつうの日本語の続き**に見える
        #     （`したいです` `をします`。`_rest_is_ordinary_japanese`）
        # という切れ目でだけ切る。**語の途中では切らない。**
        #
        # **誤字の見本らしい行は触らない**（項目48-EA と同じ門）。
        # うにさんのメモの実測（2026-08-19・全タブ）で、この道が
        # 火を吹く行は**ちょうど1行**あり、それが
        #
        #     ・シフトキーを押していないものを補正するときは、
        #       漢字変換させる。（きようちよう ⇒ 強調）
        #
        # ——**この機能を頼んだ指示そのもの**だった。
        # 直したら、指示が消える。**見本を壊さない門は要る。**
        if _KANA_TO_KANJI and not _LOOKS_LIKE_EXAMPLE.search(line):
            for h_s, h_e, h_run in find_hiragana_runs(
                    line, min_len=_SHIFT_MIN_LEN, allow_adjacent_kanji=True):
                # 直せる位置がどこにも無ければ、この連続は関係が無い。
                # **2万件の走査もDPも起こらない**（字を見るだけ）。
                if not _shift_lost_positions(h_run):
                    continue
                _hit = None
                # 長いほうから見る（項目48-CR。短い芯を先に取ると
                # 長いほうにある正解に届かない）。
                for _i in range(0, len(h_run) - _SHIFT_MIN_LEN + 1):
                    if _i and not _is_all_functional(h_run[:_i]):
                        continue
                    for _j in range(len(h_run), _i + _SHIFT_MIN_LEN - 1, -1):
                        _body = h_run[_i:_j]
                        # **安い順に置く**。`_rest_is_ordinary_japanese` は
                        # 経路探索を含むので、当たりが出てから調べる。
                        _rd, _kj = _shift_lost_kanji(_body, store, dict_index)
                        if not _kj:
                            continue
                        _rest = h_run[_j:]
                        if _rest and not _rest_is_ordinary_japanese(
                                _rest, tokenize_fn):
                            _trace('シフト', f'{_body!r} → {_kj!r} にしたいが、'
                                             f'残り {_rest!r} が語の途中に見える')
                            continue
                        _hit = (_i, _j, _body, _rd, _kj)
                        break
                    if _hit:
                        break
                if not _hit:
                    continue
                _i, _j, _body, _rd, _kj = _hit
                _a, _b = h_s + _i, h_s + _j
                # **同じ直しの途中で止まっているものは、引き取って直しきる。**
                #
                # `にゆうりよく` は、かなの経路が `ゆうりよく → ゆうりょく`
                # （後ろの拗音だけ戻した形）で止まっていた。**それ自体は
                # 語ではない**（語彙にも辞書にも無い）。全部戻した
                # `にゅうりょく`＝`入力` のほうが正しい。
                # `しゆうせい → しゅうせい` も同じで、こちらは
                # **語として立っている**が、うにさんの指定
                # 「シフトを押していないものを補正するときは漢字変換」
                # のとおり `修正` まで進める。
                #
                # 引き取ってよいのは、重なっている直しが**全部
                # こちらの範囲の内側**にあるときだけ。そのうえで:
                #
                #   (a) **範囲がこちらより狭い**なら引き取る。
                #       **長いほうから見る**（項目48-CR）と同じ考え。
                #       語の一部だけを見た直しより、語まるごとで
                #       説明が付くほうが強い。
                #       実例（2026-08-19）: `ざいりように` は
                #       芯 `ざいり` が `ざいる` に直されて止まっていた。
                #       `ざいりよう` 全体で見れば `材料` である。
                #   (b) 範囲が**ぴったり同じ**なら、それが
                #       「同じ打ち損ねを途中まで戻したもの」のときだけ
                #       （元も直し先もひらがな・長さが同じ・大書きに
                #       開くと元に戻る・戻した位置が含まれる）。
                #       `しゆうせい → しゅうせい` を `修正` まで進める
                #       のがこれ。**別の判断には手を出さない。**
                _over = [r for r in replacements
                         if not (_b <= r[0] or _a >= r[1])]
                _ok = True
                for _rs, _re, _rn, _rc in _over:
                    _ro = line[_rs:_re]
                    if not (_a <= _rs and _re <= _b):
                        _ok = False
                        break
                    if (_rs, _re) == (_a, _b) and not (
                            len(_rn) == len(_ro)
                            and all(is_hiragana(c) for c in _ro)
                            and all(is_hiragana(c) for c in _rn)
                            and ''.join({'ゃ': 'や', 'ゅ': 'ゆ',
                                         'ょ': 'よ'}.get(c, c) for c in _rn)
                            == _ro
                            and _youon_small_positions(_rn)
                            <= _youon_small_positions(
                                _rd[_rs - _a:_re - _a])):
                        _ok = False
                        break
                if not _ok:
                    _trace('シフト', f'{_body!r} → {_kj!r} は、既に決まって'
                                     f'いる別の直しと重なるので触らない')
                    continue
                _after = line[:_a] + _kj + line[_b:]
                # 読める並びと同じ敷居（項目48-AE）。
                # janome が無ければ「意見なし」→触らない。
                if not _naturalness.worth_touching_readable(
                        line, _after, default=False):
                    _trace('シフト',
                           f'{_body!r} → {_kj!r} は自然にならない'
                           f'（差 {_naturalness.gain(line, _after)}）')
                    continue
                _trace('シフト', f'{_body!r} → {_rd!r} → {_kj!r}'
                                 f'（シフトの押し損ね）')
                if _over:
                    replacements[:] = [r for r in replacements
                                       if (_b <= r[0] or _a >= r[1])]
                replacements.append((_a, _b, _kj, 'かな入力'))
                _loan_taken.append((_a, _b))
                _shift_taken.append((_a, _b))

        # --- ひらがなで書いた外来語の打ち間違い（項目48-EC）---
        #
        # うにさんの見本: `かーそねを持って行った ⇒ カーソルを持って行った`
        #
        # 2つの穴が重なっていた:
        #
        #  1. **4文字のカタカナ語が丸ごと落ちていた。** かなの外来語の
        #     経路は5文字以上しか見ない（`_LW.MIN_LENGTH`）ので、
        #     `かーそる` と**正しく打っても**カタカナにならない
        #     （`katakana_for_hiragana('かーそる')` が None）。
        #  2. ひらがなで書いた外来語の**打ち間違い**を直す道が無かった。
        #     カタカナで書けば `プセネタリウム → プラネタリウム` と
        #     直るのに、ひらがなだと当たらない。
        #
        # `katakana_for_hiragana` の説明書きに「**別の関門で既に根拠が
        # 揃っている場合だけ**4文字まで下げてよい」とある。ここでの
        # 根拠が **並記**（直した結果が同じ行に書かれている）。
        # SPEC の持ち越しにも「カール位置→カーソル位置…直すなら
        # **並記の関門つきで拡張する**」と書いてある。
        #
        # **並記を外すと、守っているセリフ・擬音を軒並み壊す**
        # （実機メモで実測。12件中6件がこれ）:
        #
        #     くぅーん → クイーン ／ じゅるる → ジュール
        #     どすーん → バスーン ／ よかったー → カッター
        #     うにゅーん → メニューん
        #
        # 並記を要ると 2件（どちらも `かーそね → カーソル`）だけになる。
        # **同じ行の中だけ**を見る（上下の行まで広げない）。
        for h_s, h_e, h_run in find_hiragana_runs(
                line, min_len=_LOAN_KANA_MIN, allow_adjacent_kanji=True):
            if _loan_overlaps(h_s, h_e):
                continue
            for _len in range(len(h_run), _LOAN_KANA_MIN - 1, -1):
                _body = h_run[:_len]
                _kata = _LW.katakana_for_hiragana(
                    _body, store, min_length=_LOAN_KANA_MIN)
                if not _kata:
                    _kata = _LW.katakana_for_hiragana_typo(
                        _body, store, min_length=_LOAN_KANA_MIN)
                if not _kata:
                    continue
                # **並記の関門**。同じ行の、いま見ている場所の外に、
                # 直した結果が文字通り書かれていること。
                if _kata not in (line[:h_s] + line[h_s + _len:]):
                    _trace('外来語', f'{_body!r} → {_kata!r} は同じ行に'
                                     f'書かれていないので触らない')
                    break
                _after = line[:h_s] + _kata + line[h_s + _len:]
                if not _naturalness.worth_touching_readable(
                        line, _after, default=False):
                    _trace('外来語', f'{_body!r} → {_kata!r} は自然に'
                                     f'ならない（差 '
                                     f'{_naturalness.gain(line, _after)}）')
                    break
                _trace('外来語', f'{_body!r} → {_kata!r}'
                                 f'（ひらがなの外来語・同じ行に並記あり）')
                replacements.append((h_s, h_s + _len, _kata, '外来語'))
                _loan_taken.append((h_s, h_s + _len))
                break

        # --- 記号が紛れた英単語（P:lanetarium）（項目48-EB）---
        #
        # `find_english_runs` は、前後に `. _ - @ / :` が
        # くっついた並びを**わざと外している**（識別子・URL・パス。
        # `:` は 2026-08-10 に足した。`P:lanetarium` から
        # `lanetarium` を英単語として覚えてしまっていたため）。
        # そのため `P:lanetarium` は英単語として見えず、
        # `Pk` `Pll` `mm` は直るのに `:` だけ落ちていた。
        #
        # **覚える側の門はそのまま**にして、直す側にだけ道を足す。
        # 記号を抜いた綴りが知っている語になるときだけ通すので、
        # `C:\Users` `key:value` は通らない。
        for m_s, m_e, m_fix in _LW.find_miskeyed_english(line, store):
            if _loan_overlaps(m_s, m_e):
                continue
            _trace('英語', f'{line[m_s:m_e]!r} → {m_fix!r}'
                           f'（かなのキーの記号が紛れた形）')
            replacements.append((m_s, m_e, m_fix, '英語'))
            _loan_taken.append((m_s, m_e))

        # --- 英単語（Pplanetarium → Planetarium）---
        for e_s, e_e, e_run in _LW.find_english_runs(line):
            if _loan_overlaps(e_s, e_e):
                continue
            fixed = _LW.fix_english_word(e_run, store)
            if fixed:
                _trace('英語', f'{e_run!r} → {fixed!r}')
                replacements.append((e_s, e_e, fixed, '英語'))
                _loan_taken.append((e_s, e_e))

    # --- 記号のつもりで打った、同じキーのかな（項目48-EG）---
    # 行末の1文字だけを見る。`（→ゆ` の逆向き。
    # **行の途中の語連続も見る**（2026-08-16。`（強調ぬ）` や
    # `いいよねぬ ⇒ …` のように、行末以外の対象が素通りしていた）。
    #
    # 重なったときは**同じキーの読み替えを優先する**。こちらは
    # 「同じキーの文字」「手前がまるごと既知語」という名指しの
    # 証拠を持つ。芯の再構築側は `よかったねめ → よよかったね` と
    # どこにも無い並びを作っていた（実測）。
    # **サ変の す抜けを先に決める**（項目48-EM）。`設定る` は
    # `設定。`（同じキー）より `設定する`（す抜け）のほうが自然で、
    # **解析がサ変接続だと言っている**のがその証拠。
    _sahen = _fix_sahen_suru(line, tokenize_fn, dict_index)
    for _sk in _fix_samekey_punctuation_all(line, store, tokenize_fn,
                                            dict_index):
        if any(not (_sk[1] <= s1 or _sk[0] >= e1)
               for s1, e1, _n1 in _sahen):
            _trace('同じキー',
                   f'{line[_sk[0]:_sk[1]]!r} は サ変の す抜けを優先する')
            continue
        replacements[:] = [
            (s0, e0, _n, _c) for s0, e0, _n, _c in replacements
            if (_sk[1] <= s0 or _sk[0] >= e0)]
        replacements.append((_sk[0], _sk[1], _sk[2], '記号'))

    for _sh in _sahen:
        if any(not (_sh[1] <= s0 or _sh[0] >= e0)
               for s0, e0, _n, _c in replacements):
            continue
        replacements.append((_sh[0], _sh[1], _sh[2], 'サ変'))

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
        # **余りの1文字を吸収する**（項目48-DS）。
        # 直し先は当たっているのに、置く場所が1文字ずれていて
        # 「正しい語＋余りの1文字」になっていた形を直す。
        _s2, _e2 = absorb_stray_char(line, start, end, new_surface)
        if (_s2, _e2) != (start, end):
            _trace('置換', f'{line[start:end]!r} → {new_surface!r} は'
                           f'{line[_s2:_e2]!r} の範囲で置く'
                           f'（外した1文字を作り直していた）')
            start, end = _s2, _e2
        original = line[start:end]
        if new_surface == original:
            continue        # 範囲を広げたら元と同じ＝直していない
        # ユーザーが「この補正は不要」と判断した置換は行わない。
        # 統計や辞書より、本人が明示した判断を優先する。
        # 補正経路は複数あるが、ここは全ての置換が必ず通る最終検査なので、
        # ここで見ることで判断経路を増やさずに済む（SPEC.md の設計方針）。
        if decisions is not None and decisions.blocks(original, new_surface):
            continue
        # 半角・ローマ字をかなに直した箇所は、文字数が大きく変わるのが
        # 正常なので長さの検査から外す（mojinyuuryoku → もじにゅうりょく）。
        is_halfwidth = any(not (end <= s or start >= e)
                           for s, e in halfwidth_taken + _shift_taken)
        if not is_halfwidth and abs(len(new_surface) - len(original)) > 2:
            continue
        # 置換によって、元には無かった同じ文字の連続が生まれた場合は
        # 範囲の取り方が誤っている（助詞の切り離しに失敗して
        # 文字が二重になった等）。採用しない。
        # **「記号」（同じキーのかな・項目48-EG）は対象外**
        # （2026-08-16）。あちらは1文字対1文字の読み替えで範囲が
        # ずれようがなく、`め・ → ？？` `１ぬ → ！！` のように
        # **直した先が同じ記号の連続になるのが正しい形**。
        # この砦が食べていた。
        if category != '記号' and _has_new_repetition(original, new_surface):
            continue
        # **句読点の連続だけは、記号でも塞ぐ**（項目48-EI・
        # うにさん指定 (f)「『。。』に違和感を感じる必要がある」）。
        # 上で「記号」を対象外にした穴を、**元に無かった句読点の
        # 連続が生まれる場合**に限って塞ぎ直す。`！！` `！？` は
        # 同じキーの連続の正しい出力なので通る（`_new_punct_run`）。
        if _new_punct_run(line, start, end, new_surface):
            _trace('置換', f'{original!r} → {new_surface!r} は'
                           f'句読点の連続を作るので採らない')
            continue
        # **長音の書き分けが違うだけの正しい語を壊さない**（項目48-EL）。
        # `めにゅう` は語彙の `めにゅー`（メニュー・1,227回）と同じ語。
        # 実機で `メニューとめにゅう → つにゅう` と壊していた
        # （第38回からの持ち越し）。
        _lv = long_vowel_protected_span(line, start, end, new_surface,
                                        store, dict_index)
        if _lv:
            _trace('置換', f'{original!r} → {new_surface!r} は '
                           f'{_lv} を壊すので採らない（長音の書き分け）')
            continue
        # 直した先がひらがなで、その読みの表記が**カタカナのものしか
        # 無い**外来語なら、カタカナで書く（うにさんの指定・
        # 項目48-r「カタカナが適した単語はカタカナに補正する」）。
        # どの経路で直した結果にも同じ扱いをしたいので、
        # 全ての置換が必ず通るこの最終検査の場で一度だけ行う。
        if _LW is not None and new_surface != original:
            try:
                _kata = _LW.katakana_for_hiragana(new_surface, store,
                                                  min_length=4)
            except Exception:
                _kata = None
            if _kata:
                new_surface = _kata
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

# 形態素解析の控えの上限（項目48-BO）。1行の解析で出てくる
# 文字列は多くても数十なので、これだけあれば行をまたいで効く。
TOKENIZE_CACHE_LIMIT = 20000


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

    if not HAS_JANOME:
        # 簡易分割は `store.lookup` を見るので、語彙が育つと答えが
        # 変わる。**控えない**（控えるなら語彙の版も鍵に要る）。
        return _fallback

    # **同じ文字列を何度も分割し直さない**（項目48-BO）。
    #
    # 実測（うにさんのメモ tab0・977行）: `correct_line` 1回につき
    # **形態素解析が 5.1 回**呼ばれていた。1行の中で、行全体・
    # かなの連なり・切り出した窓・候補の検算…と、**同じ短い文字列**を
    # 何度も渡している。1回 0.48ミリ秒なので、これだけで
    # **1行 8.3ミリ秒のうち 2.4ミリ秒**を使っていた。
    #
    # janome の分割は**入力の文字列だけで決まる**（語彙ストアを
    # 見ない）ので、控えても答えは1文字も変わらない。
    # 学び46「件数 × 単価のどちらか一方ではなく両方を数える」の
    # 件数の側。
    cache = {}
    order = []

    def _cached(line):
        got = cache.get(line)
        if got is None:
            got = _from_janome(line)
            cache[line] = got
            order.append(line)
            if len(order) > TOKENIZE_CACHE_LIMIT:
                # 古いものから捨てる（際限なく増やさない）
                for old_key in order[:TOKENIZE_CACHE_LIMIT // 4]:
                    cache.pop(old_key, None)
                del order[:TOKENIZE_CACHE_LIMIT // 4]
        # **控えの実物を渡さない。** 呼ぶ側が並びに手を入れても
        # 控えが汚れないようにする（中身のタプルは書き換わらない）。
        return list(got)

    return _cached
