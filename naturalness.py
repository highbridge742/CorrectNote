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
**単語と単語の結びつきが自然か**で判断する（項目48-AD / 48-AE）。

うにさんの指定（2026-08-11）:

「**正しく読めるとは、辞書と一致するではなく、単語と単語の
結びつきに違和感がないこと**や、何を目的としてその文字が
入力されているのか。**意図が分かれば変換候補は確定します**」
「局所的な修正はきりがありません。**連接コストを優先して
組み立てましょう**」

**中身は `morphology.path_cost`**（janome の Viterbi 最小コスト）。
ここはその使い方だけを決める。

----------------------------------------------------------------
**必ず「比べて」使う。しきい値では決めない。**
----------------------------------------------------------------

1文字あたりのコストは、語の長さや珍しさに引きずられる。実測では
正しい日本語28件の中央値 1322/字 に対し、壊れた並び23件の最小が
1011/字 で**重なっていた**（`naturalness_check.py`）。
`7文字の名詞`（正しい）は 5827/字 もある。

**比べれば決まる。** 同じ文の中で「元」と「直し先」を比べると:

  - 直したい例 15/17 で、直し先のほうが安い
  - 壊してはいけない例 11/14 で、元のほうが安い

----------------------------------------------------------------
**これ単独では足りない。**
----------------------------------------------------------------

実測で外した3件は、どれも**正しい語を別の正しい語に**
置き換える形だった:

  打った行 → 打っ作業（+1874）／ 左ペイン → 索引（+1690）
  階層を見直す → 回想を見直す（+360）

だから **今までの関門は全部残す**。連接コストは
**関門を通ったあとの決め手**と、
**「辞書で読めるから触らない」を「明らかに自然でなければ触らない」
に変えるための物差し**として使う。

うにさん:「IMEの変換はそもそも修正が多いので、独自で判定する
優れた仕組みが必要です。**先に連接コスト、その先で独自の工夫**です。
独自の工夫とは、**馴染みのない単語の優先を下げる**こともひとつ」
→ 馴染みの薄い語を下げる話は**次の段**。ここには入れない。

**その必要性を示す実例**（この土台を作った時点で出た）:

    best_of('たんあごの繋がり',
            ['単語の繋がり', '担架の繋がり', 'たんごの繋がり'])
      → **('担架の繋がり', 8881)**

`担架`（8881）のほうが `単語`（8606）より「自然」だと出る。
IPAdic のコストは新聞のコーパス由来なので、**日常のメモでは
まず使わない語**でも安く出ることがある。
うにさんの言う「IMEの変換はそもそも修正が多い」はこれ。

**だから `best_of` を単独の選び手にしてはいけない。**
候補づくり（使用実績・語彙）で絞ったあとの**決め手**として使う。
馴染みの薄い語を下げる仕組みが入れば、ここも任せられる。
"""

try:
    from morphology import path_cost as _raw_path_cost, path_words
except Exception:      # morphology が読めない状況でも落とさない
    def _raw_path_cost(_line):
        return None

    def path_words(_line):
        return []

try:
    import familiarity as _familiarity
except Exception:
    _familiarity = None


def path_cost(text):
    """その並びの不自然さ（連接コストそのまま）。"""
    return _raw_path_cost(text)


def _unfamiliar(text):
    """
    その並びが持ち込む**馴染みの薄さ**（項目48-AF）。

    **直し先にだけ効かせる。** 元にも足すと、元のコストが上がって
    **どんな置き換えも「自然になった」ように見える**。
    実際それで `目もち長 → メモちょが` が戻り、誤爆が
    388 → 409 に増えた（2026-08-11 に実測して気付いた）。

    見たいのは「**この直しは馴染みの薄い語を持ち込むか**」であって、
    「元が馴染み薄いか」ではない。元は**うにさんが打った文字**で、
    馴染みがあるかどうかを問う筋合いのものではない。
    """
    if _familiarity is None:
        return 0
    try:
        return _familiarity.penalty(path_words(text))
    except Exception:
        return 0


# 「明らかに自然になった」と言える差。
#
# **実測から決めた**（naturalness_check.py）。直したい例で出た差は
# +248（開業→改行）〜 +19915（たんほ→単語）。
# 一方、通してはいけない側で出た差は +360（階層→回想）・
# +1690（左ペイン→索引）・+1874（打った行→打っ作業）。
# **重なっているので、差だけでは切れない。**
#
# だからここは「差が出れば通す」ためではなく、
# **「ほんの少し安いだけでは通さない」ための下限**として置く。
# 通してよいかどうかの本体は、今までの関門が受け持つ。
MIN_GAIN = 300

# 「辞書で読める並び」に手を入れるときの下限。
#
# **2000 では低すぎた**（2026-08-11 に実測して分かった）。
# 誤爆が 418 → 552 に増えた。中身はこういうもの:
#
#     安全性 → 安全良い（+3861）／可能性 → 可能良い（+3861）
#     操作性 → 操作良い（+2754）／目もち長 → メモちょが（+2798）
#
# **接尾語の「性」を、ありふれた語の「良い」に置き換えている。**
# IPAdic のコストは新聞のコーパス由来なので、
# **`良い` のような日常語がとにかく安く**、接尾語は高い。
# うにさんの言う「IMEの変換はそもそも修正が多い」そのもの。
#
# 直したい例の差は +5509〜+7600 に固まっていたので、
# **5000** にした。これで上の4件は通らず、
# `目もち長→メモ帳`(+7314) `性格→正確`(+7600)
# `簡易流力→簡易入力`(+6110) `待ち外→間違い`(+5509) は通る。
#
# **馴染みの表（項目48-AF）を入れたあとも 5000 のままが良かった。**
# 2500 まで下げたら誤爆が 388 → 495 に戻った
# （`目もち長 → メモちょが` など）。馴染みの表は
# **辞書に載っている語**にしか効かないので、`メモちょが` のような
# 語ですらない並びは下げられない。そこは敷居が受け持つ。
#
# **動かすときは realcheck.py（直る力）と misfire.py（誤爆）の
# 両方で測ること。片方だけ見ると必ずどちらかが崩れる。**
def _looks_unnatural(text):
    """
    **出す先が、日本語の文字の並びとして無理がないか**（項目48-BM）。

    「何にも属さない文字列」を出さないための検品。**止める側にしか
    使わない**（点が高いことを直してよい根拠にはしない）。
    表が無ければ止めない。
    """
    try:
        import charngram
        return charngram.looks_unnatural(text)
    except Exception:
        return False


MIN_GAIN_READABLE = 5000


def cost(text):
    """その並びの不自然さ。測れなければ None（意見なし）。"""
    return path_cost(text)


def gain(before, after):
    """
    `before` を `after` にすると、どれだけ自然になるか。

    正なら自然になる（＝直し先のほうが安い）。
    測れなければ None（意見なし）。
    """
    if not before or not after or before == after:
        return None
    a = path_cost(before)
    b = path_cost(after)
    if a is None or b is None:
        return None
    # **直し先が持ち込む「馴染みの薄さ」だけを引く**（項目48-AF）。
    return a - (b + _unfamiliar(after))


def is_more_natural(before, after, min_gain=None, default=None):
    """
    `after` のほうが**明らかに自然**か。

    default: 測れないときに返す値。
        **呼ぶ側が「意見なしのときどうするか」を必ず決めること。**
        janome の無い環境（tests_mock）では常にこれが返るので、
        ここを True にすれば今までどおり、False にすれば
        「janome が無いと直らない」になる。
    """
    g = gain(before, after)
    if g is None:
        return default
    return g >= (MIN_GAIN if min_gain is None else min_gain)


def _has_kanji_or_katakana(text):
    for ch in text or '':
        if ('\u4e00' <= ch <= '\u9fff'
                or '\u30a1' <= ch <= '\u30fa'):
            return True
    return False


def comparable(before, after):
    """
    連接コストで比べる意味がある組か。

    **かなだけ ⇄ かなだけ の直しは比べられない**（実測・48-AE）。
    連接コストは「その並びをどう読むか」の話なので、
    **長いかなの連なりは、正しくても必ず高く出る**:

        'たんあごの繋がり' 17577  →  'たんごの繋がり' 25768（悪化）
        'たんあごの繋がり' 17577  →  '単語の繋がり'    8971（改善）

    `たんご` は打ち間違いとしては正しい直しだが、
    **かなのままでは自然にならない**。このアプリは
    「ひらがなで入力されたものはひらがなのまま補正」する方針なので、
    かなの直しをコストで裁くと**必ず却下**になる。

    そこで、**どちらかに漢字かカタカナが含まれるときだけ**
    コストで比べる。かな同士は今までどおりの判断に任せる。
    """
    return _has_kanji_or_katakana(before) or _has_kanji_or_katakana(after)


def worth_touching_readable(before, after, default=None):
    """
    **辞書としては読める並び**を、あえて直してよいか。

    今までは「読める＝触らない」で門を閉じていた。
    そこを「**読めるなら、明らかに自然にならない限り触らない**」に
    変えるための判定（項目48-AE）。

    かな同士の直しは比べられないので `default` を返す
    （＝呼ぶ側の今までの判断に任せる。`comparable` の説明を参照）。
    """
    if _looks_unnatural(after):
        return False
    if not comparable(before, after):
        return default
    return is_more_natural(before, after,
                           min_gain=MIN_GAIN_READABLE, default=default)


def gain_in_line(line, start, end, after):
    """
    その一箇所を直したとき、**行ぜんたい**がどれだけ自然になるか
    （項目48-AH）。

    **断片だけで比べてはいけない。** うにさんの言う
    「**単語と単語の結びつきに違和感がないこと**」は、
    断片には無い。切り出した瞬間に、前後との継ぎ目が消えるため。

    実測（2026-08-11）。同じ直しを、断片で比べた差と
    行ごと比べた差:

        作れるこ→される    断片 +10755 ／ **行  -1096**
        重いこ  →おもい    断片  +6911 ／ **行 -12887**
        広く使  →こう消し  断片  +7324 ／ **行  -8412**
        取りに行→とりない  断片  +6863 ／ **行  -9524**
        選択し直→選択肢ない 断片 +6970 ／ **行 -13661**
        誤って消→誤っでき  断片  +5107 ／ **行  -5737**
        目もち長→メモ帳    断片  +7314 ／ **行  +6028**

    **断片で見ると全部「自然になった」に見える。**
    `される` `おもい` のようなありふれた語は、それ単体では
    とても安いため。行ごと見ると継ぎ目の不自然さが出て
    **符号が反転する**。直したい `目もち長→メモ帳` だけが正のまま。

    馴染みの薄さ（項目48-AF）は**直し先の文字にだけ**足す。
    行ぜんたいに足すと、うにさんが自分で書いた語まで
    「馴染みが薄い」と数えてしまう（学び33）。
    """
    if not line or start < 0 or end > len(line) or end <= start:
        return None
    after_line = line[:start] + after + line[end:]
    if line == after_line:
        return None
    a = path_cost(line)
    b = path_cost(after_line)
    if a is None or b is None:
        return None
    return a - (b + _unfamiliar(after))


def worth_touching_readable_here(line, start, end, after, default=None):
    """
    **文全体では読める範囲**を、あえて直してよいか（行ごとに比べる）。

    `worth_touching_readable` の行ごと版。比べてよい組かどうかは
    **断片で決める**（行で決めると、行のどこかに漢字があるだけで
    かな⇄かなの直しまで比べに行ってしまう。`comparable` の説明）。
    """
    if not line or end > len(line) or end <= start:
        return default
    if _looks_unnatural(after):
        return False
    if not comparable(line[start:end], after):
        return default
    g = gain_in_line(line, start, end, after)
    if g is None:
        return default
    return g >= MIN_GAIN_READABLE


def line_not_worse(line, start, end, after, default=None):
    """
    **範囲が語を途中で切っているとき**に使う関門（項目48-AH）。

    切れている範囲を直すのは、たいてい「範囲の取り方が悪い」だけ。
    それでも直したいなら、せめて**行が悪くなっていない**ことを
    求める。敷居は低くてよい。実測（2026-08-11）で、
    語を途中で切っている組はこう分かれた:

        通したい  みきれま→みきれます  **+12023**
        止めたい  残すか消→残す効か      -850
                  作れるこ→される      -1096
                  できるほ→できれ      -4649
                  誤って消→誤っでき     -5737
                  広く使  →こう消し     -6476
                  対して行→足し指定     -7311
                  選択し直→選択肢ない   -7811
                  長く消  →帳書き       -8126
                  取りに行→とりない     -9524
                  直すと決→直す溶け     -9867
                  重いこ  →おもい      -10608
                  らない  →かない      -12268

    **止めたい側は全部マイナス**。`MIN_GAIN`（300）で切れる。
    高い敷居（MIN_GAIN_READABLE）は要らないし、使うと
    `みきれま→みきれます` 以外の正しい直しも巻き込む。

    **ここでは `comparable`（かな⇄かなは比べない）を使わない。**
    あの制限は**断片で比べるとき**のもので、理由は
    「長いかなの連なりは、正しくても必ず高く出る」だった。
    行ごとに比べるなら、行には漢字も入っているので、
    差を決めるのは**継ぎ目**であって、かなの長さではない。
    実測でもそのとおりに出た:

        みきれま→みきれます（かな⇄かな・通したい）  **+12023**
        らない  →かない    （かな⇄かな・止めたい）  **-12268**

    断片の決まりをそのまま持ち込むと、`みきれま→みきれます` が
    「比べられない」となって落ちる（2026-08-11 に実際に落とした）。
    """
    if not line or end > len(line) or end <= start:
        return default
    g = gain_in_line(line, start, end, after)
    if g is None:
        return default
    return g >= MIN_GAIN


def best_of(before, candidates, min_gain=None):
    """
    候補の中から、**いちばん自然になるもの**を選ぶ。

    うにさんの「意図が分かれば変換候補は確定します」に当たる部分。
    どれも自然にならなければ None（＝直さない）。

    candidates: 直し先の文字列の並び。
    戻り値: (選んだ文字列, どれだけ自然になったか) または None
    """
    base = path_cost(before)
    if base is None:
        return None
    need = MIN_GAIN if min_gain is None else min_gain
    best = None
    for cand in candidates:
        if not cand or cand == before:
            continue
        c = path_cost(cand)
        if c is None:
            continue
        g = base - c
        if g >= need and (best is None or g > best[1]):
            best = (cand, g)
    return best
