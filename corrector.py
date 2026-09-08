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
    # **〜てる（〜ている の縮約）**（項目48-TF・2026-09-06。`包装されてるのが`
    #   の `る` を 48-IT が「機能語の並びとして異様」と落とした）
    'てる', 'てた', 'てて', 'てます', 'てない', 'てれば',
    'でる', 'でた', 'でて', 'でます', 'でない', 'でれば',
    'でしょう', 'ましょう', 'ください', 'ておく', 'ている', 'ていた',
    'ていない', 'てある', 'てしまう', 'ちゃう', 'られる', 'させる',
    'せる', 'れる', 'たい', 'たがる', 'そうだ', 'らしい', 'ようだ',
    'ない', 'なかった', 'なく', 'なくて', 'ず', 'ぬ',
    # 仮定形（`成立しなければ` の `なければ`。無いと 48-IT の機能語の
    # 並びの判定で `け` を落として `しなれば` に壊した・実機のメモで実測）
    'なければ', 'ければ', 'なきゃ',
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

# **基本動詞の活用形**（項目48-IS）。ある・いる・する・なる・できる・
# くる・いく の活用形は、文の骨組みとして機能語と同じ働きをする。
# かな連続の「読める」（`_kana_run_explained`）と敷き詰め
# （`_covered_by_known`）の部品。同梱の表は活用形を持たないので、
# これが無いと `ことがあったため` の `あった` が説明できず、読めない
# 扱いになって `ふった` に直された（実測・2026-08-23）。閉じた類。
#: **48-IS の機能語に `んの` は足さない**（項目48-PS・**測って外した**）。
#: `し**てんの**` を説明させるために `んの`・`んだ`・`んです` を
#: 48-IS の機能語に足したら、**`たごんのつながり`**（`たんごのつながり`
#: ＝単語のつながり の的）まで「説明が付く」になった——`たご`＋`んの`＋
#: `つながり` と読めてしまう。**しかも `してんの` は直らなかった**
#: （芯の再構築は別の道で `進展の` にしている）。**外した。**
#: `pos_grammar` の側（48-PS(i)・`_PIECES['TE']` の `んの`）は残す
#: ——あちらは**活用の文法**で、`たご` を語幹にできないので害が無い。

#: **補助動詞になれる形**（項目48-PP・2026-09-03）。
#: 〜ている・〜てある・〜ておく・〜てみる・〜てくる・〜ていく。
#: **`て`／`で` のあとにしか立てない**——`おくゆく` が
#: `おく`（機能語）＋`ゆく`（語）で「説明が付く」になっていた（実測）。
#: **`する`・`できる`・`なる`・`いう` は入れない**——`かくにんできる`・
#: `よくなる` のように、て形でなくても名詞・副詞に付く（実測で確かめた）。
#:
#: **`いる`・`ある` は入れない**（測って絞った）。あの2つは
#: **形容詞の連用形（く）にも付く**（難し**く ありません**）し、
#: ほかの語の中にも現れる——入れると `そういった`・`において`・
#: `のよくある`・`しくありません` など**19の正しい並び**が
#: 「説明できない」に倒れた（実測）。4つに絞ると**失うのは1つ**
#: （`においでぇ` という擬音の断片）だけで、的の `おくゆく` は落ちる。
_AUX_VERB_AFTER_TE = {
    'おく', 'おい', 'おいた', 'おいて', 'おきます',
    'みる', 'みた', 'みて', 'みれば', 'みます', 'みました', 'みない',
    'くる', 'きた', 'きて', 'くれば', 'きます', 'きました', 'こない',
    'いく', 'いっ', 'いった', 'いって', 'いけば', 'いきます',
    'いきました', 'いかない',
}

BASIC_VERB_FORMS = {
    # **得る**（可能の補助動詞・連用形に付く。取り得る・あり得る。項目48-SX・
    #   2026-09-06。`無限にとりうる` に紫が立っていた）。**うる だけ**——
    #   える・えない を足すと `おじえる`＝おじ＋える・`かんえる`＝かん＋える と
    #   打ち間違いまで説明できてしまい、readcheck の直りを失った（実測）。
    #   位置を見られる 48-KS の自動機（R のあとだけ）には え→E も置いてある
    'うる',
    'ある', 'あり', 'あっ', 'あった', 'あって', 'あれば', 'あろう', 'あります',
    # 1字の形（い・き・み）は入れない。`ほらい` が `ほら`＋`い` で
    # 説明できてしまい、`ほせい`（補正）に直らなくなった（tests_mock）。
    'ありました', 'ありません', 'いる', 'いた', 'いて', 'いれば', 'います',
    'いない', 'いなかった', 'いなく', 'いよう',
    'いました', 'いません', 'する', 'し', 'した', 'して', 'すれば', 'しよう',
    'します', 'しました', 'しません', 'しない', 'なる', 'なり', 'なっ', 'なった',
    'なって', 'なれば', 'なろう', 'なります', 'なりました', 'ならない',
    'できる', 'でき', 'できた', 'できて', 'できれば', 'できます', 'できました',
    'できない', 'くる', 'きた', 'きて', 'くれば', 'きます', 'きました',
    'こない', 'いく', 'いっ', 'いった', 'いって', 'いけば', 'いきます',
    'いきました', 'いかない', 'おく', 'おい', 'おいた', 'おいて', 'おきます',
    'みる', 'みた', 'みて', 'みれば', 'みます', 'みました', 'みない',
    'いう', 'いい', 'いった', 'いって', 'いえば', 'いいます', 'いわない',
    'おもう', 'おもい', 'おもっ', 'おもった', 'おもって', 'おもいます',
    'わかる', 'わかり', 'わかっ', 'わかった', 'わかって', 'わかります',
    'わからない', 'つかう', 'つかい', 'つかっ', 'つかった', 'つかって',
    'つかいます', 'つかわない',
}

# 指示語・代名詞
DEMONSTRATIVES = {
    # 連体詞「ある」（ある行・ある日）。この/その と同じ働きの
    # 機能語であり、「ある＋語」の並びに単語は無い
    # （実機で「ある行を」が、自動学習で紛れ込んだ「歩い」
    #   （歩く の連用形・count 4）に化けた。2026-08-08）。
    'ある',
    'これ', 'それ', 'あれ', 'どれ', 'この', 'その', 'あの', 'どの',
    'これら', 'それら', 'あれら', 'どれら',
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

# --- 項目48-NV: **複合辞は1語として扱う**（2026-09-01・うにさんの指定）---
#
#     「**とはいえ、の4文字で接続詞判定するべきです。**
#       ・と ➔ 格助詞（引用）  ・は ➔ 副助詞
#       ・いえ ➔ 動詞「言う」の仮定形
#       元々は『〜と言うとしても』という慣用フレーズが、1つの決まった
#       繋ぎ言葉として定着したため、現代では単体で『接続詞』として
#       扱われています」
#
# 解析器（janome／IPAdic）は `とはいえ` を **と／は／いえ(動詞・命令ｅ)**
# に割る。うにさんが画面で `と` を選ぶと「品詞判定 **フィラー**」と出て
# いた（`と` 単独は IPAdic ではフィラー）。
#
# **これは「1語だけの手当て」ではない。** IPAdic 自身が
# `だからといって`(接続詞)・`したがって`(接続詞)・`にあたって`(助詞)・
# `ともあれ`(接続詞)・`要するに`(副詞) を**すでに1語で登録している**。
# つまり方針は同じで、**抜けているものがある**だけ。ここはその抜けを
# 埋める表であって、新しい考え方ではない。
#
# 載せる決まり（**この3つを全部満たすものだけ**）:
#   (あ) いまの日本語で、**全体が1つの接続詞・助詞として働く**
#   (い) IPAdic が**割ってしまう**（同じ族の語は1語で登録済み）
#   (う) **割れた読みのほうが正しい場面が無い**
#        —— `をもって` は外した（「ペンをもって書く」＝持って がある）。
#           `というのは`・`ということは` も外した
#           （「AというのはBだ」は名詞の言い方で、接続詞ではない）
#
# **出どころ**: 品詞の名前は IPAdic の体系。どれを載せるかは
# **この AI（Claude Opus 4.6・2026-09-01）が日本語として判断した**もの。
COMPOUND_FUNCTION_WORDS = {
    # と＋は＋「言う」の活用 の族（うにさんの指定した形）
    'とはいえ': '接続詞',
    'とはいうものの': '接続詞',
    'とはいっても': '接続詞',
    'そうはいっても': '接続詞',
    'とはいうが': '接続詞',
    # **`そうはいっても` は、いま `はいっ`＝「入っ」と読まれている**
    # （そう／はいっ／て／も）。1語にすると、その誤読ごと消える。
    # 〜にせよ／〜にしても の族（`せよ` は命令ｙｏ）。
    # **`にせよ` 単体は載せない**——「これを参考にせよ」は
    # 「参考にする」の命令形で、割れたほうが正しい。
    'どちらにせよ': '接続詞',
    'いずれにせよ': '接続詞',
    'なんにせよ': '接続詞',
    '何にせよ': '接続詞',
    'いずれにしても': '接続詞',
    'どちらにしても': '接続詞',
    # そのほか
    'にもかかわらず': '助詞:接続助詞',
    'かといって': '接続詞',
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

# **複合辞も「触らない語」に入れる**（項目48-NV）。表は上のひとつ
# だけで、ここは合流させるだけ——**同じ名簿を2つ作らない**（48-GN）。
CONNECTIVES |= set(COMPOUND_FUNCTION_WORDS)

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


def is_reading_gloss(line, i):
    """
    **位置 i から始まる連なりが「読みの注記」かどうか**（項目48-LN・
    うにさんの規則・2026-08-30）:

        「直前に漢字があり、括弧に入った平仮名は、平仮名として
          書きたい意図がある。英語読みも同様。」

        接頭辞（せっとうじ、prefix）   ← せっとうじ は読みの注記
        KyTea（キューティー）          ← 英語の読みの注記

    連なりの直前が開き括弧で、その括弧の直前が漢字か英字なら True。
    読みの注記は**書きたくて書いた かな**なので、変換もかな補正も
    しない（せっとうじ → 決闘時・ぐげんけい → ぐんせい の誤検知を
    実測してから入れた）。
    """
    if i < 2:
        return False
    if line[i - 1] not in '（(':
        return False
    p = line[i - 2]
    return is_kanji(p) or (p.isascii() and p.isalpha())


#: 同音異義語の並記を区切る字（項目48-OO の受け皿・2026-09-03）
_HOMO_LIST_SEP = '、・,／/'


def is_reading_headword(line, a, b):
    """
    **位置 a..b の かな連続が「読みの見出し」かどうか**
    （項目48-OO の受け皿・2026-09-03）。

    `is_reading_gloss`（48-LN）の**逆向き**——あちらは
    「漢字（かな）」＝括弧の中が読みの注記。こちらは

        **かんしん（関心、感心、歓心など）**
        **こうせい（更生、校正、恒星、更正、構成 …）**

    ＝**読みを見出しにして、その表記の候補を括弧の中に並べている**形。
    見出しの かなは**書きたくて書いた かな**なので、変換しない。

    門は**形だけ**（辞書も語彙も引かない・環境に依らない）:
      ・連なりの**直後**が開き括弧
      ・その括弧の中が `、・,／/` で2つ以上に割れ
      ・割れた項目のうち**2つ以上が漢字だけの語**

    2つ以上を要るのは、`効率（こうりつ）` のような**ふつうの言い添え**
    と分けるため。同音異義語の並記は、**必ず2つ以上**並ぶ。
    """
    n = len(line)
    if b >= n or line[b] not in '（(':
        return False
    close = '）' if line[b] == '（' else ')'
    end = line.find(close, b + 1)
    if end < 0 or end - b > 80:
        return False
    inner = line[b + 1:end]
    parts = [p for p in _split_any(inner, _HOMO_LIST_SEP) if p]
    if len(parts) < 2:
        return False
    kanji_items = sum(1 for p in parts
                      if len(p) >= 2 and all(is_kanji(c) for c in p))
    return kanji_items >= 2


def _split_any(text, seps):
    """`seps` のどの字でも切る。"""
    out, cur = [], []
    for c in text:
        if c in seps:
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
    out.append(''.join(cur))
    return [x.strip() for x in out]


def kana_is_mentioned(line, a, b):
    """
    その かな連続が「**語そのものを言及している**」形か——
    読みの注記（48-LN）か、読みの見出し（48-OO の受け皿）。
    **判定はここ1つ**（同じことを2度書かない・48-GN）。
    """
    return is_reading_gloss(line, a) or is_reading_headword(line, a, b)


#: かな連続を割る助詞（項目48-MN／48-MS）。
#: `を` は**いつでも**割る（現代語で語の中に現れない）。
#: `の` は**右側が語のときだけ**割る（`もの` `その` `など` のように
#: 語の中にも現れるので、無条件では割れない）。
_RUN_SPLIT_ALWAYS = 'を'
_RUN_SPLIT_IF_WORD = 'の'

#: **助詞のトークンで区切ってよい1字**（項目48-PI・2026-09-03）。
#: 格助詞・係助詞の1字。`を` は上の `_RUN_SPLIT_ALWAYS` が常に割り、
#: `の` は `_RUN_SPLIT_IF_WORD` が右の語を見て割る。**ここは字面では
#: 割らない**——解析が「その1字を独立した助詞のトークンにしている」
#: ときだけ（`_psplit_cut`）。
_RUN_SPLIT_IF_TOKEN = 'がにはでとへも'

#: 区切った右側の**頭に立てない字**（語の途中で切れた印）。
_PSPLIT_NG_HEAD = frozenset('ゃゅょぁぃぅぇぉっー')


def _psplit_cut(run, tokenize_fn, store=None, dict_index=None,
                after_kanji=False):
    """
    **異様なかな連続を、助詞のトークンで区切る切れ目**（項目48-PI・
    2026-09-03・うにさんの問い）。切れ目の位置（`run[k]` が助詞）か
    `None` を返す。

    うにさんの問い（2026-09-03）:

        「`かいすせき` は解析に正しく補正されます。
          `かいすせきがおわった` は補正されません。
          **`がおわった` の品詞判定は正しいです。** 何が問題に
          なっていますか」

    ①（異様か）は立っている。止まっていたのは③——解析は
    `かいす(動詞)／せき(名詞)／が(格助詞)／おわっ(動詞)／た(助動詞)` と
    **正しく切っている**のに、③は連続を1つの塊として端を削るだけで、
    **`が` の手前で切った `かいすせき` を一度も芯にしなかった**。

    **字面の `が` で切ってはいけない**（項目48-DM で実測——
    `ちゅうがくを` の芯が `ちゅう`・`まぐねねっと` の芯が `まぐね` に
    なり、**語の中の が・ね で真っ二つ**になった）。切ってよいのは、
    **解析がその1字を独立した助詞のトークンにしていて、その右側が
    文法で完結している**とき。`ちゅうがく` は1トークンなので `が` は
    助詞のトークンにならず、この証拠は立たない。

    条件（どれか1つでも欠けたら切らない）:

      (a) **①が立っている連続だけ**——`_kana_run_explained` が False。
          説明が付く連続は、そもそも触らない
          （★★「自然な文には、補正を実行しない」）
      (b) `run[k]` が**ちょうど1トークン**で、品詞が
          **助詞:格助詞／係助詞／接続助詞**（終助詞・副助詞は切らない）
      (c) **左は4字以上・右は2字以上**。3字の切れ端は、単独の行なら
          連続にすらならない長さ（`find_hiragana_runs` の min_len=4）
          ——**区切った切れ端に、連続の決まりより緩い門を通らせない**。
          試作 v2 は左3字で切って `まいすがありました → ますが…`・
          `かんうがありました → カンゾウが…` を壊した
      (d) 右側のトークンが**全部読みが立つ**／右の先頭トークンが
          **2字以上**で小書き・っ・ー で始まらない（語の途中で
          切れた断片で区切らない）
      (e) 右側が**かなの文法で説明が付く**（`pos_grammar.explain_kana_run`）
      (g) **左の切れ端が、それ自体で説明が付かない**こと
          ——付くなら、そこには直すものが無い（`ものまね`）
      (h) **かなで書いた外来語の頭でない**こと
          ——あとの道（外来語）が丸ごと直す（`すけるとん`）
      (i) **左の切れ端を 48-IT が書き換える形でない**こと
          ——区切るのは芯の再構築に届かせるため（`はいてく`）
      (j) **左の切れ端が「世の中に在る読み」でない**こと
          ——在るなら直すものが無い（`ゆうえき`・`ものまね`）

    **(g)(h)(i) は入れたあとに反証で足した門**（2026-09-03）。
    どれも「**あとの道が丸ごと直せるなら切らない**」の言い換えで、
    (f) の「最後の手」を**この輪の外まで**広げたもの。

    **(f)「区切りは最後の手」は呼ぶ側の仕事**——連続まるごとを
    今までどおり通し、**何も直らず「色だけ付ける」に落ちたとき**だけ
    ここを呼ぶ（`correct_line` の輪）。先に区切ると、連続全体で見る道
    （48-HI の畳み・48-HJ の戻し・芯の再構築）が消える——試作 v2 は
    それで **直っていた6語を落とした**（`しつうははったつ`・
    `しるくははっと`・`かんけん → 還元` ほか）。
    """
    if os.environ.get('CN_PSPLIT') == '0':
        return None
    if not run or tokenize_fn is None:
        return None
    if not all(is_hiragana(c) or c == 'ー' for c in run):
        return None
    n = len(run)
    if n < 7:                       # 左4字＋助詞1字＋右2字
        return None
    try:
        # (a) 説明が付く連続は触らない
        if _kana_run_explained(run, tokenize_fn=tokenize_fn):
            return None
        toks = [t for t in tokenize_fn(run) if t[0]]
    except Exception:
        return None
    for i, t in enumerate(toks):
        k = t[3]
        # (b) ちょうど1トークンの助詞
        if t[4] != k + 1 or run[k] not in _RUN_SPLIT_IF_TOKEN:
            continue
        pos = t[1] or ''
        if not (pos.startswith('助詞:格助詞')
                or pos.startswith('助詞:係助詞')
                or pos.startswith('助詞:接続助詞')):
            continue
        # (c) 左4字以上・右2字以上
        if k < 4 or n - k - 1 < 2:
            continue
        right = toks[i + 1:]
        # (d) 右は全部読みが立ち、頭は2字以上の語
        if not right or not all(t2[5] for t2 in right):
            continue
        if len(right[0][0]) < 2 or right[0][0][0] in _PSPLIT_NG_HEAD:
            continue
        # (e) 右側がかなの文法で説明が付く
        try:
            import pos_grammar as _pg
            if not _pg.explain_kana_run(run[k + 1:]):
                continue
        except Exception:
            continue
        # (g) **左の切れ端が、それ自体で説明が付くなら切らない**
        #     ——そこには直すものが無い（①が立っているのは別の場所）。
        #     ★★「自然な文には、補正を実行しない」。実測:
        #       `ものまねがおわった` → 切ると左 `ものまね` を通し直し、
        #       窓が `ものま` に縮んで 48-IT が `もの` にした
        #       （`ものまね` は表に在る語・費用142。**正しい文を壊した**）
        if _kana_run_explained(run[:k], tokenize_fn=tokenize_fn):
            continue
        # (h) **かなで書いた外来語は、あとの道（外来語）が丸ごと直す。**
        #     先に区切るとその道が消える（★ 区切りは最後の手）。実測:
        #       すけるとんがおわった → **するとんがおわった**
        #         （切らなければ `スケルトンがおわった`）
        #       たっくすへいぶんがおわった → **てっくすへいぶん…**
        #       えれくとろにくすがおわった → **エレクトロンにくす…**
        #     janome は未変換のかな列を助詞込みで刻むので、語の中の
        #     `へ`（へいぶん）まで「独立した助詞のトークン」になる
        #     ——48-DM の守り（`ちゅうがく` は1トークン）は
        #     **かなのままの外来語には効かない**。
        #     判定は外来語の道と同じ関数（`katakana_for_hiragana`）。
        if _psplit_is_kana_loanword(run, store):
            continue
        # (i) **左の切れ端を 48-IT が書き換える形なら切らない。**
        #     区切るのは「芯の再構築に届かせる」ためで、
        #     **機能語の並びの異様（48-IT）に渡すためではない**。実測:
        #       はいてくとてんとうむし（ハイテクとテントウムシ・誤字なし）
        #         → 切ると左 `はいてく` を 48-IT が `はいく` にした
        #     的（`かいすせき`・`かんげげん`・`めんせせき` ほか）は
        #     48-IT が何も言わない——ここで断っても失うものは無い。
        # ★ **`after_kanji` は本番と同じものを渡す**（検品で指摘・
        #   2026-09-07）。ここは「48-IT が書き換えるか」を**予想**して
        #   いるので、本番（`_fix_functional_run(window, after_kanji=…)`）
        #   と条件が違うと**起きない書き換えを恐れて区切りをやめる**
        #   （48-UK で漢字の直後の巻き込みを止めたので、ずれが出た）。
        if _fix_functional_run(run[:k], after_kanji=after_kanji,
                               store=store, tokenize_fn=tokenize_fn):
            continue
        # (j) **左の切れ端が「世の中に在る読み」なら切らない。**
        #     そこに直すものは無い（①が立っているのは別の場所）。
        #     判定は芯の再構築と同じ `dict_index.is_world_reading`
        #     ——trace の「世の中に在る語なので触らない（48-EN）」と
        #     同じ問い（**新しい判定を作らない**・48-GN）。実測:
        #       ゆうえきがらいとぺん（有益がライトペン・誤字なし）
        #         → 切ると左 `ゆうえき` の窓が `ゆうえ` に縮み、
        #           48-IT が `ゆえ` にした（**同じ通しの中で
        #           「これは語だ」と言った直後に壊していた**）
        #     的の16語（`かんげげん`・`めんせせき`・`あなろく` ほか）は
        #     **1つも世の中の読みではない**——断っても失うものは無い。
        if dict_index is not None:
            try:
                if dict_index.is_world_reading(run[:k]):
                    continue
            except Exception:
                pass
        return k
    return None


def _psplit_is_kana_loanword(run, store):
    """
    その かな連続の**頭が、かなで書いた外来語**か（項目48-PI(h)）。

    あとの道（`correct_line` の「ひらがなで書かれた外来語」）が
    **頭から長いほうへ**同じ引き方をするので、そこで丸ごと直る。
    引くのは同じ関数（`loanword.katakana_for_hiragana`）——
    **新しい名簿も判定も作らない**（48-GN）。
    """
    if store is None:
        return False
    try:
        import loanword as _lw_ps
        for _len in range(len(run), _lw_ps.MIN_LENGTH - 1, -1):
            if _lw_ps.katakana_for_hiragana(run[:_len], store):
                return True
    except Exception:
        return False
    return False


def split_runs_at_particle(runs, min_len=2, known=None):
    """
    かな連続を、**助詞で区切る**（項目48-MN／48-MS・2026-08-31・
    うにさんの指定）:

        「**「を」は単語で出てこないので、助詞として判定して
          前後を区切るとよいです**」

    現代語で `を` は助詞にしかならず、**語の読みの中に現れない**。
    この事実はもともと **「`を` を含む範囲は触らない」** の根拠として
    使っていた（48-CL・48-DO・3か所）。**触らないのではなく、
    そこで区切って両側をふつうに見る**——同じ事実の、もっと素直な使い方。

        つづき**を**はなす   → `つづき` ／ `はなす`
        もじ**を**うと       → `もじ` ／ `うと`（右だけを直せる）

    **`の` は右側が語のときだけ**（項目48-MS）。`の` は `もの` `その`
    `など`（の を含む語）のように**語の中にも現れる**ので、無条件で
    割ると語を真っ二つにする（48-CL の但し書きと同じ用心）。
    右側が**表か語彙の語**なら、その `の` は連体化の助詞だと言える:

        やんご**の**つながり  → `やんご` ／ `つながり`
                              （`やんごの` 単独なら直っていたのに、
                                後ろに語が続くと窓が丸ごとになって
                                芯が立たなかった）

    区切ったあとは `を` を含まないので、48-CL/48-DO の3つの門は
    自然に通る（門は残す。**別の道から を を跨ぐ範囲が来たときの守り**）。

    runs: [(始まり, 終わり, 文字列), ...]（`find_hiragana_runs` の形）
    min_len: これより短い切れ端は捨てる。
    known: その並びが語かを返す関数（`の` の判断にだけ使う）。
        渡さなければ `を` だけで割る（今までどおり）。

    **`がにはでとへも` はここでは割らない**（項目48-PI・2026-09-03）。
    あちらは「解析が独立した助詞のトークンにしていて、右が文法で
    完結していて、**しかも連続まるごとでは何も直らなかった**とき」
    という**順番のある**話なので、連続を作るこの段ではなく
    **`correct_line` の輪の中**（`_psplit_cut` ／ `_psplit_retry`）に
    置いてある。**判定を2か所に書かない**（48-GN）。
    """
    for s0, e0, run in runs:
        cuts = []
        n = len(run)
        for k, ch in enumerate(run):
            if ch in _RUN_SPLIT_ALWAYS:
                cuts.append(k)
            elif (known is not None and ch in _RUN_SPLIT_IF_WORD
                    and k >= min_len and n - k - 1 >= min_len):
                try:
                    if known(run[k + 1:]):
                        cuts.append(k)
                except Exception:
                    pass
        if not cuts:
            yield (s0, e0, run)
            continue
        i = 0
        for k in cuts:
            if k - i >= min_len:
                yield (s0 + i, s0 + k, run[i:k])
            i = k + 1
        if n - i >= min_len:
            yield (s0 + i, e0, run[i:])


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
        if len(run) >= min_len and prev_ok and next_ok \
                and not kana_is_mentioned(line, i, j):
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
        surface, _pos, _reading, _s, _e, known = tok[:6]
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
            # **窓の頭が小書き（ょ・ゅ・っ…）なら、その境目は嘘**
            # （項目48-LP・2026-08-30）。正しい日本語で小書きから
            # 始まる語は無いので、そこで切った解析のほうが壊れて
            # いる。手前のトークンごと窓に含めて、本来の入力を
            # 塊全体から探れるようにする（`がいし|ょつする` →
            # 窓 `がいしょつする` → がいしゅつ＝外出 に届く）。
            while (i > 0 and run[w_start:w_start + 1] in 'ゃゅょぁぃぅぇぉっ'
                   and w_end - toks[i - 1][3] <= max_len):
                i -= 1
                w_start = toks[i][3]
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


def _lq_attested_insertion(line, a, b, window_ext, dict_index=None):
    """
    **同じ行の並記からの脱字の訂正**（項目48-LQ・2026-08-30）。

    ⇒で正解を並べたメモ・同じ語を書き直した行では、**本来の入力が
    同じ行に文字どおり書かれている**。どの探索でも直せなかった窓
    `window_ext`（line[a:b]）に、「内側の1字を足すと、行の**後ろ**の
    並びに一致する」ものが**ただ1つ**あれば、それを返す
    （かなちでのほせい → かなうちでのほせい。回9のうにさんの指摘
    「開いた平仮名が補正できていません。より簡単なはずですが」への答え）。

    **端の1字の挿入は採らない**——窓の切り出しが助詞を落としただけの
    並び（ほせい に対する のほせい）と区別が付かないため。
    **並記は窓より後ろにあること**——書き直し・⇒の正解は、壊れた形の
    **後**に書かれる。前も見ていた最初の版は、⇒の**右の正しい側**を
    左の壊れた側で「補って」いた（さんこうになる→さつんこうになる・
    もとにもどります→もみとにもどります・さいしょうか→さそいしょうか
    の3件を全行検品で実測。世の中の語を割るかで裁く案は もと が
    2字で掬えず捨てた——判定は1つにする・48-GN）。
    見つからなければ None。
    """
    w = window_ext
    if len(w) < 4:
        return None
    n = len(w) + 1
    found = set()
    for i in range(b, len(line) - n + 1):       # **窓より後ろだけ**
        s = line[i:i + n]
        if s in found:
            continue
        if not all(is_hiragana(c) or c == 'ー' for c in s):
            continue
        for k in range(1, n - 1):       # 内側の挿入だけ
            if s[:k] + s[k + 1:] == w:
                found.add(s)
                break
    if len(found) == 1:
        return next(iter(found))
    return None


def _reading_spelled_in_bracket(line, a, b, tokenize_fn):
    """
    **読みの並記は書きたい形**（項目48-LS・2026-08-30）。

    回14の規則「直前に漢字があり、括弧に入った平仮名は、平仮名として
    書きたい意図がある」（is_reading_gloss）の**逆向き**——かなの
    連なりの直後に、括弧で**その読みの表記**が並ぶ形:

        しょくじけん（食事券）

    は、読みを見せるために**わざとかなで書いた**もの。実機で
    `初期事件（食事券）` に化けていた（写しでは 初期800・事件300 の
    実績を水増しして再現・2026-08-30 17回目）。

    置換の範囲 [a, b) がかなだけで、それを含むかなの連なりの直後が
    開き括弧、括弧の中が漢字を含む表記で、**その読みが連なりと
    一致する**とき True（＝触らない）。
    """
    if tokenize_fn is None or b <= a:
        return False
    if not all(is_hiragana(c) or c == 'ー' for c in line[a:b]):
        return False
    i = a
    while i > 0 and (is_hiragana(line[i - 1]) or line[i - 1] == 'ー'):
        i -= 1
    j = b
    n = len(line)
    while j < n and (is_hiragana(line[j]) or line[j] == 'ー'):
        j += 1
    run = line[i:j]
    if len(run) < 2 or j >= n or line[j] not in '（(':
        return False
    close = -1
    for k in range(j + 1, min(n, j + 20)):
        if line[k] in '）)':
            close = k
            break
    if close < 0:
        return False
    inner = line[j + 1:close]
    if not inner or not any(is_kanji(c) for c in inner):
        return False
    try:
        ts = tokenize_fn(inner)
        rd = ''.join((t[2] or '') for t in ts)
    except Exception:
        return False
    if not rd:
        return False
    # 読みはカタカナで返る。ひらがなへ寄せて比べる
    hira = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
                   for c in rd)
    return hira == run


# 組み直し（項目48-LU）で使う機能語の部品——**専用の狭い名簿**。
# 最初の版は保護用の表（PARTICLES_1CHAR・AUXILIARY_TAILS）を流用
# したが、あちらは語尾の**保護**のために ち・い・さ・し のような
# 1字も持っていて、何でも敷けてしまい拮抗がゴミで埋まった（実測）。
# 組む側は「文を作れる部品」だけ——助詞と、ありふれた活用の尾
# （AI の判断で書き下した閉じた名簿・2026-08-30）。
_LU_FUNCTIONAL = tuple(sorted(
    {'の', 'は', 'が', 'を', 'に', 'で', 'と', 'へ', 'も', 'や',
     'から', 'まで', 'など', 'ので', 'のに', 'ても', 'では', 'には',
     'とは', 'た', 'て', 'だ',
     'ます', 'です', 'ました', 'でした', 'ません', 'ない', 'なかった',
     'なる', 'なり', 'なっ', 'する', 'した', 'して', 'します',
     'いる', 'いた', 'います', 'ある', 'あり', 'ください'},
    key=len, reverse=True))


def _lu_katakana_face(frag):
    """読みをカタカナに綴った形が**世の中で1語**なら、その表記（4字以上。
    `_convert_odd_kana_run` の `_world_katakana_piece` と同じ門・48-OR(c)）。"""
    if not frag or len(frag) < 4:
        return None
    try:
        from loanword import hiragana_to_katakana as _h2k
        import seed_japanese as _sj
    except Exception:
        return None
    k = _h2k(frag)
    if k == frag or not all(is_katakana(_c) or _c == 'ー' for _c in k):
        return None
    try:
        return k if _sj.is_unit(k) else None
    except Exception:
        return None


def _lu_dominant(r, store, dict_index=None):
    """
    **その読みの「優勢な」表記を、回数なしで決める**（項目48-SC・
    2026-09-06。48-LU の `dominant`（床10・比20倍）は回数を廃した
    48-QG' で成立しなくなり、道が丸ごと眠っていた）。

    順に:
      (1) 本人の語彙に **solid（実績2以上）** の表記——ただ1つならそれ。
          2つ以上なら **段（`kango_tier`）→ 同梱の費用** で1つに
          （いどう: 移動〔段1〕／異動〔段2〕→ 移動）。並べば None
      (2) 索引の顔（`_index_face`——段1の2字漢語がただ1つ）
      (3) 世の中のカタカナ語（`_lu_katakana_face`・4字以上）

    **count 1 の表記は数えない**（48-LU の注記「立った表記がただ1つ」
    へ緩めた案は、育ちの readcheck で本当の化けを 34 作った）。
    戻り値: (表記, 強さ) か None。強さは (1)=3・(2)(3)=2。
    """
    if not r or store is None:
        return None
    faces = []
    try:
        for e in store.lookup(r):
            sf = e.get('surface') or ''
            if sf and e.get('count', 0) >= 2 and sf not in faces \
                    and sf != r:
                faces.append(sf)
    except Exception:
        faces = []
    if faces:
        if len(faces) == 1:
            return faces[0], 3

        def _key(sf):
            tc = _table_cost(sf)
            return (_kango_tier_of(sf), tc if tc is not None else 10 ** 9)
        faces.sort(key=lambda sf: (_key(sf), sf))
        if _key(faces[0]) < _key(faces[1]):
            return faces[0], 3
        return None
    if dict_index is not None:
        try:
            f = _index_face(r, store, dict_index)
        except Exception:
            f = None
        if f:
            return f, 2
    k = _lu_katakana_face(r)
    if k:
        return k, 2
    return None


def _lu_moved_piece(run, v, tokenize_fn):
    """゛の位置ずれで変わった2か所を含む、v の解析の**同じ語**の範囲
    （`つづき` → (0, 3)／`むだ|つかい` は別々の語に散るので None・項目48-SB）。"""
    if not run or not v or len(run) != len(v) or tokenize_fn is None:
        return None
    diff = [i for i in range(len(v)) if run[i] != v[i]]
    if not diff:
        return None
    try:
        toks = list(tokenize_fn(v))
    except Exception:
        return None
    if not toks or ''.join(t[0] or '' for t in toks) != v:
        return None
    for t in toks:
        try:
            s0, e0 = int(t[3]), int(t[4])
        except Exception:
            return None
        if s0 <= diff[0] < e0:
            return (s0, e0) if all(s0 <= d < e0 for d in diff) else None
    return None


def _lu_moved_in_one_word(run, v, tokenize_fn):
    """（旧名・同じ判定）゛の位置ずれで変わった2か所が同じ語の中に在るか。"""
    return _lu_moved_piece(run, v, tokenize_fn) is not None


def _lu_changed_positions(run, v):
    """手が変えた v の位置の集まり（落とした字は、落とした位置・項目48-SC）。"""
    if not run or not v or run == v:
        return set()
    out = set()
    try:
        import difflib as _dl
        for tag, _i1, _i2, j1, j2 in _dl.SequenceMatcher(
                None, run, v, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            if j2 > j1:
                out.update(range(j1, j2))
            elif j1 < len(v):
                out.add(j1)
            elif v:
                out.add(len(v) - 1)
    except Exception:
        return set()
    return out


def _lu_orig_piece_known(run, v, store, tokenize_fn):
    """
    **手を当てる前の、その語が「知っている語」か**（項目48-SC の
    ゛の位置ずれの門）。語の切れ目は**手を当てた読み v の解析**で取り
    （壊れた run の解析は当てにならない——`つつぎをはなす` は
    つつ｜ぎをはなす）、同じ範囲の run の字を見る。位置ずれは長さを
    変えないので範囲はそのまま使える。
    """
    if not run or not v or len(run) != len(v) or tokenize_fn is None:
        return False
    p = 0
    while p < len(v) and run[p] == v[p]:
        p += 1
    if p >= len(v):
        return False
    try:
        toks = list(tokenize_fn(v))
    except Exception:
        return False
    if not toks or ''.join(t[0] or '' for t in toks) != v:
        return False
    for t in toks:
        try:
            s0, e0 = int(t[3]), int(t[4])
        except Exception:
            return False
        if s0 <= p < e0:
            seg = run[s0:e0]
            if len(seg) < 2:
                return False
            try:
                if any(e.get('count', 0) >= 2 for e in store.lookup(seg)):
                    return True
            except Exception:
                pass
            return _table_cost(seg) is not None
    return False


def _lu_changed_piece_known(run, v, store, tokenize_fn, against=None):
    """
    **手を当てた読み v の、変わった所を含む語が「知っている語」か**
    （項目48-SC の かな→かな の受け入れ・48-PO と同じ物差し）。

    語の切れ目は解析（`tokenize_fn`）に聞く——`もとにもどります` の
    変わった所（み を落とした 1）は `もと`。知っているとは、本人の
    語彙に実績2以上か、同梱の費用の表に在ること（`is_world_reading`
    は `くみと` まで True で使えない・48-PO の実測）。
    """
    if not run or not v or tokenize_fn is None:
        return False
    # `against` を渡すと、変わった所は run と against の差で決め、語は v
    # （＝run そのもの）の側で見る（元の語が知っている語か）
    other = against if against is not None else v
    if run == other:
        return False
    p = 0
    while p < min(len(run), len(other)) and run[p] == other[p]:
        p += 1
    if p >= len(v):
        p = len(v) - 1
    try:
        toks = list(tokenize_fn(v))
    except Exception:
        return False
    if not toks or ''.join(t[0] or '' for t in toks) != v:
        return False
    seg = ''
    for t in toks:
        try:
            s0, e0 = int(t[3]), int(t[4])
        except Exception:
            return False
        if s0 <= p < e0:
            seg = t[0] or ''
            break
    if len(seg) < 2:
        return False
    try:
        if any(e.get('count', 0) >= 2 for e in store.lookup(seg)):
            return True
    except Exception:
        pass
    return _table_cost(seg) is not None


def _lu_functional_only(tail):
    """その尾が **`_LU_FUNCTIONAL`（閉じた名簿）の並びだけ**で埋まるか
    （項目48-SC）。`になる`・`して`・`のには` は True、`かして`（か は
    名簿の外）は False。`_is_all_functional` は緩すぎた（実測）。"""
    n = len(tail)
    ok = [False] * (n + 1)
    ok[0] = True
    for i in range(n):
        if not ok[i]:
            continue
        for fp in _LU_FUNCTIONAL:
            if tail.startswith(fp, i):
                ok[i + len(fp)] = True
    return ok[n]


def _lu_predicate_tail(tail, tokenize_fn):
    """
    **その尾は、名詞の直後に直付きできる述語か**（項目48-SC・2026-09-06）。

    メモの文は助詞を省く（`入力みています`・`スクロール後のみえた` の
    `みえた`）。尾が **い段の送り仮名の頭**（み・し・き＝連用形）で
    始まり、送り仮名＋機能語で説明が付く（`_okurigana_functional_only`）
    か、解析が **動詞（形容詞）＋付属語だけ** と読んで文法でも説明が
    付く（`みえた`＝見え＋た）ときだけ。`う` で始まる尾（`うして`）は
    名詞に付かないので False。
    """
    if not tail or tail[0] not in OKURIGANA_HEADS:
        return False
    # **1字の語幹で立てるのは、閉じた名簿だけ**（し＝する・き＝来る／
    # 着る・`pos_grammar._BASIC_STEMS_1`＝見る・居る・出る・寝る…）。
    # `え`・`せ`・`て` のような送り仮名の頭は、名詞の直後では動詞に
    # ならない（`タブ以後|えして` の junk・実測）
    try:
        import pos_grammar as _pg_h
        _stems1 = set(_pg_h._BASIC_STEMS_1) | {'し', 'き'}
    except Exception:
        _stems1 = set('しきみい')
    try:
        if tail[0] in _stems1 and _okurigana_functional_only(tail):
            return True
    except Exception:
        pass
    if tokenize_fn is None:
        return False
    try:
        ts = list(tokenize_fn(tail))
    except Exception:
        return False
    if not ts or ''.join(t[0] or '' for t in ts) != tail:
        return False
    if any(len(t) > 5 and not t[5] for t in ts):
        return False
    p0 = ts[0][1] or ''
    if not (p0.startswith('動詞') or p0.startswith('形容詞')):
        return False
    if len(ts[0][0] or '') < 2 and (ts[0][0] or '') not in _stems1:
        return False
    for t in ts[1:]:
        pz = t[1] or ''
        # 2つ目からは付属語だけ（`すら|き|が|おわっ|た` のように別の
        # 自立語の動詞が続く並びは、1つの述語ではない・実測）
        if not (pz.startswith('助詞') or pz.startswith('助動詞')
                or pz.startswith('動詞:非自立')
                or pz.startswith('形容詞:非自立')):
            return False
    try:
        import pos_grammar as _pg_t
        return bool(_pg_t.explain_kana_run(tail))
    except Exception:
        return False


def lu_run_candidates(run, store, dict_index, tokenize_fn,
                      input_method=None, limit=6):
    """
    **紫のかな連続まるごとの候補**（項目48-SF・2026-09-06・うにさんの
    指定「`たぶいごうして`、して は正しい。たぶい の候補に 舞台 を
    挙げているが、それだと 舞台ごうして で成立しない」）。

    F2 の候補一覧のための口。48-LU/48-SC の受け皿が**組めた表記を
    全部**（手の段の順・強さの順）返す——自動の直しは「ただ1つ」の
    ときだけだが、候補なら並べてよい（脱字の段も含める）。
    連続の一部（`たぶい`）ではなく**連続そのもの**に対する候補なので、
    選ぶと連続まるごとが置き換わる（呼び手が `span` を持つ）。
    """
    got = []
    out = []
    # **自動の直しが決めた答えが先頭**（④の選び方をそのまま候補の順に）
    try:
        _top = _lu_compose_odd_run(run, store, input_method=input_method,
                                   tokenize_fn=tokenize_fn,
                                   dict_index=dict_index,
                                   odd_known=True, bare_head=True)
        if _top and _top != run:
            out.append(_top)
    except Exception:
        pass
    try:
        _lu_compose_odd_run(run, store, input_method=input_method,
                            tokenize_fn=tokenize_fn, dict_index=dict_index,
                            odd_known=True, bare_head=True, collect=got)
    except Exception:
        return out
    got.sort(key=lambda t: (t[0], t[1], t[2]))
    for _ti, _st, sf in got:
        if sf not in out and sf != run:
            out.append(sf)
        if len(out) >= limit:
            break
    return out


def _lu_compose_odd_run(run, store, input_method=None, tokenize_fn=None,
                        context_vec=None, dict_index=None, odd_known=False,
                        bare_head=False, collect=None):
    """
    **異様なかな連なりを、見本なしで語の列として組み直す**
    （項目48-LU・2026-08-30 19回目）。うにさんの指定:

        「こんなミスタイプと意図した文章が実際に横に並んで残り続けると
          思いますか？ …これらは開発用の文字列です。つまり、正しい文の
          見本がなくても異様な文字列を正しく漢字に補正する必要が
          あります」

    形は ★★ の順そのもの:
      ① 異様と判定された連なりだけが来る（窓のどの探索でも直せず、
         紫に落ちる直前——呼び元がその場所）
      ③ 本来の入力を探る——手は**1つまで**
      ④ 確かめる——直した読みが**優勢な語＋機能語で端から端まで
         組み上がり**、組み上がる表記が**ただ1つ**のときだけ採る

    ### 7巡目で起こした（項目48-SC・2026-09-06・**④の選び方**）

    回数を廃した 48-QG' で `dominant`（床10・比20倍）が成立しなく
    なり、この道は丸ごと眠っていた（48-RW で「かな連続の受け皿が
    無い」と見えたのはそのため）。**優勢は回数なしで決める**
    （`_lu_dominant`——solid・段・費用・索引の顔・世の中のカタカナ語）。
    あわせて:

      ・**手を費用の段に分ける**（48-OQ(e')「打った字を使う手が先」）:
          0手 → 安い1手（隣のキー≤1.0・゛の付け外し・**゛の位置ずれ**
          〔48-SB〕・**余分な字に濁点**〔48-OR(b)・たで→だ〕・
          **余分な隣のキー／同じキー**を落とす）→ 遠い隣（≤1.4・
          `たぶいごうして` の ご→ど）→ 脱字（1字足す・1.5）。
          **どの字でも消す手は止めた**（余分な打鍵は隣のキーのとき
          だけ——SPEC の型5）
      ・**述語の尾はそのまま1つの部品**（`みています`・`して`・
        `になる` は `_okurigana_functional_only`＝送り仮名＋機能語で
        説明が付く尾。語の列に敷き詰めず、そのまま後ろに置く）——
        芯の切り出しが `にゅうりゅくみ` に み を巻き込んでいた形の答え
      ・**2字の部品は solid かカタカナだけ**（右・タブ。2字の漢字を
        索引の顔で埋めると `ぶんうつ → 文打つ` の族・48-ON）
      ・**自然さは、共通の尾を除いて比べる**（`入力みています` は
        まるごとだと差 2091 で落ちるが、比べるべきは
        にゅうりゅく → 入力 の頭）
      ・**かな→かな も受け入れる**（漢字に届かないとき）: 手を当てた
        読みが文法で説明が付き、変わった所を含む語が知っている語
        （solid か費用の表）で、その段の候補が**ただ1つ**なら
        （`もみとにもどります → もとにもどります`。48-PO の かな版）
      ・`odd_known`: 呼び手が行全体の①（`odd_kana_spans`）で「この
        窓は異様」と確かめてある（窓だけでは説明が付いて見える形——
        `もみと`）。`bare_head`: 窓が行の頭

    戻り値: 組み上がった表記（漢字を含むもの／かな→かな）か None。
    """
    if not (4 <= len(run) <= 14):
        return None
    if not all(is_hiragana(c) or c == 'ー' for c in run):
        return None
    # **文法で説明の付く連なりには掛けない**（①異様か判定する、が先。
    # 窓の readable だけでは甘く、たんごのつながり→単語の繋がる・
    # せっけいのみして→設計の見せて を作った——48-KS の異様判定
    # （pos_grammar）で説明が付くなら、それは書きたい形でありうる）
    try:
        import pos_grammar as _pg
        if not odd_known and _pg.explain_kana_run(run, bare_head=bare_head):
            return None
    except Exception:
        _pg = None

    dom_cache = {}

    def dominant(r):
        if r in dom_cache:
            return dom_cache[r]
        got = _lu_dominant(r, store, dict_index)
        dom_cache[r] = got
        return got

    seg_cache = {}

    def seg_full(v):
        """v を端から端まで組む。{(表記, 最弱の強さ, 部品の組)} を返す。"""
        if v in seg_cache:
            return seg_cache[v]
        n = len(v)
        CAP = 8
        memo = {n: (('', 10 ** 9, ()),)}

        def rec(i):
            # **打ち切るなら、良いものを残す**（項目48-NE・2026-08-31）——
            # 貯めるのは全部、切るのは並べたあと。並べる軸は全順序
            if i in memo:
                return memo[i]
            outs = set()
            # **組の頭は内容語**（文は機能語では始まらない）
            if i > 0:
                for fp in _LU_FUNCTIONAL:
                    if v.startswith(fp, i):
                        for s2, mn, cs in rec(i + len(fp)):
                            outs.add((fp + s2, mn, (('f', fp, len(fp)),) + cs))
                # **述語の尾は、そのまま1つの部品**（項目48-SC）。
                # 尾の頭は **名詞の直後に置ける機能語**（に・を・して・
                # です…`_noun_tail_start`）か、**い段の送り仮名で始まる
                # 述語**（`_lu_predicate_tail`・みています・みえた）に
                # 限る——`う` で始まる尾（`タブ以後|うして`）は名詞に付かない
                tail = v[i:]
                try:
                    _tail_ok = ((_lu_functional_only(tail)
                                 and _noun_tail_start(tail))
                                or _lu_predicate_tail(tail, tokenize_fn))
                except Exception:
                    _tail_ok = False
                if _tail_ok:
                    outs.add((tail, 10 ** 9, (('f', tail, len(tail)),)))
                # **カタカナのサ変名詞の直後の `ご` は `後`**（48-PQ の
                # かな版。`すくろーる|ご|の|みえた`——後ろに 名詞に付く
                # 助詞が続くときだけ。前がカタカナの部品かは、組み上がりを
                # 見る側で確かめる）
                if v[i] == 'ご' and i + 1 < n and v[i + 1] in 'のにではも':
                    for s2, mn, cs in rec(i + 1):
                        outs.add(('後' + s2, min(mn, 2), (('c', '後', 1),) + cs))
            for L in range(2, min(8, n - i) + 1):
                got = dominant(v[i:i + L])
                if not got:
                    continue
                face, strength = got
                # **2字の部品は solid かカタカナだけ**（48-ON の族）
                if L == 2 and strength < 3 \
                        and not all(is_katakana(_c) or _c == 'ー'
                                    for _c in face):
                    continue
                for s2, mn, cs in rec(i + L):
                    outs.add((face + s2, min(mn, strength),
                              (('c', face, L),) + cs))
            memo[i] = tuple(sorted(outs, key=lambda t: (
                -t[1],
                sum(1 for _pc in t[2] if _pc[0] == 'c'),
                t[0], t[2])))[:CAP + 1]
            return memo[i]

        out = rec(0)
        seg_cache[v] = out
        return out

    # --- 手の段（安い順）。**先頭の字には掛けない**（頭の1字は打った字
    #     そのもの。48-LS「頭のかなは動かさない」）
    n = len(run)
    mark, cheap, drop, far, ins = [], [], [], [], []
    try:
        from kana_layout import nearby_candidates as _nearby
    except Exception:
        _nearby = None
    if _nearby is not None:
        for i in range(1, n):
            ch = run[i]
            try:
                alts = _nearby(ch, input_method=input_method)
            except TypeError:
                alts = _nearby(ch)
            except Exception:
                alts = []
            for alt, dist in alts:
                if alt == ch:
                    continue
                v = run[:i] + alt + run[i + 1:]
                if dist <= 1.0:
                    cheap.append(v)
                elif dist <= _CHUNK_NEAR_MAX:
                    far.append(v)
    # ゛゜の打ち忘れ・打ちすぎ（かな入力では ゛ が独立キー・48-LL と同じ）
    try:
        from morphology import _DAKUTEN_COMPOSE, _HANDAKUTEN_COMPOSE
        _fwd = dict(_DAKUTEN_COMPOSE)
        _fwd.update(_HANDAKUTEN_COMPOSE)
        _rev = {v: k for k, v in _fwd.items()}
        for i in range(1, n):
            ch = run[i]
            if ch in _fwd:
                mark.append(run[:i] + _fwd[ch] + run[i + 1:])
            if ch in _rev:
                mark.append(run[:i] + _rev[ch] + run[i + 1:])
    except Exception:
        pass
    # ゛が1つ隣にずれた形も1手（項目48-SB。頭は変えない）——**打った字を
    # 全部使って読み替える手**なので、隣のキーと同じ段
    for v in _moved_dakuten_variants(run):
        mark.append(v)
    # 余分な字に濁点が付いた形（48-OR(b)・たで→だ）
    for i in range(1, n - 1):
        u, w = run[i], run[i + 1]
        if u in _OR_DAKUTEN_BASE and w in _OR_VOICED_KANA \
                and u in _TYPO_DAKUTEN:
            drop.append(run[:i] + _TYPO_DAKUTEN[u] + run[i + 2:])
    # 余分な打鍵は**隣のキーか同じキー**のときだけ落とす（SPEC の型5。
    # どの字でも消す手は junk を作る——`チサ積んこうになる` の族）
    for i in range(1, n):
        nb = False
        for j in (i - 1, i + 1):
            if 0 <= j < n:
                if run[j] == run[i]:
                    nb = True
                else:
                    try:
                        if adjacent_slip(run[j], run[i],
                                         input_method or 'kana'):
                            nb = True
                    except Exception:
                        pass
        if nb:
            drop.append(run[:i] + run[i + 1:])
    # 脱字（1字を足す。頭には足さない——切り出しの紛れと区別が
    # 付かない・48-LQ と同じ理由）。**打っていない字を足す手はあと**
    _ks = [chr(c) for c in range(ord('ぁ'), ord('ゖ') + 1)] + ['ー']
    for i in range(1, n + 1):
        for ch in _ks:
            ins.append(run[:i] + ch + run[i:])
    # **段の順**（項目48-SC・④の選び方の「手の種類」）:
    #   0手 → 打った字を**全部使って読み替える**手（隣のキー≤1.0・
    #   ゛の位置ずれ）→ 打った字を**落とす／印を付け外す**手（余分な
    #   隣のキー・余分な字に濁点・゛の付け外し）→ 遠い隣（≤1.4）→
    #   脱字（打っていない字を足す・1.5）。`つつぎをはなす` は
    #   ゛の位置ずれ（続きを話す）が 重複打鍵を落とす（次を話す）より先。
    #   **手は先頭の字に掛けない**（どの段も。頭の1字は打った字）
    # **脱字（1字足す）の段は自動の直しには使わない**（項目48-SC・
    # 実測 `しゅうりょじ → 囚虜文字`〔もじ を足して 文字〕）。打っていない
    # 字を足す手は候補が広すぎる——う挿入（48-KV/48-OP）・同じ行の並記
    # （48-LQ）の持ち場に任せる。`ins` は作るだけ（F2 の候補の材料）
    # **゛の段が隣のキーより先**（項目48-SJ・2026-09-06。48-OQ(e') の費用
    # ——濁点 0.3・位置ずれ 0.8・隣のキー 1.0。readcheck の `めさす`〔材料
    # めざす〕は す→き の隣のキー〔目先〕が ゛を戻す手〔目指す〕より先に
    # 組めていた）
    tiers = [[run], mark, cheap, drop, far]

    def _grammar_ok(surf, v=None):
        """組み上がりが文の形か（品詞対と自然さ・項目48-LU）。"""
        if tokenize_fn is None:
            return False
        try:
            ts = tokenize_fn(surf)
        except Exception:
            return False
        if not ts or ''.join(t[0] for t in ts) != surf:
            return False
        if any(not t[5] for t in ts):
            return False            # 未知語を作らない
        prev = ''
        prev_infl = ''
        for t in ts:
            pos = t[1] or ''
            # **動詞の直後に動詞・名詞は文にならない**（置く往く固定）
            if prev.startswith('動詞') and (pos.startswith('動詞')
                                            or pos.startswith('名詞')):
                return False
            # **名詞の直後の ます・た 系も文にならない**（入力未定ます）
            if prev.startswith('名詞') and pos.startswith('助動詞') \
                    and t[0] in ('ます', 'ました', 'ません', 'た'):
                return False
            # **動詞の基本形（終止形）の直後の です・ます も**（項目48-SJ・
            # `目指すです`。活用形は t[6]・48-NT）
            if (prev.startswith('動詞') and prev_infl == '基本形'
                    and pos.startswith('助動詞')
                    and t[0] in ('です', 'でした', 'ます', 'ました')):
                return False
            prev = pos
            prev_infl = (t[6] if len(t) > 6 else '') or ''
        # **「する」にならない名詞に し／して を付けない**（48-OQ(d)・
        # `タブ以降して`）——判定は `_suru_attach_ok` の1本
        try:
            if not _suru_attach_ok(surf, tokenize_fn):
                return False
        except Exception:
            pass
        # 仕上げは自然さ（字の並び）。明らかに自然になる組だけ。
        # **共通の尾は除いて比べる**（項目48-SC）——尾（みています）は
        # 打ったまま残るので、比べるべきは変えた頭だけ
        k = 0
        while (k < min(len(run), len(surf)) - 1
               and run[-1 - k] == surf[-1 - k]):
            k += 1
        b0 = run[:len(run) - k] if k else run
        a0 = surf[:len(surf) - k] if k else surf
        if not a0 or not b0:
            a0, b0 = surf, run
        try:
            # 組み上がり**全体**が字の並びとして異様でないこと
            # （`_looks_unnatural` は `参考` のような2字の語だけでも
            #  True と言うので、頭だけには掛けない）
            if _naturalness._looks_unnatural(surf):
                return False
            if _naturalness.comparable(b0, a0):
                return bool(_naturalness.is_more_natural(
                    b0, a0, min_gain=_naturalness.MIN_GAIN_READABLE,
                    default=False))
            return bool(_naturalness.worth_touching_readable(
                run, surf, default=False))
        except Exception:
            return False

    _pos_cache = {}

    def _lu_face_pos(face):
        """部品の表記の品詞（先頭の語・解析に聞く。無ければ ''）。"""
        if face in _pos_cache:
            return _pos_cache[face]
        got = ''
        if tokenize_fn is not None:
            try:
                _tf = tokenize_fn(face)
                got = (_tf[0][1] or '') if _tf else ''
            except Exception:
                got = ''
        _pos_cache[face] = got
        return got

    def _lu_clause_shape(pieces):
        """組み上がりが**句の形**か（上の注記の (a)(b)）。"""
        cs = [k for k in range(len(pieces)) if pieces[k][0] == 'c']
        if not cs:
            return False
        last = cs[-1]
        tail = ''.join(t[1] for t in pieces[last + 1:])
        if len(cs) == 1:
            return _lu_tail_shape(tail)
        if len(cs) > 2:
            return False
        c1, c2 = pieces[cs[0]][1], pieces[cs[1]][1]
        between = ''.join(t[1] for t in pieces[cs[0] + 1:cs[1]])
        if between:
            # 間は1字の格助詞（を・が・に・で・と・へ）だけ
            return (len(between) == 1 and between in 'をがにでとへ'
                    and (not tail or _lu_tail_shape(tail)))
        if c2 == '後':
            return True                         # カタカナ＋後（上で確かめ済み）
        if len(c2) >= 4 and all(is_katakana(_c) or _c == 'ー'
                                for _c in c2):
            return not tail or _lu_tail_shape(tail)
        try:
            import seed_japanese as _sj_cl
            if _sj_cl.is_unit(c1 + c2) is True:
                return not tail or _lu_tail_shape(tail)
        except Exception:
            pass
        # 2つ目＋尾がサ変（移動＋して）
        if tail and tail[0] in 'しさせ' and _lu_face_pos(c2).startswith(
                '名詞:サ変接続'):
            return True
        return False

    def _lu_tail_shape(tail):
        """最後の内容語の後ろの尾が、**2字以上の機能語／述語**か。"""
        if not tail or len(tail) < 2:
            return False
        if _lu_functional_only(tail) and _noun_tail_start(tail):
            # 1字の助詞だけの並び（へは・には）は不可——2字以上の
            # 機能語（して・になる・でした・ます）を1つは含むこと
            for fp in _LU_FUNCTIONAL:
                if len(fp) >= 2 and fp in tail:
                    return True
            return False
        if _lu_predicate_tail(tail, tokenize_fn):
            return True
        # 1字の格助詞＋述語（の＋みえた・が＋おわった）
        if tail[0] in 'のにをがでとへはも' and len(tail) > 2:
            return _lu_predicate_tail(tail[1:], tokenize_fn)
        return False

    def _tier_surfaces(variants):
        """その段の変種から組める表記（文の形になるものだけ）。"""
        surfaces = {}
        surf_var = {}
        for v in dict.fromkeys(variants):
            for surf, mn, pieces in seg_full(v):
                cset = tuple(t[1] for t in pieces if t[0] == 'c')
                if not cset or surf == run:
                    continue
                if not any(is_kanji(c) for c in surf):
                    continue        # 漢字に届く組だけ（かな→かなは別の道）
                # `後`（ご）は**カタカナの部品の直後**だけ（48-PQ の門）。
                # **内容語の直後の機能語は、名詞の直後に置けるもの**
                # （`_noun_tail_start`）か述語の尾（`_lu_predicate_tail`）
                # ——`以後て`・`ウソて` の て は動詞に付く助詞（実測の junk）
                _go_bad = False
                for _pk in range(len(pieces)):
                    _pv = pieces[_pk - 1] if _pk > 0 else None
                    if pieces[_pk][:2] == ('c', '後'):
                        if (_pv is None or _pv[0] != 'c'
                                or not all(is_katakana(_c) or _c == 'ー'
                                           for _c in _pv[1])):
                            _go_bad = True
                            break
                    if (pieces[_pk][0] == 'f' and _pv is not None
                            and _pv[0] == 'c'):
                        _fp = pieces[_pk][1]
                        if not (_noun_tail_start(_fp)
                                or _lu_predicate_tail(_fp, tokenize_fn)):
                            _go_bad = True
                            break
                # **内容語を3つ以上直に並べた組は採らない**（`タブ|以後|打て`
                # の junk・実測。複合名詞は2語まで、3語目は機能語を挟む）。
                # **名詞の部品の直後に、読みから組んだ動詞の部品は置かない**
                # （`巨人|書く`・実測。名詞に直付きしてよい述語は、打った
                # ままの尾〔`入力|みています`〕だけ——語の組み立てで動詞を
                # 生やすと、名詞＋動詞の当て推量が無限に作れる）
                _run_c = 0
                _prev_c = None
                for _pc in pieces:
                    if _pc[0] == 'c':
                        _run_c += 1
                        if _run_c >= 3:
                            _go_bad = True
                            break
                        if _prev_c is not None:
                            _pp = _lu_face_pos(_pc[1])
                            if _pp.startswith('動詞') or _pp.startswith('形容詞'):
                                _go_bad = True
                                break
                        _prev_c = _pc[1]
                    else:
                        _run_c = 0
                        _prev_c = None
                if _go_bad:
                    continue
                # ★★ **句の形をしている組だけ**（項目48-SC・readcheck で
                # 受け止めた門。育ち +46／初期 +45 の化けのほとんどが
                # **裸の1語**（`めさす → 目先`・`しごう → 思考`・
                # `つうく → 通過`）か **語＋語の当て推量**（`いらせんす →
                # 医科センス`・`せなかあせわ → 背中お世話`）だった）。
                # 裸の1語は芯の再構築の持ち場で、この道は**語の列**を組む:
                #   (a) 内容語が1つ → 最後の内容語の後ろに **2字以上の
                #       機能語／述語の尾**（参考|になる・入力|みています・
                #       解析|でした）。1字の助詞だけ（`上|へ|は`）は不可
                #   (b) 内容語が2つ → 間に格助詞（続き|を|話す）か、
                #       2つ目＋尾がサ変（タブ|移動|して）か、
                #       2つ目が世の中のカタカナ語4字以上（右|ダブルクリック）か、
                #       組んだ形が世の中の1語（`is_unit`）か、
                #       カタカナ＋後（スクロール|後）
                if not _lu_clause_shape(pieces):
                    continue
                # ★★ **内容語1つ＋です・ます・でした の組は、その語が本人の語彙の
                # solid のときだけ**（項目48-SK・2026-09-06・readcheck で受け止めた
                # 門）。`〜です` の枠は語の選びに何の証拠も足さない——索引の顔
                # （段1がただ1つ）で埋めると `びじょうです → 微笑です`・
                # `こくどです → 今度です` のように、届かない材料（2字の脱字・
                # 順序違い）に**もっともらしい別の語**を当てる。本人が使う語
                # （solid）なら「その語を書こうとした」と言える（`かいすせきでした
                # → 解析でした`）
                if len(cset) == 1 and mn < 3:
                    _lc = [k for k in range(len(pieces)) if pieces[k][0] == 'c'][0]
                    _tl = ''.join(t[1] for t in pieces[_lc + 1:])
                    # **索引の顔（強さ2）の1語は、尾がその語を述語にする形
                    # （サ変: し・する・させ・でき／になる・にする・となる）の
                    # ときだけ**（項目48-SK'。`参考|になる`・`外出|する`）。
                    # です・がありました・をみます・いきます のような尾は
                    # 語の選びに証拠を足さない——readcheck の枠で
                    # `つうく → 通過をみます`・`かんう → 簡易がありました`・
                    # `こくど → 今度` と、届かない材料に別の語を当てた。
                    # 本人の語（solid・強さ3）はどの尾でも今までどおり
                    if not (_tl and (_tl[:1] == 'し' or _tl.startswith((
                            'する', 'させ', 'でき', 'になる', 'になっ', 'になり',
                            'にする', 'にし', 'となる', 'とし', 'として')))):
                        continue
                # ★★ **手を当てた所が、機能語／述語の尾の中に在る組は採らない**
                # （項目48-SC・`probe_born_particle` で受け止めた:
                # `ほせいがきいた` は 0手で `補正がきいた` に組めない〔`きいた`
                # ＝聞く のイ音便を文法が説明できない〕のに、き→は の1手で
                # `補正が|はいた` が組めて通った。手は**語（内容語）の中**に
                # 当てるもの——打ったままの尾を手で作り替えて組む形は当て推量）
                if v != run:
                    _pos = 0
                    _bad_hand = False
                    _chg = _lu_changed_positions(run, v)
                    for _pc in pieces:
                        _a, _b = _pos, _pos + int(_pc[2])
                        _pos = _b
                        if _pc[0] == 'f' and any(_a <= _q < _b for _q in _chg):
                            _bad_hand = True
                            break
                    if _bad_hand:
                        continue
                old = surfaces.get(surf)
                if old is None or mn > old[0]:
                    surfaces[surf] = (mn, frozenset(cset), len(cset),
                                      pieces)
                    surf_var[surf] = v
        if surfaces:
            surfaces = {s3: val for s3, val in surfaces.items()
                        if _grammar_ok(s3, surf_var.get(s3))}
        if len(surfaces) > 1:
            # **同じ変種（同じ読み）から出た組どうしは、漢字の多い側**
            by_var = {}
            for s3 in surfaces:
                by_var.setdefault(surf_var.get(s3), []).append(s3)
            drop_s = set()
            for _v3, group in by_var.items():
                if len(group) < 2:
                    continue
                kc = {s3: sum(1 for c in s3 if is_kanji(c))
                      for s3 in group}
                mx = max(kc.values())
                tops = [s3 for s3 in group if kc[s3] == mx]
                if len(tops) == 1:
                    drop_s |= set(group) - {tops[0]}
            for s3 in drop_s:
                surfaces.pop(s3, None)
        if len(surfaces) > 1:
            # **強い組が1つだけなら、それ**（項目48-SC。solid の語だけで
            # 組めた形 3 は、索引の顔や世の中のカタカナ語で埋めた形 2
            # より強い証拠）
            top = max(val[0] for val in surfaces.values())
            strong = [s3 for s3, val in surfaces.items() if val[0] == top]
            if len(strong) == 1 and top >= 3:
                surfaces = {strong[0]: surfaces[strong[0]]}
        return surfaces, surf_var

    per_tier = [_tier_surfaces(variants) for variants in tiers]
    if collect is not None:
        # **候補一覧のための口**（`lu_run_candidates`・48-SF）——組めた
        # 表記を段ごとに積んで返す。脱字の段（`ins`）も候補には出す
        for _ti, (_sf2, _sv2) in enumerate(per_tier + [_tier_surfaces(ins)]):
            for _k3, _v3 in _sf2.items():
                collect.append((_ti, -_v3[0], _k3))
        return None
    # **かな→かな はこの道では受け入れない**（項目48-SB'・2026-09-06に外した）。
    # 7巡目で「濁点の位置ずれだけ」を受けたが、解析が壊れた連なりを
    # `と|くどく` と刻むので、変わった語の範囲が取れず門が立たなかった
    # （`これはとぐとくです → とくどく`・初期の readcheck）。位置ずれの
    # かな→かな は**芯の再構築**（`_moved_dakuten_fix`——窓が語の単位で来る）の
    # 持ち場（`つつぎをはなす → つづきをはなす` はそちらで届く・実測）
    def _a0(cands):
        """(A0) **直接隣り合う内容語の対（複合語の形）の共起**で裁く
        （かな×打ち 0.69 ／ かな×待ち 0.27——床 0.35・2倍の差）。"""
        if context_vec is None:
            return None
        scored = []
        for surf, (_mn, _cs, _n, pieces) in cands.items():
            best = 0.0
            for i2 in range(len(pieces) - 1):
                if pieces[i2][0] == 'c' and pieces[i2 + 1][0] == 'c':
                    try:
                        sim = context_vec.similarity(pieces[i2][1],
                                                     pieces[i2 + 1][1])
                    except Exception:
                        sim = 0.0
                    best = max(best, sim)
            scored.append((best, surf))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= 0.35 \
                and (len(scored) == 1 or scored[0][0] >= 2 * scored[1][0]):
            return scored[0][1], scored[0][0]
        return None

    # **安い段から見て、その段でただ1つならそれ**（④の選び方・項目48-SC）。
    # 段の中で拮抗したら、(A0) は**全部の段の候補**で裁く——複合語の対を
    # 本人の実績が知っているなら、手の段より強い証拠
    # （`かなちでのほせい`: 隣のキーの段は 各地での補正／適っでの補正 で
    #  拮抗、脱字の段の かな打ちでの補正 が かな×打ち 0.69 で勝つ）。
    # それでも決まらなければ、その段の中で (A) 周りの語 → (B) 語数
    for surfaces, surf_var in per_tier:
        if not surfaces:
            continue
        if len(surfaces) == 1:
            _s = next(iter(surfaces))
            _trace('組み直し', f'{run!r} → {_s!r}（{surf_var.get(_s)!r} を'
                               f'語の列として組んだ '
                               f'{[t[1] for t in surfaces[_s][3]]}・'
                               f'項目48-LU/48-SC）')
            return _s
        _all = {}
        for _sf2, _sv2 in per_tier:
            for k3, v3 in _sf2.items():
                _all.setdefault(k3, v3)
        got = _a0(_all)
        if got:
            _trace('組み直し', f'{run!r} → {got[0]!r}'
                               f'（拮抗を複合語の対の共起 {got[1]:.2f} で'
                               f'裁いた・項目48-LU）')
            return got[0]
        # (A) **周りの語**——組どうしの違いが「1語の入れ替わり」
        if context_vec is not None:
            common = None
            for _mn, cs, _n, _p in surfaces.values():
                common = cs if common is None else (common & cs)
            diffs = {}
            ok_frame = True
            for surf, (_mn, cs, _n, _p) in surfaces.items():
                d = cs - (common or frozenset())
                if len(d) > 1:
                    ok_frame = False
                    break
                diffs[surf] = next(iter(d)) if d else None
            if ok_frame and common:
                cand_words = [w for w in diffs.values() if w]
                if cand_words:
                    try:
                        sel = context_vec.pick_best_by_context(
                            cand_words, sorted(common))
                    except Exception:
                        sel = None
                    if sel:
                        for surf, w in diffs.items():
                            if w == sel:
                                _trace('組み直し',
                                       f'{run!r} → {surf!r}'
                                       f'（拮抗を周りの語 {sel!r} で'
                                       f'裁いた・項目48-LU）')
                                return surf
        # (B) **語数が最少**の組がただ1つなら、それ
        ns = sorted(val[2] for val in surfaces.values())
        if len(ns) > 1 and ns[0] < ns[1]:
            least = [s3 for s3, val in surfaces.items() if val[2] == ns[0]]
            if len(least) == 1:
                _trace('組み直し', f'{run!r} → {least[0]!r}'
                                   f'（拮抗を語数で裁いた・項目48-LU）')
                return least[0]
        _trace('組み直し', f'{run!r} → 拮抗 {sorted(surfaces)[:4]} は'
                           f'組まない（項目48-LU）')
        return None
    # **かな→かな はこの道では受け入れない**（項目48-SC・測って外した。
    # 文法の説明は緩く、`さとんこう`・`ももと` のような候補が並んで
    # 拮抗ばかりになった。かな→かな は 芯の再構築（48-SB の位置ずれ
    # など）と 48-PO の持ち場）
    return None


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


#: 拗音の小書き3文字（項目48-MX）。ゃ・ゅ・ょ。
_SMALL_YOON = frozenset('ゃゅょ')


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
    # **拗音の小書きどうし**（ゃ・ゅ・ょ）は、どちらの入力でも
    # 1回の誤りで説明が付く（項目48-MX・2026-08-31）。
    #
    #   かな入力    や(0,6) ゆ(0,7) よ(0,8) の **隣り合う3キー**を
    #               Shift と一緒に押す。`kana_key_distance` は
    #               ゃ-ゅ・ゅ-ょ を 1.0 と答える（**この道は既に
    #               通っていた**）が、ゃ-ょ だけ 2.0 で落ちていた
    #   ローマ字    ya / yu / yo ——**同じ2字の枠の、母音1字違い**。
    #               `_KANA_TO_ROMAJI` で見ると o と u は
    #               QWERTY で隣ではない（間に i）ので落ちていた
    #
    # **同じ誤りが、入力の設定で通ったり通らなかったりしていた**
    # （学び22 の形）。3文字・3組の閉じた集まりなので、広がらない。
    #
    #     がいしょつする → **がいしゅつする**（うにさんの一覧。
    #       似た読みは がいしゅつ が 1.0 でただ1つ、次が 2.4）
    if a in _SMALL_YOON and b in _SMALL_YOON:
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

#: **1字の漢字の読み替え**の門（48-JG）を、**丸ごと1語**がくぐれる
#: 実績の床（48-LB → 項目48-NG・2026-09-01 に **10 → 2** へ下げた）。
#:
#: 48-JG が塞いでいる化けは `空白行 → 空白くい`(実績96) と
#: `高橋佑 → 高橋よう`(実績3)。**どちらも2語の組**で、丸ごと1語では
#: ない。48-LB はそこに気づいて「丸ごと1語で実績10以上なら通す」と
#: 抜け道を作ったが、**10 という数はうにさんの育ちの `平仮名`(16) に
#: 合わせただけ**で、初期状態の `平仮名`(2) は通れなかった:
#:
#:     雛仮名 → **ひらがな**（かな表記・実績2）が
#:              **平仮名**（実績2）に勝っていた
#:
#: 2 に下げて全部測ると、初期・育ちとも readcheck/fpcheck/seedcheck は
#: **差0**、実機メモは **+2行**（`雛仮名 → 平仮名`）で壊し0。
#: **床は「丸ごと1語かどうか」で効いていて、数では効いていなかった。**
_WHOLE_KANJI_FLOOR = int(os.environ.get('CN_WHOLE_FLOOR', '2'))


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
    # ★★ **読み損ねたときは、控えに入れない**（項目48-TV・2026-09-07）。
    # ここで空のまま控えると、**その版のあいだローマ字の道が丸ごと黙る**
    # ——語彙は在るのに「1語も知らない」ことになり、直るはずのものが
    # 静かに直らなくなる（★★ 黙って飛ばさない）。
    # 読めなかった回は「意見なし」で返し、次の呼びでやり直す。
    try:
        readings = store.all_readings()
    except Exception:
        return []
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
    for surface, pos, reading, start, end, has_reading, *_ in tokens:
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


#: **1字の機能語だけで説明してよい並びの長さの上限**（項目48-RS）。
#: これより長い並びを 1字の機能語だけで「説明が付く」とは言わない。
_ALL_FUNC_ONECHAR_MAX = 6


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
    # multi[i] = その説明に **2字以上の機能語が1つでも使われた**道が
    #            在るか（項目48-RS・2026-09-05）
    reach = [False] * (n + 1)
    multi = [False] * (n + 1)
    reach[0] = True
    for i in range(n):
        if not reach[i]:
            continue
        for tail in tails:
            if run.startswith(tail, i):
                j = i + len(tail)
                reach[j] = True
                if len(tail) >= 2 or multi[i]:
                    multi[j] = True
    if not reach[n]:
        return False
    # **1字の機能語だけの説明は、7字以上には認めない**（項目48-RS・
    # 2026-09-05・うにさんの指定「せ が ゛ の隣接打ち間違いを疑う」の
    # かな欄）。1字の機能語は **44 字**あるので、長い並びは何でも
    # 「か・い・せ・き・か・せ・な・か・せ・く」と説明が付いてしまい、
    # `かいせきかせなかせく`（壊れている）も `かいせきがながく`（正しい
    # 読み）も**同じ門で読める扱い**になって、①が立たなかった。
    # 実機メモで数えると、1字だけで説明される 5字以上の連なりは 26 種、
    # うち **7字以上は 4 種で全部この族**（5〜6字は `になっていて`・
    # `がおわった` のような正しい並び）。**5〜6字は今までどおり。**
    if n > _ALL_FUNC_ONECHAR_MAX and not multi[n]:
        return False
    return True


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
    multi = [False] * (n + 1)   # 2字以上の機能語を使った道が在るか（48-RS）
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
                j = i + len(tail)
                reach[j] = True
                if len(tail) >= 2 or multi[i]:
                    multi[j] = True
    if not reach[n]:
        return False
    # **1字の機能語だけの説明は7字以上には認めない**（項目48-RS・
    # 2026-09-05）——`_is_all_functional` と同じ門。かな欄の
    # `かいせきかせなかせく` はあちらを抜けたあと、こちらが
    # 「か（送り仮名）＋い・せ・き・か・せ・な・か・せ・く」で止めていた
    # （学び22——兄弟の門に同じ規則を掛ける。送り仮名の頭は1字の
    # 機能語には数えない＝多字の道には数えない）
    if n > _ALL_FUNC_ONECHAR_MAX and not multi[n]:
        return False
    return True


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


# --- 項目48-MF: **補正の範囲は、空白を跨がない**（2026-08-31）--------
#
# うにさんの画面（v1.3.0 の初期状態）に書かれていた:
#
#     「・**赤い補正範囲がタブスペースに掛かっている**」
#
# 行を丸ごと直し直す道（濁点の合成・括弧・Shift の押し忘れ・読みの
# 併合…**10か所ある**）は、直したあとで **`difflib` に元の行と
# 突き合わせさせて**「変わった範囲」を作っていた。`difflib` は
# 文字の並びしか見ないので、**タブを平気で跨ぐ**:
#
#     元   にゆうりよくみす<TAB>にゅうりょくみす<TAB>入力ミス
#     後   入力ミス<TAB>入力ミス<TAB>入力ミス
#     範囲 [0:17] = 'にゆうりよくみす<TAB>にゅうりょくみす' ⇒ '入力ミス'
#          [22:22] = '' ⇒ '<TAB>入力ミス'          ← 幅0の差し込み
#
# 直した**文字列**は正しいのに、**どこを直したか**が壊れている。
# 画面の赤はここから引くので、タブの上まで塗られる。「この補正は
# 不要」「今後直さない」も**この対を覚える**ので、覚える中身まで
# タブ混じりになっていた。
#
# 直し: **空白（タブ・半角空白・全角空白）で区切って、区画ごとに
# 突き合わせる。** 空白の並びが前後で同じなら区画は1対1に対応する
# ので、区画の中だけで差を取れば範囲は空白を跨げない。空白の並びが
# 変わった行（空白そのものを直した行）は、今までどおり行ごと突き
# 合わせる——**そこは空白が直しの中身**なので跨いでよい。
#
# **直した文字列は1文字も変わらない**（範囲の付け方だけの話）。
_WS_RUN = re.compile('[ 	　]+')


def _split_on_space(text):
    """空白の連なりで割る。戻り値は ([(始まり, 終わり), ...], [区切り, ...])。"""
    parts, seps, i = [], [], 0
    for m in _WS_RUN.finditer(text):
        parts.append((i, m.start()))
        seps.append(m.group(0))
        i = m.end()
    parts.append((i, len(text)))
    return parts, seps


def _map_inner_spans(outer, inner_line, spans):
    """
    **入れ子で通した行の印（紫・unsure）を、外の行の位置へ写す**
    （項目48-RU・2026-09-05）。

    `correct_line` は「行を組み替えて自分をもう一度通す」入れ子を
    10か所持つ（遅れた濁点・場違いな濁点・異様の塊の先直し・英字…）。
    どれも内側の `odd_spans` を **`[]` に捨てて**いた（座標が違うので
    そのまま渡せない、と注記だけして）。その結果、**同じ行に直しが
    1つ在ると、直っていない別の塊の紫まで消えていた**——
    `・「解析課背中セク、」は、まず「背中セク」が…` で前の塊を
    `解析が長く、` に直したら、後ろの `背中セク` の紫が落ちた
    （触る前は `乳リュク見ていますと背中セク → 入力見ていますと背中セク`
    でも同じ）。**直せなくても印は立てる**（CLAUDE.md ★★）に反する。

    写し方は `_diff_spans` と同じ difflib の並び。内側の位置は
    `inner['original']`（内側に渡した行）の上に在るので、外の行との
    **equal の塊の中に丸ごと入る印だけ**を、その塊のずれで写す。
    組み替えた（直した）範囲に掛かる印は写さない＝「直せた範囲は
    消える」（`_odd_spans_for_line` の決まり）と同じ結果になる。
    **答えは1文字も変えない**（印の位置だけ）。
    """
    if not spans:
        return []
    if outer == inner_line:
        return list(spans)
    try:
        import difflib as _dl
        eq = [(i1, i2, j1, j2) for tag, i1, i2, j1, j2
              in _dl.SequenceMatcher(None, outer, inner_line,
                                     autojunk=False).get_opcodes()
              if tag == 'equal']
    except Exception:
        return []
    out = []
    for a, b in spans:
        for i1, i2, j1, j2 in eq:
            if j1 <= a and b <= j2:
                out.append((a - j1 + i1, b - j1 + i1))
                break
    return out


def _diff_spans(before, after):
    """
    元の行と直した行の差を **[(元の始まり, 元の終わり, 後の始まり,
    後の終わり), ...]** で返す（項目48-MF）。**空白を跨がない。**
    """
    import difflib

    def _plain(b, a, off_b=0, off_a=0):
        out = []
        sm = difflib.SequenceMatcher(None, b, a, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            out.append((i1 + off_b, i2 + off_b, j1 + off_a, j2 + off_a))
        return out

    pb, sb = _split_on_space(before)
    pa, sa = _split_on_space(after)
    if len(pb) != len(pa) or sb != sa:
        # 空白の並びが変わった＝空白そのものが直しの中身。行ごと見る。
        return _plain(before, after)
    out = []
    for (b0, b1), (a0, a1) in zip(pb, pa):
        if before[b0:b1] == after[a0:a1]:
            continue
        out.extend(_plain(before[b0:b1], after[a0:a1], b0, a0))
    return out


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


def _rest_is_own_word(rest, store):
    """
    芯の後ろに残った並びが、**それ自体で1つの語**か（項目48-NU）。

    「終わりの字を保つ」制限は、**芯が語幹の途中で切れている**ことを
    前提にしている（`あらゆ`＋`る`）。後ろが `こてい`(固定) のように
    独立した語なら、その前提が無いので制限も要らない。

    **3字以上・実績2以上**に限る。2字だと `てい`・`こと` のような
    語尾や形式名詞を拾って、語の途中で切ってしまう。
    """
    if not rest or len(rest) < 3:
        return False
    try:
        return any(en['count'] >= 2 for en in store.lookup(rest))
    except Exception:
        return False


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
    # --- 項目48-NU: **後ろが既知語なら、その手前も芯にする**
    #     （2026-09-01）------------------------------------------
    #
    # 上の注記は「逆向きはやって、`きのままでよい` で壊したので
    # やめた」と言っている。**壊れた理由は注記自身が書いている**
    # ——「前側は語の途中から始まっていることが多く（**直前の
    # 漢字の送り仮名**）」。つまり**壊したのは `after_kanji` の
    # ときだけ**で、族ごと捨てる理由ではなかった（★★
    # 「壊れるリスクを恐れすぎて前へ進んでない」）。
    #
    #     きのままでよい   ← `色付き` の**送り仮名から始まる**窓。
    #                       前側は語の途中なので信用できない
    #     おくゆくこてい   ← **独立したかな連続**。頭は語の頭
    #                       `こてい`(固定) が既知なので、直すのは
    #                       手前の `おくゆく` → `おくゆき`(奥行)
    #
    # なので**独立したかな連続のときだけ**開ける。切り離す後ろは
    # **3字以上の既知語**（実績2以上）に限る——2字だと機能語や
    # 語尾（`てい`・`こと`）を拾って、語の途中で切る。
    def _known_kanji_word(frag):
        """
        その並びが、**本人が漢字で書く語**か（項目48-NU）。

        `_known`（実績2以上）だけでは、**かなで書く語**まで境目に
        なってしまい、語の途中で切る（実測で2つ壊した）:

            こてい   → **固定**(99)    ← 漢字で書く。境目にしてよい
            どうして → どうして(35)    ← かなで書く副詞。境目にしない
                       （`たぶいどうして` を `ぶたいどうして` に壊した）
            くみす   → くみす(4)       ← かなで書く動詞。境目にしない
                       （`にゅうりょくみす` を `入力くみす` に壊した）

        **漢字で書く語がかなのまま並んでいる**というのが、
        「ここで切ってよい」の証拠。かなで書く語は、ふつうに
        かなで並んでいるだけなので証拠にならない。
        """
        try:
            return any(en['count'] >= 2
                       and any(is_kanji(c) for c in (en['surface'] or ''))
                       for en in store.lookup(frag))
        except Exception:
            return False

    _known_tail_at = None
    if not after_kanji:
        for i in range(min_len, n - 2):
            if _known_kanji_word(window[i:]):
                _known_tail_at = i
                push(0, i)
                break

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
    # **既知語の途中で切れる芯は落とす**（項目48-NU・2026-09-01）。
    #
    # `おくゆくこてい` は末尾の剥がしが貪欲すぎて `くこてい` を
    # 語尾とみなし、芯が `おくゆ` になっていた。残る `くこてい` は
    # **既知語 `こてい`(固定) の1字手前から始まる**——語尾ではなく、
    # **語の途中を切っている**。そこから直すと、終わりの字を保つ
    # 制限と噛み合って `おゆ`(お湯) に削られ、
    # **`おゆくこてい` に化けていた**（育ちの実機メモ）。
    #
    # 後ろに既知語が立っているなら、芯はその**手前で終わる**か、
    # **その語ごと含む**かのどちらかしかない。
    if _known_tail_at is not None:
        _cut = [(x, e) for (x, e) in out if e < _known_tail_at]
        if _cut and len(_cut) < len(out):
            _trace('芯', f'{window!r} → 後ろの {window[_known_tail_at:]!r} '
                         f'は既知語なので、その途中で切れる芯 '
                         f'{[window[x:e] for x, e in _cut]} は落とす'
                         f'（項目48-NU）')
            out = [(x, e) for (x, e) in out if e >= _known_tail_at]
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
            # **2字の漢字の顔は段で決める**（項目48-OJ・2026-09-02）。
            # 索引が 2字漢語の帯（5600まで）を持つようになったので、
            # 先頭をそのまま採ると 主導性・語彙性・妻帯化時 が出た（実測）。
            # 2字以外の顔（引き継ぎ・カタカナ語 …）は今までどおり先頭
            # **帯は見ない**（`band=False`・項目48-OJ）。この関数は造語の道
            # （①が立っていない）からも呼ばれる——帯を見せると
            # `未提示 → 未定時`（未定 は帯の語）。2字の顔の順位は段のまま
            for s in _surfaces_no_band(dict_index, stem):
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
    ★★ **もう誰も呼んでいない**（項目48-QG'・2026-09-05）。
    最終使用時刻を記録しなくなり、弱まりそのものを廃止したため。
    `CORRECTNOTE_NOW` を置いても、補正の答えはもう動かない
    ——**時計で答えが変わることが無くなった**のがこの巡の副産物。
    残してあるのは、道具（`measure.sh`）が置く環境変数の意味を
    ここで説明しておくため。以下は廃止前の説明。

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
    その読みの「使われぶり」。

    ★★ **日数による弱まりは廃止した**（項目48-QG'・2026-09-05）。
    最終使用時刻（`last_seen`）を記録しなくなったので、
    「最近使ったか」は**もう誰も知らない**——うにさんの指定
    「履歴として記録されることをユーザは望みません」の帰結。

    残るのは「立っているか」だけなので、この値は **1 か 2** しか
    取らない（`_USAGE_CAP` は当たらない）。つまり

        `< _USAGE_MIN`（20）      … **常に成立する**
        `< 二番手 × _USAGE_DOMINANCE`（4倍）… 1 と 2 では成立しない

    ＝ **`_break_tie_by_usage` と `_break_tie_by_generality` の
    `_USAGE_MIN` の門は、これ以降は必ず「決めない」に落ちる。**
    落ちた先は「決めずに次へ渡す」＝安全側なので、そのまま受ける。

    **初期状態では、この関数は前から 1〜2 しか返していない**
    （辞書から取り込んだ語は count 1・種は 2・どちらも入れたばかりで
    弱まりが掛からない）。だから**初期状態の答えは 1 つも変わらない**
    ——変わるのは育った語彙のほうだけ（§4 の「代償」そのもの）。

    「一般的さ」で決めたい場所は `_general_count`（world と費用の表を
    見る）へ寄せること。**こちらには一般度の情報が無い。**
    """
    try:
        entries = store.lookup(reading)
    except Exception:
        return 0
    if not entries:
        return 0
    best = 0
    for e in entries:
        n = min(e.get('count', 0), _USAGE_CAP)
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

    ★★ **回数を廃したので、実質は `world`（世の中での使われぶり）
    だけになった**（項目48-QG'・2026-09-05）。取りうるのは
    {1, 2, 5, 20} ——1/2/5/20 は取り込みの帯（書籍での上位 16%／34%／
    78%／残り）で、種の語と立った語はここに 2 の下限が乗る。
    **初期状態では前から count が 1〜2 しかないので、初期の答えは
    1つも変わらない**（変わるのは育った語彙のほう）。

    `_usage_count` との違い（**使い分けること**）:

        _usage_count    立っているか（1 か 2）。**一般度を知らない**
        _general_count  「一般的さ」。**world の帯**。よく使う語か

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


def _break_tie_by_generality(candidates, store, loose=False):
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
    # **読めない芯では下限を求めない**（項目48-IS・loose）。初期状態の
    # 回数は 1〜3 で、20 には届かない。`すきにん` の候補
    # かくにん(確認 3回)・しんにん(新任 1回)・すきゃな(1回) は
    # 3 対 1 で「確認」が一般的——それで決めてよい（読めない並びは
    # 正しく書けた語ではないので、駅名の読みがなの巻き添えは起きない）。
    #
    # loose では、先に**同梱の表の費用**（世の中でよく使う順）で決める。
    # `びっり` の候補 びっくり(95)・びっしり(133)・びっちり(133) は
    # 回数も world も同じで、字の頻度では びっしり が勝っていた。
    # 表の費用が最小のものが1つなら、それを採る。
    if loose:
        # ★★ **費用が同点のときだけ、段（`kango_tier`・AI の判断）で
        # 決める**（項目48-QG'・2026-09-05）。うにさんの指定
        # 「一般的か、自然か、もっともらしいか、**このような主観の
        # 判断は AI の能力を活かす**」（48-OJ）。
        #
        # 費用表は**2字の漢語に同点が多い**——`確認` も `新任` も
        # **101**。回数を廃す前は、育った字の並びの表（`charngram`）が
        # 偶然そこを裁いていたが、そちらも初期分だけにしたので
        # （48-QL）、**`すきにん → 新任` に倒れた**（移行したあとの
        # 実機メモで実測）。段で見れば 確認=1（日常語）・
        # 新任=2（一般語）で割れる。
        #
        # **段を第1の軸にする形は測って外した**——初期で 直り −4／
        # 化け +2（`まいす` が `麻酔`〔段1〕に負けて `ますい` に）。
        best_key = None
        best_rd = None
        tie = False
        for r, _c, _e in candidates:
            try:
                keys = [(_table_cost(e['surface']), _kango_tier_of(e['surface']))
                        for e in store.lookup(r)]
            except Exception:
                keys = []
            keys = [k for k in keys if k[0] is not None]
            if not keys:
                continue
            k = min(keys)
            if best_key is None or k < best_key:
                best_key, best_rd, tie = k, r, False
            elif k == best_key:
                tie = True
        if best_rd is not None and not tie:
            return best_rd
    # ★★ **この門は、回数を廃した今は必ず成立する**（項目48-QG'）。
    # `_usage_count` は 1 か 2 しか返さない（`last_seen` を廃止して
    # 弱まりを掛けなくなり、`count` は solid の写しになった）ので
    # `< 20` は恒真＝**読める芯の側（loose=False）では、この関数は
    # 必ず「決めない」に落ちる**。落ちた先は「直さない」＝安全側。
    # **初期状態では前からそうだった**（初期の count は 1〜3 で
    # 20 に届かない）ので、初期の答えは1つも変わらない。
    # 一般度で復活させるなら `_general_count`（world）で測り直すこと
    # ——ヒューリスティックなので、★★のとおり**測って**から入れる。
    if not loose and _usage_count(scored[0][1], store) < _USAGE_MIN:
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
    # ★★ **恒真になった**（項目48-QG'）。`_usage_count` は 1 か 2。
    # ＝ `_prefer_general`（打鍵の近さでは二番手でも、桁違いによく使う
    # 語があればそちらへ）は**この巡から働かない**。倒れる先は
    # 「費用がいちばん安い候補をそのまま採る」＝補正は実行される。
    # **初期状態では前から働いていない**（count 1〜3）。
    # うにさんの `たこご → たまご(費用1.0) ではなく たんご(単語1312回)`
    # は**育った回数の話**で、回数を廃した以上そのままでは戻せない。
    # 復活させるなら world／同梱の費用表で測り直す（巡3）。
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
    # ★★ **恒真になった**（項目48-QG'）。`_usage_count` は 1 か 2 で
    # 20 に届かない＝**`_break_tie_by_usage` はこの巡から必ず None**。
    # 芯の拮抗の裁定から「本人の使用実績」の段が抜け、次の段
    # （`_core_is_unnatural` → `_break_tie_by_generality` →
    #   異様と判定した側なら 字の並び・読みの並び・字の頻度・先頭）へ
    # 落ちる。**異様な芯では最後に必ず何かしら決まる**ので、
    # うにさんの「異様だと判定したら何かしらに決める」は保たれる。
    # **初期状態では前からそうだった**（count 1〜3）。
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


# ====================================================================
# **項目48-KH（正の判定）は、うにさんの指示で「無効」にしてある**
# ====================================================================
# うにさんの指示（2026-08-28）:
#
#     「外しましょう。**ただし、まだ消しません。無効にして、
#       読まれないようにします。意図的にその状態にしてることが
#       わかるようにする**」
#
# なぜ外せるようになったか——**項目48-KP（K3）で根が直った**。
# 48-KH は `切り替え時 → 切り返し` を止めるために置いた
# **迂回**（「この塊は品詞の並びとしてできあがっている」と
# 先に言って、補正の道を走らせない）だった。止めていた本体は
#
#     `替` の音訓に `かえ` が在り、本文の送り仮名 `え` と繋ぐと
#     **`きりかええじ`（え が二重）** という読みを作っていたこと
#
# で、48-KP がその読みを作るところで直した。**迂回を外して測っても
# `切り替え時` は無傷**（更新したファイル_Fable_20260828c.md §6c）:
#
#     K3 前 ＋ 迂回を切る   切り替え時… → **切り返し**…  ← 壊れる
#     K3 後 ＋ 迂回を切る   切り替え時… → **切り替え時**… ← 無傷
#
# **消していない。** `oddness.is_sound_run` はそのまま在る。
# 戻すなら**この旗を True にするだけ**。
#
# 48-KI（**補正の入口を1つにする**）という**構えは残っている**
# ——`_chunk_is_intact` はこれからも入口で、新しい「できあがり」の
# 判定はここへ入れる。いま**中身が空**なだけ。
_USE_48KH_SOUND_RUN = False     # ← **意図的に切ってある**（上の説明）


def _chunk_is_intact(chunk, tokenize_fn, after_kanji=False,
                     starts_inside_word=False):
    """
    **その塊は、もうできあがっているか**（＝補正を走らせない）。
    **決めているのはこの1か所**（項目48-KI・2026-08-27）。

    うにさんの指定（2026-08-27）:

        「自然な文ができたら、そこから文字の重複を削って考えてみるなど、
          **補正をする必要はありません**。補正が動くのは**異様な文字列
          だけ**で、**自然な文に対しては実行しなくてよい**です」

    いままでは逆で、**どの道も「できあがっているか」を見ずに走り、
    道ごとに別々の断り方**をしていた。今日3回、同じ形で踏んだ:

        切り替え時 → 切り返し      芯の再構築が「読めない読み」で動いた
                                   （正しい読みの側は自分で断れていた）
        鍵括弧    → 過括弧        設計46 を試したときに出た
        語彙読込  → 語彙詠込め    同上

    **48-GN の教え**「同じ判定をもう一度書くと、いつか食い違う」
    そのもの。**だから入口を1つにする。**

    実測（`tools_local/diag_odd_gate.py`・2026-08-27）:
    実機メモでいま変わる行のうち、**この判定が立つ行は 0**
    （初期171行・育ち185行とも）。**入れても失うものが無い。**

    **いまは中身が空**（2026-08-28・うにさんの指示）。唯一在った
    48-KH（正の判定）は `_USE_48KH_SOUND_RUN = False` で切ってある
    ——48-KP で根が直り、迂回が要らなくなったため（上の説明）。
    **入口という構えは残す。** 道ごとに散らばっている断り方
    （`_reading_intact`・`打った読み＝解析の読み`・`_run_is_word`）を
    ここへ移すのは K1 のまま。移すだけなら答えは変わらないはずで、
    **変わったらそれが食い違いの証拠**になる。
    """
    if not chunk or len(chunk) < 2:
        return False
    # 48-VK: 漢字の直後の「送り仮名＋機能語」は既存の判定を借りる。
    # 順序入れ替えもこの入口を通す。頭2字だけ守っても「初めでした」の
    # 後ろの「した」が動いてしまう。文全体の解析と同梱表が語の途中だと
    # 言う場合だけ。漢字の直後という位置だけで送り仮名を仮定しない。
    if (after_kanji and starts_inside_word
            and _okurigana_functional_only(chunk, any_head=True)):
        return True
    # ★★ (A) **同梱の表が「1語として在る」と言うなら、できあがっている**
    #     （項目48-UI・2026-09-07）。
    #
    #     この門は 48-FC（2026-08-21）から在ったが、**造語の道にだけ**
    #     掛かっていた。`tools_local/probe_seed_intact.py` で表の語を
    #     1語ずつ当てたら、**入口を通る道が丸ごと素通り**していた:
    #
    #       キングブリザード → **ハングブリザード**（設計27・48-LA）
    #       ヤングクリケット → **ハングクリケット**
    #       ノースサンド → **コースサンド**  ジョーホール → **ショーホール**
    #
    #     ★★ 入口は1か所（この関数の役目そのもの）。ここに置けば
    #     **この入口を通る道**（`_resolve_reading_list`・
    #     `_resolve_reading_seq`・`_reopen_odd_chunk` ほか）には全部効く。
    #     ★ **ただし全部の道がここを通るわけではない**（検品で指摘・
    #     2026-09-07）。漢字塊の輪・混合塊の輪・`_resplit_by_elements` は
    #     `_chunk_is_intact` を呼ばないので、**48-UG／48-UG'／48-UG''' の
    #     門は要る**（外すと `小川忠 → コンチュウ` が戻る）。
    #     名簿は1つ（`seed_japanese.is_unit`）なので食い違わない。
    #
    #     `is_unit` は **None を返すことがある**（表が読めない）。
    #     `is True` で見て、None は「意見なし」＝今までどおり。
    try:
        import seed_japanese as _sj_in
        if _sj_in.is_unit(chunk) is True:
            return True
    except Exception:
        pass
    # (0) **動作の語＋「中/時」でできあがっている**（項目48-LP・
    #     2026-08-30）。変換中・解析中・起動時——うにさんの画面の誤検知
    #     `変換中 → 変換かな`（読み へんかんなか の なか⇄かな 入れ替えを
    #     語の組が拾い、近くの 変換・かな で裏が取れてしまった）を
    #     ここで止める。
    #
    #     頭は**単位の表の語**かつ**サ変の名詞**に限る——「〜中・〜時」が
    #     付くのは動作の名詞で、`囚虜時`（頭は表に在るが 名詞:一般）の
    #     ような誤変換まで守ってしまわないため（最初の版で
    #     `囚虜時 → 終了時` の ◎ を1つ失って絞った・実測）。
    #     接尾も測った2字（中・時）だけ。増やすのは測ってから。
    if len(chunk) >= 3 and chunk[-1] in '中時':
        try:
            import seed_japanese as _sj0
            if _sj0.is_unit(chunk[:-1]) is True:
                _hd = tokenize_fn(chunk[:-1])
                if (len(_hd) == 1
                        and (_hd[0][1] or '').startswith('名詞:サ変接続')):
                    return True
        except Exception:
            pass
    # (1) **何にでも自由に付く1字が末尾に来ている**（項目48-ME・
    #     2026-08-31）。うにさんの画面の誤検知 `一番下に → 一番化に`。
    #
    #     解析は `一番下` を **一番（名詞）＋下（名詞:接尾）** と読み、
    #     しかも **下 の読みを `か`** と言う（支配下・管理下 の か）。
    #     造語の道（48-EX）はその読み `いちばんか` を**そのまま**
    #     `一番`＋`化` と綴り直して `一番化` を作っていた。
    #     **誤打はひとつも直していない**——同じ読みの別の綴りに
    #     置き換えただけ。
    #
    #     `oddness.can_join` は既に「**名詞＋位置の1字**は繋げてよい」
    #     （6-3'）と言っている——画面に紫も出ていない。**判定は
    #     立っているのに、造語の道がそれを見ずに走っていた**
    #     （CLAUDE.md ★★④「できあがっている塊には、どの道も
    #     走らせない」・項目48-KI の入口はここ）。
    #
    #     **名簿は作らない。** `oddness` の閉じた3つの類をそのまま
    #     借りる（位置の1字 `上下左右…`・区画の1字 `行欄列枠桁段頁`・
    #     形と集合の1字 `塊群層列束片団帯`）。**どれも「何にでも
    #     自由に付く」と既に書かれている類**なので、その1字で
    #     終わる塊は、頭が語であればもうできあがっている。
    #
    #     的を落とさないことは形で分かる——うにさんの直したい塊
    #     （殺意代価・再退化・誘い消化・小売り坂・背景食・最大家事）は
    #     **どれもこの3つの類の字で終わっていない**。
    if len(chunk) >= 3 and all(is_kanji(c) for c in chunk):
        try:
            import oddness as _odd1
            if (chunk[-1] in _odd1._POSITION_KANJI
                    or chunk[-1] in _odd1._LAYOUT_KANJI
                    or chunk[-1] in _odd1._AGGREGATE_KANJI):
                import seed_japanese as _sj1
                if _sj1.is_unit(chunk[:-1]) is True:
                    return True
        except Exception:
            pass
    # (2) **動詞の活用列としてできあがっている**（項目48-PX・
    #     2026-09-04 → **48-QV で広げた**・2026-09-05）。
    #     もとは 未解決.txt の注記の行（`糸を察して → 意図をさして
    #     （触る前は「意図を察して」…）`）で、壊れた形の見本が**並記**に
    #     なり、正しい側の `察して` が `さして` に壊された。
    #
    #     `察し`（連用形）＋`て`（接続助詞）は**完成した接続形**——
    #     文法がそう決めている（★★「論理的に正しいものは重ねる」）。
    #     読みを変える手で別の語に置き換えるのは補正ではない。
    #
    #     ### ★★ 48-PX が「2トークンちょうど」だったので抜けていた
    #
    #     うにさんの実機で **`見ていない → 検定ない`**（2026-09-05）。
    #     4トークンとも品詞は正しい——
    #     見[動詞:自立/連用形] て[助詞:接続助詞] い[動詞:非自立/未然形]
    #     ない[助動詞]。**文法として完成した列**なのに、`見てい` の
    #     3トークンが「2ちょうど」を外れて素通りし、`語の組` が
    #     **音音で開いて** `けん`＋`てい` ＝ `検定` に置き換えていた
    #     （設計23 の「元は非単位だから通す」で届いた）。
    #     **紫は1つも立っていない**——①（異様か）が立たないのに
    #     走る道が残っていた（CLAUDE.md ★★ の順番そのもの）。
    #     同じ形で `書いていない → 海底ない`・
    #     `見ていなかった → 検定なかった` も壊れていた（実測）。
    #
    #     **て/で のあとに続くのは、閉じた文法の類だけ**——
    #     補助動詞（動詞:非自立。い・いる・いく・おく・くれ・しまう・
    #     みる・ください）／助動詞（ない・た・ます・たい・なかっ）／
    #     もう1つの接続助詞 て・で（持っていって）。**名簿は作らない。**
    #     この形に**きれいに割れること自体**が「打ち損ねの塊ではない」
    #     という証拠になる——誤打の塊は 動詞:自立連用形＋接続助詞 の
    #     頭を作れない。
    #
    #     **守るべき的は当たらない**（形で分かる・実測でも確かめた）:
    #       `差釣れません`      差[名詞:一般] が頭 → 動詞:自立ではない
    #       `かいすせきがおわった` かいす[基本形]＋せき[名詞] → て が無い
    #       `解す咳`・`囚虜時`   て が無い
    #     **末尾が言い切りである必要は無い**——呼び手は `見てい` のような
    #     途中までの塊を渡してくる。**そこまでが正しく割れている**なら、
    #     それは打ち損ねではない。
    try:
        _tk2 = tokenize_fn(chunk)
    except Exception:
        _tk2 = None

    # 48-VR: 辞書にある普通名詞＋既存の派生接尾辞は完成した語。
    # 補正先を組む表と同じ _SUFFIX_SURFACE を使う（別の名簿は作らない）。
    # 時・中などの副詞可能な接尾辞や、人名・接頭辞からの推測は含めない。
    # 候補の文字頻度が高いというだけで、正常な語幹を読み替えない。
    if (_tk2 and len(_tk2) == 2
            and _tk2[0][1] in ('名詞:一般', '名詞:サ変接続', '名詞:形容動詞語幹')
            and _tk2[1][1] in ('名詞:接尾:一般', '名詞:接尾:形容動詞語幹')
            and _SUFFIX_SURFACE.get(_tk2[1][2]) == _tk2[1][0]
            and all(t[5] for t in _tk2)
            and ''.join(t[0] for t in _tk2) == chunk):
        try:
            from seed_japanese import is_unit
            if is_unit(_tk2[0][0]) is True:
                return True
        except Exception:
            pass

    def _te_tail_ok(t):
        """て/で のあとに続いてよい類か（閉じた文法。名簿は作らない）。"""
        pos = t[1] or ''
        if pos.startswith('動詞:非自立') or pos.startswith('助動詞'):
            return True
        # 持っていって——接続助詞の て/で がもう一度来る形
        return pos.startswith('助詞:接続助詞') and t[0] in ('て', 'で')

    if (_tk2 and len(_tk2) >= 2
            and (_tk2[0][1] or '').startswith('動詞:自立')
            and ((_tk2[0][6] if len(_tk2[0]) > 6 else '')
                 in ('連用形', '連用タ接続'))
            and _tk2[1][0] in ('て', 'で')
            and (_tk2[1][1] or '').startswith('助詞:接続助詞')
            and all(_te_tail_ok(t) for t in _tk2[2:])
            and all(t[5] for t in _tk2)
            and ''.join(t[0] for t in _tk2) == chunk):
        return True
    # 48-VQ: 未然形＋接尾動詞は受身・可能・尊敬・使役の活用。
    # 「示さ＋れる」を別の語へ読み替えない。使役受身の接尾も、
    # 直前が未然形であることを確かめる。助動詞などを無条件に
    # 足して「示されるない」まで完成形にしない。
    if (_tk2 and len(_tk2) >= 2
            and (_tk2[0][1] or '').startswith('動詞:自立')
            and all(len(t) > 6 and t[5] for t in _tk2)
            and _tk2[0][6] == '未然形'
            and (_tk2[1][1] or '').startswith('動詞:接尾')
            and all(((_tk2[i][1] or '').startswith('動詞:接尾')
                      and _tk2[i - 1][6] == '未然形')
                    for i in range(2, len(_tk2)))
            and ''.join(t[0] for t in _tk2) == chunk):
        return True
    # (3) **連体詞＋名詞でできあがっている**（項目48-QX・2026-09-05）。
    #
    #     うにさんの実機で **`同じ字 → 叔父時`**。2トークンとも正しい——
    #     同じ[連体詞] 字[名詞:一般]。`造語` の道（設計18・48-EX）が
    #     読み `おなじじ` を開いて `な` を落とし、`おじじ` を
    #     `叔父`＋`時` と綴り直していた。**誤打はひとつも直していない。**
    #     紫も立っていない（①が立たないのに走る道・CLAUDE.md ★★）。
    #
    #     `芯` の道は**同じ材料で自分から断れていた**——
    #     「`おなじ` は、読める並びを覆すほど自然にならないので直さない」。
    #     **正しい読みの側は断れているのに、別の道が走っていた**＝
    #     48-GN の型そのもの。だから**入口**で止める。
    #
    #     連体詞は IPAdic の**閉じた小さな類**（この・その・あの・同じ・
    #     大きな・あらゆる・いわゆる…）。打ち損ねの塊が連体詞に割れる
    #     ことは無い——その並びが辞書にそのまま在るということだから。
    #     **名簿は作らない**（品詞名だけを見る）。
    #
    #     **守るべき的は当たらない**（どれも頭が連体詞ではない）:
    #       `囚虜時`（名詞＋名詞）・`解す咳`（動詞＋名詞）・
    #       `殺意代価`・`再退化`・`誘い消化`・`小売り坂`・`最大家事`
    if _tk2 and len(_tk2) == 2 \
            and (_tk2[0][1] or '').startswith('連体詞') \
            and (_tk2[1][1] or '').startswith('名詞') \
            and all(t[5] for t in _tk2) \
            and ''.join(t[0] for t in _tk2) == chunk:
        return True
    if not _USE_48KH_SOUND_RUN:
        return False        # **意図的に切ってある**（上の ==== の説明）
    try:
        import oddness as _odd
        if not _odd.available():
            return False
        # (1) 品詞の並びとしてできあがっている（項目48-KH）
        if _odd.is_sound_run(chunk, tokenize_fn):
            return True
    except Exception:
        return False
    return False


def _single_known_token(chunk, tokenize_fn):
    """**解析が1語の辞書語と読む塊か**（項目48-TB）。2字以上・読みが立つ・
    固有名詞ではない（人名・地名は 48-OR で信用しない）。"""
    if not chunk or len(chunk) < 2 or tokenize_fn is None:
        return False
    try:
        toks = [t for t in (tokenize_fn(chunk) or ()) if t[0]]
    except Exception:
        return False
    if len(toks) != 1:
        return False
    t = toks[0]
    if len(t) > 5 and not t[5]:
        return False
    if '固有名詞' in (t[1] or ''):
        return False
    return t[0] == chunk


# **数字の直後に来る、かなの助数詞**（項目48-TG）。長いものが先。
_KANA_COUNTERS = ('かげつ', 'かしょ', 'びょう', 'ほん', 'にん', 'だい', 'かい',
                  'ばん', 'まい', 'さつ', 'ひき', 'けん', 'はい', 'だん', 'つう',
                  'ねん', 'がつ', 'にち', 'ふん', 'えん', 'わり', 'ぶん', 'つ', 'こ',
                  'ど')


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
    # **塊そのものが、品詞の並びとして日本語になっているなら触らない**
    # （**正の判定**・項目48-KH・2026-08-27。うにさんの指定
    #  「切り替え時、が自然な文字列と判定されないことが問題です。
    #    これを正しいとする分析をします」）。
    #
    # `切り替え時` ＝ 名詞:一般 ＋ 名詞:接尾:副詞可能（起動時・保存時・
    # 入力時・変換中と同じ組み）。**逆算の読みは当てにならない**——
    # `替` の音訓 かえ と本文の送り仮名 え が繋がって `きりかええじ` が
    # でき、それが「読めない」ので `きりかえし`（切り返し）に寄せられて
    # いた。読みを1つずつ見る前に、**書かれた形そのもの**で決める。
    if _chunk_is_intact(chunk, tokenize_fn):
        _trace('語の組', f'{chunk!r} はもうできあがっている'
                         f'（項目48-KI の入口）ので触らない')
        return None
    # **読める読みが1つでも在ったら、下位の読みには高い敷居を掛ける**
    # （項目48-PF・2026-09-03）。読みは確からしい順に並んでいるので、
    # 上位の読みが日本語として読めて直し先も無いなら、その塊は
    # 壊れていない。そこで下位の読みまで**同じ低い敷居**で見ると、
    # **こちらの読みの当て損ないが「壊れている証拠」に化ける**——
    # 実測（項目48-PE で音訓表に 音=いん が入った直後）:
    #
    #     開音節  ①かいおんせつ（読める・直し先なし）
    #             ②かいいんせつ（読めない）→ **かんせつ → 関節**
    #
    # ★★「自然な文には、補正を実行しない」。**門は閉じない**
    # （項目48-AE）——`readable_hint` を渡して敷居を上げるだけにする。
    _readable_seen = False
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
        # **解析が1語の辞書語と読む塊は、その読みに手を当てない**（項目48-TB・
        # 2026-09-06。`効き目` は 効き目(名詞:一般・読みが立つ) の1語なのに、
        # 芯が `ききめ → きめ`（1字落とし）で `決め` にした——育ちで実測。
        # 同音の置き換え（上の枝: `視覚 → 四角`・`市内 → しない`）は手を
        # 当てないので今までどおり。48-KI「できあがった塊には走らせない」）
        if _single_known_token(chunk, tokenize_fn):
            _trace('混合塊', f'{chunk!r} は1語の辞書語なので、読み '
                             f'{reading!r} に手を当てない（項目48-TB）')
            return None
        fix = rebuild_window_core(reading, store, tokenize_fn,
                                  context_vec=context_vec,
                                  surrounding_words=surrounding,
                                  whole_only=True,
                                  # **上位の読みが読めていたら敷居を上げる**
                                  # （項目48-PF）
                                  readable_hint=_readable_seen,
                                  # **隣接の判定は入力方式で変わる**
                                  # （項目48-FX/FZ）。混合塊の経路にも
                                  # 同じ門を掛ける。
                                  input_method=input_method)
        if fix is None:
            if not _readable_seen \
                    and _looks_like_valid_japanese(reading, tokenize_fn) \
                    and not _verb_noun_joined(reading, tokenize_fn):
                _trace('混合塊', f'{reading!r} は日本語として読めて、直し先も'
                                 f'無い。**下位の読みは敷居を上げる**'
                                 f'（項目48-PF）')
                _readable_seen = True
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


def _attest_insert_variants(base, attest_text):
    """
    **同じ行に書かれた並びからの脱字の変種**（項目48-LS・48-LQ の
    読み版）。attest_text（塊の外の同じ行）の中から、「内側に1字
    足すと base になる」全かなの並びを拾う。

        かな地: 読み かなち ＋ う ＝ かなうち が ⇒ の側に在る

    盲目の挿入は候補が爆発する（46字×位置）ので、**行に文字どおり
    書かれた並びに一致する挿入だけ**を作る。端の挿入は採らない
    （48-LQ と同じ理由——切り出しが助詞を落としただけの並びと
    紛れる）。向きの門（48-LQ の「並記は後ろ」）はここでは要らない
    ——この変種は語彙の完全一致と並記の支えをどのみち通るので、
    でたらめな挿入は語彙に無くて死ぬ。
    """
    if not base or not attest_text:
        return []
    n = len(base) + 1
    found = []
    for i in range(len(attest_text) - n + 1):
        s = attest_text[i:i + n]
        if s in found:
            continue
        if not all(is_hiragana(c) or c == 'ー' for c in s):
            continue
        for k in range(1, n - 1):       # 内側の挿入だけ
            if s[:k] + s[k + 1:] == base:
                found.append(s)
                break
    return found


def _middle_is_working_particle(chunk, ms, me, tokenize_fn):
    """
    塊の [ms:me) が、**いまの表記のまま助詞として働いているか**
    （項目48-PY・2026-09-04）。

    真ん中助詞の3分割（1-F）は `[語][助詞1字][語]` に組み直すが、
    元の真ん中が既に**名詞に正しく付いた助詞**（`前より前` の
    `より`＝格助詞）なら、関節はできあがっている——別の助詞への
    書き換えは補正ではない（未解決.txt の注記の行で `より` が
    1字削除の変種で `よ` に壊された・実測）。

    見るのは**名詞に付く類**（格・係・副・並立・連体化）だけ。
    接続助詞（ば・て）は動詞に付くもので、名詞の後ろでは働いて
    いないから対象のまま（クリックばドラッグ → クリックかドラッグ
    のような直しは止めない）。
    """
    try:
        toks = tokenize_fn(chunk)
    except Exception:
        return False
    mids = [t for t in toks
            if int(t[3]) >= ms and int(t[4]) <= me]
    if not mids:
        return False
    # 範囲と境目が一致していること（語の途中を跨ぐ範囲は対象外）
    if int(mids[0][3]) != ms or int(mids[-1][4]) != me \
            or sum(int(t[4]) - int(t[3]) for t in mids) != me - ms:
        return False
    ok_sub = ('助詞:格助詞', '助詞:係助詞', '助詞:副助詞',
              '助詞:並立助詞', '助詞:連体化')
    return all((t[1] or '').startswith(ok_sub) for t in mids)


def _seq_recomposes_known_kanji(chunk, surface, tokenize_fn):
    """漢字だけ・読みの立つトークンだけの塊で、元のトークンが1つも surface に
    残らないか（項目48-TD）。"""
    if not chunk or not surface or surface == chunk or tokenize_fn is None:
        return False
    if not all(is_kanji(c) for c in chunk):
        return False
    try:
        toks = [t for t in (tokenize_fn(chunk) or ()) if t[0]]
    except Exception:
        return False
    if len(toks) < 2:
        return False
    if any(len(t) > 5 and not t[5] for t in toks):
        return False
    return not any(t[0] in surface for t in toks)


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
    # **できあがっている塊には走らせない**（項目48-KI の入口・学び22）。
    # うにさんの指定「補正が動くのは異様な文字列だけ」。この道にも
    # 同じ入口を掛ける——片方だけに置くと、そちらを迂回して素通りする。
    if _chunk_is_intact(chunk, tokenize_fn):
        _trace('語の組', f'{chunk!r} はもうできあがっている'
                         f'（項目48-KI の入口）ので触らない')
        return None
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
            # 3字の読みは、**同じ行の並記からの脱字の変種**が作れる
            # ときだけ通す（項目48-LS。かな地: かなち＋う＝かなうち が
            # ⇒ の側に文字どおり在る）。4字の下限は「短い読みは偶然
            # 別の語へ化けやすい」ための門で、行に書かれた並びに
            # 一致する挿入は証拠が別枠にある。
            if not (len(reading) == 3 and attest_text
                    and _attest_insert_variants(reading, attest_text)):
                continue
        peels = [(reading, '')]
        if reading[-1] in PARTICLES_1CHAR and len(reading) - 1 >= 4:
            peels.append((reading[:-1], reading[-1]))
        for base, tail in peels:
            variants = [(base, 0, 'base')]
            # 連打の畳みの変種も、重複打鍵の直しの1つ
            # （CN_NO_DUP=1 のときは作らない・学び22）
            if _dup_repair_enabled():
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
            # 同じ行に書かれた並びからの**脱字**の変種（項目48-LS。
            # かなち → かなうち。_attest_insert_variants の説明を参照）。
            # **手の数は 1**——読みの側に挿入の1手が既に入っている。
            # 0 にすると、組んだ表記（かな＋打ち）が「無傷で組める＝
            # 同音のすり替え」として捨てられる（最初の版で実測）。
            if not tail:
                for _s1 in _attest_insert_variants(base, attest_text or ''):
                    if all(_s1 != w for w, _c, _k2 in variants):
                        variants.append((_s1, 1, 'attest_insert'))
            for w, collapsed, kind in variants:
                if len(w) < 3:
                    continue
                # --- 塊全体が1つの語彙語（変換し損ね・挿入の訂正） ---
                # 説明ぶん＝せつめいぶん→説明文／
                # 差釣れません＝さつれません−つ→されません。
                # 読みそのままの完全一致は、ひらがなを含む塊
                # （変換し損ねの形）か、削除で届いた読みに限る
                # （漢字だけの塊の同音すり替えを防ぐ）。
                if kind in ('base', 'attest_insert'):
                    # 変換し損ね（説明ぶん→説明文）: 塊にひらがなが
                    # あり、表記に漢字が入る（漢字→ひらがなへの
                    # 格下げはしない。押しても→おしても を防ぐ）。
                    # 並記の脱字（attest_insert・項目48-LS）も同じ扱い。
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
                    if got_w and kind in ('base', 'attest_insert') \
                            and not any(is_kanji(c) for c in got_w[0]):
                        got_w = None
                    if got_w and kind not in ('base', 'attest_insert') \
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
                        # **漢字・カタカナの真ん中は、その読みが助詞と同じ
                        # ときだけ**書き換える（項目48-SV・2026-09-06。48-PG
                        # と同じ線——`化`→`か` は読みが同じ。`引き月資料 →
                        # 引きが資料` は 月 の読みに が が無いのに、自然さの
                        # 差だけで通っていた）
                        if middle and any(is_kanji(_c) or is_katakana(_c)
                                          for _c in middle) \
                                and p1 not in _gap_readings(middle):
                            continue
                        # 元の真ん中が既に働いている助詞なら、関節は
                        # できあがっている（項目48-PY。前より前 の
                        # より を よ に書き換えない。判定は
                        # _middle_is_working_particle に1回だけ書く）
                        if middle and _middle_is_working_particle(
                                chunk, len(mx[0]),
                                len(chunk) - len(my[0]), tokenize_fn):
                            _trace('語の組', f'{chunk!r} → 真ん中の '
                                             f'{middle!r} は働いている助詞'
                                             f'なので書き換えない（48-PY）')
                            continue
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

    # **ひらがな頭＋漢字の塊は、頭のかなを動かさない**（項目48-LS・
    # 2026-08-30）。かなは指で打った字そのもので、化けるのは IME が
    # 変換した漢字の側。い' の列挙（ひらがな頭＋漢字1字）を広げたら
    # `」だと分かる` の だと分 が拾われ、頭の機能語 だと を 出し に
    # 置換して `出しぶんかる` を作った（全行検品で実測）——
    # かな地→かな打ち（頭 かな が無傷）は通り、頭を書き換える組は
    # 捨てる。カタカナ頭（カニ打ち→かな打ち）は今までどおり
    # （カタカナは IME が作った字なので動かしてよい）。
    _hh = 0
    while _hh < len(chunk) and is_hiragana(chunk[_hh]):
        _hh += 1
    if _hh >= 2 and _hh < len(chunk) \
            and all(is_kanji(c) for c in chunk[_hh:]):
        _head = chunk[:_hh]
        _before = len(cands)
        cands = [c for c in cands if c['surface'].startswith(_head)]
        if len(cands) != _before:
            _trace('語の組', f'{chunk!r} → 頭のかな {_head!r} を'
                             f'動かす組を {_before - len(cands)} 件捨てた')
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
                # ★★ **恒偽になった**（項目48-QG'・回数を廃した）。
                # `_exact` は `count >= 2` で絞ってから数を返すので
                # `rep[1]` は**必ず 2**、右辺は最小 4。＝この段は
                # この巡から必ず外れ、**拮抗は文脈だけが決める**。
                # 倒れる先は下の「決め手が無い」＝**触らない**（安全側）。
                # 初期状態では前からほぼ成立しなかった（count 1〜3）ので、
                # 変わるのは育った語彙のときだけ。
                # 生かし直すなら証拠を `_general_count`（world・費用表）
                # へ寄せる——**入れる前に初期と育ちの両方で測る**。
                ordered = sorted(reps, key=lambda r: -r[1])
                if ordered[0][1] >= max(1, ordered[1][1]) \
                        * _USAGE_DOMINANCE:
                    picked = ordered[0]
            if picked is None:
                _trace('語の組', f'{chunk!r} → 拮抗 '
                                 f'{[r[0] for r in reps]} の決め手が無い')
                return None
            win = picked[2]

    # **辞書の語だけでできた漢字の塊を、丸ごと別の語の組にしない**
    # （項目48-TD・2026-09-06。`焙煎度`〔焙｜煎｜度・どれも読みが立つ〕を
    # 「明らかに自然になる（差 17090）」で `浴び選択` にした——ngram の表は
    # 珍しい語を知らないので、差は当てにならない。元の語が1つも残らない
    # 組は当て推量。同音の置き換えと 設計27 の受け皿は別の道）
    if _seq_recomposes_known_kanji(chunk, win.get('surface', ''),
                                   tokenize_fn):
        _trace('語の組', f'{chunk!r} → {win.get("surface")!r} は、辞書の語'
                         f'だけの漢字の塊を丸ごと組み替えた形。通さない'
                         f'（項目48-TD）')
        return None
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

#: **撤去した**（項目48-QG'・2026-09-05）。回数の記録をやめたので
#: 100 には届かない。`_katakana_melt_ok` の末尾を参照——溶かす
#: 置き換え先は**種の語だけ**になった。名前だけ残すと、いつか
#: 「回数がある」前提のコードがまた生える。


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
    for surface, _pos, _reading, _s, _e, has_reading, *_ in toks:
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
    # ★★ **種の語だけになった**（項目48-QG'・2026-09-05）。
    # ここは「使い込まれた語（実績100以上）だけがカタカナを溶かす
    # 置き換え先になれる」という門だったが、回数の記録をやめたので
    # **100 には二度と届かない**。倒れる先は「溶かさない」＝安全側で、
    # 実害も無い——上の `_seed_surfaces()` が `入力`・`単語` のような
    # 日常語を通しているので、うにさんの的（`乳リュク → 入力`・
    # `タン子 → 単語`）は**種の側で全部通っている**（実測）。
    #
    # 一般度の表で開き直す案は**入れない**。この門が止めたいのは
    # まさに `縦シュー → 大衆`・`ブチ上 → 日常`・`耳コピ → 事項`
    # で、**どれも世の中では在る語**（表では裁けない）。
    # 「使い込んだか」は回数でしか言えなかったので、**言わない**。
    return False


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
        # **活用語尾・複合助詞も部品**（項目48-IS）。`かくにんします` の
        # `します` は `is_protected_word` に無く（あれは骨組みの語の
        # 表）、語彙の読みでもないので敷き詰められず、`すきにん →
        # かくにん` が「語彙と助詞で説明できない」で落ちていた。
        # 機能語の表（`AUXILIARY_TAILS`・`PARTICLES_MULTI`）は
        # `_kana_run_explained` と同じもの。
        for j in range(i + 2, min(n, i + 8) + 1):
            if not ok[j] and (run[i:j] in AUXILIARY_TAILS
                              or run[i:j] in PARTICLES_MULTI
                              or run[i:j] in BASIC_VERB_FORMS):
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

#: 濁点を取れる清音（項目48-OR(b)）。**名前を `_OR_` で始める**——
#: `_DAKUTEN_BASE` は **13899行に別の表（辞書）が在って、あとから
#: 上書きされる**（`う → ゔ` を含むので `_TYPO_DAKUTEN` に無い字が
#: 通り、KeyError で `_reopen_odd_chunk` が丸ごと落ちた・2026-09-03 実測）
_OR_DAKUTEN_BASE = frozenset('かきくけこさしすせそたちつてとはひふへほ')
#: 濁音・半濁音（項目48-OR(b)）
_OR_VOICED_KANA = frozenset('がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ')


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
# **`し` の対は `じ`**（2026-09-06・項目48-SB で見つけた表の誤り。
# `ございず` と書いてあり `し → い` になっていた——`_mark_slip_repairs` が
# し＋゛の隣 を い にしていた。48-SB の位置ずれの手が `かたい → かだし` を
# 作って見つかった）
_MARK_COMPOSE_DAKUTEN = {}
for _a, _b in zip('かきくけこさしすせそたちつてとはひふへほう',
                  'がぎぐげござじずぜぞだぢづでどばびぶべぼゔ'):
    _MARK_COMPOSE_DAKUTEN[_a] = _b
_MARK_COMPOSE_HANDAKUTEN = dict(zip('はひふへほ', 'ぱぴぷぺぽ'))


def _dup_repair_enabled():
    """
    **重複打鍵（同じ字が2度→1つ消す）の直しを使うか**

    ★★ **2026-09-08 から既定オフ**（項目48-VH・うにさんの指定
    「**同一キーの連続重複を1つに補正する機能自体を無効にして
    ください。無効でしばらく様子を見て問題がなければ機能削除します**」）。
    2026-08-28 の検討「2度同じキーを押すのは意図しているところが
    大きい」の続き。

    ★ **決めているのは `vocabulary.dup_repair_enabled` の1か所**
    （48-GN——同じ判定を2つ書かない）。あちらは費用表の側
    （`_REPEAT_GAP_COST`）も同じ答えで動かす。

    止まるのは**全部の道**（学び22——片方だけに置くと迂回する）:

        _typo_repairs / _typo_repairs_cheap の「1つ消す」候補
        _fold_repeat_to_word（設計22・畳むと在る語）
        vocabulary._REPEAT_GAP_COST（編集距離の連打割引）

    **「新しい重複を作らない」側の守り**（_has_new_repetition）は
    切らない——あれは直しではなく、壊れを防ぐ砦。

    戻すときは `CN_NO_DUP=0`（2026-09-08 より前の挙動）。
    """
    try:
        from vocabulary import dup_repair_enabled as _de
    except Exception:
        # 判定できないなら**うにさんの指定の側へ倒す**（オフ）。
        return False
    return _de()


def _typo_repairs(core, extra_key=False, input_method='kana'):
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
    # 重複打鍵: 同じ字の連続を1つ減らす（CN_NO_DUP=1 のときは出さない）
    if _dup_repair_enabled():
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
    # （濁点の位置ずれ〔48-SB〕は**ここには置かない**——語彙で受ける門が無く、
    #   芯の再構築の「誤打を巻き戻した候補」で `とぐとく → とくどく`〔正しくは
    #   ゛を外す とくとく〕を作った・初期の readcheck で実測。芯は
    #   `_moved_dakuten_fix`、設計27 は `_fixes`、48-LU は かな→かな を受けず、
    #   どれも「゛1つの手が勝るなら採らない」付きで持つ・項目48-SB'）
    # 脱字: 1字入れる（**いちばん数が多いので最後**）
    for i in range(n + 1):
        head, tail = core[:i], core[i:]
        for ch in _TYPO_KANA:
            push(head + ch + tail)
    # **余分な隣のキー**（項目48-PL(b)・2026-09-03）。前後どちらかの字と
    # 隣のキーになっている1字を落とす——48-KI の手（`_reopen_odd_chunk`
    # の `_fixes`）と**同じ考え方**だが、**同じ形ではない**（下見で
    # 分かった食い違い・N25）: `_fixes` は `range(1, len(rd)-1)`（頭と
    # 尾は消さない）・隣の広さ **1.0**、こちらは `range(n)`（頭尾も
    # 見る）・`adjacent_slip`（**1.6**）。`かいすせき` の `す` は
    # `い`(E) の隣(R)。
    #
    # **`extra_key=True` のときだけ足す。** 渡すのは
    # `fallthrough_rebuild_ok` の「誤打の種類で説明が付くか」の**門**、
    # しかも **①（動詞基本形＋名詞の直付き）が立つ塊だけ**
    # （項目48-PL(b')・2026-09-04。無条件で渡すと育ちで正しい文を
    # 3行壊す——`意図を察して → 意図をさして` ほか・実測）。
    # **候補を作る側には渡さない**——渡して測ったら readcheck で
    # **直りが失われた5・化け +6**（いそし→いし・よつし→よし・
    # きうす→きす・さしび→さび・せんしゅんけ→せんしんけ。
    # **短い語へ削る候補が費用で勝つ**。並べる順を後ろにしても同じ）。
    if extra_key and n >= 3:
        for i in range(n):
            _nb = ((i > 0 and core[i - 1] != core[i]
                    and adjacent_slip(core[i - 1], core[i], input_method))
                   or (i + 1 < n and core[i] != core[i + 1]
                       and adjacent_slip(core[i], core[i + 1], input_method)))
            if _nb:
                push(core[:i] + core[i + 1:])
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
    # 重複打鍵: 同じ字の連続を1つ減らす（CN_NO_DUP=1 のときは出さない）
    if _dup_repair_enabled():
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


def _moved_dakuten_variants(run):
    """
    **濁点・半濁点が隣の字にずれて付いた形を戻す**（項目48-SB・
    2026-09-06・うにさんの指定「濁点の入れ替えが苦手なように感じる。
    平仮名に開く時、濁音は清音と濁点に分けて考える。`つつき゛`」）。

    かな入力では ゛ は独立したキーなので、開いた読みを
    **清音＋゛** に分けて見ると、

        つつぎ ＝ つ つ き ゛     打ちたかった  つづき ＝ つ つ ゛ き

    は **き と ゛ の順序違い**（隣どうしの入れ替え・SPEC の誤打の型）
    にすぎない。合成された字のままだと「ぎ→き ＋ つ→づ の2手」に
    見えて、1手の道に届かなかった。**濁音の字から印を外し、隣の
    字（印を受けられる清音）に付け直す**——左右どちらの隣も見る。
    半濁点（ぱ行）も同じ。**頭の字は変えない**（48-LS「頭のかなは
    動かさない」）——`ぎつ → きづ` のように印が頭へ移る形は、
    頭の1字が別の字になるので作らない。

    戻り値: 戻した並びの一覧（元と同じものは含まない）。
    """
    out = []
    n = len(run)
    if n < 2:
        return out
    for table in (_MARK_COMPOSE_DAKUTEN, _MARK_COMPOSE_HANDAKUTEN):
        rev = {v: k for k, v in table.items()}
        for i in range(n):
            ch = run[i]
            if ch not in rev:
                continue
            base = rev[ch]
            for j in (i - 1, i + 1):
                if not (0 <= j < n) or j == 0:
                    continue          # 印を頭の字へ移す形（頭が変わる）は作らない
                if run[j] not in table:
                    continue          # 隣は印を受けられる清音であること
                chars = list(run)
                chars[i] = base
                chars[j] = table[run[j]]
                v = ''.join(chars)
                if v != run and v[0] == run[0] and v not in out:
                    out.append(v)
    return out


def _lu_known_score(x, store):
    """その読みを**どれくらい知っているか**（小さいほど強い・None＝知らない）。
    本人の語彙 solid → 0、語彙に在る（count 1）→ 50、同梱の費用の表 → その費用。"""
    if not x or store is None:
        return None
    try:
        es = list(store.lookup(x))
    except Exception:
        es = []
    if any(e.get('count', 0) >= 2 for e in es):
        return 0
    if es:
        return 50
    tc = _table_cost(x)
    return tc if tc is not None else None


def _dakuten_rival_stronger(x, moved, store):
    """
    **゛の付け外し1つ**で届く読みのほうが、位置ずれで届く読み `moved` と
    同じかそれ以上に知られているなら True（項目48-SB の門・初期の
    readcheck で受け止めた: `むたづかい` は だ の゛を戻す1手〔むだづかい〕
    が正しく、位置ずれ〔むだつかい〕は当て推量。`つつぎ` は `つつき`〔185〕
    より `つづき`〔143〕が知られているので通る）。
    """
    ms = _lu_known_score(moved, store)
    for i, ch in enumerate(x):
        alt = _TYPO_DAKUTEN.get(ch)
        if not alt:
            continue
        v = x[:i] + alt + x[i + 1:]
        sc = _lu_known_score(v, store)
        if sc is None:
            continue
        if ms is None or sc <= ms:
            return True
    return False


def _moved_dakuten_fix(core, store, dict_index=None):
    """
    **芯が「濁点の位置がずれた語」なら、その1手を先に採る**（項目48-SB）。

    芯の再構築には「守る語＋1字は対象外」（48-GZ）の門があり、
    `つつぎ`（守る語 つつ ＋ ぎ）はそこで止まっていた。**濁点の
    位置ずれは形だけで立つ仮説**（正しい日本語で、印が隣の字に
    付いた形と、元の形の両方が語であることはまず無い）なので、
    その門より先に見る。

    採るのは、**元の芯が語でなく**、戻した形が**ただ1つ**、語として
    立つ（本人の語彙に実績2以上・同梱の費用の表に在る・世の中の読み
    〔4字以上〕）ときだけ。決まらなければ None（今までの道へ）。
    """
    if not core or len(core) < 3 or store is None:
        return None

    def _known(x):
        try:
            if any(e.get('count', 0) >= 2 for e in store.lookup(x)):
                return True
        except Exception:
            pass
        if _table_cost(x) is not None:
            return True
        if dict_index is not None and len(x) >= 4:
            try:
                return bool(dict_index.is_world_reading(x))
            except Exception:
                return False
        return False

    if _known(core):
        return None
    good = []
    for v in _moved_dakuten_variants(core):
        if _known(v) and v not in good \
                and not _dakuten_rival_stronger(core, v, store):
            good.append(v)
    return good[0] if len(good) == 1 else None


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
                          tokenize_fn=None, prev_char=''):
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
    # (0-) **できあがっている塊には走らせない**（項目48-ME・
    #      2026-08-31。入口は `_chunk_is_intact` ただ1つ・48-KI）。
    #      この道はいちばん最後の手なので、**掛け忘れていた**
    #      ——`一番下 → 一番化` はそれで出ていた（学び22 の型）。
    if _chunk_is_intact(chunk, tokenize_fn):
        _trace('造語', f'{chunk!r} はもうできあがっている（48-KI の入口）'
                       f'ので触らない')
        return None
    # **数字の直後から始まる漢字の塊は数え方**（項目48-SR・2026-09-06）。
    # 数字の直後の漢字は助数詞・単位（2個・3回・10日・100円・2倍）で、
    # 塊だけを解析すると `個` は 名詞:一般 になって見えない
    # （`2個以下` の `個以下` を造語めいた複合と見て `語彙化` に組み直して
    # いた。うにさんの実機・初期でも）。呼び手が直前の1字を渡す。
    # 判定はここ1か所（呼び手は2つ在る・48-GN）
    if (prev_char and (prev_char.isdigit() or prev_char in '０１２３４５６７８９')
            and is_kanji(chunk[0])):
        _trace('造語', f'{chunk!r} は数字の直後から始まる（数え方）ので'
                       f'触らない（項目48-SR）')
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
            # **手を当てた読みの語幹を索引の顔で立てるのは、直し先が世の中で
            # 1語のときだけ**（項目48-OJ・2026-09-02）。索引が2字漢語の帯を
            # 持ったので、`接周辞`（せっしゅうじ）に手を当てて せっしゅ＝接種
            # を立て **`接種化時`** を出した（実測）。48-MK「組む道は直し先が
            # 世の中で1語」と同じ門。手なし（`最大家事 → 最大化時`・読みは
            # さいだいかじ のまま）と、本人の語彙の語幹（実績2以上）は今まで
            # どおり。`殺意代価 → 最大化` は 最大化 が1語なので通る
            if cand != rd:
                try:
                    _own = any((e.get('count', 0) or 0) >= 2
                               for e in store.lookup(stem_rd)
                               if e.get('surface') == head)
                except Exception:
                    _own = False
                if not _own:
                    try:
                        import seed_japanese as _sj4
                        _is1 = _sj4.is_unit(full) is True
                    except Exception:
                        _is1 = False
                    if not _is1:
                        _trace('造語', f'{chunk!r} → {full!r} は手を当てた読みの'
                                       f'語幹 {head!r} が本人の語彙に無く、直し先'
                                       f'も世の中で1語でないので採らない（48-OJ）')
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
                        input_method=None, before_kanji=None):
    """
    単語として成立していない窓を、語彙にある読みへ組み直す。
    before_kanji: 窓の直後が漢字か（None＝分からない）。末尾の お/ご を
                  次の語の接頭辞と読んでよいかに使う（項目48-TJ）。

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
        readable = bool(readable_hint) or (
            _looks_like_valid_japanese(window, tokenize_fn)
            # **動詞の基本形＋名詞の直付きは「読める」に数えない**
            # （項目48-PL(a)・うにさんの「解す咳 は品詞のつながりが
            #   異様」）。①ではなく**④の敷居**の側で効く
            and not _verb_noun_joined(window, tokenize_fn))
        # 混合塊（漢字を読みに戻した列・whole_only）には掛けない。
        # `間違った` を `まちがった` に戻した列が読めない扱いになり、
        # `まちがかった` に化けた（実測）。漢字を読みに戻した列は
        # 本人の打った形ではないので、新しい「読める」の外。
        if readable and not whole_only \
                and not _kana_run_explained(window, after_kanji,
                                            tokenize_fn,
                                            before_kanji=before_kanji):
            _trace('芯', f'{window!r} → 解析は読めると言うが、かなの語と'
                         f'機能語では説明できない（項目48-IS）。読めない扱い')
            readable = False
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
    # **「読める」は芯ごとに決め直す**（項目48-IS・実測）。前の芯
    # `ちでのほら` が読めたせいで次の芯 `ほらい` まで読める扱いになり、
    # `ほせい` への直しが拒否権で落ちた（tests_mock）。窓の判定を
    # 起点に戻してから、その芯の判定を重ねる。
    _readable_window = readable
    for c_s, c_e in cores:
        readable = _readable_window
        core = window[c_s:c_e]
        if len(core) < 3:
            _trace('芯', f'{core!r} → 3文字未満なので対象外')
            continue
        # ★★ **濁点の位置ずれは、下の門より先に**（項目48-SB・2026-09-06。
        # `つつぎ` は「守る語 つつ に1字足しただけ」で止まっていた）
        _md = _moved_dakuten_fix(core, store, dict_index)
        if _md:
            _trace('芯', f'{core!r} → 濁点の位置がずれた形。{_md!r} に'
                         f'直す（項目48-SB）')
            return c_s, c_e, _md
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
        # 漢字の直後の芯（頭が送り仮名）は、かなの語と機能語の説明だけで
        # 見る。解析は `らまず` の `ら` を1字の断片と言って読めないと
        # するが、`ら` は `済んだら` の送り仮名で `まず` は副詞（項目48-IS）。
        # 頭と芯の間に助詞が無いときだけ（`ちでの|ほらい` は `での` で
        # 切れているので、`ほ` は送り仮名ではない）。
        # 芯の直後が窓の中のかななら、芯の末尾の お/ご は接頭辞ではない
        # （項目48-TJ）。窓の末尾まで芯なら、窓の直後の字で決める
        _bk_core = before_kanji if c_e >= len(window) else False
        if after_kanji and c_s <= 3 and not whole_only \
                and not any(ch in PARTICLES_1CHAR for ch in window[:c_s]):
            _core_readable = _kana_run_explained(core, True,
                                                 before_kanji=_bk_core)
        else:
            _core_readable = _looks_like_valid_japanese(core, tokenize_fn) \
                and (whole_only or _kana_run_explained(
                    core, before_kanji=_bk_core)) \
                and not _verb_noun_joined(core, tokenize_fn)
        # ★★ **芯まるごとが同梱の表の語なら、それは「読める」**
        # （項目48-UE・2026-09-07）。
        #
        # 上の `_core_readable` は「解析が読めると言うか」（janome）と
        # 「かなの語と機能語で説明が付くか」（表）の**両方**を要求して
        # いた。ところが**表がまるごと1語だと言っている**のに、janome が
        # 短い断片に割って「読めない」と言うと、そちらが勝っていた:
        #
        #     めちゃ  表=語  解析= め(1字)+ちゃ  → **むちゃ** に化けた
        #     きんめ  表=語  解析= き+ん+め      → **きんり**
        #     くさみ  表=語  解析= く+さ+み      → **くさき**
        #     とうしつ 表=語 解析= 割れる        → **当日**（糖質！）
        #     いけす  表=語  解析= 割れる        → **けいす**
        #
        # `tools_local/probe_seed_intact.py`（同梱の表の語を1語ずつ
        # 枠に入れて当てる新しい面）で見つけた。ひらがな 600 語で **16件**。
        #
        # ★ **門ではなく敷居**（48-AE と同じ構え）。読める＝
        # 「明らかに自然になる直しだけ通す」であって、止めるのではない。
        # 48-EN が「窓まるごとにだけ掛ける・部分芯には掛けない」と
        # したのは**返り値 None の門**の話で、こちらは敷居なので別。
        #
        # ★ 失う上限を先に測った: readcheck の3,467組のうち、壊した
        # 読みが表に語として在るのは 235（6.8%）、**そのうち「直った」は
        # 8件**（`おもわす → おもわず` など）。敷居なので全部は失わない。
        try:
            import seed_japanese as _sj_rd
            if _sj_rd.is_unit(core) is True:
                _core_readable = True
        except Exception:
            pass
        if _core_readable:
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
        # **読めない芯は候補を多めに取る**（項目48-IS）。6件で切ると、
        # `すきにん` の `かくにん`（2手・費用2.0）が6番目で落ちていた。
        found = find_similar_readings(core, store, max_cost=max_cost + 1.5,
                                      limit=(6 if readable else 12))
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
                                          min_count=1,
                                          limit=(6 if readable else 12))
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
        #   - **読めない芯では、隣のキー2回までの置換を許す**
        #     （項目48-IS・2026-08-23）。`すきにん → かくにん` は
        #     す→か・き→く の2回で、どちらも隣のキー（費用 1.0 ずつ）。
        #     「別の語への乗り換え」は費用が高い（あやこう→たんこう）。
        #     費用 2.0 以内＝2回とも隣のキー、だけを通す。
        #     **ただし、変えてよいのは説明の付かない字だけ**（実測して
        #     足した）。`これはん` の `これ`・`は` は機能語、`じょうです`
        #     の `です` は活用語尾で、そこを変えて `くれそん`
        #     `じょうてい` にしていた。
        # **読めない芯の自由は、混合塊（漢字を読みに戻した列・whole_only）
        # には与えない**（項目48-IS・実測）。`ひどい句` を `ひどいく` に
        # 戻した列が読めない扱いになり、`ひといき → 一息` に化けた
        # （2箇所訂正の説明文にある実例そのもの）。
        decisive = (not readable) and (not whole_only)
        # **表の語の途中から始まる・途中で終わる芯では決めない**
        # （項目48-IS・実測）。`やがいぶんしょう` の芯 `いぶんしょう` は
        # `やがい` の途中から始まっていて、`いんしょう` に化けた。
        # 窓の切り方がずれた芯は、読めなくても動かさない（48-HU の
        # 門(2) と同じ考え）。
        if decisive and (c_s > 0 or c_e < len(window)):
            _cut = False
            for _ws, _we in _table_word_spans(window):
                if _ws < c_s < _we or _ws < c_e < _we:
                    _cut = True
                    break
            if _cut:
                _trace('芯', f'{core!r} → 表の語の途中で切れている芯なので'
                             f'決めない（項目48-IS）')
                continue
        _editable = _unexplained_mask(core) if decisive else None

        def _only_unexplained(cand):
            if _editable is None or len(cand) != len(core):
                return True
            return all(_editable[i] for i, (x, y) in enumerate(zip(core, cand))
                       if x != y)

        found = [f for f in found
                 if f[2] < 2 or (len(f[0]) != len(core)
                                 and f[1] / f[2] <= 1.4)
                 or (decisive and f[2] == 2 and f[1] <= 2.0
                     and _only_unexplained(f[0]))]
        # **漢字の直後の送り仮名は変えない**（項目48-IS・実測）。
        # `現れんとす` の窓 `れんとす` が `けんとう` に、`間違った` の
        # `った` が `かった` になった。窓の頭が送り仮名なら、その字は
        # 前の漢字に属している。読めない芯でも頭の字は保つ。
        if decisive and after_kanji and core:
            found = [f for f in found if f[0][:1] == core[:1]]
        # 「助詞を1文字消しただけ」の候補は採らない。
        # 「二つばかり」の つばかり から ば を消すと つかり（浸かり）に
        # 届いてしまうが、助詞は打ち間違いで紛れ込む文字ではなく、
        # 意図して打たれた区切りである（実機・2026-08-09）。
        def _is_particle_drop(cand):
            if len(cand) != len(core) - 1:
                return False
            for _i, _ch in enumerate(core):
                if _ch in PARTICLES_1CHAR \
                        and core[:_i] + core[_i + 1:] == cand:
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
        #
        # **後ろがそれ自体で既知語なら、この制限は掛けない**
        # （項目48-NU・2026-09-01）。この制限の理由は「芯が**語幹の
        # 途中**で切れているから、終わりの字を変えると残した**語尾**と
        # 繋がらない」——`あらゆ`＋`る`。後ろが `こてい`(固定) のような
        # **独立した語**なら、そもそも語幹の途中ではないので理由が無い。
        #
        #     おくゆく|こてい   芯 `おくゆく` → `おくゆき`(奥行)
        #       終わりの字は く → き と変わるが、後ろは語尾ではない
        #       （掛けたままだと `おゆ`＝お湯 に削られて
        #        **`おゆくこてい` に化けていた**）
        rest = window[c_e:]
        if rest and rest[0] not in PARTICLES_1CHAR \
                and not _rest_is_own_word(rest, store):
            found = [f for f in found if f[0][-1] == core[-1]]
        if not found:
            continue
        # **読めない芯は、手数ではなく費用で並べる**（項目48-IS）。
        # `すきにん` は れきにん(2.4・1手)・せきにん(2.4・1手) が前に
        # 並び、かくにん(2.0・**2手**＝隣のキー2回) が後ろに回っていた。
        # 費用は打鍵の近さを足したものなので、こちらが「最有力」。
        _trace('芯', f'{core!r} → 読める={readable}')
        if decisive:
            found = sorted(found, key=lambda f: (f[1], f[2]))
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
        # 拮抗している候補（同じ訂正回数で、費用が僅差のもの）。
        # 読めない芯では手数をまたいで費用だけで見る（項目48-IS）。
        #
        # **読めない芯の「拮抗」は費用がほぼ同じものだけ**（項目48-IS・
        # 実測して絞った）。tie_band（1.0）の幅で束ねると、`ざほん` の
        # `ざぼん`(0.5) と `さらん`(1.5) が拮抗に見えて字の頻度が
        # `さらん` を選んだ（初期の readcheck で化け 18→121）。
        # 最有力＝費用がいちばん安い候補。同じ費用のときだけ決め手を使う。
        if not decisive:
            close = [f for f in found
                     if f[2] == edits and f[1] - cost < tie_band
                     and f[1] < max_cost]
        else:
            # 幅を 0.5 にも広げてみたが、初期の readcheck で化けが
            # 62→96 に増えた（費用の高い候補が「拮抗」に入って字の頻度で
            # 選ばれる）。費用が同じものだけに戻した。
            close = [f for f in found
                     if f[1] - cost < 0.05 and f[1] < max_cost]
        if len(close) > 1:
            second_cost = close[1][1]
            if second_cost - cost >= min_margin and len(close) == 2:
                pass        # 二番手と十分な差がある。最有力でよい
            else:
                # 周りの語で決める。決まらなければ使用実績で決める。
                # どちらでも決まらなければ直さない。
                # **読みの並びを連鎖の頭に**（CN_YOMI_TIE=2・2026-08-28・
                # うにさんの指定「次に来やすいキーは、各種補正よりも
                # 先に見てください」の文字どおりの置き方。異様判定が
                # 立っているときだけ＝統計を証拠にはしない）。
                picked = None
                how = ''
                if decisive and _yomi_tie_mode() == 2:
                    picked = _break_tie_by_yomigram(close, window, c_s, c_e)
                    how = '読みの並び'
                if picked is None:
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
                    picked = _break_tie_by_generality(
                        close, store, loose=decisive)
                    how = '一般的さ'
                # **読めない芯は、必ず決める**（項目48-IS・うにさんの指定
                # 「拮抗したら何もしないは逆効果。異様であれば最有力の
                # 候補に補正する。優先順位が付かなければ平仮名1文字の
                # 頻度で決める」）。字の頻度でも同じなら先頭。
                # **字の並び（文字3連）を字の頻度の手前に**（2026-08-28・
                # CN_TRI_TIE=1 のときだけ。前後の文字まで見るぶん、
                # 1字の頻度より情報が多い。測って差が出たら既定にする）。
                if picked is None and decisive and _tri_tie_enabled():
                    picked = _break_tie_by_charngram(close, window, c_s, c_e)
                    how = '字の並び'
                # **読みの並びを字の頻度の手前に**（CN_YOMI_TIE=1・
                # 保守的な置き方。2026-08-28）。
                if picked is None and decisive and _yomi_tie_mode() == 1:
                    picked = _break_tie_by_yomigram(close, window, c_s, c_e)
                    how = '読みの並び'
                # **並べ替えの問いにだけ答える**（CN_YOMI_TIE=3/4・
                # 2026-08-28・うにさんの指定「自然な文であれば補正
                # しなくていいので、**異様な文に対してのみ活用**する。
                # **効果のあるものを活かす**ようにしたい」）。
                #
                #   3  候補が全部「芯と同じ字の並べ替え」のときだけ
                #      （＝順序違いの向きの問い・表の力は 92.8%）。
                #      字が違う候補が混じれば語の見分けの問いなので黙る
                #      ——1/2 を落とした3例（トランシット／せきにん／
                #      しんつう）は全部そちら側だった
                #   4  3 に加えて、**その連続が異様なときだけ**
                #      （`_kana_run_explained` が「かなの語＋機能語で
                #      説明が付く」と言ったら自然な文なので触らない。
                #      項目48-IT の門を 48-KM と同じ形で流用する）
                if picked is None and decisive and _yomi_tie_mode() in (3, 4):
                    _ok = True
                    if _yomi_tie_mode() == 4:
                        try:
                            _ok = not _kana_run_explained(core, after_kanji)
                        except Exception:
                            _ok = False
                    if _ok:
                        picked = _break_tie_by_yomigram(
                            close, window, c_s, c_e, order_only=True)
                        how = '読みの並び（順序限定）'
                if picked is None and decisive:
                    picked = _break_tie_by_kana_frequency(close)
                    how = '字の頻度'
                    if picked is None:
                        picked = close[0][0]
                        how = '先頭（費用順）'
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
        # **直し先が「既知語＋1字助詞」に割れる語なら採らない**
        # （項目48-PK・2026-09-04・学び22——A道（ひらがな連続）に
        # 掛けただけでは、**芯の再構築が同じ直し先を拾う**。実測:
        # `かなちで` は A道で `かなで`・`さかなで` を断っても、
        # ここの似た読みが `かなで` を採って同じ化けになった）
        if _target_splits_word_particle(best, store):
            _trace('芯', f'{core!r} → {best!r} は直し先が 既知語＋1字助詞'
                         f' に割れる（語ではない）ので採らない'
                         f'（項目48-PK）')
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
    # **1字でも漢字なら内容語**（項目48-JL・2026-08-25）。
    # 「2文字以上」の門は雑音（かな1字）を落とすための AI 側の守り
    # だったが、漢字1字（傷・絵・顔・手・私）は意味を持つ内容語で、
    # 同音異義語の**対の単語**そのもの。ここで捨てていたせいで
    # `傷が治りました` の 傷 が材料に入らず、設計35 の守りの手がかりが
    # 空振りして `直りました` に化けた（実測）。
    def _content(surface):
        # 1字の漢字は**保護語でも材料には入れる**（私・手・絵・顔・傷）。
        # 保護は「補正しない」ことであって「文脈の手がかりにしない」
        # ことではない（`私の重い` の 私 が落ちて対の表が空振りした）。
        if len(surface) == 1:
            return is_kanji(surface)
        return not is_protected_word(surface)

    before = []
    after = []
    for tok in tokens:
        surface, _pos, _reading, ts, te = tok[0], tok[1], tok[2], tok[3], tok[4]
        if te <= start:
            if _content(surface):
                before.append(surface)
        elif ts >= end:
            if _content(surface):
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


# --- 方針2 が「惜しいところで止まった」語（項目48-JH・2026-08-25） ----
#
# うにさんの指定「異様であると認識しているのかが重要です。紫の表示が
# なければその判定が必要です」。方針2 は守りの門で正しく止まるが、
# **止まったこと自体が「合っていないかもしれない」の認識**である。
# 置き換え先の候補が作れて、次のどれかで止まったとき、その語を
# ここに控えて **紫（odd_spans）にだけ**出す（答えは1文字も変えない）:
#   (a) 書かれている語に支持があるが、**置き換え先にも同等以上の
#       太い証拠がある**（育ちの共起は誤変換の行からも学ぶ・48-IQ。
#       `売った文字` の 売っ 対 打っ の形）
#   (b) 置き換え先が差で勝ったが、証拠が細くて棄却した
#   (c) 並記（同じ行に別表記）があるのに、共起が決めなかった
# **並記の右側は控えない**（自分より前に同読みの別表記が書かれている
# なら、そこは正しい側——`組んで ⇒ 汲んで` の 汲ん に紫を出さない）。
# 消費は `_odd_spans_for_line`。行の処理の頭で毎回空にする。
_HOMOPHONE_UNSURE = []


def _flag_homophone_unsure(surface, alt_surfaces, line_text):
    """
    方針2 が惜しく止まった語を、紫に出すために控える（48-JH）。

    控えは (語, 候補たち)。**並記の右側（自分より前に同読みの別表記が
    書かれている出現）を弾くのは消費側**（`_odd_spans_for_line`）——
    ここに来る attest_text は**自分を伏せ字にした行**なので、
    自分の位置がもう分からない（実測で踏んだ）。
    """
    if not surface:
        return
    if any(s == surface for s, _a in _HOMOPHONE_UNSURE):
        return
    _HOMOPHONE_UNSURE.append(
        (surface, tuple(a for a in alt_surfaces if a and a != surface)))


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
# **置き換え先の使用実績**（回）。
#
# 10 → **2** にした（項目48-IQ・2026-08-22・うにさんの指定
# 「`_HOMOPHONE_MIN_USAGE = 10` は逆効果に感じています」
# 「初期状態を重要視して調整します。壊さないことを恐れすぎては
#   解決に至らない」）。
# 初期語彙は全部 count=2 なので、10 のままだと**初期状態では方針2 が
# 原理的に一度も動かない**（項目48-HY の「共起 0.0」の手前で、
# 置き換え先が先に落ちていた・項目48-IP）。2 は「初期語彙か、
# この人が一度は使った語」の線。辞書から取り込んだだけの語
# （count=1）は今までどおり置き換え先にしない。
_HOMOPHONE_MIN_USAGE = 2

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
# **活用形の同音**（項目48-IQ）は、さらに1語太い証拠を要る。
# 育った語彙の fpcheck で `まず厳しいから始めます → 初めます` が出た
# （初め 共通2語で 0.158・3語で 0.047）。初期状態の話題のまとまりは
# 共通の相手が多い（2語でも3語でも同じ点）ので、初期の的は落ちない。
_HOMOPHONE_MIN_SHARED_CONJ = 3
# **活用形の同音は、書かれている語に文脈の支持が無いときだけ動く**
# （項目48-IQ）。育った語彙では、うにさんのメモが誤変換の行
# （`動作の思い`）から `思い↔動作` の共起を学んでいて、正しい
# `動作が重い` 7行が `思い` に化けた（上下の行の語まで材料に入ると
# 差 0.12 を越えていた）。初期の話題のまとまりは正しい側
# （`重い↔動作` 0.289）を支持するので、この門で正しい行は動かない。
# 誤変換の側（`思い` に対して `動作`）は支持 0 なので動く。
# 0.05 では足りなかった（`アプリの動作が重いので` の 重い は 0.044 で
# 通り、上下の行の語まで入れると `思い` が勝った）。**1つでも共起の
# 支持があれば動かさない**（＝0）。初期状態の誤変換は周りとの共起を
# 持たない（支持 0）ので、初期の的は1つも落ちない。
_HOMOPHONE_HELD_MAX_CONJ = 1e-9
# 活用形の道の**差**。書かれている語の支持が 0 であることを上で
# 求めているので、置き換え先の支持だけで決まる。初期の話題のまとまりは
# 上下の行の語（最大12語）が材料に混じると薄まる（`直り` は行だけなら
# 0.159・上下込みで 0.081）ので、漢字だけの道の 0.12 より低く置く。
_HOMOPHONE_MIN_MARGIN_CONJ = 0.06

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
#
# **既定を入に変えた**（項目48-IQ・2026-08-22・うにさんの指定
# 「初期状態を重要視」「過去の決まりも見直したり、一度無効にしたり」）。
# 初期状態では `治り→直り` `売った→打った` `映る→移る` のような
# **活用形の同音異義語が、この切で全部止まっていた**。一族
# （売る・打つ・撃つ）の問題は、置き換え先を**初期の話題のまとまり**
# （`seed_context.py`）と共起の差で選ぶ形にして測った。
# 戻すなら `CN_CONJ_HOMOPHONE=0`。
_CONJ_HOMOPHONE = (os.environ.get('CN_CONJ_HOMOPHONE', '1') != '0')


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
    # **撥音便**（項目48-IQ）。組ん→組む・飛ん→飛ぶ・死ん→死ぬ。
    # `意図を組んで` が `汲んで` に届かなかった（`ん` の行が無かった）。
    'ん': ('む', 'ぶ', 'ぬ'),
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


def _compound_verb_backed(surface, reading, attest_text, max_prefix=3):
    """
    書かれている活用形が、**直前の語と合わせて表に在る複合動詞**か
    （項目48-IQ）。`換わり` は `書き換わる` の一部。

    attest_text（同じ行）の中で surface の直前 max_prefix 字までを
    取り、その末尾 1〜max_prefix 字＋語幹＋基本形の語尾が
    同梱の表（`oddness` の語）に在れば True。表が無ければ False。
    """
    if not surface or not attest_text:
        return False
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        return False
    if not words:
        return False
    stem, tail = _split_stem_tail_local(surface)
    if not stem or not tail:
        return False
    bases = {surface}
    for base_tail in _CONJ_TO_BASE.get(tail[-1], ()):
        bases.add(stem + tail[:-1] + base_tail)
    idx = attest_text.find(surface)
    while idx >= 0:
        # 前に付く形（書き＋換わる）
        prefix = attest_text[max(0, idx - max_prefix):idx]
        for k in range(1, len(prefix) + 1):
            head = prefix[-k:]
            if not all(is_hiragana(c) or is_kanji(c) for c in head):
                break
            for b in bases:
                if (head + b) in words:
                    return True
        # 後ろに付く形（映り＋込む）。書かれている形のまま続きを足す
        end = idx + len(surface)
        rest = attest_text[end:end + max_prefix]
        for k in range(1, len(rest) + 1):
            tail_part = rest[:k]
            if not all(is_hiragana(c) or is_kanji(c) for c in tail_part):
                break
            if (surface + tail_part) in words:
                return True
        idx = attest_text.find(surface, idx + 1)
    return False


def _conjugated_alts(surface, reading, store, skip_self_backed=True):
    """
    書かれている活用形（漢字＋送り仮名）に対して、
    **基本形が語彙に在る**同音の別表記を、元の送り仮名に合わせて作る。

    skip_self_backed: 書かれている語そのものが語彙に在るなら空を返す
        （並記の関門で**向きが逆にならない**ため・既定）。
        共起で測る経路（項目48-IQ）では False——書かれている側も
        置き換え先も語彙に在るのが同音異義語のふつうの形で、
        どちらが合うかは共起の差で決める（漢字だけの語の道と同じ）。

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
            if e_stem == stem and not skip_self_backed:
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

    かな・カタカナの表記が**立っている**読みは、**かなも正しい
    書き方**なので触らない:

        つながり → 繋がり と つながり の両方が立っている → 触らない
        たんご   → 単語 だけ                            → 直してよい
        かよわい → かよわい だけ（漢字が無い）           → 触らない

    ★★ **2026-09-05〜09-08 のあいだ、この関数は常に None を
    返していた**（項目48-VG）。門は `best['count'] < _K2K_MIN_USAGE`
    ＝**10回以上その漢字で書いている**（習慣か）だったが、48-QG で
    回数を廃止したあと `count` は **solid を写した 1 か 2 しか
    取らない**ので、10 には永久に届かない。
    呼び手は2本——`_shift_lost_kanji`（項目48-FU・うにさんが頼んだ
    `きようちよう ⇒ 強調`）と、かな→漢字の道。**両方が丸ごと
    眠っていた**（`きようちようしたい` も `しゆうせいします` も
    素通りしていた）。48-LU が同じ形で眠っていたのと同じ
    （48-SC で起こした）。

    ★ **「習慣的か」を写せる数字は、もう無い。**
    `world` は**辞書から取り込んだ語にしか付かず、本人が覚えた語は
    0**（別の軸。48-QG' の落とし穴）。決まりどおり**二値に落とす**
    ——「移せないなら二値にする」（48-QG'）。**その漢字表記が
    立っている（solid＝2回以上書いた）こと**を条件にする。

    ★ **立っている漢字が2つ以上あるなら返さない。** 回数が在った
    頃は「多いほう」を採れたが、二値では順位が付かない。
    決められないものは触らない（設計38〜40・48-JJ）。
    """
    try:
        entries = store.lookup(reading)
    except Exception:
        return None
    if not entries:
        return None
    try:
        from vocabulary import entry_is_solid as _solid
    except Exception:
        return None          # 判定できないなら触らない
    best = None
    for e in entries:
        surf = e.get('surface') or ''
        if not any(is_kanji(c) for c in surf):
            if _solid(e):
                return None        # かなでも書く語
            continue
        if not _solid(e):
            continue
        if best is not None and best != surf:
            return None            # 立っている漢字が2つ——決められない
        best = surf
    return best


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
#   (2) **直せる位置は「い段＋やゆよ」と「語頭・語末でない つ」**。
#       拗音はシフトを押さないと出ない字で、かつ前の字が決まっている。
#       小書き母音（ぁぃぅぇぉ）は外来語の書き方で、漢字にならない
#       （`_kanji_surface_for_reading` が None を返す）ので入れない。
#       ★★ **促音「っ」は 2026-09-08 に入れた**（項目48-VF'・
#       うにさんの指定「シフトキー補正を進める」）。ここには
#       「ぶつかる 111件のうち大半が `もつ／かつ／まさつ` の形で、
#       得るものより危ない」と書いてあったが、**その111件は
#       (1) の `known_or_bundled` が全部止める**——「打たれた並び
#       それ自体が語なら触らない」は、拗音と同じように促音にも効く。
#       語彙の「2文字目が っ の3字の読み」を全部当てて確かめた
#       （`いつか` `しつけ` `かつて` `さつき` `めつき` は全部止まる）。
#       得るほうは `がつこう → 学校`・`いつしよ → 一緒`・
#       `おいしかつた → 美味しかった`（**形容詞の過去形が丸ごと**）。
#       ★ 語末の `つ` は見ない——`っ` で終わるのは `あっ` `えっ` の
#       感嘆の書き方で、打ち損ねとは別。
#   (3) **答えが1つに定まらないなら触らない**。組み合わせが複数の
#       読みに当たり、漢字表記が食い違うなら判断がつかない。
#   (4) 漢字にする条件は項目48-EA と**同じ関数**を使う
#       （`_kanji_surface_for_reading`＝かなでも書く語は触らない・
#       **その漢字表記が立っていること**〔solid〕）。
#       新しい物差しを増やさない。
#       ★ 2026-09-05〜09-08 のあいだ、ここは「使用実績 10回以上」で、
#       回数の廃止（48-QG）のあと `count` が {1,2} しか取らなくなった
#       ため**永久に届かず、この道は丸ごと眠っていた**（項目48-VG）。
#   (5) **明らかに自然になること**（項目48-AE の敷居）。
#
# 拗音の頭に立てる字（い段）。`ぢ` `ゐ` は現代の入力では出ない。
_YOUON_HEADS = frozenset('きぎしじちにひびぴみり')
# 大書きで打たれた拗音 → 本来の小書き。
_YOUON_SMALL = {'や': 'ゃ', 'ゆ': 'ゅ', 'よ': 'ょ'}
# ★★ **促音も同じ Shift の押し損ね**（項目48-VF・2026-09-08・
# うにさんの指定「**シフトキー補正を進める**」）。
#
# かな入力で `っ` は **Shift＋つ**。拗音（ゃゅょ）とまったく同じ
# 押し損ねなのに、この道は**拗音しか見ていなかった**:
#
#     がつこう → **がっこう**（学校）   けつか → **けっか**（結果）
#     いつしよ → **いっしょ**（一緒）   とつきゆう → **とっきゅう**（特急）
#
# **道は増やさない**（48-GN）。同じ関数の字の集合を広げるだけ。
# 組み合わせ（拗音と促音が同じ語に両方ある `いつしよ`）も、
# 元から在るマスクの輪がそのまま面倒を見る。
_SOKUON_SMALL = {'つ': 'っ'}
#: 戻せる字の全部。
_SHIFT_SMALL = dict(_YOUON_SMALL)
_SHIFT_SMALL.update(_SOKUON_SMALL)
# この道で見る並びの最短の長さ。`ちよう` `きよう` のような3字は
# それ自体が語になりやすいので見ない（`きよう`＝器用）。
_SHIFT_MIN_LEN = 4
# ★★ **促音だけなら3字から、は測って戻した**（項目48-VF''・2026-09-08）。
#
# 4 は**拗音**のための天井（`きよう`＝器用・`ちよう` のように
# 「大書きのままでも語」が3字に多い）。促音は `けつか`（→結果）
# `こつか`（→国家）`ざつか`（→雑貨）のように**3字がふつう**なので、
# 3 へ下げて測った:
#
#   利得  **初期 +1 ／ 育ち +33**（語彙の「2文字目が っ の3字の読み」を
#         全部当てた。危ない3字＝`いつか` `しつけ` `かつて` `さつき` は
#         元から在る `known_or_bundled` が**全部止める**——初期9/育ち16）
#   値段  守る18・実機メモ9・readcheck10・memo_guard・shift_guard36・
#         画面32・実機メモ2,435行・語彙4,000語は**すべて差0**。
#         ところが**育ちの readcheck で1件化けた**——
#         `あつかかわ`（`あつかわ` の重複打鍵）の**内側**から
#         `あつか` を採って **`悪化かわ`**（化け 191 → 192）
#
# 締めようとしたが分けられなかった。`_rest_is_ordinary_japanese` は
# `かわを` も `がありました` も「ふつう」と言う。「残りが助詞で始まる」
# に替えても、`_p1` に **`か`・`や` が入っている**（語頭にも立つ字）ので
# `かわ` を弾けない。**3字の境目を言える証拠が、まだ無い。**
#
# **初期を先に見る**決まり（利得は初期 +1）と「壊さない ＞ 直る」に従い、
# **いまは入れない**。危ないからではなく、**門が作れないから**。
# 作れたら 33 件が待っている。
# 直す位置の上限。組み合わせは 2^n 通り見るので、天井を置く。
# 実機のメモで n が 3 を超える並びは 1つも無かった。
_SHIFT_MAX_POS = 6


def _youon_small_positions(text):
    """小書きの拗音（ゃゅょ）が立っている位置の集合。"""
    return frozenset(i for i, c in enumerate(text) if c in 'ゃゅょ')


def _shift_lost_positions(typed):
    """
    **シフトを押し損ねた小書きになりうる位置**を返す。

    拗音（48-FU）  「い段の字＋や/ゆ/よ」の並び
    促音（48-VF）  `つ` が**語頭でも語末でもない**位置に在る

    ★ 促音を**語末で見ない**のは、`っ` で終わるのが
    「あっ」「えっ」のような感嘆の書き方だから（項目48-EX の
    `_is_expressive_kana_run` が守っている側）。促音は必ず
    次の字と組むので、**うしろに字が在るときだけ**見る。

    ここが空なら、この道はそもそも関係が無い
    （ほとんどの並びは字を見るだけでここを抜ける）。
    """
    out = []
    last = len(typed) - 1
    for i in range(1, len(typed)):
        c = typed[i]
        if c in _YOUON_SMALL and typed[i - 1] in _YOUON_HEADS:
            out.append(i)
        elif c in _SOKUON_SMALL and i < last:
            out.append(i)
    return out


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
                chars[i] = _SHIFT_SMALL[typed[i]]
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
                           tokenize_fn=None, input_method='kana'):
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
        if rd in _typo_repairs(_ar, input_method=input_method):
            return True
    except Exception:
        pass
    # **余分な隣のキー（extra_key）は、①（異様の判定）が立つ塊だけに
    # 開く**（項目48-PL(b')・2026-09-04・うにさんの指定）。
    #
    # 前回（48-PL(b)・2026-09-03）は extra_key を**無条件**で開いて
    # 測り、的（`解す咳が終わった → 解析が終わった`）は通ったが
    # **育ちで正しい文を3行壊した**（`糸を察して → 意図をさして`×2・
    # `ひとつ前より前も… → 人前より前も…`）ので外していた。
    # うにさんの正し:
    #
    #     「正しい文が補正されている、つまり、**正しい文が異様と
    #       判定されているのが問題**です」
    #
    # 手の強さ・距離では分けられなかった（どれも距離1.0）が、**分ける
    # のは①**だった——`解す咳` は**動詞の基本形に名詞が直付き**
    # （品詞のつながりが異様・うにさんの品詞分析）で、`糸を察して`
    # （名詞＋を＋て形）も `ひとつ前より前も`（名詞の列）も**正しい
    # 品詞の並び**。①が立つ塊だけにこの手を開けば、正しい文には
    # そもそも走らない（★★「順番は 異様か → 決める」）。
    # 判定は 48-PL(a) の `_verb_noun_joined` ただ1つ（48-GN——同じ
    # 判定を2度書かない）。反例26文（`書く本`〜`眠る猫`）と
    # 実機メモ・readcheck・fpcheck は差0、動いたのは的だけ（実測・
    # `tools_local/probe_48plb2.py`）。
    try:
        if (tokenize_fn is not None
                and _verb_noun_joined(chunk, tokenize_fn)
                and rd in _typo_repairs(_ar, extra_key=True,
                                        input_method=input_method)):
            _trace('語の組', f'{chunk!r} は品詞のつながりが異様'
                             f'（動詞基本形＋名詞）なので、余分な隣のキーの'
                             f'手まで見て譲る → {surface!r}')
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
            if dict_index.readings_for_surface(core) \
                    or dict_index.surfaces_for_reading(core):
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
        # **終助詞の直前は、助動詞か終助詞であること**（項目48-LP・
        # 2026-08-30）。言い切りの文末は よ＋ね／た＋ね／だ＋ね と
        # 重なるが、**格助詞のあとに終助詞は立たない**（…にな は
        # 文末ではなく語の途中）。うにさんの画面の誤検知
        # `さんこうになる → さんこうにな。`——`…に(格助詞)＋な(終助詞)`
        # を言い切りと誤読して、末尾の る を 。 にしていた。
        # いいよね(よ+ね)・よかったね(た+ね)・そうだね(だ+ね) は残る。
        _p2 = ts[-2][1] or ''
        if not (_p2.startswith('助動詞') or _p2.startswith('助詞:終助')):
            return False
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
        # **中黒の列挙は触らない**（項目48-LN・2026-08-30。うにさんの
        # 誤検知報告——`（現在・1人称単数）` の ・ が ？ になった。
        # ・→？ は「しつもん・」のような**言い終わりの打ち損ね**の
        # 対であって、・の直後にまだ語の字が続くなら列挙の中黒）
        #
        # ★★ **空白は飛ばして見る**（項目48-QW・2026-09-05）。
        # うにさんの実機で `実機メモ全タブ・ 同梱の見本` の ・ が
        # `？` になった——**直後が空白1つ**だったので、この見張りが
        # 素通りしていた（`実機メモ全タブ・同梱の見本` は正しく
        # 断れていた。実測で両方確かめた）。列挙の中黒は
        # **`A・ B` とも `A・B` とも書く**ので、間の空白は列挙か
        # どうかを1つも変えない。
        # **言い終わりの打ち損ねは失わない**——`しつもん・` は
        # 行末（＝飛ばした先も行末）なので今までどおり通る。
        _nx = end
        while _nx < len(line) and line[_nx] in ' \u3000\t':
            _nx += 1
        if '・' in run and _nx < len(line) \
                and (is_japanese_word_char(line[_nx])
                     or line[_nx].isalnum()):
            _trace('同じキー', f'{run!r} の直後に語が続く＝列挙の中黒。'
                               f'触らない')
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


def _kana_run_is_ordinary_word(body, store, dict_index):
    """
    その かなの並びは、**普通の日本語の語として在る**か。

    在るなら綴りとは読まない（`わいわい` を `YY` にしない）。
    同梱の表（`is_unit`・ひらがな 79,645語を含む）と、**同梱の外来語の
    表**（`loanword._katakana_seed_all`・9,094語）と、学習した語彙・
    辞書の索引に聞く。表が無ければ `is_unit` は None を
    返すので、そこは「意見なし」として扱う。

    ★★ **外来語の表は 48-UA（2026-09-07）で足した。** それまで
    `イージー` が **`EG`** になっていた（`イー`＝E ／ `ジー`＝G）。
    `tools_local/probe_katakana_intact.py`——**同梱の外来語 9,094 語を
    そのまま書いて壊れないか**を1語ずつ当てる面——で見つけた。
    9,094 語のうち壊れていたのは**この1語だけ**。

    足しても失うものが無いことは測ってある: 字の読みを2つ並べて
    外来語の表に載るのは **9通り**（BC・DG・EG・NG・OK・PH・QP・SF・US）
    で、**EG 以外の8つは元から下の3つが止めていた**（`オーケー`・
    `エヌジー`・`キューピー`…）。`エフ2 → F2` も
    `エイチディーエムアイ → HDMI` も通ったまま。

    ★ **ひらがなに寄せて聞くこと**（下の注記と同じ理由）。外来語の表の
    見出しもひらがななので、そのまま合う。
    ★★ ただし**この表に対しては、ひらがなで聞いても字の名前を避けられない**
    （検品で指摘・2026-09-07）。見出しがカタカナ語の**読み**なので、
    `エフ` が載れば `えふ` として載る。いま 9,094 語に
    `えふ`・`えいち`・`でぃー`・`えむ`・`あい`・`じー`・`けー`・`わい`・
    `ぶい`・`えす`・`えぬ` は**1つも無い**（数えた）ので `エフ2 → F2` も
    `エイチディーエムアイ → HDMI` も通る。**`seed_katakana` に字の名前を
    足すときは、ここが黙って死ぬ**ことを思い出すこと。
    """
    try:
        from seed_japanese import is_unit
    except Exception:
        is_unit = None
    import alphabet as _AB
    if is_unit is not None:
        # **ひらがなに寄せた形で聞く。**
        # カタカナのまま聞いてはいけない——同梱の表には `エフ`
        # `エイ` `アイ` のような**字の名前そのもの**がカタカナ語
        # として載っており、`エフ2` が一生直らなくなる（実測）。
        # ひらがな側には `わいわい` `ぶいぶい` `あいあい` `える`
        # `だぶる` `ええ` `えっち` が在り、守りたいのはこちら。
        try:
            if is_unit(_AB.to_hiragana(body)):
                return True
        except Exception:
            pass
    try:
        # **同梱の外来語の表**（項目48-UA）。見出しはひらがななので、
        # 上と同じくひらがなに寄せて聞く
        from loanword import _katakana_seed_all as _ks
        if _AB.to_hiragana(body) in (_ks() or {}):
            return True
    except Exception:
        pass
    try:
        if _known_word(body, store, dict_index):
            return True
    except Exception:
        pass
    return False


def _fix_kana_alphabet(line, store, tokenize_fn=None, dict_index=None):
    """
    **かなで書いたアルファベットの読みを、英字に戻す**（項目48-IZ）。

        エフ2 → F2 ／ えふ2 → F2 ／ エフエフ9 → FF9
        えいちでぃーえむあい → HDMI ／ えいちでーえむあい → HDMI

    うにさんの指定（2026-08-23）。字→読みの表は `alphabet.py`
    **ここ1つ**で、この関数が持つのは「触ってよい並びか」の門だけ。

    門（どれも実測ではなく**壊さない側**から先に置いたもの）:

      (1) **かなの連続がまるごと綴りとして読めること。**
          1文字でも余ったら触らない（`カーソル` `ディスプレイ`
          `ですます` はここで落ちる）。部分一致では動かない。
      (2) **字が2つ以上**。ただし**直後に数字が続くなら1つでよい**
          （`エフ2`）。`える`（得る）`あい`（愛）`わい`（我）の
          ような1字ぶんの読みが、単独で英字になってしまうのを防ぐ。
      (3) **その並びが1語として在るなら触らない**（項目48-FC と
          同じ門）。`わいわい` `あいあい` `だぶる` `ええ` が
          ここで守られる。表と語彙と辞書の3つに聞く。
      (4) **直前が漢字なら触らない。** 漢字に続くかなは送り仮名で
          ある可能性が高く、字の読みと字面で区別が付かない。
      (5) **直前・直後が英数字なら触らない**（`F えふ` `2えふ`）。

    前後の機能語は剥がして試す（`えいちでぃーえむあいを` の `を`）。
    剥がす道具は既にあるものを使う
    （`_leading_particle_len` / `_trailing_functional_len`）。
    **剥がす長さは 0 から見立てまで全部試す**（項目48-UB）——2通りだけ
    だと、見立てが1文字多いだけで綴りに届かず黙って落ちる。

    ★ **先頭に剥がせるのは助詞だけ**（`_leading_particle_len` の作り）。
    `このえいちでぃーえむあいを` の `この` は連体詞なので剥がれず、
    **この形はまだ直らない**（説明文が「この も剥がす」と書いていたのは
    誤り。48-UB で直した）。

    返り値は `[(start, end, 置き換える文字列), ...]`。**長さが変わる**
    ので、呼ぶ側は1文字置換ではなく切り貼りで当てること。
    """
    import alphabet as _AB
    out = []
    n = len(line)
    i = 0
    while i < n:
        if not _AB.is_kana_char(line[i]):
            i += 1
            continue
        j = i
        while j < n and _AB.is_kana_char(line[j]):
            j += 1
        run = line[i:j]
        digits = _AB.trailing_digits(line, j)
        # **読みの注記は綴りに変えない**（項目48-LN・うにさんの規則
        # 「英語読みも同様」。`KyTea（キューティー）` の キューティー
        # が QT になった・実測）
        if kana_is_mentioned(line, i, j):
            i = j + digits
            continue
        # (4)(5) 前後の字。行端は「無い」として通す
        _prev = line[i - 1] if i > 0 else ''
        _next = line[j + digits] if j + digits < n else ''

        def _ascii_alnum(ch):
            # **`str.isalnum()` は日本語にも True を返す。**
            # ここで素の isalnum を使うと、直後の助詞（`を`）や
            # 漢字（`端子`）で全部が弾かれる（実測。的が5つとも
            # 直らなかった原因）。見たいのは**英数字**だけ。
            return bool(ch) and ch.isascii() and ch.isalnum()

        if (_prev and (is_kanji(_prev) or _ascii_alnum(_prev))) \
                or _ascii_alnum(_next):
            i = j + digits
            continue
        head_n = _leading_particle_len(run)
        tail_n = _trailing_functional_len(run)
        # ★★ **剥がす長さは 0 から全部試す**（項目48-UB・2026-09-07）。
        # `0 と全部` の2通りしか試していなかったため、剥がす長さの
        # 見立てが1文字でも多いと**綴りに届かないまま黙って落ちて**いた。
        #
        #   `エイチディーエムアイを`  末尾＝1（`を`）      → HDMI  ○
        #   `えいちでぃーえむあいを`  末尾＝**2**（`いを`）→ 届かない ×
        #
        # ひらがなだと解析の切れ目が変わって `い` まで機能語に数える。
        # **うにさん自身が挙げた例**（2026-08-23・`えいちでぃーえむあい`）が
        # ひらがなでは直らなくなっていた。
        #
        # 見立てより**多く**は剥がさない（上限は今までどおり）。
        # **少ない側から試す**——剥がさないほど本体が長く、門(1)
        # 「まるごと綴りとして読める」が厳しくなるので、いちばん
        # 確かな読み方から採る（今までの並び順と同じ意味）。
        # 途中の長さを増やしても、門(1)・門(2)「字が2つ以上」・
        # 門(3)「1語として在るなら触らない」・門(6)はそのまま掛かる。
        hit = None
        for head in range(0, head_n + 1):
            for tail in range(0, tail_n + 1):
                s0, e0 = i + head, j - tail
                if e0 - s0 < 2:
                    continue
                # 末尾を削ったなら、その先の数字は綴りの一部ではない
                d = digits if tail == 0 else 0
                body = line[s0:e0]
                letters = _AB.spell_out(body)          # (1)
                if not letters:
                    continue
                if len(letters) < 2 and d == 0:        # (2)
                    continue
                if d == 0 and len(set(letters)) == 1:
                    # (6) **同じ字の繰り返しだけなら触らない。**
                    # `ワイワイ` `ブイブイ` `キューキュー` のような
                    # 声の形は、字を綴ったものではない。数字が
                    # 続くとき（`エフ2`）は綴りと見てよい。
                    continue
                if _kana_run_is_ordinary_word(body, store, dict_index):
                    continue                            # (3)
                hit = (s0, e0 + d, letters + line[e0:e0 + d])
                break
            if hit:
                break
        if hit:
            _trace('アルファベット',
                   f'{line[hit[0]:hit[1]]!r} → {hit[2]!r}')
            out.append(hit)
        i = j + digits
    return out


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


# 設計35 の「この表記で正しいと確認した」印（項目48-JL）。
# 呼び出し側はこれを受けたら**他の同音の道も止める**（触らない確定）。
_D35_KEEP = object()


def _design35_fix(surface, reading, surrounding_words, attest_text,
                  after_text='', prev_text=''):
    """
    **設計35: AI が焼いた同音異義語の対の表**で直せるか（項目48-JJ）。

    うにさんの指定「**見本がなくても補正できないといけません**」
    （2026-08-25）。的リストの1行目の定義そのもの——「同音異義語：
    **対の単語に合わせる形**で同じ意味を持つもの」。
    本人の回数・履歴・育った共起は**一切見ない**——うにさんのメモは
    誤変換の議論だらけで、誤変換の側の count と共起まで育っている
    （48-IQ）。表（`homophone_pairs.py`・版つき・方向つき）は世の中の
    結びつきを AI が書いた閉じた表で、**直す側の手がかりが周りに在り、
    書かれている側の手がかりが1つも無い**ときだけ動く。

    置く場所は2つの入口（evaluate_candidate の頭＝count の盾より前、
    _homophone_by_context の頭＝活用形の道・48-IQ）。中身はここ1か所。
    """
    if not surrounding_words:
        return None
    # **「X」で括られた語は、言及であって使用ではない**（引用の守り。
    # `※「治り」を右クリック…` の 治り を直すと説明が壊れる——実測）。
    # attest_text はこの語を1つの空白に伏せた行（または行そのもの）
    # なので、伏せ字ごしの `「 」` と、別の出現の `「語」` を見る。
    if attest_text and ('「 」' in attest_text
                        or ('「' + surface + '」') in attest_text):
        return None
    try:
        import homophone_pairs as _hp
        material = tuple(w for w in surrounding_words if w and w != surface)
        fix = _hp.find_fix(surface, material, after=after_text,
                           prev=prev_text)
    except Exception:
        return None
    if fix == getattr(_hp, 'KEEP', None):
        # 書かれている側の手がかりが在る＝この表記で正しいと確認。
        # 方針2（毒された共起で逆を指すことがある・48-IQ）も止める
        _trace('同音', f'{surface!r} は対の表の手がかりが「この表記で'
                       f'正しい」と言うので、どの同音の道でも触らない')
        return _D35_KEEP
    if not fix or fix == surface:
        return None
    # 複合動詞の一部（思い出す・書き換わる が表に在る形）は
    # 今までどおり触らない（項目48-IQ の守り）
    if not _is_all_kanji(surface) \
            and _compound_verb_backed(surface, reading, attest_text):
        return None
    _trace('同音', f'{surface!r} → 対の表の手がかりで '
                   f'{fix!r} に合わせる（設計35）')
    return (fix, 'その他', EVIDENCE_VECTOR)


def _homophone_by_context(surface, reading, store, context_vec,
                          surrounding_words, dict_index=None,
                          attest_text='', after_text='', prev_text=''):
    """
    方針2: 正しく書けている漢字語を、同じ読みの別の表記へ、
    周りの語との共起だけを根拠に置き換えてよいか。

    「明確に誤りだと言えるか」で採否を決めるという原則の、唯一の
    例外にあたる経路なので、次をすべて満たすときだけ通す。

      - 書かれている表記が**漢字だけ**なら、置き換え先も漢字だけで
        **字数が同じ**
      - **漢字＋送り仮名**（活用形）なら（項目48-IQ・初期状態のため）:
          送り仮名を揃えて作った同音の別表記（`_conjugated_alts`）
          ／**複合動詞の一部なら触らない**（`書き換わる` が表に在る）
          ／**書かれている語に周りの支持があるなら触らない**
          （_HOMOPHONE_HELD_MAX_CONJ。育った共起が誤変換の行から
            学んだ `思い↔動作` で正しい `重い` を壊すのを止める）
          ／共起で決まらなければ**並記**（同じ行に文字どおり在る）を
          二番手にする
      - 置き換え先に使用実績がある（_HOMOPHONE_MIN_USAGE 以上。
        10 → 2・項目48-IQ。初期語彙が通るように）
      - 周りの語が、書かれている表記より置き換え先を
        **はっきり支持している**（_HOMOPHONE_MIN_MARGIN 以上の差）
      - **選び終わったあと**、置き換え先の側だけを「共通の共起相手が
        _HOMOPHONE_MIN_SHARED 語以上（活用形は _CONJ＝3）」の証拠に
        限って測り直しても、まだ差が保つ（項目48-BY。**落とすことしか
        しない関門**）

    判断そのものは既存の pick_best_by_context に委ねる
    （補正の判断経路を増やさない、という設計原則のため）。
    書かれている表記を候補に混ぜて比べるので、差は
    「今の表記に対してどれだけ勝っているか」になる。

    戻り値: (置き換え先の表記, カテゴリ, 証拠の強さ) または None
    """
    if context_vec is None or not surrounding_words:
        return None
    # 設計35（項目48-JJ）はここにも置く——この関数は evaluate_candidate
    # の is_known_word の道のほかに、**活用形の道（48-IQ・語尾で切られた
    # 映る/思い/描く の入口）からも直接呼ばれる**（学び22: 門・表は
    # 全部の道に）。中身は `_design35_fix` の1か所。
    _fix35 = _design35_fix(surface, reading, surrounding_words, attest_text,
                           after_text=after_text, prev_text=prev_text)
    if _fix35 is _D35_KEEP:
        return None
    if _fix35:
        return _fix35
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
        attest_alts = [a for a in _conjugated_alts(surface, reading, store)
                       if attest_text and a['surface'] in attest_text]
        # 並記（同じ行に別の表記が文字どおり書かれている）は、
        # **共起で決まらなかったときの二番手**にする（項目48-IQ）。
        # 先にしていたら `「に」と売ってエンターを…次のキーを撃った`
        # の行で、同じ行に在る `撃っ` を採った（共起は `打っ` 0.335・
        # `撃っ` 0 で、打っ を指していた）。
        # **共起で測る**（項目48-IQ・2026-08-22）。
        #
        # 48-DZ は「並記が無いときは何もしない。共起に落とさないこと」
        # と書いた。根拠は育った語彙での `書き換わり → 書き変わり`
        # （`換わり` 対 `変わり` +0.211）。**それは育った共起の話**で、
        # 初期状態の共起（`seed_context.py` の話題のまとまり）は
        # こちらが書いたものなので、同じ形の誤爆は材料で測れる。
        # うにさんの指定「初期状態を重要視」「壊さないことを恐れすぎない」
        # により、**下の漢字だけの語と同じ門（差・証拠の太さ）**で通す。
        # 何が壊れたかは項目48-IQ に名前で書く。
        made = _conjugated_alts(surface, reading, store,
                                skip_self_backed=False)
        if not made:
            return None
        # **複合動詞の一部なら触らない**（項目48-IQ）。
        # `書き換わりました` の `換わり` は、単独では `変わり` と
        # 共起で競るが、直前の `書き` と合わせた **`書き換わる` が
        # 表の語**である（48-DZ の誤爆はこれ）。塊まるごとが語なら
        # 中の対は見ない、という 48-IP と同じ考え方。
        if _compound_verb_backed(surface, reading, attest_text):
            _trace('同音', f'{surface!r} は複合動詞の一部（表に在る）'
                           f'なので置き換えない')
            return None
        alts = made
    else:
        attest_alts = []
        alts = [e for e in store.lookup(reading)
                if e['surface'] != surface
                and e['count'] >= _HOMOPHONE_MIN_USAGE
                and len(e['surface']) == len(surface)
                and _is_all_kanji(e['surface'])]
    if not alts:
        return None

    # ★★ **その読みで最後に選んだ表記があるなら、それが最優先**
    # （項目48-QH・2026-09-05）。うにさんの指定:
    #
    #   「同音異義語の一覧表を作成し、**最後にどの変換をしたか、
    #     それぞれ履歴1回分記録します**」
    #
    # 回数（`_HOMOPHONE_MIN_USAGE` の実績・`demote_homophones` の
    # 0.2倍）でやっていたことを、**1枠の上書き**に置き換えた形。
    # 共起（下）より先に見る——共起はうにさんのメモが誤変換の議論
    # だらけで毒されうる（項目48-IQ）が、**枠は本人が選んだ事実**。
    #
    # **枠が「いま書かれている表記」を指しているなら動かさない。**
    # 本人が最後にそう選んだのだから、それが正しい（学び「正しく
    # 書いたものを壊さない ＞ 直る」）。
    try:
        import last_choice as _lc_frame
        _framed = _lc_frame.surface_for_reading(reading)
    except Exception:
        _framed = None
    if _framed:
        if _framed == surface:
            _trace('同音', f'{surface!r} は前回この読みで選んだ表記'
                           f'なので動かさない（項目48-QH）')
            return None
        _fe = next((e for e in alts if e['surface'] == _framed), None)
        if _fe is not None:
            _trace('同音', f'{surface!r} → 前回この読みで選んだ '
                           f'{_framed!r} に合わせる（項目48-QH）')
            return (_framed, _fe.get('category', 'その他'), EVIDENCE_VECTOR)

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

    def _attest_fallback():
        """
        並記の二番手——**使わない**（項目48-IQ・実測で外した）。

        育った語彙で `映します。⇒ 移します。` の**右側**（正しい
        `移し`）が `映し` に返された。うにさんの語彙は誤変換の
        `映す` を学んでいて `移す` を持たないので、「語彙の裏打ちが
        ある側は動かさない」が**逆向きに効く**。並記は左右どちらからも
        成り立つので、向きは共起でしか決められない。記録だけ残す。
        """
        if attest_alts:
            _trace('同音', f'{surface!r} は同じ行に並記があるが、'
                           f'共起が決めないので動かさない')
            # (c) 並記がある＝メモのどこかに正しい形が文字どおり在る。
            # 直しは決めないが、認識は紫で残す（項目48-JH。
            # 並記の右側は `_flag_homophone_unsure` が弾く）
            _flag_homophone_unsure(
                surface, [a['surface'] for a in attest_alts], attest_text)
        return None

    margin = _HOMOPHONE_MIN_MARGIN
    if conjugated:
        # **書かれている語も置き換え先も、その文字そのものは材料から外す**
        # （項目48-IQ）。上下の行に同じ誤変換が書いてあると（`治り` の
        # 議論の行）、自分との一致（similarity=1.0）が「支持」に見える。
        # 同じ行に並記があると、置き換え先の文字がそのまま材料に居て
        # **右側（正しい `汲んで`）が左の `組んで` に返される**。
        # 繰り返した誤変換も並記も共起ではない。向きは共起だけで決める。
        _self_forms = {surface}
        _st, _tl = _split_stem_tail_local(surface)
        if _st and _tl:
            for _bt in _CONJ_TO_BASE.get(_tl[-1], ()):
                _self_forms.add(_st + _tl[:-1] + _bt)
        _alt_forms = set()
        for e in alts:
            _alt_forms.add(e['surface'])
            _alt_forms.add(vec_of[e['surface']])
        material = tuple(w for w in material
                         if w not in _self_forms and w not in _alt_forms)
        if not material:
            return None
        margin = _HOMOPHONE_MIN_MARGIN_CONJ
        # 書かれている語の支持は**基本形でも**見る（`汲ん` の文脈は
        # `汲む` が持っている）。どれか1つでも支持があれば動かさない。
        # 支持は**共通の相手2語以上**で数える（項目48-BY と同じ太さ）。
        # 話題のまとまりどうしは `画面` のような語を共有するので、
        # 1語の共有だけでは「支持」にならない（`映る`↔`チャット` は
        # `画面` 1語を共有して 0.152 出るが、2語なら 0）。
        try:
            held0 = max(context_vec.context_score(
                            f, material, min_shared=_HOMOPHONE_MIN_SHARED)
                        for f in _self_forms)
        except Exception:
            held0 = 0.0
        if held0 >= _HOMOPHONE_HELD_MAX_CONJ:
            _trace('同音', f'{surface!r} は周りの語の支持がある'
                           f'（{held0:.3f}）ので活用形の道では動かさない')
            # 認識（紫）をここで出すのは**試して外した**（項目48-JH）。
            # 「置き換え先にも同等以上の太い証拠がある」を条件にしたが、
            # 育ちの共起は誤変換の行からも学ぶ（48-IQ・思い↔動作）ので、
            # **正しい `動作が重い` の 重い に紫が6行以上立った**。
            # 支持どうしの綱引きでは正誤が割れない（48-IQ の実測と同じ
            # 結論）。認識も (b) 棄却・(c) 並記 の2つだけに絞る。
            return _attest_fallback()
    try:
        picked_vec = context_vec.pick_best_by_context(
            [surface] + [vec_of[e['surface']] for e in alts], material,
            min_margin=margin)
    except Exception:
        return None
    if not picked_vec or picked_vec == surface:
        return _attest_fallback()
    picked = next((e['surface'] for e in alts
                   if vec_of[e['surface']] == picked_vec), None)
    if not picked or picked == surface:
        return _attest_fallback()

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
            picked_vec, material,
            min_shared=(_HOMOPHONE_MIN_SHARED_CONJ if conjugated
                        else _HOMOPHONE_MIN_SHARED))
        held = context_vec.context_score(surface, material)
    except Exception:
        return None
    if thick - held < margin:
        _trace('同音', f'{surface!r} → {picked!r} は証拠が細い（棄却）')
        # (b) 差では {picked} が勝っていた。直しは棄却するが、
        # 「合っていないかもしれない」の認識は紫で残す（項目48-JH）
        _flag_homophone_unsure(surface, [picked, picked_vec], attest_text)
        return _attest_fallback()

    entry = next((e for e in alts if e['surface'] == picked), None)
    if entry is None:
        return None
    _trace('同音', f'{surface!r} → 周りの語が {picked!r} を強く支持')
    return (picked, entry['category'], EVIDENCE_VECTOR)


def evaluate_candidate(surface, reading, store, context_vocab,
                       find_readings, max_dist, is_known_word=False,
                       context_vec=None, surrounding_words=None,
                       dict_index=None, attest_text='', after_text='',
                       prev_text=''):
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
    # --- 0. 設計35: AI が焼いた同音異義語の対の表（項目48-JJ）--------
    # 下の 1.（count>=2 の盾）と辞書の盾（48-CF）より**先に**見る——
    # うにさんのメモでは誤変換の側の count まで育っているため。
    # 中身と根拠は `_design35_fix`。
    _fix35 = _design35_fix(surface, reading, surrounding_words, attest_text,
                           after_text=after_text, prev_text=prev_text)
    if _fix35 is _D35_KEEP:
        return None
    if _fix35:
        return _fix35

    # --- 1. 既に正しく書けているなら触らない ---
    # ★★ **その読みで最後に選んだ表記そのものなら、触らない**
    # （項目48-QH）。語彙に立っていなくても、本人が選んだ事実は
    # 「立っている」より強い証拠（うにさんの指定・2026-09-05）。
    try:
        import last_choice as _lc_eval
        if _lc_eval.surface_for_reading(reading) == surface:
            return None
    except Exception:
        pass
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
                                     attest_text=attest_text,
                                     after_text=after_text)

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


def _span_inside_one_token(tokens, a, b):
    """
    **その範囲は、1つの語の**中**に収まっているか**（項目48-UL・2026-09-07）。

    文全体の解析が「ここからここまでで1語」と言っていて、範囲がその
    **内側**（＝語より短い）なら、範囲は**語の一部でしかない**。

        ひっくり返す   解析は 0〜6 で1語（動詞:自立・ひっくりかえす）
        かな連続 `ひっくり` は 0〜4 ＝ **語の中の断片**

    この形に「かなの語と機能語で説明が付くか」（項目48-IS）を聞いては
    いけない。**断片は、語でも機能語でもないので必ず説明が付かない**。
    実際 `ひっくり` は説明できない側に落ち、芯の再構築が
    **`びっくり`** に直していた（`ひっくり返す` はごく普通の語）。

    範囲が語ちょうどのとき（`a == 語頭 and b == 語尾`）は **False**——
    そのときは断片ではなく語そのものなので、今までどおり見る。

    ★★ **囲んでいる語は、同梱の表も「語だ」と言うものだけ**
    （項目48-UL''・2026-09-07・**測って足した**）。解析は誤字の上にも
    平気で語を当てる——`ぎょうがい`（業界の誤り）を **`ぎょうが`＋`い`**、
    `おもろしう` を **`おもろし`＋`う`** と割る。この当て推量を
    「1語だから触るな」の証拠にすると、**直っていた誤字が直らなくなる**
    （実測で readcheck の直りが 2 落ちた）。

        ひっくり返す  解析=1語  表=**語**   → 断片扱い（守る）
        さまざま      解析=1語  表=**語**   → 断片扱い（守る）
        ぎょうが      解析=1語  表=無い     → 断片扱いにしない（直す）
        おもろし      解析=1語  表=無い     → 同上

    **2つの目が揃ったときだけ**（48-DE「推測の上に推測を重ねない」）。
    """
    if a >= b:
        return False        # 空の範囲は「語の中」ではない（検品で指摘）
    for t in (tokens or ()):
        if not t[5]:
            continue                    # 読みの立たない語は証拠にしない
        if not (t[3] <= a and b <= t[4] and (t[4] - t[3]) > (b - a)):
            continue
        # ★ **表が読めないときは門を掛けない**（ほかの門と同じ向き。
        # 検品で指摘——ここだけ `except` が `return True` に落ちていて、
        # 「意見なし」なのに補正を止める側へ倒れていた）
        try:
            import seed_japanese as _sj_sp1
            if _sj_sp1.is_unit(t[0]) is not True:
                continue                # 解析の当て推量は証拠にしない
        except Exception:
            continue
        return True
    return False


def _chunk_with_okurigana_is_word(line, a, b):
    """
    **塊のうしろに送り仮名を足すと、表の語になるか**（項目48-VB・
    2026-09-07）。

    塊の切り出しは**漢字で終わる**ことがあるので、うしろに続く
    ひらがな（＝送り仮名）まで含めて初めて1語になる形を取りこぼす。

        揺さ振ら   表に在る（`is_unit` True）
        塊は **`揺さ振`**（漢字で終わる）→ `suggest_for_run` が
        読みを `こうさてん` と推して **`交差点`** にしていた
        （`飛上がら → 非常がら`・`突き披け → 突撃け` も同じ形）

    うしろのひらがなを1字ずつ足して、**どれかで表の語になれば True**。
    足すのは**4字まで**（送り仮名はそれ以上伸びない）。

    表が読めなければ False（＝今までどおり）。
    """
    if not line or a >= b or b >= len(line):
        return False
    try:
        import seed_japanese as _sj_ok
    except Exception:
        return False
    for k in range(1, 5):
        e = b + k
        if e > len(line) or not is_hiragana(line[e - 1]):
            break
        try:
            if _sj_ok.is_unit(line[a:e]) is True:
                return True
        except Exception:
            return False
    return False


def _kata_run_is_word(line, a, b):
    """
    **その範囲を含むカタカナの連なりが、まるごと1語か**（項目48-VA・
    2026-09-07）。

    範囲がカタカナ（＋`ー`）だけで、**左右へ字の種類で伸ばした連なり**が
    同梱の表の語なら、範囲は**語の一部でしかない**。

        ショートライン  同梱の表に在る（`is_unit` True）
        ところが解析は **ショー|トラ|イン**（**人名として割る**）ので、
        異様の対 `('ショー', 'トラ')` から印 `ショートラ` ができ、
        **`ショートに`** に直していた

    ★ **解析の切れ目は当てにならない**——カタカナ語は人名に割られやすい。
      だから `_span_inside_one_token`（解析の位置で見るもの）ではなく、
      **字の種類で伸ばして表に聞く**。

    伸びなければ False（＝連なりそのもの。今までどおり見る）。
    表が読めなければ False。
    """
    if not line or a >= b:
        return False

    def _k(c):
        return ('ァ' <= c <= 'ヶ') or c == 'ー'

    if not all(_k(c) for c in line[a:b]):
        return False
    s0, e0 = a, b
    while s0 > 0 and _k(line[s0 - 1]):
        s0 -= 1
    while e0 < len(line) and _k(line[e0]):
        e0 += 1
    if (e0 - s0) <= (b - a):
        return False
    try:
        import seed_japanese as _sj_kr2
        return _sj_kr2.is_unit(line[s0:e0]) is True
    except Exception:
        return False


def _starts_inside_word(tokens, a, kana_only=False):
    """
    **その位置は、1つの語の途中か**（項目48-UN・2026-09-07）。

    文全体の解析が「ここからここまでで1語」と言っていて、`a` がその
    **内側**（語頭でも語尾でもない）なら、`a` から始まる窓の頭は
    **前の漢字に付く送り仮名**である。

        思いやり   解析は 0〜4 で1語（名詞）
        かな連続は `いやりがありました`＝**1 から始まる** ＝ 語の途中

    ここを書き換えると、**前に在る漢字ごと語が壊れる**——実機の語彙で
    `思いやり` が **`思稲荷`**（`いやり` を `いなり` と読んで組み直し）に
    なっていた。

    `_span_inside_one_token` と同じく、**囲む語は同梱の表も「語だ」と
    言うものだけ**（解析は誤字の上にも語を当てる・48-DE）。

    ★★ `kana_only=True` は**かなだけの語**に限る（項目48-UX'・
    2026-09-07・**測って足した**）。漢字＋送り仮名の語（`打ち`）では、
    かな連続は**送り仮名から始まるのが普通**なので、そこを「語の途中」と
    数えると**ほとんどの窓が消える**——`かな打ちでのほらい` の紫まで
    消えた（見張りが捕まえた）。かなだけの語（`わざわざ`）を途中から
    切るのとは別の話。
    """
    for t in (tokens or ()):
        if not t[5]:
            continue
        if not (t[3] < a < t[4]):
            continue
        if kana_only and any(is_kanji(c) for c in (t[0] or '')):
            continue
        try:
            import seed_japanese as _sj_si
            if _sj_si.is_unit(t[0]) is not True:
                continue
        except Exception:
            continue
        return True
    return False


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
    for surface, pos, _reading, s, e, has_reading, *_ in covered:
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
    for surface, pos, reading, s, e, has_reading, *_ in tokens or ():
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


# **ひらがな1字の頻度の順**（項目48-IS）。拮抗が最後まで解けないときの
# 決め手。一般的な日本語の文中での出現の多い順（こちらの知識から
# 書き下した閉じた表。増えない）。前にあるほどよく使う字。
_KANA_FREQ_ORDER = ('いんうしのかとたくてになるはがをでこきもすまりさおれら'
                    'つよだあせけろえめじわちみどばほごゆぶげびむへねざぎふ'
                    'ずやぐぞぜひべぼぬぱぴぷぺぽぢづゃゅょっぁぃぅぇぉゔ')
_KANA_FREQ_RANK = {c: i for i, c in enumerate(_KANA_FREQ_ORDER)}


def _kana_freq_score(reading):
    """読みの字がどれだけよく使う字か（大きいほど一般的）。"""
    n = len(_KANA_FREQ_ORDER)
    vals = [n - _KANA_FREQ_RANK.get(c, n) for c in reading]
    return sum(vals) / max(1, len(vals))


# **拮抗を「字の並び」で決めるときに要る差**（2026-08-28・仮の値）。
# `charngram.logp_parts` の合計対数確率で、1位と2位がこれ未満しか
# 離れていなければ意見を言わない（呼び出し側が字の頻度に進む）。
# 対数の 1.0 ＝ 出現の比でおよそ e 倍。**測って決め直すこと。**
_TRI_TIE_MARGIN = 1.0


def _tri_tie_enabled():
    """
    **拮抗の決め手に文字3連を使うか**（2026-08-28・測るための切り替え）。

    うにさんの検討「どの文字の次にどの文字が来やすいか等、言語の
    特徴を補正に用いて、隣接キーの候補に優先順位を付けたり、脱字の
    文字が何か推測したりする」。既定は使わない。`CN_TRI_TIE=1` の
    ときだけ、字の頻度（1字のジップ順・48-IS）の**手前**に
    `_break_tie_by_charngram` が入る。測って差が出たら既定にする。
    """
    import os as _os
    return _os.environ.get('CN_TRI_TIE') == '1'


def _break_tie_by_charngram(candidates, window='', c_s=0, c_e=0):
    """
    拮抗が最後まで解けないとき、**文字の並び**（文字3連）で決める
    （2026-08-28・うにさんの検討）。

    字の頻度（1字のジップ順）より1段情報が多い——候補を**窓に
    はめ込んだ形**で前後の文字ごと測るので、「この場所に来やすい
    字か」で並ぶ。隣接キー候補・脱字の推測字・濁点の付け外しが
    同じ費用で並んだとき、その場所の文脈で順位が付く。

    **新しい補正は生まない。** ここへ来るのは異様判定が立って
    （decisive）、門を通った候補だけ。順番を決めるだけ。
    差が `_TRI_TIE_MARGIN` 未満なら None（意見なし）。

    **同じ長さの候補にだけ意見を言う。** 3連表は畳んだ（短い）形の
    ほうを 99.4% 「自然」と読む偏りがある（probe_tri_power の D）。
    長さの違う候補を比べさせたら、正しい入れ替え形 `せいざい` より
    切り詰め形 `せいざ` を採って2行壊した（2026-08-28 に実測）。
    """
    try:
        import charngram
        if not charngram.available():
            return None
    except Exception:
        return None
    if len({len(r) for r, _c, _e in candidates}) > 1:
        return None
    scored = []
    for r, _c, _e in candidates:
        text = (window[:c_s] + r + window[c_e:]) if window else r
        total, n = charngram.logp_parts(text)
        if not n:
            return None
        scored.append((total, r))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) >= 2 and scored[0][0] - scored[1][0] < _TRI_TIE_MARGIN:
        return None
    return scored[0][1]


# **読みの並び（yomigram）で拮抗を決めるときに要る差**（2026-08-28・
# 仮の値。合計対数確率で、1位と2位がこれ未満なら意見を言わない）。
_YOMI_TIE_MARGIN = 1.0


def _yomi_tie_mode():
    """
    **拮抗の決め手に「読みの並び」を使うか**（2026-08-28・うにさんの
    指定「次に来やすいキーは、各種補正よりも先に見てください」を
    受けた測るための切り替え）。

        CN_YOMI_TIE=1   字の頻度の**手前**に入れる（保守的な置き方）
        CN_YOMI_TIE=2   連鎖の**頭**（周りの語より先）に入れる
                        （「先に見る」の文字どおりの置き方）
        CN_YOMI_TIE=3   **並べ替えの問いにだけ**答える（順序限定・
                        字の頻度の手前）。2026-08-28・うにさんの指定
                        「**効果のあるものを活かす**ようにしたい」
        CN_YOMI_TIE=4   3 に加えて、**異様な連続のときだけ**
                        （`_kana_run_explained` が説明を付けたら黙る）。
                        うにさんの指定「**自然な文であれば補正しなくて
                        いい**ので、**異様な文に対してのみ活用**する」
        それ以外        使わない（既定）

    表は `yomigram`（読みの3連・同梱のみ）。表記の3連（CN_TRI_TIE）は
    読みに無力だと測って落ちた——読みの表は 順序違い71.7%・隣接キー
    3位内28.4%・怪しい箇所±1 71.3%（probe_tri_power --yomi・初期）。

    **1/2 は測って入れなかった**（項目48-KL）。理由は「最後の拮抗まで
    落ちる場面は**どれも在り得る語**の同点で、頻度の重みはかえって
    多数派の語へ引っ張る」——トランシット→トランペット・
    せきにん→せっきん・しんつう→しんせつ。**どれも「別の字を含む
    候補」＝語の見分けの問い**で、表がいちばん弱いところだった
    （語の表を焼き足した強い表でも同じ・ytie1b）。
    一方 **順序違いの向きは 92.8%**（項目48-KL の A）。
    3/4 は「**表が強い問いにだけ意見を言わせる**」置き方。
    """
    import os as _os
    v = _os.environ.get('CN_YOMI_TIE')
    return int(v) if v in ('1', '2', '3', '4') else 0


def _same_letters(a, b):
    """**同じ字の並べ替えか**（順序の問いかどうかの判定・2026-08-28）。"""
    return len(a) == len(b) and sorted(a) == sorted(b)


def _break_tie_by_yomigram(candidates, window='', c_s=0, c_e=0,
                           order_only=False):
    """
    拮抗を**読みの並び**（読みの文字3連）で決める（2026-08-28）。

    候補を窓にはめ込んだ形で `yomigram.logp_parts`（合計対数確率）に
    より並べる。各位置で「前の2文字から3文字目に来やすいか」を掛け
    合わせるので、**うにさんの指定（前2文字→3文字目・文頭は ^^・
    文末は $）がそのまま入っている**。差が `_YOMI_TIE_MARGIN` 未満なら
    None（意見なし・呼び出し側が次の決め手へ進む）。

    **新しい補正は生まない**——異様判定が立って（decisive）門を通った
    候補の順番を決めるだけ。

    order_only=True なら、**候補が全部「芯と同じ字の並べ替え」のとき
    だけ**意見を言う（CN_YOMI_TIE=3/4）。字が1つでも違えば
    「語の見分けの問い」なので黙る——そこが 1/2 を落とした理由
    そのもの（トランシット／トランペットは字が違う）。
    """
    try:
        import yomigram
        if not yomigram.available():
            return None
    except Exception:
        return None
    if order_only:
        core = window[c_s:c_e] if window else ''
        if not core or len(candidates) < 2:
            return None
        # **字を1つも変えない問いだけ**（＝並べ替え＝順序違い 92.8%）
        if not all(_same_letters(r, core) for r, _c, _e in candidates):
            return None
    scored = []
    for r, _c, _e in candidates:
        text = (window[:c_s] + r + window[c_e:]) if window else r
        total, n = yomigram.logp_parts(text)
        if not n:
            return None
        scored.append((total, r))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) >= 2 and scored[0][0] - scored[1][0] < _YOMI_TIE_MARGIN:
        return None
    return scored[0][1]


def _yomi_prior_enabled():
    """
    **設計27 の候補の並べ順に「読みの並び」を足すか**（2026-08-28・
    測るための切り替え。`CN_YOMI_PRIOR=1` のときだけ）。

    設計27 の並べ順は 実績（-cnt）が主軸（項目48-IE・うにさんの指定
    「実績のいちばん高い候補に直す」）。これは動かさない。**実績が
    同点のとき**、いままで並び順の最後が表記の五十音順（＝でたらめ）
    だったところを、開いた読みの自然さで並べる。
    """
    import os as _os
    return _os.environ.get('CN_YOMI_PRIOR') == '1'


def _yomi_prior_bucket(reading):
    """
    読みの並びの自然さを**大まかな段**にしたもの（小さいほど自然）。

    連続値のまま並べ順に入れると、僅差の揺れが答えを揺らすので、
    0.5 きざみの段に丸める。表が無ければ 0（＝意見なし・全員同段）。
    """
    try:
        import yomigram
        if not yomigram.available():
            return 0
    except Exception:
        return 0
    s = yomigram.score(reading)
    return -int(s * 2)      # score は負の値。自然なほど小さい段になる


def _break_tie_by_kana_frequency(candidates):
    """
    拮抗が最後まで解けないとき、**字の頻度**で決める（項目48-IS）。

    うにさんの指定（2026-08-23）:「優先順位が付かなければ、平仮名1文字の
    頻度分析を導入します。すべての1文字のひらがなに順序をつけます」。
    同点なら None（呼び出し側が先頭を採る）。
    """
    scored = sorted(((_kana_freq_score(r), r) for r, _c, _e in candidates),
                    reverse=True)
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1] if scored else None


def _table_word_spans(run):
    """
    かな連続の中で**表の語（かなで書かれる語・2字以上）**が占める範囲の
    一覧（項目48-IS）。芯がその途中から始まる・途中で終わるなら、
    芯の切り方がずれている（`やがいぶんしょう` の芯 `いぶんしょう` は
    `やがい` の途中から）。表が無ければ []。
    """
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        words = None
    if not words:
        return []
    n = len(run)
    out = []
    # 3字以上の語だけ見る。2字の語（`きに` `のち`）は助詞の組と
    # 区別が付かず、`だいんき|に` `たんごの|ちながり` の正しい芯まで
    # 「語の途中」に見えた（実測）。
    for i in range(n):
        for ln in range(3, min(12, n - i) + 1):
            if run[i:i + ln] in words:
                out.append((i, i + ln))
    return out


def _unexplained_mask(run):
    """
    かな連続の各字が「かなの語・機能語で説明が付かない」かの並び
    （項目48-IS）。`これはん` → [False, False, False, True]。
    説明の付く字（機能語・表の語）は、読めない芯でも動かさない。
    表が無ければ全部 True（意見なし＝制限しない）。
    """
    n = len(run)
    if not n:
        return []
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        words = None
    funcs = (set(PARTICLES_MULTI) | set(AUXILIARY_TAILS)
             | set(DEMONSTRATIVES) | set(FUNCTION_NOUNS)
             | set(BASIC_VERB_FORMS) | {'よい', 'いい', 'ない'})
    # **守るのは機能語の字だけ**。表の語まで守ると `すき|にん` の
    # ように「語の直結で読めない」並びが全部守られて、`かくにん` に
    # 届かない（実測して戻した）。読めない芯では、語の側は動かしてよい。
    explained = [False] * n
    for i in range(n):
        if run[i] in PARTICLES_1CHAR:
            explained[i] = True
        for ln in range(2, min(12, n - i) + 1):
            frag = run[i:i + ln]
            if frag in funcs:
                for k in range(i, i + ln):
                    explained[k] = True
    return [not x for x in explained]


_FINAL_PARTICLES = set('よねわさぞぜ')


def _keys_adjacent(a, b):
    """2つのかなが、かな配列で隣のキーか（濁点・拗音の差も近い）。"""
    if not a or not b or a == b:
        return False
    try:
        from kana_layout import nearby_candidates as _near
        return any(alt == b and d <= 1.0
                   for alt, d in _near(a, max_dist=1.0, include_phonetic=False))
    except Exception:
        return False


def _only_particles(rest):
    """残りが空か、助詞だけか（`かーそね|を`・項目48-IT）。`ん` は含めない。"""
    if not rest:
        return True
    if rest in PARTICLES_MULTI:
        return True
    return all(c in PARTICLES_1CHAR for c in rest)


def _is_expressive_strict(run):
    """
    伸ばし・擬音の形の**狭いほう**（項目48-IT）。`_is_expressive_kana_run`
    は「ーが1つあれば」伸ばし言葉と見るので `かーそね` まで擬音になる。
    外来語の打ち間違いを疑うときは、**末尾が ー／ーん／ーっ／小書き**か
    **同じ並びの繰り返し**だけを擬音とする（くぅーん・どりーん・みかーん
    は擬音、かーそね は違う）。
    """
    if not run:
        return False
    if run.endswith(('ー', 'ーん', 'ーっ')) or run[-1] in 'ぁぃぅぇぉっ':
        return True
    half = len(run) // 2
    return len(run) >= 4 and run[:half] == run[half:half * 2]


def _loan_typo_plausible(body, kata):
    """
    ひらがなの並び body を外来語 kata に直すのが、**打ち間違いの形**として
    説明できるか（項目48-IT）。2字目以降の隣のキー1つ／脱字／余分／
    入れ替え、のどれか1手で、かつ元がかなの語と機能語で説明できない。
    """
    try:
        from loanword import katakana_to_hiragana as _k2h, single_edit
    except Exception:
        return False
    if _kana_run_explained(body):
        return False
    # 2字の並びは、隣のキー1つでいくらでも別の語に届く（`めね → メモ`・
    # 初期状態の readcheck で実測）。うにさんの例は4字（かーそね）。
    if len(body) < 3:
        return False
    # **かなで書いたそれ自体がカタカナ語として表に在る**なら、本人は
    # 正しい語をかなで書いただけ（`すりーぷ`＝スリープ → スープ にした・
    # 実機のメモで実測・項目48-IU）。
    try:
        from loanword import hiragana_to_katakana as _h2k
        if _in_word_table(_h2k(body)):
            return False
    except Exception:
        pass
    target = _k2h(kata)
    kind, a, b, i = single_edit(body, target)
    if kind == '置換':
        return i >= 1 and _keys_adjacent(a, b)
    # 脱字は、**ひらがなの並びそのものに外来語の印**（長音・外来音
    # ぃぇぉゔ・でゅ 等）があるときだけ。印の無い 3〜4字のかなは、
    # 1字足せば何かのカタカナ語に届いてしまう（`げんい → ゲンセイ`
    # `きんん → キンカン` `びっく → ビックリ` `たんこ → タコ`・初期状態の
    # readcheck と実機のメモで実測）。`かーそね` `でぃすぷれ` は印がある。
    # 余分・入替も印があれば見る（`しぇららっく → シェラック`
    # `ちぇすれた → チェレスタ`・初期 readcheck で 35件。外すと失う）。
    if not _loan_signature(body):
        return False
    return kind in ('脱字', '余分', '入替')


def _loan_signature(body):
    """ひらがなの並びに**外来語らしい印**があるか（項目48-IT）。"""
    return (any(c in 'ーぃぇぉゔ' for c in body)
            or any(x in body for x in ('でゅ', 'てゅ', 'ふゅ', 'ゔ')))


def _is_dropout_fix(run, fixed):
    """
    カタカナの直しが**脱字**（1字足す）だけか（項目48-IT）。
    2語に割れて読める並び（ディス＋レイ）を直してよいのは、脱字で
    表の語（ディスプレイ）に届くときだけ。置換（キーコード→キーボード）は
    本人の複合語を壊す（seedcheck で実測）。
    """
    try:
        from loanword import katakana_to_hiragana as _k2h, single_edit
        kind = single_edit(_k2h(run), _k2h(fixed))[0]
    except Exception:
        return False
    return kind == '脱字'


def _in_word_table(text):
    """同梱の表（`oddness` の語）に、その表記がまるごと在るか。"""
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        return False
    return bool(words) and text in words


_COMMON_WORD_COST = 150


def _strict_pieces():
    pieces = (set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
              | set(DEMONSTRATIVES) | set(CONNECTIVES)
              | set(FUNCTION_NOUNS) | set(BASIC_VERB_FORMS)
              | {'よい', 'いい', 'ない'})
    return {x for x in pieces if len(x) >= 2}


#: **現代語の五段動詞が在る行**（項目48-PJ・2026-09-03）。
#: `_GODAN_ROW` は `ず`／`づ`／`ふ`／`ぷ`／`ゆ` も持っているが、
#: **現代語にその行の五段動詞は無い**（文語の `あふ`・`かふ`、名詞の
#: `まず`・`つづ`・`ほっぷ` が「活用形」に化けて、4行だけで
#: **1,281 の幻の形**ができていた・実測）。
_GODAN_LIVE = ('う', 'く', 'ぐ', 'す', 'つ', 'ぬ', 'ぶ', 'む', 'る')

#: 「その語は動詞か」の控え（解析に1回だけ聞く）。
_VERB_WORD_CACHE = {}


def _is_verb_word(word):
    """
    その語は**動詞**か（項目48-PJ・2026-09-03）。

    ウ段で終わる語を全部「五段動詞」と見ると、**名詞まで活用する**:

        てつ（鉄・費用115） → `てて` が「活用形」→ `示し**てて**います` の
                              2度押しが説明できてしまい、直りが消えた
        りす（137）→ `りし` ／ とつ（突・0）→ `とと` も同じ（実測）

    **解析に聞く。品詞を言えないときは False**（＝この道は黙る。
    janome の無い環境のモックは `'*'` しか返さない・48-PG と同じ構え）。
    """
    got = _VERB_WORD_CACHE.get(word)
    if got is not None:
        return got
    out = False
    try:
        from morphology import tokenize as _mtok_v
        toks = [t for t in _mtok_v(word) if getattr(t, 'surface', '')]
        out = (len(toks) == 1
               and (getattr(toks[0], 'pos', '') or '') == '動詞')
    except Exception:
        out = False
    if len(_VERB_WORD_CACHE) > 20000:
        _VERB_WORD_CACHE.clear()
    _VERB_WORD_CACHE[word] = out
    return out


#: **「よく使う語の動詞の活用形か」の控え**（項目48-PJ・2026-09-03）。
_COMMON_VERB_FORM_CACHE = {}


def _is_common_verb_form(frag):
    """
    その並びは、**よく使う語の動詞の活用形**か（項目48-PJ・2026-09-03）。

    48-IT の物差し（`_kana_run_explained_common`）は「よく使う語＋
    機能語で説明できるか」で異様を決めるが、**活用を知らなかった**:

        きかない  ＝ きく（動詞）の未然形 きか ＋ ない
        → `きか` は表に無い（`きく` は在る）ので「説明できない＝異様」
        → 48-IT が `かない` に直した（**触る前から壊れていた**）

    48-KS の `pos_grammar` は「表の語がウ段で終われば動詞とみなし、
    語幹＋活用形も語と認める」を持っている——**片方にしか無い**
    （学び22）。

    **`pos_grammar.explain_kana_run` に丸投げしてはいけない。**
    あちらは語の表を**費用で絞らずに**使う（778,340語）ので、
    `すねると` まで説明が付いてしまい、48-IT の的が消える（実測）。
    借りるのは **`_GODAN_ROW` / `_ICHIDAN_TAIL`（つなぎ方の表）だけ**で、
    語の母集合は「よく使う語」（費用 ≤ `_COMMON_WORD_COST`）のまま。

    **辞書形の側から引く**（活用形を全部作らない）。作ると 122,076形・
    13.5MB・**6.4秒**かかった（実測）。ここは1文字ずつの敷き詰めから
    何度も呼ばれるので、**逆に辿って控える**:

        きか → 語尾 `か` は `く` の行（かきくけこ）→ `きく` は
               よく使う語か？（費用 137）→ **在る**
        たべ → `たべ + る` がよく使う語で、`べ` がエ段 → 一段の語幹

    五段は あ／い／え／お段＋音便（っ・ん・い）、一段は語幹。
    """
    got = _COMMON_VERB_FORM_CACHE.get(frag)
    if got is not None:
        return got
    out = False
    if len(frag) >= 2:
        try:
            from pos_grammar import _GODAN_ROW, _ICHIDAN_TAIL
            import oddness as _odd_cv
            words = _odd_cv._load() or frozenset()

            def _common(w):
                if w not in words:
                    return False
                c = _table_cost(w)
                # **`c is not None` で見る**——`かく`・`とる` の費用は
                # **0** で、`c or 9999` のような書き方をすると落ちる
                return c is not None and c <= _COMMON_WORD_COST

            stem, last = frag[:-1], frag[-1]
            for u in _GODAN_LIVE:
                if last in _GODAN_ROW[u] and _common(stem + u) \
                        and _is_verb_word(stem + u):
                    out = True
                    break
            if not out and frag[-1] in _ICHIDAN_TAIL \
                    and _common(frag + 'る') and _is_verb_word(frag + 'る'):
                out = True                      # 一段の語幹（たべ・み）
        except Exception:
            out = False
    if len(_COMMON_VERB_FORM_CACHE) > 20000:
        _COMMON_VERB_FORM_CACHE.clear()
    _COMMON_VERB_FORM_CACHE[frag] = out
    return out


def _kana_run_explained_common(run):
    """
    かな連続が、**よく使う語**（同梱の表で費用 _COMMON_WORD_COST 以下）と
    機能語だけで説明できるか（項目48-IT）。`_kana_run_explained` の
    語の側を「よく使う語」に絞ったもの。珍しい語（すねる 181）は
    説明に数えないので、`すねると` は説明が付かず異様のまま。
    """
    if not run:
        return True
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        return False
    if not words:
        return False
    funcs = _strict_pieces()
    n = len(run)
    reach = [set() for _ in range(n + 1)]
    reach[0].add('start')
    # **頭の「お」「ご」は美化語の接頭**（項目48-MH・2026-08-31）。
    # `_is_functional_strict` は 48-LN でここを持っている（`おかれて
    # いる`）のに、**こちらの道には無かった**——同じ判定が片方にしか
    # 置かれていない形（学び22）。そのせいで
    #
    #     おせわになりました → **おわになりました**   ← 同梱の見本を壊す
    #
    # が出ていた（`せわになりました` は説明が付くのに、頭に `お` が
    # 付いた途端に「説明できない＝異様」になり、`せ` を隣接キーの
    # 巻き込みと見て落としていた。`seedcheck` の唯一の壊し）。
    # **閉じた文法の類**（新しく増えない2字）であって、語の表ではない。
    # 続きが説明できるときだけ通るので安全側。
    if n >= 3 and run[0] in 'おご':
        reach[1].add('func')
    for i in range(n):
        if not reach[i]:
            continue
        kinds = reach[i]
        if run[i] in PARTICLES_1CHAR or run[i] == 'ん':
            reach[i + 1].add('func')
        for ln in range(2, min(12, n - i) + 1):
            frag = run[i:i + ln]
            if frag in funcs:
                reach[i + ln].add('func')
            if (kinds - {'word'}):
                # **`or` で並べる**（項目48-PJ）。`elif` にすると効かない
                # ——`きか` は表に**在る**（費用 185・気化／帰化）ので
                # `frag in words` が True になり、費用の門で落ちたあと
                # 活用形の側へ行かない（実測）。同じ形が
                # `きけ` 161・`きこ` 180・`きい` 156 にもある
                c = _table_cost(frag) if frag in words else None
                if ((c is not None and c <= _COMMON_WORD_COST)
                        or _is_common_verb_form(frag)):
                    reach[i + ln].add('word')
    return bool(reach[n])


def _is_functional_strict(run):
    """
    機能語の並びとして**きちんと**説明できるか（項目48-IT）。
    `_is_all_functional` は `う` `く` `し` のような1字の活用語尾も
    部品にするので、`がうく`（うまく から ま を落とした形）まで通る。
    ここでは **2字以上の機能語か、1字の助詞**だけを部品にする。
    """
    pieces = (set(AUXILIARY_TAILS) | set(PARTICLES_MULTI)
              | set(DEMONSTRATIVES) | set(CONNECTIVES)
              | set(FUNCTION_NOUNS) | set(BASIC_VERB_FORMS)
              | {'よい', 'いい', 'ない'})
    pieces = {x for x in pieces if len(x) >= 2}
    # **使役・受身の て形**も部品（項目48-LN・2026-08-30。うにさんの
    # 誤検知報告 `連鎖させていく → 連鎖させいく`——していく・
    # になっていく は通るのに、させて が部品に無くて て/い の隣接
    # キーから「巻き込み」と誤解していた）
    pieces |= {'させて', 'されて', 'させられて'}
    n = len(run)
    # 位置 → そこに至った部品の種類（'start' / 'p1'＝1字の助詞 / 'piece'）
    reach = [set() for _ in range(n + 1)]
    reach[0].add('start')
    # **頭の「お」は敬語の接頭**（項目48-LN・2026-08-30。うにさんの
    # 誤検知報告 `おかれている → かれている`——お＋動詞のかな書き
    # 〔置かれ〕を知らず、お/か の隣接キーから「巻き込み」と誤解して
    # お を落としていた。続きが説明できるときだけ通るので安全側）
    if n >= 3 and run[0] == 'お':
        reach[1].add('piece')
    for i in range(n):
        if not reach[i]:
            continue
        # 1字の助詞。**「し」**（接続助詞・する の連用形）も1字の部品
        # （`効きますし、` `したいということで`・実機のメモで実測。
        #   無いと `ますし` が異様になり `し` を落として壊した）。
        if run[i] in PARTICLES_1CHAR or run[i] == 'し':
            reach[i + 1].add('p1')
        # **て・で の直後の「い」**（補助動詞 いる の連用形）も部品
        # （項目48-KX'・2026-08-29。無いと `していたり` が異様になり
        #   い を落として `してたり` に壊した——うにさんの一覧の
        #   「動詞のように見えて、後ろの平仮名のつながりが合わない」
        #   は、こちらの部品が足りない側だった。て＋いる は
        #   pos_grammar の接続と同じ規則。がうく の穴は開かない——
        #   い を置けるのは て・で の直後だけ）。
        if run[i] == 'い' and i > 0 and run[i - 1] in 'てで':
            reach[i + 1].add('piece')
        # 「た」も て・で の直後に置ける——**ていた の話し言葉**
        # （できてた・行ってた。項目48-LK・2026-08-30 うにさんの
        # 誤検知報告「補正できてたものが → 補正できたものが」——
        # てた を知らず、て/た が隣のキーなので「巻き込み」と誤解して
        # て を落としていた）
        if run[i] == 'た' and i > 0 and run[i - 1] in 'てで':
            reach[i + 1].add('piece')
        # 「ん」（助動詞・撥音）は**1字の助詞の直後には置けない**
        # （`これはん`。`分からん` `をみません` は置ける）。
        if run[i] == 'ん' and (reach[i] - {'p1'}):
            reach[i + 1].add('piece')
        for pc in pieces:
            if run.startswith(pc, i):
                reach[i + len(pc)].add('piece')
    return bool(reach[n])


def _doubled_is_word_boundary(window, i, tokenize_fn=None):
    """
    **同じ助詞が2つ並んだ所は、語の切れ目か**（項目48-UV・2026-09-07）。

    `これは` ＋ `はなし` のように、**前の語に付く助詞**と**次の語の頭**が
    たまたま同じ字だと、`はは` の並びができる。これは打ちすぎではない。

        これははなしです  → **これはなしです**（は が1つ消えた）
        これははなやかの… → **これはなやかの…**
        これははしの…     → **これはしの…**

    どれもうにさんが書いても不思議のない形で、**意味が変わる**。

    見分けは**解析の切れ目**で行う（表の語で見ると足りない——
    `_is_all_functional('はなし')` は は＋な＋し で True になり、
    `_strict_pieces` にも `とか` は入っていない。**測って外した**）:

      (1) 2つ目より前が**2文字以上**（窓の頭の2度押しを外す）
      (2) 解析が **`i+1` ちょうどで語を始めて**いて、それが
          **内容語**（名詞／動詞:自立／形容詞:自立）
      (3) その手前の語が**助詞**で、`i+1` で終わっている

    実測（枠と的の見分け）:

        これ|は|**はなし**   (1)(2)(3) 揃う → 打ちすぎではない
        なんと|**とか**      (2) が助詞なので × → 今までどおり直す
        わ|かかし           `かかし` は i+1 から始まらない × → 直す
        ね|**ばば**|し      同上 ×／はも|に|に|か  (2) が助詞 ×
        に|に|し|て（頭）    (1) で × ／ ささ|れる|ので（頭） (1) で ×

    `tokenize_fn` が無ければ False（＝今までどおり打ちすぎと見る）。
    """
    if i < 2 or tokenize_fn is None:
        return False
    try:
        toks = list(tokenize_fn(window) or ())
    except Exception:
        return False
    _left = False
    _right = False
    for t in toks:
        pos = t[1] or ''
        if t[4] == i + 1 and pos.startswith('助詞'):
            _left = True
        if t[3] == i + 1 and (pos.startswith('名詞')
                              or pos.startswith('動詞:自立')
                              or pos.startswith('形容詞:自立')):
            _right = True
    return _left and _right


def _fix_functional_run(window, after_kanji=False, store=None,
                        tokenize_fn=None):
    """
    **機能語の並びの異様**（項目48-IT・2026-08-23）。うにさんの指定:

        「ような書式ににして」は「ににして」が異様。ただし「ににして」
        という文字列に対して修正するのではなく、**構成する要素で判定**
        します。「に」の連続を押しすぎと捉えれば「ような書式にして」。
        「オンマウスすねると」の「すねると」が異様。「ね」と「る」が
        隣接キーなので**巻き込んで押した**と疑う。片方が消えて
        「すねと」「すると」が候補に出て、自然に繋がる文字列は見つかる。
        「いいですよわね」も同じ。

    この窓は今まで「機能語だけ」「送り仮名＋機能語」として**門の外**
    だった（設計29 は自然さの表で裁こうとして壊れた・項目48-IA）。
    ここでは自然さの表を使わず、**要素の形**だけで見る:

      異様の印（どれか）
        (1) 同じ1字の助詞が2つ続く          ににして
        (2) 終助詞が3つ続く                  よわね
        (3) 機能語だけでは説明が付かない     すねると（すねる が要る）
      直し方
        (1) は片方を落とす
        隣のキーが続いている所は、**片方を落とす**（巻き込み）
      受け入れ
        直した並びが**機能語だけで説明できる**こと（すると・にして・
        いいですよね）。2つ以上残るなら、落とした字が**珍しい字**の
        ほう（巻き込まれた側は、普段打たない字）。同点なら触らない。

    戻り値: 直した並び。直さないなら None。
    """
    if not window or len(window) < 3:
        return None
    if not all(is_hiragana(c) or c == 'ー' for c in window):
        return None
    n = len(window)
    strict_pieces = _strict_pieces()

    def _starts_piece(i):
        return any(window.startswith(pc, i) for pc in strict_pieces)

    def _ends_piece(i):
        return any(window[:i + 1].endswith(pc) for pc in strict_pieces)

    # (1) 同じ助詞の連続。ただし2つ目が**2字以上の機能語の頭**なら
    #     連続ではない（`正規表現でできる` の `でで`＝で＋できる・実測）。
    #     1つ目が**2字以上の機能語の尻尾**でも連続ではない
    #     （`意味がないことと、` の `とと`＝こと＋と・実機のメモで実測）。
    # **同じ1字の助詞の連続に、活用形の免除は入れない**（項目48-PJ・
    # 2026-09-03・**測って外した**）。`かかない`（書か＋ない）を守ろうと
    # して「その2字が活用形なら押しすぎではない」を入れたが、
    # **送り仮名の頭の2度押しを丸ごと素通り**させた（手書き16行のうち
    # 11行・紫すら立たない）:
    #
    #     表示さされるので → **無変化**（旧は `表示される`）
    #     直さされてしまいます／記憶さされています／動かかして／
    #     確かかにします／つかかいました
    #
    # かな連続は**漢字の直後から始まる**ので、送り仮名の2度押しは
    # ちょうど窓の頭（i==0）に来る——絞っても救えない。
    # `かかない`・`ささやかな` は**触る前から壊れている**別の穴
    # （引き継ぎ N23。窓が語の途中を切っている）。
    # ★ **2つ目が新しい語の頭なら押しすぎではない**（項目48-UV）
    doubled = any(window[i] == window[i + 1] and window[i] in PARTICLES_1CHAR
                  and not _starts_piece(i + 1) and not _ends_piece(i)
                  and not _doubled_is_word_boundary(window, i,
                                                    tokenize_fn)
                  for i in range(n - 1))
    finals = 0
    run = 0
    for c in window:
        run = run + 1 if c in _FINAL_PARTICLES else 0
        finals = max(finals, run)
    # 元が**厳密な機能語の並び**（をみます・させないわよ・分からんかね）
    # なら、(1)(2) の印が無い限り異様ではない。
    original_ok = _is_functional_strict(window)
    # 元が**よく使う語**（同梱の表で費用 _COMMON_WORD_COST 以下）と機能語で
    # 説明できるなら異様ではない（`たらり` `くるり` `あんまり` `ひとつに`・
    # fpcheck で実測）。`すねる`（181）のような珍しい語は説明に数えない。
    if not original_ok and _kana_run_explained_common(window):
        return None
    # ★★ **まるごと1語なら、機能語の並びの異様ではない**（項目48-UF・
    # 2026-09-07）。
    #
    # ①（異様か）の中身は `doubled`（同じ助詞の押しすぎ）・
    # `finals >= 3`（終助詞3連）・**`not original_ok`**（厳密な機能語の
    # 並びではない）の3つ。3つ目は**内容語なら必ず立つ**ので、
    # 上の「よく使う語なら異様ではない」だけが内容語を守っていた。
    # ところがその物差しは**よく使う語だけ**（費用 `_COMMON_WORD_COST`
    # 以下）なので、**同梱の表に在るが珍しい語**が丸ごと素通りしていた:
    #
    #     かいとる（買い取る） → **かいる**    かきすて → **かきて**
    #     たるめる → **ためる**                 いてる（凍てる） → **いる**
    #     のまさ → **のさ**                     もらわ → **もわ**
    #     きょろ → **きょり**                   にぎりづめ → **にきりつめ**
    #
    # `tools_local/probe_seed_intact.py` で見つけた。**別の道は自分から
    # 断れていた**——`かきすて` には 48-EN が
    # 「世の中に在る語なので触らない」と言い、48-AE が「単体でも読める」と
    # 言っていたのに、この道だけが走って壊していた（48-QX と同じ形）。
    #
    # ★ **`doubled` と `finals >= 3` はそのまま**。あちらは
    # 「同じ字を2度打った」「終助詞が3つ」という**打鍵の形そのもの**が
    # 証拠なので、語であることでは覆らない（`表示さされる` を守る）。
    # ここで外すのは「機能語の並びではない」という**内容語なら必ず立つ**
    # 印だけ。
    if not original_ok and not doubled and finals < 3:
        try:
            import seed_japanese as _sj_ff
            if _sj_ff.is_unit(window) is True:
                return None
        except Exception:
            pass
        # ★★ **本人が書いた語も同じ**（項目48-UO・2026-09-07）。
        # 同梱の表は**かなで書いた形**を持たないことがある——
        # `まもなく` は表に無い（`間もなく` は在る）のに、うにさんの
        # 語彙には `まもなく`／`間もなく` として在った。それでも
        # **`もなく`** に直していた（`ま` を巻き込みで落とす）。
        # 窓の道は「この読みが語彙にあるので触らない」と**先に断って
        # いた**のに、この控えが最後に当たっていた（48-QX と同じ形）。
        #
        # ★ `store` を渡されたときだけ見る（渡さない呼び手は今までどおり）。
        # ★ 立っているのが「機能語の並びではない」だけのときに限る——
        #   押しすぎ・終助詞3連は**打鍵の形そのもの**が証拠なので、
        #   語であることでは覆らない（48-UF と同じ線）。
        if store is not None:
            # ★ **「立っているか」は決められた読み方で聞く**
            # （`vocabulary.entry_is_solid`・検品で指摘・2026-09-07）。
            # `e['count']` はいまは `solid` の写しでしかなく、
            # **巡4 で片付ける予定**（48-QG）。そのとき `KeyError` が
            # 黙って `except` に落ちて、**この門が静かに効かなくなる**。
            try:
                from vocabulary import entry_is_solid as _eis
                if any(_eis(e) for e in store.lookup(window)):
                    return None
            except Exception:
                pass
        # ★★ **内容語が2つ以上ある窓は、機能語の並びではない**
        # （項目48-UP・2026-09-07）。
        #
        # この道が見ているのは「**機能語の並び**の中の打ち損ね」——
        # うにさんの例はどれも**内容語が1つ以下**:
        #
        #     すねると 1 ／ ににして 1 ／ いいですよわね 1 ／ さされるので 0
        #
        # ところが窓は助詞をまたいで伸びるので、**語＋助詞＋用言**まで
        # 1つの窓になることがある。そこへ「隣のキーを巻き込んだ」を
        # 当てると、**先頭の語の1字が落ちる**:
        #
        #     あけれがありました → **あれがありました**（内容語2）
        #     ややがありました   → **やがありました**（内容語2）
        #     すねるがありました → **するがありました**（内容語2）
        #
        # 数えるのは `_sm_content_count`（48-SM で作ったもの。
        # 接頭・接尾・非自立・助詞・助動詞・記号・数を除いて数える）——
        # **新しい判定を作らない**（48-GN）。
        # 解析できないときは 99（＝多い側）を返すので、**渡されなければ
        # 今までどおり**（`tokenize_fn` が None なら見ない）。
        if tokenize_fn is not None:
            # ★ **解析できなければ意見なし**（検品で指摘）。
            # `_sm_content_count` は解析に失敗すると **99**（多い側）を
            # 返すので、そのままだと「内容語が2つ以上」に化けて
            # **門が掛かってしまう**。ほかの門と同じく、
            # 分からないときは**掛けない**に倒す。
            try:
                _n_ct = _sm_content_count(window, tokenize_fn)
            except Exception:
                _n_ct = None
            if _n_ct is not None and 2 <= _n_ct < 99:
                return None
    odd = doubled or finals >= 3 or not original_ok
    if not odd:
        return None
    # ★★ **巻き込みを疑うのは、その並びが文法の形をしているときだけ**
    # （項目48-UQ・2026-09-07）。
    #
    # 「隣のキーを一緒に押した」＝**打ちたかった語は在って、そこに1字
    # 余計に入った**という見立て。だから**残りが文法の形をしている**
    # ことが要る。うにさんの例はどれもそうなっている:
    #
    #     すねると（拗ねる＋と）／いいですよわね／さされるので／はいてく
    #
    # 形をしていない並びで1字落とすのは、ただの当て推量だった。
    # `readcheck` の初期で **19件**がこの形で化けていた——どれも
    # **脱字や順序違いの誤字**で、1字落として短くしただけ:
    #
    #     こうい（公倍→公益の誤り）→ **こう**    たいう → **たい**
    #     どこく → **どこ**   そかう → **そう**   まんし → **んし**
    #     こいう → **こう**   いしく → **いく**   つしよ → **しよ**
    #
    # 判定は `pos_grammar.explain_kana_run(stems_only=True)`——48-TH で
    # 使っているものと**同じ**（新しい判定を作らない・48-GN）。
    # 表が読めなければ True（意見なし＝今までどおり）。
    #
    # ★ **押しすぎ（同じ助詞の2度打ち）と終助詞3連には掛けない**。
    #   あちらは**打鍵の形そのもの**が証拠なので、文法の形は要らない
    #   （`ににして` は文法の形をしていないが、`に` の2度打ちが見えている）。
    _maki_ok = True
    if not (doubled or finals >= 3):
        try:
            import pos_grammar as _pg_mk
            _maki_ok = bool(_pg_mk.explain_kana_run(window,
                                                    stems_only=True))
        except Exception:
            _maki_ok = True
    cands = {}
    for i in range(n - 1):
        a, b = window[i], window[i + 1]
        if a == b and a in PARTICLES_1CHAR:
            cands.setdefault(window[:i] + window[i + 1:], ('押しすぎ', a))
        elif a != b and _keys_adjacent(a, b):
            # ★★ **漢字の直後のかな連続からは、巻き込みで字を落とさない**
            # （項目48-UK・2026-09-07）。
            #
            # 元は「**頭2字だけ**は送り仮名なので落とさない」だった
            # （`変わらない` の `わらない` から `ら` を落として `変わない`）。
            # ところが**送り仮名は2字で終わらない**。形容詞の
            # `〜ましい`（望ましい・目覚ましい・羨ましい・微笑ましい）は
            # 3字目の `い` が落ちる位置に来るので、そのまま通っていた:
            #
            #     望ましい  → **望まし**    目覚ましい → **目覚まし**
            #     思わしくない → **思わしない**（7つの活用形すべて）
            #     炊きたて  → **炊きた**
            #
            # `tools_local/probe_vocab_intact.py`（**本人の語彙 25,372 語**を
            # 1語ずつ当てる面）で見つけた。
            #
            # ★ **48-IT の的は失わない**。この道の的は
            # 「同じ助詞の押しすぎ」（`ににして`・`さされるので`）と
            # 「終助詞3連」（`いいですよわね`）で、どちらも**別の枝**。
            # 巻き込み（隣のキーを一緒に押した）が要るのは
            # `すねると → すると` のような**漢字の直後でない**連続。
            #
            # ★ なぜ全部止めるのか: 漢字の直後のかなは**送り仮名か、
            # そこから続く活用・助動詞**。どこで送り仮名が終わるかは
            # 字面では決められない（**学び13**）。決められないなら
            # **落とさない**（★★ 壊さない ＞ 直る）。
            if not after_kanji and _maki_ok:
                cands.setdefault(window[:i] + window[i + 1:], ('巻き込み', a))
                cands.setdefault(window[:i + 1] + window[i + 2:],
                                 ('巻き込み', b))
    ok = [(c, how, ch) for c, (how, ch) in cands.items()
          if c != window and len(c) >= 2 and _is_functional_strict(c)]
    if not ok:
        return None
    # 元が機能語だけで説明できるなら、(1)(2) の印が要る
    if original_ok and not (doubled or finals >= 3):
        return None
    pushed = [x for x in ok if x[1] == '押しすぎ']
    if pushed:
        ok = pushed
    if len(ok) == 1:
        return ok[0][0]
    # 落とした字が珍しいほう（巻き込まれた側）を採る。同点なら触らない
    scored = sorted(((_kana_freq_score(ch), c) for c, _h, ch in ok))
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _kana_run_explained(run, after_kanji=False, tokenize_fn=None,
                        before_kanji=None):
    """
    **かな連続が、かなで書かれる語と機能語だけで説明できるか**
    （項目48-IS・2026-08-23）。

    うにさんの問い:「`ひ|らん|が|な` が読めるは意味が分かりません。
    これらを詞の種類にした時、本当に横に並べて成立しますか？」
    ——成立しない。janome は `ひら(動詞)+ん(助動詞)+が+な` と割って
    「読める」と言うが、それは辞書の語を並べただけで日本語ではない。

    ここでは別の材料で見る: 同梱の表（`seed_japanese`）のうち
    **かなで書かれている語 80,649語**（＝実際にかなで書かれる語）と
    機能語（助詞・助動詞・活用語尾・指示語・形式名詞）だけで、
    連続をすき間なく説明できるか。決まり:

      - 語は2字以上。**1字の残り**（`ひ`）があれば説明できない
      - **語と語を直接つなげない**（`たん|あご` `すき|にん`）。
        かなの中で内容語が直結する形は複合語で、それなら表に
        まるごと在る（`たんあご` は無い）。間に機能語があれば続く
      - 連続まるごとが表の語なら説明できる

    表が無いときは True（意見なし＝今までどおり janome に任せる）。
    """
    if not run:
        return True
    if not all(is_hiragana(c) or c == 'ー' for c in run):
        return True
    # **動詞の未然形＋打消の「ん」**（項目48-OQ(f)・2026-09-03）。
    # `つまらん`（つまら〔未然形〕＋ん）は日本語の形だが、下の表の
    # 道は `つまら` を語として持たないので「説明できない」に倒れ、
    # 芯の再構築が **さんらん**（似た読み 2.0）に直していた
    # （実機メモ `つまらない ➔ 「つまらん」`）。
    # **文法として決まっている形**なので、標本の当たりの数では
    # 決めない（★★「論理的に正しいものは入れる」）。
    # 兄弟（しらん・わからん・たべん・できん）は語幹が表に在るので
    # 今までも通っていた——**つまら だけが表から漏れていた**。
    # `pos_grammar.explain_kana_run` を丸ごと借りるのは**駄目**
    # （測った: じゅんけしょう・おくゆくこてい まで「説明が付く」に
    # なって、直りが 2 落ちる）。**この形だけ**を足す。
    # **用言の活用＋機能語で説明が付くなら「読める」**（項目48-TH'・
    # 2026-09-06）。`やめたら`（やめる＋たら）・`ひどくて`（ひどい＋くて）は
    # かなの語の表に無く、この判定が「説明できない」と言って芯が
    # `やたら`・`ひとくち` に直した。48-KS の自動機は活用を知っている
    # （語の表は動詞・形容詞の根拠にだけ使う `stems_only`——名詞を
    # 敷き詰める読みは打ち間違いも説明してしまう〔48-SQ の実測〕）。
    # 同じ材料で答えが割れたら、文法の側を採る（48-QX）。芯は
    # 「明らかに自然になる直しだけ通す」側に置かれる
    try:
        import pos_grammar as _pg_is
        if _pg_is.explain_kana_run(run, after_kanji=after_kanji,
                                   before_kanji=before_kanji,
                                   stems_only=True):
            return True
    except Exception:
        pass
    if tokenize_fn is not None and len(run) >= 3 and run.endswith('ん'):
        try:
            _ts = [t for t in tokenize_fn(run) if t[0]]
        except Exception:
            _ts = []
        if (len(_ts) == 2 and (_ts[0][1] or '').startswith('動詞')
                and (_ts[0][6] if len(_ts[0]) > 6 else '') == '未然形'
                and _ts[1][0] == 'ん'
                and (_ts[1][1] or '').startswith('助動詞')):
            return True
    try:
        import oddness as _odd
        words = _odd._load()
    except Exception:
        return True
    if not words:
        return True
    if run in words:
        return True
    funcs = (set(PARTICLES_MULTI) | set(AUXILIARY_TAILS)
             | set(DEMONSTRATIVES) | set(FUNCTION_NOUNS)
             | set(BASIC_VERB_FORMS) | {'よい', 'いい', 'ない'})
    n = len(run)
    # 位置 → 直前に置いた種類の集合（'word' / 'func' / 'start'）
    reach = [set() for _ in range(n + 1)]
    reach[0].add('start')
    # **直前が漢字なら、頭の1〜2字は送り仮名**（項目48-IS・実測）。
    # `済んだらまず` の芯 `らまず` は `ら` が `済んだら` の送り仮名で、
    # それを残りの1字と見て読めない扱いにし、`まず → んず` に化けた。
    # `_covered_by_known` の after_kanji と同じ扱い。
    if after_kanji:
        for k in range(1, min(2, n) + 1):
            reach[k].add('func')
    for i in range(n):
        if not reach[i]:
            continue
        kinds = reach[i]
        if run[i] in PARTICLES_1CHAR:
            reach[i + 1].add('func')
        for ln in range(2, min(12, n - i) + 1):
            frag = run[i:i + ln]
            if frag in funcs:
                if _aux_needs_te(run, i, frag):
                    # **補助動詞の形なのに て形のあとではない**（48-PP）。
                    # 機能語ではなく**ふつうの動詞＝語**として置く
                    # （置けるのは直前が語でないときだけ）。
                    # 落としてしまうと `そういった`・`において`・
                    # `きます`・`があったので` まで説明が付かなくなる
                    # （実測で43件・どれも正しい日本語）
                    if (kinds - {'word'}):
                        reach[i + ln].add('word')
                else:
                    reach[i + ln].add('func')
            # 語は「直前が語ではない道」が1つでもあれば置ける。
            # `したのち` は `した` が機能語でも表の語でもあるので、
            # 「語の後ろに語」だけ見ると `のち` が置けなくなっていた。
            if frag in words and (kinds - {'word'}):
                reach[i + ln].add('word')
    return bool(reach[n])


def _aux_needs_te(run, i, frag):
    """
    **補助動詞の形なのに、直前が `て`／`で` でない**か（項目48-PP・
    2026-09-03）。

    48-IS（`_kana_run_explained`）は `BASIC_VERB_FORMS` を機能語として
    敷くので、`おくゆく` が **`おく`（機能語）＋`ゆく`（語）** で
    「説明が付く」になっていた——`おくゆくこてい`（奥行固定）の芯が
    48-AE の高い敷居に落ちる原因（実測）。

    **補助動詞は て形のあとにしか立てない。** それ以外の場所
    （行の頭・語のあと）では**ふつうの動詞＝語**として扱い、
    次の語を直結できないようにする。

    `する`・`できる`・`なる`・`いう` は**入れない**（`_AUX_VERB_AFTER_TE`
    の注記）——`かくにんできる`・`よくなる` のように、て形でなくても
    名詞・副詞に付く。
    """
    if frag not in _AUX_VERB_AFTER_TE:
        return False
    return not (i >= 1 and run[i - 1] in 'てで')


def _verb_noun_joined(run, tokenize_fn):
    """
    **動詞の基本形に、名詞が直付きになっているか**（項目48-PL(a)・
    2026-09-03・うにさんの指定）。

        「`解す咳` は「解す」動詞終止形、「咳」名詞。
          **品詞のつながりが異様**です」

    文法だけで見ると `書く本`・`見る目`・`読む人`（連体形＋名詞）と
    **同じ形**なので、**①（異様の判定）には使わない**。使うのは
    **④の敷居**（項目48-AE「読める並びを覆すほど自然にならないなら
    直さない」）の側——`かいすせき` を「読める」と数えるのをやめる。

    実測（`tools_local/probe_verb_noun.py`・26文）: `書く本`・`見る目`・
    `読む人`・`走る車`・`切る紙`・`食べる物`・`使う人`・`入る時`・
    `戻る先`・`押す場所`・`開く画面`・`選ぶ候補`・`残る文字`・`光る星`・
    `飛ぶ鳥`・`眠る猫` は**1つも動かない**——敷居が下がっても
    **直し先が無い**ので何も起きない。動くのは、下げたところに
    直し先が在る `かいすせき → かいせき` だけ。

    **`_looks_like_valid_japanese` そのものには入れない。** 入れて
    測ったら、ひらがな連続の古い道が「読めない連続」として先に走り、
    `かいすせき、を見てます` が `解析、` ではなく `かいせき、`（読みまで）
    になった（実機メモ 6:13 で実測）。掛けるのは**「読める」を決めて
    いる3か所**だけ（窓・芯・混合塊の敷居）。

    **もう1か所、48-PL(b')（2026-09-04）がここを①の門として引く**——
    `fallthrough_rebuild_ok` で「余分な隣のキー」の手を開くのは、
    この判定が立つ塊だけ（紫を立てる①ではなく、**強い手を開く前の
    異様判定**。正しい文に走らないための順番）。

    非自立・接尾の名詞は除く（`書くこと`・`する時` は正しい形）。
    """
    try:
        toks = tokenize_fn(run)
    except Exception:
        return False
    prev = None
    for t in toks:
        pos = t[1] or ''
        infl = (t[6] if len(t) > 6 else '') or ''
        if prev is not None and _verb_noun_pair(prev[0], prev[1], pos):
            return True
        prev = (pos, infl)
    return False


def _verb_noun_pair(prev_pos, prev_infl, pos):
    """
    **隣り合う2語が「動詞の基本形＋名詞の直付き」か**（48-PL の判定の
    芯・2026-09-04 に括り出した）。見るのは3つ:

        `_verb_noun_joined`（この上・④の敷居と 48-PL(b') の門）
        `units._refit_run_tail`（48-PV・壊れた連なりの末尾の切り直し）
        `explain.pos_lines`（48-PW・品詞判定に「つながりが異様」の注記）

    **判定は1本**（48-GN）。units と explain は手元の token で見るので、
    文字列を渡して解析し直させない（1行の組み立て・候補一覧の
    表示ごとに呼ばれる場所——重くしない）。
    """
    return ((prev_pos or '').startswith('動詞:自立')
            and prev_infl == '基本形'
            and (pos or '').startswith('名詞')
            and not (pos or '').startswith('名詞:非自立')
            and not (pos or '').startswith('名詞:接尾'))


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
    for surface, pos, reading, start, end, has_reading, *_ in toks:
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
        # **働いている助詞は吸収しない**（項目48-IS・実測）。
        # `だいんきに行きます` の芯 `だいんき → だいにんき` で、後ろの
        # `に` を「作り直した余り」と見て範囲に含め、`だいにんき行きます`
        # と助詞を食っていた。助詞の次がかな以外（漢字・記号・行末）なら、
        # その助詞は文をつないでいる字であって余りではない。
        _working_particle = (ch in PARTICLES_1CHAR
                             and (end + 1 >= len(line)
                                  or not is_hiragana(line[end + 1])))
        if (is_hiragana(ch) or is_katakana(ch)) \
                and not _working_particle \
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


#: 48-PK が見る1字の助詞（格助詞・係助詞だけ）。`PARTICLES_1CHAR` は
#: 終助詞（ね・よ・さ・な…）まで含むので使わない——`さかな`（頭 さか
#: ＝坂）のような**本物の1語**まで「語＋助詞」に割れてしまう。
_PK_PARTICLES = frozenset('がをにではもとへ')


def _target_splits_word_particle(reading, store):
    """
    **直し先の読みが「既知語＋1字助詞」に割れるか**（項目48-PK・
    2026-09-04・5巡目の指示書）。

    育った語彙は `かなで`(65) のような**「かな＋で」を学習で1語に
    取り込んだもの**を持っている。語彙の実績はあっても、
    **語＋助詞は語ではない**——それを直し先にすると、正しい構造の
    壊れた列がそこへ吸い込まれる:

        かなちでのほせい（かな打ちでの補正 の脱字）
          → ひらがな連続の道が「ち を落とすと在る語 `かなで`」で
            **かなでのほせい** に化けた（うにさんの画面17行・
            **育ちだけ**・実測。初期は かなで が無いので紫のまま）

    門: 末尾が1字の格助詞・係助詞（`_PK_PARTICLES`）／頭が2字以上で
    **実績2以上**の語彙の語。`_known_head_plus_functional`（入力側・
    残り2字以上）と向きが逆——こちらは**直し先の側**を見る。
    """
    if not reading or len(reading) < 3:
        return False
    if reading[-1] not in _PK_PARTICLES:
        return False
    try:
        return bool([e for e in store.lookup(reading[:-1])
                     if e['count'] >= 2])
    except Exception:
        return False



def _fold_repeat_to_word(run, store, tokenize_fn=None):
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
    if not _dup_repair_enabled():
        return None
    # **項目48-PB は測って外した**（2026-09-03）。うにさんの育ちで
    # `まあいいか → **まあいか**`（`まあ`＋`いい`＋`か` で、`いい` の
    # 二重は語の形そのもの。畳んだ `まあい` が育ちの語彙に在る）を
    # 止めようとして、2つの形を測った。**どちらも損のほうが大きい**:
    #
    #   ・「連続の全部のトークンに読みが立っているなら畳まない」
    #     → `よかかった → よかった`・`わるくくない → わるくない`・
    #       `おばばけ → おばけ` まで塞ぐ（2026-08-20 に測って
    #       初期40件・育ち80件の直りを失うと分かっている形）
    #   ・「連打の2字がまるごと機能語のトークンなら畳まない」
    #     → readcheck で **直り −5**（`やきいいも → やきいも`・
    #       `かいここう → かいこう`・`こうつつう → こうつう`・
    #       `はんここう → はんこう`・`さいいき → さいき`。
    #       どれも `いい`・`ここ`・`つつ` が機能語の表に在る）
    #
    # **`まあいいか` と `やきいいも` は、いま在るどの物差しでも
    # 区別が付かない**（`explain_kana_run` はどちらも True・
    # 畳んだあともどちらも True・トークンの並びも同じ形）。
    # 足りないのは「**畳み先が日本語として尤もらしいか**」で、
    # 48-HI は**語彙の実績**しか見ていない（48-KN と同じ型）。
    # `まあい` はうにさんが2回打っただけの断片。
    _fold_skip = set()
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
        if i in _fold_skip:
            continue                    # 機能語そのものの二重（項目48-PB）
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



# **順序違いの拮抗を、読みの並びで裁くか**（2026-08-28・うにさんの
# 指定「自然な文であれば補正しなくていいので、**異様な文に対しての
# み活用**することを検討して。**効果のあるものを活かす**ように
# したい」）。`CN_SWAP_TIE=1` のときだけ。既定は切り。
#
# `_swap_to_word` は「入れ替えを戻すと在る語になる」を1通りに絞った
# あと、**畳み・脱字・濁点でも在る語に届くなら降りる**（48-HJ の門。
# `いちん` の12件の化けを止めた実績がある）。降りた先は
# **「決め手が無いので直さない」**——CLAUDE.md ★★ の
# 「異様だと判定したら何かしらに決める。候補が複数あることは
# 身を引く理由にならない」に、まさに当たる場所。
#
# ここは**入れ替えか、そうでないか**の問いなので、読みの表がいちばん
# 強い問い（**順序違いの向き 92.8%**・項目48-KL の A）。語の見分け
# （トランシット／トランペット）ではないので、48-KL で落とした
# 置き方とは別物。
#
# 走るのはもともと**異様な連続だけ**（塊まるごとが在る語なら
# 呼び元の `known_or_bundled` と本体の門が先に守る）ので、
# うにさんの「自然な文には補正を実行しない」を満たしている。
_SWAP_TIE_MAX_RIVALS = 8
# 入れ替えの側がこれだけ自然でなければ、いままでどおり降りる
# （合計対数確率の差）。仮の値・測って決める。
_SWAP_TIE_MARGIN = 1.0


def _swap_tie_enabled():
    """
    **既定で入っている**（2026-08-28・項目48-KN）。`CN_SWAP_TIE=0` で
    切れる（48-KM の `CN_ABAB` と同じ形＝測って効いたので反転した）。
    """
    import os as _os
    return _os.environ.get('CN_SWAP_TIE') != '0'


def _swap_beats_rivals(answer, rivals):
    """
    入れ替えの答えが、拮抗する別の解釈より**読みとして自然**か。

    表が無ければ False（＝いままでどおり降りる）。**表が無い環境で
    答えが変わらない**ようにしておく（同梱の表なので実機では在る）。
    """
    try:
        import yomigram
        if not yomigram.available():
            return False
    except Exception:
        return False
    try:
        a_tot, a_n = yomigram.logp_parts(answer)
        if not a_n:
            return False
        best = None
        for r in rivals:
            r_tot, r_n = yomigram.logp_parts(r)
            if not r_n:
                continue
            if best is None or r_tot > best:
                best = r_tot
        if best is None:
            return False
        return (a_tot - best) >= _SWAP_TIE_MARGIN
    except Exception:
        return False


def _swap_to_word(run, store, after_kanji=False, keep_tail='',
                  tokenize_fn=None, starts_inside_word=False):
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
    # 48-VK: 両方の呼び口で、できあがった塊を入れ替えない。
    if _chunk_is_intact(run, tokenize_fn, after_kanji=after_kanji,
                        starts_inside_word=starts_inside_word):
        return None
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
    # **かな連続の最後の助詞は動かさない**（項目48-DJ をこの道にも
    # 掛ける・項目48-KR・2026-08-28）。
    #
    # 48-DJ は芯の道と従来の探索に在って、**入れ替えの道には
    # 掛かっていなかった**（学び22——片方だけに置くと、そちらを
    # 迂回する）。実際に迂回されていた:
    #
    #     かいんに行きます。        （助詞 `に` が末尾）
    #       入れ替え `かいんに` → `かいにん`（解任）が在る語
    #       → **`に` ごと食って** `かいにん行きます。`
    #
    # 助詞は「打ち間違いで紛れ込む文字ではなく、意図して打たれた
    # 区切り」（2026-08-09 の決まり・`_is_particle_drop` の説明）。
    #
    # **判断は呼び元の `run_tail_particle` に任せる**（48-DJ の
    # 唯一の判断点・「決めているのは最初の行」）。ここで
    # `run[-1] in PARTICLES_1CHAR` と自前に書いたら**大損した**——
    # `か` `さ` `ぞ` `と` `し` は**語の最後の字であると同時に
    # 助詞の字**なので、`こうんか`・`おばんさ`・`こうくぞ`・
    # `ばりりば` の語末の入れ替えまで塞いで
    # **初期 readcheck が 直った −11・化けた +2**（実測）。
    # `run_tail_particle` は「**かな連続の直後が漢字かカタカナ**」を
    # 見ているので、`「こうんか」と…` のような括弧・読点の前は
    # 助詞と数えない。
    for i in range(_i0, len(run) - 1):
        if run[i] == run[i + 1]:
            continue
        if keep_tail and i + 1 >= len(run) - len(keep_tail):
            continue        # 末尾の助詞を巻き込む入れ替えは見ない（48-DJ）
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
    # **拮抗する別の解釈**（畳み・脱字・濁点）を集める場所。
    # 既定（`CN_SWAP_TIE` が無い）では**1つ見つけた時点で降りる**——
    # いままでと1バイトも変わらない。切り替えを立てたときだけ、
    # 集めて読みの表に裁かせる（下の `_swap_beats_rivals`）。
    rivals = []
    _tie = _swap_tie_enabled()
    # 連打の畳みでも説明が付くなら触らない（拮抗）。
    # **畳みだけは、読みの表にも押し切らせない**（2026-08-28・
    # うにさんの判断）。`てんんか` を engine は `てんかん` に直して
    # いたが、**`てんか`（天下・点火・添加・転嫁…）のほうが日常的**で、
    # 元の `てんか` のままが正しい。readcheck は「語彙から採った語を
    # 壊して作る」ので、**壊す前の語が自動的に「正解」**になるだけ——
    # 日本語としてどちらが尤もらしいかは見ていない。
    # **ものさしの正解ラベルを、人の判断より優先しない。**
    # 素の下見（`tools_local/diag_swap_rivals.py`）でも、畳みが相手の
    # ときだけ 2正/3誤 と当てずっぽう以下だった。
    #
    # 畳みとの拮抗は「入れ替えか否か」ではなく
    # **「てんかん か てんか か」＝語の見分けの問い**で、48-KL で
    # 読みの表がいちばん弱いと測ったところ（トランシット／
    # トランペット）と同じ形。ここは語の一般的さに任せる。
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
        if len(rivals) >= _SWAP_TIE_MAX_RIVALS:
            break
        for ch in _chars:
            ins = run[:pos] + ch + run[pos:]
            for b in _bodies(ins):
                if len(b) >= 3 and _known(b):
                    if not _tie:
                        return None
                    rivals.append(ins)
                    break
            if len(rivals) >= _SWAP_TIE_MAX_RIVALS:
                break
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
                    if not _tie:
                        return None
                    rivals.append(var)
                    break
    # **語どうしで比べる**（2026-08-28・うにさんの指摘）。
    # `got[0][0]` は助詞が付いたままの並び（`てんかんを`）で、
    # `got[0][1]` が在る語の本体（`てんかん`）。生の並びで比べると
    # **助詞側の並びの差が勝ってしまう**——
    #     てんかんを −23.60 vs てんかを −29.54  差 +5.94（押し切る）
    #     てんかん   −20.57 vs てんか   −20.46  差 −0.11（**黙る**）
    # `かを` と `んを` の差であって、「てんかん と てんか の
    # どちらが尤もらしいか」は一度も比べていなかった。
    if rivals and not _swap_beats_rivals(got[0][0], rivals):
        return None
    return got[0]



def _gap_readings(text):
    """
    その隙間（漢字・カタカナ）の**読み**（項目48-PG・2026-09-03）。

    `化` → `か` のように、**かなが誤変換されただけ**かどうかを見る。
    出どころは既にある2つ——同梱の費用の表（表記→読み）と、
    漢字の読みの逆算（`kanji_guess`）。**新しい表は作らない。**
    """
    got = set()
    try:
        for r in (_table_readings_for_surface(text) or ()):
            got.add(r)
    except Exception:
        pass
    try:
        from kanji_guess import reading_combos_with_rank as _rc
        for r, _rank in _rc(text)[:6]:
            got.add(r)
    except Exception:
        pass
    return got


def _gap_does_grammar_work(text):
    """
    その隙間は**文法の仕事をしているか**（項目48-PG・2026-09-03）。

    `該当**あの**範囲` の `あの` は解析で **フィラー**（言い淀み）。
    文法の仕事をしていないので落としてよい。
    `右端**まで**到達` の `まで`（副助詞）・`異様**さの**判定` の
    `さの`（接尾＋連体化）は**仕事をしている**ので落とせない。
    見るのは**閉じた2つの品詞**（フィラー・感動詞）だけ。

    **解析が品詞を言えないときは False**（＝この門は意見を持たない・
    今までどおり）。janome の無い環境のモックは、どの語にも `'*'` しか
    返さないので、`あの` と `まで` を分けられない——そこで門を立てると
    **分けられないまま片側に倒す**ことになる（`該当あの範囲 →
    該当の範囲` を失う。実測）。**言えないなら黙る。**
    """
    if not text:
        return False
    try:
        from morphology import tokenize as _mtok
        toks = [t for t in _mtok(text) if getattr(t, 'surface', '')]
    except Exception:
        return False
    if not toks:
        return False
    kinds = [getattr(t, 'pos', '') or '' for t in toks]
    if any(k in ('', '*') for k in kinds):
        return False                     # 解析が言えない＝意見なし
    return not all(k in ('フィラー', '感動詞') for k in kinds)


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
        # **余った字が、隣の組の語とくっついて1語になるなら、
        # 元の書き方が正しい**（項目48-LN・2026-08-30。うにさんの
        # 誤検知報告 `事実上不可能である → 事実の不可能である`——
        # 組の語 [事実, 不可能] の間の 上 は `事実上` という1語の
        # 一部だった。該当の範囲・クリックかドラッグ は余りが
        # 1語を作らないので従来どおり）
        for w in solid:
            p = chunk.find(w)
            while p >= 0:
                if p + len(w) < len(chunk) \
                        and _sj.is_common_unit(chunk[p:p + len(w) + 1]):
                    return None
                if p > 0 and _sj.is_common_unit(chunk[p - 1:p + len(w)]):
                    return None
                p = chunk.find(w, p + 1)
        # **組の結果に、助詞でない1字のかなが残ってはいけない**
        # （項目48-PA・2026-09-03）。うにさんの育ちで
        # `協力技発動 → **協力わ発動**`——`協力`＋`発動` はどちらも
        # 1語として在るが、あいだの **`わ` が余っている**。
        # 組み立ては「読みを語で埋める」道なので、**埋まらずに
        # 残ってよいのは文法がかなで書く場所だけ**（格助詞と機能語）。
        _rest = surface
        _gaps = []
        for w in solid:
            _k = _rest.find(w)
            if _k < 0:
                _gaps = None
                break
            _gaps.append(_rest[:_k])
            _rest = _rest[_k + len(w):]
        if _gaps is not None:
            _gaps.append(_rest)
            for _g in _gaps:
                if not _g:
                    continue
                # **1字は格助詞だけ**（`pos_grammar._CASE_PARTICLES`）。
                # `PARTICLES_1CHAR` は終助詞（ね・よ・さ・わ）まで
                # 含むので、`協力**わ**発動` が通ってしまう
                if len(_g) == 1 and _g in 'はがをにでとものへやか':
                    continue
                if len(_g) >= 2 and _is_all_functional(_g):
                    continue
                if all('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ'
                       or c in 'ー々' for c in _g):
                    continue        # 漢字・カタカナの余りは別の門の持ち場
                return None
        # **もとの隙間が「文法の仕事をしている機能語」なら、
        #   そこは書き換えない**（項目48-PG・2026-09-03）。
        #
        # この枝は「**混入した字を落とすだけ**」の道（上の説明）。
        # ところが隙間の中身までは見ていなかったので、**正しい助詞を
        # 別の助詞に書き換える**ことができた（育ちで実測）:
        #
        #     右端**まで**到達  → 右端**で**到達
        #     異様**さの**判定  → 異様**の**判定
        #
        # どちらも誤打を1つも直していない。**文法が要求している字を
        # 削っただけ**。★★「自然な文には、補正を実行しない」。
        #
        # 落としてよいのは、**文法の仕事をしていない字**だけ——
        # 機能語ですらない混入（`該当**あ**範囲` の `あ`）と、
        # **言い淀み**（フィラー・感動詞。`該当**あの**範囲` の `あの`は
        # 解析でも フィラー）。的の `該当あの範囲 → 該当の範囲` は
        # こちらに入るので残る。**解析が品詞を言えないときは黙る**
        # （`_gap_does_grammar_work` の説明）。
        _rest2 = chunk
        _og = []
        for w in solid:
            _k = _rest2.find(w)
            if _k < 0:
                _og = None
                break
            _og.append(_rest2[:_k])
            _rest2 = _rest2[_k + len(w):]
        if _og is not None and _gaps is not None:
            _og.append(_rest2)
            for _a, _b in zip(_og, _gaps):
                if not _a or _a == _b:
                    continue
                # **漢字・カタカナの隙間は、読みが同じときだけ書き換える**
                # （項目48-PG）。育ちで実測——
                # `引用**後**解除してください` → `引用**と**解除…`
                # （組の語 引用・解除、あいだの `後` は接尾辞の1語。
                #  `後` の読みは ご・あと・のち で、`と` ではない）。
                # 的の `クリック**化**ドラッグ → クリック**か**ドラッグ` は
                # **`化` の読みがそのまま `か`**——かなが誤変換された
                # だけなので残る。結果の側の余りは 48-PA が同じ線を引く。
                if any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ' or c in 'ー々'
                       for c in _a):
                    if _b and _b in _gap_readings(_a):
                        continue
                    return None
                # **敬語の接頭辞（お・ご）は仕事をしている**（項目48-SO・
                # 2026-09-06。`医師にご相談 → 医師に相談` と落としていた）。
                # `_is_all_functional` の並びに ご を足す形は **readcheck で
                # 直りを失った**（`さきご`＝さき＋ご が説明できてしまう。
                # ご は名詞の頭にしか立たない）ので、ここで直に見る
                # 隙間 `にご` → `に` のように、**落ちた字が お・ご だけ**なら
                # それも同じ（元の隙間から新しい隙間を除いた残りで見る）
                if (_a in ('お', 'ご')
                        or (_b and _a.replace(_b, '', 1) in ('お', 'ご'))):
                    return None
                if not _is_all_functional(_a):
                    continue     # 機能語ですらない＝混入。落としてよい
                if _gap_does_grammar_work(_a):
                    return None
                continue         # 言い淀み・解析が言えない＝今までどおり
        return (f'組の語 {solid} はどれも1語として在り、'
                f'元の塊にそのまま入っている')
    except Exception:
        pass
    return None



def _ime_exact_respell(chunk, store, tokenize_fn, dict_index=None):
    """
    **打った読みが語彙の語にそのまま在り、いまの表記が語として無いなら、
    表記を組み直す**（設計30・項目48-IX・2026-08-23）。

    うにさんの指定「`待ち外` が異様と判定できればよい。これら単語にだけ
    効く局所的なものではなく、共通して補正される判定を」。

    `待ち外` は 待ち(名詞)＋外(接尾) と読めてしまい、漢字の並びの印
    （`oddness`）は立たない。だが**本人が打った読み**（設計25(甲) の対・
    `まちがい`）は語彙の `間違い` にそのまま一致し、`待ち外` という表記は
    同梱の表（778k）にも語彙にも辞書にも無い。**読みは正しく、IME の
    表記の選択だけが違う**——この形は文字列の並びからは見えず、対が
    あって初めて分かる（48-IC の設計30 の下見は対 54 件で 1 組だけ
    届いた。いまは 262 件）。

    要素の決まり（全部揃ったときだけ）:
      1. その塊そのものに IME の対がある（本人が一度に確定した範囲）
      2. いまの表記は**語として無い**（語彙の読みに無い・同梱の表の広い側
         にも無い・辞書索引にも無い・固有名詞でもない）。在るなら本人の
         選択（`官僚` は表に在るので触らない・48-HE）
      3. 打った読みは世の中の読み（索引）で、語彙に**漢字を含む表記**が在る
      4. 同じ読みに表記が並べば使用実績の多いほう

    実機メモ 1,295 行で当たるのは `待ち外`・`説明ぶん`・`時ッ層` だけ
    （数えた・2026-08-23。後の2つは別の道でも直っている）。

    戻り値: (表記, 分類) または None。
    """
    try:
        from kanji_guess import _IME_READINGS_PROVIDER as _prov
        import seed_japanese as _sj
    except Exception:
        return None
    if _prov is None or not chunk or not any(is_kanji(c) for c in chunk):
        return None
    try:
        readings = [r for r in (_prov(chunk) or ()) if r]
    except Exception:
        readings = []
    if not readings:
        return None
    # 2. いまの表記が語として在るなら、本人の選択
    try:
        if store.reading_of(chunk):
            return None
    except Exception:
        pass
    try:
        if _sj.is_unit(chunk):
            return None
    except Exception:
        pass
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(chunk):
                return None
        except Exception:
            pass
    try:
        if _is_whole_proper_noun(chunk, tokenize_fn):
            return None
    except Exception:
        pass
    best = None
    for rd in readings:
        if not all(is_hiragana(c) or c == 'ー' for c in rd):
            continue
        if dict_index is not None:
            try:
                if not dict_index.is_world_reading(rd):
                    continue
            except Exception:
                pass
        try:
            ents = [e for e in store.lookup(rd)
                    if e['surface'] != chunk
                    and any(is_kanji(c) for c in e['surface'])]
        except Exception:
            ents = []
        for e in ents:
            key = (-e.get('count', 0), e['surface'])
            if best is None or key < best[0]:
                best = (key, e, rd)
    if best is None:
        _trace('打った読み', f'{chunk!r} → 打った読み {readings} は語彙の'
                             f'漢字の語に届かない。触らない')
        return None
    _key, e, rd = best
    _trace('打った読み', f'{chunk!r} → 打った読み {rd!r} がそのまま語彙の '
                         f'{e["surface"]!r}（実績{e.get("count", 0)}）。'
                         f'{chunk!r} は語として無いので組み直す（設計30）')
    return e['surface'], e.get('category', 'その他')


def _resplit_by_elements(line, start, end, chunk, tokens, store, tokenize_fn,
                         dict_index=None, input_method=None):
    """
    **違和感の範囲を左端から要素で割り直す**（設計32・項目48-IW・2026-08-23）。

    うにさんの分析（`これからな学外しょつする` → `これから長く外出する`）:

        「左から読んで違和感があるのは `な学外しょつする`。`これからな` で
          区切るにはセリフだと考えると成立するが、句読点も無く不自然。
          故に `これから` でひとつ区切りがあると考え、`な学外しょつする`
          をどうするか考える。`学外` を がくがい と読むより先に、
          **頭の `な` と `学` が繋がるか**を人は考えるはず。ここから
          `ながい` が出せれば前の `これから` とも合うので腑に落ちる。
          残る `外しょつ` は がいしょつ。音訓分解も踏まえて
          がいしゅつ だろうと思えれば、あとは補正は難しくない」

    手順はその言葉のまま。**文字列でなく、構成する要素で判定する**
    （項目48-IT と同じ決まり）:

        1. 違和感   混合塊（漢字1〜2＋かな尾）が読めず、範囲の中に
                    読みの立たない語がある（`ょつする`）
        2. 左端     直前のかな（1〜3字）を頭として足す。**頭の前は語の
                    切れ目**（解析の語境に在る／前が既知語・機能語）
        3. 頭の語   頭のかな＋漢字の頭の読みが**語彙にそのまま在る**
                    （な＋がく＝ながく → 長く）。**ここは直さない（錨）**
        4. 尻尾の語 漢字の尻尾の読み＋かなの頭（がい＋しょつ）を
                    **隣のキー1つ**で語彙の読みへ（ょ→ゅ・がいしゅつ →
                    外出）。1文字目は動かさない（48-IT）・3字以上（48-HU）
        5. 尾       残りのかなは機能語で説明が付く（する）
        6. 受け入れ 全部の要素に説明が付いたときだけ。**直すのは1箇所**、
                    頭の語と尾は無傷の完全一致。janome があるときは
                    組んだ表記が語の並びとして読める（読みが全部立つ）
                    ことを拒否権にする

    既存の道が届かない理由（2026-08-23・実測）: `_resolve_reading_seq` は
    2分割＋末尾助詞1字で、訂正は2文字の部分にしか許さない（ここは
    長く｜外出｜する の3分割で、訂正は5文字の部分に入る）。
    `_resolve_reading_list` は塊全体を1語として探す。どちらも**塊に頭の
    かなを足さない**ので、`ながく` に届く読みが最初から無い。正しい塊と
    読みを直に渡しても両方 None。

    守り（要素で）:
      - 頭のかなが語の途中なら足さない（`大きな学外…` の `な` は
        `大きな` の一部。解析の語境に無い）
      - `学外` のように**漢字の並び自体が在る語**でも、範囲全体が読めず
        割り直しで全部に説明が付くときだけ動く。正しい `学外` は後ろが
        読めるので入口（1）に入らない
      - 尻尾の語の読みそのものが語彙に在るなら、それは別の正しい語。
        直さない（表記変換の禁止・項目48-IU の原則）
      - 直し先の読みは語彙に在り、辞書索引があれば世の中の読みでもある
      - 組んだ表記が元と同じなら採らない

    実機メモ 1,285行でこの形（漢字1〜2＋かな尾の混合塊が読めず、中に
    読みの立たない語がある）は**この1行だけ**（2026-08-23・数えた）。

    戻り値: (新しい開始位置, 表記, 分類) または None。
    """
    try:
        from kanji_guess import readings_for_char, looks_like_real_word
        from kana_layout import nearby_candidates
    except Exception:
        return None
    if not chunk or not is_kanji(chunk[0]):
        return None
    nk = 0
    while nk < len(chunk) and is_kanji(chunk[nk]):
        nk += 1
    # **漢字は1字か2字**。2字なら割るのは漢字と漢字の間（頭のかな＋
    # 漢字1字目＝頭の語／漢字2字目＋かなの頭＝尻尾の語）。1字なら
    # 頭の語は無く、**漢字＋かなの頭＝尻尾の語** と 尾 だけで説明する
    # （`外しょつする` → 外出する。うにさんの実機・2026-08-23）。
    # 3字以上は混合塊の切り出しに乗らない
    if nk not in (1, 2):
        return None
    tail = chunk[nk:]
    if len(tail) < 2 or not all(is_hiragana(c) for c in tail):
        return None
    # --- 1. 違和感: 塊が読めず、範囲の中に読みの立たない語がある ---
    if looks_like_real_word(chunk, store, tokenize_fn):
        return None
    # ★★ **同梱の表が「1語として在る」と言うなら触らない**
    # （項目48-UG'''・2026-09-07）。48-FC（造語）・48-UG（漢字塊）・
    # 48-UG'（混合塊）と**同じ門を4つ目の道にも**（学び22——片方だけに
    # 置くと、そちらを迂回して素通りする）。
    try:
        import seed_japanese as _sj_sp
        if _sj_sp.is_unit(chunk) is True:
            return None
    except Exception:
        pass
    # かな尾が**送り仮名＋機能語だけで説明が付く**なら違和感ではない
    # （`言って` の `って`。janome 無しの簡易分割はこれを未知語にする
    # ので、tests_mock の `MTGスタン率直に言って` が壊れた・2026-08-23）
    if _is_all_functional(tail) or _okurigana_functional_only(
            tail, any_head=True):
        return None
    inside = [t for t in tokens if t[3] < end and t[4] > start]
    if not inside or all(t[5] for t in inside):
        _trace('要素', f'{chunk!r} → 読みの立たない語が無い'
                       f'（違和感の印が無い）。割り直さない')
        return None
    try:
        from morphology import HAS_JANOME as _has_janome
    except Exception:
        _has_janome = False

    # --- 2. 左端: 直前のかなを頭として足す。頭の前は語の切れ目 ---
    hs = start
    while hs > 0 and is_hiragana(line[hs - 1]) and start - hs < 6:
        hs -= 1

    def _head_ok(h):
        if h == 0:
            return True
        p = start - h
        cov = [t for t in tokens if t[3] <= p < t[4]]
        if not cov:
            return True
        t = cov[0]
        if t[3] == p:
            return True                 # 解析の語境に在る
        pre = line[t[3]:p]
        # 解析が頭まで1語に繋いでいる（janome 無しのかな連続）なら、
        # 手前が**語彙に在る語か守る語**のときだけ（`大きな` の `き` を
        # 機能語の断片で通すと、`大きな学外…` でも頭を足してしまう）
        if pre and all(is_hiragana(c) for c in pre) and (
                is_protected_word(pre) or store.lookup(pre)):
            return True
        return False

    per = []
    for ch in chunk[:nk]:
        try:
            rs = [r for r in (readings_for_char(ch, dict_index) or ())
                  if r and all(is_hiragana(c) or c == 'ー' for c in r)]
        except Exception:
            rs = []
        if not rs:
            return None
        per.append(rs[:4])
    import itertools as _it
    cands = []
    # **頭のかなは必ず1字以上**。頭が無ければ `学外` を割る理由が無い——
    # 育ちの readcheck で `昨日ゅちうかい` が 咲く＋平地 に化けた
    # （2026-08-23・実測。正しい語 `昨日` を頭無しで割っていた）
    if nk == 2:
        shapes = [(h, 1) for h in range(1, min(3, start - hs) + 1)]
    else:
        shapes = [(0, 0)]               # 漢字1字: 頭の語なし
    for h, k in shapes:
        if not _head_ok(h):
            continue
        head = line[start - h:start]
        orig = line[start - h:end]
        for combo in _it.product(*per):
            # --- 3. 頭の語: 頭のかな＋漢字1字目の読み（漢字1字なら無し）---
            if True:
                a_read = head + ''.join(combo[:k])
                if k == 0:
                    a_surf, a_best = '', {'count': 10 ** 9}
                else:
                    if len(a_read) < 2:
                        continue        # 1字を根拠にしない（48-HU）
                    try:
                        a_entries = list(store.lookup(a_read))
                    except Exception:
                        a_entries = []
                    if not a_entries:
                        continue
                    a_best = max(a_entries,
                                 key=lambda e: e.get('count', 0))
                    a_surf = a_best['surface']
                    # 漢字の読みを含む頭の語を、かな・カタカナだけの
                    # 表記にするのは「読みに開くだけ」（がく → ガク）。
                    # 訂正ではない
                    if not any(is_kanji(c) for c in a_surf):
                        continue
                rest = ''.join(combo[k:])
                # --- 4/5. 尻尾の語＋尾 ---
                for c in range(1, len(tail) + 1):
                    b_read = rest + tail[:c]
                    f = tail[c:]
                    if f and not _is_all_functional(f):
                        continue
                    if len(b_read) < 3:
                        continue
                    try:
                        if store.lookup(b_read):
                            continue    # 在る読み＝別の正しい語。直さない
                    except Exception:
                        pass
                    for i in range(1, len(b_read)):
                        try:
                            near = nearby_candidates(b_read[i])
                        except Exception:
                            near = ()
                        for alt, d in near:
                            if alt == b_read[i] or d > 1.0:
                                continue
                            if not adjacent_slip(b_read[i], alt,
                                                 input_method or 'kana'):
                                continue
                            b_fixed = b_read[:i] + alt + b_read[i + 1:]
                            try:
                                b_entries = list(store.lookup(b_fixed))
                            except Exception:
                                b_entries = []
                            if not b_entries:
                                continue
                            if dict_index is not None:
                                try:
                                    if not dict_index.is_world_reading(
                                            b_fixed):
                                        continue
                                except Exception:
                                    pass
                            b_best = max(b_entries,
                                         key=lambda e: e.get('count', 0))
                            # 尻尾の語も漢字の読みを含むので、同じ理由で
                            # 漢字の無い表記は採らない
                            if not any(is_kanji(c)
                                       for c in b_best['surface']):
                                continue
                            new_text = a_surf + b_best['surface'] + f
                            if new_text == orig:
                                continue
                            cands.append((
                                d, -min(a_best.get('count', 0),
                                        b_best.get('count', 0)),
                                new_text, h, b_best.get('category', 'その他'),
                                a_read, b_read, b_fixed))
    if not cands:
        _trace('要素', f'{chunk!r} → 頭のかなを足しても、全部の要素に'
                       f'説明が付く割り方が無い')
        return None
    # 拮抗は決める（48-IS の順: 費用 → 使用実績 → 並び）。ただし
    # **頭を多く説明する割り方を先に**——人は頭の `な` と `学` が
    # 繋がるかを先に考える（うにさん）。頭を足さない割り方は、`な` を
    # 説明しないまま残す
    cands.sort(key=lambda x: (x[0], -x[3], x[1], x[2]))
    for d, _negc, new_text, h, cat, a_read, b_read, b_fixed in cands:
        # --- 6. 受け入れ: janome があれば、組んだ並びが読めること ---
        if _has_janome:
            try:
                nt = tokenize_fn(new_text)
            except Exception:
                nt = []
            if not nt or not all(t[5] for t in nt):
                _trace('要素', f'{chunk!r} → {new_text!r} は語の並びとして'
                               f'読めない。採らない')
                continue
        _trace('要素', f'{line[start - h:end]!r} → {new_text!r}'
                       f'（頭の語 {a_read!r} は無傷・尻尾の語 {b_read!r} → '
                       f'{b_fixed!r} 隣のキー1つ・尾は機能語・設計32）'
               if a_read else
               f'{line[start - h:end]!r} → {new_text!r}'
               f'（漢字1字: 尻尾の語 {b_read!r} → {b_fixed!r} 隣のキー1つ・'
               f'尾は機能語・設計32）')
        return (start - h, new_text, cat)
    return None


def _abab_enabled():
    """
    ABAB（2文字2回）の道を使うか（項目48-KM・2026-08-28）。

    **既定は使う**（測って採った——初期 直り+5/化け±0・育ち +2/±0・
    fpcheck 0・実機メモ差0。suite の記録は abab3、最後の を の門は
    件を特定して個別に検証）。`CN_ABAB=0` で切れる（測るため）。
    """
    import os as _os
    return _os.environ.get('CN_ABAB') != '0'


# ABAB の対象にする字（**素のかなだけ**）。小書き・っ・ー が絡む形は
# 拗音の語（しゃしん 等）と隣り合わせで危ないので、まず狭く始める
# （48-JJ「1対ずつ検品してから」と同じ構え）。
# **を も外す**——を はほぼ助詞専用で、繰り返し語の中には出ない。
# 末尾の助詞が本体に入り込むと `すとすを`（すとれす の脱字＋を）が
# `すをすを` に吸われた（育ちの readcheck で実測・2026-08-28）。
_ABAB_PLAIN = frozenset(
    chr(c) for c in range(ord('あ'), ord('ん') + 1)
) - frozenset('ぁぃぅぇぉゃゅょっゎを')


def _abab_repair(run, store):
    """
    **2文字2回の繰り返し（ABAB型）へ1手で戻る崩れ**（2026-08-28・
    うにさんの指定）:

    > 「日本語の繰り返しの特徴は、『そもそも』『わくわく』『ぴかぴか』
    >   『なになに』『どれどれ』のような2文字2回繰り返し傾向で、
    >   『そももそ』『そもそみ』などは補正の材料になります」

    語彙に頼る道（設計22・48-HJ）が先に走るので、ここへ来るのは
    **語彙で説明の付かなかった連続**。ABAB という**形そのもの**を
    証拠にする——擬音・擬態語は無数にあって語彙に載り切らないが、
    2文字2回の型は共通している。

    見るもの: 4文字のかな連続（末尾の助詞1文字は剥がしてよい）。
    直せる形（どちらも1手）:
      - 隣どうしの**入れ替え**1回で ABAB になる（そももそ → そもそも）
      - 1文字を**隣のキー**に替えると ABAB になる（そもそみ → そもそも）
    門:
      - 4字とも**素のかな**（小書き・っ・ー は対象外。しゃしん 型を
        巻き込まないため）・A ≠ B
      - 連続そのもの（と、助詞を剥いだ本体）が在る語なら触らない
        （かたかな を かたかた にしない）
      - **ABAB の答えがただ1つ**のときだけ
      - 同じ1手（入れ替え・隣のキー・濁点の付け外し）で**別の在る語**
        にも届くなら決め手なしで触らない（設計22・48-HJ と同じ拮抗）
    戻り値: (直した連続, ABAB形) または None。
    """
    if not _abab_enabled():
        return None
    from vocabulary import store_is_young as _sy
    _mc = 1 if _sy(store) else 2

    def _known(t):
        try:
            return bool([e for e in store.lookup(t) if e['count'] >= _mc])
        except Exception:
            return False

    # 末尾の助詞1文字は剥がしてよい（剥いだ本体が4字のときだけ）
    tail = ''
    body = run
    if len(run) == 5 and run[-1] in PARTICLES_1CHAR:
        body, tail = run[:-1], run[-1]
    if len(body) != 4:
        # **長い連続の中の4字窓は掛けない**（2026-08-28 に測って外した）。
        # 活用の連なりは偶然 ABAB に1手で届く形だらけで
        # （`しまいま`→しましま・`にしまし`→にしにし・`のもので`…）、
        # 実機メモの正しい文を7行壊した。窓走査（_abab_repair_window）は
        # 判定の材料が立つまで使わない。孤立した4字（＋助詞1字）だけ。
        return None
    if _known(run):
        return None
    got = _abab_fix_body(body, _known)
    if got is None:
        return None
    abab, how = got
    # 剥がした助詞と繋いだ境目に、元に無かった同じ字の2連を**作らない**
    # （_has_new_repetition と同じ考え。`ぴかぴあか` を
    # `ぴかぴか＋か`＝かか にしない・実測 2026-08-28）
    if tail and abab[-1] == tail:
        return None
    _trace('かな連続', f'{run!r} → {abab + tail!r} に直す'
                     f'（2文字2回の型・{how}・ABAB {abab!r}・'
                     f'2026-08-28）')
    return (abab + tail, abab)


def _abab_fix_body(body, _known):
    """
    **4字の本体が ABAB に1手で戻るなら** `(ABAB形, 手)` を返す
    （門と決め方は `_abab_repair` の説明のとおり。窓走査と共用）。
    """
    if len(body) != 4 or any(c not in _ABAB_PLAIN for c in body):
        return None
    if body[:2] == body[2:]:
        return None                 # もう ABAB（正しい形。触らない）
    if _known(body):
        return None                 # 在る語（かたかな）は触らない
    # **かなの語と機能語で説明が付く並びは触らない**（48-IT の門を
    # ここにも・学び22）。`しました`（し＋ました）は語彙に載らない
    # 活用形なので上の known では守れず、隣接キー1つで在る語
    # `しましま`（縞々）に吸われて**正しい文の枠を116回壊した**
    # （fpcheck 7.73%・実測 2026-08-28）。文法として説明の付く並びに
    # 型の証拠は使わない。
    if _kana_run_explained(body):
        return None
    try:
        from kana_layout import nearby_candidates as _near
    except Exception:
        return None

    got = {}                        # ABAB形 → 手の説明
    # 隣どうしの入れ替え1回
    for i in range(3):
        if body[i] == body[i + 1]:
            continue
        v = body[:i] + body[i + 1] + body[i] + body[i + 2:]
        if v[:2] == v[2:] and v[0] != v[1]:
            got.setdefault(v, '入れ替え')
    # 1文字を隣のキーに（打った字の隣に、型に合う字があるとき）
    for j in range(4):
        want = body[(j + 2) % 4]    # ABAB なら2つ隣と同じ字のはず
        if want == body[j]:
            continue
        try:
            near = {a for a, d in _near(body[j], max_dist=1.0)
                    if a != body[j]}
        except Exception:
            near = set()
        if want in near:
            v = body[:j] + want + body[j + 1:]
            if v[:2] == v[2:] and v[0] != v[1]:
                got.setdefault(v, '隣のキー')
    if not got:
        return None
    # **2つ並ぶのは構造のせい**（実測・2026-08-28）: ABBA は両側への
    # 入れ替えで ABAB にも BABA にもなり、ABAC はどちらの B を直しても
    # 型になる（そももそ → そもそも／もそもそ、そもそみ → そもそも／
    # そみそみ）。決め方は2段:
    #   1. **在る語がただ1つなら、それ**（語彙の証拠が一番強い）
    #   2. **1つ目の単位（最初の2文字）を型とする**——繰り返しは
    #      1つ目の単位を打ってから写すので、崩れは2つ目に出やすい。
    #      うにさんの指定 48-CV「さいしょのもじは正しい確率がかなり
    #      高い」を、字から**単位**に広げた形（そももそ・そもそみ・
    #      わくわう・ぴかぴき の4例が全部この段で そもそも・わくわく・
    #      ぴかぴか に決まる）
    if len(got) == 1:
        abab, how = next(iter(got.items()))
    else:
        known_forms = sorted(v for v in got if _known(v))
        first_unit = body[:2] + body[:2]
        if len(known_forms) == 1:
            abab = known_forms[0]
        elif not known_forms and first_unit in got:
            abab = first_unit
        else:
            return None             # 決め手なし
        how = got[abab]
    # **同じ1手で別の在る語にも届くなら触らない**（拮抗）。
    others = set()
    for i in range(3):
        if body[i] != body[i + 1]:
            others.add(body[:i] + body[i + 1] + body[i] + body[i + 2:])
    for j in range(4):
        try:
            for a, d in _near(body[j], max_dist=1.0):
                if a != body[j]:
                    others.add(body[:j] + a + body[j + 1:])
        except Exception:
            pass
    for j, ch in enumerate(body):
        alt = _TYPO_DAKUTEN.get(ch)
        if alt:
            others.add(body[:j] + alt + body[j + 1:])
    for v in others:
        if v != abab and _known(v):
            return None
    return (abab, how)


def _abab_repair_window(run, store, _known):
    """
    **長い連続の中の4字窓**に 2文字2回の型を掛ける（2026-08-28）。

    `わくわうしながら` の頭4字のように、型の崩れが語連続の一部の
    こともある。窓ごとに `_abab_fix_body` を掛け、**直せる窓が
    ただ1つ**のときだけ直す。窓の両隣と繋いだ境目に、元に無かった
    同じ字の2連を作らない（_has_new_repetition と同じ考え）。
    """
    if len(run) < 6:
        return None
    n = len(run)

    def _overlaps_known(k):
        # 窓 [k, k+4) に**かかっている在る語**（3字以上）があるなら、
        # その窓は正しい語の一部かもしれない——触らない
        # （`わたしたちが` の窓 `たしたち` を `たしたし` にした・
        # 実測 2026-08-28。窓だけ見ると `わたしたち` が見えない）。
        for s in range(max(0, k - 7), min(k + 4, n)):
            for e in range(max(s + 3, k + 1), min(s + 8, n) + 1):
                if e <= k or s >= k + 4:
                    continue
                if _known(run[s:e]):
                    return True
        return False

    hits = []
    for k in range(len(run) - 3):
        got = _abab_fix_body(run[k:k + 4], _known)
        if got is None:
            continue
        if _overlaps_known(k):
            continue
        abab, how = got
        left = run[k - 1] if k > 0 else ''
        right = run[k + 4] if k + 4 < len(run) else ''
        if (left and abab[0] == left) or (right and abab[-1] == right):
            continue
        hits.append((k, abab, how))
        if len(hits) > 1:
            return None             # 2つ以上＝決め手なし
    if len(hits) != 1:
        return None
    k, abab, how = hits[0]
    fixed = run[:k] + abab + run[k + 4:]
    _trace('かな連続', f'{run!r} → {fixed!r} に直す'
                     f'（2文字2回の型・{how}・窓 {run[k:k + 4]!r} → '
                     f'{abab!r}・2026-08-28）')
    return (fixed, abab)


def _pt_extend_over_dead_katakana(line, start, end, tokens):
    """
    項目48-PT: 隣接するカタカナが**読みの立たない断片**なら、その
    連なりぶんだけ塊を広げて返す（解析課背中|セク → 解析課背中セク）。
    読みが立つカタカナ語（本物の語）に接しているなら None
    ——48-HU の守り本来の形（文字乳|リュク のような「語を奪う」防止は
    読める語に接しているときの話）。
    """
    s, e = start, end
    changed = False
    while e < len(line) and ('ァ' <= line[e] <= 'ヶ' or line[e] == 'ー'):
        t = next((t0 for t0 in tokens if t0[3] == e), None)
        if t is None:
            return None
        sf = t[0] or ''
        if not sf or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in sf):
            return None
        if len(t) > 5 and t[5]:
            return None          # 読みが立つ＝本物の語。守る（48-HU）
        e = int(t[4])
        changed = True
    while s > 0 and ('ァ' <= line[s - 1] <= 'ヶ' or line[s - 1] == 'ー'):
        t = next((t0 for t0 in tokens if t0[4] == s), None)
        if t is None:
            return None
        sf = t[0] or ''
        if not sf or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in sf):
            return None
        if len(t) > 5 and t[5]:
            return None
        s = int(t[3])
        changed = True
    return (s, e) if changed else None


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


def _single_kanji_diff(chunk, surf):
    """
    chunk → surf の**表の差が、元側の漢字1字だけ**か（項目48-JG）。

    共通の頭と尻を落として、残った元側が漢字1字なら True。
    読みを編集した直し（誤打の型・隣接キー）でここが True のとき、
    根拠はその1字の読み替えしかない＝証拠が細すぎる（48-HU 門(3)）。
    `空白行 → 空白くい／空白以降`（行 いく→くい・いこう）と
    `高橋佑 → 高橋よう／高橋優雅`（佑 ゆう→よう・ゆうが）の型。
    読みを編集していない直し（背景食 → 背景色・クリック化 →
    クリックか＝同じ読みの表記選び）は呼び出し側の条件で通る。
    """
    if not chunk or not surf:
        return False
    i = 0
    n = min(len(chunk), len(surf))
    while i < n and chunk[i] == surf[i]:
        i += 1
    j = 0
    while j < n - i and chunk[len(chunk) - 1 - j] == surf[len(surf) - 1 - j]:
        j += 1
    ca = chunk[i:len(chunk) - j]
    return len(ca) == 1 and is_kanji(ca)


#: **開いた読みに手を当てるときの、隣接キーの幅**（項目48-OA）。
#:
#: **1.4 に広げて、戻した**（2026-09-01・同じ日に）。うにさんの一覧
#: `たぶいごうして ⇒ たぶいどうして` の `ご→ど` は費用1.4で、
#: 1.0 の門にちょうど落ちている。広げたら readcheck・fpcheck・
#: seedcheck・紫は**全部差0**だったが、**実機メモの中身を読んだら
#: 1行壊していた**:
#:
#:     引き月資料 → 引き継ぎ資料（正）  →  **引き抜き資料**（誤）
#:
#: `ひきつきしりょう` は **濁点1つ**（つき→つぎ）で `引き継ぎ` に
#: 届くのに、幅を広げると **つ→ぬ**（1.4）で `引き抜き` が入り、
#: 実績で勝ってしまう。**候補は費用で順を付けていない**のが元。
#:
#: **件数だけ見て「差0」と言ったのが誤り**——変わった行は 255 で
#: 同じだったが、**中身が入れ替わっていた**（48-NL と同じ型を
#: もう一度踏んだ）。**dump を突き合わせること。**
#:
#: **やった**（項目48-OQ(e)・2026-09-03）: `_fixes` の候補に
#: **費用を持たせ、安い順に並べた**。濁点(0.3)が隣接キー(1.4)より
#: 先に採られるので、**幅を 1.4 に広げても `引き継ぎ` は守れる**。
#: 広げると うにさんの一覧4行目 `たぶいごうして ⇒ たぶいどうして`
#: （`ご→ど`＝費用1.4）が届き、48-OQ(a)(b) と合わせて
#: **田部井号して → タブ移動して** になる。
_CHUNK_NEAR_MAX = 1.4


#: **「する」にならない名詞の細分類**（項目48-OQ(d)・2026-09-03）。
#: 副詞可能（以降・以前・当時・今日）・非自立・数・代名詞・接尾は
#: **文法として「〜する」の形を作らない**。サ変接続・形容動詞語幹は作る。
_NO_SURU_SUB = ('副詞可能', '非自立', '数', '代名詞', '接尾')


def _suru_attach_ok(surface, tokenize_fn):
    """
    組んだ表記の中で、**「〜する／〜し」が付けない名詞に付いていないか**
    （項目48-OQ(d)・2026-09-03）。

    `タブ以降して` は、読みの上では たぶ＋いこう＋して で敷き詰まるが、
    **`以降` は副詞可能名詞で「以降する」という形を作らない**。
    文法として決まっていることなので、組み上がりで断る
    （★★「論理的に正しいもの」——標本の当たりの数では決めない）。

    `移動`（サ変接続）・`成功`（サ変接続）・`安定`（形容動詞語幹）は通る。
    `切り替え`（名詞:一般）も通す——「〜する」を作れるかは細分類では
    決まらないので、**作れないと決まっている側だけ**を断る。

    解析できなければ True（意見なし）。
    """
    if not surface or tokenize_fn is None:
        return True
    try:
        toks = [t for t in tokenize_fn(surface) if t[0]]
    except Exception:
        return True
    for i in range(len(toks) - 1):
        ap = toks[i][1] or ''
        b_sf = toks[i + 1][0] or ''
        bp = toks[i + 1][1] or ''
        if not (bp.startswith('動詞') and b_sf in _SURU_FORMS_LOCAL):
            continue
        if not ap.startswith('名詞'):
            continue
        # (1) **「する」の形を作らないと決まっている名詞**
        if any(x in ap for x in _NO_SURU_SUB):
            return False
        # (2) **名詞＋名詞＋する の複合は、後ろがサ変接続のときだけ**
        #     （項目48-OQ(d)）。`タブ移動して`（移動＝サ変接続）は
        #     「目的語＋動作名詞」の複合で自然だが、`タブ違法して`
        #     （違法＝形容動詞語幹）は複合にならない。
        #     **単独の `安定して` は見ない**——前に名詞が無いので
        #     この枝に入らない（安定する は正しい日本語）
        if i > 0 and (toks[i - 1][1] or '').startswith('名詞') \
                and 'サ変' not in ap:
            return False
    return True


#: 「する」の活用形（`oddness._SURU_FORMS` と同じ中身・借りる）。
try:                                    # pragma: no cover - 表は1つ
    from oddness import _SURU_FORMS as _SURU_FORMS_LOCAL
except Exception:                       # pragma: no cover
    _SURU_FORMS_LOCAL = frozenset(('し', 'する', 'すれ', 'しろ', 'せよ',
                                   'さ', 'せ'))


def _dakuten_rival_reading(reading, store, dict_index):
    """
    **その読みに、濁点1つ違いの「よくある語」が別に在るか**
    （項目48-OO の受け皿・2026-09-03）。

    48-OO（索引の顔で かな連続を変換する）を既定 ON にしたとき、
    readcheck で出た化けは**4件とも同じ形**だった:

        正解 かんとう ← 打った かんどう  → **感動**（読みが違う化け）
        正解 せいけん ← 打った せいげん  → **制限**
        正解 せんけつ ← 打った せんげつ  → **先月**
        正解 かいがん ← 打った かいかん  → **会館**

    **打ち間違いの読みが、たまたま別の日常語**になっている。
    濁点1つで別の日常語に変わるなら、**どちらを打ったのかは
    その場では決められない**——①（異様）が立っていない場所の
    決まり「**ただ1つのときだけ採る**」（設計38〜40）に照らして、
    ここは決めない。

    **①が立っている道には掛けない**（★★「異様だと判定したら、
    何かしらに決める」）。掛けるのは 48-MI（異様と判定していない
    かな連続の変換）だけ。

    戻り値: 濁点1つ違いの段1の語が在れば True。
    """
    if not reading or dict_index is None:
        return False
    for i, ch in enumerate(reading):
        alt = _TYPO_DAKUTEN.get(ch)
        if not alt:
            continue
        v = reading[:i] + alt + reading[i + 1:]
        try:
            if any((e.get('count', 0) or 0) >= 2 for e in store.lookup(v)):
                return True
            if _has_tier1_word(v, dict_index):
                return True
        except Exception:
            continue
    return False


def _has_tier1_word(reading, dict_index):
    """
    その読みに、**段1（AI がよく使うと判じた2字漢語）の表記が在るか**。
    `_index_face` は「段1が**ただ1つ**」を要るが、こちらは
    **1つでも在れば True**——「相手がいる」ことだけを見る場所で使う。
    """
    if not reading or dict_index is None or len(reading) < 2:
        return False
    try:
        import kango_tier as _kt
        if not _kt.available():
            return False
        for s in (dict_index.surfaces_for_reading(reading) or ()):
            if s and len(s) == 2 and all(is_kanji(c) for c in s) \
                    and _kt.tier(s) == 1:
                return True
    except Exception:
        return False
    return False


def _reading_gap(reading, base):
    """
    **読みと読みの隔たり**（項目48-OQ(d)・2026-09-03）。
    ふつうの編集距離（置換・挿入・削除は1）。`base` が空なら 0。
    """
    if not base or reading == base:
        return 0
    prev = list(range(len(base) + 1))
    for i, ch in enumerate(reading, 1):
        cur = [i]
        for j, ch2 in enumerate(base, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ch != ch2)))
        prev = cur
    return prev[-1]


def _katakana_runs(text):
    """文字列の中の、カタカナ（と `ー`）の連なりを全部返す。"""
    out, i, n = [], 0, len(text)
    while i < n:
        if is_katakana(text[i]) or text[i] == 'ー':
            j = i
            while j < n and (is_katakana(text[j]) or text[j] == 'ー'):
                j += 1
            out.append(text[i:j])
            i = j
        else:
            i += 1
    return out


def _grown_katakana_is_own_word(surface, chunk, store):
    """
    **元に無かったカタカナが、本人が使っている語か**（項目48-OQ(c)・
    2026-09-03）。

    48-ND(a)「元に無かったカタカナを生やさない」の**例外**。
    あの門が止めたいのは `メモうち帳` のような**辞書だけの**カタカナ
    ——「読みは合うが、その人はそう書かない」形。**本人が実績2以上で
    使っている語**（タブ・コピー・ファイル）は、その理屈に当たらない
    ——「打った人が選んで書く」側の語だからこそ語彙に積まれている。

    `surface` の中の**カタカナの連なり**を全部見て、

        ・元の塊（`chunk`）にも在る          → 生やしていない
        ・本人の語彙に**実績2以上**で在る    → 生やしてよい

    のどちらかを**全部が満たす**ときだけ True。1つでも外れたら False
    （＝門はそのまま効く）。
    """
    runs = _katakana_runs(surface)
    if not runs:
        return False
    for w in runs:
        if w in chunk:
            continue
        try:
            rd = store.reading_of(w)
            ents = store.lookup(rd) if rd else []
        except Exception:
            ents = []
        if not any(e.get('surface') == w and (e.get('count', 0) or 0) >= 2
                   for e in ents):
            return False
    return True


def _po_replace_odd_span(chunk, odd_pairs, ar, fixes, tokenize_fn,
                         store, dict_index):
    """
    **手を当てた読みが文法で説明が付くなら、異様の範囲だけを
    その読みで置き換える**（項目48-PO・2026-09-04・5巡目の指示書・
    うにさんの画面12行目）。

        も水戸に戻ります → **もとに戻ります**
          ① 行頭の係助詞に地名が直付き（48-KX・対は も＋水戸）
          ② 開いた読み もみとにもどります
          ③ 余分な隣のキーの手（み＝も(M) の隣(N)）で もとにもどります
          ④ **語＋助詞＋語は表記に組めず**、設計27は「表記が一つも
             組めない。決めない」で降りていた

    直しの表記が組めなくても、**手を当てた読みが 48-IS（かなの語と
    機能語）で説明が付く**なら、それが本来の入力。**異様の対の範囲
    だけ**をその読みで置き換えて出す（残りは書いてあるまま）。
    表記は**かなのまま**——`もと` は 元/本/基/素 で顔が決まらない
    （段1の顔がただ1つなら漢字、は次の材料）。育ちでは本人が
    `もと` をかなで書いている（48-ND「書かれ方は変えない」の側）。

    門（狭く開ける）:
      ・異様の対が**1組だけ**／解析が全トークンの読みを言い切っている
        ／その連結が ar と一致（48-DE・当て推量の読みに手を重ねない）
      ・手は**設計27と同じ `_fixes`**（費用の安い順）。**編集が対の
        読みの範囲に収まっている**こと（前後の読みは1字も動かない）
      ・置き換えた読みが**2字以上**／直した塊で**異様さが消える**こと
    """
    if not odd_pairs or len(odd_pairs) != 1 or not ar:
        return None
    a_sf, b_sf = odd_pairs[0]
    try:
        toks = list(tokenize_fn(chunk))
    except Exception:
        return None
    if not toks or any(len(t) <= 5 or not t[5] or not t[2] for t in toks):
        return None
    if ''.join(t[0] or '' for t in toks) != chunk:
        return None

    def _hira(rd):
        return ''.join(chr(ord(c) - 0x60)
                       if 'ァ' <= c <= 'ヶ' and c != 'ー' else c
                       for c in rd)
    rds = [_hira(t[2]) for t in toks]
    if ''.join(rds) != ar:
        return None
    k = None
    for i in range(len(toks) - 1):
        if (toks[i][0] or '') == a_sf and (toks[i + 1][0] or '') == b_sf:
            k = i
            break
    if k is None:
        return None
    pre_rd = ''.join(rds[:k])
    odd_rd = rds[k] + rds[k + 1]
    post_rd = ''.join(rds[k + 2:])
    if len(odd_rd) < 2:
        return None
    # **対の外に、書いてあるまま保たれる残りがあること**（測って
    # 足した門・2026-09-04）。対が塊全体を覆う形まで開くと、この
    # 受け皿は「かなの連なりを、手1つで表の語に置き換える」に
    # 退化する——readcheck で `ふだく → いだく`（抱く）・
    # `せわい → よわい`（弱い）の**化けを4面で+1〜+2作った**（実測）。
    # 残りが在る形（も水戸＋に戻ります）だけが、この受け皿の持ち場。
    if not pre_rd and not post_rd:
        return None
    # **対に漢字を含むこと**——「表記が組めない」のは漢字混じりの
    # 悩みで、かなだけの連なりには既存の道（A道・芯）が持ち場を
    # 持っている（同上の測定で足した門）。
    if not any(is_kanji(c) for c in (a_sf + b_sf)):
        return None
    try:
        s0, e1 = int(toks[k][3]), int(toks[k + 1][4])
    except Exception:
        return None
    try:
        import oddness as _odd_po
    except Exception:
        return None
    for _v in (fixes(ar) or ()):
        if not (_v.startswith(pre_rd)
                and (_v.endswith(post_rd) if post_rd else True)):
            continue
        fixed_odd = _v[len(pre_rd):len(_v) - len(post_rd)] \
            if post_rd else _v[len(pre_rd):]
        if not fixed_odd or fixed_odd == odd_rd or len(fixed_odd) < 2:
            continue
        # **置き換えた範囲そのものが「知っている語」であること**
        # （本人の語彙 count>=2 か、世の中の読み）。48-IS だけだと
        # 費用の安い置換の手が先に通る——`もみと` は `くみと`
        # （くみ＋と＝語＋助詞の当て推量）が `もと`（余分な隣のキー
        # み を落とす・語彙45回）より安く、**くみとに戻ります** を
        # 作った（実測・受け止めた門）。`もと` は語で `くみと` は
        # 語でない——ここで割れる。
        # 出どころは**本人の語彙（count>=2）**と**同梱の費用の表**
        # （かな表記そのものを持っている・48-KN の教訓のとおり
        # `is_world_reading` は `くみと` まで True で使えない——実測）
        _known_odd = False
        try:
            _known_odd = bool([e for e in store.lookup(fixed_odd)
                               if e['count'] >= 2])
        except Exception:
            pass
        if not _known_odd:
            _known_odd = _table_cost(fixed_odd) is not None
        if not _known_odd:
            continue
        if not _kana_run_explained(_v):
            continue
        new_chunk = chunk[:s0] + fixed_odd + chunk[e1:]
        try:
            if _odd_po.is_odd_run(new_chunk, tokenize_fn,
                                  store=store, dict_index=dict_index):
                continue
        except Exception:
            continue
        return new_chunk
    return None


def _new_katakana_known(text, chunk, dict_index=None):
    """
    **元に無いカタカナの連続は、世の中の語か**（項目48-SU・2026-09-06）。
    text の中のカタカナ2字以上の連続のうち、元の塊 chunk にそのまま
    無いものは `oddness._katakana_word_known`（AI の表・外来語の表・
    費用の表・索引の読み）で語であること。1つでも語でなければ False。
    """
    if not text:
        return True
    try:
        import oddness as _odd
    except Exception:
        return True
    i, n = 0, len(text)
    while i < n:
        if not (is_katakana(text[i]) or text[i] == 'ー'):
            i += 1
            continue
        j = i
        while j < n and (is_katakana(text[j]) or text[j] == 'ー'):
            j += 1
        k = text[i:j]
        i = j
        if len(k) < 2 or k in chunk:
            continue
        if _katakana_known_or_compound(k, dict_index):
            continue
        return False
    return True


def _katakana_known_or_compound(k, dict_index=None):
    """カタカナ語が世の語か、**世の語2つの複合**か（ダブル＋クリック・48-SU）。

    ★★ ここは**生やす側**なので `spelling=True` で聞く（項目48-TY）——
    費用表は読みごとにカタカナ綴りを**作って**持っているので、
    「その綴りが在る」の証拠にならない（48-RO）。
    実機の `使用シュワー → 使用シヤワー` は、`シヤワー` を語だと
    言ったのが**費用表だけ**だった。
    """
    try:
        import oddness as _odd
    except Exception:
        return True
    try:
        if _odd._katakana_word_known(k, dict_index, spelling=True):
            return True
        for i in range(2, len(k) - 1):
            if (_odd._katakana_word_known(k[:i], dict_index, spelling=True)
                    and _odd._katakana_word_known(k[i:], dict_index,
                                                  spelling=True)):
                return True
    except Exception:
        return True
    return False


def _trailing_predicate(chunk, tokenize_fn):
    """
    **塊の末尾に在る「活用した用言」**（項目48-UT・2026-09-07）。

    末尾の側から見て、**漢字を含む 動詞:自立／形容詞:自立** が
    見つかったら、そこから塊の終わりまでを返す。無ければ `''`。

        じょうを見ました  →  **`見ました`**（見＝動詞:自立・漢字を含む）
        簡易流力          →  `''`（流・力 は 名詞:接尾）
        目もち長          →  `''`（長 は 名詞:接尾）

    使いみち: 塊の組み直し（48-LA）が**ここまで書き換えないように**
    する。述語は文法として完成した1つの単位で、その手前の誤字が
    そこまで伸びることはない。実際 `じょうを見ました` が
    **`異常をみました`** になっていた——`じょう → 異常` は当たって
    いるのに、**正しく書けていた `見` をかなに開き戻していた**。

    ★★ **本当に末尾でなければ空**（検品で指摘・2026-09-07）。
    用言のうしろに**内容語**が続いていたら、それは「末尾の述語」ではない
    ——`作った資料`・`考えた内容` まで丸ごと守ってしまい、**48-LA の道が
    その塊まるごと死ぬ**（直せるものが黙って直らなくなる）。
    用言のうしろに来てよいのは**助動詞・助詞・活用語尾・非自立**だけ。

    解析できなければ `''`（意見なし＝今までどおり）。
    """
    try:
        toks = list(tokenize_fn(chunk) or ())
    except Exception:
        return ''
    _tail_ok = ('助動詞', '助詞', '動詞:非自立', '動詞:接尾',
                '名詞:接尾:助動詞語幹', '記号')
    for k in range(len(toks) - 1, -1, -1):
        t = toks[k]
        pos = t[1] or ''
        if not (pos.startswith('動詞:自立')
                or pos.startswith('形容詞:自立')):
            continue
        if not any(is_kanji(c) for c in (t[0] or '')):
            continue
        # うしろは機能語だけか（内容語が続くなら末尾の述語ではない）
        if not all(any((toks[m][1] or '').startswith(x) for x in _tail_ok)
                   for m in range(k + 1, len(toks))):
            return ''
        try:
            return chunk[t[3]:]
        except Exception:
            return ''
    return ''


def _sm_content_count(text, tokenize_fn):
    """
    **内容語のトークンの数**（項目48-SM・2026-09-06）。接頭・接尾・
    非自立・助詞・助動詞・記号・数を除いて数える。`効率化`（効率＋化）・
    `最大化`・`終了時` は 1、`今日探索`・`驚嘆潜水`・`創建無茶` は 2、
    `引き月資料`（引き｜月｜資料）は 3。解析できなければ 99（＝多い側）。
    """
    try:
        toks = list(tokenize_fn(text) or ())
    except Exception:
        return 99
    n = 0
    for t in toks:
        pos = t[1] or ''
        if any(x in pos for x in ('接頭', '接尾', '非自立', '助詞',
                                  '助動詞', '記号', '数')):
            continue
        n += 1
    return n


def _sm_single_unit(text, tokenize_fn):
    """**1つの語（＋接辞）か**（項目48-SM）。`_sm_content_count` が 1 まで。"""
    return _sm_content_count(text, tokenize_fn) <= 1


def _reopen_odd_chunk(chunk, store, tokenize_fn, dict_index=None,
                      input_method=None, assemble=False, vocab_only=False,
                      as_kana_run=False):
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
    # **できあがっている塊には走らせない**（項目48-KI の入口・学び22）
    if _chunk_is_intact(chunk, tokenize_fn):
        _trace('異様', f'{chunk!r} はもうできあがっている'
                       f'（項目48-KI の入口）ので開かない')
        return None
    _odd_pairs = _odd.is_odd_run(chunk, tokenize_fn,
                                 store=store, dict_index=dict_index)
    if not _odd_pairs and not as_kana_run:
        return None                     # 印が立たない＝入口に入らない
    # **かな連続**（項目48-RW・2026-09-05）: ①は呼び手が 48-KS
    # （`pos_grammar.odd_kana_spans`）で確かめている。`is_odd_run` は
    # 漢字・カタカナの対の判定なので、かなだけの連続には立たない——
    # 「異様と判定はしているのに、決める道に渡していない」を塞ぐ入口。
    # 漢字で書けば直り（`田部井号して → タブ移動して`）、かなで書けば
    # 直らない（`たぶいごうして`）を同じ受け皿にする。
    if not _odd_pairs:
        _trace('異様', f'{chunk!r} → かな連続に①が立っている（48-KS）ので、'
                       f'異様の受け皿に通す（項目48-RW）')
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
    # **「1字を根拠にしては動かない」は外した**（項目48-IS・2026-08-23・
    # うにさんの指定「壊れるリスクを恐れすぎて前へ進んでいない。無しに
    # してもよい。型不一致は成立した自然な文字列だから、それを自然と
    # 判定するものがあればよい」）。`型不一致` は 48-IP の否定の接頭辞の
    # 規則で**印が立たなくなった**ので、この門の動機は消えている。
    # `一度止まる` は門(2)、`文字乳リュク` は門(1) が守る。
    if _odd_pairs:
        _trace('異様', f'{chunk!r} → 印が立った（{_odd_pairs}・設計27の入口）')
    # **印が立った理由は「表で見たことのない並び」だけか**（項目48-SM・
    # 2026-09-06）。うにさんの実機（web の商品説明の貼り付け）で
    #
    #     強炭酸 → 今日探索    強炭酸水 → 驚嘆潜水    爽健美茶 → 創建無茶
    #     電動爪切り → 電動締切  自動爪切り → 指導締切  九州方言 → 吸収放言
    #     炭酸度 → たんと       厚爪対応 → あつめ対応
    #
    # 元はどれも**辞書の語だけでできた0手の塊**。印は `can_join` の
    # 「その並びを表で見たことがない」だけで立った。置き換えの側は
    # **手を1つ当てた読みを、やはり見たことのない2語に敷き詰めた**もの
    # ——元より弱い証拠で、正しく書いたものを壊す。
    # そういう塊は、**1つの語（＋接辞）に届いて漢字を減らさないとき**
    # だけ置き換える（`小売り坂 → 効率化`・`再退化 → 最大化` は届く）。
    # 届かなければ紫だけ残す（決めない＝「補正先が無い」の側）。
    # 号＋し・流＋力・断片 のような**文法の判定**で立った印は今までどおり
    # （`田部井号して → タブ移動して`・`簡易流力 → 簡易入力` は 2語に組む）。
    _sm_unseen_only = False
    if _odd_pairs:
        try:
            _sm_unseen_only = not _odd.is_odd_run(
                chunk, tokenize_fn, store=store, dict_index=dict_index,
                skip_join=True)
        except Exception:
            _sm_unseen_only = False
    _sm_nk = sum(1 for _c in chunk if is_kanji(_c))
    _sm_n0 = _sm_content_count(chunk, tokenize_fn) if _sm_unseen_only else 0

    def _sm_ok(_repl):
        # **1語（＋接辞）に届くか、内容語が元より減る**（項目48-SM'）。
        # `引き月資料`（引き｜月｜資料＝3）→ `引き継ぎ資料`（2）は
        # 語の境目をまたいで1語に届いた形なので通す（き→ぎ の1手）。
        # `強炭酸`（2）→ `今日探索`（2）は減っていないので通さない
        if not _sm_unseen_only or not _repl:
            return True
        # **漢字を減らして、そのぶんかなを増やさない**（48-ND (b) と同じ線・
        # 48-GN）。`炭酸度 → たんと`・`厚爪対応 → あつめ対応` を止める。
        # 漢字の数だけで見ると `素帰任 → 確認`（余分な1打を落とすので
        # 1字減る）を、割合で見ると `引き月資料 → 引き継ぎ資料`（送り仮名が
        # 1字増える）を止めてしまった——実測して、この形に落ち着いた
        # かなは**カタカナも**（`語彙素同士 → ボイス同士`——漢字を読みに開いて
        # 本人の語彙のカタカナ語に敷き詰めた形。実機メモで実測）
        _kana = lambda _c: is_hiragana(_c) or is_katakana(_c)
        if (sum(1 for _c in _repl if is_kanji(_c)) < _sm_nk
                and sum(1 for _c in _repl if _kana(_c))
                > sum(1 for _c in chunk if _kana(_c))):
            return False
        _n1 = _sm_content_count(_repl, tokenize_fn)
        return _n1 <= 1 or _n1 < _sm_n0
    if _sm_unseen_only:
        _trace('異様', f'{chunk!r} → 印の理由は見たことのない並びだけ。'
                       f'置き換えは1語（＋接辞）か内容語が減るもので、'
                       f'漢字を減らしてかなを増やさないものに限る（項目48-SM）')

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
    # **打った読みの記録（`ime_readings`）を、補正を止める門には
    # 使わない**（項目48-NQ・2026-09-01・うにさんの指定）:
    #
    #     「**`ime_readings`（本人が確定した記録）の守りが想定外です。
    #       一度打って打ち直したものは、自動の補正判断として記録
    #       します。学習メニューの補正の判断に登録される認識です。
    #       あとから手動で解除できなければ困る類いです。
    #       手動で編集のない入力履歴は同音異義語などに用いられる
    #       だけです。**」
    #
    # **設計を取り違えていた。** 「本人が確定した」の記録は
    # **`decisions`（補正の判断）**のほう——学習メニューに出て、
    # **あとから手動で解除できる**。置換の最終検査で
    # `decisions.blocks(...)` が見ている（そこは今までどおり）。
    #
    # `ime_readings` は**手動で編集のない入力履歴**にすぎない。
    # 使い道は**同音異義語などの手がかり**だけで、
    # `kanji_guess._with_ime_readings` が打った読みを候補の
    # **先頭に置く**（設計25(乙)）——そちらは残す。
    #
    # ここに在った門（48-IS/48-LB「打った読みが解析の読みと同じなら
    # 触らない／丸ごと1語・実績20以上だけ受け入れる」）は、
    # **外して測ったら1行も動かなかった**（育ちの実機メモ0行・
    # readcheck 1759/174 で同じ）。守っていたはずの
    # `鍵括弧`・`漢字塊` は、いま **48-ME（できあがった塊の入口）**
    # ほかが守っている。**もう要らない門だった。**
    if _ar and _ar not in readings:
        readings.append(_ar)
    # **読みを広げる**（項目48-IS・2026-08-23・うにさんの指定
    # 「異様なものをそのままにしない」）。解析の言い切り1つでは
    # `素帰任 → もときにん` しか開けず、打ったはずの `すきにん` に
    # 届かなかった。
    #   (a) 漢字ごとの読みの組み合わせ（`reading_combos_with_rank`）
    #       の上位——48-DE が造語の道で避けた材料だが、ここは
    #       「異様さが消えた∧読める∧実績」の受け入れが後ろに在る
    #   (b) 解析の切り方のまま、各語の**辞書の別読み**を掛け合わせる
    #       （`仮名` = かめい／かな）
    _chunk_has_unknown = False
    try:
        from kanji_guess import reading_combos_with_rank as _combos
        for r, _rank in (_combos(chunk, dict_index) or ())[:6]:
            if r and r not in readings:
                readings.append(r)
    except Exception:
        pass
    _tok_info = []      # (表記, 読みが立つか) をトークン順に（項目48-RV''）
    try:
        # **格下げ後の並び**で見る（48-OR。`田部井`・`右田` は読みの
        # 立たない語として扱い、境目の門で守らない）
        _dtoks = list(_odd.downgraded_tokens(
            list(tokenize_fn(chunk) or ()), store=store,
            dict_index=dict_index))
    except Exception:
        _dtoks = []
    # **読みの立つ2字以上の漢字語は、解析の読みのまま**（項目48-TC・
    # 2026-09-06）。`産地アソート` の開いた読みに、漢字の読みの組
    # （`kanji_guess`）が `さんじ…` を混ぜ、48-LA が `三時アゾート` を
    # 組んだ——`産地` は読みが立つ語で、さんち 以外に読みようがない。
    # 信用しない固有名詞（48-OR で `_dtoks` が落とす）は縛らない
    try:
        from morphology import katakana_to_hiragana as _k2h_tc
        _fixed_rd = [_k2h_tc(t[2]) for t in _dtoks
                     if t[0] and len(t[0]) >= 2 and t[2]
                     and all(is_kanji(_c) for _c in t[0])
                     and len(t) > 5 and t[5]
                     and '固有名詞' not in (t[1] or '')]   # 田部井（たぶい）
    except Exception:
        _fixed_rd = []
    if _fixed_rd and len(readings) > 1:
        _keep_rd = [r for r in readings if all(f in r for f in _fixed_rd)]
        if _keep_rd and len(_keep_rd) < len(readings):
            _trace('異様', f'{chunk!r} → 読みの立つ語 {_fixed_rd} の読みを'
                           f'変えた組 {len(readings) - len(_keep_rd)} 件を'
                           f'落とす（項目48-TC）')
            readings = _keep_rd
    try:
        _alts_per_tok = []
        for _k_t, t in enumerate(tokenize_fn(chunk) or ()):
            _known_t = not ((len(t) > 5 and not t[5])
                            or t[0] in 'ゃゅょっぁぃぅぇぉ')
            if _k_t < len(_dtoks) and len(_dtoks[_k_t]) > 5 \
                    and not _dtoks[_k_t][5]:
                _known_t = False
            _tok_info.append((t[0] or '', _known_t))
            if (len(t) > 5 and not t[5]) or t[0] in 'ゃゅょっぁぃぅぇぉ':
                # **読みの立たない断片・小書き1字**（二ゅ力ミス の ゅ）。
                # 壊れた塊は書きたい形ではありえないので、下の
                # 「2語の組＋手」の門を開けたままにする（48-LN の例外）
                _chunk_has_unknown = True
            surf = t[0] or ''
            cand = []
            rd0 = t[2] or ''
            if rd0:
                cand.append(rd0)
            if dict_index is not None and surf:
                for r in (dict_index.readings_for_surface(surf) or ()):
                    if r and r not in cand:
                        cand.append(r)
            if surf and any(is_kanji(ch) for ch in surf):
                for r in _table_readings_for_surface(surf):
                    if r and r not in cand:
                        cand.append(r)
            if not cand:
                cand = [surf]
            # **1語あたり6つまで**（項目48-KW・2026-08-29。4つで切ると
            # `平` の読みが たいら・へい・びょう・ひょう で止まり、
            # **ひら（5番目）が落ちて** `平ん仮名 → ひらんがな` に
            # 開けなかった。ここは異様と判定した塊だけの道で、
            # 受け入れの門（異様さが消えた∧読める∧実績）は後ろに在る。
            # 順番は変えないので、今まで届いていた読みが先に決まる）
            _alts_per_tok.append(cand[:6])
        import itertools as _it
        for combo in _it.islice(_it.product(*_alts_per_tok), 36):
            r = ''.join(combo)
            if r and all(is_hiragana(c) or c == 'ー' for c in r) \
                    and r not in readings:
                readings.append(r)
    except Exception:
        pass
    readings = readings[:20]
    if not readings:
        _trace('異様', f'{chunk!r} → **ひらがなに開けない**'
                       f'（IMEの読みも解析の読みも無い）。決めない')
        return None
    _trace('異様', f'{chunk!r} → 開いた読み {readings}')

    # --- 3. 隣接キーなどを試す ---
    def _fixes(rd):
        got = {}
        _cost = {}

        def _add(_r, _why_, _c):
            """手の結果を、**費用つき**で積む（項目48-OQ(e)）。"""
            if _r not in got:
                got[_r] = _why_
                _cost[_r] = _c
            elif _c < _cost.get(_r, 9.9):
                _cost[_r] = _c
        # **入力方式を渡す**（項目48-OA・2026-09-01）。48-NJ'
        # （うにさんの指定「**ローマ字入力はローマ字の隣接キーを
        # 見てください。かな入力の隣接は見ません**」）を
        # `vocabulary.find_known_readings_flex` には掛けたのに、
        # **開いた読みに手を当てるこの道には掛け忘れていた**（学び22）。
        #
        # **幅も 1.0 → 1.4 に広げた**。うにさんの一覧
        # `たぶいごうして ⇒ たぶいどうして` の `ご→ど` は**費用1.4**で、
        # 1.0 の門にちょうど落ちていた。芯の再構築は 3.0 まで見て
        # いるので、1手の置き換えに 1.4 は狭いほうの数字。
        # **測って差0**（初期 readcheck 1949/99・1948/105、
        # fpcheck 0/0、seedcheck 39/40 壊し0、実機メモ 255/250、
        # 紫117、画面20行 ◎6——**全部据え置き**）。
        for i, ch in enumerate(rd):
            try:
                for alt, d in _near(ch, input_method=input_method):
                    if alt != ch and d <= _CHUNK_NEAR_MAX:
                        _add(rd[:i] + alt + rd[i + 1:], '隣接キー', d)
            except Exception:
                pass
        try:
            # **打った字を使う手が先、打っていない字を足す手はあと**
            # （項目48-OQ(e')・2026-09-03。**育ちで測って足した**）。
            # 重複・順序違い・濁点は**打鍵の証拠が在る**（打った字を
            # 読み替える）ので 1.0。**脱字**（1字入れる）は
            # **打っていない字を足す**ので **1.5**——隣接キーの上限
            # （1.4）より高くする。育ちで `たぶいごうして` に
            # 脱字の か を入れた `たぶかいごうして → **タブ会合して**`
            # が、隣接キーの `たぶいどうして → タブ移動して` を
            # 先に横取りしていた（`会合` が育ちの語彙に実績2）。
            _cheap = set()
            try:
                _cheap = set(_typo_repairs_cheap(rd))
            except Exception:
                pass
            for r in _typo_repairs(rd):
                _add(r, '誤打の型', 1.0 if r in _cheap else 1.5)
        except Exception:
            pass
        # **隣のキーを一緒に叩いた1字**（項目48-OL・2026-09-02。うにさんの
        # 一覧 `札ん港になる ⇒ 参考になる`＝さ**つ**んこう の つ(Z) は
        # さ(X) の隣）。SPEC の4つの型（重複・脱字・順序違い・濁点）に
        # 無い5つ目——余分な打鍵。**隣のキーのときだけ**（どの字でも
        # 消せる形にはしない。`_lc_hand_unit_fix` の1字削除も語の中だけ）。
        # 頭と尾は消さない（語の切り詰めで別の語がただ現れる・48-LC）
        for i in range(1, len(rd) - 1):
            try:
                _nb = set()
                for _c in (rd[i - 1], rd[i + 1]):
                    _nb.update(a for a, d in _near(_c, input_method=input_method)
                               if d <= 1.0)
            except Exception:
                _nb = set()
            if rd[i] in _nb:
                _add(rd[:i] + rd[i + 1:], '余分な隣のキー', 1.0)
        # **余分な字に濁点が付いた**（項目48-OR(b)・2026-09-03。
        # うにさんの一覧17行目 `右田でブルクリック`）:
        #
        #     打ちたかった   みぎた**゛**ぶるくりっく   （た＋濁点）
        #     打ったもの     みぎた**て゛**ぶるくりっく （て が余分）
        #     IME が合成     みぎた**で**ぶるくりっく
        #
        # ＝**清音 U ＋ 濁音 V** の並びは、`U゛` のつもりで
        # **余分な字を1つ挟んでしまい、濁点がそちらに乗った**形。
        # 直しは `U + V → U゛`（`たで → だ`）。
        # **頭は触らない**（`_i` は 1 から）——語の切り詰めで別の語が
        # ただ現れるのを避ける（48-LC と同じ用心）。
        # 費用は 1.3（余分な隣のキー 1.0 ＋ 濁点 0.3）
        for i in range(1, len(rd) - 1):
            u, v = rd[i], rd[i + 1]
            if u not in _OR_DAKUTEN_BASE or v not in _OR_VOICED_KANA:
                continue
            _add(rd[:i] + _TYPO_DAKUTEN[u] + rd[i + 2:],
                 '余分な字に濁点', 1.3)
        # **濁点の位置ずれ**（項目48-SB'・2026-09-06。つつぎ → つづき。
        # ゛1つの手で届く読みのほうが強いなら採らない——`むたづかい`）
        try:
            for r in _moved_dakuten_variants(rd):
                if not _dakuten_rival_stronger(rd, r, store):
                    _add(r, '濁点の位置ずれ', 1.0)
        except Exception:
            pass
        # **印のキーの隣を叩いた**（48-FX の手。項目48-OM・2026-09-02）。
        # うにさんの一覧 `解析課背中セク、 ⇒ 解析が長く、`＝かいせき**かせ**
        # な**かせ**く の せ(P) は ゛(@) の隣（2か所）。この手は
        # `rebuild_window_core` にしか掛かっていなかった（学び22）。
        # 同じ手が2回続く形（Shift の押し忘れ 48-KV と同じ理屈——手の
        # 位置ずれは連続して起きる）も1つの候補にする。上限は2回
        try:
            for r in _mark_slip_repairs(rd):
                _add(r, '印のキーの隣', 1.0)
                for r2 in _mark_slip_repairs(r):
                    # **同じ誤りの繰り返しは1つの仮説**（項目48-RR・
                    # 2026-09-05・うにさんの指定「背中セクよりも先に、
                    # せ が ゛ の隣接打ち間違いを疑う」）。費用は 2.0 の
                    # ままだが、`_add` の挿入順＋安定な並べ替えで、
                    # **同じ費用の「似た読み 2.0」（別々の手2つ）より
                    # 先**に来る。記録名で見分けられるようにした
                    _add(r2, '同じ誤りの繰り返し（印の隣×2）', 2.0)
        except Exception:
            pass
        # **似た読み（2手まで・費用2.0まで）**（項目48-IS）。
        # `すきにん → かくにん` は隣のキー2回（費用2.0）。1手の道
        # だけでは届かない。費用は打鍵の近さなので、ここまでは
        # 「打ち間違い」の範囲。
        try:
            from vocabulary import find_known_readings_flex as _fkr
            for r, c, e in _fkr(rd, store, max_edits=2):
                if c <= 2.0 and r != rd:
                    _add(r, f'似た読み({c:.1f})', c)
        except Exception:
            pass
        got.pop(rd, None)
        _cost.pop(rd, None)
        # **切り詰めは採らない**（項目48-OZ・2026-09-03）。
        # 芯の再構築には**同じ判定が既に在る**（6246行）のに、
        # 異様の道（開いた読みへの手）には無かった（学び22）。
        # うにさんの画面 `技発動 → **発動**`——開いた読み `ぎはつどう` に
        # 似た読み(1.1)で `はつどう`（頭の1字を落とした形）が当たって
        # いた。**打ち間違いで壊れた語は、元の語と別の形になるのが
        # 普通で、きれいに短くなることはまず無い。**
        # **連打の重複を取り除いただけ**（たたんご → たんご）は
        # 切り詰めではない——同じ `_is_repeat_collapse` で外す
        for _r in [_r for _r in list(got)
                   if len(_r) < len(rd) and _r in rd
                   and not _is_repeat_collapse(rd, _r)]:
            got.pop(_r, None)
            _cost.pop(_r, None)
        # **安いほうを先に**（項目48-OQ(e)・2026-09-03）。
        # `_CHUNK_NEAR_MAX` の注記に「次にやること」として書いてあった
        # もの。順位が無いまま幅だけ広げると、**濁点1つ（0.3）で
        # 届く直しを、隣接キー（1.4）の直しが実績で追い越す**
        # （`引き月資料` が `引き継ぎ資料` ではなく `引き抜き資料`
        # になった・2026-09-01 の実測）。費用で並べれば、幅を
        # 広げても安い手が先に採られる。並びは**安定**（同じ費用は
        # 今までの順のまま）
        return {k: got[k]
                for k in sorted(got, key=lambda r: _cost.get(r, 9.9))}

    # --- 4. 直した読みから表記を組む（部分は使用実績2以上）---
    def _surfaces(rd):
        out = {}
        parts = {}                  # 2語の組: 表記 → (読みa, 表記x, 読みb, 表記y)
        whole = set()               # 丸ごと1語で組めた表記（項目48-IS）
        try:
            for e in store.lookup(rd):
                if e.get('count', 0) >= 2:
                    out[e['surface']] = max(out.get(e['surface'], 0),
                                            e['count'])
                    whole.add(e['surface'])
        except Exception:
            pass
        # **索引の顔を丸ごと1語の表記に**（項目48-OJ・2026-09-02）。
        # 語彙に実績が無い基本語（課題・効率）が、異様と判定した塊の
        # 直し先になれるように。2語の組には使わない（48-IS の化け
        # かぎ各国・漢字近い の型）
        try:
            _f = _index_face(rd, store, dict_index)
            if _f and _f not in out:
                out[_f] = 2
                whole.add(_f)
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
                    if (x + y) in whole:
                        continue
                    # **片方が1字の漢字なら、組んだ形が世の中の1語のときだけ**
                    # （項目48-RV・2026-09-05）。`背中セク → 背中枠`（育ち）——
                    # 断片 `セク` を隣接キーで `わく` にし、`枠`（実績2）を
                    # `背中` に貼っていた。1字の漢字は読みが短く何にでも当たる。
                    # `is_unit('背中枠')` False／`手ブレ`・`入力ミス` True——
                    # **表で割れる**。表が無いとき（None）も採らない（守る側）
                    # **短いかなの部品も同じ**（`背中セク → 背中しく`——
                    # `せく→しく` の2字かなを `背中` に貼った・同日）。
                    # `入力ミス`（ミス 2字）は `is_unit` True で通る
                    def _sf_short(_p):
                        return ((len(_p) == 1 and is_kanji(_p))
                                or (len(_p) <= 2
                                    and all(is_hiragana(_c) or is_katakana(_c)
                                            or _c == 'ー' for _c in _p)))
                    if _sf_short(x) or _sf_short(y):
                        try:
                            import seed_japanese as _sj_sf
                            if _sj_sf.is_unit(x + y) is not True:
                                continue
                        except Exception:
                            continue
                    # ★★ **品詞のつながりで裁く**（項目48-RV'・2026-09-05・
                    # うにさんの指定「品詞の判定やつながりを重要視して
                    # ください」）。2語の組は**複合名詞**を組む道——
                    # `背中セク → 背中狭く`（名詞＋形容詞の連用形の直付き。
                    # `狭く` が solid だっただけ）は語ではない。両方が
                    # **名詞**（前は非自立・接尾を除く／後ろは接尾・サ変も可）
                    # のときだけ組む。`is_odd_run` は名詞＋形容詞を
                    # 「くっつけない並び」に数えていない（実測 []）ので、
                    # ここで見る
                    try:
                        _tx = tokenize_fn(x)
                        _ty = tokenize_fn(y)
                    except Exception:
                        _tx = _ty = None
                    if not _tx or not _ty:
                        continue
                    _px = (_tx[-1][1] or '') if _tx else ''
                    _py = (_ty[0][1] or '') if _ty else ''
                    if (not _px.startswith('名詞')
                            or _px.startswith('名詞:非自立')
                            or _px.startswith('名詞:接尾')
                            or not _py.startswith('名詞')
                            or _py.startswith('名詞:非自立')):
                        _why['品詞のつながり'] += 1
                        continue
                    if min(cx, cy) > out.get(x + y, 0):
                        parts[x + y] = (a, x, b, y)
                    out[x + y] = max(out.get(x + y, 0), min(cx, cy))
        _surfaces.whole = whole
        _surfaces.parts = parts
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
                if surf == chunk:
                    continue
                # **長さ ±1**（設計27 の受け入れ）。ただし
                # **カタカナを含む塊は縮んでよい**（項目48-MU・
                # 2026-08-31）——カタカナは**読みを字で綴った形**
                # なので1字≒1拍、漢字は1字≒2拍。字数で測ると
                # `乳リュク`(4) → `入力`(2) が「縮みすぎ」に見えるが、
                # **読みは にゅうりゅく → にゅうりょく で同じ長さ**。
                # 伸びる側は今までどおり ±1（膨らむ化けを止める）。
                _dl = len(surf) - len(chunk)
                if _dl > 1:
                    continue
                if _dl < -1 and not (any(is_katakana(c) for c in chunk)
                                     and len(surf) >= 2):
                    continue
                # **本人確定の記録がある塊は、丸ごと1語・実績20以上
                # だけが上書きできる**（項目48-LB。2語の組は 48-IS の
                # 化け かぎ各国・漢字近い の型なので通さない）
                _seen_any = True
                # 5-a: **異様さが消えたか**
                if _odd.is_odd_run(surf, tokenize_fn,
                                   store=store, dict_index=dict_index):
                    _why['異様さが消えない'] += 1
                    continue
                # 5-a': **2語の組では、読みを変えていない側の表記は元のまま**
                # （項目48-IU）。直したのは読みであって、読みが同じ側は
                # 本人が IME で選んだ表記がそのまま在る。`鍵括弧`
                # （かぎ＋かっこ → かぎ＋かっこく）で `かぎ` 側が `カギ` に
                # 変わる組は在り得ない。`野外文章 → 長い文章` は `文章` 側が
                # 元のままなので通る。
                _pt = getattr(_surfaces, 'parts', {}).get(surf)
                if _pt is not None and surf not in getattr(_surfaces,
                                                           'whole', ()):
                    _a, _x, _b, _y = _pt
                    if ((rd.startswith(_a) and not chunk.startswith(_x))
                            or (rd.endswith(_b) and not chunk.endswith(_y))):
                        _why['読みを変えていない側の表記が変わる'] += 1
                        continue
                # 5-a'': **読みを編集した直しで、表の差が漢字1字だけの
                # 形は採らない**（項目48-JG・2026-08-25。うにさんの
                # 「補正の誤検知」: `空白行 → 空白くい`（行 いく→くい・
                # 実績96）と `高橋佑 → 高橋よう`（佑 ゆう→よう・実績3）。
                # 1つ塞ぐと次の候補で化ける（→空白以降・高橋優雅＝48-CV
                # の型）ので、**読みの編集（fixed != rd）そのもの**に門を
                # 掛ける。根拠がその1字の読み替えしかない＝48-HU 門(3)。
                # 読みを編集しない表記選び（背景食 → 背景色・クリック化 →
                # クリックか）は fixed == rd なので通る。
                # **丸ごと1語で実績10以上なら、この門はくぐれる**
                # （項目48-LB・2026-08-29。`雛仮名 → 平仮名`(実績16) が
                # 雛→平 の1字差で落ち、かな表記 `ひらがな`(実績2) に
                # 負けていた。48-JG の化け（空白くい・高橋よう）は
                # どちらも**2語の組**で、丸ごと1語ではない）
                if fixed != rd and _single_kanji_diff(chunk, surf) \
                        and not (surf in getattr(_surfaces, 'whole', ())
                                 and cnt >= _WHOLE_KANJI_FLOOR):
                    _why['1字の漢字の読み替え'] += 1
                    continue
                # 5-a'''': **読みに手を掛けた「2語の組」は採らない**
                # （項目48-LN・2026-08-30。国語辞書 → 今後辞書・
                # 同音異義 → 同音過ぎ〔置換〕を塞ぐと 利用辞書・
                # 同音会議〔挿入〕が来た——48-CV の型なので手の種類を
                # 問わず族ごと閉じる。読み＋手＋2語の組は、正しい
                # 複合語と打ち間違いを**構造では割れない**。
                # **丸ごと1語**（素帰任 → 確認・目もち長 → メモ帳）と、
                # **読みを変えない表記選び**（fixed == rd・背景食 →
                # 背景色）は従来どおり。野外文章 → 長い文章（植えた
                # テスト語）はこれで失われる——壊さない＞直る）
                if fixed != rd \
                        and surf not in getattr(_surfaces, 'whole', ()) \
                        and not _chunk_has_unknown:
                    _why['手を掛けた2語の組'] += 1
                    continue
                # ★★ **読みの立たない語が居る塊でも、手を掛けた2語の組は
                # 「断片を直して貼り直す形」だけ**（項目48-RV''・2026-09-05・
                # うにさんの指定「品詞の判定やつながりを重要視」）。
                # `背中セク` は、上の例外（塊に断片が居るので手＋組を許す）で
                # `背中枠`→`背中しく`→`背中狭く`→**`ハイ仲良く`**と、塞ぐ
                # たびに次の当て推量が出た。最後のは `背中` の読み `せなか` を
                # `はい｜なか` に**切り直して**組んだもの——手は断片 `セク` に
                # 当てたのに、組の境目は断片の境目（`せなか｜せく` の 3）に
                # 無い。**組の境目が、読みの立たない語の境目に揃うときだけ**
                # 通す。読みの切れ目を変える組は当て推量（48-ND「書かれ方は
                # 変えない」を読み方にも）
                if fixed != rd and _pt is not None \
                        and surf not in getattr(_surfaces, 'whole', ()) \
                        and not _hand_boundaries_ok(
                            _tok_info, _alts_per_tok, rd, fixed,
                            [len(_pt[0])]):
                    _why['読みの立つ語の読みを切り直す組'] += 1
                    continue
                # 5-b: 語の並びとして読めるか
                try:
                    if not _real(surf, store, tokenize_fn):
                        _why['語の並びとして読めない'] += 1
                        continue
                except Exception:
                    _why['語の並びとして読めない'] += 1
                    continue
                # 5-c: **自然さは拒否権だけ**（大きく悪くなるなら採らない）。
                # **丸ごと1語の表記には掛けない**（項目48-IS・実測）。
                # 自然さの表は かな を漢字より大きく下げる（48-EP）ので、
                # `雛仮名` の直し先 `ひらがな`（−10008）が落ち、2語の組
                # `引い仲間`（−3859）が通った。実績のある1語は、それだけで
                # 日本語として在る。拒否権は2語の組にだけ使う。
                try:
                    if surf not in getattr(_surfaces, 'whole', ()) \
                            and _naturalness.gain(chunk, surf) \
                            < -_ODD_REOPEN_DROP:
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
                # 元が漢字なら漢字の表記を優先する（`非欄仮名` →
                # `平仮名` と `ひらがな` が同じ実績なら前者・項目48-IS）
                _kanji_pref = 0 if (_is_all_kanji(chunk)
                                    and any(is_kanji(c) for c in surf)) else 1
                # **丸ごと1語が、2語の組より先**（項目48-IS）。育った語彙で
                # `非欄仮名` が `開き`＋`かな` に組まれ、`ひらがな` に負けた。
                _whole_pref = 0 if surf in getattr(_surfaces, 'whole',
                                                   ()) else 1
                # **実績が同点なら、開いた読みの自然さで並べる**
                # （CN_YOMI_PRIOR=1・2026-08-28。いままで同点の最後は
                # 表記の五十音順＝でたらめだった。実績の軸（48-IE）は
                # 動かさない——同点の中の順だけ）。
                _yp = _yomi_prior_bucket(fixed) if _yomi_prior_enabled() else 0
                # ★★ **実績の目盛りが2段しか残らないぶんを、
                # 「世の中での一般度」で埋める**（項目48-QG'・2026-09-05）。
                #
                # うにさんの指定（2026-08-21・項目48-IE）は「異様だと
                # 判定したら、**実績のいちばん高い候補に直す**」。
                # 回数を廃した今、`cnt` は 2 か 2（＝ほぼ同点）にしか
                # ならないので、**この軸だけでは決まらなくなった**:
                #
                #     好き任 → 確認(実績3) が 後任(実績2) に勝っていた
                #            → 同点になり、**表記の字コード順で 後任**
                #     田部井号して → タブ移動(world 2) と タブ異動(world 1)
                #            → 同点になり、**異動** が勝った（実測）
                #
                # 一般度の軸（`_tc` → `_kt_rank`）を `-cnt` のすぐ
                # 後ろではなく `_kanji_pref` の後ろに置く——48-IS の
                # 「元が漢字なら漢字の表記を優先」は一般度より上の
                # 決まり（`非欄仮名 → 平仮名`）。
                #
                # **順序（費用 → 段）とその根拠は `_kango_tier_of` の
                # 説明を見ること**（項目48-QR。「決めているのは最初の
                # 行」——同じ実測を2か所に書くと、いつか食い違う）。
                # ここで実際に解けた例だけ書く:
                #
                #     確認 段1 ／ 新任 段2  —— **費用はどちらも 101**
                #
                # 費用だけだと同点になり、**表記の字コード順**で
                # `新任` が勝っていた（育ちの実機メモで
                # `すきにん → 新任`）。費用が同点のときだけ段で割る。
                #
                # ★★ **`world` を軸にする案も、測って外した**。
                # `world`（書籍での帯・48-DA）は**辞書から取り込んだ語
                # にしか付かない**——本人が打って覚えた語は 0 のまま。
                # 育ちで `移動`（本人の語・world 無し）が
                # `異動`（辞書・world 1）に負けた。
                _kt_rank = _kango_tier_of(surf)
                _tc = _table_cost(surf)
                if _tc is None:
                    _tc = 10 ** 9
                key = (_whole_pref, -cnt, _kanji_pref, _tc, _kt_rank,
                       _yp, len(surf), surf)
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
    # **打った記録は、語の組み立ての道には掛けない**（項目48-NP・
    # 2026-09-01・うにさんの指定）:
    #
    #     「**有力はまだ直りませんね。有力の後ろに続いてミスが来る
    #       はずないのですが。**」
    #
    # `に有力ミス` は うにさん自身が変換して確定した並びなので、
    # 48-LB の門（本人確定の記録がある塊は、丸ごと1語・実績20以上
    # だけが上書きできる）が全部を塞いでいた。だが**その記録は
    # 「IME がそう変換した」ことしか言っていない**——打ち間違いの
    # まま変換して確定しても同じ記録が残る（48-LB 自身がそう書いて
    # いる）。**在り得ない並びなら、記録は「本人が選んだ」の証拠に
    # ならない。**
    #
    # 床（実績20以上）を置いたのは **48-IS の化け（かぎ各国・
    # 漢字近い）が2語の組だったから**。**語の組み立て（48-LA）は
    # 2語の組ではない**——読みを語で敷き詰める別の道で、受け入れは
    # 48-MZ/48-ND で書かれ方まで見るようにしてある。**この道にだけ
    # 記録の床を外す。**
    if best is None and assemble:
        # **語の組み立て（語＋語）でも当てる**（項目48-LA・2026-08-29。
        # **前段（_reopen_mixed_run_fixes）から呼ばれたときだけ**——
        # 本道の塊にも効かせると `音訓送り仮名 → 音訓送りかな` を
        # 作った（実測）。
        # `にゅうりょ組ス` の開いた読み にゅうりょくみす は**1語**では
        # 実績に届かないが、**入力（実績）＋ミス** で組める。道具と門は
        # 48-KV の⑤（変換が既定）と同じ——先頭の区切りは語彙 count>=2
        # かつ読み4字以上・中身の区切りは2つまで・残りは機能語）。
        # **開いた読みそのものと、手を当てた読みの両方**に掛ける
        # （項目48-MW・2026-08-31）。`にゅ力ミス` の開いた読み
        # `にゅりょくみす` はそのままでは組めないが、**う を戻すと**
        # `にゅうりょくみす` ＝ 入力＋ミス。`にゅうりよくみす`
        # （かなだけ）は 48-KV が う を戻してここへ来るのに、
        # **漢字の混ざった `にゅ力ミス` は来られなかった**——
        # 同じ誤りなのに、書かれ方で届いたり届かなかったりしていた。
        #
        # **ここは best が無いときだけの受け皿**（順位には割り込まない）。
        # 先に足すと `雛仮名 → 表明`・`にゅうりょ組ス → 入力ます` に
        # なった（実測。組めているならそちらが上）。
        _tried = set()
        # **元の塊の頭が漢字で書かれていて、変種がその読みから始まるなら、
        # 頭はその表記を保つ**（項目48-RQ(iii)・48-IU の一般化・2026-09-05）。
        # `解析課背中セク` の `解析`（かいせき）には手を当てていない——
        # 会席・懐石に置き換えない。使うのは 48-RQ の枝（語＋手が生んだ
        # 助詞＋語）だけ
        _keep_head = None
        try:
            _t0 = (tokenize_fn(chunk) or ())[0]
            if (_t0 and _t0[0] and all(is_kanji(_c) for _c in _t0[0])
                    and len(_t0) > 5 and _t0[5] and _t0[2]
                    and all(is_hiragana(_c) for _c in _t0[2])):
                _keep_head = (_t0[2], _t0[0])
        except Exception:
            _keep_head = None
        # **解析が読んだ読みに近いものから試す**（項目48-OQ(d)・
        # 2026-09-03）。この受け皿は「最初に通ったものを採る」ので、
        # **並び順がそのまま順位**になる。いままでの並びは
        # `reading_combos_with_rank` の順（＝音訓表の順）で、
        # `田部井` を **たぶせい**（井＝せい）と読む形が
        # **たぶい**（井＝い）より先に来ていた。そこに濁点の手
        # （費用 0.3）が当たって `たぶせいこうして → タブ成功して` が
        # 隣接キーの手（1.4）の `たぶいどうして → タブ移動して` を
        # 先に横取りしていた（実測・実機メモ3行）。
        #
        # **補正は「打ち間違いを戻す」**なので、解析が読んだ読み
        # （＝書いてあるとおりの読み）から遠い読みを先に採るのは、
        # 打ち間違い以上のことを決めていること。48-ND「書かれ方は
        # 変えない」を**読み方**にも当てる。並びは**安定**なので、
        # 隔たりが同じものは今までの順のまま。
        for _rd in (sorted(readings, key=lambda r: _reading_gap(r, _ar))
                    if _ar else readings):
            _try = [_rd]
            try:
                _fx = _fixes(_rd)
                _try += [v for v in _fx if v not in _tried]
                # **手の並びを記録に残す**（項目48-RR・2026-09-05）——
                # 「どの仮説を先に疑ったか」を trace で読めるように。
                # 同じ費用なら `_fixes` の挿入順（安定な並べ替え）で、
                # **同じ誤りの繰り返し（印の隣×2）が、別々の手2つ
                # （似た読み 2.0）より先**に来る
                _trace('異様', f'{_rd!r} の手（先頭12）: '
                               f'{list(_fx.items())[:12]}')
            except Exception:
                pass
            for _v in _try:
                if _v in _tried:
                    continue
                _tried.add(_v)
                try:
                    _conv = _convert_odd_kana_run(
                        _v, store, dict_index,
                        vocab_only=vocab_only, short_head=True,
                        # **手が変えた位置**（項目48-RQ(i)）。元の読み
                        # そのもの（_v == _rd）なら無し＝語＋助詞＋語の
                        # 枝は開かない
                        born=(_born_positions(_rd, _v)
                              if _v != _rd else None),
                        keep_head=_keep_head, tokenize_fn=tokenize_fn)
                except Exception:
                    _conv = None
                if not _conv or _conv[0] == chunk:
                    continue
                # ★★ **手を当てていない読みの立つ語の読みの中に、組の頭の
                # 境目を置かない**（項目48-RV''。`背中セク` → `はいなかよく`
                # → `ハイ｜仲良く` は `背中` の読みを切り直していた）
                if _v != _rd and len(_conv) > 1 and _conv[1] \
                        and not _hand_boundaries_ok(
                            _tok_info, _alts_per_tok, _rd, _v, [_conv[1]]):
                    _why['読みの立つ語の読みを切り直す組'] += 1
                    continue
                # 受け入れは本道と同じ形で——**長さ ±1**（カタカナを
                # 含む塊は縮んでよい）と**異様さが消えたか**
                _dl2 = len(_conv[0]) - len(chunk)
                if _dl2 > 1:
                    continue
                if _dl2 < -1 and not (any(is_katakana(c) for c in chunk)
                                      and len(_conv[0]) >= 2):
                    continue
                if _odd.is_odd_run(_conv[0], tokenize_fn,
                                   store=store, dict_index=dict_index):
                    continue
                # **「する」にならない名詞に「し／して」を付けない**
                # （項目48-OQ(d)）。`たぶいこうして → タブ以降して` は
                # 読みでは敷き詰まるが、`以降` は副詞可能名詞で
                # 「以降する」の形を作らない。48-IX の族の、組み上がり側
                if not _suru_attach_ok(_conv[0], tokenize_fn):
                    continue
                # **書かれ方は変えない**（項目48-ND・2026-08-31）。
                # 組み立ては「読みを語に敷き詰める」道なので、
                # **打った人が使っていない字種を生やす**ことがある。
                # 育ちの実機メモで、1つずつ受け止めて3つになった:
                #
                #   接周辞 → **結集言葉**      漢字が増えた（3→4）
                #   由良仮名 → **有料借りや**  漢字だけの塊にかなが残った
                #   音訓送り仮名 → **音訓送りかなり**  漢字が減った（5→3）
                #
                # どれも「読みは合うが、その人はそう書かない」形。
                # 3つとも**元の塊の書かれ方**だけを見ていて、語彙も
                # 辞書も引かない——**同じ判定を2度書かない**（48-GN）。
                #
                # (a) **元に無かったカタカナは生やさない**。カタカナは
                #     読みを字で綴った形なので、打った人が選んで書く
                #     （`にゅ力ミス → 入力ミス` は元に ミス が在る）
                #
                #     **例外**（項目48-OQ(c)・2026-09-03）: **その
                #     カタカナ語が本人の語彙に実績2以上で在る**とき
                #     （タブ）は生やしてよい。この門が止めたいのは
                #     `メモうち帳` のような**辞書だけの**カタカナで、
                #     本人が使っている語は「打った人が選んで書く」側。
                #     判定は `_grown_katakana_is_own_word` ただ1つ。
                _kata_own = _grown_katakana_is_own_word(_conv[0], chunk,
                                                        store)
                if any(is_katakana(c) for c in _conv[0]) and not _kata_own \
                        and not any(is_katakana(c) for c in chunk):
                    continue
                # (b) **漢字を減らして、そのぶんかなを増やさない**。
                #     組み立ては読みを語で埋める道なので、埋めきれない
                #     所を**かなのまま出す**（`_tail_kana_ok`）。それが
                #     元の漢字の上に乗ると、**書いてあった語をかなに
                #     開き戻す**（音訓送り仮名 → 音訓送り**かなり**）。
                #     **漢字どうしの入れ替えは通す**——`奥悠久子帝`(5) →
                #     `奥行固定`(4) はかなが増えていないので別の話
                _nk = sum(1 for c in chunk if is_kanji(c))
                _nh = sum(1 for c in chunk if is_hiragana(c))
                if sum(1 for c in _conv[0] if is_kanji(c)) < _nk \
                        and sum(1 for c in _conv[0]
                                if is_hiragana(c)) > _nh \
                        and not _kana_growth_is_grammar(_conv[0]):
                    continue
                # (c) **漢字だけの塊は、長くならない**。漢字1字はおよそ
                #     2拍なので、同じ読みを敷き詰めて**字数が増える**のは
                #     読みの切れ目を変えた（＝当て推量した）しるし
                if _is_all_kanji(chunk) and len(_conv[0]) > len(chunk):
                    continue
                # (d) **元に無いカタカナの連続は、世の中の語でなければ
                #     生やさない**（項目48-SU・2026-09-06）。(a) は
                #     「元にカタカナが在れば生やしてよい」だが、元の
                #     `シュワー` を手で `シヤワー` に変えて敷き詰めた形は
                #     語ではない（うにさんの実機 `使用シュワー → 使用シヤワー`）
                if not _new_katakana_known(_conv[0], chunk, dict_index):
                    _why['生やしたカタカナが世の語ではない（48-SU）'] += 1
                    continue
                if not _sm_ok(_conv[0]):
                    _why['見たことのない並びに、手を当てた語の組（48-SM）'] += 1
                    continue
                # (e) ★★ **末尾の「活用した用言」は書き換えない**
                #     （項目48-UT・2026-09-07）。述語は文法として完成した
                #     1つの単位で、その手前の誤字がそこまで伸びることはない。
                #
                #         じょうを見ました → **異常をみました**
                #         （`じょう → 異常` は当たっているのに、
                #           **正しく書けていた `見` をかなに開き戻していた**）
                #
                #     名詞の接尾（`流`・`力`・`長`）には掛からないので、
                #     `簡易流力 → 簡易入力`・`目もち長 → メモ帳` はそのまま。
                _tp = _trailing_predicate(chunk, tokenize_fn)
                if _tp and not _conv[0].endswith(_tp):
                    _why['末尾の用言を書き換える語の組（48-UT）'] += 1
                    continue
                _trace('異様', f'{chunk!r} → 異様なので {_v!r} に開き、'
                               f'語の組み立てで {_conv[0]!r}（項目48-LA）')
                return _conv[0], 'その他'
    if best is None:
        # --- 項目48-PO: 表記に組めなくても、手を当てた読みが文法で
        #     説明が付くなら、**異様の対の範囲だけ**をその読みで置き換える
        #     （も水戸に戻ります → もとに戻ります）。
        _po = _po_replace_odd_span(chunk, _odd_pairs, _ar, _fixes,
                                   tokenize_fn, store, dict_index)
        if _po is not None and _po != chunk and not _sm_ok(_po):
            _trace('異様', f'{chunk!r} → 読みでの置き換え {_po!r} は、'
                           f'見たことのない並びだけの塊には当てない（項目48-SM）')
            _po = None
        if _po is not None and _po != chunk:
            _trace('異様', f'{chunk!r} → 表記には組めないが、手を当てた'
                           f'読みが文法で説明が付く。異様の対の範囲だけを'
                           f'読みで置き換えて {_po!r}（項目48-PO）')
            return _po, 'その他'
        # **ここは assemble ブロックの外**（2026-08-30 実測）。中に
        # インデントされていたため、本道（assemble=False）で best が
        # 無いと下の取り出しへ落ちて**未処理の例外**になり、同じ行の
        # あとの塊が全部飛ばされていた（`野外文章／素帰任` の
        # 素帰任 が黙って素通り。野外文章が必ず直っていた間は
        # 露出しなかった）。
        # **48-RK**（2026-09-05）: 直し先が出なかった／全部落ちた。
        # **開いた読みを、既知の頭で割って熟語＋熟語に決める**
        # （`簡易流力` → 開くと `かんいりゅうりょく` → `簡易入力`）。
        # A/B の道（かな連続）と**同じ1本**を呼ぶ（48-GN）。
        for _rd_try in readings[:8]:
            _khc = _fix_known_head_compound(_rd_try, store, tokenize_fn,
                                            dict_index)
            if _khc is not None and _khc != chunk and not _sm_ok(_khc):
                _trace('異様', f'{chunk!r} → 既知の頭で割った {_khc!r} は、'
                               f'見たことのない並びだけの塊には当てない'
                               f'（項目48-SM）')
                _seen_any = True
                continue
            if _khc is not None and _khc != chunk:
                _trace('異様', f'{chunk!r} → 異様なので {_rd_try!r} に開き、'
                               f'既知の頭で割って {_khc!r}（項目48-RK）')
                return _khc, 'その他'
        if not _seen_any:
            _trace('異様', f'{chunk!r} → 直し先の**表記が一つも組めない**'
                           f'（実績2以上の語に届かない）。決めない')
        else:
            _trace('異様', f'{chunk!r} → 直し先は出たが全部落ちた: '
                           f'{dict(_why)}。決めない')
        return None
    _, surf, how, rd, fixed, cnt = best
    if not _sm_ok(surf):
        _trace('異様', f'{chunk!r} → {how}の {surf!r} は、見たことのない'
                       f'並びだけの塊には当てない（項目48-SM）。決めない')
        return None
    _trace('異様', f'{chunk!r} → 異様なので {rd!r} に開き、'
                   f'{how}で {fixed!r} に直して {surf!r}'
                   f'（実績{cnt}・設計27）')
    return surf, 'その他'



_TABLE_READINGS = None
_TABLE_COST = None


def _kango_tier_of(surface):
    """
    **その表記の「一般的さの段」**（`kango_tier`・AI の判断・48-OJ）。
    1＝日常語／2＝一般語／3＝それ以外。**2字の漢語だけ**が表に在る。

    ★★ **表に無い形（3字以上・かな混じり・カタカナ）は 1 を返す**
    ——**罰しない**。この表が知っているのは「**この2字漢語は日常語では
    ない**」ということだけで、載っていない形について何も言っていない。
    「知らない」を「珍しい」の側に倒すと、**カタカナ語が負ける**:

        まいす（マイナス の脱字）→ 段2 扱いにすると
        **`麻酔`（段1）に負けて `ますい`** になった（実測・初期状態）

    ＝ この軸は「**段2・段3 と分かっている2字漢語を下げる**」だけの
    片側の軸。`world` の 0 で同じ間違いを一度踏んでいる（項目48-QG'）。

    ★★ **見るのは、同梱の費用表が同点だったときだけ**（費用 → 段）。
    段を第1の軸にした形も測ったが、**割れすぎた**——初期で
    直り −4／化け +2。費用表は 2字の漢語に同点が多い（`確認` も
    `新任` も 101）ので、**そこだけを段が裁く**のがちょうどよい。

    48-VZのLD（独立かなの置換）では、既存の一般性が同点の候補を
    段→費用の順で比べる。学習済みでも日常語が珍しい語に負けないため。
    この順序変更はLDの候補だけで、他の道の費用→段は維持する。

    引き当ての内側から呼ばれるので**例外を外へ出さない**。
    """
    if not surface or len(surface) != 2:
        return 1
    try:
        if not all(is_kanji(c) for c in surface):
            return 1
        import kango_tier as _kt
        if not _kt.available():
            return 1
        return int(_kt.tier(surface))
    except Exception:
        return 1


def _base_reading_is_own_word(reading, store):
    """
    **書かれている語の読みに、表記が1つでも在るか**
    （項目48-QG'・2026-09-05）。在るなら、そこは触らない。

    （名前は「この人の語か」と読めるが、**聞いているのは在るか無いか**
    ——`solid` で聞くと壊れる。下の「solid で聞いたら」の節。）

    回数を廃した（48-QG）ぶんの、48-KU の**優勢の比（20倍）の
    置き換え**。もとは

        need = max(2, 20 * 書かれている語の回数)

    で、**書かれている語をまだ使っていない**（回数0）ときは
    `need = 2`＝「直し先が立っていれば通す」、使っているときは
    **20倍の圧倒的な差**を求めていた。回数を廃すと 20倍は
    二度と越えられないので、**残るのは前半の意味だけ**:

        書かれている語がこの人の語として立っている → 触らない
        立っていない                               → 直し先が立てば通す

    ### ★★ 費用の差で言い直す案は、**測って外した**

    「直し先のほうが同梱の表で安い（＝世の中でよく使う）なら通す」に
    してみたら、**わずかな差でも通ってしまい**、育ちで壊れた:

        居で以下 → 巨大化（正しい）→ **強大化**
        （`巨大` 費用 119 ／ `強大` 費用 113 ——**6 の差は誤差**）

    もとの門は「20倍」＝圧倒的な差を求めていたのに、置き換えが
    「わずかでも上」になっていた。では何点で圧倒的かというと、
    `囚虜 115 → 終了 101` は 14 の差で**通したい**——**14 と 6 の
    あいだに線を引く根拠は無い**（★★ 数字の当てもの）。
    **言えないことは言わない。**

    代償: 育ちで `囚虜時 → 終了時` が沈黙する（打鍵の試しで
    `囚虜` を覚えてしまっているため）。**初期状態では語彙に無い**
    ので今までどおり直る。§4 の「数の証拠が消えるぶんの失い」の1つ。

    ### ★★ **`solid` で聞いたら、門が広がって正しい語を壊した**

    最初は `count >= 2`（＝ solid）で聞いた。だが旧の `base_count == 0`
    は「**その読みの entry が1つも無い**」という意味で、
    「立っていない」ではない。育ちの語彙には **count 1 の entry が
    13,866件**あり、solid で聞くとそれが全部「立っていない」側へ
    落ちて、**門が旧より広く開く**。実測（育ちの2字漢語 3,398語×接尾）
    で、**旧が無傷だった 21件を新だけが書き換えた**:

        除雪用 → **常設用** ／ 助演者 → **上演者**
        考古的 → **口腔的** ／ 粗大化 → **壮大化**

    ★★「正しく書いたものを壊さない ＞ 直る」。**entry が1つでも
    在るなら触らない**——それが旧の `base_count == 0` そのもの。
    """
    try:
        return bool(store.lookup(reading))
    except Exception:
        return True         # 分からないときは触らない側へ


def _table_cost(surface):
    """
    同梱の表（`seed_japanese_cost.txt.gz`）での**その表記の費用**
    （小さいほど世の中でよく使う・項目48-IS）。無ければ None。
    びっくり 95 ／ びっしり 133 ／ びっちり 133。
    """
    _table_readings_for_surface('')          # 読み込みを起こす
    if not _TABLE_COST:
        return None
    return _TABLE_COST.get(surface)


def table_surfaces_for_reading(reading, limit=4):
    """
    同梱の表（`seed_japanese_cost.txt.gz`・読み→表記:費用）を**表の
    向きのまま**引いて、その読みの**漢字を含む表記**を費用の低い順に
    返す（項目48-KC・2026-08-27。F2 の「漢字にする」候補の材料）。

    `dict_index` は費用 4000 で刈ってあるので `何故`（`なぜ`）や
    `平仮名`（`ひらがな`）を持たない。表はその外側も持つ。
    無ければ []（意見なし）。
    """
    _table_readings_for_surface('')          # 読み込みを起こす
    if not _TABLE_SURFACES or not reading:
        return []
    got = sorted(_TABLE_SURFACES.get(reading, ()))
    return [sf for _c, sf in got[:limit]]


_TABLE_SURFACES = None


def _table_readings_for_surface(surface):
    """
    同梱の表（`seed_japanese_cost.txt.gz`・読み→表記）を逆に引いて、
    **その表記が持ちうる読み**を返す（項目48-IS）。`仮名` → かな／かめい。

    janome は `仮名` を `かめい` としか言わず、索引（`dict_index`）は
    費用 4000 で刈ってあるので `仮名`（5614）を持たない。壁③。
    表は漢字を含む4字までの表記だけ持つ（読みは費用の低い順）。
    無ければ []（意見なし）。
    """
    global _TABLE_READINGS, _TABLE_COST, _TABLE_SURFACES
    if _TABLE_READINGS is None:
        _TABLE_READINGS = {}
        _TABLE_COST = {}
        _TABLE_SURFACES = {}
        try:
            import gzip as _gz
            import os as _os
            here = _os.path.dirname(_os.path.abspath(__file__))
            path = _os.path.join(here, 'seed_japanese_cost.txt.gz')
            if not _os.path.exists(path):
                path = 'seed_japanese_cost.txt.gz'
            with _gz.open(path, 'rt', encoding='utf-8') as f:
                for raw in f:
                    parts = raw.rstrip('\n').split('\t')
                    rd = parts[0]
                    if not rd or not all(is_hiragana(c) or c == 'ー'
                                         for c in rd):
                        continue
                    for pr in parts[1:]:
                        if ':' not in pr:
                            continue
                        sf, c = pr.rsplit(':', 1)
                        try:
                            c = int(c)
                        except Exception:
                            continue
                        if len(sf) <= 8:
                            _old = _TABLE_COST.get(sf)
                            if _old is None or c < _old:
                                _TABLE_COST[sf] = c
                            # 読み→漢字表記（`table_surfaces_for_reading`・
                            # 項目48-KC）。1読み6件まで（行は費用順）。
                            if (any(is_kanji(ch) for ch in sf)
                                    and len(rd) >= 2):
                                _lst = _TABLE_SURFACES.setdefault(rd, [])
                                if len(_lst) < 6:
                                    _lst.append((c, sf))
                        if not (1 <= len(sf) <= 4) \
                                or not any(is_kanji(ch) for ch in sf):
                            continue
                        _TABLE_READINGS.setdefault(sf, []).append((c, rd))
            for sf, lst in _TABLE_READINGS.items():
                lst.sort()
        except Exception:
            _TABLE_READINGS = {}
            _TABLE_SURFACES = {}
    return [rd for _c, rd in _TABLE_READINGS.get(surface, ())[:4]]


def _arrow_respell(line, tokenize_fn, dict_index=None, _source_check=True):
    """
    **設計34: `誤 ⇒ 正` の並記で、読みが同じ差分の左を右に合わせる**
    （項目48-JI・2026-08-25。うにさんの指定「変わる方法を検討して
    ください」から）。

    的リストの1行目にうにさんが定義を書いている——
    「同音異義語：**対の単語に合わせる形**で同じ意味を持つもの」。
    そして的の記法そのものが `誤 ⇒ 正` の並記である。48-IQ で並記を
    証拠から外した理由は「**向きが共起でしか決められない**」だった
    （`映します。⇒ 移します。` の右が左に返された）が、**⇒ の左右で
    向きは決まる**（48-AY「対比を書いたのは開発としてです。直します」・
    48-HW「⇒ は正解つきの的」。左が誤・右が正）。

    やること: 行を最初の `⇒` で割り、両側をトークンに割って、
    **頭と尻の共通トークンを落とす**。残った真ん中どうしの**読みが
    同じ**（janome の読み・辞書の読み・かなはそのまま、の集合が交わる）
    なら、左の範囲を右の表記に置き換える候補を返す。

    門（すべて満たすときだけ）:
      ・真ん中が両側とも1〜6文字で、どちらかに漢字がある
      ・**どのトークンも読みが立っている**（未知語は照合できない）
      ・読みの集合が交わる（濁点違い・脱字は同音ではない——
        `再退化 ⇒ 最大化` は タ/ダ で交わらず、別の道の仕事）
    置き換えは全置換共通の最終検査（decisions.blocks ほか）を通る。

    戻り値: [(開始, 終了, 直し先, カテゴリ), ...]（⇒ の左側の位置）
    """
    p = line.find('⇒')
    if p <= 0 or p >= len(line) - 1 or tokenize_fn is None:
        return []
    left, right = line[:p], line[p + 1:]

    def _toks(text, base):
        out = []
        pos = 0
        try:
            tt = list(tokenize_fn(text))
        except Exception:
            return None
        for t in tt:
            surf = t[0] or ''
            if not surf.strip():
                continue
            try:
                s0, e0 = int(t[3]), int(t[4])
            except Exception:
                s0, e0 = pos, pos + len(surf)
            pos = e0
            out.append((surf, t[2] or '', bool(t[5]) if len(t) > 5 else False,
                        base + s0, base + e0))
        return out

    tl = _toks(left, 0)
    tr = _toks(right, p + 1)
    if not tl or not tr:
        return []
    i = 0
    while i < min(len(tl), len(tr)) and tl[i][0] == tr[i][0]:
        i += 1
    j = 0
    while j < min(len(tl), len(tr)) - i \
            and tl[len(tl) - 1 - j][0] == tr[len(tr) - 1 - j][0]:
        j += 1
    mid_l = tl[i:len(tl) - j]
    mid_r = tr[i:len(tr) - j]
    if not mid_l or not mid_r:
        return []
    text_l = ''.join(s for s, _r, _k, _a, _b in mid_l)
    text_r = ''.join(s for s, _r, _k, _a, _b in mid_r)
    if text_l == text_r or not (1 <= len(text_l) <= 6) \
            or not (1 <= len(text_r) <= 6):
        return []
    if not any(is_kanji(c) for c in text_l + text_r):
        return []

    def _readings(mid):
        try:
            from morphology import katakana_to_hiragana as _k2h
        except Exception:
            _k2h = lambda s: s
        sets = []
        for surf, rd, known, _a, _b in mid:
            got = set()
            if known and rd:
                got.add(_k2h(rd))
            if all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in surf):
                got.add(surf)
            if dict_index is not None:
                try:
                    for r in dict_index.readings_for_surface(surf):
                        got.add(_k2h(r))
                except Exception:
                    pass
            if not got:
                return None             # 読みが立たない＝照合できない
            sets.append(got)
        out = {''}
        for got in sets:
            out = {a + b for a in out for b in got}
            if len(out) > 64:
                return None
        return out

    rl = _readings(mid_l)
    rr = _readings(mid_r)
    if not rl or not rr or not (rl & rr):
        return []
    # 48-VZ: 補正が生んだ矢印の左右を、新しい利用者の指定と解釈しない。
    # 最初の本文にも同じ同音の対応があった場合だけ、再解析後にも使う。
    source = _CORRECTION_SOURCE.get()
    if _source_check and source is not None and source != line:
        original_pairs = _arrow_respell(source, tokenize_fn, dict_index,
                                        _source_check=False)
        if not any(''.join(source[a:b].split()) == text_l and replacement == text_r
                   for a, b, replacement, _ in original_pairs):
            return []
    start = mid_l[0][3]
    end = mid_l[-1][4]
    _trace('並記', f'{text_l!r} ⇒ {text_r!r} は読みが同じ'
                   f'（{sorted(rl & rr)[0]!r}）。左を右に合わせる（設計34）')
    return [(start, end, text_r, 'その他')]


def _kana_backed(reading, store):
    """
    その読みが、**この人の語として立つか**（設計38・39 の共通の物差し）。

    判定の本体は `vocabulary.entry_is_solid` **1本**（項目48-QG・48-QS）。
    `count >= 2` と書き下さない——巡4 でメモリ上の `count` の写しを
    落としたとき、**ここだけ黙って古い意味のまま残る**（48-GN）。
    """
    try:
        from vocabulary import entry_is_solid as _solid
        return any(_solid(e) for e in store.lookup(reading))
    except Exception:
        return False


def _kana_run_backed(fixed, store):
    """
    直したかな連続が「語」または「語＋**助詞**の尾」として立つか。

    連続には助詞が含まれる（`こんょに` の に）。丸ごとの読みだけを
    見ると、挿入の正解 `こんきょ＋に` が落ちて、たまたま丸ごと語に
    なる `こんなに` が独り勝ちした（readcheck で実測）。
    尾は**助詞の字だけ**——機能語判定（_is_all_functional）まで
    緩めると `でんしゃ＋し` が通って順序違いの型を壊した（実測）。

    **設計38（場違いな小書き）と設計39（場違いな濁点）で同じもの**
    （同じ意味の物差しを2つ作らない）。
    """
    if _kana_backed(fixed, store):
        return True
    tail_ok = 'のをにがはでとへもやかね'
    for cut in range(len(fixed) - 1, 1, -1):
        if all(c in tail_ok for c in fixed[cut:]) \
                and _kana_backed(fixed[:cut], store):
            return True
    return False


def _misplaced_small_kana_fixes(line, store):
    """
    **設計38: 場違いな小書きを、隣のキーの通常字に置き換えて直す**
    （項目48-JN・2026-08-25。うにさんの骨格「最初に文が異様なのかどうかを
    正しく判定する→平仮名に開く→隣接キーや脱字などチェックして、
    本来の入力を探る」の、いちばん形の良い実例）。

    ゃ・ゅ・ょ は**い段の字の直後にしか立てない**。それ以外の場所
    （行頭・小書きの直後・い段でない字の直後）に居る小書きは、
    日本語として不可能＝**異様の判定が構造だけで立つ**。

    隣接キーの総当たり（`tools_local/probe_adjacent_matrix.py`・
    初期語彙225語×7,962崩し）で見つけた「別のもの」の最大族がこれ:

        もじ**ゃゅ**うりょく → もじゅうりょく（に を削って誤魔化す）
        へ**ゃ**かん         → へんか（ん ごと失う）

    正しい直しは削除ではなく**置換**——場違いを作っている字
    （小書きそのもの、または前の字）を**隣のキー**の通常字に戻す:

        ゃ→に（隣）で もじにゅうりょく（文字入力）✓
        ゃ→ん（隣）で へんかん（変換）✓

    受け入れは**ただ1つのときだけ**（直した連続が、使用実績のある
    読みにそのまま一致する候補が1つだけなら採る。2つ以上並んだら
    決めない）。正しい文には場違いな小書きが存在しないので、
    誤爆の面はもともと無い（fpcheck で確かめる）。

    戻り値: [(開始, 終了, 直したかな, カテゴリ), ...]（かな連続ごと）
    """
    try:
        from kana_layout import nearby_candidates
    except Exception:
        return []
    small = 'ゃゅょ'
    idan = set('きしちにひみりぎじぢびぴ')

    def _runs():
        i, n = 0, len(line)
        while i < n:
            if is_hiragana(line[i]):
                j = i
                while j < n and is_hiragana(line[j]):
                    j += 1
                yield i, j
                i = j
            else:
                i += 1

    def _backed(reading):
        return _kana_backed(reading, store)

    def _backed_run(fixed):
        return _kana_run_backed(fixed, store)

    out = []
    for rs, re_ in _runs():
        run = line[rs:re_]
        bad = [k for k, ch in enumerate(run)
               if ch in small
               and (k == 0 or run[k - 1] in small
                    or run[k - 1] not in idan)]
        if len(bad) != 1:
            continue                    # 2つ以上壊れた形は今回は見ない
        k = bad[0]
        cands = set()
        # (a) 場違いな小書きそのものを、隣のキーの通常字へ
        for nb, _d in nearby_candidates(run[k], max_dist=1.05,
                                        include_phonetic=False):
            if nb != run[k] and nb not in small:
                fixed = run[:k] + nb + run[k + 1:]
                if _backed(fixed):
                    cands.add(fixed)
        # (b) 前の字を、い段の隣のキーへ（に→ゃ の化けで ゃゅ が並んだ形）
        if k > 0:
            for nb, _d in nearby_candidates(run[k - 1], max_dist=1.05,
                                            include_phonetic=False):
                if nb != run[k - 1] and nb in idan:
                    fixed = run[:k - 1] + nb + run[k:]
                    if _backed(fixed):
                        cands.add(fixed)
        # (c) **脱字**——間のい段の字が落ちて小書きが取り残された形
        # （きょう[ち]ょう）。うにさんの骨格「隣接キーや**脱字など**」の
        # 脱字の側。挿入で語に届く形も同じ土俵に載せる。**候補が2つ以上
        # 並んだら身を引き、既存の脱字の道（順位づけを持つ）に任せる**
        # ——最初は (a)(b) だけで出したら、readcheck の脱字の型を
        # 3件横取りして壊した（きょうょう → きょうゆう。正解は
        # 挿入の きょうちょう）。実測して足した門。
        for ins in idan:
            fixed = run[:k] + ins + run[k:]
            if _backed_run(fixed):
                cands.add(fixed)
        # (d) **順序の入れ替わり**（しゃ→ゃし の型）も同じ土俵に載せる。
        # これが載っていないと、挿入の候補（でんしゃ＋し）が独り勝ちして
        # 順序違いの型を壊す（readcheck で実測）。衝突すれば「ただ1つ」で
        # 身を引き、既存の順序違いの道（順位づけを持つ）が受け持つ。
        for j in (k - 1, k + 1):
            if 0 <= j < len(run):
                sw = list(run)
                sw[k], sw[j] = sw[j], sw[k]
                fixed = ''.join(sw)
                if fixed != run and _backed_run(fixed):
                    cands.add(fixed)
        if len(cands) == 1:
            fixed = cands.pop()
            _trace('かな連続', f'{run!r} → 場違いな小書き（{run[k]!r}）を'
                               f'隣のキーで戻すと {fixed!r}（設計38）')
            out.append((rs, re_, fixed, 'かな入力'))
    return out


#: 大書き → 小書き（Shift の押し忘れ。項目48-KV）
_LARGE_TO_SMALL = {'や': 'ゃ', 'ゆ': 'ゅ', 'よ': 'ょ'}

#: 拗音の前に立てる字（い段）。項目48-KV
_KV_I_DAN = frozenset('いきぎしじちぢにひびぴみり')

#: 「う挿入」（長音の脱字）を許す場所（お段・ょ・ゅ の直後）。項目48-KV
_KV_U_AFTER = frozenset('おこごそぞとどのほぼぽもよろょゅ')

#: 拗音の小書き（項目48-OP）。長音 う の位置ずれは、この直後どうしで起きる
_KV_SMALL_YOON = frozenset('ゃゅょ')


def _kv_move_u_variants(base):
    """
    **長音「う」の位置ずれ**（項目48-OP・2026-09-03）。

    かな入力で う キーを打つ拍が1つずれた形。うにさんの一覧2行目
    `にゆりょうくみす ⇒ にゅうりょくみす`（本来は 入力ミス）:

        にゅ|りょう  →  にゅう|りょ     （う を1拍前へ）
        にゅう|りょ  →  にゅ|りょう     （後ろへ。**両向き**）

    **う挿入（手(ii)）では届かない。** にゅりょうくみす に う を
    足すと にゅう＋りょう＋く＋みす で敷き詰まってしまい、
    そこから先の変換が立たない（実測）。打ったのは う ではなく
    **う の場所**が1拍ずれた形なので、**足すのではなく移す**。

    動かす う は**拗音の小書き（ゃゅょ）の直後**に在り、
    移す先も**拗音の小書きの直後**（門）。頭と尾は触らない。

    戻り値: {移したあとの読み: 移したあとの う の位置}
    """
    out = {}
    yoon = [i for i, c in enumerate(base) if c in _KV_SMALL_YOON]
    if len(yoon) < 2:
        return out
    for i in yoon:
        # 動かす う は、拗音の小書きの**直後**に在るものだけ
        if i + 1 >= len(base) or base[i + 1] != 'う':
            continue
        rest = base[:i + 1] + base[i + 2:]       # う を抜いた形
        for j in yoon:
            if j == i:
                continue
            # 抜いたぶん、う より右に在った拗音は1つ左へ詰まる
            k = j + 1 if j < i else j
            out[rest[:k] + 'う' + rest[k:]] = k
    return out


def _kv_finish(run, base, u_pos, store, dict_index):
    """
    **48-KV の⑤（漢字変換が既定）と、う の位置の門**（項目48-OP で
    ここへ括り出した——手(ii)（う挿入）と手(iii)（う の位置ずれ）が
    **同じ⑤と同じ門**を通るようにするため。学び22——片方だけに
    置くと、そちらを迂回する）。

    ⑤ **漢字変換が既定**（うにさんの指定・2026-08-29・2度目の正し）:

      「変換の確信が立たないときは かな止まり、ではありません。
        **かなのまま打ちたいことの確信がなければ漢字変換する**、
        です。例えばF6キーが変換中に押されたら、それは平仮名の
        意図が感じられます。これは一例です」

    かなのまま残るのは、機能語・助詞の部分と、錨（語彙 count>=2）が
    無くて敷き詰めの切れ目が立たないときだけ（あたえき を 仇駅 に
    しない門）。F6 のような「平仮名の意図」の証拠は、アプリ側から
    渡す口ができたらここで見る。

    戻り値: 直した表記（決まらなければ None）
    """
    conv = _convert_odd_kana_run(base, store, dict_index)
    # **変換の道はもう1本ある**（項目48-MG・2026-08-31）。
    # うにさんの画面「**しゅうりょじ　が補正されない**」。
    #
    #     しゅうりょじ  ①異様（48-KS が立つ）
    #                   ③う挿入 → しゅうりょうじ（敷き詰まる）
    #                   ⑤変換 …… `_convert_odd_kana_run` は
    #                      **語彙の実績2以上の4字語**を先頭に
    #                      要求する。初期状態に `しゅうりょう` は
    #                      無いので None ＝ここで落ちていた
    #
    # ところが **48-KX'（語幹（実績）＋接尾）は同じ連続を
    # `終了時` に組めている**（`しゅうりょうじ` を直に渡せば
    # 出る・実測）。**変換の道が2本あるのに、う挿入の門は1本しか
    # 聞いていなかった**（学び22 の型——片方だけに置くと、
    # そちらを迂回して素通りする）。
    #
    # **門は緩めない。** 48-KX' の答えにも「語幹の終わり」を
    # 返させて、**う が語幹の内側に落ちること**を同じように問う
    # （`しゅうりょ|う|じ` の う は 終了＝しゅうりょう の内側）。
    if conv is None and u_pos is not None:
        _cx = _compose_kana_run_fixes(base, store, dict_index,
                                      with_head=True)
        if (len(_cx) == 1 and _cx[0][0] == 0
                and _cx[0][1] == len(base) and _cx[0][2] != base):
            conv = (_cx[0][2], _cx[0][4])
    # **う を動かした形は、変換まで立ち、かつ う が先頭の語の内側に
    # 落ちるときだけ採る**——かな止まりで出すと `たんほの →
    # たんほうの` を、内側の門なしだと `しゅうりょじ → 囚虜ウジ`
    # （しゅうりょ|うじ＝う が区切りの外）を作った（実測）。
    # 手(iii)（位置ずれ）にも**同じ門**を掛ける（48-OP）。
    if u_pos is not None:
        if not conv:
            return None
        if u_pos >= conv[1]:
            return None
    fix = conv[0] if conv else (base if base != run else None)
    if not fix or fix == run:
        return None
    return fix


def _has_trusted_proper_noun(run, store, dict_index):
    """
    その並びに、**信用してよい固有名詞**が居るか（項目48-RN・
    2026-09-05・うにさんの報告「以前も言ったが、**地名と人名判定の
    優先度を下げなければいけない**」）。

    48-OR は①（異様か判定する）で「解析の言う固有名詞を特別扱い
    しない」と決めた。だが**同じ判定を、止まる門が見ていなかった**
    ——「固有名詞が混じっていたら判定しない」型の門が、
    **信用できない札**（`右田`＝地名・`ブル`＝人名。どちらも
    カタカナ語や漢字列を割った跡）でも降りていた。
    48-OR が①で開けたはずの道が、ここで塞がっていた（学び22）。

    ★★ **判定は借りるだけ。新しい判定は作らない**（48-GN）——
    `oddness._proper_noun_downgradable`（そもそも落としてよい形か）と
    `oddness._proper_noun_is_trusted`（信用してよいか）の2本を、
    ①が見ているのと**同じ材料**で呼ぶ。

    **守る門はこれを使わない**——48-JL（登録した姓を守る）・
    48-CS（`_is_whole_proper_noun`）・地名の接尾は、
    「本人の語・登録した姓を守る」持ち場なので今までどおり。
    """
    if not any('固有名詞' in ((t[1] or '') if len(t) > 1 else '')
               for t in run):
        return False            # そもそも固有名詞が居ない
    if dict_index is None:
        # **世の読みが引けないときは判定できない**——`_proper_noun_is_trusted`
        # の4つの出どころのうち2つ（カタカナの扱い・世の読み）が
        # 効かないので、当て推量かどうかを言えない。
        # ★★ **分からないときは今までどおり**（止める側＝守る側）。
        # 実機は必ず渡す（`correct_line` の引数）ので、これで落ちるのは
        # 作り物の試験だけ
        return True
    try:
        import oddness as _odd
    except Exception:
        return True             # 分からないときは今までどおり（止める側）
    for _i, t in enumerate(run):
        if '固有名詞' not in ((t[1] or '') if len(t) > 1 else ''):
            continue
        try:
            if not _odd._proper_noun_downgradable(run, _i):
                return True     # 落としてよい形ですらない＝守る
            if _odd._proper_noun_is_trusted(
                    (t[0], t[1], (t[2] if len(t) > 2 else '')),
                    store, dict_index):
                return True
        except Exception:
            return True
    return False


def _known_head_kanji(head, store):
    """
    **既知の頭を漢字に決める**（項目48-RK）。無理なら None。

    ★★ 順番は「本人の語 → 世の中の語」。本人の語彙に**立った**表記が
    在るならそれ（`かんい` は種の語彙に `簡易` が在る）。無ければ
    同梱の費用表の表記を **段（`kango_tier`）で絞り**、
    **(段, 費用) の順で先頭を採る**（★★ CLAUDE.md「候補が複数でも
    優先度の高い1つに決める」）——`かんい` は 簡易(段2) が
    官位・冠位(段3) に勝つ。
    """
    try:
        from vocabulary import entry_is_solid as _solid
        for e in store.lookup(head):
            sf = e.get('surface') or ''
            if _solid(e) and len(sf) == 2 and all(is_kanji(c) for c in sf):
                return sf
    except Exception:
        pass
    best = None
    for sf in (table_surfaces_for_reading(head) or ()):
        if len(sf) != 2 or not all(is_kanji(c) for c in sf):
            continue
        t = _kango_tier_of(sf)
        if t > 2:
            continue                # 段3＝専門・文語。頭には採らない
        c = _table_cost(sf)
        key = (t, c if c is not None else 10 ** 9, sf)
        if best is None or key < best[0]:
            best = (key, sf)
    return best[1] if best else None


_QUOTE_OPEN = '「『“"‘'
_QUOTE_CLOSE = '」』”"’'


def _fix_known_head_compound(run, store, tokenize_fn, dict_index,
                             find_readings=None, max_dist=1.6,
                             before='', after=''):
    """
    **既知の頭で割り、残りを直し、2字漢語＋2字漢語に決める**
    （項目48-RK・2026-09-05・うにさんの指定）:

        「`かんいりゅうりょく`——`かんい` は候補の先頭で 簡易、
          `りゅうりょく` は打ち間違いで 入力 かもと出る。
          **ここまで揃うなら 簡易入力 に導いてよいはず**」

    F2 の単位は 48-RI で `かんい｜りゅうりょく` に切れているのに、
    **エンジンはその切り方を知らなかった**（48-GN の食い違い）。
    芯・窓は「連続まるごと」と助詞での区切り（48-PI）しか試さない。

        かんいりゅうりょく → **簡易入力**

    ### 門（**熟語＋熟語の形だけ**に絞る）

        H  既知の読み・**3字以上**（本人の語彙で立つ／世の読み）
           ——48-RI と同じ形。**R まるごとが語なら割らない**
        T  **4字以上**・頭が小書きでない
        H の漢字  `_known_head_kanji`（本人の語 → 段と費用）
        T の直し  **既存のかな連続の道**——`find_readings` で
                  **1手以内**の読みにし、`_convert_odd_kana_run` で漢字
        両方      **2字の漢語で、段 ≤ 2**（`kango_tier` が知っている）
        複合      `oddness.is_odd_run(H+T)` が **[]**

    ★★ **非対称**（頭が既知のときだけ）。逆向き（T が既知で H を
    直す）は作らない——`きょじえ` 単独は `きょぞう` に直るので
    `きょじえかくらん → 巨像攪乱` を作ってしまう。

    戻り値: 直した表記か None。
    """
    if not run or len(run) < 7:
        return None
    # ★★ **かぎ括弧にちょうど囲まれた読みは「引用」**——触らない
    # （項目48-RK・実機メモで測って足した門）。うにさんのメモは
    # **誤字の話を書いたメモ**なので、読みを括弧に入れて引く形が出る:
    #
    #     「やがいぶんしょう」という誤入力  → **「野外文章」という誤入力**
    #     「かんいりゅうりょく」を確認しました → **「簡易入力」を…**
    #
    # 直すと**文の意味が壊れる**（「誤入力」の例が正しい形になる）。
    # 48-LS「読みの並記は書きたい形」と同じ考え方——
    # **括弧はかなで書きたい意図の証拠**。
    if before in _QUOTE_OPEN and after in _QUOTE_CLOSE and before:
        return None
    if find_readings is None:
        # **同じ1本を使う**（48-GN）——呼び手が持っていない道
        # （`_reopen_odd_chunk`）からも同じ手で探す
        try:
            from vocabulary import find_known_readings_flex as find_readings
        except Exception:
            return None
    if not all(is_hiragana(c) for c in run):
        return None
    try:
        import kango_tier as _kt
        import oddness as _odd
    except Exception:
        return None
    # **まるごとが語なら割らない**
    try:
        if store.has_reading(run):
            return None
    except Exception:
        pass
    for hl in range(min(len(run) - 4, 6), 2, -1):
        head, tail = run[:hl], run[hl:]
        if tail[0] in _SMALL_KANA_HEADS:
            continue
        known_head = False
        try:
            known_head = bool(store.has_reading(head))
        except Exception:
            known_head = False
        if not known_head and dict_index is not None:
            try:
                known_head = bool(dict_index.is_world_reading(head))
            except Exception:
                known_head = False
        if not known_head:
            continue
        hk = _known_head_kanji(head, store)
        if not hk or _kt.tier(hk) > 2:
            continue
        # --- T を既存の道で直す（1手以内・同じ上限）---
        best_t = None
        try:
            cands = list(find_readings(tail, store, max_dist))
        except Exception:
            cands = []
        for rd, dist, edits in cands[:8]:
            if edits > 1 or not rd:
                continue
            # ★★ **字を落とす直しは採らない**（測って足した門・48-RK）。
            # 長さが変わる直し＝挿入か脱落で、**残りの一部を捨てて**
            # 熟語に見せかけることになる。自分で作った反例で出た:
            #     かんいけいさんき → **簡易計算**（`き` を落とした）
            #     ほぞんとひょうじ → **保存表示**（助詞 `と` を飲んだ）
            # 的（`りゅうりょく → にゅうりょく`・
            # `にゅうりゅく → にゅうりょく`）は**どちらも同じ長さ**。
            if len(rd) != len(tail):
                continue
            try:
                got = _convert_odd_kana_run(rd, store, dict_index)
            except Exception:
                got = None
            if not got:
                continue
            tk = got[0] if isinstance(got, tuple) else got
            if not tk or len(tk) != 2 or not all(is_kanji(c) for c in tk):
                continue
            if _kt.tier(tk) > 2:
                continue
            best_t = tk
            break
        if not best_t:
            continue
        whole = hk + best_t
        try:
            if _odd.is_odd_run(whole, tokenize_fn, store=store,
                               dict_index=dict_index):
                continue        # できた形そのものが異様なら採らない
        except Exception:
            continue
        _trace('かな連続',
               f'{run!r} → {whole!r}（既知の頭 {head!r}＝{hk!r} で割り、'
               f'残り {tail!r} を直して {best_t!r}・項目48-RK）')
        return whole
    return None


def _kana_run_is_odd_by_grammar(run, dict_index, store):
    """
    **そのかな連続に①が立っているか**（項目48-RW・2026-09-05）。

    かな連続の①は `oddness.is_odd_run`（漢字・カタカナの対）ではなく
    **48-KS の品詞文法**（`pos_grammar.odd_kana_spans`）で立つ——画面の
    紫（`_odd_spans_for_line`）と同じ判定を借りる（48-GN。ここで別の
    判定を書かない）。連続をまるごと覆う印が在れば True。
    """
    if not run or dict_index is None:
        return False
    if os.environ.get('CN_POS_ODD') == '0':
        return False
    try:
        import pos_grammar as _pg
        for a, b in _pg.odd_kana_spans(run, dict_index, store):
            if a <= 0 and b >= len(run):
                return True
    except Exception:
        return False
    return False


def _convert_fixed_kana_run(text, store, dict_index):
    """
    **A の道で直した読み（かな→かな）を、正しく打ったかなと同じ変換の道に
    通す**（項目48-RW'・2026-09-05）。

        おくゆくこてい → おくゆきこてい（読みは直った）   → **奥行固定**
        かすくにん   → かくにん                           → **確認**

    正しく打った `おくゆきこてい`・`かくにん` は 48-LD（語＋語で組む）・
    48-MI（かなのまま残った漢語を変換）で漢字になるのに、**打ち間違えて
    直された読みはかなのまま**だった——変換の道は**元の行**のかな連続しか
    見ないから。同じ2つの関数を、直した読みだけに掛ける（判定は借りる。
    新しい判定は作らない）。打ち間違いの手（48-KV・う挿入…）は掛けない
    ——直しに直しを重ねると連鎖する。
    戻り値: 変換した字。変わらなければ None。
    """
    if (not text or store is None or dict_index is None
            or not all(is_hiragana(c) or c == 'ー' for c in text)):
        return None
    # ★★ **直した読みは、正しく打った読みより証拠が弱い**——測って絞った
    # （2026-09-05・readcheck）。最初は 48-KX'（語幹＋接尾）と 48-MI を
    # そのまま掛けたら、育ちで `きょううせい → きょうせい → **今日性**`、
    # 初期で `ちゅうし → 中止`・`きゅうけい → 休憩` のように**同音の顔を
    # 決めてしまう形が 60 件**出た（材料の表記と違う顔＝当て推量）。
    # 掛けるのは 48-MI だけ、しかも**その読みの漢字の顔がただ1つ**か、
    # **本人の語彙にその表記が solid で在る**ときだけ。語幹＋接尾は掛けない
    fixes = []
    try:
        got = _kango_kana_fixes(text, store, dict_index) or []
    except Exception:
        got = []
    for f in got:
        if len(f) < 3 or f[0] >= f[1]:
            continue
        seg = text[f[0]:f[1]]
        ok = False
        try:
            if any(e.get('surface') == f[2] and e.get('count', 0) >= 2
                   for e in store.lookup(seg)):
                ok = True
            elif len(_kanji_faces_for_reading(seg, store, dict_index)) == 1:
                ok = True
        except Exception:
            ok = False
        if not ok:
            continue
        if any(not (f[1] <= s0 or f[0] >= e0) for s0, e0, _x in fixes):
            continue
        fixes.append((f[0], f[1], f[2]))
    if not fixes:
        # **そのまま語＋語で組める**（48-LD の「そのまま」の枝と同じ判定
        # `_two_word_faces`——`おくゆきこてい → 奥行固定`）。門も同じ:
        # 連なりそのものが語彙の語なら 48-MI の持ち場・機能語の並びなら
        # 触らない・同じ字の連続（連打の跡）は触らない
        try:
            if any(e.get('count', 0) >= 2 for e in store.lookup(text)):
                return None
            if _is_functional_strict(text):
                return None
        except Exception:
            return None
        if any(text[x] == text[x + 1] for x in range(len(text) - 1)):
            return None
        faces = _two_word_faces(text, 2, store)
        if len(faces) == 1:
            fx = next(iter(faces))
            return fx if fx != text else None
        return None
    chars = list(text)
    for s, e, fx in sorted(fixes, reverse=True):
        chars[s:e] = list(fx)
    out = ''.join(chars)
    return out if out != text else None


def _hand_boundaries_ok(tok_info, alts_per_tok, rd, fixed, bounds_in_fixed):
    """
    **手を当てていない「読みの立つ語」の読みの中に、組の境目を置かない**
    （項目48-RV''・2026-09-05・うにさんの指定「品詞の判定やつながりを
    重要視してください」）。

    `背中セク` を `はいなかせく` に開き、手で `はいなかよく` にして
    `ハイ｜仲良く` に組む——境目 2 は `背中` の読み `はいなか` の**中**。
    手は断片 `セク` に当てたのに、組は手を当てていない `背中` の読みを
    切り直している。これは当て推量（48-ND「書かれ方は変えない」を
    **読みの切れ目**にも当てる）。

    守るのは**読みの立つ語**だけ——48-OR で格下げした固有名詞（`田部井`・
    `右田`）は守らない（`たぶ｜いどう`・`みぎ｜だぶるくりっく` は IME の
    切り方が間違っていた的）。**手が触った語**も守らない（`解析課背中セク`
    の `背中` は手で `が`・`ながく` に変わる側）。境目が手の中に落ちる
    ときは意見なし。

    tok_info:        [(表記, 読みが立つか), ...]（塊のトークン順・格下げ後）
    alts_per_tok:    トークンごとの読みの候補（`rd` はこの積のどれか）
    rd / fixed:      開いた読み／手を当てた読み
    bounds_in_fixed: 組の境目（`fixed` の上の位置）の並び
    戻り値: True＝置いてよい（または判断できない＝意見なし）
    """
    if (not tok_info or not alts_per_tok
            or len(tok_info) != len(alts_per_tok) or not bounds_in_fixed):
        return True

    # rd をトークンに沿って割る。読みの候補で当たればそれを、当たらない
    # **漢字の語**は「残りのトークンが揃う長さ」を取る（開いた読みには
    # `kanji_guess` の1字ずつの音訓〔はい＋なか〕から来たものが在り、
    # トークンの候補（せなか）とは揃わない——**後ろの断片の読み（せく）
    # は確定しているので、そこから逆算できる**）
    n_tok = len(alts_per_tok)

    def _align(k, pos):
        if k == n_tok:
            return [] if pos == len(rd) else None
        alts = alts_per_tok[k]
        for a in alts:
            if a and rd.startswith(a, pos):
                rest = _align(k + 1, pos + len(a))
                if rest is not None:
                    return [(pos, pos + len(a))] + rest
        sf = tok_info[k][0]
        if sf and any(is_kanji(c) for c in sf):
            for ln in range(1, len(rd) - pos + 1):
                rest = _align(k + 1, pos + ln)
                if rest is not None:
                    return [(pos, pos + ln)] + rest
        return None

    spans = _align(0, 0)
    if spans is None:
        return True                     # 揃え方が分からない＝意見なし
    try:
        import difflib as _dl
        ops = _dl.SequenceMatcher(None, rd, fixed,
                                  autojunk=False).get_opcodes()
    except Exception:
        return True
    touched = set()
    for tag, i1, i2, _j1, _j2 in ops:
        if tag != 'equal':
            touched.update(range(i1, i2))
    guarded = [(a, b) for (sf, known), (a, b) in zip(tok_info, spans)
               if known and b - a >= 2
               and not any(a <= p < b for p in touched)]
    if not guarded:
        return True
    for hl in bounds_in_fixed:
        q = None
        for tag, i1, i2, j1, j2 in ops:
            if j1 <= hl <= j2:
                if tag == 'equal':
                    q = i1 + (hl - j1)
                elif hl == j1:
                    q = i1
                elif hl == j2:
                    q = i2
                break
        if q is None:
            continue                    # 境目が手の中＝意見なし
        for a, b in guarded:
            if a < q < b:
                return False
    return True


def _born_positions(before, after):
    """
    **手が変えた位置**（`after` の中の添字の集合・項目48-RQ・2026-09-05）。

        かいせきかせなかせく → かいせきがながく   {4, 6}（2つの が）
        りゅうりょく → にゅうりょく               {0}

    手の種類を問わず、**2つの読みの差分**から採る（どの手が生んだかは
    問わない——「その位置の字は打たれたままではない」ことだけが要る）。
    同じ読みなら空。
    """
    if not before or not after or before == after:
        return set()
    try:
        import difflib as _dl
        out = set()
        for tag, _i1, _i2, j1, j2 in _dl.SequenceMatcher(
                None, before, after, autojunk=False).get_opcodes():
            if tag != 'equal':
                out.update(range(j1, j2))
        return out
    except Exception:
        return set()


def _word_born_particle_fix(run, store, dict_index, tokenize_fn):
    """
    **印のキーの隣を叩いた形を巻き戻し、語＋（手が生んだ1字格助詞）＋語
    に組めるなら、それを採る**（項目48-RQ・2026-09-05・うにさんの指定
    「背中セクよりも先に、せ が ゛ の隣接打ち間違いを疑う。解析課の か が
    が に繋がれば接続詞として自然で、後ろの文とも繋がる」）。

        かいせきかせなかせく  →  かいせき[か゛]な[か゛]く
                              →  かいせきがながく  →  解析が長く

    A/B の道（かな連続）の**最後の手**——48-PI・48-RK と同じ構え
    （この連続で何も直らなかったときだけ）。D の道（異様の塊）は
    `_reopen_odd_chunk` → `_convert_odd_kana_run(born=…)` で**同じ門**を
    通る（48-GN——判定は `_convert_odd_kana_run` の中の1か所）。

    仮説は `_mark_slip_repairs`（48-FX／48-OM）を借りる。**同じ誤りの
    繰り返し（×2）も1つの仮説**として作る（1回のものを先に・費用順）。
    受け入れは `_convert_odd_kana_run(only_born_particle=True)`——
    語＋助詞＋語の枝**だけ**を開く（丸ごと1語・語＋語の枝は、この道では
    開かない。そちらは `rebuild_window_core` の持ち場）。
    """
    if not run or len(run) < 6 or store is None or dict_index is None:
        return None
    try:
        if _chunk_is_intact(run, tokenize_fn):
            return None                     # 48-KI の入口
    except Exception:
        pass
    variants = []
    seen = {run}
    try:
        for v1 in _mark_slip_repairs(run):
            if v1 not in seen:
                seen.add(v1)
                variants.append(v1)
        for v1 in list(variants):
            for v2 in _mark_slip_repairs(v1):
                if v2 not in seen:
                    seen.add(v2)
                    variants.append(v2)
    except Exception:
        return None
    for v in variants:
        born = _born_positions(run, v)
        if not born:
            continue
        try:
            conv = _convert_odd_kana_run(
                v, store, dict_index, born=born,
                tokenize_fn=tokenize_fn, only_born_particle=True)
        except Exception:
            conv = None
        if conv and conv[0] and conv[0] != run:
            _rep = '・同じ誤りの繰り返し' if len(born) > 1 else ''
            _trace('かな連続', f'{run!r} → {v!r}（印のキーの隣{_rep}）'
                               f'に開き、語＋手が生んだ助詞＋語 で '
                               f'{conv[0]!r}（項目48-RQ）')
            return conv[0]
    return None


def _convert_odd_kana_run(text, store, dict_index, strict_anchor=False,
                          index_anchor=False,
                          vocab_only=False, short_head=False,
                          born=None, keep_head=None, tokenize_fn=None,
                          only_born_particle=False):
    """
    **異様と判定した かな連続を、漢字に変換する**（項目48-KV・⑤）。

    うにさんの指定（2026-08-29・2度目の正し）:

        「変換の確信が立たないときは かな止まり、ではありません。
          **かなのまま打ちたいことの確信がなければ漢字変換する**、です。
          例えばF6キーが変換中に押されたら、それは平仮名の意図が
          感じられます。これは一例です」

    **変換が既定。** かなのまま残るのは:
      ・機能語・助詞の部分（文法がかなで書く場所）
      ・敷き詰めが立たないとき（読みの切れ目が分からないものを
        当て推量で漢字にはしない——あたえき を 仇駅 にしない門）
      ・（将来）アプリ側から「平仮名の意図」の証拠が渡されたとき
        （F6 など。いまのエンジンにはまだその口が無い）

    敷き詰めの部品と門:
      ・語彙の読み（表記は count 最大のもの。**count>=2 の語が
        1つ以上**——錨。錨が無い並びは変換しない）
      ・辞書の読み（`surfaces_for_reading` の先頭＝一般的な語）
      ・機能語・1字の格助詞（かなのまま出す）

    ### 締めた形（2026-08-29・全行検品で化けを受け止めた）

    最初の形（錨1つ＋敷き詰め）は、**細切れの敷き詰めでも変換して
    しまった**——`すきにん → 好きにん`（正しい直し かくにん を
    先取りして壊す）・`がいしょつする → 害しようつする`・
    `めもちちょう → メモうち帳`・`しゅうりょじ → 囚虜ウジ`（全部
    育ちの実測）。だから:

      ・**中身の区切りは2つまで**（語＋語まで。3つ以上の細切れは
        当て推量）
      ・**先頭の区切りは、語彙 count>=2 の語で、読みが4字以上**
        （にゅうりょく=6字 ○ ／ すき・がい・めも=2字 ×・おわり=3字 ×）
      ・2つ目の区切りは語彙か辞書の表記（ミス）
      ・残りは機能語・1字の格助詞（かなのまま出す）

    `strict_anchor=True` なら、先頭の錨は **実績2以上だけ**
    （2字の漢語の錨〔項目48-MK〕は使わない）。**異様と判定して
    いない連続を変換する道**（48-MI）から呼ぶときに立てる——
    そこは いちばん delicate な場所なので、いちばん厳しい錨で。

    戻り値: (変換した文字列, 先頭の区切りの終わり位置) か None。
    """
    if not text or store is None or dict_index is None:
        return None
    try:
        import pos_grammar as _pg
        _w, _funcs, _p1 = _pg._load_tables()
    except Exception:
        return None
    n = len(text)

    def _tail_kana_ok(i):
        """位置 i から先が機能語・1字の格助詞だけで埋まるか。"""
        ok = [False] * (n + 1)
        multi = [False] * (n + 1)   # 2字以上の機能語を使った道が在るか
        ok[i] = True
        for j in range(i, n):
            if not ok[j]:
                continue
            if text[j] in _p1:
                ok[j + 1] = True
                if multi[j]:
                    multi[j + 1] = True
            for ln in range(2, min(10, n - j) + 1):
                if text[j:j + ln] in _funcs:
                    ok[j + ln] = True
                    multi[j + ln] = True
        if not ok[n]:
            return False
        # **尾が接頭の お で終わる形は無い**（項目48-RV・2026-09-05・
        # `由良仮名 → 有料かお`——`かお` を 助詞か＋接頭お の機能語の並びと
        # 認めていた。お は後ろに語が要る）
        if i < n and text[n - 1] == 'お':
            return False
        # **1字の助詞だけの尾は、2字までは認めない**（同・`有料かや`——
        # か＋や。48-RS「1字の機能語だけの説明は認めない」を尾にも。
        # 1字の尾（`〜に`・`〜を`）はよい。2字以上なら 2字以上の機能語
        # （して・になる・ます…）を1つは使うこと）
        if n - i >= 2 and not multi[n]:
            return False
        return True

    def _content_piece(frag):
        """区切り1つぶんの表記（語彙優先・無ければ辞書の先頭）。

        `vocab_only` なら**辞書の索引には落とさない**（項目48-MZ）。
        """
        entries = [e for e in store.lookup(frag)
                   if e.get('count', 0) >= 1]
        if entries:
            return max(entries, key=lambda e: e.get('count', 0))['surface']
        if vocab_only:
            return None
        try:
            faces = _surfaces_no_band(dict_index, frag)
        except Exception:
            faces = []
        return faces[0] if faces else None

    def _world_katakana_piece(frag):
        """
        **読みをカタカナに綴った形が、世の中で1語か**（項目48-OR(c)・
        2026-09-03。うにさんの一覧17行目 `右田でブルクリック ⇒
        右ダブルクリック`）。

        `だぶるくりっく` は本人の語彙にも同梱の**外来語の表**
        （`loanword`・9,094語）にも無いが、**世の中の語の表**
        （`seed_japanese`）には在る。カタカナは**読みを字で綴った形**
        なので、読みが決まれば表記も1つに決まる——漢字のような
        当てずっぽうが起きない。

        **4字以上**に限る。`うつ → ウツ`・`しせつ → シセツ` のような
        短い形まで通すと、48-ON で壊した `ぶんうつ → 文打つ` の族が
        別の顔で戻る（実測: `ウツ` は世の中で1語）。
        """
        if strict_anchor or vocab_only or not short_head or len(frag) < 4:
            return None
        try:
            from loanword import hiragana_to_katakana as _h2k
            import seed_japanese as _sj
        except Exception:
            return None
        k = _h2k(frag)
        if k == frag or not all(is_katakana(_c) or _c == 'ー' for _c in k):
            return None
        try:
            return k if _sj.is_unit(k) else None
        except Exception:
            return None

    def _strong_piece(frag):
        """**強い2つ目**——語彙の実績2以上か、索引の段で1つに決まる顔
        （項目48-ON）。辞書の先頭には落とさない。
        **世の中のカタカナ語（4字以上）も強い**（項目48-OR(c)）。"""
        try:
            _e2 = [e for e in store.lookup(frag) if e.get('count', 0) >= 2]
        except Exception:
            _e2 = []
        if _e2:
            return max(_e2, key=lambda e: e.get('count', 0))['surface']
        if strict_anchor or vocab_only:
            return None
        return (_index_face(frag, store, dict_index)
                or _world_katakana_piece(frag))

    # 先頭は長い順。**基本は4字以上**。
    #
    # **2〜3字の先頭は「本人の語彙にあるカタカナ語」だけ**
    # （項目48-OQ(b)・2026-09-03）。48-ON（2026-09-02）で 2〜3字を
    # 一律に開けたら `ぶんうつ → 文打つ`（順序違いの読みがそのまま
    # 文＋打つ に割れる）・`外しょつする → 外施設する` が出た——
    # **どちらも漢字の先頭**。漢字の2〜3字は同音の表記が多く、
    # 「実績2以上の錨」＋「強い2つ目」でも当てずっぽうが残る。
    #
    # **カタカナ語は違う**——カタカナは**読みを字で綴った形**なので、
    # 読みが決まれば表記も1つに決まる（タブ＝たぶ に別の表記は無い）。
    # そのうえで「本人の語彙に**実績2以上**」を要る（下の `_short` の
    # 門）ので、当てずっぽうにはならない。うにさんの一覧4行目
    # `田部井号して ⇒ タブ移動して`（たぶ＋いどう＋して）の的。
    for ln1 in range(min(10, n), 1, -1):
        _short = ln1 < 4
        # **2〜3字の先頭を開けるのは、組み立ての受け皿だけ**
        # （項目48-OQ(b')・2026-09-03。**育ちで測って足した門**）。
        #
        # 初期状態のカタカナの語彙は**種の29語**しか無いので、
        # 「実績2以上のカタカナ語」は狭い錨に見えていた。**育ちでは
        # 4,358語**——`コマ`(305)・`バグ`(63)・`ホン`(19)・`ハイ`(24)・
        # `クロ`(22)・`ウソ`(50) まで錨になり、**素のかな連続**を
        # `こまがく → コマがく`・`はいじじょ → ハイ二女`・
        # `うそてん → ウソテン` に組み立てた（育ちの readcheck で
        # **直り −12・化け +9**）。
        #
        # 的（`田部井号して → タブ移動して`）は **元の塊が漢字で
        # 書かれていて、その書かれ方に戻す道**（`_reopen_odd_chunk` の
        # 組み立ての受け皿）から来る。**素のかな連続の変換**
        # （48-KV の⑤・48-MI）は 48-ON で測って壊した側なので、
        # そちらには開けない。
        if _short and not short_head:
            continue
        first = text[:ln1]
        # **変換の錨**（項目48-MK）——実績2以上、または2字の漢語
        entries = [e for e in store.lookup(first)
                   if (e.get('count', 0) >= 2
                       if (strict_anchor or vocab_only)
                       else _is_conversion_anchor(e, first))]
        # **錨は先頭でなくてよい**（項目48-MY・2026-08-31）。
        # 錨が言いたいのは「**この並びは当てずっぽうではない**」で
        # あって、「先頭が実績を持つ」ではない。実績2以上の語が
        # 並びの**どこかに**在れば、証拠は立っている:
        #
        #     ひきつぎ|しりょう
        #     引き継ぎ(実績1) 資料(**実績3**)  → 引き継ぎ資料
        #
        # 先頭が弱いときは (い) の枝だけ・**2つ目は語彙の実績2以上**
        # に限る（`_content_piece` の辞書の索引には落とさない——
        # そこが `こほううに → 広報ウニ` の出どころ・48-MK）。
        # 先頭の表記も**語彙にただ1つ**のときだけ（どの漢字かを
        # 当てずっぽうにしない・設計38〜40）。
        _weak = False
        # **索引の顔を錨にする**（項目48-OJ・2026-09-02）。語彙に無い
        # 基本語（課題・効率・巨大・参考）は、索引の段で1つに決まる
        # ときだけ錨になる。①が立った道だけ（strict_anchor では呼ばない）。
        # **弱い先頭（48-MY）より先に見る**——さんこう は語彙に 参向(実績1)
        # がただ1つ在るので、先に弱い先頭を採ると 参向 が錨になって
        # 参考（段1）に届かなかった（実測: 札ん港になる → 昨年こうになる）。
        # `_index_face` は語彙に**実績2以上**が在れば None を返すので、
        # 本人が使った語は今までどおり語彙が決める
        _idx = False
        if ((not strict_anchor or index_anchor) and not vocab_only
                and not any(e.get('count', 0) >= 2 for e in entries)):
            # 語彙の実績2以上が無いとき（＝count1 の漢語の錨しか無い、
            # または何も無い）は、**段で1つに決まるなら索引の顔**。
            # さんこう は語彙に 参考・鑽孔・参向（全部 count1・漢語）が
            # 並び、48-MK の「表記がただ1つ」の門で止まっていた。
            # 段が付いた今は、門ではなく順位で決める（★★）
            _face = _index_face(first, store, dict_index)
            if _face:
                entries = [{'surface': _face, 'count': 0, 'reading': first}]
                _idx = True
        if not entries and not strict_anchor:
            _cand = [e for e in store.lookup(first)
                     if e.get('count', 0) >= 1]
            if len({e['surface'] for e in _cand}) == 1:
                entries = _cand
                _weak = True
        if not entries:
            continue
        # **短い先頭は実績2以上の錨だけ**（項目48-ON）。48-OA で
        # 「先頭2字まで」を一律に許すと 書く死守・どう餓死 が出た——
        # 2つ目が辞書の先頭で埋まっていたから。ここは錨の実績と、
        # 下の「強い2つ目」の両方を要る
        if _short and not any(e.get('count', 0) >= 2 for e in entries):
            continue
        head = max(entries, key=lambda e: e.get('count', 0))['surface']
        # **短い先頭は「カタカナ語」だけ**（項目48-OQ(b)・2026-09-03）。
        # 漢字の2〜3字を開けると `ぶんうつ → 文打つ`・
        # `外しょつする → 外施設する` を作る（48-ON で実測）。
        # カタカナは読みを字で綴った形なので、表記の当てずっぽうが
        # 起きない。`ー` は語の中に入る（コピー・データ）
        #
        # **漢字の短い先頭は、2つ目が「世の中のカタカナ語（4字以上）」
        # のときだけ**（項目48-OR(c)）——`みぎ|だぶるくりっく`
        # ＝ 右＋ダブルクリック。ここも当てずっぽうにならないのは、
        # **2つ目の表記が読みから1つに決まる**から
        _short_kanji = _short and not all(is_katakana(_c) or _c == 'ー'
                                          for _c in head)
        # **広げた錨（2字の漢語）は、読みの漢字表記がただ1つのときだけ**
        # （項目48-MK）。実績が無い語を錨にするのだから、**どの漢字か**
        # まで当てずっぽうにはできない（`ちゅかい → ちゅうかい` を
        # 戻したあと **注解** を選んだ・readcheck で実測。仲介／注解の
        # どちらかは決められない）。異様判定が立っていないときの門
        # 「ただ1つのときだけ採る」と同じ（設計38〜40・CLAUDE.md）。
        # **弱い先頭（項目48-MY）は、ここは通す**——うにさん自身が
        # その表記で書いた語であり、語彙にただ1つと確かめてある。
        # この門は「実績の**無い**語を錨にする」48-MK のための門で、
        # **漢字だけの表記**を数える（`引き継ぎ` のような送り仮名つきは
        # 数に入らないので、掛けると必ず落ちる）。
        if (not _weak and not _idx
                and not any(e.get('count', 0) >= 2 for e in entries)):
            if len(_kanji_faces_for_reading(first, store,
                                            dict_index)) != 1:
                continue
        # (あ) 残りが機能語・助詞だけ
        # **弱い先頭では通さない**（項目48-MY）——この枝は
        # 先頭だけが証拠なので、その先頭に実績が要る。
        # 索引の錨（実績の無い語）のときは、**尾が名詞に続く機能語で
        # 始まる**こと（項目48-ON。殺人＋こうになる の こう は副詞で、
        # 名詞の直後には来ない。参考＋になる の に は格助詞）
        if _idx and not _noun_tail_start(text[ln1:]):
            continue
        if (not _weak and not _short and not only_born_particle
                and _tail_kana_ok(ln1)):
            out = head + text[ln1:]
            return (out, ln1) if out != text else None
        # **広げた錨（2字の漢語）は、(い) の枝へは渡さない**（項目48-MK）。
        # (い) は2つ目の区切りを**辞書の索引の先頭**で埋めるので、
        # 実績のない語まで錨にすると `こほううに → 広報**ウニ**` が出る
        # （広報＝2字の漢語で錨になり、残りの `うに` を索引が ウニ と
        # 埋めた・readcheck で実測）。**錨が実績2以上のときだけ**。
        if not any(e.get('count', 0) >= 2 for e in entries) and not _weak:
            continue
        # (い) 中身の区切りをもう1つだけ（語＋語）
        # **語＋語**。**語＋1字の格助詞＋語**（項目48-OM・`かいせきがながく`
        # ＝ 解析＋が＋長く）は**測って外した**（2026-09-02）: 2つ目を強い語に
        # 限っても `うづるに行きます → 移るに後期ます`（正しい 行き を
        # 後期 に置き換えた）・`きゃらくたででぃすぷれい → キャラクタで
        # ディスプレイ`（重複打鍵の で を助詞と読んだ）が出た。的の
        # `解析課背中セク → 解析が長く` は 48-ND(b) でも落ちる。
        # `_gap` は 0 と 1（項目48-RQ・2026-09-05・うにさんの指定
        # 「背中セクよりも先に、せ が ゛ の隣接打ち間違いを疑う。解析課の
        # か が が に繋がれば接続詞として自然で、後ろの文とも繋がる」）。
        # **1 は「手が生んだ助詞」のときだけ開ける**——N2 を閉じた2件
        # （`うづる**に**行きます`・`きゃらくた**で**でぃすぷれい`）は
        # **打たれたままの助詞**だった。今回の的 `かいせき**が**ながく` の
        # が は か＋せ（゛の隣）から手が生んだ字。**手が、語の境目に
        # ちょうど格助詞を生む**のは偶然では起きにくい——それが
        # 「接続詞としてより自然」の中身。門は6つ（全部が立つときだけ）:
        #   (i)   助詞の位置が `born`（手が変えた位置）に入っている
        #   (ii)  その字が1字の格助詞（`_p1`）
        #   (iii) 左は実績2以上の錨（弱い先頭・索引の錨では開けない）。
        #         元の塊の頭が漢字で手を当てていないなら、その表記を保つ
        #         （`keep_head`——解析 を 会席・懐石 にしない・48-IU）
        #   (iv)  右は強い語（`_strong_piece`）
        #   (v)   組んだ読み全体が `_looks_like_valid_japanese`
        #   (vi)  助詞の直後の字が助詞と同じ（でで）なら開けない
        #         （重複打鍵の持ち場）
        for _gap in (0, 1):
            if _gap and (ln1 >= n or text[ln1] not in _p1):
                continue
            if _gap:
                if not born or ln1 not in born:
                    continue                                    # (i)
                if _weak or _idx or not any(
                        e.get('count', 0) >= 2 for e in entries):
                    continue                                    # (iii)
                if ln1 + 1 < n and text[ln1 + 1] == text[ln1]:
                    continue                                    # (vi)
                if tokenize_fn is None:
                    continue                                    # (v)
                try:
                    if not _looks_like_valid_japanese(text, tokenize_fn):
                        continue
                except Exception:
                    continue
            elif only_born_particle:
                continue            # この呼び手は 48-RQ の枝だけを使う
            _head_use = head
            if _gap and keep_head and keep_head[0] == first:
                _head_use = keep_head[1]
            _base = ln1 + _gap
            for ln2 in range(2, min(10, n - _base) + 1):
                _frag = text[_base:_base + ln2]
                if _weak or _short or _gap:
                    # 錨が後ろに在る形（項目48-MY）・短い先頭（48-ON）・
                    # 助詞を挟む形（48-OM）: **2つ目は強い語**——
                    # ここが並び全体の証拠になるので、辞書の索引の
                    # 先頭では代わりにならない
                    piece = _strong_piece(_frag)
                else:
                    piece = _content_piece(_frag)
                if piece is None:
                    continue
                # **2つ目がかなだけなら部品ではない**（項目48-RV・2026-09-05・
                # `由良仮名 → 有料かお`——語彙に在るかな表記 `かお` を2つ目の
                # 語に採っていた）。かなのまま残す部分は尾の門
                # （`_tail_kana_ok`）が見る所で、語の組み立ての部品は
                # 漢字かカタカナに限る（`_two_word_faces` と同じ考え）
                if all(is_hiragana(c) or c == 'ー' for c in piece):
                    continue
                # **読みが2字以下の部品に手の変更が掛かっているなら採らない**
                # （項目48-RV・`由良仮名 → 有料カニ`——`かな` の な を に に
                # 変えて `カニ`。半分が作り物の2字は証拠にならない。手が触って
                # いない2字（`入力ミス` の ミス）と、3字以上（`タブ移動して` の
                # いどう）は今までどおり）
                if (born and ln2 <= 2
                        and any(_base <= _p < _base + ln2 for _p in born)):
                    continue
                # ★★ **品詞のつながり**（項目48-RV'・2026-09-05・うにさんの
                # 指定「品詞の判定やつながりを重要視してください」）。
                # 助詞を挟まない 語＋語 は**名詞＋名詞（複合名詞）**だけ。
                # `背中セク → はいながく → ハイ＋長く`（名詞に形容詞の
                # 連用形が直付き）は語ではない。`解析が長く` は が を挟む
                # （`_gap == 1`）ので用言が続いてよい
                if not _gap and tokenize_fn is not None:
                    try:
                        _tp = tokenize_fn(piece)
                    except Exception:
                        _tp = None
                    if _tp:
                        _pp = (_tp[0][1] or '')
                        if (not _pp.startswith('名詞')
                                or _pp.startswith('名詞:非自立')):
                            continue
                # **漢字の短い先頭は、2つ目が世の中のカタカナ語のときだけ**
                # （項目48-OR(c)）
                if _short_kanji and piece != _world_katakana_piece(_frag):
                    continue
                if not _tail_kana_ok(_base + ln2):
                    continue
                out = (_head_use + text[ln1:_base] + piece
                       + text[_base + ln2:])
                if _gap:
                    _trace('かな連続', f'{text!r} → 語＋手が生んだ助詞'
                                       f'（{text[ln1]}）＋語 で {out!r}'
                                       f'（項目48-RQ）')
                return (out, ln1) if out != text else None
    return None


def _misplaced_large_kana_fixes(line, store, dict_index=None):
    """
    **項目48-KV: 場違いな大書き（Shift の押し忘れ）を小書きに戻す**
    （2026-08-29・うにさんの一覧「にゆうりよくみす　にゅうりょくみす
    入力ミス」）。

    かな入力では小書き（ゃゅょ）に Shift が要る。押し忘れると

        にゆうりよくみす   ← にゅうりょくみす（にゅ・りょ の2か所）

    ができる。★★の流れのとおり:

        ① 異様か判定   `pos_grammar.odd_kana_spans` が立つ連続だけ開く
                       （48-KS の判定。正しい文は最初から開かない）
        ③ 手           **い段の直後の大書き やゆよ → 小書き**。
                       該当する場所を**全部まとめて**1つの候補にする
                       （Shift の押し忘れは連続して起きる）
        ④ 確かめ       元の並びは世の中の読みで敷き詰められないが、
                       直した並びは**敷き詰められる**こと
                       （`pos_grammar.world_covered`——刈り込む前の
                       読み＋機能語）。候補は作りからただ1つ

    **小書き同士の取り違え（ょ⇄ゅ・がいしょつする）は入れていない**
    ——正しい `にゅうりょくみす` を `にょうりょくみす` に壊す
    （どちらも敷き詰められて、比べる物差しがまだ無い・実測）。
    受け止める判定が立つまで開かない。

    実測（2026-08-29・両写し）: 実機メモ1,494行で手が届くのは
    的の3行だけ（にゆうりよくみす×2・にゆうりょく）・誤爆0。

    戻り値: [(始まり, 終わり, 直した連続, 分類), ...]
    """
    if not line or dict_index is None:
        return []
    if os.environ.get('CN_KANA_SHIFT') == '0':
        return []
    try:
        import pos_grammar as _pg
        spans = _pg.odd_kana_spans(line, dict_index, store)
    except Exception:
        return []
    out = []
    for a, b in spans:
        run = line[a:b]
        # ③ 手(i): い段の直後の大書き やゆよ → 小書き（全部まとめて）
        spots = [i for i in range(1, len(run))
                 if run[i] in _LARGE_TO_SMALL and run[i - 1] in _KV_I_DAN]
        base = run
        if spots:
            chars = list(run)
            for i in spots:
                chars[i] = _LARGE_TO_SMALL[run[i]]
            base = ''.join(chars)
        # ④ 世の中の読みで敷き詰められること。立たなければ
        #    手(ii): **う挿入**（長音の脱字・1か所・ただ1つのときだけ。
        #    にゅりょくみす → にゅうりょくみす）
        #    手(iii): **う の位置ずれ**（項目48-OP・2026-09-03。
        #    にゅ|りょう → にゅう|りょ。拗音の直後どうしで移す・
        #    移した形がただ1つのときだけ）
        # 「元が敷き詰められないこと」は**見ない**——世の中の読みは
        # 密で、にゆうりよくみす さえ に＋ゆうり＋よく＋みす と
        # 読めてしまう（実測）。①の異様判定（48-KS）が既に
        # 「元はおかしい」と言っているので、そこに重ねない（48-GN）。
        # **ただし手(iii) は「元が敷き詰められない」ときだけ**——
        # 敷き詰まっている読みを、わざわざ崩して並べ替えない。
        try:
            import pos_grammar as _pg
            cands = []                  # 試す順の [(読み, う の位置)]
            if _pg.world_covered(base, dict_index):
                cands.append((base, None))
            else:
                # 手(ii): う挿入
                good = {}
                for k in range(len(base)):
                    if base[k] not in _KV_U_AFTER:
                        continue
                    v = base[:k + 1] + 'う' + base[k + 1:]
                    if _pg.world_covered(v, dict_index):
                        good.setdefault(v, k + 1)
                if len(good) == 1:
                    cands.append(next(iter(good.items())))
                # 手(iii): う の位置ずれ（項目48-OP）。
                # **手(ii) のあとに試す**——`しゅうりょじ`（48-MG）は
                # 両方の手が立つ（(ii) しゅうりょうじ → 終了時 ／
                # (iii) しゅりょうじ）。う挿入で答えが出ているものを
                # 位置ずれが横取りしないよう、順は (ii) → (iii)。
                _mv = {v: k for v, k
                       in _kv_move_u_variants(base).items()
                       if _pg.world_covered(v, dict_index)}
                if len(_mv) == 1:
                    cands.append(next(iter(_mv.items())))
        except Exception:
            continue
        if not cands:
            continue        # 読みの切れ目が立たない＝証拠不足
        # ⑤ 漢字変換が既定（`_kv_finish`。手(ii)・(iii) で同じ門）
        fix = None
        for _base, _u_pos in cands:
            fix = _kv_finish(run, _base, _u_pos, store, dict_index)
            if fix:
                base = _base
                break
        if not fix:
            continue
        _trace('かな連続', f'{run!r} → {fix!r}（場違いな大書き／う挿入'
                           f'／う の位置ずれ・項目48-KV/48-OP）')
        out.append((a, b, fix, 'かな入力'))
    return out


#: 引用のかぎ括弧・括弧（項目48-MI）。中に入っただけの かなは
#: 「その語を**言及している**」形なので、変換しない。
_QUOTE_OPEN = "「『“\"'（(【〔《〈"
_QUOTE_CLOSE = "」』”\"'）)】〕》〉"


def _is_quoted_whole(line, a, b):
    """[a:b) が、かぎ括弧・括弧に**そっくり**入っているか。"""
    if a <= 0 or b >= len(line):
        return False
    i = _QUOTE_OPEN.find(line[a - 1])
    return i >= 0 and line[b] == _QUOTE_CLOSE[i]


#: `_is_kango` の控え（同じ組を何度も測らない。表は入力だけで
#: 決まるので、控えても答えは変わらない）。項目48-MI/MK。
_KANGO_CACHE = {}
_KANGO_CACHE_LIMIT = 20000


def _is_kango(surface, reading):
    """
    その表記と読みが、**音読みだけで組める2字以上の漢語**か
    （項目48-MI・2026-08-31）。

    `確認`＝確(かく・音)＋認(にん・音) は漢語。`平仮名`＝平(ひら・訓)
    は漢語ではない。表は `kanji_onkun`（音訓の印つき）をそのまま使う
    ——**名簿を2つ作らない**。表が読めなければ False（＝触らない）。

    連濁・促音便（学校＝がく→がっ）は組めないので False になる。
    **落とす側に倒れるだけ**なので、それでよい。
    """
    if len(surface) < 2 or not all(is_kanji(c) for c in surface):
        return False
    got = _KANGO_CACHE.get((surface, reading))
    if got is not None:
        return got
    try:
        import kanji_onkun as _ok
        if not _ok.available():
            return False
    except Exception:
        return False
    n = len(surface)
    reach = [set() for _ in range(n + 1)]
    reach[0].add(0)
    for i in range(n):
        for p0 in reach[i]:
            for r in _ok.readings_of(surface[i]):
                # **印ではなく形で見る**（項目48-MQ）。表の印は穴だらけで
                # （効 の こう・力 の りょく・形 の けい・致 の ち は
                #  どれも `'?'`）、印だけを見ると `効率` も `形態` も
                # 「漢語ではない」になっていた。
                if not _ok.is_on_reading(surface[i], r):
                    continue
                if reading.startswith(r, p0):
                    reach[i + 1].add(p0 + len(r))
    out = len(reading) in reach[n]
    if len(_KANGO_CACHE) > _KANGO_CACHE_LIMIT:
        _KANGO_CACHE.clear()
    _KANGO_CACHE[(surface, reading)] = out
    return out


def _na_adj_ka_word(full):
    """
    **形容動詞語幹＋化 は、表に無くても1語**（項目48-OK・2026-09-02）。

    巨大化・正常化・安定化・活性化——「〜化」は形容動詞語幹に**生産的に
    付く**（文法として決まっている形。★★「論理的に正しいものは標本で
    差が出なくても入れる」）。同梱の表に `巨大化` が無いだけで
    `居で以下 → 巨大化` が2つの道（48-MP・48-MK の compose）で落ちて
    いた。**サ変の名詞（注意化）・一般の名詞（課題化）には広げない**
    ——そちらは表（`seed_japanese.is_unit`）で確かめる。

    語幹の品詞は解析器（janome）に聞く。無ければ False（＝表のまま）。
    """
    if not full or len(full) < 3 or not full.endswith('化'):
        return False
    try:
        from morphology import tokenize as _mtok
        toks = [t for t in _mtok(full[:-1]) if getattr(t, 'surface', '')]
    except Exception:
        return False
    if len(toks) != 1:
        return False
    return (getattr(toks[0], 'pos', '') == '名詞'
            and getattr(toks[0], 'pos_sub', '') == '形容動詞語幹')


# **名詞の直後に来る機能語の頭**（項目48-ON）。1字の格助詞（_p1）の
# ほかに、2字で始まるもの。閉じた表——文法で決まる並びだけ
_NOUN_TAIL2 = frozenset((
    'から', 'まで', 'より', 'など', 'だけ', 'でも', 'では', 'には', 'とは',
    'です', 'でし', 'だっ', 'する', 'した', 'して', 'しま', 'され', 'させ',
    'でき', 'っぽ', 'らし', 'みた', 'たち', 'さん', 'ごと', 'ずつ', 'こそ',
    'しか', 'さえ', 'なら', 'なり', 'なの', 'じゃ', 'って'))


def _kana_growth_is_grammar(surf):
    """
    **増えたかなが、文法のかな（助詞1字・送り仮名）だけか**（項目48-OM・
    2026-09-02）。48-ND(b)「漢字を減らして、そのぶんかなを増やさない」は
    「語をかなに開く」組み立てを止める門。`解析課背中セク → 解析が長く`
    は漢字が減ってかなが増えるが、増えたのは **が（格助詞）と く（長く の
    送り仮名）**——書かれ方を変えたのではなく、文法が要るかな。
    かなの連なりが**全部2字以下で、漢字に接している**ならそれと見る。
    `昨年こうになる`（こうになる＝5字）は通らない。
    """
    if not surf:
        return False
    i, n = 0, len(surf)
    while i < n:
        if not is_hiragana(surf[i]):
            i += 1
            continue
        j = i
        while j < n and is_hiragana(surf[j]):
            j += 1
        if j - i > 2:
            return False
        left = surf[i - 1] if i > 0 else ''
        right = surf[j] if j < n else ''
        if not ((left and is_kanji(left)) or (right and is_kanji(right))):
            return False
        i = j
    return True


def _noun_tail_start(tail):
    """その尾は、名詞の直後に置ける機能語で始まるか（項目48-ON）。"""
    if not tail:
        return True
    if tail[0] in 'かがでとにのはへもやを':
        return True
    return tail[:2] in _NOUN_TAIL2


def _surfaces_no_band(dict_index, reading):
    """
    索引の顔を**帯を除いて**引く（項目48-OJ）。①が立っていない道から
    呼ぶときはこちら。`band` を知らない索引（tests_mock の模擬・古い
    写し）には従来の呼び方で落とす——**索引の型で壊れない**ように。
    """
    try:
        return dict_index.surfaces_for_reading(reading, band=False)
    except TypeError:
        return dict_index.surfaces_for_reading(reading)


def _index_face(reading, store, dict_index):
    """
    **異様と判定したあと、その読みの漢字表記を索引の順位で1つに決める**
    （項目48-OJ・2026-09-02）。

    うにさん（2026-09-02）:「そのような基本的な単語が見つからない場所が
    あってもよいのか」——課題・効率・巨大・参考 は初期語彙にも索引にも
    無かった（取り込みのコスト上限 4500・索引 4000。項目48-OF）。
    **語彙（count＝本人の回数）へ入れる形は測って捨てた**（12,482語を
    入れると全部の道が「知っている語」として読み、化け +22。
    `janome_import.is_two_kanji_noun` の説明）。**索引（世の中の語）**に
    2字漢語の帯を持たせ、順位は `kango_tier`（AI の判断）で付ける。

    決め方（CLAUDE.md ★★「候補が複数あっても、優先度の高い1つに
    決めて補正する」）:
      ・本人の語彙に**実績2以上**の表記が在れば、そちらの持ち場（None）
      ・索引の**漢字2字の表記**を段で見て、**いちばん高い段がただ1つ**
        ならそれ（課題(1) 過大(2) → 課題／効率(1) 高率(3) → 効率）
      ・同じ段に2つ（公園・講演）→ **決めない**（None）。段3 しか無い
        （参向・鑽孔）→ 決めない

    **呼ぶのは①（異様判定）が立ったあとの道だけ。** 異様と判定して
    いない連続を変換する道（48-MI・strict_anchor）からは呼ばない。
    """
    if not reading or dict_index is None or len(reading) < 2:
        return None
    try:
        import kango_tier as _kt
        if not _kt.available():
            return None
    except Exception:
        return None
    try:
        if any((e.get('count', 0) or 0) >= 2 for e in store.lookup(reading)):
            return None
    except Exception:
        pass
    try:
        faces = [s for s in dict_index.surfaces_for_reading(reading)
                 if s and len(s) == 2 and all(is_kanji(c) for c in s)]
    except Exception:
        return None
    if not faces:
        return None
    tiers = [(_kt.tier(s), s) for s in faces]
    # **段1（日常語）がただ1つのときだけ決める。** 段2 では決めない——
    # 2026-09-02 に測った: 段2 で決めると 手動補正 → 主導性（手動 は
    # IPAdic の既定コスト 5622 で索引の外・主導(段2) だけが見えた）・
    # 雛仮名 → 表明(段2)・いちょう → 医長(段2)。索引に無い日常語の
    # 同音語が居るかは分からないので、**段1 だけを「決め手」にする**
    top = [s for t, s in tiers if t == 1]
    if len(top) != 1:
        return None
    return top[0]


def _is_conversion_anchor(entry, reading):
    """
    **その語を「変換の錨」にしてよいか**（項目48-MK・2026-08-31）。

    変換の道（`_convert_odd_kana_run`・`_compose_kana_run_fixes`）は
    「**先頭は語彙の実績2以上**」を要求してきた。ところが初期状態の
    語彙 17,090件のうち**実績2以上は 401件だけ**（＝種の語）で、
    残りは janome から取り込んだ count 1。だから初期状態では
    **種の401語しか直し先になれない**:

        さいだいか → 最大化   最大が実績1なので届かない
        かくにん  → 確認     確認は種に在って実績3なので届く

    **枠を広げれば直る**——ただし `count` を上げてはいけない。
    実測（1,190語の2字漢語を count=2 に上げた写しで測った・2026-08-31）:

        readcheck 直った 1888 → 1898（+10）／**化けた 102 → 110（+8）**
        実機メモ  `語彙素 → **合意**`・`長尾真 → **長官**`・
                  `構成する → **校正する**`・`開音節 → **回折**`・
                  同音異義語の一覧が `関心、感心、**感心**` に潰れた

    `count` は**全部の道が「本人が使う語」として読む**（同音異義の
    裁定・芯の再構築・語の組…）。そこを上げると、変換とは関係の
    ない道まで新しい直し先を掴む。**だから「変換の錨」だけを別の
    印で言う**——`count>=2` に加えて、**2字の漢語**（音読みだけで
    組める漢字2字）を錨として認める。

    なぜ2字の漢語か: **漢語をかなで書いたままなのは、まず変換し忘れ**
    （48-MI の門(6) と同じ見立て）。和語はかなで書くのがふつうなので
    入れない。**閉じた形の条件**であって、語を拾い集めた表ではない。
    """
    if not entry:
        return False
    if entry.get('count', 0) >= 2:
        return True
    sf = entry.get('surface') or ''
    return _is_kango(sf, reading)


def _kanji_faces_for_reading(reading, store, dict_index):
    """
    その読みの**漢字だけの表記**を集める（項目48-MI の門(5)）。
    語彙（**回数は問わない**）と辞書の索引の和。かな・カタカナの
    表記は数えない——「かなのままか、漢字か」を決める話ではないので。

    **回数を問わないのが要**。ここで聞いているのは「本人がどちらを
    使うか」ではなく「**その読みが、そもそも1つの漢字に決まるか**」。
    `せんたく` は 選択(実績3)／**洗濯(実績1)** の2つがあるので、
    かなで書かれていても**どちらの意味か決められない**——
    同梱の見本 `せんたくする` を守るのはここ。
    """
    faces = set()
    try:
        for e in store.lookup(reading):
            sf = e.get('surface') or ''
            if sf and all(is_kanji(c) for c in sf):
                faces.add(sf)
    except Exception:
        pass
    try:
        # **帯は数えない**（`band=False`・項目48-OJ）。この門は異様と判定して
        # いない連続（48-MI）の「ただ1つ」——帯を数えると かくにん に
        # 覚認 が並んで 確認 に届かなくなる
        for sf in _surfaces_no_band(dict_index, reading):
            if sf and all(is_kanji(c) for c in sf):
                faces.add(sf)
    except Exception:
        pass
    return faces


def _kango_kana_fixes(line, store, dict_index=None):
    """
    **かなのまま残った漢語を、漢字に変換する**（項目48-MI・2026-08-31）。

    うにさんの画面（v1.3.0 の初期状態）:「・**平仮名が漢字変換されない**」
    ——`かすくにん ⇒ かくにん` までは直るのに、`かくにん` が `確認` に
    ならない。設計指針 U0（2026-08-29）:

        「**かなのまま打ちたいことの確信がなければ漢字変換する**」

    変換の道（`_convert_odd_kana_run`）は在るのに、走るのは
    **異様と判定された連続だけ**だった。`かくにん` は語として説明が
    付く（＝異様ではない）ので、その道に一度も乗らない。

    **「異様だから直す」ではなく「かなのままの確信が無いから変換する」**
    ——別の理由なので、別の口を作る。その代わり門は厳しくする:

      (1) 4字以上の かな連続（短いのは助詞と見分けが付かない）
      (2) **読みの注記ではない**（`is_reading_gloss`・48-LN）
      (3) **かぎ括弧・括弧にそっくり入っていない**——引用は
          「その語を言及している」形（`本来の読みは「しゅるい」`）
      (4) `_convert_odd_kana_run` が立つ（＝**先頭は語彙の実績2以上の
          4字以上の語**・中身の区切りは2つまで・残りは機能語）
      (5) **その読みの漢字表記が、ただ1つ**であること（語彙の実績2
          以上と、辞書の索引を合わせて）。`せんたく` は **洗濯／選択**
          の2つがあるので触らない——**異様判定が立っていない場所の
          門は「ただ1つのときだけ採る」**（設計38〜40・CLAUDE.md）。
          この道はまさに「異様ではないが変換したい」場所なので、
          いちばん厳しい門がそのまま当てはまる。
      (6) **直し先の頭が漢語**（音読みだけで組める2字以上の漢字語）。
          ここが要——`ひらがな → 平仮名`（平は訓読み）・
          `かんがえる → 考える`・`まちがい → 間違い` は和語なので
          かなで書くのが普通で、変換すると**書きたい形を壊す**。
          漢語をかなで書いたままなのは、まず変換し忘れ。

    実測（実機メモ 1,948行・初期状態）: 門(6) が無いと 16種が立ち、
    そのうち和語・注記が 5種混ざる。門(6) を掛けると **3種**（うち
    1つは 門(3) が落とす引用）＝**的の `かくにん → 確認` だけが残る**。
    門(5) は `せんたくする → 選択する`（同梱の見本の守り。**洗濯**か
    **選択**か決められない）を落とす。
    readcheck・fpcheck は kana/romaji とも差0。

    戻り値: [(始まり, 終わり, 直し先, 分類), ...]
    """
    if not line or store is None or dict_index is None:
        return []
    if os.environ.get('CN_KANGO_CONV') == '0':
        return []
    out = []
    i, n = 0, len(line)
    while i < n:
        if not ('ぁ' <= line[i] <= 'ゖ' or line[i] == 'ー'):
            i += 1
            continue
        j = i
        while j < n and ('ぁ' <= line[j] <= 'ゖ' or line[j] == 'ー'):
            j += 1
        run, a0 = line[i:j], i
        i = j
        if len(run) < 4:
            continue
        if kana_is_mentioned(line, a0, j):
            continue
        if _is_quoted_whole(line, a0, j):
            continue
        # **錨は実績2以上だけ**（項目48-MK）。ここは異様と判定して
        # いない連続を変換する場所なので、いちばん厳しい錨で問う
        # （広げた錨を通すと `こうどう → 行動`——`こうとう` の濁点の
        # 脱けを戻す道を先取りして壊した・readcheck で実測）。
        # **索引の顔（段1がただ1つ）を、この道の錨にも使う**（項目48-OO・
        # 2026-09-02 → **2026-09-03 に既定 ON**）。うにさんの決定:
        # 「**試さないと分かりません**」（2026-09-03・項目48-OO の追記）。
        # 入れると `こうりつを上げる → 効率を上げる`・`さんこうにする →
        # 参考にする` が初期状態で通る。引き換えに readcheck で
        # **読みが違う化けが4**（かんどう → 感動・せいげん → 制限・
        # せんげつ → 先月・かいかん → 会館＝打ち間違いの読みが
        # たまたま別の日常語）・fpcheck 1（たくさんでした → 沢山でした）。
        # **切るときは `CN_MI_INDEX=0`**（suite/measure の名簿にも在る）
        got = _convert_odd_kana_run(run, store, dict_index,
                                    strict_anchor=True,
                                    index_anchor=(os.environ.get('CN_MI_INDEX')
                                                  != '0'))
        if not got or got[0] == run:
            continue
        surface, head_end = got
        # **濁点1つ違いで別の日常語になるなら決めない**（48-OO の
        # 受け皿・項目48-OQ の測定で出た化け4件を受け止める門）。
        # ここは①（異様）が立っていない場所なので、設計38〜40
        # 「ただ1つのときだけ採る」が効く
        if _dakuten_rival_reading(run[:head_end], store, dict_index):
            _trace('かな連続', f'{run!r} → 濁点1つ違いの日常語が別に'
                               f'在るので決めない（項目48-OO の受け皿）')
            continue
        # 直し先の**頭**（読みの先頭 head_end 字に当たる表記）。
        # 尻尾はかなのまま残る作りなので、その分を後ろから外す。
        #
        # **尻尾が本当にかなのまま残っているかを確かめる**（項目48-PH・
        # 2026-09-03）。この道は「**かなのまま残った漢語を変換**する」
        # ためのもので、尻尾は触らない前提だった。ところが確かめて
        # いなかったので、48-PE で `威` に読み `い` が入った途端に
        # こうなった（育ちの readcheck で実測）:
        #
        #     きょういだに → **脅威ダニ**（`だに` が カタカナの ダニ に）
        #
        # 頭（脅威）だけを見る門は全部通ってしまう。**尻尾が元のまま
        # でないなら、それは「漢語を変換した」ではない。**
        # 的は全部そのまま——`こうりつを → 効率を`・
        # `さんこうにする → 参考にする`・`いちばんうえ → 一番うえ`。
        tail = len(run) - head_end
        if tail and not surface.endswith(run[head_end:]):
            _trace('かな連続', f'{run!r} → {surface!r} は尻尾'
                               f'（{run[head_end:]!r}）まで変わっている。'
                               f'漢語の変換ではないので触らない（項目48-PH）')
            continue
        head_surface = surface[:len(surface) - tail] if tail else surface
        # **世の中がその語をかなで書いているなら、かなのまま**
        # （項目48-OO の受け皿(3)・2026-09-03）。
        #
        # U0「**かなのまま打ちたいことの確信がなければ漢字変換する**」の
        # **確信のほう**を、同梱の表の費用で測る——`seed_japanese_cost`
        # は「小さいほど世の中でよく使う」なので、**かなの形のほうが
        # 安いなら、世の中はその語をかなで書いている**:
        #
        #     たくさん **89** ／ 沢山 106   → かなのまま（当て字）
        #     できる   **90** ／ 出来る 110 → かなのまま
        #     いちばん 100 ／ 一番 **60**   → 変換する
        #     こうりつ 126 ／ 効率 **107**  → 変換する
        #     さんこう 142 ／ 参考 **103**  → 変換する
        #
        # **48-MI（①が立っていない連続）だけに掛ける**——異様だと
        # 判定した道は★★「何かしらに決める」なので、ここには来ない。
        # 表が片方でも読めなければ**変換する側**（今までどおり）
        _c_kana = _table_cost(run[:head_end])
        _c_kanji = _table_cost(head_surface)
        if (_c_kana is not None and _c_kanji is not None
                and _c_kana < _c_kanji):
            _trace('かな連続', f'{run!r} → 世の中は かな で書く語'
                               f'（{run[:head_end]!r} {_c_kana} < '
                               f'{head_surface!r} {_c_kanji}）。'
                               f'かなのまま（項目48-OO の受け皿）')
            continue
        # (5) **その読みの漢字表記がただ1つ**であること
        if (len(_kanji_faces_for_reading(run[:head_end], store,
                                         dict_index)) != 1
                and _index_face(run[:head_end], store, dict_index)
                != head_surface):
            _trace('かな連続', f'{run!r} → 読み {run[:head_end]!r} の'
                               f'漢字表記が1つに決まらないので触らない'
                               f'（項目48-MI）')
            continue
        # (6) **直し先の頭が漢語**
        if not _is_kango(head_surface, run[:head_end]):
            continue
        _trace('かな連続', f'{run!r} → {surface!r}（かなのまま残った'
                           f'漢語を変換・項目48-MI）')
        out.append((a0, j, surface, 'かな入力'))
    return out


def _onbin_dakuten_fixes(line, store, tokenize_fn, dict_index=None):
    """
    **音便と た/だ の相補分布**（項目48-LL・2026-08-30）。

    形態論の「異形態」——過去・接続の た/て は音便の種類で形が
    機械的に決まる（相補分布）:

        撥音便（ん）のあと      **必ず で/だ**   読んで・遊んだ
        ガ行のイ音便のあと      **必ず で/だ**   泳いで・騒いで・稼いだ
        カ行のイ音便・促音便    て/た            書いて・行った

    だから `読んて` `泳いた` は**文法だけで異様と言い切れ**、直し先も
    ゛追加の1手で一意——濁点が独立キーの かな入力で、うにさんの
    いちばん多い打ち間違いの族（゛の打ち忘れ）がここに落ちる。

    門（AI の判断で先回りした罠・実測）:
      ・ガ行の判定は**読み**で（語幹の読み＋ぐ が世の中の読みに在り、
        ＋く が**無い**ときだけ。書い＝かく が在るので触らない）
      ・漢字の語幹は**表記でも**見る——`急いて` は 急ぐ(いそぐ) なら
        誤りだが、**急く(せく) の音便としては正しい**（「急いては事を
        仕損じる」）。語幹＋く が辞書の表記に在るなら触らない
      ・て は助詞:接続助詞・た は助動詞のときだけ（引用の て を外す）

    戻り値: [(始まり, 終わり, 直した1字), ...]
    """
    if not line or tokenize_fn is None or dict_index is None:
        return []
    if os.environ.get('CN_LL') == '0':
        return []
    # 同じ漢字が ぐ動詞と く動詞を両方持つ表記（急ぐ いそぐ／急く
    # せく——「急いては事を仕損じる」は正しい）。音訓の表は薄くて
    # 引けない（急に いそ・せ が無い・実測）ので、閉じた名簿にする
    # （AI の判断で書き下し・Fable 5・2026-08-30）
    _LL_AMBIG = frozenset(('急い',))
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return []
    from morphology import katakana_to_hiragana
    out = []
    for i in range(len(tokens) - 1):
        t, u = tokens[i], tokens[i + 1]
        if t[4] != u[3]:
            continue
        if (t[1] or '') != '動詞:自立':
            continue
        if len(t) > 5 and not t[5]:
            continue                # 推測読みでは判定しない
        ch = u[0][:1]
        if ch not in ('て', 'た'):
            continue
        up = u[1] or ''
        if ch == 'て' and not up.startswith('助詞:接続助詞'):
            continue
        if ch == 'た' and not up.startswith('助動詞'):
            continue
        rd = katakana_to_hiragana(t[2] or '')
        sf = t[0]
        voiced = 'で' if ch == 'て' else 'だ'
        fire = False
        how = ''
        if sf.endswith('ん') and rd.endswith('ん'):
            fire = True
            how = '撥音便'
        elif sf.endswith('い') and rd.endswith('い') and len(rd) >= 3:
            stem = rd[:-1]
            try:
                g = dict_index.is_world_reading(stem + 'ぐ')
                k = dict_index.is_world_reading(stem + 'く')
            except Exception:
                g = k = True
            if g and not k and sf not in _LL_AMBIG:
                fire = True
                how = 'ガ行のイ音便'
        if fire:
            a = u[3]
            _trace('かな連続', f'{sf}＋{ch} → {sf}＋{voiced}'
                               f'（{how}のあとは濁る・項目48-LL）')
            out.append((a, a + 1, voiced))
    return out


def _adjective_tail_fixes(line, store, tokenize_fn, dict_index=None):
    """
    **項目48-KZ (S2): 文節末尾の「て」を隣のキーの「い」と疑って、
    イ形容詞に戻す**（2026-08-29・うにさんの案「文節最後の文字を
    隣接キーと疑ったらイ形容詞…として自然に繋がったり」）。

        動作が重て、 → 動作が重い、   （い＝Eキー・て＝Wキー＝隣）

    ① 異様の判定   **形容詞の語幹だけ（送り仮名なし）＋接続助詞て**。
                   正しい文には出ない形（正しくは 重い／重くて。
                   動詞のて形〔書いて〕は品詞が違う）
    ③ 手           て → い（かな配列で隣のキー）
    ④ 確かめ       語幹＋い が語彙か辞書に**在る語**であること

    戻り値: [(始まり, 終わり, 直した文字), ...]（て の位置を い に）
    """
    if not line or tokenize_fn is None:
        return []
    if os.environ.get('CN_KANA_SHIFT') == '0':
        return []
    try:
        toks = [t for t in tokenize_fn(line) if t[0]]
    except Exception:
        return []
    out = []
    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        ap, bp = a[1] or '', b[1] or ''
        if not (ap.startswith('形容詞') and a[0]
                and all(is_kanji(c) for c in a[0])
                and b[0] == 'て' and '接続助詞' in bp
                and a[4] == b[3]):
            continue
        word = a[0] + 'い'
        known = False
        try:
            if store.reading_of(word):
                known = True
        except Exception:
            pass
        if not known and dict_index is not None:
            # 表記の索引は形容詞を刈り込んでいる（広い が引けない・
            # 実測）ので、**世の中の読み**（語幹の読み＋い）でも見る
            try:
                if dict_index.readings_for_surface(word):
                    known = True
                else:
                    from morphology import katakana_to_hiragana as _k2h
                    _ar = _k2h(a[2] or '')
                    if _ar and dict_index.is_world_reading(_ar + 'い'):
                        known = True
            except Exception:
                pass
        if not known:
            continue
        _trace('かな連続', f'{a[0]}て → {word}（文節末尾の て を隣の'
                           f'キーの い と疑う・項目48-KZ S2）')
        out.append((b[3], b[4], 'い'))
    return out


#: 濁点が付く字（項目48-LA'）
_DAKUTEN_BASE = {'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
                 'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
                 'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
                 'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
                 'う': 'ゔ'}


def _lagged_dakuten_fixes(line, store, tokenize_fn, dict_index=None):
    """
    **項目48-LA': 遅れて打たれた濁点を、手前の字に当てはめる**
    （2026-08-29。うにさんの一覧 `硬い゛に取り掛かる ⇒ 課題に
    取り掛かる`＝かたい゛ の ゛ は **た に付くはずだった**）。

    浮いた ゛（直前の字が濁点を取れない）は、いままで黙って捨てられる
    （初期）か れ に化ける（育ち）だけだった。ここでは:

      ① 直前の字に付かない ゛ だけ見る（かたい**゛**——い に ゛ は
         付かない。付く形〔た゛＝だ〕は濁点合成が既に持ち場）
      ② 直前の語（解析のトークン）の読みの中の、濁点が付く字に
         1か所ずつ当てはめる（かたい → **かだい**／**がたい**）
      ③ 語彙の実績2以上の表記に届く形が**ただ1つ**なら、その表記に
         直す（かだい → 課題。がたい は実績が無いので競らない）

    戻り値: [(始まり, 終わり, 直した表記, 分類), ...]
    """
    if not line or tokenize_fn is None or '゛' not in line:
        return []
    try:
        toks = [t for t in tokenize_fn(line) if t[0]]
    except Exception:
        return []
    from morphology import katakana_to_hiragana
    out = []
    for i, t in enumerate(toks):
        if t[0] != '゛':
            continue
        m_s, m_e = t[3], t[4]
        prev = line[m_s - 1] if m_s > 0 else ''
        if prev in _DAKUTEN_BASE:
            continue                     # 付く形は濁点合成の持ち場
        # 直前のトークン（読みが立っている語）
        if i == 0:
            continue
        a = toks[i - 1]
        if a[4] != m_s or not a[0]:
            continue
        if len(a) > 5 and not a[5]:
            continue
        rd = katakana_to_hiragana(a[2] or '')
        if not rd or len(rd) < 2:
            continue
        faces = {}
        for p, c in enumerate(rd):
            if c not in _DAKUTEN_BASE:
                continue
            v = rd[:p] + _DAKUTEN_BASE[c] + rd[p + 1:]
            for e in store.lookup(v):
                if e.get('count', 0) >= 2 and e['surface'] != a[0]:
                    faces[e['surface']] = v
        if not faces:
            # **語彙に実績が無ければ、索引の顔**（項目48-OJ）。
            # かたい゛ → かだい → 課題（段1がただ1つ）
            for p, c in enumerate(rd):
                if c not in _DAKUTEN_BASE:
                    continue
                v = rd[:p] + _DAKUTEN_BASE[c] + rd[p + 1:]
                _f = _index_face(v, store, dict_index)
                if _f and _f != a[0]:
                    faces[_f] = v
        if len(faces) != 1:
            continue
        surf, v = next(iter(faces.items()))
        _trace('かな連続', f'{a[0]}゛ → {surf!r}（遅れた濁点を {v!r} に'
                           f'当てはめた・項目48-LA\'）')
        out.append((a[3], m_e, surf, 'かな入力'))
    return out


def _has_unknown_katakana(piece):
    """
    その塊に、**世の中のカタカナ語の表に無いカタカナの連なり**が
    在るか（項目48-MV・2026-08-31）。

    `乳リュク` の `リュク` は表に無い＝IME が変換しそこねた跡。
    `カール位置` の `カール`・`クリック化ドラッグ` の `クリック`
    `ドラッグ` は表に在る＝正しく書けている（触らない）。

    **「解析が読みを立てられたか」では見ない**——janome の無い
    環境では全部が「立たず」になり、正しいカタカナ語まで開いて
    しまう（`tests_mock` で3件踏んだ）。**表を見れば環境に依らない。**
    """
    try:
        import loanword as _lw
        tbl = _lw._katakana_seed_all()
    except Exception:
        return False
    if not tbl:
        return False
    i, n = 0, len(piece)
    while i < n:
        if not (is_katakana(piece[i]) or piece[i] == 'ー'):
            i += 1
            continue
        j = i
        while j < n and (is_katakana(piece[j]) or piece[j] == 'ー'):
            j += 1
        frag = piece[i:j]
        i = j
        if len(frag) < 2:
            continue
        try:
            from morphology import katakana_to_hiragana as _k2h
            if _k2h(frag) not in tbl:
                return True
        except Exception:
            return False
    return False


def _insert_na_ni(line, tokenize_fn):
    """
    **ナ形容詞の語幹に動詞が直付きなら、間に「に」を入れる**
    （項目48-NN・2026-09-01）。

    うにさんの指定:

        「**静か歩く、異様なので平仮名にして、しずかあるく、
          ここまで来ますね。隣接キーの疑惑よりも先に、
          1文字の接続詞を疑うべきでしょうか**」

        静か歩く → **静かに歩く**

    **はい、先に疑うべき。** 1字の助詞は**閉じた小さな集まり**なので
    候補が広がらず、入れて読めれば**それが本来の入力**である。
    隣接キーは「読める候補」が複数出て決め手が要る——順番が逆だった。

    しかも**ここは平仮名に開くまでもない**。うにさんが列挙した
    「ナ形容詞の語幹の後ろに来られる形」（項目48-NM）から、
    **語幹＋動詞のあいだに入る助詞は「に」ただ1つ**に決まる
    （静か**に**歩く・有力**に**なる）。「が」「を」は名詞にしか付かず、
    「で」「と」は連用修飾にならない。**文法が答えを1つにする。**

    かなに開いてから助詞を入れる形も測ったが（`しずかあるく` →
    `しずかにあるく`）、**名詞＋動詞では が/を/に/で/と が並んで
    決まらない**（`もじうつ`）。**決まるのはナ形容詞の側だけ。**

    戻り値: [(始まり, 終わり, 直した文字, 種別), ...]
    """
    if tokenize_fn is None or not line:
        return []
    import oddness as _odd_nn
    try:
        toks = list(tokenize_fn(line))
    except Exception:
        return []
    out = []
    for k in range(1, len(toks)):
        a, b = toks[k - 1], toks[k]
        ap, bp = (a[1] or ''), (b[1] or '')
        # **判定は `oddness.naadj_stem_bare` ただ1つ**（項目48-NM'・
        # 2026-09-01）。ここに**同じ品詞の見方をもう一度書いていた**
        # ので、印（紫）を直しても直しの側が古いままになり、
        # **`元気出して！` を `元気に出して！` に壊した**（実測）。
        # 48-GN「同じ判定をもう一度書くと、いつか食い違う」そのもの。
        if not _odd_nn.naadj_stem_bare(a[0], ap, b[0], bp):
            continue
        if '非自立' in bp:
            continue
        # **1字がらみでは動かない**（48-HU と同じ門・実測）。
        # `これは**んさち**です。` の解析は `はんさ`（煩瑣・形容動詞
        # 語幹）＋ `ち`（動詞）で、**1字の動詞**に に を入れて
        # `はんさにち` を作った。語幹の側も同じ理由で2字以上に。
        if len(a[0]) < 2 or len(b[0]) < 2:
            continue
        # **「する」の活用は入れない**（項目48-NN の門2・実測）。
        # ナ形容詞の語幹＋する＝**サ変動詞**（安定する・確認する）で、
        # 助詞は要らない。入れると `安定している` を
        # **`安定にしている`** にした（実機メモで実測）。
        # 判定は `oddness._SURU_FORMS` に任せる——**同じ名簿を
        # 2つ作らない**（48-GN）。
        try:
            import oddness as _odd_suru
            if b[0] in _odd_suru._SURU_FORMS:
                continue
        except Exception:
            pass
        if 'サ変' in ap:
            continue
        start = b[3]
        fixed = line[:start] + 'に' + line[start:]
        # **入れたら異様さが消えること**（入口はここ1つ）
        try:
            import oddness as _odd_nn
            if _odd_nn.odd_spans(fixed, tokenize_fn):
                continue
            # **入れた「に」が助詞として切れること**
            ts2 = list(tokenize_fn(fixed))
            if not any(t[0] == 'に' and (t[1] or '').startswith('助詞')
                       and t[3] == start for t in ts2):
                continue
        except Exception:
            continue
        _trace('助詞の脱字', f'{a[0]!r}（ナ形容詞の語幹）と {b[0]!r}'
                            f'（動詞）のあいだに に を入れる（項目48-NN）')
        out.append((start, start, 'に', 'かな入力'))
    return out


#: **人を「を」で受けない動詞**（項目48-SA・2026-09-06）。語幹 → 五段の
#: 活用の列（'' は一段）。'サ変' は 名詞:サ変接続 の語。閉じた小さな表——
#: **叙述・記述の動詞**だけ（話す・語る・述べる・言う・書く・読む・記す・
#: 伝える・説明・報告・記述）。「人を呼ぶ／探す／見る」は正しい形なので
#: 入れない（うにさんの指定「`都築を話す`、人名/を話す、というのは文が
#: 成立していない」）
_NO_PERSON_OBJECT_VERBS = {
    '話': 'さしすせそ', '語': 'らりるれろ', '書': 'かきくけこ',
    '読': 'まみむめも', '言': 'わいうえお', '記': 'さしすせそ',
    '述べ': '', '伝え': '', '説明': 'サ変', '報告': 'サ変', '記述': 'サ変',
}


def _verb_takes_no_person_object(tok):
    """そのトークンが、人を を で受けない叙述の動詞か（48-SA の表）。"""
    sf, pos = (tok[0] or ''), (tok[1] or '')
    for stem, row in _NO_PERSON_OBJECT_VERBS.items():
        if not sf.startswith(stem):
            continue
        rest = sf[len(stem):]
        if row == 'サ変':
            if rest == '' and pos.startswith('名詞:サ変接続'):
                return True
            continue
        if not pos.startswith('動詞'):
            continue
        if row == '':
            if rest in ('', 'る'):
                return True
            continue
        if rest and (rest[0] in row or rest[0] in 'っいん'):
            return True
    return False


def _person_object_fixes(line, store, tokenize_fn, dict_index=None):
    """
    **人名（姓）＋ を ＋ 叙述の動詞 は文が成立しない**（項目48-SA・
    2026-09-06・うにさんの指定「`都築を話す`、人名/を話す、というのは
    文が成立していない」）。

        都築を話す → **続きを話す**

    ①（品詞のつながり）: 解析が `都築` を人名:姓と読み、直後が `を`、
    その直後が **話す・語る・書く・読む…**（人を目的語に取らない
    叙述の動詞・`_NO_PERSON_OBJECT_VERBS`）なら、その姓は**同音の
    普通語の変換違い**。② 姓の読み（つづき）に開き、③ 手は要らない
    （読みは正しい）、④ 顔は 本人の語彙の solid → 索引の顔（段1が
    ただ1つ） → 同梱の表の先頭（費用最小・漢字を含む・固有名詞でない）。
    顔が無ければ**紫だけ**（①は立てる）。

    門: 漢字だけの姓／**本人の語彙にその表記が solid なら意見しない**
    （登録した姓・48-JL）／直した塊に異様さが残らないこと。
    戻り値: [(始まり, 終わり, 直した表記, 種別), ...]
    """
    if tokenize_fn is None or not line or 'を' not in line:
        return []
    try:
        toks = [t for t in tokenize_fn(line) if t[0]]
    except Exception:
        return []
    out = []
    for k in range(len(toks) - 2):
        a, b, c = toks[k], toks[k + 1], toks[k + 2]
        ap = a[1] or ''
        sf = a[0] or ''
        if '固有名詞' not in ap or '人名' not in ap:
            continue
        if len(sf) < 2 or not all(is_kanji(ch) for ch in sf):
            continue
        if (b[0] or '') != 'を' or not (b[1] or '').startswith('助詞'):
            continue
        if not _verb_takes_no_person_object(c):
            continue
        try:
            if int(a[4]) != int(b[3]) or int(b[4]) != int(c[3]):
                continue
        except Exception:
            continue
        from morphology import katakana_to_hiragana as _k2h
        rd = _k2h(a[2] or '') if len(a) > 2 else ''
        if not rd or not all(is_hiragana(ch) for ch in rd):
            continue
        try:
            ents = list(store.lookup(rd))
        except Exception:
            ents = []
        if any(e.get('surface') == sf and e.get('count', 0) >= 2
               for e in ents):
            continue                    # 登録した姓（48-JL）——意見しない
        _trace('型', f'{sf!r}（人名:姓）＋を＋{c[0]!r}（叙述の動詞）は文が'
                     f'成立しない。同音の普通語の変換違いと見る（項目48-SA）')
        face = None
        solid = sorted({e.get('surface') for e in ents
                        if e.get('count', 0) >= 2 and e.get('surface')
                        and e.get('surface') != sf})
        if len(solid) == 1:
            face = solid[0]
        if face is None and dict_index is not None:
            try:
                face = _index_face(rd, store, dict_index)
            except Exception:
                face = None
        if face is None:
            try:
                _tf = [x for x in table_surfaces_for_reading(rd)
                       if x != sf and any(is_kanji(ch) for ch in x)]
            except Exception:
                _tf = []
            if _tf:
                face = _tf[0]           # 費用の低い順の先頭
        s0, e0 = int(a[3]), int(a[4])
        if face is None or face == sf:
            if (s0, e0) not in _ODD_PENDING:
                _ODD_PENDING.append((s0, e0))
            continue
        fixed = line[:s0] + face + line[e0:]
        try:
            import oddness as _odd_sa
            if _odd_sa.is_odd_run(fixed[s0:int(c[4])], tokenize_fn,
                                  store=store, dict_index=dict_index):
                if (s0, e0) not in _ODD_PENDING:
                    _ODD_PENDING.append((s0, e0))
                continue
            _t2 = [t for t in tokenize_fn(fixed) if t[0]]
            if any((t[0] == face and '固有名詞' in (t[1] or ''))
                   for t in _t2):
                if (s0, e0) not in _ODD_PENDING:
                    _ODD_PENDING.append((s0, e0))
                continue
        except Exception:
            continue
        out.append((s0, e0, face, 'その他'))
    return out


def _katakana_go_after_fixes(line, tokenize_fn):
    """
    **カタカナのサ変名詞に直付きの接尾「語」は「後」**（項目48-PQ・
    2026-09-04・5巡目の指示書・うにさんの画面5行目）。

        スクロール語の見えた → スクロール**後**の見えた

    接尾 `語` が付くのは**言語名・国名・分野**（日本語・英語・
    専門用語）。**動作の名詞（サ変接続）に `語` は付かない**。
    同じ読み `後`（ご）は逆に**動作の名詞に付く**（スクロール後・
    保存後・入力後——48-LP の 中/時 と同じ族）。1字・同音・
    接尾どうしの入れ替えなので「書かれ方は変えない」の内。

    門（指示書の実測で絞った形）:
      ・頭は**カタカナ**のサ変名詞だけ。**漢語のサ変＋語は掛けない**
        ——検索語・省略語・入力語・派生語・合成語・翻訳語 は正しい語
        なのに表に無い（`is_unit` False）ので、表では守れない。
        カタカナなら `カタカナ語`（サ変でない）・`ドイツ語`
        （固有名詞）が品詞で外れる
      ・その塊が世の中の語なら、できあがっている（`is_unit`・守り）

    **印だけ立てて設計27に任せてはいけない**——`スクロール語 →
    スクロール語彙`（より悪い形）になる（N26・実測）。`語 → 後` を
    ここで名指しで書く（`_scoped_tail_fix` は漢字だけの門で、`語` は
    「何にでも付く側」としてわざと表に入れていない字）。

    戻り値: [(始まり, 終わり, 直した文字, 種別), ...]
    """
    if tokenize_fn is None or not line or '語' not in line:
        return []
    try:
        toks = list(tokenize_fn(line))
    except Exception:
        return []
    out = []
    for k in range(1, len(toks)):
        a, b = toks[k - 1], toks[k]
        if (b[0] or '') != '語' or not (b[1] or '').startswith('名詞:接尾'):
            continue
        sf = a[0] or ''
        if not (a[1] or '').startswith('名詞:サ変接続'):
            continue
        if len(sf) < 2 or not all(is_katakana(c) or c == 'ー' for c in sf):
            continue
        try:
            if int(a[4]) != int(b[3]):
                continue
        except Exception:
            continue
        try:
            import seed_japanese as _sj
            if _sj.is_unit(sf + '語') is not False:
                continue          # できあがっている塊には走らせない
        except Exception:
            continue
        _trace('型', f'{sf!r}（カタカナのサ変名詞）に接尾 語 は付かない。'
                     f'同じ読みで動作の名詞に付く接尾は 後（項目48-PQ）')
        out.append((int(b[3]), int(b[4]), '後', 'その他'))
    return out


def _open_adv_ni_noun(line, tokenize_fn):
    """
    **副詞＋に の後ろの名詞を、読みのかなに開く**（項目48-NS・
    2026-09-01。うにさんの一覧 `そのままに市内 ⇒ そのままにしない`）。

    判定は 48-NR（`oddness.adverb_ni_dangling`）——「そのままに」は
    連用修飾なので**後ろには用言が来るはず**なのに、名詞で終わって
    いる。**修飾する相手が居ない。**

    直しは 48-NK と同じ向き（**漢字をかなに開き戻す**）。ここは
    1字ではなく**語まるごと**で、証拠は「開くと**用言が現れる**」:

        そのままに**市内**（しない）→ そのままに**しない**
          `しない` ＝ し（動詞:自立）＋ ない（助動詞）＝ 用言
          同音異義語（市内／しない）を、**文法が裁く**

    門は3つ:

      (1) 48-NR の紫が立っている場所の名詞であること
      (2) 読みがかなだけで、**開くと用言が現れる**こと
      (3) 開いたら**異様さが消える**こと

    戻り値: [(始まり, 終わり, 直した文字, 種別), ...]
    """
    if tokenize_fn is None or not line:
        return []
    import oddness as _odd_ns
    try:
        toks = list(tokenize_fn(line))
    except Exception:
        return []
    if len(toks) < 3:
        return []
    spans = []
    pos = 0
    for t in toks:
        try:
            s0, e0 = int(t[3]), int(t[4])
            if not (0 <= s0 <= e0 <= len(line)):
                raise ValueError
        except Exception:
            s0, e0 = pos, pos + len(t[0] or '')
        spans.append((s0, e0, t))
        pos = e0
    out = []
    for i in range(1, len(spans) - 1):
        try:
            if not _odd_ns.adverb_ni_dangling(spans, i):
                continue
        except Exception:
            continue
        b_s, b_e, b = spans[i + 1]
        rd = (b[2] or '')
        if not rd or not all(is_hiragana(c) for c in rd):
            continue
        opened = line[:b_s] + rd + line[b_e:]
        if opened == line:
            continue
        try:
            toks2 = list(tokenize_fn(opened))
        except Exception:
            continue
        # (2) 開いた所に**用言が現れる**こと
        _yougen = False
        for u in toks2:
            if not (b_s <= u[3] < b_s + len(rd)):
                continue
            q = u[1] or ''
            if (q.startswith('動詞') or q.startswith('形容詞')
                    or q.startswith('助動詞')):
                _yougen = True
                break
        if not _yougen:
            continue
        # (3) 異様さが消えること
        try:
            if _odd_ns.odd_spans(opened, tokenize_fn):
                continue
        except Exception:
            continue
        _trace('副詞＋に', f'{b[0]!r}（{rd}）→ 後ろに用言が要るので'
                          f'かなに開く（項目48-NS）')
        out.append((b_s, b_e, rd, 'かな入力'))
    return out


def _open_one_kana(line, start, rd, tokenize_fn, _odd_nk):
    """1字を読み `rd` に開いてよいか（項目48-NK の門(2)(3)）。"""
    opened = line[:start] + rd + line[start + 1:]
    try:
        toks2 = list(tokenize_fn(opened))
    except Exception:
        return None
    # (2) 開いた かな が、**隣のかなと合わさって1つの機能語になる**こと。
    #
    #     `の` ＋ `み` → `のみ`（助詞:副助詞）
    #
    # **「1語になれば十分」に緩めると駄目**（実測）。当たりは
    # 4 → 14件に増える（号・乱・力・組——全部が的の行）が、
    # **開いた先がかなのまま止まる**（`きょじえかく乱` →
    # `きょじえかくらん` で終わり）。かなに変えただけの画面は、
    # **紫のままより悪い**。門(3)「異様さが消えるか」は
    # **かなだけの並びでは必ず通る**（紫は漢字の対から立つので）ため、
    # 受け皿にならない。**合わさって機能語になる**ことが、
    # 「切り方が違っていた」の証拠。
    merged = False
    for u in toks2:
        if len(u[0]) <= len(rd):
            continue
        if not (u[3] <= start and u[3] + len(u[0]) >= start + len(rd)):
            continue
        if '助詞' in (u[1] or '') or '助動詞' in (u[1] or ''):
            merged = True
        break
    if not merged:
        return None
    # (3) 異様さが消えること
    try:
        if _odd_nk.odd_spans(opened, tokenize_fn):
            return None
    except Exception:
        return None
    return (start, start + 1, rd, 'かな入力')


def _open_odd_single_kanji(line, tokenize_fn):
    """
    **異様な1字の漢字を、読みのかなに開く**（項目48-NK・2026-09-01）。

    うにさんの指定:

        「**『見』を『み』と読んでるのに1文字で区切っているのが
          変ですよね。**」（`設計の**見**して、 ⇒ 設計の**み**して`）

    解析は `設計|の|見(み)|し|て` と切る。紫も `('見','し')` に立って
    いる——**判定は在って、直す道が無かった**。ここまでの道はどれも
    「かなを漢字に直す」向きで、**漢字をかなに開き戻す**道が無い。

    門は3つ。どれも**この行の中だけ**を見る（語彙も辞書も引かない）:

      (1) **紫の中に居る1字の漢字**で、読みが3拍まで
      (2) 開くと、**隣のかなと合わさって1つの機能語になる**
          （`の`＋`み` → `のみ`＝助詞:副助詞）。**ここが証拠**——
          うにさんの「1文字で区切っているのが変」そのもの
      (3) 開いたら**異様さが消える**

    **読みは解析の1つだけに頼らない**（2026-09-01・うにさんが
    「見る」の他の例を挙げてくれた）:

        一段（語幹＝連用形）  着き・居い・似に・煮に・得え・食べ・起き
        五段（イ段）          書き・行き・話し・待ち・読み・走り
        サ変カ変              する→し ・ 来る→き

    1字で立っている漢字に解析が与える読みは**たいてい音読み**
    （着→ちゃく・居→きょ）で、`見→み` はたまたま訓読みだった。
    **同梱の `kanji_onkun` に、うにさんの一覧がそのまま在る**
    （`readings_of('着')` ＝ ちゃく・**き**・ぎ・つ）ので、
    **表を新しく作らず**そこから訓読みも試す（48-GN）。

    実機メモ全タブ（1,740行）で **当たり4件・全部が的・誤爆0**。

    戻り値: [(始まり, 終わり, 直した文字, 種別), ...]
    """
    if tokenize_fn is None or not line:
        return []
    import oddness as _odd_nk
    try:
        toks = list(tokenize_fn(line))
    except Exception:
        return []
    if not toks:
        return []
    try:
        marks = _odd_nk.odd_spans(line, tokenize_fn) or []
    except Exception:
        return []
    if not marks:
        return []
    out = []
    for t in toks:
        surf, rd, start = t[0], (t[2] or ''), t[3]
        if len(surf) != 1 or not is_kanji(surf):
            continue
        # (1) 紫の中に居ること
        if not any(a <= start < b for a, b in marks):
            continue
        _rds = []
        if rd and len(rd) <= 3 and all(is_hiragana(c) for c in rd):
            _rds.append(rd)
        try:
            import kanji_onkun as _ok
            for _r in _ok.readings_of(surf) or ():
                if (_r and _r not in _rds and len(_r) <= 3
                        and all(is_hiragana(c) for c in _r)
                        and _ok.kind_of(surf, _r) != 'on'):
                    _rds.append(_r)
        except Exception:
            pass
        for _rd in _rds:
            got = _open_one_kana(line, start, _rd, tokenize_fn, _odd_nk)
            if got is not None:
                _trace('1字を開く',
                       f'{surf!r}（{_rd}）→ 隣のかなと合わさって'
                       f'機能語になるので開く（項目48-NK）')
                out.append(got)
                break
    return out


def _reopen_mixed_run_fixes(line, store, tokenize_fn, dict_index=None,
                            input_method=None):
    """
    **項目48-LA: 混ざった連なり（かな＋漢字＋カタカナ）を、自然な
    境界まで含めて開く**（2026-08-29・うにさんの指示「左端の文字が
    補正されるよう進めて」）。

    `にゅうりょ組ス` は、塊づくりが かな側（にゅうりょ）と漢字側
    （組）に分けてしまい、**開く道（設計27）の入口に全体が届かず**、
    芯が にゅうりょく の部分直しで止まっていた。48-HU の
    「端がカタカナに接している塊は途中で切れている」も、切り出しが
    悪いだけで、**連なり全体を渡せば端の門は構成で満たされる**。

    ① 連なりに `oddness.is_odd_run` の印が立つときだけ開く
    ② 開く・③試す・④確かめる は既存の `_reopen_odd_chunk` のまま
       （項目48-LA の「語の組み立て」込み——にゅうりょくみす ＝
        入力＋ミス）

    連なりは3〜8字・漢字を含み、かな か カタカナ も含む形だけ
    （漢字だけの塊は今までの道が持ち場）。
    戻り値: [(始まり, 終わり, 直した表記, 分類), ...]
    """
    if not line or tokenize_fn is None:
        return []
    if os.environ.get('CN_KANA_SHIFT') == '0':
        return []
    # **印は行全体の文脈で取る**（連なりを単独の文として判定すると、
    # 行頭の規則が誤発火して `が異様 → 該当／概要`・`を直接 → 直接` の
    # 化けを作った・実測）。
    try:
        import oddness as _odd
        marks = _odd.is_odd_run(line, tokenize_fn, with_spans=True,
                                store=store, dict_index=dict_index)
    except Exception:
        marks = []
    if not marks:
        return []
    try:
        toks = [t for t in tokenize_fn(line) if t[0]]
        # **印と同じ並びを見る**（項目48-OR・2026-09-03）。
        # `is_odd_run` は信用できない固有名詞の「読みが立った」を
        # 落として印を立てるので、**断片の見立ても同じ並びで**
        # ——落とさないと `右田でブルクリック` は印が立つのに
        # `ブル` が断片に数えられず、連なりが開かれない（学び22）
        toks = _odd.downgraded_tokens(toks, store, dict_index)
    except Exception:
        toks = []
    # janome の無い環境（簡易分割）は**全トークンが読み立たず**なので、
    # 「断片を含む」が常に真になってしまう。読みが1つも立たない行は
    # 開かない（tests_mock の 1-F の守りを壊した・実測）。
    if not any(len(t) > 5 and t[5] for t in toks):
        return []

    # **①の印の左が「名詞に直付きした1字の漢字」なら、それも断片**
    # （項目48-OQ(a)・2026-09-03）。うにさんの一覧4行目
    # `田部井号して ⇒ たぶいごうして ⇒ たぶいどうして ⇒ タブ移動して`:
    #
    #     田部井（名詞:固有名詞:人名:姓）＋ 号（名詞:接尾）＋ し ＋ て
    #
    # `号` は解析では立派な接尾辞なので**読みが立ち**、いままで
    # 「読みの立たない断片」に数えられず、連なりが開かれなかった。
    # ところが **①（48-JC）は既に「号＋し は続けて置けない」と
    # 言っている**——その印の中の1字なら、語の断片として扱ってよい。
    # **し は触らない**（機能語のまま。うにさんの言う「田部井を
    # 開いてつなげる」ぶんだけ）。
    #
    # 門（**過去に壊した2件を、そのまま外す形で決めた**）:
    #   ・1字の**漢字**であること（かなの接尾は 48-OL の持ち場）
    #   ・品詞が **名詞:接尾 か 名詞:一般**
    #     → `設計の見して` の `見` は **動詞:自立** なので来ない
    #       （「印の縁の1字かな全部」に広げたときは
    #         `設計の見して → 設計のして` を作った・実測）
    #   ・**左に名詞が居る**こと
    #     → `そのままに市内` の左は 助詞 `に` なので来ない
    #       （同じ実験で `そのままや市内` を作った・実測）
    #   ・左が**数詞なら開かない**（`3号して` は正しい書き方）
    _suffix_frags = set()
    for _i, _t in enumerate(toks):
        if _i == 0:
            continue
        _sf = _t[0] or ''
        if len(_sf) != 1 or not is_kanji(_sf):
            continue
        _pos = _t[1] or ''
        if not (_pos.startswith('名詞:接尾') or _pos == '名詞:一般'):
            continue
        _lp = toks[_i - 1][1] or ''
        if not _lp.startswith('名詞') or _lp.startswith('名詞:数'):
            continue
        _suffix_frags.add((_t[3], _t[4]))

    def _has_fragment(a, b):
        """範囲 a..b に、読みの立たない**かなの断片**が居るか。
        漢字だけの未知（差釣）は既存の道の持ち場なので数えない
        （数えると方針1-F の守りを壊した・実測）。"""
        for t in toks:
            if t[4] <= a or t[3] >= b:
                continue
            sf = t[0] or ''
            if len(t) > 5 and not t[5] and sf \
                    and all(is_hiragana(c) or is_katakana(c) or c == 'ー'
                            for c in sf) \
                    and not _is_functional_strict(sf):
                return True                 # ません（機能語）は断片ではない
            if len(sf) == 1 and sf in 'ゃゅょぁぃぅぇぉ':
                return True
            # **1字の ん も断片**（項目48-OL・2026-09-02。うにさんの一覧
            # `札ん港になる ⇒ 参考になる`）。解析は ん を格助詞（俺ん家 の
            # ん）と読むが、①（`is_odd_run`）が「ん＋港 は続けて置けない」
            # と既に言っている塊の中では、ん は語の断片。俺ん家・僕ん家・
            # 先生ん所 は①が立たないので、ここへ来ない（実測）
            if sf == 'ん':
                return True
            # **名詞に直付きした1字の漢字の接尾**（項目48-OQ(a)）
            if (t[3], t[4]) in _suffix_frags:
                return True
        return False

    def _cls(c):
        if is_hiragana(c) or c == 'ー':
            return 'h'
        if is_kanji(c):
            return 'k'
        if is_katakana(c):
            return 'c'
        return ''

    out = []
    i, n = 0, len(line)
    while i < n:
        if not _cls(line[i]):
            i += 1
            continue
        j = i
        kinds = set()
        while j < n and _cls(line[j]):
            kinds.add(_cls(line[j]))
            j += 1
        run = line[i:j]
        a0, i = i, j
        if len(run) < 3:
            continue
        if 'k' not in kinds or not ({'h', 'c'} & kinds):
            continue
        inside = [(ma, mb) for _x, _y, ma, mb in marks
                  if ma >= a0 and mb <= j]
        if not inside:
            continue
        # 開いてよいのは、**読みの立たない断片を含む連なり**か、
        # **本当の行頭に立つ印**だけ。既知語どうしの印（送り|仮名 の
        # 類）まで開くと、今までの道が守っていたものを壊す
        # （`送り仮名 → 送りかな` の化け・実測）。
        _head_ok = False
        if a0 == 0:
            for _asf, _bsf, ma, mb in marks:
                # 行頭条項は **1字ひらがなの印（48-KX の形）だけ**。
                # 漢字頭の印（差釣）まで拾うと、方針1-F「並記なしは
                # 触らない」の守りを壊した（実測）
                if ma == 0 and len(_asf) == 1 and is_hiragana(_asf):
                    _head_ok = True
                    break
        _frag_marks = [(ma, mb) for ma, mb in inside
                       if _has_fragment(ma, mb)]
        if not (_frag_marks or _head_ok):
            continue
        # **連なりが長いときは、印の立った範囲だけを開く**
        # （項目48-MV・2026-08-31）。`乳リュク見ています` は9字で
        # この道の枠（3〜8字）から外れていたが、印は `乳リュク`(0..4)
        # に立っている。**印は「どこが異様か」を言っている**ので、
        # そこを開けばよい——連なり全体を開くのは、切り出しがずれて
        # いるときの手当てであって、印が場所を教えているときは要らない。
        #
        # **開くのは「読みの立たない断片を含む印」だけ**（上の門と
        # 同じ）。既知語どうしの印まで開くと、`誤字し` を開いて
        # `誤字`（し の削除）にしてしまった（実測。行頭条項も、
        # 連なり全体の話なので、ここでは使わない）。
        if len(run) > 8:
            _long_done = False
            _long_openable = False
            # **印の外にも読みの立たない語が在るなら、連なりごと**
            # （項目48-OR(c')・2026-09-03。**育ちで測って足した門**）。
            # 48-MV は「印は場所を教えている」ので印の範囲だけを開く。
            # ところが `右田でブルクリック` は**印の外（右田）も
            # 読みの立たない語**（48-OR で格下げされた固有名詞）で、
            # **連なり全体が壊れている**。ここで印の範囲だけを開くと、
            # 育ちの語彙が `ブルクリック → バルクリック`（バル 実績28）を
            # 先に決めてしまい、`右ダブルクリック` に届かない（実測）。
            # `乳リュク見ています` は印の外（見ています）の読みが立つので
            # 今までどおり印の範囲だけ。
            _outside_broken = False
            for _t in toks:
                if _t[4] <= a0 or _t[3] >= j:
                    continue
                if any(_t[3] >= _ma and _t[4] <= _mb
                       for _ma, _mb in _frag_marks):
                    continue
                _sf = _t[0] or ''
                if (len(_t) > 5 and not _t[5] and _sf
                        and not _is_functional_strict(_sf)):
                    _outside_broken = True
                    break
            for _ma, _mb in ([] if _outside_broken else _frag_marks):
                if not (3 <= _mb - _ma <= 8):
                    continue
                _piece = line[_ma:_mb]
                # **開くのは「漢字＋読みの立たないカタカナ」の塊だけ**
                # （項目48-MV）。
                #
                # ・ひらがなを含む印は、助詞や活用の尾を巻き込んで
                #   いることがあり、開くと**語の境目を跨いで**直す
                #   （実測: `昨日どっききょを見ました。` の印を開いて
                #   **を見 → 読** にした・readcheck で 8行）
                # ・カタカナは**読みを字で綴った形**＝IME が変換し
                #   そこねた跡だが、**世の中に在るカタカナ語**
                #   （ドラッグ・クリック・カール・スクロール）は
                #   正しく書けている。**同梱のカタカナ語の表
                #   （9,094語）に無いカタカナ**（リュク）だけが跡。
                #   実測: 載っている側まで開くと `カール位置`
                #   `クリック化ドラッグ` を壊した（tests_mock で3件）。
                #   **「読みが立つか」で見ないのは、janome の無い
                #   環境では全部が「立たず」になるから**（学び。
                #   表を見れば環境に依らない）
                if any(is_hiragana(_c) for _c in _piece):
                    continue
                if not _has_unknown_katakana(_piece):
                    continue
                # ★★ **カタカナの連なりがまるごと表の語なら開かない**
                # （項目48-VA・2026-09-07）。上の門は「同梱の外来語の表
                # （9,094語）に無いカタカナ」だけを見るので、
                # **日本語の表（778,340語）に在る長いカタカナ語**が
                # 素通りしていた。しかも解析はカタカナ語を**人名に割る**:
                #
                #     ショートライン → ショー|トラ|イン（人名:姓＋名＋一般）
                #     → 印 `ショートラ` → **`ショートに`**
                #
                # ★ ここは**字の種類で伸ばして表に聞く**（解析の切れ目は
                #   当てにならない）。
                if _kata_run_is_word(line, _ma, _mb):
                    _trace('異様', f'{_piece!r} → カタカナの連なりが'
                                   f'まるごと1語なので開かない（項目48-VA）')
                    continue
                _long_openable = True
                try:
                    _got = _reopen_odd_chunk(
                        _piece, store, tokenize_fn, dict_index=dict_index,
                        input_method=input_method, assemble=True)
                except Exception:
                    _got = None
                if _got and _got[0] and _got[0] != _piece:
                    _trace('異様', f'{_piece!r} → 印の範囲だけ開いて '
                                   f'{_got[0]!r}（項目48-MV）')
                    out.append((_ma, _mb, _got[0], _got[1]))
                    _long_done = True
                    break
            # **印の範囲では決まらなかったときだけ、連なりごと開く**
            # （項目48-OR(c)・2026-09-03）。`右田でブルクリック` は
            # 9字でこの枝に来るが、印（ブル｜クリック）の範囲だけを
            # 開いても `ブルクリック` は組めない。**うにさんの答えは
            # `右ダブルクリック`＝連なり全体**（みぎたでぶるくりっく →
            # みぎだぶるくりっく）。
            #
            # **開いてよい印が在ったときだけ**（`_long_openable`）。
            # 48-MV の理由をそのまま引き継ぐ——**ひらがなを含む印は、
            # 助詞や活用の尾を巻き込んでいる**ので開かない。
            # **測って受け止めた門**: これが無いと
            # `だいにんぎに行きます → 大人気にこうきます`
            # （正しく漢字で書いてある `行き` を読みに開き戻す）を
            # 11行作った（readcheck・2026-09-03 実測）。
            # 12字までに留める——長い連なりは切り出しがずれている
            # ときの手当てで、全体を開く根拠が薄くなる
            if not (_long_openable or _outside_broken):
                continue
            if _long_done or len(run) > 12:
                continue
        try:
            got = _reopen_odd_chunk(run, store, tokenize_fn,
                                    dict_index=dict_index,
                                    input_method=input_method,
                                    assemble=True)
        except Exception:
            got = None
        if got and got[0] and got[0] != run:
            _trace('異様', f'{run!r} → 連なりごと開いて {got[0]!r}'
                           f'（項目48-LA）')
            out.append((a0, j, got[0], got[1]))
    return out


def _compose_kana_run_fixes(line, store, dict_index=None, with_head=False):
    """
    **項目48-KX': かな連続を「語幹＋接尾」で漢字に組む**（2026-08-29）。

    `しゅうりょうじ` ＝ 終了（語彙の実績3）＋時 → **終了時**。
    いままでは敷き詰め（じ の1字が部品にならない）にも掛からず、
    そのまま先の かな連続の道が `しょうりょう` に**壊していた**
    （うにさんの一覧 31行目）。**変換が既定**（かなのまま打ちたい
    確信が無ければ漢字にする）の族なので、48-EX と同じ道具
    （`compose_suffix_surface`）で**先に**組む。

    門（実測から）:
      ・接尾は閉じた10個・2段まで・組めた表記がただ1つ
        （compose_suffix_surface 自身の門）
      ・**語幹は、語彙の実績2以上の漢字語**であること。辞書だけの
        語幹は当て推量——`高いものか` の `いものか` が
        `鋳物化`（鋳物＝辞書に在るだけ）に化けた（実測）

    実測（2026-08-29）: 中立文 8,000 で 0件。実機メモ 1,494行で
    立つのは6行——うち5行は**本来の変換そのもの**（さいだいか→
    最大化・さいしょうか→最小化・しゅうりょうじ→終了時）、
    残り1行（鋳物化）はこの語幹の門で消える。

    戻り値: [(始まり, 終わり, 組んだ表記, 分類), ...]
        `with_head=True` なら**語幹の終わり**（連続の中での位置）を
        5つ目に足す（項目48-MG。う挿入の門が「う が語幹の内側に
        落ちるか」を見るのに要る）。
    """
    if not line or dict_index is None:
        return []
    if os.environ.get('CN_KANA_SHIFT') == '0':
        return []
    out = []
    i, n = 0, len(line)
    while i < n:
        if not ('ぁ' <= line[i] <= 'ゖ' or line[i] == 'ー'):
            i += 1
            continue
        j = i
        while j < n and ('ぁ' <= line[j] <= 'ゖ' or line[j] == 'ー'):
            j += 1
        run = line[i:j]
        a0, i = i, j
        if len(run) < 4:
            continue
        if kana_is_mentioned(line, a0, j):
            continue            # 読みの注記・見出し（48-LN／48-OO）
        try:
            got = compose_suffix_surface(run, store, dict_index,
                                         want_parts=True)
        except Exception:
            got = None
        if not got:
            # **compose は2段剥がすので、こうりつか が か→化・りつ→率
            # と剥がれて語幹が こう まで削れて組めない**（項目48-LD で
            # 実測）。1段だけの剥がしを代わりに試す（語幹の実績2以上・
            # 表記がただ1つのときだけ——KX' の門と同じ強さ）
            try:
                _one = {f for f, _c, _p in _peel_one_suffix(
                    run, 2, store, dict_index=dict_index)}
            except Exception:
                _one = set()
            if len(_one) == 1:
                _f1 = _one.pop()
                if _f1 != run:
                    _trace('かな連続',
                           f'{run!r} → {_f1!r}（語幹（実績）＋接尾・'
                           f'1段の剥がし・項目48-KX\'）')
                    # 1段の剥がしは接尾が1字か2字かを言わないので、
                    # 語幹は**短いほう**（安全側）で答える。
                    out.append((a0, j, _f1, 'かな入力')
                               + ((max(0, len(run) - 2),)
                                  if with_head else ()))
            continue
        head, full, stem, _npeel = got
        if not full or full == run:
            continue
        try:
            _ents = [e for e in store.lookup(stem)
                     if e.get('surface') == head]
            solid = any(_is_conversion_anchor(e, stem) for e in _ents)
            # **索引の顔が語幹**（項目48-OJ。こうりつ → 効率）
            if not solid and _index_face(stem, store, dict_index) == head:
                solid = True
            # **広げた錨（2字の漢語）のときは、組んだ表記が
            # 「世の中で1語」であることまで要る**（項目48-MK）。
            # この道は接尾を足して**新しい複合語を作る**ので、錨だけを
            # 広げると `ちゅういか → **注意化**`（注意＝2字の漢語）が
            # 出る（48-KX' が「辞書だけの語幹は当て推量」と書いて
            # 塞いだ `鋳物化` と同じ穴・readcheck で実測）。
            # **表を「直す証拠」に使うのではなく「直し先が在ること」の
            # 条件に使う**（48-KF が入れなかった向きの逆）。
            if solid and not any(e.get('count', 0) >= 2 for e in _ents):
                import seed_japanese as _sj2
                if (_sj2.is_unit(full) is not True
                        and not _na_adj_ka_word(full)):
                    _trace('かな連続',
                           f'{run!r} → {full!r} は、語幹の錨が2字の漢語'
                           f'だけなのに直し先が1語として在らない'
                           f'（項目48-MK）ので採らない')
                    solid = False
        except Exception:
            solid = False
        if not solid:
            continue
        _trace('かな連続', f'{run!r} → {full!r}（語幹（実績）＋接尾で'
                           f'組んだ・項目48-KX\'）')
        out.append((a0, j, full, 'かな入力')
                   + ((len(stem),) if with_head else ()))
    return out


def _two_word_faces(v, lo_a, store):
    """
    かな連なり v を「語（実績 lo_a 以上）＋語（実績2以上）」に割る
    （48-LD の中身を持ち上げたもの・項目48-RW'・2026-09-05。
    `_kana_run_hand_fixes` の入れ子だったが、**直した読みを変換の道に
    通す** `_convert_fixed_kana_run` からも同じ判定を借りるため）。
    両半分とも**3字以上**（2字のかけらは 差し退化・再度医科 の junk を
    作った・実測）。どちらの半分も表記が優勢（2位の20倍）なときだけ。
    戻り値: {表記: 実績}
    """
    got = {}
    if store is None or not v:
        return got
    for sp in range(3, len(v) - 2):
        va, vb = v[:sp], v[sp:]
        try:
            sa = sorted(((e.get('count', 0), e.get('surface'))
                         for e in store.lookup(va)
                         if e.get('count', 0) >= lo_a
                         and e.get('surface')), reverse=True)
            sb = sorted(((e.get('count', 0), e.get('surface'))
                         for e in store.lookup(vb)
                         if e.get('count', 0) >= 2
                         and e.get('surface')), reverse=True)
        except Exception:
            continue
        if not sa or not sb:
            continue
        if len(sa) > 1 and sa[0][0] < 20 * sa[1][0]:
            continue
        if len(sb) > 1 and sb[0][0] < 20 * sb[1][0]:
            continue
        if not any(is_kanji(c) for c in sa[0][1]) \
                or not any(is_kanji(c) for c in sb[0][1]):
            continue
        face = sa[0][1] + sb[0][1]
        got[face] = max(got.get(face, 0), min(sa[0][0], sb[0][0]))
    return got


def _known_whole_word_faces(reading, dict_index):
    """同じ読みの既知の一語。辞書の表記順位を維持する。"""
    from seed_japanese import is_unit
    lookup = getattr(dict_index, 'surfaces_for_reading', None)
    if not callable(lookup):
        return []
    return [surface for surface in lookup(reading)
            if surface and any(is_kanji(c) for c in surface)
            and is_unit(surface) is True]


def _known_suffix_word_faces(reading, store, dict_index):
    """48-VZ: 元の読みと補正候補に同じ語幹＋接尾の裏付けを使う。"""
    from seed_japanese import is_unit
    got = {}
    for suffix, tail_surface in _SUFFIX_SURFACE.items():
        if len(reading) <= len(suffix) + 1 or not reading.endswith(suffix):
            continue
        stem = reading[:-len(suffix)]
        surfaces = {e.get('surface') for e in store.lookup(stem)}
        lookup = getattr(dict_index, 'surfaces_for_reading', None)
        if callable(lookup):
            surfaces.update(lookup(stem))
        for surface in surfaces:
            if not surface or not all(is_kanji(c) for c in surface):
                continue
            full = surface + tail_surface
            if is_unit(full) is True or _na_adj_ka_word(full):
                got[(full, len(stem))] = (full, 1, len(stem))
    return sorted(got.values())


def _kana_run_hand_fixes(line, store, dict_index=None, input_method='kana'):
    """
    項目48-LD／48-VZ: 独立したかな連続の隣接キー・濁音の置換を検査。

    4〜8字で、引用・読みの注記・既知語・完成した活用・機能語の列を除く。
    元の読みと候補の両方で、既存辞書と同梱語彙の語幹＋接尾の根拠を共有する。
    新しい語幹＋接尾の補正は元の読みが語彙にない場合だけ。
    手が接尾辞自体を作る候補は採らず、指定の入力方式で隣接キーを探す。
    候補は普通の一語も合わせ、既知の単位・既存の一般性・費用で選ぶ。
    複数あることを理由に紫だけにはしない。
    既存の2語への分割経路の入口・敷居は維持する。

    戻り値: [(始まり, 終わり, 直した表記, 分類), ...]
    """
    if not line or dict_index is None:
        return []
    if os.environ.get('CN_LD') == '0':
        return []
    try:
        from kana_layout import nearby_candidates as _near
    except Exception:
        return []
    out = []
    i, n = 0, len(line)
    while i < n:
        if not ('ぁ' <= line[i] <= 'ゖ' or line[i] == 'ー'):
            i += 1
            continue
        j = i
        while j < n and ('ぁ' <= line[j] <= 'ゖ' or line[j] == 'ー'):
            j += 1
        run = line[i:j]
        a0, i = i, j
        if not (4 <= len(run) <= 8):
            continue
        prev = line[a0 - 1] if a0 > 0 else ''
        nxt = line[j] if j < n else ''
        if any(c and (is_kanji(c) or 'ァ' <= c <= 'ヺ')
               for c in (prev, nxt)):
            continue
        if kana_is_mentioned(line, a0, j) or _is_quoted_whole(line, a0, j):
            continue            # 読み・引用として提示した綴りは、この推定で読み替えない。
        # 48-VZ: 候補を探す前に、既知語・活用として正常な入力を除く。
        from pos_grammar import explain_kana_run
        if explain_kana_run(run, before_kanji=False, bare_head=True, stems_only=True):
            continue
        if (_known_whole_word_faces(run, dict_index)
                or _known_suffix_word_faces(run, store, dict_index)):
            continue
        ents0 = store.lookup(run)
        base_count = max([e.get('count', 0) for e in ents0] or [0])
        if any(e.get('count', 0) >= 2 for e in ents0):
            continue
        if _peel_one_suffix(run, 2, store, dict_index=dict_index):
            continue            # 組める＝正しい形（48-KX' の持ち場）
        try:
            if _is_functional_strict(run):
                continue
        except Exception:
            pass
        # **同じ字が続く連なりは重複の道の持ち場**（めもちちょう →
        # めもちょう が正解なのに、ち→と の手が 目元帳 を作った・実測）
        if any(run[x] == run[x + 1] for x in range(len(run) - 1)):
            continue

        def _two_word(v, lo_a):
            """語（実績 lo_a 以上）＋語（実績2以上）。判定は
            `_two_word_faces`（持ち上げた・項目48-RW'）の1本——
            「両半分とも漢字を含む表記」（まるいかっこ → 丸いカッコ・
            ながい → 長い の当て推量を作らない）もそちらに在る。"""
            return _two_word_faces(v, lo_a, store)

        # **そのままで「語＋語」に割れて読める形は、壊す対象ではない**
        # （ひきつぎしりょう ＝ ひきつぎ82＋しりょう21。手の版は
        #   ぎ→ぐ で 引き継ぐ資料 に壊した・実測）。⑤変換が既定
        # なので、割り方と表記がただ1つなら**そのまま漢字に組む**。
        # 複数あるなら触らない（正しいかなを漢字で当て推量しない）
        as_faces = _two_word(run, 2)
        if as_faces:
            if len(as_faces) == 1:
                fix0 = next(iter(as_faces))
                if fix0 != run:
                    _trace('かな連続',
                           f'{run!r} → {fix0!r}（そのまま語＋語で'
                           f'組んだ・⑤変換が既定・項目48-LD）')
                    out.append((a0, j, fix0, 'かな入力'))
            continue
        # 48-QG'で回数を廃止したため、旧来の2語候補はこの敷居を越えない。
        # 48-VZの語幹＋接尾候補は、回数でなく辞書と語としての裏付けを使う。
        # 2語候補側の入口をここで広げることはしない。
        need = max(10, 20 * base_count)
        faces = {}
        seen = set()
        for k, ch in enumerate(run):
            alts = []
            try:
                alts = [alt for alt, d in _near(ch, input_method=input_method)
                        if alt != ch and d <= 1.0]
            except Exception:
                pass
            _b = _LC_UNVOICED.get(ch)
            if _b:
                try:
                    alts.extend(alt for alt, d in _near(_b, input_method=input_method)
                                if alt != ch and d <= 1.0)
                except Exception:
                    pass
            for alt in alts:
                v = run[:k] + alt + run[k + 1:]
                if v == run or v in seen:
                    continue
                seen.add(v)
                # 先(2): 語幹＋接尾（手が接尾を作った形は採らない）
                for _full, _sc, _sst in (_known_suffix_word_faces(v, store, dict_index)
                        if base_count == 0 else []):
                    if _full != run and k < _sst:
                        _old = faces.get(_full)
                        if _old is None or _sc > _old[1]:
                            faces[_full] = (v, _sc)
                # 先(3): 手の入っていない後ろ半分＋前半分の2語の組
                #        （48-IU「読みを変えていない側」の かな版。
                #        両半分3字以上——2字のかけらは junk を作る）
                for sp in range(max(3, k + 1), len(v) - 2):
                    va, vb = v[:sp], v[sp:]
                    sb = sorted(((e.get('count', 0), e.get('surface'))
                                 for e in store.lookup(vb)
                                 if e.get('count', 0) >= 2
                                 and e.get('surface')
                                 and any(is_kanji(c)
                                         for c in e['surface'])),
                                reverse=True)
                    if not sb:
                        continue
                    if len(sb) > 1 and sb[0][0] < 20 * sb[1][0]:
                        continue        # 後ろ半分の表記が競る
                    for e in store.lookup(va):
                        s = e.get('surface') or ''
                        if s and e.get('count', 0) >= need \
                                and any(is_kanji(c) for c in s):
                            _f2 = s + sb[0][1]
                            _old = faces.get(_f2)
                            if _old is None or e['count'] > _old[1]:
                                faces[_f2] = (v, e['count'])
        if not faces:
            continue
        # 接尾辞付きの形だけで競わせず、同じ置換範囲の普通の一語も比較する。
        # 新しい補正入口にはせず、上で候補が立った入力にだけ加える。
        whole_order = {}
        for reading in sorted(seen):
            for order, surface in enumerate(_known_whole_word_faces(reading, dict_index)):
                whole_order[(surface, reading)] = order
                if surface not in faces:
                    faces[surface] = (reading, 1)
        # 48-VZ: 回数ではなく、既存の語としての裏付け・費用で順位を決める。
        # ①を通った未知の入力なので、候補数を理由に補正を止めない。
        from seed_japanese import is_unit
        def _face_rank(item):
            surface, (reading, _) = item
            cost = _table_cost(surface)
            return (is_unit(surface) is not True,
                    -_general_count(reading, store),
                    _kango_tier_of(surface),
                    cost if cost is not None else float('inf'),
                    whole_order.get((surface, reading), 1000), surface, reading)
        ranked = sorted(faces.items(), key=_face_rank)
        fix, (v, face_cnt) = ranked[0]
        _trace('かな連続', f'{run!r} → {fix!r}（読みの1手 {v!r}・'
                           f'語の裏付けと費用で選択・項目48-VZ）')
        out.append((a0, j, fix, 'かな入力'))
    return out


def _misplaced_dakuten_fixes(line, store):
    """
    **設計39: 場違いな濁点・半濁点を、隣のキーの通常字に置き換えて戻す**
    （項目48-JP・2026-08-25。うにさんの骨格「最初に文が異様なのかどうかを
    正しく判定する→平仮名に開く→隣接キーや脱字などチェックして、
    本来の入力を探る」の、設計38 に続く2例目）。

    かな入力では濁点が独立したキーなので、隣を叩くと**印だけが取り残される**:

        もじれつ の れ を隣の ゛ で打つ → もじ゛つ

    `normalize_marks` は、**かなの直後にあって合成できない印**を
    「濁点キーの誤打」として**落とす**（もじ゛つ → もじつ）。
    落とすのは正しい後始末だが、**材料も一緒に消える**ので、
    そこから先の探索は `もじつ` を直そうとして届かない
    （隣接キーの台帳・項目48-JN で「別のもの」に数えられていた形）。

    **異様の判定が構造だけで立つ**のが、この族の良いところ——
    正しい日本語に「付けられない字の後ろの濁点」は存在しない。
    だから、落とす前に**隣のキーで戻せないか**を見る。

    **`normalize_marks` より前に居なければならない**（引き継ぎの
    実装方針1）。落とす決まりそのものは normalize_marks が持ち、
    こちらは `dropped=` でその位置を教えてもらう——**同じ判定を
    2か所で書かない**（学び22）。

    受け入れは**ただ1つのときだけ**（設計38 と同じ）。土俵には
    **いまの後始末（印を落とす）も一緒に載せる**——落としたほうでも
    語になるなら、どちらとも決められないので身を引き、今までどおりに
    する（「壊さない ＞ 直る」）。

    戻り値: [(開始, 終了, 直したかな), ...]（印を含むかな連続ごと）
    """
    try:
        from kana_layout import nearby_candidates
        from morphology import (DAKUTEN_MARKS, HANDAKUTEN_MARKS,
                                normalize_marks, _DAKUTEN_COMPOSE,
                                _HANDAKUTEN_COMPOSE)
    except Exception:
        return []
    marks = set(DAKUTEN_MARKS) | set(HANDAKUTEN_MARKS)
    if not any(ch in marks for ch in line):
        return []
    # **落とされる印だけ**を見る。行頭の印・記号の後ろの印
    # （うにさんの `@ ⇒ ゛`）は落とされないので、ここにも出てこない。
    # 打つ順番の入れ替え（項目48-AO）で説明が付く印も出てこない
    # （`swap_across=True`。あちらが先・学び38）。
    dropped = []
    try:
        normalize_marks(line, swap_across=True, dropped=dropped)
    except Exception:
        return []
    if not dropped:
        return []

    def _run_of(i):
        """印を含むかな連続の範囲。"""
        s = i
        while s > 0 and (is_hiragana(line[s - 1]) or line[s - 1] in marks):
            s -= 1
        e = i + 1
        while e < len(line) and (is_hiragana(line[e]) or line[e] in marks):
            e += 1
        return s, e

    def _ok(fixed):
        """直した連続が語として立つか（印の合成は normalize に任せる）。"""
        try:
            merged = normalize_marks(fixed)
        except Exception:
            merged = fixed
        if any(c in marks for c in merged):
            return False        # 説明の付かない印が残っている
        return _kana_run_backed(merged, store)

    out = []
    used = set()
    for i in dropped:
        rs, re_ = _run_of(i)
        if (rs, re_) in used:
            continue            # 同じ連続に2つ以上——決められない
        if sum(1 for k in dropped if rs <= k < re_) != 1:
            used.add((rs, re_))
            continue
        used.add((rs, re_))
        run = line[rs:re_]
        k = i - rs
        table = (_HANDAKUTEN_COMPOSE if run[k] in HANDAKUTEN_MARKS
                 else _DAKUTEN_COMPOSE)
        cands = set()
        # (a) 印そのものを、隣のキーの通常字へ（もじ゛つ → もじれつ）
        for nb, _d in nearby_candidates(run[k], max_dist=1.05,
                                        include_phonetic=False):
            if nb != run[k] and nb not in marks and is_hiragana(nb):
                fixed = run[:k] + nb + run[k + 1:]
                if _ok(fixed):
                    cands.add(fixed)
        # (b) 前の字のほうが誤打で、印は正しかった形
        #     （印を受け取れる隣のキーへ戻すと語になる）
        if k > 0:
            for nb, _d in nearby_candidates(run[k - 1], max_dist=1.05,
                                            include_phonetic=False):
                composed = table.get(nb)
                if composed and nb != run[k - 1]:
                    fixed = run[:k - 1] + composed + run[k + 1:]
                    if _ok(fixed):
                        cands.add(fixed)
        # (c) **いまの後始末（印を落とす）も同じ土俵に載せる**。
        #     落としても語になるなら決められない——身を引く。
        drop = run[:k] + run[k + 1:]
        if _ok(drop):
            cands.add(drop)
        if len(cands) != 1:
            continue
        fixed = cands.pop()
        if fixed == drop:
            continue            # いまと同じ。normalize に任せる
        _trace('かな連続', f'{run!r} → 場違いな印（{run[k]!r}）を'
                           f'隣のキーで戻すと {fixed!r}（設計39）')
        out.append((rs, re_, fixed))
    return out


def _misplaced_long_vowel_fixes(line, store, decisions=None):
    """
    **設計40: 伸ばし棒（ー）の打ち間違いを、隣のキーで戻す**
    （項目48-JS・2026-08-26。【Opus への実装方針】2番「ー と隣キーの相互」）。

    かな配列では `ー` の隣が **ろ(0.2)・れ・け・む・め** なので、
    この6つは互いに打ち間違えやすい。48-JN の台帳（初期語彙の読みを
    隣のキーで崩す）で、ー が絡む崩しだけを数えると:

        ー→他  75件（直った 48 ／ そのまま 13 ／ **別のもの 14**）
        他→ー  36件（直った  2 ／ そのまま 34 ／ 別のもの  0）

    **向きで形が違う**ので、門も別に置く。

    **(A) 連続の先頭の `ー`**（他→ー の側）。
        `ー` は**直前のかなの母音を伸ばす印**なので、**連続の頭には
        立てない**（48-EL の「長音の書き分け」がその裏返し）。
        設計38 の小書きと同じ**構造だけで立つ異様**——
        `ーいかく` `ーんらく` `ーもちょう` `ーーす` は日本語ではない。
        隣のキーの通常字に戻して、語になるものが**ただ1つ**なら採る。

    **(B) `ー` のはずが隣のキーになった**（ー→他 の側）。
        `ぺめすと` は**構造としては可能**なので、(A) のような
        「不可能」の印は立たない。代わりに3つで締める:

            ・**その連続が、それ自体では語として立たない**
              （`くれる` `かれ` のような正しい語には触らない）
            ・戻し先が**カタカナを含む表記**（`ー` を持つ語は外来語か
              `ローマ字` の類。48-IT の「外来語の印」と同じ考え）
            ・**ただ1つ**のときだけ（2か所以上で語になったら決めない）

        頭の1字は (A) が受け持つので、ここでは **i>0 だけ**見る。

    直した行は**丸ごと補正し直す**（設計39 と同じ形）。そうしないと
    `かろそる` が `かーそる` のまま止まって、**いままで `カーソル` に
    なっていたものが平仮名に戻る**（＝直っているのに悪くなる）。

    **止まること**: (A) は頭の `ー` を1つ減らす。(B) は「語として
    立たない連続」を「立つ連続」に変えるので、どちらも同じ連続では
    二度は成立しない。

    戻り値: [(開始, 終了, 直したかな), ...]（かな連続ごと）
    """
    if 'ー' not in line and not any(c in 'ろれけむめ' for c in line):
        return []
    try:
        from kana_layout import nearby_candidates
    except Exception:
        return []
    near = [nb for nb, _d in nearby_candidates('ー', max_dist=1.05,
                                               include_phonetic=False)
            if nb != 'ー' and is_hiragana(nb)]
    if not near:
        return []

    def _runs():
        i, n = 0, len(line)
        while i < n:
            if is_hiragana(line[i]) or line[i] == 'ー':
                j = i
                while j < n and (is_hiragana(line[j]) or line[j] == 'ー'):
                    j += 1
                # **前がカタカナ・漢字なら、頭の `ー` はその語のもの**
                # （`レディーまで` の `ー` は レディー の一部）。
                # ここを外すと `ーまで` を連続の頭の伸ばし棒と読んで、
                # **正しいカタカナ語から `ー` を削る**（fpcheck 誤検知
                # 5件・2026-08-26 に実測して足した門）。
                while (i < j and line[i] == 'ー' and i > 0
                       and (is_katakana(line[i - 1]) or is_kanji(line[i - 1])
                            or is_hiragana(line[i - 1]))):
                    i += 1
                if i < j:
                    yield i, j
                i = j
            else:
                i += 1

    def _loan(fixed):
        """語として立ち、かつ**カタカナを含む表記**に届くか。"""
        try:
            entries = store.lookup(fixed)
        except Exception:
            return False
        return any(e.get('count', 0) >= 2
                   and any(is_katakana(c) for c in (e.get('surface') or ''))
                   for e in entries)

    def _written(run, fixed):
        """
        画面に出す形。**表記がカタカナだけの外来語ならカタカナで書く**
        （項目48-r・うにさんの指定。`dakuten_typo_fix` と同じ決まりを
        同じ道具（`katakana_for_hiragana`）で通す——別の決まりを作らない）。

        これを忘れると、**いままで `カーソル` になっていた `かろそる` が
        `かーそる` で止まる**（＝直っているのに悪くなる）。実測で気づいた。
        """
        try:
            from loanword import katakana_for_hiragana
            kata = katakana_for_hiragana(fixed, store, min_length=3)
        except Exception:
            kata = None
        out = kata or fixed
        if decisions is not None:
            try:
                if decisions.blocks(run, out):
                    return None     # 「この補正は不要」と言われている
            except Exception:
                pass
        return out

    out = []
    for rs, re_ in _runs():
        run = line[rs:re_]
        if len(run) < 3:
            continue                    # 1字動かすと形が残らない
        cands = set()
        if run[0] == 'ー':
            # (A) 頭の ー は立たない。ただし **ー だけの連続**は
            # 区切り線や引き伸ばしなので触らない。
            if all(c == 'ー' for c in run):
                continue
            for nb in near:
                fixed = nb + run[1:]
                if _kana_run_backed(fixed, store):
                    cands.add(fixed)
            drop = run[1:]              # 印を落とす道も土俵に載せる
            if _kana_run_backed(drop, store):
                cands.add(drop)
            if len(cands) == 1:
                one = cands.pop()
                if one == drop:
                    continue            # 落とすのは直しではない（設計39 と同じ）
                fixed = _written(run, one)
                if fixed and fixed != run:
                    _trace('かな連続', f'{run!r} → 頭の伸ばし棒を隣のキーで'
                                       f'戻すと {fixed!r}（設計40-A）')
                    out.append((rs, re_, fixed))
            continue
        # (B) その連続がそれ自体で語なら触らない
        if _kana_run_backed(run, store):
            continue
        # **できあがっている塊には走らせない**（★★④・項目48-PB'・
        # 2026-09-03）。この道には**①（異様か判定）の入口が無かった**
        # （学び22）。うにさんの育ちで `食べれる → **食ベール**`・
        # `決めれる → **決メール**`——`食べ＋れる`（ら抜き）は
        # 文法として決まった形なのに、`べれる` の `れ` を伸ばし棒に
        # 戻すと `ベール`（外来語）になるので通っていた。
        # 判定は `pos_grammar.explain_kana_run` ただ1つ（48-GN）——
        # ①と同じ物差しで、**直前の漢字も渡す**（食＋べれる）
        try:
            import pos_grammar as _pg40
            _prev40 = line[rs - 1] if rs > 0 else ''
            _after40 = bool(_prev40) and (is_kanji(_prev40)
                                          or is_katakana(_prev40))
            _stem40 = ''
            if _after40:
                _k40 = rs
                _same40 = is_kanji if is_kanji(_prev40) else is_katakana
                while _k40 > 0 and _same40(line[_k40 - 1]):
                    _k40 -= 1
                _stem40 = line[_k40:rs]
            if _pg40.explain_kana_run(
                    run, after_kanji=_after40,
                    before_kanji=bool(re_ < len(line)
                                      and is_kanji(line[re_])),
                    kanji_stem=_stem40,
                    is_word=lambda f: (
                        len(f) >= 2
                        and bool(store.reading_of(f)))):
                continue
        except Exception:
            pass
        for k in range(1, len(run)):
            if run[k] == 'ー' or run[k] not in near:
                continue
            fixed = run[:k] + 'ー' + run[k + 1:]
            if _loan(fixed):
                cands.add(fixed)
        if len(cands) == 1:
            fixed = _written(run, cands.pop())
            if fixed and fixed != run:
                _trace('かな連続', f'{run!r} → 隣のキーを伸ばし棒に戻すと '
                                   f'{fixed!r}（設計40-B）')
                out.append((rs, re_, fixed))
    return out


_ONE_EDIT_KANA = tuple(chr(c) for c in range(0x3041, 0x3097)) + ('ー',)


def _one_edit_words(run, store, limit=None):
    """
    **1手で届く語を、族ごとに全部あげる**（項目48-JT・2026-08-26）。

    「打ち間違いは1か所」という前提で、**どの族の1手でも**同じ土俵に
    載せる:

        頭    連続の**頭の1字**を隣のキーへ
        置換  頭以外の1字を隣のキーへ
        濁点  濁点・半濁点の付け外し
        脱字  かなを1字入れる
        余分  1字落とす
        入替  隣り合う2字を入れ替える

    **なぜ全部要るのか。** 頭の族だけで決めると、`さいけん`（＝さいげん
    の濁点落ち）を `はいけん` に、`おぐ`（＝およぐ の脱字）を `すぐ` に
    してしまう。**別の族の1手のほうが正しい**のに、こちらが先に掴む。
    実測で readcheck の化けが **+59** になった（2026-08-26。設計38 が
    48-JN §2 で踏んだのと同じ形）。

    戻り値: {直した並び: 族の名前}
    """
    try:
        from kana_layout import nearby_candidates, DAKUTEN_BASE
    except Exception:
        return {}
    global _ONE_EDIT_VOICED
    try:
        voiced = _ONE_EDIT_VOICED
    except NameError:
        voiced = {}
        for v, base in DAKUTEN_BASE.items():
            voiced.setdefault(base, v)
        _ONE_EDIT_VOICED = voiced
    handaku = {'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ'}
    out = {}

    def add(fixed, family):
        if fixed != run and _kana_run_backed(fixed, store):
            out.setdefault(fixed, family)
            return True
        return False

    for nb, _d in nearby_candidates(run[0], max_dist=1.05,
                                    include_phonetic=False):
        if nb != run[0] and is_hiragana(nb):
            add(nb + run[1:], '頭')
    if limit == '頭':
        return out
    for i in range(1, len(run)):
        for nb, _d in nearby_candidates(run[i], max_dist=1.05,
                                        include_phonetic=False):
            if nb != run[i]:
                add(run[:i] + nb + run[i + 1:], '置換')
    for i, ch in enumerate(run):
        for tbl in (voiced, handaku, DAKUTEN_BASE):
            v = tbl.get(ch)
            if v:
                add(run[:i] + v + run[i + 1:], '濁点')
    for i in range(len(run) + 1):
        for k in _ONE_EDIT_KANA:
            add(run[:i] + k + run[i:], '脱字')
    for i in range(len(run)):
        if len(run) - 1 >= 2:
            add(run[:i] + run[i + 1:], '余分')
    for i in range(len(run) - 1):
        sw = list(run)
        sw[i], sw[i + 1] = sw[i + 1], sw[i]
        add(''.join(sw), '入替')
    return out


# **設計41 は測って、入れなかった**（項目48-JT・2026-08-26）。
#
# 頭の1字の隣接置換は、**族をまたいだ「1手はこれだけ」**で締めれば
# ほとんど決まる（下の数字）。ところが**この直りは readcheck に出ない**——
# readcheck の崩し方は 濁点・重複・脱字・順序違い の4族で、
# **隣接キーの置換が入っていない**。つまりあちらでは
# **得は測れず、損だけが出る**。
#
#     初期・CN_HEAD_MIN=3   readcheck 直った 1856→1853 / **化けた 92→97**
#                           先頭の台帳 569(30%)→**1679(91%)** / 別 64→10
#     初期・CN_HEAD_MIN=5   readcheck 直った 1855 / 化けた 93
#                           台帳 741(40%) / 別 54
#     初期・CN_HEAD_MIN=6   readcheck **差0** / 台帳 617(33%)（＝ほぼ効かない）
#     **育ちでは どの値でも readcheck 差0**（候補が2つ以上になり身を引く）
#     実機メモ memodiff は **どの値でも差0**／fpcheck **0**
#
# 増えた化け5件は、**正しい語が語彙に無い**行だった
# （`うるい`→かるい。正解の `うるさい` が初期語彙に無い）。
# 「1手がこれだけ」は**語彙が薄いほど嘘をつく**。
#
# 足りないのは受け入れの証拠のほうで、門ではない——
# 設計37 が待っている「**開く前の異様の判定**」と同じ場所。
# **入れるならその材料が要る。** 切り替えだけ残す。
_DESIGN41_ON = (os.environ.get('CORRECTNOTE_DESIGN41') == '1')
_DESIGN41_MIN = int(os.environ.get('CN_HEAD_MIN', '3'))


# **助詞をはさまない、どれも単独では立っていない名詞の連なり**
# ——切り直すと語＋助詞で読み切れるなら、そちらへ寄せる（設計42）。
_D42_PARTICLE = frozenset('にでとがをはもへやかのねよ')

# **異様と判定したのに、決める先が無かった範囲**（項目48-JW・2026-08-26。
# 項目48-KS で **唯一の台帳**に格上げ・2026-08-29）。
# うにさんの指定:「**補正できないと判断する場合でも、紫の色は付けます。**
# 紫を付けるものは候補が多かろうが何かしらに補正してしまうので紫が残らない
# ことが多いですが、**それでも補正先がない場合は紫だけが残ります**」。
# 行ごとに使い切る（`_HOMOPHONE_UNSURE` と同じ形）。
#
# **積む資格**（Fable の判断・2026-08-29・`Fableの判断_紫の台帳と品詞_20260829.md`）:
#   ・**入口が異様判定になっている道だけ**が積む（いまは設計42）。
#   ・到達性の道（外来語・同じキー・窓——「表に届かなかった」）は
#     積まない。「届かない」は「異様」を意味しない。
#   ・文脈の道（同音）は形の異様ではないので、ここではなく
#     `_HOMOPHONE_UNSURE`（①-b の台帳）のまま。
# 中身は (開始, 終了) の範囲。設計42 以外の道が積むときも同じ形で積む。
_ODD_PENDING = []
_D42_ODD = _ODD_PENDING     # 旧名（第49回の記録が引く名前。同じ実体）


def _d42_known_unit(surface, store, dict_index=None):
    """その表記は**世の中で1語**か（語彙・辞書・778,340語の集合）。"""
    if not surface or len(surface) < 2:
        return False
    try:
        if store.reading_of(surface):
            return True
    except Exception:
        pass
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(surface):
                return True
        except Exception:
            pass
    try:
        import seed_japanese as _sj
        if _sj.is_unit(surface):
            return True
    except Exception:
        pass
    return False


def _d42_free_kanji(run):
    """
    **何にでも自由に付く1字**が連なりに居るか（項目48-JW）。

    位置・方向（上下左右内外中…）・画面の区画（行欄列枠桁段頁）・
    形や集合（塊群層列束片団帯）は、**閉じた文法の類**であって
    語の一覧ではない（48-HT／48-IS／48-JG）。`欄内` `前の` `用紙縦` は
    ふつうの略記で、異様ではない。**表は `oddness` のものを借りる。**
    """
    try:
        import oddness as _odd
        free = (_odd._POSITION_KANJI | _odd._LAYOUT_KANJI
                | _odd._AGGREGATE_KANJI)
    except Exception:
        return False
    return any(len(t[0]) == 1 and t[0] in free for t in run)


def _d42_has_yougen(text, tokenize_fn):
    """切り直した形に**用言（動詞・形容詞）**が居るか（項目48-SW）。"""
    if not text or tokenize_fn is None:
        return False
    try:
        toks = list(tokenize_fn(text) or ())
    except Exception:
        return False
    return any((t[1] or '').startswith(('動詞', '形容詞')) for t in toks)


def _d42_covered(text, store):
    """
    切り直した形が、**語彙の語と1字の助詞だけ**で埋まっているか。

    `に解析` = に(助詞) + 解析(語) ○ ／ `と切っそう` = と + 切っ + そう
    のように語で埋まらない並びは × （`そう` が語として立たない）。
    """
    i, n = 0, len(text)
    got_word = False
    while i < n:
        if text[i] in _D42_PARTICLE:
            i += 1
            continue
        hit = 0
        for L in range(min(8, n - i), 1, -1):
            try:
                if store.reading_of(text[i:i + L]):
                    hit = L
                    break
            except Exception:
                break
        if not hit:
            return False
        got_word = True
        i += hit
    return got_word


def _d42_one_word_somehow(run, reading, store, dict_index=None):
    """
    その連なりは、**どれかの読み方で1語になる**か（同じ土俵の勝ち負け）。

    `時ッ層` は確定した読みが `ときっそう` だが、`時` を `じ` と読めば
    `じっそう` ＝ **実装**。1語で読み切れる形のほうが証拠が固いので、
    そちらの道に譲る（**身を引くのではなく、勝ったほうを採る**）。
    """
    from morphology import katakana_to_hiragana

    def _known(r):
        try:
            if store.lookup(r):
                return True
        except Exception:
            pass
        if dict_index is not None:
            try:
                if dict_index.surfaces_for_reading(r):
                    return True
            except Exception:
                pass
        return False

    if _known(reading):
        return True
    combos = ['']
    for t in run:
        opts = [katakana_to_hiragana(t[2] or t[0])]
        if dict_index is not None:
            try:
                for r in dict_index.readings_for_surface(t[0]):
                    r = katakana_to_hiragana(r)
                    if r not in opts:
                        opts.append(r)
            except Exception:
                pass
        if len(t[0]) == 1:
            try:
                import kanji_readings as _kr
                for r in _kr.readings_of(t[0]):
                    r = katakana_to_hiragana(r)
                    if r not in opts:
                        opts.append(r)
            except Exception:
                pass
        new = []
        for pre in combos:
            for o in opts[:4]:
                if len(new) >= 12:
                    break
                new.append(pre + o)
        combos = new
        if not combos:
            return False
    for c in combos:
        if c != reading and _known(c):
            return True
    return False


def _resegment_fixes(line, tokenize_fn, store, dict_index=None,
                     decisions=None):
    """
    **設計42: 読みを、語の境目で切り直す**（項目48-JV・2026-08-26）。

    うにさんの的「**切り替え時二階席が走っていて ⇒ 切り替え時に解析が
    走っていて**」。IME が**同じ読みを別の場所で切った**形で、
    打ち間違いは1つも無い。読みは合っているのに境目が違う。

    ### 異様の判定（**開く前に立てる**）

    うにさんの決まり「**異様であれば何かしらの補正をします。そのままには
    しません**」（48-JG・2026-08-26 再指定「**原文が異様であり、候補が
    複数の時は、何かしらに決める**」）。だから先に**異様かどうか**を
    構造だけで決める。設計38（場違いな小書き）・設計40（連続の頭の `ー`）
    と同じ形:

        ・**助詞をはさまない名詞の連なり**（2〜4語・2〜8字・漢字を含む）
        ・**どの語も単独では立っていない**——1字か、辞書に無い。
          `二階席` は 二/階/席 でどれも1字（＝語として立っていない）。
          `タブ機能` は `機能` が立つので**触らない**
        ・**連なり全体も辞書に無い**（`京都` `料理屋` `機能` は通らない）
        ・**数え方は異様ではない**——数詞＋助数詞で閉じる連なり（`二本`）と、
          直前が数詞の連なり（`1行分`）は触らない（`oddness.can_join` の
          (4) と同じ考え）
        ・**接尾だけの連なりでもない**（中身のある名詞が要る）

    ### 決める（**候補が複数でも身を引かない**）

        ・**どれかの読み方で1語になるなら、そちらが勝ち**——
          `時ッ層` は `じっそう`＝`実装` の道に譲る。
          **長いほうが1語になるなら、短く切り出さない**
        ・残ったら読みの DP（`kana_to_kanji_where_possible`）で切り直し、
          **語彙の語＋1字の助詞だけで読み切れる**形なら採る

    ### 測った（項目48-JV。**初期を先に**）

        初期 実機メモ1,342行 **2か所**（どちらも的）／ fpcheck 1,500文 **0**
        育ち 実機メモ1,342行 **2か所**（同じ）／ fpcheck 1,500文 **0**

    判定を付けない DP は 初期2,431・育ち4,350か所を書き換える（48-JU §2）。
    **門ではなく、異様判定が桁を落とした。**

    戻り値: [(始まり, 終わり, 直した形), ...]
    """
    if not line or tokenize_fn is None:
        return []
    try:
        from halfwidth import kana_to_kanji_where_possible as _cut
    except Exception:
        return []
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return []
    from morphology import katakana_to_hiragana
    blocks = getattr(decisions, 'blocks', None) if decisions else None
    out = []
    used = []
    for i in range(len(tokens)):
        for L in (4, 3, 2):
            if i + L > len(tokens):
                continue
            run = tokens[i:i + L]
            pos = [(t[1] or '') for t in run]
            if not all(p.startswith('名詞') for p in pos):
                continue
            # どの語も単独では立っていないこと
            if any(_d42_known_unit(t[0], store, dict_index) for t in run):
                continue
            # 数え方は異様ではない
            if '数' in pos[-1] or '助数詞' in pos[-1]:
                continue
            # （頭が数詞の連なり〔`十六茶`＝十｜六｜茶〕を数え方として外すのは
            #   **測って外した**——設計42 の的 `二階席 → に解析` も 二｜階｜席 で
            #   頭が数詞。`十六茶` の紫は残す・項目48-SW'）
            if i > 0 and '数' in (tokens[i - 1][1] or ''):
                continue
            if not any('接尾' not in p and '数' not in p
                       and '非自立' not in p for p in pos):
                continue
            # **固有名詞が混じっていたら判定しない**（`田無駅`
            # `玉子五十個入`の`入`）。48-JL の「姓の保護」と同じ考え——
            # 辞書に無くて当然の名前を異様と呼ばない。
            # ★★ ただし**信用できる札のときだけ**（項目48-RN）——
            # `右田`・`ブル` のような当て推量で降りると、48-OR が
            # ①で開けた道がここで塞がる（学び22）。
            # **1字の名詞＋接尾は語の作り**（項目48-SW・2026-09-06。
            # 車用・紙製・目印。`車用 → 来る迷う`・`腰楽 → 越しらく` は
            # 育ちで実測。1字だから「立っていない」のではなく、接尾が
            # 付いて1語になっている）
            # **読みの立つ名詞＋接尾は語の作り**（48-SW'。`二つ目`・`三つ目`
            # は 二つ(名詞)＋目(接尾) で紫が立っていた。1字に限らない）
            if (L == 2 and '接尾' in pos[1] and run[0][0]
                    and (len(run[0]) <= 5 or run[0][5])):
                continue
            if _has_trusted_proper_noun(run, store, dict_index):
                continue
            # **何にでも自由に付く1字**（位置・区画・集合）が居るなら
            # 異様ではない（`欄内` `前の`）。**表は `oddness` のものを
            # 借りる**——同じ意味の名簿を2つ作らない（決まりごと）。
            if _d42_free_kanji(run):
                continue
            surface = ''.join(t[0] for t in run)
            if not (2 <= len(surface) <= 8):
                continue
            if not any(is_kanji(c) for c in surface):
                continue
            if _d42_known_unit(surface, store, dict_index):
                continue
            reading = ''.join(katakana_to_hiragana(t[2] or t[0]) for t in run)
            if not reading or not all(is_hiragana(c) or c == 'ー'
                                      for c in reading):
                continue
            # **長いほうが1語になるなら、短く切り出さない**
            if _d42_one_word_somehow(run, reading, store, dict_index):
                break
            # ここから先は「**決める**」段階。異様の判定はもう立って
            # いるので、決められなかったら**紫で残す**（項目48-JW）。
            _odd_here = (run[0][3], run[-1][4])
            try:
                cut = _cut(reading, store)
            except Exception:
                cut = None
            # **切り直しは名詞（＋助詞）の並びであること**（項目48-SW）。
            # 設計42 は「読みを語の境目で切り直す」道で、名詞の連なりを
            # 別の名詞の連なりにする。用言（来る・迷う）に読み替えたら、
            # それは切り直しではなく当て推量
            if cut and _d42_has_yougen(cut, tokenize_fn):
                cut = None
            if not cut or cut == surface or cut == reading \
                    or not any(is_kanji(c) or is_katakana(c) for c in cut) \
                    or not _d42_covered(cut, store):
                if _odd_here not in _ODD_PENDING:
                    _ODD_PENDING.append(_odd_here)
                break
            # **行の頭に助詞は立てない。** `二階席が取れました` を
            # `に解析が取れました` にしてはいけない——日本語の文は
            # 助詞では始まらない（構造だけで立つ門。設計40-A の
            # 「連続の頭に `ー` は立てない」と同じ形）。
            # 読点・括弧の直後も同じく「文の頭」とみなす。
            if cut[0] in _D42_PARTICLE:
                _before = line[:run[0][3]].rstrip()
                if not _before or _before[-1] in '、。，．・「」『』（）()[]〔〕【】':
                    continue
                # **切り直した助詞は、その前の名詞に付く。**
                # 付く相手が名詞でないなら立てない——`劇場**の**二階席`
                # （助詞の後）も `**この**二階席`（連体詞の後）も、
                # 助詞を置ける場所ではない。構造だけで決まる。
                if i == 0 or not (tokens[i - 1][1] or '').startswith('名詞'):
                    continue
            a, b = run[0][3], run[-1][4]
            if blocks and blocks(surface, cut):
                break
            if any(not (b <= s0 or a >= e0) for s0, e0 in used):
                break
            used.append((a, b))
            out.append((a, b, cut))
            break
    # **直せた範囲に重なる印は落とす**（項目48-JW）。長いほうを先に
    # 試すので「4語では決められず、中の3語で決められた」ことがある。
    # 決められたのだから、そこに紫は要らない。
    if out and _ODD_PENDING:
        _keep = [(a, b) for a, b in _ODD_PENDING
                 if not any(not (b <= s0 or a >= e0) for s0, e0, _f in out)]
        del _ODD_PENDING[:]
        _ODD_PENDING.extend(_keep)
    return out


def _peel_one_suffix(v, floor, store, kango_ok=False, dict_index=None):
    """読みの終わりから接尾を**1段だけ**剥がし、残った語幹が語彙の
    漢字語（実績 floor 以上）なら (語幹の表記＋接尾の字, 実績,
    接尾の始まり位置) を並べて返す（項目48-LC/LD の部品）。
    compose は2段剥がすので、こうりつか が か→化・りつ→率 と
    剥がれて語幹が こう まで削れた（実測）。ここは1段・語彙の
    実績だけ（辞書の代替もしない）。

    `kango_ok=True` なら、**2字の漢語**（音読みだけで組める漢字2字）は
    実績が床に届かなくても語幹にしてよい（項目48-MP・2026-08-31）。
    初期状態の語彙は**実績2以上が種の401語だけ**なので、床10は
    `最大`（実績1）にも届かない——**門ではなく枠の話**（48-MK と
    同じ形）。**呼ぶ側が「張り合う読みが無い」ときだけ立てる**。
    """
    got = []
    for suf, kanji in _SUFFIX_SURFACE.items():
        if len(v) > len(suf) + 1 and v.endswith(suf):
            stem = v[:-len(suf)]
            for e in store.lookup(stem):
                s = e.get('surface') or ''
                if not s or not all(is_kanji(c) for c in s):
                    continue
                c = e.get('count', 0)
                if c >= floor or (kango_ok and c >= 1
                                  and _is_kango(s, stem)):
                    got.append((s + kanji, max(c, 1),
                                len(v) - len(suf)))
            # **語彙に無ければ、索引の顔**（項目48-OJ・2026-09-02）。
            # こうりつ → 効率（段1がただ1つ）。`dict_index` を渡した
            # 呼び手だけ（小売り坂 → 効率化 は 48-LC の道）
            if dict_index is not None and kango_ok and not any(
                    g[2] == len(v) - len(suf) for g in got):
                _f = _index_face(stem, store, dict_index)
                if _f:
                    got.append((_f + kanji, 1, len(v) - len(suf)))
    return got


def _lc_hand_unit_fix(run, tokens, i, L, store, dict_index, tokenize_fn,
                      blocks):
    """
    **読みに手を1つ加えると、優勢な単位**（項目48-LC・2026-08-29）。

    うにさんの一覧の「〜化の族」。IME が打ち間違いの読みをそのまま
    別の語の組に変換した形で、単位はどこにも立っていない:

        再退化     さいたいか → ゛追加(た→だ) → さいだいか ＝ 最大化
        歳で以下   さいでいか → 隣接キー(で→だ) → さいだいか ＝ 最大化
        誘い消化   さそいしょうか → 1字削除(そ) → さいしょうか ＝ 最小化
        小売り坂   こうりさか → 隣接キー(さ→つ) → こうりつか ＝ 効率化
        居で以下   きょでいか → 隣接キー(で→だ) → きょだいか ＝ 巨大化
        引き月資料 ひきつきしりょう → ゛追加(き→ぎ) → 引き継ぎ＋資料

    ### 異様の判定（①・開く前に立てる）

        ・名詞の連なり（頭は接頭詞:名詞接続 でもよい）か、
          **名詞＋で＋名詞**（で は だ の隣のキー。歳で以下）
        ・連なり全体が単位としてどこにも無い（語彙・辞書・表）
        ・そのままの読みで語彙の表記が立つなら 48-KT の持ち場（触らない)
        ・**そのままの読みで 語幹(実績2以上)＋接尾 が組めるなら、
          正しい複合語**（符号化 ＝ 符号＋化）——48-KU が実測で踏んだ
          `符号化 → 不幸化` を受け止める判定
        ・読みの1手（隣接キー1字・゛の付け外し・1字削除）の先に、
          優勢な単位（実績10以上・優勢の比 20倍）が**ただ1つ**立つこと

    ### 決める

        ・ただ1つ → 直す（紫は補正の色に変わる）
        ・複数     → 紫だけ残す（判定は立った・48-JW の形）
        ・無い     → 黙る（判定不成立）

    直し先は3種: 語彙の単位／語幹＋接尾の組み立て（compose・48-EX の
    閉じた表）／L=3 で後ろの語は触っていない2語の組（読みを変えて
    いない側の表記は元のまま・項目48-IU の決まり）。
    """
    pos = [(t[1] or '') for t in run]
    head_ok = pos[0].startswith('名詞') or pos[0] == '接頭詞:名詞接続'
    mid_de = (L == 3 and run[1][0] == 'で'
              and pos[1].startswith('助詞:格助詞'))
    if mid_de:
        shape_ok = head_ok and pos[2].startswith('名詞')
    else:
        shape_ok = head_ok and all(p.startswith('名詞') for p in pos[1:])
    if not shape_ok:
        return None
    # 固有名詞は**信用できる札のときだけ**降りる（項目48-RN）
    if any('数' in p for p in pos) \
            or _has_trusted_proper_noun(run, store, dict_index):
        return None
    if any(x in pos[0] for x in ('接尾', '非自立')):
        return None
    if '接頭' in pos[-1]:
        return None
    if any(run[k][4] != run[k + 1][3] for k in range(L - 1)):
        return None
    if any(len(t) > 5 and not t[5] for t in run):
        return None
    # 前後に名詞・接頭詞が直接付いているなら、大きな連なりの一部
    if i > 0 and tokens[i - 1][4] == run[0][3] \
            and ((tokens[i - 1][1] or '').startswith('名詞')
                 or '接頭' in (tokens[i - 1][1] or '')):
        return None
    if i + L < len(tokens) \
            and (tokens[i + L][1] or '').startswith('名詞') \
            and tokens[i + L][3] == run[-1][4]:
        return None
    # **直後に動詞・助動詞が直接続くなら、崩れは連なりの外にもある**
    # （`経補正る。`——正しい直しは す の脱字の側〔経補正する〕なのに、
    #   連なりだけ見て 恐怖性る に化けた・実測）。身を引く
    if i + L < len(tokens) \
            and tokens[i + L][3] == run[-1][4] \
            and ((tokens[i + L][1] or '').startswith('動詞')
                 or (tokens[i + L][1] or '').startswith('助動詞')):
        return None
    surface = ''.join(t[0] for t in run)
    if not (3 <= len(surface) <= 6):
        return None
    if not any(is_kanji(c) for c in surface):
        return None
    if _d42_known_unit(surface, store, dict_index):
        return None
    if _chunk_is_intact(surface, tokenize_fn):
        return None             # できあがりの入口（48-KI・学び22）
    from morphology import katakana_to_hiragana
    try:
        from kana_layout import nearby_candidates as _near
    except Exception:
        return None
    # 各語の別読みを掛け合わせる（歳＝とし/さい・坂＝ざか/さか。
    # 解析の言い切りだけでは打った読みに届かない——48-KW と同じ考え）
    alts = []
    for t in run:
        cand = [katakana_to_hiragana(t[2] or '')]
        if dict_index is not None and t[0]:
            try:
                for r2 in (dict_index.readings_for_surface(t[0]) or ()):
                    r2 = katakana_to_hiragana(r2)
                    if r2 and r2 not in cand:
                        cand.append(r2)
            except Exception:
                pass
        try:
            for r2 in _table_readings_for_surface(t[0]):
                if r2 and r2 not in cand:
                    cand.append(r2)
        except Exception:
            pass
        alts.append([c for c in cand
                     if c and all(is_hiragana(x) or x == 'ー'
                                  for x in c)][:4])
    if not all(alts):
        return None
    import itertools as _it

    readings = []       # [(読み, 1字トークンの位置, 語の頭・尾の位置)]
    _seen_r = set()
    for combo in _it.islice(_it.product(*alts), 12):
        r = ''.join(combo)
        if not (4 <= len(r) <= 8) or r in _seen_r:
            continue
        _seen_r.add(r)
        ones = set()            # 読み1字のトークンが占める位置
        edges = set()           # 各トークンの読みの頭と尾の位置
        p = 0
        for part in combo:
            if len(part) == 1:
                ones.add(p)
            edges.add(p)
            edges.add(p + len(part) - 1)
            p += len(part)
        # で挟みの で の、読みの中の位置（この1字だけは置換してよい）
        dpos = len(combo[0]) if mid_de else -1
        # **読み1字の内容トークンを含む組は対象にしない**——1字の
        # 読みに手を入れても「語の置き換え」にしかならない（実測:
        # かな字打ち の 字＝じ → 漢字打ち・スクロール語 の 語＝ご）。
        # で挟みの で だけは例外（で↔だ の打ち間違いの仮説そのもの）
        if ones - {dpos}:
            continue
        readings.append((r, frozenset(ones), frozenset(edges), dpos))
    if not readings:
        return None
    base_count = 0
    for r, _ones, _edges, _dpos in readings:
        ents = store.lookup(r)
        base_count = max([base_count]
                         + [e.get('count', 0) for e in ents])
        # そのままの読みで別の表記が立つ＝48-KT の持ち場。触らない
        if any(e.get('count', 0) >= 2 and e['surface'] != surface
               for e in ents):
            return None
        # そのままの読みで 語幹(実績2以上)＋接尾 が組める＝正しい複合語
        # （符号化 ＝ 符号＋化。48-KU が実測で踏んだ 符号化 → 不幸化）
        #
        # **守りの側を広げても効かない**（項目48-MP で測った）。
        # `一致率 → 一途率`・`形態的 → 生態的` の元の語幹
        # （一致・形態）は**語彙にそもそも無い**ので、語彙を見る
        # 守りでは掴めない。受け止めるのは下の「直し先が世の中で
        # 1語であること」のほう。
        if _peel_one_suffix(r, 2, store, dict_index=dict_index):
            return None
    # ★★ **回数を廃したので、この敷居は越えられない**（項目48-QG'）。
    # `base_count` も面の count も 2 が上限で、`need` は 10 以上。
    # ＝**実績で立つ面は無くなり**、表（世の中で1語か・48-MP）と
    # 索引の顔（48-OJ）で立つ面だけが残る。倒れる先は「面が無い →
    # None／紫」＝安全側。**初期状態では前からそうだった**。
    # 直し先を裁く側は、末尾の**競合の見張り**を費用表へ移した（48-QG'）。
    need = max(10, 20 * base_count)
    # で挟みの形では2語の組を作らない——「で は だ の打ち間違い」の
    # 仮説は**全体が1語**という主張。後ろを残す組（サイト以下・
    # 再度以下…）は仮説と矛盾する上に、面を濁らせるだけ（実測）
    tail_rd = katakana_to_hiragana(run[-1][2] or '') \
        if (L == 3 and not mid_de) else ''
    tail_sf = run[-1][0] if (L == 3 and not mid_de) else ''
    faces = {}
    for r, _ones, _edges, _dpos in readings:
        seen = set()
        for k in range(len(r)):
            # **読み1字のトークンの丸ごと置換は、打ち間違いではなく
            # 語の置き換え**（補正後 → 補正化 は 後↔化 の置き換え。
            # 実測で 補正後・入力後・引用後…が全部 化 に化けた）。
            # 例外は で挟みの で（で↔だ の打ち間違いの仮説そのもの）
            if k in _ones and k != _dpos:
                continue
            try:
                edits = [r[:k] + alt + r[k + 1:]
                         for alt, d in _near(r[k])
                         if alt != r[k] and d <= 1.0]
            except Exception:
                edits = []
            # **連濁の手**: 読みの濁りは IME が付けたもので、打った
            # キーは清音（坂＝ざか の ざ は、打った さ の連濁）。
            # 濁点を外した字の隣のキーも1手（こうりざか → こうりつか）
            _base = _LC_UNVOICED.get(r[k])
            if _base:
                try:
                    edits.extend(r[:k] + alt + r[k + 1:]
                                 for alt, d in _near(_base)
                                 if alt != r[k] and d <= 1.0)
                except Exception:
                    pass
            # 1字削除は**語の読みの中だけ**（頭・尾は不可）。頭や尾の
            # 削除は語の切り詰めで、別の語がただ現れる（実測:
            # 誤判定 → 判定・補助動詞 → 助動詞・確定文字 → 確定時・
            # スクロール語 → スクロール）
            if len(r) - 1 >= 4 and k not in _edges:
                edits.append(r[:k] + r[k + 1:])
            for v in edits:
                if v == r or v in seen:
                    continue
                seen.add(v)
                # ※「語彙の単位への1手置換」という先は**置かない**
                # （2026-08-29 実測: 勝ち0・化け3——タブ内 → 危ない・
                #   ひとつ前 → 必然・かな字打ち → 漢字打ち。どれも
                #   正しい複合語が、たまたま1手先の常用語に届く。
                #   48-KU が濁点の手を落としたのと同じ判断）
                # 先(2): 語幹＋接尾（1段だけ・語幹の実績も同じ床）。
                # **手が接尾そのものを作った形は採らない**——接尾は
                # 手の前から在る字であること（実測: 空白行 の 行 を
                # いき→てき と直して 的 を剥いだ・補正付き → 補正的）
                # **張り合う読みが無いときだけ、2字の漢語も語幹に
                # してよい**（項目48-MP）。`base_count == 0` ＝
                # そのままの読みではどの表記も立っていない、という
                # ことなので、優勢の比（20倍）の話が要らない場面。
                for _full, _sc, _sst in _peel_one_suffix(
                        v, need, store, kango_ok=(base_count == 0),
                        dict_index=(dict_index if base_count == 0
                                    else None)):
                    if _full != surface and k < _sst:
                        _old = faces.get(_full)
                        if _old is None or _sc > _old[1]:
                            faces[_full] = (v, _sc)
                # 先(3): 後ろの語は触っていない2語の組（L=3・48-IU）
                if tail_rd and v.endswith(tail_rd) \
                        and len(v) - len(tail_rd) >= 2 \
                        and k < len(v) - len(tail_rd):
                    va = v[:-len(tail_rd)]
                    _head_sf = ''.join(t[0] for t in run[:-1])
                    for e in store.lookup(va):
                        if e.get('count', 0) >= need \
                                and e['surface'] != _head_sf:
                            _f2 = e['surface'] + tail_sf
                            _old = faces.get(_f2)
                            if _old is None or e['count'] > _old[1]:
                                faces[_f2] = (v, e['count'])
    faces.pop(surface, None)
    a, b = run[0][3], run[-1][4]
    if not faces:
        return None
    # **2字の漢語を語幹にして立った面は、直し先が「世の中で1語」で
    # あることまで要る**（項目48-MP・2026-08-31）。
    #
    # 実績の床（10）を漢語で越えさせたぶん、面が増える。**増えた面は
    # 実績で裁けない**（どれも実績1）ので、比の20倍が効かない:
    #
    #     歳で以下 → 裁定化(1) と 最大化(1) が並ぶ
    #     一致率  → **一途率**   ／  形態的 → **生態的**（実測の化け）
    #
    # **表を「直す証拠」ではなく「直し先が在ること」の条件に使う**
    # （48-KF が入れなかった向きの逆・48-MK と同じ形）。
    # `最大化` は世の中に在り、`裁定化`・`一途率`・`生態的` は無い。
    #
    # **床を越えた面（実績で立った面）はそのまま**——今までの答えは
    # 1つも動かない。**張り合う読みが無いとき（base_count == 0）
    # だけ**掛ける。
    if base_count == 0 and any(c0 < need for _v0, c0 in faces.values()):
        # **形容動詞語幹＋化 は、表に無くても1語**（項目48-OK・
        # 2026-09-02）。巨大化・正常化・安定化・活性化——「〜化」は
        # 形容動詞語幹に生産的に付く（文法として決まっている形）。
        # 同梱の表に `巨大化` が無いだけで `居で以下 → 巨大化` が
        # 落ちていた。サ変の名詞（注意化）・一般の名詞（課題化）には
        # 広げない——そちらは表で確かめる（48-MP のまま）
        try:
            import seed_japanese as _sj3
            kept = {f: fv for f, fv in faces.items()
                    if fv[1] >= need or _sj3.is_unit(f) is True
                    or _na_adj_ka_word(f)}
        except Exception:
            kept = {f: fv for f, fv in faces.items()
                    if fv[1] >= need or _na_adj_ka_word(f)}
        if kept != faces:
            _trace('読み繋ぎ',
                   f'{surface!r} → 実績の足りない面のうち、世の中で'
                   f'1語なのは {sorted(kept)} だけ（項目48-MP）')
            faces = kept
        if not faces:
            return None
    # 面が複数でも、**最上位が2位の20倍以上**（優勢の比）なら採る
    # （再退化: 最大化1124 ＞ 最多化47×20 ＞ 最低化29。★★の
    #   「一般的か」を数字にした形）。開かないなら紫だけ（48-JW）
    ranked = sorted(faces.items(), key=lambda kv: -kv[1][1])
    if len(ranked) > 1 and ranked[0][1][1] < 20 * ranked[1][1][1]:
        _trace('読み繋ぎ', f'{surface!r} → 1手先の単位が競う '
                           f'{[(f, c) for f, (v0, c) in ranked]} '
                           f'なので紫だけ（項目48-LC）')
        return ('紫', a, b)
    fix, (v, _face_cnt) = ranked[0]
    # **競合の見張り**: 同じ長さ・2手以内の語彙の読みに、直し先より
    # **世の中で一般的な表記**があるなら、1手で見えた答えが最良とは
    # 限らない（`好き任`: 1手の せきにん＝責任 より、2手の
    # かくにん＝確認 のほうが優勢——設計27 が決める持ち場）。
    # 身を引いて紫だけ残す（判定は立った・決めるのは向こう）。
    #
    # ★★ **証拠を「回数」から「同梱の表の費用」へ移した**
    # （項目48-QG'・2026-09-05）。もとは `_rc >= max(_face_cnt, need)`
    # ——**相手の使用回数**が直し先の実績と床（10以上）を上回るか、
    # だった。回数を廃した今、`_rc` は 1 か 2 にしかならず、床 10 を
    # 越えられない＝**この見張りは黙って死ぬ**。**死ぬ先は
    # 「そのまま直す」＝壊す側**なので、置き換えないわけにいかない。
    #
    # 新しい証拠は `_table_cost`（`seed_japanese_cost.txt.gz`・
    # **小さいほど世の中でよく使う**）。相手が **この人の語として
    # 立っていて**（solid）、その表記が直し先と同じかそれ以上に
    # 一般的なら、身を引く。表に無い相手は証拠にしない
    # （知らないものを「一般的だ」とは言わない）。
    try:
        from vocabulary import find_known_readings_flex as _fkr
        from vocabulary import entry_is_solid as _solid
        _fix_cost = _table_cost(fix)
        for _r0, _o0, _e0, _d0 in readings:
            for _r2, _c2, _n2 in _fkr(_r0, store, max_edits=2):
                if not (_c2 <= 2.0 and _r2 != _r0 and _r2 != v
                        and len(_r2) == len(_r0)):
                    continue
                for _e2 in store.lookup(_r2):
                    _s2 = _e2.get('surface') or ''
                    if _s2 == fix or not _solid(_e2):
                        continue
                    _rc2 = _table_cost(_s2)
                    if _rc2 is None:
                        continue
                    if _fix_cost is None or _rc2 <= _fix_cost:
                        _trace('読み繋ぎ',
                               f'{surface!r} → 2手以内に、より一般的な '
                               f'{_s2!r}（費用 {_rc2}／直し先 {fix!r} は '
                               f'{_fix_cost}）が競るので紫だけ'
                               f'（項目48-LC・48-QG\'）')
                        return ('紫', a, b)
    except Exception:
        pass
    if blocks and blocks(surface, fix):
        return None
    _trace('読み繋ぎ', f'{surface!r} → {fix!r}（読みの1手 {v!r}・'
                       f'優勢{need}以上・項目48-LC）')
    return (a, b, fix)


def _lm_zero_edge_fix(run, tokens, i, store, dict_index, tokenize_fn,
                      blocks):
    """
    **実績0の語ふたつは、縁を信じない**（項目48-LM・2026-08-30）。

    `解す咳` ＝ 余分な す が IME の切り方を壊して生まれた、実在しない
    2語。**どちらの語にも使用実績が無い**ときだけ、繋いだ読みの
    **どの位置の1字削除も**（縁も含めて）試し、実績の立つ1語が
    優勢の比でただ1つなら直す。かいすせき − す ＝ かいせき ＝ 解析。

    戻り値: (始まり, 終わり, 直した表記) または None。
    """
    from morphology import katakana_to_hiragana
    pos = [(t[1] or '') for t in run]
    for p in pos:
        if not (p.startswith('名詞') or p == '動詞:自立'):
            return None
        if '数' in p or '接尾' in p or '非自立' in p:
            return None
    # 固有名詞は**信用できる札のときだけ**降りる（項目48-RN）
    if _has_trusted_proper_noun(run, store, dict_index):
        return None
    if run[0][4] != run[1][3]:
        return None
    if any(len(t) > 5 and not t[5] for t in run):
        return None
    surface = ''.join(t[0] for t in run)
    if not (2 <= len(surface) <= 6):
        return None
    if not any(is_kanji(c) for c in surface):
        return None
    # 前後に名詞が直接付くなら大きな連なりの一部
    if i > 0 and tokens[i - 1][4] == run[0][3] \
            and ((tokens[i - 1][1] or '').startswith('名詞')
                 or '接頭' in (tokens[i - 1][1] or '')):
        return None
    if i + 2 < len(tokens) \
            and (tokens[i + 2][1] or '').startswith('名詞') \
            and tokens[i + 2][3] == run[1][4]:
        return None
    if _d42_known_unit(surface, store, dict_index):
        return None
    if _chunk_is_intact(surface, tokenize_fn):
        return None
    # **構成する語のどちらにも使用実績が無い**こと（誤判定 は
    # 判定 に実績があるので入らない）
    for t in run:
        rd_t = katakana_to_hiragana(t[2] or '')
        try:
            if any(e.get('surface') == t[0] and e.get('count', 0) >= 1
                   for e in store.lookup(rd_t)):
                return None
        except Exception:
            return None
    reading = ''
    ones = set()        # 読み1字のトークンが占める位置（丸ごと削除禁止）
    for t in run:
        rd_t = katakana_to_hiragana(t[2] or '')
        if len(rd_t) == 1:
            ones.add(len(reading))
        reading += rd_t
    if not (4 <= len(reading) <= 8) \
            or not all(is_hiragana(c) or c == 'ー' for c in reading):
        return None
    base = max([e.get('count', 0) for e in store.lookup(reading)] or [0])
    # ★★ **恒偽になった**（項目48-QG'・回数を廃した）。メモリ上の
    # `count` は写し（solid なら 2・そうでなければ 1）なので `base` は
    # 最大 2、`need` は最小 10 ——`count >= need` は**もう成立しない**。
    # ＝下の `faces` は必ず空になり、`if not faces: return None` で
    # **この道は丸ごと黙る**（倒れる先は None＝触らない・安全側）。
    # 兄弟（16226・17233）は「表と索引の顔で立つ面だけが残る」＝
    # 目減りで済むが、**ここには代わりの面の供給元が無い**。
    # 初期状態では前から成立しなかった（種 2・辞書 1 で need 10 に
    # 届かない）ので、失うのは**育ちの直りだけ**——この機械は
    # 育ちの直りを数えない（★★「初期状態でどうなるかが大切」）。
    # 生かし直すなら証拠を world・費用表へ寄せる（測ってから）。
    need = max(10, 20 * base)
    faces = {}
    for k in range(len(reading)):
        # **読み1字のトークンの丸ごと削除は、語の消去**（48-LC と同じ
        # 門・学び22。`移行し` の し を消して 以降 に乗り換えた・実測）
        if k in ones:
            continue
        v = reading[:k] + reading[k + 1:]
        for e in store.lookup(v):
            if e.get('count', 0) >= need and e['surface'] != surface:
                _old = faces.get(e['surface'], 0)
                faces[e['surface']] = max(_old, e['count'])
    if not faces:
        return None
    ranked = sorted(faces.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[0][1] < 20 * ranked[1][1]:
        return None                 # 面が競う。触らない
    fix = ranked[0][0]
    if blocks and blocks(surface, fix):
        return None
    _trace('読み繋ぎ', f'{surface!r} → {fix!r}（実績0の語ふたつ・'
                       f'1字削除で優勢{need}以上・項目48-LM）')
    return (run[0][3], run[1][4], fix)


def _run_reading_merge_fixes(line, tokenize_fn, store, dict_index=None,
                             decisions=None):
    """
    **読みを繋ぐと、よくある1語**（項目48-KT・2026-08-29）。

    うにさんの正解メモ「**待ち外の補正 ⇒ 間違いの補正**」。

        待ち外 ＝ 待ち（まち）＋ 外（**がい**・接尾）
        → 読みを繋ぐと **まちがい** ＝ 間違い（よくある1語）
        → 塊 `待ち外` 自体は、語彙にも辞書にも表にも**単位として無い**

    IME が1語の読みを**別の語の組**に変換した形。設計42 の裏向き
    （あちらは「切り直すと語＋助詞」、こちらは「繋ぐと1語」）。
    `待ち` も `外` も**単独では立つ語**なので、設計42 の
    「どの語も立っていない」には掛からず、今まで誰も見ていなかった
    （紫も付かない・48-KJ の問い `待ち外` そのもの）。

    ### 異様の判定（開く前に立てる・★★の順番）

        ・助詞をはさまない**名詞の連なり**（2〜3語・2〜6字・漢字を含む）
        ・**前後に名詞が付いていない**——`最大|化時` の `化時` は
          大きな連なりの一部なので見ない（かじ→家事 の誤爆の芽・実測）
        ・固有名詞・数詞は見ない（48-JL の姓名保護と同じ）
        ・連なり全体が**単位としてどこにも無い**（想定外・切り替え時は
          単位が立つので触らない・実測）
        ・繋いだ読みが**同梱の表でよくある語**（費用 _COMMON_WORD_COST 以下）

    ### 決める

        ・語彙にその読みの表記（count>=2・元と別の表記）が**ただ1つ**
          → その表記に直す（間違い）
        ・複数 → **紫だけ残す**（判定は立った・決められない・48-JW の形）
        ・無い → 判定不成立として黙る——読みがよくある語なだけでは
          異様と言えない（`竹かんむり`＝たけかんむり は正しい書き方・実測）

    ### 測った（2026-08-29・初期・きれいな写し）

        的   待ち外の補正 → 候補 (待ち外, まちがい, 費用105, 間違い)
        守り 想定外・時間外・切り替え時・補正欄・添付画像・空白行・
             対象外・範囲外・二階席・大声・目下・手元 → 全部無傷
        実機メモ 1,435行 → 候補9行＝的4行＋前後に名詞が付く形1行
             （化時・この門で消える）＋直し先の無い形4行（竹かんむり
             ×2・さ位置・コマ目・この「黙る」の決まりで消える）

    戻り値: [(始まり, 終わり, 直した形), ...]
    """
    if not line or tokenize_fn is None:
        return []
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return []
    from morphology import katakana_to_hiragana
    blocks = getattr(decisions, 'blocks', None) if decisions else None
    out = []
    for i in range(len(tokens)):
        for L in (2, 3):
            if i + L > len(tokens):
                continue
            run = tokens[i:i + L]
            pos = [(t[1] or '') for t in run]
            # --- 項目48-KW: 動詞の連体形＋数詞＋助数詞（`貸す九人`）----
            # 連体形＋数は文法としては正しい形（集まる十人）なので
            # **構造では割れない**（引き継ぎ E で「判定の材料が立つまで
            # 開かない」とした族）。材料は読みの1手——**1字を落とすと、
            # ずっとよく使う語彙の語**になること（かすくにん → かくにん
            # ＝確認。押しすぎの手＋48-KU と同じ優勢の比 20倍）。
            if (L == 3 and (pos[0] or '').startswith('動詞')
                    and '数' in pos[1] and '助数詞' in pos[2]
                    and run[0][0] and run[0][0][-1] in 'うくぐすずつぬふぶむゆる'
                    and not any(run[k][4] != run[k + 1][3]
                                for k in range(L - 1))
                    and not any(len(t) > 5 and not t[5] for t in run)):
                surface = ''.join(t[0] for t in run)
                if (2 <= len(surface) <= 6
                        and not _d42_known_unit(surface, store, dict_index)
                        and not _chunk_is_intact(surface, tokenize_fn)):
                    # 読みは**各語の別読みを掛け合わせて**作る（九＝
                    # きゅう／く。解析の言い切りだけだと かすきゅうにん
                    # にしかならず、打った かすくにん に届かない——
                    # 開く道（48-IS）と同じ考え）
                    _alts = []
                    for t in run:
                        cand = [katakana_to_hiragana(t[2] or '')]
                        try:
                            for r2 in _table_readings_for_surface(t[0]):
                                if r2 and r2 not in cand:
                                    cand.append(r2)
                        except Exception:
                            pass
                        _alts.append([c for c in cand if c][:4])
                    import itertools as _it
                    faces = set()
                    for combo in _it.islice(_it.product(*_alts), 12):
                        reading = ''.join(combo)
                        if not (4 <= len(reading)
                                and all(is_hiragana(c) or c == 'ー'
                                        for c in reading)):
                            continue
                        # ★★ 回数を廃したので、`base_count` が 1 以上の
                        # ときは越えられない敷居になる（項目48-QG'）。
                        # `base_count == 0`（＝その読みでは何も立って
                        # いない）のときだけ `need = 2`＝**立っているか**
                        # に落ちて、今までどおり働く。倒れる先は
                        # 「面が無い」＝安全側。
                        base_count = max(
                            [e.get('count', 0)
                             for e in store.lookup(reading)] or [0])
                        need = max(2, 20 * base_count)
                        for k in range(len(reading)):
                            v = reading[:k] + reading[k + 1:]
                            faces.update(
                                e['surface'] for e in store.lookup(v)
                                if e.get('count', 0) >= need
                                and e['surface'] != surface)
                    if len(faces) == 1:
                        fix = faces.pop()
                        a, b = run[0][3], run[-1][4]
                        if not (blocks and blocks(surface, fix)):
                            _trace('読み繋ぎ',
                                   f'{surface!r} → {fix!r}（読みの1字を'
                                   f'落とすと優勢・項目48-KW）')
                            out.append((a, b, fix))
                            break
                continue
            # --- 項目48-LM: 実績0の語ふたつは、縁を信じない -------------
            # （2026-08-30。`解す咳が終わった ⇒ 解析が終わった`——余分な
            #   す が IME の切り方を壊し、実在しない2語〔解す・咳〕が
            #   生まれた形。48-LC の「縁の削除は語の切り詰め」の門は
            #   **トークンの縁**を信じるが、その縁自体が切り方の産物の
            #   ことがある。**構成する語のどちらにも使用実績が無い**
            #   ときだけ、どの位置の1字削除も試し、実績の立つ1語
            #   （床10・優勢の比）がただ1つなら直す。誤判定・補助動詞・
            #   確定文字・スクロール語 は構成語に実績があるので入らない)
            if os.environ.get('CN_LM') != '0' and L == 2:
                _lm = _lm_zero_edge_fix(run, tokens, i, store, dict_index,
                                        tokenize_fn, blocks)
                if _lm is not None:
                    out.append(_lm)
                    break
            # --- 項目48-LC: 読みに手を1つ加えると、優勢な単位 -----------
            # （〜化の族。そのままの読みで単位が立つ形は中で断って
            #   48-KT/KU に譲るので、順番はここでよい・CN_LC=0 で切る）
            if os.environ.get('CN_LC') != '0':
                _lc = _lc_hand_unit_fix(run, tokens, i, L, store,
                                        dict_index, tokenize_fn, blocks)
                if _lc is not None:
                    if _lc[0] == '紫':
                        if (_lc[1], _lc[2]) not in _ODD_PENDING:
                            _ODD_PENDING.append((_lc[1], _lc[2]))
                    else:
                        out.append(_lc)
                    break
            if not all(p.startswith('名詞') for p in pos):
                continue
            # 途切れなく隣り合っていること
            if any(run[k][4] != run[k + 1][3] for k in range(L - 1)):
                continue
            # **前後に名詞・接頭詞が直接付いているなら、大きな連なりの一部**
            if i > 0 and tokens[i - 1][4] == run[0][3] \
                    and ((tokens[i - 1][1] or '').startswith('名詞')
                         or '接頭' in (tokens[i - 1][1] or '')):
                continue
            if i + L < len(tokens) \
                    and (tokens[i + L][1] or '').startswith('名詞') \
                    and tokens[i + L][3] == run[-1][4]:
                continue
            # **連なりの頭が、前の語にぶら下がる品詞なら、語の頭ではない**
            # （`高|さ|位置` の `さ位置`——さ は接尾。育ちの実測で
            #   `高さ位置 → 高才智` と化けた。受け止める判定はこれ）。
            # 終わりが接頭詞なのも同じ（次の語にぶら下がる）。
            if any(x in pos[0] for x in ('接尾', '非自立')):
                continue
            if '接頭' in pos[-1]:
                continue
            # 固有名詞は**信用できる札のときだけ**降りる（項目48-RN）
            if any('数' in p for p in pos) \
                    or _has_trusted_proper_noun(run, store, dict_index):
                continue
            # 読みが立っていること（janome の推測読みでは判定しない）
            if any(len(t) > 5 and not t[5] for t in run):
                continue
            surface = ''.join(t[0] for t in run)
            if not (2 <= len(surface) <= 6):
                continue
            if not any(is_kanji(c) for c in surface):
                continue
            if _d42_known_unit(surface, store, dict_index):
                continue
            if _chunk_is_intact(surface, tokenize_fn):
                continue        # できあがりの入口（48-KI・学び22）
            # ★★ **塊＋送り仮名が表の語なら触らない**（項目48-VB'・
            # 2026-09-07・学び22）。この道は**名詞の連なり**だけを見るので、
            # 用言の漢字部分（`飛上`＋`がら`＝飛上がら）が名詞2つに見える:
            #
            #     飛上がら → **非常がら**（読み ひ＋じょう を繋いで 非常）
            #
            # 塊は漢字で終わるので `_chunk_is_intact('飛上')` は False。
            # うしろの送り仮名まで含めて表に聞く（48-VB と同じ関数）。
            if _chunk_with_okurigana_is_word(line, run[0][3], run[-1][4]):
                _trace('読み繋ぎ', f'{surface!r} は送り仮名まで含めると'
                                   f'1語として在るので触らない（項目48-VB）')
                continue
            reading = ''.join(katakana_to_hiragana(t[2] or '') for t in run)
            if not reading or not all(is_hiragana(c) or c == 'ー'
                                      for c in reading):
                continue
            a, b = run[0][3], run[-1][4]
            # --- 48-KT: 繋いだ読みが、そのままよくある1語 ---------------
            cost = _table_cost(reading)
            if cost is not None and cost <= _COMMON_WORD_COST:
                targets = sorted({e['surface'] for e in store.lookup(reading)
                                  if e.get('count', 0) >= 2
                                  and e['surface'] != surface})
                if targets:
                    if len(targets) > 1:
                        # 判定は立った・決められない → 紫だけ残す（48-JW）
                        _trace('読み繋ぎ',
                               f'{surface!r} は {reading!r} で1語だが'
                               f'表記が複数 {targets} なので紫だけ')
                        if (a, b) not in _ODD_PENDING:
                            _ODD_PENDING.append((a, b))
                        break
                    fix = targets[0]
                    if blocks and blocks(surface, fix):
                        break
                    _trace('読み繋ぎ',
                           f'{surface!r} → {fix!r}'
                           f'（読み {reading!r} を繋ぐと1語・項目48-KT）')
                    out.append((a, b, fix))
                    break
            # --- 48-KU: 接尾の枠を保った「う挿入」（囚虜時 ⇒ 終了時）----
            # 前の部分の読みに長音の脱字を1つ戻すと、**ずっとよく使う語**
            # になる形。うにさんの一覧「しゅうりょじ ⇒ しゅうりょうじ
            # 終了時」。門:
            #   ・前は**漢字2字以上**（1字＋接尾〔秒数〕は普通の組み立て。
            #     実測: 秒数 → 表数 の誤爆をこの門で受け止めた）
            #   ・後ろは**接尾**（状態・資料などの一般名詞は不可）
            #   ・手は**う挿入**だけ（濁点は 符号化 → 不幸化 の誤爆を
            #     作り、勝ちが無かったので入れていない）
            #   ・**優勢**: 書かれている語が**この人の語として立って
            #     いない**こと（`_base_reading_is_own_word`）。
            #
            #     ★★ もとは「回数が **20倍以上**」だった（項目48-KU）。
            #     回数の記録をやめた（48-QG）ので 20倍は二度と越えられ
            #     ない。残るのは前半——**書かれている語をまだ使って
            #     いないとき**（もとの `base_count == 0`）だけ通す形。
            #     費用の差で言い直す案は**測って外した**（詳しくは
            #     `_base_reading_is_own_word` の説明。`巨大化 → 強大化`
            #     の化けを作った）。
            if (L == 2 and '接尾' in pos[1]
                    and len(run[0][0]) >= 2
                    and all(is_kanji(c) for c in run[0][0])):
                ra = katakana_to_hiragana(run[0][2] or '')
                if ra and len(ra) >= 3 and all(
                        is_hiragana(c) or c == 'ー' for c in ra):
                    # **書かれている語がこの人の語なら、そもそも見ない**
                    # （項目48-QG'。輪の中で毎回聞かない——同じ答えしか
                    #   返らないので、輪に入る前に決める）
                    _ku_ok = not _base_reading_is_own_word(ra, store)
                    done = False
                    for k2 in range(len(ra)) if _ku_ok else ():
                        if ra[k2] not in _KU_O_DAN:
                            continue
                        v = ra[:k2 + 1] + 'う' + ra[k2 + 1:]
                        faces = sorted({
                            e['surface'] for e in store.lookup(v)
                            if e.get('count', 0) >= 2
                            and e['surface'] != run[0][0]})
                        if len(faces) != 1:
                            continue
                        fix = faces[0] + run[1][0]
                        if blocks and blocks(surface, fix):
                            continue
                        _trace('読み繋ぎ',
                               f'{surface!r} → {fix!r}（{ra!r} に う を'
                               f'戻すと {v!r}・書かれている語は立って'
                               f'いない・項目48-KU／48-QG\'）')
                        out.append((a, b, fix))
                        done = True
                        break
                    if done:
                        break
    return out


# 「う挿入」を許す場所（お段・小書きの ょ の直後＝長音の脱字が
# 起きる場所。項目48-KU）
_KU_O_DAN = frozenset('おこごそぞとどのほぼぽもよろょ')


# 濁った字 → 清音（連濁の手・項目48-LC。読みの濁りは IME が付けた
# もので、本人が打ったキーは清音のほう）
_LC_UNVOICED = {v: b for b, v in zip(
    'かきくけこさしすせそたちつてとはひふへほ',
    'がぎぐげござじずぜぞだぢづでどばびぶべぼ')}


# --- 設計43: 助詞をはさんだ読みを1語へ寄せる（対の表・項目48-JZ）-----
#
# 的（うにさんの的リスト・実装方針4の A族「寄せる」）:
#
#     全体と押して       ⇒ 全体通して      （と＋押し ＝ とおし ＝ 通し）
#     長いことで来ません   ⇒ 長いことできません（で＋来 ＝ でき）
#
# IME が1語の読みを **助詞＋自立語** に割った形。打ち間違いは1つも
# 無く、境目だけが違う（設計42 の裏向き）。
#
# **「繋いだ読みが語彙の語」だけを証拠にはできない**——初期の実機メモで
# 立つ候補18か所が**全部誤爆の向き**だった（て来→テキ・と入れ→トイレ・
# で書ける→出かける…。`tools_local/diag_split.py`・2026-08-27 実測）。
# **自然さでも裁けない**（48-JN §5 実測: 正解の で来→でき が −2152 で
# 符号が逆）。だから **閉じた対の表**（48-JE の `_BOUND_SUFFIX`・
# 48-JJ の `homophone_pairs` と同じ型）にし、対ごとに**構造の門**を書く。
# **広げるときは1対ずつ** memodiff+fpcheck で検品する（48-JJ の決まり）。
#
#     particle  助詞の表記（この1字のトークンだけ。`として` は janome が
#               1語に切るのでここへ来ない）
#     verb      直後の動詞の頭の漢字
#     okuri     その次に続いてよい送りの1字目（活用の列が同じことの確認。
#               押す/通す は同じサ行五段、来ませ/でき ませ は文字がそのまま
#               残って正しい形になる）
#     fix       助詞＋動詞の頭を、これで置き換える
#     gate      対ごとの門（下の関数を見る）
#
# 門の根拠（実機メモの実測・2026-08-27）:
#   ・`F9F10と押しても同じです`（tab0:559）という**正しい並び**が在る。
#     「と格＋目的語なし」だけでは壊すので、`通して` の相手になる
#     **手がかり語**（全体・全部…）を直前に要求する（48-JJ の手がかり語と
#     同じ考え）。
#   ・`バスで来ません` `そのことで来ません` は正しい日本語。
#     `長いこと`（形容詞＋こと＝期間の言い回し）は「〜で来る」の
#     相手にならないので、**形容詞＋こと の直後だけ**にする。
_D43_PAIRS = (
    {'particle': 'と', 'verb': '押', 'okuri': 'しすさせそ',
     'fix': '通', 'gate': 'hint', 'hints': ('全体', '全部', '全文')},
    {'particle': 'で', 'verb': '来', 'okuri': 'まるたて',
     'fix': 'でき', 'gate': 'adj_koto'},
)


# --- 設計44: 並記の親戚——「〜中か」に続く同音の対（項目48-KA）--------
#
# 的（引き継ぎ D）:
#
#     上昇中か加工中華 ⇒ 上昇中か下降中か
#
# `上昇中か` が並列の型（A中かB中か）を立てる。続く `加工中華`
# （かこうちゅうか）を同じ型で読めば `下降中か`——`加工 → 下降` は
# 同音（かこう）の対、`中華 → 中か` は読みの再分割（ちゅう＋か）。
#
# **片方だけでは開かない**（48-JV の残りに実測の注意——`上昇中か加工中か`
# は、かえって読めない）。**両方そろう形だけ**を、閉じた対の表で
# **原子的に**（2か所同時に）直す。並列の相手（上昇⇔下降）が閉じた
# 証拠なので、使用実績は見ない（48-JE の `_BOUND_SUFFIX` と同じ理屈。
# 初期語彙の `下降` は実績1で、count>=2 の道では届かない——その門は
# うにさんの指定で触らない・2026-08-24）。
#
#     (並列の相手, 直し先, 直し先の読み)
#
# 広げるときは**1対ずつ** memodiff＋fpcheck で検品（48-JJ の決まり）。
_D44_PAIRS = (
    ('上昇', '下降', 'かこう'),
)


def _parallel_pair_fixes(line, tokenize_fn, decisions=None):
    """
    設計44 の本体。`A中か B中華` の並びを `A中か B'中か` へ。

    戻り値: [(始まり, 終わり, 直した形), ...]（2要素・原子的）か []。
    """
    if not line or tokenize_fn is None:
        return []
    if '中華' not in line or '中か' not in line:
        return []                   # 速い門
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return []
    from morphology import katakana_to_hiragana as _h
    blocks = getattr(decisions, 'blocks', None) if decisions else None
    for i in range(len(tokens) - 4):
        t0, t1, t2, t3, t4 = tokens[i:i + 5]
        # 並列の錨: A ＋ 中（接尾）＋ か（助詞）
        if t1[0] != '中' or not (t1[1] or '').startswith('名詞:接尾'):
            continue
        if t2[0] != 'か' or not (t2[1] or '').startswith('助詞'):
            continue
        # 続き: B（名詞・読みが対の読み）＋ 読み ちゅうか の語
        if not (t3[1] or '').startswith('名詞'):
            continue
        if _h(t4[2] or '') != 'ちゅうか':
            continue
        for anchor, fix, rd in _D44_PAIRS:
            if t0[0] != anchor:
                continue
            if t3[0] == fix or _h(t3[2] or '') != rd:
                continue
            if blocks and (blocks(t3[0], fix) or blocks(t4[0], '中か')):
                continue
            # **両方そろって初めて開く**（2か所同時）
            return [(t3[3], t3[4], fix), (t4[3], t4[4], '中か')]
    return []


def _particle_merge_fixes(line, tokenize_fn, decisions=None):
    """
    設計43 の本体。対の表に合う **助詞＋動詞の頭** を1語へ寄せる。

    戻り値: [(始まり, 終わり, 直した形), ...]（設計42 と同じ形）
    """
    if not line or tokenize_fn is None:
        return []
    if not any(p['particle'] + p['verb'] in line for p in _D43_PAIRS):
        return []                   # 速い門（ほとんどの行はここで帰る）
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return []
    blocks = getattr(decisions, 'blocks', None) if decisions else None
    out = []
    for i in range(1, len(tokens) - 1):
        t = tokens[i]
        if not (t[1] or '').startswith('助詞'):
            continue
        for pair in _D43_PAIRS:
            if t[0] != pair['particle']:
                continue
            v = tokens[i + 1]
            if not (v[1] or '').startswith('動詞'):
                continue
            if not v[0].startswith(pair['verb']):
                continue
            # 動詞の頭の次の1字（送り・助動詞の頭）が、寄せても
            # 正しい形になる列にあること
            _k = v[3] + len(pair['verb'])
            if line[_k:_k + 1] not in pair['okuri']:
                continue
            # --- 対ごとの門 ---
            prev = tokens[i - 1]
            if pair['gate'] == 'hint':
                if prev[0] not in pair['hints']:
                    continue
                if not (prev[1] or '').startswith('名詞'):
                    continue
            elif pair['gate'] == 'adj_koto':
                if prev[0] != 'こと' or i < 2:
                    continue
                if not (tokens[i - 2][1] or '').startswith('形容詞'):
                    continue
            else:
                continue
            a, b = t[3], v[3] + len(pair['verb'])
            if blocks and blocks(line[a:b], pair['fix']):
                continue
            out.append((a, b, pair['fix']))
            break
    return out


def _head_typo_fixes(line, store, decisions=None):
    """
    **設計41: かな連続の「頭の1字」の打ち間違いを、隣のキーで戻す**
    （項目48-JT・2026-08-26。【Opus への実装方針】3番「先頭の崩れ」）。

    48-JN の台帳で**いちばん弱いのが先頭**（戻し率 29%。中 47%・末尾 29%）。
    語頭は探索の錨なので、そこが崩れると読みの木を降りる起点が消える。

    **受け入れは「1手で届く語がただ1つ」**——族をまたいで数える
    （`_one_edit_words`）。頭の族だけで決めると、別の族の1手のほうが
    正しい行を横取りして壊す（実測・readcheck の化け +59）。

    育ちの入れ物で数えた（初期語彙225語の先頭を崩した 1,837件）:

        **1手がただ1つ＝正解（採れる）** … **884件**
        1手の候補が2つ以上（身を引く）   …  861件（既存の道が決める）
        崩した形がそれ自体で語（触れない）…   88件
        **ただ1つだが別（誤爆）**        …    **1件**

    ほかの門（狭く始める。うにさんの「1歩ずつ」）:

        ・**連続がそれ自体で語（＋助詞の尾）なら触らない**
        ・**3字以上**の連続だけ
        ・**前が漢字・カタカナなら見ない**——送り仮名や複合語の途中を
          「語の頭」と読み違えるため。行頭・記号・空白の直後だけを
          「語の始まり」の証拠にする

    **既定では動かない**（`CORRECTNOTE_DESIGN41=1` で入る）。理由は
    下の「測って、入れなかった」。

    戻り値: [(開始, 終了, 直したかな), ...]
    """
    if not _DESIGN41_ON:
        return []

    def _runs():
        i, n = 0, len(line)
        while i < n:
            if is_hiragana(line[i]) or line[i] == 'ー':
                j = i
                while j < n and (is_hiragana(line[j]) or line[j] == 'ー'):
                    j += 1
                yield i, j
                i = j
            else:
                i += 1

    out = []
    _min = _DESIGN41_MIN
    for rs, re_ in _runs():
        run = line[rs:re_]
        if len(run) < _min or run[0] == 'ー':
            continue
        if rs > 0 and (is_kanji(line[rs - 1]) or is_katakana(line[rs - 1])):
            continue            # 送り仮名・複合語の途中かもしれない
        if _kana_run_backed(run, store):
            continue            # そのままで語＝打ち間違いではない
        # **まず安い判定**（頭の族だけ）。ここで決まらなければ、
        # 高い全族の走査はしない。
        head_only = _one_edit_words(run, store, limit='頭')
        if len(head_only) != 1:
            continue
        fixed = next(iter(head_only))
        every = _one_edit_words(run, store)
        if len(every) != 1:
            continue            # 別の族の1手もある。既存の道に任せる
        try:
            from loanword import katakana_for_hiragana
            kata = katakana_for_hiragana(fixed, store, min_length=3)
        except Exception:
            kata = None
        shown = kata or fixed
        if decisions is not None:
            try:
                if decisions.blocks(run, shown):
                    continue
            except Exception:
                pass
        if shown == run:
            continue
        _trace('かな連続', f'{run!r} → 頭の1字を隣のキーで戻すと '
                           f'{shown!r}（設計41・1手はこれだけ）')
        out.append((rs, re_, shown))
    return out


def _decided_spans(line, decisions):
    """
    **うにさんが「もう直さない」と決めた文字列**が、この行のどこに
    在るか（2026-08-28・項目48-KO）。

    候補一覧のいちばん下の2つ——「この補正は不要（X のまま）」と
    「「X」は今後直さない」——で覚えたものを、`decisions` から取る。
    重なりを見るので、**印のほうが広くても狭くても外れる**
    （`奥悠久子帝` を決めたなら `久子帝` の印も消える）。
    """
    out = []
    if decisions is None or not line:
        return out
    try:
        texts = decisions.left_alone_texts()
    except Exception:
        return out          # 古い形の判断置き場でも落ちない
    for w in texts:
        if not w or len(w) < 2:
            continue
        at = 0
        while True:
            p = line.find(w, at)
            if p < 0:
                break
            out.append((p, p + len(w)))
            at = p + 1
    return out


def visible_odd_spans(line, odd_spans, decisions):
    """
    **画面に出す紫だけを残す**（項目48-QY・2026-09-05）。
    **紫下げの門は、これ1本**（48-GN——同じ判定を2か所に書かない）。

    ### なぜエンジンから描画側へ移したか

    もとは `_odd_spans_for_line` の中で間引いていた。だが
    `decisions.leave_odd_alone`（紫を下げるだけの台帳・48-QU）は
    **補正の答えを1バイトも変えない**のに、間引きがエンジン側に在ると
    「印を1つ下ろす」ために**解析をやり直す**しかなかった:

        `_leave_odd_alone` → `_after_decision` → `_reanalyze_all`
        → 全タブの控えを捨てて `_prev_lines` を空にする
        → 全行が `_blank_result`（補正色も網掛けも紫も無い）になり、
          **色の消えた画面が一度出てから**塗り直される

    うにさんの報告そのもの——「**他の行の補正の色が一度消えて
    再度つく**」（2026-09-05）。**捨てる理由が無い。**

    印だけの門を描画側へ移せば、下げ／取り消しは**塗り直すだけ**で済む。

    ### 掛ける場所（学び22——1つ漏れるとそこだけ紫が出続ける）

    画面へ紫を塗る口は**アプリに1か所しか無い**
    （`tag_add('odd')` は全ファイルで `app.py` の1か所）。そこに掛ける。
    `_odd_span_at`・F2 の「この文字列は正しい」・実画面の見張り
    （`probe_odd_protect` / `probe_odd_color`）は**塗ったタグを読む**ので
    自動で追従する。**紫を数える道具は `correct_line` に `decisions` を
    渡していない**ので、前も後も素通し＝ものさしの数字は動かない。

    `odd_spans` も `_decided_spans` も**原文の上の位置**なので、
    座標系はそのまま合う。
    """
    if not odd_spans:
        return []                      # 紫が無い行では何もしない（費用）
    drop = _decided_spans(line, decisions)
    if not drop:
        return list(odd_spans)
    return [(a, b) for a, b in odd_spans
            if not any(not (b <= s0 or a >= e0) for s0, e0 in drop)]


def _odd_spans_for_line(line, tokenize_fn, taken,
                        store=None, dict_index=None, reasons_out=None):
    """
    **異様と見た範囲を紫で見せるための位置**（項目48-IR・2026-08-23）。

    うにさんの指定:「異様な文字列、つまり解釈できない文字列や、
    それは何と感じる文字列に色を付けてください。**どこまで判定できて
    いるのか、よく分からないので**」。

    直せた範囲（taken）と重なるものは外す（直したものは色が要らない）。
    印の中身は `oddness.is_odd_run`（項目48-HO/48-HT/48-IP）で、
    ここは位置を並べるだけ。表が無い・解析できないときは []。

    `reasons_out` を渡すと、**印を立てた理由**を
    `[(始まり, 終わり, 理由の言葉), ...]` で積む（項目48-MD・
    2026-08-31。候補一覧の「－ 補正根拠 －」の1行目）。
    **落とす前の全部**を積む——直せた範囲は `odd_spans` からは
    消えるが、「なぜ直したのか」を聞かれるのはまさにそこなので、
    理由の側には残す。**答えは1文字も変えない**（積むだけ）。

    **うにさんが「もう直さない」と決めた範囲を落とすのは、ここではない**
    （2026-08-28・項目48-KO → **48-QY で描画側へ移した**・2026-09-05）:

        「候補の一番下から、**もう直さないと選択学習したものは、
          紫の色がつかないように**して」

    紫は「**異様だと判定した**」という印（CLAUDE.md ★★）なので、
    本人が「これでよい」と決めた文字列に立て続けるのは、判定として
    間違っている。**決めた側が上。**

    ★★ ただし**それは「見せるか」の話**であって、判定そのものでは
    ない。だからここは**素の紫**を返し、間引きは `visible_odd_spans`
    が画面の直前で1回だけ行う（理由はあちらの説明）。
    **この関数は `decisions` を受け取らない**——受け取ると
    「門はここにも在る」と読まれ、いつか2か所に増える（48-GN）。
    """
    if not line or tokenize_fn is None:
        return []
    def _why(a, b, text):
        """印の出どころを1件控える（`reasons_out` が在るときだけ）。"""
        if reasons_out is not None:
            reasons_out.append((a, b, text))

    try:
        import oddness as _odd
        # 理由は `odd_spans` の中で積んでもらう（繋ぐ前の対ごと）。
        # **もう一度 `is_odd_run` を呼ばない**——同じ判定を2度回すと
        # 1行ぶんの手間が倍になるうえ、いつか食い違う（48-GN）。
        spans = list(_odd.odd_spans(line, tokenize_fn,
                                    reasons_out=reasons_out,
                                    store=store, dict_index=dict_index))
    except Exception:
        spans = []
    # **かな連続の①-a**（項目48-KS・2026-08-29。うにさんの指定
    # 「品詞を判定したり、品詞の組み合わせとしての予測など動いて
    # いますか？無ければ検討してください」）。語の表・機能語・
    # **活用の文法**（pos_grammar——い段=連用形・て＋補助動詞・
    # イ形容詞の活用…）のどれでも説明の付かない ひらがな連続に
    # 印を立てる。いままで かな側には台帳が無く、`にゅカミス`
    # `ゆすかりた` が「直らず・紫も出ない」だった（48-KJ の問い）。
    # 答えは変えない（印だけ）。`CN_POS_ODD=0` で切れる。
    if os.environ.get('CN_POS_ODD') != '0':
        try:
            import pos_grammar as _pg
            for _a, _b in _pg.odd_kana_spans(line, dict_index, store):
                spans.append((_a, _b))
                _why(_a, _b,
                     '品詞として識別できない（かなの並びに説明が付かない）')
        except Exception:
            pass
    # **姓＋姓の連なり（どちらも語彙の実績0）は異様**（項目48-LE・
    # 2026-08-29。`柚須苅田`——ゆすかりた の IME 変換。janome は
    # 柚須（姓）＋苅田（姓）と読むので品詞対の規則には掛からない）。
    # 実機メモ1,494行でこの形は**的の2行だけ**（誤爆の芽0・実測）。
    # 本人がよく使う姓（語彙に実績）は立てない。印だけ・答えは
    # 変えない。`CN_POS_ODD=0` で一緒に切れる。
    if os.environ.get('CN_POS_ODD') != '0' and store is not None:
        try:
            from morphology import katakana_to_hiragana as _k2h
            _tk = list(tokenize_fn(line))
            for _i in range(len(_tk) - 1):
                _ta, _tb = _tk[_i], _tk[_i + 1]
                if _ta[4] != _tb[3]:
                    continue
                _sei_a = (_ta[1] or '') == '名詞:固有名詞:人名:姓'
                _sei_pair = _sei_a \
                    and (_tb[1] or '') == '名詞:固有名詞:人名:姓'
                # **実績0の姓＋用言**も同じ形（項目48-LV・2026-08-30
                # 20回目。`柚須借りた`——ゆすかりた の変換ゆれ。
                # 使わない珍しい姓の直後に動詞が続く文は、姓＋姓と
                # 同じく IME の切り違いの疑いが濃い。**印だけ**）
                _sei_verb = _sei_a \
                    and (_tb[1] or '').startswith('動詞:自立')
                if not (_sei_pair or _sei_verb):
                    continue
                _why_text = ('実績の無い姓が2つ続いている'
                             if _sei_pair
                             else '実績の無い姓に用言が直付き')
                _used = False
                for _t in ((_ta, _tb) if _sei_pair else (_ta,)):
                    for _e in store.lookup(_k2h(_t[2] or '')):
                        if _e.get('surface') == _t[0] \
                                and _e.get('count', 0) >= 1:
                            _used = True
                            break
                    if _used:
                        break
                if not _used:
                    spans.append((_ta[3], _tb[4]))
                    _why(_ta[3], _tb[4], _why_text)
        except Exception:
            pass
    # 方針2 が惜しいところで止まった語（項目48-JH・上の
    # `_HOMOPHONE_UNSURE`）。答えは変えず、認識だけ紫で見せる。
    # **並記の右側は付けない**——その出現より前に、同読みの別表記が
    # 行に書かれているなら、そこは正しい側（`治り ⇒ 直り` の 直り）。
    # **異様と判定したのに決める先が無かった範囲**（項目48-JW）。
    # 設計42 が置いた台帳。直せた範囲（taken）と重なるものは下で外れる。
    for _a, _b in _ODD_PENDING:
        if 0 <= _a < _b <= len(line):
            spans.append((_a, _b))
            _why(_a, _b, '異様だと見たが、直し先を決められなかった')
    for w, alts in _HOMOPHONE_UNSURE:
        at = 0
        while True:
            p = line.find(w, at)
            if p < 0:
                break
            at = p + len(w)
            if any(0 <= line.find(a) < p for a in alts):
                continue
            spans.append((p, p + len(w)))
            _why(p, p + len(w),
                 f'同じ読みの別の語と迷った（{"・".join(alts[:3])}）')
    spans.sort()
    # **同じところに2つ印を立てない**（項目48-JW）。設計42 の台帳と
    # `oddness` が同じ範囲を見ていることがあり、そのままだと紫が
    # 二重に付く。**内側に入っている範囲も落とす**（`的手図` が在れば
    # `手図` は要らない）——うにさんの「候補も大げさ」（48-GL）と同じ用心。
    kept = []
    for a, b in spans:
        if any(s0 <= a and b <= e0 for s0, e0 in kept):
            continue
        kept = [(s0, e0) for s0, e0 in kept
                if not (a <= s0 and e0 <= b)]
        kept.append((a, b))
    kept.sort()
    # 直せた範囲（taken）を外す。**「もう直さない」と決められた範囲は
    # ここでは外さない**——`visible_odd_spans` が画面の直前で外す
    # （項目48-QY）
    drop = list(taken)
    return [(a, b) for a, b in kept
            if not any(not (b <= s0 or a >= e0) for s0, e0 in drop)]


# 48-VZ: 再帰的な補正でも、利用者が最初に書いた本文を失わない。
# 呼び出しが終われば破棄する。履歴やファイルには保存しない。
from contextvars import ContextVar
from functools import wraps
_CORRECTION_SOURCE = ContextVar('correctnote_correction_source', default=None)


def _with_correction_source(fn):
    @wraps(fn)
    def wrapped(line, *args, **kwargs):
        if _CORRECTION_SOURCE.get() is not None:
            return fn(line, *args, **kwargs)
        token = _CORRECTION_SOURCE.set(line)
        try:
            return fn(line, *args, **kwargs)
        finally:
            _CORRECTION_SOURCE.reset(token)
    return wrapped


@_with_correction_source
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
    # **読みの探索に、入力方式を結び付ける**（項目48-NJ・2026-09-01）。
    # `find_known_readings_flex` は**かなキー配列の距離**だけで候補を
    # 集めていて、ローマ字入力の人には別の配列だった。呼び出しは
    # この関数の中に何十か所もあるので、**入口で1回だけ結ぶ**
    # （学び22——道ごとに書き分けない）。受け取らない探索関数
    # （古い呼び出し・見張りの偽物）でも落ちないようにする。
    try:
        import inspect as _insp
        if 'input_method' in _insp.signature(find_readings).parameters:
            import functools as _ft
            find_readings = _ft.partial(find_readings,
                                        input_method=input_method)
    except Exception:
        pass
    empty = {'original': line, 'corrected': line, 'changed': False,
             'details': [], 'spans': [], 'original_spans': [],
             'unsure_spans': [], 'odd_spans': [], 'odd_reasons': []}
    if not line or not line.strip():
        return empty
    # 方針2 の「惜しく止まった」控えは行ごと（項目48-JH）。
    # 濁点合成の再入では内側が自分で消して自分で使い切る。
    del _HOMOPHONE_UNSURE[:]
    del _ODD_PENDING[:]

    # --- 設計39: 場違いな濁点を、隣のキーで戻す（項目48-JP）---------
    # **`normalize_marks` より前に置く。** あちらは説明の付かない印を
    # 落とすので、後ろに置くと**材料が消えてから**探すことになる
    # （`もじ゛つ` が `もじつ` になってから `もじれつ` を探しても届かない）。
    # 直した行を丸ごと補正し直せば、中身は普段の道で直る
    # （下の濁点合成・括弧と同じ形）。**印が1つ減る方向にしか進まない**
    # ので、この入れ子は必ず止まる。
    # --- 項目48-LA': 遅れて打たれた濁点（設計39 より**前**）----------
    # 設計39 は浮いた ゛ を「隣のキー（れ）の打ち間違い」と見るが、
    # `かたい゛`（た に付くはずの ゛ が遅れた）はそれより先に、
    # **語彙の実績つき**で当てはめ先を探す（かだい＝課題69。証拠が
    # 立てばこちら、立たなければ今までどおり設計39へ）。
    _ld0 = _lagged_dakuten_fixes(line, store, tokenize_fn, dict_index)
    if _ld0:
        _ld_chars = list(line)
        for _ld_s, _ld_e, _ld_fix, _ld_c in reversed(sorted(_ld0)):
            _ld_chars[_ld_s:_ld_e] = list(_ld_fix)
        _ld_line = ''.join(_ld_chars)
        if _ld_line != line:
            inner = correct_line(_ld_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    _dk = _misplaced_dakuten_fixes(line, store)
    if _dk:
        _d_chars = list(line)
        for _dk_s, _dk_e, _dk_fix in reversed(_dk):
            _d_chars[_dk_s:_dk_e] = list(_dk_fix)
        _d_line = ''.join(_d_chars)
        if _d_line != line:
            inner = correct_line(_d_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # --- 設計40: 伸ばし棒（ー）の打ち間違いを戻す（項目48-JS）-------
    # 設計39 と同じ形（直した行を丸ごと補正し直す）。**平仮名のまま
    # 止めない**——止めると `かろそる` が `かーそる` で終わって、
    # いままで `カーソル` になっていたものが悪くなる。
    _lv = _misplaced_long_vowel_fixes(line, store, decisions)
    if _lv:
        _lv_chars = list(line)
        for _lv_s, _lv_e, _lv_fix in reversed(_lv):
            _lv_chars[_lv_s:_lv_e] = list(_lv_fix)
        _lv_line = ''.join(_lv_chars)
        if _lv_line != line:
            inner = correct_line(_lv_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # --- 項目48-KV: 場違いな大書き（Shift の押し忘れ）を小書きに ----
    # 設計39・40 と同じ形（**直した行を丸ごと補正し直す**——かなで
    # 止めると、育ちで にゆうりょくミス → 入力ミス まで届いていた行が
    # にゅうりょくミス 止まりになる・実測）。48-KS の異様判定が立つ
    # 連続だけ開く（①→③→④）。直した連続には い段＋大書き が
    # 残らないので、この入れ子は必ず止まる。
    _kv = _misplaced_large_kana_fixes(line, store, dict_index)
    # 項目48-KX'（語幹＋接尾で組む）も同じ口に載せる（重なりは KV 優先）
    for _ck in _compose_kana_run_fixes(line, store, dict_index):
        if not any(not (_ck[1] <= s0 or _ck[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_ck)
    # 項目48-LD（素のかな連なりに手を1つ）も同じ口に載せる
    for _kh in _kana_run_hand_fixes(line, store, dict_index, input_method=input_method):
        if not any(not (_kh[1] <= s0 or _kh[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_kh)
    # 項目48-KZ (S2)（形容詞の語幹＋て → い）も同じ口に載せる
    for _at in _adjective_tail_fixes(line, store, tokenize_fn, dict_index):
        _at4 = (_at[0], _at[1], _at[2], 'かな入力')
        if not any(not (_at4[1] <= s0 or _at4[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_at4)
    # 項目48-LL（音便のあとの た/だ）も同じ口に載せる
    for _ob in _onbin_dakuten_fixes(line, store, tokenize_fn, dict_index):
        _ob4 = (_ob[0], _ob[1], _ob[2], 'かな入力')
        if not any(not (_ob4[1] <= s0 or _ob4[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_ob4)
    # 項目48-LA（混ざった連なりを連なりごと開く）も同じ口に載せる
    for _mx in _reopen_mixed_run_fixes(line, store, tokenize_fn,
                                       dict_index, input_method):
        if not any(not (_mx[1] <= s0 or _mx[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_mx)
    # 項目48-NN（ナ形容詞の語幹＋動詞に「に」を入れる）も同じ口に。
    # **1字の助詞の脱字は、隣接キーより先に疑う**（うにさんの指定）
    for _ni in _insert_na_ni(line, tokenize_fn):
        if not any(not (_ni[1] <= s0 or _ni[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_ni)
    # 項目48-NS（副詞＋に の後ろの名詞を、かなに開く）も同じ口に。
    for _an in _open_adv_ni_noun(line, tokenize_fn):
        if not any(not (_an[1] <= s0 or _an[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_an)
    # 項目48-PQ（カタカナのサ変名詞＋接尾 語 → 後）も同じ口に。
    for _kg2 in _katakana_go_after_fixes(line, tokenize_fn):
        if not any(not (_kg2[1] <= s0 or _kg2[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_kg2)
    # 項目48-SA（人名＋を＋叙述の動詞 → 同音の普通語）も同じ口に。
    for _pj in _person_object_fixes(line, store, tokenize_fn, dict_index):
        if not any(not (_pj[1] <= s0 or _pj[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_pj)
    # 項目48-NK（異様な1字の漢字を、読みのかなに開く）も同じ口に。
    for _o1 in _open_odd_single_kanji(line, tokenize_fn):
        if not any(not (_o1[1] <= s0 or _o1[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_o1)
    # 項目48-MI（かなのまま残った漢語を変換）も同じ口に載せる。
    # **いちばん最後**——これは「異様だから直す」ではなく
    # 「かなのままの確信が無いから変換する」という別の理由なので、
    # 直しの手が立つ場所には割り込ませない。
    for _kg in _kango_kana_fixes(line, store, dict_index):
        if not any(not (_kg[1] <= s0 or _kg[0] >= e0)
                   for s0, e0, _f0, _c0 in _kv):
            _kv.append(_kg)
    _kv.sort()
    # **読みの並記は書きたい形**（項目48-LS）——この口の直しにも、
    # 最終検査（checked の門）と同じ判定を掛ける。ここは行を
    # 丸ごと書き換える**もう1つの適用点**で、48-LD がここを通って
    # `しょくじけん（食事券）→ 初期事件（食事券）` を作っていた
    # （学び22——片方だけに置くと、そちらを迂回して素通りする）。
    _kv_kept = []
    for _t in _kv:
        if _reading_spelled_in_bracket(line, _t[0], _t[1], tokenize_fn):
            _trace('置換', f'{line[_t[0]:_t[1]]!r} → {_t[2]!r} は、直後の'
                           f'括弧に表記が並ぶ読みの並記なので触らない')
            continue
        _kv_kept.append(_t)
    _kv = _kv_kept
    if _kv:
        _kv_chars = list(line)
        for _kv_s, _kv_e, _kv_fix, _kv_c in reversed(_kv):
            _kv_chars[_kv_s:_kv_e] = list(_kv_fix)
        _kv_line = ''.join(_kv_chars)
        if _kv_line != line:
            inner = correct_line(_kv_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # --- 設計41: かな連続の頭の1字を隣のキーで戻す（項目48-JT）-----
    # 設計40 と同じ形（直した行を丸ごと補正し直す）。
    # **連続がそれ自体で語なら触らない**ので、正しく書けたものは通らない。
    _hd = _head_typo_fixes(line, store, decisions)
    if _hd:
        _hd_chars = list(line)
        for _hd_s, _hd_e, _hd_fix in reversed(_hd):
            _hd_chars[_hd_s:_hd_e] = list(_hd_fix)
        _hd_line = ''.join(_hd_chars)
        if _hd_line != line:
            inner = correct_line(_hd_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # --- 設計42: 読みを語の境目で切り直す（項目48-JV）-------------
    # 設計39〜41 と同じ形（直した行を丸ごと補正し直す）。
    # **異様判定を先に立ててから開く**（うにさんの決まり
    # 「異様であれば何かしらの補正をします。そのままにはしません」）。
    _rs = _resegment_fixes(line, tokenize_fn, store, dict_index, decisions)
    # --- 項目48-KT: 読みを繋ぐと1語（待ち外 ⇒ 間違い）。設計42 と
    # 同じ口に載せる（直した行を丸ごと補正し直す）。`CN_RUN_MERGE=0`
    # で切れる。範囲は設計42 と重ならない（あちらは「どの語も単独で
    # 立っていない」連なり・こちらは「単独で立つ語の連なり」）。
    if os.environ.get('CN_RUN_MERGE') != '0':
        _rm = _run_reading_merge_fixes(line, tokenize_fn, store,
                                       dict_index, decisions)
        if _rm:
            _rs = sorted(_rs + [x for x in _rm
                                if not any(not (x[1] <= s or x[0] >= e)
                                           for s, e, _f in _rs)])
    if _rs:
        _rs_chars = list(line)
        for _rs_s, _rs_e, _rs_fix in reversed(_rs):
            _rs_chars[_rs_s:_rs_e] = list(_rs_fix)
        _rs_line = ''.join(_rs_chars)
        if _rs_line != line:
            inner = correct_line(_rs_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # --- 設計43: 助詞をはさんだ読みを1語へ寄せる（項目48-JZ）--------
    # 設計42 と同じ形（直した行を丸ごと補正し直す）。対の表と門は
    # `_D43_PAIRS` を見る。
    # --- 設計44: 並記の親戚（項目48-KA）は同じ口に載せる ------------
    # `_parallel_pair_fixes` は2か所を原子的に返す。範囲は互いに
    # 重ならないので、設計43 の直しと同じ形で当てられる。
    _pm = (_particle_merge_fixes(line, tokenize_fn, decisions)
           + _parallel_pair_fixes(line, tokenize_fn, decisions))
    if _pm:
        _pm.sort()                  # 後ろから当てるので昇順に揃える
        _pm_chars = list(line)
        for _pm_s, _pm_e, _pm_fix in reversed(_pm):
            _pm_chars[_pm_s:_pm_e] = list(_pm_fix)
        _pm_line = ''.join(_pm_chars)
        if _pm_line != line:
            inner = correct_line(_pm_line, store, tokenize_fn, find_readings,
                                 max_dist=max_dist,
                                 context_vocab=context_vocab,
                                 decisions=decisions, context_vec=context_vec,
                                 dict_index=dict_index,
                                 input_method=input_method,
                                 nearby_words=nearby_words,
                                 recent_words=recent_words)
            corrected = inner['corrected']
            changed = corrected != line
            spans = []
            original_spans = []
            details = []
            if changed:
                for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
                # **内側の印を外の行の位置へ写す**（項目48-RU）——
                # 捨てると、同じ行の別の塊の紫まで消える
                'unsure_spans': _map_inner_spans(
                    line, inner['original'], inner.get('unsure_spans', [])),
                'odd_spans': _map_inner_spans(
                    line, inner['original'], inner.get('odd_spans', [])),
            }

    # かな入力では濁点・半濁点が独立したキーなので、
    # 「たんこ゛」のように濁点だけが分離して残ることがある。

    # これを「たんご」に合成してから補正にかける。
    # 合成できない組み合わせ（「こ゜」など）は濁点キーの誤打なので
    # normalize_marks 側で取り除かれる。
    _mark_dropped = []
    try:
        from morphology import normalize_marks
        normalized = normalize_marks(line, dropped=_mark_dropped)
    except Exception:
        normalized = line
    # **落としただけか**（合成が1つも起きていないか）を、
    # ここで見ておく（項目48-OG）。落とした位置を抜いた形と
    # 同じなら、この行で起きたのは**印を消したことだけ**。
    _only_dropped = False
    if _mark_dropped:
        try:
            _cut = ''.join(c for i, c in enumerate(line)
                           if i not in set(_mark_dropped))
            _only_dropped = (_cut == normalized)
        except Exception:
            _only_dropped = False
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
        # **印を落としただけで、何も直せなかったなら元に戻す**
        # （項目48-OG・2026-09-02）。
        #
        #     硬い゛に取り掛かる → **硬いに取り掛かる**
        #       （本来は かたい゛ → かだい → 課題に取り掛かる）
        #
        # 落とすのは「かなを打った直後に濁点キーを叩いた」という
        # 見立てで、**その先で語に届いてはじめて裏が取れる**。
        # 届かないなら見立ては立っていないので、★★「判断がつかない
        # ものは触らない（色を付けて知らせるだけ）」に従う。
        # **印は打った人が打ったもの**で、消すと
        #   ・打った人の文が変わる（壊さない ＞ 直る）
        #   ・**次に直すための材料が消える**
        # 合成（たんこ゛→たんご）が1つでも起きていれば、それは
        # 落としたのではないので、ここには入らない（`_only_dropped`）。
        if _only_dropped and not inner['changed'] \
                and inner['corrected'] == normalized:
            _trace('かな入力', f'{line!r} → 印を落としただけで先へ'
                               f'進めないので、**元に戻す**（項目48-OG）')
            return {
                'original': line,
                'corrected': line,
                'changed': False,
                'details': [],
                'spans': [],
                'original_spans': [],
                'unsure_spans': inner.get('unsure_spans', []),
                'odd_spans': _odd_spans_for_line(
                    line, tokenize_fn, (),
                    store=store, dict_index=dict_index),
            }
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
            for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
            # **内側の印を外の行の位置へ写す**（項目48-RU）
            'unsure_spans': _map_inner_spans(
                line, inner['original'], inner.get('unsure_spans', [])),
            'odd_spans': _map_inner_spans(
                line, inner['original'], inner.get('odd_spans', [])),
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
        _brk_pos = {s for s, _e, _r in _brk}
        for i1, i2, j1, j2 in _diff_spans(line, corrected):
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
            # **内側の印を外の行の位置へ写す**（項目48-RU）
            'unsure_spans': _map_inner_spans(
                line, inner['original'], inner.get('unsure_spans', [])),
            'odd_spans': _map_inner_spans(
                line, inner['original'], inner.get('odd_spans', [])),
        }

    # --- かなで書いたアルファベットの読み（`エフ2 → F2`）---
    # うにさんの指定（2026-08-23・項目48-IZ）。項目48-IB で
    # 「いまの経路に無い機能」として残してあった5組。
    # **括弧と同じ形**——先に字へ戻し、戻した行を普段の道で
    # 補正し直す（英字になれば、あとは今までどおり）。
    _alp = _fix_kana_alphabet(line, store, tokenize_fn, dict_index)
    if _alp:
        _a_line, _a_prev = [], 0
        for _a_s, _a_e, _a_r in _alp:
            _a_line.append(line[_a_prev:_a_s])
            _a_line.append(_a_r)
            _a_prev = _a_e
        _a_line.append(line[_a_prev:])
        _a_line = ''.join(_a_line)
        inner = correct_line(_a_line, store, tokenize_fn, find_readings,
                             max_dist=max_dist, context_vocab=context_vocab,
                             decisions=decisions, context_vec=context_vec,
                             dict_index=dict_index,
                             input_method=input_method,
                             nearby_words=nearby_words,
                             recent_words=recent_words)
        corrected = inner['corrected']
        spans, original_spans, details = [], [], []
        _a_pos = {s for s, _e, _r in _alp}
        for i1, i2, j1, j2 in _diff_spans(line, corrected):
            original_spans.append((i1, i2))
            spans.append((j1, j2))
            details.append((line[i1:i2], corrected[j1:j2],
                            'アルファベット' if i1 in _a_pos else 'かな入力'))
        return {
            'original': line,
            'corrected': corrected,
            'changed': corrected != line,
            'details': details,
            'spans': spans,
            'original_spans': original_spans,
            # 位置が動いているので、**写して**渡す（項目48-RU。
            # 前は「そのまま渡せない」と捨てていた）
            'unsure_spans': _map_inner_spans(
                line, inner['original'], inner.get('unsure_spans', [])),
            'odd_spans': _map_inner_spans(
                line, inner['original'], inner.get('odd_spans', [])),
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
    lu_taken = []       # 語の列として組み直した範囲（項目48-LU）
    # **かなを漢字に変換した範囲**（項目48-NF）。変換は語ごとに縮む
    # （がいしゅつする → 外出する は3字ぶん）ので、下の「長さの検査」
    # から外す。48-LU と同じ理由・同じ扱い。
    conv_taken = []

    # --- 設計38: 場違いな小書きを隣のキーで戻す（項目48-JN）----------
    # 異様の判定が構造だけで立つ（正しい文に場違いな小書きは無い）ので、
    # どの探索よりも先に置く。採った範囲はかな連続の道から外す
    # （_d38_taken は後段の hiragana_taken の初期値になる）。
    _d38_taken = []
    for _ms, _me, _mf, _mc in _misplaced_small_kana_fixes(line, store):
        replacements.append((_ms, _me, _mf, _mc))
        _d38_taken.append((_ms, _me))

    def _odd_judge(candidate):
        # 半角入力から組み立てた候補を裁く口（項目48-JC・2026-08-25）。
        # うにさんの指定「**異様ならさらに次の変換候補を追ってもらいます**」
        # （2026-08-24）。異様と見た範囲を返す（`oddness.odd_spans`——
        # 画面の紫と同じ判定。判断経路を増やさない）。
        # 表が無い・解析できないときは []（意見なし）＝今までどおり。
        try:
            import oddness as _odd
            return _odd.odd_spans(candidate, tokenize_fn,
                                  store=store, dict_index=dict_index)
        except Exception:
            return []

    for start, end, chunk in find_halfwidth_runs(line):
        # 全角で入ってしまった場合は、まず半角に戻して解釈する
        # （ｍｄ＠い（４ｌ）ｈ → md@i(4l)h → もじにゅうりょく）
        fixed = None
        if has_zenkaku_ascii(chunk):
            fixed = correct_zenkaku_input(chunk, store, find_readings,
                                          max_dist, judge=_odd_judge)
        if not fixed:
            # かな入力配列として解釈する（md@i(4l)h → もじにゅうりょく）
            fixed = correct_halfwidth(chunk, store, find_readings, max_dist,
                                      judge=_odd_judge)
        if not fixed:
            # ローマ字として解釈する（mojinyuuryoku → もじにゅうりょく）
            fixed = correct_romaji(chunk, store, find_readings, max_dist,
                                   judge=_odd_judge)
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
            # ★★ **同梱の表が「1語として在る」と言うなら触らない**
            # （項目48-UG'・2026-09-07・**学び22**）。
            # 48-FC は造語の道、48-UG は漢字塊の道。**3つ目がここ**。
            # `probe_seed_intact.py` の 800 語で、造語も漢字塊も
            # 断れているのに**この道だけが走って壊していた**:
            #
            #     小川忠 → **コンチュウ**   青グマ → **アナグマ**
            #     ニルソン図 → **煮るソントン**
            try:
                import seed_japanese as _sj_mx
                if _sj_mx.is_unit(chunk) is True:
                    _trace('混合塊', f'{chunk!r} は1語として在る'
                                     f'（項目48-FC の門を混合塊にも・'
                                     f"48-UG'）ので触らない")
                    continue
            except Exception:
                pass
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
            # **かなの頭が機能語の並びとして立ち、残りが漢字1〜2字**の
            # 塊は、字種の変わり目で切れて見えただけ——読み直さない
            # （項目48-LN・2026-08-30。うにさんの誤検知報告
            # `位置が上方にあって下との距離 → …悪化との距離`。
            # あって は動詞＋て の続き、下 は独立した位置の語）
            _kh = 0
            while _kh < len(chunk) and is_hiragana(chunk[_kh]):
                _kh += 1
            if _kh >= 2 and 1 <= len(chunk) - _kh <= 2 \
                    and all(is_kanji(c) for c in chunk[_kh:]) \
                    and _is_functional_strict(chunk[:_kh]):
                _trace('混合塊', f'{chunk!r} → かなの頭 {chunk[:_kh]!r} は'
                                 f'機能語の並びで、残りは独立した漢字。'
                                 f'読み直さない（項目48-LN）')
                continue
            _ex = _ime_exact_respell(chunk, store, tokenize_fn, dict_index)
            if _ex is not None:                     # 設計30（項目48-IX）
                replacements.append((t_start, t_end, _ex[0], _ex[1]))
                kanji_taken.append((t_start, t_end))
                continue
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
            _ex = _ime_exact_respell(chunk, store, tokenize_fn, dict_index)
            if _ex is not None:                     # 設計30（項目48-IX）
                replacements.append((m_start, m_end, _ex[0], _ex[1]))
                kanji_taken.append((m_start, m_end))
                continue
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
                        tokenize_fn, input_method):
                    # --- 設計32（項目48-IW・2026-08-23）: 違和感の範囲を
                    # 左端から要素で割り直す ---
                    # 組でも芯でも決まらない漢字頭の混合塊は、ここまで
                    # **黙って**終わっていた（`学外しょつする` → 記録0件で
                    # 抜け、B道が `しょつ` だけを `しょーつ` にしていた）。
                    # 頭のかなを足して要素で割り直す道へ順番を回す
                    # （入口を増やすだけ。判断は `_resplit_by_elements` の
                    # 中に全部書いてある）。
                    if is_kanji(chunk[0]):
                        _rs = _resplit_by_elements(
                            line, m_start, m_end, chunk, tokens, store,
                            tokenize_fn, dict_index=dict_index,
                            input_method=input_method)
                        if _rs is not None and not any(
                                not (m_end <= s or _rs[0] >= e)
                                for s, e in halfwidth_taken + kanji_taken):
                            replacements.append(
                                (_rs[0], m_end, _rs[1], _rs[2]))
                            kanji_taken.append((_rs[0], m_end))
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
                    chunk, [_sr], store, dict_index, tokenize_fn,
                    prev_char=(line[m_start - 1] if m_start > 0 else ''))
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
                    store, dict_index, tokenize_fn,
                    prev_char=(line[m_start - 1] if m_start > 0 else ''))
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
            # --- 設計30（項目48-IX）: 打った読みがそのまま語彙の語 ---
            # 読める塊（`待ち外`＝待ち＋外）でも、本人が打った読みが
            # 語彙の語に一致し、いまの表記が語として無いなら組み直す。
            # 3つの道（漢字塊・かな＋漢字・混合塊）に同じ口を置く（学び22）
            _ex = _ime_exact_respell(chunk, store, tokenize_fn, dict_index)
            if _ex is not None:
                replacements.append((k_start, k_end, _ex[0], _ex[1]))
                kanji_taken.append((k_start, k_end))
                continue
            _readable = looks_like_real_word(chunk, store, tokenize_fn)
            # ★★ **同梱の表が「1語として在る」と言うなら読める**
            # （項目48-UG・2026-09-07・**学び22**）。
            #
            # 同じ門は 48-FC で**造語の道にだけ**掛かっていた。
            # `tools_local/probe_seed_intact.py` で漢字を含む 800 語を
            # 当てたら、**造語の道は自分から断れているのに、この道が
            # 走って壊していた**（48-QX と同じ形）:
            #
            #     和田垣  → **お互い**    小川忠 → **コンチュウ**
            #     ダンバー数 → **段ボール** ニルソン図 → **煮るソントン**
            #     不二見  → **不気味**    青グマ → **アナグマ**
            #     グリセロリン酸 → **グリセリン酸**
            #
            # どれも**人名・地名・学術語**——「語彙に無い」は
            # 「壊れている」ではない（48-EN と同じ言い分）。
            # 解析（`looks_like_real_word`）が知らないだけ。
            if not _readable and _chunk_with_okurigana_is_word(
                    line, k_start, k_end):
                # ★★ **塊＋送り仮名が表の語なら、塊は語の一部**
                # （項目48-VB・2026-09-07）。塊は漢字で終わるので、
                # うしろの送り仮名まで含めて初めて1語になる形
                # （`揺さ振`＋`ら`＝揺さ振ら）を取りこぼしていた。
                _trace('漢字塊', f'{chunk!r} は送り仮名まで含めると'
                                 f'1語として在る（項目48-VB）ので読める扱い')
                _readable = True
            if not _readable:
                try:
                    import seed_japanese as _sj_kr
                    if _sj_kr.is_unit(chunk) is True:
                        _trace('漢字塊', f'{chunk!r} は1語として在る'
                                         f'（項目48-FC の門を漢字塊にも・'
                                         f'48-UG）ので読める扱い')
                        _readable = True
                except Exception:
                    pass
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
                #
                # ★★ **上と同じ `_readable` を見る**（項目48-UG''・
                # 2026-09-07）。ここだけ `looks_like_real_word` を
                # 呼び直していたので、**48-UG で足した「同梱の表が
                # 1語だと言う」が効かず**、`小川忠 → コンチュウ` が
                # 残っていた（**同じ判定を2か所に書くと、いつか
                # 食い違う**・48-GN）。
                # 読める側へ入ると 方針1-D（周りの語の裏付けが要る）に
                # なるだけで、道が閉じるわけではない。
                if _readable:
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
                                tokenize_fn, input_method):
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
            #
            # ★★ **恒真になった**（項目48-QG'）。`_usage_count` は
            # 1 か 2 なので `_weak_guess` は常に True ＝ **当てた語が
            # 何であれ、必ずフォールバックとも比べる**。
            # `_USAGE_MIN` の4か所のうち、ここだけは倒れる先が
            # 「決めない」ではなく「**別の直しを採る**」。ただし
            # 対象は異様と判定した塊だけで、フォールバック側にも
            # 「文全体では読める並びなら直さない」門が掛かっている。
            # **初期状態では前から常に True**（count 1〜3）なので、
            # 変わるのは育ちのときだけ。
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
                    _pt_start, _pt_end = k_start, k_end
                    if not _odd_edge:
                        # 項目48-PT: **読みの立たないカタカナ断片は、
                        # 塊に含める**（48-HU の守りは「読みが立つ
                        # カタカナ語に接している」ときだけに絞る）
                        _ext = _pt_extend_over_dead_katakana(
                            line, k_start, k_end, tokens)
                        if _ext is None:
                            _trace('異様', f'{chunk!r} → 端がカタカナに'
                                           f'接しているので、この塊は'
                                           f'途中で切れている。決めない'
                                           f'（設計27・項目48-HU）')
                            continue
                        _pt_start, _pt_end = _ext
                        chunk = line[_pt_start:_pt_end]
                        if any(not (_pt_end <= s or _pt_start >= e)
                               for s, e in kanji_taken):
                            continue
                        _trace('異様', f'{line[k_start:k_end]!r} → 隣の'
                                       f'カタカナは読みの立たない断片な'
                                       f'ので、塊に含めて {chunk!r}'
                                       f'（項目48-PT）')
                    # **塊の頭が、前の語にぶら下がる品詞なら開かない**
                    # （項目48-LN・2026-08-30。`ChaSen用辞書` の 用 は
                    #   行の解析では 名詞:接尾——ChaSen に付く語尾で、
                    #   塊 `用辞書` の頭ではない〔48-KT の さ位置 と
                    #   同じ判定〕。塊だけで解析し直すと 名詞:一般 に
                    #   化けるので、**行の解析の品詞**で見る。
                    #   ようじか → 容赦 と書き換えていた・実測）
                    _head_tok = next((t for t in tokens
                                      if t[3] == k_start), None)
                    _hp = (_head_tok[1] or '') if _head_tok else ''
                    if '接尾' in _hp or '非自立' in _hp:
                        _trace('異様', f'{chunk!r} → 頭 '
                                       f'{_head_tok[0]!r} は前の語に'
                                       f'ぶら下がる品詞。開かない'
                                       f'（項目48-LN）')
                        continue
                    _odd_got = _reopen_odd_chunk(
                        chunk, store, tokenize_fn,
                        dict_index=dict_index, input_method=input_method,
                        assemble=True, vocab_only=True)
                    if _odd_got is not None:
                        replacements.append((_pt_start, _pt_end,
                                             _odd_got[0], _odd_got[1]))
                        kanji_taken.append((_pt_start, _pt_end))
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

    # **`の` で区切ってよいかの見分け**（項目48-MS）。右側が語なら、
    # その `の` は連体化の助詞。表（世の中の語）と本人の語彙の両方を
    # 見る——**名簿は作らない**（どちらも既に在るもの）。
    def _split_known(frag):
        if len(frag) < 2:
            return False
        try:
            import oddness as _odd_sk
            _w = _odd_sk._load()
            if _w and frag in _w:
                return True
        except Exception:
            pass
        try:
            return bool(store.lookup(frag))
        except Exception:
            return False

    # 設計38（場違いな小書き・項目48-JN）が採った範囲を初期値にして、
    # かな連続の道が同じ場所を二重に触らないようにする
    hiragana_taken = list(_d38_taken)
    for run_start, run_end, run in split_runs_at_particle(
            find_hiragana_runs(line), known=_split_known):
        # 半角入力として既に補正した範囲とは重ねない
        if any(not (run_end <= s or run_start >= e) for s, e in halfwidth_taken):
            continue

        # ローマ字入力のつもりで、かな入力モードのまま打った場合。
        # かなをキー配列で半角に戻し、ローマ字として読み直す。
        # 「もらまにみらみんななすんらのな」→「もじにゅうりょく」
        as_romaji = correct_kana_typed_as_romaji(
            run, store, find_readings, max_dist, judge=_odd_judge)
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
        _c22 = _fold_repeat_to_word(run, store, tokenize_fn)
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
            _c23 = _swap_to_word(
                run, store, tokenize_fn=tokenize_fn,
                keep_tail=run_tail_particle(line, run_start, run_end))
        if _c23 is not None:
            _swp, _body = _c23
            _trace('かな連続', f'{run!r} → {_swp!r} に戻す'
                             f'（入れ替え・戻すと {_body!r} が在る語・'
                             f'項目48-HJ）')
            replacements.append((run_start, run_end, _swp, 'かな入力'))
            hiragana_taken.append((run_start, run_end))
            continue
        # **2文字2回（ABAB）の型**（2026-08-28・CN_ABAB=1）。語彙で
        # 説明の付く道（上の畳み・戻し）が先。入口は48-KI のとおり
        # `_chunk_is_intact`（できあがっている塊には走らせない）。
        # **直前が漢字・カタカナなら掛けない**——送り仮名に続く活用の
        # 連なり（消|せませんか・スクロール|してしまいます）は偶然
        # ABAB に1手で届く形だらけで、実機メモの正しい文を壊した
        # （2026-08-28 に実測して足した門）。
        _prev_c = line[run_start - 1] if run_start > 0 else ''
        # ★★ **1つの語の中の断片には掛けない**（項目48-UZ・もう一方の道
        # にも同じ門を・学び22）
        _c24 = (None if (_chunk_is_intact(run, tokenize_fn)
                         or is_kanji(_prev_c)
                         or ('ァ' <= _prev_c <= 'ヶ') or _prev_c == 'ー'
                         or _span_inside_one_token(tokens, run_start,
                                                   run_end))
                else _abab_repair(run, store))
        if _c24 is not None:
            replacements.append((run_start, run_end, _c24[0], 'かな入力'))
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
                # **直し先が「既知語＋1字助詞」に割れる語なら採らない**
                # （項目48-PK・2026-09-04）。`かなで`(65) は本人の語彙に
                # 在るが **かな＋で** であって語ではない——採ると
                # `かなちで` がそこへ吸い込まれる（育ちだけの化け・実測）
                if _target_splits_word_particle(cand_reading, store):
                    _trace('かな連続', f'{target!r} → {cand_reading!r} は'
                                     f'直し先が 既知語＋1字助詞 に割れる'
                                     f'（語ではない）ので採らない'
                                     f'（項目48-PK）')
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
        # **同じ長さの直しは、置き換えだけで説明が付くこと**
        # （項目48-MT・2026-08-31）。長さが同じなのに**位置ごとに
        # 違う字の数**が編集の数より多いなら、それは字が**横にずれて
        # いる**——打ち間違いの形ではない:
        #
        #     かなちで → **さかなで**   頭に さ を足して ち を消す
        #                              （位置の違いは3・編集は2）
        #     にゅうりよく → にゅうりょく  違いも編集も1（打ち間違い）
        #     そももそ → そもそも        違いも編集も2（入れ替え）
        #
        # 打鍵の誤りは**その場**で起きる（置き換え・脱字・重複）。
        # 「頭に足して途中を消す」は**別の語への滑り込み**。
        if len(cand_reading) == (end - start):
            _hamming = sum(1 for _x, _y in zip(line[start:end], cand_reading)
                           if _x != _y)
            if _hamming > edits:
                _trace('かな連続', f'{line[start:end]!r} → {cand_reading!r} は'
                                 f'字が横にずれている（違い {_hamming} ＞ '
                                 f'手 {edits}・項目48-MT）ので採らない')
                continue
        # **長さが変わる直しは、手が1つのときだけ**（項目48-MJ・
        # 2026-08-31。うにさんの画面 `きょだいか ⇒ **きょうか**`）。
        #
        # 長さが変わる＝脱字か重複打鍵で、どちらも**1打の誤り**。
        # そこに置き換えを重ねた「2手で、しかも長さも違う」直しは、
        # 誤りの説明ではなく**近い語への寄せ**になる:
        #
        #     きょだいか（巨大化の読み）→ きょ**う**か  だ→う ＋ い の脱落
        #
        # 語彙に `きょだい` が無いので「読めない並び」に見え、
        # 空いた席へ知っている語が吸い込む型（48-HH と同じ）。
        # **同じ長さの2手はそのまま**（隣接キーが続く形は在る）。
        if len(cand_reading) != (end - start) and edits > 1:
            _trace('かな連続', f'{line[start:end]!r} → {cand_reading!r} は'
                             f'長さが変わるのに手が {edits} つ要る'
                             f'（項目48-MJ）ので採らない')
            continue
        # **数字の直後から始まる連なりは触らない**（項目48-NO・
        # 2026-09-01。うにさんの画面 `以下の2つがある ⇒
        # **以下の2つかえる**`）。
        #
        #     2つがある   ← かな連続は `つがある`（数字は かな でない）
        #                    **助数詞の `つ` が数から切り離されている**
        #                    → 育った語彙の `つかえる`（使える）に
        #                      吸い込まれた（が→か・あ→え の2手）
        #
        # `_preceded_by_digit` は既に在る（助数詞・単位の並びは
        # 数字が「意図した表記」の証拠・項目41/42）。48-LU の
        # 組み直しにも同じ門が掛かっている——**この道だけ素通り
        # だった**（学び22。門は経路ごとに掛け直す）。
        if _preceded_by_digit(line, start):
            _trace('かな連続', f'{line[start:end]!r} → {cand_reading!r} は'
                             f'数字の直後から始まる連なり（助数詞が'
                             f'切れている）ので触らない（項目48-NO）')
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
    # **連続の輪は worklist**（項目48-PI・2026-09-03）。
    # 連続まるごとを今までどおり通し、**何も直らず「色だけ付ける」に
    # 落ちたとき**だけ、助詞のトークンで区切って**左の切れ端を先頭に
    # 戻して**もう一度通す（`_psplit_retry`）。★「区切りは最後の手」
    # ——先に区切ると、連続全体で見る道（48-HI の畳み・48-HJ の戻し・
    # 芯の再構築）が消える（試作 v2 で直りを6語失った）。
    _psplit_work = list(split_runs_at_particle(
        find_hiragana_runs(line, allow_adjacent_kanji=True),
        known=_split_known))
    _psplit_seen = set()
    # **行全体で立つ かな連続の①**（項目48-SC・2026-09-06）。窓だけを
    # 見ると説明が付いて見える形（`もみと`＝もみ＋と）でも、行の連続
    # まるごと（`もみとにもどります`）には印が立つ。48-LU に「この窓は
    # 異様と確かめてある」を渡すのに使う（判定は 48-KS の1本）
    _line_odd_kana = []
    if dict_index is not None and os.environ.get('CN_POS_ODD') != '0':
        try:
            import pos_grammar as _pg_lo
            _line_odd_kana = list(_pg_lo.odd_kana_spans(line, dict_index,
                                                        store))
        except Exception:
            _line_odd_kana = []

    def _lu_scope(a0, b0, text0):
        """
        **48-LU に渡す範囲**（項目48-SC・2026-09-06）。窓 [a0,b0) を
        覆う「行全体の①（48-KS）」の範囲が在り、そこに別の直しが
        掛かっていなければ、**その範囲まるごと**を渡す（窓が
        `たぶいご`＝既知語＋短い残り に切られていても、連続 `たぶいごうして`
        で組める）。戻り値: (始まり, 終わり, ①が立っているか, 行頭か, 文字列)
        """
        for _sa, _sb in _line_odd_kana:
            if _sa <= a0 and b0 <= _sb:
                if any(not (_sb <= r0[0] or _sa >= r0[1])
                       for r0 in replacements):
                    break
                return (_sa, _sb, True,
                        not line[:_sa].strip(' \t\u3000'), line[_sa:_sb])
        return (a0, b0, False, not line[:a0].strip(' \t\u3000'), text0)

    def _psplit_retry(run, run_start, run_end, pending_ff, uns_mark):
        """
        48-PI の呼び口——**この連続で何も直らなかったとき**だけ、
        助詞のトークンで区切って左の切れ端を worklist に戻す。

        呼ばれるのは「直せないので色だけ付ける」に落ちた所（窓は
        連続まるごとのことも、その一部のこともある——
        `かいすせきにいく` の窓は `かいす` だった・実測）。

        断る形は3つ:
          ・**この連続に既に直しが付いている**（★ 区切りは最後の手）
          ・`pending_ff`（48-IT の控え）が在る——48-IT がこのあと
            直すので、これも「まるごとで直る」側
          ・同じ連続を2度は切らない（`_psplit_seen`）

        通ったら、**この連続で付けた紫を取り消して**（`uns_mark` まで
        戻す）左の切れ端を worklist の先頭に置く。紫は、切れ端を
        通し直した結果（直り or 紫）が代わりになる。
        """
        if (run_start, run_end) in _psplit_seen or pending_ff:
            return False
        if any(not (run_end <= _r[0] or run_start >= _r[1])
               for _r in replacements):
            return False            # この連続には既に直しが付いている
        _k = _psplit_cut(run, tokenize_fn, store, dict_index,
                         after_kanji=(run_start > 0
                                      and is_kanji(line[run_start - 1])))
        if _k is None:
            return False
        # **切れ端が、連続としてそのまま入口で弾かれる形なら区切らない。**
        # まるごとの紫を取り消したのに切れ端も弾かれると、
        # **その連続の紫が丸ごと消える**（★★「紫は判定そのもの」）。
        # 判定は入口と同じ関数を呼ぶ（新しく書かない・48-GN）。
        _lend = run_start + _k
        if (_is_before_honorific(line, _lend)
                or _is_expressive_kana_run(run[:_k])
                or (_k <= 5 and _followed_by_shout_mark(line, _lend))):
            return False
        _psplit_seen.add((run_start, run_end))
        # **左のぶんの紫だけ取り消す。** 右は通し直さないので、
        # 右にだけ付いた印は残す（★★「紫は判定そのもの」）。
        _cut_abs = run_start + _k
        unsure_spans[uns_mark:] = [_sp for _sp in unsure_spans[uns_mark:]
                                   if _sp[0] >= _cut_abs]
        _trace('かな連続', f'{run!r} → {run[_k]!r}（助詞のトークン・右 '
                           f'{run[_k + 1:]!r} は文法で完結・まるごとでは'
                           f'直らない）で区切る（項目48-PI）')
        # **左だけを戻す。** 右は「完結している」と判定した側なので
        # 補正の道に流さない（★★④「できあがっている塊には走らせない」。
        # 試作 v1 は右を流して `ほせいがきかない → ほせいがかない` を
        # 作った——右の `きかない` が単独の連続として走り、48-IT が
        # `き` を落とした）。
        _psplit_work.insert(0, (run_start, run_start + _k, run[:_k]))
        return True

    while _psplit_work:
        run_start, run_end, run = _psplit_work.pop(0)
        # **数字の直後の助数詞（かな）は連続の頭に入れない**（項目48-TG・
        # 2026-09-06。`5つ中5つちょっと` の `つちょっと` を 48-IT が
        # 「機能語の並びとして異様」と見て `つ` を落とした。数字＋助数詞は
        # 数え方で、その先が連続の頭）
        if (run_start > 0 and line[run_start - 1] in '0123456789０１２３４５６７８９'):
            for _cnt in _KANA_COUNTERS:
                if run.startswith(_cnt) and len(run) > len(_cnt):
                    run_start += len(_cnt)
                    run = run[len(_cnt):]
                    break
            if not run:
                continue
        if any(not (run_end <= s0 or run_start >= e0)
               for s0, e0 in taken_all):
            continue
        if _is_before_honorific(line, run_end):
            continue
        # 伸ばし言葉・擬音の形は話し言葉なので触らない（2026-08-08）。
        # **①（48-KS）が連続まるごとに立っているなら通す**（項目48-SC・
        # `すくろーるごのみえた`——ー を含むだけで擬音扱いになり、外来語の
        # 頭が組み直しに届かなかった。擬音・叫び声は 48-KS が説明の付く
        # 形として除いているので、①が立つものは擬音ではない）
        if _is_expressive_kana_run(run):
            # **①（48-KS）が連続まるごとに立っているなら、語の列として
            # 組む道（48-LU）だけを通す**（項目48-SI・2026-09-06）。48-SC で
            # 「①が立つなら通す」と窓の輪まで開けたら、ローマ字の `かーそね` の
            # 窓 `かーそ` に従来の探索が `かーど` を当てて、外来語の道
            # （カーソル）を横取りした（実機メモ3行・実測）。伸ばしを含む
            # 連続は外来語の持ち場なので、窓の輪は今までどおり通さない
            _cov = [(_sa, _sb) for _sa, _sb in _line_odd_kana
                    if _sa <= run_start and run_end <= _sb]
            # **伸ばし（ー）を含まない形**（小書きの母音だけ——ふぁしりてぃ・
            # いんたちちぇんじ）で①が立つなら、**窓の輪を今までどおり通す**
            # （項目48-SI'。外来語の道が先に当たる。48-LU は輪の中で最後に
            # 当たる。7巡目の readcheck の外来語の直り 60〜70 はここから）。
            # 横取りが起きたのは ー を含む `かーそね` だけ
            if _cov and 'ー' not in run:
                _cov = []
                _lu_pass = True
            else:
                _lu_pass = False
            _lu_x = None
            if _cov and not (run_start > 0 and (
                    line[run_start - 1].isdigit()
                    or line[run_start - 1] in '０１２３４５６７８９')) \
                            and not any(not (_cov[0][1] <= r0[0]
                                     or _cov[0][0] >= r0[1])
                                for r0 in replacements):
                try:
                    _lu_x = _lu_compose_odd_run(
                        line[_cov[0][0]:_cov[0][1]], store,
                        input_method=input_method, tokenize_fn=tokenize_fn,
                        context_vec=context_vec, dict_index=dict_index,
                        odd_known=True,
                        bare_head=not line[:_cov[0][0]].strip(' \t\u3000'))
                except Exception:
                    _lu_x = None
            # ★★ **語の途中から始まる窓は、見本なしでは組み直さない**
            # （項目48-UN・**3本すべてに掛ける**・学び22。検品で指摘）
            if _lu_x and _cov and _starts_inside_word(tokens, _cov[0][0]):
                _trace('窓', f'{line[_cov[0][0]:_cov[0][1]]!r} → 語の途中から'
                             f'始まる窓なので、見本なしでは組み直さない'
                             f'（項目48-UN）')
                _lu_x = None
            if _lu_x and not (decisions and decisions.blocks(
                    line[_cov[0][0]:_cov[0][1]], _lu_x)):
                _trace('窓', f'{line[_cov[0][0]:_cov[0][1]]!r} → {_lu_x!r}'
                             f'（伸ばしを含む連続に①。語の列として組み直し・'
                             f'項目48-SI）')
                replacements.append((_cov[0][0], _cov[0][1], _lu_x,
                                     'かな入力'))
                lu_taken.append((_cov[0][0], _cov[0][1]))
                taken_all.append((_cov[0][0], _cov[0][1]))
                continue
            if not _lu_pass:
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
            _c22 = _fold_repeat_to_word(run, store, tokenize_fn)
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
                    run, store, tokenize_fn=tokenize_fn,
                    starts_inside_word=_starts_inside_word(tokens, run_start),
                    after_kanji=(run_start > 0
                                 and is_kanji(line[run_start - 1])),
                    keep_tail=run_tail_particle(line, run_start, run_end))
            if _c23 is not None:
                _swp, _body = _c23
                _trace('かな連続', f'{run!r} → {_swp!r} に戻す'
                                 f'（入れ替え・戻すと {_body!r} が在る語・'
                                 f'項目48-HJ）')
                replacements.append((run_start, run_end, _swp,
                                     'かな入力'))
                taken_all.append((run_start, run_end))
                continue
            # **2文字2回（ABAB）の型**（2026-08-28・CN_ABAB=1・
            # もう一方の道と同じ順で掛ける・学び22。入口は 48-KI。
            # 直前が漢字・カタカナなら掛けない——もう一方の道と同じ門）。
            _prev_c = line[run_start - 1] if run_start > 0 else ''
            # ★★ **1つの語の中の断片には掛けない**（項目48-UZ・
            # 2026-09-07・学び22）。この道の門は「**直前**が漢字・
            # カタカナなら掛けない」だけで、**うしろが漢字**の形が
            # 抜けていた:
            #
            #     どんでん返し  解析は 0〜6 で1語（表にも在る）
            #     かな連続は `どんでん`（0〜4）＝ **語の中の断片**
            #     → **どんどん返し** に直していた（ど と で は隣のキー）
            #
            # 判定は 48-UL と同じ `_span_inside_one_token`（新しく
            # 書かない・48-GN）。
            _c24 = (None if (_chunk_is_intact(run, tokenize_fn)
                             or is_kanji(_prev_c)
                             or ('ァ' <= _prev_c <= 'ヶ') or _prev_c == 'ー'
                             or _span_inside_one_token(tokens, run_start,
                                                       run_end))
                    else _abab_repair(run, store))
            if _c24 is not None:
                replacements.append((run_start, run_end, _c24[0],
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
        # **機能語の並びの異様**（項目48-IT）の直しは、窓ごとに控えて
        # おき、**語としての直しが付かなかった窓だけ**に使う（下の
        # 後始末）。先に当てると `まいす`（マイナスの脱字）が `ます` に
        # なり、従来なら直っていた語を取り上げてしまう（初期状態の
        # readcheck で実測・マイナス 3件）。
        # **語の表を使わず、機能語・活用・名前＋敬称だけで説明が付く連続は
        # 触らない**（項目48-SQ・2026-09-06）。**48-TH（同日）: 用言の活用も**
        # ——`やめたら`（やめる＋たら）・`ひどくて`（ひどい＋くて）は芯が
        # 「読めない」として `やたら`・`ひとくち` にした。表の語を名詞の
        # 部品には使わず、動詞・形容詞の活用の根拠にだけ使う読み
        # （`stems_only`）。名詞を敷き詰める読みは readcheck の直りを失う
        # （48-SQ の実測）ので使わない。`処分のしやすさ` は し＋やす＋さ、
        # `たかちゃん` は 名前＋敬称——内容語が1つも無いので、語彙で直すものが
        # 無い。古い分解（explain_cores）が `しやす` を窓に切って芯が `いやす`
        # に直し、芯が `たかちゃん` を `あかちゃん` にしていた。
        # **最初は「①（48-KS）が立たない連続」を全部止めた**が、①は語の表で
        # 短い読みを敷き詰めて説明するので、readcheck の直りを 初期 −77・
        # 育ち −183 失った（`きゅうずいを`＝きゅう＋ずい＋を）。**語を使わない
        # 読み**（`no_words=True`）に狭めた。語彙の語で切れた窓
        # （token_windows）は今までどおり
        # **機能語だけの並び**（`いいですよわね`・`ににして`）は 48-IT
        # （機能語の並びの異様は要素で直す）の持ち場なので、ここでは
        # 見ない——`_is_all_functional` が True の連続は通す
        _sq_readable = False
        if (source != 'token_windows' and len(run) >= 3
                and not _is_all_functional(run)):
            try:
                import pos_grammar as _pg_sq
                _sq_kw = dict(after_kanji=run_after_kanji,
                              before_kanji=(run_end < len(line)
                                            and is_kanji(line[run_end])))
                _sq_pure = _pg_sq.explain_kana_run(run, no_words=True,
                                                   **_sq_kw)
                _sq_stems = (not _sq_pure) and _pg_sq.explain_kana_run(
                    run, stems_only=True, **_sq_kw)
            except Exception:
                _sq_pure = _sq_stems = False
            if _sq_pure:
                _trace('かな連続', f'{run!r} → 機能語・活用・名前＋敬称だけで'
                                 f'説明が付く（内容語が無い）ので触らない'
                                 f'（項目48-SQ）')
                continue
            if _sq_stems:
                # **用言の活用で説明が付く連続は「読める」**（項目48-TH）。
                # 触らないのではなく、芯を「明らかに自然になる直しだけ」の
                # 側に置く——`やめたら`・`ひどくて` は残り、`すねると → すると`
                # （うにさんの的。拗ねる＋と でも文にならない）は通る
                _sq_readable = True
                _trace('かな連続', f'{run!r} → 用言の活用と機能語で説明が'
                                 f'付く。芯は明らかに自然になる直しだけ'
                                 f'（項目48-TH）')
        pending_ff = []
        # 48-PI: この連続で付けた紫の始まり（区切るときに取り消す）
        _psplit_uns_mark = len(unsure_spans)
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
            # ★★ **1つの既知語の中に収まっている窓は触らない**
            # （項目48-UL'・2026-09-07）。
            #
            # 文全体の解析が「ここからここまでで1語」と言っていて、窓が
            # その**内側**なら、窓は**語の一部でしかない**。書き換えれば
            # **その語が壊れる**。
            #
            #     ひっくり返す  解析は 0〜6 で1語（動詞:自立）
            #     かな連続 `ひっくり` は 0〜4 ＝ 語の中の断片
            #     → 芯の再構築が **`びっくり返す`** にしていた
            #       （`ひっくり返す` はごく普通の語。本人の語彙にも在る）
            #
            # ★ 窓の切り出しは `token_windows`（解析の分割）が第一候補で、
            #   それが何も出さないときだけ語彙ベースの `explain_cores` を
            #   使う——**解析が「1語」と言っている所を、語彙の側が切って
            #   いた**。この門は、その順番の建前をそのまま守るもの。
            # ★ 窓が語ちょうどのときは掛からない（`_span_inside_one_token`
            #   は**語より短い**ときだけ True）。
            # ★★ **48-IT の控えを積む前に置くこと**——控えは
            # 「ほかの直しが無ければ最後に当てる」ので、ここで
            # `continue` しても**積んだ分は残って当たってしまう**
            # （検品で指摘・2026-09-07）。断片を書き換えれば、それを
            # 含む語が壊れる。
            if _span_inside_one_token(tokens, a, b):
                _trace('窓', f'{window!r} → 1つの語の中の断片なので触らない'
                             f'（項目48-UL）')
                continue
            # ★★ **項目48-UX は測って外した**（2026-09-07）。
            #
            # 「**語の途中から始まる窓**も、芯の再構築に渡さない」を
            # 試した（48-UN を窓の輪にも広げる形）。狙いは
            # `説明のわざわざについて → 説明のざわざわについて` を
            # 止めること——解析は `わざわざ` を1語と言うのに、窓は
            # `ざわざについて`＝**3文字目から**始まっていた。
            #
            # **2段階で外した**:
            #   1. 全部の語に掛けたら、`かな打ちでのほらい` の**紫まで
            #      消えた**（漢字＋送り仮名の語では**かな連続は送り仮名
            #      から始まるのが普通**なので、門が全部を飲む）。
            #      見張り（`tests_mock_ui` の「ほらい は色が付く」）が捕まえた
            #   2. **かなだけの語**に絞っても、初期で
            #      **`ねるっさんす → ルネッサンス` を失った**（−1）。
            #      得たのは育ちの化け −1 だけ。
            #
            # ★ そもそも実文では `わざわざ来てくれました` のように
            #   使われ、`_is_expressive_kana_run`（伸ばし・擬音の形）が
            #   守っている。**枠の中でしか起きない形**だった。
            #   `_starts_inside_word` は 48-UN（見本なしの組み直し3本）
            #   でだけ使う。
            # **機能語の並びの異様**（項目48-IT）。門の外に出す前に、
            # 要素の形で見て直せるなら直す（ににして→にして・
            # すねると→すると・いいですよわね→いいですよね）。
            _ff = _fix_functional_run(
                window, after_kanji=(a > 0 and is_kanji(line[a - 1])),
                store=store, tokenize_fn=tokenize_fn)
            if _ff:
                _trace('窓', f'{window!r} → 機能語の並びとして異様。'
                             f'語の直しが無ければ {_ff!r} に直す（項目48-IT）')
                pending_ff.append((a, b, _ff))
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
            # ★ 48-UL の「断片には 48-IS を当てない」は**ここには要らない**
            # （検品で指摘・2026-09-07）。上の 48-UL' が同じ判定で
            # **先に `continue`** しているので、ここへ来る窓は断片ではない。
            # 同じ判定を2度書かない（48-GN）。
            if window_readable and not _kana_run_explained(
                    window,
                    before_kanji=(b < len(line) and is_kanji(line[b]))):
                _trace('窓', f'{window!r} → 解析は読めると言うが、かなの語と'
                             f'機能語では説明できない（項目48-IS）。読めない扱い')
                window_readable = False
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
            if _looks_like_valid_japanese(window, tokenize_fn) \
                    and _kana_run_explained(
                        window, before_kanji=(b < len(line)
                                              and is_kanji(line[b]))):
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
                readable_hint=(window_readable or _sq_readable),
                before_kanji=(max(b, run_end) < len(line)
                              and is_kanji(line[max(b, run_end)])),
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
                # **かぎ括弧の門は、ここには掛けられない**（項目48-OQ(f)・
                # 2026-09-03。**測って外した**）。48-MI の
                # `_is_quoted_whole`（言及している語は変換しない）を
                # 芯の再構築にも掛けたら、**readcheck が 直り −9**——
                # 標本の型の1つが `「{w}」と書きました。` で、
                # **かぎ括弧の中の打ち間違いは、ふつうに直す**もの
                # だった（`「ひどりぐらし」` → ひとりぐらし）。
                # 48-MI の門は**変換（かな→漢字）**を止めるためのもので、
                # **直し（打ち間違いを戻す）**を止める理由にはならない。
                # 残った `つまらない ➔ 「つまらん」 → 「さんらん」` は
                # **別の根**——`つまらん`（未然形＋打消の ん）を
                # 48-IS が「かなの語と機能語で説明できない」と見る。
                # 直すなら `_kana_run_explained` の文法側（引き継ぎ N12）
                # **直した読みを、そのまま漢字へ**（項目48-NF・
                # 2026-09-01）。うにさんの一覧 `がいしょつする ⇒
                # 外出する`・`すきにん ⇒ 確認`・`ひらんがな ⇒ 平仮名`
                # ——読みは芯の再構築で直るのに、**かなのまま止まって**
                # いた。
                #
                # 変換の道（48-MI `_kango_kana_fixes`）は**元の行**の
                # かな連続を見るので、`がいしょつ`（語ではない）しか
                # 見ていない。**直したあとの `がいしゅつ` は誰も見ない。**
                #
                # ここは**異様だと判定して芯を建て直した場所**なので、
                # 48-MI が使う「いちばん厳しい錨」ではなく**ふつうの錨**
                # （48-MK・実績2以上または2字の漢語）でよい——48-MI が
                # 厳しいのは「異様と判定していない連続」を触るからで、
                # ここはその逆。うにさんの指定（48-KV ⑤）
                # 「**かなのまま打ちたいことの確信がなければ漢字変換
                # する**」。
                #
                # **変換するのは芯だけ**（窓ごとは触らない）。窓ごと
                # 差し替える形も測ったが、**芯が伸びる直し**（びじす →
                # びじねす）で窓を組み直すと、下の守り（長さ・同じ字の
                # 連続）を**迂回**して `びじすねがありました →
                # ビジネスネガありました` を作った（育ちで実測。ほかに
                # `もおしろう → も面白う`・`のりえこる → 乗り越えコル`）。
                # 芯だけなら、範囲も守りも今までどおり。
                # 変換に掛けるのは**建て直した窓**（芯だけを見ると
                # 尻尾の機能語が見えない）。ただし**採るのは芯の範囲
                # だけ**で、尻尾は元のまま残す。門は3つ:
                #   ・芯が窓の頭から始まること（`c_s == 0`）
                #   ・**変換の頭が、芯とぴたり同じ長さ**であること
                #     （芯を丸ごと1語にできたときだけ。頭だけ漢字に
                #       なって かなの尻尾が芯の中に残る形は採らない）
                #   ・**尻尾が元のまま**であること＝48-KV ⑤ の (あ) の枝
                #     （残りが機能語だけ）。(い) の枝〔2つ目の区切りも
                #     語で埋める〕は尻尾を書き換えるので、ここで落ちる
                #     ——`のりこえ|こるがありました → 乗り越え**コル**が…`・
                #     `びじねす|ねがありました → ビジネス**ネガ**…`
                #     （どちらも育ちで実測）
                # **直前に、ひとりぼっちのひらがなが1字だけ立って
                # いるなら、変換まではしない**（項目48-NF の門4）。
                # その1字は**この語の一部かもしれない**——切り出しが
                # ずれたまま漢字に固めると、もっと良い直しを閉め出す:
                #
                #     昨日**も**おしろうを見ました   ← 窓は `おしろう`
                #       芯 `おもしろう` → 変換 `面白う` → **も面白う**
                #       （窓の外の道は `もおしろう → おもしろう` と
                #         丸ごと直せていた・育ちで実測）
                #
                # **2字以上のかなが続いているなら通す**——そちらは
                # 前の語がふつうに終わっている形（`これからながく|
                # がいしょつする → これからながく**外出する**`）。
                # 48-KX の「頭の1字ひらがな」と同じ見立て。
                # **かなのままなら今までどおり直す**——固めないので、
                # あとの道がやり直せる。
                _core_conv = None
                _rest = window_ext[c_e:]
                _bk = a
                while _bk > 0 and is_hiragana(line[_bk - 1]):
                    _bk -= 1
                _head_free = (a - _bk) != 1
                if (dict_index is not None and c_s == 0 and core_fix
                        and _head_free
                        and not any(is_kanji(_c) or is_katakana(_c)
                                    for _c in core_fix)):
                    _win_fix = core_fix + _rest
                    try:
                        _cc = _convert_odd_kana_run(_win_fix, store,
                                                    dict_index)
                    except Exception:
                        _cc = None
                    if (_cc and _cc[1] == len(core_fix)
                            and _cc[0] != _win_fix
                            and (not _rest or _cc[0].endswith(_rest))):
                        _hs = _cc[0][:len(_cc[0]) - len(_rest)]
                        import oddness as _odd_nf
                        if (_hs and _hs != core_fix
                                and any(is_kanji(_c) or is_katakana(_c)
                                        for _c in _hs)
                                and not _odd_nf.is_odd_run(
                                    _cc[0], tokenize_fn,
                                    store=store, dict_index=dict_index)):
                            _core_conv = _hs
                if _core_conv:
                    _trace('窓', f'{window_ext!r} → 芯の再構築で '
                                 f'{core_fix!r}、さらに変換して '
                                 f'{_core_conv!r}（項目48-NF）')
                    replacements.append((a + c_s, a + c_e, _core_conv,
                                         'かな入力'))
                    conv_taken.append((a + c_s, a + c_e))
                else:
                    _trace('窓', f'{window_ext!r} → 芯の再構築で '
                                 f'{window_ext[c_s:c_e]!r} を '
                                 f'{core_fix!r} に直す')
                    replacements.append((a + c_s, a + c_e, core_fix,
                                         'かな入力'))
            elif not edge_word:
                # **同じ行の並記からの脱字の訂正**（項目48-LQ・
                # 2026-08-30）。⇒で正解を並べたメモ・同じ語を
                # 書き直した行では、**本来の入力が同じ行に文字どおり
                # 書かれている**。どの探索でも直せなかった窓に、
                # 「内側の1字を足すと、行の別の場所の並びに一致する」
                # ものが**ただ1つ**あれば、それが本来の入力
                # （かなちでのほせい → かなうちでのほせい。回9の
                # うにさんの指摘「開いた平仮名が補正できていません。
                # より簡単なはずですが」への答え）。
                # **端の1字の挿入は採らない**——窓の切り出しが助詞を
                # 落としただけの並び（ほせい に対する のほせい）と
                # 区別が付かないため。
                # **見本なしの組み直しを先に試す**（項目48-LU・
                # 2026-08-30 19回目。うにさんの指定「正しい文の見本が
                # なくても異様な文字列を正しく漢字に補正する必要が
                # あります」——判断が先、行内の証拠（48-LQ）は控え）。
                _lqw = window_ext
                # 異様かどうかの判定は _lu_compose_odd_run の頭の
                # pos_grammar（48-KS）が一手に持つ（窓の readable は
                # 「辞書で読めるか」で、さつんこうになる＝札+ん+港 の
                # ような**読めるが異様**を塞いでしまう・実測。
                # 判定は1つにする——48-GN）。
                # **数字の直後の連なりには掛けない**——頭の つ・こ は
                # 助数詞（1つだけ → 1続け を3行で作った・全行検品）。
                _lu_ok = not (a > 0 and (line[a - 1].isdigit()
                                         or line[a - 1] in '０１２３４５６７８９'))
                _lu = None
                _lu_a, _lu_b, _lu_odd, _lu_head, _lqw = _lu_scope(
                    a, max(b, run_end), window_ext)
                if _lu_ok:
                    _lu = _lu_compose_odd_run(_lqw, store,
                                              input_method=input_method,
                                              tokenize_fn=tokenize_fn,
                                              context_vec=context_vec,
                                              dict_index=dict_index,
                                              odd_known=_lu_odd,
                                              bare_head=_lu_head)
                # ★★ **語の途中から始まる窓は、見本なしでは組み直さない**
                # （項目48-UN・2026-09-07）。窓の頭が**前の漢字の送り仮名**
                # なら、書き換えれば**前に在る漢字ごと語が壊れる**:
                #
                #     思いやり  解析は 0〜4 で1語。かな連続は 1 から始まる
                #     → `いやり` を `いなり` と読んで **`思稲荷`**
                #     （芯の再構築は「拮抗の決め手が無い」と**断れていた**のに、
                #       こちらが走った——48-QX と同じ形）
                #
                # ★ 見本（同じ行の並記）が在る道（`_lq`）には掛けない——
                #   あちらは**本人が正しい形を同じ行に書いている**という
                #   強い証拠を持っている。
                if _lu and _starts_inside_word(tokens, _lu_a):
                    _trace('窓', f'{_lqw!r} → 語の途中から始まる窓なので、'
                                 f'見本なしでは組み直さない（項目48-UN）')
                    _lu = None
                if _lu:
                    _trace('窓', f'{_lqw!r} → {_lu!r}（語の列として'
                                 f'組み直し・見本なし・項目48-LU）')
                    replacements.append((_lu_a, _lu_b, _lu, 'かな入力'))
                    lu_taken.append((_lu_a, _lu_b))
                    continue
                _lq = _lq_attested_insertion(line, a, max(b, run_end),
                                             window_ext,
                                             dict_index=dict_index)
                if _lq is not None:
                    # 直した読みが**語の列として組み上がる**なら、
                    # 漢字まで進める（かなちでのほせい →〔脱字〕
                    # かなうちでのほせい →〔組み直し〕かな打ちでの補正。
                    # 項目48-LU。数字の直後は同じ門で見送る）
                    _lq2 = None
                    if _lu_ok:
                        _lq2 = _lu_compose_odd_run(
                            _lq, store, input_method=input_method,
                            tokenize_fn=tokenize_fn,
                            context_vec=context_vec, dict_index=dict_index,
                            bare_head=_lu_head)
                    if _lq2:
                        _trace('窓', f'{_lq!r} → {_lq2!r}（直した読みを'
                                     f'語の列として組み直し・項目48-LU）')
                        replacements.append((a, max(b, run_end), _lq2,
                                             'かな入力'))
                        lu_taken.append((a, max(b, run_end)))
                        continue
                if _lq is not None:
                    _trace('窓', f'{_lqw!r} → {_lq!r}'
                                 f'（同じ行の並記・内側の1字の脱字）')
                    replacements.append((a, max(b, run_end), _lq,
                                         'かな入力'))
                    continue
                # **48-PI**（2026-09-03）: ここまでで何も直らなかった。
                # 助詞のトークンで区切れるなら、**左の切れ端をもう一度**
                # （まるごとの紫は付けない——左の結果が代わりになる）。
                if _psplit_retry(run, run_start, run_end, pending_ff,
                                 _psplit_uns_mark):
                    break
                # **48-RQ**（2026-09-05）: ここまでで何も直らなかった。
                # **印のキーの隣（せ＝゛ の隣・同じ誤りの繰り返しも）を
                # 巻き戻し、語＋手が生んだ1字格助詞＋語 に組めるなら採る**
                # （`かいせきかせなかせく → 解析が長く`）。48-PI・48-RK と
                # 同じ構え——この連続で何も直らなかったときだけの最後の手。
                # 48-RK より先に置く（うにさんの指定「先に疑う」。仮説が
                # 作れない連続では何もしないので、48-RK の的は横取りしない）
                _wbp = _word_born_particle_fix(run, store, dict_index,
                                               tokenize_fn)
                if _wbp is not None and not (
                        decisions and decisions.blocks(run, _wbp)):
                    replacements.append((run_start, run_end, _wbp,
                                         'かな入力'))
                    hiragana_taken.append((run_start, run_end))
                    conv_taken.append((run_start, run_end))
                    del unsure_spans[_psplit_uns_mark:]
                    break
                # **48-RK**（2026-09-05）: ここまでで何も直らなかった。
                # **既知の頭で割って、残りを直して熟語＋熟語に決める**
                # （`かんいりゅうりょく → 簡易入力`）。48-PI と同じ構え
                # ——**この連続で何も直らなかったときだけ**の最後の手。
                _khc = _fix_known_head_compound(
                    run, store, tokenize_fn, dict_index, find_readings,
                    max_dist,
                    before=(line[run_start - 1] if run_start > 0 else ''),
                    after=(line[run_end] if run_end < len(line) else ''))
                # ★★ **末尾の助詞は、この道でも動かさない**
                # （項目48-UU・2026-09-07・**学び22**）。
                # `run_keep_tail`（48-DJ）は「従来の探索」と「芯の再構築」の
                # **2本に渡してある**と書いてあるのに、**この3本目**には
                # 渡っていなかった。実測:
                #
                #     こんばんはという言葉を使います。
                #       → **今晩配当言葉を使います。**
                #       （頭 `こんばん`＝今晩 で割り、残り `はという` を
                #        `配当`〔はいとう〕に直して、**`という` を食った**）
                #     たいまつという言葉 → **大麻追悼言葉**
                #
                # trace には**すぐ上の行に**「末尾の 'という' は助詞なので
                # 動かさない」と出ている——**印は立っていたのに、この道が
                # 見ていなかった**（48-QX と同じ形）。
                if (_khc is not None and run_keep_tail
                        and not _khc.endswith(run_keep_tail)):
                    _trace('かな連続', f'{run!r} → 既知の頭で割った '
                                     f'{_khc!r} は末尾の {run_keep_tail!r} を'
                                     f'食うので採らない（項目48-UU）')
                    _khc = None
                if _khc is not None and not (
                        decisions and decisions.blocks(run, _khc)):
                    replacements.append((run_start, run_end, _khc,
                                         'かな入力'))
                    hiragana_taken.append((run_start, run_end))
                    # **長さの検査から外す**（`conv_taken`）。かなを
                    # 漢字の熟語に組むと必ず縮む（9字 → 4字）ので、
                    # 「差は2字まで」の検査に落ちる。48-LU の組み直しと
                    # 同じ扱い——**長さの代わりの砦は、両方が段2以下の
                    # 2字漢語で、できた形が異様でないこと**（あちらは
                    # 「読みの列の完全な組み上がり」）
                    conv_taken.append((run_start, run_end))
                    del unsure_spans[_psplit_uns_mark:]
                    break
                # **48-RW（測って外した・2026-09-05）**: ①が立っている
                # かな連続を、異様の塊と同じ受け皿（`_reopen_odd_chunk(
                # as_kana_run を立てて）`）に通してみた。漢字欄 `田部井号して →
                # タブ移動して`・`札ん港になる → 参考になる` が直るのに
                # かな欄 `たぶいごうして`・`さつんこうになる` が紫のままなのは
                # 受け皿が無いからで、通せば届くはず——**通したら壊れた**:
                #     たぶいごうして   → **タブ以後かして**（う→か・1.0）
                #     さつんこうになる → **チサ積んこうになる**（頭に ち を足す脱字）
                # 受け皿は**費用順で最初に組めた変種**を採る。漢字欄では
                # 「書かれ方」の門 (b)(c)（漢字を減らさない・漢字だけの塊は
                # 長くならない）が悪い変種を落としていたが、かなだけの塊には
                # その門が**何も言わない**。足りないのは**④の選び方**——
                # 組めた変種を全部集め、部品の品詞（名詞だけ）・尾の形
                # （サ変＋して／助詞＋用言）・手の種類（打った字を読み替える
                # 手を、字を足す手より上）で選び、上位2つが拮抗なら紫のまま。
                # `as_kana_run` の口は残してある（呼び手はまだ無い）
                _trace('窓', f'{window!r} → 直せないので色だけ付ける')
                # edge_word（既知語＋短い残り）の窓は、直せなかった
                # ときに色も付けない。「よろしくお（ねがいします）」の
                # ように、残りが次の語の頭であるだけで壊れていない
                # 可能性が高いため（実機からの指定）。
                unsure_spans.append((a, b))
            else:
                # **①が連続まるごとに立っているなら、その範囲で組み直す**
                # （項目48-SC。初期状態の `たぶいごうして` は窓が `たぶいご`
                # ＝既知語（タブ）＋短い残り に切られ、ここで見送られていた）
                _lu_a, _lu_b, _lu_odd, _lu_head, _lqw = _lu_scope(
                    a, max(b, run_end), window_ext)
                _lu = None
                if _lu_odd and not (a > 0 and (
                        line[a - 1].isdigit()
                        or line[a - 1] in '０１２３４５６７８９')):
                    _lu = _lu_compose_odd_run(_lqw, store,
                                              input_method=input_method,
                                              tokenize_fn=tokenize_fn,
                                              context_vec=context_vec,
                                              dict_index=dict_index,
                                              odd_known=True,
                                              bare_head=_lu_head)
                # ★★ 同じ門（項目48-UN・3本目）
                if _lu and _starts_inside_word(tokens, _lu_a):
                    _trace('窓', f'{_lqw!r} → 語の途中から始まる窓なので、'
                                 f'見本なしでは組み直さない（項目48-UN）')
                    _lu = None
                if _lu:
                    _trace('窓', f'{_lqw!r} → {_lu!r}（語の列として'
                                 f'組み直し・①の範囲・項目48-LU/48-SC）')
                    replacements.append((_lu_a, _lu_b, _lu, 'かな入力'))
                    lu_taken.append((_lu_a, _lu_b))
                    continue
                _trace('窓', f'{window!r} → 直せず、既知語＋短い残りの形'
                             f'なので色も付けない')
        # 後始末: 機能語の並びの異様（項目48-IT）。語の直しが重なって
        # いない窓だけ直す。色だけ付けていた印は外す。
        for _pa, _pb, _pf in pending_ff:
            if any(not (_pb <= r[0] or _pa >= r[1]) for r in replacements):
                _trace('窓', f'{line[_pa:_pb]!r} → 語の直しがあるので'
                             f'機能語の並びとしては直さない（項目48-IT）')
                continue
            _trace('窓', f'{line[_pa:_pb]!r} → 機能語の並びとして異様。'
                         f'{_pf!r} に直す（項目48-IT）')
            replacements.append((_pa, _pb, _pf, 'かな入力'))
            unsure_spans[:] = [(s_, e_) for s_, e_ in unsure_spans
                               if e_ <= _pa or s_ >= _pb]

    # **48-RW'**（2026-09-05）: A の道で直した読み（かな→かな）を、正しく
    # 打ったかなと同じ変換の道（48-LD・48-MI）に通す。`おくゆくこてい →
    # おくゆきこてい` で止まっていたものが `奥行固定` に、`かすくにん →
    # かくにん` が `確認` に——正しく打てば漢字になるのに、直されると
    # 読みのままだった食い違いを無くす
    for _ri in range(len(replacements)):
        _rr = replacements[_ri]
        if len(_rr) < 4:
            continue
        _rs, _re, _rn, _rc = _rr[0], _rr[1], _rr[2], _rr[3]
        if (_rc != 'かな入力' or not _rn or _rn == line[_rs:_re]
                or not all(is_hiragana(c) or c == 'ー' for c in _rn)):
            continue
        # **窓だけ直したときは、かな連続まるごとで見る**——`おくゆくこてい`
        # は窓 `おくゆく` だけが `おくゆき` に直る。変換の道は `おくゆきこてい`
        # まるごと（語＋語）で組むので、直した窓を含むかな連続全体を作って渡す。
        # 連続の中に別の置き換えが在れば触らない
        _rs2, _re2 = _rs, _re
        while _rs2 > 0 and is_hiragana(line[_rs2 - 1]):
            _rs2 -= 1
        while _re2 < len(line) and is_hiragana(line[_re2]):
            _re2 += 1
        if any(_rj != _ri and len(replacements[_rj]) >= 2
               and not (replacements[_rj][1] <= _rs2
                        or replacements[_rj][0] >= _re2)
               for _rj in range(len(replacements))):
            _rs2, _re2 = _rs, _re
        _whole = line[_rs2:_rs] + _rn + line[_re:_re2]
        _cv = _convert_fixed_kana_run(_whole, store, dict_index)
        if _cv and _cv != _whole and not (decisions
                                          and decisions.blocks(_whole, _cv)):
            _trace('かな連続', f'{_whole!r} → {_cv!r}（直した読みを変換の道に'
                               f'通した・項目48-RW\'）')
            replacements[_ri] = (_rs2, _re2, _cv, _rc) + tuple(_rr[4:])
            conv_taken.append((_rs2, _re2))
            if (_rs2, _re2) not in hiragana_taken:
                hiragana_taken.append((_rs2, _re2))
    spans = find_editable_spans(line, tokens)

    for start, end, surface, reading, is_known_word in spans:
        # 既に補正した範囲（ひらがな連続・半角入力）とは重複させない
        if any(not (end <= s or start >= e)
               for s, e in hiragana_taken + halfwidth_taken + kanji_taken):
            continue
        # 語尾に助動詞・活用語尾が付いている場合は、
        # 語幹だけを判断対象にして語尾はそのまま残す。
        # この語の周りにある内容語（文脈スコアの材料）。
        # 同じ行の前後を最優先し、直前の変換履歴・上下の行と続ける
        # （_surrounding_content_words が並び順で優先度を表す）。
        surrounding = None
        if context_vec is not None:
            surrounding = _surrounding_content_words(
                tokens, start, end,
                nearby_words=nearby_words, recent_words=recent_words)

        stem_surface, tail_surface = split_protected_tail(surface)
        if tail_surface:
            # **語尾を持つ実在語は、同音異義語の道だけ通す**
            # （項目48-IQ・2026-08-22）。`映る` `思い` `映し` は語尾
            # （る・い・し）で切られて、ここで**素通り**していた。
            # 同音の道は送り仮名を揃えて比べる（`_conjugated_alts`）ので
            # 「読みと表記の対応」の問題は起きない。戻り値は
            # 語尾込みの表記（`移る`）なので、そのまま置き換える。
            if is_known_word and context_vec is not None and surrounding:
                _hp = _homophone_by_context(
                    surface, reading, store, context_vec, surrounding,
                    dict_index=dict_index, attest_text=line,
                    after_text=line[end:end + 4],
                    prev_text=line[max(0, start - 1):start])
                if _hp is not None and _hp[0] != surface \
                        and len(_hp[0]) == len(surface):
                    replacements.append((start, end, _hp[0], _hp[1]))
                continue
            # 語尾を切り離した結果、語幹が短すぎるなら触らない。
            # 断片は偶然どれかの語に一致しやすく誤爆の元になる。
            if len(stem_surface) < 2:
                continue
            # 語尾を切り離した場合、読みの側も対応させる必要があるが、
            # 表記と読みの対応を正確に取るのは難しいため、
            # 語尾を持つ語はこのエンジンでは補正対象にしない。
            # （「引き下げました」→「引き下また」のような破壊を防ぐ）
            continue

        result = evaluate_candidate(surface, reading, store, context_vocab,
                                    find_readings, max_dist,
                                    is_known_word=is_known_word,
                                    context_vec=context_vec,
                                    surrounding_words=surrounding,
                                    dict_index=dict_index,
                                    attest_text=line,
                                    after_text=line[end:end + 4],
                                    prev_text=line[max(0, start - 1):start])
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

    # --- 1字の同音異義語（項目48-JK・2026-08-25）----------------------
    # うにさんの問い「**1文字を弾いているのはなぜですか？** 特にそう
    # してほしいといったことはない」への答え: 1字を土俵から外す門
    # （find_editable_spans の len<2）は、**読みの探索では1字の読みが
    # 何にでも一致して誤爆する**という、こちら側の実測から置いた守りで、
    # うにさんの指定ではない。守りの本体は「証拠が1字ぶんしか無いこと」
    # ——設計35（対の表・48-JJ）の証拠は**表と手がかり語**なので、
    # **表に載っている字だけ**土俵に上げる（糸 → 意図）。
    # 通すのは設計35 だけ。読みの探索・他の道には出さない。
    try:
        from homophone_pairs import SINGLE_LEFT as _hp_single
    except Exception:
        _hp_single = ()
    if _hp_single:
        for surface, pos, reading, start, end, has_reading, *_ in tokens:
            if surface not in _hp_single:
                continue
            if any(x in (pos or '') for x in ('助詞', '助動詞', '記号')):
                continue
            if any(not (end <= s or start >= e)
                   for s, e, _n, _c in replacements):
                continue
            if any(not (end <= s or start >= e)
                   for s, e in hiragana_taken + halfwidth_taken
                   + kanji_taken):
                continue
            _sur = _surrounding_content_words(
                tokens, start, end,
                nearby_words=nearby_words, recent_words=recent_words)
            got = _design35_fix(surface, reading, _sur, line,
                                after_text=line[end:end + 4],
                                prev_text=line[max(0, start - 1):start])
            if got and got is not _D35_KEEP:
                replacements.append((start, end, got[0], got[1]))

    # --- 設計36: 1字の漢字を、かなに開いて機能語として成立するなら開く
    # （項目48-JM・2026-08-25）。うにさんの指定:
    # 「**1字でスキップするのは、脱字だけです。**『度のファイルを』これが
    #   異様であることは見て分かります。変換ミスとの候補として、
    #   **無変換の『どの』が自然**であることは分かります」
    # 門は3つ（全部で1つの閉じた形）:
    #   ・1字の漢字で、**前が行頭・助詞・記号**（語に付いていない）
    #   ・トークンの読み（文脈込みで janome が選んだもの）で開くと、
    #     後続のかなと合わせて**1語の連体詞**になる（ど＋の＝どの。
    #     `手の` の ての は 助詞2つで1語にならないので通らない）
    #   ・**その先が名詞**（連体詞は名詞に掛かる。`度の強い眼鏡` の
    #     度=レンズの度数 は次が形容詞なので触らない）
    if tokenize_fn is not None:
        for _i36 in range(len(tokens)):
            _sf, _pos, _rd, _st, _en = tokens[_i36][:5]
            if len(_sf) != 1 or not is_kanji(_sf):
                continue
            if not _rd or not (1 <= len(_rd) <= 2) \
                    or not all(is_hiragana(c) for c in _rd):
                continue
            if _i36 > 0:
                _pp = tokens[_i36 - 1][1] or ''
                if not any(x in _pp for x in ('助詞', '記号')):
                    continue
            if any(not (_en <= s or _st >= e)
                   for s, e, _n, _c in replacements):
                continue
            _j36 = _en
            while _j36 < len(line) and is_hiragana(line[_j36]):
                _j36 += 1
            _tail36 = line[_en:_j36]
            if not _tail36:
                continue
            _nx = next((t for t in tokens if t[3] >= _j36 and t[0]), None)
            if _nx is None or not (_nx[1] or '').startswith('名詞'):
                continue
            _merged = _rd + _tail36
            try:
                _mt = [t for t in tokenize_fn(_merged) if t[0]]
            except Exception:
                continue
            if len(_mt) == 1 and (_mt[0][1] or '').startswith('連体詞'):
                _trace('同音', f'{_sf!r} をかなに開くと {_merged!r}（連体詞）'
                               f'が成立する。無変換が自然（設計36）')
                replacements.append((_st, _en, _rd, 'その他'))

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
        for k_s, k_e, k_run in _LW.find_katakana_runs(line, min_katakana=3):
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
            # **1語で読めるなら本人の語**。2語以上に割れてしか読めない
            # （ディス＋レイ）なら、1手で表の語に届く `ディスプレイ` を採る
            # （項目48-IT。うにさんの指定「ディスレイ・ディスプレ は異様」）。
            # 短い並び（3〜4字）は、漢字・英数字の隣では触らない
            # （`アナマ岩` `ウロウ根` `エアバスＡ３００`・実測）。
            if fixed and (span_e - k_s) <= 4:
                _prev = line[k_s - 1] if k_s > 0 else ''
                _next = line[span_e] if span_e < len(line) else ''
                if (is_kanji(_prev) or is_kanji(_next)
                        or (_next and not (is_hiragana(_next)
                                           or _next in '、。，．！？'))):
                    _trace('外来語', f'{line[k_s:span_e]!r} → 短い並びで'
                                     f'漢字・英数字に接しているので触らない')
                    fixed = None
            if fixed and _LW.dictionary_explains(line[k_s:span_e],
                                                 tokenize_fn) \
                    and (_LW.dictionary_single_word(line[k_s:span_e],
                                                    tokenize_fn)
                         or _in_word_table(line[k_s:span_e])
                         or not _is_dropout_fix(line[k_s:span_e], fixed)):
                _trace('外来語', f'{line[k_s:span_e]!r} → '
                                 f'辞書の1語なので触らない')
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
                # **並記が無くても、打ち間違いの形で説明が付けば直す**
                # （項目48-IT・うにさんの指定「かーそね: 2文字目から
                # 隣接キーを試す。ね→る で カーソル。見つからなければ
                # 脱字も疑う」）。元がかなの語と機能語で説明できる
                # （＝正しい語かもしれない）なら今までどおり並記を待つ。
                if _kata not in (line[:h_s] + line[h_s + _len:]) \
                        and not (_only_particles(h_run[_len:])
                                 and not _is_expressive_strict(h_run[:_len])
                                 and _loan_typo_plausible(_body, _kata)):
                    _trace('外来語', f'{_body!r} → {_kata!r} は同じ行に'
                                     f'書かれていないので触らない')
                    break
                # **切れ目が語の途中でないこと**（項目48-LP・2026-08-30）。
                # 並記があっても、残りが語の途中なら語を真っ二つに
                # する（すくろーる｜ごのみえた——ご は 語/後 の読み）。
                # 16801 の口（48-DL）と同じ物差しを使う（48-GN——
                # 同じ判定を別の言い方で書かない）。
                if h_run[_len:] and not _rest_is_ordinary_japanese(
                        h_run[_len:], tokenize_fn):
                    _trace('外来語', f'{_body!r} → {_kata!r} にしたいが、'
                                     f'残り {h_run[_len:]!r} が'
                                     f'語の途中に見える')
                    continue
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
        # 大文字だけの略語の打ち違い（YRLは → URLは・項目48-LW）
        try:
            for m_s, m_e, m_fix in _LW.find_miskeyed_acronym(line, store):
                if _loan_overlaps(m_s, m_e):
                    continue
                _trace('英語', f'{line[m_s:m_e]!r} → {m_fix!r}'
                               f'（略語の隣のキー・項目48-LW）')
                replacements.append((m_s, m_e, m_fix, '英語'))
                _loan_taken.append((m_s, m_e))
        except Exception:
            pass

        # --- 英単語（Pplanetarium → Planetarium）---
        for e_s, e_e, e_run in _LW.find_english_runs(line):
            if _loan_overlaps(e_s, e_e):
                continue
            fixed = _LW.fix_english_word(e_run, store)
            if fixed:
                _trace('英語', f'{e_run!r} → {fixed!r}')
                replacements.append((e_s, e_e, fixed, '英語'))
                _loan_taken.append((e_s, e_e))

    # --- `誤 ⇒ 正` の並記（設計34・項目48-JI）---
    # うにさんの記法そのものを証拠にする。左右の差分の読みが同じなら、
    # 左を右に合わせる。既に他の道が直した範囲には重ねない。
    if '⇒' in line:
        for _as, _ae, _an, _ac in _arrow_respell(line, tokenize_fn,
                                                 dict_index):
            if any(not (_ae <= s0 or _as >= e0)
                   for s0, e0, _n0, _c0 in replacements):
                continue
            replacements.append((_as, _ae, _an, _ac))

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
        out = dict(empty)
        out['unsure_spans'] = unsure_spans
        _why_out = []
        out['odd_spans'] = _odd_spans_for_line(line, tokenize_fn, (),
                                               store, dict_index,
                                               reasons_out=_why_out)
        out['odd_reasons'] = _why_out
        return out

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
        # **読みの並記は書きたい形**（項目48-LS）。かなの連なりの
        # 直後に括弧でその表記が並ぶ形（しょくじけん（食事券））は、
        # 読みを見せるためにわざとかなで書いたもの。回14の規則の
        # 逆向き。全ての道が通るこの場に置く（学び22）。
        # ★★ **かぎ括弧の門を、ここ（最終検査）に置くのは測って外した**
        # （項目48-RK'・2026-09-05）。「括弧にちょうど囲まれた塊は
        # 引用だから触らない」を全部の道に掛けたところ、**readcheck の
        # 直りが 1,971 → 1,652（−319）**になった——ものさしの材料が
        # **語を括弧で囲んだ形**なので、正しい直しまで丸ごと止まる。
        # 引用の守りは `_fix_known_head_compound` の中（かなの連なりを
        # まるごと漢字に組む手）**だけ**に置いてある。
        if _reading_spelled_in_bracket(line, start, end, tokenize_fn):
            _trace('置換', f'{original!r} → {new_surface!r} は、直後の'
                           f'括弧に表記が並ぶ読みの並記なので触らない')
            continue
        # 半角・ローマ字をかなに直した箇所は、文字数が大きく変わるのが
        # 正常なので長さの検査から外す（mojinyuuryoku → もじにゅうりょく）。
        is_halfwidth = any(not (end <= s or start >= e)
                           for s, e in halfwidth_taken + _shift_taken)
        # 語の列としての組み直し（項目48-LU）は語ごとに漢字へ縮む
        # ので、長さの検査から外す（かいせきがおわった→解析が終わった
        # は2字、組む語が多いほど縮む。読みの列の完全な組み上がりが
        # 長さの代わりの砦）。
        is_lu = any(not (end <= s or start >= e)
                    for s, e in lu_taken + conv_taken)
        if not is_halfwidth and not is_lu \
                and abs(len(new_surface) - len(original)) > 2:
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
        out = dict(empty)
        out['unsure_spans'] = unsure_spans
        _why_out = []
        out['odd_spans'] = _odd_spans_for_line(line, tokenize_fn, (),
                                               store, dict_index,
                                               reasons_out=_why_out)
        out['odd_reasons'] = _why_out
        return out

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
    _why_out = []
    final_odd = _odd_spans_for_line(line, tokenize_fn, original_spans,
                                    store, dict_index,
                                    reasons_out=_why_out)

    return {
        'original': line,
        'corrected': corrected,
        'changed': corrected != line,
        'details': details,
        'unsure_spans': final_unsure,
        # **異様と見た範囲**（項目48-IR）。直せなくても紫で見せる。
        'odd_spans': final_odd,
        # **なぜ異様と見たのか**（項目48-MD・2026-08-31）。
        # `[(始まり, 終わり, 理由), ...]`。**直せた範囲のぶんも残す**
        # （`odd_spans` からは消えるが、理由を聞かれるのはそこ）。
        # 画面の「－ 補正根拠 －」だけが読む。答えには関わらない。
        'odd_reasons': _why_out,
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


_COMPOUND_MAX_LEN = max(len(w) for w in COMPOUND_FUNCTION_WORDS)


def compound_ranges(surfaces):
    """
    **表層の並びの、どこからどこが複合辞か**（項目48-NV）。

    戻り値: [(始まりの添字, 終わりの添字（**含む**）, 語), ...]

    **繋ぐ側の形（要素数・添字）を知らない。** 解析の語（7要素）でも、
    画面の品詞判定が使う形（`explain._tokens_for` の5要素）でも
    同じに使える——**判定は1本、繋ぎ方だけ各所**（項目48-GN
    「同じ判定をもう一度書くと、いつか食い違う」／学び22）。

    **いちばん長い一致**を採る（`いずれにせよ` と `いずれにしても` の
    ように頭を共有する族があるため）。**2語以上のときだけ**返す
    ——解析器が既に1語にしているものは繋ぎ直す必要が無い。
    """
    out = []
    i, n = 0, len(surfaces)
    while i < n:
        hit = None
        surf = ''
        for j in range(i, n):
            surf += (surfaces[j] or '')
            if len(surf) > _COMPOUND_MAX_LEN:
                break
            if j > i and surf in COMPOUND_FUNCTION_WORDS:
                hit = (j, surf)
        if hit is not None:
            out.append((i, hit[0], hit[1]))
            i = hit[0] + 1
            continue
        i += 1
    return out


def merge_compound_words(toks):
    """
    **複合辞を1語に繋ぎ直す**（項目48-NV・2026-09-01・うにさんの指定
    「とはいえ、の4文字で接続詞判定するべきです」）。

        と(格助詞) / は(係助詞) / いえ(動詞・命令ｅ)
          → **とはいえ(接続詞)** ひとつ

    どこを繋ぐかは `compound_ranges` が決める（判定は1本）。
    ここがやるのは**繋ぎ方**だけ:

        読み       繋げたものを並べる
        位置       先頭の始まり〜末尾の終わり（**画面の印がここに乗る**）
        読み確定   全部が確定しているときだけ立てる
        活用形     **必ず空**（複合辞は活用しない。`命令ｅ` を残すと
                   画面が「接続詞・命令形」と出す）

    **入力の要素数に合わせて返す**——janome の道は7要素、janome の
    無い道は6要素。`oddness.infl_mismatch` は `len(a) < 7` を
    「活用形が分からない環境」の印にしているので、幅を勝手に
    広げてはいけない。
    """
    if not toks or len(toks) < 2:
        return toks
    hits = compound_ranges([t[0] for t in toks])
    if not hits:
        return toks
    out = list(toks)
    wide = len(toks[0]) >= 7
    for a, b, whole in reversed(hits):
        part = out[a:b + 1]
        rd = ''.join((t[2] or '') for t in part)
        known = all(bool(t[5]) for t in part)
        merged = (whole, COMPOUND_FUNCTION_WORDS[whole], rd,
                  part[0][3], part[-1][4], bool(known))
        out[a:b + 1] = [merged + ('',) if wide else merged]
    return out


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
            # **活用形も渡す**（項目48-NT・2026-09-01・うにさんの指定
            # 「異様さとは、品詞の文法が間違っていることが大半」）。
            # 品詞だけでは文法が見きれない——`書け`（仮定形）と
            # `食べ`（連用形）はどちらも `動詞:自立` で、後ろに来られる
            # ものが違う。**7つ目**に足す（分解している所は `*_` で
            # 受けるようにした）。
            out.append((t.surface, pos, t.reading or '',
                        t.start, t.end, bool(t.has_reading and t.reading),
                        getattr(t, 'infl_form', '') or ''))
        # **複合辞を1語に繋ぎ直す**（項目48-NV）。ここが janome の
        # 道の**唯一の出口**なので、掛けるのはこの1か所でよい
        # （`morphology.tokenize` を呼ぶのはこの関数だけ）。
        return merge_compound_words(out)

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
                # **複合辞はその品詞で**（項目48-NV・学び22——
                # janome の道だけに置くと、こちらが素通りする）
                pos = COMPOUND_FUNCTION_WORDS.get(w)
                if pos is None:
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
        # **janome の道と同じに繋ぐ**（項目48-NV・学び22）。
        # 上のひらがな枝は「連なりまるごとが表の語」のときだけで、
        # **`何にせよ` のように漢字を含む複合辞には当たらない**
        # （文字種で切るので 何／にせよ に割れる）。
        # **6要素のまま返る**（繋ぎは入力の幅に合わせる）。
        #
        # **仕組みの限界**（掛け忘れではない・書いておく）: この簡易
        # 分割はひらがなの連なりを**一度も割らない**ので、
        # `まあとはいえそうだ` のように複合辞が長いかなの中に埋もれて
        # いる形は、janome が無いと取り出せない。
        return merge_compound_words(out)

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
