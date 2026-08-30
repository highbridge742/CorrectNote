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
**かなで書いたアルファベットの読みを、英字に戻す**（項目48-IZ）。

    エフ2               → F2
    えふ2               → F2
    エフエフ9           → FF9
    えいちでぃーえむあい → HDMI
    えいちでーえむあい   → HDMI

うにさんの指定（2026-08-23）「平仮名かカタカナでアルファベットの
発音を書いたらアルファベットに補正する」。項目48-IB で「いまの経路に
無い機能」として残していた5組がこれにあたる。

**ここは表と分解だけを持つ。** 「触ってよい並びか」の門は
`corrector.py` 側に置く（表の在庫・助詞・前後の字を見る必要があり、
それはこのモジュールの仕事ではない）。**名簿は1つ**の決まりどおり、
字→読みの表はここ1つだけにする。

読みの選び方:

- **1字につき、実際に打たれる形だけを挙げる。** 「びい」「しい」の
  ような、長音符を使わない書き方は**入れていない**——`しい`（椎・
  思い）のような普通の語と衝突する。長音符が要る、というのが
  そのまま「アルファベットを綴っている」証拠になっている。
- `ジー`(G) と `ズィー`(Z) は分けてある。`ゼット`(Z) も入れた。
- `エー`(A) と `エイ`(H の頭) が前で重なるので、**分解は
  長いほうから試して総当たりで戻る**（前から貪欲に取るだけだと
  `えいち` を `えい`＋`ち` と切って失敗する）。
"""

# 字 → その字を口で言うときのかな（**ここ1つが名簿**）。
LETTER_READINGS = {
    'A': ('えー', 'えい'),
    'B': ('びー',),
    'C': ('しー', 'すぃー'),
    'D': ('でぃー', 'でー', 'ぢー'),
    'E': ('いー',),
    'F': ('えふ',),
    'G': ('じー',),
    'H': ('えいち', 'えっち', 'えーち'),
    'I': ('あい',),
    'J': ('じぇー', 'じぇい'),
    'K': ('けー', 'けい'),
    'L': ('える', 'える'),
    'M': ('えむ',),
    'N': ('えぬ',),
    'O': ('おー',),
    'P': ('ぴー',),
    'Q': ('きゅー',),
    'R': ('あーる',),
    'S': ('えす',),
    'T': ('てぃー', 'てー'),
    'U': ('ゆー',),
    'V': ('ぶい', 'ゔい'),
    'W': ('だぶりゅー', 'だぶるゆー', 'だぶりゅ'),
    'X': ('えっくす',),
    'Y': ('わい',),
    'Z': ('ぜっと', 'ずぃー'),
}

# 読み → 字（引く側）。同じ読みが2つの字に付くことは無い
# （`じー`=G と `ずぃー`=Z のように、わざと分けてある）。
_BY_READING = {}
for _ch, _rds in LETTER_READINGS.items():
    for _rd in _rds:
        _BY_READING.setdefault(_rd, _ch)

# 長いものから試す（`えいち` を `えい`＋`ち` に切らないため）
_READINGS_LONGEST = tuple(sorted(_BY_READING, key=len, reverse=True))

_MAX_READING = max(len(r) for r in _BY_READING)


def to_hiragana(text):
    """カタカナをひらがなに寄せる（`ー` と `ヴ` はそのまま扱う）。"""
    out = []
    for ch in text:
        if ch == 'ヴ':
            out.append('ゔ')
        elif 'ァ' <= ch <= 'ヶ':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def is_kana_char(ch):
    """ひらがな・カタカナ・長音符か。"""
    return ('ぁ' <= ch <= 'ゖ') or ('ァ' <= ch <= 'ヶ') or ch == 'ー'


def spell_out(kana):
    """
    かなの並びを**まるごと**字の並びに読み替える。

    全部が字の読みで説明できるときだけ答えを返す。1文字でも
    余ったら **None**（部分一致では返さない——「読める形だけ触る」）。

    答えが2通りあるときは**字数の少ないほう**を採る（人が綴るときは
    長い読みから当てるため。`えいち` は `H` であって `A`+`ち` ではない）。
    """
    if not kana:
        return None
    s = to_hiragana(kana)
    n = len(s)
    # best[i] = i 文字目まで綴ったときの、いちばん短い字の並び
    best = [None] * (n + 1)
    best[0] = ''
    for i in range(n):
        if best[i] is None:
            continue
        for rd in _READINGS_LONGEST:
            j = i + len(rd)
            if j > n:
                continue
            if s[i:j] != rd:
                continue
            cand = best[i] + _BY_READING[rd]
            if best[j] is None or len(cand) < len(best[j]):
                best[j] = cand
    return best[n]


def trailing_digits(text, start):
    """
    `start` から続く数字（半角・全角）の長さ。

    `エフ2` のように**字1つ＋数字**でも綴りとして意味が通る形が
    あるので、呼ぶ側がここを見て門をゆるめる。
    """
    i = start
    while i < len(text) and (text[i].isdigit()
                             or '０' <= text[i] <= '９'):
        i += 1
    return i - start
