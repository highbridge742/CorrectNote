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
語として成立しない漢字列を、読みに戻して推測する。

かな入力の誤打はIMEを通って漢字に変換されるため、
画面に出てくるのは「かなの誤り」ではなく **漢字の誤変換** である。

  「かくにん」と打つつもりで「すきにん」と打ってしまうと、
  IMEはそれらしく変換して「素帰任」を作る。

「素帰任」は語として存在しない。この判断には文脈は要らない。
**その文字列単体がありえない** と分かれば、あとは機械的に導ける。

  素 = す、帰 = き、任 = にん  → すきにん
  隣接キーを考えれば「かくにん」に届く  → 確認

同じ構造の誤りとして、実機から次が報告されている:

  時ッ層     → じ・っ・そう  → じっそう → 実装
  見切れ魔訶 → み・き・れ・ま・か → みきれます → 見切れます
  素帰任     → す・き・にん  → すきにん → 確認

読みに戻す手段は2つ併用する（kanji_readings.py 参照）:
  1. janome 内蔵辞書の逆引き（dict_index）… 主
  2. 自前の単漢字読み表 … janome で引けない分の補い

**この処理は「直すかどうか」を判断しない。**
判断は corrector.py に集約されているという設計を守り、
ここは「ありえない漢字列を見つけ、届きうる読みを並べる」
までを担う。採否は corrector.py 側が既存の基準
（使用実績のある語か・打ち間違いとして自然か）で決める。
"""

# 1つの塊として扱う最大の長さ。長すぎる範囲を一度に置き換えると
# 外したときの被害が大きいので、ほどほどで切る。
MAX_RUN_LEN = 8
# 最低これだけの長さが無いと対象にしない。
MIN_RUN_LEN = 2

# 塊の途中に挟まってよいひらがなの最大の長さ。
# 「見切れ魔訶」の「れ」のように、送り仮名や活用語尾が
# 漢字の間に入ることがあるため、短いものは塊に含める。
# 長いひらがなの並びは、そこで文が区切れているとみなす。
MAX_INNER_KANA = 2

# 塊の途中に挟まっていても、そこで区切るべきひらがな。
# 助詞は語と語の境目なので、またいで1つの塊にすると
# 無関係な語どうしを繋げてしまう
# （「単語の繋がり」を「単語の繋がり」全体で1語と見ない）。
_BOUNDARY_KANA = set('のはをがにへとでもやかねよねなら')

# **語の一部になりえない、硬い境目**（項目48-CH・2026-08-13）。
#
# 上の `_BOUNDARY_KANA` は「助詞かもしれない字」で、**1文字でも
# 助詞でない字が混じれば塊として繋ぐ**作りになっている。
# 「目もち長」の「もち」を繋ぐために要る決まりだが、
# **「るを」のように活用語尾＋助詞の組でも繋がってしまう**:
#
#     物語るを確認しました。  →  物語を確認しました。
#     （塊が `物語るを確認` になり、助詞「を」を跨いでいた）
#
# `を` は現代語では**ほぼ必ず助詞**で、語の送り仮名になることが無い。
# ここだけは「1文字でもあれば切る」にする。
#
# 実測: 実機のメモ全6タブ＋正しい日本語＋散文で、
# **変わった行は51件のまま、答えも1件も動かない**。
# `たん子の繋がり → 単語の繋がり` も通ったまま。
# （`が` `は` `に` `で` `と` `も` は語の中にも現れる——すが・かが・
#   には・ので・こと・もの——ので、同じ扱いにはしない）
_HARD_BOUNDARY_KANA = 'を'


# 読みの組み合わせを何通りまで試すか。
# 漢字1文字あたり2〜3通りの読みがあるため、掛け算で急に増える。
MAX_COMBOS = 24


# 文の終わりを示す記号。塊のすぐ後ろにこれが来ていれば、
# その塊は文末にあたる（＝活用語尾で終わる可能性が高い）。
SENTENCE_END = set('、。.，,！!？?）)」』】〕：:；;…')


def _looks_sentence_end(line, end):
    """
    塊の直後が文の終わり（またはその手前）か。

    「見切れ魔訶。」のように文末記号が続くなら、その塊は
    「〜ます」「〜です」のような活用語尾で終わる語である
    可能性が高い。語幹だけを辞書で探しても届かないので、
    語尾を補って探す手がかりにする。
    絵文字が続く場合も、文の区切りとして同じに扱う。
    """
    if end >= len(line):
        return True        # 行末も文末とみなす
    ch = line[end]
    if ch in SENTENCE_END:
        return True
    # 絵文字・記号（日本語でもASCIIでもないもの）
    if ord(ch) > 0x2000 and not (
            '\u3041' <= ch <= '\u30fa' or '\u4e00' <= ch <= '\u9fff'):
        return True
    return False


# 文末で現れやすい活用語尾。長いものから試す。
# 語幹に付け足して、辞書に届くかを見るために使う。
SENTENCE_TAILS = [
    'ます', 'ません', 'ました', 'ましょう',
    'です', 'でした', 'ですね', 'でしょう',
    'する', 'した', 'します', 'しました',
    'れる', 'れます', 'られる',
    'ある', 'あります', 'いる', 'います',
    'ない', 'ません',
]


def _tail_variants(reading):
    """
    読みの末尾を、文末で現れやすい語尾に差し替えた候補を作る。

    「みきれまか」の末尾「まか」は、打ち間違いとしては
    「ます」に近い（か と す は隣接キー）。しかし語彙には
    活用した形（見切れます）が載っているとは限らないため、
    語尾を差し替えた形も探索の入口として用意しておく。

    末尾1〜3文字を、それぞれの語尾で置き換えたものを返す。
    """
    out = []
    for cut in (2, 3, 1):
        if len(reading) <= cut:
            continue
        stem = reading[:-cut]
        if len(stem) < 2:
            continue
        for tail in SENTENCE_TAILS:
            cand = stem + tail
            if cand != reading and cand not in out:
                out.append(cand)
    return out


def _is_kanji(ch):
    return '\u4e00' <= ch <= '\u9fff'


def _is_hiragana(ch):
    return '\u3041' <= ch <= '\u3096'


def _is_katakana(ch):
    # \u9577\u97f3\u300c\u30fc\u300d\u3082\u30ab\u30bf\u30ab\u30ca\u8a9e\u306e\u4e00\u90e8\u3068\u3057\u3066\u6271\u3046\u3002
    # \u3053\u308c\u3092\u5916\u3059\u3068\u300c\u30ed\u30fc\u30de\u5b57\u5165\u529b\u300d\u304c \u30ed\uff0f\u30fc\uff0f\u30de\u5b57\u5165\u529b \u306b\u5206\u65ad\u3055\u308c\u3001
    # \u300c\u30de\u5b57\u5165\u529b\u300d\u3060\u3051\u304c\u584a\u306b\u306a\u3063\u3066\u300c\u6587\u5b57\u5165\u529b\u300d\u306b\u5316\u3051\u308b
    # \uff08\u5b9f\u6a5f\u3067\u300c\u30ed\u30fc\u30de\u5b57\u5165\u529b\u300d\u2192\u300c\u30ed\u30fc\u6587\u5b57\u5165\u529b\u300d\u3068\u58ca\u308c\u305f\uff09\u3002
    return '\u30a1' <= ch <= '\u30f6' or ch == '\u30fc'


# 誤変換の塊に混ざりうる、小さいカタカナ（促音・拗音）。
# 「時ッ層」の「ッ」のように、かなの一部がカタカナで
# 確定してしまうことがある。
_SMALL_KATAKANA = {
    'ッ': 'っ', 'ャ': 'ゃ', 'ュ': 'ゅ', 'ョ': 'ょ',
    'ァ': 'ぁ', 'ィ': 'ぃ', 'ゥ': 'ぅ', 'ェ': 'ぇ', 'ォ': 'ぉ',
}


def _has_rare_kanji(text):
    """
    日常では使わない漢字が混ざっているか。

    「魔訶」の「訶」のように、見ただけで異様と分かる漢字が
    入っているなら、短い塊でも誤変換を疑ってよい。
    """
    try:
        import kanji_readings
    except Exception:
        return False
    return any(_is_kanji(c) and not kanji_readings.is_everyday(c)
               for c in text)


def is_suspicious_run(text):
    """
    その塊を、誤変換の疑いありとして調べる価値があるか。

    長さだけで決めない。短くても異様な漢字を含むなら調べるし、
    日常的な漢字だけの短い塊は触らない。

      「魔訶」  2文字だが「訶」が異様 → 調べる
      「見切」  日常的な漢字だけ      → 触らない
                （「見切れます」を壊さないため）

    3文字以上あれば、日常的な漢字だけでも調べる価値がある
    （「素帰任」は全て日常の漢字だが、並びとしてありえない）。

    カタカナと漢字が混ざった塊（「タン子」「タン具」）も調べる。
    かな入力の誤打では、IMEが途中までをカタカナ、残りを漢字に
    変換してしまうことがあり、これは単独では意味を成さない
    （実機で報告された）。ただしカタカナだけの塊は対象にしない。
    外来語・固有名詞・略語が大半で、辞書に無くて当然だからである
    （「ネイル」「スタン」を壊した過去がある）。
    """
    n = len(text)
    if n < MIN_RUN_LEN or n > MAX_RUN_LEN:
        return False
    has_kanji = any(_is_kanji(c) for c in text)
    if not has_kanji:
        return False
    if n >= 3:
        return True
    return _has_rare_kanji(text)


def find_kanji_runs(line):
    """
    漢字を軸にした塊を取り出す。

    漢字の間に挟まった短いひらがな（送り仮名・活用語尾）は、
    塊の一部として含める。
      「見切れ魔訶」→ 見・切・れ・魔・訶 で1つの塊
    こうしないと「れ」で分断されて「魔訶」だけが残り、
    元の打鍵（みきれまか）を復元できない。

    ただし助詞（の・は・を・が…）は語の境目なので、そこで切る。
    またいで繋げると、無関係な語どうしを1語と見てしまう
    （「単語の繋がり」を丸ごと1語として扱わない）。

    「時ッ層」のように、誤変換の塊にはカタカナの促音・拗音が
    混ざることもあるため、それらも塊の一部として扱う。

    戻り値: [(開始, 終了, 文字列), ...]
    """
    runs = []
    i = 0
    n = len(line)
    while i < n:
        if not _is_kanji(line[i]) and not _is_katakana(line[i]):
            i += 1
            continue
        j = i
        last_solid = i if _is_kanji(line[i]) else -1
        while j < n:
            ch = line[j]
            if _is_kanji(ch):
                last_solid = j
                j += 1
                continue
            if _is_katakana(ch) and ch not in _SMALL_KATAKANA:
                # カタカナは塊に含めるが、塊の終わりとしては数えない
                # （「タン子」の「子」までを塊にしたいが、
                #   「タン」で終わる塊は作らない）。
                j += 1
                continue
            if ch in _SMALL_KATAKANA and j + 1 < n and (
                    _is_kanji(line[j + 1]) or _is_katakana(line[j + 1])):
                # 小さなカタカナは、後ろに漢字かカタカナが続くときだけ
                # 塊に含める。カタカナが続く場合を切ってしまうと、
                # 「ドラッグ変換」が ドラ／ッグ変換 に分断され、
                # 「グ変換」だけが塊になって壊れる（実機で
                # 「ドラッグ変換」→「ドラッカナ漢」と壊れた）。
                j += 1
                continue
            if _is_hiragana(ch):
                # 短いひらがなを挟んで、その先にまだ漢字が続くなら
                # ひとつながりの塊とみなす（見切れ魔訶 の「れ」）。
                # 助詞（の・は・を…）1文字だけを挟む形は語の境目
                # なので繋がない（単語の繋がり を1塊にしない）。
                # ただし「目もち長」の「もち」のように、助詞と同じ字が
                # 挟まったかなの一部であることがあるため、挟まった
                # かなに助詞でない字が混ざっていれば塊として繋ぐ。
                k = j
                while (k < n and _is_hiragana(line[k])
                       and k - j < MAX_INNER_KANA):
                    k += 1
                inner = line[j:k]
                if (k < n and _is_kanji(line[k])
                        and inner[-1:] in _HARD_BOUNDARY_KANA):
                    # **`を` のすぐ後ろに漢字が来る形は、そこで切る**
                    # （項目48-CH）。`を` は現代語ではほぼ必ず助詞で、
                    # その直後の漢字は**別の語の頭**である。
                    #
                    #   物語るを確認しました。 → 物語を確認しました。
                    #   （塊が `物語るを確認` になっていた）
                    #
                    # **`を` が橋の途中にあるとき（`をお願` など）は
                    # 触らない。** そこで切ると塊が短くなり、
                    # **短くなったぶん新しく直せてしまう**:
                    #
                    #   再実行をお願いします。 → 最高をお願いします。
                    #   （`再実行をお願` を `再実行` に切ったせい。
                    #     実 janome では `再実行` が実在語として
                    #     守られるので出ないが、mock では出た）
                    #
                    # 塊ごと捨てる形も測ったが、
                    # `該当あの範囲を選ぶ`（混入かなの削除）が
                    # 直らなくなった（tests_mock が1件落ちた）。
                    # **`を` が橋の最後にあるときだけ**が、3つとも
                    # 満たす唯一の形だった。
                    break
                if (k < n and _is_kanji(line[k])
                        and any(c not in _BOUNDARY_KANA for c in inner)):
                    j = k
                    continue
            break
        if last_solid < 0:
            # 漢字が1つも無い（カタカナだけ）。対象にしない。
            i = max(j, i + 1)
            continue
        end = last_solid + 1
        chunk = line[i:end]
        if is_suspicious_run(chunk):
            runs.append((i, end, chunk))
        i = max(j, i + 1)
    return runs


def kana_for_ascii(ch):
    """
    半角（または全角化された）英字・記号1文字を、JISかな配列で
    そのキーに割り当てられたかなに読み替える候補。

    かな入力の途中で一瞬だけ半角モードに落ちると、かなの並びの
    中に英字・記号が1文字だけ混入する（実機で報告された1-B）:
      たｂごの繋がり  （ｂ のキーは こ）
      単=の繋がり     （= のキーは ほ）

    Shift側の割り当て（=→ほ 等）も候補に含める。
    かなに対応しないもの（゛゜・空など）は返さない。

    戻り値: [かな, ...]（0〜2件）
    """
    try:
        from halfwidth import HALFWIDTH_TO_KANA, SHIFT_TO_KANA
    except Exception:
        return []
    code = ord(ch)
    if 0xFF01 <= code <= 0xFF5E:      # 全角 → 半角
        ch = chr(code - 0xFEE0)
    out = []
    for kana in (HALFWIDTH_TO_KANA.get(ch.lower() if ch.isalpha() else ch),
                 SHIFT_TO_KANA.get(ch)):
        if kana and _is_hiragana(kana) and kana not in out:
            out.append(kana)
    return out


def find_ascii_mixed_runs(line, max_len=MAX_RUN_LEN):
    """
    日本語の並びの中に半角英字・記号が **1文字だけ** 混入した塊を
    取り出す（方針1-B）。

      たｂごの繋がり → たｂご
      他b後の繋がり  → 他b後
      単=の繋がり    → 単=
      たんb後の繋がり → たんb後

    条件（正しい文章を巻き込まないための絞り込み）:
      - その文字が **英字（全角含む）か「=」** で、かなキーに
        対応している（kana_for_ascii）。
        数字・記号は対象にしない。「第1章」の 1、「例：単語」の ：
        のように、日本語に挟まれた数字・句読点は意図した表記が
        圧倒的に多い（実機で「例：単語」が ：→け の読み替えから
        「英単語」に化けた）。かな入力の打鍵は大半が英字キーなので、
        英字に絞っても取りこぼしは小さい。= だけは実機の報告
        （単=の繋がり）にあるため対象に残す。
      - 直前・直後が日本語（かな・カタカナ・漢字）
        （「Python3で」の 3 は前が英字なので対象外）
      - 塊は助詞（の・は・を…）で区切る（find_kanji_runs と同じ）
      - 塊の中の非日本語文字はその1文字だけ
      - 混入文字が塊の先頭に来る形は対象外
        （「AとB案」の B のように、前が助詞で切れて先頭に
          残るのは、意図した英字である可能性が高い）

    戻り値: [(開始, 終了, 文字列), ...]
    """
    def _jp(c):
        return _is_hiragana(c) or _is_katakana(c) or _is_kanji(c)

    def _stray_ok(c):
        code = ord(c)
        if 0xFF01 <= code <= 0xFF5E:
            c = chr(code - 0xFEE0)
        return c.isalpha() or c == '='

    runs = []
    n = len(line)
    i = 0
    while i < n:
        ch = line[i]
        if _jp(ch) or not _stray_ok(ch) or not kana_for_ascii(ch):
            i += 1
            continue
        # 同じ英字の2連（たｂｂご）は1打として扱う。
        # かな入力では同じキーの連打が起きやすく（連打の費用が
        # 安い理由と同じ）、ローマ字打ちには「Nを2回押して ん」の
        # 習慣もある（実機からの指摘）。3連以上は意図した英語とみなす。
        code = ord(ch)
        ch_half = chr(code - 0xFEE0) if 0xFF01 <= code <= 0xFF5E else ch
        pair = (i + 1 < n and line[i + 1] == ch and ch_half.isalpha())
        j = i + 2 if pair else i + 1
        if j < n and line[j] == ch:
            while j < n and line[j] == ch:
                j += 1
            i = j
            continue
        if i == 0 or j >= n:
            i = j
            continue
        if not (_jp(line[i - 1]) and _jp(line[j])):
            i = j
            continue
        s = i
        while s > 0 and _jp(line[s - 1]) \
                and line[s - 1] not in _BOUNDARY_KANA:
            s -= 1
        e = j
        while e < n and _jp(line[e]) \
                and line[e] not in _BOUNDARY_KANA:
            e += 1
        run = line[s:e]
        if not (2 <= len(run) <= max_len) or s == i:
            i = j
            continue
        others = [c for c in run if not _jp(c)]
        if len(others) != (2 if pair else 1):
            i = j
            continue        # 別の英字も混ざる → 意図した英語とみなす
        runs.append((s, e, run))
        i = j
    return runs


def find_trailing_kanji_runs(line, max_head=3):
    """
    「かな2〜3文字＋漢字1文字」の塊を取り出す（方針1-C）。

    かなの並びの最後の1音だけがIMEで漢字に化けた形:
      たん子（たんこ → 単語）／やん後（やんご）／タン子

    正しい文章を巻き込まないための条件:
      - 漢字は1文字だけで、直後に漢字・送り仮名（非助詞のひらがな）が
        続かない（「詰め」「感じ」「タブ機能」は対象外）
      - 前はひらがな・カタカナ2〜3文字で、その前は語の切れ目
        （行頭・助詞・記号・非日本語）
      - 「その辺」「いい子」のような機能語＋漢字は呼び出し側で除く
        （機能語の判定は corrector 側にあるため）

    戻り値: [(開始, 終了, 文字列), ...]
    """
    runs = []
    n = len(line)
    for i, ch in enumerate(line):
        if not _is_kanji(ch):
            continue
        if i + 1 < n and _is_kanji(line[i + 1]):
            continue
        if i + 1 < n and _is_hiragana(line[i + 1]) \
                and line[i + 1] not in _BOUNDARY_KANA:
            continue        # 送り仮名が続く形は正しい活用の可能性
        s = i
        while (s > 0 and i - s < max_head
               and (_is_hiragana(line[s - 1]) or (_is_katakana(line[s - 1])
                                                  and line[s - 1] != 'ー'))
               and line[s - 1] not in _BOUNDARY_KANA):
            s -= 1
        if i - s < 2:
            continue
        # 塊の前が語の切れ目であること（行頭・助詞・記号・非日本語）。
        # 漢字・カタカナ・助詞でないひらがなが直前にあるなら、
        # 語の途中から拾っている（見たん子 の「見」＝送り仮名の頭）。
        if s > 0 and (_is_kanji(line[s - 1]) or _is_katakana(line[s - 1])
                      or (_is_hiragana(line[s - 1])
                          and line[s - 1] not in _BOUNDARY_KANA)):
            continue
        runs.append((s, i + 1, line[s:i + 1]))
    return runs


def find_leading_kanji_runs(line, max_tail=3):
    """
    「漢字1文字＋カタカナ2〜3文字」の塊を取り出す（方針1-C）。

    かなの並びの最初の1音だけがIMEで漢字に化け、残りがカタカナで
    確定した形: 乳リュク（にゅうりゅく → 入力）。

    条件は find_trailing_kanji_runs の鏡写し:
      - 漢字は1文字だけで、直前に漢字・かなが続かない（語の頭）
      - 後ろはカタカナ2〜3文字（ー・小書き含む）で、その後は
        語の切れ目（行末・ひらがな助詞・記号・非日本語）

    戻り値: [(開始, 終了, 文字列), ...]
    """
    runs = []
    n = len(line)
    for i, ch in enumerate(line):
        if not _is_kanji(ch):
            continue
        # 語の頭、または前の語（漢字・助詞）との切れ目であること。
        # 前が漢字でも拾う（「文字乳リュク」の 乳リュク。前の
        # 「文字」は重なり処理と分割解決が守る。実機で「乳リュクは
        # 直るが 文字乳リュク はそのまま」と報告された）。
        # 前がカタカナ・助詞でないひらがななら、語の途中なので拾わない。
        if i > 0 and (_is_katakana(line[i - 1])
                      or (_is_hiragana(line[i - 1])
                          and line[i - 1] not in _BOUNDARY_KANA)):
            continue
        j = i + 1
        while j < n and _is_katakana(line[j]) and j - i - 1 < max_tail:
            j += 1
        if j - i - 1 < 2:
            continue
        if j < n and (_is_katakana(line[j]) or _is_kanji(line[j])):
            continue        # カタカナ・漢字がまだ続く（長い語の途中）
        if j < n and _is_hiragana(line[j]) \
                and line[j] not in _BOUNDARY_KANA:
            continue
        runs.append((i, j, line[i:j]))
    return runs


def find_mixed_kana_runs(line, max_head=3):
    """
    カタカナ・かなの混じった塊を取り出す（方針1-D）。

    かな入力の誤打がIMEを通ると、かなの一部がカタカナや漢字に
    化けて確定することがある。化けた部分だけを見ても語の切り出しに
    掛からず、既存の塊（find_kanji_runs / trailing / leading）にも
    乗らない形が2つ報告された:

      あ. カタカナ2〜3文字＋漢字1文字＋送り仮名1〜2文字
          「カニ打ち」（かな打ち の かな が カニ に化けた形）。
          送り仮名まで塊に含めるのが find_trailing_kanji_runs との
          違い。送り仮名込みだと実在語の並び（カニ＋打ち）として
          読めてしまうため、塊全体を読みの列に戻して、語の組として
          解決する（判断は corrector 側の共通の関門に委ねる）。

      い. ひらがな2〜3文字＋漢字2文字
          「かな地腕」（かな打ちで の 打ちで が 地腕 に化けた形）。
          日常漢字2文字だけの塊は find_kanji_runs が調べない
          （「見切」を守るため）が、直前のかなと合わせて読みの列に
          戻せば、語の組（かな＋打ち＋で）として解決できる。

    正しい文章（カニ料理・ここ数年 等）もこの形に一致するが、
    切り出しは「調べる価値がある」だけの意味で、直すかどうかは
    corrector 側の解決器（as-is との拮抗裁定・文脈の裏付け）が決める。

    戻り値: [(開始, 終了, 文字列), ...]
    """
    runs = []
    n = len(line)
    for i, ch in enumerate(line):
        if not _is_kanji(ch):
            continue
        # --- あ: カタカナ頭＋漢字1文字＋送り仮名 ---
        if not (i + 1 < n and _is_kanji(line[i + 1])):
            s = i
            while (s > 0 and i - s < max_head
                   and _is_katakana(line[s - 1]) and line[s - 1] != 'ー'):
                s -= 1
            head_ok = (i - s >= 2 and not (
                s > 0 and (_is_kanji(line[s - 1])
                           or _is_katakana(line[s - 1])
                           or (_is_hiragana(line[s - 1])
                               and line[s - 1] not in _BOUNDARY_KANA))))
            if head_ok:
                j = i + 1
                while (j < n and j - i - 1 < 2 and _is_hiragana(line[j])
                       and line[j] not in _BOUNDARY_KANA):
                    j += 1
                # 送り仮名が1文字以上あり、その先が語の切れ目である
                # （まだ漢字・カタカナ・送り仮名が続くなら長い語の途中）
                if (j > i + 1 and not (
                        j < n and (_is_kanji(line[j])
                                   or _is_katakana(line[j])
                                   or (_is_hiragana(line[j])
                                       and line[j] not in _BOUNDARY_KANA)))):
                    runs.append((s, j, line[s:j]))
        # --- う: 漢字1〜2文字＋ひらがな2〜5文字（方針1-F） ---
        # 変換し損ね（説明ぶん＝せつめいぶん→説明文）と、
        # 挿入打鍵で機能語列が漢字に化けた形
        # （差釣れません＝さつれません→されません）。
        # 塊の前後は語の切れ目であること。
        if not (i > 0 and (_is_kanji(line[i - 1])
                           or _is_katakana(line[i - 1])
                           or (_is_hiragana(line[i - 1])
                               and line[i - 1] not in _BOUNDARY_KANA))):
            j = i
            while j < n and _is_kanji(line[j]) and j - i < 2:
                j += 1
            if not (j < n and _is_kanji(line[j])):
                t = j
                if t < n and _is_hiragana(line[t]) \
                        and line[t] not in _BOUNDARY_KANA:
                    while (t < n and _is_hiragana(line[t])
                           and line[t] not in _BOUNDARY_KANA
                           and t - j < 5):
                        t += 1
                    if (t - j >= 2 and not (
                            t < n and (_is_kanji(line[t])
                                       or _is_katakana(line[t])
                                       or (_is_hiragana(line[t])
                                           and line[t]
                                           not in _BOUNDARY_KANA)))):
                        runs.append((i, t, line[i:t]))
        # --- え: カタカナ＋漢字1文字＋カタカナ（方針1-F） ---
        # 助詞が漢字に化けて2つのカタカナ語を繋いだ形
        # （クリック化ドラッグ→クリックかドラッグ）。
        # 正しい複合語（システム化プロジェクト）も同じ形に一致する
        # ため、直すかどうかは corrector 側の関門（並記）が決める。
        if not (i + 1 < n and _is_kanji(line[i + 1])):
            s = i
            while (s > 0 and i - s < 6
                   and _is_katakana(line[s - 1])):
                s -= 1
            j = i + 1
            while j < n and _is_katakana(line[j]) and j - i - 1 < 6:
                j += 1
            if (i - s >= 2 and j - i - 1 >= 2
                    and not (s > 0 and (_is_kanji(line[s - 1])
                                        or _is_katakana(line[s - 1])))
                    and not (j < n and (_is_kanji(line[j])
                                        or _is_katakana(line[j])))):
                runs.append((s, j, line[s:j]))
        # --- い': ひらがな頭＋漢字1文字（項目48-LS・2026-08-30） ---
        # かな地（かな打ちでの補正 の 打ち が 地 に化けた形）。
        # い と同じ締まり（頭の前は行頭・記号・非日本語、後ろは語の
        # 切れ目）で、漢字が1文字だけの形。trailing の口は頭の歩みが
        # 「助詞かもしれない字」（か・な・や…）で止まるので、かな地・
        # やん後 はどの列挙にも乗っていなかった。直すかどうかは
        # corrector 側の解決器（as-is との拮抗・並記の裏付け）が決める。
        if not (i + 1 < n and (_is_kanji(line[i + 1])
                               or _is_katakana(line[i + 1]))):
            s = i
            while (s > 0 and i - s < max_head
                   and _is_hiragana(line[s - 1])):
                s -= 1
            if (i - s >= 2
                    and not (s > 0 and (_is_kanji(line[s - 1])
                                        or _is_katakana(line[s - 1])
                                        or _is_hiragana(line[s - 1])))):
                j = i + 1
                if not (j < n and _is_hiragana(line[j])
                        and line[j] not in _BOUNDARY_KANA):
                    runs.append((s, j, line[s:j]))
        # --- い: ひらがな頭＋漢字2文字 ---
        if (i + 1 < n and _is_kanji(line[i + 1])
                and not (i + 2 < n and _is_kanji(line[i + 2]))
                and not (i + 2 < n and _is_katakana(line[i + 2]))):
            s = i
            while (s > 0 and i - s < max_head
                   and _is_hiragana(line[s - 1])):
                s -= 1
            # 頭のかなは2〜3文字で、その前は行頭・記号・非日本語
            # （かなの途中から拾わない。「目もち長」の「もち」は
            #   前が漢字なのでここには掛からない）
            if i - s < 2:
                continue
            if s > 0 and (_is_kanji(line[s - 1]) or _is_katakana(line[s - 1])
                          or _is_hiragana(line[s - 1])):
                continue
            j = i + 2
            # 塊の直後は語の切れ目（行末・助詞・記号・非日本語）
            if j < n and (_is_kanji(line[j]) or _is_katakana(line[j])):
                continue
            if j < n and _is_hiragana(line[j]) \
                    and line[j] not in _BOUNDARY_KANA:
                continue
            runs.append((s, j, line[s:j]))
    return runs


def readings_for_char(ch, dict_index=None):
    """
    1文字ぶんの読みの候補を、確からしい順に返す。

    janome の逆引きを主に使い、そこで引けないものを
    自前の表で補う（実機の janome には単漢字の読みが
    取り出せないビルドがあるため）。
    """
    out = []

    if ch in _SMALL_KATAKANA:
        return [_SMALL_KATAKANA[ch]]
    if _is_hiragana(ch):
        return [ch]
    if _is_katakana(ch):
        if ch == 'ー':
            return ['ー']
        return [chr(ord(ch) - 0x60)]
    # 半角（全角化含む）の英字・記号は、JISかな配列のキー割り当てで
    # かなに読み替える（方針1-B: たｂご の ｂ → こ）。
    if not _is_kanji(ch):
        mapped = kana_for_ascii(ch)
        if mapped:
            return mapped

    if dict_index is not None:
        try:
            for r in dict_index.readings_for_surface(ch):
                # 単漢字の読みとして扱えるのは、かなだけのもの。
                # 送り仮名を含む読み（「かえ-る」等）は
                # ここでは扱いきれないので落とす。
                if r and all(_is_hiragana(c) or c == 'ー' for c in r):
                    if r not in out:
                        out.append(r)
        except Exception:
            pass

    try:
        import kanji_readings
        for r in kanji_readings.readings_of(ch):
            if r not in out:
                out.append(r)
    except Exception:
        pass

    # **UniDic から作った表で埋める**（うにさんの指定・2026-08-11）。
    #
    # うにさんのメモに出る漢字632種のうち、**284種（44%）は
    # ここまでで読みが1つも取れていなかった**。`格` `賀` もそこに
    # 入っていて、`性格` `賀古` は読みの候補がゼロだった
    # （＝関門で止まっていたのではなく、**土俵に上がれていなかった**）。
    #
    # 表は音読みを先に並べて返す。誤変換のもとになる読みは
    # たいてい熟語の音読みなので、そちらを先に試したい。
    try:
        import kanji_onkun
        for r in kanji_onkun.readings_of(ch):
            if r not in out:
                out.append(r)
    except Exception:
        pass

    return out


def reading_combos(text, dict_index=None, max_combos=MAX_COMBOS,
                   next_char=None):
    """
    漢字列がとりうる読みの組み合わせを、確からしい順に並べる。

    各文字の読みは「よく使う順」に並んでいるので、
    先頭どうしを組み合わせたものが最も確からしい。
    幅優先で広げ、上限に達したら打ち切る。

    戻り値: [読みの文字列, ...]
    """
    return [r for r, _rank in reading_combos_with_rank(text, dict_index,
                                                        max_combos,
                                                        next_char)]


def _okurigana_after(text, i, next_char):
    """
    その漢字の**すぐ後ろに続く平仮名**（送り仮名になりうる並び）。

    塊の中に在ればそれを、塊の最後の字なら `next_char` を見る
    （`_drop_okurigana_readings` と同じ見方）。無ければ ''。
    """
    if i + 1 < len(text):
        run = ''
        for c in text[i + 1:]:
            if not _is_hiragana(c):
                break
            run += c
        return run
    if next_char and _is_hiragana(next_char):
        return next_char
    return ''


def _trim_okurigana_from_readings(text, i, readings, next_char):
    """
    **送り仮名が続く漢字の読みが、その送り仮名で終わっているなら、
    送り仮名ぶんを削る**（項目48-KP・2026-08-28）。

    引き継ぎ H2（Opus・2026-08-27）が「**読みを作るところで直すのが
    本筋**」と名指ししていた根:

        `替` の音訓に `かえ` が在り、本文の送り仮名 `え` と繋ぐと
        **`きりかええじ`（え が二重）** ができる。48-KH/KI は
        「この塊は正しい」と先に言って**迂回した**だけで、
        **二重になる読みを作ること自体は直していない**。

    同じ形は `込(こみ)＋み` にも在る（`見込みが` → みこみみ）。
    **削るのは、送り仮名と実際に重なっているぶんだけ**——読みの
    お尻が、後ろに続く平仮名の頭と一致する長さ。

        替 かえ ＋ え   → か（え が重なる）
        込 こみ ＋ み   → こ
        替 かえ ＋ えて → か（えて の頭 え だけ重なる）

    **読みが丸ごと消える形は削らない**（`野`＝の に助詞 `の` が
    続く、`荷`＝に に `に` が続く——送り仮名ではなく助詞で、
    削ると読みが空になる）。

    `_drop_okurigana_readings`（送り仮名が**無い**ときに、送り仮名が
    要る読みを外す）と対になる。**あちらは無いとき・こちらは在るとき**で、
    どちらも `reading_combos_with_rank` と `_ime_segment_combos` の
    両方に掛ける（学び22——片方だけに置くと、そちらを迂回する）。
    """
    run = _okurigana_after(text, i, next_char)
    if not run:
        return readings
    out = []
    for r in readings:
        cut = 0
        for k in range(min(len(r) - 1, len(run)), 0, -1):
            if r[-k:] == run[:k]:
                cut = k
                break
        out.append(r[:-cut] if cut else r)
    # 削った結果、同じ読みが並ぶことがある（こみ・ごみ → こ・ご は
    # 別だが、表によっては重なる）。**順は保ったまま**重複を落とす。
    seen = set()
    got = []
    for r in out:
        if r and r not in seen:
            seen.add(r)
            got.append(r)
    return got or readings


def _drop_okurigana_readings(text, i, ch, readings, next_char):
    """
    **送り仮名が付いていない漢字から、送り仮名が要る読みを外す**
    （うにさんの指定・2026-08-11・項目48-AP）。

    「誤り・誤る・誤って」と**後ろに平仮名が付いて初めて**
    `誤` は **あやま** と読める。付いていなければ **ご**。
    だから `誤学習` は **ごがくしゅう**であって、
    あやまがくしゅう ではない（IMEに打っても出てこない）。

    **どこに平仮名があれば「付いている」と見るか**:

      塊の中の、その字より後ろのどこか。すぐ隣でなくてよい。
      複合動詞は送り仮名が後ろの字に付くため
      （**見切れ** の `れ` は `切` に付くが、`見` も み と読む）。

      塊の**最後の字**は、塊の外に何があるか分からない。
      `next_char` を貰っていればそれで見て、
      **貰っていなければ落とさない**（疑わしきは残す）。
      `見せる` の `見` を けん にしてしまわないため。

    表が無い環境でも動く（何も落とさないだけ）。
    """
    try:
        import okurigana
    except Exception:
        return readings
    for c in text[i + 1:]:
        if _is_hiragana(c):
            return readings
    if i == len(text) - 1:
        if next_char is None or _is_hiragana(next_char):
            return readings
    return okurigana.without_okurigana(ch, readings)


# --------------------------------------------------------------------
#  **IME から打った読み**を差す口（設計25(乙)）
# --------------------------------------------------------------------
#
# うにさんの指定（2026-08-20）:
#
#     「確定直前のひらがな情報を保持する実装を次に始めてください。
#       **ひらがながあれば、読みが分かるので自動補正します**」
#
# ここまでの読みは**逆算**（漢字を1字ずつ読みに戻して組み合わせる）
# だった。逆算には限界があり、`奥悠久子帝` は **`帝` の読みが
# どちらの表にも無い**ので **1つも組み合わせが作れなかった**
# （項目48-GU の壁①）。**1字でも欠けると塊全体が0になる。**
#
# IME は、打った本人が何と打ったかを知っている。**逆算ではなく
# 事実**なので、在るなら**先に**試す。
#
#   置き場は `ime_readings.py`（**語彙とは別**・学び2）。
#   ここは**引くだけ**。書くのは app.py の見張りだけ。
#
# **差していないときは、今までと1バイトも変わらない**
# （`_IME_READINGS_PROVIDER` が None なら素通り）。
# ものさし（readcheck / fpcheck / seedcheck / memodiff）は
# 差さずに回るので、**対が空なら diff は0行**になる。
_IME_READINGS_PROVIDER = None


def set_ime_readings_provider(fn):
    """
    「表記 → 打った読みの並び」を返す関数を差す（`None` で外す）。

    `app.py` が `IMEReadings.readings_for` を差す。
    **差さなければ何も変わらない**（今までどおり逆算だけ）。
    """
    global _IME_READINGS_PROVIDER
    _IME_READINGS_PROVIDER = fn


def ime_readings_for(text):
    """
    その表記について**打たれた読み**を返す（無ければ空）。

    保存済みの読みを最優先の材料として返す。今回の入力位置に
    結び付いた確定対とは断定しない。取得に失敗した場合は逆算へ進む。
    """
    fn = _IME_READINGS_PROVIDER
    if fn is None or not text:
        return []
    try:
        got = fn(text)
    except Exception:
        return []
    return [r for r in (got or ()) if r and isinstance(r, str)]


#: 音訓の型で足す点（項目48-PC）。**門ではなく順位**。
#:
#: **読み方が何通りかあって、どれが良いかは測って決める**（CN_PAT_RANK）:
#:
#:   'a'   塊まるごとで見る。音音 +0 ／ 表に在る混読み +1 ／
#:         表に無い混読み +2（Fable の指示書のまま）
#:   'b'   塊まるごと。**表に在る語は表の型を先頭に**（+0）・
#:         表と違う型は +2。表に無い語は 音音 +0／混読み +2
#:         （うにさんの言葉「そこに一致する単語はそのルールで読み、
#:           一致しないものは音音読みで分析する」のまま）
#:   'ap'  **隣り合う漢字の対ごと**に 'a' を当てて足す
#:   'bp'  **対ごと**に 'b' を当てて足す
#:   '0'   切る（今までどおり）
#:
#: **対ごとが要る理由**（実測・2026-09-03）: ②が呼ばれる塊は
#: 実機メモで 2,113 種あるが、**ちょうど2字の漢字はそのうち3種**
#: （のべ 5,270 回のうち 5 回）しかない。塊は「漢字とカタカナの
#: 連なり」で切られるので、**塊まるごとを表に当てても口を出せない**。
#: 表（2字の語）が効くのは、**塊の中の隣り合う2字**を見たときだけ。
_PATTERN_MODE = (__import__('os').environ.get('CN_PAT_RANK') or 'apr').lower()
_PATTERN_ADD_KNOWN = 1
_PATTERN_ADD_UNKNOWN = 2


#: 「その漢字2字は世の中の語か」の控え（同じ組を何度も引かない）。
_PAIR_IS_WORD = {}


def _pair_is_word(_ok, pair):
    """
    その漢字2字は、**世の中に在る語**か（項目48-PC）。

    **読みの型（重箱・湯桶・訓訓）は「語」の性質**なので、語でない
    切れ目に点を付けても意味がない。塊の中を2字ずつ滑らせると、
    `保存先` から `存先`・`一番下` から `番下`・`入力見` から `力見`
    のような**語の境目をまたいだ組**が出る——実測で、そこに点を
    付けると `ほぞんさき → ほぞんせん`・`いちばんした → いちばんか`
    のように**正しい訓読みを落としていた**。

    出どころは2つだけ（**名簿を増やさない**）——同梱の費用の表
    （`corrector._table_cost`・SudachiDict 由来）と、読みの型の表そのもの
    （`reading_patterns.json` の1,057語のうち45語は費用の表に無い）。
    """
    got = _PAIR_IS_WORD.get(pair)
    if got is not None:
        return got
    out = _ok.pattern_of(pair) is not None
    if not out:
        try:
            import corrector as _c
            out = _c._table_cost(pair) is not None
        except Exception:
            out = False
    if len(_PAIR_IS_WORD) > 20000:
        _PAIR_IS_WORD.clear()
    _PAIR_IS_WORD[pair] = out
    return out


#: 「その漢字2字の、世の中での読み」の控え。
_PAIR_READINGS = {}


def _pair_readings(pair):
    """
    同梱の表（`seed_japanese_cost`）が知っている、その2字の**読み**
    （項目48-PC・2026-09-03）。知らなければ空。

    **型（重箱・湯桶）より、読みそのもののほうが強い。** 型は音訓表の
    印から推すので `'?'` の穴でぶれる（`相手` の `あい` は印が `'?'` で
    形は音読み——表が「訓訓」と言っても、組み立て側が訓を作れない）。
    表が読みを持っているなら、**それに合うかどうかを直に聞く**。

        背中 ['せなか']            → せなか +0 ／ はいちゅう +2
        入力 ['にゅうりょく']      → にゅうりょく +0 ／ いりょく +2
        仮名 ['かな','がな','かめい','けみょう']
                                   → **どれも +0**（読みが何通りもある語に、
                                     型は何も言えない。`送り仮名` を
                                     `送り仮名` のまま残すのはここ）
    """
    got = _PAIR_READINGS.get(pair)
    if got is not None:
        return got
    try:
        import corrector as _c
        got = tuple(_c._table_readings_for_surface(pair) or ())
    except Exception:
        got = ()
    if len(_PAIR_READINGS) > 20000:
        _PAIR_READINGS.clear()
    _PAIR_READINGS[pair] = got
    return got


def _pair_penalty(_ok, pair, kinds, mode, reading=''):
    """漢字2字とその音訓の並びから、足す点を返す（項目48-PC）。"""
    if not _pair_is_word(_ok, pair):
        return 0                      # 語でない切れ目は、何も言わない
    # **表が読みを知っているなら、それが答え**（型より強い・上の説明）。
    # 連濁・音便（学校＝がっこう）は1字ずつの読みでは組めないので、
    # その語の組み合わせは**全部**外れて同じ点になる＝順は変わらない。
    if reading and 'r' in mode:
        known = _pair_readings(pair)
        if known:
            return 0 if reading in known else _PATTERN_ADD_UNKNOWN
    listed = _ok.pattern_of(pair)
    name = _ok.pattern_name(kinds)
    if mode.startswith('b') and listed:
        # 表に在る語は、**表の型が先頭**（うにさんの言葉のまま）
        return 0 if name == listed else _PATTERN_ADD_UNKNOWN
    if kinds[0] == 'on' and kinds[1] == 'on':
        return 0
    if listed and name == listed:
        return _PATTERN_ADD_KNOWN
    return _PATTERN_ADD_UNKNOWN


def _pattern_penalty(text, parts):
    """
    その読みの組み立ての**音訓の型**から、rank に足す点を返す
    （項目48-PC・2026-09-03・うにさんの提案）。

    > 「漢字の重箱読み、湯桶読みの一覧を作っておいて、そこに一致する
    >   単語はそのルールで読み、一致しないものは音音読みで分析する」

    **門にはしない**（`kanji_onkun.mixed_reading` の注記・
    `pattern_of` の説明）。落とすと `素帰任 → 確認`（すきにん）・
    `待ち外 → 間違い`（まちがい）・`田部井号して`（たぶい）が死ぬ
    ——**どれも混読みが的**。だから**下げるだけ**にする。

    parts: `text` の1字ずつに当てた読み（`text` と同じ長さ）。
    漢字でない字（かな・記号）は型を見ない。**漢字が2つ以上ある
    ときだけ**効く——1字の訓読み（`本`＝ほん／もと）は混読みでは
    ないので、点を付ける相手ではない。
    """
    mode = _PATTERN_MODE
    if mode in ('0', 'off', 'no'):
        return 0
    try:
        import kanji_onkun as _ok
    except Exception:
        return 0
    kinds = [(ch, _ok.on_or_kun(ch, r)) for ch, r in zip(text, parts)
             if _is_kanji(ch)]
    if len(kinds) < 2:
        return 0
    if 'p' in mode:
        # **隣り合う漢字の対ごと**。表（2字の語）が口を出せる唯一の形
        total = 0
        for i in range(len(text) - 1):
            a, b = text[i], text[i + 1]
            if not (_is_kanji(a) and _is_kanji(b)):
                continue
            total += _pair_penalty(_ok, a + b,
                                   (_ok.on_or_kun(a, parts[i]),
                                    _ok.on_or_kun(b, parts[i + 1])), mode,
                                   parts[i] + parts[i + 1])
        return total
    # 塊まるごと。表は**2字の語**だけなので、口を出せるのは2字の塊だけ
    if len(text) == 2 and len(kinds) == 2:
        return _pair_penalty(_ok, text, (kinds[0][1], kinds[1][1]), mode,
                             ''.join(parts))
    if all(k == 'on' for _c, k in kinds):
        return 0
    return _PATTERN_ADD_UNKNOWN


def reading_combos_with_rank(text, dict_index=None, max_combos=MAX_COMBOS,
                             next_char=None):
    """従来の読み・順位API。由来が必要な場合はwith_evidence版を使う。"""
    return _reading_combos_with_rank(text, dict_index, max_combos, next_char)


def reading_combos_with_evidence(text, dict_index=None, max_combos=MAX_COMBOS,
                                 next_char=None):
    """同じ一度の探索から、採用した読みの生成元を返す（48-WP）。

    保存対を今回の確定対と偽らない。順位は従来APIと同一。
    一字読みの辞書・音訓表の内訳や、今回の入力位置の証拠は未収録。
    """
    evidence = []
    _reading_combos_with_rank(text, dict_index, max_combos, next_char, evidence)
    return evidence


def _reading_combos_with_rank(text, dict_index=None, max_combos=MAX_COMBOS,
                              next_char=None, evidence=None):
    """
    reading_combos と同じだが、各組み合わせの
    「読みとしての確からしさ」を表す数値（rank）も一緒に返す。

    **打った読みが分かっているなら、それを先頭に置く**（設計25(乙)）。
    `set_ime_readings_provider` で差されているときだけ効く。
    逆算で1つも作れない塊（`奥悠久子帝`）でも、打った読みが
    在れば**そこだけは返す**。

    `next_char` は**塊のすぐ後ろの1文字**（行の中での次の文字）。
    最後の字に送り仮名が付いているかの判断だけに使う。
    渡さなければ「分からない」＝落とさない。

    rank は、その組み合わせを作るのに使った各文字の読みの
    優先順位（0が最も一般的）の合計。値が小さいほど、
    それぞれの漢字にとってより普通の読みだけで組み立てた
    組み合わせだということになる。

    「素」の読みは「そ」（rank 0）「す」（rank 1）のどちらも
    普通に使われる。combos を作る際の直積の順序だけで
    「どちらがより確からしいか」を決めてしまうと、他の文字の
    読みが2番目・3番目でも、たまたま先に出てきた組み合わせが
    優先されてしまう（実機で「素帰任」が「そきにん→責任」に
    先に届き、「すきにん→確認」より優先されてしまった）。
    rank を明示的に持たせることで、訂正コストと合わせて
    公平に比較できるようにする。

    戻り値: [(読みの文字列, rank), ...]
    """
    # **打った読み**（在れば）。逆算より先に置く。
    known = ime_readings_for(text)
    # **対で塊を切り分けた組み立て**（項目48-HB・案B）。
    # 塊まるごとの対が無いときだけ。対が空なら [] で、何も変わらない。
    segs = [] if known else _ime_segment_combos(text, dict_index, next_char)

    n = len(text)
    per_char = []
    for i, ch in enumerate(text):
        rs = readings_for_char(ch, dict_index)
        if not rs:
            # 1文字でも読めないなら組み合わせを作れない。
            # **ただし打った読みが在るなら、それは返す**
            # （`奥悠久子帝` は `帝` が読めず、ここで 0件だった）。
            # 対で切り分けた組み立て（segs）も同じ扱い。読めない字が
            # 対の中に覆われていれば、組み立ては作れている（48-HB）。
            return _reading_result(known, segs, [], evidence)
        rs = _drop_okurigana_readings(text, i, ch, rs, next_char)
        rs = _trim_okurigana_from_readings(text, i, rs, next_char)
        per_char.append(rs[:3])

    combos = [('', 0, 0, ())]
    for rs in per_char:
        new = []
        for prefix, prank, pchanged, pparts in combos:
            for idx, r in enumerate(rs):
                new.append((prefix + r, prank + idx,
                           pchanged + (1 if idx > 0 else 0),
                           pparts + (r,)))
                if len(new) >= max_combos:
                    break
            if len(new) >= max_combos:
                break
        combos = new
    # **音訓の型で順位を付ける**（項目48-PC）。足すだけ・消さない。
    combos = [(prefix, prank + _pattern_penalty(text, parts), pchanged)
              for prefix, prank, pchanged, parts in combos]
    # 確からしい順に並べる。
    #   1. rank（各漢字の読みの一般的さの合計）が小さい順
    #   2. 同じ rank なら、一般的でない読みを使った文字数が
    #      少ない順（1文字だけ別の読みにしたものを優先）
    # 2つ目の基準が無いと、直積の生成順序次第で
    # 「そきまか」（2文字を別の読みにした）が
    # 「すきにん」（1文字だけ別の読み）より前に来てしまい、
    # 上位だけを探索する際に本命を取りこぼす
    # （実機で「素帰任」が「確認」に届かなくなった原因）。
    combos.sort(key=lambda prc: (prc[1], prc[2]))
    return _reading_result(known, segs,
                           [(r, rank) for r, rank, _changed in combos], evidence)


def _reading_result(known, segments, guessed, evidence):
    """並べ替え・重複除去で実際に残った経路を記録。追加探索はしない。"""
    result = _with_ime_readings(known, _merge_by_rank(segments, guessed))
    if evidence is not None:
        # _merge_by_rankと同じ優先順。より低いrankの一字読みが勝つこともある。
        origins = {}
        tagged = ([(rank, 0, i, reading, 'saved_ime_segment_reconstruction')
                   for i, (reading, rank) in enumerate(segments)]
                  + [(rank, 1, i, reading, 'character_reading_reconstruction')
                     for i, (reading, rank) in enumerate(guessed)])
        for rank, _, _, reading, source in sorted(tagged):
            origins.setdefault(reading, source)
        for reading in known:
            origins[reading] = 'saved_ime_pair'
        for position, (reading, rank) in enumerate(result, 1):
            evidence.append(dict(reading=reading, rank=rank, order=position,
                                 source=origins[reading], occurrence_verified=False))
    return result


def _with_ime_readings(known, guessed):
    """
    **打った読み**を、逆算で作った読みの**前**に並べる（設計25(乙)）。

    known:   IME から取れた読み（新しい順）。無ければ空。
    guessed: 逆算で作った [(読み, rank), ...]

    - 打った読みの rank は **0**（いちばん確からしい）。
      負の値は使わない。rank は下流で訂正コストと足し合わされる
      ので、そこに負の値を持ち込むと比較の意味が変わる。
    - **同じ読みは重ねない。** 逆算でも同じ読みに届いていたら、
      前のほう（打った側）だけを残す。
    - **known が空なら guessed をそのまま返す**
      ＝差していない環境では今までと同じ答えになる。

    > **押し出されることに注意。** 呼ぶ側は `combos[:6]` で
    > 上から6つしか試さない（`corrector.py`）。打った読みを k 個
    > 前に置くと、逆算の下位 k 個は窓から出る。1表記あたりの
    > 読みはたいてい1つなので影響は小さいが、**0ではない**。
    """
    if not known:
        return guessed
    out = []
    seen = set()
    for r in known:
        if r and r not in seen:
            seen.add(r)
            out.append((r, 0))
    for r, rank in guessed:
        if r not in seen:
            seen.add(r)
            out.append((r, rank))
    return out


# --------------------------------------------------------------------
#  **対で塊を切り分けて読みを組み立てる**（項目48-HB・設計25(乙)の引き方）
# --------------------------------------------------------------------
#
# 対は「IME が一度に確定した範囲」で覚えるが、エンジンは「塊」で
# 読みを聞く。**塊は語ではない**（漢字・カタカナの連なりで切られる）
# ので、表記の完全一致では**実質引けない**ことが実機の51行で
# 確かめられた（項目48-HA §7-b・対のせいで変わった行 0件）。
#
# ここでは塊の**中**を対の表記で切り分ける:
#
#     該当あの範囲  =  該当(がいとう) + あ + の + 範囲(はんい)
#
# かなは素通し（表記＝読み）。対で覆えない字は、今までどおり
# 1字ずつの逆算（readings_for_char）で補う。
# **対を1つも使わなかった組み立ては返さない**（それは逆算と同じ
# ものなので、逆算の側に任せる）。
#
# 決めごと:
#   - **1文字だけの対は、塊の中では使わない。**
#     `表 → おもて` を持っていると、`時刻表` の中に「おもて」が
#     紛れ込む（正しい `じこくひょう` と並んでしまう）。
#     1文字の対は、塊まるごとの一致（known）でだけ効かせる。
#   - 対の読みは**新しい順に2つまで**。逆算の読みは**3つまで**
#     （per_char[:3] と同じ幅）。
#   - rank は「対＝0（打った事実）」「逆算＝読みの順位」の合計。
#     逆算と同じ物差しなので、下流の訂正コストとそのまま足せる。
#
# > **土俵が広がる向きの変更である**（項目48-GU の但し書きと同じ）。
# > 「その表記を打ったことがある」だけを根拠に、塊の一部へ読みを
# > 与える。`奥悠久子帝 → おくゆくこてい` のような**誤変換の対**が
# > 別の塊の中で使われる道もできる。使う向きは「漢字→読み」だけ
# > （学び2）は保っている。
_IME_SEG_MAX_SURFACE = 16    # 対の表記として試す最大の長さ
_IME_SEG_MIN_SURFACE = 2     # 1文字の対は塊の中では使わない（上記）
_IME_SEG_MAX_STATES = 4      # 位置ごとに残す組み立ての数
_IME_SEG_MAX_TEXT = 32       # これより長い塊では組み立てない
_IME_SEG_MAX_OUT = 3         # 返す組み立ての数


def _ime_segment_combos(text, dict_index=None, next_char=None):
    """
    塊 `text` を対の表記で切り分けて、読みの組み立てを返す。

    戻り値: [(読み, rank), ...]（対を1つ以上使えたものだけ・
            rank の小さい順・最大 _IME_SEG_MAX_OUT 件）。
    差されていない・対が空・覆えないときは []（＝何も変わらない）。
    """
    if _IME_READINGS_PROVIDER is None:
        return []
    n = len(text)
    if n < 2 or n > _IME_SEG_MAX_TEXT:
        return []

    # states[i] = [(読みの前半, rank, 使った対の数), ...]
    states = {0: [('', 0, 0)]}
    for i in range(n):
        cur = states.get(i)
        if not cur:
            continue
        # 位置ごとに、rank の小さい順で数を絞る（組み合わせ爆発を防ぐ）
        if len(cur) > _IME_SEG_MAX_STATES:
            cur.sort(key=lambda s: s[1])
            del cur[_IME_SEG_MAX_STATES:]
        # --- 対（長い表記から） ---
        top = min(n, i + _IME_SEG_MAX_SURFACE)
        for j in range(top, i + _IME_SEG_MIN_SURFACE - 1, -1):
            if j - i < _IME_SEG_MIN_SURFACE:
                break
            rds = ime_readings_for(text[i:j])
            if not rds:
                continue
            dst = states.setdefault(j, [])
            for k, rd in enumerate(rds[:2]):
                for prefix, rank, used in cur:
                    dst.append((prefix + rd, rank + k, used + 1))
        # --- 1文字（かなは素通し・漢字は逆算） ---
        ch = text[i]
        rs = readings_for_char(ch, dict_index)
        if rs:
            rs = _drop_okurigana_readings(text, i, ch, rs, next_char)
            rs = _trim_okurigana_from_readings(text, i, rs, next_char)
            dst = states.setdefault(i + 1, [])
            for idx, r in enumerate(rs[:3]):
                for prefix, rank, used in cur:
                    dst.append((prefix + r, rank + idx, used))

    got = [(r, rank) for r, rank, used in states.get(n, ())
           if used >= 1 and r]
    if not got:
        return []
    got.sort(key=lambda s: s[1])
    out = []
    seen = set()
    for r, rank in got:
        if r not in seen:
            seen.add(r)
            out.append((r, rank))
        if len(out) >= _IME_SEG_MAX_OUT:
            break
    return out


def _merge_by_rank(segs, guessed):
    """
    対で組み立てた読み（segs）と逆算の読み（guessed）を
    **rank の小さい順**に混ぜる。同じ rank なら対の側を前に
    （打った事実を含むぶんだけ確からしい）。同じ読みは重ねない。

    segs が空なら guessed をそのまま返す
    ＝**対が空なら今までと1バイトも変わらない**。
    """
    if not segs:
        return guessed
    tagged = ([(rank, 0, i, r) for i, (r, rank) in enumerate(segs)]
              + [(rank, 1, i, r) for i, (r, rank) in enumerate(guessed)])
    tagged.sort(key=lambda t: (t[0], t[1], t[2]))
    out = []
    seen = set()
    for rank, _src, _i, r in tagged:
        if r not in seen:
            seen.add(r)
            out.append((r, rank))
    return out


def looks_like_real_word(text, store, tokenize_fn=None):
    """
    その漢字列が「実在する語（またはその並び）」として通るか。

    通るなら誤変換ではないので、触ってはいけない。
    ここを緩くすると正しい文章を壊すため、判定は厳しめにする
    （疑わしきは「実在する」側に倒す）。
    """
    # 語彙ストアに、その表記が使用実績つきで載っている
    try:
        if store.reading_of(text):
            return True
    except Exception:
        pass

    # 形態素解析が、辞書にある語だけで分割できる。
    #
    # ここが本来の防波堤になる。「分割時」なら「分割」「時」の
    # 両方が janome の辞書に独立した語として載っているので、
    # 全ての語の読みが確定し、実在する語の並びと判断できる。
    if tokenize_fn is not None:
        try:
            toks = tokenize_fn(text)
        except Exception:
            toks = []
        if toks and ''.join(t[0] for t in toks) == text:
            # 全ての語が「読みが確定している（＝辞書にある）」なら、
            # 実在する語の並びとみなす。
            # ただし**固有名詞（人名・地名）は実在の根拠にしない**。
            # janome の辞書には「安吾（坂口安吾）」のような人名が
            # 載っており、「田安吾」（たあんご→単語 の誤変換）が
            # 「田＋安吾」と読めるせいで守られてしまった（実機）。
            # 固有名詞は IME の誤変換先にもなりやすい語であり、
            # 「読める」ことが「意図した語」を意味しない。
            # 本物の人名は敬称の直前の保護（_is_before_honorific）と、
            # その後の関門（語彙に届かなければ直さない）が守る。
            if all(t[5] for t in toks):
                if not any('固有名詞' in (t[1] or '') for t in toks):
                    return True
                # 固有名詞を含む場合、原則は実在の根拠にしない
                # （田安吾＝田＋安吾。上の説明のとおり）。
                # ただし **どのトークンも2文字以上（または接尾・
                # 接頭）** の並びは、固有名詞を含む正しい複合語と
                # みなす（山手＋線・日清＋戦争・鳥取＋自動車道・
                # 徳間＋文庫・日本＋市場）。これを実在扱いに
                # しないと、有名な地名・社名入りの複合語が
                # 当てずっぽうの探索に掛けられて 山手線→選手権・
                # 大正時代→音声時代 と壊れる（実機・2026-08-09）。
                # 1文字トークンは、語のうしろに付く接尾
                # （山手＋線 の 線）だけを許す。先頭の1文字
                # （田安吾 の 田、素帰任 の 素）は、名前・語の
                # 頭が化けた形と区別できないので守らない。
                #
                # 例外: **1文字の固有名詞が2つ隣り合っている**並びは
                # 許す。janome のビルドによっては 日中（日＋中）・
                # 日清（日＋清）のような日常の熟語が、1文字の固有名詞
                # 2つに割れて読まれる。この形は辞書に両方の字が
                # その読みで載っていることを意味し、実在する熟語の
                # 可能性が高い（実機で 日中→日常・日清戦争→実在戦争
                # と壊れた・2026-08-09）。田安吾（田安＋吾）のような
                # 寄せ集めは隣り合う1文字固有名詞にならないので、
                # 引き続き守らない。
                def _ok1(idx, t):
                    if len(t[0]) >= 2:
                        return True
                    pos1 = t[1] or ''
                    if idx > 0 and '接尾' in pos1:
                        return True
                    # 語のうしろに付く1文字の助詞・助動詞（思って の
                    # て）も、繋ぎとして自然な形なので許す
                    # （実機で 思って日中 が 思っ暑中 に化けた・
                    # 2026-08-09）。先頭の1文字は引き続き守らない。
                    if (idx > 0 and t[5]
                            and pos1.split(':')[0] in ('助詞', '助動詞')):
                        return True
                    if '固有名詞' in pos1 and t[5]:
                        for j in (idx - 1, idx + 1):
                            if 0 <= j < len(toks):
                                tj = toks[j]
                                if (len(tj[0]) == 1 and tj[5]
                                        and '固有名詞' in (tj[1] or '')):
                                    return True
                    return False
                if all(_ok1(idx, t) for idx, t in enumerate(toks)):
                    return True

    return False


def _seed_surfaces():
    """
    アプリがあらかじめ用意している初期語彙（seed_vocabulary.py）の
    表記の集合。キャッシュして毎回読み込み直さない。

    これはユーザーの使用回数（count）に一切依存しない、
    最初から確実に「正しい語」だと分かっている語の集合である。
    ユーザーの語彙は、検証時の貼り付けの繰り返しなどで
    使用回数が意図せず膨らむことがある（実機で確認された）。
    「分割」のような基本語を守る根拠を、そういった汚れうる数値
    ではなく、アプリが最初から知っている確実な語だけに置く。
    """
    global _SEED_SURFACES_CACHE
    if _SEED_SURFACES_CACHE is None:
        try:
            from seed_vocabulary import SEED_VOCABULARY
            _SEED_SURFACES_CACHE = {surface for _r, surface, _c
                                    in SEED_VOCABULARY}
        except Exception:
            _SEED_SURFACES_CACHE = set()
    return _SEED_SURFACES_CACHE


_SEED_SURFACES_CACHE = None


def strangeness(text, store, dict_index=None):
    """
    その漢字列の「異様さ」を測る。0〜3。大きいほど異様。

    どこまで踏み込んで推測してよいかを、この値で決める。
    異様であればあるほど「正しい語であるはずがない」ので、
    打鍵の誤りまで踏み込んで直しにいける。逆に、ふつうの熟語に
    見えるものは、辞書に無いだけの正しい語かもしれないので、
    軽い誤り（変換ミスだけ）しか直さない。

    「分割時」は日常の漢字が素直に並んだ、ごくふつうの熟語構造。
    辞書に無くても正しい語である可能性が高い（実機で
    「分割」を「分科」に壊した）。
    「素帰任」は、どの部分を取っても語にならず、
    漢字の組み合わせとして意味を成さない。こちらは
    2箇所直してでも「確認」に届けにいく価値がある。

    ユーザーの使用回数（count）には頼らない。
    以前は「塊の一部が、使用実績のある既知語なら安全」という
    判定をしていたが、これは語彙が育つほど脆くなる。
    たとえば検証中の貼り付けの繰り返しで「帰任」の使用回数だけが
    人工的に積み上がると、無関係な「素帰任」まで「帰任を含むから
    安全」と誤って保護してしまう（実機で確認された）。
    「帰任をいくら使っていても、素帰任の不自然さとは無関係」
    という指摘のとおり、部分一致による安全側の判定こそが
    ここでは危険因子になる。

    そこで、既知語かどうかは **塊全体が丸ごと1語として辞書にあるか**
    （janome の逆引き・自前の単漢字表）だけで判定し、
    使用回数や部分一致には頼らない。
    """
    score = 0

    # 日常では使わない漢字が入っている（魔訶 の「訶」）
    if _has_rare_kanji(text):
        score += 2

    # カタカナと漢字が混ざっている（タン子）。
    # 正しい日本語では、この混ざり方はまず起こらない。
    has_kata = any(_is_katakana(c) and c not in _SMALL_KATAKANA
                   for c in text)
    if has_kata and any(_is_kanji(c) for c in text):
        score += 2

    # 漢字の間に送り仮名が挟まっている（見切れ魔訶）。
    # 熟語なら漢字が続くはずで、途中でかなを挟んだ形は
    # 変換の失敗を示す。
    inner_kana = any(_is_hiragana(c) for c in text[1:-1])

    # 塊全体が、確実な語の集合に丸ごと1語として載っているか。
    # ユーザーの使用回数には頼らない:
    #   1. アプリの初期語彙（seed_vocabulary.py）に載っている
    #      これは count に関係なく、最初から正しいと分かっている語
    #   2. janome 辞書の逆引き（dict_index）に載っている
    # どちらも「塊の一部が既知語」ではなく「塊そのもの」を見る。
    # 部分一致で判定すると、「素帰任」が「帰任」を含むという
    # だけで安全とみなされてしまう（実機で確認された誤り。
    # 「帰任をいくら使っていても、素帰任の不自然さとは無関係」
    # という指摘のとおり）。
    if text in _seed_surfaces():
        return 0
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(text):
                return 0
        except Exception:
            pass

    # 塊のどの部分を取っても、確実な語（シード語彙・辞書）の
    # 全体一致が無い。
    #
    # 「分割時」は塊全体としては辞書に無くても、内部を
    # 「分割」＋「時」に区切れば、少なくとも一方（「分割」）が
    # シード語彙・辞書に丸ごと一致する。このように、塊の一部を
    # 切り出して確実な語と完全一致するかどうかは見てよい
    # （count には頼らない、辞書・シード語彙との「全体一致」の
    #   範囲でだけ判断するので、「帰任」のような汚染された
    #   使用回数の影響は受けない——ただし「帰任」自体は
    #   シード語彙にも辞書にも無い語なので、ここでも
    #   「素帰任」を保護する材料にはならない）。
    if not _has_solid_part(text, dict_index):
        score += 2
        # 送り仮名の挟まりを踏み込みの根拠にするのは、
        # 確実な語の部分一致が無いときだけにする。
        #
        # 「取り違（え）」「切り出（し）」「引き受（ける）」のような
        # 活用語の頭は、塊の切り出しが最後の漢字で止まるため
        # 「漢字＋かな＋漢字」の形になり、送り仮名の挟まりと
        # 区別が付かない。ここで +1 すると1箇所の訂正が許され、
        # 「取り違」→「種類」「切り出し」→「説明し」のような
        # 破壊が起きた（実機で発生。直後が「」等の記号だと
        # 送り仮名込みの実在語チェックでも守れない）。
        # 「取り」「切り」のような確実な部分一致がある塊は、
        # 実在する活用語の頭である可能性が高いので踏み込まない。
        if inner_kana:
            score += 1

    return min(score, 3)


def _has_solid_part(text, dict_index=None):
    """
    塊の一部（2文字以上）が、確実な語の集合
    （シード語彙・janome辞書）に丸ごと一致するか。

    ユーザーの語彙（count）は一切見ない。汚染された使用回数に
    左右されない、確実な語の集合だけを根拠にする。
    """
    seed = _seed_surfaces()
    n = len(text)
    for size in range(n, 1, -1):
        for i in range(0, n - size + 1):
            part = text[i:i + size]
            if part in seed:
                return True
            if dict_index is not None:
                try:
                    if dict_index.readings_for_surface(part):
                        return True
                except Exception:
                    pass
    return False


def _is_solid_known_word(part, store, dict_index=None, min_count=2):
    """
    その部分文字列が「十分に使われている、確からしい既知語」か。

    reading_of は表記から読みを引くだけなので、たまたま1回だけ
    学習された語（誤変換の副産物や、極めて稀な用法）まで
    「既知語」として拾ってしまう。ユーザーの語彙が育つほど、
    偶然の部分一致で「素帰」「帰任」のような、実際には
    ありえない並びまで既知語扱いされる余地が生まれる
    （実機の7000語を超える語彙で「素帰任」が異様と判定されなく
      なった原因）。
    使用実績（count）がある程度高いものだけを、判断の材料にする。
    """
    try:
        reading = store.reading_of(part)
    except Exception:
        reading = None
    if reading:
        try:
            entries = store.lookup(reading)
        except Exception:
            entries = []
        for e in entries:
            if e.get('surface') == part and e.get('count', 0) >= min_count:
                return True
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(part):
                return True
        except Exception:
            pass
    return False


def _contains_known_part(text, store, dict_index=None):
    """
    塊の一部（2文字以上、かつ塊自体より短い）に、既知の語が現れるか。

    塊がちょうど2文字の場合（「分割」等）、それより短い2文字以上の
    部分文字列は存在しないため、この判定だけでは常に False になる。
    そのままだと2文字の塊は「既知語を含まない＝異様」という
    判定に自動的に倒れてしまう（実機で「分割」を壊した原因）。
    2文字の塊については、表記そのものが既知語かどうかを見る。
    """
    n = len(text)
    if n == 2:
        return _is_solid_known_word(text, store, dict_index)

    for size in range(n - 1, 1, -1):
        for i in range(0, n - size + 1):
            part = text[i:i + size]
            if part == text:
                continue
            if _is_solid_known_word(part, store, dict_index):
                return True
    return False


def _suggest_cache_key(text, store, min_count, at_sentence_end):
    """
    推測結果をキャッシュするための鍵。

    同じ塊に対する推測は、語彙が変わらない限り同じ結果になる。
    メモの中に同じ誤字が何度も出てくる場合や、編集のたびに
    全行を解析し直す場合に、同じ重い探索を繰り返さずに済む。

    語彙の規模（件数）を鍵に含めることで、語を覚えたあとは
    自動的にキャッシュが作り直される。
    """
    try:
        vocab_size = len(store._by_reading)
    except Exception:
        vocab_size = -1
    return (text, vocab_size, min_count, at_sentence_end)


_SUGGEST_CACHE = {}
_SUGGEST_CACHE_LIMIT = 2000


def suggest_for_run(text, store, find_readings, dict_index=None,
                    tokenize_fn=None, max_dist=1.6, max_edits=3,
                    min_count=2, at_sentence_end=False,
                    context_vec=None, surrounding_words=None):
    """
    ありえない漢字列に対して、届きうる語を1つ提案する。

    読みの組み合わせを確からしい順に試し、
      1. その読みそのものが既知の語 → それを採る（誤変換のみ）
      2. 打ち間違いとして訂正すると既知の語に届く → それを採る
    という順に見る。1を先に見るのは、打鍵は正しく変換だけが
    誤っている場合（「時ッ層」＝じっそう→実装）を、
    打ち間違いの推測より優先するため。

    **採否の最終判断はここではしない**。呼び出し側（corrector.py）が
    既存の基準で判断できるよう、材料を返すだけにする。

    戻り値: (提案する表記, カテゴリ, 元になった読み) または None
    """
    # 文脈で結果が変わりうる場合（周辺語を見て選び分ける場合）は
    # キャッシュしない。それ以外は同じ塊なら同じ結果になる。
    cacheable = not (context_vec is not None and surrounding_words)
    cache_key = None
    if cacheable:
        cache_key = _suggest_cache_key(text, store, min_count,
                                       at_sentence_end)
        if cache_key in _SUGGEST_CACHE:
            return _SUGGEST_CACHE[cache_key]

    result = _suggest_for_run_uncached(
        text, store, find_readings, dict_index=dict_index,
        tokenize_fn=tokenize_fn, max_dist=max_dist, max_edits=max_edits,
        min_count=min_count, at_sentence_end=at_sentence_end,
        context_vec=context_vec, surrounding_words=surrounding_words)

    if cacheable and cache_key is not None:
        if len(_SUGGEST_CACHE) >= _SUGGEST_CACHE_LIMIT:
            _SUGGEST_CACHE.clear()
        _SUGGEST_CACHE[cache_key] = result
    return result


def _suggest_for_run_uncached(text, store, find_readings, dict_index=None,
                              tokenize_fn=None, max_dist=1.6, max_edits=3,
                              min_count=2, at_sentence_end=False,
                              context_vec=None, surrounding_words=None):
    """suggest_for_run の中身（キャッシュを挟まない実処理）。"""
    if looks_like_real_word(text, store, tokenize_fn):
        return None

    combos_ranked = reading_combos_with_rank(text, dict_index)
    if not combos_ranked:
        return None
    combos = [r for r, _rk in combos_ranked]

    # --- 1. 読みそのものが既知の語（変換だけが誤っている） ---
    for reading in combos:
        entries = [e for e in store.lookup(reading)
                   if e['count'] >= min_count]
        if not entries:
            continue
        if len(entries) >= 2:
            # 同じ読みに有力な表記が複数ある。どれかは決められないが、
            # 「今の漢字列がありえない」ことは分かっているので、
            # 最もよく使われているものを採る。
            entries.sort(key=lambda e: -e['count'])
        best = entries[0]
        if best['surface'] != text and _is_safe_replacement(text, best):
            return (best['surface'], best['category'], reading)

    # --- 2. 打ち間違いを訂正すると既知の語に届く ---
    # 確からしい組み合わせから順に見て、最初に見つかったものを返す。
    #
    # ここは「ありえない漢字列」という手がかりだけを頼りに、
    # 打鍵の誤りまで推測する、最も踏み込んだ判断になる。
    # 辞書に無いだけの正しい熟語（「分割時」のような、
    # よくある語でも初期の語彙には無いもの）を巻き込むと
    # 正しい文章を壊すため、通常の補正より強い証拠を求める:
    #
    #   - 訂正できる箇所数は、その塊の「異様さ」で決める
    #     （異様であるほど、正しい語である見込みが無いので
    #       踏み込んで直せる。ふつうの熟語に見えるものは
    #       辞書に無いだけの正しい語かもしれないので控える）
    #   - 読みの長さが変わらないこと（既に変換が確定している以上、
    #     打鍵の誤りなら文字数は保たれているはず）
    #   - 届いた先が、十分に使われている語であること
    strange = strangeness(text, store, dict_index)
    if strange <= 0:
        # ふつうの熟語に見える。変換の誤り（1.）だけを直し、
        # 打鍵の推測まではしない。
        edit_limit = 0
    elif strange == 1:
        edit_limit = 1
    else:
        edit_limit = 2

    # 全ての読みの組み合わせを見た上で、最も自然な訂正を選ぶ。
    #
    # 「素」の読みは「そ」「す」のどちらもあり得るため、同じ塊から
    # 複数のもっともらしい訂正先（「責任」「確認」等）に届くことが
    # ある。どちらも正しい日本語であり、機械的には決め手が無い
    # （実機で「素帰任」が「責任」に直ったが「確認」を期待されていた、
    #   という報告があった）。
    #
    # そこで、訂正コストが拮抗している候補が複数見つかった場合は、
    # 文脈ベクトル（周辺の語との意味的な近さ）を追加の手がかりに
    # する。それも無ければ、最も訂正コストの低いもの
    # （最も打ち間違いとして自然なもの）を機械的に選ぶ
    # ——これは必ずしもユーザーの意図と一致するとは限らないが、
    # その場合は選び直し（右クリック・F2）で直せる。
    # 打ち間違いの探索（find_readings）は、語彙が育つほど重くなる
    # 総当たりに近い処理で、1回あたり数ミリ秒かかる。
    # 読みの組み合わせすべて（最大8通り）に掛けると、1つの塊に
    # 数十ミリ秒を要し、行数の多いメモでは起動時の全行解析だけで
    # 何秒もかかってしまう（実機で「起動に9秒かかる」と報告された）。
    #
    # ただし絞りすぎると本命を取りこぼす（「素帰任」の正解に至る
    # 「すきにん」は、確からしさの順で4番目に来ることがある）。
    # 塊ごとの結果はキャッシュされるので、同じ塊を何度も
    # 調べ直す費用は掛からない。取りこぼさない程度に広く見る。
    SEARCH_COMBOS = 6
    searched = set()    # 同じ読みを二度探索しない

    candidates_found = []   # [(key, surface, category, cand_reading), ...]
    for reading, reading_rank in combos_ranked[:SEARCH_COMBOS]:
        if edit_limit <= 0:
            break
        if reading in searched:
            continue
        searched.add(reading)
        try:
            found = find_readings(reading, store, max_dist=max_dist,
                                  max_edits=max_edits)
        except Exception:
            continue
        for cand_reading, cost, edits in found:
            if edits == 0:
                continue
            if edits > edit_limit:
                continue
            # 訂正後の読みの長さが変わるものは採らない。
            # 短くなるのは語を削る補正（文字化→文）、
            # 長くなるのは無い文字を足す補正で、どちらも
            # 「変換が確定した文字列の打ち直し」としては不自然。
            if len(cand_reading) != len(reading):
                continue
            # 訂正が「打ち間違いとして自然か」は corrector.py の
            # 基準をそのまま借りる（判断の物差しを増やさない）。
            try:
                import corrector
                if not corrector.is_plausible_typo(reading, cost, edits):
                    continue
            except Exception:
                pass
            entries = [e for e in store.lookup(cand_reading)
                       if e['count'] >= min_count]
            if not entries:
                continue
            entries.sort(key=lambda e: -e['count'])
            best = entries[0]
            if best['surface'] == text or not _is_safe_replacement(
                    text, best):
                continue
            key = reading_rank + cost
            candidates_found.append(
                (key, best['surface'], best['category'], cand_reading))

    if candidates_found:
        # 同点（key が同じ）候補の順序を表記・読みで確定させる。
        # 並び順が探索順（＝起動ごとに揺れうる順）のままだと、
        # 同じメモでも起動のたびに違う候補が「最良」になる。
        candidates_found.sort(key=lambda c: (c[0], c[1], c[3]))
        top_key = candidates_found[0][0]
        # 最良の候補と僅差（0.3以内）のものを、拮抗している候補として集める。
        # 僅差でなければ、迷わずその1つを採る。
        tied = [c for c in candidates_found if c[0] - top_key <= 0.3]
        tied_surfaces = sorted({c[1] for c in tied})
        if len(tied_surfaces) >= 2 and context_vec is not None \
                and surrounding_words:
            picked = context_vec.pick_best_by_context(
                tied_surfaces, surrounding_words)
            if picked:
                for c in tied:
                    if c[1] == picked:
                        return (c[1], c[2], c[3])
        best_c = candidates_found[0]
        return (best_c[1], best_c[2], best_c[3])

    # --- 3. 文末なら、活用語尾を補って探す ---
    # 「見切れ魔訶。」の「まか」は、打ち間違いとしては「ます」に近い。
    # しかし「見切れます」のような活用した形は語彙に載りにくく、
    # 語幹だけを探しても届かない。文末にある塊に限って、
    # 語尾を差し替えた形も入口として試す
    # （文末以外でこれをやると、語尾の付け替えで無関係な語に
    #   化けやすいので、範囲を絞る）。
    if at_sentence_end:
        for reading in combos[:4]:
            for variant in _tail_variants(reading):
                entries = [e for e in store.lookup(variant)
                           if e['count'] >= min_count]
                if not entries:
                    continue
                entries.sort(key=lambda e: -e['count'])
                best = entries[0]
                if best['surface'] != text and _is_safe_replacement(text, best):
                    return (best['surface'], best['category'], variant)

    return None


def _is_safe_replacement(text, entry):
    """
    その置き換えが「壊さない」と言えるか。

    ありえない漢字列だと分かっていても、置き換え先が極端に短いと
    語を削るだけの改悪になる。
      「文字化」（ぶんじか）→「文」（ぶん）
    元の漢字列は誤変換とはいえ、打った文字数ぶんの情報を持っている。
    それが半分以下になるような置き換えは、別の語に化けたと見て
    採らない（取りこぼしは我慢できるが、破壊は我慢できない
    という、このアプリの一貫した方針）。
    """
    new_surface = entry['surface']
    if len(new_surface) * 2 < len(text):
        return False
    return True
